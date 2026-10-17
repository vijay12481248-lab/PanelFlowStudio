# PanelFlow Studio — Pipeline Specification

## Pipeline Overview

PanelFlow Studio processes graphic literature through a deterministic multi-stage workflow. Each stage has strict preconditions, atomic operations, and verifiable outputs.

```mermaid
flowchart LR
    NEW[NEW] --> RA[RIGHTS_APPROVED]
    RA --> ACQ[ACQUIRED]
    ACQ --> NORM[NORMALIZED]
    NORM --> PD[PANELS_DETECTED]
    PD --> OCRC[OCR_COMPLETE]
    OCRC --> OCRA[OCR_APPROVED]
    OCRA --> SG[SCRIPT_GENERATED]
    SG --> SA[SCRIPT_APPROVED]
    SA --> VG[VOICE_GENERATED]
    VG --> SPG[SHOT_PLAN_GENERATED]
    SPG --> REND[RENDERED]
    REND --> QAA[QA_APPROVED]
    QAA --> EXP[EXPORTED]
```

---

## Phase 1 Operational Stages

### 1. NEW
- **Description**: The project has been registered in the database, and its workspace directory structure has been created (`source/`, `logs/`, `project.json`).
- **Preconditions**:
  - Valid title provided.
  - Source type and locator (directory path, archive path, or URL) provided.
- **Outputs**:
  - `ProjectRecord` created in SQLite.
  - Workspace directory initialized at `projects/<id>/`.
  - Initial `project.json` written to disk.

### 2. RIGHTS_APPROVED
- **Description**: Legal and rights verification has been recorded and approved.
- **Preconditions**:
  - `rights_status` must NOT be `UNKNOWN`.
  - Must be one of `PUBLIC_DOMAIN`, `CREATIVE_COMMONS`, `LICENSED`, `USER_OWNED`, or `EXPLICIT_PERMISSION`.
  - License notes or permission details documented.
- **Rule**: If `rights_status` is `UNKNOWN`, the project CANNOT progress to acquisition or downstream publication.

### 3. ACQUIRED
- **Description**: Source images have been fetched, decoded, validated, hashed, stored deterministically, and reviewed.
- **Operations**:
  1. **Inspection**: Adapter discovers chapters and page candidates.
  2. **Deterministic Ordering**: Candidates are sorted by natural alphanumeric sort.
  3. **Download / Import**: Assets are streamed into temporary buffers.
  4. **Validation**: Content-type verified; image headers and raster decodability checked with Pillow/OpenCV. Corrupt images or HTML error pages are caught and rejected.
  5. **Deduplication & Storage**: Image copied to `projects/<id>/source/page_{sequence:04d}.{ext}`. SHA-256 computed.
  6. **Resequencing & Review**: User can reorder, delete blank/corrupt pages, and rotate images before confirming order.
  7. **Manifest Generation**: Canonical `manifest.json` written to project root.
- **Outputs**:
  - `manifest.json` describing all pages and source hashes.
  - `pages` table records updated with dimensions, size, and hash.
  - Project status promoted to `ACQUIRED`.

---

## Phase 1.5 Operational Stages

### 4. NORMALIZED
- **Description**: Non-destructive image preprocessing and standardization. Source images in `source/` remain strictly immutable.
- **Preconditions**: Project must be in stage `ACQUIRED` with valid `source/` files.
- **Operations**:
  - EXIF orientation auto-rotation (`ImageOps.exif_transpose`).
  - Alpha channel flattening onto pure white paper backing.
  - Color profile conversion to sRGB.
  - Working resolution scaling (default 1920px target width with aspect ratio preservation).
  - Webtoon long-strip classification (`aspect >= 2.5` or `height >= 4000`).
- **Outputs**:
  - `projects/<id>/normalized/` directory containing derivative images (`page_0001.jpg`, etc.).
  - `page_normalizations` database records storing source SHA-256, normalized SHA-256, dimensions, and operational flags.
  - Project stage promoted to `NORMALIZED`.

### 5. PANELS_DETECTED
- **Description**: Automated panel segmentation identifying individual comic panels with human-in-the-loop review.
- **Preconditions**: Project must be in stage `NORMALIZED`.
- **Operations**:
  - Polarity-aware gutter survey detecting light or dark gutter modes.
  - Morphological edge closing and adaptive thresholding extracting candidate panels.
  - Nested contour filtering suppressing internal artwork doodles while preserving inset panels.
  - Webtoon vertical strip chunking (3000px tiles with 1200px overlap).
  - Reading order calculation (`ltr`, `rtl`, `vertical`) tracking `sequence_page` and `sequence_global`.
  - Fallback to `FULL_PAGE` marked `NEEDS_REVIEW` if zero contours qualify.
  - Visual review canvas enabling drag, resize, split (horizontal/vertical), merge, and timeline resequencing.
- **Strict Stage Gating Rule**: Automated detection execution leaves the project in `NORMALIZED`. The project transitions to `PANELS_DETECTED` **only** upon explicit user confirmation via `POST /api/projects/{id}/panels/confirm`.
- **Outputs**:
  - `projects/<id>/panels/` containing cropped panel images and previews.
  - `panels` table populated with canonical `PanelRecord` entries.
  - Canonical `panels.json` written to workspace root.

---

## Phase 2 Operational Stages

### 6. OCR_COMPLETE
- **Description**: Automated speech balloon segmentation and optical character recognition.
- **Preconditions**: Project must be in stage `PANELS_DETECTED`.
- **Operations**:
  - Speech bubble, caption box, and onomatopoeia localization via `ClassicalTextRegionDetector`.
  - Fallback to whole-panel center region marked `NEEDS_REVIEW` if zero distinct balloons qualify.
  - OCR extraction across regions using pluggable `OCREngine` (`mock_ocr`, `windows_media`, `paddle_ocr`, `manga_ocr`, `vision_llm`).
  - Content-addressed OCR cache (`ocr_cache` table) keyed by SHA-256 of crop image + engine + settings.
  - Machine provenance saved immutably to Layer 1 (`raw_text`, `raw_confidence`, `ocr_engine`, `ocr_extracted_at`) in `text_regions` table.
  - Automatic quality flagging: any region with confidence $< 0.70$ or empty text is assigned `status="NEEDS_REVIEW"`.
- **Outputs**:
  - Populated `text_regions` table.
  - Project stage promoted to `OCR_COMPLETE`.

### 7. OCR_APPROVED
- **Description**: Human-in-the-loop review, dialogue correction, and speaker assignment preparation.
- **Preconditions**: Project must be in stage `OCR_COMPLETE`.
- **Operations**:
  - OCR Review UI allows line-by-line correction of transcript errors.
  - Edits written to Layer 2 (`corrected_text`, `corrected_by`, `correction_status="VERIFIED"`), preserving immutable Layer 1.
  - Optional speaker attribution hook in Layer 3 (`speaker_character_id`, `speaker_confidence`, `speaker_assignment_method`).
  - **Strict Gate Rule**: `POST /api/projects/{id}/ocr/confirm` executes atomic database validation. If ANY text region remains in `NEEDS_REVIEW` status, approval is strictly blocked (HTTP 400 Bad Request with unresolved count).
- **Outputs**:
  - Project stage promoted to `OCR_APPROVED`.
  - Canonical Downstream Export Contract available at `GET /api/projects/{id}/export/contract` for Milestone 4 (Story Understanding) handoff.

---

## Milestone 4 Pipeline Stages (Implemented)

### 8. STORY_ANALYZED
- **Description**: Story analysis and Narrative IR extraction from approved OCR.
- **Preconditions**: Project must be in stage `OCR_APPROVED`.
- **Operations**:
  - Deterministic balloon geometry heuristics (narration boxes, solitary character, tail vectors, left/right positioning).
  - Character discovery, alias resolution, and canonical identity tracking.
  - Physical event extraction (ENTER, ATTACK, DISCOVER, etc.).
  - Scene segmentation and dramatic beat structuring with advisory intents.
  - Automated continuity audit detecting invalid speakers, missing actors, or misorders.
- **Outputs**:
  - Project stage promoted to `STORY_ANALYZED`.
  - Canonical `narrative.json` sidecar and database records.

### 9. STORY_APPROVED
- **Description**: Human director approval of the Narrative IR.
- **Operations**:
  - Review in `StoryReviewScreen`: character merge/split, speaker reassignment, scene boundary adjustments.
  - Strict gate: Blocks approval if any critical `ERROR`-severity continuity warnings exist.
- **Outputs**: Project stage promoted to `STORY_APPROVED`.

### 10. SCRIPT_GENERATED
- **Description**: Script adaptation transforming Narrative IR into spoken video script format.
- **Preconditions**: Project must be in stage `STORY_APPROVED`.
- **Operations**:
  - Synthesizes narration and dialogue segments according to selected profile (`FAITHFUL`, `CONDENSED`, `DRAMATIC_NARRATION`, `ACCESSIBLE_RECAP`).
  - Calculates line-by-line timing via deterministic WPM math and cadence punctuation pauses.
  - Evaluates faithfulness against source evidence (`SUPPORTED`, `WEAKLY_SUPPORTED`, `UNSUPPORTED`).
- **Outputs**: `story/script.json` and database records.

### 11. SCRIPT_APPROVED
- **Description**: Human-in-the-loop review and approval of video script.
- **Operations**:
  - Interactive line editing, duration re-calculation, emotion/intensity tuning, and advisory motion intent.
  - Approval gate confirms script for downstream motion and audio planning.
- **Outputs**: Project stage promoted to `SCRIPT_APPROVED`.

---

## Future Pipeline Stages (Milestone 5+)

### 12. VOICE_GENERATED
- **Description**: Line-by-line speech synthesis using TTS engines.
- **Operations**:
  - Synthesis generated per line (never as one giant monolithic narration file).
  - Storage under `audio/characters/<char_id>/line_<seq>.wav`.
  - Silence padding and breath adjustment.

### 13. SHOT_PLAN_GENERATED
- **Description**: Algorithmic camera planning for motion comics.
- **Operations**:
  - Generates structured camera instructions: `pan_left`, `slow_zoom_in`, `face_focus`, `impact_shake`, `parallax`, `crossfade`.
  - Structured shot-plan JSON output (never allows the LLM to directly mutate video frames).

### 14. RENDERED
- **Description**: Deterministic video composition using FFmpeg.
- **Profile**: 1920x1080, 30 FPS, H.264 video, AAC 48 kHz audio.
- **Outputs**: `renders/` intermediate scene clips and final composite draft.

### 15. QA_APPROVED
- **Description**: Automated audio-visual verification.
- **Checks**: Audio clipping, sync drift, blank frames, missing subtitles, aspect ratio integrity.

### 16. EXPORTED
- **Description**: Final master package exported to target distribution format with burned or sidecar captions (`.srt`/`.vtt`).
