# PanelFlow Studio — Acquisition Integration Handoff & Future UI Contract

## 1. Concurrency Boundary Adherence

In accordance with project agent concurrency instructions:
- **Zero changes** were made to `engine/story/`, `engine/audio/`, Narrative IR, Video Script, TTS, or Music subsystems.
- **Zero changes** were made to story/audio database models or shared desktop UI routes.
- The entire adaptive extraction engine is self-contained within `engine/acquisition/web/`.

---

## 2. Python Backend Integration Interface

Downstream background jobs or API endpoints can consume `AdaptiveChapterExtractor` via:

```python
from engine.acquisition.web.chapter_extractor import AdaptiveChapterExtractor

extractor = AdaptiveChapterExtractor()

# Step 1: Inspect and Extract Chapter Manifest (Dry-run)
result = await extractor.extract(url)

if result.state == ExtractionState.EXTRACTED:
    manifest = result.manifest
    # Step 2: Resumable download into project workspace
    dl_status = await extractor.download(
        manifest=manifest,
        output_dir=project_workspace / "source",
        progress_cb=job_progress_callback,
        cancel_token=cancel_token,
    )

elif result.state == ExtractionState.NEEDS_REVIEW:
    # Surface candidate clusters to user in Teach Mode
    clusters = result.candidate_clusters
```

---

## 3. Future Desktop UI Specification

When wiring the desktop React/Tauri interface:

### A. URL Input & Inspection Card
- **User Action**: Pastes URL into the "New Project from Web" input field.
- **UI State**: Displays loading skeleton while executing `extractor.extract(url)`.
- **Card Display**:
  - **Series / Chapter Title**: e.g., *"Chapter 42: The Awakening"*
  - **Discovered Pages**: e.g., `38 pages`
  - **Extraction Strategy**: e.g., `Rendered DOM + Network Verification`
  - **Confidence**: e.g., `97%`
  - **Completeness**: e.g., `98% (Contiguous 1..38)`
  - **Content Layout**: `Paged Comic` or `Long-Strip Webtoon`
  - **Thumbnail Strip**: Horizontal carousel of page previews.
  - **Action Button**: `[ Confirm & Acquire ]`

### B. Teach Mode Modal (`NEEDS_REVIEW`)
If the extractor returns `state == "NEEDS_REVIEW"` (e.g. uncertain between two large image clusters):
- **UI Prompt**: *"We found multiple possible image groups in this reader. Please select the correct chapter pages:"*
- **Choices**:
  - **Group A**: 36 large images (800x1200px) from `/manga/ch42/`
  - **Group B**: 12 cover thumbnails (150x200px) from `/recommendations/`
- **User Action**: User clicks Group A -> sends `teach_selection(result, "cluster_1")`.
- **Outcome**: Engine caches a permanent `ReaderRecipe` for that domain and advances to acquisition.
