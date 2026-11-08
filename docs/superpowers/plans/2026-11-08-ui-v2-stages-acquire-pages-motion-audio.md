# UI v2 Stage Rebuilds: Acquire, Pages, Motion, Audio Implementation Plan (M5b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four smallest legacy stage screens (Acquisition 331 lines, Page review 708, Motion 554, Audio 1,044) with v2 stages built on the workbench frame, keeping every engine call, approval gate and playback behaviour, and removing their duplicate headers, back buttons, `window.confirm` and `alert`.

**Architecture:** Each stage is `features/stages/<name>/` with a pure model (state machine, reorder, shot normalisation, default casting) covered by unit tests, thin React Query hooks, and v2 components. A small shared kit (`features/stages/kit`) holds what every stage needs: toolbar, confirm dialog, page thumbnail, job progress and the stage-navigation hook. The frame (M5a) already provides title, stepper and Auto-Pilot, so stages drop `onBack`, their own title and their own project header.

**Tech Stack:** React 18, `@panelflow/ui-v2`, react-router 7, `@tanstack/react-query` 5, `tsx --test`, Playwright on installed Chrome. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (section 6 "Workbench", section 7 row M5). Builds on M1 to M5a (done on `feat/ui-v2`). Open items: `docs/UI_V2_UNCOVERED.md`.

## Scope

- **In M5b:** Acquire, Pages, Motion, Audio (in that order of difficulty, Audio last because of its playback engine and voice casting). Shared stage kit. Removal of the four legacy screens and their `onBack` wiring.
- **Deferred:** M5c Story and Script; M5d Panels and OCR; Narration Studio (M7). `OriginalStories`, `ChronoFlow` and the Story Editor are not touched.
- **Facts from the code that shape this plan:**
  - Pages uses HTML5 drag to reorder, which a keyboard cannot do; the rebuild adds Move earlier / Move later buttons and keeps drag as a convenience.
  - Motion's per-shot controls (camera move, intensity, effect, prompt) only feed an H3 **preview**; they are never saved to the plan, although the engine has `POST /projects/{id}/motion/overrides` and the client has `setShotOverrides`. The rebuild states "Preview only" on those controls and does not wire saving, because the override schema is not documented in the repo (listed in `UI_V2_UNCOVERED.md`).
  - Audio picks default voices by **matching character names** to `marcus`, `seraphina`, `leon`, `kaelen` and `aria`, and its voice list and troubleshooting text are hard-coded. That is tuned to one story and breaks the owner's "generic solutions only" rule. The rebuild takes voices from `GET /api/audio/providers` and assigns defaults by a generic rule (see Task 6).
  - Audio's master player runs its own `HTMLAudioElement` sequencing (play intervals in order, pauses between, rate, volume, mute); that behaviour is extracted into a tested hook, not rewritten.
- The engine and the owner's uncommitted YouTube files stay untouched; `packages/api-client` is not edited.

## Global Constraints

- Semantic tokens only (the colour ratchet enforces it); sentence case, verb-first buttons, errors say what happened and what to do and never show a raw exception, empty states invite an action; status is never colour alone. Rights gate and the owner's rules unchanged: nothing here weakens an approval gate.
- Every approve, start, cancel, retry, delete and regenerate button guards against a fast double click with a synchronous ref and shows its busy state.
- No `window.confirm`, `window.alert` or `prompt`: destructive or costly actions use the shared `ConfirmDialog`; results use the toast from `useToast`.
- Polling and audio playback start only while the stage is mounted and visible work exists, and stop on unmount (tests assert no further calls after cleanup).
- Test commands: `npm run test:ui`, `cd apps/desktop && npx tsc --noEmit -p .`, `cd apps/desktop && npx playwright test`; run with `--tsconfig apps/desktop/tsconfig.json`; page tests use `features/__tests__/pageHarness.tsx` (`mountPage`, `settle`, `press`, `clickTwice`, `setValue`, `setSelect`).
- Commit only the files a task touches, with explicit paths (never `git add -A` on a folder). After each task `git diff HEAD` over the owner's files hashes the same as the baseline in the ledger (`done.sh` checks it). Real-data checks only read and navigate: do not press Start acquisition, Confirm, Plan, Generate, Regenerate, Approve or Delete on the owner's projects; say what was not exercised.
- Behaviour is preserved, so port each legacy screen's calls exactly (names below); where this plan says "same", the legacy file is the reference until it is deleted in Task 7.

## Review Focus

1. The approval gates are unchanged: Confirm acquisition, Approve motion and Approve audio call the same endpoints, show the engine's refusal in words, do not move to the next stage on failure, cannot be double-submitted, and are only enabled when their precondition holds (ready pages exist, a motion plan exists, an audio timeline exists). (Tasks 3, 5, 6)
2. Nothing is tuned to one story: default voice casting works for arbitrary character names and an engine voice list of any size, including empty. (Task 6)
3. Every destructive or costly action asks in an in-app dialog, and page reorder, rotate and delete work from the keyboard. (Tasks 1, 4)
4. Polling and playback stop when you leave the stage, and a job already running when the stage opens (acquisition, audio generation) is picked up, not restarted. (Tasks 3, 6)
5. Failed pages, no plan, no timeline, a broken image and an engine error each show the reason and the next action. (Tasks 3 to 6)

---

### Task 1: Stage kit and stage navigation

**Files:**
- Create: `apps/desktop/src/features/stages/kit/StageToolbar.tsx`, `ConfirmDialog.tsx`, `PageThumb.tsx`, `JobProgress.tsx`, `useStageNav.ts`, `stageData.ts`
- Modify: `apps/desktop/src/features/legacy/LegacyStageRoute.tsx` (use `useStageNav`; the legacy screens still get `onBack`, new ones do not)
- Test: `apps/desktop/src/features/stages/kit/__tests__/kit.test.tsx`, `useStageNav.test.tsx`

**Interfaces:**
- `StageToolbar({ title: string; description?: string; status?: React.ReactNode; actions?: React.ReactNode })`: renders an `h2` (the frame owns the `h1`), the description, a status slot and the actions.
- `ConfirmDialog({ open: boolean; title: string; description: string; confirmLabel: string; danger?: boolean; onConfirm: () => void; onCancel: () => void })`: built on the v2 `Dialog`; Cancel is the default focus; confirming calls `onConfirm` once.
- `PageThumb({ src?: string; label: string; failed?: boolean; selected?: boolean; onOpen?: () => void })`: 3:4 tile; an image that errors or `failed` shows the page label and the word "Failed", never a broken-image icon.
- `JobProgress({ job: Job | null | undefined; idleLabel: string })`: v2 `Progress` (`job.progress` is 0 to 1) plus `job.message`, a status chip in words (Running, Waiting, Done, Failed, Cancelled), and the idle label when there is no job.
- `useStageNav(project: Project, stage: Stage)`: `{ advance(updated: Project): void; goTo(stage: Stage): void; back(): void }` extracted from `StageScreen` in `LegacyStageRoute` (`advance` writes `updated` into the `["project", id]` query cache, then navigates to `nextStage(stage)`; `back` goes to `prevStage` or `/projects`).
- `stageData.ts`: `usePages(projectId: string)` (`api.listPages`, polls every 1000 ms only while `pollWhileActive` is true), `useProjectJobs(projectId: string)` (`api.listProjectJobs`, newest first, polls every 1500 ms while its newest job is `RUNNING` or `QUEUED`), `useJob(jobId: string | undefined)` (`api.getJob`, polls every 1000 ms while active), all gated on `useEngine().connected`.

- [ ] **Step 1: Write failing tests:** toolbar renders one `h2` and no `h1`; `ConfirmDialog` closed renders nothing, open shows title and description, Cancel calls `onCancel` only, a double click on the confirm button calls `onConfirm` once, Escape cancels; `PageThumb` with a failing image (fire `error`) shows the label and "Failed" and no `img`; `JobProgress` shows 40 percent for `progress: 0.4`, the message and "Running", and the idle label for `null`; `useStageNav` (rendered in a memory router with a query client): `advance` stores the project and navigates to the next stage, `back` from `acquire` goes to `/projects`, `goTo` navigates; the existing M2 route tests still pass.
- [ ] **Step 2:** Run the two files; expect FAIL. **Step 3:** Implement; refactor `LegacyStageRoute` to use `useStageNav` without changing behaviour. **Step 4:** Run `npm run test:ui` and `tsc`; expect PASS. **Step 5:** Commit: `feat(stages): shared stage kit and navigation hook`.

### Task 2: Acquire stage

**Files:**
- Create: `apps/desktop/src/features/stages/acquire/acquireModel.ts`, `AcquireStage.tsx`
- Test: `acquireModel.test.ts`, `acquireStage.test.tsx` (same folder `__tests__`)

**Interfaces:**
- `type AcquirePhase = "ready" | "running" | "succeeded" | "failed" | "cancelled"`; `acquirePhase(job: Job | null | undefined): AcquirePhase` (none gives ready; `RUNNING`/`QUEUED` running; `SUCCEEDED`; `FAILED`; `CANCELLED`); `pageCounts(pages: Page[]): { total: number; ready: number; failed: number }`; `acquireActions(phase: AcquirePhase, counts): { start: "Start acquisition" | "Restart acquisition" | null; cancel: boolean; retryFailed: number | null; review: boolean }` (start when ready, failed or cancelled with the Restart label unless ready; cancel only while running; retry failed only when not running and `failed > 0`; review when `ready > 0`).
- `AcquireStage({ project, onReviewPages })`: `StageToolbar` ("Acquire pages", actions Open source folder and Review pages (N)), status card with `JobProgress` and "N of M pages downloaded", buttons per `acquireActions` calling the same endpoints as the legacy screen (`api.startAcquisition` then `api.getJob`, `api.cancelJob`, `api.retryFailedPages`, `api.openProjectFolder`), a thumbnail grid of `PageThumb` using `api.getPageImageUrl`, failed pages flagged, an empty state with "Start acquisition" guidance. On mount it loads `usePages` and `useProjectJobs`; a running job found on mount is followed, not restarted. Errors are reported through `useError().reportError` with the legacy titles ("Cancel Job Failed", "Page Download Retry Failed", "Could Not Open Folder") and shown inline in words.

- [ ] **Step 1: Write failing tests:** the phase and action matrix (every phase times zero and some failed pages); `pageCounts`; stage test with stubbed `api`: ready state shows Start acquisition and the empty-state guidance, pressing it twice quickly calls `startAcquisition` once and then follows the new job; a running job on mount shows progress, Cancel and no Start, and polling stops after cleanup (no more `getJob` calls); a failed job with 2 failed pages offers Restart acquisition and "Retry failed pages (2)"; success with ready pages offers Review pages and calls `onReviewPages`; a rejected start shows "Couldn't start acquisition" with advice and no raw exception; the page grid shows a failed page as Failed.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(stages): Acquire stage`.

### Task 3: Pages stage

**Files:**
- Create: `apps/desktop/src/features/stages/pages/pagesModel.ts`, `PagesStage.tsx`, `PageInspector.tsx`, `ManifestDialog.tsx`
- Test: `pagesModel.test.ts`, `pagesStage.test.tsx`

**Interfaces:**
- `moveItem<T>(items: T[], from: number, to: number): T[]` (returns a new array; out-of-range indices return the input copy unchanged); `pageIdsAfterMove(pages: Page[], from: number, to: number): string[]`; `canConfirm(pages: Page[]): { ok: boolean; reason: string | null }` (needs at least one `READY` page; reason `"No pages are ready yet. Go back to Acquire."` otherwise; failed pages do not block but are counted in the button label).
- `PagesStage({ project, onConfirmed })`: `StageToolbar` ("Review pages", description "Confirm the order, rotate scans, remove blanks."), `Confirm acquisition (N pages)` primary button (same `api.confirmAcquisition(project.id)` then `onConfirmed(updated)`; guarded; refusal shown in words, no navigation on failure), `Retry failed pages`, `View manifest` (`api.getManifest` in `ManifestDialog`). Grid of `PageThumb`s with per-page Move earlier, Move later (disabled at the ends), Rotate (`api.rotatePage(project.id, page.id, 90)`, then refresh and bump a cache-buster on that page's image), Delete (opens `ConfirmDialog` "Delete page N? The remaining pages are renumbered." then `api.deletePage`), and drag-and-drop reorder as a convenience; every reorder calls `api.reorderPages(project.id, ids)` and on failure restores the previous order with an error in words. Clicking a page opens `PageInspector` (a v2 `Drawer`): the full page, view modes Fit width, Fit page, Original, zoom 25 to 400 percent in 25 steps, Rotate. The pages list is `usePages` without polling.

- [ ] **Step 1: Write failing tests:** `moveItem` and `pageIdsAfterMove` (middle, ends, out of range, no mutation); `canConfirm` with no pages, only failed pages, one ready page; stage tests: pages render in `sequence` order; Move later on the first page calls `reorderPages` once with the swapped ids and the grid updates; a failing `reorderPages` restores the order and shows the error; Move earlier is disabled on the first page; Rotate calls `rotatePage(…, 90)` once on a double click; Delete asks first, Cancel deletes nothing, confirming calls `deletePage` once and shows the remaining pages; no `window.confirm` or `window.alert` is called (spy that throws); Confirm acquisition is disabled with the reason when no page is ready, calls `confirmAcquisition` once and then `onConfirmed(updated)` otherwise, and a rejected confirmation shows the reason and does not call `onConfirmed`; the manifest dialog shows `getManifest` data; the inspector changes view mode and zoom within 25 to 400.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(stages): Pages stage`.

### Task 4: Motion stage

**Files:**
- Create: `apps/desktop/src/features/stages/motion/motionModel.ts`, `MotionStage.tsx`, `ShotCard.tsx`
- Test: `motionModel.test.ts`, `motionStage.test.tsx`

**Interfaces:**
- `type ShotView = { key: string; index: number; title: string | null; motionType: string; easing: string; startSec: number; endSec: number; durationSec: number; startCamera: Camera; endCamera: Camera; caption: { speaker: string; text: string } | null; transition: string | null; panelId: string | null }` with `type Camera = { center_x: number; center_y: number; zoom: number }`; `shotView(shot: any, index: number): ShotView` normalising the engine's alternative field names exactly as the legacy screen does (`camera_start` or `start_rect` else the default camera; `duration_sec`, `duration`, or `end_time - start_time`; `motion_type` or `camera_motion_type` else "CINEMATIC"; `easing` or `easing_function` else "SMOOTHSTEP"; first of `caption_cues`; `transition_in` as a string or its `transition_type` with `duration_sec`); `matchPanel(shot: any, index: number, panels: Panel[]): Panel | undefined` with the legacy three-step rule (provenance panel ids or `source_panel_id` or `panel_id`; then `panel_<n>` in `source_panel_id` matched by `sequence`; then `panels[index % panels.length]`); `formatClock(seconds: number): string` (`"6:10"`).
- `MotionStage({ project, onApproved })`: `StageToolbar` ("Plan camera motion"), preset select (the legacy `MotionStylePreset` values) and video engine select (`ken_burns`, `fast_h3`), `Plan motion` (same `api.planMotion(project.id, preset)`; if a plan already exists it asks first through `ConfirmDialog` "Replace the current plan?"), `Approve motion` (same `api.approveMotion` then `api.getProject`, then `onApproved(updated)`; enabled only when a plan exists and the stage is not already approved; guarded; refusal shown as "Motion can't be approved yet" plus the engine's reason), shot list of `ShotCard`s (`SvgCameraFramingVisualizer` from `@panelflow/ui` with the matched panel image from `api.getPanelImageUrl`, shot metadata, caption, start and end zoom). Each `ShotCard` keeps the H3 preview controls (camera move, intensity, effect, prompt tags) and `Generate preview` calling `api.previewShotVideo(project.id, panelId, motion, prompt, engine, intensity, fx)` with the returned `video_url` shown in a `<video controls>`; the controls are labelled "Preview only. These choices are not saved to the plan." No override is saved.

- [ ] **Step 1: Write failing tests:** `shotView` and `matchPanel` over a table of legacy field shapes (each alternative name, missing camera, string and object transitions, no panels, panel found by provenance, by `panel_3`, by wrap-around); `formatClock`; stage tests: no plan shows an invitation with Plan motion and no Approve; planning calls `planMotion(id, "cinematic")` once on a double click and then shows shots; an existing plan asks before replacing (Cancel makes no call); Approve is disabled without a plan and when already approved, calls `approveMotion` then `getProject` once and then `onApproved`, and a rejected approval shows the reason without calling `onApproved`; a shot with no matched panel disables Generate preview with the reason; Generate preview passes the chosen motion, intensity and effect and shows the returned video; the Preview only note is present; a failed preview shows "Couldn't make the preview" and keeps the controls.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(stages): Motion stage`.

### Task 5: Audio model and playback hook

**Files:**
- Create: `apps/desktop/src/features/stages/audio/casting.ts`, `useIntervalPlayback.ts`
- Test: `casting.test.ts`, `useIntervalPlayback.test.tsx`

**Interfaces:**
- `type Voice = { id: string; name: string; gender?: string }`; `voicesFromProviders(res: { primary_provider: string; providers: Array<{ id: string; voices?: any[] }> }): Voice[]` (the primary provider's voices, `id` from `voice.name ?? voice.id`, de-duplicated by name, `gender` kept when present; empty when none).
- `defaultCasting(characters: Array<{ character_id?: string; canonical_name: string; display_name?: string; gender?: string }>, voices: Voice[], current?: Record<string, string>): Record<string, string>` (keeps every entry already in `current`; the narrator key is not touched; for the rest it picks by this generic rule: prefer a voice whose `gender` equals the character's `gender` when both are known, taking the voices of that gender in turn; otherwise all non-narrator voices in turn in engine order; with no voices it leaves the key unset so the engine default applies; never reads a name). Keys are `character_id || canonical_name`, as the legacy screen.
- `useIntervalPlayback(intervals: AudioInterval[], opts: { urlFor(interval): string; createAudio?: () => HTMLAudioElement })`: returns `{ playing, activeIndex, currentTime, rate, volume, muted, play(), pause(), toggle(), playFrom(index), setRate(n), setVolume(n), setMuted(b) }` reproducing the legacy master player: plays intervals in order by `start_time`, waits for the gap to the next interval's `start_time` before starting it (clamped to 0 to 2 seconds), applies rate, volume and mute to the current element, stops after the last interval, and releases every element and timer on unmount. The legacy screen (`AudioScreen.tsx` lines about 130 to 300) is the reference for exact timing; Task 5's first step records its behaviour as test cases.

- [ ] **Step 1: Write failing tests:** `voicesFromProviders` (primary only, de-duplicated, empty cases); `defaultCasting` for names that mean nothing (`"Zed"`, `"???"`, `"Marcus"`: the result must not depend on the name: the same list in a different name order gives the same assignment by position and gender), keeps existing choices, handles zero voices, one voice, more characters than voices (wraps), and genders; `useIntervalPlayback` with a fake audio factory and fake timers: play starts interval 0, the next starts after its gap, `playFrom(2)` skips earlier ones, rate, volume and mute reach the element, pause stops the timer and the element, the end of the last interval sets `playing` false, and unmount pauses and releases (no timer left, no `play()` after cleanup).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(stages): generic voice casting and the interval playback hook`.

### Task 6: Audio stage

**Files:**
- Create: `apps/desktop/src/features/stages/audio/AudioStage.tsx`, `VoiceCastingDialog.tsx`, `IntervalList.tsx`, `MasterPlayer.tsx`
- Test: `audioStage.test.tsx`

**Interfaces:**
- `AudioStage({ project, onApproved })`: `StageToolbar` ("Review the voice track"), `Generate audio` (same `api.generateAudioJob(project.id, casting)` then follow the job with `useJob` until done, then `api.getAudioTimeline`; a generation already running when the stage opens (`useProjectJobs` newest `AUDIO_GENERATION` active) is followed, not restarted; if a timeline exists it asks before regenerating through `ConfirmDialog`), `Voice casting` opening `VoiceCastingDialog` (one select per character from `voicesFromProviders(await api.getAudioProviders())`, defaults from `defaultCasting`, saved only into the next generate call, as the legacy screen), `MasterPlayer` (play or pause, rate 0.5 to 2, volume, mute, current time, using `useIntervalPlayback` with `api.getAudioFileUrl`), `IntervalList` (each interval: speaker, text, duration, play from here, Regenerate take via `api.regenerateAudioSegment` then reload the timeline, guarded per segment), `SvgAudioEqualizer` while playing, and `Approve audio` (same `api.approveAudio` then `api.getProject`, then `onApproved(updated)`; enabled only when a timeline exists and the stage is not approved; refusal shown as "Audio can't be approved yet" plus the reason; guarded). Generation errors show "Couldn't generate the audio" plus advice that comes from the engine's message and generic steps (check Tools in Settings, check the engine log in Diagnostics); no hard-coded paths or product names.
- The legacy `VOICE_PRESETS` export is not carried over; if anything else imports it (grep first) it moves to the engine-driven list or is removed with its user.

- [ ] **Step 1: Write failing tests:** no timeline shows an invitation with Generate audio and no Approve or player; generating calls `generateAudioJob` once on a double click with the default casting from the stubbed providers and characters, shows job progress, then the intervals; an active generation job on mount is followed and `generateAudioJob` is not called; with an existing timeline Generate audio asks before regenerating; the casting dialog lists the engine's voices (a stub list with made-up names) and a changed choice is sent in the next generate call; Regenerate take calls `regenerateAudioSegment` once for that segment and reloads; Approve is disabled without a timeline and when approved, calls `approveAudio` then `getProject` once then `onApproved`, and a rejection shows the reason and does not call `onApproved`; playback buttons drive the hook (fake audio) and leaving the stage stops playback and polling; the error text contains no `C:\` path and no product name; a failed providers call still lets generation use the engine default voices and says so.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(stages): Audio stage`.

### Task 7: Wire the stages, retire the legacy screens, verify

**Files:**
- Modify: `apps/desktop/src/features/legacy/LegacyStageRoute.tsx`, `apps/desktop/src/__tests__/legacyColorAllowlist.json` (regenerate), `apps/desktop/e2e/workbench.spec.ts`, `docs/UI_V2_UNCOVERED.md`, `docs/superpowers/specs/2026-11-08-ui-v2-design.md`
- Delete: `screens/AcquisitionScreen.tsx`, `PageReviewScreen.tsx`, `MotionScreen.tsx`, `AudioScreen.tsx`, and `screens/__tests__/AudioScreen.test.ts` after moving any still-valid assertions into the new tests (the legacy test is not in the root `npm test` list; confirm)

- [ ] **Step 1:** `grep -rn "AcquisitionScreen\|PageReviewScreen\|MotionScreen\|AudioScreen\|VOICE_PRESETS" apps/desktop/src`; the only users are `LegacyStageRoute` and the files being deleted.
- [ ] **Step 2:** The `acquire`, `pages`, `motion` and `audio` cases render the new stages with `useStageNav` callbacks (`onReviewPages` goes to `pages`, `onConfirmed` and `onApproved` call `advance`); delete the four screens and regenerate the colour allowlist (the diff only removes deleted files). Run `npm run test:ui`, `npm test`, `tsc`; all exit 0.
- [ ] **Step 3: Playwright (read and navigate only; never press Start, Confirm, Plan, Generate, Regenerate, Approve or Delete):** extend `workbench.spec.ts`: for the first pipeline project the acquire, pages, motion and audio routes each show exactly one `h1`, one `h2` toolbar title, the stepper, and no second back button ("Projects" breadcrumb only); pages shows Move earlier and Move later buttons and, when pages exist, the Confirm acquisition button; motion shows either shots with the Preview only note or the Plan motion invitation; audio shows either the player or the Generate audio invitation; no `window.confirm` dialog appears when opening Delete on a page and cancelling it (handle `dialog` events and fail if one fires). Run `npx playwright test`; expect all pass.
- [ ] **Step 4: Real app at 1440x900 and 1100x700:** open the four stages of a real project, screenshot, read; check no console errors, no sideways scroll, images or fallbacks (the real project's page files are missing, so Pages and Acquire must show the Failed fallback, not broken icons), and that opening the Delete dialog and Cancel changes nothing. State what was not exercised.
- [ ] **Step 5:** Update `UI_V2_UNCOVERED.md` (Motion overrides not saved and why; generic casting replaced the name matching; the four legacy screens removed; engine voice list now used; `acceptMotionPlan`, `approveMotionTimeline`, `applyMotionOverrides` still unwired) and the spec status line (M5b done, M5c and M5d remain) with verified and not-verified. Commit explicit paths: `refactor(stages): Acquire, Pages, Motion and Audio on the workbench`. Do not write the M5c plan; report and ask.
