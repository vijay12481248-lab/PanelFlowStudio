# ChronoFlow "New Video" Start Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "New Video" opens a 3-step wizard (start mode, length, story idea) that builds a Storyboard of N cards; each card renders in its own mode, is approved or redone, and the next card continues from the approved clip's tail frame.

**Architecture:** Pure planning/validation logic lives in a new `engine/chronoflow/start_modes.py`; clip rendering dispatch in `engine/chronoflow/scene_render.py` (existing `pipeline.build_h3_prompt` for first-frame modes, `engine/original/h3_modes.make_clip` for text / last / first+last / reference). The router gets thin endpoints. The wizard and the approval gate are plain JS in a new `static/nle/newvideo.js` (loaded like the other NLE scripts); `index.html` gets the popup markup and card changes.

**Tech Stack:** Python 3.14 FastAPI, pytest (`.venv\Scripts\python.exe -m pytest ... -p no:cacheprovider`), vanilla JS tested with `node --test tests/js`, ComfyUI H3 workflows, Ollama `qwen3.5:9b`.

**Spec:** `docs/superpowers/specs/2026-11-15-video-start-modes-design.md`

## Global Constraints
- Local-first; never fall back silently to a different mode, cloud or mock (AGENTS.md). A card missing a required frame is an error naming the card and slot.
- One text-to-image path: frame-slot Generate calls the existing `POST /api/chronoflow/generate_image` (`ArtEngine`). Do not add another.
- Clip length 5.17 s (124 frames); other lengths snap via `h3_modes.clip_seconds`. `T2VA_SIZE = (960, 544)`; 9:16 uses `(544, 960)`.
- Reference mode = 1 or 2 pictures (`make_clip` limit). The old `POST /generate` route and its 9-ref path stay untouched.
- Generic only: no per-story prompts or genre tuning anywhere.
- Mode ids (exact strings): `text`, `first`, `first_last`, `last`, `reference`, `from_video`.
- Commit only the files each task lists; the tree has unrelated dirty files.

## Review Focus
1. A card's required frame file is missing from `COMFY_INPUT_DIR` (old code silently rendered text-to-video): render returns HTTP 400 naming the file. Test in Task 2.
2. Length that is not a multiple of 5.17 s (e.g. 20 s, 7 s) or absurd (0, 5000 s): count = `max(1, round(length/5.17))`, length outside 1..600 s is rejected with 400. Test in Task 1.
3. LLM draft returns the wrong number of lines, empty lines or garbage: 502 with the reason, no padding with canned text. Test in Task 3.
4. Redo of card N after card N+1 already rendered from N's old tail: N+1 (and chained followers) become `stale`, never silently kept. Test in Task 4.
5. Cards reordered, deleted or inserted: the gate and tail inheritance re-read the previous card in current order; a deleted dependency never leaves a card stuck "waiting". Test in Task 4.

---

### Task 1: Mode table and plan builder

**Files:**
- Create: `engine/chronoflow/start_modes.py`
- Test: `tests/unit/test_chronoflow_start_modes.py`

**Interfaces:**
- Produces:
  - `START_MODES: tuple[str, ...]` = the six ids above.
  - `SEG_SECONDS = 5.17`, `MAX_LENGTH_SECONDS = 600`.
  - `slots_for(mode: str) -> tuple[str, ...]`: `text` -> `()`, `first`/`from_video` -> `("first",)`, `first_last` -> `("first","last")`, `last` -> `("last",)`, `reference` -> `("ref1","ref2")`. Unknown mode raises `ValueError`.
  - `segment_count(length_seconds: float) -> int`: `max(1, round(length/SEG_SECONDS))`; raises `ValueError` outside 1..600.
  - `build_plan(mode: str, length_seconds: float, title: str = "Untitled Video") -> dict`: the screenplay dict `{title, duration, protagonist:{}, anchor_images:{}, parent_path:"", folders:[], scenes:[...]}` saved by `/screenplay/save`. Each scene: `shot_index, title, shot_type:"Medium Tracking", duration:5.2 (last one the remainder, min 1.0), start_mode, workflow, prompt:"", first_frame:"", last_frame:"", ref_images:[], first_prompt:"", last_prompt:"", state:"empty", approved:False, inherits_tail:bool`. `inherits_tail` is True for scene index >= 1 when its mode takes a `first` slot (`first`, `from_video`) or is `text` (later segments of a text video continue from tail frames; their effective mode is `first`).
  - `effective_mode(scene: dict, index: int) -> str`: a `text` scene with `index >= 1` and `inherits_tail` is `first`; otherwise `scene["start_mode"]`.
  - `missing_inputs(scene: dict, index: int) -> list[str]`: slot names the effective mode needs that are empty, treating `first` as satisfied when `inherits_tail` and the scene has no own frame (the tail is supplied at render time, so this returns `[]` for it); `reference` needs at least `ref1`; empty `prompt` returns `["prompt"]`.

- [ ] **Step 1: Write failing tests** in `tests/unit/test_chronoflow_start_modes.py`: `test_segment_count_rounds_and_clamps` (`segment_count(300) == 58`, `segment_count(15) == 3`, `segment_count(1) == 1`; `pytest.raises(ValueError)` for 0 and 5000), `test_slots_for_each_mode` (all six ids; unknown raises), `test_build_plan_five_minutes` (58 scenes, `shot_index` 1..58, scene 1 `inherits_tail` False for `first_last`, scene 2 True for `first`, durations sum within 5.2 of 300), `test_text_plan_continues_from_tail` (`effective_mode(scene2, 1) == "first"`, `effective_mode(scene1, 0) == "text"`), `test_missing_inputs_names_slots` (`first_last` scene with only a first frame -> `["last"]`; reference with no refs -> `["ref1"]`; empty prompt -> `"prompt"` included; `first` scene 2 with inherits_tail and no frame -> no `first`).
- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/unit/test_chronoflow_start_modes.py -p no:cacheprovider` — expect FAIL (module missing).
- [ ] **Step 3: Implement** the functions above in `engine/chronoflow/start_modes.py`. Scene `workflow` field: `reference` for `reference`, `flf2v` for `first_last`, else `sliding_window` (display only; routing uses `start_mode`).
- [ ] **Step 4: Run the same command** — expect all PASS.
- [ ] **Step 5: Commit** `git add engine/chronoflow/start_modes.py tests/unit/test_chronoflow_start_modes.py` / `git commit -m "feat(chronoflow): start-mode table and segment plan builder"`.

### Task 2: Per-mode render dispatch

**Files:**
- Create: `engine/chronoflow/scene_render.py`
- Modify: `engine/api/routers/chronoflow.py` (`RenderShotRequest` at ~301, `render_storyboard_shot` at ~1702)
- Test: `tests/unit/test_chronoflow_scene_render.py`

**Interfaces:**
- Consumes: `start_modes.effective_mode`, `start_modes.missing_inputs`, `h3_modes.make_clip`, `h3_modes.t2va_prompt/fl2va_prompt/l2va_prompt/ref2va_prompt`, `h3_modes.clip_seconds`, `ChronoFlowPipeline.build_h3_prompt / execute_prompt / extract_tail_frame`.
- Produces: `async def render_scene(pipeline, scene: dict, index: int, *, width: int, height: int, steps: int, lora_choice: str, out_dir: Path, input_dir: Path, tail_name: str) -> tuple[Path, str | None]`: returns the mp4 path in `out_dir` and the tail-frame filename written to `input_dir` (None if extraction failed). `RenderShotRequest` is unchanged: `shot_index` (1-based) is the card position, and the scene dict carries `start_mode`, `prev_tail` (filename of the previous approved clip's tail frame, set by the client) and the fields from Task 1. The `/storyboard/render_shot` response gains `tail_frame: str | None`.

- [ ] **Step 1: Write failing tests** with `monkeypatch` on `engine.original.h3_modes.make_clip` (record kwargs, return `b"mp4"`) and a fake pipeline object: `test_text_mode_uses_t2va_with_size` (mode `text`, index 0 -> `make_clip("t2va", ...)`, `size == (960, 544)`; 768x1344 request -> `(544, 960)`), `test_first_last_passes_both_frames`, `test_last_only_uses_l2va`, `test_reference_passes_one_or_two_refs` (three refs -> error), `test_first_mode_uses_build_h3_prompt_not_make_clip`, `test_missing_frame_file_is_400` (scene names a frame that does not exist in `input_dir` -> `HTTPException(400)` whose detail contains the file name; nothing rendered), `test_duration_is_honored` (scene duration 3.0 -> `make_clip(seconds=3.0)`; first-frame path gets `length = snap_frames(3.0)`), `test_inherited_tail_used_when_first_empty` (index 1, `inherits_tail`, `first_frame == ""`, `prev_tail` file present -> used; absent -> 400 "previous shot has no tail frame").
- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/unit/test_chronoflow_scene_render.py -p no:cacheprovider` — expect FAIL.
- [ ] **Step 3: Implement `render_scene`.** Resolve effective mode; call `missing_inputs`; map frame names to `input_dir / name` and raise `HTTPException(400, detail=...)` if a named file does not exist (never degrade the mode). `make_clip` is blocking: run it with `asyncio.to_thread`. For `h3_modes` routes wrap the card's plain action text with the matching prompt builder unless it already contains `integrated_multimodal_description` or `detailed_description:` (then send as written); `ref2va` subject tuples: `("the character shown in the reference picture", n, "fully_preserved", "face, hair, outfit")` per ref. For `first`: existing `pipeline.build_h3_prompt(..., workflow_mode="sliding_window", first_frame_filename=...)` with `length` from the scene duration. Write mp4 bytes / copy graph output to `out_dir`, then `pipeline.extract_tail_frame` into `input_dir / tail_name`.
- [ ] **Step 4: Modify `render_storyboard_shot`** to build the scene's previous-tail name (`chronoflow_tail_<scene id or shot_index-1>`: use `scene.get("prev_tail")` supplied by the client), call `render_scene`, return `{success, shot_index, video_url, filename, tail_frame}`. Remove the old silent "generating text-to-video instead" branch. Run `tests/unit/test_chronoflow_storyboard_api.py` and `tests/unit/test_chronoflow_api.py` too — they must still pass.
- [ ] **Step 5: Run** the three test files — expect PASS. **Commit** (`engine/chronoflow/scene_render.py`, `engine/api/routers/chronoflow.py`, `tests/unit/test_chronoflow_scene_render.py`): `feat(chronoflow): render storyboard cards per start mode`.

### Task 3: Plan, draft-prompts and tail-frame endpoints

**Files:**
- Modify: `engine/api/routers/chronoflow.py` (after `ai_director_plan`)
- Modify: `engine/chronoflow/start_modes.py` (add `parse_draft(text: str, n: int) -> list[str]`)
- Test: `tests/unit/test_chronoflow_start_modes.py`, `tests/unit/test_chronoflow_storyboard_api.py`

**Interfaces:**
- Consumes: `start_modes.build_plan`, `OllamaProvider.generate_text(prompt=..., system_prompt=...)`, `pipeline.extract_tail_frame`.
- Produces:
  - `POST /storyboard/plan` body `{mode, length_seconds, title}` -> `build_plan(...)`; `ValueError` -> 400.
  - `POST /storyboard/draft_prompts` body `{idea, count, mode}` -> `{success, prompts: list[str]}` (len == count); count mismatch / empty line / provider error -> 502 with reason.
  - `POST /storyboard/tail_frame` body `{video: str}` (a filename under `STUDIO_OUTPUT_DIR` or the library clip's bare name) -> `{success, filename}` tail PNG written to `COMFY_INPUT_DIR` (for "From a video"). Bare names only: reject path separators with 400.
  - `parse_draft(text, n) -> list[str]`: the LLM is asked for a JSON array of n strings; this strips code fences, `json.loads`, checks `len == n` and every item non-empty, else raises `ValueError`.

- [ ] **Step 1: Write failing tests**: `test_parse_draft_accepts_fenced_json`, `test_parse_draft_rejects_wrong_count_and_blank_items` (in the start_modes test file); API tests with a monkeypatched provider: plan 300 s returns 58 scenes; plan 0 s -> 400; draft with provider returning 3 items for count 4 -> 502; `tail_frame` with `"..\\x.mp4"` -> 400.
- [ ] **Step 2: Run** both test files — expect FAIL.
- [ ] **Step 3: Implement.** Draft system prompt (generic, no genre text): each item is one plain-language action for one 5-second shot, each continuing the previous, naming subject, setting, motion and camera, no dialogue; reply with only a JSON array of `count` strings. Use `OllamaProvider(...).generate_text` the way `autogen_prompt` does; no fallback to canned text.
- [ ] **Step 4: Run** both test files — expect PASS.
- [ ] **Step 5: Commit** `feat(chronoflow): storyboard plan, AI prompt draft and tail-frame endpoints`.

### Task 4: Wizard logic and approval gate (JS, tested)

**Files:**
- Create: `engine/chronoflow/static/nle/newvideo.js`
- Test: `tests/js/chronoflow_newvideo.test.js`

**Interfaces:**
- Produces (object `NewVideo`, also `module.exports` when `module` exists, like `grade.js`):
  - `segmentCount(seconds) -> number` (same rule as the server: `Math.max(1, Math.round(seconds/5.17))`) and `lengthLabel(seconds) -> string` ("5 min = 58 segments x 5.17 s").
  - `slotsFor(mode) -> string[]` (same table as the server).
  - `canRender(scenes, i) -> {ok: boolean, reason: string}`: ok unless `scenes[i].inherits_tail` and has no own `first_frame` and the nearest previous scene (current order) is not `approved`; for `i === 0` always ok. A scene with its own frames is always ok.
  - `markRedo(scenes, i)`: sets `scenes[i].approved = false, state = "ready"`, clears its `rendered_video`, and sets `state = "stale"` on every following scene that is chained (`inherits_tail` and no own `first_frame`) up to the first scene that is not chained.
  - `approve(scenes, i)`: sets `approved = true, state = "approved"`.
  - `mount(api: {post(path, body), onPlanReady(screenplay)})`: wizard open/close, step navigation, calls `/storyboard/plan` then optional `/storyboard/draft_prompts`, then `onPlanReady`.

- [ ] **Step 1: Write failing tests** (`node:test`, same header style as `chronoflow_grade.test.js`): `segmentCount(300) === 58`, `lengthLabel(300)` contains "58 segments", `canRender` blocks scene 2 until scene 1 approved, allows scene 2 once approved, allows a scene with its own `first_frame` regardless, ignores a deleted dependency (scenes = [a(approved), c(inherits)] -> c ok), `markRedo` on scene 1 turns chained scenes 2-3 `stale` but leaves an independent scene 4 untouched.
- [ ] **Step 2: Run** `node --test tests/js` — expect FAIL for the new file.
- [ ] **Step 3: Implement** `newvideo.js`. Pure functions first; `mount` builds no markup itself: it wires the element ids that Task 5 defines (`nvStep1`, `nvStep2`, `nvStep3`, `nvModeCards`, `nvLengthPreset`, `nvLengthCustom`, `nvLengthLabel`, `nvIdea`, `nvDraft`, `nvCreate`).
- [ ] **Step 4: Run** `node --test tests/js` — expect all PASS.
- [ ] **Step 5: Commit** `feat(chronoflow): new-video wizard logic and approval gate`.

### Task 5: Wizard popup in the studio

**Files:**
- Modify: `engine/chronoflow/static/index.html` (`#promptModal` at ~4716, `loadNLEAssets` list at ~11812, the "Start New Video Production" buttons)

**Interfaces:**
- Consumes: `NewVideo.mount`, `/storyboard/plan`, `/storyboard/draft_prompts`, existing `loadScreenplay`/storyboard state (`storyboardScenes`, `currentScreenplay`, `renderStoryboardUI`, `saveCurrentStoryboard`, `switchTab`).

- [ ] **Step 1: Replace the contents of `#promptModal`** with the three steps (ids from Task 4): step 1 six mode cards with a one-line description each; step 2 length presets 15 s / 30 s / 1 min / 5 min / custom, live `nvLengthLabel`, format 16:9 / 9:16, and a "More" disclosure holding speed (4-step / 8-step); step 3 story idea, "Draft all prompts with AI" checkbox, Create button. Keep `openPromptModal/closePromptModal/handlePromptModalOverlayClick`. Remove the Cat/Cyberpunk/Anime presets and the old inline resolution/duration selects; keep `startNewProductionRun` defined (agents may call it) but unreferenced by the UI.
- [ ] **Step 2: Add `'newvideo.js'`** to the script list in `loadNLEAssets` and call `NewVideo.mount` after the other mounts in `initApp`. `onPlanReady` loads the screenplay into `storyboardScenes`/`currentScreenplay`, saves it with `saveCurrentStoryboard`, switches to the Storyboard tab, opens card 1.
- [ ] **Step 3: Rename** the button labels to "New Video" (the two `renderTriggerButton` strings at ~6031 and ~6263/6271 and the markup at ~4796 become the wizard's Create button text "Create storyboard").
- [ ] **Step 4: Verify in the in-app browser** (engine on :8765): open the studio, click New Video, walk the three steps, create a 5 min text plan, see 58 cards. Screenshot each step. Console must show no errors.
- [ ] **Step 5: Commit** `feat(chronoflow): New Video wizard popup`.

### Task 6: Cards, frame slots, review states

**Files:**
- Modify: `engine/chronoflow/static/index.html` (`renderStoryboardGrid` ~10829, `openBeatEditor` ~11026, `renderSingleStoryboardShot` ~11276, `addNewStoryboardBeat` ~11123)
- Modify: `engine/chronoflow/static/nle/newvideo.js` (slot helpers)

**Interfaces:**
- Consumes: `canRender`, `approve`, `markRedo`, `slotsFor`; endpoints `POST /upload_image` (header `x-filename`, raw body), `POST /generate_image` (`prompt, width, height, workflow_id` default Qwen), `POST /storyboard/tail_frame`, `POST /storyboard/render_shot`.
- Produces: `NewVideo.slotWidget(sceneIdx, slotName) -> html` (thumbnail or empty, buttons Upload / Vault / Generate); `NewVideo.generateSlotImage(sceneIdx, slotName)` (prompt box -> `/generate_image` -> preview -> Accept writes `first_frame` / `last_frame` / `ref_images[n]`).

- [ ] **Step 1: Card** shows mode chip (effective mode, "First frame: from Shot N tail" when inherited), the slots for the mode with thumbnails, a state badge (`empty / ready / rendering / review / approved / stale`) and the 960x544 warning chip for `text`/`reference` cards in a 1344x768 video. Cards keep move/delete/link/inpaint buttons.
- [ ] **Step 2: Beat editor** gets a mode selector (changing it re-derives slots and `inherits_tail`) and the image-prompt fields `first_prompt` / `last_prompt` next to their slots.
- [ ] **Step 3: `renderSingleStoryboardShot`** checks `canRender` (disabled button with the reason as tooltip), sends `scene.start_mode`, `duration`, the video size and `prev_tail`, shows the spinner state, replaces the blocking `alert` with the card's review state: video preview plus **Approve** and **Redo** (Redo opens the prompt for editing and calls `markRedo`). On success stores `rendered_video` and the returned `tail_frame` on the scene as the next card's `prev_tail`, then `saveCurrentStoryboard()`.
- [ ] **Step 3b:** "From a video" step 1 option opens the media library picker, calls `/storyboard/tail_frame`, and sets card 1's `first_frame`.
- [ ] **Step 4: Verify in the in-app browser** without rendering (no fake render path; real renders happen in Task 7): check layout at 58 cards, slot Upload and Generate against the real engine, gate tooltip on card 2, console clean.
- [ ] **Step 5: Run** `node --test tests/js` and the three unit test files from Tasks 1-3 — all PASS. **Commit** `feat(chronoflow): storyboard cards with mode slots and per-shot review`.

### Task 7: Real-data verification and docs

**Files:**
- Modify: `AGENTS.md` ("What exists", one line), `docs/superpowers/specs/2026-11-15-video-start-modes-design.md` (add a "Measured" section)

- [ ] **Step 1: Start the stack** (ComfyUI with `PANELFLOW_COMFYUI_WORKFLOW_DIR` set per AGENTS.md; engine on :8765). Confirm `ComfyWorkflowRegistry.preflight` is ready for `fastvideo_h3_film_t2va`, `..._fl2va`, `..._l2va`, `fastvideo_h3_omniref`; if any model is missing, stop and report (downloads need the owner's approval).
- [ ] **Step 2: Render and watch** one real clip per mode through the UI: text, first+last, last-only, reference (2 pictures, one of them generated with the slot's Generate), plus a 3-card first-frame chain through Approve/Redo. For each: open the mp4, extract a few frames, say what is wrong (identity drift, zoom, invented speech). Record render time and VRAM.
- [ ] **Step 3: Mixed sizes:** put a 960x544 text clip and a 1344x768 clip on the timeline and run a Deliver render; report whether it scales or letterboxes. If it breaks, fix in `engine/chronoflow/deliver.py` with a test, else only document.
- [ ] **Step 4: Write the "Measured" section** in the spec (what worked, what did not, timings, anything not verified, e.g. 9:16 sizes) and one line in AGENTS.md pointing to the spec.
- [ ] **Step 5: Run** the full `tests/unit` suite for chronoflow and h3_modes: `.venv\Scripts\python.exe -m pytest tests/unit -k "chronoflow or h3_modes" -p no:cacheprovider` plus `node --test tests/js` — all PASS. **Commit** `docs(chronoflow): measured results for start modes`.
