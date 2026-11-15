# Audio Studio - research and design (2026-11-15)

Status: **draft for the owner's approval. Nothing is built or downloaded yet.**

## 1. Intent

PanelFlow makes good pictures and video. Sound is the weak part. The owner wants a professional Audio Studio where:

- music and sound effects (SFX) are generated or found **in sync with the video**, not dropped in by hand;
- **coding agents** (Claude Code, Antigravity, OpenCode, Hermes) can drive the whole thing and produce good-quality sound without a human editing a waveform;
- it looks and behaves like audio software from a serious company: cue sheet, multitrack timeline, mixer, meters, stems, loudness delivery;
- everything is **free to use and commercially usable** for the videos the owner publishes, and runs locally.

Success = take a finished video, run one agent command, get a mixed, loudness-correct master plus stems where every hit lands on its frame, and a cue sheet that says where every sound came from and under what licence.

Anti-goals: silent cloud fallback (AGENTS.md: local-first); a second GPU job loop; per-story hand-written prompts; a from-scratch DAW (no VST hosting, no sample-level editing as the main feature); using any model whose licence forbids commercial output.

## 2. What exists today (verified in the repo)

| Piece | Where | State |
|---|---|---|
| ACE-Step 1.5 music (turbo DiT + 1.7B LM) | `engine/audio/providers/ace_step.py`, `music_director.py`, `/api/.../music/*` | Works. Story-aware plan, ducking, 60 s verified master (Chapter 9 report) |
| SFX | `/music/sfx/capability` says **no neural SFX model installed**; "curated library" | Weak. `tools/build_sound_design.py`, `tools/design_funny_sfx.py` are one-off numpy synths for single shorts |
| Narration (TTS) | `engine/narration`, `engine/audio/synthesis.py`, Narration Studio UI | Works, separate studio |
| Audio Library UI | `apps/desktop/src/components/audio-library/` | **Fed by `AudioLibrary.mock.ts`**, a mock catalog with a placeholder tone. Not a real studio |
| Timeline + player + Web Audio graph + loudness deliver | ChronoFlow NLE `engine/chronoflow/static/nle/*`, `deliver.py` (-14 LUFS presets) | Works. Has gain nodes, meters, crossfade. No audio tracks beyond clip audio |
| MCP | `scripts/run_mcp_server.py`, profiles `all/creative/chronoflow`; only `panelflow_music_health`, `get_music_plan`, `generate_audio_job` for audio | Thin |
| Hardware | RTX 5060 Ti 16 GB; ComfyUI + Ollama already hold ~13 GB | Audio models must run **one at a time** through `JobManager` |

## 3. Research: what is available and what we may use

Licences below were read from the primary file (GitHub LICENSE/README, Hugging Face metadata, the licence text) unless marked *secondary*. "Commercial" is about the **audio we publish**, for a creator with revenue under USD 1 M.

### Music

| Model | Licence (source) | Verdict |
|---|---|---|
| **ACE-Step 1.5** (already installed) | MIT: repo `LICENSE` and HF metadata read. README adds a copyright-similarity disclaimer | **Use.** Also has cover, repaint, track separation, vocal-to-BGM, BPM/key control, 10 s-10 min, LoRA from ~8 songs. XL (4B) variants need >=12 GB with offload; cannot run beside ComfyUI |
| Stable Audio 3.0 (Small / Medium, open weights, May 2026) | HF: `other / stable-audio-community`, **gated**; text unreadable without login. *Secondary*: Community Licence free commercial under USD 1 M revenue, instrumental only | **Candidate, unverified.** Owner must accept the HF gate; read the licence before use |
| MusicGen / AudioCraft | Code MIT, **weights CC-BY-NC** | Out |
| YuE, DiffRhythm, SongGeneration 2, SongBloom | Not read (searches gave no licence text) | Not planned. Re-check only if ACE-Step proves insufficient |

### Sound effects (text to sound)

| Model | Licence | Verdict |
|---|---|---|
| **Earshot SFX bank** (252 sounds rendered from code, CPU, no samples, no network) | Repo MIT (GitHub API). Sounds are synthesised, so no sample licence | **Use** as the free, zero-risk baseline and for UI/whoosh/hit classes |
| Stable Audio 3.0 Small SFX / Stable Audio Open Small (341 M, built for short SFX and production elements) | HF: Stability Community licence, **gated**. *Secondary*: commercial under USD 1 M | **Primary generator candidate, unverified.** Benchmark before adopting |
| TangoFlux | README: "non-commercial, research-only" (Stability licence + WavCaps academic) | Out |
| AudioLDM 2 | CC-BY-NC-SA 4.0 | Out |

### Video to audio (sound that watches the picture)

| Model | Licence | Verdict |
|---|---|---|
| **HunyuanVideo-Foley** | Tencent Hunyuan Community Licence, read in full: free commercial use, **not valid in EU / UK / South Korea**, outputs must not be used to train another AI model, 100 M-MAU cap. 48 kHz. 20 GB VRAM, **12 GB with offload** (XXL), XL 16 GB / 8 GB offload. ComfyUI nodes exist | **Conditional.** Only strong open V2A with a commercial path. Usable if the owner is outside those territories |
| MMAudio | Code MIT, **checkpoints CC-BY-NC 4.0**; authors do not guarantee commercial fitness | Out for published videos |
| ThinkSound | README: "Commercial use is NOT permitted" | Out |
| Sony Woosh | Weights CC-BY-NC (its best model is private) | Out |
| LTX-2 / MOVA (video+audio generators) | Not read | Watch-list; PanelFlow's video engine is MiniMax H3 |

No independent benchmark of V2A frame accuracy was found (vendor posts admit this). **We will measure sync ourselves** (section 5).

### Libraries of real recordings

| Source | Finding |
|---|---|
| **Openverse audio API** | **Tested live today**: anonymous call returned Freesound results with a per-item `license` and `license_type=commercial` filter. Indexes Freesound (~592 k), Wikimedia Commons (~4 M), Jamendo (~645 k). Files returned are Freesound CDN **previews (lossy mp3)** |
| Freesound API directly | Official terms: free **only for non-commercial** use; commercial API use needs a licence from the operator. Per-sound licences are CC0 / CC-BY / CC-BY-NC |
| Others (Sonniss GDC, Pixabay, BBC, ZapSplat) | Terms not verified (fetches empty or conflicting). BBC is non-commercial. Not planned |

Rule that follows: **default to CC0 only**; keep CC-BY as opt-in (needs a credit line, and may trigger YouTube Content ID claims); never CC-NC. Unverified: whether pulling Freesound previews through Openverse is covered by Freesound's API terms. The conservative reading is "the CC0 licence on the item governs"; the owner should confirm.

### Agent tooling

- **Earshot** (MIT, ~4.9 k stars, active today): "ears for coding agents", CPU only, CLI + Python + **MCP server**. `describe`, `match` (does this file fit this description), `find` (best moment in a long recording), `timeline` (second-by-second transcript with **sync of sound to picture cuts**), `measure` (LUFS, true peak, tempo), `critique` (scorecard with timestamped fixes), `sfx` and `kit` (place bank sounds with measured onset/peak against the cut and the music bed), `forge` (agent writes a sound as code and improves it by listening). I could not identify a tool called "real SFX" with confidence; please send the link if it is something else.
- ElevenLabs / Sonilo MCP servers: hosted and paid; Sonilo has a video-to-SFX MCP tool. Cloud, so **not default**. Could exist as an explicitly enabled, off-by-default provider later.
- Utilities: Demucs (MIT) stems; Beat This (MIT) beat/downbeat; librosa (ISC); LAION CLAP code (CC0, weights licence unread); ffmpeg already used. **Pedalboard is GPL-3**: do not link it; do EQ/compression/ducking with ffmpeg filters.

### What professional suites do (the target feel)

Adobe Firefly now generates music, speech and SFX in one place, with voice-timed effects. DaVinci Resolve Fairlight: library search, audition against picture, separate Foley/ambience/music tracks, dialogue leveler, voice isolation. Descript edits audio through text. The post-production process they follow: **spotting** (decide where sound goes) -> cue sheet -> sound design in layers -> **premix** -> final mix -> loudness check -> **stems** (dialogue, music, effects; the M&E pair for dubbing) -> versioned delivery with a change log.

## 4. Approaches considered

1. **Model-first.** One video-to-audio model (Hunyuan-Foley) makes all sound for a clip. Fast to demo, but one opaque blob per clip, fixed to the territory licence, 12-20 GB VRAM, no control over a single hit, and no proof it is frame accurate.
2. **Cue-first (recommended).** The video is *spotted* into a cue sheet. Each cue (a door slam at 12.48 s, a rain bed from 0-30 s, a theme from 0-45 s) is sourced separately from the best available source (library CC0 -> code bank -> generated), **measured, and placed by its measured onset** so the hit lands on the frame. Models are interchangeable plug-ins behind one interface. Hunyuan-Foley becomes one optional source for ambience/bed. Matches how the pros work, gives agents small verifiable steps, and keeps every cue's licence on record.
3. **Wrap an existing DAW** (Reaper/Ardour scripting). Mature mixing, but not embeddable in a Tauri app, extra install, and the agent would drive a GUI. Rejected.

**Picked: 2 (owner delegated the how; this is my call).**

## 5. Design

### 5.1 One source of truth: the Sound Plan (cue sheet)

A JSON document per video, stored with the project, read and written by UI, REST and MCP alike.

```
SoundPlan { video_ref, fps, duration, tracks[], cues[], mix, deliverables }
Track     { id, role: dialogue|music|sfx|ambience|foley, gain_db, duck_under, pan, mute }
Cue       { id, track, kind, t_in, t_out | null, hit_t (the moment that must land),
            intent (plain words), source: library|bank|generated|recorded,
            takes[], chosen_take, gain_db, fade_in, fade_out, status, provenance{ licence, url, model, seed } }
```

Every cue carries its provenance, so the delivery step can print a credits block and refuse CC-NC items.

### 5.2 Pipeline (each step is a callable, an MCP tool and a UI action)

1. **Spot.** Deterministic sync points: shot cuts, cut/transition times from the timeline, narration word timings (already produced by the narration step), motion peaks. A vision pass (Ollama `qwen3.5:9b` on keyframes) proposes *what* is happening at each point. Output: draft cue list.
2. **Plan.** Directors write cue intents from the story/scene plan (reuse `music_director.py`, `chapter_plan.py`); no hand-written per-story prompts.
3. **Source.** `AudioEngine` (the single entry point, like `ArtEngine`): ask providers in order library -> bank -> generator -> optional V2A. Providers are small classes with the same interface (`find` / `make`). GPU providers submit through `JobManager`, one at a time, honouring the VRAM hold-back.
4. **Place.** Measure each take's onset/peak (energy envelope), then shift so `hit_t` lands on the target frame. **Acceptance metric: placement error in ms**, reported per cue.
5. **Listen / QA.** Deterministic rules first (clipping, silence, DC, duration, true peak, ducking depth, placement error); then Earshot `match` and `timeline` as a second, independent witness (the repo's own rule: agreement of independent witnesses, low confidence is shown, not hidden).
6. **Premix and mix.** ffmpeg filter graph: per-track gain/EQ/compressor, sidechain ducking under dialogue, bus, limiter. Same graph runs for preview and final so what you hear is what you export.
7. **Master and stems.** Loudness to the preset (-14 LUFS YouTube/Shorts exists in `deliver.py`), plus stems: dialogue, music, effects, M&E, and the cue-sheet CSV/JSON with credits.
8. **Version.** Each run is a numbered version with a change log; approved takes survive regeneration (same pattern as Narration Studio).

### 5.3 Agent interface

- REST under `/api/audio/studio/*` (OpenAPI, for agents without MCP).
- MCP tools in the existing server, `creative` profile: `panelflow_audio_spot`, `_plan_get/put`, `_find_sfx`, `_make_sfx`, `_make_music`, `_place`, `_listen`, `_mix`, `_export`, `_status`. Small, idempotent, each returns evidence (numbers, file paths), not prose.
- A plain-Markdown skill `.claude/skills/audio-studio-production/SKILL.md` (same pattern as `shorts-reels-production`) telling any agent the order of tools, the rules (CC0 default, no cloud fallback, always listen before approving), and the gotchas we measure. Claude Code, Antigravity, OpenCode and Hermes can all read it.

### 5.4 UI (recommended: a new Audio module inside the ChronoFlow NLE)

Reason: the video player, timeline, Web Audio graph, meters and Deliver already live there, alongside Color and Fusion. The React `AudioLibrary` page stays as the browse view but reads real data instead of `AudioLibrary.mock.ts`.

```
+-------------------------------------------------------------+
| Spot | Plan | Source | Mix | Deliver          [version v7] |
+--------------------+----------------------+-----------------+
| Browser            | Video monitor        | Inspector       |
| library/bank/gen   | + safe frame, TC     | cue: intent,    |
| search + audition  |                      | takes, gain,    |
|                    |                      | fades, licence  |
+--------------------+----------------------+-----------------+
| DX  |#### ##   ###|  multitrack lanes with waveforms,       |
| MX  |=========== ==|  cue blocks, hit markers on the cut     |
| SFX |  *   *    *  |  grid, ducking curve overlay            |
| AMB |~~~~~~~~~~~~~~|                                         |
+-----+--------------+-----------------------------------------+
| Mixer strips + LUFS (M/S/I) + true peak + spectrum + sync err |
+-------------------------------------------------------------+
```

Pro touches that matter: frame-accurate snapping to cuts and hit markers, per-cue take comparison (A/B), solo/mute per track, live loudness meters, a "sync error" badge per cue, a delivery tab with stems and the credits block.

### 5.5 Where things go

`engine/audio/studio/`: `plan.py` (schema + store), `spot.py`, `engine.py` (`AudioEngine`), `providers/{openverse,bank,earshot_bank,stable_audio,ace_step,hunyuan_foley}.py`, `place.py`, `mix.py` (ffmpeg graph builder), `qa.py`, `stems.py`. Router `engine/api/routers/audio_studio.py`; MCP `engine/mcp/tools/audio_studio_tools.py`; docs `docs/AUDIO_STUDIO.md` (measured results, written as we go).

## 6. Phases (each ends with a check on real data, per the owner's rules)

| Phase | Delivers | Needs approval for | Done when |
|---|---|---|---|
| **1 Core, no new models** | Sound Plan, spot, place, QA, mix, stems, REST + MCP + skill; Auto / Ask-me pick modes; sources = ACE-Step, Openverse CC0, code synth (no curated catalogue exists in the repo, only a mock file) | Nothing new (standing OK for CC0 fetches given) | A real existing video (a Short and the Dawn Gate film) gets a mixed master + stems; **placement error under 40 ms on at least 95% of hit cues**; I measure it and the owner listens (I cannot hear audio) |
| **2 Ears and bank** | Earshot installed in its own venv (MCP/CLI, CPU), its 252-sound bank as a provider, `listen` tool | Earshot package + its CLAP/audio-tagging model downloads: exact files and sizes first | Agent can reject a bad take using measured evidence; cases where Earshot and deterministic QA disagree are listed |
| **3 SFX generator** | Stable Audio 3 Small SFX or Open Small behind `AudioEngine`; blind benchmark of 20 fixed prompts vs bank vs Openverse | HF gate acceptance, licence read by me, download size | Owner rates the blind set; keep the generator only if it beats bank+library on the classes it is meant for |
| **4 UI** | Audio module in the NLE (section 5.4), React library page on real data | none | Opened in a real window and driven end to end (the desktop UI has never been opened in a real window yet) |
| **5 Video-aware beds** | HunyuanVideo-Foley as an optional ambience/bed source; ACE-Step repaint/fit-to-length, style LoRA per channel | Weights download (exact file and size first) | Sync error measured against the cue method; kept only if it beats cue-first placement for beds |

Phase 1 is the milestone that changes how videos feel; phases 2-5 can be reordered.

## 7. Constraints and rules this design follows

- Local-first; no silent cloud or mock fallback; a provider that is missing says so (the current `/music/sfx/capability` does this and stays honest).
- One place talks to GPU audio models (`AudioEngine` via `JobManager`); tests fail if a second private submit loop appears (same guard idea as `test_art_engine.py`).
- Rights: CC0 default; CC-BY opt-in with auto credits; CC-NC refused like UNKNOWN in the anime rights gate; provenance recorded for every cue.
- Publishing rules unchanged (private by default).
- Model/file downloads need the owner's approval with exact file, size and source first.

## 8. Not verified

- Stable Audio 3 / Open Small licence text (gated; only metadata and secondary reports read).
- ACE-Step's generated-music IP risk beyond its own disclaimer; YouTube may still Content-ID-match style-similar music.
- Whether any open V2A model is frame accurate. No independent benchmark exists; we will measure.
- Sonniss, Pixabay, YuE, DiffRhythm, LTX-2, MOVA, CLAP weights licences.
- Freesound-via-Openverse preview terms (see section 3).

## 9. Owner decisions (answered 2026-11-15)

1. **Owner is in India**, so HunyuanVideo-Foley's territory exclusion (EU/UK/South Korea) does not apply. Phase 5 stays in the plan. Its other conditions still apply: outputs must not be used to train another AI model.
2. **Use is personal.** The software is never published or redistributed; only the videos and audio it makes go to YouTube, Instagram and other monetised channels. The licences above are read on that basis (no model weights are redistributed).
3. **CC0 clips: the engine may fetch them on its own** (a few hundred KB each), logging provenance on the cue. **Both modes exist**: *Auto* (engine picks and moves on) and *Ask me* (engine shows the top candidates and the owner picks). Mode is per project and per cue; the owner can always override a pick later. Anything that is not CC0 (CC-BY) is never taken in Auto mode.
4. **Host: ChronoFlow Studio**, as the Audio module beside Video, Image, Color and Fusion.
5. **Revenue is unknown and currently near zero** (new channel). Stable Audio's free commercial licence applies below USD 1 M annual revenue across all income, so it covers the owner for now. If income ever approaches that line, re-check the licence before continuing; record this in `docs/AUDIO_STUDIO.md`. The Hugging Face gate on Stable Audio models is accepted by the owner personally in their own account; the agent will not do it.
