# UI v2 Home, Projects and Jobs Implementation Plan (M3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old dashboard (and its four queue views) with three v2 screens: a Home inbox of what needs the owner, a Projects page, and a Jobs page, then delete the old dashboard code.

**Architecture:** Screens read engine data through React Query hooks (`features/data/queries.ts`). All decisions (what needs attention, how jobs group, how projects filter) live in small pure modules with unit tests; the screens are thin and built only from `@panelflow/ui-v2`. Routes `/home`, `/projects`, `/jobs` switch from the legacy `HubRoute` to the new pages; `/library` gets an honest page until M7.

**Tech Stack:** React 18, `@panelflow/ui-v2`, react-router 7, `@tanstack/react-query` 5, `tsx --test`, Playwright on installed Chrome.

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (sections 5, 6, 7 row M3). Builds on `docs/superpowers/plans/2026-11-08-ui-v2-foundations-and-shell.md` (M1+M2, done on branch `feat/ui-v2`). Open items: `docs/UI_V2_UNCOVERED.md`.

## Global Constraints

- Engine (`engine/`) is not changed; no new dependencies. Screens use semantic tokens only (no raw hex or palette utilities; the ratchet test enforces it). Sentence case, verb-first buttons, errors say what happened and what to do, empty states invite an action. Status is never colour alone. `backdrop-blur` only on hub surfaces (Home, Projects, Jobs headers and panels), never on lists that scroll long content.
- Fixed owner rules: the rights gate stays (a project with `rights_status === "UNKNOWN"` is never offered a path past it); uploads are private by default and nothing here publishes, schedules or uploads; local-first.
- Test commands: `npm run test:ui` (add new test dirs to the script in Task 1), `cd apps/desktop && npx tsc --noEmit -p .`, `cd apps/desktop && npx playwright test`. Tests run with `--tsconfig apps/desktop/tsconfig.json`.
- Check each screen in the real app against the live engine at 1440x900 and 1100x700 and say what was not verified. Commit only the files a task touches (the tree has unrelated changes).
- Polling intervals: jobs 3000 ms while any job is RUNNING or QUEUED, else 8000 ms; projects 8000 ms; resources 8000 ms; all only while `useEngine().connected`.

## Review Focus

1. Fresh install with no projects, no jobs, no series: Home shows "Nothing needs you" with a Create a project action; Projects and Jobs show invitations, not blank panels. (Tasks 5, 6, 7)
2. A failed job that a later job of the same project and type has superseded (succeeded, running or queued) must not appear in the inbox. (Task 2)
3. A project with unknown rights shows one "Rights decision" item that opens the acquire stage; no inbox item for it may link to render, publish or upload. (Task 2)
4. A cover image that 404s or never loads shows the initials tile, not a broken-image icon (the audit saw one). (Task 6)
5. Retry and Cancel on a job cannot be double-submitted (button shows loading and ignores a second click), and deleting a project always asks first in an in-app dialog and reports a failure in words. (Tasks 5, 6)

---

### Task 1: Data hooks

**Files:**
- Create: `apps/desktop/src/features/data/queries.ts`
- Modify: root `package.json` (`test:ui` also globs `apps/desktop/src/features/**/__tests__/*.test.ts*`)
- Test: `apps/desktop/src/features/data/__tests__/queries.test.ts`

**Interfaces:**
- Produces: `queryKeys = { projects: ["projects"], jobs: ["jobs"], resources: ["resources"], cover: (id: string, version: string) => ["cover", id, version], series: ["original-series"], creations: ["creations"] } as const`; `jobsPollInterval(jobs: Job[] | undefined): number` (3000 if any `RUNNING`/`QUEUED`, else 8000); `coverVersion(p: Pick<Project,"updated_at"|"total_pages">): string` (`"<updated_at>:<total_pages>"`); hooks `useProjects(): UseQueryResult<Project[]>`, `useJobs(limit?: number): UseQueryResult<Job[]>` (default 200 via `api.listAllJobs(undefined, undefined, limit)`), `useResources(): UseQueryResult<SystemResourcesResponse>`, `useOriginalSeries(): UseQueryResult<OriginalSeries[]>`, `useCreations(): { stories: OriginalStorySummary[]; chronoJobs: ChronoFlowJobSummary[]; failed: boolean }`, `useProjectCovers(projects: Project[]): Record<string, string | undefined>` (first page by `sequence === 1` or first, URL from `api.getPageImageUrl`, one query per project keyed by `coverVersion`), `useRetryJob()` and `useCancelJob()` returning `UseMutationResult<unknown, Error, string>` that invalidate `queryKeys.jobs` on success and call `useError().reportError` on failure with the old messages ("Retry job failed", "Cancel job failed").

- [ ] **Step 1: Write failing tests:** `jobsPollInterval([])` is 8000; with one `RUNNING` job 3000; with only `SUCCEEDED` 8000; `undefined` 8000; `coverVersion({updated_at:"2026-11-06", total_pages:78})` is `"2026-11-06:78"`; `queryKeys.cover("p1","v")` equals `["cover","p1","v"]`.
- [ ] **Step 2:** Run `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/data/__tests__/queries.test.ts`; expect FAIL (module missing).
- [ ] **Step 3:** Implement the pure helpers and the hooks (hooks set `enabled: useEngine().connected`, `refetchInterval` as in Global Constraints, `retry: 1`). Add `"apps/desktop/src/features/**/__tests__/*.test.ts*"` to the `test:ui` script in the root `package.json`.
- [ ] **Step 4:** Run the test; expect PASS; `npx tsc --noEmit -p .` exit 0.
- [ ] **Step 5:** Commit: `feat(data): query hooks for projects, jobs, covers and creations`.

### Task 2: Inbox model

**Files:**
- Create: `apps/desktop/src/features/home/inbox.ts`
- Test: `apps/desktop/src/features/home/__tests__/inbox.test.ts`

**Interfaces:**
- Consumes: `Stage`, `paths`, `isChronoFlowProject` from `../../app/routes`; `InboxKind` from `@panelflow/ui-v2`.
- Produces: `type InboxAction = { type: "open"; to: string } | { type: "retry-job"; jobId: string }`; `interface InboxItem { id: string; kind: InboxKind; title: string; subtitle: string; actionLabel: string; action: InboxAction; projectId?: string; at: string }`; `reviewStageFor(stage: PipelineStage): Stage | null`; `buildInbox(input: { projects: Project[]; jobs: Job[]; series: OriginalSeries[]; now?: number }): InboxItem[]`; `pickFocusProject(projects: Project[], items: InboxItem[]): Project | undefined`.
- Rules, in order of priority per project (one item per project, the highest wins; episode items are independent):
  1. **failed**: for each project and `job_type`, take the newest job by `created_at`; if its status is `FAILED` and it finished within 7 days of `now` (default `Date.now()`), emit `kind "failed"`, title `"<Job label> failed, <project title>"`, subtitle the first line of `job.error` (else `job.message`) cut at 90 characters, `actionLabel "Retry"`, action `retry-job`. A newer `SUCCEEDED`, `RUNNING` or `QUEUED` job of the same type removes it.
  2. **blocked**: `rights_status === "UNKNOWN"` gives `"Rights decision, <title>"`, subtitle `"Source rights are unknown, so rendering is held"`, `actionLabel "Decide"`, action open `paths.stage(id, "acquire")`.
  3. **review** via `reviewStageFor`: `ACQUIRED` pages, `PANELS_DETECTED` panels, `OCR_COMPLETE` ocr, `STORY_ANALYZED` story, `SCRIPT_GENERATED` script, `VOICE_GENERATED` audio, `SHOT_PLAN_GENERATED` motion, `RENDERED` render; every other stage `null`. Title `"Review <noun>, <title>"` (nouns: pages, panels, OCR, story, script, audio, motion, render), `actionLabel "Review"`.
  4. **publish**: `QA_APPROVED` gives `"Package and upload, <title>"`, action open `paths.stage(id, "publish")`, `actionLabel "Open"`.
  - Episodes: for each series episode with `status === "done"`, no `youtube_url` and `upload_status === ""`: `kind "publish"`, title `"Upload episode <n>, <series name>"`, action open `paths.create("stories")`; `upload_status === "failed"`: `kind "failed"`, subtitle `upload_error`.
  - ChronoFlow projects (`isChronoFlowProject`) produce no stage items. Order: kind rank failed, blocked, review, publish, then `at` newest first (`at` is `updated_at` for projects, `finished_at ?? created_at` for jobs).
  - `pickFocusProject`: the project of the first item that has a `projectId`; else the most recently `updated_at` project; `undefined` when there are none.

- [ ] **Step 1: Write failing tests** (fixtures with the real field names): a project at each of the 8 review stages yields the right `to` path and label; `OCR_APPROVED` and `NEW` yield nothing; an `UNKNOWN`-rights project yields exactly one `blocked` item whose `to` is `/projects/<id>/acquire` and no item for that project links to `render` or `publish`; a `FAILED` OCR job with a newer `SUCCEEDED` OCR job yields nothing, with a newer `RUNNING` one yields nothing, but a `FAILED` job older than 7 days yields nothing and one 1 day old yields a `retry-job` item; a project with both a failed job and a review stage yields only the failed item; an episode matrix (done/no upload, done/uploaded, done/failed, running) yields publish, nothing, failed, nothing; ordering is failed, blocked, review, publish; a ChronoFlow project at `OCR_COMPLETE` yields nothing; `pickFocusProject` cases; empty input yields `[]`.
- [ ] **Step 2:** Run the test; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS. **Step 5:** Commit: `feat(home): inbox model`.

### Task 3: Jobs model

**Files:**
- Create: `apps/desktop/src/features/jobs/jobsView.ts`
- Test: `apps/desktop/src/features/jobs/__tests__/jobsView.test.ts`

**Interfaces:**
- Produces: `type JobTab = "active" | "failed" | "done"`; `jobLabel(jobType: string): string` (`"OCR_EXTRACTION"` gives `"OCR extraction"`, `"RENDER"` gives `"Render"`, unknown `"H3_CLIP"` gives `"H3 clip"`: words lowercased, first letter upper-cased, tokens `OCR`, `H3`, `PDF`, `GPU` kept upper-case); `groupJobs(jobs: Job[]): Record<JobTab, Job[]>` (active = `RUNNING` then `QUEUED`, each newest first; failed = `FAILED` and `CANCELLED`, newest first by `finished_at ?? created_at`; done = `SUCCEEDED`, newest first); `jobDuration(job: Job, now: number): string | null` (`"3 min 12 s"`, `"45 s"`, `"1 h 4 min"`; uses `started_at` to `finished_at ?? now`; `null` without `started_at`); `firstErrorLine(job: Job): string` (first non-empty line of `error`, cut at 160 characters, else `message`, else `"No details were recorded."`).

- [ ] **Step 1: Write failing tests** with the examples above plus: `groupJobs([])` gives three empty arrays; a `CANCELLED` job lands in failed; a job with `started_at` null has duration `null`; `firstErrorLine` for a multi-line traceback returns only line one.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS. **Step 5:** Commit: `feat(jobs): jobs view model`.

### Task 4: Projects model

**Files:**
- Create: `apps/desktop/src/features/projects/projectsView.ts`, `apps/desktop/src/features/projects/favorites.ts`
- Move: `components/dashboard/__tests__/groupBySeries.test.ts` to `features/projects/__tests__/groupBySeries.test.ts` (git mv; fix its import) and move `groupBySeries` with its `CHAPTER_RE` out of `ProjectsWorkspace.tsx` into `projectsView.ts` unchanged
- Test: `apps/desktop/src/features/projects/__tests__/projectsView.test.ts`

**Interfaces:**
- Produces: `groupBySeries(projects: Project[]): { groups: Array<{ series: string; projects: Project[] }>; singles: Project[] }` (unchanged behaviour); `type ProjectFilter = "all" | "needs-you" | "favorites"`; `filterProjects(projects: Project[], opts: { query: string; filter: ProjectFilter; favorites: Record<string, boolean>; needsYou: ReadonlySet<string> }): Project[]` (case-insensitive substring on title; then filter; result sorted by `updated_at` newest first); `projectInitials(title: string): string` (first letters of the first two words, upper-case; `"Regressed Son Of A Duke"` gives `"RS"`; single word gives its first two letters; empty gives `"?"`); `stageLabel(stage: PipelineStage): string` (`"OCR_COMPLETE"` gives `"OCR ready for review"`, mapping: NEW "Not started", RIGHTS_APPROVED "Rights approved", ACQUIRED "Pages imported", NORMALIZED "Pages prepared", PANELS_DETECTED "Panels ready for review", OCR_COMPLETE "OCR ready for review", OCR_APPROVED "OCR approved", STORY_ANALYZED "Story ready for review", STORY_APPROVED "Story approved", SCRIPT_GENERATED "Script ready for review", SCRIPT_APPROVED "Script approved", VOICE_GENERATED "Audio ready for review", AUDIO_APPROVED "Audio approved", SHOT_PLAN_GENERATED "Motion ready for review", MOTION_APPROVED "Motion approved", RENDERED "Render ready for review", QA_APPROVED "Ready to upload", EXPORTED "Exported"); `toggleFavorite(favorites: Record<string, boolean>, id: string): Record<string, boolean>`; `loadFavorites(storage: Pick<Storage,"getItem">): Record<string, boolean>` and `saveFavorites(storage: Pick<Storage,"setItem">, favorites)` using the existing key `panelflow_project_favorites` (invalid JSON or a throwing storage gives `{}`).

- [ ] **Step 1: Write failing tests:** `filterProjects` with query `"duke"` matches case-insensitively; `needs-you` keeps only ids in the set; `favorites` keeps favourites; results are newest-updated first; `projectInitials` cases above; `stageLabel` has a non-empty entry for all 18 stages; `toggleFavorite` flips and does not mutate its input; `loadFavorites` with bad JSON and with a throwing `getItem` returns `{}`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run (including the moved `groupBySeries` test); expect PASS. **Step 5:** Commit: `feat(projects): projects view model`.

### Task 5: Jobs page

**Files:**
- Create: `apps/desktop/src/features/jobs/JobsPage.tsx`, `JobRow.tsx`, `JobDetailsDrawer.tsx`
- Test: `apps/desktop/src/features/jobs/__tests__/jobsPage.test.tsx` (jsdom `mount`, QueryClient with `api.listAllJobs` and `api.listProjects` stubbed on the singleton, `client.clear()` in cleanup)

**Interfaces:**
- Consumes: Task 1 hooks, Task 3 helpers, `Tabs`, `Drawer`, `JobCard`-style rows, `EmptyState`, `ErrorState`, `Skeleton`, `PageHeader`.
- Produces: `JobsPage: React.FC` (tabs Active, Failed, Done with counts; header meta "N running, M waiting"); `JobRow({ job, projectTitle, onOpen, onRetry, onCancel, busy })` (title `jobLabel` plus project title, `Progress` while running, duration, `firstErrorLine` for failed, Retry for failed, Cancel for active; both buttons `loading={busy}`); `JobDetailsDrawer({ job, projectTitle, open, onOpenChange })` (status, message, full error in a selectable `pre`, started/finished, retries, project link).

- [ ] **Step 1: Write failing tests:** with 1 running, 1 queued, 2 failed, 3 succeeded the tab labels read "Active 2", "Failed 2", "Done 3"; the Active tab lists running before queued; a failed job shows its first error line and a Retry button; clicking Retry calls `api.retryJob` once with the job id even when clicked twice quickly; with no jobs at all every tab shows an invitation ("No jobs yet. Start a pipeline stage and it shows up here."); a rejected `listAllJobs` shows an `ErrorState` with Retry.
- [ ] **Step 2:** Run `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/jobs/__tests__/jobsPage.test.tsx`; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(jobs): Jobs page`.

### Task 6: Projects page

**Files:**
- Create: `apps/desktop/src/features/projects/ProjectsPage.tsx`, `ProjectTile.tsx`, `CreationsSection.tsx`
- Test: `apps/desktop/src/features/projects/__tests__/projectsPage.test.tsx`

**Interfaces:**
- Consumes: Tasks 1, 2, 4 and `Menu`, `Dialog`, `Tile`, `Tabs`, `Input`, `useToast`.
- Produces: `ProjectsPage: React.FC` (search field, tabs All / Needs you / Favorites, projects grouped by `groupBySeries` with a heading per series, singles after; header action "Create a project" to `paths.create("new")`; `CreationsSection` lists Original Stories and ChronoFlow videos exactly as the old `CreationsPanel` did, using `ListRow`s that open the folder, the video or the studio); `ProjectTile({ project, coverUrl, favorite, needsYou, onOpen, onToggleFavorite, onOpenEditor, onOpenFolder, onDelete })` (Tile with `stageLabel` subtitle, a "Needs you" `Chip` when `needsYou`, a star `IconButton` with `aria-pressed`, a `Menu` with Open story editor, Open folder, Delete project).
- Delete flow: Delete project opens a `Dialog` ("Delete <title>?", "This removes the project and its workspace. You cannot undo this.") with Cancel and a danger Delete project button; success removes it from the cache and shows a toast "Project deleted"; failure keeps it and reports "Couldn't delete the project. <engine message>" through `useError().reportError`.

- [ ] **Step 1: Write failing tests:** typing "duke" in search hides non-matching tiles; the Favorites tab shows only starred projects and the star toggle persists through `saveFavorites`; a project whose cover URL fails (`img` `onError`) shows its initials, no `<img>`; Delete opens the dialog, Cancel closes it without calling `api.deleteProject`, confirming calls it once with the id and removes the tile; a rejected `deleteProject` keeps the tile; zero projects shows the invitation "No projects yet" with a Create a project button.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement (cover state per tile: `useState(false)` failed flag set by `onError`). **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(projects): Projects page`.

### Task 7: Home page

**Files:**
- Create: `apps/desktop/src/features/home/HomePage.tsx`, `ProjectHero.tsx`, `NeedsYou.tsx`, `RunningNow.tsx`
- Test: `apps/desktop/src/features/home/__tests__/homePage.test.tsx`

**Interfaces:**
- Consumes: `buildInbox`, `pickFocusProject`, Tasks 1 and 4, `InboxRow`, `JobCard`, `Tile` (the shell already shows engine state, so Home does not repeat it).
- Produces: `HomePage: React.FC` laid out as the approved mockup (`docs/design/mockups/home-midnight-glass.html`): left column `ProjectHero` (cover via `useProjectCovers`, title, `stageLabel`, `Chip`s, primary Continue to the project's `stageForProject` route, ChronoFlow projects to ChronoFlow) above "Recent projects" tiles (4, newest updated); right column `NeedsYou({ items, onAction })` (grouped headings Failed, Blocked, Review, Ready to publish; the first row selected; capped at 8 with "Show all N" expanding in place) and `RunningNow({ jobs })` (up to 3 active jobs as `JobCard`s with progress, link "All jobs" to `/jobs`). `onAction`: `open` navigates, `retry-job` calls `useRetryJob`. Empty inbox: `EmptyState` "Nothing needs you" with Create a project and Open Original Stories actions.

- [ ] **Step 1: Write failing tests** (stub `api` methods, jsdom): with a review item, a failed item and a publish item the sections appear in the order Failed, Review, Ready to publish; clicking the failed row's Retry calls `api.retryJob` once; clicking a review row navigates to `/projects/<id>/ocr` (memory router); with 12 inbox items 8 show until "Show all 12" is pressed; with no projects the empty state with Create a project is shown and no hero; the hero is the project of the first inbox item; running jobs render with progress and "All jobs" links to `/jobs`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(home): Home inbox`.

### Task 8: Routes and Library

**Files:**
- Modify: `apps/desktop/src/app/router.tsx`; Create: `apps/desktop/src/features/library/LibraryPage.tsx`
- Test: extend `apps/desktop/src/app/__tests__/legacyRoutes.test.tsx` (rename kept) with route-table assertions

**Interfaces:** `/home` lazy-loads `HomePage`, `/projects` `ProjectsPage`, `/jobs` `JobsPage`; `/library` and `/library/*` load `LibraryPage`.

- [ ] **Step 1: Write failing test:** `matchRoutes(appRoutes, "/jobs")` has a route whose `lazy` resolves to a component other than the legacy hub (assert it resolves `JobsPage` by `displayName`/`name`); same for `/home`, `/projects`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement the routes. For Library, first open `AudioLibrary` (`components/audio-library/AudioLibrary.tsx`) in the gallery against the live engine: if it lists real assets, mount it at `/library/audio` and make `/library` redirect there; if it needs mock data or fails, make `LibraryPage` an `EmptyState` ("The library opens inside the story editor for now. A standalone library comes later.") with a Create link, and add that to `docs/UI_V2_UNCOVERED.md`. Record the choice in the ledger as a Ruling.
- [ ] **Step 4:** Run `npm run test:ui`; expect PASS. **Step 5:** Commit: `feat(app): route Home, Projects, Jobs and Library to the v2 pages`.

### Task 9: Delete the old dashboard

**Files:**
- Delete: `apps/desktop/src/components/dashboard/` (all files except what Task 4 moved), `apps/desktop/src/components/MultiProjectQueueDashboard.tsx` (unreferenced), `apps/desktop/src/features/legacy/HubRoute.tsx`
- Modify: `apps/desktop/src/__tests__/legacyColorAllowlist.json` (regenerate), `docs/UI_V2_UNCOVERED.md`

- [ ] **Step 1:** `grep -rn "components/dashboard\|MultiProjectQueueDashboard\|HubRoute" apps/desktop/src` shows only the files being deleted.
- [ ] **Step 2:** Delete them; `JobActivityPanel.tsx` stays (the editor and error modal use it) and `NarrationJobQueue` stays (Narration Studio, M7).
- [ ] **Step 3:** `UPDATE_COLOR_ALLOWLIST=1 npx tsx --test apps/desktop/src/__tests__/noRawColors.test.ts`, check the diff only removes deleted files, then run `npm run test:ui`, `npm test`, `npx tsc --noEmit -p .`; all exit 0.
- [ ] **Step 4:** In `UI_V2_UNCOVERED.md` mark fixed: Library mislabel, the four queue views (now one), `listAnimeJobs` and `listBatchJobs` still not shown (add "decide in M3 follow-up: only engine jobs are listed").
- [ ] **Step 5:** Commit: `refactor(ui): remove the old dashboard and unused queue dashboard`.

### Task 10: Verify and close M3

**Files:**
- Create: `apps/desktop/e2e/hubs.spec.ts`; Modify: spec status line in `docs/superpowers/specs/2026-11-08-ui-v2-design.md`

- [ ] **Step 1: Playwright (engine required, skipped otherwise):** Home shows a "Needs you" region and, when the inbox has rows, activating the first row changes the route to a project stage; Projects search "xyz-no-match" shows the empty result message and clearing it restores tiles; Jobs shows the three tabs and switching tab changes the visible list; each page has exactly one `h1`. Run `npx playwright test`; expect all pass.
- [ ] **Step 2: Real app at 1440x900 and 1100x700:** open `#/home`, `#/projects`, `#/jobs`; screenshot each; read them; check no horizontal overflow (`scrollWidth <= innerWidth`), no console errors, covers load or fall back to initials, Retry on a real failed job (only if one exists) re-queues it, text selectable. State what was not exercised (for example Delete on real data: do not delete a real project; verify the dialog only).
- [ ] **Step 3: Glass cost:** in the browser pane sample 120 `requestAnimationFrame` deltas on `#/home` while scrolling and report the average frame time; repeat with `backdrop-filter` forced off (`document.querySelectorAll("*")` style override) and keep blur only if the difference is under 3 ms; otherwise drop blur from the lists and note it in the ledger.
- [ ] **Step 4:** Update the spec status to "M1 to M3 implemented" with what was verified and not; update `docs/UI_V2_UNCOVERED.md`; commit `docs(ui): M3 done`.
- [ ] **Step 5:** Write the M4 plan (Settings: engine, models, providers, YouTube, diagnostics).
