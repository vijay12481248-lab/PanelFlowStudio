# Narration Compiler P4 — Studio + Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the compiler path a complete replacement for legacy narration.
- **Parity:** audio approval and BGM work, and a chapter parked in review can be finished.
- **Owner tools:** a review queue and a run inspector in Narration Studio.
- **Learning loop:** the owner's edits feed the writer's few-shot pack.
- **Rollout gate:** the default can be flipped once the gold set and the owner say so.

**Architecture:**
- Backend:
  - `engine/narration/project.py` gains audio-timeline and BGM parity.
  - `engine/narration/review.py` gains `continue_after_approval`, which runs ⑥–⑧ and the projection for an approved run.
  - A new FastAPI router, `engine/api/routers/narration.py`, exposes the queue, the inspector and the line actions. It addresses runs by `(project_id, run_id)`, never by raw paths.
- Frontend:
  - `packages/api-client` gains typed methods.
  - Narration Studio gains `NarrationReviewQueue` and `NarrationRunInspector`.
- Learning:
  - Owner edits are stored as preference pairs.
  - A CLI refreshes a user few-shot pack that the writer merges with the base pack.

**Tech Stack:** Python 3.12+, FastAPI and TestClient, SQLAlchemy, React 18 + TypeScript, and the node test runner (`npx tsx --test`, `renderToStaticMarkup`).

**Spec:** `docs/superpowers/specs/2026-10-30-narration-compiler-design.md` §6.4 (review queue), §6.5 (learning loop), §6.6 (run inspector), §7 (migration, feature flag), §10 (P4 exit). Narration code is in `engine/narration/`, main at `1a27033`.

## Global Constraints
- Legacy behaviour is unchanged while `narration_engine = "legacy"`, which stays the default in this plan. Tasks 1–6 add nothing to the legacy path.
- **Trust boundary:** every HTTP route addresses a run as `project_id` plus `run_id`.
  - The server resolves `run_dir = <project.workspace_path>/narration/<run_id>`.
  - `run_id` must match `^\d{8}T\d{6}-[0-9a-f]{6}$`.
  - The resolved path must be inside the workspace (`resolve_contained_path`).
  - Raw paths from the client are never accepted.
- Line text from the owner passes the same `rule_checks` as in P2 (`edit_line`). Blocked edits are rejected with the reasons (HTTP 400).
- Long work (approve then continue, regenerate) runs as a background job through the existing jobs pattern (`engine/api/routers/jobs.py`). Copy how autopilot starts jobs; HTTP handlers never block on models.
- Preference pairs are stored locally, as JSONL under `settings.app_data_dir / "narration_learning"`. They hold no images, only text and fact strings.
- Frontend tests use `node:test` + `renderToStaticMarkup`, the same as `apps/desktop/src/components/__tests__/autoPilotModal.test.tsx`. Each new test file is added to the root `package.json` `test` script.
- Backend tests are offline (fakes; SQLite like `tests/unit/narration/test_inputs.py`).

## Rulings made while writing this plan
- Approving a run that went to review at ⑦ voice accepts its flagged takes as they are (the owner has listened to them), then runs ⑧ and the projection. Approving a run that stopped at critique or repair runs ⑥–⑧ and the projection. Cost if wrong: a garbled take reaches the timeline if the owner didn't listen.
- BGM parity: the default BGM block legacy writes is moved into one shared helper, `default_bgm_tracks(...)`. Legacy and the compiler projection both call it, and the projection only adds it when `bgm_tracks` is empty. Cost if wrong: none; legacy output is identical.
- The learning loop covers few-shot refresh only. "Extend banned phrases from edits" (§6.5) is left out: deriving bans from free-text edits is guesswork. Cost if wrong: the owner adds banned phrases by hand (they already live in the bible).
- Flipping the default and deleting legacy (Task 8) is owner-gated. Agents prepare it and run the gate check, but the flip lands only after the owner signs off in chat. The legacy code is deleted in a later release, as §7 says.
- Bible hygiene: a proposed character whose name ends in a place word (Manor, Sect, Hall, Palace, Pavilion, Mountain, Peak, City, Falls, Valley, Temple, Clan, School) is turned into an `add_location` proposal. This was seen in a real run, where "Flying Cloud Manor" was proposed as a character. Cost if wrong: a person named like a place becomes a location the owner must fix.

## Review Focus
1. A crafted `run_id` (`..\..\x`, an absolute path, or a valid id belonging to another project) must be rejected with 400 or 404 before any file read. Test in Task 3.
2. Approving twice, or approving while a continue job is still running, must never apply the bible twice or project twice. Approve is idempotent per run. Test in Task 2.
3. The audio-timeline record written by the projection passes `approve_audio` exactly: every NARRATOR segment has a speech interval with identical text. Test in Task 1 by calling the real `approve_audio`.
4. A review queue with a corrupt or foreign `review.json` still lists the rest. Test in Task 3.
5. An owner edit that is rejected by the rules shows the reasons in the UI and leaves the line unchanged. Test in Task 5.

---

### Task 1: Audio approval and BGM parity in the projection

**Files:**
- Modify `engine/narration/project.py`.
- Modify `engine/pipeline/autopilot.py`: extract the BGM default block (around line 7406, "Ensure atmospheric background music") into `default_bgm_tracks(...)` in a new module `engine/audio/bgm_defaults.py`. Legacy calls it in place of the inline literal.
- Test: `tests/unit/narration/test_project.py`, and `tests/unit/test_bgm_defaults.py` (the legacy output is unchanged).

**Interfaces:**
- `apply_to_project(...)` also does the following:
  1. Adds an `AudioTimelineRecord(project_id, status="DRAFT", total_duration=tl.duration, timeline_json=MasterAudioTimeline(...).model_dump(), voice_casting={"Narrator": voice})`.
     - It has one `AudioInterval(script_segment_id=<segment id>, text=<line text>, start_time, end_time, is_speech=True, audio_file_uri=<same relative path legacy uses>)` per line.
     - Check how legacy fills `audio_file_uri` in `engine/audio/service.py`, around line 280–300.
  2. Writes the same JSON sidecar legacy writes (`audio/master_audio_timeline.json`, via `write_contained_json`).
  3. Sets `bgm_tracks` to `default_bgm_tracks(...)` when the existing list is empty.
  4. Sets `project.current_stage = PipelineStage.VOICE_GENERATED.value`.
- `default_bgm_tracks(...)` returns exactly what legacy inlines today. Its signature follows the values the legacy block reads.

- [ ] **Step 1:** Write failing tests:
  - `test_projection_audio_timeline_passes_real_approve_audio` (call `AudioService().approve_audio(db, pid)` and expect True)
  - `test_projection_adds_default_bgm_only_when_empty`
  - `test_projection_sets_voice_generated_stage`
  - `test_default_bgm_tracks_matches_legacy_literal`
- [ ] **Steps 2–4:** RED, implement, GREEN. Run `tests/unit/narration` plus the new test, then `tests/unit` once.
- [ ] **Step 5:** Commit `feat(narration): projection writes an approvable audio timeline and default BGM`.

### Task 2: Finish a reviewed chapter

**Files:** Modify `engine/narration/review.py` and `engine/narration/compiler.py`. Test `tests/unit/narration/test_review.py`.

**Interfaces:**
- `NarrationCompiler.continue_run(run_dir: Path, inputs: ChapterInputs, workspace: Path) -> CompileResult`:
  - Loads `script.json`, `beat_sheet.json`, `panel_facts.json` and the bible from the run.
  - Runs ⑥ perform, then releases the LLM, then ⑦ voice, then ⑧ timeline.
  - Appends these steps to the run's `run.json`.
  - If `takes.json` exists and the review came from voice, re-uses the takes and clears their `flagged` flag (ruling above) instead of re-voicing.
- `review.approve(run_dir, bibles)` keeps its current checks and bible apply, and also returns `needs_continue: bool`. That is True unless `timeline.json` already exists.
- `async continue_after_approval(project_id: str, run_id: str) -> str`:
  - Resolves the run, calls `continue_run`, then `apply_to_project`, and returns the VideoScript id.
  - It is idempotent: it writes `<run_dir>/continued.json` (VideoScript id) at the end. A second call returns the stored id without work.
  - A per-run lock file (`continue.lock`, created exclusively) makes a concurrent second call raise `ValueError("continue already running")`.
- CLI: `python -m engine.narration review approve <run_dir>` runs the continue step after a successful approve and prints the VideoScript id.

- [ ] **Step 1:** Write failing tests with fakes:
  - `test_continue_after_critique_review_runs_perform_voice_timeline`
  - `test_continue_after_voice_review_reuses_takes_unflagged`
  - `test_continue_is_idempotent`
  - `test_concurrent_continue_rejected`
  - `test_approve_reports_needs_continue`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): approved review runs finish through voice, timeline and projection`.

### Task 3: Narration HTTP routes

**Files:** Create `engine/api/routers/narration.py`, register it in `engine/api/app.py`. Test `tests/unit/narration/test_api.py` (FastAPI `TestClient`; follow an existing router test under `tests/unit` that uses TestClient and the DB dependency override).

**Interfaces (prefix `/api/narration`):**
- `GET /review`: `[{project_id, project_title, run_id, reasons, line_ids, created}]`. Pending only, newest first, and corrupt files are skipped.
- `GET /runs/{project_id}`: that project's runs, newest first: `[{run_id, gate, created, steps: [{step, status, seconds, model_calls}]}]`, read from `run.json`.
- `GET /runs/{project_id}/{run_id}`: inspector payload, with these fields:
  - `run` (run.json)
  - `lines: [{line_id, panel_id, text, status, kind, checks: [{rule, passed, severity, reason}], facts: <panel_line text>, take: {wer, flagged, stt_text} | null}]`
  - `beat_sheet: {hook, chapter_summary, scenes: [{scene_id, goal, first_panel_id, last_panel_id}]}`
  - `review: ReviewItem | null`
- `POST /runs/{project_id}/{run_id}/lines/{line_id}`, body `{action: "accept"|"edit"|"fallback"|"regenerate", text?: str, hint?: str}`:
  - accept, edit and fallback are synchronous and return the updated line.
  - regenerate starts a job and returns `{job_id}`.
  - A `ValueError` from the review functions becomes 400 with the message.
- `POST /runs/{project_id}/{run_id}/approve`: runs `review.approve`, then (if `needs_continue`) starts a `continue_after_approval` job. Returns `{bible_version, job_id | null}`.
- Run resolution follows the Global Constraints. Unknown project gives 404, a bad `run_id` format gives 400, a missing run gives 404.

- [ ] **Step 1:** Write failing tests:
  - `test_review_list_skips_corrupt`
  - `test_run_id_traversal_rejected` (cases: `..%5C..%5Cx`, `C:\x`, wrong format; a valid id of a different project gives 404)
  - `test_inspector_payload_shape`
  - `test_edit_rejected_by_rules_is_400_and_unchanged`
  - `test_approve_starts_continue_job` (job runner stubbed)
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): review queue and run inspector API`.

### Task 4: API client methods

**Files:** Modify `packages/api-client/src/index.ts`; add types to `packages/shared-types` if that is where response types live (check how `AudioTimelineResponse` is defined and follow it). Test `packages/api-client/src/narration.test.ts` (node:test, stub `fetch`, follow `history.test.ts`), and add it to the root `test` script.

**Interfaces:**
- `listNarrationReview()`
- `listNarrationRuns(projectId)`
- `getNarrationRun(projectId, runId)`
- `narrationLineAction(projectId, runId, lineId, body)`
- `approveNarrationRun(projectId, runId)`

Each uses `this.request<T>(...)`, the same as `getAudioTimeline`. The types mirror Task 3's JSON exactly.

- [ ] **Steps 1–4:** Write failing tests (method hits the right URL and method, sends the right body, and parses the result), then RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(api-client): narration review and inspector methods`.

### Task 5: Review queue and run inspector UI

**Files:**
- Create `apps/desktop/src/components/narration-studio/NarrationReviewQueue.tsx` and `NarrationRunInspector.tsx`.
- Modify `NarrationStudio.tsx` to add two tabs, "Review queue" and "Run inspector", following its existing tab pattern.
- Test `apps/desktop/src/components/narration-studio/__tests__/narrationReview.test.tsx`, and add it to the root `test` script.

**Behaviour:**
- **Queue:**
  - Groups pending runs by project and shows each run's reasons.
  - Selecting a run shows its blocked or fallback lines.
  - Each line shows the panel image (`api.getPanelImageUrl(projectId, panelId)`), the line text, the failed checks with severity and reason, and the facts string.
  - Actions per line: Accept, Edit (inline textarea; the server's 400 reasons are shown under it and the text stays unchanged), Fallback, and Regenerate with a hint (shows "regenerating…" until the job completes; reuse the app's existing job-polling helper).
  - An "Approve chapter" button is enabled only when no line is blocked, and shows the continue job's progress.
- **Inspector:**
  - Pick a project, then a run.
  - A steps table (step, status, seconds, model calls).
  - A line table with every line, its status and checks; click to expand facts and the take (WER, heard text).
- Use the existing `@panelflow/ui` components (`Button`, `Icons`, `ProgressBar`) and Tailwind classes the same way the neighbouring narration-studio components do. Every control has an accessible label.

- [ ] **Step 1:** Write failing tests (`renderToStaticMarkup` with prop-injected data, no network):
  - `review queue lists reasons and failing checks`
  - `approve disabled while a line is blocked`
  - `edit error shows server reasons`
  - `inspector renders steps and lines`
- [ ] **Steps 2–4:** RED, implement, GREEN. Run the root `npm test` and `npx tsc -p apps/desktop` (or the app's `tsc` step) clean.
- [ ] **Step 5:** Commit `feat(desktop): narration review queue and run inspector`.

### Task 6: Learning loop

**Files:** Create `engine/narration/learning.py`. Modify `engine/narration/review.py` (record pairs), `steps/write.py` (merge the user pack) and `__main__.py` (CLI). Test `tests/unit/narration/test_learning.py`.

**Interfaces:**
- `record_pair(kind: Literal["edit","regenerate"], before: str, after: str, facts: str, reasons: list[str]) -> None` appends one JSON line to `learning_root() / "pairs.jsonl"`, where `learning_root() = settings.app_data_dir / "narration_learning"`.
  - Called by `edit_line` and by `regenerate_line` (when the result is not `needs_review`).
- `refresh_fewshot(min_pairs: int = 5, max_rows: int = 10) -> Path | None`:
  - Builds `learning_root()/"fewshot_user.jsonl"` from the newest pairs whose `after` is 5–10 words and has no banned phrase, as `{"facts", "line": after}` rows, deduped by line.
  - Returns None when fewer than `min_pairs` usable pairs exist.
- In `write.py`, `load_fewshot()` merges the user pack's rows (if the file exists) in front of the base pack. The prompt keeps 6 rows. Including the user rows changes the prompt hash, which is expected.
- CLI: `python -m engine.narration fewshot refresh` prints the path or "not enough edits yet (<n>/5)".
- Bible hygiene (ruling): in `understand._proposals`, a new character whose last word is in the place-word set becomes `BibleProposal(kind="add_location", payload={"id": "l_<n>", "name": name})`.

- [ ] **Step 1:** Write failing tests (tmp app dir via monkeypatch):
  - `test_edit_records_pair`
  - `test_refresh_needs_min_pairs`
  - `test_refresh_filters_and_dedupes`
  - `test_write_prompt_uses_user_rows_first`
  - `test_place_named_character_becomes_location`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): owner edits feed the few-shot pack; places are not characters`.

### Task 7: Exit check

**Files:** none, unless a defect is found.

- [ ] **Step 1:** With `PANELFLOW_NARRATION_ENGINE=compiler`, run autopilot on Ch927 and TDG 536.1. Then approve audio through the real API route (`POST /api/projects/{id}/audio/approve`). It must succeed, and the render has BGM.
- [ ] **Step 2:** Force one chapter into review (e.g. a temporary banned phrase in its bible). Then, through the API, edit or accept its lines and approve. The continue job finishes, and a render succeeds.
- [ ] **Step 3:** Open Narration Studio in the dev app. The review queue and inspector load real runs, and Edit shows rule rejections.
- [ ] **Step 4:** Make 5 owner edits, run `fewshot refresh`, and re-run write on one chapter. The prompt contains the user rows.

### Task 8: Rollout gate (owner-gated; agents prepare, the owner decides)

**Files:** none until the owner signs off.

- [ ] **Step 1:** Run `narration eval` on the gold set (at least 3 chapters; add one more real chapter with `gold add` first). Report grounded, coverage, invented names and preference against legacy.
- [ ] **Step 2:** If preference ≥ 55 % and the owner approves in chat, change the `narration_engine` default to `"compiler"` in `engine/config/settings.py`, run `tests/unit` once, and commit `feat(narration): compiler becomes the default narration engine`. Otherwise stop and report.
- [ ] **Step 3:** Leave legacy code in place. Its removal is a follow-up release task (§7: "legacy deleted one release later").
