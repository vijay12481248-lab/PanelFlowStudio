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

## Phase 5: the open items (2026-11-07)
**Camera default** (commit 24efde2): Static Shot is the default; a move is explicit per shot (`Panel.camera`). The loop now tracks the exact camera sentence a clip was made with.

**Character presence** (`engine/original/clip_identity.py`, `tools/h3_identity_calibration.py`; 9 clips judged by eye): a narrow yes/no question per named character and frame, asked twice in different words; a frame counts only where both
answers agree; a flag is only ever `suspected`.
| Clip | Truth | Result |
|---|---|---|
| `p005` r4_a2, r3_a3 | Pip leaves after 0.5 s / ~1.6 s | **flagged** (`PP....`) both |
| `p012`, `p046`, `p070` x2, cat `p001_1`, `p010_1` | everyone stays | no flag (6 of 6; Pip is not in `p070`'s first frame so cannot vanish) |
| `p070` r3_a0 (outfits wash out), cat `p004_1` (hair turns blue) | colour drift | colour answer said "matches": **missed 2 of 2**, so it is information only and never flags |
Presence works on this sample (2 of 2, 0 false alarms). The colour check does not; the histogram drift trigger remains the colour/lighting detector. ~15-60 s per clip.

**Boundary check** (`engine/original/continuity.py`). Measured: 157 adjacent Dawn Gate pairs, same-scene histogram distance median 0.46 vs 0.56 across scenes (148 of 157 pairs are the same scene), edge audio level step median 8 dB (90th percentile 21 dB):
these cannot separate a continuity break from a normal cut, so a cut is never flagged. A boundary the caller declares continuous is checked: a real continuation pair (clip B generated from clip A's last frame, scenario 10) measured
histogram 0.139 / gray 3.4; the same clip followed by an unrelated one measured 0.997 / 123 (thresholds 0.25 / 25, provisional, one continuation pair).

**Modes** (`engine/original/h3_modes.py`; workflows `fastvideo_h3_film_{fl2va,l2va,t2va}`; official-skeleton prompt builders). Clips made and looked at, 3.75 s each, 68-92 s per clip:
| Scenario | Result |
|---|---|
| 2 stickman walking, I2VA, Static Shot | static camera, same figure and line style throughout; it walks **in place** (the prompt also said "same distance"). The evaluator's "zoom -21%" is `suspected` only: a thin figure on white gives the tracker almost nothing to hold |
| 3 girl lifts a cup and drinks (I2VA) | the cup keeps its shape and colour; camera -4.2% (confirmed, just above the 3% limit even with Static Shot) |
| 4 first + last frame (FL2VA) / last frame only (L2VA) | both drink and land on the supplied last frame (gray difference 3.1 / 3.4 of 255); no cut; camera -4.2% / -2.2% |
| T2VA stickman, text only | walks left to right across the frame, static camera, consistent figure; the drift flag (0.52) is a false alarm on a white page |
| 10 continuity: clip B from clip A's last frame, "sets the cup down" | B starts exactly where A ended, the cup ends on the table; boundary measured as above |

**Engine hooks:** `GET /api/original/story/{slug}/film/clip/{shot}/eval`, `POST .../improve` (background job), `GET .../history`; MCP `panelflow_original_clip_eval|improve|history`; ChronoFlow's reviewer now returns real measurements
(no score or grade) and its UI no longer shows the hard-coded "94% (A) APPROVED FOR MASTER CUT". The running engine must be restarted to load them.

## Storyboard approach and the long-take Director (2026-11-07)
`engine/original/director.py` (one brief -> a plan), `storyboard.py` (pictures first, then video), `tools/produce_video.py --storyboard`, `tools/h3_length_probe.py`.

**One clip can be 15 s on this GPU:** 362 frames, 6.3 min, peak VRAM 15.7 of 16.3 GB, followed a five-beat script in order (probe, `output/H3_LongTake/`).

**Approach 1 - one first picture + a prompt (I2VA long takes, 4 x 15 s):** exactly one woman and one cat in every sampled frame (closed-cast wording), but H3 ignored the plan: a guide told to walk to the right walked at the
camera, shots jumped, a cat grew a human hand. The brief's "walks" never reached the plan (the Director's word match missed "walks"/"walked").

**Approach 2 - storyboard (start and end picture per shot, FL2VA between them, 8 x 7.5 s):** every clip lands on its two pictures (gray difference 4-9 of 255). What it took, in the order the evidence arrived:
| Finding (measured) | Fix |
|---|---|
| a second cat in 3 of 8 pictures: the cat was described twice (cast layout + the action sentence) | each character is described once (`split_actions`); characters may not be carried by each other |
| H3 acts out every event in the prompt ("a massive blue lightning bolt arcs down" made a lightning scene) | the clip prompt says only "change gradually from picture 1 to picture 2" + where the characters end |
| start and end pictures that differ in weather/effects: H3 fills the gap with smoke and rings (6 of 8 shots) | the end picture keeps the start's scenery; only the characters move |
| **naming unwanted things makes H3 draw them**: "no smoke, dust clouds, rings, bolts or glow" filled 8 of 8 shots with dust clouds and rings (an earlier clause naming "smoke and light effects" did the same) | positive wording only; clean on all 8 after the change |
| a walker chained from an end picture already on the side it walks to cannot be drawn walking | such a shot is drawn fresh; a VLM checks that start and end are on different thirds of the frame |
| narration used 9-13 of 18 words (half the video silent) | at least 65% of the slot; hook first, takeaway last |
| "rock to the right" counted as a walk | a walk needs a locomotion verb followed by a direction |

**Final storyboard video (`storm_board2`, 64 s, -16.8 LUFS):** cat counted once in every sampled frame, both characters present in every sampled frame, no dust or explosions, walking visible in shots 1-2 (by eye).
Remaining: camera still moves 3-7% in 6 of 8 shots (`camera` confirmed; the walker's scale changes), a faint ring effect around the cat in shot 7, all skies are sunny (the 9B's plan does not build a storm), the cat design is odd
(black body, orange tail), the 9B's science is plain; the "girl" counter reads 0 in a few frames of a walker in profile (counter error). Tests: `tests/unit/test_storyboard.py`, `test_director.py`.

## Camera drift and the sky arc (storyboard runs, 2026-11-07)

- **Drift is measured on the background, not on features** (`clip_eval.camera_motion_area`: area-weighted Farneback flow on a grid, robust similarity fit). A subject that grows or walks no longer reads as a camera move
  (two of eight clips were false alarms before). On the first storm video the real drift was pan 5-10 %, tilt 11 %, and one clip 31-34 % zoom.
- **`engine/original/stabilize.py`** removes a drift of 3-12 % (a straight ramp to the net drift, then a crop zoom that hides the borders) and **keeps the original unless the evaluator measures the result as
  at least 40 % steadier** (a first version with a coarser flow made a walking shot worse; that check is what caught it). Above 12 % it refuses: the cause is a different scale between the start and end picture,
  and the fix is to redraw the shot's pictures. `produce_video.py --stage stabilize` runs it (the raw clip is kept as `<id>_raw.mp4`).
  Second storm video: t2 4.5 -> 0.9 %, t6 3.6 -> 1.1 % fixed; t5 (14.7 %) and t8 (24.2 %) refused. **`stage_fix_drift`** (default 2 rounds, `--fix-drift N`) then redraws such a shot's pictures with new seeds
  (unchained), makes the clip again and stabilises again: t5 14.7 -> 0.3 % and t8 24.2 -> 0.3 % after ONE round. It is a retry loop, not a prevention: a cheap pre-check on the pictures (SIFT background
  agreement) did not separate the bad pairs from the good ones, so the GPU time of the bad clip (about 3 min each) is still spent once. A redrawn shot no longer starts from the previous shot's end picture.
- **Sky arc:** in storyboard mode the Writer plans one `atmosphere` (sky and light, 5-14 words) per take, neighbours must differ (`check_writer`); it goes into the take's prompt and into BOTH keyframes
  (`ShotSpec.lighting`, `Panel.atmosphere`). Measured on the second storm video: sunny -> grey -> purple storm with lightning -> clearing with sun rays -> rainbow, where the first video was sunny throughout.
  Known weakness: the image model over-draws the middle of the arc (take 3 "grey clouds gathering" came out as a full purple storm), so the build-up is a jump from take 2 to take 3 rather than gradual.

## Voice, picture and sound acting together (Phase 1, 2026-11-07)

Owner's complaint on the second storm video: audio and animation "are not acting together". Measured cause (not the image model): the narration explained invisible
science (ice crystals colliding, charge separating) while all eight pictures showed the guide and her cat standing in a field; two takes said the same sentence; speech
filled 59 % of 64 s (about 3 s of silence after every line); lightning was shown in silence (clips are animated with a silent anchor and there was no sound bed).

- **Picture first** (`director.picture_first`, storyboard mode): every take names a `visual` (the visible thing that carries its fact; it becomes `Panel.key_visuals`, goes into
  both picture prompts and is checked on both pictures by two VLM witnesses, `storyboard.visual_problems`); the narration must mention it; a take whose narration shares
  more than 70 % of its content words with the earlier narration is rejected. A chained shot whose copied start lacks its visual draws its own start.
- **The clip lasts as long as its line** (storyboard `make_clips`): the clip length is the padded narration on the H3 frame grid, not a fixed 7.5 s. Pace budget 2.8 words/s
  (Kokoro measured 2.86). The 9B often writes 10-12 words where 16 were asked, so after 4 tries a short line is accepted (it costs screen time, not silence).
- **Weather sound** (`ambience.py`, used by `film_master.normalize` for clips without their own sound): a faint outdoor air bed, rain / wind / thunder layers from the shot's
  own words (weather that has ended - "as rain stops" - is ignored), thunder 0.4-1.2 s after each lightning flash found in the picture (a brightness jump), or one distant roll
  when the shot names a storm but no flash is seen. Local noise synthesis, no model.
- **Planning robustness** (all seen on real runs): the 9B writes character ids as "maya: center facing right" or "maya stands center-left..." (`character_id` reads the
  leading id); it sometimes loops to the token limit (5 rounds of retries now); the visual comes as a full sentence (up to 30 words accepted).

Third storm video (`storm_board4`): each shot shows what its line talks about (a rising warm-air bubble, a cumulonimbus tower, ice crystals, a lightning bolt, rain from
leaves, wind bending trees, a rainbow); QA flags on 0 of 8 clips (first time); speech fills ~81 % of the video; sound gaps measured -44 dB (sunny air bed), rain -28 dB,
wind -29 dB under speech at about -16 dB, thunder in the lightning shot. The drift loop redrew 3 shots (t2 25.9 %, t7 13.2 %, t8 not stabilisable) and all landed under 1.4 %.
**Length fix:** `director.lengthen` rewrites a line shorter than 80 % of its budget in ONE focused ask (same meaning, one more detail about the visual, still names it, no repeat); the original is kept when no rewrite passes, and the plan warns when `planned_seconds` is under 85 % of the asked length. On the same storm plan: 6 of 7 short lines lengthened (8-12 -> 15-18 words; one kept at 11 after 4 tries), video 39.2 s -> 50.5 s, speech 85 % of it, QA flags still 0 of 8. Full 60 s would need ~18 words in every take; that is the ceiling at 7.5 s per take.
**Not good yet:** the sky arc was weak in this plan (a rainbow in the ice-crystal shot, rain under a blue sky);
the lightning is a static bolt in both pictures, so no flash is seen and the thunder is the fallback roll; the "shockwave" shot was drawn as literal rings.
