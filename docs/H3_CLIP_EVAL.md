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

**Applied (2026-11-07):** the camera sentence defaults to the Static Shot wording (`animate.STATIC_CAMERA`) and a push-in or other move is an explicit per-shot choice (`Panel.camera`). Clip length unchanged.
Consequence: the prompt of every shot changes, so `film.make_clips` treats all existing Dawn Gate clips as stale and would regenerate them (~158 clips, hours of GPU). The master is built from the existing clips and is unaffected until someone runs that job.

## Phase 3: correction loop (`engine/original/clip_loop.py`)
`python -m engine.original.clip_loop <story_dir> <shot> [--attempts 3] [--camera any] [--suspected] [--apply]`. Levers implemented: `static_camera`, `seed`. Judged by the
worst defect in severity order (temporal > consistency > camera > artifacts > motion > audio); same axis: at least 25% smaller; a tie falls through to the next defect. History:
`<ws>/film/history/<shot>.json`; attempt clips: `<ws>/film/attempts/<shot>/`; the real clip is replaced only with `--apply`. Tests: `tests/unit/test_clip_loop.py` (fake generator, no GPU).

Real runs on an isolated copy of Dawn Gate (2026-11-07, 1-3 attempts each, ~80-110 s per attempt), outcomes checked on contact sheets:
| Shot | Start | Result | Verdict |
|---|---|---|---|
| `p046` | zoom +163.7%, camera confirmed | `static_camera`, 1 attempt: zoom +0.4%, no flags; frames show a fixed camera and the goggle glow as prompted | **fixed** |
| `p070` (dialogue, anchored voice) | zoom -19.9%, drift 0.60 | camera fixed on attempt 2-3 (-2.2%); drift unchanged (0.59): jackets and the whole scene still wash to blue-white by 2.5 s | camera fixed, **colour/outfit drift NOT fixed** |
| `p005` | hard cut at 0.58 s | cut removed by `static_camera`; the new seed kept still jumps from the close-up to the glider at about 1.6 s (flagged only as suspected transition) | **transition not fixed**; loop says "no confirmed defect left; SUSPECTED remain" |

What the real runs taught (fixed in the same phase): the first version ignored a +164% zoom because the evaluator capped confirmation at 50% (now: confirmed when the tracker kept >=90% of points),
compared flag counts instead of size (rejected `p070`'s zoom fix), rejected a fix of a worse defect for adding a minor one (`p005`), and reported "no defect left" while a fast transition was
only suspected (the evaluator now flags a tracker-lost run as a suspected transition and the loop lists remaining suspected flags).
With only camera and seed levers the loop fixes camera defects; drift and scene transitions need the not-yet-built levers (redraw the first frame, simplify the action text). Sample: 3 shots.

### Phase 3b: `simplify_action` and `redraw_frame` levers (2026-11-07)
Same isolated Dawn Gate copy, 3-4 attempts per shot, outcomes checked on contact sheets. Per-attempt records: `output/H3_Phase3/dawn/film/history/<shot>.json` (run 3).
| Shot | Attempts (lever -> decision) | Result |
|---|---|---|
| `p070` | `simplify_action` kept (drift 0.60 -> 0.13), `static_camera` kept (zoom 13.8 -> 8.2%), `seed` kept (5.95%) | **drift fixed**: colours and lighting stay stable in all 8 frames; camera still +6% (confirmed, above the 3% limit). The beat "the blue light growing" was removed by the rule |
| `p005` | `static_camera` kept (cut removed), `simplify_action` discarded, `redraw_frame` discarded, `seed` discarded (3 hard cuts) | **not fixed**: the clip still jumps from the close-up to the glider at about 1.6 s; loop ends "attempts used up", temporal (suspected) left |
Lessons: a growing-light clause in the motion text was the cause of `p070`'s washed-out colours (seeds had not moved it); `p005`'s cause is a first frame (close-up of the girl and the cat) that does not show the flying machine its action describes, which none of the four levers fixes. Next lever if wanted: regenerate the first frame from the ACTION (shot size matching what the motion needs), not a reroll of the same prompt. Sample: 2 shots.

### Phase 3c: `widen_frame` lever (2026-11-07)
`widen_frame` draws the first frame one shot size wider (extreme_close -> close -> medium -> wide) from the same action text; the clip keeps the shot's own size, camera sentence
and length. For temporal defects it is tried after `static_camera`. Run on `p005` (history run 4, 3 attempts, `--suspected`):
| Attempt | Lever | Decision | Evidence |
|---|---|---|---|
| 1 | `static_camera` | kept | the hard cut at 0.58 s is gone |
| 2 | `widen_frame` (medium -> wide) | kept | by eye: the glider banks around the same rock spire from 1.0 s to the end; no jump to a different scene (earlier clips jumped at about 1.6 s). Numbers: camera 30.2 -> 6.8%, drift 0.46 |
| 3 | `simplify_action` | discarded | 4 hard cuts appeared |
Residual problems seen on the kept clip: Pip (the cat) leaves the frame after 0.5 s; one fast move around 1.0 s (the wing fills the frame; the evaluator still marks `temporal` suspected);
camera stays above the 3% limit. The evaluator's flags did NOT show the improvement (the suspected transition flag is unchanged), so this result rests on looking at the frames.
Conclusion (1 shot): when the first frame does not show what the action needs, a wider first frame fixes the scene jump where reroll, text cut and seed did not.
