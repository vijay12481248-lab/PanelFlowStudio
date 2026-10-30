# Narration Compiler P2 — Write + Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn P1's PanelFacts + BeatSheet into a grounded, critiqued and repaired ScriptIR (one line per story panel), with a review-queue backend, a gold set and a `narration eval` command.

**Architecture:** Three new compiler steps follow ② UNDERSTAND: ③ WRITE (per scene, role `writer`), ④ CRITIQUE (code rules plus yes/no judges, role `judge`) and ⑤ REPAIR (failed lines only, at most 2 rounds, then code-built fallback). The flow is the same as P1: typed artifacts, the content-addressed cache, prompts as versioned assets, and the model scheduler. A failing gate parks the run in a file-based review queue. A passing run applies its bible proposals.

**Tech Stack:** Python 3.12+, Pydantic v2, local Ollama via `ProviderModelClient`, pytest (offline, `FakeModelClient`), stdlib `difflib` and `html`.

**Spec:** `docs/superpowers/specs/2026-10-30-narration-compiler-design.md` (§3.4–3.5, §4.3–4.5, §6.1–6.4, §8–10). P1 code: `engine/narration/` (merged at `b2ab63f`).

## Global Constraints
- Local models only. Every model call goes through `ModelClient.structured(role, prompt, schema)`; nothing in `engine/narration/` calls a cloud provider.
- Every model call is JSON-schema constrained and Pydantic-validated, with one retry carrying the validation error, then `StepModelError`. Never substitute placeholder or canned text. The only non-model text allowed is the §4.5 fact-only fallback built from PanelFacts.
- Steps ③–⑤ use only facts from PanelFacts, BeatSheet and SeriesBible ("facts flow forward only").
- Exactly one ScriptIR line per story panel, in reading order.
- Every prompt passes `guard_prompt(client, role, text)` before the call. No prompt may exceed `num_ctx` (8192); ③ is per scene, so a scene over budget is split into chunks of at most 30 panels.
- Role params come from `narration_models.yaml`: `writer` temperature 0.7, top_p 0.9; `judge` temperature 0. The provider must actually receive `top_p` for the writer (P1 deferred this). Send it in `ProviderModelClient.structured` the same way `num_ctx`/`temperature` are sent.
- One heavy model loaded at a time. Work is grouped by role through `ModelScheduler.map`: all writer calls, then all judge calls, then repair (writer), and so on.
- Artifacts are JSON written with `ensure_ascii=False`, atomically (temp file plus `os.replace`). Cached through `ArtifactCache` with `cache_key(step, inputs, prompt_sha, model, params)`.
- Tests are offline: no Ollama, no GPU. Async code is tested with `asyncio.run(...)` inside sync tests.
- Prompt files live at `engine/narration/prompts/<step>/v1.md` and are LF-normalised (P1 `.gitattributes`).
- Gold-set chapters contain third-party manga images, so they live outside the repo under `settings.app_data_dir / "narration_gold"`. The repo carries only a tiny synthetic fixture for tests.

## Rulings made while writing this plan (spec gaps)
- Hook and cliffhanger are not extra lines. The hook is the line for the first story panel (`kind="hook"`) and the cliffhanger is the line for the last (`kind="cliffhanger"`). Each is chosen from 3 candidates by pairwise judging. This keeps "one line per story panel" exact. Cost if wrong: an opening line that must also describe panel 1.
- The word budget targets 5–10 words, but the `block` rule fires only outside 4–12 words. Small models drift ±2 words, and a 2-word miss is a pacing issue, not an error. Cost if wrong: slightly uneven pace.
- Effective review threshold: after 2 repair rounds every still-failing line becomes a fallback, and the chapter goes to review when fallbacks are more than 10 % of lines. §4.5's 10 % is stricter than §4.4's 15 %, so it decides. Cost if wrong: more chapters reach review.
- "Auto with review queue": a run whose gate is `pass` counts as approved and applies its bible proposals at once. Cost if wrong: small-model character proposals enter the bible unreviewed until the P4 review UI.
- P2 builds the review-queue backend as a Python service plus CLI commands. The HTTP routes ship with the P4 UI that calls them. Cost if wrong: P4 adds a thin router.
- Preference in eval is measured against each gold chapter's reference script (the legacy production script captured when the chapter was added), judged pairwise per scene in both orders.

## Review Focus
1. **A scene longer than 30 panels, or one whose facts exceed the prompt budget.** It must be chunked and still produce exactly one line per panel. Test in Task 4.
2. **A writer answer with a missing, extra, duplicated or out-of-order panel number.** One re-ask, then `NeedsReview`; never silently padded. Test in Task 4.
3. **Names in a line that appear in neither the bible nor the OCR** (e.g. the model "names" a stranger). Must be a `block` failure, and must not fire on sentence-initial words or common words. Test in Task 5.
4. **A line whose panel's character is `unknown_<n>` when it reaches fallback.** The fallback must not print the raw label. Test in Task 7.
5. **Re-running a chapter after a crash.** Write, critique and repair results all come from the cache, with zero model calls on the second run. Test in Task 8.

---

### Task 1: Script and critique artifacts, series-key widening

**Files:**
- Modify: `engine/narration/artifacts.py`
- Modify: `engine/narration/bible/store.py` (`series_key_for`)
- Test: `tests/unit/narration/test_artifacts.py`, `tests/unit/narration/test_bible_store.py`

**Interfaces:**
- Produces (all `_Strict`):
  - `LineKind = Literal["hook", "narration", "paraphrase", "transition", "cliffhanger"]`
  - `LineStatus = Literal["draft", "passed", "repaired", "fallback", "needs_review"]`
  - `ScriptLine(line_id: str, panel_id: str, text: str, facts_used: list[str], kind: LineKind, target_words: int = 8, status: LineStatus = "draft")`. `text` must be non-blank. `facts_used` items must match `^(action|emotion|dialogue|characters|setting|sfx|beat:[A-Za-z0-9_-]+)$`.
  - `ScriptIR(project_id: str, revision: int = 0, parent_revision: int | None = None, changed_line_ids: list[str] = [], lines: list[ScriptLine] (min 1))`. Validator: `line_id`s are unique.
  - `LineCheck(rule: str, passed: bool, severity: Literal["block", "warn"], reason: str = "")`
  - `LineCritique(line_id: str, checks: list[LineCheck], scores: dict[str, bool] = {})`, where the score keys are a subset of `grounded`, `clear`, `voice`, `flow`. Property `blocked -> bool` (any failed block check).
  - `CritiqueReport(revision: int, lines: list[LineCritique], coverage: float, pace_estimate: float, repetition: int, gate: Literal["pass", "repair", "review"], gate_reasons: list[str] = [])`
  - `check_script_ids(script: ScriptIR, story_panel_ids: list[str]) -> list[str]` returns problem strings: count mismatch, order mismatch, unknown panel id.
- `series_key_for`: also split on a trailing chapter marker. `re.split(r"\s*[-–:|]?\s*\b(?:chapter|ch\.?|episode|ep\.?)\s*\d", title, flags=re.I)[0]`, applied when no `series_title` is given.

- [ ] **Step 1: Write the failing tests**
  - `test_script_line_rejects_bad_fact_ref`: `facts_used=["vibes"]` raises `ValidationError`.
  - `test_script_ir_rejects_duplicate_line_ids`
  - `test_check_script_ids_reports_order_and_count`: story ids `[a, b, c]` against lines for `[a, c]` gives one count problem; lines for `[b, a, c]` give one order problem; a line for `z` gives an unknown-id problem.
  - `test_critique_blocked_property`: one failed `warn` gives `blocked` False; one failed `block` gives True.
  - `test_series_key_for_chapter_variants`, parametrized:
    - `"Magic Emperor Chapter 927"` → `magic-emperor`
    - `"Magic Emperor - Ch. 12"` → `magic-emperor`
    - `"Log Into The Future Episode 5"` → `log-into-the-future`
    - `"Solo Leveling"` → `solo-leveling`
    - `"Return of the Mount Hua Sect - chapter 3"` → `return-of-the-mount-hua-sect`
- [ ] **Step 2: Run them and see them fail.** `& .venv\Scripts\python.exe -m pytest tests/unit/narration/test_artifacts.py tests/unit/narration/test_bible_store.py -v -p no:cacheprovider`
- [ ] **Step 3: Implement the models and `check_script_ids`, and widen `series_key_for`.**
- [ ] **Step 4: Run `tests/unit/narration` in full; all pass.**
- [ ] **Step 5: Commit** `feat(narration): ScriptIR and CritiqueReport artifacts; series key ignores chapter markers`

### Task 2: Send `top_p` to the provider

**Files:**
- Modify: `engine/narration/runtime/client.py`; `engine/llm/providers/ollama.py` only if the text path drops `top_p`
- Test: `tests/unit/narration/test_runtime_client.py`

**Interfaces:**
- `ProviderModelClient.structured` passes `top_p=role.top_p` whenever the role config sets it, on the text path. `params_for(role)` includes `top_p` when set, so it is part of the cache key.

- [ ] **Step 1: Write the failing test.** `test_writer_top_p_reaches_provider`: a recording provider sees `top_p == 0.9` for role `writer`, and no `top_p` for `planner` (unset).
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Implement.** If `RoleConfig` lacks `top_p: float | None = None`, add it. Check that `narration_models.yaml` sets `top_p: 0.9` for the writer.
- [ ] **Step 4: Run `tests/unit/narration` and `tests/unit/test_ollama*` (if present); all pass.**
- [ ] **Step 5: Commit** `fix(narration): writer top_p reaches the provider`

### Task 3: Few-shot pack and compact fact view

**Files:**
- Create: `engine/narration/fewshot/recap_v1.jsonl` (8 lines)
- Create: `engine/narration/steps/factview.py`
- Test: `tests/unit/narration/test_factview.py`

**Interfaces:**
- `load_fewshot(pack: str = "recap_v1") -> list[dict]`: each row is `{"facts": str, "line": str}`. Raises `ValueError` on a row missing either key.
- `panel_line(k: int, f: PanelFacts, names: dict[str, str]) -> str`: compact one-line facts for prompts. The format is `P{k} | chars: {names or '-'} | action: {action} | emotion: {emotion} | said: {dialogue joined ' / ' or '-'} | sfx: {sfx or '-'}`. `unknown_<n>` ids render as `a stranger`, never the raw label.
- `display_name(char_id: str, names: dict[str, str]) -> str`: the bible name, or `"a stranger"` for `unknown_*`, or the id itself as a last resort.
- The few-shot rows are original recap-style lines written for this pack: 5–10 words, present tense, third person, paraphrased dialogue, no "in this panel". Example row: `{"facts": "chars: Kai | action: Kai blocks a sword strike with his forearm | said: You're too slow", "line": "Kai catches the blade bare-handed and mocks his attacker's speed."}`

- [ ] **Step 1: Write the failing tests.**
  - `test_fewshot_rows_valid`: 8 rows, each line 5–10 words, no row containing "panel".
  - `test_panel_line_hides_unknown_labels`: the output contains `a stranger` and not `unknown_1`.
  - `test_panel_line_dialogue_verbatim`: OCR text appears unchanged.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement and write the pack.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): recap few-shot pack and compact fact view`

### Task 4: ③ WRITE

**Files:**
- Create: `engine/narration/steps/write.py`
- Create: `engine/narration/prompts/write_scene/v1.md`, `engine/narration/prompts/write_candidates/v1.md`
- Test: `tests/unit/narration/test_write.py`

**Interfaces:**
- Consumes: `PanelFacts`, `BeatSheet`, `SeriesBible`, `ModelClient`, `ModelScheduler`, `ArtifactCache`, `cache_key`, `load_prompt`, `guard_prompt`, `NeedsReview` (from `steps/understand.py`), `panel_line`, `load_fewshot`.
- Produces:
  - `WRITE_PROMPT_VERSION = "v1"`, `SCENE_STEP = "write_scene"`, `CANDIDATE_STEP = "write_candidates"`
  - Draft schemas (not artifacts):
    - `LineDraft(panel: int, text: str, facts_used: list[str], kind: Literal["narration", "paraphrase", "transition"])`
    - `SceneLinesDraft(lines: list[LineDraft])`
    - `CandidatesDraft(candidates: list[str])` (exactly 3)
  - `async write_chapter(project_id, facts, sheet, bible, client, scheduler, cache) -> tuple[ScriptIR, dict[str, list[str]]]`. Returns revision 0, all statuses `draft`, `line_id = f"L{k:03d}"` in story order, plus candidates `{"hook": [3 texts], "cliffhanger": [3 texts]}`.
- **Behaviour:**
  - Write one prompt per scene; a scene with more than 30 panels is split into consecutive chunks of at most 30.
  - Each prompt gets:
    - the scene goal and turn
    - its beats as `beat:<id> P{a}-P{b}: what_happens`
    - its panels via `panel_line` (P-numbers local to the chunk, starting at 1)
    - the last 3 written lines of the previous chunk (none for the first)
    - bible `narrator_voice.style_notes` and `banned_phrases`
    - 6 few-shot rows
    - the rules: "exactly N lines, one per P-number in order, 5–10 words each, paraphrase dialogue, never quote, never mention panels or images"
  - Calls go through `scheduler.map("writer", prompts, ...)` with the cache, as in `understand.cached`.
  - Map P-numbers back to panel ids. Run `check_script_ids` on the chunk. On problems, one re-ask with `"\n\nFix these problems: ..."` appended (cached under its own text); still wrong raises `NeedsReview([...])`.
  - Hook: one `write_candidates` call with the first story panel's facts plus `sheet.hook` gives 3 candidates. Cliffhanger: the same with the last panel plus the final scene turn. Candidates are not chosen here (④ picks).

- [ ] **Step 1: Write the failing tests** (FakeModelClient scripted answers):
  - `test_one_line_per_story_panel_in_order`: 2 scenes, 7 story panels, plus 1 non-story panel that gets no line.
  - `test_scene_over_30_panels_is_chunked`: 65-panel scene gives 3 writer calls and 65 lines; the second prompt contains the last 3 lines of the first chunk.
  - `test_missing_panel_reasks_once_then_review`: first answer skips P2 and triggers a re-ask; the re-ask also skips it, giving `NeedsReview`.
  - `test_reask_fixes_answer`: the re-ask answer is accepted; 2 calls in total.
  - `test_candidates_three_each`
  - `test_rerun_uses_cache`: the second run makes zero model calls.
  - `test_prompt_over_budget_fails_loud`: a tiny `num_ctx` gives `StepModelError`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement `write.py` and the two prompts.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): ③ WRITE one grounded line per story panel`

### Task 5: ④ CRITIQUE — rule checks

**Files:**
- Create: `engine/narration/steps/critique/__init__.py`, `engine/narration/steps/critique/rules.py`
- Test: `tests/unit/narration/test_critique_rules.py`

**Interfaces:**
- `DEFAULT_BANNED = ("in this panel", "the image shows", "in the image", "we see", "this scene shows", "the panel shows")`
- `rule_checks(script: ScriptIR, facts: dict[str, PanelFacts], story_ids: list[str], bible: SeriesBible) -> dict[str, list[LineCheck]]`, keyed by `line_id`. Rule names:
  - `order` (block): applied to every line when `check_script_ids` reports anything.
  - `word_budget` (block): words < 4 or > 12.
  - `banned_phrase` (block): case-insensitive, `DEFAULT_BANNED` plus bible banned phrases.
  - `unknown_name` (block): a capitalised token that is not sentence-initial and not after `"` / `—`, and is not in bible names, aliases or glossary keys, chapter OCR words (case-insensitive) or the stopword set (`I`, `I'm`, days, months).
  - `raw_unknown_label` (block): matches `unknown_\d+`.
  - `repeated_opener` (warn): same first word (lowercased) as either of the 2 previous lines.
  - `similar_to_previous` (warn): `difflib.SequenceMatcher(None, a, b).ratio() > 0.8`.
- `chapter_stats(script) -> tuple[float, int]`: `pace_estimate` (mean words per line ÷ 2.75 words/s, i.e. seconds per line) and `repetition` (count of warn failures).

- [ ] **Step 1: Write the failing tests**, one per rule: a pass case and a fail case each.
  - `test_unknown_name_ignores_sentence_start_and_ocr_names`: "Kai strikes. Then Ryu falls." with bible `Kai` and OCR "Ryu!" gives a pass. "Kai faces Zorath." gives a fail on `Zorath`.
  - `test_warn_rules_do_not_block`
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): ④ critique rule checks`

### Task 6: ④ CRITIQUE — judges, pairwise picking, gate

**Files:**
- Create: `engine/narration/steps/critique/judges.py`
- Create: prompts `critique_grounded/v1.md`, `critique_clear/v1.md`, `critique_voice/v1.md`, `critique_flow/v1.md`, `critique_pair/v1.md`
- Test: `tests/unit/narration/test_critique_judges.py`

**Interfaces:**
- `CRITIQUE_PROMPT_VERSION = "v1"`. Drafts: `Verdict(yes: bool, reason: str)` and `PairVerdict(winner: Literal["A", "B"], reason: str)`.
- `async judge_lines(script, line_ids: list[str] | None, facts, sheet, bible, client, scheduler, cache) -> dict[str, list[LineCheck]]`. For each selected line (None means all), run 4 judge calls, all with role `judge`:
  - **grounded:** sees only the line, its panel's `panel_line` and the beat `what_happens`.
  - **clear:** sees only the line and the previous line.
  - **voice:** sees only the line and the style notes.
  - **flow:** sees only the previous line and the line.

  Each gives `LineCheck(rule=<name>, passed=yes, severity="block", reason=reason)`.
- `async pick_best(kind: str, candidates: list[str], context: str, client, scheduler, cache) -> str`. Judge every pair in both orders (A/B and B/A); a win scores 1; the highest total wins; a tie goes to the earlier candidate.
- `async critique(script, facts, story_ids, sheet, bible, client, scheduler, cache, line_ids=None) -> CritiqueReport`:
  - Merges rule checks and judge checks.
  - `scores` holds the four judge booleans.
  - `coverage` is the share of story panels that have a line with status other than `fallback`/`needs_review`.
  - `gate` is `repair` if any line is blocked, else `pass`. `review` is decided by the repair loop (Task 7), not here.
  - When `line_ids` is given, only those lines are re-judged. The remaining lines keep their previous checks, so the caller passes `previous: CritiqueReport | None`; add that parameter.

- [ ] **Step 1: Write the failing tests.**
  - `test_judge_sees_only_its_inputs`: the grounded prompt contains the panel facts and not other panels' facts.
  - `test_pairwise_runs_both_orders`: 3 candidates give 6 judge calls; a position-biased fake that always answers "A" ends in a tie, so the first candidate wins.
  - `test_gate_repair_when_any_block_fails`
  - `test_rejudge_only_changed_lines`: `line_ids=["L002"]` gives exactly 4 judge calls; the other lines are copied from `previous`.
  - `test_judge_cache_rerun_zero_calls`
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): ④ critique judges, pairwise picking and gate`

### Task 7: ⑤ REPAIR and fallback

**Files:**
- Create: `engine/narration/steps/repair.py`, prompt `repair_line/v1.md`
- Test: `tests/unit/narration/test_repair.py`

**Interfaces:**
- `REPAIR_PROMPT_VERSION = "v1"`, `MAX_ROUNDS = 2`, `FALLBACK_LIMIT = 0.10`. Draft: `RepairDraft(text: str, facts_used: list[str])`.
- `fallback_text(f: PanelFacts, names: dict[str, str]) -> str`: the panel's `action` with every character id replaced by `display_name`. Cap it at 12 words and end it with a full stop.
- `async repair_loop(script, report, facts, story_ids, sheet, bible, client, scheduler, cache) -> RepairResult`, where `RepairResult` is a dataclass with `script: ScriptIR` (final), `report: CritiqueReport`, `gate: Literal["pass", "review"]`, `reasons: list[str]` and `revisions: list[ScriptIR]` (every revision written, in order):
  - Each round, for each blocked line, run one writer call with:
    - the original line
    - its failed checks with their reasons
    - its `panel_line`
    - the previous and next lines

    Then:
    - Write a new `ScriptIR` revision (`revision + 1`, `parent_revision`, `changed_line_ids`), with those lines set to `status="repaired"`.
    - Call `critique(..., line_ids=changed, previous=report)`.
  - Stop when nothing is blocked or after `MAX_ROUNDS`.
  - Every line still blocked becomes `fallback_text` with `status="fallback"`, `facts_used=["action", "characters"]`, in one more revision.
  - Lines that pass end as `passed`, or stay `repaired` if they were repaired.
  - The gate is `review` when the fallback share is more than `FALLBACK_LIMIT`, with the reason `"<n> of <m> lines fell back to facts"`; otherwise `pass`.
  - The compiler (Task 8) writes each entry of `revisions` to the run directory.

- [ ] **Step 1: Write the failing tests.**
  - `test_repair_fixes_line_in_one_round`: 2 revisions; `changed_line_ids == ["L002"]`; status `repaired`.
  - `test_two_rounds_then_fallback`
  - `test_fallback_hides_unknown_label`: the action "unknown_1 lunges at Kai" becomes "a stranger lunges at Kai." (first word capitalised: "A stranger…").
  - `test_too_many_fallbacks_goes_to_review`: 2 of 10 lines fall back, giving `review`; 1 of 10 gives `pass`.
  - `test_repair_rejudges_only_changed_lines`
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): ⑤ repair loop with fact-only fallback`

### Task 8: Compiler and CLI wiring

**Files:**
- Modify: `engine/narration/compiler.py`, `engine/narration/__main__.py`
- Test: `tests/unit/narration/test_compiler.py`, `tests/unit/narration/test_main.py`

**Interfaces:**
- `NarrationCompiler.run(..., stop_after: Literal["perceive", "understand", "write"] = "write")`. `"write"` runs ③④⑤. The steps are recorded in `run.json` as `write`, `critique` and `repair` via `_recorded`. Critique and repair record the `judge` and `writer` models.
- After ④, `pick_best` replaces the first line's text with the chosen hook candidate (`kind="hook"`) and the last line's text with the chosen cliffhanger (`kind="cliffhanger"`). Both lines are then re-critiqued with `line_ids`.
- Run-dir files: `script_r<rev>.json` for every revision, `critique.json` (final) and `script.json` (final).
- `CompileResult` gains `script: ScriptIR | None` and `critique: CritiqueReport | None`.
- Gate: a repair-loop `review` becomes `result("review", reasons)`. On `pass`, apply the bible proposals: `bible2, applied = apply_proposals(bible, sheet.bible_proposals)`, then `self.bibles.save(bible2, inputs.project_id, applied)` when `applied` is non-empty.
- CLI: `--stop-after` choices `perceive|understand|write` (default `write`), and it prints `lines: <n>`, `fallbacks: <n>` and `coverage: <x.xx>`.

- [ ] **Step 1: Write the failing tests.**
  - `test_full_run_pass_writes_artifacts_and_applies_bible`
  - `test_review_gate_parks_without_bible_update`
  - `test_rerun_after_crash_zero_model_calls`: run, then run again with the same cache gives `model_calls == 0` for write, critique and repair in `run.json`.
  - `test_cli_prints_line_stats`
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): compile through write, critique and repair`

### Task 9: Review-queue backend

**Files:**
- Create: `engine/narration/review.py`
- Modify: `engine/narration/__main__.py` (subcommands)
- Test: `tests/unit/narration/test_review.py`

**Interfaces:**
- `ReviewItem(_Strict)`: `run_id`, `project_id`, `run_dir: str`, `reasons: list[str]`, `line_ids: list[str]` (lines blocked or fallback), `status: Literal["pending", "approved"]`. It is written by the compiler as `<run_dir>/review.json` whenever the gate is `review` (add that to the compiler in this task).
- `list_pending(projects_root: Path) -> list[ReviewItem]`: globs `*/narration/*/review.json` and keeps `status == "pending"`, newest first.
- `edit_line(run_dir: Path, line_id: str, text: str) -> ScriptIR`: new revision, status `passed`, `facts_used` kept. Still runs `rule_checks` on that line; a failing block rule raises `ValueError` with the reasons.
- `accept_line(run_dir, line_id) -> ScriptIR`: status `passed`, no text change.
- `fallback_line(run_dir, line_id) -> ScriptIR`: uses `fallback_text`.
- `async regenerate_line(run_dir, line_id, hint: str, client, scheduler, cache) -> ScriptIR`: one repair call with the hint appended to the reasons, status `repaired`.
- `approve(run_dir: Path, bibles: BibleStore) -> SeriesBible`: requires every line `status in {passed, repaired, fallback}`. Applies the beat sheet's proposals, writes `script.json`, and sets `review.json` `status="approved"`.
- CLI: `python -m engine.narration review list` and `python -m engine.narration review approve <run_dir>`.

- [ ] **Step 1: Write the failing tests.**
  - `test_review_json_written_on_review_gate`
  - `test_list_pending_skips_approved`
  - `test_edit_line_rejects_banned_phrase`
  - `test_edit_creates_new_revision_with_lineage`
  - `test_approve_applies_bible_once`: approving twice raises `ValueError` and the bible version rises by 1.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): review-queue backend and CLI`

### Task 10: Gold set and `narration eval`

**Files:**
- Create: `engine/narration/eval/__init__.py`, `engine/narration/eval/gold.py`, `engine/narration/eval/metrics.py`, `engine/narration/eval/report.py`
- Create: prompt `eval_pair/v1.md`
- Modify: `engine/narration/__main__.py`, `engine/narration/inputs.py` (`dump_chapter_inputs`, `load_chapter_inputs_from_dir`)
- Create: `tests/fixtures/narration_gold_mini/` (3 synthetic panels as tiny PNGs, `inputs.json`, `facts.json`, `reference.json`)
- Test: `tests/unit/narration/test_eval.py`

**Interfaces:**
- Gold directory: `gold_root() = settings.app_data_dir / "narration_gold"`. Per chapter `<slug>/` contains:
  - `inputs.json` (ChapterInputs with image paths relative to `<slug>/panels/`)
  - `panels/*.png`
  - `facts.json` (PanelFacts to hand-correct, starting as a copy of the run's facts)
  - `reference.json` (`{"lines": [{"panel_id", "text"}]}` from the project's current legacy `VideoScript`)
  - `meta.json` (`{"slug", "project_id", "kind": "manhua|manhwa|webtoon", "frozen": false}`)
- `add_gold(project_id: str, slug: str) -> Path`: CLI `narration gold add <project_id> <slug>`. Copies the panel images, dumps the inputs, takes facts from the newest run and the legacy script lines. Refuses an existing slug.
- `async run_eval(slugs: list[str] | None, compiler_factory) -> EvalReport`. Per chapter:
  - Run the compiler from `load_chapter_inputs_from_dir`, seeding the cache with the gold `facts.json`. Skip ① by passing `facts_override: list[PanelFacts] | None` to `NarrationCompiler.run`; add that parameter.
  - Then compute:
    - `grounded` (share of lines whose grounded judge passed)
    - `coverage` (from CritiqueReport)
    - `hallucinated_names` (count of `unknown_name` failures in the final revision)
    - `fallback_share`
    - `preference` (pairwise `eval_pair` judge per scene: compiler lines against reference lines, both orders, win rate)
- `EvalReport(_Strict)`: `created`, `chapters: list[ChapterMetrics]`, `totals: ChapterMetrics` (macro mean, `hallucinated_names` summed), `spotcheck: list[dict]` (20 random lines with the grounded verdict and reason, seeded by `random.Random(0)`).
- `write_report(report, out_dir) -> tuple[Path, Path]`: `report.json` plus `report.html` (a stdlib-`html`-escaped table; red cells where a metric misses its §1.5 target: grounded ≥ 0.95, coverage ≥ 0.95, hallucinated_names == 0, preference ≥ 0.55).
- `compare(current: EvalReport, baseline: EvalReport, tolerance: float = 0.02) -> list[str]` lists regressions. CLI: `narration eval [--slug S ...] [--baseline path]` exits 2 when `compare` lists anything.

- [ ] **Step 1: Write the failing tests** (mini fixture plus a fake client):
  - `test_dump_and_load_inputs_round_trip`
  - `test_eval_metrics_on_mini_fixture`: metric values are exact for scripted judge answers.
  - `test_preference_both_orders`
  - `test_report_html_escapes_text`: a line containing `<script>` is escaped.
  - `test_compare_flags_regression`
  - `test_add_gold_refuses_existing_slug`
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/unit/narration` in full.**
- [ ] **Step 5: Commit** `feat(narration): gold set and narration eval`

### Task 11: Exit check (real models)

**Files:** none (ledger only), unless a defect is found.

- [ ] **Step 1:** `python -m engine.narration run <id>` on Ch927 (`098c6713-…`), TDG 536.1 (`d20d6fd8-…`) and one more real chapter with real OCR. Record for each:
  - gate
  - lines
  - fallbacks
  - coverage
  - wall time
  - `run.json` model calls
- [ ] **Step 2:** `narration gold add` those 3 chapters. Hand-correct `facts.json` only where obviously wrong (owner can refine later). Run `narration eval`.
- [ ] **Step 3:** Record the §1.5 metrics that P2 owns (grounded, coverage, hallucinated names, preference) against their targets. P2 exits when grounded ≥ 95 % and coverage ≥ 95 % on the gold set (spec §10). If it misses, file each cause as a finding for the final fix wave.
- [ ] **Step 4:** Read 10 random final lines from each chapter yourself, next to their panels. Note any ungrounded line the judge passed: that is judge-calibration evidence for §6.2.
