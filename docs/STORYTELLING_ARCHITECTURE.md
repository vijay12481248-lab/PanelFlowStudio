# Storytelling Architecture

PanelFlow retains its three truth layers and adds a canonical-state and production bridge.

1. Layer A stores approved pages, panels, text regions, OCR, rights, and provenance.
2. Layer B stores observations, characters, scenes, beats, events, and the versioned `WorldState` contract.
3. Canonical replay applies only explicit state changes with source evidence and creator approval. Contradictions become blocking continuity warnings.
4. Layer C adapts approved Layer B facts into scripts. Approval fails when the narrative is missing, speech is empty, evidence is unrelated, or claims are unsupported.
5. The narration bridge maps each spoken script segment to an editor scene through panel evidence. Reused clips must match the approved script.
6. Audio timing is computed from measured WAV duration. Each scene receives the sum of its speech plus one 0.35 second breathing cushion.

Generated state approvals are reset to pending. Previously approved canonical state survives reanalysis only when the independently computed source-context digest is unchanged. A changed digest requires review.

The next vertical slices extend this foundation with performance-plan persistence, multi-panel allocation, smooth shot-plan integration, cue sheets/mastering, and final-video QA.

