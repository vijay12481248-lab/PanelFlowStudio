# Anatomy and pose review (check, redraw, learn)

Status: written for the owner's approval, 2026-11-16. Nothing is built yet.

## Why

On 2026-11-16 the agent judged 64 test pictures from small contact sheets and called them correct. The owner opened two of them and found a woman with four hands
(klein, "sitting cross-legged, hands on knees", seed 101) and a hug with stray text, mismatched shoes and tangled arms. The system itself has the same blind spot:
the Scene Director's two vision judges (`engine/original/judges.py`, cross-check in `crosscheck.py`) read the whole picture for camera angle, number of people and each
person's action, were right 81-91 % of the time on those items, never zoom, and never count arms, hands or legs. Reels and the other art callers do not use any review.

The owner wants the system to look the way the agent finally looked (zoom in, count, compare with what was asked), redraw when it finds a mistake, and remember the
mistake so later prompts avoid it ("exactly two arms, nothing in the lap"). Decision made by the owner: **redraw and also learn**.

## Goals

1. For a generated picture, produce a written defect list: wrong number of arms, hands, legs or feet for the people shown; a pose that was asked for but not shown
   (cross-legged, hands on knees, raised leg, two-handed grip); the same object twice (ghost second blade); stray text or letters nobody asked for; mismatched pairs
   (two different shoes on one person); merged or tangled bodies in contact poses (hugs).
2. Redraw with a new seed, up to a budget, and keep the cleanest picture. Say plainly when the best picture still has a problem.
3. Learn: record each confirmed failure keyed by what failed (defect kind, pose word, image model), never by story words, and put the matching positive rule at the end
   of later prompts. Measure whether the rules reduce the defect rate before claiming they do.
4. Keep a labelled test set (the agent's 64 audited pictures plus every picture the owner flags) and report the reviewer's honest accuracy against it.

## Non-goals

- Fixing a defect inside the picture (masked repair). Redraw only.
- Replacing the owner's judgement, a new desktop screen, video clips, camera-angle review (the Scene Director already covers that).

## Anti-goals (a failure even if it technically works)

- A "clean" verdict that is wrong. The original sin of this work. The reviewer must say `unverified` when its two judges cannot agree, and an unverified picture is
  shown as unverified, never as passed.
- Endless redraw loops, or a reel stage that becomes unusably slow.
- Lessons written from a single noisy sighting, or from the story's own words.

## Constraints

- Local-first: Ollama `qwen3.5:9b` and ComfyUI Qwen3-VL 8B (`TextGenerate`, needs `--disable-dynamic-vram`) are the judges. No cloud fallback.
- The 9B models are noisy: measured 0.81 and 0.91 accuracy on easier questions. Counting may be worse. That is why the build is gated by a measurement.
- GPU: judges and the image model swap in and out of 16 GB; the existing judging cost is about 9 s per picture for three questions, so tiles multiply it.
- The negative prompt is ignored by klein and Qwen (cfg 1), so every lesson is a positive sentence added to the end of the prompt, like `scene_lessons.py` does.
- Downloads need the owner's approval with exact file, size and source.

## Approaches considered

- **A. Zoomed tiles through the two existing vision judges.** No download, reuses `judges.py` / `crosscheck.py`. Accuracy at counting unknown.
- **B. A pose-estimation model** (keypoints per person, counts from geometry). Objective, but needs a download and may be weak on cartoon and anime figures.
- **C. A first, B only if A fails a measured gate.** Chosen (the agent's call; the owner handed over the how). Reason: nothing to download or install now, a labelled set
  already exists to measure against, and if A fails there is a concrete reason to ask for B.

## Design (approach C)

New module `engine/original/anatomy_review.py` (plus tests), built on the existing judges, cross-check and `MistakeLedger`.

1. **Tiles.** The picture whole (at least 768 px on the long side) plus overlapping zoomed tiles (upper body, middle, lower body, and left/right halves for two or more
   people), each upscaled so a hand is readable. Deterministic; no detector needed.
2. **Questions.** Narrow, blind (never told what to expect), plain-text answers parsed strictly like `judges.py`:
   per tile "how many arms, hands, legs, feet are visible and what does each hand touch?", "is there any text or letters?", "is any object shown twice?";
   per picture "how many people?", plus yes/no pose checks derived from the prompt's own pose words (cross-legged, hands on knees, one leg raised, two hands on the grip).
3. **Rules on top of the answers (deterministic).** Hands greater than two per person, arms greater than two per person, legs greater than two per person, text when none
   was asked, a duplicated object, a pose word asked but not seen. Each rule produces a defect with its evidence sentence and the tile it came from.
4. **Two judges, honest confidence.** A defect is `confirmed` when both judges report it, `suspected` when only one does, and the picture is `unverified` when the judges
   cannot give usable answers. Confirmed -> redraw. Suspected -> keep, flag. Unverified -> keep, flag as unverified.
5. **Redraw loop.** `generate_checked(...)` around `ArtEngine.generate`: up to N seeds (default 4) and a time budget; keeps the first clean picture, else the one with the
   fewest confirmed defects; writes every attempt's report beside the picture. Opt-in per caller; Reels `stage_art` first, then Original Stories.
6. **Learning.** Confirmed defects go to the ledger, domain `anatomy:<image model>`, keyed by `<defect kind>:<pose word>`. A rule becomes active after two sightings
   (the existing `recurrence_count` threshold), except the rules already established by the owner-checked audit (klein cross-legged extra arms, klein ghost second blade),
   which start active and are marked as agent-labelled. Rule text is a positive sentence ("Exactly two arms. Both hands rest on the knees; nothing in the lap.")
   appended to the prompt. For each model and defect kind the report keeps the defect rate with rules off and on; no claim of improvement without that comparison.
7. **Knowledge base.** Per model and pose: pictures checked, defect rate by kind, redraws needed, rule on/off rate, owner flags. Queryable like the Scene Director's
   knowledge endpoints (`/api/original/anatomy/stats`, MCP tool). The owner can flag "this picture had a mistake the system missed"; the picture and the note join the
   labelled set and count as a miss for the judges.
8. **Gate before it is trusted.** Run the reviewer on the labelled set (64 audited pictures and the owner's two). Required: it finds the known extra-arm and ghost-object
   defects (recall at least 0.8 on confirmed) with at most 1 false alarm per 10 clean pictures. Report the real numbers. If it fails, it ships as flag-only and the next
   step is approach B, which needs the owner's approval for the model download.

## Left to the builder

File layout, exact tile geometry, prompt wording of the questions (iterate on the labelled set), the sidecar report format, the stats query shape, and the tests.
Calls made by the agent, not agreed by the owner: tiles instead of a detector, default budget of 4 seeds, Reels first, rules for the audited klein failures start active.
Two more builder-level calls: (a) the labelled pictures live under `output/anatomy_labels/` (about 45 MB, not committed) and only the small label file (arm, hand,
leg and defect counts per picture) is committed; the first labels are the agent's counts from 2026-11-16 and are marked agent-labelled until the owner confirms them;
(b) pose words are taken from the prompt with a short keyword list (cross-legged, hands on knees, kick, raised, two hands) and, for Scene Director runs, from the plan's
action states; free-text poses outside the list are simply not checked and the report says so.
