# Storytelling Existing-System Audit

Verified 2026-10-23 against the live repository and local tool inventory.

## Reusable capabilities

- The three-layer Narrative IR already separates immutable source truth, narrative interpretation, and presentation scripts.
- `NarrativeRecord.document` persists the full Pydantic document as JSON, so additive world-state contracts require no destructive database migration.
- The script adapter and validator already carry panel and text-region provenance.
- Chatterbox Turbo, ACE-Step 1.5, and Lumina audio tooling are installed locally. Runtime and model health remain to be benchmarked.
- Story-aware music plans, render audio ducking, motion shot planning, durable history, and media invalidation already exist.
- Autopilot has nine stages from page ingestion through packaging.

## Verified gaps and first fixes

- Autopilot formerly swallowed script-generation errors, used the wrong `VideoScript` ID field, and marked the stage complete. It now fails the stage and requires successful validation and approval.
- Audio formerly invented generic `sample_bank` narration when no script was available. Audio now consumes only a current approved script and Narrative IR.
- Existing editor clips formerly bypassed the grounding gate. They now must match current approved script segments; creator voice/media choices are retained when they match.
- Script approval formerly treated a missing Narrative IR as fully supported. Service and durable-history approval paths now fail closed.
- Chapter-wide lexical overlap could support a claim using unrelated panels. Validation now limits evidence to cited panels, cited regions, the matching scene, and matching beats/events.
- Canonical equipment, location, and knowledge state did not exist. Versioned, explicit before/after state changes and deterministic continuity replay now exist.

## Benchmark reality

The live Magic Emperor Chapter 924 workspace is useful baseline material, but its current `narrative.json` has 49 observations, 4 characters, 7 scenes, 10 beats, and zero utterances. It therefore is not yet an independently annotated golden corpus. The existing renders and dialogue WAV files remain useful comparison artifacts after annotations and acceptance labels are added.

## Remaining gaps

- Narrative version history still replaces the active record instead of retaining reviewed versions.
- Performance fields exist in the domain model but are not fully persisted through SQL records.
- Multi-panel narration cannot yet be deliberately allocated across multiple one-panel editor scenes.
- Motion Autopilot still overwrites creator framing with a static camera instead of using the existing smooth shot planner.
- LUFS and true-peak mastering, forced alignment, final-video defect localization, and selective repair are not implemented end to end.

