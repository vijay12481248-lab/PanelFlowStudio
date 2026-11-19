# Proof of Capability Non-Destructive Test Plan

**Date of Audit**: 2026-11-19  
**Status**: Ready for execution upon explicit user approval.  
**Strict Safety Constraints**: No new package installations, no model downloads, no overwriting of source files, zero VRAM oversubscription.

---

## 1. Overview of Verification Strategy

To empirically validate our architectural findings without modifying the workspace or consuming excessive compute, this document defines 6 small, non-destructive proof-of-capability tests. Each test verifies a specific subsystem using existing files and cached models.

---

## 2. Test Specifications

### Test 1: Standalone DWPose 133-Keypoint Extraction (CPU ONNX)
- **Test ID**: `POC-CV-01`
- **Subsystem**: Vision Intelligence Layer (Body & Hand Geometry).
- **Input**: An existing generated panel (e.g. from `tests/data/` or a temporary test image).
- **Execution Script**: One-line Python invocation of `engine.motion_bank.dwpose_extractor.DWPoseExtractor.extract_frame_pose(image_rgb, 0, 0.0)`.
- **Expected Output**: A structured `FramePoseData` object containing:
  - `body`: 18 OpenPose coordinates $(x, y, \text{conf})$.
  - `left_hand`: 21 landmark coordinates.
  - `right_hand`: 21 landmark coordinates.
  - `face`: 68 landmark coordinates.
  - `bbox`: Person bounding box $(x_1, y_1, x_2, y_2)$.
- **Required Models**: `models\dwpose\yolox_l.onnx` and `models\dwpose\dw-ll_ucoco_384.onnx`.
- **Resource Footprint**: **0 MB GPU VRAM**, ~450 MB System RAM, runtime $< 250$ ms.
- **What the Test Proves**: Proves that person detection, finger keypoint tracking, and body pose estimation are 100% operational on this machine without touching the GPU.
- **What it Does Not Prove**: Does not prove whether DWPose can detect an extra 3rd hand when that hand is detached from a shoulder.

---

### Test 2: YOLOv8m Face Detection & Bounding Box Localization
- **Test ID**: `POC-CV-02`
- **Subsystem**: Vision Intelligence Layer (Face Localization).
- **Input**: An existing character image.
- **Execution Script**: Invocation of `ultralytics.YOLO(r'E:\VIJAY SEKAR\ComfyUI\models\ultralytics\bbox\face_yolov8m.pt')(image_bgr)`.
- **Expected Output**: Array of detected face bounding boxes with confidence scores $\ge 0.70$.
- **Required Models**: `models\ultralytics\bbox\face_yolov8m.pt`.
- **Resource Footprint**: **0 MB VRAM** (can run on CPU) or $< 150$ MB VRAM, runtime $< 80$ ms.
- **What the Test Proves**: Proves that face localization operates correctly across local images.
- **What it Does Not Prove**: Does not prove face recognition identity similarity (handled by POC-CV-03).

---

### Test 3: InsightFace ArcFace Identity Embedding & Cosine Similarity
- **Test ID**: `POC-CV-03`
- **Subsystem**: Vision Intelligence Layer (Character Identity & Duplicate Detection).
- **Input**: Two cropped face images (Crop A and Crop B).
- **Execution Script**: `insightface.app.FaceAnalysis(name='antelopev2')` embedding extraction followed by `np.dot(emb_a, emb_b)`.
- **Expected Output**:
  - Two normalized 512-dimensional float vectors.
  - Cosine similarity score between -1.0 and 1.0 (similarity $> 0.70$ for identical character, $< 0.35$ for different individuals).
- **Required Models**: `models\insightface\models\antelopev2\glintr100.onnx`.
- **Resource Footprint**: **0 MB GPU VRAM**, ~380 MB System RAM, runtime $< 120$ ms on CPU.
- **What the Test Proves**: Proves that identity verification and intra-frame duplicate character detection can execute at zero VRAM cost.
- **What it Does Not Prove**: Does not prove accuracy on extreme minimalist stickmen (which lack facial features).

---

### Test 4: OpenCV Video Scene Boundary Detection & Frame Slicing
- **Test ID**: `POC-VID-01`
- **Subsystem**: Video Intelligence Layer (Temporal Boundary & Slicing).
- **Input**: An existing MP4 video clip from the workspace.
- **Execution Script**: `engine.anime.scene_detector.AnimeSceneClipper().detect_scenes_opencv(video_path, min_cut_sec=1.5, max_cut_sec=4.0)`.
- **Expected Output**: List of timestamp tuples `[(0.0, 2.5), (2.5, 4.0), ...]` marking valid shot cuts based on HSV color histogram transitions.
- **Required Models**: None (pure algorithmic OpenCV).
- **Resource Footprint**: **0 MB GPU VRAM**, ~150 MB System RAM, runtime $< 1.5$ seconds.
- **What the Test Proves**: Proves that videos can be automatically sliced into coherent semantic shots prior to temporal inspection.
- **What it Does Not Prove**: Does not prove frame-to-frame keypoint jitter.

---

### Test 5: Ollama Qwen 3.5 9B Blind Multi-Tile Hand Enumeration
- **Test ID**: `POC-VLM-01`
- **Subsystem**: Quality Decision Engine (Multi-Witness VLM Inspection).
- **Input**: A test image (e.g. clean 2-hand character or known 4-hand calibration image).
- **Execution Script**: Call `engine.original.anatomy.review.review_picture(judges=[OllamaJudge(provider)], image_bytes=png)`.
- **Expected Output**:
  - `AnatomyReport` with status (`clean` or `defects`).
  - List of enumerated hands: `HAND 1: ...`, `HAND 2: ...`.
  - People count and text flags.
- **Required Models**: Ollama `qwen3.5:9b` (Q4_K_M).
- **Resource Footprint**: ~6.5 GB GPU VRAM (standalone sequential execution; ComfyUI idle), runtime 4–8 seconds.
- **What the Test Proves**: Proves that the VLM judge can be invoked, receives image bytes, and parses hand counts reliably without hallucination.
- **What it Does Not Prove**: Does not prove inpainting auto-correction.

---

### Test 6: ComfyUI Localized Inpainting Workflow Execution
- **Test ID**: `POC-CORR-01`
- **Subsystem**: Auto-Correction Layer (Inpainting Engine).
- **Input**: A temporary duplicate test image and a synthetic circular mask PNG covering a 100x100 pixel area.
- **Execution Script**: Dispatch `engine/comfyui/workflows/anime_sdxl_inpaint.api.json` through `ArtEngine.run` with destination prefix `temp_test_inpaint`.
- **Expected Output**: A newly decoded image where the masked region has been seamlessly re-sampled while leaving 95%+ of the unmasked pixels bit-identical.
- **Required Models**: `models\checkpoints\animagine-xl-4.0.safetensors`.
- **Resource Footprint**: Peak ~7.5 GB GPU VRAM (Ollama unloaded), runtime 3.5–5.0 seconds.
- **What the Test Proves**: Proves that ComfyUI's REST API, image upload, mask application, latent noise masking, and composite blend are functioning end-to-end.
- **What it Does Not Prove**: Does not prove whether inpainting can fix every possible complex anatomical defect in a single pass.

---

## 3. Recommended Execution Sequence

When the user grants approval:
1. Run **POC-CV-01** (DWPose on CPU) $\to$ Zero VRAM check.
2. Run **POC-CV-02** and **POC-CV-03** (YOLOv8 + InsightFace on CPU) $\to$ Zero VRAM check.
3. Run **POC-VID-01** (OpenCV scene detection on CPU) $\to$ Zero VRAM check.
4. Run **POC-VLM-01** (Ollama VLM review) $\to$ Verify semantic inspection.
5. Run **POC-CORR-01** (ComfyUI Inpainting) $\to$ Verify auto-correction.
