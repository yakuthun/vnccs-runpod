import json
import torch
import torch.nn.functional as F
import numpy as np
import os
import sys


def _mask4(mask):
    if mask.ndim == 2:
        mask = mask.unsqueeze(0)
    return mask.float().clamp(0, 1)


class VNCCSMaskChoice:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"automatic_mask": ("MASK",)},
                "optional": {"manual_mask": ("MASK",)}}
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("person_mask",)
    FUNCTION = "choose"
    CATEGORY = "VNCCS/Masked Replacement"

    def choose(self, automatic_mask, manual_mask=None):
        if manual_mask is not None and float(manual_mask.max()) > 0.001:
            return (_mask4(manual_mask),)
        mask = _mask4(automatic_mask)
        if float(mask.max()) <= 0.001:
            raise ValueError("Kaynak sahnede tek bir kişi maskesi bulunamadı; manuel maske yükleyin.")
        if mask.shape[0] != 1:
            raise ValueError("Birden fazla kişi bulundu; tek kişilik manuel maske yükleyin.")
        return (mask,)


class VNCCSAutoPersonMask:
    """Uses VNCCS' installed BiRefNet person masker (the same SAM3D import helper)."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",)}}
    RETURN_TYPES = ("MASK", "STRING")
    RETURN_NAMES = ("person_mask", "person_bbox")
    FUNCTION = "segment"
    CATEGORY = "VNCCS/Masked Replacement"

    def segment(self, source):
        custom_nodes_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if custom_nodes_dir not in sys.path:
            sys.path.insert(0, custom_nodes_dir)
        from ComfyUI_VNCCS_Utils.vnccs_sam3d.processing.birefnet_mask import auto_mask_bgr
        rgb = (source[0, ..., :3].detach().cpu().clamp(0, 1).numpy() * 255).astype(np.uint8)
        bgr = rgb[..., ::-1].copy()
        mask, boxes = auto_mask_bgr(bgr)
        if mask is None or boxes is None or len(boxes) != 1:
            count = 0 if boxes is None else len(boxes)
            raise ValueError(f"Kaynak sahnede tam olarak bir kişi bekleniyor; bulunan kişi sayısı: {count}.")
        m = np.asarray(mask, dtype=np.float32)
        if m.ndim == 3:
            m = m[0]
        box = np.asarray(boxes[0]).reshape(-1).tolist()
        return (torch.from_numpy(m).unsqueeze(0).clamp(0, 1), json.dumps(box))


class VNCCSMaskedCropPrepare:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",), "person_mask": ("MASK",),
                             "expand": ("INT", {"default": 24, "min": 0, "max": 256}),
                             "feather": ("INT", {"default": 12, "min": 0, "max": 128}),
                             "crop_padding": ("INT", {"default": 96, "min": 0, "max": 512})}}
    RETURN_TYPES = ("IMAGE", "MASK", "MASK", "STRING")
    RETURN_NAMES = ("crop_before", "crop_mask", "full_mask", "crop_info")
    FUNCTION = "prepare"
    CATEGORY = "VNCCS/Masked Replacement"

    def prepare(self, source, person_mask, expand, feather, crop_padding):
        m = _mask4(person_mask)[:1]
        h, w = source.shape[1:3]
        m = F.interpolate(m.unsqueeze(1), (h, w), mode="bilinear", align_corners=False)[:, 0]
        if float(m.max()) <= 0.001:
            raise ValueError("Kişi maskesi boş.")
        if expand:
            k = expand * 2 + 1
            m = F.max_pool2d(m.unsqueeze(1), k, 1, expand)[:, 0]
        hard = (m > 0.01).float()
        if feather:
            k = feather * 2 + 1
            m = F.avg_pool2d(m.unsqueeze(1), k, 1, feather)[:, 0].clamp(0, 1)
        ys, xs = torch.where(hard[0] > 0)
        x0 = max(0, int(xs.min()) - crop_padding); x1 = min(w, int(xs.max()) + 1 + crop_padding)
        y0 = max(0, int(ys.min()) - crop_padding); y1 = min(h, int(ys.max()) + 1 + crop_padding)
        # Qwen/VAE-safe dimensions without changing the source aspect ratio.
        x0 = max(0, (x0 // 8) * 8); y0 = max(0, (y0 // 8) * 8)
        x1 = min(w, ((x1 + 7) // 8) * 8); y1 = min(h, ((y1 + 7) // 8) * 8)
        info = json.dumps({"x": x0, "y": y0, "width": x1-x0, "height": y1-y0,
                           "source_width": w, "source_height": h})
        return (source[:, y0:y1, x0:x1, :3], m[:, y0:y1, x0:x1], m, info)


class VNCCSExactMaskedComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",), "edited_crop": ("IMAGE",),
                             "full_mask": ("MASK",), "crop_info": ("STRING",)}}
    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "FLOAT")
    RETURN_NAMES = ("replacement_full_scene", "replacement_character_transparent",
                    "replacement_mask", "outside_mask_max_difference")
    FUNCTION = "composite"
    CATEGORY = "VNCCS/Masked Replacement"

    def composite(self, source, edited_crop, full_mask, crop_info):
        b = json.loads(crop_info); x, y, cw, ch = b["x"], b["y"], b["width"], b["height"]
        edit = edited_crop[..., :3].permute(0, 3, 1, 2)
        edit = F.interpolate(edit, (ch, cw), mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        mask = _mask4(full_mask)[:1]
        h, w = source.shape[1:3]
        mask = F.interpolate(mask.unsqueeze(1), (h, w), mode="bilinear", align_corners=False)[:, 0]
        # Values which SaveImage would quantize to zero must already be exact zero
        # during compositing, otherwise a saved-mask comparison can show 1-LSB drift.
        mask = torch.where(mask < ((1.0 / 255.0) + 1e-8), torch.zeros_like(mask), mask)
        canvas = source[..., :3].clone()
        a = mask[:, y:y+ch, x:x+cw].unsqueeze(-1)
        canvas[:, y:y+ch, x:x+cw] = source[:, y:y+ch, x:x+cw, :3] * (1-a) + edit * a
        outside = mask <= 0.0
        diff = float((canvas - source[..., :3]).abs()[outside.unsqueeze(-1).expand_as(canvas)].max()) if outside.any() else 0.0
        if diff != 0.0:
            raise RuntimeError(f"Outside-mask pixel difference is not zero: {diff}")
        rgba = torch.cat((canvas, mask.unsqueeze(-1)), dim=-1)
        mask_rgb = mask.unsqueeze(-1).repeat(1,1,1,3)
        return (canvas, rgba, mask_rgb, diff)


class VNCCSMaskExpandFeather:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",), "person_mask": ("MASK",),
                             "expand": ("INT", {"default": 16, "min": 0, "max": 256}),
                             "feather": ("INT", {"default": 8, "min": 0, "max": 128})}}
    RETURN_TYPES = ("MASK", "IMAGE")
    RETURN_NAMES = ("full_mask", "mask_preview")
    FUNCTION = "prepare"
    CATEGORY = "VNCCS/Masked Replacement"

    def prepare(self, source, person_mask, expand, feather):
        h, w = source.shape[1:3]
        mask = _mask4(person_mask)[:1]
        mask = F.interpolate(mask.unsqueeze(1), (h, w), mode="bilinear", align_corners=False)[:, 0]
        if float(mask.max()) <= 0.001:
            raise ValueError("Kişi maskesi boş.")
        if expand:
            k = expand * 2 + 1
            mask = F.max_pool2d(mask.unsqueeze(1), k, 1, expand)[:, 0]
        if feather:
            k = feather * 2 + 1
            mask = F.avg_pool2d(mask.unsqueeze(1), k, 1, feather)[:, 0].clamp(0, 1)
        mask = torch.where(mask < ((1.0 / 255.0) + 1e-8), torch.zeros_like(mask), mask)
        return (mask, mask.unsqueeze(-1).repeat(1, 1, 1, 3))


class VNCCSExactFullFrameComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",), "edited_full_scene": ("IMAGE",),
                             "full_mask": ("MASK",)}}
    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "FLOAT")
    RETURN_NAMES = ("final_pose_scene", "replacement_character_transparent",
                    "replacement_mask", "outside_mask_max_difference")
    FUNCTION = "composite"
    CATEGORY = "VNCCS/Masked Replacement"

    def composite(self, source, edited_full_scene, full_mask):
        h, w = source.shape[1:3]
        edit = edited_full_scene[..., :3].permute(0, 3, 1, 2)
        edit = F.interpolate(edit, (h, w), mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        mask = _mask4(full_mask)[:1]
        mask = F.interpolate(mask.unsqueeze(1), (h, w), mode="bilinear", align_corners=False)[:, 0]
        mask = torch.where(mask < ((1.0 / 255.0) + 1e-8), torch.zeros_like(mask), mask)
        alpha = mask.unsqueeze(-1)
        canvas = source[..., :3] * (1.0 - alpha) + edit * alpha
        outside = mask <= 0.0
        diff = float((canvas - source[..., :3]).abs()[outside.unsqueeze(-1).expand_as(canvas)].max()) if outside.any() else 0.0
        if diff != 0.0:
            raise RuntimeError(f"Outside-mask pixel difference is not zero: {diff}")
        rgba = torch.cat((canvas, alpha), dim=-1)
        mask_rgb = alpha.repeat(1, 1, 1, 3)
        return (canvas, rgba, mask_rgb, diff)


NODE_CLASS_MAPPINGS = {
    "VNCCS_AutoPersonMask": VNCCSAutoPersonMask,
    "VNCCS_MaskChoice": VNCCSMaskChoice,
    "VNCCS_MaskedCropPrepare": VNCCSMaskedCropPrepare,
    "VNCCS_ExactMaskedComposite": VNCCSExactMaskedComposite,
    "VNCCS_MaskExpandFeather": VNCCSMaskExpandFeather,
    "VNCCS_ExactFullFrameComposite": VNCCSExactFullFrameComposite,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VNCCS_AutoPersonMask": "VNCCS Auto Person Mask (BiRefNet)",
    "VNCCS_MaskChoice": "VNCCS Mask Choice (Manual or SAM3)",
    "VNCCS_MaskedCropPrepare": "VNCCS Masked Crop Prepare",
    "VNCCS_ExactMaskedComposite": "VNCCS Exact Outside-Mask Composite",
    "VNCCS_MaskExpandFeather": "VNCCS Full Mask Expand + Feather (No Crop)",
    "VNCCS_ExactFullFrameComposite": "VNCCS Exact Full-Frame Composite (No Crop)",
}
