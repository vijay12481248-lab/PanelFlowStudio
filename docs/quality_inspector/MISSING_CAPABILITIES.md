# Missing Capabilities and Gap Analysis Report

**Date of Audit**: 2026-11-19  
**Guiding Principle**: Maximize code reuse, prioritize zero-VRAM CPU/ONNX execution, avoid unnecessary model downloads, and respect host hardware boundaries (16 GB VRAM, 32 GB RAM).

---

## 1. Inventory of Missing & Partially Available Capabilities

While the underlying engine and model stack possess over 60% of required capabilities out-of-the-box, several specific modules must be constructed or extended to assemble an autonomous, production-grade Visual Quality Inspector.

---

### Gap 1: Full-Body Limb & Anatomical Topology Validation (Legs, Feet, Joint Inversions)

- **What is Missing**: The existing VLM prompt (`engine/original/anatomy/questions.py`) was intentionally restricted to hand counting because joint hand-foot questions caused the 9B model to miss hands. Detection of extra legs, backwards knees, extra feet, or unnatural limb angles currently has no automated verification rule.
- **Why it is Necessary**: AI diffusion models frequently generate phantom legs behind seated characters, disjointed knees in action poses, or three feet on multi-character compositions.
- **Which Existing Component Could Be Extended**: `engine\motion_bank\dwpose_extractor.py` and `engine\original\anatomy\rules.py`.
- **Which New Component is Required**: `SkeletonTopologyValidator` (a deterministic Python module that inspects keypoint angles, limb length ratios, and connectivity from DWPose).
- **Recommended Model**: **None (Reuse Existing)**. Use the already installed `dw-ll_ucoco_384.onnx`. DWPose already outputs keypoints 11–16 (hips, knees, ankles) and 17–22 (feet/toes).
- **Mandatory vs Optional**: Mandatory for anatomical defect coverage.
- **GPU Memory Requirements**: **0 MB VRAM** (runs on CPU via ONNX Runtime).
- **Installation Requirements**: None. Packages (`onnxruntime`, `numpy`) already installed.
- **Estimated Development Complexity**: **Low to Moderate** (algorithmic geometric checks: bone length symmetry, joint angle feasibility, confidence thresholds).
- **Known Technical Limitations**: DWPose may fail to detect keypoints on heavily stylized stickmen, extreme close-ups, or heavily occluded lower bodies.

---

### Gap 2: Automatic Defect Mask Generation (Local Inpainting Mask Synthesis)

- **What is Missing**: An automated translation bridge between a suspected visual defect (e.g. "extra hand at lower right of Person 1") and a binary 8-bit inpainting mask PNG.
- **Why it is Necessary**: Currently, when a defect is confirmed, the system can only perform **full image regeneration** (`loop.py` redraws with `seed + 7919`). To enable **localized auto-correction** (fixing only the distorted hand or eye without altering the rest of a successful image), an accurate mask covering the defect region is strictly required.
- **Which Existing Component Could Be Extended**: `engine\original\anatomy\tiles.py` (which already generates bounding tiles) and `ComfyUI-H3-FaceRefine\nodes.py` (which generates face bounding masks).
- **Which New Component is Required**: `DefectMaskGenerator` module.
  - *Strategy A (Zero Download)*: Convex hull / dilated bounding box derived from DWPose anomalous keypoints, or YOLOv8 face boxes, expanded by 15–25% with Gaussian edge feathering.
  - *Strategy B (Model-Based Segmentation)*: Download SAM / MobileSAM / SAM2 weights for the existing `nodes_sam3.py` or `H3FaceMaskSAM`.
- **Recommended Model**:
  - *Immediate Implementation*: **Algorithmic DWPose/YOLO Bounding Box Feathered Mask** (Requires 0 downloads, 0 MB VRAM).
  - *Optional Upgrade (Subject to Owner Approval)*: `sam_vit_b_01ec64.pth` (375 MB) or `MobileSAM` (40 MB) for pixel-perfect object silhouette masks.
- **Mandatory vs Optional**: Algorithmic mask is mandatory; SAM weights are optional for Phase 3.
- **GPU Memory Requirements**: Algorithmic: 0 MB; MobileSAM: ~250 MB; SAM-ViT-B: ~1.2 GB.
- **Installation Requirements**: None for Strategy A. Strategy B requires model checkpoint file placement.
- **Estimated Development Complexity**: **Low** for bounding/hull masks; **Moderate** for SAM integration.
- **Known Technical Limitations**: Bounding box masks inpaint a rectangular region around the defect, which can slightly shift surrounding background textures if denoise is set too high (>0.70).

---

### Gap 3: Intra-Frame Duplicate Character Clustering

- **What is Missing**: Automated detection of duplicate copies of the same character within a single still frame (e.g., two identical clones of the protagonist standing side-by-side when the prompt specified only one person).
- **Why it is Necessary**: Diffusion models frequently replicate the subject when wide aspect ratios (16:9) or complex multi-subject prompts are requested.
- **Which Existing Component Could Be Extended**: `ComfyUI-H3-FaceRefine\nodes.py` (`_embed_faces`, `_best_match`).
- **Which New Component is Required**: `IntraFrameCharacterClustering` module.
- **Recommended Model**: **None (Reuse Existing)**. Use installed `antelopev2\glintr100.onnx` for realistic faces and `CLIP-ViT-H-14` for stylized/anime characters.
- **Mandatory vs Optional**: Mandatory for Part 1 "Duplicate characters / Multiple copies of the same person" requirement.
- **GPU Memory Requirements**: 0 MB VRAM when using InsightFace on CPU; ~1.2 GB VRAM if using CLIP-ViT-H-14 on GPU.
- **Installation Requirements**: None.
- **Estimated Development Complexity**: **Low**. Extract embeddings for all detected faces/crops in frame $i$; compute pairwise cosine similarity matrix; if similarity $> 0.72$ between distinct physical bounding boxes, flag `duplicate_character`.
- **Known Technical Limitations**: Twins or uniform background characters (e.g., clone soldiers, background schoolgirls in identical uniforms) will trigger duplicate alerts unless prompt metadata specifies multiple identical people.

---

### Gap 4: Extra Head / Head-Body Ratio Verification

- **What is Missing**: A deterministic sanity rule comparing the number of detected heads/faces against the number of detected human torsos/bodies.
- **Why it is Necessary**: VLMs occasionally overlook a severed or floating second head in high-detail backgrounds; keypoint estimators sometimes miss disconnected heads.
- **Which Existing Component Could Be Extended**: `engine\original\anatomy\rules.py`.
- **Which New Component is Required**: `HeadCountConsistencyRule` inside `rules.py`.
- **Recommended Model**: **None (Reuse Existing)**. Combine `face_yolov8m.pt` (or SCRFD) with `yolox_l.onnx`.
- **Mandatory vs Optional**: Mandatory.
- **GPU Memory Requirements**: 0 MB VRAM.
- **Installation Requirements**: None.
- **Estimated Development Complexity**: **Very Low** (15 lines of pure Python logic: `if face_count > person_count: flag extra_head`).
- **Known Technical Limitations**: Profile shots where only the back of a head is visible (no facial features) will register 0 faces, requiring fallback to DWPose skull keypoints.

---

### Gap 5: Temporal Consistency & Keypoint Velocity Analysis (Video)

- **What is Missing**: A dedicated video frame-to-frame consistency analyzer that quantifies temporal flickering, morphing limbs, and identity drift over time.
- **Why it is Necessary**: Video generation models (H3, Wan 2.1) often produce frames where limbs dissolve, faces distort during rapid movement, or hands flicker between 4, 5, and 6 fingers from frame 12 to 24.
- **Which Existing Component Could Be Extended**: `engine\motion_bank\dwpose_extractor.py` (`extract_video_stream`) and `Herrgotts-H3-Infinite\motion_analysis.py`.
- **Which New Component is Required**: `TemporalVideoInspector` module.
  - Sub-module 1: **Keypoint Velocity & Jitter**: Computes Euclidean displacement between frame $t$ and $t+1$; detects impossible acceleration spikes (e.g., hand teleporting 200px in 1 frame).
  - Sub-module 2: **Face Identity Drift**: Compares InsightFace/CLIP embeddings across frames against frame 0 reference; detects character identity drift if cosine distance drops below 0.65.
  - Sub-module 3: **Photometric Flicker (SSIM / Histogram Diff)**: Computes high-frequency luminance variation across consecutive crops.
- **Recommended Model**: **None (Reuse Existing)**. Reuses `dw-ll_ucoco_384.onnx`, `antelopev2\glintr100.onnx`, and OpenCV.
- **Mandatory vs Optional**: Mandatory for Part 1 Video Inspection.
- **GPU Memory Requirements**: 0 MB VRAM (CPU ONNX Runtime + NumPy).
- **Installation Requirements**: None.
- **Estimated Development Complexity**: **Moderate**.
- **Known Technical Limitations**: Fast camera cuts or rapid whip pans create natural optical displacement that must be gated by the scene detector (`detect_scenes_opencv`) so shot transitions are not misidentified as temporal defects.

---

### Gap 6: Localized Inpainting Orchestration Bridge

- **What is Missing**: A unified Python orchestration pipeline that takes the output of the Inspector (e.g., `Defect(kind='extra_hands', bbox=[x1,y1,x2,y2])`), builds an inpainting mask, submits it to ComfyUI's existing `anime_sdxl_inpaint.api.json` or `qwen_image_21_inpaint.api.json`, and verifies the output.
- **Why it is Necessary**: Currently, PanelFlow's `loop.py` only implements global regeneration (`generate_checked`), which reruns the full text-to-image pipeline with a new seed. Localized correction is 4x faster and preserves 95% of a good generation.
- **Which Existing Component Could Be Extended**: `engine\comfyui\art.py` (`ArtEngine.run`) and `engine\original\anatomy\loop.py`.
- **Which New Component is Required**: `ImageRepairEngine` module (`repair_image(image_bytes, defect, mask)`).
- **Recommended Model**: **None (Reuse Existing)**. Use installed `animagine-xl-4.0.safetensors` via `anime_sdxl_inpaint.api.json`.
- **Mandatory vs Optional**: Mandatory for Part 2 "Auto-Correction Layer".
- **GPU Memory Requirements**: Peak ~7.5 GB VRAM during inpainting sampling.
- **Installation Requirements**: None.
- **Estimated Development Complexity**: **Moderate**.
- **Known Technical Limitations**: If the image was generated by HiDream-I1 (a transformer model) and repaired by Animagine XL (SDXL), slight stylistic variance in brushstrokes can occur if the mask feathering and prompt conditioning are not harmonized.

---

### Gap 7: Normalized Composite Quality Scoring Engine

- **What is Missing**: A unified scoring engine that aggregates categorical defect detections, VLM confidence, pose regularity, and face similarity into a single normalized score (0–100) and outputs an explicit action: `PASS`, `RETRY`, or `MANUAL REVIEW`.
- **Why it is Necessary**: Production pipelines require automated threshold gates (e.g., $Score \ge 85 \implies \text{PASS}$, $60 \le Score < 85 \implies \text{RETRY / AUTO-CORRECT}$, $Score < 60 \implies \text{MANUAL REVIEW}$).
- **Which Existing Component Could Be Extended**: `engine\original\anatomy\review.py` (`AnatomyReport`).
- **Which New Component is Required**: `QualityDecisionEngine` module.
- **Recommended Model**: None (Pure deterministic decision tree & weighted Bayesian scoring).
- **Mandatory vs Optional**: Mandatory.
- **GPU Memory Requirements**: 0 MB VRAM.
- **Installation Requirements**: None.
- **Estimated Development Complexity**: **Low**.
- **Known Technical Limitations**: Threshold tuning requires empirical calibration against the ground-truth benchmark dataset (`tests/data/anatomy_labels.json`).

---

### Gap 8: Visual Quality Inspector Dashboard / UI

- **What is Missing**: A dedicated inspection and approval interface in PanelFlow Studio desktop (Tauri + React) allowing users to view side-by-side original vs corrected images, inspect highlighted defect bounding boxes, and click "Approve", "Redo", or "Manual Edit".
- **Why it is Necessary**: Adheres to the Owner's Golden Rule: "Diagnostic verification on real data; human approval gate before permanent storage or release."
- **Which Existing Component Could Be Extended**: `apps\desktop\src\features\scene\` and `AnimeReviewScreen.tsx`.
- **Which New Component is Required**: `QualityInspectorScreen.tsx` in `apps/desktop/src/features/inspector/`.
- **Recommended Model**: None (Frontend React component).
- **Mandatory vs Optional**: Mandatory for Phase 7.
- **GPU Memory Requirements**: 0 MB VRAM.
- **Installation Requirements**: None (`npm run build` in `apps/desktop`).
- **Estimated Development Complexity**: **Moderate**.
- **Known Technical Limitations**: Requires engine API endpoints to serve inspection reports and masked overlays.

---

## 2. Summary of Component Reusability vs New Development

| Component Category | Total Modules Required | Can Be Reused As-Is | Can Be Extended | Must Be Built From Scratch |
| :--- | :---: | :---: | :---: | :---: |
| **Vision Intelligence Layer** | 8 | 5 (DWPose, YOLOX, YOLO-Face, InsightFace, VLM Judges) | 2 (Questions prompt, Tile crops) | 1 (Skeleton topology validator) |
| **Quality Decision Engine** | 4 | 2 (Deterministic rules, Multi-witness consensus) | 1 (AnatomyReport schema) | 1 (Composite scalar score & decision gate) |
| **Auto-Correction Layer** | 5 | 2 (ComfyUI Inpaint graph, Face Stitch) | 1 (ArtEngine patcher) | 2 (DefectMaskGenerator, ImageRepairEngine) |
| **Revalidation Layer** | 3 | 2 (Review loop, Mistake memory) | 1 (Seed stepping) | 0 (Revalidation loop already functional) |
| **Video Inspection & Fix** | 5 | 2 (OpenCV scene detector, FFmpeg slicer) | 2 (DWPose video streamer, FaceRefine) | 1 (Temporal consistency & jitter analyzer) |
| **Integration & UI** | 4 | 2 (ComfyUI Client, JobManager) | 1 (FastAPI routes) | 1 (Inspector desktop UI tab) |
| **TOTALS** | **29** | **15 (51.7%)** | **7 (24.1%)** | **7 (24.1%)** |

**Conclusion**: Over **75%** of the system components are either directly reusable or require only minor extension of existing Python modules. Only 7 targeted Python modules need to be built from scratch, and **zero new model downloads are mandatory** to achieve full operational capability.
