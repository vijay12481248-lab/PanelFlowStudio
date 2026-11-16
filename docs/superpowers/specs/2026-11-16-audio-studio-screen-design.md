# Audio Studio screen - design (2026-11-16)

Status: the owner asked for it ("I would like to see a very professional audio studio ... a different screen ... besides Video Studio and Image Studio ... narration as well ... think about the plan and start"). The owner delegated the design; every choice below is my call and is marked so. Builds on Phase 1 (engine, `docs/AUDIO_STUDIO.md`) and Phase 4 (the Audio rail page inside Video Studio, which stays as the quick view).

## Intent
One top-level **Audio Studio** tab (next to Video Studio, Image Studio, Gallery, Storyboard, Organizer) where a creator makes **narration, music, sound effects and the final mix** for a video, with every control labelled by what it is for. It works on the same sound plan the agents use (MCP/REST), so a person and an agent can work on one video together.

Success: a creator who has never seen it can open a video, understand each panel from its title and one-line purpose, and get to a finished mix (narration + music + effects, loudness-correct, exported or sent back to Video Studio) without reading documentation.

Non-goals: VST plugin hosting, multitrack recording, sample-level editing, a second mixing engine in the browser, auto-publishing. Anti-goals: a second copy of plan logic (the page talks to `/api/audio/studio` only); any change to how Video Studio behaves except the hand-off buttons; cloud services.

## Calls I made (state, reason, cost if wrong)
1. **A real tab, not another rail page.** The tab gets the whole screen (bigger video, wider lanes, a full mixer, a Create panel). The rail "Audio" page in Video Studio stays as the quick view. Both are the same code (`audio.js` becomes a factory with two hosts), so they cannot drift apart. Only one is open at a time. Cost: a small refactor of `audio.js`.
2. **The plan is the single source of truth, narration included.** Narration lines become cues on the Voice lane (`track: dialogue`, `kind: narration`, with `text`, `voice`, `provider`, `speed`), sourced by a new local **narration provider** (Kokoro 82M, Apache-2.0, in-process; Qwen3-TTS 1.7B, Apache-2.0, voice cloning from the references in `voice_references`; both already installed under `D:\Tools` / the venv). No cloud, no silent fallback. The mix puts narration cues and (optionally) the video's own audio into the dialogue stem, and music ducks under both.
3. **"Original audio" is a switch, not a track you must manage**: keep / mute the video's own sound (`plan.keep_original_audio`, default true when the video has audio and no narration cues exist, false once narration is added and the owner says so).
4. **Hand-offs** (the owner's explicit ask):
   - *Video -> Audio, from the timeline*: button "Sound this timeline" in Video Studio renders the current timeline to a picture (existing `render_timeline_edl`), creates the plan, and **stores the timeline's clip boundaries as the plan's picture cuts** (authoritative, not guessed by scene detection). The plan remembers the job id. Also "Open in Audio Studio" from a Media card.
   - *Video -> Audio, live*: the Audio Studio header shows "Cuts from Video Studio timeline" and can refresh them after the owner edits the timeline.
   - *Audio -> Video*: "Send mix to Video Studio" exports the mix with the video (`master.mp4`) and imports it into Media as a new project (existing library import), then opens it in Video Studio. Cue "Show in Video Studio" jumps the Edit playhead to that time.
   Cost if wrong: Deliver itself does not yet read the mix (a later step could let Deliver mux the plan master).
5. **Everything labelled, one purpose per panel, a start-here strip.** Each panel header has a title and a one-line purpose; empty states say what to do next; a 3-step strip (1 Open a video, 2 Add sound, 3 Mix and export) shows the current step. Plain words, no jargon (e.g. "Lands on: the start / the swell").
6. **Automation that adds value and is cheap**: *Auto sound design* (Spot -> draft -> Source all -> Preview -> QA in one click, then a plain summary of what it did and what needs the owner), *Fix problems* (re-source clipped/silent cues, nudge late hits), loudness presets (YouTube/Shorts -14, Podcast -16, Cinema -23), *Narration from script* (paste text -> lines placed back to back, or one line per picture cut), *Voice sample* (hear a voice on your own line before committing). Each is a thin wrapper over existing engine steps.
7. **Built on a branch in a worktree** (`feat/audio-screen`, `.worktrees/audio-screen`), tested on an isolated engine on :8767 with a temporary data folder; the owner's live engine is not touched.

## Screen layout (1600x900 reference)
```
[Video Studio][Image Studio][Gallery][Storyboard][Organizer][Audio Studio]            (top tabs)
+- AUDIO STUDIO ---------------------------------------------------------------------------+
| plan: dawn_gate.mp4 v7 ▾  [Open video][Sound this timeline]   Auto sound design  ● saved  |
| 1 Open a video ✓   2 Add sound ▶   3 Mix and export                                       |
+--------------------+-------------------------------+-------------------------------------+
| CREATE             |  MONITOR                      | INSPECTOR  (what this cue is)       |
| [Narration][Music] |  [video]   00:01:12:05        |  words / voice / speed / gain /     |
| [Effects][Cues]    |  ◀ ▶ ▶|  Space                |  fades / source + licence / takes   |
|  tab contents:     |                               |  ▶ audition  Pick  Source  Delete   |
|  Narration: script,|                               +-------------------------------------+
|   voice, sample,   |                               | MIXER  Voice | Music | Effects      |
|   place on cuts    |                               |  fader meter M S    MASTER -14 LUFS |
|  Music: describe,  |                               |  loudness preset  [Master][Export]  |
|   mood, bpm, key   |                               |  [Send mix to Video Studio]         |
|  Effects: describe,|                               |                                     |
|   search, add      |                               |                                     |
+--------------------+-------------------------------+-------------------------------------+
| ruler + picture cuts + playhead                                                            |
| VOICE   original-audio waveform + narration blocks                                         |
| MUSIC / SFX / AMBIENCE / FOLEY lanes with waveforms and hit markers                        |
+--------------------------------------------------------------------------------------------+
```

## Narration (the owner called it important)
- **Create > Narration**: script box (paste or type); voice (Qwen3-TTS reference voices on disk, Kokoro voices), provider, speed; "Voice sample" speaks the first sentence; "Place lines": *back to back from the playhead* or *one line per picture cut*; estimated length per line shown before generating (words / speaking rate) and the real length after.
- **Lines are cues**: edit words, voice, speed, retake (new seed / slower), alternates with Ask-me, gap control (pause before / after), per-line gain. A line longer than the room before the next cut/line is flagged by QA ("narration runs 0.8 s into the next scene").
- **Mix**: narration cues render into the dialogue stem; original audio is added only when `keep_original_audio`; ducking follows the combined dialogue.
- **Takes are content-addressed and licence-recorded** (provider, model, voice, text, seed); voice references are the owner's own recordings (their rights; flagged in the doc, not checked by software).

## Music and effects (existing engine, better front door)
- **Create > Music**: describe the music in plain words, mood chips, tempo and key (defaults, optional), length = the selected span or the whole video, Ask-me with 2-3 takes; fits under narration automatically via ducking.
- **Create > Effects**: describe the sound, kind chips (whoosh, impact, click, pop, ding, riser, drop, noise bed), "search free library" (Openverse CC0) with audition, "Add at playhead" or "Add on every cut".

## Engine changes needed
`plan`: `keep_original_audio`, `source` (`{kind: file|timeline, job_id}`), narration fields on cues (`text, voice, provider, speed, pause_before`). `sources/narration.py` provider. `mix.render_roles`: dialogue cues + original audio into the dialogue stem. `POST /plans/from_timeline`, `POST /search` (ad-hoc library search), `POST /narration/sample`, `GET /voices`, `POST /plans/{id}/fix`, `POST /plans/{id}/auto`. MCP tools for the new endpoints.

## Verification (owner's rule: real data)
pytest for engine pieces with fakes; **real** Kokoro and Qwen3-TTS lines generated and measured (duration, peak, a spectrogram looked at; not heard); real ACE-Step music if the GPU has room; node tests for pure logic; headless Chromium checks against the isolated engine; a real reel narrated and mixed end to end; Video Studio -> Audio -> Video round trip on a real timeline. Not verifiable here: hearing the audio, the Tauri window.

## Risks
GPU is shared (ComfyUI + Ollama ~13 GB): Qwen3-TTS (about 5 GB) and ACE-Step (about 3 GB) may be held back by the job manager; Kokoro runs on the CPU and is the safe default. The 5-hour usage limit can interrupt long sessions: the plan is in milestones, each committed.
