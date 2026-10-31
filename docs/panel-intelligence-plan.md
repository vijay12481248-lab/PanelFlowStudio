# Panel Intelligence Milestone — Plan

Goal: every rendered video shows exactly the story panels, cropped to real panel
boundaries, with zero scanlator promotion, in the order the narration speaks about them.

## 1. Why the same problems keep coming back (evidence, 2026-10-31)

Checked against the real app database (`%LOCALAPPDATA%\PanelFlow Studio\database\panelflow.db`).

| Symptom | Root cause | Evidence |
|---|---|---|
| Promo text visible in Ch 927 | Cleanup only runs inside panel *detection*. Projects detected before the feature (committed 2026-10-29) or re-run with "skip existing" never get cleaned. | Ch 927 (created 10-26): `content_cleanup_report = NONE`. Ch 928 (10-30): report present. |
| "READ FIRST AT" blurred but "MANHUAPLUS.COM" still visible | Matching is per OCR line. OCR reads the white outlined line but misses the red/black italic logo on dark art, so only half the stamp is blurred. | Ch 928 panels #22, #28: one line matched, logo left untouched (verified on the crop files). |
| 快看漫画 (Kuaikan) watermark visible | Not in the label list, and it is a graphic stamp, not reliable OCR text. | Ch 928 panel #7, Ch 927 Act 3 preview. |
| Cover / Discord outro shown | Cover/outro decisions are `REVIEW`, which waits for a human and is never resolved in an unattended run. | Ch 928 #1 and #48 were `REVIEW`. |
| "Whole page" shown instead of a panel | The webtoon splitter cuts only where a full-width band is plain background for ≥25 px. Bubbles, smoke, gradients and SFX that cross gutters merge several panels into one crop. Side-by-side/staggered panels are never split horizontally. | Ch 928: crops of 1920×5822, 1920×6025, 1920×6018 contain 3–4 panels each. Log Into The Future 1–5: 70 `FALLBACK` full-page panels. |
| Fixes regress | No test runs on real chapters, and no gate checks the *final video*. Unit tests use synthetic images only. | `tests/unit/test_automatic_content_cleanup.py` and the panel benchmark fixtures are synthetic. |

## 2. How manhua / webtoon chapters are built (what the system must understand)

- **One continuous vertical strip**, cut into "pages" arbitrarily by the uploader. A panel can start at the bottom of page N and finish at the top of page N+1.
- **Panel styles**: framed rectangles; borderless art that fades into the background; full-width splash; two or three panels staggered side by side; inset panels; panels tilted or broken by action.
- **Gutters** are large vertical gaps whose colour changes with mood (white → black → blue). Narration boxes and speech bubbles often sit *in* the gutter or straddle a border.
- **Non-story content** follows a pattern:
  - cover/credits page first (`CH 927`, `TL:`, `PR:`, `TS:`, `RP:`, website, Patreon);
  - scanlator stamps on story panels (`READ FIRST AT` + logo), same graphic every time;
  - original-publisher watermarks baked into the art (快看漫画, Bilibili and others), usually bottom-right;
  - promo banners between panels ("IF YOU ENJOYED THIS SERIES…");
  - outro panel last (Discord/Patreon bubble on top of artwork).

## 3. Design

### 3.1 Non-story and watermark removal (deterministic, cheap, runs every time)

1. **Always run cleanup** for any active panel without a report matching the current crop hash and rules hash (the fingerprint already exists). Run it at autopilot start and in the panels stage, not only on new detections.
2. **Logo template matching** (OpenCV multi-scale `matchTemplate`) for fixed stamps: ManhuaPlus `READ FIRST AT` logo, the "IF YOU ENJOYED" banner, 快看漫画, and others. Templates live in app data. Panel Review gets an "Add as watermark template" action on a drawn box. This does not depend on OCR reading stylised text.
3. **Text-block grouping**: when one OCR line matches, expand the blur to the whole block (adjacent lines with overlapping x-range and gap < 1.5× line height).
4. **Cover/credits/outro classifier** with position priors (first 2 and last 2 panels), credit keywords (`TL:`, `PR:`, `TS:`, `RP:`, `CH \d+`, patreon, discord) and the story step's `non_story_panels`. A confident result means EXCLUDE the whole panel automatically (audited, one-click undo). `REVIEW` remains only for a genuinely ambiguous middle-of-chapter panel.
5. **Final-video gate (the "self-review")**: sample a frame every 0.5 s from the rendered MP4 and run template matching plus OCR label matching. Any hit fails the render with the timestamp and panel id. Nothing ships with a leak.

### 3.2 Panel segmentation v2

1. **Strip stitching**: join consecutive pages into one strip (processed in overlapping windows to bound memory), segment the strip, then map boxes back to pages. Panels that span pages become one crop.
2. **Multi-signal candidates**:
   - *Frame detector*: straight-edge / rectangle detection (LSD lines → closed quads) finds bordered panels, including side-by-side and staggered ones.
   - *Gutter detector v2*: mask detected bubbles and text first, then run the projection. A bubble straddling a gutter no longer merges two panels.
   - *Learned detector (evaluate)*: a pretrained comic panel/bubble model (e.g. Magi, or YOLO comic-panel weights). Requirements: check the licence for monetised YouTube use, and run on CPU/GPU locally.
3. **Fusion and sanity rules**: merge candidates by IoU. Any crop with height > 2.5× width, or containing ≥2 internal frame edges, gets a forced re-split attempt. Fall back to a full page only with a visible `FALLBACK` warning in Panel Review, never silently.
4. **Reading order**: top-to-bottom; for side-by-side groups, left-to-right (`ordering.py` exists, so reuse it).
5. Decide whether to reuse or delete the unused `SmartPanelSlicer`, `SmartFramer` and `PanelClassifier`.

### 3.3 Story-synced playback

1. Each narration beat already references panels. Add **shots**: a shot is a panel crop or a sub-region of a tall panel.
2. For tall panels, build camera keyframes that pan between the bubbles/characters in reading order, timed to the beat's audio duration. A bubble's position comes from OCR text regions.
3. Never show a panel the narration skipped. Never hold a static full page. The coverage check (every retained panel exactly once) stays.

## 4. Measurement (so fixes stop regressing)

Build a ground-truth set from real chapters already on disk: Magic Emperor 927, 928; Tales of Demons and Gods 536.1; Log Into The Future 1–5.

- Label panel boxes plus non-story / watermark boxes (about 1 hour per chapter, done in Panel Review).
- Metrics: panel F1 at IoU ≥ 0.7, merged-crop rate, full-page fallback rate, promo leaks in the final video (target **0**).
- These run as a test suite on every change to `engine/imaging/**`.

## 5. Phases

| Phase | Scope | Output | Size |
|---|---|---|---|
| **0. Stop the leaks** | 3.1 items 1–5 | Ch 927 / 928 re-render with zero promo; final-video gate live | 1–2 days |
| **1. Research spike + dataset** | Label 5–8 chapters; benchmark current detector; evaluate learned detectors (accuracy, speed, licence) | Baseline numbers + model decision | 2–3 days |
| **2. Segmentation v2** | 3.2 | Merged-crop rate and fallback rate cut, measured on the set | 4–6 days |
| **3. Story-synced shots** | 3.3 | Shots and pans driven by narration beats | 3–5 days |
| **4. Review UX** | Template capture, fallback warnings, one-click undo | Panel Review updates | 2 days |

## 6. Decisions needed from you

1. Start Phase 0 now (fixes visible leaks in days), or go straight to the full milestone?
2. Learned models: is a non-commercial licence acceptable? Is a GPU available for inference?
3. Auto-exclude cover/outro without review: acceptable, given an audit log and undo?

**Answered 2026-10-31:** full milestone first; commercial-safe licences only; CUDA torch on the RTX 5060 Ti; auto-exclude cover/credits/outro.

## 7. Progress log

### 2026-10-31 — measured on real chapters

Ground truth: `tests/fixtures/panel_truth/magic_emperor_927.json`, `magic_emperor_928.json` (strip coordinates).
Tools: `scripts/panel_truth/` (render, overlay, evaluate, synth, real_tiles, train_detector, detect_learned, sandbox_project, redetect, cleanup_sheet).

| Chapter 928 (held out from training) | Production detector | Strip model + fill (sandbox, end to end) |
|---|---|---|
| Panel F1, IoU ≥ 0.5 | 0.645 | **0.96** |
| Panel F1, IoU ≥ 0.7 | 0.194 | ~0.83 (early checkpoint) |
| Merged multi-panel crops | 8 | 2 |
| Cover / outro shown | via REVIEW limbo | 0 (auto-excluded) |
| Promo marks found (stamps, banners, 快看漫画) | OCR only, partial | 0.83–1.0 recall, ≤1 false |

Log Into The Future ch5 (full-bleed style, no crisp panels, label-free metrics): art rows shown 80% → 99.6%; crops over 2.5× tall 18 → 3.

What changed:
- **Strip detector** (`engine/imaging/panels/strip_detector.py`): fine-tuned RT-DETRv2-R18 (Apache-2.0 base) for panel / bubble / promo on overlapping 1920×3840 windows of the stitched chapter; truncated boxes dropped when a neighbour window sees them whole; pieces of tall panels joined only when windows saw the same rows; crops over 3× tall split at seams avoiding bubbles; uncovered art filled into seam-cut shots. Used for vertical-scroll chapters when a model is installed at `%LOCALAPPDATA%\PanelFlow Studio\models\panel_detector`; otherwise the old per-page detector runs. Pages with an existing timeline stay protected.
- **Cleanup** (`engine/imaging/content_cleanup.py`): any domain / promo phrase (not only listed sites); two-line stamps blurred whole; OCR-split logos joined; credits/cover/outro auto-excluded; detector-seen watermarks blurred; old-rule blurs re-judged from the untouched original; runs on every panel each autopilot run (fingerprinted).
- **Windows OCR bug fixed**: boxes were in the deskewed frame whenever Windows detected slanted text (`TextAngle`), misplacing blurs by ~150 px on italic panels. Note: this provider's confidence is a constant 0.95 — confidence thresholds are meaningless with it.
- **Final-video gate** (`engine/render/promo_gate.py`, `scripts/check_video_promo.py`): OCR every second of the MP4; the render stage fails with timestamps on any promo text. On the old Ch 927 video it reports 100+ hits, starting at 0:00.

Synthetic training data must include full-bleed layouts; the first model was nearly blind to Log Into The Future until the seam fill was added.
