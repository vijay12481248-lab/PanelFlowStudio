# Regeneration strategy

Never regenerate blindly. Same frame + prompt + seed + workflow = identical clip `[verified]`, so every retry must change exactly one input, chosen from the defect.

## Loop (manual today; automation is Phase 3)
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
`shot id, attempt n, mode, prompt, first-frame hash, seed, workflow sha, length, evaluator report (flags with t), lever applied, result (kept/discarded), reason`. `film/clips.json` already stores sig, seed, seconds, prompt, workflow, prompt_id, elapsed, stats per shot; the `attempts[]` list is not built yet.

## Cost
Short shots took 47-133 s each, so 3 attempts are about 2-7 minutes per shot. Budget a story by shots x attempts, not by "regenerate everything".
