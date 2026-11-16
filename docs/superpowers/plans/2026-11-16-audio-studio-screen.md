# Audio Studio Screen Implementation Plan

> Executed natively in this session, milestone by milestone, each committed; test first (TDD) for engine code, headless-browser checks for the page. Spec: `docs/superpowers/specs/2026-11-16-audio-studio-screen-design.md`.

**Goal:** a top-level Audio Studio tab with narration, music, effects and mix, linked both ways with Video Studio, on the same sound plan the agents use.

**Architecture:** engine gets narration cues (provider + mixing + QA) and a few convenience endpoints; `audio.js` becomes a factory with two hosts (rail page, full tab); a Create panel and hand-off buttons are added; everything else is reused.

## Global constraints
- Branch `feat/audio-screen`, worktree `.worktrees/audio-screen`; Python `E:/VIJAY SEKAR/PanelFlow Studio/.venv/Scripts/python.exe` with `PYTHONPATH=<worktree>`; isolated test engine on :8767 with a temporary data folder; never touch the live engine (8765) or its data; commit only own files.
- Local-first: no cloud, no silent fallback between speech providers; a missing tool says so. Model/file downloads need the owner's approval first.
- Do not change Video Studio behaviour except the hand-off buttons; layout rules in `layout.css`; page text uses `textContent`; engine token on media URLs.
- GPU is shared: Kokoro (CPU capable) is the default narration provider; Qwen3-TTS and ACE-Step go through the GPU slot and say "GPU busy" instead of forcing.

## Review Focus
- A plan with narration cues only / original audio only / both / neither: mix, preview, export do not crash and stems keep the video length.
- A narration line longer than the room before the next cue/cut: flagged, not silently truncated.
- TTS tool missing or GPU busy: the cue fails with the reason; nothing fake is produced.
- Two page instances (rail page and tab) never play at once; switching tabs while playing pauses.
- Hand-offs: timeline with no clips, a render that fails, a moved/deleted video file, the same video opened from both studios.

## Milestones
### M1 Engine: narration cues, provider, mix, QA
- Plan fields (`keep_original_audio`, `source`, cue `text/voice/provider/speed/pause_before`) with defaults that keep old plans valid.
- `sources/narration.py`: `NarrationProvider` (kind `narration`): Kokoro in-process, Qwen3-TTS via its runner; injectable synth for tests; availability probes; voices list; length estimate.
- `mix.render_roles`: dialogue stem = narration cue wavs (+ original audio when `keep_original_audio`); music ducks under the sum.
- QA: `narration_overrun` (line runs into the next dialogue cue or the next picture cut by more than 0.15 s), `narration_too_fast` (words per second above 4.2).
- Engine registers the provider; skill/doc updated. Real check: one Kokoro line and one Qwen3-TTS line generated, measured, spectrogram looked at.

### M2 API and MCP conveniences
`GET /voices`, `POST /narration/sample`, `POST /search` (library search without a cue), `POST /plans/from_timeline`, `POST /plans/{id}/script` (paste -> narration cues, back to back or per cut), `POST /plans/{id}/auto` (Spot -> draft -> source all -> preview -> QA, returns a summary), `POST /plans/{id}/fix` (re-source clipped/silent, nudge late hits); MCP tools for each; tests.

### M3 The screen
`audio.js` factory (two hosts), new top tab and `tab-audio` layout, start-here strip, panel titles with one-line purposes, Create panel (Narration / Music / Effects / Cues), inspector for narration cues (words, voice, speed, pause, retake), full mixer with loudness presets, Auto sound design and Fix problems buttons. Browser checks for each.

### M4 Hand-offs
"Sound this timeline" (Video Studio -> Audio Studio, cuts from the timeline), "Open in Audio Studio" on Media cards, "Show in Video Studio" (jump the Edit playhead), "Send mix to Video Studio" (export + library import + open). Browser checks on a real timeline.

### M5 Verify, document, review, merge
Real run: a reel narrated with Kokoro and Qwen3-TTS, music from ACE-Step if the GPU allows, mixed, exported, sent back to Video Studio; screenshots looked at; docs; fresh whole-branch review; fix important findings test-first; ask the owner before merging or pushing.
