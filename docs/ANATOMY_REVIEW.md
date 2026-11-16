# Anatomy and pose review

Checks a generated picture for wrong bodies, redraws when it finds a confirmed mistake, and remembers the mistake so later prompts avoid it.
Design: `docs/superpowers/specs/2026-11-16-anatomy-review-design.md`. Plan: `docs/superpowers/plans/2026-11-16-anatomy-review.md`.
Code: `engine/original/anatomy/` (`tiles`, `questions`, `rules`, `review`, `lessons`, `store`, `loop`, `draw`). Tools: `tools/anatomy/build_labels.py`, `calibrate.py`.

Why it exists: on 2026-11-16 the agent called 64 test pictures correct from 300 px sheets; the owner found a woman with four hands (klein, "sitting cross-legged, hands
on knees", seed 101). Counting arms needs a zoomed look and a count the judge cannot skip.

## How it works

1. **Tiles** (`tiles.py`): the whole picture plus three overlapping bands along the long side, plus left/right halves when two or more people are in it, each upscaled to
   a 1280 px long side. No detector.
2. **Questions** (`questions.py`), to each judge (`qwen3.5:9b` through Ollama and Qwen3-VL 8B through ComfyUI), blind (never told what to expect):
   *list every hand, one per line* (the code counts the lines), a short flags question (people, writing, doubled held object, merged bodies), and one yes/no question per
   pose word found in the prompt (cross-legged, hands on knees, kick, raised leg, two hands gripping).
3. **Rules** (`rules.py`): more than two hands per person in any view = `extra_hands`; writing nobody asked for = `stray_text`; a held object drawn twice =
   `duplicate_object`; two bodies merged = `merged_bodies`; an asked pose answered "no" = `pose_missing`. Counts are never added across tiles (the bands overlap).
4. **Confidence** (`review.py`): a defect is **confirmed** when both judges report it, or (for `extra_hands`) when ONE judge reports it from two different views.
   Reported once otherwise = **suspected** (kept, flagged, never a reason to redraw). **unverified** = no judge gave a usable whole-picture answer. `clean` means a judge
   looked and nothing was confirmed, never "nobody looked".
5. **Redraw** (`loop.py`, `draw.py`): `generate_checked(...)` draws, reviews, and redraws with seed + 7919 while a defect is confirmed (default 4 attempts, 240 s); the cleanest
   picture is delivered with its report (`clean`, `best_effort` or `unverified`). Opt-in per caller.
6. **Learn** (`lessons.py`, `store.py`): confirmed defects are recorded per image model and defect kind (never story words); after two sightings the matching positive rule
   is appended to later prompts ("Exactly two arms and two hands per person ... nothing but the legs in the lap."). Two rules start active, labelled agent-labelled
   2026-11-16 audit: klein `extra_hands` and `duplicate_object`. Every attempt is a line in `<app-data>/config/anatomy_checks.jsonl`; `GET /api/original/anatomy/stats` and
   the MCP tool `panelflow_anatomy_stats` give the defect rate per model and kind with lessons off and on. `POST /api/original/anatomy/flag` (MCP `panelflow_anatomy_flag`)
   is how the owner says "the reviewer missed this"; those pictures count against the judges.

Use it from Reels with `REEL_ANATOMY_CHECK=1 python tools/reels/make_reel.py art <reel>`; the report sits beside each panel as `s<N>.anatomy.json`. Without the variable nothing changes.
From code: `engine.original.anatomy.draw.draw_picture(art_engine, ..., check=True, judges=default_judges(provider), ledger=..., record_path=checks_path())`.

## What was measured (2026-11-16, RTX 5060 Ti)

- **Counting by number does not work.** Asked "ARMS: n" for the four-hand klein picture both judges said 2. Asked to list each hand, qwen3.5:9b listed the right number on all 4 probe pictures (4, 4, 2, 2, on
  both the whole picture and the zoomed lower tile); Qwen3-VL 8B listed 2 hands on every view of the first four-hand picture and 2-3 on the second (it undercounts). That is why the question is a list and why a count defect can be confirmed by one
  judge from two views.
- A joint "hands and feet" list made qwen3.5:9b list 2 hands on the whole four-hand picture, so v1 lists hands only. **Extra feet and legs are not checked.**
- **Calibration** (`tools/anatomy/calibrate.py`, 29 pictures: all 14 with a known defect and a fixed sample of 15 clean ones; both judges; about 45-60 s per picture):

  | defect kind | known | confirmed | only suspected |
  |---|---|---|---|
  | `extra_hands` (klein cross-legged seeds 101, 103) | 2 | 2 | 0 |
  | `duplicate_object` (klein ghost second blade) | 2 | 2 | 0 |
  | `stray_text` (the owner's hug picture) | 1 | 1 | 0 |
  | `pose_missing` (hands clasped instead of on the knees; one hand loose on the sword) | 8 | 1 | 5 |
  | `merged_bodies` (Z-Image hugs) | 2 | 0 | 1 |

  Gate (the spec's kinds, `extra_hands` + `duplicate_object`): recall 4/4 = 1.0, **0 confirmed false alarms in 15 clean pictures**: **PASS**. 4 of the 15 clean pictures carried
  a *suspected* flag (stray text or a doubled object seen by one judge only); none was confirmed, so none would be redrawn.
- **Not trustworthy yet:** pose checks and merged bodies. Both judges answer "yes, hands on the knees" for pictures the agent labelled as clasped in the lap, so a pose
  defect is almost never confirmed (and those labels are partly a matter of taste). They are reported, never redrawn on unless both judges agree.

## End-to-end check (real klein drawing, real judges, redraw, lessons; four seeds of "sitting cross-legged, both hands resting on her knees")

- First run: both four-hand seeds (101, 103) were caught as confirmed `extra_hands` and redrawn clean on the second attempt; seed 102 needed three attempts (a pose
  miss, then a new picture with extra hands, then clean). About 75 s for a picture that is clean at once and 150 s with one redraw.
- **It found a bug the unit tests could not:** the seeded rule said "exactly one sword", and klein drew a sword into three of the four calm sitting pictures. The rule now
  names no object and is only added when the prompt names a held object (`ONLY_WHEN` in `lessons.py`).
- Second run with the fixed rule: seeds 101, 102 and 104 were clean at the first draw and 103 needed one redraw. Counted by eye at 380 px, every delivered picture has two
  arms and two hands, and no stray objects. Caution: with the hand rule in the prompt, seed 101 itself came out with two hands where the plain prompt gave four, so the rule
  may help, but 4 seeds are far too few to say so; the stats keep `rate_rules_off` and `rate_rules_on` so it can be measured properly.

## Known weaknesses (not fixed)

- Tiny test set: 4 gated defects and 15 clean pictures, all labelled by the agent (`tests/data/anatomy_labels.json`, `source: agent-2026-11-16`), one owner-pointed picture.
  A recall of 1.0 on 4 pictures is not a guarantee. The owner's flags will grow the set.
- Slow: about 45-60 s of judging per picture on top of an 8 s draw; a 13-picture reel with redraws can add 15-20 minutes. Never queue a long ComfyUI job (HiDream) at the
  same time: the Qwen3-VL judge waits behind it.
- Finger counts (three fingers up), shoes that do not match and tangled arms in contact poses are not checked. Only hands are counted.
- The lessons are generic rule sentences; whether a rule changes klein's picture is measured per model in the stats (`rate_rules_off` / `rate_rules_on`), not assumed.
