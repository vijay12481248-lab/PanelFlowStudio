# Existing Environment and Infrastructure Audit

**Date of Audit**: 2026-11-19  
**Audit Team**: Principal AI Architect, Computer Vision Engineer, Generative AI Engineer, ComfyUI Workflow Specialist, Video AI Engineer, Python Backend Engineer, AI Model Research Engineer, QA and Automation Engineer.  
**Project Target**: AI Visual Quality Inspector and Auto-Correction System  
**Audit Location**: `E:\VIJAY SEKAR\PanelFlow Studio` & `E:\VIJAY SEKAR\ComfyUI`

---

## 1. Executive Summary of Environment Findings

1. **Path Resolution**: The user prompt cited `C:\Users\Vijaya sekhar\claude\ComfyUI` as the primary investigation target. Physical file system probing confirmed that `C:\Users\Vijaya sekhar` does not exist on this machine. The live, active ComfyUI environment is located at `E:\VIJAY SEKAR\ComfyUI`, and the application engine is at `E:\VIJAY SEKAR\PanelFlow Studio` (a historical backup also exists at `C:\PanelFlow_BACKUP_20261106_1130`).
2. **Compute & Memory Envelope**: The host is equipped with an **NVIDIA GeForce RTX 5060 Ti (16 GB VRAM, Driver 621.01, CUDA UMD 13.5)**, **32 GB System RAM (~16 GB available)**, and 94.8 GB free disk space on Drive E.
3. **Dual Python Environments**:
   - ComfyUI runs in its dedicated Python 3.13.17 environment (`E:\VIJAY SEKAR\ComfyUI\venv`) equipped with PyTorch 2.14.1+cu130, `ultralytics` 8.4.202, `insightface` 2.1, `transformers` 5.22.1, OpenCV 5.0.0, and PyAV 19.0.2.
   - PanelFlow Studio runs in Python 3.14.9 (`.venv`) with FastAPI 0.146.0, Uvicorn 0.54.0, PyTorch 2.14.1+cu130, OpenCV 5.0.0, PyAV 19.0.2, and ONNX Runtime 1.31.1.
4. **VRAM Footprint & Coexistence Constraint**:
   - Generation models (HiDream-I1 Fast, Z-Image Turbo, MiniMax H3) require 8–14 GB VRAM during active sampling.
   - Ollama `qwen3.5:9b` (Q4_K_M) requires ~6.5 GB VRAM when loaded in GPU memory.
   - Concurrently running generation and VLM inspection on a 16 GB card will cause VRAM contention or Out-of-Memory (OOM) faults unless sequential execution or offloading is enforced.
   - Crucially, ONNX Runtime runs on `CPUExecutionProvider` on this host. Consequently, **DWPose keypoint extraction and InsightFace face embedding generation run on the 32 GB host RAM / multi-core CPU at 0 MB VRAM cost**.

---

## 2. Hardware and Operating System Profile

| Component | Specification | Operational Status |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 64-bit (Build 26100+) | Fully operational |
| **GPU** | NVIDIA GeForce RTX 5060 Ti | 16,311 MiB (16 GB GDDR7/GDDR6), Driver 621.01 |
| **CUDA Driver / UMD** | CUDA 13.5 (UMD) / CUDA 13.0 Runtime | Fully operational, CUDA Available: `True` |
| **System Memory (RAM)** | 32,314,716 KB (~32 GB DDR5/DDR4) | ~16 GB currently free |
| **Storage (Drive C:)** | NVMe SSD: 281.20 GB Used / 69.79 GB Free | Adequate for temp files |
| **Storage (Drive E:)** | NVMe/SATA SSD: 346.07 GB Used / 94.82 GB Free | Primary model and workspace drive |
| **System FFmpeg** | FFmpeg 9.0.1-essentials (Gyan build, MSYS2 gcc 16.1.0) | Global CLI available; supports H.264/H.265/NVENC |

---

## 3. Python Virtual Environments Detailed Audit

### Environment A: ComfyUI Host Environment
- **Path**: `E:\VIJAY SEKAR\ComfyUI\venv\Scripts\python.exe`
- **Python Version**: `3.13.17 (MSC v.1944 64 bit)`
- **PyTorch Stack**:
  - `torch`: `2.14.1+cu130` (CUDA accelerated)
  - `torchvision`: `0.29.1+cu130`
  - `torchaudio`: `2.11.0+cu130`
- **Vision and Detection Packages**:
  - `ultralytics`: `8.4.202` (Active, supports YOLOv8, YOLOv9, YOLOv11)
  - `insightface`: `2.1` (Active, supports ArcFace, SCRFD, landmarking)
  - `onnxruntime`: `1.31.1` (Active; execution providers: `['AzureExecutionProvider', 'CPUExecutionProvider']`)
  - `onnx`: `1.23.2`
  - `opencv-python (cv2)`: `5.0.0`
  - `av (PyAV)`: `19.0.2`
  - `Pillow (PIL)`: `13.0.0`
  - `numpy`: `2.5.4`
  - `scipy`: `1.18.1`
  - `einops`: `0.8.2`
- **NLP / Model Frameworks**:
  - `transformers`: `5.22.1`
  - `safetensors`: `0.8.0`
- **Missing / Not Installed**:
  - `accelerate`: `NOT INSTALLED`
  - `diffusers`: `NOT INSTALLED`
  - `mediapipe`: `NOT INSTALLED`
  - `mmpose` / `mmcv`: `NOT INSTALLED`
  - `openpose`: `NOT INSTALLED`

### Environment B: PanelFlow Studio Core Engine
- **Path**: `e:\VIJAY SEKAR\PanelFlow Studio\.venv\Scripts\python.exe`
- **Python Version**: `3.14.9 (MSC v.1944 64 bit)`
- **PyTorch Stack**:
  - `torch`: `2.14.1+cu130` (CUDA accelerated)
  - `torchvision`: `NOT INSTALLED` (Relies on PIL / OpenCV for image transforms)
  - `torchaudio`: `NOT INSTALLED`
- **Vision and Detection Packages**:
  - `onnxruntime`: `1.31.1` (Active; providers: `['AzureExecutionProvider', 'CPUExecutionProvider']`)
  - `opencv-python (cv2)`: `5.0.0`
  - `av (PyAV)`: `19.0.2`
  - `Pillow (PIL)`: `13.0.0`
  - `numpy`: `2.5.4`
  - `scipy`: `1.18.1`
  - `transformers`: `5.20.1`
  - `safetensors`: `0.8.0`
- **API & Orchestration Frameworks**:
  - `fastapi`: `0.146.0`
  - `uvicorn`: `0.54.0`
  - `httpx`: `0.28.1`
  - `pydantic`: `2.14.1`
- **Missing / Not Installed**:
  - `ultralytics`: `NOT INSTALLED` (Present in ComfyUI venv)
  - `insightface`: `NOT INSTALLED` (Present in ComfyUI venv)
  - `accelerate`: `NOT INSTALLED`
  - `diffusers`: `NOT INSTALLED`
  - `mediapipe`, `mmpose`, `openpose`: `NOT INSTALLED`

---

## 4. Installed External Services and Daemons

### 1. Ollama LLM / VLM Daemon
- **Address**: `http://127.0.0.1:11434`
- **Status**: Running and accessible.
- **Installed Models**:
  - `qwen3.5:9b` (Digest: `56671c2ab9...`, Format: GGUF `Q4_K_M`, Size: 6.55 GB, Context: 262,144 tokens).
  - **Verified Capabilities**: Text completion, Vision (multimodal image analysis), Tool calling, Thinking / Chain-of-Thought reasoning.
  - **Latency / Performance**: 1.2–2.5 s for text queries; 4.0–8.0 s for 1280px visual interrogation.

### 2. ComfyUI Server
- **Address**: `http://127.0.0.1:8188`
- **Start Command**: `E:\VIJAY SEKAR\ComfyUI\venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188`
- **Status**: Offline during audit (managed on-demand or background service).
- **Protocol**: HTTP REST API + WebSocket (`/ws`) event streaming.
- **Execution Parameter Note**: Must be launched with `--disable-dynamic-vram` when running Qwen3-VL 8B via the `TextGenerate` node to prevent native `memmove` crash in `comfy_kitchen`.

### 3. PanelFlow Studio Engine
- **Address**: `http://127.0.0.1:8765`
- **Status**: Offline during audit.
- **Protocol**: FastAPI application exposing `/api/*` endpoints with SQLite-backed state (`panelflow.db`).

---

## 5. File System and Model Distribution Map

```
E:\VIJAY SEKAR\
├── ComfyUI\
│   ├── blueprints\                     # 80+ ComfyUI native templates (SAM3, Inpaint, Pose, Video)
│   ├── comfy_extras\
│   │   ├── nodes_sam3.py               # Native SAM3 segmentation and video tracking node definitions
│   │   ├── nodes_sam3d_body.py         # SAM3D Body pose and 3D mesh node definitions
│   │   └── sam3d_body\                 # SAM3D rasterizer, capsule exporter, openpose exporter
│   ├── custom_nodes\
│   │   ├── ComfyUI-H3-FaceRefine\      # YOLOv8 face detector, InsightFace recognition, SAM face mask
│   │   ├── ComfyUI-H3-Motion-Context...# Latent motion transfer, masked extension, de-rope
│   │   ├── ComfyUI-MiniMaxH3-Context...# Context take, masked bridge, pixel continuity
│   │   ├── ComfyUI-PuLID-Flux\         # PuLID character face identity conditioning for FLUX
│   │   ├── ComfyUI_IPAdapter_plus\     # IP-Adapter Plus (SDXL, FaceID, Regional)
│   │   └── Herrgotts-H3-Infinite...    # Latent math, seamless stitch, motion analysis
│   └── models\                         # 140+ GB of local diffusion models, weights & ONNX graphs
└── PanelFlow Studio\
    ├── engine\
    │   ├── anime\scene_detector.py      # OpenCV HSV scene transition detector & FFmpeg slicer
    │   ├── comfyui\art.py               # ArtEngine (HiDream-I1 Fast, Z-Image Turbo, H3-Edit)
    │   ├── comfyui\client.py            # HTTP/WebSocket client for ComfyUI API
    │   ├── comfyui\workflow_registry.json
    │   ├── motion_bank\
    │   │   ├── dwpose_extractor.py      # Standalone ONNX DWPose (18 body, 42 hand, 68 face)
    │   │   └── visualizer.py            # OpenPose-18 + hand/face skeletal renderer
    │   └── original\
    │       ├── anatomy\                 # Multi-tile enumeration review, rules & lesson memory
    │       └── judges.py                # Dual-judge (Ollama qwen3.5:9b + ComfyUI Qwen3-VL 8B)
    └── docs\quality_inspector\          # Inspection and planning documentation
```

---

## 6. VRAM & Compute Constraints Analysis

1. **Host VRAM Budget**: 16,311 MiB.
   - Operating system and display drivers consume ~1.6 GB.
   - Available VRAM for AI workloads: **~14.5 GB**.
2. **Model Memory Footprint Matrix**:
   - `hidream_i1_fast_fp8.safetensors`: ~12.5 GB peak VRAM during sampling.
   - `z_image_turbo_int8_convrot.safetensors`: ~7.8 GB peak VRAM.
   - `fasth3_omniref_8step` / `wan2.1_i2v`: ~14.0 GB peak VRAM (near saturation).
   - `qwen3.5:9b` (Ollama Q4_K_M): ~6.5 GB VRAM.
   - `qwen3vl_8b_int8` (ComfyUI `TextGenerate`): ~8.5 GB VRAM.
   - `DWPose` (ONNX Runtime): **0 MB VRAM** (Allocated to 32 GB CPU RAM via `CPUExecutionProvider`).
   - `InsightFace Antelopev2` (ONNX): **0 MB VRAM** (Allocated to CPU RAM via `CPUExecutionProvider`).
   - `YOLOv8m Face` (PyTorch/ONNX): ~120 MB VRAM (or runs on CPU).
3. **Engineering Conclusion**:
   The Quality Inspector **cannot** run heavy generative inpainting simultaneously with a VLM query on the GPU. The pipeline must operate in **sequential stages**:
   - **Stage 1 (Detection & Feature Extraction)**: Run DWPose and InsightFace on CPU (0 MB VRAM impact) concurrently with image generation if needed.
   - **Stage 2 (VLM Semantic Inspection)**: Free generation buffers -> invoke Ollama / ComfyJudge.
   - **Stage 3 (Correction / Inpainting)**: Unload VLM -> load Inpainting / Regeneration model in ComfyUI.
