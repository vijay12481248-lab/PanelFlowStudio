# Anatomy and Pose Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the owner said "go ahead and build it"; this session implements every task itself). Steps use checkbox syntax.

**Goal:** Check a generated picture for wrong limb counts, missing poses, ghost objects and stray text with zoomed tiles and the two local vision judges, redraw on confirmed defects, and learn prompt rules from the failures.

**Architecture:** New package `engine/original/anatomy/` built on the existing judges (`engine/original/judges.py`), `MistakeLedger` (`engine/creative/mistakes.py`) and `ArtEngine`. Tiles are cut deterministically; judges answer narrow blind questions; deterministic rules turn answers into defects; a defect is confirmed only when both judges report it. Records go to an append-only JSONL file under the app-data config folder (works in tools and in the engine).

**Tech Stack:** Python 3.14, Pillow, pydantic, pytest, FastAPI router, MCP tool registry, Ollama `qwen3.5:9b` + ComfyUI `TextGenerate` Qwen3-VL 8B.

**Spec:** `docs/superpowers/specs/2026-11-16-anatomy-review-design.md`

## Global Constraints

- Local-first: no cloud or mock fallback; a judge never raises (`ok=False` instead).
- A picture is never reported `clean` unless at least one judge produced a usable whole-picture answer; otherwise `unverified`.
- Redraw only on `confirmed` defects (both judges); `suspected` (one judge) is kept and flagged. With a single judge available nothing is ever confirmed.
- Defaults: 4 attempts, 240 s budget, tiles upscaled to a 1280 px long side, lesson active after `recurrence_count >= 2`.
- Lessons are positive sentences appended to the END of the prompt (klein and Qwen ignore negative prompts); keyed by defect kind and pose word, never by story words.
- Seeded klein rules start active and carry `example_good="agent-labelled 2026-11-16"`.
- Files under `output/anatomy_labels/` are not committed; only `tests/data/anatomy_labels.json` is.
- Gate before trust: recall >= 0.8 on confirmed known defects and <= 1 false alarm per 10 clean pictures, measured by `tools/anatomy/calibrate.py`; report the real numbers; if it fails, ship flag-only (opt-in stays off) and say so.

## Review Focus

- A judge that rambles, echoes the template or is offline: report `unverified`, never `clean`.
- Both judges disagree about how many people there are: count rules are skipped (unverified for counts), not guessed.
- Only one judge exists: defects are `suspected`, the loop never redraws on them.
- The prompt has no pose words from the list: pose checks are skipped and the report names that.
- The redraw budget runs out or the art engine raises on attempt 2: the best earlier picture is still delivered with its report.
- The lessons file is missing or corrupt: the check still runs and the prompt is left unchanged.
- Tiny or very wide pictures: tiling never produces an empty or zero-size tile.

## File Structure

- Create `engine/original/anatomy/__init__.py` (exports), `tiles.py`, `questions.py`, `rules.py`, `review.py`, `loop.py`, `lessons.py`, `store.py`.
- Modify `engine/original/judges.py` (public `ask` on judges), `tools/reels/make_reel.py` (opt-in hook), `engine/api/` (router registration), `engine/mcp/tools/` (two tools).
- Create `engine/api/routers/anatomy.py`, `tools/anatomy/calibrate.py`, `tools/anatomy/build_labels.py`, `tests/data/anatomy_labels.json`, `tests/unit/test_anatomy_*.py`, `docs/ANATOMY_REVIEW.md`.

### Task 1: Judges can answer any question

**Files:** Modify `engine/original/judges.py`; Test `tests/unit/test_anatomy_judges_ask.py`
**Interfaces:** Produces `async def ask(self, image: Path | bytes, prompt: str) -> str` on `_Base` (returns `""` when the judge fails) and on the `Judge` Protocol.
- [ ] Failing test: a `_Base` subclass whose `_ask` raises returns `""` from `ask`; one that returns text returns that text.
- [ ] Implement `ask` in `_Base`; add it to the `Judge` Protocol.
- [ ] Run the test, then `tests/unit/test_judges*.py`; all pass. Commit.

### Task 2: Tiles

**Files:** Create `engine/original/anatomy/tiles.py`; Test `tests/unit/test_anatomy_tiles.py`
**Interfaces:** Produces `@dataclass(frozen=True) class Tile: name: str; box: tuple[int, int, int, int]; png: bytes` and `def make_tiles(image: bytes, people: int | None = None, target_side: int = 1280) -> list[Tile]`.
- [ ] Failing tests: 768x1344 image gives names `["whole","upper","middle","lower"]`; `people=2` adds `"left"` and `"right"`; every tile decodes, long side == `target_side` (whole included, upscaled), boxes lie inside the image and overlap neighbouring bands by about 15 %; a 16x16 image still gives non-empty tiles (Review Focus: tiny pictures).
- [ ] Implement with Pillow (LANCZOS); bands are thirds with 15 % overlap; halves for `people >= 2`.
- [ ] Run tests. Commit.

### Task 3: Questions and strict parsers

**Files:** Create `engine/original/anatomy/questions.py`; Test `tests/unit/test_anatomy_questions.py`
**Interfaces:** Produces `WHOLE_PROMPT: str`, `TILE_PROMPT: str`, `def pose_prompt(question: str) -> str`, `@dataclass class Answer: tile: str; judge: str; ok: bool; people: int | None; arms: int | None; hands: int | None; legs: int | None; feet: int | None; text: bool | None; double: bool | None; merged: bool | None; evidence: str`, `def parse_reply(text: str, judge: str, tile: str) -> Answer`, `def parse_yes_no(text: str) -> bool | None`. Reuses `judges._people` for numbers.
- [ ] Failing tests: a well-formed reply parses every field; "ARMS: 2 or 3" and "ARMS: four arms and two legs" give `None` (not guessed); an echoed template (contains `<` `>` or `|`) gives `ok=False`; `parse_yes_no("Yes, clearly")` is True, `"not really"` is False, `"unclear"` is None; empty text gives `ok=False`.
- [ ] Implement: line-based `FIELD: value` parsing like `judges._field`; counts via `_people`; yes/no by first token with negation guard.
- [ ] Run tests. Commit.

### Task 4: Rules (answers to defects)

**Files:** Create `engine/original/anatomy/rules.py`; Test `tests/unit/test_anatomy_rules.py`
**Interfaces:** Consumes `Answer`. Produces `DEFECT_KINDS = ("extra_arms","extra_hands","extra_legs","extra_feet","stray_text","duplicate_object","pose_missing","merged_bodies")`, `class Defect(BaseModel): kind: str; judge: str; tile: str; detail: str; pose: str | None = None`, `POSE_WORDS: dict[str, tuple[str, str]]` (word to (pose key, yes/no question)) covering `cross-legged`, `hands on knees`, `kick`, `raised`, `two hands`, `def pose_asks(prompt: str) -> tuple[list[tuple[str, str]], list[str]]` (asks, skipped words), `def judge_defects(answers: list[Answer], people: int | None, pose_answers: dict[str, bool | None], text_asked: bool = False) -> list[Defect]`.
- [ ] Failing tests: people=1, a tile answer hands=4 gives `extra_hands`; hands=2 gives none; arms=4 with people=2 gives none (<= 2 per person), arms=5 gives `extra_arms`; counts are compared per tile and the whole picture by maximum, never summed (two tiles of hands=1 each do not trigger); `people=None` skips count rules; `text=True` gives `stray_text` unless `text_asked`; `double=True` gives `duplicate_object`; `merged=True` gives `merged_bodies`; a pose answer False gives `pose_missing` with the pose key, None gives nothing; `pose_asks("sitting cross-legged, hands resting on her knees")` returns two asks and no skipped words, and a prompt with no list word returns no asks and its words unchanged in `skipped`.
- [ ] Implement as pure functions.
- [ ] Run tests. Commit.

### Task 5: Reviewer (two judges, confirmed vs suspected)

**Files:** Create `engine/original/anatomy/review.py`; Test `tests/unit/test_anatomy_review.py`
**Interfaces:** Consumes `make_tiles`, `questions`, `rules`, a list of `Judge` (with `ask`). Produces `class AnatomyReport(BaseModel): status: Literal["clean","defects","unverified"]; confirmed: list[Defect]; suspected: list[Defect]; people: int | None; judges: list[str]; counts_skipped: bool; pose_skipped: list[str]; seconds: float` and `async def review_picture(judges: list[Judge], image: bytes, prompt: str = "", *, between: Callable[[], None] | None = None) -> AnatomyReport`.
- [ ] Failing tests with scripted fake judges: both report hands=4 on the same tile -> `confirmed` extra_hands and status `defects`; only one does -> `suspected`, status `clean`; a lone judge never confirms; both unparseable -> `unverified`; judges give different people counts -> `counts_skipped=True`, no count defects, still a pose check; `between` is called once between judges; a prompt without pose words fills `pose_skipped`.
- [ ] Implement: whole question on the whole tile for each judge, people = the value both agree on; tile questions on the remaining tiles; pose yes/no questions on the whole tile; run judge-by-judge (call `between` after each judge) to respect VRAM; confirmed = same `(kind, pose)` from both judges.
- [ ] Run tests. Commit.

### Task 6: Lessons (learn)

**Files:** Create `engine/original/anatomy/lessons.py`; Test `tests/unit/test_anatomy_lessons.py`
**Interfaces:** Consumes `AnatomyReport`, `MistakeLedger`. Produces `def domain(model: str) -> str` (`anatomy:<model>`), `RULES: dict[str, str]` (kind or `pose_missing:<pose>` to a positive sentence, e.g. `extra_arms` -> "Exactly two arms per person, no extra arms or hands anywhere."), `def record_report(ledger, model, report) -> int` (one sighting per confirmed defect key), `def rules_for(ledger, model, prompt: str, min_recurrence: int = 2) -> str` (only rules that fit the prompt's pose words; pose rules only when that pose word appears), `def seed_known_rules(ledger, model: str = "flux2_klein_4b") -> int` (idempotent).
- [ ] Failing tests (tmp ledger file): one sighting records but `rules_for` returns "" ; a second sighting activates it; a `pose_missing:cross_legged` rule is returned only for a prompt containing "cross-legged"; `seed_known_rules` twice gives one record per rule and the rules are active immediately; a corrupt ledger file makes `rules_for` return "" instead of raising.
- [ ] Implement over `ledger.record_or_escalate_mistake(domain=..., flawed_pattern=key, prevention_rule=RULES[key], category=kind, example_good=...)`.
- [ ] Run tests. Commit.

### Task 7: Knowledge records and stats

**Files:** Create `engine/original/anatomy/store.py`; Test `tests/unit/test_anatomy_store.py`
**Interfaces:** Produces `def checks_path() -> Path` (`settings.app_data_dir / "config" / "anatomy_checks.jsonl"`), `def append_check(path: Path, *, model: str, picture: str, prompt: str, rules_used: bool, report: dict, attempt: int) -> None`, `def flag_missed(path: Path, *, picture: str, model: str, note: str) -> None`, `def stats(path: Path) -> dict` with keys `checked`, `by_model` (per model: `checked`, `defect_rate`, `by_kind`, `rate_rules_off`, `rate_rules_on`, `redraws`), `owner_flags`.
- [ ] Failing tests: three appended checks (one with defects) give the right counts and rates; rules-on and rules-off rates are computed separately; a flagged miss is counted and listed; a missing file gives zeros; a half-written last line is skipped, not fatal.
- [ ] Implement JSONL append with a lock file-free single `open("a")`; tolerant reader.
- [ ] Run tests. Commit.

### Task 8: Redraw loop

**Files:** Create `engine/original/anatomy/loop.py`; Test `tests/unit/test_anatomy_loop.py`
**Interfaces:** Consumes `review_picture`, `rules_for`, `record_report`, `append_check`. Produces `class AnatomyBudget(BaseModel): max_attempts: int = 4; max_seconds: float = 240.0`, `@dataclass class CheckedPicture: png: bytes; report: AnatomyReport; status: Literal["clean","best_effort","unverified"]; attempts: list[dict]; seed: int; prompt: str`, `def generate_checked(art_engine, judges, *, prompt: str, width: int, height: int, seed: int, prefix: str, workflow_id: str = ART_WORKFLOW_ID, reference_images=None, budget: AnatomyBudget = AnatomyBudget(), ledger: MistakeLedger | None = None, record_path: Path | None = None, between: Callable | None = None) -> CheckedPicture` (blocking).
- [ ] Failing tests with fake art engine and judge: clean first picture returns after one attempt; confirmed defect then clean redraws once with seed `seed + 7919`; all attempts defective returns the one with fewest confirmed defects, status `best_effort`; unverified reports are delivered as `unverified` and never redraw; the art engine raising on attempt 2 still delivers attempt 1; `max_seconds` stops new attempts; lessons from `rules_for` are appended to the prompt as " Remember: ..." only when non-empty; every attempt is appended to `record_path`.
- [ ] Implement: attempt loop, keep per-attempt report; after the loop `record_report` for the first attempt only (what the plain prompt gets wrong, like `scene_run.py`).
- [ ] Run tests. Commit.

### Task 9: API, MCP, labelled set and calibration gate

**Files:** Create `engine/api/routers/anatomy.py`, `tools/anatomy/build_labels.py`, `tools/anatomy/calibrate.py`, `tests/data/anatomy_labels.json`, `tests/unit/test_anatomy_api.py`; Modify the app router registration and `engine/mcp/tools/` (`panelflow_anatomy_stats`, `panelflow_anatomy_flag`).
**Interfaces:** `GET /api/original/anatomy/stats` returns `stats(...)`; `POST /api/original/anatomy/flag` body `{picture, model, note}` calls `flag_missed`; calibrate prints and writes `output/anatomy_labels/calibration.json` with `recall_confirmed`, `false_alarms_per_10_clean`, `unverified_share`, per-picture rows.
- [ ] Failing API tests with a temp path (stats shape; flag then stats shows `owner_flags == 1`; flag rejects an empty note).
- [ ] Implement router, MCP tools, label builder (copies the audited pictures to `output/anatomy_labels/` and writes counts; pictures the agent is unsure of, the klein hugs, carry `expected: null` and are excluded from the metrics), and the calibrate script.
- [ ] Run the new unit tests and the full `tests/unit` run; only pre-existing failures remain. Commit.
- [ ] Run `tools/anatomy/calibrate.py` for real (ComfyUI and Ollama up). Record recall and false alarms in `docs/ANATOMY_REVIEW.md`. If the gate fails, leave the Reels opt-in documented as flag-only.

### Task 10: Opt-in for Reels, docs, memory

**Files:** Modify `tools/reels/make_reel.py` (`stage_art`), create `docs/ANATOMY_REVIEW.md`; Test `tests/unit/test_anatomy_reels_hook.py` (the helper that picks plain or checked drawing).
- [ ] With `REEL_ANATOMY_CHECK=1` and the gate passed, `stage_art` draws through `generate_checked` and stores the report beside the panel; default behaviour unchanged.
- [ ] Write `docs/ANATOMY_REVIEW.md` (how it works, measured numbers, known weaknesses, how to flag a miss) and a memory note.
- [ ] Run the touched tests. Commit.
