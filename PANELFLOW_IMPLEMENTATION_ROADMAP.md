# PanelFlow Studio 2.0 Implementation Roadmap

## Milestone 0 — foundation and release hygiene

**Done/in progress**

- Fix frontend build blocker.
- Keep Tauri build green.
- Make implicit mock story fallbacks opt-in.
- Schedule persisted job retries.
- Fail loudly on SQLite migration errors.
- Add focused ComfyUI capability tests.
- Publish the four architecture/audit documents.

**Exit criteria**

- `npm run build` passes.
- `cargo check` passes.
- Focused Python tests pass.
- Full Python environment is reproducible and the complete suite runs in CI.

## Milestone 1 — ComfyUI single-image vertical slice

**Implemented backend slice**

- Added an approved workflow registry with SHA-256 verification for the installed API-format Qwen/LongCat workflows.
- Registered `manga_image_generation` as the first text-to-image workflow.
- Added safe workflow parameter patching for prompt, negative prompt, dimensions, seed and output prefix.
- Added project-scoped `AssetRecord` persistence with image dimensions, byte size, checksum and provenance.
- Added ComfyUI image job submission through the existing `job_manager`.
- Added ComfyUI output retrieval and image decodability validation.
- Added API endpoints for registry inspection, image job submission and generated-asset listing.
- Added typed frontend API-client methods for the new endpoints.
- Verified one real 512×768 image generation against the local ComfyUI instance.

**Implemented since initial slice:** desktop prompt/job/asset UI and required-model/node preflight.

**Remaining release gate:** API-level queue/restart integration, complete project filesystem and durable-job security review, and an independent passing pre-commit verdict. The real generated image and asset persistence are verified; this does not imply release readiness.

## Milestone 2 — Story Bible and Character Registry

- Add versioned story-bible documents.
- Add canonical character records, reference assets, attributes and approval state.
- Persist generation model/workflow/seed/provenance.
- Add reference selection to scene jobs.
- Add human review for canon changes.

**Acceptance:** two recurring original characters retain approved identifying traits across a small scene set, subject to human review.

## Milestone 3 — storyboard and asset reuse

- Convert an approved screenplay into scene and shot contracts.
- Choose reuse, crop/reframe, edit or new generation per shot.
- Generate only missing visual requirements.
- Preserve approved scenes when another scene is regenerated.

**Acceptance:** 8–12 shots for one short story, with at least one approved asset reused.

## Milestone 4 — narrated motion-comic slice

- Reuse existing TTS and render systems.
- Add segment-level voice replacement.
- Build a deterministic 1080p timeline.
- Add selective pan/zoom, transitions, subtitles and audio alignment.
- Validate the final media file with FFprobe and a playback smoke test.

**Acceptance:** approximately 60 seconds, 1920×1080, correct audio/video duration and editable project reopen.

## Milestone 5 — QC and rights

- Unify narrative, visual, audio and video checks.
- Add finite repair loops and manual-review escalation.
- Add rights/provenance export.
- Require cloud-cost and destructive-operation approval.
- Add backups, quota enforcement and recovery tests.

## Milestone 6 — Hermes Studio Director

- Expose selected PanelFlow APIs through a dedicated MCP server.
- Use project-scoped tokens/permissions and idempotency keys.
- Persist director decisions and task envelopes in PanelFlow.
- Add bounded delegation and approval states.
- Keep PanelFlow operational when Hermes is offline.

## Priority order

1. Reproducible Python environment and full regression execution.
2. ComfyUI approved-workflow job slice.
3. Character/reference persistence.
4. Storyboard and asset reuse.
5. Narrated 1080p artifact acceptance.
6. Unified QC and rights report.
7. Hermes tool bridge and autonomous coordination.

## Non-goals for the first release

- Automatic model downloads.
- Automatic third-party custom-node installation.
- Unbounded multi-agent conversations.
- Claims of perfect character consistency or copyright safety.
- Image-to-video generation as a hard dependency.
