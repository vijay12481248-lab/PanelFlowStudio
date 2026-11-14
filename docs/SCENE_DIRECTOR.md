# Scene Director

Turns a vague brief ("hero fights the villain") into a written scene plan, draws it, checks the picture against the plan, corrects, and measures how often the owner agrees.
Design: `docs/superpowers/specs/2026-11-14-scene-director-design.md`. Plan: `docs/superpowers/plans/2026-11-14-scene-director.md`.
Code: `engine/original/scene_*.py`, playbooks in `engine/original/playbooks/`, baseline tools in `tools/scene_director/`.

Everything below is a measurement from this PC (RTX 5060 Ti 16 GB, ComfyUI + Ollama `qwen3.5:9b` running) unless it says otherwise.

## Baseline (raw: the brief goes straight to Qwen Image 2.1 Turbo)

- 24 vague briefs (8 fight, 8 emotion, 8 concept art) in `tools/scene_director/baseline_briefs.json`, 1344x768, fixed seed per brief.
- Drawing time: median 7.6 s, mean 9.5 s per picture, 0 failures. Slower pictures overlapped with other GPU work.
- Owner ratings of these 24 pictures: **not yet collected** (open `contact_sheet.html` in the baseline output folder, rate, download `ratings.json`, then `summary()` from `engine/original/scene_ratings.py`). This is the number the Scene Director must beat.

## Planner

- 6 real briefs (2 per type), local model: 2-4 s per plan once the model is loaded (the very first call took 20 s, model load).
- Real-data findings fixed: the model copied the word "slug" into actor ids (prompt now asks for one short word); it invented actors for a place-only brief (prompt now says to include only people the brief implies); "lost her best friend" counted as stating the state "lost" (a state now counts as stated only when the brief says the state chosen for that actor).
- Not measured: how often the first answer passes validation; plans for non-English briefs.

## Plan to prompt

- The plan is compiled by the existing `PromptCompiler` (an ephemeral one-scene story, genre `anime_adventure`); the compiler draws at most two characters, a plan with more is still checked for all of them. Emphasis is stated first ("Most important: ..."), as the refine loop does. Lessons only go to the negative prompt.
- Contacts are written with positions ("directed at the figure on the right"), never names: two men are both "the adult man" to the compiler.
- Real-data findings fixed: the model returned gender "neutral" for "a girl" and Qwen drew a boy (for ONE human actor with unset gender the brief's own words now decide; a gender the model chose is never overridden).
- First look (1 seed each, different seeds, so a smoke test, not a measurement): raw "the hero fights the villain" drew one bloodied man with a sword and no opponent; the director's plan drew two men, the one on the left punching toward the one on the right who raises a palm to block, low angle, light behind. The emotion plan drew a close grieving face in an empty classroom. Draw time 10.5-10.8 s through this path (baseline median 7.6 s).

## Check (plan-based, fast mode)

- Fast mode asks the vision model one batched question for the critical plan items, counts the figures with a separate question that does not say the expected number, and does a **blind read** of camera angle and each person's action (the model classifies, it is never asked to confirm). Where a second witness agrees (count, side from the reported box, blind read) the item is believed at confidence 0.9, otherwise 0.5; a disagreement fails the item. Unreachable reviewer or all-uncertain answers: `accept_low`, confidence 0, "unverified", never a pass.
- Measured on real pictures (fast mode, full resolution): 8.6-15 s per check; the full reviewer took 19-37 s here (70 s measured earlier with the whole pipeline).
- **The yes/no claim check is too agreeable.** The first fast check accepted a level-camera brawl (raw fight-03) as "low angle, left fighter striking" with score 1.0. The blind read called the camera level and the left fighter "readying", which matches what the picture shows. With the blind read: director fight picture accepted (score 1.0), raw fight-03 rejected (camera, left fighter's action), raw fight-01 rejected (counted 1 figure, plan has 2).
- **Resolution matters.** The same low-angle picture was read "looks_up" at 1344x768 and "level" at 1024, 768 and 512. Fast mode therefore does NOT shrink the picture by default (`max_side=None`); this replaces the shrink-to-768 speed idea in the plan.
- Real-data fixes in the same pass: the planner's validator rejected the model's "left to right" direction (the last horizontal word is the destination now); the provider's length-limit error escaped `propose()` (now retried, then `ValueError`); the plan said "grieving" and the blind read said "lost" for one sad face, so the emotion playbook has `state_groups` (families a 9B model cannot tell apart; fight has none, striking and blocking are never merged).
- Not measured: agreement with the owner's ratings (none yet). Checked against my own reading of 4 pictures only. Emotion checks are coarse by design (three families).

## Lessons (learning from failed checks)

- `engine/original/scene_lessons.py` on the existing `MistakeLedger`, one domain per model and scene type (`scene:qwen_image_21:fight`). A failure is keyed by WHAT failed (camera angle, a pose word, side, figure count, contact), never by story words. The failures of the FIRST attempt of each run are recorded (what the plain prompt gets wrong); a failure seen twice becomes a rule added to the next prompts. A single sighting only waits (the 9B judge is noisy). Use a ledger file under the app-data folder, not the repo's vault ledger.
- **Measured: the Qwen Turbo workflow ignores the negative prompt.** Same seed, empty vs strong vs default negative prompt: mean pixel difference 0.0 (BasicGuider, no CFG). Lessons are therefore written as positive statements and appended to the END of the positive prompt ("Remember: ..."). The long negative list the compiler builds has no effect on Qwen pictures. Where in the prompt a lesson works best (end vs start) is not measured.
