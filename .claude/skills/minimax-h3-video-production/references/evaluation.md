# Evaluating a clip

Tool: `engine/original/clip_eval.py` (details and calibration data in `docs/H3_CLIP_EVAL.md`).
`python -m engine.original.clip_eval clip.mp4 [any]` -> JSON: measurements + flags. `expect_camera` = `static` (default) or `any` (a move was asked for). Cost ~0.7 s per clip.

## Procedure
1. Run `evaluate`. 2. Open `contact_sheet` (8 timestamped frames) and look: the evaluator misses identity, objects and prompt adherence. 3. Write each finding with a time, a status and its evidence. 4. Only then say pass/fail. No single overall score.

## Axes and how each is measured
| Axis | Measured by | Status |
|---|---|---|
| Camera control | whole-frame and border-ring zoom/pan/roll (LK + RANSAC about the centre); `confirmed` only if both agree, inliers >= 0.5, and |zoom| <= 50% or tracker inliers >= 0.9 (a +164% zoom with inliers 0.99 was real) | measured |
| Temporal / unexpected transition | hard cut: step >= 8x median and >= 40 gray levels (`confirmed`); tracker loses the picture in >= 5 frame steps (`suspected`: whip/morph transitions or violent motion; flags 19/140 Dawn clips at >=3 steps; cross-dissolves are NOT detected) | measured (caught `p005`'s cut; its later fast transition only as suspected) |
| Visual artifacts / flicker | luminance second difference > 1.5 | measured, content dependent |
| Motion quality | mean frame step < 0.3 = still | measured |
| Lighting / colour consistency | histogram drift > 0.35 vs frame 0 | trigger only: 3/3 bad cat clips, 0/18 good; 35/140 Dawn Gate flags unlabelled |
| Audio presence/level | `audio_stats`, loudness, ASR WER | measured |
| Character consistency, composition, object integrity | contact sheet by eye; VLM witness | **no deterministic measure yet** |
| Prompt adherence | by eye against the prompt; VLM only to explain | not measured |
| Audio-visual sync | anchored voice by construction; ASR | timing not measured |

## Status words
- **confirmed**: a measurement backs it (cut, zoom beyond threshold with agreeing border, no audio).
- **suspected**: a trigger fired or the measurement is unreliable (inliers low, value over 50%, flicker, drift). Look at the frames before acting.
- **stylistic**: differs from the prompt but is a taste choice (lens flare style, colour grade).
- **acceptable**: creative variation inside the brief (extra blink, small prop shift).

## VLM witness `[verified: qwen3.5:9b, 12 clips x 2 runs]`
Low recall: found the hair change (2/2), the zoom (2/2); missed the darkening and the real cut (0/2 each); no false defects on 5 good clips; ~15 s per set. Use `vlm_witness` to explain a measured flag; never to decide, never alone. Require agreement between two witnesses (two metrics, or metric + VLM) before `confirmed`.

## Thresholds
Provisional (21 cat + 140 Dawn clips + 6 Phase 1 shots). Re-check when new labelled failures exist; record changes with the evidence in `docs/H3_CLIP_EVAL.md`.

## Report format
`clip, prompt hash, seed, workflow; per flag: axis, status, t, evidence, frame; what was NOT checked`.
