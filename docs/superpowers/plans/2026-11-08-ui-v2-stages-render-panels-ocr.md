# UI v2 Stage Rebuilds: Render, Panels and OCR Implementation Plan (M5d)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the last three legacy stage screens (Render 1,209 lines, Panels 1,744, OCR 2,816) with v2 stages on the workbench frame, keeping every engine call and approval gate, fixing the defects the real data exposed, and giving every pointer-only edit a keyboard path.

**Architecture:** Three self-contained parts, each ending with its legacy screen deleted and the work committed, so the plan can stop after any part. **Part A Render** (a form, a job and a result: no canvas). **Part B Panels** and **Part C OCR** share one new piece, a tested page/panel **canvas** (`features/stages/kit/canvas`: pure geometry functions plus a pointer/keyboard SVG overlay) and one shared **redaction kit** (blur dialogs). Pure models are unit-tested; stages use the M5b/M5c kit (`StageToolbar`, `ConfirmDialog`, `JobProgress`, `engineReason`/`refusal`, `useStageNav`, `useJob`, `useProjectJobs`). Long jobs are followed through React Query, not hand-rolled loops with timeouts.

**Tech Stack:** React 18, `@panelflow/ui-v2`, react-router 7, `@tanstack/react-query` 5, `tsx --test`, Playwright on installed Chrome. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (section 6 "Workbench", section 7 row M5). Builds on M1 to M5c (done on `feat/ui-v2`). Open items: `docs/UI_V2_UNCOVERED.md`.

## Scope

- **In M5d:** Render, Panels and OCR stages; the canvas and redaction kits; removal of `RenderScreen`, `PanelReviewScreen`, `OCRReviewScreen` and their `onBack` wiring.
- **Deferred:** Narration Studio, the story editor (it keeps `YouTubePackagingModal`, so that component stays), audio library (M7), M6 and M8.
- **Execution order matters:** Part A first (smallest, real data in hand), then B, then C (C reuses B's canvas and redaction kit). Parts are independent commits; stopping after A or B leaves a working app.
- **Facts from the code and the real data that shape this plan** (read-only probes; "inferred" means read from code, not run):
  - **Render.** Project `098c6713…` has 16 renders: 3 `COMPLETE`, 5 `FAILED`, **8 `STALE`**. `STALE` is not in the `RenderStatus` type. The legacy screen treats any status other than `COMPLETE`/`FAILED`/`CANCELLED` as a running job, so (inferred) opening Render on that project shows a job as running, hides the settings and offers Cancel. The engine's real profiles are four (`standard_1080p`, `vertical_shorts`, `square_feed`, `draft_720p`, from `GET /api/render/profiles`); the legacy select hard-codes five, including `preview_1080p`, which the engine does not list. Real validation reports carry more than the typed shape (`gate_status: "PRODUCTION_READY"`, `file_size_bytes`, `planned_duration_sec`, `actual_duration_sec`, `duration_diff_sec`, `quality_flags`, `semantic_qa`, `frame_samples`) and one complete render has `is_valid: true` with `sync_valid: false`, so the sync flag cannot be shown as a plain pass/fail without explanation. The legacy screen opens `YouTubePackagingModal`; Publish (M5a) now owns packaging, so Render links there instead.
  - **Panels.** Real projects have 22 to 625 panels (one has 625); panels have status `DETECTED` or `IGNORED` and type `WEBTOON_SEGMENT` (strips 1920 px wide and up to about 22,000 px tall). The legacy screen uses `alert`/`confirm` for every failure and for "Delete panel" (the Delete key deletes at once), commits a move or resize with `console.error` only on failure (the box stays where it was dragged while the engine keeps the old geometry), polls normalisation for 18 s and detection for 24 s then gives up while the job continues, runs "Detect and review" in a 600-iteration loop with no cleanup on unmount, and has no keyboard way to move or resize a box.
  - **OCR.** Real projects have 1 to 24 text regions (`status`, `region_type`, `raw_text`, `corrected_text`, `speaker_character_id`, polygon and page coordinates). "Confirm all pending" writes `"..."` as the corrected text of blank `NEEDS_REVIEW` regions and sends every update at once (`Promise.all`). The default engine is hard-coded to `windows_media`; the engine list on this PC is `mock_ocr` (available), `windows_media` (available), `paddle_ocr`, `manga_ocr`, `vision_llm` (unavailable). Two stale banners ("Milestone 3 Production Gate Passed", "M4 Story Preview Experimental") and an `alert` on contract export remain.
  - The engine, the owner's uncommitted YouTube files, `packages/api-client` and the untracked `ImageEditorModal.tsx` are not edited.

## Global Constraints

- Semantic tokens only (the colour ratchet enforces it); sentence case, verb-first buttons; errors say what happened and what to do and never show a raw exception (`refusal` / `engineReason`); empty states invite an action; status is never colour alone. Every approval gate stays and a refusal never moves on.
- Every start, cancel, confirm, detect, normalise, blur, reset, merge, split, delete, save and approve guards against a fast double click with a synchronous ref and shows its busy state.
- No `window.confirm`, `alert` or `prompt`; no failure handled by `console.*` alone; no placeholder text written into user data.
- Polling starts only while the stage is mounted and work is active, and stops on unmount (tests assert no further calls after cleanup). A job already running when a stage opens (render, panel detection, normalisation, text-region detection, OCR) is followed, not restarted. No hard time limit may declare a job failed while the engine still reports it running.
- Every pointer action on a canvas has a keyboard equivalent, and every control has an accessible name.
- Destructive or costly actions ask first: delete panel, delete region, merge, batch blur, reset all, start render when one is running, re-detect over edited panels.
- Test commands: `npm run test:ui`, `cd apps/desktop && npx tsc --noEmit -p .`, `cd apps/desktop && npx playwright test`; run with `--tsconfig apps/desktop/tsconfig.json`; stage tests use `features/__tests__/pageHarness.tsx` (`mountPage`, `settle`, `press`, `clickTwice`, `setValue`, `setSelect`, `fire`), stub methods on the shared `api` object, close any open modal before `cleanup()` (Radix keeps page state while one is open and can hang the test process), and avoid focus-return assertions (covered at the Dialog level).
- Commit only the files a task touches, with explicit paths. The owner's uncommitted files (`ProviderHealthModal.tsx`, `engine/youtube/*`, `packages/api-client/src/index.ts`, `engine/chronoflow/*`, `ImageEditorModal.tsx` and whatever else `git status` shows modified or untracked at the start) are never staged. Real-data checks only read and navigate: never press Start render, Cancel render, Detect, Normalize, Run OCR, Confirm, Approve, Blur, Reset, Merge, Split, Delete, Save or Export on the owner's projects; opening a dialog and cancelling is allowed. State what was not exercised.
- Test-first for every behaviour; after a green run, mutate the guard or rule the test claims to protect and watch it fail (M5b and M5c each found a hidden gap this way). Test fixtures use the real field names above, not only the `shared-types` shapes.

## Review Focus

1. **Coordinates and data integrity.** Pointer to image coordinates are right at any zoom and scroll and on very tall strips; a box can never leave the image or fall below the minimum size; a failed commit rolls the box back and says so (the legacy screen left it diverged); regions are never confirmed with placeholder text. (Tasks B1, B2, B4, C1, C4)
2. **Gates.** Confirm panels, confirm OCR and start render keep their preconditions and show the engine's refusal in words; nothing moves on after a refusal; approvals cannot be double-submitted. (Tasks A2, B3, C2)
3. **Jobs.** Render, detection, normalisation and OCR are followed from React Query, resumed on open, stopped on unmount, and never declared failed by a local timeout; `STALE` renders are history, not running jobs. (Tasks A1, A2, B3, C2)
4. **Destructive actions and history.** Deletes, merges, batch blurs and "reset all" ask first; undo and redo use the engine's history and respect `conflicted` / `recoveryRequired`; per-item actions cannot race each other. (Tasks B4, B5, C4, C5)
5. **Honest and scalable states.** 625 panels, missing images, zero regions, an unavailable OCR engine, a failed profile list and a validation report with an unexplained flag each show the reason and the next action, and the lists stay responsive. (Tasks A1, B3, C2, C3)

---

## Part A: Render

### Task A1: Render model

**Files:**
- Create: `apps/desktop/src/features/stages/render/renderModel.ts`
- Test: `apps/desktop/src/features/stages/render/__tests__/renderModel.test.ts`

**Interfaces (produces):**
- `RUNNING_RENDER: ReadonlySet<string>` exactly `QUEUED, PREPARING, COMPOSING, ENCODING, MUXING, VALIDATING`. `isRunning(job)`, `activeRender(renders: RenderJob[]): RenderJob | null` (the newest running one). `STALE`, `COMPLETE`, `FAILED`, `CANCELLED` and any unknown status are never running.
- `renderStatus(status: string): { word: string; tone: "ok" | "warn" | "bad" | "accent" | "neutral" }`: `COMPLETE` Done, `FAILED` Failed, `CANCELLED` Cancelled, `STALE` Out of date (warn), running statuses their stage in words (Preparing, Composing, Encoding, Muxing, Checking), `QUEUED` Waiting, unknown shown as the raw status title-cased with neutral.
- `profileChoices(profiles: Array<{ id: string; name: string; description?: string; width?: number; height?: number; fps?: number }> | null | undefined): { options: Array<{ id: string; label: string; hint: string }>; defaultId: string | null; fromEngine: boolean }`: labels from the engine's names with `"1920x1080 · 30 fps"` hints; no list (null or empty) yields `fromEngine: false`, options `[]` and `defaultId: null` (never invented ids).
- `RenderSettings` (`profile`, `subtitles`, `bgmVolumeDb`, `dialogueGainDb`, `minPanelDuration`, `panelZoomMode: "fit" | "motion" | "cover"`, `narrationSpeed`, `videoEngine: "fast_h3" | "ken_burns"`, `motionFx`, `saveLocation`), `DEFAULT_SETTINGS` (the legacy defaults: music -10 dB, dialogue 0 dB, 4.0 s per panel, `fit`, speed 1.0, `fast_h3`, fx `none`, subtitles off, empty location), `clampSettings(s)` (ranges taken from the legacy sliders: read `RenderScreen.tsx` lines 419 to 560 first), and `startOptions(s: RenderSettings): Parameters<typeof api.startRender>[1]` mapping to the exact option names the client expects, with `isDraft` true only for `draft_720p` and an empty `saveLocation` sent as `undefined`.
- `validationSummary(report: unknown): { verdict: { word: string; tone: Tone }; rows: Array<{ label: string; value: string; tone: Tone; note?: string }>; warnings: string[] }`: reads typed and extra fields defensively; verdict from `gate_status` when present (`PRODUCTION_READY` "Ready for production"), else `is_valid`; rows for Video, Audio, Sync, Black frames, Timeline gaps, Clipping, Duration (planned vs actual and the difference), File size (MiB, one decimal); a flag that is `false` while the overall verdict is a pass gets the `note` "The engine reports this check as not confirmed, but still passed the render as production ready." (the real `sync_valid: false` case); missing fields are omitted, never shown as 0.
- `formatBytes(n)`, `outputName(path)` (file name of a Windows or POSIX path).

- [ ] **Step 1: Write failing tests** from real fixtures (a copy of the real COMPLETE job's keys, one FAILED, one STALE): `STALE` is not running and `activeRender` skips it; `renderStatus` for every status above and an unknown one; `profileChoices` with the four real profiles, with `null`, with `[]`; `clampSettings` at both ends of each range; `startOptions` names, `isDraft`, empty location; `validationSummary` for the real report (verdict "Ready for production", sync row with the note, duration difference 0.003 s, file size "88.0 MiB" from 92,299,740 bytes), for a typed-only report, for `null`, and for a failing report; `outputName` for both separators.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate "STALE is not running" and watch a test fail. **Step 5:** Commit: `feat(stages): render model`.

### Task A2: Render stage (settings, start, follow, cancel, history)

**Files:**
- Create: `features/stages/render/RenderStage.tsx`, `renderData.ts`, `RenderSettingsPanel.tsx`, `RenderHistory.tsx`
- Test: `features/stages/render/__tests__/renderStage.test.tsx`

**Interfaces:**
- `renderData.ts`: `useRenders(projectId)` (from `features/workbench/queries`, which already polls while one runs), `useRenderProfiles()` (`api.getRenderProfiles`, failure sets `isError`), `useQuickDestinations(projectId)` (`api.getQuickDestinations`, failure `[]`).
- `RenderStage({ project, onRenderComplete })`: `StageToolbar` ("Render the video", status chip from the viewed render), `Start render` (disabled with the reason when there is no profile list: "Couldn't load the render profiles. Check that the engine is running."; asks through `ConfirmDialog` "A render is already running. Start another?" only when one runs), `Cancel render` (`api.cancelRender`, one at a time). `RenderSettingsPanel` (hidden while a render runs): profile select from `profileChoices`, destination text field plus `Browse folder` / `Save as file` (`api.pickDirectoryNative` / `api.pickSaveFileNative`; a picker failure shows "Couldn't open the folder picker." instead of `console.warn`) and the quick-destination chips, pacing presets (Brisk 2.0, Standard 3.0, Comfortable 4.0, Relaxed 5.5) with a slider, zoom mode, narration speed, motion engine, motion fx, music volume, dialogue gain, subtitles switch, all through `clampSettings`. Start: `api.startRender(project.id, startOptions(settings))`; follow the job with `useRenders`; a running render on open is followed and shows progress (`JobProgress`-style: stage word, `frames_done/frames_total`, percent), not the settings; when it ends: `COMPLETE` calls `api.getProject` then `onRenderComplete(updated)` and toasts "Render finished.", `FAILED` shows `refusal("Render failed.", new Error(job.error_message ?? ""), ADVICE)` with generic advice (no paths, no product names), `CANCELLED` shows a notice. `RenderHistory`: every render newest first with status word, profile, date and, for `COMPLETE`, `View` and `Open file` (`api.openPath(path, true)`); `STALE` rows say "Out of date: the project changed after this render" and offer no actions.

- [ ] **Step 1: Write failing tests** (stub `api`; fixtures include real-shaped STALE, FAILED and COMPLETE jobs): (a) a project whose renders are only STALE and COMPLETE shows the settings and Start, **not** a running job or Cancel (the legacy bug); (b) the profile select lists exactly the engine's four profiles; with a failed profile list Start is disabled with the reason and no profile is invented; (c) Start sends `startOptions` once on a double click (check every option name, the `draft_720p` flag, an empty location as `undefined`); (d) a running render on open shows progress and Cancel, not the settings, and is not restarted; polling stops after unmount; (e) Cancel cancels once; (f) completion calls `getProject` then `onRenderComplete` once and toasts; (g) a failed render shows words with no path or address; a cancelled one shows a notice; (h) starting while one runs asks first; (i) folder and save-as pickers fill the location, a picker failure is shown in words, quick-destination chips set it; (j) history lists renders newest first, STALE rows have no actions, `Open file` calls `openPath(path, true)` once; (k) one h2 and no h1.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the start guard, "settings hidden while running" and the STALE rule and watch a test fail for each. **Step 5:** Commit: `feat(stages): Render stage`.

### Task A3: Render result, then wire and retire the legacy screen

**Files:**
- Create: `features/stages/render/RenderResult.tsx`, `ValidationReport.tsx`
- Modify: `RenderStage.tsx` (show the viewed render's result), `features/legacy/LegacyStageRoute.tsx`, `legacyColorAllowlist.json` (remove only the deleted file; never add another file's entry), `e2e/workbench.spec.ts`, `docs/UI_V2_UNCOVERED.md`
- Delete: `screens/RenderScreen.tsx`
- Test: `__tests__/renderResult.test.tsx`

**Interfaces:**
- `RenderResult({ projectId, render })` for a `COMPLETE` render: media tabs (v2 `Tabs`): Video (`<video controls>` from `api.getRenderVideoUrl`, audit-frame markers that seek, `Open file`, `Open folder` via `api.openPath(path, false)`, `Export QA audit` as a JSON download without an `alert`), Contact sheet (`api.getRenderContactSheetUrl`, image fallback "Contact sheet unavailable"), Audit samples (`api.getRenderAuditSampleUrl(projectId, id, index)` for each `frame_samples` entry, each with timestamp and luminance, failures shown per image). `ValidationReport({ report })` renders `validationSummary`. A closing line links to Publish: "Next: check the render and copy the packaging in Publish." with a `Continue to publish` button (`useStageNav`).

- [ ] **Step 1: Write failing tests:** a COMPLETE render shows the three tabs, the video source, the verdict "Ready for production", the sync row with its explanatory note, the duration line and the file size; Contact sheet and Audit samples show their images and each broken image shows its own fallback; `Open file` and `Open folder` call `openPath` once with the right flag; `Export QA audit` produces a download (stub `URL.createObjectURL`) and no browser dialog; a FAILED render shows its error in words and no media tabs; `Continue to publish` navigates.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement; wire the `render` case in `LegacyStageRoute` (`<RenderStage project onRenderComplete={store} />`, `store` from `useStageNav`); delete `RenderScreen.tsx` (grep first: only the route imports it); update the allowlist by removing the one line. **Step 4:** Run `npm run test:ui`, `npm test`, `tsc`; mutate the explanatory-note rule and watch a test fail. **Step 5: Playwright** (read and navigate only): `render` shows one h1, one h2, the stepper and no second back button; the project with renders shows the history with at least one STALE row labelled in words and no Cancel button; no browser dialog fires. **Step 6: Real app** at 1440x900 and 1100x700 on `098c6713…`: screenshot Render, check the 16-render history, the STALE rows, the complete render's tabs and report (no clicks that start, cancel or open anything outside the app), no console errors, no sideways scroll. **Step 7:** Document in `UI_V2_UNCOVERED.md` section 11 (STALE, the invented profile, the sync flag, packaging moved to Publish) and commit: `refactor(stages): Render on the workbench`.

---

## Part B: Panels

### Task B1: Geometry model

**Files:**
- Create: `apps/desktop/src/features/stages/kit/canvas/geometry.ts`
- Test: `apps/desktop/src/features/stages/kit/canvas/__tests__/geometry.test.ts`

**Interfaces (produces; all pure, all in image pixels):**
- `type Box = { x: number; y: number; w: number; h: number }`, `type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw"`, `MIN_SIZE = 30` (the legacy value), `MIN_DRAW = 20`.
- `pointToImage(rect: { left: number; top: number; width: number; height: number }, image: { w: number; h: number }, client: { x: number; y: number }): { x: number; y: number }` rounds, clamps into the image, and works at any zoom because `rect` is the on-screen rectangle of the image.
- `clampBox(box: Box, image): Box` (inside the image, at least `MIN_SIZE`); `moveBox(start: Box, dx: number, dy: number, image): Box`; `resizeBox(start: Box, handle: Handle, dx: number, dy: number, image): Box` reproducing the legacy rules (an edge that would shrink the box below `MIN_SIZE` stays put) for all eight handles; `drawBox(a: Point, b: Point): Box` (corner-order independent); `isDrawable(box): boolean` (both sides over `MIN_DRAW`); `nudgeBox(box, key: "ArrowLeft" | ..., step: number, resize: boolean, image): Box` (arrows move by `step`, Shift+arrows resize the south-east corner; clamped).
- `normalizeBox(box: Box, image): { x: number; y: number; w: number; h: number }` as fractions rounded to 4 places (the legacy `normalized_*` fields).
- `boxesOverlap(a: Box, b: Box): number` (intersection over smaller area, for a warning), `hitTest(boxes: Array<Box & { id: string }>, p: Point): string | null` (the smallest box containing the point, so a small box inside a big one stays selectable).

- [ ] **Step 1: Write failing tests:** `pointToImage` at 100%, 25% and 400% zoom, with the rect scrolled out of view, on a 1920x22528 strip, and clamping outside the image; `moveBox` clamps at every edge; `resizeBox` for each of the eight handles including the "would go below 30" cases for the west and north edges (the legacy asymmetry), never leaving the image; `drawBox` from any corner order; `isDrawable`; `nudgeBox` plain and shifted and clamped; `normalizeBox` rounding; `boxesOverlap` identical, nested, disjoint; `hitTest` prefers the smaller of two nested boxes.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate one handle's clamp and the `pointToImage` scale and watch a test fail for each. **Step 5:** Commit: `feat(stages): canvas geometry`.

### Task B2: PageCanvas component

**Files:**
- Create: `features/stages/kit/canvas/PageCanvas.tsx`, `useCanvasInteraction.ts`
- Test: `features/stages/kit/canvas/__tests__/pageCanvas.test.tsx`

**Interfaces:**
- `PageCanvas({ image: { src: string; width: number; height: number; alt: string }, boxes: CanvasBox[], selectedId: string | null, onSelect(id | null), onChange(id, box: Box) /* during a drag */, onCommit(id, box: Box, previous: Box) /* when it ends */, onDraw?(box: Box), drawMode?: boolean, showBoxes?: boolean, zoom: number, editable?: boolean })` where `CanvasBox = { id: string; box: Box; label: string; tone: Tone; locked?: boolean }`. It renders the image with an absolutely-positioned SVG overlay in image coordinates (`viewBox`), a scroll viewport, the selected box's eight handles, and a draw rectangle. Pointer events use `setPointerCapture`, `pointToImage` with `getBoundingClientRect` (not `getScreenCTM`, which jsdom lacks), and `useCanvasInteraction` holds the drag state machine (`idle | move | resize | draw`). Keyboard: a box is focusable (`role="button"`, `aria-label` with its label, position and size); arrows nudge by 10 px (1 px with Alt), Shift+arrows resize, Escape cancels the drag, Delete is **not** handled here (the stage asks first). A failed image shows "Page image unavailable" with `Retry` instead of an empty canvas.

- [ ] **Step 1: Write failing tests** (jsdom with stubbed `getBoundingClientRect` and a `PointerEvent` helper from `fire`): pointer down on a box selects it; a drag calls `onChange` with the moved box and `onCommit` once on pointer up with the previous box; a drag that never moves calls no commit; Escape during a drag restores and commits nothing; dragging a handle resizes per `resizeBox`; draw mode draws a box and calls `onDraw` only when `isDrawable`; at 50% zoom the same pointer distance moves the box twice as far in image pixels; arrows and Shift+arrows nudge and resize and commit once per key press; `editable: false` ignores pointers and keys; a locked box cannot move; the box labels and positions are exposed to assistive technology; the broken image state and Retry.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate "commit once" and the zoom scaling and watch a test fail for each. **Step 5:** Commit: `feat(stages): page canvas`.

### Task B3: Panels stage core (pages, detection, normalisation, history, gate)

**Files:**
- Create: `features/stages/panels/PanelsStage.tsx`, `panelsData.ts`, `panelsModel.ts`, `PageStrip.tsx`
- Test: `panelsModel.test.ts`, `panelsStage.test.tsx`

**Interfaces:**
- `panelsModel.ts`: `panelsOnPage(panels, pageId)` (by `page_sequence`), `panelTone(panel)` and `panelWord(panel)` (`DETECTED` Detected, `CONFIRMED` Confirmed, `NEEDS_REVIEW` Needs review, `IGNORED` Ignored, `MANUAL` Manual, `APPROVED` Approved, unknown title-cased), `canConfirmPanels(panels): { ok; reason }` (reason `"Detect or add at least one panel first."`; ignored panels do not count), `pageCounts(panels, pages)` (panels per page, pages with none), `readingDirectionOptions` (`ltr`, `rtl`), `historyAvailability(state)` (`{ canUndo, canRedo, blocked: string | null }` blocked for `conflicted` and `recoveryRequired` with a sentence).
- `panelsData.ts`: `usePanels(projectId)` (`api.listPanels`), `usePagesLite` (from the M5b `usePages`), `useHistory(projectId)` (`api.getCachedProjectHistory` seed, refreshed after undo/redo).
- `PanelsStage({ project, onConfirmed, onContinue, onOpenStoryEditor })`: `StageToolbar` ("Review panels"), reading-direction and detection-profile selects, `Detect panels` (`api.detectPanels(project.id, direction, 0.02)` then follow the job with `useJob`; no local timeout; re-detecting when panels already exist asks first: "Detect again? Edited and linked pages are preserved." per the legacy status text), `Detect this page` (`api.detectPagePanels`), `Normalize pages` (`api.normalizeProject(project.id, 1920)` and follow its job; a failed job is shown, the legacy screen ignored it), `Undo` / `Redo` (server history; `historyShortcut` keys; disabled while busy or blocked, with the reason), `Confirm panels` (same `api.confirmPanels` then `api.getProject` then `onConfirmed`; disabled with the `canConfirmPanels` reason; refusal in words), `Continue to OCR` when confirmed, `Open story editor` (`onOpenStoryEditor(project)`). `PageStrip`: thumbnails of the pages (`PageThumb`) with panel counts, current page marked, Left and Right arrows change page; a running detection, normalisation or detection job on open is followed.

- [ ] **Step 1: Write failing tests:** model tests (each status word, the confirm reasons, ignored panels excluded, history blocked states, panels per page ordering); stage tests with a real-shaped fixture (`DETECTED` and `IGNORED` panels, `WEBTOON_SEGMENT`, 1920x22000 pages): one h2; Detect sends direction once on a double click and follows the job, then reloads panels; a running detection on open is followed not restarted and polling stops after unmount; no local time limit (a job running past 60 simulated polls is still shown running); re-detect asks first; a failed job and a failed normalisation show words; Confirm disabled with the reason when nothing is ready, confirms once and hands over the project, a refusal shows the reason and does not move on; Undo and Redo call the engine once, refresh panels, and are disabled with the sentence when history is blocked; page arrows change page and a page with no panels says so; 625 panels render the strip without rendering 625 DOM thumbnails (windowed to the nearest 40 pages' worth or fewer).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement (the canvas arrives in B4; this task shows the page image with panel outlines read-only). **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the confirm gate, the re-detect confirmation and the unmount cleanup and watch a test fail for each. **Step 5:** Commit: `feat(stages): Panels stage core`.

### Task B4: Panel editing (canvas edits, add, split, merge, full page, delete, reorder)

**Files:**
- Create: `features/stages/panels/PanelEditor.tsx`, `PanelInspector.tsx`, `PanelList.tsx`, `AddPanelDialog.tsx`, `usePanelEditing.ts`
- Modify: `PanelsStage.tsx`
- Test: `panelEditing.test.tsx`

**Interfaces:**
- `usePanelEditing({ project, panels, setPanels, history })`: one change at a time (a synchronous flight ref; `busy` state), each returning `Promise<boolean>`: `move(panel, box)` (`api.updatePanel(projectId, id, x, y, w, h)`; **on failure the box is restored and "Couldn't save the new position. It was put back." is shown**), `draw(pageId, box)` (`api.addPanel`), `addManual(pageId, box)` (the dialog), `split(panelId, "horizontal" | "vertical")` (`api.splitPanel(..., 0.5)`), `merge(ids)` (`api.mergePanels`; needs two or more, shown as a disabled button with the reason, not an alert), `markFullPage(panel, image)` (`api.updatePanel(..., "CONFIRMED", "FULL_PAGE")` with the **image's** width and height), `remove(panelId)`, `reorder(pageId, panelIds)` (`api.reorderPanels`; optimistic with rollback), each followed by `getCachedProjectHistory` refresh and a cache-buster for crops.
- `PanelEditor` renders `PageCanvas` with the page's panels as boxes (selected, merge-selected with Shift or Ctrl+click or the list's checkboxes, ignored in neutral tone and not draggable), a toolbar (zoom, show boxes, draw mode, fit width), and the keyboard shortcuts from the legacy screen (`[` `]` and Tab to move between panels, Delete asks first, Escape leaves draw mode and clears the selection). `PanelInspector`: crop preview (`api.getPanelImageUrl`), coordinates as number fields (Apply sends one `updatePanel`), Split horizontal / vertical, Merge selected, Mark full page, Delete (asks through `ConfirmDialog`: "Delete panel N? It can be undone with Undo."). `PanelList`: the page's panels in reading order with Move earlier / Move later buttons (and drag as a convenience) and a warning chip when two panels overlap by more than 80 percent (`boxesOverlap`).

- [ ] **Step 1: Write failing tests** (stub `api`; a canvas stand-in that fires `onCommit`): a committed move calls `updatePanel` once with the box; **a failed move restores the previous box and shows the sentence** (the legacy bug); a draw adds one panel; the add dialog validates (inside the image, minimum size) with inline errors; split sends the type and 0.5 once on a double click; merge is disabled with fewer than two selected and merges once; mark full page sends the image dimensions; Delete (button and key) asks first, Cancel deletes nothing, confirming deletes once and clears the selection; reorder with the buttons calls `reorderPanels` with the new order and rolls back on failure; a second change while one is running is not sent; no `alert`, `confirm` or `console.error` is called (spies throw); every pointer action also works from the inspector's number fields and the canvas keyboard path; an `IGNORED` panel cannot be dragged but can be restored or deleted (read the legacy status handling first).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the rollback, the single-flight ref and the delete confirmation and watch a test fail for each. **Step 5:** Commit: `feat(stages): panel editing`.

### Task B5: Redaction kit, content cleanup and Detect and review

**Files:**
- Create: `features/stages/kit/redaction/BlurPanelControls.tsx`, `BatchBlurDialog.tsx`, `useRedaction.ts`; `features/stages/panels/ContentCleanup.tsx`, `DetectAndReview.tsx`
- Modify: `PanelInspector.tsx`, `PanelsStage.tsx`
- Test: `redaction.test.tsx`, `contentCleanup.test.tsx`

**Interfaces:**
- `useRedaction(projectId)`: `status(panelId)` (`api.getPanelBlurStatus`, failure `null`), `blurPanel(panelId, radius)` (`api.blurEntirePanel`), `reset(panelId)` (`api.resetPanelImage`), `batchBlur(preset, heightPx)` (`api.batchBlurPanels` with `TOP_WATERMARK | BOTTOM_SUBSCRIBE | ALL_TEXT_REGIONS | ENTIRE_PANEL`), `batchReset()` (`api.batchResetPanels`); one operation at a time; results are returned for display, never `alert`ed.
- `BlurPanelControls({ panelId })`: blur state in words ("Blurred, N regions" / "Not blurred" / "Original saved"), `Blur panel`, `Restore original` (asks first when the panel is blurred). `BatchBlurDialog`: preset radio group, height field for the presets that use one, and a separate `Restore every panel` section that asks a second time ("This puts every panel back to its original image. It can't be undone."); the result is shown inside the dialog ("Blurred 12 of 46 panels.").
- `ContentCleanup`: the rules (`api.getContentCleanupRules`: enabled switch and the label list, saved with `api.saveContentCleanupRules`), the report (`api.getContentCleanupReport`), and the suggestions (`api.getPanelContentSuggestions`, labels saved with `api.savePanelContentLabels`); loads are errors in words, not a stray message string. `DetectAndReview` is the legacy "Detect and review" pipeline (detect panels, find text regions, read each with a real OCR engine, then suggest content labels) rebuilt as **a sequence of followed jobs with visible steps and a Cancel**, using the first available non-mock engine and stopping with "Configure an available OCR engine in Settings, then try again." when none exists; it never polls after unmount.

- [ ] **Step 1: Write failing tests:** blur and restore call the engine once each (double click), restore of a blurred panel asks first; the batch dialog sends the chosen preset and height once, shows its result in the dialog, and `Restore every panel` needs the second confirmation and sends once; a failure shows words inside the dialog and leaves it open (close it before cleanup); cleanup rules load, save and report with errors in words; label saves send the edited list once; `DetectAndReview` runs its steps in order with progress, stops at the first failure with words, uses no mock engine and says so when only mock engines are available, and issues no calls after unmount.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the restore-all second confirmation and the no-mock-engine rule and watch a test fail for each. **Step 5:** Commit: `feat(stages): redaction kit and content cleanup`.

### Task B6: Wire Panels, retire the legacy screen, verify

**Files:**
- Modify: `LegacyStageRoute.tsx`, `legacyColorAllowlist.json` (remove only the deleted file), `e2e/workbench.spec.ts`, `docs/UI_V2_UNCOVERED.md`
- Delete: `screens/PanelReviewScreen.tsx` (grep first; delete any test that only imports it after moving still-valid assertions)

- [ ] **Step 1:** Wire the `panels` case (`onConfirmed={advance}`, `onContinue={advance}`, `onOpenStoryEditor={openEditor}`); delete the screen; update the allowlist. Run `npm run test:ui`, `npm test`, `tsc`; all exit 0.
- [ ] **Step 2: Playwright (read and navigate only):** `panels` shows one h1, one h2, the stepper and no second back button; a project with panels shows the page strip, the canvas with at least one labelled panel and the inspector; pressing Delete with a panel selected opens the app's dialog (Cancel it) and no browser dialog fires; `Tab` moves the selection; the project with 625 panels (found through the API, not assumed) opens without more than a few hundred panel DOM nodes and without a sideways scroll at 1440 and 1100.
- [ ] **Step 3: Real app** at 1440x900 and 1100x700 on a project with panels and on the 625-panel one: screenshot, read; check the strip, outlines at the right place on a tall strip, a missing page image shows its fallback, no console errors. Open and cancel the add-panel, batch-blur and delete dialogs. Do not drag, draw, detect or blur.
- [ ] **Step 4:** Document in `UI_V2_UNCOVERED.md` section 12 (the diverging commit, no keyboard edit, jobs given up by timers, panel status `IGNORED`, canvas and redaction kits) and commit: `refactor(stages): Panels on the workbench`.

---

## Part C: OCR

### Task C1: OCR model

**Files:**
- Create: `apps/desktop/src/features/stages/ocr/ocrModel.ts`
- Test: `apps/desktop/src/features/stages/ocr/__tests__/ocrModel.test.ts`

**Interfaces (produces):**
- `regionStatus(status: string): { word: string; tone: Tone }` (`NEEDS_REVIEW` Needs review, `CONFIRMED` Confirmed, `IGNORED` Ignored, `REJECTED`, unknown title-cased) and `regionTypeWord(type)` (`SPEECH`, `NARRATION`, `SFX`, `THOUGHT`, ... read the legacy `getRegionBorderColor` and type list first).
- `needsReview(regions)`, `canConfirmOCR({ regions, running }): { ok; reason }` (reasons `"Run text detection first."`, `"Text is still being read."`, `"N regions still need review."` singular for 1).
- `pickEngine(engines: OCREngineInfo[]): string | null`: the first `is_available` engine whose id does not contain `mock`, preferring none by name (the legacy `windows_media` preference is dropped: no engine id is hard-coded); `null` with a sentence from `engineProblem(engines)` ("No OCR engine is available. Install one in Settings." / "Only a test engine is available. Choose or install a real one in Settings.").
- `confirmPatch(region): { status: "CONFIRMED"; corrected_text: string } | null`: **a region with neither `corrected_text` nor `raw_text` returns `null`** (it must be typed or ignored; the legacy screen wrote `"..."`).
- `regionsByPanel(regions)`, `panelFilter(panels, regions, filter: "all" | "needs_review" | "no_text" | "has_text")`, `jumpToNextFlagged(regions, panels, currentRegionId)`.
- `editForm(region)` and `regionPatch(region, form)` (only changed fields; a corrected text equal to the machine text is still saved as a correction when the person pressed Approve).
- `speakerOptions(characters)` (Unknown, Narrator, Sound effect, then characters by name, using the M5c `normalizeCharacters` and `characterName`).

- [ ] **Step 1: Write failing tests** with fixtures of the real region shape (`raw_text`, `corrected_text`, `region_type`, `speaker_character_id`, `status`, `panel_id`, `sequence_in_panel`): every function above including `confirmPatch` for blank text (null), whitespace-only text (null), raw-only (uses raw), corrected (uses corrected); `pickEngine` with the real list on this PC (`windows_media` chosen as the first available real engine by order, not by name: assert the choice changes when the list order does), with only mock, with none; `canConfirmOCR` each reason; `jumpToNextFlagged` wraps; `regionPatch` omits unchanged fields.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate `confirmPatch` (allow blank) and the engine preference and watch a test fail for each. **Step 5:** Commit: `feat(stages): OCR model`.

### Task C2: OCR stage core (engine, detection, reading, gate)

**Files:**
- Create: `features/stages/ocr/OcrStage.tsx`, `ocrData.ts`, `GateBanner.tsx`
- Test: `ocrStage.test.tsx`

**Interfaces:**
- `ocrData.ts`: `useTextRegions(projectId)` (`api.listTextRegions`), `useOcrEngines()` (`api.listOCREngines`), `useOcrRecords(projectId)` (`api.listProjectOCR`), `useOcrPanels(projectId)` (the panels from B3's `usePanels`).
- `OcrStage({ project, onApproved, onContinue, onOpenStoryEditor })`: `StageToolbar` ("Review the text"), engine select (from the engine list, unavailable engines shown disabled with "Not installed", never preselecting a mock; `engineProblem` shown when none), `Detect text regions` (`api.detectTextRegions`), `Read text` (`api.extractOCR` for the whole project: read the legacy `handleRunProjectOCR`, lines 338 to 392, first and follow it through `useJob` if it returns a job id, otherwise show its result and progress as the legacy screen does; per-region reading `api.ocrSingleRegion(project.id, regionId, engine)` for single regions; a job running on open is followed), `Confirm all with text` (confirms only regions where `confirmPatch` is not null, **sequentially with progress**, never `"..."`, and reports "N confirmed, M left because they have no text."), `Approve text` (same `api.confirmOCR` then `api.getProject` then `onApproved`; disabled with the `canConfirmOCR` reason; a refusal shows the engine's reason and does not move on), `Continue to story` when approved, `Export contract` (`api.getCanonicalExportContract` as a download; a failure in words, no alert), Undo and Redo as in Panels (the shared history hook). `GateBanner`: the NEEDS_REVIEW count with `Jump to next flagged`; the two stale milestone banners are gone.

- [ ] **Step 1: Write failing tests** (real-shaped regions): one h2; no mock engine is preselected and the select disables unavailable engines; with only mock or no engine the reason shows and Read text is disabled; Detect once on a double click; Read text follows a job, a running job on open is followed, polling stops after unmount; `Confirm all with text` skips blank regions, writes real text only, never `"..."`, runs one request at a time and reports counts; Approve is disabled with the reason, approves once, refusal shown and no move; export downloads without a browser dialog; undo and redo blocked states; the gate banner counts and jumps.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the `"..."` rule, the approve gate and the sequential confirm and watch a test fail for each. **Step 5:** Commit: `feat(stages): OCR stage core`.

### Task C3: Panel strip, region canvas and region list

**Files:**
- Create: `features/stages/ocr/PanelStrip.tsx`, `RegionCanvas.tsx`, `RegionList.tsx`
- Modify: `OcrStage.tsx`
- Test: `ocrNavigation.test.tsx`

**Interfaces:**
- `PanelStrip({ panels, regions, selectedPanelId, filter, onFilter, onSelect, onDelete })`: filter pills (all, needs review, no text, has text) with counts, a jump-to-panel number input with clear, and the panel thumbnails with region count and status, **windowed**: at most 60 items rendered with `Show more` (the real data has up to 625 panels), the selected panel always included; a per-panel `Delete panel` asks first through `ConfirmDialog` ("Delete panel N? It can be undone with Undo.") and calls `api.deletePanel`.
- `RegionCanvas`: `PageCanvas` over the **panel crop** (`api.getPanelImageUrl` with the cache-buster) showing the panel's text regions as boxes (region order and type label, tone from status), pan and zoom (25 to 300 percent, wheel and buttons, `Fit`), previous/next panel buttons, and the keyboard keys of the legacy screen (`[` `]` / Tab for regions, arrows for panels, Escape). `RegionList`: the active panel's regions with status and a one-line preview.

- [ ] **Step 1: Write failing tests:** the filter pills and counts; a strip of 625 panels renders at most 60 thumbnails plus the selected one and `Show more` adds 60; the jump input selects a panel and clears; panel delete asks first, Cancel deletes nothing, confirming deletes once; region boxes appear at the right place for a panel crop and selecting a box selects the region; wheel and buttons clamp zoom to 25 to 300; the bracket and Tab keys move between regions and wrap; panel arrows stop at the ends; a missing crop shows the unavailable state.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the windowing cap and the delete confirmation and watch a test fail for each. **Step 5:** Commit: `feat(stages): OCR panel strip and region canvas`.

### Task C4: Region editor

**Files:**
- Create: `features/stages/ocr/RegionEditor.tsx`, `useRegionEditing.ts`
- Modify: `OcrStage.tsx`
- Test: `regionEditor.test.tsx`

**Interfaces:**
- `useRegionEditing({ project, onChanged })`: one change at a time: `save(region, form)` (`api.updateTextRegion(projectId, id, regionPatch(...))`), `approve(region, form)` (status `CONFIRMED`, refuses blank text with "Type the text, or ignore this region." instead of saving a placeholder), `reject(region)` (status `IGNORED`), `remove(region)` (`api.deleteTextRegion`, asks first), `readOne(region, engine)` (`api.ocrSingleRegion`), `createFromBox(panelId, box)` (`api.createManualTextRegion`), `saveAndNext`. Failures are words in the editor.
- `RegionEditor`: the three layers of the legacy screen as sections: **Machine reading** (read-only text, engine, confidence, `Read again` with the chosen engine), **Correction** (the canonical text area, the quick formatting chips of the legacy screen, type and status selects), **Speaker** (the `speakerOptions` select, assignment method shown), and `Save`, `Approve`, `Ignore`, `Save and next`, `Delete region`.

- [ ] **Step 1: Write failing tests:** the form starts from the region (corrected text, else raw text); Save sends only changed fields once on a double click; Approve of blank text is refused with the sentence and sends nothing; Approve sends `CONFIRMED` with the text; Ignore sends `IGNORED`; Save and next saves then selects the next region of the panel (and the next flagged one when the panel is done); Delete region asks first and sends once; Read again sends the chosen engine once and updates the machine text; a draw on the canvas creates a manual region once; a failed save keeps the form and says why; a second action while one runs is not sent; the speaker select shows names (the M5c `normalizeCharacters` shape) and Unknown for an unmatched id.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the blank-text refusal and the single-flight ref and watch a test fail for each. **Step 5:** Commit: `feat(stages): OCR region editor`.

### Task C5: OCR redaction

**Files:**
- Create: `features/stages/ocr/OcrRedaction.tsx`
- Modify: `OcrStage.tsx`
- Test: `ocrRedaction.test.tsx`

**Interfaces:**
- `OcrRedaction`: reuses the B5 kit (`BlurPanelControls`, `BatchBlurDialog`) and adds the OCR-only parts: `Blur this text region` (`api.blurTextRegion`), `Blur all text in this panel` (`api.blurPanelText`), `Blur area` (the marquee: draw a box on the canvas, then a confirmation bar with a blur-radius select and `Apply blur` (`api.blurPanelRegion`) or `Create text region` (`api.createManualTextRegion`), both once at a time), and the custom-box dialog with quick presets and number fields (`api.blurPanelRegion` with typed coordinates, validated inside the image).

- [ ] **Step 1: Write failing tests:** each blur sends its call once on a double click with the right ids and radius; the marquee needs a drawable box and offers both actions once; the custom-box dialog validates coordinates inline and sends once; failures show words and leave the dialog open (close it before cleanup); `Restore original` asks first when blurred (via the B5 controls).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0; mutate the marquee validation and one single-flight guard and watch a test fail for each. **Step 5:** Commit: `feat(stages): OCR redaction`.

### Task C6: Wire OCR, retire the legacy screen, verify, document

**Files:**
- Modify: `LegacyStageRoute.tsx`, `legacyColorAllowlist.json` (remove only the deleted file), `e2e/workbench.spec.ts`, `docs/UI_V2_UNCOVERED.md`, `docs/superpowers/specs/2026-11-08-ui-v2-design.md`
- Delete: `screens/OCRReviewScreen.tsx` (grep first)

- [ ] **Step 1:** Wire the `ocr` case; delete the screen; update the allowlist; run `npm run test:ui`, `npm test`, `tsc`; all exit 0. After this step no legacy stage screen remains: confirm `LegacyStageRoute` imports nothing from `screens/` for stages, and say so.
- [ ] **Step 2: Playwright (read and navigate only):** `ocr` shows one h1, one h2, the stepper and no second back button; for a project with text regions (found through the API) the panel strip, the canvas, the region editor and the gate banner appear, the first region's three layers are visible, `Approve` on a blank region is not offered as a placeholder save, and no browser dialog fires when opening and cancelling the delete-panel and custom-blur dialogs; the 625-panel project's strip stays windowed.
- [ ] **Step 3: Real app** at 1440x900 and 1100x700 on `9b7cb59d…` (48 panels, 24 regions) and one project without regions: screenshot, read; check names, boxes aligned on the crop, the engine select (no mock preselected, unavailable engines disabled), the empty state, no console errors, no sideways scroll. Do not detect, read, confirm, approve, blur or edit.
- [ ] **Step 4:** Document in `UI_V2_UNCOVERED.md` section 13 (the `"..."` placeholder, the hard-coded engine preference, stale banners, windowing, sequential confirms, what the engine could expose: a reachable `STALE` in the `RenderStatus` type and the render list, a text-region count on the panel list) and update the spec status line (M5d done; the pipeline stages are all v2; M6 to M8 remain) with verified and not-verified. Commit explicit paths: `refactor(stages): OCR on the workbench`. Do not write the M6 plan; report and ask.
