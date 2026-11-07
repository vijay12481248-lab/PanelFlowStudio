# Regeneration strategy

Never regenerate blindly. Same frame + prompt + seed + workflow = identical clip `[verified]`, so every retry must change exactly one input, chosen from the defect.

## Loop (automated for one shot: `python -m engine.original.clip_loop <story_dir> <shot> [--attempts 3] [--camera any] [--suspected] [--apply]`)
1. `evaluate` + contact sheet; list confirmed defects, rank by severity (identity/scene break > camera > artifact > audio).
2. Take the top one. Name its likely cause class: **prompt**, **first frame**, **action size/length**, **seed**, **audio anchor**, **post**.
3. Apply ONE lever from the table. Regenerate only that shot (`film.make_clips(..., ids=[id], seeds={id: n})`; delete the clip or change its inputs so the signature changes).
4. Re-evaluate. Compare with the previous best on the same axes (not an overall number). Keep the better clip; record both.
5. Stop when no confirmed defect remains, after 3 attempts, or when two attempts do not move the metric. Report what remains; use the clip as a still or cut it if needed.

## Defect -> cause -> lever
| Defect (evidence) | Likely cause | Lever |
|---|---|---|
| Zoom/pan in a static shot (camera flag) `[verified]` | our push-in sentence | camera sentence -> Static Shot wording |
| Outfit/colour/light change (drift flag, contact sheet) | strong implied action; long clip; lighting event | shorten/simplify action; fewer verbs; redraw first frame; then new seed |
| Invented speech/music in a silent shot (ASR finds speech) | model | `quiet` (silent anchor); or new seed |
| Mouth on a faceless speaker | voice anchored to a faceless subject | `FACELESS` path |
| Object invented/changed (contact sheet) | prompt implies a result (pour, spill) | remove the result-implying verb; name the end state |
| Unrequested scene change (cut flag) | prompt/first frame suggests another place; large action | one action; remove travel/transition words; static camera |
| Still picture (motion flag) | calm first frame, no action | add the action, or accept a calm beat |
| Subject too small/not the described subject | first frame | redraw frame (`film.make_frames(..., rerolls={id: n})`), not the video prompt |
| Face/hand distortion | model | new seed; `minimax_h3_facerefine_i2v` `[hypothesis]` |
| Longer clip needed | audio length | add the second action as a second shot; do not stretch (124 frames added zoom, drift and invention in 6/6 shots) |

## Do not
Change prompt and seed together; stretch clip length to "give H3 more room" `[verified: worse]`; regenerate a clip whose only defect is a suspected flag you have not looked at; raise thresholds to make a flag go away; touch the real `film/clips` while another job is writing there (use an isolated workspace like `tools/h3_phase1_experiment.py`).

## History (record per attempt)
`shot id, attempt n, mode, prompt, first-frame hash, seed, workflow sha, length, evaluator report (flags with t), lever applied, result (kept/discarded), reason`. `film/clips.json` already stores sig, seed, seconds, prompt, workflow, prompt_id, elapsed, stats per shot; the loop writes the per-attempt record to `<ws>/film/history/<shot>.json` and keeps attempt clips in `<ws>/film/attempts/<shot>/` (real `film/clips` is replaced only with `--apply`).

The loop has four levers and judges by the worst defect in severity order (temporal > consistency > camera > artifacts > motion > audio); on the same axis a new clip must be at least 25% smaller in the measured number, a tie falls through to the next defect.
- `static_camera` - Static Shot sentence. `[verified]` fixes push-in zoom (`p046`).
- `simplify_action` - `clip_loop.simplify_motion`: for a colour/lighting defect drop the clauses that name a light event; otherwise keep only the first clause. `[verified, 1 shot]` `p070` drift 0.60 -> 0.13 with stable colours on the contact sheet. It REMOVES part of the story beat (the growing light): check before `--apply`.
- `redraw_frame` - new first frame via `film.make_frames(rerolls)`; needs the art runner (CLI default; `--no-redraw` to skip). `[verified, 1 shot]` did not fix `p005`'s transition.
- `seed` - deterministic new seed. `[verified]` did not change `p070`'s drift; on `p005` it introduced 3 hard cuts. Keep it last.
Order per defect (hypothesis, from 3 shots): temporal: static_camera, simplify_action, redraw_frame, seed; consistency: simplify_action, redraw_frame, seed; camera: static_camera, seed.
Not implemented: `quiet` (needs speech detection); a fix for a shot whose first frame does not show what the action needs (`p005`: close-up of the girl, action = glider around a spire: all four levers failed, 0/4 attempts). Defects with no lever are reported, not hidden.

## Cost
Short shots took 47-133 s each, so 3 attempts are about 2-7 minutes per shot. Budget a story by shots x attempts, not by "regenerate everything".
