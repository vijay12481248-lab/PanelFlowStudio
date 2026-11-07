# Camera and motion

## Vocabulary `[official]`
Static Shot; Push In / Pull Out; Zoom In / Zoom Out; Pan Left/Right; Truck Left/Right; Tilt Up/Down; Pedestal Up/Down; Arc Shot; Tracking Shot; Shake Slightly/Strongly; POV; Roll Clockwise/Counterclockwise. Add amplitude (`with small amplitude`) and speed (`at slow speed`); write them as natural prose inside the shot, not as stacked labels: "The camera pushes in with small amplitude at slow speed toward the folded letter."
A push-in or pull-out changes distance to the subject (dolly). Zoom changes focal length. Say which you want; they are not the same picture.

## Fixed camera `[verified, Phase 1]`
Our own prompt used to ask for a push-in in every shot. NOW (2026-11-07) the default is the Static Shot sentence (`animate.STATIC_CAMERA`) and a camera move is an explicit per-shot choice: `Panel.camera = "a slow, steady push-in"`. Clips made before the change keep their old signature; running `film.make_clips` regenerates any clip whose prompt differs, i.e. all of them for Dawn Gate. Measured on 140 Dawn Gate clips: median zoom +9%, 119/140 clips beyond 3%. On 6 shots with the single camera sentence swapped:
| Camera sentence | mean abs zoom | flagged |
|---|---|---|
| "a very slight, slow push-in" / "a slow, steady push-in" | 38% (range +6% to +164%) | 6/6 |
| "nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt" | 0.8% | 0/6 |
Even "very slight" gave +6-7% on extreme close-ups. Use the static sentence unless a move is wanted.

Rules for a fixed camera:
1. Say **Static Shot** and list what does not happen: no zoom, no pan, no tilt.
2. Say the subject keeps its size and position unless it is meant to move.
3. Separate subject from camera: "Mira turns her head" is subject motion; "the camera follows" is a camera move. Never write both when you want one.
4. Verify: `clip_eval.evaluate(path, "static")` - `camera` flags with zoom/pan %, border-ring numbers and inlier share.

## Wanted camera moves
Say the move once, with amplitude and speed, and expect the number: push-in "slow, steady" ~ +6 to +13% over 3-4 s `[verified]`. Pan, tilt, truck, arc, handheld: not measured here `[hypothesis]`; run `evaluate(path, "any")`, read `camera` and compare with what you asked.
Fast subject motion toward the camera also reads as zoom in the numbers (`p039`: subject lunges, +354%); the border-ring estimate helps but does not prove it is the camera.

## Motion amplitude
Describe the action in order and with size: "slowly", "small", "once". H3 over-extends actions; fewer verbs, one result state. Calm beats: first frame = last frame loops keep motion minimal `[verified, cat video]`. Do not trust mean frame step as quality: it falls with a static camera (5.68 -> 3.09) without the action disappearing `[verified, 2 shots viewed]`.
