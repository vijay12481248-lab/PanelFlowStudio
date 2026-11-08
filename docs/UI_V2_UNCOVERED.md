# UI v2: uncovered areas and missing wiring

Kept current during the UI v2 work (spec: `docs/superpowers/specs/2026-11-08-ui-v2-design.md`).
Generated list: `node scripts/audit-api-usage.mjs` (228 `api-client` methods; 34 had no caller in `apps/desktop/src` on 2026-11-08).
"Route exists" means the engine router defines the endpoint (checked by grep, not by calling it).

## 1. Engine features with a client method and a route, but no UI

| Area | Client methods | Notes |
|---|---|---|
| Render | `getRenderProfiles`, `subscribeRenderEvents` (`getRenderValidation` is wired in the Publish stage since M5a) | Routes `/api/render/profiles`, `/api/projects/{id}/render/jobs/{job}/validation`, `/api/render/events` exist. The Render screen polls instead of using events and shows no validation report or profile picker. Decide in M5. |
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

## 8. Changes in M5a (workbench frame and Publish)

- Fixed: every pipeline stage sits in one frame (`WorkbenchFrame`): project header, rights and stage chips, one Auto-Pilot button, an Open story editor link, and a ten-step stepper (the old bar had no Pages or Publish step and could not show Blocked). `PipelineNavbar` is deleted. Five stage screens rendered a second `h1`; they now use `h2`.
- Fixed: the Auto-Pilot dialog could not be closed with Escape.
- New: **Publish stage** (checks, latest render with its validation report, YouTube packaging to copy). It never uploads, publishes or schedules.
- Still open: **pipeline projects cannot be uploaded to YouTube from PanelFlow.** The engine has an upload path only for Original Stories episodes; Publish hands off the title, description, chapters, tags and thumbnail prompt to copy into YouTube Studio.
- Still open: **`GET /api/projects/{id}/youtube/packaging` generates packaging when none is saved** (a slow local-model job), so the UI treats Get packaging as a generate action and never calls it on page open. A read-only "is packaging saved?" endpoint would let Publish show it without generating.
- Still open: render profiles and render progress events (`getRenderProfiles`, `subscribeRenderEvents`) are not used.
- Still open: **three legacy stage screens are still the old ones** inside the new frame (M5b rebuilt Acquire, Pages, Motion and Audio; M5c rebuilt Story and Script). Remaining: M5d Panels, OCR and Render. They keep their own back button, title and approve actions until then.
- Data observation (not a UI bug): the real project used for checking is at `RENDERED` but the engine lists no renders for it, so Publish shows "Render the video first". The October database restore may have lost render records.

## 9. Changes in M5b (Acquire, Pages, Motion, Audio)

- Fixed: the four legacy screens (2,637 lines) are deleted and replaced by v2 stages (`features/stages/*`) that sit in the workbench frame without their own back button, title or rights badge. `window.confirm` and `alert` are gone: deleting a page, replacing a motion plan and regenerating the voice track ask in an app dialog. Page order can be changed from the keyboard (Move earlier / Move later); drag and drop still works.
- Fixed (owner's "generic solutions only" rule): Audio no longer hard-codes one story's voices or matches default voices to character names ("marcus", "seraphina", ...). Voices come from `GET /api/audio/providers`; defaults depend only on the order of characters, their gender when known, and the order of voices. The `C:\Tools\Chatterbox` troubleshooting text is gone. The per-take native audio controls were removed: one player plays every take.
- Fixed (found on real data): the engine sends characters with `id` and a null `canonical_name`, so the old casting keys were undefined and nobody could be cast; the timeline uses `text`, `speaker_character_id` and `sample_rate` and has no speech count, so the old screen showed "0 takes" and an invented 48,000 Hz. Both now read the real fields; a missing sample rate says "Not reported". A saved narrator voice (`Narrator: am_michael`) is kept and shown.
- Fixed: a page whose file is missing on disk but whose status is READY said "Failed"; it now says "Image unavailable" ("Failed" is only for pages the engine marked failed).
- Changed: Acquire follows the newest acquisition or retry job (the old screen followed the newest job of any type). Pages keeps a "Continue to panels" button that moves on without confirming, as the old "Detect Panels" did.
- Still open: **Motion's per-shot choices (camera move, intensity, effect, prompt) are preview-only.** They feed an H3 preview and are not saved to the plan. The client has `setShotOverrides` / `applyMotionOverrides` and the engine has `POST /projects/{id}/motion/overrides`, but the override schema is not documented in the repo, so saving them was not wired. `acceptMotionPlan` and `approveMotionTimeline` (a copy of `approveMotion`) are still unused.
- Still open (engine side, outside this milestone): `/api/audio/providers` returns a fixed list of three voices (Aria, Marcus, Seraphina) and `_DEFAULT_VOICE_CASTING` in `engine/audio/service.py` is keyed on one story's characters. The real timeline was made with a different voice (`am_michael`) that the provider list does not know.
- Judgement to confirm: regenerating sends a default voice for every character that has no saved voice (the old screen did too). The checked project's timeline was narrator-only, so regenerating it would now voice characters. The change is visible in Voice casting and Regenerate asks first.
- Data observation: the checked project's page files return 404 (missing on disk), so Pages and Acquire show "Image unavailable" tiles. No project in the app has a saved motion plan, so Motion's shot cards were only tested with synthetic data.

## 10. Changes in M5c (Story, Script)

- Fixed: the legacy Story and Script screens and their two helpers (2,115 lines) are deleted and replaced by v2 stages. Re-analyzing, re-adapting, merging characters, removing a line and merging a line with the next one now ask first; the ten per-line buttons are one menu; no browser dialogs or console-only failures.
- Fixed (found on real data): `GET /characters` and `GET /scenes` send `id`, not `character_id` / `scene_id`, and every `canonical_name` is null. The old screens read the missing fields, so (from reading the code against the real field names, not run) the Scenes tab could not match beats to scenes and character edit, merge, split and the speaker list used an undefined id. The new stages build characters and scenes from the narrative document and accept `id` as a fallback. Checked in the real app: the Scenes tab shows each beat under its scene and characters show their display names.
- Fixed: story analysis defaulted to the **mock** provider for non-visual projects (against the "never fall back silently to mock" rule). No mock is ever preselected; it is labelled "Test data only"; with no healthy real model Run is disabled and says why.
- Fixed: "Faithfulness coverage" showed an invented `100%` when nothing had been validated (now "Not checked"); a stale "Milestone 4 Boundary Guard" banner claimed voice generation was locked (removed); the storyboard beat editor sent an intensity it could not change (it has a slider now); an approved script's unsupported statements were described as blocking approval (now reported as found); split asks for panels from a checklist of where the character speaks instead of typing panel ids; an unknown speaker id is shown as "Unknown", never raw.
- Disclosure: **opening the Script stage runs `POST /scripts/{id}/validate`**, which recomputes and saves the script's quality metrics (idempotent; the old screen did the same on every open). My browser and Playwright checks opened the Script stage of your projects several times, so those metrics were recomputed. I pressed no Validate, Approve, Generate, Re-adapt or edit button.
- Correction: the M5c plan said the checked project has no script row. That was my probe's mistake (I called `/script`; the route is `/scripts`). The project has an APPROVED script of 36 lines with 94 percent coverage and two unsupported statements (22 and 25); the stage shows them.
- Still open (engine side): `GET /characters` and `GET /scenes` should send the typed field names and a real name; a read-only validation report (validate writes metrics, so the UI cannot fetch the report without a write); `canonical_name` is null for every character.
- Data observation: the real narrative's utterances include site watermarks and credits read as dialogue (for example "MANHUAPLUS.COM", "FASTER RELEASE PLEASE READ"), so the Utterances tab is mostly OCR noise to reassign. That is the analysis, not the UI; a "watermark" filter at the analysis or OCR step would help.
- Not exercised against real data: Run or Re-analyze, Approve (Story and Script), Generate or Re-adapt, Validate (pressed), every edit, line action, character edit, merge and split (the dialogs were only opened and cancelled). Script editing flows are tested with synthetic data.
- The colour ratchet (`noRawColors.test.ts`) currently fails on `apps/desktop/src/components/ImageEditorModal.tsx`, an untracked file that is not part of this work; it needs tokens or an allowlist entry when it is committed.
