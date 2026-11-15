# UI v2 Workbench Frame and Publish Stage Implementation Plan (M5a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every pipeline stage one consistent frame (project header, a real pipeline stepper with stale and blocked states, Auto-Pilot in one place) and add the missing Publish stage, so a finished video ends in a screen that checks it and hands the owner everything needed to upload.

**Architecture:** A pure `stageModel` turns a project into stepper states. `WorkbenchFrame` renders the header and stepper around whatever stage body the route supplies (the nine legacy screens keep working inside it). `PublishStage` is new, built on `@panelflow/ui-v2`, with its decisions in a pure `publishModel`. Per-stage rebuilds of the legacy screens are **not** in this plan (see Scope).

**Tech Stack:** React 18, `@panelflow/ui-v2`, react-router 7, `@tanstack/react-query` 5, `tsx --test`, Playwright on installed Chrome. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (sections 5, 6, 7 row M5). Builds on M1 to M4a (done on `feat/ui-v2`). Open items: `docs/UI_V2_UNCOVERED.md`.

## Scope

- **In M5a:** stage model and stepper (adds the Pages and Publish steps the old stage bar lacks), `WorkbenchFrame` replacing `PipelineNavbar` and the page title in `LegacyStageRoute`, one Auto-Pilot button, the Publish stage (checks, latest render with its validation report, YouTube packaging to copy), heading-level cleanup, browser checks.
- **Deferred, each its own plan after this one, in this order of use:** M5b Acquire, Pages, Motion, Audio (small, 330 to 1,040 lines); M5c Story and Script (about 1,000 lines each); M5d Panels and OCR (1,700 and 2,800 lines and 28 to 34 engine calls each: the densest tools, rebuilt last and carefully). The legacy screens keep their own approve actions and their own back button until then.
- **Engine facts this plan respects:** there is no upload endpoint for pipeline projects (YouTube upload exists only for Original Stories episodes), so Publish never offers to upload, publish or schedule. `GET /api/projects/{id}/youtube/packaging` **generates** packaging when nothing is saved (a slow LLM job), so Publish never calls it on page open, only when the owner presses a button. The rights gate is enforced at project creation and by the engine; this plan adds no path past it.

## Global Constraints

- Engine (`engine/`) and the owner's uncommitted files (`components/ProviderHealthModal.tsx`, `packages/api-client/src/index.ts`, `engine/youtube/*`, `engine/api/routers/youtube.py`) are not edited; no new dependencies; semantic tokens only (the colour ratchet enforces it); sentence case, verb-first buttons, errors say what happened and what to do, empty states invite an action; status is never colour alone.
- Fixed owner rules: rights UNKNOWN is refused and never shown as ready; YouTube uploads are private by default and nothing here publishes; local-first.
- Stage keys and routes stay as in `app/routes.ts` (`acquire, pages, panels, ocr, story, script, audio, motion, render, publish`); `stageForProject`, `nextStage`, `prevStage` are unchanged.
- Tests: `npm run test:ui`, `cd apps/desktop && npx tsc --noEmit -p .`, `cd apps/desktop && npx playwright test`; run with `--tsconfig apps/desktop/tsconfig.json`; page tests use `features/__tests__/pageHarness.tsx` (`mountPage`, `settle`, `press`, `clickTwice`).
- Commit only the files a task touches, with explicit paths (never `git add -A` on a folder). After each task `git diff HEAD` over the owner's files must hash the same as the baseline recorded in the ledger. Checks on real data only read and navigate: do not press Generate or Refresh packaging, Retry, Approve, or Auto-Pilot's Start on the owner's projects; say what was not exercised.

## Review Focus

1. A stage's state never lies: a stale stage says Stale in words even if it was done; a project with unknown rights shows Render and Publish as Blocked, never ready or done. (Task 1)
2. Publish never offers upload, publish or schedule for a pipeline project, says uploads are private by default, and makes no packaging request until a button is pressed. (Task 4)
3. A project with no render, a failed render, a stale render, or no packaging yet shows the reason and the next action in each part of Publish, not a blank panel. (Task 4)
4. Every stage URL still opens, the legacy approve and proceed callbacks still move to the next stage, and Auto-Pilot's stage links still land on the right stage. (Task 2)
5. Exactly one h1 and no sideways scroll on every stage at 1440 and 1100 px, and the stepper works from the keyboard. (Tasks 2, 5)

---

### Task 1: Stage model

**Files:**
- Create: `apps/desktop/src/features/workbench/stageModel.ts`
- Test: `apps/desktop/src/features/workbench/__tests__/stageModel.test.ts`

**Interfaces:**
- Consumes: `Stage`, `STAGES`, `paths` from `app/routes`; v2 `Step`.
- Produces: `STAGE_LABEL: Record<Stage, string>` (acquire "Source", pages "Pages", panels "Panels", ocr "OCR", story "Story", script "Script", audio "Audio", motion "Motion", render "Render", publish "Publish"); `stageSteps(project: Pick<Project, "id" | "current_stage" | "rights_status" | "stale_stages">): Step[]` in `STAGES` order, each `{ id, label, status, href? }`.
- Rules (a stage is "within" its range when `current_stage` is in it, and "past" when `current_stage` is later than the range): ranges: acquire `NEW`..`RIGHTS_APPROVED`; pages `ACQUIRED`; panels `NORMALIZED`..`PANELS_DETECTED`; ocr `OCR_COMPLETE`..`OCR_APPROVED`; story `STORY_ANALYZED`..`STORY_APPROVED`; script `SCRIPT_GENERATED`..`SCRIPT_APPROVED`; audio `VOICE_GENERATED`..`AUDIO_APPROVED`; motion `SHOT_PLAN_GENERATED`..`MOTION_APPROVED`; render `RENDERED`; publish `QA_APPROVED`, and publish is also done at `EXPORTED`. Status order of precedence: `stale` (the stage key is in `stale_stages`) beats everything; then `blocked` (rights `UNKNOWN` and the stage is render or publish and it is not past); then `active` (within range); then `done` (past); else `upcoming`. `href` (`paths.stage(id, stage)`) is set for every step that is not `upcoming`, and for the first `upcoming` step after the last non-upcoming one (the next stage, which the owner can open); later upcoming steps have no `href`.

- [ ] **Step 1: Write failing tests:** a project at each of the 18 `PipelineStage` values produces exactly one `active` step at the expected stage (for example `OCR_COMPLETE` gives ocr active, acquire to panels done, story to publish upcoming; `QA_APPROVED` gives publish active and render done; `EXPORTED` gives every step done); `stale_stages: ["audio"]` at `SCRIPT_APPROVED` makes audio `stale` and keeps the others as they are; stale beats done (project at `RENDERED` with `["motion"]` shows motion stale, not done); rights `UNKNOWN` at `MOTION_APPROVED` makes render and publish `blocked` and nothing else blocked, while at `EXPORTED` they stay done; an unknown `AUTHORIZED_WEB`-style rights value is not blocked; `href` exists for done, active, stale and blocked steps and for exactly one upcoming step; labels match `STAGE_LABEL`; the step ids equal `STAGES`.
- [ ] **Step 2:** Run `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/workbench/__tests__/stageModel.test.ts`; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(workbench): stage model for the stepper`.

### Task 2: WorkbenchFrame and wiring

**Files:**
- Create: `apps/desktop/src/features/workbench/WorkbenchFrame.tsx`, `rightsLabel.ts`
- Modify: `apps/desktop/src/features/legacy/LegacyStageRoute.tsx`
- Delete: `apps/desktop/src/components/PipelineNavbar.tsx` (only `LegacyStageRoute` uses it; confirm with grep first)
- Test: `apps/desktop/src/features/workbench/__tests__/workbenchFrame.test.tsx`, `rightsLabel.test.ts`

**Interfaces:**
- `rightsLabel(status: string): { word: string; tone: "ok" | "warn" | "neutral" }`: `UNKNOWN` gives "Rights unknown" with tone warn; `PUBLIC_DOMAIN` "Public domain"; `CREATIVE_COMMONS` "Creative Commons"; `LICENSED` "Licensed"; `USER_OWNED` "Your own work"; `EXPLICIT_PERMISSION` "Permission granted"; `COMMENTARY_REVIEW` "Commentary and review" (all ok); any other value is humanised (`AUTHORIZED_WEB` gives "Authorized web", neutral).
- `WorkbenchFrame({ project, stage, onAutoPilot, children })`: a breadcrumb link "Projects" to `/projects`; the project title as the page's one `h1`; chips for the pipeline stage (`stageLabel` from `features/projects/projectsView`), the rights label, and "Needs a rerun" when `stale_stages` is non-empty; actions Auto-Pilot (secondary button, calls `onAutoPilot`; the only Auto-Pilot control on the page) and "Open story editor" (link to `paths.editor(project.id)`); the v2 `Stepper` from `stageSteps(project)` with the current `stage` step marked current by the frame (the frame passes `aria-current="step"` through `Stepper`'s `status: "active"` only for the project's own active step; the viewed stage gets a visible ring via a `viewed` flag added to `Step`); the stage body below in `<div data-stage-body>`.
- `LegacyStageRoute` renders `WorkbenchFrame` around the legacy stage screen (replacing `PageHeader`, the `GlassPanel` with `PipelineNavbar`, and its Auto-Pilot button) and keeps `AutoPilotModal` and every callback unchanged; its `publish` case renders `PublishStage` once Task 4 lands (until then it renders `RenderScreen` as today).
- v2 change: add optional `viewed?: boolean` to `Step`; `Stepper` marks it with a ring and `aria-label` text "viewing" in addition to the status word (update `patterns.test.tsx`).

- [ ] **Step 1: Write failing tests:** `rightsLabel` mapping and humanising; frame markup: ten stepper items in order with the Source to Publish labels, `Stale` and `Blocked` shown as words for a stale or unknown-rights project, exactly one button named Auto-Pilot, one link named Open story editor to `/editor/<id>`, exactly one `h1` with the project title, the viewed stage marked, children rendered inside `[data-stage-body]`; a stepper step that is `upcoming` beyond the next one is not a link; `Stepper` test for `viewed`.
- [ ] **Step 2:** Run both new files and `patterns.test.tsx`; expect FAIL. **Step 3:** Implement; replace the frame pieces in `LegacyStageRoute`; delete `PipelineNavbar.tsx` and its now-unused key maps (`NAVBAR_KEY_TO_STAGE`, `stageToNavbarKey`) after grep shows no users. **Step 4:** Run `npm run test:ui` (including the M2 route tests) and `tsc`; expect PASS. **Step 5:** Update the colour allowlist if a legacy file disappears (`UPDATE_COLOR_ALLOWLIST=1 ...noRawColors.test.ts`, diff only removes deleted files). Commit: `feat(workbench): workbench frame with a real pipeline stepper`.

### Task 3: Publish model

**Files:**
- Create: `apps/desktop/src/features/workbench/publishModel.ts`
- Test: `apps/desktop/src/features/workbench/__tests__/publishModel.test.ts`

**Interfaces:**
- Produces: `type CheckState = "pass" | "fail" | "pending"`; `interface PublishCheck { id: "rights" | "approved" | "render" | "fresh" | "valid"; label: string; state: CheckState; detail: string }`; `latestRender(renders: RenderJob[]): RenderJob | undefined` (newest `COMPLETE` render by `render_id` order of the list as returned newest first; else undefined); `publishChecks(input: { project: Pick<Project, "current_stage" | "rights_status" | "stale_stages">; renders: RenderJob[] }): PublishCheck[]` in this order: rights (`pass` unless `UNKNOWN`: detail "Rights are declared" or "Rights are unknown, so publishing is held"); approved (`pass` when `current_stage` is `QA_APPROVED` or `EXPORTED`, else `pending` with "Approve the render first"); render (`pass` when a complete render exists, `fail` when the newest render failed with its `error_message`, `pending` when none: "Render the video first"); fresh (`fail` "Audio or motion changed after this render. Render again." when `stale_stages` includes render, else `pass`); valid (from the latest render's `validation_report`: `pass` when `is_valid` with warnings counted in the detail, `fail` listing the first warning when not valid, `pending` when no report); `canHandOff(checks: PublishCheck[]): boolean` is true only when no check is `fail` (pending checks do not block copying, but the UI says what is pending).
- `chaptersText(chapters: YouTubeChapter[]): string` (one `"<timestamp> <title>"` per line); `packagingBundle(data: YouTubePackagingData, title: string): string` (title, blank line, description, blank line, chapters if any, blank line, tags line from `tags_string`, hashtags line from `hashtags_string`); `durationLabel(seconds: number): string` (`"6 min 10 s"`, `"45 s"`, `"1 h 4 min"`).

- [ ] **Step 1: Write failing tests:** the five checks in order for a project at each of: unknown rights (rights fails, `canHandOff` false), approved with a valid render (all pass), `RENDERED` without approval (approved pending), no renders (render pending, valid pending), failed newest render (render fails with its message), stale render (fresh fails), invalid report with two warnings (valid fails, detail names the first warning), a valid report with three warnings (pass, detail "3 warnings"); `latestRender` picks the newest complete one and ignores failed and queued; `chaptersText` and `packagingBundle` exact strings for a fixture (including no chapters, no tags); `durationLabel` cases.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(workbench): publish checks and packaging text`.

### Task 4: Publish stage

**Files:**
- Create: `apps/desktop/src/features/workbench/PublishStage.tsx`, `PublishChecks.tsx`, `LatestRender.tsx`, `PackagingPanel.tsx`, `queries.ts`
- Modify: `apps/desktop/src/features/legacy/LegacyStageRoute.tsx` (`publish` case)
- Test: `apps/desktop/src/features/workbench/__tests__/publishStage.test.tsx`

**Interfaces:**
- `queries.ts`: `useRenders(projectId: string)` (`api.listRenders`, refetch every 5000 ms only while the newest render is not `COMPLETE` or `FAILED`), `useRenderValidation(projectId: string, renderId: string | undefined)` (`api.getRenderValidation`, enabled only with a render id), hooks gated on `useEngine().connected`.
- `PublishStage({ project })`: three panels. (1) `PublishChecks`: the five checks with Pass, Failed or Waiting in words and their detail; a sentence "PanelFlow does not upload pipeline videos yet. Copy the details below and upload in YouTube Studio, with the video set to Private first. Original Stories episodes upload from Create." (2) `LatestRender`: the newest complete render: output profile, duration (`durationLabel` from the validation report), a `<video controls preload="metadata">` using `api.getRenderVideoUrl(project.id, render.render_id)`, the validation summary (video, audio, sync valid in words, black frame and gap counts, warnings list) from `useRenderValidation`, and an Open project folder button (`api.openProjectFolder`); with no render, an `EmptyState` "No finished render yet" with an Open render stage link. (3) `PackagingPanel`: initially an `EmptyState` "Packaging isn't loaded" explaining that loading saved packaging, or generating it if none exists, can take a minute, with a **Get packaging** button; only that button calls `api.getYoutubePackaging(project.id, false)`; once loaded: selectable titles (the selected one marked), the description in a read-only textarea, tags, hashtags, chapters, thumbnail prompt and text hooks, each with a Copy button that copies exactly the shown text and says "Copied", a Copy everything button using `packagingBundle`, and a Refresh packaging button (`refresh=true`) behind a confirm `Dialog` ("This asks the local model to write new packaging. It can take a minute and replaces the saved version."). A failed load shows "Couldn't load packaging. Check that the engine and Ollama are running, then try again." with Retry (no raw exception text).
- Busy guards are synchronous refs (fast double clicks request once).

- [ ] **Step 1: Write failing tests** (stub `api`): opening the page makes no call to `getYoutubePackaging` or `generateYoutubePackaging`; the checks panel shows each state in words and never contains the words Upload now, Publish now or Schedule; the copy explains private-first and manual upload; a project with unknown rights shows the rights check failing and the hand-off sentence still appears; with a complete render the video element has the output URL, the validation shows `Video valid`, `Audio valid`, `Sync valid` and a warning text, and Open project folder calls `api.openProjectFolder` once on a double click; with no renders the empty state shows and no video element exists; pressing Get packaging calls `getYoutubePackaging(id, false)` once even on a double click and then shows titles, description, tags, chapters and the thumbnail prompt; each Copy writes exactly the displayed text through an injected `copy` prop and shows Copied; Refresh asks for confirmation first, Cancel makes no request and Confirm calls `getYoutubePackaging(id, true)` once; a rejected packaging load shows the sentence above without the exception text and offers Retry; a failed render shows its error message and that Render is the next action.
- [ ] **Step 2:** Run `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/workbench/__tests__/publishStage.test.tsx`; expect FAIL. **Step 3:** Implement; render `PublishStage` for the `publish` stage in `LegacyStageRoute` (inside the frame, no legacy screen). **Step 4:** Run; expect PASS; `npm run test:ui` and `tsc` exit 0. **Step 5:** Commit: `feat(workbench): Publish stage`.

### Task 5: Headings, browser checks and the real app

**Files:**
- Modify: legacy stage screens only if they render an `h1` (one-word edit each, `h1` to `h2`); Create: `apps/desktop/e2e/workbench.spec.ts`

- [ ] **Step 1: Find the duplicates:** for each stage of a real project (`#/projects/<id>/<stage>` for acquire, pages, panels, ocr, story, script, audio, motion, render, publish) count `document.querySelectorAll("h1")`; list every stage that has more than one. Write the Playwright spec first so it fails on those: for the first project returned by the engine, each stage route has exactly one `h1` (the project title), the stepper has ten items, the Source to Publish labels in order, no sideways scroll of `main` at 1440 and 1100 px, and `Tab` reaches a stepper link and `Enter` follows it. Run; expect FAIL where legacy screens add an `h1`.
- [ ] **Step 2:** Change only the offending `h1` tags in the legacy screens to `h2` (same classes, so nothing visual moves); re-run until green.
- [ ] **Step 3: Playwright, read and navigate only (never press Approve, Retry, Get or Refresh packaging, or Start in Auto-Pilot):** Auto-Pilot opens its dialog from the frame's one button and Escape closes it; Open story editor goes to `/editor/<id>`; Publish shows the checks panel, a latest-render card or the empty state, and the Get packaging button without having requested packaging (watch network requests: none to `/youtube/packaging`). Run `npx playwright test`; expect all pass.
- [ ] **Step 4: Real app at 1440x900 and 1100x700:** open a stage of a real project and Publish for a rendered one; screenshot, read; check no console errors, the stepper shows Stale or Blocked in words where the data says so, and the video plays its first frame (do not press Get packaging). State what was not exercised.
- [ ] **Step 5:** Commit explicit paths: `test(workbench): stage frame and Publish checks in the browser`.

### Task 6: Docs and close

**Files:** Modify: `docs/UI_V2_UNCOVERED.md`, `docs/superpowers/specs/2026-11-08-ui-v2-design.md`

- [ ] **Step 1:** In `UI_V2_UNCOVERED.md`: mark the render validation API as wired (Publish), keep render profiles and render events as unwired, add "Pipeline projects cannot be uploaded to YouTube from PanelFlow (no engine endpoint; Publish hands off packaging to copy)" and "`GET .../youtube/packaging` generates when nothing is saved, so the UI must treat it as a generate action", and list M5b to M5d as the remaining stage rebuilds.
- [ ] **Step 2:** Set the spec status to "M1 to M3, M4a and M5a implemented" with what was verified and not (including the legacy stage bodies still in place). Commit `docs(ui): M5a done`. Do not write the M5b plan in this task; report and ask.
