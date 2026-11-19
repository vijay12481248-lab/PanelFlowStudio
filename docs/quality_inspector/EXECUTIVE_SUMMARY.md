# AI Visual Quality Inspector & Auto-Correction System: Executive Summary

**Date of Audit**: 2026-11-19  
**Audit Team**: Principal AI Architect, Computer Vision Engineer, Generative AI Engineer, ComfyUI Workflow Specialist, Video AI Engineer, Python Backend Engineer, AI Model Research Engineer, QA and Automation Engineer  
**Status**: Discovery and Environment Audit Complete. **STOPPED FOR OWNER APPROVAL.**

---

## 1. Core Answers to Strategic Questions

### Question 1: What do we already have?
1. **Installed Hardware Envelope**: An NVIDIA GeForce RTX 5060 Ti (16 GB VRAM, Driver 621.01, CUDA 13.5), 32 GB System RAM (~16 GB free), and 94.8 GB of free storage on Drive E.
2. **Local AI Services**:
   - Ollama running locally with `qwen3.5:9b` (Q4_K_M, multimodal vision + thinking, 262k context).
   - ComfyUI API server architecture on port 8188 with 80+ blueprints and custom node suites.
   - PanelFlow Studio FastAPI backend (`engine/`) with SQLite durable job queue (`engine/jobs`).
3. **Computer Vision & Pose Models (Installed on Disk)**:
   - `dw-ll_ucoco_384.onnx` (128 MB): DWPose 133-keypoint estimator (18 body, 42 hand, 68 face).
   - `yolox_l.onnx` (207 MB): YOLOX human bounding box detector.
   - `face_yolov8m.pt` (50 MB): YOLOv8m face detector for photorealistic and anime faces.
   - `antelopev2\` (407 MB): InsightFace ArcFace suite (`glintr100.onnx`, `scrfd_10g_bnkps.onnx`, 106-point landmarking).
   - `CLIP-ViT-H-14` (2.4 GB): Vision encoder for anime/stylized character embeddings.
4. **Generation & Inpainting Models (Installed on Disk)**:
   - `hidream_i1_fast_fp8.safetensors` (16.3 GB): Default text-to-image generator (MIT license).
   - `z_image_turbo_int8_convrot.safetensors` (5.9 GB): Clean geometry text-to-image generator.
   - `animagine-xl-4.0.safetensors` (6.6 GB): Active SDXL inpainting model.
   - `fasth3_omniref_8step`, `wan2.1_i2v_14B`: Video generation engines.
5. **Existing Codebases**:
   - `engine/original/anatomy/`: Proven multi-tile hand enumeration, stray text detection, deterministic defect rules, seed-stepped redraw loop (`loop.py`), and persistent mistake memory (`lessons.py`).
   - `engine/motion_bank/dwpose_extractor.py`: Complete standalone ONNX DWPose video/frame extractor with IoU actor tracking.
   - `engine/anime/scene_detector.py`: OpenCV HSV scene boundary detector and FFmpeg video slicer.
   - `ComfyUI-H3-FaceRefine`: Face tracking, head crop stabilization, InsightFace identity matching, and affine stitching.
   - `engine/comfyui/workflows/anime_sdxl_inpaint.api.json`: Verified, ready-to-run masked inpainting workflow.

---

### Question 2: What can we reuse?
- **Reuse Directly (51.7% of architecture)**:
  - `DWPoseExtractor`: Instant 133-keypoint extraction on CPU at **0 MB VRAM cost**.
  - `OllamaJudge`: Blind multi-tile semantic review.
  - `AnimeSceneClipper`: OpenCV scene boundary detection.
  - `anime_sdxl_inpaint.api.json`: ComfyUI localized inpainting.
  - `H3FaceTrackCrop` & `H3FaceStitch`: Multi-frame face stabilization and stitch.
  - `ComfyUIClient` & `JobManager`: API dispatch, polling, and VRAM arbitration.
  - `lessons.py` & `store.py`: Persistent defect tracking and prompt lesson memory.

---

### Question 3: What can we build immediately?
We can build the **Image-Level Visual Quality Inspector and Auto-Correction Bridge** immediately using existing Python packages (`opencv-python`, `onnxruntime`, `pydantic`, `httpx`) without downloading a single byte:
1. `SkeletonTopologyValidator`: Algorithmic joint angle and extra-limb detector using DWPose coordinates.
2. `FaceIntegrityAnalyzer`: Face-to-body ratio check (extra heads) and intra-frame face cosine similarity (duplicate characters).
3. `DefectMaskGenerator`: Generates feathered inpaint masks from DWPose/YOLO bounding boxes.
4. `QualityDecisionEngine`: Synthesizes CV and VLM evidence into a single 0–100 score and outputs `PASS`, `RETRY`, or `MANUAL REVIEW`.

---

### Question 4: What do we need?
- **No new mandatory model downloads**. We already have all required models for full operational status.
- **Optional Enhancement (Subject to Approval)**: SAM / MobileSAM weights (40–375 MB) if pixel-perfect non-face object masks are requested in Phase 3 (currently substituted by dilated bounding/hull masks).

---

### Question 5: What must we develop?
We must develop 7 targeted Python modules:
1. `engine/inspector/schema.py`: Canonical Pydantic schemas.
2. `engine/inspector/topology.py`: DWPose skeleton geometric validation rules.
3. `engine/inspector/face_check.py`: YOLOv8/InsightFace face count & clustering.
4. `engine/inspector/decision.py`: Composite scoring and decision state machine.
5. `engine/inspector/mask_gen.py`: Bounding/hull feathered mask synthesizer.
6. `engine/inspector/repair.py`: Bridge connecting Inspector to ComfyUI inpainting graph.
7. `engine/inspector/temporal.py`: Video frame-to-frame keypoint jitter and identity drift analyzer.

---

### Question 6: What are the biggest technical challenges?
1. **16 GB VRAM Hardware Boundary**: Running generation, VLM inspection, and inpainting simultaneously will crash with CUDA Out-of-Memory.
   - *Solution*: Enforce strict sequential execution. Run CV feature extraction on CPU (0 MB VRAM); offload generation DiT before calling VLM; unload VLM before inpainting.
2. **VLM Prior Bias & Undercounting**: Vision LLMs hallucinate that deformed bodies are normal when asked direct count questions (e.g., answering "2" for a 4-armed person).
   - *Solution*: Blind line-by-line enumeration ("HAND 1: ...") combined with deterministic DWPose keypoint verification.
3. **Domain Shift Across Art Styles**: Face recognition models trained on photos fail on stylized anime and stickmen.
   - *Solution*: Fall back to YOLOv8m face boxes and CLIP-ViT-H-14 vision embeddings when ArcFace SCRFD detects no candidates.

---

### Question 7: What is the recommended implementation order?
1. **Milestone 1 (Foundations & Image Inspector)**: Implement schemas, DWPose topology checks, and integrate existing multi-tile VLM review into a unified `ImageInspector`.
2. **Milestone 2 (Image Auto-Correction & Inpaint Bridge)**: Implement mask generation and wire ComfyUI SDXL inpainting with automated revalidation.
3. **Milestone 3 (Video Temporal Inspector)**: Implement frame sampling, actor tracking, and keypoint velocity/drift analysis.
4. **Milestone 4 (Desktop UI & Pipeline Integration)**: Add the Visual Quality Inspector tab to PanelFlow Studio desktop.

---

## 2. Summary Status & Decision Gate

The environment audit and capability discovery confirm that our existing installation possesses the necessary infrastructure, models, and code to build the proposed system without external dependencies.

**In accordance with instructions, all implementation has been halted.** We await the user's explicit approval before proceeding to Milestone 1.
