# UI v2: uncovered areas and missing wiring

Kept current during the UI v2 work (spec: `docs/superpowers/specs/2026-11-08-ui-v2-design.md`).
Generated list: `node scripts/audit-api-usage.mjs` (228 `api-client` methods; 34 had no caller in `apps/desktop/src` on 2026-11-08).
"Route exists" means the engine router defines the endpoint (checked by grep, not by calling it).

## 1. Engine features with a client method and a route, but no UI

| Area | Client methods | Notes |
|---|---|---|
| Render | `getRenderProfiles`, `getRenderValidation`, `subscribeRenderEvents` | Routes `/api/render/profiles`, `/api/projects/{id}/render/jobs/{job}/validation`, `/api/render/events` exist. The Render screen polls instead of using events and shows no validation report or profile picker. Decide in M5. |
| Music | `getMusicServiceHealth`, `saveProjectMusicPlan`, `updateCuePrompt`, `listProjectMusicTakes`, `selectMusicTake`, `addTakeToTimeline` | Routes under `/api/projects/{id}/music/*` exist. No screen picks between generated takes or edits cue prompts. Belongs to the audio library work in M7. |
| Jobs | `listBatchJobs` (`/api/series/batch-jobs`), `listAnimeJobs` (`/api/anime/jobs`) | The M3 Jobs page lists engine jobs (`/api/jobs`) only; series batch jobs and anime jobs are still not shown. Their payload shape has not been checked against `Job`. |
| YouTube | `listYoutubeChannels`, `getYoutubeAgentSettings` | Original Stories shows one channel preset list from a different endpoint. M4 (Settings, YouTube). |
| System | `setConcurrencySettings`, `getAllAvailableLLMProviders`, `getAudioProviders` | Still unwired after M4a. The Models section saves the concurrency mode and slot limit through the Ollama config (`saveOllamaConfig`), which is the same setting; the separate concurrency endpoint, the "all providers" list and the audio provider list have no UI. |
| Motion graphics | `renderMotionGraphic`, `getMotionPreset` | Router `/api/motion-graphics/*` exists; the editor inspector does not call these. M7. |
| Narration | `harmonizeNarration` | Route `/api/projects/{id}/narration/harmonize` exists. M7. |
| Files | `browseFilesystem` | `/api/system/browse` exists; the new-project screen uses its own picker. |
| Adapters | `listAdapters` | `/api/adapters` exists; source adapters are chosen elsewhere. |

## 2. Client methods whose endpoint could not be confirmed or that look superseded

`generateScript`, `generateAudio`, `acceptAudioDraft`, `acceptSynthesizedAudio`, `approveAudioTimeline`, `acceptMotionPlan`, `approveMotionTimeline`, `setShotOverrides`, `applyMotionOverrides` (1 internal caller), `updateAdaptedBlock`, `mergeScenes`.
The scripted extraction found no literal path for several of these, so they are probably thin wrappers over other methods or from an older pipeline. Read each before deleting; remove in M8 if dead.
Not a gap: `executeProjectHistoryCommand` (used by 39 history methods) and `getPanelOCR` (used by another client method).

## 3. Engine features with no dedicated screen (not seen in the UI at all)

- Film pipeline (`/film/job`), explainer batches, the upload kit (`1_TO_UPLOAD` / `2_ALREADY_UPLOADED`): driven from MCP and scripts only.
- Shorts (vertical cut) and channel watermark on original-story videos: not built (AGENTS.md).
- "Opening the desktop UI in a real window" (Tauri) has never been checked (AGENTS.md); verified in M2.

## 4. Wiring problems found in the existing UI

- ~~Dashboard nav "Library" opens the Tools and Models modal.~~ Fixed in M3 (the dashboard is gone). The engine modal is still reachable from Settings; M4 replaces it.
- Auto-Pilot has two buttons on pipeline screens (header and stage bar). Fixed in M2.
- `body { user-select: none }` blocks copying OCR text and scripts. Fixed in M2.
- `handleOpenProject` sends projects at `NORMALIZED` or `PANELS_DETECTED` straight to OCR (or Story when visual storytelling is on) and skips the Panels review stage. M2 keeps this behaviour in `stageForProject`; **owner to confirm whether skipping panel review is intended.**
- A broken panel thumbnail ("Panel 1" with a broken image icon) appeared in the OCR screen's panel list while auditing; not yet diagnosed (may be a project with missing files).
- `ProjectsScreen.tsx` is imported by `App.tsx` but never rendered: dead; removed in M2.

## 5. Decisions deferred

- A single engine `/inbox` endpoint (the Home inbox is aggregated client-side in M3).
- Light theme ("Paper").

## 6. Changes in M3 (Home, Projects, Jobs)

- Fixed: the four queue views are one Jobs page (`JobActivityPanel` stays because the editor and error modal use it; `NarrationJobQueue` stays inside Narration Studio, M7). `MultiProjectQueueDashboard` was never used and is deleted.
- New gap: **Library has no standalone screen.** `AudioLibrary` renders mock assets (`MOCK_AUDIO_ASSETS`) and defaults to a hard-coded project id, so `/library` shows an honest placeholder. Music and sound effects are chosen inside the story editor. A real library is M7 work.
- New gap: **"Ready to publish" on Home covers Original Stories episodes and projects at `QA_APPROVED` only.** The upload kit (`1_TO_UPLOAD`) and explainer batches have no API, so they cannot appear in the inbox.
- Dead tests found: the old `components/dashboard/__tests__` files used vitest, which is not installed, so they never ran. They were deleted with the dashboard; `groupBySeries` now has a node:test.
- Inbox rule to confirm: failed jobs older than 7 days are not shown, and a project shows one item (failed job, then rights, then review, then publish).

## 7. Changes in M4a (Settings)

- Fixed: engine, models, providers and diagnostics are one Settings area (`/settings/*`). The 148-line provider screen (`components/ai-gateway`) is deleted; its Routing, Usage and Gateway diagnostics tabs only ever said "not available" and are not replaced.
- Still open: **YouTube multi-channel settings (M4b).** The YouTube section shows connection status and opens the existing settings window, which stays because Narration Studio also uses it. It waits for the owner's uncommitted work in `ProviderHealthModal.tsx`, the api-client and `engine/youtube/*`. M4a left those files untouched (diff checksum identical before and after every task).
- Still open: the concurrency benchmark (`runConcurrencyBenchmark`) and the "Usage dashboard" idea have no UI.
- The old modal's Routing, Cloud, Ollama and System tabs are now duplicated by the new sections until M4b removes the modal's non-YouTube tabs.
- Settings never display a stored secret: the Ollama token and cloud API key are write-only (tests check the page, the query and mutation caches and storage).
