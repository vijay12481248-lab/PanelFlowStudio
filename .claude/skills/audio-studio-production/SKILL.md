---
name: audio-studio-production
description: Add music, sound effects and a loudness-correct mix to a finished PanelFlow video, with every hit landing on its frame - spot the cuts, write a cue sheet, source CC0 clips / code-made effects / ACE-Step music, check, mix with ducking, export stems and credits. Use when asked for sound design, SFX, a score, ducking, stems, or "make the audio for this video". Not for narration (Narration Studio) or lyrics songs (tools/songs).
---

# Audio Studio production (PanelFlow, local)

You drive the Audio Studio through MCP tools named `panelflow_chronoflow_audio_*` (profiles `chronoflow` and `all`) or the REST API under `/api/audio/studio` (OpenAPI at `/docs` on `127.0.0.1:8765`). Everything hangs off one document, the **sound plan** (cue sheet): you read it and write it, the engine sources, places, checks and mixes. Design: `docs/superpowers/specs/2026-11-15-audio-studio-design.md`; facts and limits: `docs/AUDIO_STUDIO.md`.

## Rules (the owner's, from AGENTS.md)
1. **Verify on real data.** Run `qa`, read the numbers, look at the spectrogram or waveform if you can. You cannot hear: say so, give the measurements, and ask the owner to listen before anything is published.
2. **CC0 by default.** `allow_cc_by` stays false unless the owner turns it on; then credits are written to `credits.txt` and must go in the video description. CC-NC and unknown licences are refused by the engine; do not work around it.
3. **Local-first, no silent fallback.** If a provider is down, `providers` says why and the cue ends `failed` with the reason. Never fake a sound, never switch to a cloud tool.
4. **Downloads of models/files need the owner's approval** (exact file, size, source). Fetching small CC0 clips through the engine is already approved.
5. **Generic, not per-story.** Write cue intents from what the picture shows; do not tune the engine to one video.
6. Originals only: never rip audio from another creator's video or from a piracy site.
7. Never restart the engine or ComfyUI mid-job. Commit only your own files.

## The order
1. `providers` - what works now.
2. `create_plan {video_path}` - probes fps and duration; the video's own audio is the dialogue unless you pass `dialogue_path` (e.g. the narration wav).
3. `spot` - finds picture cuts (ffmpeg scene score) and drafts one whoosh per cut plus one underscore. Low-contrast cuts can be missed: add hits yourself with `put_plan`.
4. Write the cues with `put_plan` (see below). Send only what changed: cues merge by id and unlisted cues stay; delete with `remove_cues` (e.g. drop the draft `music_1` if you will not use it, because `export` refuses draft cues).
5. `source_cue` per cue. `auto` picks and marks `ready`; `ask` leaves `candidates` with `status: needs_pick` for the owner, then `pick`. Use `ask` when taste matters (the signature sound, the main music), `auto` for fillers.
6. `qa` - fix every `error` (missing take, clipping, silent, placement over 40 ms); read each `warn`.
7. `mix` - preview master (dialogue + music ducked under it + effects, limiter, loudness). Check `integrated_lufs` and `true_peak_db`.
8. `export` - stems, `me.wav`, master, cue sheet, credits, `export.json`. Put `credits.txt` into the upload description.

## Writing cues
- **One hit = one cue.** `hit_t` is the second the sound must land on (the engine snaps it to the frame). Whooshes and risers use `anchor: "peak"` (their swell lands on the cut); impacts, clicks and pops use `"onset"`.
- `track`: `music`, `sfx`, `ambience`, `foley` (`dialogue` is the voice, not a cue).
- `kind`: the synth knows `whoosh impact click pop ding riser drop noise_bed`; any other word is only searched in the library. `music` goes to ACE-Step.
- `intent`: plain words about the sound, as you would search a library ("heavy wooden door slam"). Not timestamps, not story names. The Openverse search uses this text.
- Beds: `track: "ambience"`, `t_in`, `t_out`; a bed shorter than its span repeats with soft edges.
- Music: `t_in`, `t_out`, optional `hints: {bpm, key_scale}`. Without hints ACE-Step falls back to its defaults (85 BPM, D Minor), so set hints when the mood needs something else. Keep music out of the 2-5 kHz voice range in the prompt wording ("soft pads, no lead melody") when narration is on top.
- Gain: `gain_db` per cue, `tracks[].gain_db` per track. Music already ducks under dialogue; do not also turn it down by hand without a reason.

## Gotchas
- `put_plan` refuses `takes`, `chosen_take`, `status`, `reason`, `candidates` and `placement_error_ms`: sounds only enter a plan through `source_cue` / `pick`, so every take has a verified licence. Importing your own audio file is not supported in Phase 1.
- Parallel calls on one plan are safe (per-plan lock; slow work runs outside it), but two agents editing the same cue still means the last write wins for that cue.
- Generation is slow for music (ACE-Step); it holds the single GPU audio slot. If `providers` says "GPU busy", wait for the running job.
- `qa` renders each hit cue to measure where it lands. The number proves the pipeline is exact; it does not prove the detected onset is what a person hears. Spot-check the loudest hits by eye on a waveform.
- Library clips are Freesound previews (lossy mp3). Fine for video, not for a master you will re-process heavily.
- `export` refuses while any cue is `draft`, `needs_pick` or `failed`; use `allow_incomplete` only for a work-in-progress.
