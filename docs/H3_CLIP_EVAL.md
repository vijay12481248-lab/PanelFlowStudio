# H3 clip evaluator (Phase 0 of the H3 production skill)

`engine/original/clip_eval.py` measures a generated clip instead of scoring it. `evaluate(path, expect_camera="static"|"any")` returns measurements and
flags (`axis`, `status` confirmed|suspected, `t`, `evidence`). There is no overall score. CLI: `python -m engine.original.clip_eval clip.mp4 [any]`.
Cost: about 0.7 s per clip on CPU. Tests: `tests/unit/test_clip_eval.py` (synthetic clips with known zoom, pan, cut, flicker, drift).
`engine/chronoflow/reviewer.py` is deprecated: it returns constant scores (see its docstring).

## What it measures
| Measurement | How | Flag |
|---|---|---|
| Camera zoom / pan / roll | LK tracking + RANSAC similarity about the frame centre, whole frame and outer 18% ring | static-camera clip with zoom or pan above 3%: `confirmed` only if ring agrees in sign, tracker kept >=50% of points and the value is <=50%; else `suspected` |
| Hard cut | frame step >= 8x the median and >= 40 gray levels | `confirmed`, with time |
| Flicker | mean second difference of frame luminance | `suspected` above 1.5 (content dependent) |
| Still picture | mean frame step < 0.3 | `suspected` |
| Appearance drift | HSV histogram distance of 8 sampled frames to frame 0 | `suspected` above 0.35 (when no cut) |
| Audio | stream present, RMS, silent fraction | no stream: `confirmed` |
Also `contact_sheet` (8 timestamped frames, one PNG) and `vlm_witness` (optional, local Ollama `qwen3.5:9b`, yes/no questions on the sheet).

## Measured on real clips (2026-11-07)
**Cat video, 21 H3 clips, owner's labels** (3 bad: `p004_1` water curtain + hair turns blue, `p009_1` neon glitching, `p019_1` scene goes dark and back):
all 3 bad clips are flagged by appearance drift (0.42, 0.63, 0.57 against 0.03-0.10 for the 18 good clips), and also have the highest flicker (0.19-0.44
against <=0.09). 0 of the 18 good clips raise a camera, cut, drift or flicker flag. Only 3 bad clips: this is a gap, not a validated threshold.

**Dawn Gate, 140 clips (no labels beyond notes):**
- `p070` and `p072` (known drift) are both flagged by drift (the picture also changes lighting; the histogram cannot say outfit vs light).
- `p005` has a real unrequested scene change at 0.58 s (looked at: close-up jumps to a flying glider); the only cut flagged, and correct.
- `p078` has fast continuous motion with frame steps up to 28; the first cut floor (25) flagged it wrongly, so the floor is now 40.
- With a static camera expected, 119 of 140 clips have |zoom| or pan above 3%: `film.py`/`animate.py` ask for a push-in in every shot, and the median
  zoom is about +9%. Part of the "unwanted zoom" is requested by our own prompt.
- Drift flags 35 of 140 clips. There are no labels for the others, so the false-positive rate on action clips is UNKNOWN; on action content drift is a
  trigger for a closer look only.

**VLM witness (qwen3.5:9b on a contact sheet, 2 runs, 12 clips):** low recall. It named the hair change in `p004_1` (2/2), described `p009_1` unstably,
missed the darkening in `p019_1` (0/2), missed the real cut in `p005` (0/2) and found the zoom in `p039` (2/2). It raised no defect on 5 good clips.
~15 s per question set. Use it to explain a measured flag, never to detect.

## Known limits
- Camera estimate fails on very fast motion and cuts (values like -160% pan appear); the 50% sanity cap keeps those from being `confirmed`.
- In a close-up the subject dominates the tracked points; whole-frame and ring agreeing is evidence, not proof, that the camera moved.
- Identity and object integrity are not measured deterministically yet (no face/CLIP embedding check, no SAM3 weights found). Next phase.
- Thresholds are provisional (21 + 140 clips); re-check them when more labelled failures exist.
