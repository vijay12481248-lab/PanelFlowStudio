# Evaluation examples (real reports, abridged)

## 1. Unexpected scene change - Dawn Gate `p005`
```
frames 90 (3.75 s)  zoom -3.3% (border +10.0%)  pan x -7.9% y +12.9%  inliers 0.92/0.95
flags: temporal  confirmed  t=0.58  hard cut: frame step 92.1 vs median 7.3
       artifacts suspected          luminance flicker 2.44 > 1.5
       camera    suspected x2       zoom: border +10.0% vs whole frame -3.3% disagree in sign; pan: big values from a fast scene -> not a clean camera move
```
Contact sheet: close-up of the girl and the cat, the cat swipes across the frame, then the picture jumps to a glider in the sky. Verdict: defect (unrequested transition). Lever: one action per clip, remove "flying/travel" wording, Static Shot. The VLM missed this cut in both runs.

## 2. Colour change inside a clip - cat video `p004_1` (labelled bad)
```
flags: consistency suspected t=1.46  colour histogram distance 0.42 from frame 0
       drift series 0.0, 0.15, 0.42, 0.32, 0.14, 0.09, 0.05, 0.03   flicker 0.21 (good clips <= 0.09)
```
Contact sheet: water curtain falls at 0.75 s, the girl's hair turns blue, then returns. Verdict: confirmed by eye, metric was a trigger. Good clips in this set: drift 0.03-0.10.

## 3. Zoom from our own prompt - Dawn Gate `p046` (close-up, silent)
```
base   (push-in) : zoom +163.7%  border +159.5%  inliers 0.99  -> suspected (over the 50% trust cap)
static (Static)  : zoom   +0.4%  border   +0.2%                -> no flag
```
Contact sheet base: the face fills the frame by 3.0 s and the glow is in his eyes; static: camera fixed, the goggle lenses glow as the prompt says.

# The 10 validation scenarios

| # | Scenario | Pass condition | Status |
|---|---|---|---|
| 1 | Animate an existing character without changing its look | no confirmed consistency flag; frames 0 and last match the card by eye | done for `p012` (static): pass |
| 2 | Stickman walking, static camera | `camera` no flag; subject keeps size; by eye | not run |
| 3 | Character interacts with an object | object keeps shape/colour on the sheet; end state as named | not run |
| 4 | First + last frame | last frame reached by the end; no cut flag | blocked: no FL2VA workflow |
| 5 | Multiple reference images | references visible in the result | blocked: no Ref2VA weights |
| 6 | Detect an unwanted zoom | `camera` confirmed with border agreeing; synthetic test + `p046` base | passes (`tests/unit/test_clip_eval.py`, Phase 1) |
| 7 | Detect an identity/look change | drift flag fires and the contact sheet confirms | partial: `p004_1`, `p019_1`, `p070`; identity itself unmeasured |
| 8 | Flicker / vanishing object | flicker flag; sheet shows the object missing | flicker measured (`p060`); object loss not measured |
| 9 | Correct a failed generation | one lever; defect gone; no regression on other axes | camera case done (Phase 1); full loop not built |
| 10 | Continuity between two clips | outgoing state of n matches incoming of n+1; no visible jump | not run; boundary check not built |
