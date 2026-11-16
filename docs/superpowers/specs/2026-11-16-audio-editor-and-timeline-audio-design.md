# Audio Studio as a sound editor + audio tracks in the Video Studio timeline

Date: 2026-11-16. Replaces the "Audio Studio screen" design of the same day (that screen showed the video, cues and a mix; the owner rejected it:
"the audio studio only has to edit the audio ... apart from that I don't want anything in the audio studio").

## What the owner asked for

1. **Audio Studio = sounds only.** Make, bring in, record, edit, manipulate, update and delete voice, music and sound effects. No video, no picture
   cuts, no cue sheet, no mix of a video.
2. **The sounds go onto the Video Studio timeline.** Placement against the picture happens in the Video Studio Edit page, on audio tracks.
3. **The quick Audio page in the Video Studio stays** as the helper that places sounds automatically on picture cuts; it gains
   "send to timeline".

## Shape

```
Audio Studio (tab)                           Video Studio > Edit (timeline)
┌ Library ┐┌ Waveform editor ──────┐┌ Tools ┐   V2 Frames
│ Voice   ││ ▁▃▇▅▂▁▁▃▆▇▅▃▁   [a──b] ││ Edit  │   V1 Video
│ Music   ││ transport · zoom · sel ││ Volume│   A1 Clip sound   (existing: each clip's own audio)
│ Effects ││                        ││ Time  │   A2 Voice    ┐
│ + New   │├ Versions · licence ────┤│ FX    │   A3 Music    ├ new: free-placed sounds from the library
└─────────┘└────────────────────────┘└ Clean ┘   A4 Effects  ┘
             [Send to Video Studio ▸]
```

## 1. Sound library (engine, `engine/audio/library/`)

A **sound** is one audio file with a name, a kind (`voice`, `music`, `effect`), where it came from and its versions.

- Store: `<app data>/audio_library/<sound id>/` with `sound.json` and `v001.wav`, `v002.wav`, ... (48 kHz float WAV after the first step, so
  repeated edits do not lose quality). Writes go under a per-sound lock (the same lock + retry pattern as `PlanStore`).
- `sound.json`: `id, name, kind, created, versions: [{n, file, op, params, created, duration_s, peak_db, lufs}], current, provenance
  {source, licence, model, author, url}, trashed`.
- **Create** (each makes version 1 and records where it came from):
  - Voice: Kokoro / Qwen3-TTS through the existing `NarrationProvider` synth (text, voice, speed). Licence Apache-2.0.
  - Music: ACE-Step through the existing `sources/music.py` (description, length, bpm, key). Same GPU slot and lock. MIT.
  - Effect: the code-made `SynthProvider` kinds (whoosh, impact, riser, click, ...) and Openverse CC0 search (CC-BY only when the
    owner allows it, as now). Openverse results are picked by ear first, as in Ask-me mode.
  - Import: any file ffmpeg can read (wav, mp3, m4a, flac, ogg, or the sound track of a video). Provenance `import`, licence `owner`
    (the owner vouches for files they bring).
  - Record: the browser records the microphone (MediaRecorder); the upload becomes a sound. Provenance `recording`, licence `owner`.
- **Edit** - every operation writes a new version from the current one with ffmpeg; nothing is overwritten. Undo = make an earlier version
  current; Redo = make the later one current again; a new edit after an undo drops the versions after the current one (as in every editor).
  Operations take an optional selection `[a, b]` in seconds; without one they apply to the whole sound.

  | Group | Operation | ffmpeg |
  |---|---|---|
  | Edit | trim to selection, delete selection, insert silence, split at a time (makes a second sound), duplicate, join two sounds | atrim / concat / anullsrc |
  | Volume | gain (dB), normalize (peak, or loudness to a target LUFS), fade in, fade out, silence the selection | volume / loudnorm / afade |
  | Time and pitch | speed (keeps pitch), pitch in semitones (keeps length), reverse, loop n times | rubberband (atempo when rubberband is missing) / areverse / aloop |
  | Effects | EQ presets (bass cut, warm, bright, telephone, radio) + 3-band EQ, reverb (room, hall), echo, compressor | equalizer / highpass / lowpass / aecho / acompressor |
  | Clean up | noise reduction (light, strong), de-ess, remove long silences, remove DC / hum (50 Hz, India mains) | afftdn / anlmdn / deesser / silenceremove / highpass + bandreject |

  A selection-only operation is done as: part before + processed selection + part after, joined with 10 ms cross-fades so there are no clicks.
- **Delete** moves the sound to `audio_library/_trash/` (restorable from the library's Trash filter); emptying the trash is a separate,
  confirmed action.
- **Peaks** for drawing: a cached `peaks.json` per version (the same peak code the quick Audio page uses).

REST `/api/audio/library/*`: `GET /sounds?kind=&q=&trash=`, `GET /sounds/{id}`, `POST /sounds/voice|music|effect` (async, GPU-aware),
`POST /sounds/import` (path or upload), `POST /sounds/record` (upload), `POST /sounds/{id}/edit {op, params, a, b}`,
`POST /sounds/{id}/undo|redo`, `POST /sounds/{id}/versions/{n}/current`, `PATCH /sounds/{id} {name, kind}`, `DELETE /sounds/{id}` (trash),
`POST /sounds/{id}/restore`, `GET /sounds/{id}/file?v=`, `GET /sounds/{id}/peaks?v=`, `GET /ops` (the operation list with parameter ranges, so the
UI and agents read one source).
MCP (domain chronoflow): `panelflow_audio_library_list / create / import / edit / undo / delete / send_to_timeline`.

## 2. Audio Studio screen (no video)

Three columns and a footer, all about the one sound that is open:

- **Library** (left): kind filter (All, Voice, Music, Effects, Trash), search, list rows with name, kind colour, length and source; a
  **+ New** menu: Speak text, Make music, Make an effect, Import a file, Record.
  Each "new" opens a short form in the right column (the same form controls the old screen had for narration, music and effects).
- **Editor** (centre): large waveform (zoom with the wheel, drag to select, click to set the playhead), time ruler, transport (play / pause /
  play selection / loop), selection readout `a - b (length)`, level meter. Keyboard: Space play, Delete delete selection, Ctrl+Z / Ctrl+Y.
- **Tools** (right): the five groups from the table as collapsible sections; each tool shows its parameters and an **Apply** button, and says
  whether it acts on the selection or the whole sound. A **Preview** plays the result before it is kept (rendered to a temporary file).
- **Footer**: version history (each step's name, click to go back), licence and source line, name and kind fields, **Delete**, and
  **Send to Video Studio** (adds the current version to the timeline's matching audio track at the playhead and switches to the Edit page).

What goes away from the tab: the video monitor, "open a video", steps strip, cue list, cue inspector, mixer strips, Master, Fix problems,
Send-with-sound. Those stay only on the quick Audio page inside the Video Studio, where they already live.

## 3. Audio tracks in the Video Studio timeline

- `model.js`: `tl.audio = [{id, sound, version, file, label, track: 'voice'|'music'|'effect', start, in, out, gain_db, fadeIn, fadeOut}]`, free-placed
  like the V2 overlays (no ripple). Pure functions with node tests: add, move (snap to frames, clip edges and markers), trim, split, delete, gain, fades.
- `nle.js`: lanes A2 Voice, A3 Music, A4 Effects under A1, with waveforms, drag / trim / blade / delete like overlays, per-lane mute and solo.
  Playback: each item is decoded once into an AudioBuffer and scheduled on the shared AudioContext at the playhead (start, offset, gain,
  fades), stopped and rescheduled on seek. Music ducks under Voice during playback with a simple gain envelope (the export does the real ducking).
- The Edit page's library panel gains a **Sounds** tab (the same `/api/audio/library/sounds` list); drag a sound onto a lane.
- Saved with the timeline (the same per-project timeline JSON); old timelines without `audio` load as before.
- **Export**: `render_timeline_edl` gets `audio=[...]`. After the picture master is made, the sounds are mixed with the clip sound by reusing
  `engine/audio/studio/mix.py`: each item becomes a ready cue with its file as the chosen take (voice -> dialogue stem, music -> music,
  effect -> sfx), so ducking under the voice, the -14 LUFS loudness target and the true-peak limit are the ones already measured. The master's
  sound is replaced by that mix.

## 4. Quick Audio page (helper) -> timeline

It keeps placing sounds on picture cuts (the Sound Plan). New button **Send to timeline**: every ready cue becomes a timeline audio item at its
time (dialogue/narration -> A2, music -> A3, sfx/ambience/foley -> A4), with its gain and fades, and its take is also saved into the library
(provenance kept) so it can be edited in the Audio Studio afterwards.

## Not in this version

Multitrack editing inside the Audio Studio (that is the timeline's job), spectral editing, plug-in hosting (VST), automation curves on the
timeline (gain is per item), stem separation (needs a new model download: ask first), cloud anything.

## How it is checked

- pytest: each edit operation on a real tone (length, level, pitch measured by FFT, selection boundaries without clicks), versions / undo /
  redo / trash, create paths with fake synths, REST, the timeline export mixing a voice item and a music item (ducking measured).
- node: the timeline audio model functions.
- Headless page checks: library, waveform selection, apply a tool, undo, send to the timeline; the A2-A4 lanes, drag, playback level, export.
- Real data: a real Kokoro line edited (trim, speed, pitch, reverb, noise reduction) and listened through spectrograms / measurements; a real
  timeline exported with voice + music + effect, loudness and ducking measured. Not verified by ear unless the owner listens.
