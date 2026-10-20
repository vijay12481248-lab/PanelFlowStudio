# PanelFlow Studio 2.0 Gap Analysis

## P0 — release-blocking

### 1. Reproducible Python environment
**Problem:** The repository does not expose a complete, verified Python dependency lock strategy. The current environment cannot import at least `pytest`, `sqlalchemy`, `numpy`, OpenCV and `soundfile`.

**Impact:** Full regression results cannot be trusted because the suite does not execute.

**Improvement:** Add a supported `pyproject.toml`/lock workflow or pinned runtime and development requirements, then run the suite in a clean environment and CI. Do not hide missing dependencies behind fallback behavior.

### 2. ComfyUI generation path
**Problem:** ComfyUI is installed and healthy, but PanelFlow has no approved workflow registry connected to the durable job manager.

**Impact:** The requested core workflow still requires manual coordination between applications.

**Improvement:** Register workflows by purpose, validate node/model requirements before enqueueing, submit through `job_manager`, persist prompt IDs and metadata, retrieve outputs into a project-scoped asset directory, and verify the artifact before marking success.

### 3. Grounded story generation
**Problem:** Earlier code could silently return deterministic or mock narration when a real provider failed.

**Impact:** Users could mistake generic text for source-grounded analysis.

**Improvement:** Keep mock providers explicit and test-only. Production paths should return a visible provider error with recovery options. This fail-closed change has been started.

### 4. End-to-end acceptance evidence
**Problem:** No verified 60-second original fantasy production has been completed in the current environment.

**Impact:** Component-level success does not prove the system can create a coherent editable episode.

**Improvement:** Execute and retain a small artifact-based acceptance project before expanding scope.

## P1 — architecture gaps

### Hermes–PanelFlow boundary
PanelFlow needs a dedicated, least-privilege tool surface. Hermes should call APIs/tools, not databases or arbitrary filesystem operations. Each operation needs project scope, schema validation, idempotency, timeout, cancellation, audit record and human approval where cost, rights or destructive changes are involved.

### Story and character state
The current pipeline has story analysis and narration concepts, but 2.0 requires durable Story Bible, Character Registry, scene/shot contracts, canonical references and approval history. These should be first-class database entities or versioned project documents, not only conversation state.

### Workflow registry and model policy
A workflow file alone is not enough. PanelFlow needs:

- purpose and schema;
- required node classes;
- required model files;
- supported input/output types;
- GPU/VRAM estimate;
- model and custom-node provenance;
- allowed project modes;
- version and checksum;
- human approval state.

### Unified quality state machine
Existing validators are valuable but separate. Add a production-level state machine: `DRAFT → GENERATED → TECHNICALLY_VALID → REVIEW_REQUIRED → APPROVED` or `REJECTED → REPAIRING`, with finite retry budgets and defect-specific repair actions.

## P2 — product and commercial gaps

- Rights declarations, source license records, model/custom-node license metadata and export clearance need one reportable provenance model.
- Cloud-provider cost consent and budget enforcement are not yet a production gate.
- Asset backup, retention and disk-quota policies need explicit implementation.
- Project reopen/edit/export needs a repeatable recovery test.
- Stable voice identity, sentence-level regeneration and audio ducking need artifact-level tests.
- Music integration is not yet verified and must not be advertised until a licensed route is confirmed.
- UI needs a single place to show what Hermes changed, what is pending approval and what can be undone.
- Frontend test tooling and backend dependency installation need CI coverage.

## Deliberately deferred

Do not make image-to-video generation, autonomous code modification, uncontrolled agent loops or automatic custom-node downloads prerequisites for the first usable release. They increase cost, licensing and reliability risk without being required for a high-quality deterministic 2D motion-comic slice.
