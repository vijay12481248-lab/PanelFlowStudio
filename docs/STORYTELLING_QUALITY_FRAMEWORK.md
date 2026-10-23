# Storytelling Quality Framework

## Current blocking gates

- Story approval reruns continuity and canonical-state replay against current data.
- Script approval requires Narrative IR and rejects empty or unsupported speech.
- Evidence is scoped to cited panels and regions.
- Audio requires a current approved script and exact clip reconciliation.
- Synthesized and reused audio files must exist, contain frames, and report a positive duration.
- Timeline duration follows measured speech, including multiple lines per scene.

## Required benchmark work

Chapter 924 must receive reviewed panel count, OCR/utterance labels, speakers, scene boundaries, facts, and continuity state before being called golden. Baseline and candidate renders should be compared blind for clarity, pacing, voice naturalness, cinematic quality, continuity, and overall watchability on a documented 1–5 rubric.

## Deferred release gates

Add forced alignment and transcript comparison, loudness/true-peak measurement, black-frame and freeze detection, audio clipping/dropout checks, sync-drift localization, character-state checks, and selective repair. A green unit suite alone does not establish storytelling quality.

