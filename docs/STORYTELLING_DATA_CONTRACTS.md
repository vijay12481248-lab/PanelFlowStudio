# Storytelling Data Contracts

## Canonical state

- `WorldState`: schema version, object ownership, character location, character knowledge, source evidence, and approval.
- `StateValue`: distinguishes an unknown fact from a known explicit `None` value.
- `StateChange`: domain, subject, optional knowledge fact, exact before/after values, provenance, and immutable approval record.
- `EventEntity.caused_by` and `EventEntity.enables`: ordered causal dependencies.

Replay is deterministic and non-mutating. An event is applied atomically only when its dependencies were applied, references exist, confidence is finite and sufficient, evidence resolves to source observations/utterances, approval is explicit, and its before-state matches canonical state.

## Narration production

- Input: approved `VideoScript`, matching `NarrativeDocument`, and editor scenes with source-panel layers.
- Output clip: source script ID, source segment IDs, source evidence, exact approved text, speaker/voice settings, and audio path.
- Reconciliation preserves creator voice, volume, and audio media only when clip text and scene match one unique approved segment.
- Synchronization accepts positive finite measured durations and mutates timing only after all inputs validate.

All additive canonical fields persist inside `NarrativeRecord.document`; no SQL schema migration is required for this slice.

