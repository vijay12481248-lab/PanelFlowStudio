# Narration Compiler P1 — Foundation + Perceive + Understand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Narration Compiler foundation and its first two stages so that any chapter in the library can be turned into validated **PanelFacts** and a **BeatSheet**, cached and logged, using only local models.

**Architecture:** New package `engine/narration/` with typed artifacts, a content-addressed cache, a role-based local model runtime (roles → models, JSON-schema-constrained calls, model-grouped scheduling), a per-series Story Bible store, and two steps: ① PERCEIVE (one vision call per panel, OCR text copied verbatim) and ② UNDERSTAND (windowed scene/beat planning stitched in code, then one merge call). A `NarrationCompiler` runs the steps, routes failures to a `review` / `failed` gate, and writes `run.json`. Nothing in autopilot, render, or the editor changes in P1.

**Tech Stack:** Python 3.12+, Pydantic v2, httpx, PyYAML, existing `engine.llm` providers (Ollama `qwen3.5:9b`), SQLAlchemy models in `engine.database.models`, pytest (asyncio_mode = strict).

**Spec:** `docs/superpowers/specs/2026-10-30-narration-compiler-design.md` (P1 = §2, §3.1–3.3, §4.1–4.2, §5, §6.6 run log, §8 rows that apply, §9 unit/contract tests, §10 P1)

## Global Constraints

- Local models only. No cloud provider is called from `engine/narration/`.
- Every model call is JSON-schema constrained and Pydantic-validated; one retry with the validation error, then the step fails. Never substitute placeholder or canned text (spec §2.2 principle 6).
- Dialogue text in artifacts is copied verbatim from OCR (`corrected_text` or `raw_text`); models only assign speakers (spec §4.1).
- Unrecognised characters are `unknown_<n>`, never invented names (spec §4.1).
- No prompt may exceed `num_ctx` 8192 tokens (spec §5.5 ≈ 6k budget); ② windows are 30 story panels with 5-panel overlap (spec §4.2).
- One heavy model loaded at a time; work grouped by model; `vision` concurrency 3 (spec §5.4: 2–4), all text roles concurrency 1.
- Role defaults (spec §5.1): `vision` temperature 0.1; `planner` 0.2; `writer` 0.7, top_p 0.9; `judge` 0. All default to `qwen3.5:9b`.
- Model timeout: 2 retries with backoff (2 s, 4 s); invalid JSON: 1 retry (spec §8).
- Artifacts are JSON written with `ensure_ascii=False`, atomically (temp file + `os.replace`).
- Tests are offline: no Ollama, no GPU. Async code is tested with `asyncio.run(...)` inside sync tests (pytest `asyncio_mode = strict`).
- Keep files focused: one responsibility per module as listed in File Structure.

## Review Focus

1. A panel the vision model marks `is_story: false` (credits, ads, blank) must stay in PanelFacts but be excluded from ② windows and coverage — Task 9 test `test_non_story_panels_are_excluded_from_scenes`.
2. The model returns a speaker for an OCR `region_id` that does not belong to the panel — it must be ignored, never create dialogue — Task 8 test `test_speakers_for_unknown_regions_are_ignored`.
3. A chapter with zero story panels must stop with a review reason, not crash or produce an empty BeatSheet — Task 9 test `test_zero_story_panels_needs_review`.
4. Editing a prompt file must invalidate cached outputs for that step only — Task 2 test `test_prompt_change_misses_cache`.
5. Ollama going down mid-run must leave completed steps cached so a rerun resumes, and must not write a BeatSheet — Task 10 test `test_model_failure_marks_run_failed_and_rerun_resumes_from_cache`.
6. CJK / accented OCR text must round-trip unchanged — Task 2 test `test_unicode_round_trips`.

---

## File Structure

```
engine/narration/
  __init__.py                 # exports NarrationCompiler, CompileResult
  __main__.py                 # CLI: python -m engine.narration run <project_id>
  artifacts.py                # Pydantic artifacts (PanelFacts, SeriesBible, BeatSheet, …) + assert_known_ids
  cache.py                    # cache_key(), ArtifactCache
  inputs.py                   # ChapterInputs loader from the project DB
  compiler.py                 # NarrationCompiler, RunLog, CompileResult, NeedsReview handling
  narration_models.yaml       # default role → model config
  bible/__init__.py
  bible/store.py              # series_key_for(), BibleStore
  runtime/__init__.py
  runtime/roles.py            # RoleConfig, load_roles()
  runtime/prompts.py          # PromptAsset, load_prompt()
  runtime/client.py           # ModelClient protocol, ProviderModelClient, StepModelError
  runtime/scheduler.py        # ModelScheduler, ollama_unloader()
  steps/__init__.py
  steps/perceive.py           # ① perceive_chapter()
  steps/understand.py         # ② windows(), stitch_windows(), check_beat_sheet(), understand_chapter(), NeedsReview
  prompts/perceive/v1.md
  prompts/understand_window/v1.md
  prompts/understand_merge/v1.md
tests/unit/narration/
  __init__.py
  fakes.py                    # FakeModelClient, fake unloader, synthetic ChapterInputs builder
  test_artifacts.py
  test_cache.py
  test_runtime_roles_prompts.py
  test_runtime_client.py
  test_runtime_scheduler.py
  test_bible_store.py
  test_inputs.py
  test_perceive.py
  test_understand.py
  test_compiler.py
pyproject.toml                # add "pyyaml" to dependencies
```

---

### Task 1: Artifacts

**Files:**
- Create: `engine/narration/__init__.py` (empty for now), `engine/narration/artifacts.py`
- Test: `tests/unit/narration/__init__.py`, `tests/unit/narration/test_artifacts.py`

**Interfaces:**
- Produces (all `pydantic.BaseModel`, `model_config = ConfigDict(extra="forbid")`):
  - `OcrDialogue(region_id: str, text: str, speaker_id: str | None = None, speaker_confidence: float = 0.0)`
  - `PanelFacts(panel_id: str, order: int, is_story: bool, shot: Literal["wide","medium","close","insert"], characters_visible: list[str] = [], unknown_cues: dict[str, str] = {}, action: str, emotion: str, dialogue: list[OcrDialogue] = [], sfx: list[str] = [], setting: str = "", importance: int (1..5), confidence: float (0..1), needs_review: bool = False)` — validator: `action` ≤ 20 words.
  - `BibleCharacter(id: str, name: str, aliases: list[str] = [], appearance_cues: list[str] = [], role: str = "", relationships: dict[str, str] = {}, catchphrases: list[str] = [], pronunciation: str | None = None)`
  - `BibleLocation(id: str, name: str, description: str = "")`
  - `NarratorVoice(style_notes: list[str] = [], banned_phrases: list[str] = [], transitions: list[str] = [])`
  - `BibleRevision(version: int, project_id: str, applied: list[str])`
  - `SeriesBible(series_key: str, version: int = 0, characters: list[BibleCharacter] = [], locations: list[BibleLocation] = [], plot_so_far: str = "", open_threads: list[str] = [], glossary: dict[str, str] = {}, narrator_voice: NarratorVoice = NarratorVoice(), history: list[BibleRevision] = [])` — validator: `plot_so_far` ≤ 150 words.
  - `Beat(beat_id: str, panel_ids: list[str] (min 1), what_happens: str, function: Literal["setup","escalate","reveal","payoff","cliffhanger"], intensity: float (0..1))`
  - `Scene(scene_id: str, first_panel_id: str, last_panel_id: str, goal: str, conflict: str, turn: str, beats: list[Beat] (min 1))`
  - `BibleProposal(kind: Literal["add_character","add_location","update_plot","add_thread","close_thread"], payload: dict)`
  - `BeatSheet(project_id: str, scenes: list[Scene] (min 1), hook: str, chapter_summary: str, character_resolutions: dict[str, str] = {}, bible_proposals: list[BibleProposal] = [])`
  - `class ArtifactIdError(ValueError)`
  - `assert_known_ids(ids: Iterable[str], known: set[str], where: str) -> None` — raises `ArtifactIdError` naming every unknown id and `where`.

- [ ] **Step 1: Write the failing tests**

```python
def test_panel_facts_round_trip():
    facts = PanelFacts(panel_id="p1", order=1, is_story=True, shot="close", characters_visible=["c1", "unknown_1"],
                       unknown_cues={"unknown_1": "masked man"}, action="Yulin draws his sword.", emotion="anger",
                       dialogue=[OcrDialogue(region_id="r1", text="You dare?", speaker_id="c1", speaker_confidence=0.8)],
                       importance=4, confidence=0.9)
    assert PanelFacts.model_validate_json(facts.model_dump_json()) == facts

def test_action_longer_than_20_words_is_rejected():
    with pytest.raises(ValidationError):
        PanelFacts(panel_id="p", order=1, is_story=True, shot="wide", action=" ".join(["word"] * 21),
                   emotion="calm", importance=1, confidence=0.5)

def test_plot_so_far_capped_at_150_words():
    with pytest.raises(ValidationError):
        SeriesBible(series_key="s", plot_so_far=" ".join(["w"] * 151))

def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        Beat(beat_id="b", panel_ids=["p"], what_happens="x", function="setup", intensity=0.5, made_up=1)

def test_assert_known_ids_names_every_unknown():
    with pytest.raises(ArtifactIdError, match=r"scene s1.*p9.*p10"):
        assert_known_ids(["p1", "p9", "p10"], {"p1"}, "scene s1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_artifacts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.narration'`

- [ ] **Step 3: Implement `engine/narration/artifacts.py`** with the models and validators listed in Interfaces. Use `Field(ge=, le=)` for numeric ranges and `@field_validator` for word caps.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_artifacts.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/__init__.py engine/narration/artifacts.py tests/unit/narration/__init__.py tests/unit/narration/test_artifacts.py
git commit -m "feat(narration): typed artifacts for panel facts, series bible and beat sheet"
```

---

### Task 2: Content-addressed artifact cache

**Files:**
- Create: `engine/narration/cache.py`
- Test: `tests/unit/narration/test_cache.py`

**Interfaces:**
- Consumes: any `pydantic.BaseModel` from Task 1.
- Produces:
  - `cache_key(step: str, inputs: Any, prompt_sha: str, model: str, params: dict) -> str` — sha256 hex of `json.dumps({"step","inputs","prompt_sha","model","params"}, sort_keys=True, ensure_ascii=False, default=str)`.
  - `class ArtifactCache(root: Path)` with `get(step: str, key: str, model_cls: type[T]) -> T | None` and `put(step: str, key: str, artifact: BaseModel | list[BaseModel]) -> Path`. Layout: `root/<step>/<key>.json`. Lists are stored as a JSON array and read back with `model_cls` per element (`get` returns `list[T]` when the file holds an array). Writes are atomic (`<key>.json.tmp` then `os.replace`), UTF-8, `ensure_ascii=False`.

- [ ] **Step 1: Write the failing tests**

```python
def test_put_then_get_returns_equal_artifact(tmp_path): ...
    # put PanelFacts under step "perceive", get it back, assert ==

def test_prompt_change_misses_cache():
    a = cache_key("perceive", {"panel": "p1"}, "sha-A", "qwen3.5:9b", {"t": 0.1})
    b = cache_key("perceive", {"panel": "p1"}, "sha-B", "qwen3.5:9b", {"t": 0.1})
    assert a != b
    assert cache_key("perceive", {"panel": "p1"}, "sha-A", "qwen3.5:9b", {"t": 0.1}) == a

def test_key_ignores_dict_ordering():
    assert cache_key("s", {"a": 1, "b": 2}, "x", "m", {}) == cache_key("s", {"b": 2, "a": 1}, "x", "m", {})

def test_missing_key_returns_none(tmp_path):
    assert ArtifactCache(tmp_path).get("perceive", "nope", PanelFacts) is None

def test_unicode_round_trips(tmp_path):
    # PanelFacts with dialogue text "修炼者！ Él dijo: ¿qué?" → put → raw file contains the characters unescaped → get == original

def test_list_artifacts_round_trip(tmp_path):
    # put [facts1, facts2] → get(..., PanelFacts) == [facts1, facts2]

def test_write_is_atomic_no_tmp_left(tmp_path):
    # after put, no "*.tmp" files remain under tmp_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.narration.cache'`

- [ ] **Step 3: Implement `cache_key` and `ArtifactCache` in `engine/narration/cache.py`** per Interfaces.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_cache.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/cache.py tests/unit/narration/test_cache.py
git commit -m "feat(narration): content-addressed artifact cache"
```

---

### Task 3: Role config and versioned prompt assets

**Files:**
- Create: `engine/narration/runtime/__init__.py`, `engine/narration/runtime/roles.py`, `engine/narration/runtime/prompts.py`, `engine/narration/narration_models.yaml`
- Modify: `pyproject.toml` (add `"pyyaml",` to `[project].dependencies`, alphabetical position after `"psutil",`)
- Test: `tests/unit/narration/test_runtime_roles_prompts.py`

**Interfaces:**
- Produces:
  - `RoleConfig(model: str, temperature: float, top_p: float | None = None, max_tokens: int, num_ctx: int = 8192, concurrency: int = 1, timeout_s: float = 120.0)` (Pydantic, `extra="forbid"`).
  - `load_roles(path: Path | None = None) -> dict[str, RoleConfig]` — reads `engine/narration/narration_models.yaml`; if `settings.app_data_dir / "config" / "narration_models.yaml"` exists, its roles override the defaults key by key. Raises `ValueError` if any of `vision`, `planner`, `writer`, `judge` is missing.
  - `PromptAsset(step: str, version: str, text: str, sha256: str)` with `render(**values: str) -> str` using `string.Template.substitute` (`$name` placeholders, so JSON braces in prompts need no escaping).
  - `load_prompt(step: str, version: str = "v1") -> PromptAsset` — reads `engine/narration/prompts/<step>/<version>.md`; `sha256` is of the file bytes.
- `narration_models.yaml` content (exact values from spec §5.1 and Global Constraints):

```yaml
roles:
  vision:  {model: "qwen3.5:9b", temperature: 0.1, max_tokens: 1024, num_ctx: 8192, concurrency: 3, timeout_s: 120}
  planner: {model: "qwen3.5:9b", temperature: 0.2, max_tokens: 4096, num_ctx: 8192, concurrency: 1, timeout_s: 180}
  writer:  {model: "qwen3.5:9b", temperature: 0.7, top_p: 0.9, max_tokens: 2048, num_ctx: 8192, concurrency: 1, timeout_s: 180}
  judge:   {model: "qwen3.5:9b", temperature: 0.0, max_tokens: 512, num_ctx: 8192, concurrency: 1, timeout_s: 120}
```

- [ ] **Step 1: Write the failing tests**

```python
def test_default_roles_match_spec():
    roles = load_roles()
    assert roles["vision"].temperature == 0.1 and roles["vision"].concurrency == 3
    assert roles["writer"].temperature == 0.7 and roles["writer"].top_p == 0.9
    assert roles["judge"].temperature == 0.0
    assert {r.model for r in roles.values()} == {"qwen3.5:9b"}

def test_user_override_replaces_one_role(tmp_path, monkeypatch):
    # write <app_data>/config/narration_models.yaml with roles.judge.model = "gemma3:9b"
    # monkeypatch settings.app_data_dir to tmp_path → load_roles()["judge"].model == "gemma3:9b", vision unchanged

def test_missing_required_role_raises(tmp_path):
    # yaml with only vision → load_roles(path) raises ValueError mentioning "planner"

def test_prompt_render_and_hash(tmp_path, monkeypatch):
    # point prompts root to tmp_path; file "x/v1.md" = 'Panel $n {"a": 1}'
    p = load_prompt("x")
    assert p.render(n="7") == 'Panel 7 {"a": 1}'
    assert len(p.sha256) == 64

def test_render_missing_variable_raises():
    # PromptAsset(..., text="$a $b").render(a="1") raises KeyError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_roles_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `roles.py`, `prompts.py`, the YAML file, and the `pyproject.toml` dependency line.** `prompts.py` resolves its root as `Path(__file__).resolve().parents[1] / "prompts"` via a module-level `PROMPTS_ROOT` the test can monkeypatch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_roles_prompts.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/runtime engine/narration/narration_models.yaml pyproject.toml tests/unit/narration/test_runtime_roles_prompts.py
git commit -m "feat(narration): role-based model config and versioned prompt assets"
```

---

### Task 4: Model client (structured calls, retries, timeouts)

**Files:**
- Create: `engine/narration/runtime/client.py`, `tests/unit/narration/fakes.py`
- Test: `tests/unit/narration/test_runtime_client.py`

**Interfaces:**
- Consumes: `RoleConfig`, `load_roles()` (Task 3); `engine.llm.providers.base.LLMProvider` with `generate_structured(prompt, response_model, system_prompt=None, temperature=..., max_repair_retries=..., model=..., max_tokens=..., num_ctx=...)` and `analyze_vision(image, prompt, system_prompt=None, model=..., max_tokens=..., format_schema=dict) -> str`.
- Produces:
  - `class StepModelError(RuntimeError)` — carries `role: str` and the last cause.
  - `class ModelClient(Protocol)`: `def model_for(self, role: str) -> str`; `def params_for(self, role: str) -> dict` (the role's `temperature`, `top_p`, `max_tokens`, `num_ctx`, used in cache keys); `async def structured(self, role: str, prompt: str, schema: type[T], image: Path | None = None, system: str | None = None) -> T`.
  - `class ProviderModelClient(ModelClient)`: `__init__(self, provider: LLMProvider, roles: dict[str, RoleConfig], backoff_s: tuple[float, ...] = (2.0, 4.0))`.
    - Text call → `provider.generate_structured(..., temperature=role.temperature, max_repair_retries=1, model=role.model, max_tokens=role.max_tokens, num_ctx=role.num_ctx)`.
    - Image call → `provider.analyze_vision(image, prompt, system_prompt=system, model=role.model, max_tokens=role.max_tokens, format_schema=schema.model_json_schema())`, then `schema.model_validate_json(text)`; on `ValidationError` one retry with `"\n\nYour previous reply failed validation: <error, first 600 chars>. Reply with corrected JSON only."` appended.
    - Every call wrapped in `asyncio.wait_for(..., role.timeout_s)`; on `TimeoutError`, `httpx.HTTPError`, or `ConnectionError`: sleep `backoff_s[i]` and retry, at most `len(backoff_s)` retries; then raise `StepModelError`.
    - Validation still failing after its retry → `StepModelError` (no fallback text).
- Produces (test helper in `tests/unit/narration/fakes.py`):
  - `FakeModelClient(responses: dict[str, list[BaseModel | Exception | Callable[[str], BaseModel]]], models: dict[str, str] | None = None)` — `model_for` returns `models.get(role, "qwen3.5:9b")`, `params_for` returns `{}`; pops the next response per role (calls callables with the prompt), records `calls: list[tuple[role, prompt, image]]`, raises queued exceptions, raises `AssertionError` when a role's queue is empty.

- [ ] **Step 1: Write the failing tests** (use a small stub provider class in the test file that scripts return values / exceptions per call)

```python
def test_text_call_passes_role_params():
    # stub records kwargs → assert model="qwen3.5:9b", temperature=0.2, max_repair_retries=1, num_ctx=8192 for role "planner"

def test_vision_call_validates_json_and_retries_once_on_bad_json():
    # stub.analyze_vision returns "not json" then a valid JSON string → result validated; 2 calls; 2nd prompt contains "failed validation"

def test_vision_bad_json_twice_raises_step_model_error():
    # two invalid replies → StepModelError, role == "vision"

def test_timeout_retries_with_backoff_then_fails():
    # stub raises httpx.ConnectError 3 times; backoff_s=(0, 0) → StepModelError after 3 attempts

def test_timeout_then_success_returns_result():
    # stub raises httpx.ReadTimeout once then succeeds → returns model, 2 attempts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `client.py` and `fakes.py`** per Interfaces.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_client.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/runtime/client.py tests/unit/narration/fakes.py tests/unit/narration/test_runtime_client.py
git commit -m "feat(narration): schema-constrained model client with bounded retries"
```

---

### Task 5: Model-grouped scheduler

**Files:**
- Create: `engine/narration/runtime/scheduler.py`
- Modify: `tests/unit/narration/fakes.py` (add `RecordingUnloader`)
- Test: `tests/unit/narration/test_runtime_scheduler.py`

**Interfaces:**
- Consumes: `RoleConfig` (Task 3).
- Produces:
  - `class ModelScheduler(roles: dict[str, RoleConfig], unload: Callable[[str], Awaitable[None]])`
    - `async map(self, role: str, items: Sequence[T], fn: Callable[[T], Awaitable[R]]) -> list[R]` — results in input order; at most `roles[role].concurrency` in flight; if `roles[role].model` differs from the currently loaded model, `await unload(current)` first, then mark the new model loaded.
    - OOM handling: an exception whose `str()` contains `"out of memory"` (case-insensitive) → `await unload(model)`, halve the effective concurrency for this call (minimum 1), retry the failed items once; a second OOM propagates.
    - `async release(self) -> None` — unloads the current model (used after the last LLM step, before TTS in P3).
    - `concurrency(self, role: str) -> int` — `roles[role].concurrency` (steps use it to size their chunks).
  - `ollama_unloader(endpoint_url: str = "http://127.0.0.1:11434") -> Callable[[str], Awaitable[None]]` — `POST {endpoint}/api/generate` with `{"model": model, "keep_alive": 0}` via `httpx.AsyncClient(timeout=30)`; errors are logged, not raised.
- `RecordingUnloader` (fakes): async callable that appends model names to `.unloaded`.

- [ ] **Step 1: Write the failing tests**

```python
def test_map_preserves_order_and_limits_concurrency():
    # role concurrency 3, 10 items, fn sleeps 0.01 and tracks max in-flight → results == items order, max_in_flight == 3

def test_switching_to_a_different_model_unloads_previous():
    # roles vision=qwen, planner=gemma → map(vision) then map(planner) → unloader.unloaded == ["qwen"]

def test_same_model_across_roles_does_not_unload():
    # both roles qwen → map(vision) then map(planner) → unloaded == []

def test_out_of_memory_halves_concurrency_and_retries_once():
    # concurrency 4; first attempt of item 2 raises RuntimeError("CUDA out of memory") → item retried, all results returned,
    # unloaded contains model once, observed max in-flight during retry ≤ 2

def test_second_out_of_memory_propagates():
    # item always raises OOM → RuntimeError raised from map
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `scheduler.py`** with `asyncio.Semaphore` per call and the unload/OOM rules above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_runtime_scheduler.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/runtime/scheduler.py tests/unit/narration/fakes.py tests/unit/narration/test_runtime_scheduler.py
git commit -m "feat(narration): model-grouped scheduler with VRAM-aware retries"
```

---

### Task 6: Series Bible store

**Files:**
- Create: `engine/narration/bible/__init__.py`, `engine/narration/bible/store.py`
- Test: `tests/unit/narration/test_bible_store.py`

**Interfaces:**
- Consumes: `SeriesBible`, `BibleCharacter`, `BibleLocation`, `BibleProposal`, `BibleRevision` (Task 1).
- Produces:
  - `series_key_for(title: str, source_metadata: dict | None) -> str` — uses `source_metadata["series_title"]` when non-empty, else `title` cut before the first case-insensitive `" - chapter"`; then lowercase, non-alphanumerics → `-`, collapsed, stripped.
  - `class BibleStore(root: Path | None = None)` — default root `settings.app_data_dir / "series"`.
    - `load(series_key: str) -> SeriesBible` — `root/<key>/bible.json`, or `SeriesBible(series_key=key)` (version 0) when missing.
    - `save(bible: SeriesBible, project_id: str, applied: list[str]) -> SeriesBible` — returns a copy with `version + 1` and a new `BibleRevision`; writes `bible.v<version>.json` and `bible.json` atomically.
    - `apply_proposals(bible: SeriesBible, proposals: list[BibleProposal]) -> tuple[SeriesBible, list[str]]` — pure; returns the updated copy and a human-readable list of what was applied. Rules: `add_character` (payload = `BibleCharacter` fields; skipped if id or case-insensitive name already present); `add_location` (same rule on id/name); `update_plot` (`payload["plot_so_far"]`, must pass the 150-word validator, else skipped); `add_thread` / `close_thread` (`payload["text"]`, exact-text add/remove).
  - P1 never calls `save` from the compiler (bible updates are applied on chapter approval, P2 review flow). `save` exists so P2 only wires it.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("title,meta,key", [
    ("Magic Emperor - Chapter 927 - Twisted Reality", {}, "magic-emperor"),
    ("Anything", {"series_title": "Tales Of Demons And Gods"}, "tales-of-demons-and-gods"),
    ("Log Into The Future - CHAPTER 5", None, "log-into-the-future"),
])
def test_series_key_for(title, meta, key): assert series_key_for(title, meta) == key

def test_load_missing_returns_empty_v0(tmp_path):
    assert BibleStore(tmp_path).load("x") == SeriesBible(series_key="x")

def test_save_bumps_version_and_keeps_history(tmp_path):
    # save twice → load().version == 2, files bible.v1.json and bible.v2.json exist, history[-1].project_id == "proj-2"

def test_apply_add_character_skips_duplicate_names():
    # bible has "Yulin"; proposals add "yulin" and "Feiyun" → only Feiyun added; applied mentions "Feiyun"

def test_apply_update_plot_over_150_words_is_skipped():
    # proposal plot of 151 words → bible.plot_so_far unchanged, applied == []

def test_apply_threads_add_and_close():
    # add "Who stole the sword?" then close it → open_threads == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_bible_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `bible/store.py`** per Interfaces (atomic writes as in Task 2).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_bible_store.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/bible tests/unit/narration/test_bible_store.py
git commit -m "feat(narration): versioned per-series story bible store"
```

---

### Task 7: Chapter inputs loader

**Files:**
- Create: `engine/narration/inputs.py`
- Modify: `tests/unit/narration/fakes.py` (add `make_chapter_inputs(tmp_path, n_panels, ocr: dict[int, list[str]]) -> ChapterInputs` writing tiny PNGs)
- Test: `tests/unit/narration/test_inputs.py`

**Interfaces:**
- Consumes: `ProjectRecord`, `PanelRecord`, `TextRegionRecord` (`engine.database.models`); `resolve_contained_path` (`engine.security.paths`); `series_key_for` (Task 6).
- Produces:
  - `OcrRegionInput(region_id: str, text: str, region_type: str)`
  - `PanelInput(panel_id: str, order: int, image_path: Path, ocr: list[OcrRegionInput])`
  - `ChapterInputs(project_id: str, series_key: str, panels: list[PanelInput])`
  - `load_chapter_inputs(db: Session, project_id: str) -> ChapterInputs` — panels with `status != "IGNORED"` ordered by `sequence`, `order` = 1-based position; `image_path` = `resolve_contained_path(<workspace>/panels, crop_filename, must_be_file=True)`; OCR regions for each panel with `status != "IGNORED"`, ordered by `sequence_global`, text = `corrected_text.strip() or raw_text.strip()`, regions with empty text skipped. Raises `KeyError` for an unknown project and `ValueError` when no panels remain.

- [ ] **Step 1: Write the failing tests** (DB setup copies the pattern in `tests/unit/test_bulk_ocr_regions.py`: `init_db()`, `SessionLocal()`, `ProjectRecord`/`PageRecord`/`PanelRecord`/`TextRegionRecord`; images via `PIL.Image.new`)

```python
def test_loads_panels_in_sequence_and_skips_ignored(tmp_path):
    # 3 panels seq 2,1,3 with seq 3 IGNORED → [p(seq1), p(seq2)], orders [1, 2]

def test_ocr_prefers_corrected_text_and_skips_empty_and_ignored(tmp_path):
    # regions: corrected "Hello" raw "Helo"; raw-only "World"; empty; IGNORED "x" → texts ["Hello", "World"] in sequence_global order

def test_series_key_from_project_metadata(tmp_path):
    # source_metadata={"series_title": "Magic Emperor"} → series_key == "magic-emperor"

def test_unknown_project_raises_key_error():
    with pytest.raises(KeyError): load_chapter_inputs(SessionLocal(), "missing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_inputs.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inputs.py`** per Interfaces, and `make_chapter_inputs` in fakes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_inputs.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/inputs.py tests/unit/narration/fakes.py tests/unit/narration/test_inputs.py
git commit -m "feat(narration): load chapter panels and OCR as compiler inputs"
```

---

### Task 8: ① PERCEIVE

**Files:**
- Create: `engine/narration/steps/__init__.py`, `engine/narration/steps/perceive.py`, `engine/narration/prompts/perceive/v1.md`
- Test: `tests/unit/narration/test_perceive.py`

**Interfaces:**
- Consumes: `ChapterInputs`, `PanelInput` (Task 7); `SeriesBible`, `PanelFacts`, `OcrDialogue` (Task 1); `ModelClient` (Task 4); `ModelScheduler` (Task 5); `ArtifactCache`, `cache_key` (Task 2); `load_prompt` (Task 3).
- Produces:
  - Model output schema `PanelFactsDraft(is_story: bool, shot: Literal[...4], characters_visible: list[str], action: str, emotion: str, speakers: list[SpeakerGuess], sfx: list[str], setting: str, importance: int (1..5), confidence: float (0..1))` with `SpeakerGuess(region_id: str, speaker: str)`. The draft has **no dialogue text field**.
  - `async perceive_chapter(inputs: ChapterInputs, bible: SeriesBible, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache) -> list[PanelFacts]` (input order).
  - `PERCEIVE_PROMPT_VERSION = "v1"`.
- Rules:
  - Panels are processed in chunks of `scheduler.concurrency("vision")` via `scheduler.map("vision", chunk, …)`. (Spec §4.1 asks for the previous panel's facts; feeding the previous *chunk's* last facts keeps 2–4 panels in parallel while preserving continuity.) Each panel's prompt includes the **previous chunk's last PanelFacts** (`action` + `characters_visible`) as continuity context, the panel's OCR lines (`[region_id] text`), and bible character cards (`id: name — appearance cues`). First chunk uses `"(chapter start)"`.
  - Name mapping (same function for `characters_visible` and `speakers`): case-insensitive match on bible `name` or `aliases` → bible `id`; already-seen `unknown_<n>` labels pass through; any other string → a chapter-stable `unknown_<n>` (n by first appearance across the chapter, starting at 1), recorded in `unknown_cues[unknown_<n>] = <model string>`.
  - `dialogue` = one `OcrDialogue` per OCR region of the panel, `text` copied from OCR verbatim; `speaker_id` from the mapped speaker guess for that `region_id` (`None` if none); `speaker_confidence` = 0.8 when assigned, else 0.0. Guesses for region ids not in the panel are ignored.
  - `needs_review = confidence < 0.5`.
  - Cache key inputs: `panel_id`, sha256 of image bytes, OCR `(region_id, text)` list, previous-context string, `bible.version`; prompt sha; `client.model_for("vision")`; `client.params_for("vision")`. Cache step name `"perceive"`. Unknown-id numbering is applied after cache reads (cache stores the raw draft), so numbering stays chapter-consistent on partial reruns.
- `prompts/perceive/v1.md` asks for exactly the `PanelFactsDraft` fields, states "Do not transcribe speech bubbles; they are given below", "Use a known character name only if their appearance cues match; otherwise describe them briefly (e.g. 'masked man')", "is_story=false for credits, ads, translator notes, watermark-only panels", and includes `$previous`, `$ocr_lines`, `$characters` placeholders.

- [ ] **Step 1: Write the failing tests** (use `FakeModelClient`, `RecordingUnloader`, `make_chapter_inputs`)

```python
def test_dialogue_text_is_copied_from_ocr_verbatim(tmp_path):
    # OCR "You dare?!"; draft speakers [{"region_id": r1, "speaker": "Yulin"}] → facts.dialogue[0].text == "You dare?!"

def test_speakers_for_unknown_regions_are_ignored(tmp_path):
    # draft speaker for region "r-not-in-panel" → no extra dialogue entries, len(dialogue) == number of OCR regions

def test_bible_names_map_to_ids_and_others_become_stable_unknowns(tmp_path):
    # bible: c1 "Shangguan Yulin" aliases ["Yulin"]; panel1 visible ["yulin", "masked man"], panel2 visible ["masked man"]
    # → p1 ["c1", "unknown_1"], p2 ["unknown_1"], p1.unknown_cues == {"unknown_1": "masked man"}

def test_low_confidence_marks_needs_review(tmp_path):
    # draft confidence 0.4 → needs_review True; 0.5 → False

def test_previous_chunk_context_is_in_prompt(tmp_path):
    # vision concurrency 1, two panels; panel1 action "Yulin bows." → second vision prompt contains "Yulin bows."

def test_second_run_uses_cache_and_calls_no_model(tmp_path):
    # run twice with same inputs → second run: client.calls unchanged; results equal
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_perceive.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `perceive.py` and `prompts/perceive/v1.md`** per Interfaces and Rules.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_perceive.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/steps engine/narration/prompts/perceive tests/unit/narration/test_perceive.py
git commit -m "feat(narration): perceive step builds grounded per-panel facts"
```

---

### Task 9: ② UNDERSTAND

**Files:**
- Create: `engine/narration/steps/understand.py`, `engine/narration/prompts/understand_window/v1.md`, `engine/narration/prompts/understand_merge/v1.md`
- Test: `tests/unit/narration/test_understand.py`

**Interfaces:**
- Consumes: `PanelFacts`, `SeriesBible`, `BeatSheet`, `Scene`, `Beat`, `BibleProposal`, `assert_known_ids` (Task 1); `ModelClient` (Task 4); `ModelScheduler` (Task 5); `ArtifactCache`, `cache_key` (Task 2); `load_prompt` (Task 3).
- Produces:
  - `class NeedsReview(Exception)` with `reasons: list[str]`.
  - `windows(n: int, size: int = 30, overlap: int = 5) -> list[tuple[int, int]]` — half-open ranges over story-panel indexes; stride `size - overlap`; last window ends at `n`; `n <= size` → `[(0, n)]`; `n == 0` → `[]`.
  - Model schemas (indexes are **chapter-wide story-panel numbers starting at 1**, shown to the model as `P1…Pn`, because small models handle short numbers far better than UUIDs):
    - `WindowBeatDraft(panels: list[int] (min 1), what_happens: str, function: Literal[...5], intensity: float)`
    - `WindowSceneDraft(first: int, last: int, goal: str, conflict: str, turn: str, beats: list[WindowBeatDraft] (min 1))`
    - `WindowDraft(scenes: list[WindowSceneDraft] (min 1))`
    - `MergeDraft(hook: str, chapter_summary: str, character_resolutions: dict[str, str], bible_proposals: list[BibleProposal])`
  - `stitch_windows(spans: list[tuple[int, int]], drafts: list[WindowDraft], overlap: int = 5) -> list[WindowSceneDraft]` — between window k and k+1 the cut point is `m = spans[k+1][0] + overlap // 2` (1-based panel number `m + 1`): window k keeps panels `< m+1`, window k+1 keeps panels `≥ m+1`; scenes are clipped to their window's kept range, beats clipped to their scene, empty beats/scenes dropped; result sorted by `first`.
  - `check_beat_sheet(sheet: BeatSheet, story_panel_ids: list[str], bible: SeriesBible) -> list[str]` — error strings for: a story panel in zero or more than one scene range; scenes not contiguous / out of reading order; a beat citing a panel outside its scene range; beats out of order within a scene; `character_resolutions` values not bible ids; any id unknown (via `assert_known_ids`).
  - `async understand_chapter(project_id: str, facts: list[PanelFacts], bible: SeriesBible, client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache) -> BeatSheet`.
- Rules:
  - Story panels = `facts` with `is_story` true, in order. Zero story panels → `NeedsReview(["no story panels"])`.
  - Window pass: one `planner` call per window (via `scheduler.map("planner", …)`), each prompt listing its panels as compact lines `P<k> | <characters> | <action> | <dialogue texts joined " / ">` plus bible names and `plot_so_far`. Cache step `"understand_window"`.
  - Stitch in code (`stitch_windows`), convert numbers → panel ids, assign `scene_id = f"s{i}"`, `beat_id = f"s{i}b{j}"`.
  - Merge pass: one `planner` call with the stitched scene list (goal / beats `what_happens`, ≤ 1 line each), bible character cards, and every `unknown_<n>` with its `unknown_cues`; returns `MergeDraft`. Cache step `"understand_merge"`. `character_resolutions` keys must be `unknown_<n>` labels present in facts; invalid entries are dropped (not errors).
  - Validate with `check_beat_sheet`. On errors: re-run only the windows whose span contains a failing panel, once, appending `"Fix these problems: <errors>"` to their prompts (bypassing cache for that retry), re-stitch, re-validate; still failing → `NeedsReview(errors)`.
  - The merge draft is applied after validation passes; merge failures (`StepModelError`) propagate.

- [ ] **Step 1: Write the failing tests**

```python
def test_windows():
    assert windows(70) == [(0, 30), (25, 55), (50, 70)]
    assert windows(12) == [(0, 12)]
    assert windows(0) == []

def test_stitch_cuts_overlap_at_midpoint():
    # spans [(0,30),(25,55)]; window0 scene P20–P30, window1 scene P26–P40 → stitched scenes P20–P27 and P28–P40

def test_check_beat_sheet_reports_gap_and_double_cover():
    # 4 story panels; scenes cover p1–p2 and p2–p3 → errors mention "p2" twice-covered and "p4" uncovered

def test_non_story_panels_are_excluded_from_scenes(tmp_path):
    # facts p1 story, p2 is_story False, p3 story → window prompt lists P1, P2 only (p3 renumbered P2); sheet covers p1, p3

def test_zero_story_panels_needs_review(tmp_path):
    # all facts is_story False → NeedsReview with "no story panels"

def test_invalid_window_is_reasked_once_then_needs_review(tmp_path):
    # planner returns a draft missing panel P3 twice → NeedsReview; exactly 2 window calls; 2nd prompt contains "Fix these problems"

def test_invalid_window_fixed_on_reask_returns_sheet(tmp_path):
    # first draft misses P3, second covers it → BeatSheet returned, covers all story panels

def test_merge_resolutions_only_accept_bible_ids(tmp_path):
    # merge returns {"unknown_1": "c1", "unknown_2": "not-a-bible-id"} → sheet.character_resolutions == {"unknown_1": "c1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_understand.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `understand.py` and both prompt files** per Interfaces and Rules. Window prompt placeholders: `$plot_so_far`, `$characters`, `$panels`, `$first`, `$last`; merge prompt placeholders: `$scenes`, `$characters`, `$unknowns`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_understand.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add engine/narration/steps/understand.py engine/narration/prompts/understand_window engine/narration/prompts/understand_merge tests/unit/narration/test_understand.py
git commit -m "feat(narration): understand step plans scenes and beats in windows"
```

---

### Task 10: Compiler, run log, and CLI

**Files:**
- Create: `engine/narration/compiler.py`, `engine/narration/__main__.py`
- Modify: `engine/narration/__init__.py` (export `NarrationCompiler`, `CompileResult`)
- Test: `tests/unit/narration/test_compiler.py`

**Interfaces:**
- Consumes: everything above; `llm_registry.get_active_provider("ollama")` (`engine.llm.registry`); `SessionLocal` (`engine.database.session`); `ProjectRecord`.
- Produces:
  - `RunLog(path: Path)` — `record(step: str, *, model: str, prompt_version: str, cache_hits: int, model_calls: int, seconds: float) -> None`; `finish(gate: Literal["pass", "review", "failed"], reasons: list[str]) -> None`. Rewrites `run.json` atomically after every call: `{"run_id", "started_at", "steps": [...], "gate", "reasons"}`. (Token counts are not exposed by the current providers; `model_calls` and `seconds` are recorded instead.)
  - `CompileResult(run_id: str, gate: Literal["pass", "review", "failed"], reasons: list[str], run_dir: Path, facts: list[PanelFacts] | None, beat_sheet: BeatSheet | None)` (dataclass).
  - `class NarrationCompiler(client: ModelClient, scheduler: ModelScheduler, cache: ArtifactCache, bibles: BibleStore)`
    - `async run(self, inputs: ChapterInputs, workspace: Path, stop_after: Literal["perceive", "understand"] = "understand") -> CompileResult`
    - `run_id = <UTC yyyymmddTHHMMSS>-<first 6 hex of sha256(project_id + timestamp)>`; `run_dir = workspace / "narration" / run_id`.
    - Writes `panel_facts.json` after ①, `beat_sheet.json` after ② (only on success), `run.json` throughout.
    - `NeedsReview` → gate `review` with its reasons; `StepModelError` → gate `failed` with `"<role>: <cause>"`; no artifact is written for a failed step.
    - Cache counts per step are measured by wrapping the cache (count `get` hits vs puts).
  - CLI: `python -m engine.narration run <project_id> [--stop-after perceive|understand]` — loads inputs with `load_chapter_inputs`, bible via `BibleStore().load(inputs.series_key)`, provider `await llm_registry.get_active_provider("ollama")`, roles via `load_roles()`, scheduler with `ollama_unloader(provider.endpoint_url)`, cache root `<workspace>/narration/cache`; prints `gate`, `run_dir`, story-panel count, scene count, needs-review panel count; exit code 0 for pass, 2 for review, 1 for failed.

- [ ] **Step 1: Write the failing tests** (FakeModelClient scripted for 3 panels + 1 window + 1 merge)

```python
def test_full_run_writes_artifacts_and_passes(tmp_path):
    # result.gate == "pass"; files panel_facts.json, beat_sheet.json, run.json exist in result.run_dir
    # run.json steps == ["perceive", "understand"] with model "qwen3.5:9b"

def test_stop_after_perceive_writes_no_beat_sheet(tmp_path):
    # stop_after="perceive" → beat_sheet is None, no beat_sheet.json, gate "pass"

def test_needs_review_sets_review_gate_with_reasons(tmp_path):
    # all panels is_story False → gate "review", reasons == ["no story panels"], no beat_sheet.json

def test_model_failure_marks_run_failed_and_rerun_resumes_from_cache(tmp_path):
    # run 1: planner queue holds StepModelError → gate "failed", reasons[0] startswith "planner", no beat_sheet.json
    # run 2 (same cache, planner scripted OK): gate "pass"; perceive step recorded with model_calls == 0 and cache_hits == 3

def test_run_json_is_valid_after_each_step(tmp_path):
    # monkeypatch understand_chapter to raise after perceive → run.json parses and contains the perceive step
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration/test_compiler.py -v`
Expected: FAIL with `ImportError: cannot import name 'NarrationCompiler'`

- [ ] **Step 3: Implement `compiler.py`, `__main__.py`, and the `__init__.py` exports** per Interfaces.

- [ ] **Step 4: Run the narration test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/narration -v`
Expected: 58 passed

- [ ] **Step 5: Run the full unit suite and confirm no new failures**

Run: `.venv\Scripts\python.exe -m pytest tests/unit -q -p no:cacheprovider --continue-on-collection-errors`
Expected: the only failures are the 27 pre-existing ones listed in the session baseline (no `tests/unit/narration` failures).

- [ ] **Step 6: Commit**

```bash
git add engine/narration/compiler.py engine/narration/__main__.py engine/narration/__init__.py tests/unit/narration/test_compiler.py
git commit -m "feat(narration): compiler runs perceive and understand with run log and CLI"
```

---

### Task 11: P1 exit check on real chapters (no code)

**Files:** none (results recorded in the PR description).

- [ ] **Step 1: Run on three library chapters with the local model**

```bash
.venv\Scripts\python.exe -m engine.narration run 098c6713-478b-4b77-917c-d2737215481b
.venv\Scripts\python.exe -m engine.narration run d20d6fd8-3545-49a9-8a5e-2156f054ef58
.venv\Scripts\python.exe -m engine.narration run 4ff3ee06-7e19-4d1a-b7f3-5f8fa3f2a73b
```

Expected: Magic Emperor 927 (39 panels) and Tales of Demons and Gods 536.1 (44 panels) exit 0 with `gate pass`; Log Into The Future Ch 5 (258 panels, exercises ≈ 10 windows) exits 0 or 2. Ch 5 must have real OCR first (its stored OCR is mock text from before the OCR fix); if not re-OCR'd, expect PanelFacts dialogue to show the mock lines and record that as a known data issue, not a compiler failure.

- [ ] **Step 2: Inspect artifacts for each run** (`<workspace>/narration/<run_id>/`)

Check and record: every story panel appears in exactly one scene; `characters_visible` uses bible ids or `unknown_<n>` only; dialogue texts match OCR; credit/ad panels have `is_story: false`; `run.json` shows per-step seconds; a second run of the same command reports `model_calls: 0` for both steps.

- [ ] **Step 3: Record timings** against spec §5.6 (① 2–3 min, ② ≈ 1 min for 40 panels) in the PR description.
