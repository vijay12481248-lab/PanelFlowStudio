# Manga storytelling implementation plan

**Goal:** Extend the current PanelFlow workflow with genuine vision-first chapter storytelling and actual local speech.

**Architecture:** Reuse acquisition, persistence, review, motion and render. Add a focused visual story engine behind a project setting and bridge existing local speech adapters.

**Tech stack:** Python, Pydantic, SQLAlchemy, FastAPI, React, TypeScript; installed local AI tooling.

**Spec:** User-provided manga workflow request and `MANGA_WORKFLOW_ARCHITECTURE_AUDIT.md`.

## Tasks

- [x] Audit existing working code and local tooling before implementation.
- [x] Add regression tests for image-based analysis, chapter memory, cache reuse, invalid references and refusal of mock output.
- [x] Implement checkpointed panel vision, chapter reasoning and original narration using existing domain models.
- [x] Route URL chapter projects through the visual engine and existing persistence transaction.
- [x] Add URL storytelling preferences and preserve manual imports.
- [x] Replace speech placeholders with installed local synthesis and selective caching.
- [x] Run relevant Python tests, desktop build, real URL discovery and provider readiness checks.
- [x] Document API/UI changes, run instructions, test evidence and remaining limitations.

## Constraints

Preserve existing uncommitted work. Do not download AI models. No invented chapter-specific story. OCR is supplementary. Keep script approval before audio generation. Reuse one renderer and one project model.
