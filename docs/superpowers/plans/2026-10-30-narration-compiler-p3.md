# Narration Compiler P3 — Voice + Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a passed ScriptIR into voiced, word-aligned audio and a locked timeline. Cuts land just before the voice, with planned pauses. Project the result into the editor state, so autopilot can render a chapter through the compiler behind a feature flag.

**Architecture:** Three steps follow ⑤ REPAIR:
- **⑥ PERFORM** (role `writer`): delivery marks per line, which code maps to a TTS rate and pauses.
- **⑦ VOICE + ALIGN** (local Kokoro-82M TTS, plus local faster-whisper for word timestamps and an STT check).
- **⑧ LOCK TIMELINE** (code only): cut times from word onsets, panel holds.

A projection module writes `story_editor_state` and a `VideoScript`, so motion and render stay unchanged. Autopilot runs the compiler when `narration_engine = "compiler"`. The default stays `legacy`.

**Tech Stack:** Python 3.12+, Pydantic v2, `kokoro` (KPipeline, 24 kHz), `faster-whisper` (CPU int8), numpy, soundfile, pytest with fake audio adapters.

**Spec:** `docs/superpowers/specs/2026-10-30-narration-compiler-design.md` §1.5 (sync targets), §3.6–3.8, §4.6–4.8, §5.4, §7, §8. P1 and P2 code is in `engine/narration/` (main at `2442d3c`).

## Global Constraints
- Local only. Speech uses Kokoro-82M (cached at `models--hexgrad--Kokoro-82M`). STT and alignment use faster-whisper (cached `base`). Nothing in `engine/narration/` may call `edge_tts` or any network voice. (Today's legacy path falls back to `edge_tts_neural` because Chatterbox is not installed. The compiler path must never do this.)
- The LLM is unloaded (`scheduler.release()`) before ⑦. Kokoro and Whisper run after it, so only one heavy model is on the GPU at a time. Whisper runs on CPU int8.
- Every artifact is JSON (`ensure_ascii=False`), written atomically. Audio files are written to a temp file and then `os.replace`d.
- Voice takes are content-addressed: `sha256(text, voice, rate, pronunciation map, "kokoro-82m")`. A rerun with an unchanged line re-uses its WAV and makes no TTS call.
- Spec §1.5 targets, as written:
  - speech rate 2.5–3.0 words/s
  - cut cadence median 1.8–3.5 s
  - no panel shorter than 1.2 s or longer than 6 s
  - voice onset 80–200 ms after its cut on ≥ 98 % of cuts
  - TTS WER ≤ 5 % median and ≤ 15 % per take
- Pauses (§4.6): 150–350 ms between lines; 500–800 ms at scene turns and before `reveal` beats. Rate is 0.9–1.1.
- Each take's leading and trailing silence is normalised to 80 ms (§4.7).
- Tests are offline. Kokoro and Whisper sit behind small adapter protocols with deterministic fakes. No test loads a real model.
- Motion and render code are unchanged. The legacy autopilot path is unchanged while the flag is `legacy`.

## Rulings made while writing this plan
- faster-whisper fills both the `align` and `stt` roles. Its `word_timestamps=True` gives word onsets, and the same pass gives the STT text for WER. No wav2vec2 dependency is added. Cost if wrong: word onsets about ±50 ms less precise than a CTC aligner, which is inside the 80–200 ms window.
- The STT model is `base`, which is already cached, not `small` as the spec says. It is configurable via `narration_models.yaml` role `stt`. Cost if wrong: a slightly noisier WER check.
- A take that fails the WER check is regenerated with a slower rate (×0.95, then ×0.9), because Kokoro is deterministic and an identical retry would produce identical audio. Cost if wrong: a slightly slower line.
- Beat-word cuts (§4.8, "may") are left out of P3. Every cut is first-word onset − 120 ms. Cost if wrong: reveals cut on the line start, not on the reveal word.
- `emphasis_words` are stored in the PerformancePlan but not sent to Kokoro, which has no emphasis control. Cost if wrong: none today.
- Pronunciation: `BibleCharacter.pronunciation`, when set, replaces the name in the text sent to TTS only, never in the script. This is a respelling (e.g. "Shangguan" → "Shang-gwahn").
- Autopilot integration: with `narration_engine = "compiler"`, the `story` and `script` stages are skipped (marked complete), and the `audio` stage runs the compiler to ⑧ plus the projection. A chapter whose gate is `review` stops autopilot at the audio stage with the review reasons. It never falls back to legacy.

## Review Focus
1. **A line's audio longer than 6 s, or two lines shorter than 1.2 s together.** Holds must stay within 1.2–6 s by extending pauses, never by overlapping audio. Test in Task 5.
2. **Leading or trailing silence trimming on a take that is almost all silence, or one with no silence.** It must never produce an empty or negative-length WAV. Test in Task 3.
3. **Whisper returns zero words** (silent or garbled take). WER = 1.0 leads to a retry and then a flag. It must not raise an IndexError on onsets. Test in Task 4.
4. **Projection onto a project that already has `story_editor_state`** (`bgm_tracks`, `zoom_level` and so on). Only `scenes` and `narration_clips` are replaced. The other keys are kept, and the previous VideoScript row is kept as a prior version. Test in Task 6.
5. **Re-running after a crash in ⑦.** Already-voiced lines re-use their WAV. Only missing lines are synthesised. Test in Task 4.

---

### Task 1: Performance, voice and timeline artifacts

**Files:** Modify `engine/narration/artifacts.py`. Test `tests/unit/narration/test_artifacts.py`.

**Interfaces (all `_Strict`):**
- `LineMarks`: fields `line_id`, `emotion: str`, `energy: Literal["low","med","high"]`, `rate: float` (0.9–1.1), `pause_after_ms: int` (150–800), `emphasis_words: list[str] = []`.
- `PerformancePlan`: fields `project_id`, `script_revision: int`, `lines: list[LineMarks]` (min 1). The `line_id`s must be unique.
- `Word`: fields `text`, `start: float`, `end: float`, with `end >= start >= 0`.
- `VoiceTake`: fields `line_id`, `audio_path`, `duration: float > 0`, `words: list[Word]`, `lead_ms: int`, `tail_ms: int`, `stt_text`, `wer: float` (0–1), `tts_model`, `voice_id`, `rate`, `attempt: int` (1–3), `flagged: bool = False`.
- `TimelinePanel`: fields `panel_id`, `start`, `end`, `cut_reason: Literal["line-start","hold"]`, `scene_id`.
- `TimelineClip`: fields `line_id`, `panel_id`, `start`, `end`, `audio_path`.
- `LockedTimeline`: fields `project_id`, `duration`, `panels: list[TimelinePanel]`, `clips: list[TimelineClip]`. A validator checks:
  - panels are contiguous and non-overlapping in time, starting at 0
  - clips don't overlap
  - each clip lies inside the span of its own panel

- [ ] **Step 1:** Write failing tests:
  - `test_marks_rate_bounds`
  - `test_voice_take_word_order`
  - `test_timeline_rejects_gap_and_overlap`
  - `test_timeline_clip_inside_its_panel`
- [ ] **Step 2:** Run them and see them fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `tests/unit/narration` in full.
- [ ] **Step 5:** Commit `feat(narration): performance, voice and timeline artifacts`.

### Task 2: ⑥ PERFORM

**Files:** Create `engine/narration/steps/perform.py` and `prompts/perform_scene/v1.md`. Test `tests/unit/narration/test_perform.py`.

**Interfaces:**
- `PERFORM_PROMPT_VERSION = "v1"`. Draft: `MarksDraft(line: int, emotion: str, energy: Literal["low","med","high"], emphasis_words: list[str])`, `SceneMarksDraft(lines: list[MarksDraft])`.
- `async perform(script, sheet, facts, bible, client, scheduler, cache) -> PerformancePlan`
  - One writer call per scene, through `cached_call` and `scheduler.map("writer", ...)`.
  - Lines are P-numbered locally, as in write. The structure is checked (one mark per line, in order). There is one re-ask, then `NeedsReview`.
- `marks_to_tts(draft, beat_function: str, is_scene_last: bool, is_last: bool) -> tuple[float, int]` is code only. It returns `(rate, pause_after_ms)`:
  - Rate: 1.0 by default; 1.05 when energy is high, or the beat function is `escalate`/`payoff`; 0.95 when energy is low or the beat function is `reveal`; clamped to 0.9–1.1.
  - Pause: 250 ms by default; 650 ms at the end of a scene, or when the next line's beat is `reveal`; 0 for the last line of the chapter. The result is clamped to 150–800 when nonzero.
- `emphasis_words` are kept only if they appear in the line text.

- [ ] **Step 1:** Write failing tests:
  - `test_marks_map_to_rate_and_pause` (table of cases)
  - `test_one_mark_per_line_in_order`
  - `test_bad_structure_reasks_then_review`
  - `test_emphasis_words_filtered_to_line`
  - `test_rerun_zero_calls`
- [ ] **Steps 2–4:** RED, implement, GREEN; run `tests/unit/narration` in full.
- [ ] **Step 5:** Commit `feat(narration): ⑥ perform marks mapped to rate and pauses`.

### Task 3: Local audio adapters and signal helpers

**Files:** Create `engine/narration/runtime/audio.py`. Test `tests/unit/narration/test_audio.py`. Modify `narration_models.yaml` to add `tts: {model: "kokoro-82m", voice: "am_michael"}` and `stt: {model: "base", device: "cpu", compute_type: "int8"}`. Load these in `runtime/roles.py` as separate small models (`TtsConfig`, `SttConfig`), not as `RoleConfig`.

**Interfaces:**
- `class Tts(Protocol)`: `def synth(self, text: str, voice: str, rate: float) -> np.ndarray` (float32 mono, 24 kHz).
- `class KokoroTts`: wraps `kokoro.KPipeline(lang_code="a")`, created lazily and only once. It concatenates the generator's audio chunks.
- `class Stt(Protocol)`: `def words(self, wav_path: Path) -> tuple[str, list[Word]]`.
- `class WhisperStt`: wraps `faster_whisper.WhisperModel(model, device, compute_type)`, created lazily. It calls `transcribe(..., word_timestamps=True, language="en")`.
- `SR = 24000`, `PAD_MS = 80`
- `normalize_silence(audio: np.ndarray, sr: int = SR, pad_ms: int = PAD_MS, thresh_db: float = -40.0) -> tuple[np.ndarray, int, int]`:
  - Trims leading and trailing audio below the threshold (20 ms RMS frames), then pads with exactly `pad_ms` of zeros on each side.
  - Returns `(audio, lead_ms_before, tail_ms_before)`.
  - An all-silent input raises `ValueError("take is silent")`.
- `write_wav_atomic(path: Path, audio: np.ndarray, sr: int = SR) -> float` writes atomically and returns the duration in seconds.
- `wer(ref: str, hyp: str) -> float`: word-level Levenshtein over lower-cased, punctuation-stripped tokens. Empty `ref` raises `ValueError`. Empty `hyp` gives 1.0.
- `release_audio_models()` drops the cached KPipeline and WhisperModel.

- [ ] **Step 1:** Write failing tests (synthetic numpy signals):
  - `test_normalize_trims_and_pads_to_80ms`
  - `test_normalize_no_silence_still_pads`
  - `test_normalize_all_silent_raises`
  - `test_wer_cases` (identical gives 0; one substitution in 4 gives 0.25; empty hyp gives 1.0)
  - `test_write_wav_atomic_duration`
  - `test_audio_config_loads`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): local Kokoro and Whisper adapters with silence and WER helpers`.

### Task 4: ⑦ VOICE + ALIGN

**Files:** Create `engine/narration/steps/voice.py`. Test `tests/unit/narration/test_voice.py`.

**Interfaces:**
- `WER_LIMIT = 0.15`, `RATE_STEPS = (1.0, 0.95, 0.9)` (multipliers on the line's rate), `FLAG_LIMIT = 0.10`.
- `tts_text(text: str, bible: SeriesBible) -> str` replaces each character's name and aliases with their `pronunciation` when set, whole words only.
- `async voice_lines(script, plan, bible, tts: Tts, stt: Stt, out_dir: Path, voice: str) -> tuple[list[VoiceTake], list[str]]`. For each line, in order:
  1. Compute the key; re-use `out_dir/<key>.wav` and `<key>.json` (the VoiceTake) if both exist.
  2. Otherwise synth, `normalize_silence`, `write_wav_atomic`, run `stt.words` and compute `wer(line.text, stt_text)`.
  3. If WER > 0.15, retry with the next rate step, up to 3 attempts. Keep the best take and set `flagged` if it is still over the limit.
  4. Shift the word times so they are relative to the normalised file.

  Blocking TTS and STT calls run in `asyncio.to_thread`. The function returns the takes and the reasons. The reason is `"<n> of <m> takes failed the speech check"` when flagged takes are more than 10 % of the lines.
- Reruns: the take key includes the rate, so a line already voiced is never re-synthesised.

- [ ] **Step 1:** Write failing tests with `FakeTts` (a sine burst whose length is proportional to the word count, with 200 ms of leading silence) and `FakeStt` (returns scripted text and evenly spaced words):
  - `test_take_has_80ms_lead_and_words`
  - `test_bad_wer_retries_slower_then_flags`
  - `test_zero_words_from_stt_is_flag_not_crash`
  - `test_rerun_reuses_wavs` (the second run makes 0 synth calls)
  - `test_pronunciation_only_in_tts_text`
  - `test_too_many_flags_reason`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): ⑦ voice takes with silence normalising and speech check`.

### Task 5: ⑧ LOCK TIMELINE and sync metrics

**Files:** Create `engine/narration/steps/timeline.py`. Test `tests/unit/narration/test_timeline.py`.

**Interfaces:**
- `LEAD_CUT = 0.120` (the cut comes 120 ms before the first word), `MIN_HOLD = 1.2`, `MAX_HOLD = 6.0`.
- `lock_timeline(script, plan, takes, sheet, story_ids) -> LockedTimeline`. Pure code. Lines are in story order and each owns one panel. For line i:
  - The clip starts at `c_i` and the first-word onset is `o_i = c_i + words[0].start` (or `c_i + 0.08` if there are no words).
  - The panel cut is `t_i = o_i − 0.120`, with `t_0 = 0`, so `c_0 = 0.120 − onset_0`, at least 0.
  - Next clip start: `c_{i+1} = max(c_i + duration_i + pause_i/1000, t_i + MIN_HOLD − w_{i+1} + 0.120)`, where `w_{i+1}` is line i+1's first-word start in its file (0.08 if no words). This guarantees `t_{i+1} − t_i ≥ 1.2`.
  - Each panel lasts from `t_i` to `t_{i+1}`; the last one ends at `c_last + duration_last + 0.5`.
  - A hold longer than 6 s can only come from a long take. Keep it, and report it in `sync_metrics`.
- `sync_metrics(tl: LockedTimeline, takes, script) -> dict` returns:
  - `speech_rate` (total words ÷ total speech seconds)
  - `cut_median`
  - `holds_under_1_2`
  - `holds_over_6`
  - `onset_ok_share` (share of cuts whose voice onset is 80–200 ms after the cut)
  - `wer_median`
  - `wer_max`
  - `targets_met: dict[str, bool]` (the §1.5 targets above)

- [ ] **Step 1:** Write failing tests:
  - `test_onset_lands_120ms_after_cut`
  - `test_short_lines_are_held_to_1_2s` (pause extended, no overlap)
  - `test_pause_after_respected`
  - `test_long_take_reported_over_6s`
  - `test_metrics_targets` (built timeline: exact values)
  - `test_timeline_validates` (the result passes the `LockedTimeline` validator)
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): ⑧ lock timeline on word onsets, with sync metrics`.

### Task 6: Projection into the editor state and VideoScript

**Files:** Create `engine/narration/project.py`. Test `tests/unit/narration/test_project.py` (SQLite session; follow `test_inputs.py`).

**Interfaces:**
- `apply_to_project(db, project_id: str, tl: LockedTimeline, script: ScriptIR, sheet: BeatSheet, takes: list[VoiceTake], workspace: Path) -> str` returns the new VideoScript id.
  - Copy each take into `workspace/audio/dialogue/narr_<key>.wav` (atomic). Its `audio_url` is `/api/projects/<project_id>/audio/dialogue/<name>`.
  - Editor scenes: one per BeatSheet scene, `id = "narr_" + scene_id`. `start_time_sec` and `duration_sec` come from the panel span. Each layer is one panel:
    - `id = f"layer_{scene_id}_{k}"`
    - `source_panel_id`
    - `start_offset_sec` relative to the scene
    - `duration_sec`
    - `visible: True`
    - `transform: {x:0, y:0, scale:1, rotation:0, opacity:1, z_index:0}`
    - `motion_preset` set to `"cinematic_vertical_pan"`, matching what legacy writes today
  - Copy `background` and `camera` from the first existing scene if one exists; otherwise use the legacy defaults. Find them in `engine/pipeline/autopilot.py`, where it builds scenes, and reuse the constant or function. Don't copy it.
  - Narration clips have these fields:
    - `id = "narr_" + line_id`, `scene_id`, `text`
    - `speaker` and `voice` both `"Narrator"`
    - `emotion` (upper-cased mark), `intensity: 0.5`, `speed` = rate
    - `start_time_sec`, `duration_sec`, `scene_offset_sec`
    - `volume: 1.0`
    - `status` and `review_status` both `"APPROVED"`
    - `source_script_id`, `source_segment_ids: [segment id]`
    - `source_evidence: {panel_ids: [panel_id], text_region_ids: [], confidence: 0.9}`
    - `audio_url`
  - Replace only `scenes` and `narration_clips` in `project.settings["story_editor_state"]`. Keep every other key. Reassign the settings dict so SQLAlchemy sees the change.
  - Add a new `VideoScriptRecord` (version = max + 1, status `"APPROVED"`, `adaptation_profile = "narration_compiler"`) with one `ScriptSegmentRecord` per line: type `NARRATOR`, sequence, text, scene_id, estimated start, end and duration from the timeline, and `source_evidence` panel ids. Older VideoScripts stay.

- [ ] **Step 1:** Write failing tests:
  - `test_projection_replaces_only_scenes_and_clips`
  - `test_clip_and_layer_times_match_timeline`
  - `test_new_video_script_version_keeps_old`
  - `test_audio_copied_and_url_shape`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): project locked timeline into editor state and VideoScript`.

### Task 7: Compiler and CLI wiring

**Files:** Modify `engine/narration/compiler.py` and `__main__.py`. Tests in `test_compiler.py` and `test_main.py`.

**Interfaces:**
- `NarrationCompiler.__init__` takes optional `tts: Tts | None` and `stt: Stt | None`. When they are None, it creates `KokoroTts` and `WhisperStt` from the audio config.
- `run(..., stop_after: Literal["perceive","understand","write","perform","voice","timeline"] = "timeline")`.
  - After a `pass` from repair, run perform, then `await scheduler.release()`, then voice, then timeline.
  - Steps are recorded in `run.json` as `perform`, `voice` and `timeline`. The voice and timeline steps record `model` as the TTS and STT model names.
  - Run-dir files: `performance.json`, `takes.json`, `timeline.json` and `sync.json` (from `sync_metrics`).
  - A `review` reason from voice gives gate `review`.
  - `CompileResult` gains `timeline` and `sync`.
  - `release_audio_models()` is called in the `finally`.
- CLI:
  - `run` accepts the new `--stop-after` values and prints the sync metrics.
  - `run --apply` calls `apply_to_project` on a pass and prints the VideoScript id.

- [ ] **Step 1:** Write failing tests:
  - `test_full_run_to_timeline_with_fake_audio`
  - `test_llm_released_before_voice` (the unloader records the order)
  - `test_voice_review_gate`
  - `test_cli_apply_projects`
- [ ] **Steps 2–4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(narration): compile through perform, voice and timeline`.

### Task 8: Autopilot behind the `narration_engine` flag

**Files:** Modify `engine/config/settings.py` (add `narration_engine: Literal["legacy","compiler"] = "legacy"`, following the existing env-prefix pattern) and `engine/pipeline/autopilot.py` (the `story`, `script` and `audio` stages only). Create `engine/narration/autopilot_stage.py`. Test `tests/unit/narration/test_autopilot_stage.py`.

**Interfaces:**
- `async run_compiler_stage(project_id: str) -> None` loads the inputs, builds the compiler as the CLI does (reusing `_local_provider` and `_make_compiler` from `__main__`, moved into this module or a shared one), runs it to `timeline`, and on pass calls `apply_to_project`.
  - On `review` it raises `NarrationNeedsReview(reasons)`; on `failed` it raises `RuntimeError(reasons)`.
- In `autopilot.py`, when `settings.narration_engine == "compiler"`:
  - `_run_stage_story` and `_run_stage_script` log "skipped: narration compiler" and return.
  - `_run_stage_audio` calls `run_compiler_stage` and returns. A `NarrationNeedsReview` becomes the stage failure message `"Narration needs review: <reasons>"`.
  - With the flag set to `legacy`, nothing changes.
  - Keep the diff to a few guarded lines at the top of each of the three methods.

- [ ] **Step 1:** Write failing tests:
  - `test_flag_default_is_legacy`
  - `test_compiler_stage_applies_on_pass` (fake compiler)
  - `test_compiler_stage_review_raises`
  - `test_autopilot_story_script_skipped_under_flag` (call the methods on a minimal runner stub, or assert via monkeypatch that the legacy bodies are not entered)
- [ ] **Steps 2–4:** RED, implement, GREEN. Also run `tests/unit` fully once, to show the legacy suite is untouched.
- [ ] **Step 5:** Commit `feat(narration): autopilot runs the compiler behind narration_engine`.

### Task 9: Exit check (real models, real render)

**Files:** none, unless a defect is found.

- [ ] **Step 1:** `python -m engine.narration run <id> --apply` on Ch927 (`098c6713-…`) and TDG 536.1 (`d20d6fd8-…`). Record for each:
  - gate
  - lines
  - flagged takes
  - every value in `sync.json`
  - wall time per step
- [ ] **Step 2:** Render both with the existing autopilot render path (`video_only`, `standard_1080p`), with `PANELFLOW_NARRATION_ENGINE=compiler` (or the settings env name chosen in Task 8). Confirm the MP4 duration ≈ timeline duration (±0.5 s).
- [ ] **Step 3:** P3 exits when, on both chapters (§1.5):
  - speech rate is 2.5–3.0
  - cut median is 1.8–3.5 s
  - there are 0 holds under 1.2 s
  - onset_ok_share ≥ 0.98
  - WER median ≤ 0.05
  - a full chapter renders through the compiler

  Misses become findings for the final fix wave.
- [ ] **Step 4:** Watch the first 30 s of each render (extract frames at the cuts with ffmpeg). Confirm the picture changes just before the voice starts and lines have audible gaps.
