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

## Phase 1 experiments (2026-11-07): is the zoom our prompt, and are short clips worse?
Script: `tools/h3_phase1_experiment.py`; clips in `output/H3_Phase1/{base,static,long}/` (git-ignored). Six silent Dawn Gate shots (`p003 p031 p088` extreme close-up,
`p012 p046 p060` close-up), same first frame and seed in every variant; one change per variant.

**Reproducibility:** `base` (current prompt and length) regenerated all six existing Dawn Gate clips with mean pixel difference 0.00. Same frame + prompt + seed + workflow
gives the same clip, so single-lever comparisons are real, not noise.

| Variant | what changed | mean \|zoom\| | median drift | mean frame step | camera flags |
|---|---|---|---|---|---|
| base | nothing (push-in line, 56/73 frames) | 38.4% | 0.27 | 5.68 | 6 of 6 clips |
| static | camera sentence = "Static Shot, fixed on a tripod, no zoom, no pan, no tilt" | **0.8%** | 0.18 | 3.09 | **0 of 6** |
| long | length 124 frames (5.17 s), push-in kept | 54.8% | 0.32 | 6.25 | 6 of 6 |

- **The push-in sentence causes the zoom.** 6 of 6 shots went from +6% to +164% zoom to between -1.3% and +2.5%. The "very slight" push-in on extreme close-ups still gave +6 to +7%.
- **Static kept the action in the shots I looked at.** `p012` still shows the smile fall and eyes close with a fixed camera. In `p046` the goggle lenses glow as asked; with the push-in
  the glow appeared in his eyes instead (one example, a hypothesis that a fixed camera helps adherence).
  Mean frame step fell from 5.68 to 3.09: part of that is the zoom itself, but the action may also be calmer. Needs a check on action-heavy shots.
- **Short clips are not worse; longer ones invent more.** 124 frames did not reduce drift or flicker: more zoom (`p088` +95%, `p003` +24%), more drift, and the golem in `p088` changes
  shape and loses its foreground hands. The "56/73 frames are off-spec" hypothesis is NOT supported for these prompts. Caveat: the prompt describes one short action, so more time is
  filled by invention; `static` + `long` was not run.
- The evaluator's flags matched what I saw: `p046` base and `p088` long were marked `suspected` (zoom above the 50% trust cap), `p060` base got the flicker flag (fast-moving stars).
- Not covered: dialogue shots, wide shots, other stories, more than 6 shots.

**Recommendation (not applied; `film.py` has the owner's uncommitted edits):** default the camera sentence to the Static Shot wording and make a push-in or move an explicit per-shot
choice; keep clip length as is.
