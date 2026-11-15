# Scene Review Page with Two Cooperating Vision Judges - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each Scene Director picture, two vision models judge it and cross-check each other, the result is stored in the database, the owner is nudged to review it on a new desktop page (liked %, agree with AI or comment), and the stored feedback becomes a queryable knowledge base that feeds the Scene Director's lessons.

**Architecture:** `judges.py` (two judge adapters, one answer shape) and `crosscheck.py` (blind round, narrow re-look on disagreements) are pure engine code. `scene_store.py` keeps runs, analyses and feedback in the app's SQLite database (SQLAlchemy tables plus an FTS5 table). The existing scene router and job gain run/feedback/knowledge endpoints; the desktop app gains a Scene page, a review banner and badge. Nothing new talks to ComfyUI except through `ComfyUIClient` and `ArtEngine`.

**Tech Stack:** Python 3.14 (`.venv\Scripts\python.exe`), SQLAlchemy + SQLite (FTS5), FastAPI, local Ollama `qwen3.5:9b`, ComfyUI `TextGenerate` with `qwen3vl_8b_int8_convrot.safetensors`, React + `@tanstack/react-query` + `@panelflow/ui-v2`, tests with pytest and `node:test` via `npx tsx`.

**Spec:** `docs/superpowers/specs/2026-11-14-review-page-two-judges-design.md` (builds on `docs/SCENE_DIRECTOR.md` and the code in `engine/original/scene_*.py`)

## Global Constraints

- Two judges run one after the other, never during a draw; `release_local_model()` (`engine/comfyui/edit_prompt.py`) runs between the Ollama judge and the ComfyUI judge.
- `TextGenerate` with Qwen3-VL 8B works only when ComfyUI runs with `--disable-dynamic-vram` (measured). The graph is `LoadImage -> CLIPLoader(clip_name="qwen3vl_8b_int8_convrot.safetensors", type="qwen_image", device="default") -> TextGenerate(clip, prompt, image, max_length, sampling_mode="off", thinking=false) -> PreviewAny`; the answer is `history[prompt_id]["outputs"][<PreviewAny node>]["text"][0]`.
- Pictures are never shrunk before a judge sees them (measured: the answer changes at <=1024 px).
- Storage is the app's SQLite database (no vector database, no new service). No OS toast in v1 (no notification plugin exists). No free-form multi-round chat between judges: one re-look only.
- Downloads and new dependencies need the owner's approval first (AGENTS.md). Tests isolate state through `tests/conftest.py`.
- Run tests with `.venv\Scripts\python.exe -m pytest <path> -p no:cacheprovider`; desktop tests with `npx tsx --tsconfig apps/desktop/tsconfig.json --test <file>` from the repo root; type check with `cd apps/desktop && npx tsc --noEmit -p .`.
- Verify on real data: every phase ends with real pictures or the real app looked at. Never claim the judges are better or the page works from tests alone. Commit per milestone; stage only your own files (running the whole `tests/unit` suite leaves a stray `run_engine.py` on :8765 and rewrites `engine/chronoflow/vault/{jobs,mistakes_ledger}.json`: kill it and `git checkout` those files).

## Review Focus

1. The second judge is unavailable (ComfyUI down, flag missing, `TextGenerate` errors): the analysis is made with one judge and says `single_judge`; the picture, the run row and the review request still appear.
2. Both judges answer with unusable text or nothing: items are `unjudged` with confidence 0, never `agreed`.
3. Feedback: `liked` outside 0-100, unknown run id, submitted twice (second replaces the first, one row), a note of 100,000 characters.
4. Hundreds of unreviewed runs: the banner shows the count, the list is paged, the AppShell poll stays one cheap count request.
5. A full-text search with quotes, `AND`, `*` or unbalanced parentheses returns results or an empty list, never a SQL error.

---

### Task 1: Judges: one answer shape, two adapters (P1)

**Files:**
- Create: `engine/original/judges.py`, `tests/unit/test_judges.py`

**Interfaces:**
- Produces: `class JudgeAnswer(BaseModel)`: `judge: str`, `ok: bool` (False when unusable), `camera: Literal["looks_up","level","looks_down","tilted"] | None`, `people: int | None`, `actions: list[str]` (one lowercase word per person, left to right), `evidence: str = ""`, `raw: str = ""`.
  `read_prompt(states: list[str]) -> str` (asks for three lines `CAMERA:`, `PEOPLE:`, `ACTIONS:` and one `EVIDENCE:` line; never mentions a plan) and `reread_prompt(topic: Literal["camera","people","action"], index: int | None, other_value: str, other_evidence: str, states: list[str]) -> str` (one narrow question, states the other reviewer's claim and evidence, asks for a fresh answer and the visible evidence).
  `parse_judge_text(text: str, judge: str, states: list[str]) -> JudgeAnswer` (tolerant: "Level with them." -> `level`; "looking up from below" -> `looks_up`; "Two people." / "2" / "one person" -> int; actions split on `;`, `,` or "Left:/Right:" labels, each mapped to the nearest allowed state word else kept lowercase; unusable -> `ok=False`).
  `class Judge(Protocol)`: `name: str`; `async read(self, image: Path | bytes, states: list[str]) -> JudgeAnswer`; `async reread(self, image, topic, index, other: JudgeAnswer, states) -> JudgeAnswer`.
  `class OllamaJudge(provider, name="qwen3.5:9b")` (uses `provider.analyze_vision(image, prompt, max_tokens=300, temperature=0.0)`). `class ComfyJudge(client: ComfyUIClient, name="qwen3-vl-8b", clip_name="qwen3vl_8b_int8_convrot.safetensors")` with `build_graph(image_name: str, prompt: str) -> dict` (the graph above) and the run through `client.upload_image_bytes`, `client.submit_prompt`, `client.history` polling (timeout 120 s, then `ok=False`). `async def available_judges(provider, client) -> list[Judge]`: always the Ollama judge; the Comfy judge only when `client.node_catalog()` has `TextGenerate` and the clip file is listed (`client.discover_models()`); never raises.

- [ ] **Step 1: Failing tests** in `tests/unit/test_judges.py` (fake provider and fake client, no GPU): `test_parse_real_qwen3vl_text` (`"CAMERA: Level with them.  \nPEOPLE: Two people.  \nACTIONS: Left: Punching forward. Right: Blocking with hands."` -> camera `level`, people 2, actions `["punching", "blocking"]`), `test_parse_camera_phrases` (parametrized: "looking up from below" -> looks_up, "from above" -> looks_down, "tilted" -> tilted, "Level" -> level), `test_parse_people_words_and_digits`, `test_parse_unusable_text_is_not_ok` (empty, prose without the three lines), `test_read_prompt_never_mentions_a_plan` (no "plan", no actor words), `test_reread_prompt_contains_the_other_claim_and_asks_for_evidence`, `test_comfy_graph_has_the_four_nodes_and_flag_values` (exact class types and `sampling_mode == "off"`, `thinking is False`), `test_comfy_judge_reads_text_from_history_output`, `test_comfy_judge_error_or_timeout_is_not_ok_not_raised`, `test_ollama_judge_never_raises` (provider raising -> `ok=False`), `test_available_judges_without_textgenerate_is_ollama_only`.
- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/unit/test_judges.py -p no:cacheprovider -q` - expect FAIL (module missing).
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** expect PASS.
- [ ] **Step 5: Commit** `feat(judges): two vision judges with one answer shape`.

### Task 2: Cross-check protocol (P1)

**Files:**
- Create: `engine/original/crosscheck.py`, `tests/unit/test_crosscheck.py`

**Interfaces:**
- Consumes: `Judge`, `JudgeAnswer`, `parse_judge_text` (Task 1).
- Produces: `class Item(BaseModel)`: `key: str` (`"camera"`, `"people"`, `"action:<i>"`), `status: Literal["agreed","resolved","disputed","single","unjudged"]`, `value: str | None` (final value; `None` when disputed or unjudged), `confidence: float` (agreed 0.9, resolved 0.7, single 0.5, disputed 0.3, unjudged 0.0), `answers: dict[str, dict]` (judge name -> `{"round1": str | None, "round2": str | None, "evidence": str}`), `suspect_flips: list[str]` (judge names).
  `class CrossCheck(BaseModel)`: `judges: list[str]` (those that answered), `items: list[Item]`, `single_judge: bool`, `seconds: float`.
  `async def cross_check(judges: list[Judge], image: Path | bytes, states: list[str], *, same_state: Callable[[str, str], bool] = lambda a, b: a == b, between: Callable[[], None] = lambda: None) -> CrossCheck` (`between` is called between judges, e.g. `release_local_model`; never raises). Rules: round 1 runs each judge in turn (a raising or `ok=False` judge is dropped); items are camera, people, and one action per index present in every answering judge's `actions`; a differing item goes to round 2 where each judge `reread`s that item with the other's answer; both now equal (`same_state` for actions) -> `resolved`, else `disputed`. A **suspect flip**: a judge's round-2 value equals the other's round-1 value, differs from its own round-1 value, and its round-2 evidence is shorter than 4 words or equal to its round-1 evidence. One answering judge -> every item `single`; none -> every item `unjudged`.

- [ ] **Step 1: Failing tests** (scripted fake judges): `test_agreement_needs_no_second_round` (reread never called, confidence 0.9), `test_a_disagreement_that_both_resolve`, `test_a_disagreement_that_stays_is_disputed_with_no_value`, `test_only_the_disputed_item_is_reread`, `test_suspect_flip_is_recorded_when_a_judge_gives_in_without_evidence`, `test_flip_with_new_evidence_is_not_suspect`, `test_one_judge_down_gives_single_judge_items` (Review Focus 1), `test_both_judges_unusable_gives_unjudged_zero_confidence` (Review Focus 2), `test_judge_that_raises_is_dropped_not_fatal`, `test_actions_compare_with_same_state_groups` (e.g. "grieving"/"lost" agree), `test_people_count_mismatch_skips_action_items`, `test_between_is_called_between_judges_and_its_failure_is_ignored`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS.
- [ ] **Step 5: Commit** `feat(judges): structured cross-check between two judges`.

### Task 3: Bake-off on labelled pictures and the gate (P1)

**Files:**
- Create: `tools/scene_director/labels.json`, `tools/scene_director/judge_bakeoff.py`, `tests/unit/test_judge_bakeoff.py`
- Modify: `docs/SCENE_DIRECTOR.md` (new section "Two judges")

**Interfaces:**
- Consumes: Tasks 1-2; ComfyUI started with `--disable-dynamic-vram` (as the owner's ComfyUI is now); the baseline pictures in `output/Original_Scenes/_baseline/{raw,director}/`.
- Produces: `labels.json`: list of `{"file": <path relative to repo root>, "camera": "...", "people": N, "actions": ["..."]}` for at least 16 pictures (8 director fights, 4 emotion, 4 concept art incl. zero-person ones), labelled by LOOKING at each picture (the agent's reading: say so in the file's `"_note"` key). `score(labels: list[dict], answers: dict[str, list[CrossCheck | JudgeAnswer]]) -> dict` (pure): per method (`judge_A`, `judge_B`, `vote`, `crosscheck`) `answered`, `correct`, `wrong`, `coverage`, `accuracy_of_answered`, over camera, people and action items; vote and cross-check abstain on disputed items. `gate(report: dict) -> bool`: cross-check `wrong` is strictly fewer than each single judge's `wrong` AND coverage >= 0.7.

- [ ] **Step 1: Failing tests** for `score` and `gate` with hand-made answers (a method that abstains is not counted wrong; gate false when coverage 0.6; gate false when wrong ties).
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement `score`, `gate` and the CLI** (`--labels`, runs both judges and the cross-check per picture, prints the table and seconds per picture, writes `judge_bakeoff.json` next to the labels). **Step 4: Run** expect PASS.
- [ ] **Step 5 (real run):** write `labels.json` by looking at the pictures, run the bake-off with ComfyUI and Ollama up, record the table, seconds per picture and the number of suspect flips in `docs/SCENE_DIRECTOR.md`. **Decision gate:** if `gate(report)` is false, the Scene Director keeps the single judge with fewer wrong answers as `default_judges()` in Task 7 and the cross-check stays implemented but off by default (`SCENE_CROSSCHECK=1` turns it on); say so plainly in the docs. The page and the database (Tasks 5-10) are built either way.
- [ ] **Step 6: Commit** `feat(judges): judge bake-off, labels and gate result`.

### Task 4: Persist the ComfyUI flag in the app's launcher (P1)

**Files:**
- Modify: `engine/system/setup.py` (the `cmd` list near line 509)
- Test: `tests/unit/test_comfyui_launch_flags.py`

**Interfaces:**
- Produces: `comfyui_launch_command(py_exe, main_py, host: str, port: int) -> list[str]` extracted from the inline `cmd` in `engine/system/setup.py`, containing `--listen host --port port --disable-auto-launch --enable-cors-header * --disable-dynamic-vram`; the existing start code calls it.

- [ ] **Step 1: Failing test:** `test_launch_command_disables_dynamic_vram_and_keeps_the_old_flags` (exact list equality). **Step 2: Run** expect FAIL. **Step 3: Extract and add the flag.** **Step 4: Run** expect PASS plus the existing setup tests (`tests/unit -k comfyui_manager or setup`).
- [ ] **Step 5: Commit** `fix(comfyui): start ComfyUI with dynamic VRAM off so the second judge works`.

### Task 5: Storage: runs, analyses, feedback, full-text search (P2)

**Files:**
- Modify: `engine/database/models.py` (three tables), `engine/database/session.py` (`init_db` calls `ensure_scene_fts`)
- Create: `engine/original/scene_store.py`, `tests/unit/test_scene_store.py`

**Interfaces:**
- Produces (models): `SceneRunRecord` (`scene_runs`: `id` str36 pk, `project_id` FK `projects.id` cascade, `job_id` str null, `brief` Text, `scene_type` str32, `plan` JSON, `image_path` Text, `status` str32, `system_review` JSON, `attempts` int, `seconds` float, `review_state` str16 default `"pending"` (`pending|reviewed|dismissed`), `created_at`); `SceneAnalysisRecord` (`scene_analyses`: `id`, `run_id` FK cascade, `crosscheck` JSON, `judges` JSON, `single_judge` bool, `seconds` float, `error` Text null, `created_at`); `SceneFeedbackRecord` (`scene_feedback`: `id`, `run_id` FK cascade **unique**, `liked` int, `agrees_with_ai` bool, `good_tags` JSON, `wrong_tags` JSON, `note` Text, `created_at`).
- `ensure_scene_fts(engine) -> None` (`CREATE VIRTUAL TABLE IF NOT EXISTS scene_fts USING fts5(run_id UNINDEXED, text)`).
- `scene_store.py`: `create_run(db, *, project_id, job_id, brief, plan: dict, image_path, result: dict) -> dict`; `save_analysis(db, run_id, crosscheck: dict | None, error: str = "") -> dict`; `submit_feedback(db, run_id, *, liked: int, agrees_with_ai: bool, good_tags: list[str], wrong_tags: list[str], note: str = "") -> dict` (`KeyError` unknown run, `ValueError` for `liked` outside 0-100; upserts the one row; sets `review_state="reviewed"`; note cut to 4,000 chars; tags lowercased, max 12, each max 40 chars); `dismiss(db, run_id) -> dict`; `list_runs(db, *, unreviewed: bool = False, limit: int = 50, offset: int = 0) -> dict` (`{"items": [...], "total_unreviewed": int}`, newest first, limit capped at 200); `get_run(db, run_id) -> dict` (run + analysis + feedback, `KeyError` unknown); `search(db, query: str, limit: int = 20) -> list[dict]` (each term quoted, so operators and quotes are plain text; empty query -> `[]`); `stats(db) -> dict` with `runs`, `reviewed`, `mean_liked`, `by_scene_type` (`n`, `mean_liked`), `wrong_tags` (tag -> count), `ai_agreement` (`overall`, `when_disputed`, `single_judge`: share of reviews with `agrees_with_ai`, `None` when no reviews). FTS rows are written on create and on feedback (brief + note + tags).

- [ ] **Step 1: Failing tests** with the temp database from `tests/conftest.py` (create a project row for the foreign key): `test_run_roundtrip_with_analysis_and_feedback`, `test_feedback_twice_keeps_one_row_the_second_wins`, `test_feedback_validation_and_unknown_run` (Review Focus 3), `test_huge_note_is_cut`, `test_list_runs_unreviewed_paged_and_counted` (Review Focus 4: 120 runs, `limit=50`, total_unreviewed 120, limit 9999 -> 200), `test_search_finds_brief_and_note_text`, `test_search_with_operators_and_quotes_never_raises` (Review Focus 5: `'"`, `AND`, `*`, `(`), `test_stats_counts_agreement_by_case`, `test_deleting_a_project_removes_its_runs`.
- [ ] **Step 2: Run** `tests/unit/test_scene_store.py` expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS, plus `tests/unit/test_database*` and a quick import of `engine.api.app` (tables create on startup).
- [ ] **Step 5: Commit** `feat(scene): store runs, analyses and feedback in SQLite with full-text search`.

### Task 6: HTTP and MCP surface for runs, feedback and knowledge (P2)

**Files:**
- Modify: `engine/api/routers/scene.py`, `engine/mcp/tools/original_story_tools.py`
- Test: `tests/unit/test_scene_runs_api.py`

**Interfaces:**
- Consumes: `scene_store` (Task 5); the router's existing `ratings_path` and `SCENE_ROOT` (`engine/original/scene_job.py`); `get_db` (`engine/database/session.py`).
- Produces routes under `/api/original/scene`: `GET /runs?unreviewed=&limit=&offset=` -> `list_runs`; `GET /runs/{run_id}` (404); `GET /runs/{run_id}/image` (`FileResponse`; 404 when the file is missing or resolves outside `SCENE_ROOT`); `POST /runs/{run_id}/feedback` body `{liked: int (0-100), agrees_with_ai: bool, good_tags: [str], wrong_tags: [str], note: str}` (404 unknown, 422 invalid); `POST /runs/{run_id}/dismiss`; `GET /knowledge/stats`; `GET /knowledge/search?q=&limit=`. MCP tools `panelflow_scene_runs` (unreviewed or all), `panelflow_scene_knowledge_stats`, `panelflow_scene_knowledge_search`. The old `/rate` and `/ratings/summary` stay (they serve the baseline contact sheets).

- [ ] **Step 1: Failing tests** (TestClient with the same fixture style as `tests/unit/test_scene_api.py`): list/get/404, feedback ok/422 (liked 101, tag list of 50)/404, image path outside the root is 404, dismiss, stats and search shapes, search with `"` returns 200.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement** routes and tools. **Step 4: Run** expect PASS plus `tests/unit/test_scene_api.py tests/unit/test_mcp_protocol.py`.
- [ ] **Step 5: Commit** `feat(scene): run, feedback and knowledge endpoints and MCP tools`.

### Task 7: The generation job saves the run and runs the judges (P2)

**Files:**
- Modify: `engine/original/scene_job.py`
- Test: `tests/unit/test_scene_job_review.py`

**Interfaces:**
- Consumes: Tasks 1-2 and 5; `generate_scene` result (`SceneResult`); `release_local_model`; `default_judges(provider) -> list[Judge]` (added here: `available_judges(provider, ComfyUIClient())`; when the Task 3 gate failed or `SCENE_CROSSCHECK` is not `1`, it returns only the better single judge).
- Produces: after `generate_scene`, the operation calls `scene_store.create_run(...)` (brief = `plan.brief`), then `cross_check(default_judges(provider), image_bytes, playbook.action_states, same_state=<playbook state groups>, between=release_local_model)` and `save_analysis`; a failure inside the judging is stored as `save_analysis(db, run_id, None, error=...)` and never fails the job. The job output gains `run_id`.

- [ ] **Step 1: Failing tests** (fake `generate_scene`, fake judges, temp database): `test_job_saves_a_pending_run_and_returns_its_id`, `test_job_stores_the_crosscheck_analysis`, `test_judging_failure_is_stored_and_the_job_still_succeeds`, `test_second_judge_missing_gives_single_judge_analysis` (Review Focus 1).
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS plus `tests/unit/test_scene_api.py`.
- [ ] **Step 5 (real run):** start an isolated engine (own app-data and database, as in the earlier live check), generate two scenes through the MCP tools, read `GET /runs` and `GET /runs/{id}`, look at the stored cross-check next to the pictures, record timings (picture, judges) in `docs/SCENE_DIRECTOR.md`.
- [ ] **Step 6: Commit** `feat(scene): jobs save a reviewable run with the two-judge analysis`.

### Task 8: Desktop: API client, review banner and badge (P3)

**Files:**
- Modify: `packages/api-client/src/index.ts`, `apps/desktop/src/app/AppShell.tsx`, `apps/desktop/src/app/routes.ts`
- Create: `apps/desktop/src/features/scene/sceneQueries.ts`, `apps/desktop/src/features/scene/ReviewRequestBanner.tsx`, `apps/desktop/src/features/scene/__tests__/reviewBanner.test.tsx`

**Interfaces:**
- Produces: types `SceneRun` (id, project_id, brief, scene_type, plan, status, system_review, attempts, seconds, review_state, created_at, analysis, feedback) and `SceneRunList`; `api.listSceneRuns(opts)`, `api.getSceneRun(id)`, `api.sceneRunImageUrl(id)`, `api.submitSceneFeedback(id, body)`, `api.dismissSceneRun(id)`, `api.sceneProposal(brief)`, `api.sceneCorrect(plan, corrections)`, `api.sceneGenerate(projectId, plan, seed?)`, `api.sceneKnowledgeStats()` (all through the existing private `request`). `paths.scene(runId?)` -> `/create/scene` (`?run=<id>`). `useUnreviewedCount()` (react-query, `limit=1` list request, polls every 8 s while the engine is connected) and `ReviewRequestBanner` (strong colour, `animate-pulse` like the error bell, text "N pictures are waiting for your review", link to `paths.scene(firstRunId)`, hidden on the Scene page and when the count is 0) mounted in `AppShell` above the dock, plus a count pill next to `ErrorNotificationBell`.

- [ ] **Step 1: Failing tests** (`node:test` with `mountPage`, stubbing `api.listSceneRuns`): `test_banner_shows_the_count_and_links_to_the_oldest_waiting_picture`, `test_banner_is_hidden_with_zero_waiting`, `test_banner_is_hidden_on_the_scene_page`, `test_banner_survives_a_failing_request` (no crash, hidden).
- [ ] **Step 2: Run** `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/scene/__tests__/reviewBanner.test.tsx` expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS and `cd apps/desktop && npx tsc --noEmit -p .`.
- [ ] **Step 5: Commit** `feat(desktop): review-waiting banner and badge`.

### Task 9: Desktop: the Scene page (P3)

**Files:**
- Create: `apps/desktop/src/features/scene/ScenePage.tsx`, `AiReviewPanel.tsx`, `OwnerPanel.tsx`, `sceneView.ts`, tests `apps/desktop/src/features/scene/__tests__/sceneView.test.ts` and `scenePage.test.tsx`
- Modify: `apps/desktop/src/app/router.tsx` (route `create/scene`), `apps/desktop/src/features/create/CreateIndex.tsx` (a card)

**Interfaces:**
- Consumes: Task 8's client methods and hooks; `useProjects`.
- Produces: pure helpers in `sceneView.ts`: `itemRows(crosscheck): {label, status, value, confidencePct, statusText, perJudge}[]` (labels such as "Camera angle", "People", "Person 1 action"; disputed rows show both judges' wording), `confidenceLabel(c: number): "high" | "medium" | "low"` (>=0.8 / >=0.5), `ownerCanSubmit(state): boolean` (liked chosen and either agrees or a note or a tag present), `waitingFirst(runs)`. `ScenePage`: top, a brief box, "Plan it" (calls `sceneProposal`), the plan in plain words with an angle select and a state select per actor that call `sceneCorrect`, "Draw it" (finds or creates the project titled "Scene Director" with `source_type` `CHRONOFLOW_AI`, `rights_status` `USER_OWNED`, calls `sceneGenerate`, polls the job via `api.getJob` until `SUCCEEDED`, then opens the run); middle, the picture (`sceneRunImageUrl`) and `AiReviewPanel` (per-item rows, both judges' wording, system attempts and unmet items, a "single judge" note); bottom, `OwnerPanel` (liked slider 0-100, "I agree with the AI review" toggle, tag chips good/wrong from emotion, pose, camera, identity, style, other, note box, Submit, "Dismiss"); a side queue of waiting runs. `?run=<id>` opens that run.

- [ ] **Step 1: Failing tests:** `sceneView.test.ts` (row labels, disputed row carries both wordings, confidence labels at 0.79/0.8/0.49/0.5, `ownerCanSubmit` cases); `scenePage.test.tsx` (stubbed api): `test_opening_a_run_shows_the_picture_ai_rows_and_owner_panel`, `test_submit_sends_liked_agree_tags_and_note_then_shows_thanks`, `test_submit_disabled_until_liked_and_a_reason_exist`, `test_disputed_item_is_visibly_highlighted`, `test_single_judge_note_is_shown`, `test_planning_a_brief_shows_the_plan_and_correcting_calls_the_api`, `test_draw_it_polls_the_job_and_opens_the_new_run`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement** (use `@panelflow/ui-v2` components and theme tokens; no raw colours: `apps/desktop/src/__tests__/noRawColors.test.ts` must stay green). **Step 4: Run** the feature tests, `noRawColors`, `tsc --noEmit`.
- [ ] **Step 5 (real look):** start an isolated engine (as in Task 7) and `npm run dev` for the desktop UI, open the Scene page in the built-in browser pane, plan a brief, draw it, wait for the review request, submit feedback, and take screenshots; record what was seen and what was awkward in `docs/SCENE_DIRECTOR.md`. AGENTS.md lists "opening the desktop UI in a real window" as not done: say whether the Tauri window itself was opened or only the dev server in a browser.
- [ ] **Step 6: Commit** `feat(desktop): Scene review page`.

### Task 10: Knowledge feeds the Scene Director; docs (P4)

**Files:**
- Modify: `engine/original/scene_lessons.py`, `engine/original/scene_job.py`, `engine/original/scene_store.py` (judge report), `docs/SCENE_DIRECTOR.md`, `AGENTS.md`
- Test: `tests/unit/test_scene_lessons_from_feedback.py`

**Interfaces:**
- Produces: `lessons_from_feedback(db, scene_type: str, plan: ScenePlan, min_reviews: int = 2) -> str`: for the plan's camera angle and each of its action states, a rule (the existing `CAMERA_FIX` / `POSE_FIX` texts) is returned when at least `min_reviews` reviewed runs of this scene type with the same angle or state carry the owner tag `camera` (resp. `pose`) in `wrong_tags` with `liked < 60`; a failure the system flagged but the owner liked (>= 80) never counts. `scene_job` adds this string to `lessons`. `scene_store.judge_report(db) -> dict` (per judge: items answered, disputed share, suspect-flip share; owner agreement overall and when disputed) behind `GET /knowledge/stats` under key `judges`.

- [ ] **Step 1: Failing tests:** `test_two_owner_camera_complaints_make_a_camera_lesson_for_that_angle_only`, `test_complaint_with_high_liked_does_not_count`, `test_one_complaint_is_not_enough`, `test_other_scene_type_is_not_affected`, `test_judge_report_shapes_and_none_when_empty`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement.** **Step 4: Run** expect PASS plus the whole scene suite (`tests/unit/test_scene_*.py test_judges.py test_crosscheck.py test_comfyui_launch_flags.py`).
- [ ] **Step 5:** update `docs/SCENE_DIRECTOR.md` (flow with the review page, judges, storage, how to read the knowledge base, measured results, known weaknesses) and add one bullet to `AGENTS.md` "What exists".
- [ ] **Step 6: Commit** `feat(scene): owner feedback feeds lessons; judge report; docs`.

Out of scope until asked: OS toast notifications (needs a Tauri plugin), a vector database, more than one re-look between judges, a third (detector) witness.
