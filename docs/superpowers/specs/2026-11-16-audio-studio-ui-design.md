# Audio Studio UI (Phase 4) - design (2026-11-16)

Status: approved to proceed by the owner ("proceed", 2026-11-16, after the proposal below). The owner did not answer the open question about how they use the screen; the layout and behaviour here are my calls and are marked as such. Builds on the Phase 1 engine (`docs/AUDIO_STUDIO.md`) and the earlier spec (`2026-11-15-audio-studio-design.md`, section 5.4).

## Intent
A sixth ChronoFlow rail page, **Audio**, that is the cockpit for the sound plan: see what an agent built, play the video with the mix, audition and pick sounds, move hits, fix problems, mix and export. Also enough hand tools to build a plan without an agent. It should look like the other pages (dark navy, blue accents, fixed frame, panels scroll inside themselves) and be driven by the Phase 1 REST API only (no second source of truth).

Goals: play video + three stems in sync with instant faders and meters; waveform lanes per track with hit markers and picture cuts; drag a hit and it snaps to frames and cuts; Ask-me audition (play each candidate, pick); QA findings you can click to jump to the cue; one-click Spot / Source all / Preview / Master / Export.
Non-goals (Phase 4): editing the timeline's own audio, VST/plugins, sample-level editing, recording, a library search box (needs a new API), sample-accurate browser playback, loudness metering in the browser (the master's LUFS/true peak come from the server's measurement).
Anti-goals: a second copy of the mix logic in JavaScript that can disagree with the exported mix; any change to how Edit/Color/Fusion/Deliver behave; touching the owner's running engine data while testing.

## Calls I made (state, with reason)
1. **Picture source = a finished video file**, opened from the Media library ("Open in Audio") or a file picker. Reason: reels, stories and films are finished files, not timeline projects; it matches Phase 1 and the pro habit of locking picture first. Not the live timeline. (Cost if wrong: timeline audio tracks would be a different, larger project.)
2. **Preview = server-rendered stems played in the browser.** The server renders dialogue / music / effects with the same code as the export, compresses them (m4a) and returns waveform peaks; the page plays the video muted plus three `<audio>` elements through Web Audio gain nodes, so faders and mute are instant and what you hear is the exported mix. Changing a cue marks the preview stale; "Preview" re-renders (seconds). (Cost: a few seconds after each edit; chosen over re-implementing ducking in JS.)
3. **Sync** = the video element is the clock; each stem follows it and is re-seeked when it drifts more than 60 ms. Good enough for judging a mix, not sample accurate.
4. **Module pattern** = `audio.js` + `audio.css` + pure `audio-model.js`, a rail button, `data-page="audio"` rules in `layout.css`, exactly like Color/Fusion/Deliver. The Edit monitor and timeline are hidden on this page; Audio brings its own `<video>`.
5. **Built on its own branch in a separate worktree** (`feat/audio-ui`) with an isolated test engine on port 8767 and a temporary data folder, because the shared tree belongs to other sessions and your live engine on 8765 runs older code.

## Layout (1600x900 reference; panels resize with the existing drag handles)
```
+--------------------+---------------------------+--------------------+
| SOUND PLAN         |  [video, muted]           | CUE INSPECTOR      |
| plan / mode / CC-BY|                           | intent  kind  track|
| [Spot][Source all] |   00:00:12:05             | hit time  anchor   |
| cues (status chip) |   transport  ◀ ▶ ▶|       | gain  fades        |
| QA findings        |                           | takes / candidates |
+--------------------+---------------------------+ ▶ audition  Pick   |
| ruler + cuts + playhead                        | source, licence    |
| DX  |   ▂▃▆▃▂   ▂▂▆▆▃▂   |  lanes, one row per  | [Source][Delete]   |
| MX  |▁▂▃▃▃▂▂▂▃▃▃▃▂▂▁▁▂▂▃|  track; cue blocks   |                    |
| SFX |   ┃        ┃   ┃   |  with waveforms and  |                    |
| AMB |▁▁▂▂▁▁▂▂▁▁▁▂▂▂▁▁▁▁|  hit markers         |                    |
| FOL |                    |                      |                    |
+------------------------------------------------+--------------------+
| mixer: DX ▮ MX ▮ SFX+AMB+FOL ▮  M S  fader  meter | MASTER -14.1 LUFS  |
|  [Preview mix] [Master] [Export]                  | -1.5 dBTP  LRA 4.7 |
+---------------------------------------------------------------------+
```
Mixer strips are the three stems the preview plays (dialogue, music, effects); per-track gain in the plan (`tracks[].gain_db`) is what the fader writes, so the master and export use it too. Mute/solo are preview-only.

## Behaviour
- **Open**: Media card "Open in Audio" or "Open video..." picks a file; if a plan for that file exists it is reused, else `create_plan`. A plan switcher lists existing plans.
- **Cue list**: every cue with a status chip (draft / needs pick / ready / failed + reason), click selects and moves the playhead to it.
- **Lanes**: one row per role; blocks positioned by hit/in time with the chosen take's waveform; draft/failed cues drawn hollow; picture cuts as thin vertical lines; wheel = zoom at cursor, shift-wheel or drag = scroll, click ruler = seek.
- **Drag a block**: moves `hit_t` (hit cues) or `t_in/t_out` (beds, music), snapped to the nearest frame, or to a picture cut when within 8 px; saved with `put_plan` after the drag ends; arrow keys nudge one frame (shift = 10).
- **Inspector**: edits intent, kind, track, anchor, gain, fades, mode; shows provenance with the licence and a link; "Source" runs `source_cue` (Auto/Ask); candidates list with ▶ audition (plays the candidate alone, on the cue's time), waveform and "Pick".
- **Transport**: space play/pause, left/right = frame, home/end, L loops the selected cue region. Time code is `hh:mm:ss:ff` from the plan's fps.
- **QA**: runs `qa`, lists findings; click a finding selects its cue; placement error shown on the block.
- **Master / Export**: call `mix` / `export`, show LUFS, true peak, LRA and the folder.
- **Errors** from the API (404, 400 with a message) show in a status line; nothing fails silently.

## API additions (backend, small)
`GET /plans` list; `GET /plans/{id}/video` (Range-capable); `POST /plans/{id}/preview` -> stems (m4a) + peaks, cached per plan version; `GET /plans/{id}/takes/{take_id}/peaks`; `plan.cuts` stored by `spot`. Everything else exists.

## Verification (owner's rule: real data)
Pure logic: `node --test` on `audio-model.js`. Backend: pytest. UI: headless Chromium (Playwright) against the isolated test engine on 8767, driving a real reel and a real plan; screenshots are opened and looked at; console must show no errors; a real drag, an Ask-me pick and a preview render are exercised. Not verifiable here: hearing the audio, the Tauri window, the owner's live engine (needs a restart to expose the new endpoints).

## Risks / unknowns
Browser sync drift on long videos (Dawn Gate is 9:25); 9-minute stems as m4a are ~20 MB each; autoplay policy needs a user gesture before audio starts; the Browser pane may be too narrow to judge layout, so screenshots are taken at 1600x900 headless.
