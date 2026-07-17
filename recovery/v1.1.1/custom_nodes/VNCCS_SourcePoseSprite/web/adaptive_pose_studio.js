import { app } from "/scripts/app.js";

const ADAPTIVE_TITLE = "VNCCS POSE STUDIO - automatic import";

function installAdaptiveCameraGuard(node) {
    if (!node || node.__vnccsAdaptiveCameraGuardTimer) return;

    let attempts = 0;
    node.__vnccsAdaptiveCameraGuardTimer = window.setInterval(() => {
        attempts += 1;
        const widget = node.studioWidget;
        const adaptive = String(node.title || "").includes(ADAPTIVE_TITLE);

        if (widget && adaptive && !widget.__vnccsAdaptiveCameraGuard) {
            const original = widget.applySAM3DFrameCameraParams?.bind(widget);
            if (original) {
                widget.applySAM3DFrameCameraParams = function (poseData, meshData = null) {
                    const ok = original(poseData, meshData);
                    const params = this.exportParams || {};
                    const zoom = Number(params.cam_zoom);
                    const offsetX = Number(params.cam_offset_x);
                    const offsetY = Number(params.cam_offset_y);

                    // SAM3D sometimes fits an extreme close-up by pushing the virtual
                    // camera far into the mesh.  The render then contains only a floor-
                    // like fragment.  Render the imported bones with a neutral camera;
                    // the downstream adaptive node restores the source bbox/framing.
                    if (
                        (Number.isFinite(zoom) && zoom > 3.0) ||
                        (Number.isFinite(offsetX) && Math.abs(offsetX) > 2.75) ||
                        (Number.isFinite(offsetY) && Math.abs(offsetY) > 2.75)
                    ) {
                        params.cam_zoom = 1.55;
                        params.cam_offset_x = 0;
                        params.cam_offset_y = 0;
                        this.syncCameraWidgets?.();
                        this.applyCameraToViewer?.(true);
                        this.viewer?.setCameraParams?.(this.currentCameraParams?.());
                    }
                    return ok;
                };
                widget.__vnccsAdaptiveCameraGuard = true;
            }
        }

        if (widget?.__vnccsAdaptiveCameraGuard || attempts > 120) {
            window.clearInterval(node.__vnccsAdaptiveCameraGuardTimer);
            node.__vnccsAdaptiveCameraGuardTimer = null;
        }
    }, 100);
}

app.registerExtension({
    name: "VNCCS.SourcePoseSprite.AdaptiveCameraGuard",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "VNCCS_PoseStudio") return;
        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalCreated?.apply(this, arguments);
            installAdaptiveCameraGuard(this);
            return result;
        };
    },
});
