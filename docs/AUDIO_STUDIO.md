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

Plans live in `<app data>/audio_studio/plans/<plan id>/` (`plan.json`, `takes/`, `renders/`, `exports/v<N>/`). No UI yet (Phase 4).

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
