# Motion Bank and Motion Studio

Harvest whole-body motion from reference footage, keep it as a skeleton sequence, and use it in ChronoFlow. Code: `engine/motion_bank/`,
API `engine/api/routers/motion_bank.py` (`/api/motion_bank`), desktop page `apps/desktop/src/features/motion_bank/MotionStudio.tsx`
(Library -> Motions), ChronoFlow link `engine/chronoflow/motion_frames.py` + `engine/api/routers/chronoflow_motion.py`.

## Pipeline

1. **Ingest** (`/ingest`): a local file or a URL (yt-dlp) under a rights declaration. `UNKNOWN` is refused; `COMMENTARY_REVIEW` needs a note.
   The declaration is written to `source.json` next to the video.
2. **Segment** (`/segment`): hard cuts from ffmpeg's scene score, plus dissolves and fades from 10 fps colour-histogram differences
   (`segmenter.py`). Measured on a 142 s animated short: 29 takes with ffmpeg alone, 57 with dissolves; the dissolve at 3.6 s that ffmpeg missed
   is now a boundary. It can over-split a continuous take with a big lighting change; the minimum take is 1 s.
3. **Extract** (`/extract`): DWPose (YOLOX-L + dw-ll_ucoco_384, ONNX, files in `ComfyUI/models/dwpose`). The video must come from `/ingest` or the
   request must carry a `rights` declaration; the declaration and source hash are stored with the motion.
   - COCO-WholeBody output (17 body, 6 feet, 68 face, 21 + 21 hands) is converted to the internal layout: OpenPose-18 body (neck = shoulder midpoint),
     21 + 21 hands, 68 face, stored as a `[T, 133, 3]` safetensors tensor (x, y in 0..1, confidence).
   - One actor is followed (NMS, then overlap with the previous box). When he is lost the frame is empty, never another person; after 30 lost
     frames the main person is picked again. Dropouts of up to 8 frames are interpolated.
   - Only the **longest stretch in which the actor was followed** is kept (a cut or the actor leaving ends it). Under 1 s in a row the harvest is
     refused (422). The record says what was dropped (`segment_frames`, `trimmed`, `source_start_sec`, `source_end_sec`).
   - No model files -> 503. A fake skeleton is only stored with `synthetic=true` (tests/demos); it is tagged `synthetic`, shown as FAKE in the UI,
     hidden from ChronoFlow and excluded from guide training.
4. **Library**: SQLite + safetensors in `<app data>/motion_bank` (override with `PANELFLOW_MOTION_BANK_DIR`). Control video is H.264, with a thumbnail;
   `GET /motions/{id}/control_video|thumbnail`, `PATCH` (title, summary, tags), `DELETE` (row and files).

## In ChronoFlow

On a **First + last** card, "From motion..." opens a panel: pick a motion, pick the character picture, choose the start/end of the motion (percent),
optionally say who does what. "Preview poses" shows the two source frames at those points instantly (and saves the skeletons). "Build first + last
pictures" fits those two video frames to the card's canvas and asks the H3-Image pose transfer to draw the character in their poses (`<Picture 1>` the
character, `<Picture 2>` the video frame; see `docs/H3_IMAGE_EDIT.md`). This needs the harvested video to still be on disk.
The two pictures fill the card's first and last slots and the card stores `motion` (id, range, character, rights). Rendering is the ordinary
First + last render, so **H3 invents the movement between the two poses; the skeleton path is not followed.** Only real motions that carry a rights
record are offered. A failure (ComfyUI down, preflight) is an error, never the raw skeleton as a picture. One picture job runs at a time.

### Measured: does the character really take the pose? (not reliably yet)

Real runs 2026-11-17 (RTX 5060 Ti, ~135 s per picture, 269 s for the pair), character = the front view of the owner's `RY-01` sheet, motion =
the 3.6 s umbrella-walker take of an animated short:

- **Skeleton as `<Picture 2>`: fails.** The caption model read the skeleton as "a leaping figure", the result had an energetic pose that did not match
  the skeleton, and the skeleton lines were either painted onto the character (first picture) or drawn beside it (last picture). Skeleton pictures are
  therefore only used for the preview.
- **Source video frame as `<Picture 2>` (what is built): not yet usable on this clip.** The model kept the man from the reference frame and added
  the character as an extra figure where the woman stood, in the reference's composition. The frame had two people, one seen from behind, and the
  hint did not steer it. The earlier successful transfer (docs/H3_IMAGE_EDIT.md) used a clean two-person photograph and positional wording; that
  case has not been repeated through this path. Treat "Build first + last pictures" as **experimental** and look at both pictures before rendering.
  The second picture of the second run was not produced (the run was cut off), so only the first picture was inspected.
- What was verified end to end: listing motions, choosing the range, previewing the source frames and skeletons in the real ChronoFlow page,
  the request/response, the saved files, the card fields (unit-tested), and the failure paths (ComfyUI down, source video gone, no rights record).

## Guide model (experimental)

`guide/` trains a 22 M-parameter diffusion transformer on harvested motions (random 64-frame windows of each clip) and generates skeletons from a
text prompt. Training needs real motions (synthetic ones are skipped unless asked for) and generation refuses until a checkpoint exists.
The text embedder is named and stored in the checkpoint: `clip` (default for the API: the CLIP-L text encoder ComfyUI already has for HiDream, on CPU,
no download) or `hash` (the old offline hash). Measured on 12 action phrases in 4 groups: the closest other phrase is in the same group for 12/12 phrases
with `clip` and 5/12 with `hash` (Ollama's qwen3.5:9b was tried first and does not support `/api/embed`, HTTP 501). The guide model itself is **not trained
on real data yet** (the bank holds no real motion), so its output quality is unmeasured.

## Known limits

- DWPose is built for real people on camera. On a drawn/animated short it followed the main character for ~3.6 s and lost him on back views and
  occlusion (mean body confidence 0.6). Use filmed footage.
- Extraction runs on CPU (`onnxruntime` without the CUDA provider): about 0.2 s per frame (460 frames = 87 s). `/status` reports the provider.
- No pose-controlled video generation: the old Wan 2.1 Fun-Control bridge was removed (its node name was wrong, the checkpoint on disk is not a
  Fun-Control model and nothing called it). ComfyUI has `MiniMaxH3FunControlNetApply` (control video into H3) but `models/model_patches` is empty and
  which control type that patch expects is unverified; adding it needs the owner's approval of the exact file.
- Only the first actor is kept, hands are noisy (mean confidence 0.35-0.45), and the face is not drawn in ChronoFlow pose pictures.
