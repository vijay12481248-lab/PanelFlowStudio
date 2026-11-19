# Technical Risks, Limitations, and Mitigation Strategies

**Date of Audit**: 2026-11-19  
**Target Architecture**: AI Visual Quality Inspector and Auto-Correction System

---

## 1. Primary Risk Matrix

| Risk Category | Specific Failure Mode | Severity | Likelihood | Impact on Production | Proven Mitigation Strategy |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Hardware / VRAM** | GPU Out-of-Memory (OOM) crash during concurrent execution | **CRITICAL** | HIGH | Crash of ComfyUI or Ollama daemon; aborted batch jobs. | **Strict Sequential Execution Lifecycle**: Offload/free generation VRAM before launching VLM; run DWPose and InsightFace strictly on CPU (0 MB VRAM). |
| **Model Accuracy** | VLM undercounting extra limbs or hallucinating correctness | **HIGH** | HIGH | Undetected four-handed characters delivered to YouTube. | **Never rely on numerical VLM answers**: Require blind line enumeration ("HAND 1: ..."); enforce dual-witness consensus + DWPose geometric cross-check. |
| **Domain Shift** | Face and pose detectors failing on anime, stickmen, or cartoons | **HIGH** | MEDIUM | Degraded detection and false alarms on non-photorealistic styles. | **Tri-modal fallback**: Pair YOLOv8m (trained on anime/cartoons) with CLIP-ViT-H-14 feature embeddings when InsightFace SCRFD detects 0 faces. |
| **Inpainting Clash** | Visual seam or brushstroke mismatch between base generator and inpainter | **MEDIUM** | MEDIUM | Repaired patch looks like a blurry sticker on top of sharp art. | **Mask Feathering & Denoise Tuning**: 16–32px Gaussian blur on mask edge; set denoise to 0.55–0.68; fallback to global redraw if inpaint fails revalidation. |
| **Video Motion False Positives** | Intentional whip pans or scene cuts flagged as temporal glitches | **MEDIUM** | HIGH | Unnecessary shot regeneration; broken video pacing. | **Scene Detector Gating**: Run `detect_scenes_opencv` first; reset temporal tracking buffers across detected cut points. |
| **Throughput / Latency** | Inspection overhead adding 45–60 seconds per generated panel | **MEDIUM** | HIGH | 15–20 minute delay on 13-panel video rendering pipelines. | **Tiered Gated Inspection**: Run instant CPU CV checks (150 ms) first; invoke heavy multi-tile VLM only if CV reports anomaly or for hero keyframes. |
| **Licensing / Legal** | Monetization blocked by non-commercial or regionally restricted models | **HIGH** | LOW | YouTube copyright or license violation. | **Licensing Registry Gate**: Enforce `workflow_registry.json` license metadata; prevent usage of retired or restricted weights in commercial profiles. |

---

## 2. In-Depth Analysis of Critical Technical Risks

### 2.1 The VLM Hallucination & Undercounting Problem
- **The Empirical Reality (Measured 2026-11-16)**:
  When asked *"How many arms does this person have?"* for a known 4-armed generation (seed 101), both `qwen3.5:9b` and `Qwen3-VL 8B` responded `"2"`. Standard VLM prompts suffer from strong prior bias (humans have 2 arms) and will hallucinate standard anatomy even when four arms are clearly drawn.
- **The Codebase Solution (Already Proven in `engine/original/anatomy/`)**:
  1. The prompt never asks for a count.
  2. The prompt forces the judge to enumerate:
     ```
     HAND 1: <which side of the picture, and what the hand is touching or doing>
     HAND 2: <...>
     ```
  3. Python code counts the non-empty lines. If line count $> 2 \times \text{person count}$, a defect is declared.
  4. Multi-tile crops (whole, top, middle, bottom bands at 1280px) are fed independently. A defect is confirmed if 2 judges agree OR if 1 judge confirms across 2 distinct zoomed tiles.

---

### 2.2 Domain Variance Across Art Styles (Realistic vs Manga vs Stickman)
- **The Challenge**:
  The system must evaluate photorealistic characters, stylized anime, and minimal stickmen.
- **Detection Performance Breakdown by Style**:
  - **Photorealistic**: InsightFace Antelopev2 (SCRFD + Glintr100) and DWPose perform at 98%+ precision.
  - **Anime / Manga**: InsightFace SCRFD detector recall drops significantly. YOLOv8m (`face_yolov8m.pt`) maintains 92%+ recall. CLIP-ViT-H-14 must be used for identity embeddings rather than ArcFace.
  - **Stickman / Minimalist**: Facial detectors find 0 faces. DWPose keypoint detection often detects line segments as bones but can lose finger keypoints.
- **Architecture Defense**:
  The system detects the art style dynamically: if face detection returns 0 candidates but person detection $>0$, it automatically switches to CLIP-Vision character embedding and relaxes finger keypoint penalties.

---

### 2.3 Cross-Model Inpainting Style Mismatch
- **The Problem**:
  Base text-to-image art is generated using **HiDream-I1 Fast** (a 16 GB MIT-licensed Flow Transformer). The active inpainting workflow uses **Animagine XL 4.0** (a 6.6 GB SDXL UNet). Inpainting a small region with a model trained on different latent geometry can cause subtle boundary artifacts or color shifts.
- **Mitigation Protocol**:
  1. **Gaussian Feathering**: Dilate mask by 12–24 pixels and apply a soft Gaussian edge falloff.
  2. **Conservative Denoise**: Bound latent denoise between 0.55 and 0.65.
  3. **Revalidation Gate**: If the inpainting pass introduces a texture discontinuity or fails re-inspection, the system discards the patch and falls back to **global seed-stepped redraw** (`seed + 7919`).

---

### 2.4 GPU Memory (16 GB) Contention and Deadlock
- **Physical Reality**:
  The RTX 5060 Ti has 16,311 MiB of VRAM. Operating system rendering takes ~1.6 GB.
  - Loading HiDream-I1 Fast + Ollama `qwen3.5:9b` simultaneously requires: $12.5\,\text{GB} + 6.5\,\text{GB} + 1.6\,\text{GB} = 20.6\,\text{GB}$ $\implies$ **INSTANT OOM CRASH**.
- **Architectural Guarantee**:
  - All CV feature extraction (DWPose, YOLOX-L, InsightFace) is pinned to **ONNX Runtime CPU**. It consumes ~1.2 GB of System RAM and **0 MB of VRAM**.
  - ComfyUI and Ollama are orchestrated sequentially by `engine/jobs/workflow.py` with memory-release barriers between generation, semantic inspection, and inpainting passes.

---

### 2.5 Pipeline Latency Budget
- **Measured Latency Profile**:
  - Image Generation (HiDream-I1 Fast): ~49 seconds.
  - CPU CV Feature Extraction (DWPose + Face): ~180 milliseconds.
  - VLM Blind Multi-Tile Review: ~45–60 seconds.
  - Localized Inpainting Pass (if triggered): ~4 seconds.
- **Throughput Optimization (Tiered Inspection)**:
  - **Tier 1 (Instant CPU Gate, 180 ms)**: Check DWPose skeleton connectivity and face count ratio. If an extra limb or extra head is detected with $>0.90$ confidence, immediately trigger inpainting or redraw without waiting for VLM.
  - **Tier 2 (Full VLM Multi-Tile Review, 45–60 s)**: Reserved for hero panels, thumbnail generation, or assets where Tier 1 reports ambiguous confidence.
