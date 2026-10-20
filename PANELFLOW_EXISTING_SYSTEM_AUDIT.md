# PanelFlow Studio Existing System Audit

**Audit date:** 2026-10-19
**Repository:** `C:\Users\Vijaya sekhar\Tools\PanelFlow Studio`

## Executive assessment

PanelFlow is a substantial beta-stage desktop production application, not a blank prototype. The existing architecture is suitable for incremental expansion, but it is not release-ready for the requested original-story-to-video workflow yet.

The current release blockers were verified and one frontend blocker is fixed:

- `npm run build` now passes after removing an unsupported `variant` prop from `ProgressBar`.
- `cargo check` passes for the Tauri shell.
- Three focused ComfyUI client tests pass.
- The full Python suite still cannot run in the active environment because `pytest` and several runtime packages are not installed.
- Production story generation previously had implicit mock/deterministic fallbacks. These are now opt-in for mock LLM use.
- Job retry backoff was persisted but not actually scheduled; retry scheduling is now wired into the job manager.

## Architecture

| Layer | Verified implementation |
|---|---|
| Desktop UI | React + TypeScript + Vite in `apps/desktop` |
| Desktop shell | Tauri 2 Rust application in `apps/desktop/src-tauri` |
| Engine/API | FastAPI application in `engine/api` |
| Persistence | SQLite with WAL and foreign-key configuration; custom additive schema migration logic |
| Jobs | Durable job records, progress, cancellation, leases, dependencies, retries and resource admission in `engine/jobs` |
| Story pipeline | Acquisition/import → page normalization → panel detection/correction → OCR/text regions → story analysis → script adaptation → audio/TTS → motion/render/export |
| Shared packages | `packages/api-client`, `packages/shared-types`, `packages/ui` |
| Test assets | Synthetic panel fixtures, sample comic, benchmark fixtures and unit/integration/acceptance scripts |

The desktop engine endpoint observed in repository configuration is `127.0.0.1:8765`. Tauri owns the engine process; no second engine should be introduced for ComfyUI.

## Strong existing areas

- Visual storytelling has panel ordering, schema validation, checkpoint files, provenance metadata, source/context hashes and resume-oriented structure.
- Acquisition and panel analysis have extensive fixtures and acceptance scripts.
- The job manager already models durable work rather than relying only on an in-memory queue.
- Tauri/Rust compilation is healthy.
- The existing audio, motion and render modules provide a base for a narrated motion-comic vertical slice.

## Verified local AI environment

| Service/resource | Verified state |
|---|---|
| ComfyUI | Running at `http://127.0.0.1:8188`; API reports version `0.42.0`; queue had 0 running and 0 pending jobs |
| ComfyUI nodes | `/object_info` returned 2,695 node classes |
| ComfyUI workflows | 5 JSON files discovered under `C:\Users\Vijaya sekhar\claude\ComfyUI\workflow` |
| ComfyUI model inventory | 2 checkpoints, 8 diffusion models, 1 UNet, 10 VAEs, 6 LoRAs and 2 ControlNet entries discovered |
| GPU | NVIDIA GeForce RTX 5060 Ti; 16,311 MiB total, 9,950 MiB free at audit time |
| Ollama | Running at `http://127.0.0.1:11434` |
| Ollama models | `qwen3.8:27b`, `qwen3-coder:30b`, `qwen3-coder-gamedev:latest`, `qwen3-coder-16k:latest`, `qwen-extended:latest`, `qwen3.6:latest`, `x/flux2-klein:latest`, `kimi-k2.7-code:cloud`, `qwen3.5:9b`, `gemma4:latest` |
| FFmpeg/FFprobe | Installed and discoverable from PATH |
| Hermes | Active default profile exists; configuration contains a Comfy MCP entry. PanelFlow does not yet expose a dedicated PanelFlow MCP tool server. |

Model names are recorded as installed identifiers only. No model license, commercial-use permission, or capability is inferred from a name.

## Current implementation changes

1. Removed the unsupported `variant="accent"` argument from `ProgressBar`.
2. Added a bounded `engine/comfyui` client with:
   - health/system statistics;
   - queue status;
   - node catalog discovery;
   - configured workflow discovery;
   - local model inventory discovery;
   - API-format prompt submission primitive;
   - history lookup with prompt-id validation.
3. Added read-only API endpoints:
   - `GET /api/comfyui/capabilities`
   - `GET /api/comfyui/workflows`
4. Added focused tests for workflow scoping, fail-closed health behavior and prompt validation.
5. Job retries now schedule a new runner after the persisted exponential backoff.
6. SQLite migration failures are logged and raised instead of being silently swallowed.
7. Implicit mock LLM fallback is disabled unless `PANELFLOW_ALLOW_MOCK_LLM` is set. Explicit `mock_llm` selection remains available for fixtures/tests.
8. Deterministic narration fallback is now test-only and fails closed in production.

## Important limitations discovered

- The full Python dependency set is not represented by a reproducible project lock file visible in the repository. The active environment lacks `pytest`, `sqlalchemy`, `numpy`, OpenCV and `soundfile`.
- The ComfyUI bridge currently discovers capabilities but does not yet register approved workflows or submit image jobs through PanelFlow's durable job queue.
- Character registry, approved reference assets, identity measurements and asset reuse policy are not yet a complete production subsystem.
- There is no dedicated PanelFlow MCP server with project-scoped permissions, idempotency keys, approvals and audit logs.
- TTS and render modules exist, but a verified original-story end-to-end 60-second export has not been executed in this environment.
- Music-generation capability and licensing are not verified as a working production integration.
- Migration handling is custom SQLite logic rather than a versioned migration framework.

## Release recommendation

Treat the current project as **beta infrastructure with a working foundation**, not as commercially ready. The next production milestone should be an approved-workflow ComfyUI image job submitted through the existing PanelFlow job manager, followed by character-reference persistence and an artifact-verified single-scene export.
