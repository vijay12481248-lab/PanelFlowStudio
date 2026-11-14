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
