# PanelFlow Studio — Integration & Handoff Guide

## 1. Quickstart Usage

### Python API Integration
```python
from pathlib import Path
from engine.render import RenderEngine, RenderProfile, MusicDurationPolicy
from engine.motion.models.timeline import VisualTimeline
from engine.motion.models.input_contract import MasterAudioTimeline

# 1. Initialize RenderEngine
engine = RenderEngine()

# 2. Compile RenderPlan
plan = engine.compile_render_plan(
    timeline=visual_timeline,
    master_audio=master_audio_timeline,
    source_assets_map={"page_01": "path/to/page_01.jpg"},
    bgm_path="path/to/music.ogg",
    profile=RenderProfile.standard_1080p(),
    music_policy=MusicDurationPolicy.LOOP,
)

# 3. Preflight Check
is_ready, issues = engine.preflight_check(plan)
if not is_ready:
    raise RuntimeError(f"Preflight failed: {issues}")

# 4. Execute Render
audit_report = engine.execute_render(
    plan=plan,
    output_mp4_path=Path("output/movie.mp4"),
    progress_cb=lambda stage, current, total, pct: print(f"[{stage.value}] {pct:.1f}%"),
)

if audit_report.is_valid:
    print(f"Video rendered successfully: {audit_report.output_mp4_path}")
```

---

## 2. Command-Line Interface (CLI)

### Rendering From Timeline Files
```bash
python tools/render/render_project.py \
  --timeline path/to/visual_timeline.json \
  --audio path/to/master_audio_timeline.json \
  --assets-dir fixtures/sample_comic \
  --bgm assets/cinematics/intro/audio/someone_stayed_ace_master.ogg \
  --output output/rendered_video.mp4 \
  --profile standard_1080p \
  --music-policy LOOP
```

### Running Real Production Acceptance
```bash
python tools/render/run_real_production_render.py
```

---

## 3. Generated Artifacts Reference

| Artifact Path | Format | Description |
|---|---|---|
| `output/milestone7/first_real_panelflow.mp4` | MP4 (H.264 / AAC) | Certified broadcast-ready 1080p 30fps video file |
| `output/milestone7/visual_timeline.json` | JSON | Motion Director visual timeline recipe |
| `output/milestone7/render_plan.json` | JSON | Frame-accurate discrete RenderPlan with deterministic hash |
| `output/milestone7/validation_report.json` | JSON | Full ffprobe stream metadata, quality flags, frame sample audits |
| `output/milestone7/render_acceptance_manifest.json` | JSON | Top-level acceptance manifest with timings and render speeds |
| `output/milestone7/workspace/audit_samples/contact_sheet.jpg` | JPEG | 5-point frame contact sheet for human visual review |
