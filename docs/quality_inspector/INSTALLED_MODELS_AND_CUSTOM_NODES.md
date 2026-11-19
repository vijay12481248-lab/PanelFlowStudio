# Installed Models and Custom Nodes Audit

**Date of Audit**: 2026-11-19  
**Audit Scope**: Inventory, technical specifications, exact file paths, parameter sizes, and reusability analysis for all installed model weights and ComfyUI custom nodes.

---

## 1. Installed Model Inventory

All models were verified by inspecting physical file presence, size on disk, and format.

### 1.1 Image Generation Models

| Model Name | Physical Path | Format & Precision | Size | Status & Role |
| :--- | :--- | :--- | :--- | :--- |
| **HiDream-I1 Fast** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\hidream_i1_fast_fp8.safetensors` | Transformer, FP8 | 16,313.5 MB | **Active Default T2I**. MIT license. High aesthetics, fast (49 s @ 768x1344). Tends to add corner scribble signature. |
| **Z-Image Turbo** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\z_image_turbo_int8_convrot.safetensors` | Diffusion, INT8 ConvRot | 5,913.7 MB | **Active Secondary T2I**. Commercial check pending. Clean geometry, excellent stickman/anime adherence, no stray text. |
| **Animagine XL 4.0** | `E:\VIJAY SEKAR\ComfyUI\models\checkpoints\animagine-xl-4.0.safetensors` | SDXL Checkpoint, FP16 | 6,617.0 MB | **Active Substrate**. Primary engine for ControlNet, IP-Adapter, inpainting, and matting pipelines. |
| **FLUX.1 Schnell** | `E:\VIJAY SEKAR\ComfyUI\models\checkpoints\flux1-schnell-fp8.safetensors` | Flow Transformer, FP8 | 16,437.8 MB | **Available**. Compatible with PuLID-Flux for high-fidelity single-step face conditioning. |
| **MiniMax-H3-Image** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\minimax_h3_image_pruned_int8_convrot.safetensors` | Transformer, INT8 ConvRot | 20,007.4 MB | **Active Image Edit / T2I**. Instruction-guided image editing (`minimax_h3_image_edit`). Geographic license restrictions apply. |
| **Qwen-Image 2.1 Turbo** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\qwen_image_2.1_turbo_int8_convrot.safetensors` | Transformer, INT8 ConvRot | 6,920.6 MB | **Retired**. Non-commercial license. Retained on disk for reference/legacy audit only. |

---

### 1.2 Video Generation and Extension Models

| Model Name | Physical Path | Format & Precision | Size | Status & Role |
| :--- | :--- | :--- | :--- | :--- |
| **FastH3 OmniRef (8-step)** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\fasth3_omniref_8step_pruned_int8_convrot.safetensors` | DiT, INT8 ConvRot | 21,184.7 MB | **Active Video Generator**. Multi-reference video synthesis with prompt control. |
| **FastVideo FastH3 v2** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors` | DiT, INT8 ConvRot | 21,103.3 MB | **Active Video Generator**. High-speed 8-step I2V / T2V backbone. |
| **MiniMax H3 FL2VA** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors` | DiT, INT8 ConvRot | 19,998.9 MB | **Active First-to-Last Frame Video**. Interpolates and animates between start and end frames with audio. |
| **Wan 2.1 I2V 14B** | `E:\VIJAY SEKAR\ComfyUI\models\diffusion_models\wan2.1_i2v_480p_14B_fp8_scaled.safetensors` | DiT, FP8 Scaled | 15,641.6 MB | **Active High-End Video Generator**. 14B parameter open-weights model for high-motion consistency. |

---

### 1.3 Vision Language Models (VLM) & Multi-Modal Inspection

| Model Name | Host Engine | Precision / Format | Size | Capabilities & Role |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen 3.5 9B** | Ollama (`http://127.0.0.1:11434`) | GGUF `Q4_K_M` | 6,550.8 MB | **Primary Vision Judge**. 262k context. Tested and calibrated for multi-tile hand enumeration, stray text detection, and blind pose verification. |
| **Qwen3-VL 8B** | ComfyUI (`CLIPLoader` / `TextGenerate`) | `qwen3vl_8b_int8_convrot.safetensors` | 8,917.6 MB | **Secondary Cross-Check Judge**. Runs inside ComfyUI with `--disable-dynamic-vram`. Acts as corroborating witness to eliminate single-model hallucinations. |
| **Qwen3-VL 32B** | ComfyUI | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14,960.4 MB | **Present on disk**. Heavyweight VLM used for high-complexity prompts. Too large for real-time concurrent inspection on 16 GB VRAM. |

---

### 1.4 Computer Vision, Pose, Face & Detection Models

| Model Name | Physical Path | Format | Size | Functionality & Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **DWPose Whole-Body (dw-ll_ucoco_384)** | `E:\VIJAY SEKAR\ComfyUI\models\dwpose\dw-ll_ucoco_384.onnx` | ONNX | 128.2 MB | **133-Keypoint Estimation**: 18 body keypoints (OpenPose format), 42 hand/finger keypoints (21 per hand), 68 facial landmarks. Runs on CPU at 0 MB VRAM cost. |
| **YOLOX-L Person Detector** | `E:\VIJAY SEKAR\ComfyUI\models\dwpose\yolox_l.onnx` | ONNX | 206.7 MB | **Human Bounding Box Detection**: Pre-generates anchor grids and strides for actor detection and cropping prior to pose estimation. |
| **YOLOv8m Face Detector** | `E:\VIJAY SEKAR\ComfyUI\models\ultralytics\bbox\face_yolov8m.pt` | PyTorch / YOLOv8 | 49.6 MB | **Face Detection**: Fast bounding-box localization for face tracking, cropping, and facial defect inspection. Works on both anime and photorealistic faces. |
| **InsightFace Antelopev2 (Suite)** | `E:\VIJAY SEKAR\ComfyUI\models\insightface\models\antelopev2\` | ONNX (5 files) | 407.0 MB | **Face Analysis Suite**: Includes `glintr100.onnx` (512-dim ArcFace embedding extraction), `scrfd_10g_bnkps.onnx` (detector + 5 landmarks), `2d106det.onnx` (106 facial landmarks), `1k3d68.onnx` (3D face shape), and `genderage.onnx`. |
| **CLIP-ViT-H-14** | `E:\VIJAY SEKAR\ComfyUI\models\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | Torch / Safetensors | 2,411.2 MB | **Vision Feature Extractor**: Character embedding extraction for non-photorealistic characters (anime/stickmen) where facial recognition models fail. |
| **EVA02-CLIP-L-336** | `E:\VIJAY SEKAR\ComfyUI\models\clip\EVA02_CLIP_L_336_psz14_s6B.pt` | PyTorch | 816.8 MB | **PuLID Backbone**: High-resolution vision encoder used for zero-shot facial identity preservation. |

---

### 1.5 Conditioning, Adapters, Text Encoders & VAEs

- **Adapters**:
  - `pulid_flux_v0.9.0.safetensors` (1,089.2 MB) in `models\pulid`: PuLID face identity injection for FLUX.
  - `ip-adapter-plus_sdxl_vit-h.safetensors` (808.3 MB) in `models\ipadapter`: IP-Adapter Plus for SDXL image and style conditioning.
  - `minimax_h3_fl2v_turbo_4step` / `8step` (1,865.6 MB each) in `models\loras`: Turbo motion LoRAs for video extension.
- **Text Encoders**:
  - `clip_g_hidream.safetensors` (1,325.4 MB) & `clip_l_hidream.safetensors` (236.1 MB): Text encoders for HiDream-I1.
  - `llama_3.1_8b_instruct_fp8_scaled.safetensors` (8,660.6 MB): Text backbone for video and image conditioning.
  - `t5xxl_fp8_e4m3fn_scaled.safetensors` (4,918.4 MB) & `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6,423.9 MB).
- **Variational Autoencoders (VAEs)**:
  - `ae.safetensors` (319.8 MB): Autoencoder for HiDream-I1, Z-Image, and FLUX.
  - `minimax_h3_image_vae_fp16.safetensors` (1,114.4 MB) & `minimax_h3_video_vae_int8` (2,680.8 MB).
  - `wan_2.1_vae.safetensors` (242.1 MB).
  - `qwen_image_2.1_vae_bf16.safetensors` (644.2 MB).

---

### 1.6 Missing Weights for Built-In Nodes

- **SAM3 Segmentation Checkpoints**: Native node `comfy_extras\nodes_sam3.py` is present, but no checkpoint currently exists in `models\detection\` or `models\sam3\`.
- **SAM 3D Body Checkpoint**: Native node `comfy_extras\nodes_sam3d_body.py` is present, but `models\detection\` contains 0 MB (weights unpopulated).

---

## 2. ComfyUI Custom Nodes Deep Audit

### Node Suite 1: ComfyUI-H3-FaceRefine
- **Location**: `E:\VIJAY SEKAR\ComfyUI\custom_nodes\ComfyUI-H3-FaceRefine`
- **Class Mappings**:
  1. `H3FaceSelect`: UI and automated face selection across video shot segments.
  2. `H3FaceTrackCrop`: Multi-frame face tracking with bounding box smoothing and stabilized head-crop extraction. Supports `insightface`, `clip_vision`, and `ccip` identity matchers.
  3. `H3FaceStitch`: Re-integrates refined face crops back into the original video frame coordinates using affine transformation matrices.
  4. `H3FaceMaskSAM`: Computes face-shaped paste masks using SAM on stabilized crops with temporal smoothing to prevent edge flutter.
  5. `H3InjectVideoLatent` & `H3PerFrameDenoise`: Video latent injection and localized per-frame denoise.
- **Dependencies**: `ultralytics` (YOLOv8), `insightface` (Antelopev2), `torch`, `torchvision`, `numpy`, `scipy`.
- **Reusability**: **Extremely High**. Provides ready-made face tracking, IoU smoothing, identity cosine similarity matching, and crop-and-stitch re-integration.

---

### Node Suite 2: ComfyUI-H3-Motion-Context-MultiRef
- **Location**: `E:\VIJAY SEKAR\ComfyUI\custom_nodes\ComfyUI-H3-Motion-Context-MultiRef`
- **Key Modules**: `existing_video_extension.py`, `h3_masked_bridge.py`, `h3_mask_precision.py`, `h3_timing.py`, `h3_v2v_fractional.py`.
- **Functionality**: Handles video-to-video latent motion transfer, masked extension chains, AV bridging between discontinuous shots, and fractional frame alignment.
- **Dependencies**: ComfyUI core, PyTorch, PyAV.
- **Reusability**: **High**. Provides the exact mathematical primitives required for temporal video repair and bridging.

---

### Node Suite 3: ComfyUI-MiniMaxH3-Context-Loop
- **Location**: `E:\VIJAY SEKAR\ComfyUI\custom_nodes\ComfyUI-MiniMaxH3-Context-Loop`
- **Key Modules**: `drift_control.py`, `pixel_continuity.py`, `latent_color_carry.py`, `masked_bridge.py`, `branch_scope.py`.
- **Functionality**: Explicitly engineered to solve **character identity drift**, **color shifts between generation passes**, and **pixel boundary discontinuities**.
- **Dependencies**: ComfyUI core, PyTorch, NumPy.
- **Reusability**: **Essential for Video Inspector & Auto-Correction**. The drift control algorithms and pixel continuity routines directly address Part 1 video consistency goals.

---

### Node Suite 4: Herrgotts-H3-Infinite-Continuation-Suite
- **Location**: `E:\VIJAY SEKAR\ComfyUI\custom_nodes\Herrgotts-H3-Infinite-Continuation-Suite`
- **Key Modules**: `latent_math.py`, `motion_analysis.py`, `seamless_stitch.py`, `qwen_guides.py`.
- **Functionality**: Performs optical flow and motion analysis across video latents, stitches multi-clip sequences without seam artifacts, and integrates Qwen guidance tokens.
- **Dependencies**: PyTorch, SciPy.
- **Reusability**: **High**. Reusable for temporal consistency analysis and frame transition scoring.

---

### Node Suite 5: ComfyUI_IPAdapter_plus & ComfyUI-PuLID-Flux
- **Location**: `E:\VIJAY SEKAR\ComfyUI\custom_nodes\ComfyUI_IPAdapter_plus` & `ComfyUI-PuLID-Flux`
- **Key Capabilities**: Cross-attention feature injection from reference images (SDXL & FLUX).
- **Reusability**: Useful for reference-guided face/character reconstruction during inpainting passes.

---

### Node Suite 6: ComfyUI Built-in Core Extensions (`comfy_extras`)
- **`nodes_sam3.py`**: Open-vocabulary text-prompted and bbox-prompted segmentation (`SAM3_Detect`, `SAM3_VideoTrack`, `SAM3_TrackToMask`). Native code ready; awaits model weight configuration.
- **`nodes_sam3d_body.py`**: Complete 3D human pose and mesh prediction pipeline (`SAM3DBody_Predict`, `render_pose_data_openpose`, `build_glb_skeletal`, `face_expression`). Native code ready; awaits detection model weights.

---

## 3. Workflow Template Catalog

The system possesses 80+ workflow files in `E:\VIJAY SEKAR\ComfyUI\blueprints` and 27 registered production workflows in `PanelFlow Studio\engine\comfyui\workflows`.

Key functional workflows available immediately:
1. **Inpainting**:
   - `anime_sdxl_inpaint.api.json`: Verified working SDXL inpainting with mask input, VAE encode, noise masking, Euler-A sampling, and masked composite.
   - `qwen_image_21_inpaint.api.json`: Complete 1024px Qwen inpainting pipeline.
   - Blueprint `Image Inpainting (Flux.1 Fill Dev).json`: Reference graph for modern flow inpainting.
2. **Image Editing**:
   - `minimax_h3_image_edit.api.json`: Registered and callable via `ArtEngine`.
3. **Face Refinement**:
   - `minimax_h3_facerefine_i2v.api.json`: Automated face track, crop, upscale, and stitch.
4. **Video Frame Extraction & Stitching**:
   - Blueprints: `Get Any Video Frame.json`, `Video Stitch.json`, `Merge Videos.json`.
   - Production: `herrgott_h3_chain_start.api.json`, `herrgott_h3_chain_stitch.api.json`.
5. **Pose Conditioning**:
   - `anime_sdxl_controlnet.api.json`: OpenPose / Depth ControlNet pipeline for SDXL.
