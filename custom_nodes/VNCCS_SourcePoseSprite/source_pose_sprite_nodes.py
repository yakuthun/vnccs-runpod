import json
import os
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


_IDENTITY_PRIORITY_MARKER = "[VNCCS_IDENTITY_PRIORITY]"
_IDENTITY_PRIORITY_PATCHED = False


def _install_identity_priority_generator_patch():
    """Give image2 identity priority only for explicitly marked No-3D runs.

    VNCCS CharacterCloneGenerator normally hard-codes image1 and image2 to
    equal reference-latent weights.  That is appropriate for ordinary pose
    generation, but a close source portrait can then donate its haircut to the
    target.  The marker keeps every other VNCCS workflow on the stock path.
    """
    global _IDENTITY_PRIORITY_PATCHED
    if _IDENTITY_PRIORITY_PATCHED:
        return

    import nodes as comfy_nodes

    generator_cls = comfy_nodes.NODE_CLASS_MAPPINGS.get("VNCCS_CharacterCloneGenerator")
    extractor_cls = comfy_nodes.NODE_CLASS_MAPPINGS.get("VNCCS_MaskExtractor")
    if generator_cls is None or extractor_cls is None:
        return
    if getattr(generator_cls, "_vnccs_identity_priority_patch", False):
        _IDENTITY_PRIORITY_PATCHED = True
        return

    original = generator_cls._run_pose_generation

    def _run_pose_generation_identity_priority(
        self, poses, character, pipe, prompt, settings, lora_info=None, background="Green"
    ):
        prompt_text = str(prompt or "")
        if _IDENTITY_PRIORITY_MARKER not in prompt_text:
            return original(
                self,
                poses,
                character,
                pipe,
                prompt,
                settings,
                lora_info=lora_info,
                background=background,
            )

        prompt_text = prompt_text.replace(_IDENTITY_PRIORITY_MARKER, "").strip()
        pipe_values = self._extract_pipe(pipe)
        pose_parts = self._image_list(poses)
        character_rgb = extractor_cls().fill_alpha_with_color(character)[0]
        prompt_text = self._prompt_with_solid_background(prompt_text, background)

        positive_list, negative_list, latent_list = self._run_list_mapped(
            "VNCCS_QWEN_Encoder",
            {"image1": pose_parts},
            clip=pipe_values["clip"],
            vae=pipe_values["vae"],
            prompt=prompt_text,
            image2=character_rgb,
            target_size=int(settings["target_size"]),
            upscale_method="lanczos",
            crop_method="disabled",
            image1_name="Pose, action, crop and placement only",
            image2_name="Exclusive target identity, face, hair and outfit",
            image3_name="Unused",
            weight1=0.45,
            weight2=1.40,
            weight3=0.0,
            vl_size=512,
            background_color=str(background or "White"),
            latent_image_index=1,
            instruction=(
                "Image 1 controls only visible pose geometry, action, object contact, camera, crop, scale and placement. "
                "Image 2 is the exclusive authority for identity, face, hairstyle, haircut, hair length, hair volume, "
                "bangs, color, clothing and visual design. Never blend or copy identity, face, hair or clothing from "
                "image 1. Rebuild the target character entirely from image 2 while preserving image 1's action and framing."
            ),
            qwen_2511=True,
        )

        sampler_model = self._apply_pose_lora_to_model(
            pipe_values["model"], pipe_values["clip"], pipe, lora_info
        )
        for index, (positive, negative) in enumerate(zip(positive_list, negative_list), start=1):
            self._validate_conditioning_for_model(
                pipe_values, positive, negative, f"Identity-priority pose item {index}"
            )
        sampled_list = self._run_list_mapped(
            "KSampler",
            {"positive": positive_list, "negative": negative_list, "latent_image": latent_list},
            model=sampler_model,
            seed=pipe_values["seed"],
            steps=pipe_values["steps"],
            cfg=pipe_values["cfg"],
            sampler_name=pipe_values["sampler"],
            scheduler=pipe_values["scheduler"],
            denoise=1,
        )[0]
        decoded_list = self._run_list_mapped(
            "VAEDecodeTiled",
            {"samples": sampled_list},
            vae=pipe_values["vae"],
            tile_size=512,
            overlap=64,
            temporal_size=64,
            temporal_overlap=8,
        )[0]
        return self._safe_image_batch(decoded_list, stage="identity-priority pose generation decode")

    generator_cls._run_pose_generation = _run_pose_generation_identity_priority
    generator_cls._vnccs_identity_priority_patch = True
    _IDENTITY_PRIORITY_PATCHED = True


def _first_image(value):
    while isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("Görsel listesi boş.")
        value = value[0]
    if not torch.is_tensor(value):
        raise TypeError("IMAGE tensörü bekleniyordu.")
    if value.ndim == 3:
        value = value.unsqueeze(0)
    return value.float().clamp(0, 1)


def _first_mask(value, height, width):
    while isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("Maske listesi boş.")
        value = value[0]
    if not torch.is_tensor(value):
        raise TypeError("MASK tensörü bekleniyordu.")
    if value.ndim == 2:
        value = value.unsqueeze(0)
    value = value[:1].float().clamp(0, 1)
    if tuple(value.shape[-2:]) != (height, width):
        value = F.interpolate(value.unsqueeze(1), (height, width), mode="bilinear", align_corners=False)[:, 0]
    return value


def _bbox(mask, threshold=0.02):
    ys, xs = torch.where(mask[0] > threshold)
    if xs.numel() == 0:
        raise ValueError("Kişi maskesi boş.")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _background_rgb(name):
    name = str(name or "Green").lower()
    if name == "blue":
        return (0.0, 0.0, 1.0)
    return (0.0, 1.0, 0.0)


def _clean_generated_green_alpha(sprite):
    """Suppress chroma-screen remnants while retaining the generated person's alpha."""
    array = sprite[0].detach().cpu().numpy()
    rgb = array[..., :3]
    alpha = array[..., 3]

    # VNCCS BG Remove + SAM3 supplies the initial alpha. This only removes residual
    # green-screen texture that Qwen occasionally paints instead of flat #00ff00.
    green_dominance = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])
    chroma_keep = 1.0 - np.clip((green_dominance - 0.015) / 0.11, 0.0, 1.0)
    clean_alpha = alpha * chroma_keep
    clean_alpha = np.clip((clean_alpha - 0.12) / 0.88, 0.0, 1.0)

    candidate = (clean_alpha > 0.08).astype(np.uint8)
    separated = cv2.erode(candidate, np.ones((5, 5), np.uint8), iterations=1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(separated, 8)
    if count <= 1:
        raise ValueError("Uretilen hedef karakterin temizlenebilir foreground bileseni bulunamadi.")
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    support = cv2.dilate((labels == largest).astype(np.uint8), np.ones((13, 13), np.uint8), iterations=1)
    clean_alpha *= support.astype(np.float32)

    result = sprite.clone()
    result[0, ..., 3] = torch.from_numpy(clean_alpha).to(device=result.device, dtype=result.dtype)
    return result


class VNCCSAlignPoseGuideToSource:
    """Places the real Pose Studio render on a source-sized solid-color canvas."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pose_guide": ("IMAGE",),
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "background": (["Green", "Blue"], {"default": "Green"}),
                "scale_multiplier": ("FLOAT", {"default": 0.92, "min": 0.5, "max": 1.25, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("pose_guide_preview",)
    FUNCTION = "align"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def align(self, pose_guide, source_scene, source_person_mask, background, scale_multiplier):
        guide = _first_image(pose_guide)[0, ..., :3]
        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask)

        bg = torch.tensor(_background_rgb(background), dtype=guide.dtype, device=guide.device)
        # Pose Studio renders a solid screen. Keep the actual rendered body and discard that screen.
        distance = torch.linalg.vector_norm(guide - bg.view(1, 1, 3), dim=-1)
        foreground = (distance > 0.10).float().unsqueeze(0)
        gx0, gy0, gx1, gy1 = _bbox(foreground)
        crop_rgb = guide[gy0:gy1, gx0:gx1].permute(2, 0, 1).unsqueeze(0)
        crop_a = foreground[:, gy0:gy1, gx0:gx1].unsqueeze(1)

        target_h = max(8, int(round((sy1 - sy0) * float(scale_multiplier))))
        scale = target_h / max(1, gy1 - gy0)
        target_w = max(8, int(round((gx1 - gx0) * scale)))
        max_w = max(8, source_w - 8)
        max_h = max(8, source_h - 8)
        if target_w > max_w or target_h > max_h:
            fit = min(max_w / target_w, max_h / target_h)
            target_w = max(8, int(round(target_w * fit)))
            target_h = max(8, int(round(target_h * fit)))

        resized_rgb = F.interpolate(crop_rgb, (target_h, target_w), mode="bilinear", align_corners=False)[0].permute(1, 2, 0)
        resized_a = F.interpolate(crop_a, (target_h, target_w), mode="bilinear", align_corners=False)[0, 0].clamp(0, 1)

        source_bottom_x = (sx0 + sx1) / 2.0
        source_bottom_y = float(sy1)
        x = int(round(source_bottom_x - target_w / 2.0))
        y = int(round(source_bottom_y - target_h))
        x = min(max(0, x), max(0, source_w - target_w))
        y = min(max(0, y), max(0, source_h - target_h))

        canvas = bg.view(1, 1, 3).expand(source_h, source_w, 3).clone()
        region = canvas[y:y + target_h, x:x + target_w]
        alpha = resized_a.unsqueeze(-1)
        canvas[y:y + target_h, x:x + target_w] = resized_rgb * alpha + region * (1.0 - alpha)
        return (canvas.unsqueeze(0).cpu(),)


class VNCCSSpritePlacement:
    """Builds tight and source-sized RGBA sprites using only the generated alpha."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generated_character": ("IMAGE",),
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "tight_padding": ("INT", {"default": 24, "min": 0, "max": 256, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("target_character_tight", "target_character_full_canvas", "placement_json")
    FUNCTION = "place"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def place(self, generated_character, source_scene, source_person_mask, tight_padding):
        sprite = _first_image(generated_character)
        if sprite.shape[-1] < 4:
            raise ValueError("Üretilen hedef karakterde gerçek alpha kanalı yok; BG Remove çıktısını bağlayın.")
        sprite = sprite[:1, ..., :4]
        alpha = sprite[..., 3]
        if float(alpha.max()) <= 0.02 or float(alpha.min()) >= 0.98:
            raise ValueError("Üretilen hedef karakterin alpha kanalı geçerli bir foreground maskesi içermiyor.")

        sprite = _clean_generated_green_alpha(sprite)
        alpha = sprite[..., 3]

        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask)
        gx0, gy0, gx1, gy1 = _bbox(alpha)

        sprite_h, sprite_w = sprite.shape[1:3]
        pad = int(tight_padding)
        core = sprite[:, gy0:gy1, gx0:gx1].clone()
        tight = torch.zeros(
            (1, core.shape[1] + pad * 2, core.shape[2] + pad * 2, 4),
            dtype=core.dtype,
            device=core.device,
        )
        tight[:, pad:pad + core.shape[1], pad:pad + core.shape[2]] = core

        source_bbox_h = max(1, sy1 - sy0)
        generated_bbox_h = max(1, gy1 - gy0)
        native_scale = source_bbox_h / generated_bbox_h
        scaled_h = max(1, int(round(tight.shape[1] * native_scale)))
        scaled_w = max(1, int(round(tight.shape[2] * native_scale)))

        # Never cut the newly generated hair, clothes, hands or feet at canvas edges.
        safe_margin = min(24, max(1, source_w // 20), max(1, source_h // 20))
        fit_scale = min(1.0, (source_w - safe_margin * 2) / scaled_w, (source_h - safe_margin * 2) / scaled_h)
        scale = native_scale * fit_scale
        scaled_h = max(1, int(round(tight.shape[1] * scale)))
        scaled_w = max(1, int(round(tight.shape[2] * scale)))
        scaled = F.interpolate(tight.permute(0, 3, 1, 2), (scaled_h, scaled_w), mode="bilinear", align_corners=False).permute(0, 2, 3, 1)

        source_bottom = ((sx0 + sx1) / 2.0, float(sy1))
        generated_bottom_x_in_tight = pad + (gx1 - gx0) / 2.0
        generated_bottom_y_in_tight = pad + (gy1 - gy0)
        x = int(round(source_bottom[0] - generated_bottom_x_in_tight * scale))
        y = int(round(source_bottom[1] - generated_bottom_y_in_tight * scale))
        x = min(max(0, x), max(0, source_w - scaled_w))
        y = min(max(0, y), max(0, source_h - scaled_h))

        full = torch.zeros((1, source_h, source_w, 4), dtype=scaled.dtype)
        full[:, y:y + scaled_h, x:x + scaled_w] = scaled.cpu()

        source_center = [(sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0]
        source_bottom_center = [source_bottom[0], source_bottom[1]]
        pelvis = [(sx0 + sx1) / 2.0, sy0 + (sy1 - sy0) * 0.56]
        edge_contact = {
            "left": gx0 <= 1,
            "top": gy0 <= 1,
            "right": gx1 >= sprite_w - 1,
            "bottom": gy1 >= sprite_h - 1,
        }
        placement = {
            "source_width": int(source_w),
            "source_height": int(source_h),
            "source_person_bbox": [sx0, sy0, sx1, sy1],
            "source_person_center": source_center,
            "source_bottom_center": source_bottom_center,
            "estimated_seat_or_pelvis_anchor": pelvis,
            "generated_sprite_bbox": [gx0, gy0, gx1, gy1],
            "recommended_x": int(x),
            "recommended_y": int(y),
            "scale": float(scale),
            "generated_alpha_edge_contact": edge_contact,
            "alpha_source": "newly_generated_target_character",
            "alpha_cleanup": "VNCCS BG Remove + SAM3 details recovery, chroma residual suppression, largest generated foreground component",
        }
        return (tight.cpu(), full, json.dumps(placement, ensure_ascii=False, indent=2))


class VNCCSCanvasLockedSpritePackage:
    """Keeps the generated pose in its native source-canvas coordinates."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generated_character": ("IMAGE",),
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "tight_padding": ("INT", {"default": 24, "min": 0, "max": 256, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("target_character_tight", "target_character_full_canvas", "placement_json")
    FUNCTION = "package"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def package(self, generated_character, source_scene, source_person_mask, tight_padding):
        sprite = _first_image(generated_character)
        if sprite.shape[-1] < 4:
            raise ValueError("Generated target character has no real alpha channel; connect VNCCS BG Remove output.")
        sprite = sprite[:1, ..., :4]
        alpha = sprite[..., 3]
        if float(alpha.max()) <= 0.02 or float(alpha.min()) >= 0.98:
            raise ValueError("Generated target alpha does not contain a valid foreground mask.")
        sprite = _clean_generated_green_alpha(sprite)
        alpha = sprite[..., 3]

        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask)

        sprite_h, sprite_w = sprite.shape[1:3]
        gx0, gy0, gx1, gy1 = _bbox(alpha)
        pad = int(tight_padding)
        core = sprite[:, gy0:gy1, gx0:gx1].clone()
        tight = torch.zeros(
            (1, core.shape[1] + pad * 2, core.shape[2] + pad * 2, 4),
            dtype=core.dtype,
            device=core.device,
        )
        tight[:, pad:pad + core.shape[1], pad:pad + core.shape[2]] = core

        if (sprite_h, sprite_w) == (source_h, source_w):
            full = sprite.clone()
        else:
            full = F.interpolate(
                sprite.permute(0, 3, 1, 2),
                (source_h, source_w),
                mode="bilinear",
                align_corners=False,
            ).permute(0, 2, 3, 1).clamp(0, 1)

        full_alpha = full[..., 3]
        fx0, fy0, fx1, fy1 = _bbox(full_alpha)
        source_center = [(sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0]
        source_bottom_center = [(sx0 + sx1) / 2.0, float(sy1)]
        generated_center = [(fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0]
        generated_bottom_center = [(fx0 + fx1) / 2.0, float(fy1)]
        pelvis = [(sx0 + sx1) / 2.0, sy0 + (sy1 - sy0) * 0.56]
        placement = {
            "source_width": int(source_w),
            "source_height": int(source_h),
            "source_person_bbox": [sx0, sy0, sx1, sy1],
            "source_person_center": source_center,
            "source_bottom_center": source_bottom_center,
            "estimated_seat_or_pelvis_anchor": pelvis,
            "generated_sprite_bbox": [fx0, fy0, fx1, fy1],
            "generated_sprite_center": generated_center,
            "generated_bottom_center": generated_bottom_center,
            "recommended_x": 0,
            "recommended_y": 0,
            "scale": 1.0,
            "canvas_resize_scale_x": float(source_w / max(1, sprite_w)),
            "canvas_resize_scale_y": float(source_h / max(1, sprite_h)),
            "center_delta": [generated_center[0] - source_center[0], generated_center[1] - source_center[1]],
            "bottom_center_delta": [generated_bottom_center[0] - source_bottom_center[0], generated_bottom_center[1] - source_bottom_center[1]],
            "alignment_mode": "source_canvas_locked_no_post_placement",
            "alpha_source": "newly_generated_target_character",
            "alpha_cleanup": "VNCCS BG Remove + SAM3 details recovery, chroma residual suppression, largest generated foreground component",
            "tight_sprite_keeps_upscaled_resolution": True,
        }
        return (tight.cpu(), full.cpu(), json.dumps(placement, ensure_ascii=False, indent=2))


class VNCCSAdaptivePoseGuide:
    """Uses Pose Studio when its render is valid, otherwise keeps the visible source framing."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pose_studio_guide": ("IMAGE",),
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "background": (["Green", "Blue"], {"default": "Green"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("adaptive_pose_guide", "framing_json")
    FUNCTION = "prepare"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def prepare(self, pose_studio_guide, source_scene, source_person_mask, background):
        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask, threshold=0.5)

        guide = _first_image(pose_studio_guide)[0, ..., :3]
        bg = torch.tensor(_background_rgb(background), dtype=guide.dtype, device=guide.device)
        distance = torch.linalg.vector_norm(guide - bg.view(1, 1, 3), dim=-1)
        raw_foreground = (distance > 0.10).detach().cpu().numpy().astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(raw_foreground, 8)
        if count > 1:
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            guide_foreground = (labels == largest).astype(np.uint8)
            gx = stats[largest, cv2.CC_STAT_LEFT]
            gy = stats[largest, cv2.CC_STAT_TOP]
            gw = stats[largest, cv2.CC_STAT_WIDTH]
            gh = stats[largest, cv2.CC_STAT_HEIGHT]
            garea = stats[largest, cv2.CC_STAT_AREA]
        else:
            guide_foreground = np.zeros_like(raw_foreground)
            gx = gy = gw = gh = garea = 0

        guide_h, guide_w = raw_foreground.shape
        guide_height_ratio = gh / max(1, guide_h)
        guide_width_ratio = gw / max(1, guide_w)
        guide_fill_ratio = garea / max(1, gw * gh)
        floor_like = guide_width_ratio > 0.85 and guide_height_ratio < 0.35
        pose_valid = bool(
            garea > max(256, int(guide_h * guide_w * 0.008))
            and guide_height_ratio >= 0.35
            and guide_fill_ratio >= 0.025
            and not floor_like
        )

        source_touch = {
            "left": sx0 <= 2,
            "top": sy0 <= 2,
            "right": sx1 >= source_w - 2,
            "bottom": sy1 >= source_h - 2,
        }
        source_bbox = [sx0, sy0, sx1, sy1]
        edge_contacts = sum(bool(value) for value in source_touch.values())
        source_bbox_width_ratio = (sx1 - sx0) / max(1, source_w)
        source_bbox_height_ratio = (sy1 - sy0) / max(1, source_h)
        source_is_extreme_crop = bool(
            edge_contacts >= 3
            or (source_bbox_width_ratio >= 0.90 and source_bbox_height_ratio >= 0.85)
        )

        if pose_valid and not source_is_extreme_crop:
            aligned = VNCCSAlignPoseGuideToSource().align(
                pose_studio_guide,
                source_scene,
                source_person_mask,
                background,
                1.0,
            )[0]
            mode = "pose_studio_valid_bottom_anchor"
        else:
            # A severely cropped person has too little evidence for reliable 3D
            # reconstruction: SAM may invent off-screen legs and move the face. Build
            # an identity-suppressed gray contour guide from only the visible pixels.
            # It preserves the exact visible pose/framing without carrying hair,
            # clothing or skin colors strongly enough to compete with image2.
            rgb_np = source[0, ..., :3].detach().cpu().numpy()
            mask_np = source_mask[0].detach().cpu().numpy().clip(0, 1)
            gray = cv2.cvtColor(np.clip(rgb_np * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
            smooth = cv2.GaussianBlur(gray.astype(np.float32) / 255.0, (0, 0), 5.0)
            inside = mask_np > 0.30
            mean_luma = float(smooth[inside].mean()) if np.any(inside) else 0.5
            neutral_luma = np.clip(0.56 + (smooth - mean_luma) * 0.20, 0.42, 0.70)
            edges = cv2.Canny(gray, 55, 135)
            edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1) > 0
            neutral_luma[edges & inside] = 0.28
            body = np.repeat(neutral_luma[..., None], 3, axis=-1)
            screen_np = np.asarray(_background_rgb(background), dtype=np.float32).reshape(1, 1, 3)
            matte = mask_np[..., None].astype(np.float32)
            neutral = body * matte + screen_np * (1.0 - matte)
            aligned = torch.from_numpy(neutral.astype(np.float32)).unsqueeze(0)
            mode = "source_neutral_pose_fallback_center_anchor"

        framing = {
            "mode": mode,
            "pose_studio_valid": pose_valid,
            "pose_component_bbox": [int(gx), int(gy), int(gx + gw), int(gy + gh)],
            "pose_component_height_ratio": float(guide_height_ratio),
            "pose_component_width_ratio": float(guide_width_ratio),
            "pose_component_fill_ratio": float(guide_fill_ratio),
            "source_width": int(source_w),
            "source_height": int(source_h),
            "source_person_bbox": source_bbox,
            "source_mask_edge_contact": source_touch,
            "source_is_extreme_crop": source_is_extreme_crop,
        }
        return (aligned, json.dumps(framing, ensure_ascii=False, indent=2))


class VNCCSNeutralContourPoseGuide:
    """Build an identity-suppressed visible-pose guide without any 3D inference."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "background": (["Green", "Blue"], {"default": "Green"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("neutral_pose_guide", "framing_json")
    FUNCTION = "prepare"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def prepare(self, source_scene, source_person_mask, background):
        _install_identity_priority_generator_patch()
        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask, threshold=0.5)

        rgb_np = source[0, ..., :3].detach().cpu().numpy()
        mask_np = source_mask[0].detach().cpu().numpy().clip(0, 1)
        gray = cv2.cvtColor(
            np.clip(rgb_np * 255.0, 0, 255).astype(np.uint8),
            cv2.COLOR_RGB2GRAY,
        )
        smooth = cv2.GaussianBlur(gray.astype(np.float32) / 255.0, (0, 0), 5.0)
        inside = mask_np > 0.30
        mean_luma = float(smooth[inside].mean()) if np.any(inside) else 0.5
        neutral_luma = np.clip(0.56 + (smooth - mean_luma) * 0.20, 0.42, 0.70)
        edges = cv2.Canny(gray, 55, 135)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1) > 0

        # The source person's exact hair silhouette and facial line art are identity
        # information, not pose information.  Passing those lines through image1
        # makes Qwen preserve the source haircut even when image2 has very different
        # hair.  Replace the upper/head portion with a smooth generic face oval while
        # retaining the exact lower-body contour and pose lines.
        bbox_w = max(1, sx1 - sx0)
        bbox_h = max(1, sy1 - sy0)
        head_zone_end = min(source_h, sy0 + max(1, int(round(bbox_h * 0.37))))
        guide_matte = mask_np.copy()
        guide_matte[sy0:head_zone_end, :] = 0.0

        upper = inside[sy0:head_zone_end, sx0:sx1]
        upper_y, upper_x = np.where(upper)
        if upper_x.size >= 16:
            ux0, ux1 = int(upper_x.min()), int(upper_x.max()) + 1
            uy0, uy1 = int(upper_y.min()), int(upper_y.max()) + 1
            upper_w = max(1, ux1 - ux0)
            upper_h = max(1, uy1 - uy0)
            center = (
                int(round(sx0 + (ux0 + ux1 - 1) * 0.5)),
                int(round(sy0 + (uy0 + uy1 - 1) * 0.5)),
            )
            axes = (
                max(8, int(round(upper_w * 0.32))),
                max(10, int(round(upper_h * 0.43))),
            )
        else:
            center = (
                int(round((sx0 + sx1) * 0.5)),
                int(round(sy0 + bbox_h * 0.19)),
            )
            axes = (
                max(8, int(round(bbox_w * 0.22))),
                max(10, int(round(bbox_h * 0.16))),
            )

        generic_head = np.zeros((source_h, source_w), dtype=np.float32)
        cv2.ellipse(generic_head, center, axes, 0.0, 0.0, 360.0, 1.0, -1)
        head_blur = max(1.25, min(bbox_w, bbox_h) * 0.006)
        generic_head = cv2.GaussianBlur(generic_head, (0, 0), head_blur)
        guide_matte = np.maximum(guide_matte, generic_head)

        # Keep pose/clothing geometry below the head, but remove every source
        # face/hair edge.  The target reference can then freely rebuild bangs,
        # length and volume outside the neutral oval.
        edges[sy0:head_zone_end, :] = False
        neutral_luma[generic_head > 0.02] = 0.56
        neutral_luma[edges & (guide_matte > 0.30)] = 0.28
        body = np.repeat(neutral_luma[..., None], 3, axis=-1)
        screen_np = np.asarray(_background_rgb(background), dtype=np.float32).reshape(1, 1, 3)
        matte = guide_matte[..., None].astype(np.float32)
        guide = body * matte + screen_np * (1.0 - matte)

        source_touch = {
            "left": sx0 <= 2,
            "top": sy0 <= 2,
            "right": sx1 >= source_w - 2,
            "bottom": sy1 >= source_h - 2,
        }
        framing = {
            "mode": "source_neutral_pose_no3d_center_anchor",
            "pose_studio_valid": False,
            "uses_3d_pose_inference": False,
            "source_width": int(source_w),
            "source_height": int(source_h),
            "source_person_bbox": [sx0, sy0, sx1, sy1],
            "source_head_identity_suppressed": True,
            "generic_head_zone_end": int(head_zone_end),
            "source_mask_edge_contact": source_touch,
            "source_is_extreme_crop": bool(
                sum(bool(value) for value in source_touch.values()) >= 3
                or ((sx1 - sx0) / max(1, source_w) >= 0.90 and (sy1 - sy0) / max(1, source_h) >= 0.85)
            ),
        }
        return (
            torch.from_numpy(guide.astype(np.float32)).unsqueeze(0),
            json.dumps(framing, ensure_ascii=False, indent=2),
        )


class VNCCSAdaptiveSpritePlacement:
    """Aligns full-body renders by feet and cropped renders by their visible bbox center."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generated_character": ("IMAGE",),
                "source_scene": ("IMAGE",),
                "source_person_mask": ("MASK",),
                "framing_json": ("STRING", {"forceInput": True}),
                "tight_padding": ("INT", {"default": 24, "min": 0, "max": 256, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("target_character_tight", "target_character_full_canvas", "placement_json")
    FUNCTION = "place"
    CATEGORY = "VNCCS/Source Pose Sprite"

    @staticmethod
    def _paste_clipped(canvas, patch, x, y):
        _, canvas_h, canvas_w, _ = canvas.shape
        _, patch_h, patch_w, _ = patch.shape
        dst_x0 = max(0, x)
        dst_y0 = max(0, y)
        dst_x1 = min(canvas_w, x + patch_w)
        dst_y1 = min(canvas_h, y + patch_h)
        if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
            raise ValueError("Adaptive placement moved the generated character completely outside the source canvas.")
        src_x0 = dst_x0 - x
        src_y0 = dst_y0 - y
        src_x1 = src_x0 + (dst_x1 - dst_x0)
        src_y1 = src_y0 + (dst_y1 - dst_y0)
        canvas[:, dst_y0:dst_y1, dst_x0:dst_x1] = patch[:, src_y0:src_y1, src_x0:src_x1]

    def place(self, generated_character, source_scene, source_person_mask, framing_json, tight_padding):
        sprite = _first_image(generated_character)
        if sprite.shape[-1] < 4:
            raise ValueError("Generated target character has no real alpha channel; connect VNCCS BG Remove output.")
        sprite = _clean_generated_green_alpha(sprite[:1, ..., :4])
        source = _first_image(source_scene)
        source_h, source_w = source.shape[1:3]
        source_mask = _first_mask(source_person_mask, source_h, source_w)
        sx0, sy0, sx1, sy1 = _bbox(source_mask, threshold=0.5)
        framing = json.loads(framing_json or "{}")
        mode = str(framing.get("mode", "pose_studio_valid_bottom_anchor"))

        native_h, native_w = sprite.shape[1:3]
        base = F.interpolate(
            sprite.permute(0, 3, 1, 2),
            (source_h, source_w),
            mode="bilinear",
            align_corners=False,
        ).permute(0, 2, 3, 1).clamp(0, 1)
        gx0, gy0, gx1, gy1 = _bbox(base[..., 3])
        core = base[:, gy0:gy1, gx0:gx1].clone()

        source_bbox_w = max(1, sx1 - sx0)
        source_bbox_h = max(1, sy1 - sy0)
        generated_bbox_w = max(1, gx1 - gx0)
        generated_bbox_h = max(1, gy1 - gy0)

        source_edges = framing.get("source_mask_edge_contact", {}) or {}
        edge_contacts = sum(bool(source_edges.get(side)) for side in ("left", "top", "right", "bottom"))
        source_width_ratio = source_bbox_w / max(1, source_w)
        source_height_ratio = source_bbox_h / max(1, source_h)
        source_is_tight_or_cropped = bool(
            mode.startswith("source_cutout_fallback")
            or edge_contacts >= 2
            or source_width_ratio >= 0.85
            or source_height_ratio >= 0.85
        )

        if source_is_tight_or_cropped:
            # A close-up or edge-cropped source must fill the same visible bbox.
            # The generated sprite may be a complete body even though the source
            # shows only part of it, so scale by the dominant extent and clip only
            # the full-canvas overlay.  The separate tight PNG remains untouched.
            placement_scale = max(source_bbox_w / generated_bbox_w, source_bbox_h / generated_bbox_h)
            placement_scale = float(np.clip(placement_scale, 0.50, 3.00))
            target_w = max(1, int(round(generated_bbox_w * placement_scale)))
            target_h = max(1, int(round(generated_bbox_h * placement_scale)))
            source_anchor = ((sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0)
            x = int(round(source_anchor[0] - target_w / 2.0))
            y = int(round(source_anchor[1] - target_h / 2.0))
            anchor_type = "visible_bbox_center_bbox_matched"
        else:
            # For ordinary full-body framing, match the source person's height and
            # keep the feet/contact point fixed.  This avoids side-to-side drift
            # without turning a standing sprite into an accidental close-up.
            placement_scale = float(np.clip(source_bbox_h / generated_bbox_h, 0.50, 3.00))
            target_w = max(1, int(round(generated_bbox_w * placement_scale)))
            target_h = max(1, int(round(generated_bbox_h * placement_scale)))
            source_anchor = ((sx0 + sx1) / 2.0, float(sy1))
            x = int(round(source_anchor[0] - target_w / 2.0))
            y = int(round(source_anchor[1] - target_h))
            anchor_type = "bottom_center"

        patch = F.interpolate(
            core.permute(0, 3, 1, 2),
            (target_h, target_w),
            mode="bilinear",
            align_corners=False,
        ).permute(0, 2, 3, 1).clamp(0, 1)
        full = torch.zeros((1, source_h, source_w, 4), dtype=patch.dtype)
        self._paste_clipped(full, patch.cpu(), x, y)

        # Tight output keeps the native upscaler resolution and never uses the source mask.
        na = sprite[..., 3]
        nx0, ny0, nx1, ny1 = _bbox(na)
        native_core = sprite[:, ny0:ny1, nx0:nx1].clone()
        pad = int(tight_padding)
        tight = torch.zeros(
            (1, native_core.shape[1] + pad * 2, native_core.shape[2] + pad * 2, 4),
            dtype=native_core.dtype,
            device=native_core.device,
        )
        tight[:, pad:pad + native_core.shape[1], pad:pad + native_core.shape[2]] = native_core

        fx0, fy0, fx1, fy1 = _bbox(full[..., 3])
        placement = {
            "source_width": int(source_w),
            "source_height": int(source_h),
            "source_person_bbox": [sx0, sy0, sx1, sy1],
            "generated_bbox_before_alignment": [gx0, gy0, gx1, gy1],
            "generated_bbox_after_alignment_visible": [fx0, fy0, fx1, fy1],
            "framing_mode": mode,
            "anchor_type": anchor_type,
            "source_edge_contacts": int(edge_contacts),
            "source_is_tight_or_cropped": source_is_tight_or_cropped,
            "anchor": [float(source_anchor[0]), float(source_anchor[1])],
            "recommended_x": int(x),
            "recommended_y": int(y),
            "scale": float(placement_scale),
            "native_generated_width": int(native_w),
            "native_generated_height": int(native_h),
            "alpha_source": "newly_generated_target_character",
            "source_mask_used_for": "framing and placement metadata only",
        }
        return (tight.cpu(), full.cpu(), json.dumps(placement, ensure_ascii=False, indent=2))


class VNCCSSavePoseSpritePackage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pose_guide_preview": ("IMAGE",),
                "target_character_tight": ("IMAGE",),
                "target_character_full_canvas": ("IMAGE",),
                "placement_json": ("STRING", {"forceInput": True}),
                "output_directory": ("STRING", {"default": "/workspace"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_paths",)
    FUNCTION = "save"
    CATEGORY = "VNCCS/Source Pose Sprite"
    OUTPUT_NODE = True

    @staticmethod
    def _save_image(value, path):
        image = _first_image(value)[0].detach().cpu().numpy()
        array = np.clip(np.rint(image * 255.0), 0, 255).astype(np.uint8)
        mode = "RGBA" if array.shape[-1] == 4 else "RGB"
        Image.fromarray(array, mode=mode).save(path, format="PNG")

    def save(self, pose_guide_preview, target_character_tight, target_character_full_canvas, placement_json, output_directory):
        output_directory = os.path.abspath(str(output_directory or "/workspace"))
        os.makedirs(output_directory, exist_ok=True)
        paths = {
            "pose_guide_preview": os.path.join(output_directory, "pose_guide_preview.png"),
            "target_character_tight": os.path.join(output_directory, "target_character_tight.png"),
            "target_character_full_canvas": os.path.join(output_directory, "target_character_full_canvas.png"),
            "placement": os.path.join(output_directory, "placement.json"),
        }
        self._save_image(pose_guide_preview, paths["pose_guide_preview"])
        self._save_image(target_character_tight, paths["target_character_tight"])
        self._save_image(target_character_full_canvas, paths["target_character_full_canvas"])
        parsed = json.loads(placement_json)
        with open(paths["placement"], "w", encoding="utf-8") as handle:
            json.dump(parsed, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return (json.dumps(paths, ensure_ascii=False, indent=2),)


class VNCCSAutoPersonMask:
    """Segment exactly one source person with VNCCS' installed BiRefNet helper."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",)}}

    RETURN_TYPES = ("MASK", "STRING")
    RETURN_NAMES = ("person_mask", "person_bbox")
    FUNCTION = "segment"
    CATEGORY = "VNCCS/Source Pose Sprite"

    def segment(self, source):
        custom_nodes_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if custom_nodes_dir not in sys.path:
            sys.path.insert(0, custom_nodes_dir)
        try:
            from ComfyUI_VNCCS_Utils.vnccs_sam3d.processing.birefnet_mask import auto_mask_bgr
        except ImportError as exc:
            raise ImportError(
                "VNCCS_AutoPersonMask requires the ComfyUI_VNCCS_Utils package installed by VNCCS."
            ) from exc

        image = _first_image(source)
        rgb = np.clip(image[0, ..., :3].detach().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        mask, boxes = auto_mask_bgr(rgb[..., ::-1].copy())
        count = 0 if boxes is None else len(boxes)
        if mask is None or count != 1:
            raise ValueError(
                f"Kaynak sahnede tam olarak bir kişi bekleniyor; bulunan kişi sayısı: {count}."
            )
        value = np.asarray(mask, dtype=np.float32)
        if value.ndim == 3:
            value = value[0]
        bbox = np.asarray(boxes[0]).reshape(-1).tolist()
        return (
            torch.from_numpy(value).unsqueeze(0).clamp(0, 1),
            json.dumps(bbox, ensure_ascii=False),
        )


NODE_CLASS_MAPPINGS = {
    "VNCCS_AutoPersonMask": VNCCSAutoPersonMask,
    "VNCCS_AlignPoseGuideToSource": VNCCSAlignPoseGuideToSource,
    "VNCCS_SpritePlacement": VNCCSSpritePlacement,
    "VNCCS_CanvasLockedSpritePackage": VNCCSCanvasLockedSpritePackage,
    "VNCCS_AdaptivePoseGuide": VNCCSAdaptivePoseGuide,
    "VNCCS_NeutralContourPoseGuide": VNCCSNeutralContourPoseGuide,
    "VNCCS_AdaptiveSpritePlacement": VNCCSAdaptiveSpritePlacement,
    "VNCCS_SavePoseSpritePackage": VNCCSSavePoseSpritePackage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VNCCS_AutoPersonMask": "VNCCS Auto Person Mask (BiRefNet)",
    "VNCCS_AlignPoseGuideToSource": "VNCCS Align Pose Guide To Source Canvas",
    "VNCCS_SpritePlacement": "VNCCS New-Alpha Sprite Tight Crop + Placement",
    "VNCCS_CanvasLockedSpritePackage": "VNCCS Canvas-Locked Transparent Sprite Package",
    "VNCCS_AdaptivePoseGuide": "VNCCS Adaptive Pose Guide (Validated Pose / Cropped Fallback)",
    "VNCCS_NeutralContourPoseGuide": "VNCCS Neutral Contour Pose Guide (No 3D)",
    "VNCCS_AdaptiveSpritePlacement": "VNCCS Adaptive Sprite Placement (Full / Close-up Anchors)",
    "VNCCS_SavePoseSpritePackage": "VNCCS Save Transparent Sprite Package",
}
