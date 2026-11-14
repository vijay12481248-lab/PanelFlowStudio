# Scene Director Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a vague brief into a written scene plan, draw it with Qwen, check the picture against the plan, correct or escalate to a staging picture, learn from failures, and measure owner agreement.

**Architecture:** New modules in `engine/original/` (`scene_plan`, `scene_planner`, `scene_prompt`, `scene_check`, `scene_run`, `scene_staging`, `scene_lessons`, `scene_ratings`) sit on top of the existing `ShotSpec`, prompt compiler, reviewer (`review.py`), correction planner (`planner.py`), refine loop and `ArtEngine`. Playbooks are JSON data per scene type. Nothing new talks to ComfyUI except through `ArtEngine`.

**Tech Stack:** Python 3.14 (`.venv\Scripts\python.exe`), pydantic, FastAPI, Pillow (already used by `refine.py`), local Ollama `qwen3.5:9b`, `ArtEngine` (Qwen Image 2.1 Turbo; H3-Image edit for transfer).

**Spec:** `docs/superpowers/specs/2026-11-14-scene-director-design.md`

## Global Constraints

- One art workflow: `qwen_image_21` run only through `engine/comfyui/art.py` `ArtEngine`; do not add a second text-to-image workflow (`tests/unit/test_art_engine.py` fails if the registry gains one). H3-Image only through `ArtEngine.edit` (transfer).
- Local-first: never fall back silently to cloud or mock.
- Generic only: no per-story or per-chapter prompts; playbooks are per scene type.
- Run tests with `.venv\Scripts\python.exe -m pytest <path> -p no:cacheprovider`; tests use temp app-data via `tests/conftest.py`.
- Reviewer: one full review ~70 s (`qwen3.5:9b`); transfer edit 40-90 s; transfer prompt wording: pose picture and character picture roles as in `compose_transfer_prompt` (`engine/comfyui/edit_prompt.py`).
- Verify on real data: every phase ends with real pictures looked at and timings recorded; say what was not verified.
- Commit per milestone with its tests; `git status` shows unrelated files from other work: stage only your own files.
- Never write the 90% as achieved until measured with owner ratings.

## Review Focus

1. A brief with one actor or none (portrait, empty landscape, concept art): the plan stays valid, no attacker/defender or contact rules fire.
2. Owner's correction contradicts the plan (both fighters on the same side, strike aimed away from the target): rejected with a specific message, plan unchanged.
3. Empty, whitespace-only or very long brief: clear error or truncation before any model call.
4. Reviewer unreachable or every item "uncertain": best candidate is delivered flagged `unverified`, never reported as passed, loop still ends.
5. Cancel or GPU-busy mid-run: `is_cancelled` is honoured and candidates already drawn are kept.

---

### Task 1: Ratings store and baseline harness (P0)

**Files:**
- Create: `engine/original/scene_ratings.py`, `tools/scene_director/baseline_briefs.json`, `tools/scene_director/baseline.py`, `tests/unit/test_scene_ratings.py`

**Interfaces:**
- Produces: `class Rating(BaseModel)`: `brief_id: str`, `mode: str` ("raw"|"director"), `good: bool`, `reason: str = ""` (one of `emotion|pose|camera|identity|style|other`), `seconds: float`, `plan_path: str = ""`. `load_ratings(path: Path) -> list[Rating]` (JSON list; missing file -> `[]`). `save_rating(path: Path, r: Rating) -> None` (replaces an existing rating of the same `brief_id`+`mode`). `summary(ratings: list[Rating]) -> dict` with keys `n`, `good_rate` (0..1, 0 when `n == 0`), `by_reason` (counts over not-good), `mean_seconds`.
- `baseline.py`: `run(briefs: list[dict], mode: str, out: Path, art_engine) -> list[dict]` ("raw" sends `brief["text"]` straight to `ArtEngine.generate` with a fixed per-brief seed and 1344x768; records seconds; "director" is added in Task 6). CLI: `python tools/scene_director/baseline.py --mode raw --out <dir>` writes pictures, `results.json` and `contact_sheet.html` (one picture per card, Good / Not good buttons, reason dropdown, "Download ratings.json" button; plain HTML, no engine needed).

- [ ] **Step 1: Write failing tests** in `tests/unit/test_scene_ratings.py`: `test_summary_counts_good_rate_and_reasons` (3 ratings, 2 good, 1 not-good with reason "pose" -> `good_rate == 2/3`, `by_reason == {"pose": 1}`), `test_summary_empty_is_zero`, `test_save_rating_replaces_same_brief_and_mode` (save twice -> `len(load_ratings(p)) == 1`, latest wins), `test_load_missing_file_is_empty`.
- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/unit/test_scene_ratings.py -p no:cacheprovider` - expect FAIL (module missing).
- [ ] **Step 3: Implement** `scene_ratings.py` per Interfaces (plain JSON file, write via temp file + replace).
- [ ] **Step 4: Run tests** - expect PASS.
- [ ] **Step 5: Write `baseline_briefs.json`**: 24 briefs `{id, scene_type, text}`: 8 fight, 8 emotion, 8 concept art; each text is one vague sentence a lazy user would type (no staging detail); mix single-actor and multi-actor, genres, indoor/outdoor.
- [ ] **Step 6: Implement `baseline.py`** (cancellation not needed; one picture failing must not stop the batch: record `error` and continue).
- [ ] **Step 7 (real run, owner gate):** start ComfyUI per AGENTS.md, run mode `raw`, record seconds per picture; the owner opens `contact_sheet.html`, rates, downloads `ratings.json`. Record `summary()` and mean seconds in `docs/SCENE_DIRECTOR.md` under "Baseline". This number and the seconds set the speed budget used in Task 6.
- [ ] **Step 8: Commit** `feat(scene): ratings store and baseline harness`.

### Task 2: ScenePlan model, playbooks, validation (P1)

**Files:**
- Create: `engine/original/scene_plan.py`, `engine/original/playbooks/fight.json`, `emotion.json`, `concept_art.json`, `tests/unit/test_scene_plan.py`

**Interfaces:**
- Produces (pydantic): `ActorPlan(id, description, side: left|center|right, depth: foreground|midground|background = "midground", action_state: str, expression: str = "")`; `ContactPlan(source, target, body_part = "", direction = "")` (direction is screen-relative: `left|right|up|down|up-left|...`); `CameraPlan(angle: eye_level|low|high|dutch, distance: close|medium|wide, note = "")`; `LightPlan(direction: front|back|left|right|top|below, quality = "", color = "")`; `ScenePlan(scene_type, brief, actors, contacts = [], camera, light, depth: dict[str, str] = {}, mood = "", setting = "", assumed: list[str] = [])` where `assumed` lists dotted field paths the planner defaulted (e.g. `"camera.angle"`).
- `Playbook(scene_type, keywords: list[str], action_states: list[str], high_impact: list[str], defaults: dict, questions: dict[str, str], staging_rules: list[str])`; `load_playbook(scene_type: str) -> Playbook` (ValueError on unknown type); `scene_types() -> list[str]`.
- `validate_plan(plan: ScenePlan, playbook: Playbook) -> list[str]` returns plain-language problems (empty list = valid). Rules: every `action_state` in `playbook.action_states`; every contact `source`/`target` is an actor id; no contact to self; fight type with 2+ actors: opposite `side` for a contact's source and target, and contact `direction` points from the source's side toward the target's side; fight needs at least one actor, never requires two.

- [ ] **Step 1: Failing tests:** `test_valid_fight_plan_has_no_problems`; `test_same_side_fighters_rejected` (assert one problem mentioning both actor ids); `test_strike_direction_away_from_target_rejected`; `test_unknown_action_state_rejected`; `test_single_actor_portrait_valid` (emotion, one actor, no contacts, `validate_plan(...) == []`); `test_empty_landscape_concept_art_valid` (zero actors, concept_art); `test_load_playbook_unknown_raises`; `test_every_shipped_playbook_loads` over `scene_types()`.
- [ ] **Step 2: Run** expect FAIL.
- [ ] **Step 3: Implement** models, loader and `validate_plan`. Playbook JSON `fight`: action_states `striking, blocking, readying, struck, falling, dodging`; high_impact `["camera.angle","actors.*.action_state","light.direction"]`; each playbook has defaults for camera, light, depth and one question text per high-impact item.
- [ ] **Step 4: Run** expect PASS.
- [ ] **Step 5: Commit** `feat(scene): ScenePlan model, playbooks and validation`.

### Task 3: Planner and intake (propose, confirm, correct) (P1)

**Files:**
- Create: `engine/original/scene_planner.py`, `tests/unit/test_scene_planner.py`

**Interfaces:**
- Consumes: Task 2 (`ScenePlan`, `Playbook`, `load_playbook`, `scene_types`, `validate_plan`); `engine.original.story._ask(provider, prompt, model, check, temperature, attempts, max_tokens, notes)` (retry-with-feedback; `provider.generate_structured` is the model call).
- Produces: `class Question(BaseModel): field: str; text: str; default: str`. `class Proposal(BaseModel): plan: ScenePlan; summary: str; questions: list[Question]` (at most 3, only playbook `high_impact` items listed in `plan.assumed`).
  `classify_scene_type(brief: str) -> str | None` (playbook keywords; None when no keyword hits).
  `async propose(provider, brief: str, scene_type: str | None = None) -> Proposal` (classifies by keywords, falls back to one model call; `ValueError` for empty/whitespace brief before any model call; brief truncated to 1,000 characters; planner output is checked with `validate_plan`; fields the brief did not state are filled from playbook defaults and named in `plan.assumed`).
  `plan_to_words(plan: ScenePlan) -> str` (one plain sentence, e.g. "low angle, hero on the left striking down-right, villain on the right blocking, light from behind").
  `apply_corrections(plan: ScenePlan, playbook: Playbook, corrections: dict[str, str]) -> ScenePlan` (keys are dotted field paths; raises `ValueError(problems)` when `validate_plan` fails, plan unchanged; removes corrected paths from `assumed`).

- [ ] **Step 1: Failing tests** with a fake provider whose `generate_structured` returns a canned plan dict: `test_propose_fills_defaults_and_marks_assumed`; `test_questions_are_capped_at_three_and_high_impact_only`; `test_stated_items_are_not_asked` (brief says "from below" -> no `camera.angle` question); `test_empty_brief_raises_before_model_call` (fake provider records zero calls); `test_long_brief_is_truncated`; `test_invalid_planner_output_is_retried_with_problems` (first answer same-side fighters, second valid -> two calls); `test_apply_corrections_rejects_contradiction_and_leaves_plan_unchanged`; `test_plan_to_words_mentions_every_actor_and_camera`.
- [ ] **Step 2: Run** expect FAIL.
- [ ] **Step 3: Implement** per Interfaces; the prompt for the planner states the playbook's `action_states` and `staging_rules` verbatim and asks for JSON of `ScenePlan` fields only.
- [ ] **Step 4: Run** expect PASS.
- [ ] **Step 5 (real data):** run `propose` on 6 baseline briefs with the real local model; record planner seconds per brief and whether `validate_plan` passed first try, in `docs/SCENE_DIRECTOR.md` under "Planner".
- [ ] **Step 6: Commit** `feat(scene): planner with propose/confirm/correct intake`.

### Task 4: Plan to prompt and requirements (P1)

**Files:**
- Create: `engine/original/scene_prompt.py`, `tests/unit/test_scene_prompt.py`

**Interfaces:**
- Consumes: `ScenePlan`; `PromptCompiler.compile_image_prompt(story, spec, location_id, target, emphasis, simplify, dims, fallback_action, extra_negative, style_profile) -> CompiledPrompt` (`engine/original/prompt.py`); `ShotSpec`, `CharPose` (`engine/original/shotspec.py`); `Claim` (`engine/original/models.py`).
- Produces: `plan_to_shotspec(plan: ScenePlan) -> tuple[OriginalStory, ShotSpec, str]` (an ephemeral one-scene story whose bible holds one `Character` per actor built from `ActorPlan.description`, one `Location` from `plan.setting`; third value is the location id; the builder reads `models.py` for required fields). `compile_scene_prompt(plan: ScenePlan, *, emphasis: list[str] | None = None, lessons: str = "", target: str = "qwen_image_21") -> tuple[str, str, tuple[int, int]]` returns (positive, negative, (width, height)); `lessons` text is appended to the negative guidance, not the positive. `plan_requirements(plan: ScenePlan) -> list[Claim]`: one `Claim` per checkable fact with `kind` in `subject|pose|placement|camera|framing|environment` and `critical=True` for actor count, each actor's side and action state, contacts, camera angle; light direction and depth layers are `critical=False`; mood is never a claim (not visually verifiable).

- [ ] **Step 1: Failing tests:** `test_prompt_names_each_actor_side_and_action` (positive contains each actor description and its action word; left actor's text appears before right actor's); `test_emphasis_is_stated_first`; `test_lessons_go_to_negative_only`; `test_requirements_cover_count_sides_states_contacts_camera` (assert exact claim texts for a 2-actor fight plan fixture); `test_mood_is_not_a_requirement`; `test_no_actor_plan_compiles` (landscape).
- [ ] **Step 2: Run** expect FAIL.
- [ ] **Step 3: Implement** (reuse the compiler; do not write a second prompt grammar; camera enum to the camera strings `ShotSpec.camera` already accepts, read from `prompt.py`).
- [ ] **Step 4: Run** expect PASS.
- [ ] **Step 5: Commit** `feat(scene): compile a scene plan to a prompt and a checklist`.

### Task 5: Plan-based check (P2)

**Files:**
- Create: `engine/original/scene_check.py`, `tests/unit/test_scene_check.py`

**Interfaces:**
- Consumes: `plan_requirements`, `compile_scene_prompt`; from `review.py`: `_grounded_check(provider, image, claims)`, `_count_check`, `count_expectation`, `combine(...)`, `evaluate_prompt_image(provider, image, prompt, audit_gates, locate_defects) -> Review`, `locate_failed_items`; `Review`, `ItemVerdict` (`models.py`).
- Produces: `async check_scene(provider, image: Path, plan: ScenePlan, *, full: bool = False) -> Review`. Fast mode (default): only `critical` requirements, picture downscaled to long side 768 before the model sees it, no description pass, no anatomy audit; actor count by `_count_check` (code decides, not the description); side of each actor from the located box centre vs picture centre. Full mode: `evaluate_prompt_image` on the compiled prompt plus the plan claims. Items the picture cannot show go to `Review.unverifiable`. If the model answers "uncertain" for every item, `Review.decision == "accept_low"` and `Review.reasons` contains `"unverified"`; never "accept".
  `def spatial_failure(review: Review) -> bool`: True when a failed item has kind pose / placement / camera or is a contact (this is the escalation trigger in Task 6).

- [ ] **Step 1: Failing tests** (fake provider, no GPU): `test_wrong_actor_count_fails_even_if_description_agrees`; `test_left_actor_on_right_fails_placement`; `test_fast_mode_skips_noncritical_and_description` (fake provider records which calls were made); `test_all_uncertain_is_accept_low_unverified`; `test_unverifiable_items_are_listed_not_failed`; `test_spatial_failure_true_for_pose_false_for_style_only`.
- [ ] **Step 2: Run** expect FAIL.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** expect PASS. Also run `tests/unit/test_challenger_m1_2_stress.py` and `tests/unit/test_review_prompt_mode.py` (review.py internals are reused).
- [ ] **Step 5 (real data):** run `check_scene` fast and full on 6 real pictures from Task 1's baseline using `propose`-made plans; record seconds of each mode and agreement with the owner's ratings in `docs/SCENE_DIRECTOR.md` under "Check". Fast-mode seconds feed the Task 6 budget.
- [ ] **Step 6: Commit** `feat(scene): plan-based fast and full picture check`.

### Task 6: Fast-path run loop (P2)

**Files:**
- Create: `engine/original/scene_run.py`, `tests/unit/test_scene_run.py`
- Modify: `tools/scene_director/baseline.py` (add mode `director`: `propose` in auto mode, then `generate_scene`)

**Interfaces:**
- Consumes: Tasks 3-5; `planner.plan_correction(review, history, budget, edit_available, allow_heuristic_masks) -> CorrectionPlan`; `planner.Budget`; `refine.record_candidate(ws, key, iterations, data, mask, **meta)`; `ArtEngine.generate(prompt, negative_prompt, width, height, seed, ...) -> ArtImage`.
- Produces: `class SceneBudget(BaseModel): max_attempts: int = 3; max_seconds: float` (default set from Task 1/5 measurements, recorded in `docs/SCENE_DIRECTOR.md`); `class SceneResult(BaseModel): image_path: str; plan: ScenePlan; review: Review | None; unmet: list[str]; unverified: bool; escalated: bool; seconds: float; iterations: list[dict]`. `generate_scene(art_engine, provider, plan: ScenePlan, *, ws: Path, key: str, seed: int | None = None, budget: SceneBudget = SceneBudget(), lessons: str = "", is_cancelled: Callable[[], bool] = lambda: False) -> SceneResult` (blocking; callers in async code use a thread). Loop: compile -> generate -> `check_scene` -> `plan_correction`; stops on accept, budget, plateau or cancel; delivers the best candidate with its unmet items listed; every candidate kept under `<ws>/panels/_candidates/<key>/`. Escalation hook: `generate_scene` accepts `escalate: Callable[[ScenePlan, bytes, int], bytes] | None = None` (arguments: plan, best candidate PNG, seed; returns a new PNG; wired in Task 7 as `functools.partial(escalate_with_staging, art_engine)`); when None, a spatial failure just ends the loop with the best candidate and `unmet`.

- [ ] **Step 1: Failing tests** (fake engine and fake checker): `test_accepts_first_good_picture_in_one_attempt`; `test_failed_item_becomes_emphasis_next_attempt` (assert second prompt starts with the failed requirement); `test_stops_at_max_attempts_and_delivers_best_with_unmet`; `test_unreviewable_picture_is_delivered_unverified` (Review Focus 4); `test_cancel_stops_and_keeps_candidates` (Review Focus 5: files exist, result flags cancelled in `unmet`); `test_budget_seconds_stops_loop`.
- [ ] **Step 2: Run** expect FAIL.
- [ ] **Step 3: Implement** per Interfaces; reuse `plan_correction` rather than writing new retry rules.
- [ ] **Step 4: Run** expect PASS. Run `tests/unit/test_correction_planner.py tests/unit/test_refine_loop.py` too.
- [ ] **Step 5 (real data, owner gate):** run the 24 baseline briefs in mode `director`, owner rates, `summary()` of both modes side by side plus seconds per delivered picture in `docs/SCENE_DIRECTOR.md`. If director is not better than raw, stop and report before Task 7.
- [ ] **Step 6: Commit** `feat(scene): fast-path scene run loop`.

### Task 7: Staging picture and escalation (P3)

**Files:**
- Create: `engine/original/scene_staging.py`, `tools/scene_director/staging_spike.py`, `tests/unit/test_scene_staging.py`
- Modify: `engine/original/scene_run.py` (wire `escalate`)

**Interfaces:**
- Consumes: `compose_transfer_prompt(character_picture: bytes, pose_picture: bytes, hint: str, *, timeout_s) -> str`; `ArtEngine.edit(prompt, reference_images, *, width, height, seed, ...) -> ArtImage`; `spatial_failure`.
- Produces: `render_staging(plan: ScenePlan, size: tuple[int, int]) -> bytes` (PNG drawn with Pillow: one plain figure per actor at its `side`/`depth` position, posed from its `action_state` via a small table in `scene_staging.py`, framed by `camera.distance`/`angle`, contact arrows from `ContactPlan.direction`; figures carry no faces, clothes or style). `escalate_with_staging(art_engine, plan, best_png: bytes, *, seed: int) -> bytes` (best failed candidate = character picture, staging = pose picture, through `compose_transfer_prompt` and `ArtEngine.edit`). Escalation runs once per scene, only when `spatial_failure(review)` or two plateaued redraws, and its result is re-checked with `check_scene`.

- [ ] **Step 1 (spike, throwaway, no tests):** `staging_spike.py` renders staging pictures for 6 fight/emotion plans, runs the transfer on the matching baseline picture, saves before/after. The owner and the agent look at them. **Decision gate:** if staged results do not follow the planned pose/camera clearly better than the fast-path picture in at least 4 of 6, do not wire escalation; fall back to "best candidate + unmet list" and tell the owner. Record numbers and seconds in `docs/SCENE_DIRECTOR.md` under "Staging".
- [ ] **Step 2: Failing tests** (only if the gate passes): `test_staging_png_has_requested_size_and_one_figure_per_actor` (decode, count blobs); `test_left_actor_figure_is_in_left_half`; `test_zero_actor_plan_renders_empty_frame`; `test_escalation_runs_once_and_only_on_spatial_failure` (fake engine counts `edit` calls); `test_escalated_result_is_rechecked_and_worse_result_not_delivered`.
- [ ] **Step 3: Run** expect FAIL; **Step 4: Implement**; **Step 5: Run** expect PASS.
- [ ] **Step 6 (real data):** re-run the briefs that failed spatially in Task 6, owner rates, record whether escalation raised the good rate and what it cost in seconds.
- [ ] **Step 7: Commit** `feat(scene): staging picture escalation` (or `docs(scene): staging spike result` if the gate failed).

### Task 8: Learning from failures (P4)

**Files:**
- Create: `engine/original/scene_lessons.py`, `tests/unit/test_scene_lessons.py`
- Modify: `engine/original/scene_run.py` (read lessons before compiling, record after the run)

**Interfaces:**
- Consumes: `MistakeLedger(file_path)` with `record_or_escalate_mistake(domain, flawed_pattern, prevention_rule, example_bad, example_good, category, severity)`, `load_mistakes(domain)`, `get_anti_patterns_prompt(domain)` (`engine/creative/mistakes.py`; default file path is CWD-relative, so tests and the app pass an explicit path under `settings.app_data_dir`).
- Produces: `lesson_domain(model: str, scene_type: str) -> str` (`"scene:{model}:{scene_type}"`); `record_outcome(ledger: MistakeLedger, model: str, scene_type: str, review: Review, fixed_by: str = "") -> int` (one ledger entry per failed item, `flawed_pattern` = the requirement kind plus defect type, `prevention_rule` = the correction wording, same-pattern repeats increment `recurrence_count`; returns entries written); `lessons_for(ledger, model, scene_type, min_recurrence: int = 2) -> str` (text of entries with `recurrence_count >= min_recurrence`, empty string when none). One-off failures are recorded but not used (noisy 9B judge).

- [ ] **Step 1: Failing tests** (temp ledger path): `test_one_failure_is_recorded_but_not_a_lesson`; `test_second_identical_failure_becomes_a_lesson`; `test_lessons_are_per_model_and_scene_type`; `test_passed_items_write_nothing`; `test_ledger_file_is_not_written_to_repo_cwd` (assert the ledger path given is the only file touched).
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS.
- [ ] **Step 5:** wire into `generate_scene` (lessons string goes to `compile_scene_prompt(lessons=...)`); add `test_generate_scene_uses_lessons_and_records_outcome` in `test_scene_run.py`.
- [ ] **Step 6 (real data):** run the 24 briefs twice; record how many lessons were promoted and whether the second pass's good rate (owner rated) moved. Report plainly if it did not.
- [ ] **Step 7: Commit** `feat(scene): learn lessons from failed checks`.

### Task 9: Surfaces: HTTP, MCP, docs

**Files:**
- Modify: `engine/api/routers/original.py`, `engine/mcp/tools/original_story_tools.py`, `AGENTS.md`
- Create: `docs/SCENE_DIRECTOR.md` (if not already started in Task 1), `tests/unit/test_scene_api.py`

**Interfaces:**
- Consumes: Tasks 1-8. Follow how `original.py` starts long image work through `JobManager` (`engine/jobs/workflow.py`) and how `original_story_tools.py` wraps routes with `@registry.tool(... domain="original")` and `bridge`.
- Produces routes under `/api/original/scene`: `POST /propose {brief, scene_type?} -> Proposal`; `POST /correct {plan, corrections} -> {plan, summary}` (422 with the problem list on contradiction); `POST /generate {plan, seed?} -> job id` (result is `SceneResult`); `POST /rate {brief_id|job_id, good, reason?}`; `GET /ratings/summary -> summary()`. MCP tools: `panelflow_scene_propose`, `panelflow_scene_correct`, `panelflow_scene_generate`, `panelflow_scene_rate`.

- [ ] **Step 1: Failing tests** (FastAPI test client, fake provider/engine): `test_propose_returns_summary_and_at_most_three_questions`; `test_correct_contradiction_is_422_with_problems`; `test_generate_returns_job_id`; `test_rate_then_summary_counts_it`; `test_empty_brief_is_422`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement** routes and tools. **Step 4: Run** expect PASS; also run the full `tests/unit` command from AGENTS.md.
- [ ] **Step 5:** write `docs/SCENE_DIRECTOR.md` (flow, how to run the baseline, the measured numbers from Tasks 1-8, known weaknesses) and add one bullet to the "What exists" list in `AGENTS.md`.
- [ ] **Step 6 (real data):** drive propose -> correct -> generate -> rate through the MCP tools against the live engine (stdio client, as in the MCP video workflow memory); look at the picture.
- [ ] **Step 7: Commit** `feat(scene): HTTP and MCP surface, docs`.

Out of scope until asked: desktop UI screen for the director and the rating buttons (the contact sheet and API/MCP cover rating for now), video staging.
