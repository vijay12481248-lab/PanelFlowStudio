# Audio Studio Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cue-sheet audio engine that takes a real video, drafts and sources sound cues (ACE-Step music, Openverse CC0 clips, code-synthesised effects), places each hit on its frame, checks, mixes with ducking, and exports a loudness-correct master plus stems, driven by REST and MCP.

**Architecture:** New package `engine/audio/studio/`: a versioned `SoundPlan` JSON (cue sheet) is the single source of truth. An `AudioEngine` asks small `Provider` classes for candidates (Auto picks, Ask-me leaves the choice), every take is measured (onset/peak) and placed by `adelay`, and an ffmpeg filter graph builds the mix and stems. REST router and MCP tools are thin wrappers over the same functions. No UI in this phase.

**Tech Stack:** Python 3.14, FastAPI, pydantic, numpy/soundfile/scipy (installed), ffmpeg 9.0.1 (has `adelay`, `amix`, `sidechaincompress`, `acompressor`, `alimiter`, `loudnorm`, `ebur128`, `silencedetect`, `equalizer`; checked), existing `local_music_provider` (ACE-Step), `engine.mcp.registry`.

**Spec:** `docs/superpowers/specs/2026-11-15-audio-studio-design.md`

## Global Constraints

- Local-first. A provider that is missing or down reports it (`Availability.ok=False, reason`); **never** substitute another source silently and never fake a sound.
- Licence policy: CC0 accepted automatically; `CC-BY` only if `plan.allow_cc_by` is true; anything else (CC-NC, unknown, empty) is refused. Provenance (`source, licence, url, model, seed, author`) is stored on every take.
- GPU audio work (ACE-Step) takes the GPU slot via `SystemResourceManager.acquire_gpu_slot` like `engine/api/routers/music.py:generate_music_for_cue`, one job at a time.
- No model or weight downloads in this phase. Openverse clips: at most 5 candidates per cue, each file at most 5 MB, only `audio/*` content.
- Plan and take ids match `^[A-Za-z0-9_-]{1,64}$`; take files live under `app_data_dir/audio_studio/plans/<plan_id>/takes/`.
- Stems must sum to the premix (null test below -60 dBFS residual). Master default `-14` LUFS, true peak `-1.5` dBTP (same as `engine/chronoflow/deliver.py:loudnorm_filter`).
- Tests: `.venv\Scripts\python.exe -m pytest tests/unit/audio_studio -p no:cacheprovider -q`. State is isolated by `tests/conftest.py`.
- Commit only the files named in each task (the tree has unrelated dirty files). Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- I cannot hear audio. "Verified" in this phase means measurements, spectrograms and rule checks; the owner listens.

## Review Focus

- Video with no audio stream, or a plan with no dialogue: mix and export must work with no ducking, not crash.
- Variable or fractional fps (29.97, 23.976): `hit_t` snaps to the frame grid and stays inside `[0, duration]`.
- Hit earlier than the take's own onset (negative start): trim the take's head, do not crash or shift the hit.
- Take shorter than a bed cue (`t_out` set): loop-fade to fill; cue past the video end is clipped, not an error.
- Openverse offline, zero CC0 results, oversize file, or non-audio content type: cue ends `failed` with a stated reason, no file kept, no fake sound.
- Plan id or take id containing `..` or a path separator: rejected.

## File Structure

```
engine/audio/studio/__init__.py
  plan.py        SoundPlan/Track/Cue/Take models, snap(), PlanStore (versioned JSON)
  licence.py     licence_allowed()
  measure.py     measure_take(): onset/peak/level/clipping from a wav/mp3
  place.py       placement_for(): start/trim for an anchor
  sources/base.py      Candidate, Availability, Provider protocol
  sources/synth.py     deterministic code-synthesised effect classes
  sources/openverse.py CC0 search + capped fetch
  sources/music.py     ACE-Step wrapper
  engine.py      AudioEngine: route cue -> providers, Auto/Ask modes, pick()
  spot.py        scene-cut detection + draft cues
  qa.py          rule checks + rendered placement-error metric
  mix.py         ffmpeg filter graph, ducking, loudnorm, stems rendering
  stems.py       export dir: stems, M&E, cue sheet json/csv, credits.txt
engine/api/routers/audio_studio.py   REST   (register in engine/api/app.py)
engine/mcp/tools/audio_studio_tools.py   MCP (add to engine/mcp/tools/__init__.py)
.claude/skills/audio-studio-production/SKILL.md
docs/AUDIO_STUDIO.md
tests/unit/audio_studio/test_*.py   (one per module, plus __init__.py)
```

---

### Task 1: Sound Plan model, store and licence policy

**Files:** Create `engine/audio/studio/{__init__,plan,licence}.py`, `tests/unit/audio_studio/{__init__,test_plan.py}`

**Interfaces — Produces:**
- `licence_allowed(licence: str, allow_cc_by: bool) -> bool`
- `snap(t: float, fps: float) -> float` (nearest frame time, `round(t*fps)/fps`)
- pydantic models `Provenance`, `Take`, `Candidate`, `Cue`, `Track`, `SoundPlan` with the fields in the spec section 5.1 plus: `Cue.anchor: Literal["onset","peak"]="onset"`, `Cue.candidates: list[Candidate]`, `Cue.status: Literal["draft","needs_pick","ready","failed"]`, `Cue.reason: str|None`, `Cue.placement_error_ms: float|None`; `SoundPlan.mode: Literal["auto","ask"]="auto"`, `allow_cc_by: bool=False`, `dialogue_path: str|None`, `version: int`
- `PlanStore(root: Path)`: `create(video_path, fps, duration, **kw) -> SoundPlan`, `load(plan_id) -> SoundPlan`, `save(plan, note="") -> SoundPlan` (atomic write, `version += 1`), `take_dir(plan_id) -> Path`. Default tracks created: `dialogue, music, sfx, ambience, foley`, music `duck_under="dialogue"`.

- [ ] **Step 1: Tests (fail first).** `test_licence_allowed_cc0_always`, `_cc_by_only_when_flag`, `_refuses_nc_unknown_empty` (`"by-nc"`, `"cc-by-nc-sa"`, `"unknown"`, `""` all False even with flag); `test_snap_29_97` (`snap(1.0, 29.97)` == `30/29.97`); `test_store_roundtrip_bumps_version` (save twice → version 2, load equals saved); `test_store_rejects_bad_ids` (`"../x"`, `"a/b"`, `""` raise `ValueError`); `test_default_tracks_and_ducking`.
- [ ] **Step 2:** Run, expect FAIL (module missing).
- [ ] **Step 3: Implement** the models and store; licence match is case-insensitive on normalised slug (`cc0`, `cc0-1.0`, `pdm` count as CC0; `by`, `cc-by`, `cc-by-4.0` as CC-BY, but `by-nc*`/`by-sa*` strings containing `nc` are refused). Store root default `settings.app_data_dir / "audio_studio" / "plans"`.
- [ ] **Step 4:** Run, expect PASS.
- [ ] **Step 5: Commit** `feat(audio-studio): sound plan model, store and licence policy`.

### Task 2: Measuring and placing a take

**Files:** Create `engine/audio/studio/{measure,place}.py`, `tests/unit/audio_studio/test_measure_place.py`

**Interfaces — Produces:**
- `measure_take(path: Path) -> Measure` (`Measure`: `onset_s, peak_s, duration_s, peak_db, rms_db, clipped_samples: int`). Decode with `soundfile`; fall back to an ffmpeg decode to wav for mp3. Envelope = 5 ms RMS windows on the mono mix; **onset** = first window ≥ 10 % of the peak window's RMS, refined back to the first sample above 2 % of peak amplitude within the 20 ms before it.
- `placement_for(hit_t: float, anchor_s: float) -> Placement` (`start_s: float` ≥ 0, `trim_s: float` ≥ 0): `start_s = hit_t - anchor_s` if ≥ 0 else `start_s=0, trim_s=-(hit_t-anchor_s)`.

- [ ] **Step 1: Tests.** Build wavs in `tmp_path` with numpy: 1 s silence + 50 ms 1 kHz burst at 0.5 s. `test_onset_within_5ms` (`abs(onset_s-0.5)<0.005`, `peak_s` within 60 ms after); `test_clipping_counted` (burst at 1.0 → `clipped_samples>0`); `test_silent_file_is_reported` (`peak_db <= -90`, `onset_s == 0.0`); `test_placement_positive`, `test_placement_negative_trims` (`hit_t=0.1, anchor_s=0.3` → `start_s=0, trim_s≈0.2`).
- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Implement as specified above.
- [ ] **Step 4:** Run, expect PASS.
- [ ] **Step 5: Commit** `feat(audio-studio): measure take onset/peak and compute placement`.

### Task 3: Provider interface and code-synth source

**Files:** Create `engine/audio/studio/sources/{__init__,base,synth}.py`, `tests/unit/audio_studio/test_synth.py`

**Interfaces — Produces:**
- `base.py`: `Availability(ok: bool, reason: str|None)`; `Provider` protocol: `name: str`, `availability() -> Availability`, `find(cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 3) -> list[Candidate]` (each candidate's file already written under `out_dir`; raises nothing for "no result", returns `[]`).
- `synth.py`: `SynthProvider` with classes `SYNTH_KINDS = {"whoosh","impact","click","pop","ding","riser","drop","noise_bed"}`; `render(kind: str, duration: float, seed: int, sr: int = 48000) -> np.ndarray` (mono float32, peak ≤ 0.9, deterministic per seed); `find` renders `limit` seeds when `cue.kind in SYNTH_KINDS`, else `[]`. Provenance `source="synth", licence="CC0", model="panelflow-synth-v1", seed`. Port the generation ideas from `tools/design_funny_sfx.py` / `tools/build_sound_design.py` (whoosh = filtered-noise sweep, impact = decaying low sine + noise burst, riser, drop), written as generic functions, not tied to one video.

- [ ] **Step 1: Tests.** `test_every_kind_renders_and_is_deterministic` (same seed twice equal; different seeds differ); `test_impact_has_fast_attack` (`measure_take` onset within 10 ms of file start, `peak_db > -3`); `test_unknown_kind_returns_empty`; `test_whoosh_peak_is_late` (peak_s > 40 % of duration, so the `peak` anchor makes sense); `test_availability_ok`.
- [ ] **Step 2:** Run, expect FAIL. **Step 3:** Implement. **Step 4:** Run, expect PASS.
- [ ] **Step 5: Commit** `feat(audio-studio): provider interface and deterministic code-synth effects`.

### Task 4: Openverse CC0 source

**Files:** Create `engine/audio/studio/sources/openverse.py`, `tests/unit/audio_studio/test_openverse.py`

**Interfaces — Produces:** `OpenverseProvider(http_get: Callable[[str], bytes] | None = None, http_head: ...)`; `find()` queries `https://api.openverse.org/v1/audio/?q=<intent words>&license=cc0&page_size=10&extra...`, keeps only results whose `license` passes `licence_allowed(..., plan.allow_cc_by)`, whose `duration` (ms) ≤ 60 000 for non-bed kinds, downloads up to `limit` previews (cap 5 MB, content-type must start `audio/`), writes them under `out_dir`, returns Candidates with provenance (`source="openverse/<provider>"`, `licence`, `url=foreign_landing_url`, `author=creator`). Default `http_get` uses `urllib.request` with a 20 s timeout and a generic User-Agent (no user details). Query text = `cue.intent`; if `plan.allow_cc_by` is false the request carries `license=cc0`.

- [ ] **Step 1: Tests with a fake `http_get`** returning canned Openverse JSON and tiny wav bytes: `test_keeps_only_cc0_and_writes_files`; `test_cc_by_result_dropped_when_flag_off_kept_when_on`; `test_oversize_download_rejected` (fake returns 6 MB → no candidate, no file left); `test_non_audio_content_type_rejected`; `test_network_error_reports_unavailable` (`availability().ok` False after an `OSError`, `reason` mentions the error; `find` returns `[]`); `test_provenance_has_licence_and_url`.
- [ ] **Step 2:** Run, expect FAIL. **Step 3:** Implement. **Step 4:** Run, expect PASS.
- [ ] **Step 5:** One live check, not in CI: `.venv\Scripts\python.exe -c "from engine.audio.studio.sources.openverse import OpenverseProvider; ..."` for `door slam` with a temp plan; expect ≥1 CC0 candidate, file plays (`ffprobe` duration > 0). Record the result in `docs/AUDIO_STUDIO.md` later.
- [ ] **Step 6: Commit** `feat(audio-studio): Openverse CC0 source with size and licence caps`.

### Task 5: ACE-Step music source

**Files:** Create `engine/audio/studio/sources/music.py`, `tests/unit/audio_studio/test_music_source.py`

**Interfaces — Produces:** `MusicProvider(generator: Callable[..., MusicTakeRecord] | None = None, slot: ... )`; serves cues with `cue.kind == "music"`. `availability()` wraps `local_music_provider.check_health(timeout=2.0)["available"]`. `find` computes duration = `cue.t_out - cue.t_in` (clamped 10–180 s by the provider), calls `generate_music_take(project_id=plan.id, cue_id=cue.id, workspace_music_dir=out_dir, prompt=cue.intent, audio_duration=..., ...)` inside `acquire_gpu_slot(f"job_audiostudio_{cue.id}", required_vram_mb=0.0)` (release in `finally`), returns one Candidate per take with `source="ace-step"`, `licence="MIT"` (the model's licence; generated output is the owner's), `model=take.model_id`, `seed`. Slot busy → `[]` plus `availability` reason "GPU busy".

- [ ] **Step 1: Tests with a fake generator and fake slot:** `test_music_cue_calls_generator_with_cue_length`; `test_non_music_cue_returns_empty`; `test_gpu_slot_released_on_error`; `test_health_down_reports_reason`; `test_gpu_busy_returns_empty_with_reason`.
- [ ] **Step 2–4:** fail, implement, pass. Do **not** call real ACE-Step in unit tests.
- [ ] **Step 5: Commit** `feat(audio-studio): ACE-Step music provider for music cues`.

### Task 6: AudioEngine (Auto and Ask modes)

**Files:** Create `engine/audio/studio/engine.py`, `tests/unit/audio_studio/test_engine.py`

**Interfaces — Consumes:** Tasks 1–5. **Produces:**
- `AudioEngine(store: PlanStore, providers: list[Provider])` — the **only** code that calls providers.
- `source_cue(plan_id: str, cue_id: str, mode: Literal["auto","ask"] | None = None) -> SoundPlan`: provider order for `music` = [music]; otherwise [openverse, synth]. First provider returning candidates wins. Each candidate file is measured (`measure_take`). `auto`: choose by rule (not clipped, `duration_s` closest to `t_out-t_in` when a bed else shortest with `peak_db ≥ -30`), store the chosen `Take` on the cue, status `ready`, set `placement`-related anchor values. `ask`: store all candidates, status `needs_pick`. No candidates anywhere: status `failed`, `reason` lists each provider's reason (or "no provider has kind 'xyz'").
- `pick(plan_id, cue_id, candidate_id) -> SoundPlan` (moves candidate → chosen take, status `ready`; unknown id raises `KeyError`).
- `providers_report() -> dict[str, Availability]`.

- [ ] **Step 1: Tests with fake providers:** `test_auto_picks_and_marks_ready`; `test_ask_mode_leaves_needs_pick_then_pick_makes_ready`; `test_music_cue_never_asks_openverse`; `test_all_providers_empty_fails_with_reasons`; `test_cue_mode_overrides_plan_mode`; `test_auto_never_takes_clipped_candidate_if_clean_one_exists`; `test_pick_unknown_candidate_raises`. Plus guard `test_only_engine_calls_providers`: grep the `engine/audio/studio` and router/MCP sources for `.find(` outside `engine.py` and `providers` modules.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5: Commit** `feat(audio-studio): AudioEngine with Auto and Ask-me sourcing`.

### Task 7: Spotting and draft cues

**Files:** Create `engine/audio/studio/spot.py`, `tests/unit/audio_studio/test_spot.py`

**Interfaces — Produces:**
- `detect_cuts(video: Path, threshold: float = 0.3) -> list[float]` via `ffmpeg -vf "select='gt(scene,T)',showinfo"` parsing `pts_time`; sorted, de-duplicated within 0.15 s.
- `draft_cues(plan: SoundPlan, cuts: list[float]) -> list[Cue]`: one `sfx` cue per cut (`kind="whoosh"`, `anchor="peak"`, `hit_t=snap(cut, fps)`, `t_in = max(0, hit_t-0.5)`, intent `"transition whoosh into the cut at <t>s"`), plus one `music` cue spanning the whole video (`kind="music"`, intent `"instrumental underscore"`), status `draft`. The agent (or the owner) then rewrites intents; the local vision pass is **not** in this phase.

- [ ] **Step 1: Tests:** create a 6 s ffmpeg `lavfi` video (3 solid-colour segments of 2 s via `color` + `concat`, 24 fps, with and without an audio stream). `test_detect_cuts_finds_both_cuts` (≈2.0 and 4.0, ±1 frame); `test_draft_cues_snap_to_frames_and_stay_in_range`; `test_draft_cues_music_spans_video`; `test_no_cuts_gives_only_music_cue`.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5: Commit** `feat(audio-studio): scene-cut spotting and draft cue list`.

### Task 8: Mix, ducking and loudness

**Files:** Create `engine/audio/studio/mix.py`, `tests/unit/audio_studio/test_mix.py`

**Interfaces — Produces:**
- `render_cue(plan: SoundPlan, cue: Cue, out: Path) -> Path` — the cue alone, placed (`atrim=start=trim`, `adelay`, gain, fades, bed loop-fade to `t_out`), 48 kHz stereo wav, length = video duration.
- `render_roles(plan: SoundPlan, out_dir: Path) -> dict[str, Path]` — premix stems `dialogue, music, effects` (effects = sfx+ambience+foley), no limiter or loudnorm. Music stem has the sidechain ducking from the dialogue (`sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400`) when a dialogue file exists; otherwise no ducking. Track `gain_db` and `mute` applied. Cues past the video end are clipped.
- `render_master(plan: SoundPlan, out_wav: Path, target_lufs: float = -14.0, video_in: Path | None = None, out_video: Path | None = None) -> dict` — sums stems, `alimiter=limit=0.89`, two-pass `loudnorm` (reuse `engine.chronoflow.deliver.loudnorm_filter`), optional mux with `-c:v copy -c:a aac -b:a 192k`; returns `{"integrated_lufs","true_peak_db","lra"}` measured with `ebur128` on the output.

- [ ] **Step 1: Tests (real ffmpeg, skip if absent):** `test_cue_lands_on_hit_within_one_frame` (impact synth cue at `hit_t=1.0` → `render_cue` → `measure_take` anchor within 21 ms at 48 kHz); `test_negative_start_trims_not_crashes`; `test_stems_sum_to_premix` (render stems and a summed premix; residual peak < -60 dBFS); `test_music_ducks_under_dialogue` (RMS of music stem during a 1 s dialogue tone is ≥ 6 dB lower than the same music without dialogue); `test_no_dialogue_no_crash`; `test_master_hits_loudness_target` (a 10 s plan, target -14 → integrated within ±1 LU, true peak ≤ -1.0 dBTP); `test_bed_shorter_than_span_is_filled`; `test_cue_past_video_end_is_clipped`.
- [ ] **Step 2–4:** fail, implement (build the filtergraph as a string; keep it in one function `build_filter_complex`), pass.
- [ ] **Step 5: Commit** `feat(audio-studio): ffmpeg mix with ducking, stems premix and loudness master`.

### Task 9: Quality checks and placement metric

**Files:** Create `engine/audio/studio/qa.py`, `tests/unit/audio_studio/test_qa.py` (uses Task 8's real `render_cue`; unit tests inject a fake).

**Interfaces — Produces:** `Finding(cue_id, rule, severity: Literal["error","warn"], value, message)`; `check_plan(plan: SoundPlan, render_cue: Callable[[SoundPlan, Cue, Path], Path]) -> list[Finding]` with rules `no_take` (error, a non-draft cue lacks a chosen take), `clipping` (error if `clipped_samples>0`), `silent` (error if `peak_db<-60`), `too_loud_take` (warn > -1 dBFS peak), `placement_error` (error if > 40 ms, warn > 20 ms; metric = `abs(rendered_anchor_s - hit_t)*1000` where `rendered_anchor_s` is `measure_take(render_cue(...))` anchor; stored on `cue.placement_error_ms`), `beyond_video` (warn: `hit_t > plan.duration`).

- [ ] **Step 1: Tests:** `test_clean_plan_has_no_findings`; `test_clipped_take_is_error`; `test_missing_take_is_error`; `test_placement_error_over_40ms_is_error` (fake `render_cue` returns a wav whose hit is 60 ms late); `test_placement_error_recorded_on_cue`.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5: Commit** `feat(audio-studio): rule checks and rendered placement-error metric`.

### Task 10: Export (stems, M&E, cue sheet, credits)

**Files:** Create `engine/audio/studio/stems.py`, `tests/unit/audio_studio/test_stems.py`

**Interfaces — Produces:** `export(plan: SoundPlan, out_dir: Path, target_lufs: float = -14.0, video_in: Path | None = None) -> dict` writing `dialogue.wav, music.wav, effects.wav, me.wav (music+effects), master.wav` (+ `master.mp4` if `video_in`), `cuesheet.json`, `cuesheet.csv` (id, track, kind, hit_t, anchor, source, licence, url, placement_error_ms, status), `credits.txt` (one line per take whose licence is not CC0/synth/MIT-generated: author, title, url, licence) and `export.json` (plan version, loudness numbers, findings count). Returns paths + numbers. Refuses (`ValueError`) when any cue is `needs_pick` or `failed` unless `allow_incomplete=True`.

- [ ] **Step 1: Tests:** `test_export_writes_all_files`; `test_me_equals_music_plus_effects`; `test_credits_only_for_cc_by`; `test_refuses_needs_pick_cues`; `test_csv_has_one_row_per_cue`.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5: Commit** `feat(audio-studio): stems, M&E, cue sheet and credits export`.

### Task 11: REST router

**Files:** Create `engine/api/routers/audio_studio.py`, `tests/unit/audio_studio/test_router.py`; modify `engine/api/app.py` (import + `app.include_router(audio_studio.router)` next to the other routers, `engine/api/app.py:115-148`).

**Interfaces — Produces:** prefix `/api/audio/studio`: `GET /providers`; `POST /plans` body `{video_path, mode?, allow_cc_by?, dialogue_path?}` (probes fps/duration with `engine.chronoflow.media_tools.probe`; `dialogue_path` defaults to the video itself when it has audio); `GET/PUT /plans/{id}` (PUT replaces tracks/cues after validating ids and snapping `hit_t`); `POST /plans/{id}/spot`; `POST /plans/{id}/cues/{cue_id}/source` body `{mode?}`; `POST /plans/{id}/cues/{cue_id}/pick` body `{candidate_id}`; `POST /plans/{id}/qa`; `POST /plans/{id}/mix` body `{target_lufs?}`; `POST /plans/{id}/export`; `GET /plans/{id}/files/{name}` (FileResponse, name must be a bare file inside the plan dir). Errors: unknown plan → 404, bad body/ids/paths → 400 with a message an agent can act on. `video_path` must be an existing file; it is never served back except through `files/`.

- [ ] **Step 1: Tests (TestClient, providers faked via dependency override of the engine factory):** `test_create_plan_probes_video`; `test_get_unknown_plan_404`; `test_put_snaps_hit_t_and_bumps_version`; `test_bad_ids_400` (plan id `..`, file name `../x`); `test_source_ask_mode_returns_needs_pick_then_pick`; `test_providers_report_shape`.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5: Commit** `feat(audio-studio): REST API for sound plans`.

### Task 12: MCP tools, agent skill and docs

**Files:** Create `engine/mcp/tools/audio_studio_tools.py`, `.claude/skills/audio-studio-production/SKILL.md`, `docs/AUDIO_STUDIO.md`, `tests/unit/audio_studio/test_mcp_tools.py`; modify `engine/mcp/tools/__init__.py` (import + `__all__`).

**Interfaces — Produces:** tools registered with `domain="chronoflow"` (so profiles `chronoflow` and `all` expose them, `creative` does not): `panelflow_chronoflow_audio_{providers, create_plan, get_plan, put_plan, spot, source_cue, pick, qa, mix, export}`; each calls `bridge` against the Task 11 endpoints and returns the JSON (numbers and file paths, not prose). `mix` and `export` use a 600 s timeout.

- [ ] **Step 1: Tests:** `test_tools_registered_in_chronoflow_and_all_profiles_not_creative` (via `MCPServer(profile=...).exposed_tools()`); `test_each_tool_has_required_ids_in_schema`; `test_source_cue_posts_expected_endpoint` (monkeypatch `bridge.post`).
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5: Skill file** (frontmatter `name`, `description` like `shorts-reels-production`): order of tools (providers → create_plan → spot → edit intents → source_cue per cue → qa → fix → mix → export), the rules (CC0 default, Ask-me when taste matters, never approve a cue with a QA error, no cloud fallback, downloads need approval, report what was and was not verified), and the cue-writing rules (one hit = one cue, `anchor="peak"` for whooshes/risers, intent in plain words, kinds the synth knows). Plain Markdown so Claude Code, Antigravity, OpenCode and Hermes can read it.
- [ ] **Step 6: `docs/AUDIO_STUDIO.md`:** what exists, REST/MCP list, licence table (copy verdicts from the spec), the Stability USD 1 M revenue re-check note, honest limits (no listening yet; onset method is self-consistent, not perceptually validated).
- [ ] **Step 7: Commit** `feat(audio-studio): MCP tools, agent skill and docs`.

### Task 13: Real-video verification (acceptance)

**Files:** Create `docs/AUDIO_STUDIO.md` section "Measured (Phase 1)"; no new code unless a defect is found (fix it in its own task's file with a failing test first).

- [ ] **Step 1:** Start the engine (never mid-job; check `/api/system` first) and use two **real finished videos** from `output/` (newest finished Short; the Dawn Gate film). Drive everything through the **MCP stdio client** (per the memory note), not Python imports.
- [ ] **Step 2:** For each: `create_plan` → `spot` → rewrite 3+ cue intents → `source_cue` in Auto for all, then Ask for two cues and `pick` → `qa` → `mix` → `export`.
- [ ] **Step 3: Measure and record:** per hit cue the `placement_error_ms`; share of hit cues under 40 ms (**acceptance: ≥ 95 %**); integrated LUFS and true peak of master; stems null test; ducking depth; Openverse CC0 hit rate and any `failed` cues with reasons; ACE-Step take time and GPU slot behaviour; a spectrogram + waveform image per master, opened and looked at.
- [ ] **Step 4:** Report plainly what was **not** verified (no listening; onset method not validated against perception; unit synth quality unjudged) and ask the owner to listen to both masters.
- [ ] **Step 5:** Update the spec line "I watch it and report what I heard" to "I measure it and the owner listens", and note the dropped items (existing curated library: no real catalogue found, only `AudioLibrary.mock.ts`; local vision pass moved after Phase 1). **Commit** `docs(audio-studio): phase 1 measured results`.
