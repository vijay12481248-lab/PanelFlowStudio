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

## How to use it

Flow: `propose` (brief -> plan + summary + at most 3 questions) -> the owner says go or corrects items (`correct`, dotted paths such as `camera.angle`, `actors.hero.side`) -> `generate` (durable GPU job `SCENE_GENERATION`, needs a `project_id`; up to 3 attempts / 60 s; delivers the best picture with what it still misses in `unmet`; `unverified` means the checker could not judge it) -> `rate` (good / not good + reason).

| What | Where |
|---|---|
| HTTP | `POST /api/original/scene/{propose,correct,generate,rate}`, `GET /api/original/scene/ratings/summary` (`engine/api/routers/scene.py`) |
| MCP | `panelflow_scene_propose`, `panelflow_scene_correct`, `panelflow_scene_generate`, `panelflow_scene_rate` |
| Outputs | `output/Original_Scenes/<project_id>/panels/<key>.png`, `<key>.json` (plan, review, iterations), every candidate in `panels/_candidates/<key>/` |
| Lessons / ratings | `<app-data>/config/scene_lessons.json`, `<app-data>/config/scene_ratings.json` |

Baseline (the measure of "does it match what I imagined"): `.venv\Scripts\python.exe tools/scene_director/baseline.py --mode raw|director --out <dir>`, open `contact_sheet.html`, rate, download `ratings.json`. The sheet does not show the plan, so the rating is blind to what the system intended.

## Known weaknesses (not fixed)

- The compiler draws at most two characters; plans with more are checked for all of them but drawn with two.
- Emotion checks are coarse (three families of feelings); the 9B model cannot tell grief from guilt.
- No masked repair inside the scene loop (a located defect is redrawn whole); no desktop UI screen yet.
- Lessons are generic rule sentences per failure kind; whether a lesson at the end of the prompt actually changes Qwen's picture is not measured.

## Director run on the same 24 briefs (before the owner rates anything)

- `baseline.py --mode director` (auto mode, default budget 3 attempts / 60 s, fixed seeds). 22 of 24 delivered a picture; 2 concept-art briefs failed in the planner (the model wrote contacts between objects such as "neon_signs -> wet_pavement"; contacts to non-actors are now dropped, tested, not re-run).
- **Time: median 64.8 s, mean 64.1 s, max 111 s per picture, against 7.6 s raw.** Fights 73 s, emotion 66 s, concept art 50 s. Most briefs used all 3 attempts. This is far from "very fast".
- Checker outcome: 5 accept, 2 accept_low, 15 needs_review (picture delivered with what it misses listed), 0 unverified. Items still unmet after the attempts: camera angle (11x, almost always "low angle"), a pose/state word (11x), placement 1, figure count 1.
- **The low camera angle is the systematic miss.** 7 of 8 fights ended with "camera looks up from a low angle" unmet. Looking at fight-02 and fight-08: both are well-staged two-person fights (left attacker, right defender) with at most a mild low angle, so the blind read's "level" may be strict, or Qwen may simply not do a strong low angle; redrawing with the same words does not change it (it burns the attempts). That is exactly what the staging-picture escalation is for.
- **Plan compliance is not the same as the owner liking it.** The raw "a samurai duel at dusk" picture (symmetrical blade clash, wide, full bodies) is arguably as good as the director's (close, left attacker thrusting at the right defender). Only the owner's ratings can say which is better; they have not been collected, so no claim of improvement is made here.

## Staging picture + transfer (spike, gate FAILED: not wired in)

`tools/scene_director/staging_spike.py` (throwaway) draws a mannequin picture from the plan (blue left, red right, strike arrow, horizon height from the camera angle) and edits the raw baseline picture with it through `compose_transfer_prompt` + `ArtEngine.edit` (character picture = Picture 1, staging = Picture 2), 6 fight briefs, one seed.

| brief | edit s | checker score before -> after | camera "low angle" after |
|---|---|---|---|
| fight-01 | 66.6 | 0.29 -> 0.43 (one figure became two, planned pose followed) | still unmet |
| fight-02 | 69.7 | 0.71 -> 0.71 | still unmet |
| fight-03 | 68.3 | 0.71 -> 0.86 | still unmet |
| fight-04 | 67.6 | 0.86 -> 0.86 | still unmet |
| fight-05 | 67.5 | 0.86 -> 0.29 (two people standing, not fighting; a gun and a face mask appeared) | still unmet |
| fight-06 | 68.8 | 0.50 -> 0.63 | still unmet |

- Gate was "clearly better in at least 4 of 6": 3 better, 2 unchanged, 1 much worse. **Not met, so escalation is not wired in** (no `scene_staging.py`; `generate_scene` has no escalate hook). The camera angle was never fixed by the transfer, and one edit costs about as much as the whole 3-attempt fast path (~68 s).
- Where it helped, it helped on placement/count/pose (fight-01 had one figure, the staged edit had two with the planned pose). Mannequin pictures are a lever for those, not for the camera.
- Not tried: a better mannequin (real poses), another seed, two-pass use only after the fast path stalls on placement/count.

## The camera angle: what worked instead

- Plain compiler wording ("Shot from a low camera angle looking up.") reached a low angle (blind camera read) in **0 of 8** fights on the first attempt. Adding one strong sentence at the end of the prompt ("Remember: Camera placed near the ground looking steeply upward, the subjects tower over the viewer.") gave **3 of 8**, and with the sentence built into the default prompt, 8 fresh-seed runs gave **4 of 8** (4 of 8 accepted on attempt 1). Small samples, one seed per brief and check by the 9B blind read, so a direction, not a rate. `CAMERA_FIX` in `scene_prompt.py`; only the low angle is measured (high and dutch use the same mechanism, unmeasured).
- Live check through the MCP tools against a real engine (own temp database): `panelflow_scene_propose` -> `correct` (camera.angle low) -> `generate` (job SCENE_GENERATION) -> `rate`. "a samurai duel at dusk": plan "low angle, medium shot, samurai_a on the left striking right, samurai_b on the right blocking, light from behind", accepted on the first attempt in 24 s; looked at the picture: two fighters, left one thrusting a sword at the right one who raises an open palm, low angle, dusk sky.
