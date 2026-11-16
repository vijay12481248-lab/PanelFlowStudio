# Audio Studio

Cue-sheet audio for PanelFlow videos: music, sound effects and a loudness-correct mix, each hit placed on its frame, driven by agents (MCP / REST). Design: `docs/superpowers/specs/2026-11-15-audio-studio-design.md`. Plan: `docs/superpowers/plans/2026-11-15-audio-studio-phase1.md`. Agent guide: `.claude/skills/audio-studio-production/SKILL.md`.

## What exists (Phase 1)

| Piece | File |
|---|---|
| Sound plan (cue sheet), versioned JSON store, licence policy | `engine/audio/studio/plan.py`, `licence.py` |
| Onset/peak/level measuring, placement | `measure.py`, `place.py` |
| Sources (the only caller is `AudioEngine`) | `sources/openverse.py` (CC0 clips), `sources/synth.py` (code-made effects), `sources/music.py` (ACE-Step) |
| Engine: Auto / Ask-me sourcing, pick | `engine.py` |
| Spotting: scene cuts -> draft cues | `spot.py` |
| Checks incl. rendered placement error | `qa.py` |
| Mix, ducking, stems premix, loudness master | `mix.py` |
| Export: stems, M&E, cue sheet, credits | `stems.py` |
| REST | `engine/api/routers/audio_studio.py` (`/api/audio/studio/*`) |
| MCP | `engine/mcp/tools/audio_studio_tools.py` (`panelflow_chronoflow_audio_*`, profiles `chronoflow`, `all`) |

Plans live in `<app data>/audio_studio/plans/<plan id>/` (`plan.json`, `takes/`, `renders/`, `exports/v<N>/`). The Audio page (Phase 4) is described below.

## Licences (checked 2026-11-15 from the primary files)

| Source | Licence | Use |
|---|---|---|
| ACE-Step 1.5 | MIT | in use for music |
| Code-made effects | own code, CC0 | in use |
| Openverse clips | per item; engine accepts CC0, CC-BY only when `allow_cc_by` | in use (previews are lossy mp3) |
| Earshot | MIT | Phase 2 |
| Stable Audio 3 / Open Small | Stability Community licence, gated; free commercial below USD 1M annual revenue (secondary reports; text not read) | Phase 3, owner accepts the gate. **Re-check if income nears USD 1M** |
| HunyuanVideo-Foley | Tencent Hunyuan Community; not valid in EU/UK/South Korea (owner is in India); outputs must not train another AI model | Phase 5 |
| MMAudio weights, ThinkSound, Woosh, TangoFlux, AudioLDM 2, MusicGen | non-commercial | never |
| Pedalboard | GPL-3 | do not link; mixing uses ffmpeg |

## Honest limits

- **No listening.** All checks are measurements and rules. The owner must listen to a master before publishing.
- The placement error (ms) compares where a rendered hit lands with its frame using the same onset detector that placed it. It proves the pipeline is exact (about 0.02 ms), not that the detector matches what a person hears.
- Scene detection uses ffmpeg's scene score at 0.3: a hard cut between two similar-brightness colours scored near 0 in a test and was missed. Add hits by hand when a cut is missed.
- ACE-Step defaults to 85 BPM / D Minor unless the cue has `hints`; `engine/audio/providers/ace_step.py` is unchanged.
- The local vision pass that would describe each scene is not built; the calling agent writes the intents.
- `Track.pan` is stored but not applied.

## Measured (Phase 1, 2026-11-15, driven through the MCP tools on real videos)

Run through a router-only server on port 8766 (the owner's live engine on 8765 runs older code and was not restarted).

| | Mosquito reel (66.4 s, 1080x1920, 30 fps) | Dawn Gate draft (565.7 s, 1080p, 24 fps) |
|---|---|---|
| Spotting | 14 picture cuts | 139 cuts in 14 s |
| Cues sourced | 14 whooshes + 1 slap from Openverse CC0 (all `CC0 1.0`, Freesound), music take reused | 10 whooshes + 1 door from Openverse CC0 |
| Placement error (rendered hit vs its frame) | 15 hit cues, **max 6.9 ms, all under 40 ms** | 11 hit cues, max 6.9 ms |
| QA | 0 errors, 3 warnings (takes peaking at -0.3, -0.8, -1.0 dBFS) | 1 error (a failed cue, below), 2 warnings |
| Master | -14.1 LUFS, -1.5 dBTP, LRA 4.7; master, stems and video all 66.37 s | -14.3 LUFS, -1.5 dBTP, LRA 13.1; mix took 25 s |
| Music under narration | ducked by 5.5 dB on average (11.9 dB at most); the narration track had no pauses, so no un-ducked comparison exists | no music |
| Export | stems, M&E, master wav + mp4, cue sheet, credits written | not exported |

Looked at: a spectrogram and waveform of the reel master (speech bursts, one whoosh swell at the 9.4 s cut, no clipping). Not listened to.

What the real runs found (all fixed with a failing test first, see git history): `put_plan` replaced the cue list; the providers report called a missing ACE-Step "ok"; mp3 clips were measured by a different decoder than the mixer used (about 25 ms) and the "peak" of a two-lobed whoosh flipped lobes (about 150 ms, now an energy centroid measured at 48 kHz); Auto gave every cut the same clip (now prefers an unused one); the ducked music stem lost up to 0.16 s of tail.

Not exercised: ACE-Step itself (not installed at `C:\Tools\ACE-Step-1.5`, GPU 15.8/16.3 GB busy; the reel reuses a music take it had made earlier), cue "no match" cases for `mosquito buzz` and `night room tone` (they failed with a stated reason, which is the intended behaviour).

## More limits found

- **Openverse's anonymous API rate-limits.** After roughly a hundred requests in one day it answered HTTP 403 and the cue failed with that reason. A free Openverse API key would raise the limit; creating one is the owner's account action, so it is not wired in yet.
- Auto fetches three candidates per cue, so at most three different library clips exist per intent; vary the intent wording across cues for more variety.
- Two cues in the reel (`buzz`, `night`) found no CC0 match at all; the CC0-only default is strict by design.

## Final review (2026-11-15)

A fresh whole-branch review found no critical issues and five important ones, all fixed with a failing test first: lost updates when two calls changed one plan (per-plan lock, slow work outside it, long runs write back only what they measured); the `peak` anchor could land in silence between two far-apart sounds (now the loudest cluster, merging lobes under 0.5 s apart); the music GPU slot used a private resource manager instead of the shared one the job manager uses; `put_plan` could attach any file with any licence to a cue (server-owned cue fields are now refused); a plan with nothing to mix crashed ffmpeg (now a clear error). A malformed Openverse id can no longer reach a file name. Seven minor findings were deferred (negative t_in gives a 502, hit_t is not clamped, a new cut can reuse a sourced cue id, dialogue-track cues are never mixed, credits have no title, provider error text is shared across threads, take paths are not re-checked in the renderer).

## Audio page (Phase 4, 2026-11-16)

A sixth rail page in the ChronoFlow Video Studio (between Color and Deliver). Files: `engine/chronoflow/static/nle/audio.js` (page), `audio-model.js` (pure logic, `node --test tests/js/audio_model.test.js`), `audio.css`, `data-page="audio"` rules in `layout.css`, a rail button and panels in `index.html`, "Open in Audio" in `library.js`.

- **Open a video**: Media -> select one video -> Open in Audio, or Audio -> Open video... A plan is reused when one exists for that file.
- **Left**: plan switcher, Auto / Ask-me sourcing, CC-BY switch, Spot / Source all / QA, the cue list with status chips (placement error shown), QA findings (click one to jump to its cue).
- **Centre**: the video (muted) with frame-accurate time code and transport (Space, Home/End, `,` `.`).
- **Right**: the selected cue: words, kind, lane, hit time with one-frame nudges, what it lands on (start or swell), gain, fades, sourcing mode, provenance and licence with a link, candidates with audition (play on their own, waveform) and Pick, Source / Delete.
- **Bottom**: ruler with picture cuts, five lanes with waveforms, hit markers and the dialogue waveform in DX; drag a block to move its hit (frame snap, snaps to a cut within 8 px), arrow keys nudge a frame, wheel zooms at the cursor, Shift+wheel scrolls. Mixer: Dialogue / Music / Effects faders, mute and solo, level meters, Preview mix (renders the three stems as m4a), Master (measures LUFS / true peak / LRA), Export.
- **How playback works**: the engine renders dialogue, music and effects (the same code as the export), the page plays them through Web Audio gain nodes in step with the video (re-seeked when more than 60 ms apart). A fader is a live trim relative to the gains the stems were rendered with and is saved on the plan (`tracks[].gain_db`); the preview then reads "out of date" until you press Preview mix again.
- **API added for it**: `GET /plans`, `GET /plans/{id}/video` (Range), `GET /plans/{id}/takes/{id}/peaks`, `GET|POST /plans/{id}/preview`, `plan.cuts` stored by Spot; `put_plan` now upserts tracks like cues.
- **Checks**: `tests/ui/audio_page_check.py <4..8|all>` drives the real page in headless Chromium against an isolated engine on port 8767 (temporary data folder). See its docstring.

Limits: browser playback is not sample accurate (judge the mix by ear, then use Master); the effects fader sets sfx, ambience and foley together; with a dialogue fader move the exact ducking changes only after Preview mix; no loudness meter in the browser (Master measures on the server); no library search box; no live timeline audio in Edit.
