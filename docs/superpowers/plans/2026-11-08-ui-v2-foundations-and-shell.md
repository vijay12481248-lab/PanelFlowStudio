# UI v2 Foundations and Shell Implementation Plan (M1 + M2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Midnight Glass tokens and primitives (M1) and a new routed app shell with a dock, command palette and every legacy screen mounted inside it (M2), leaving the app fully usable.

**Architecture:** A new design system lives in `packages/ui/src/v2` (tokens, primitives, patterns) under the separate alias `@panelflow/ui-v2`, because the old `@panelflow/ui` exports clashing names (`Button`, `Input`, `Modal`...). `apps/desktop/src/app` holds the hash router, providers and shell. Legacy screens are wrapped in thin route components that load the project by id and pass the props they take today. Milestones M3 to M8 get their own plans after M2 is verified.

**Tech Stack:** React 18, Tailwind v4 (`@theme`), `react-router`, Radix UI primitives, `cmdk`, `@tanstack/react-query`, `@fontsource-variable/*` fonts, `tsx --test` (node:test + `react-dom/server`), `@playwright/test` (system Chrome).

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (mockup: `docs/design/mockups/home-midnight-glass.html`).

## Global Constraints

- Engine (`engine/`) is not changed.
- Token values come from spec section 3: `--ink #070b1c`, `--navy #0c1433`, `--glow #1b2f7a`, glass `rgba(22,32,72,.55)`, glass-hi `rgba(34,48,98,.62)`, flat `#101a3d`, edge `rgba(150,175,255,.14)`, text `#eef1ff`, dim `#9aa6d0`, faint `#6a76a3`, accent `#3b6bf5`, accent-soft `rgba(59,107,245,.22)`, ok `#46d6a3`, warn `#f0b35a`, bad `#f2667a`, info `#7aa2ff`, radii card 22px / control 14px / pill 999px, fonts Sora (display), Geist (body), Geist Mono (data), type scale 12/13/14/16/20/30, motion 120ms / 200ms, at most two floating layers.
- Tailwind theme names (this plan's decision): `fg`, `fg-dim`, `fg-faint` for the three text colours; others keep the spec names (`ink`, `navy`, `glow`, `glass`, `glass-hi`, `flat`, `edge`, `accent`, `accent-soft`, `ok`, `warn`, `bad`, `info`).
- No raw hex or palette utilities (`indigo-500`) in new code. Status is never colour alone (icon or text too). Text is selectable. `backdrop-filter` only on hub surfaces. All motion off under `prefers-reduced-motion`.
- Copy: sentence case, verb-first buttons, errors say what happened and what to do, empty states invite an action.
- Fixed owner rules: rights gate stays (UNKNOWN refused); YouTube uploads private by default; local-first; verify on real data and say what was not verified; commit only the files a task touches (the tree has unrelated changes).
- Behaviour of legacy screens is preserved in M2; only their frame and navigation change.
- Dependencies approved by the owner on 2026-11-08: `react-router`, Radix primitives, `cmdk`, `@tanstack/react-query`, `@playwright/test` (dev), plus the open-licence font files (delivered as `@fontsource-variable/sora`, `geist`, `geist-mono`). Playwright browser downloads are NOT approved: use the installed Chrome (`channel: "chrome"`).
- Tests: `npx tsx --test <files>` (node:test). New test files are picked up by the `test:ui` script added in Task 1.

## Review Focus

1. Deep link to a project id that does not exist (`#/projects/nope/ocr`): show a clear not-found state with a way back, not a blank page or a crash. (Task 13)
2. Engine offline at launch or mid-session: the shell shows the connect/retry gate and, when the engine returns, keeps the current route. (Tasks 11, 13)
3. A ChronoFlow project (`source_type === "CHRONOFLOW_AI"` or `settings.workflow_type === "chronoflow"`) opened from anywhere goes to ChronoFlow, never a pipeline stage. (Tasks 10, 13)
4. A stage URL the project has not reached yet (`/projects/:id/ocr` while `NEW`) opens, as the old stage bar allowed; an unknown stage segment redirects to the project's current stage. (Task 13)
5. `#/` and an unknown path redirect to `/home`; reload keeps the route; Ctrl K opens and Escape closes the palette and returns focus. (Tasks 13, 15)

---

## Milestone 1: Foundations

### Task 1: Dependencies, fonts and the test script

**Files:**
- Modify: `package.json` (root `scripts.test:ui`), `apps/desktop/package.json`, `packages/ui/package.json` (dependencies only)
- Modify: `apps/desktop/vite.config.ts` and `apps/desktop/tsconfig.json` (alias `@panelflow/ui-v2` -> `../../packages/ui/src/v2/index.ts`)
- Create: `packages/ui/src/v2/index.ts` (empty barrel `export {};`)

**Interfaces:**
- Produces: alias `@panelflow/ui-v2`; script `npm run test:ui` running `npx tsx --test "packages/ui/src/v2/__tests__/*.test.ts*" "apps/desktop/src/app/__tests__/*.test.ts*" "apps/desktop/src/__tests__/noRawColors.test.ts"`.

- [ ] **Step 1:** From the repo root run `npm install --workspace=@panelflow/desktop react-router @tanstack/react-query cmdk @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-tabs @radix-ui/react-tooltip @radix-ui/react-switch @radix-ui/react-toast @fontsource-variable/sora @fontsource-variable/geist @fontsource-variable/geist-mono` and `npm install -D --workspace=@panelflow/desktop @playwright/test`. Set `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` in the environment for the second command.
- [ ] **Step 2:** Add the alias in both config files and the `test:ui` script; create the empty barrel.
- [ ] **Step 3:** Verify: `cd apps/desktop && npx tsc --noEmit -p .` exits 0 and `npm run test:ui` exits 0 (no test files yet is acceptable only if node reports zero tests, otherwise defer this check to Task 2).
- [ ] **Step 4:** Commit `package.json`, both workspace `package.json` files, `package-lock.json`, `vite.config.ts`, `tsconfig.json`, the barrel: `chore(ui): add UI v2 dependencies and alias`.

### Task 2: Design tokens and contrast guard

**Files:**
- Create: `packages/ui/src/v2/tokens.css`, `packages/ui/src/v2/contrast.ts`
- Modify: `apps/desktop/src/index.css` (import fonts and `tokens.css`; add `@source "../../../packages/ui/src/v2";`)
- Test: `packages/ui/src/v2/__tests__/tokens.test.ts`

**Interfaces:**
- Produces: `contrastRatio(fg: string, bg: string): number` (hex or `rgba()` strings; alpha colours are composited over `bg`); `compositeOver(fg: string, bg: string): string` (hex); CSS custom properties `--color-<name>` for every token in Global Constraints, `--radius-card`, `--radius-ctl`, `--font-display`, `--font-body`, `--font-data` inside `@theme`.

- [ ] **Step 1: Write the failing tests** in `tokens.test.ts`: (a) `contrastRatio("#ffffff","#000000")` is within 0.01 of 21; (b) reading `tokens.css`, every name in the Global Constraints token list appears as `--color-<name>:`; (c) these pairs are at least 4.5: `fg` on `ink`, `fg` on `flat`, `fg-dim` on `ink`, `fg-dim` on `flat`, `fg-dim` on glass composited over `navy`; and `fg-faint` on `ink` is at least 3.0 (large or secondary text only, recorded as a rule in the CSS comment); (d) `accent` as background with `#ffffff` text is at least 4.5.
- [ ] **Step 2:** Run `npx tsx --test packages/ui/src/v2/__tests__/tokens.test.ts`; expect FAIL (files missing).
- [ ] **Step 3:** Implement `contrast.ts` (WCAG relative luminance, sRGB) and `tokens.css` with an `@theme { ... }` block holding all tokens, the page background gradient as a `.pf-canvas` class, and a `@media (prefers-reduced-motion: reduce)` block that zeroes durations. If a pair in (c) fails, adjust only `fg-faint`/`fg-dim` lightness until it passes and note the final values in the spec table.
- [ ] **Step 4:** Run the test; expect PASS. Then run `cd apps/desktop && npx vite build` and confirm the built CSS contains `.bg-glass` and `.text-fg-dim` (grep `dist/assets/*.css`). If the legacy `@config` swallows `@theme` colours, move the colour entries into `tailwind.config.js` under `theme.extend.colors` and re-check.
- [ ] **Step 5:** Commit: `feat(ui): Midnight Glass tokens and contrast guard`.

### Task 3: Core primitives (no Radix)

**Files:**
- Create: `packages/ui/src/v2/cx.ts`, `primitives/Button.tsx`, `IconButton.tsx`, `Chip.tsx`, `GlassPanel.tsx`, `Progress.tsx`, `Skeleton.tsx`; update `index.ts` exports
- Test: `packages/ui/src/v2/__tests__/primitives.test.tsx`

**Interfaces (all `React.FC`, forward `className` and native props):**
- `cx(...parts: Array<string | false | null | undefined>): string`
- `Button({variant: "primary"|"secondary"|"ghost"|"danger", size?: "sm"|"md", loading?: boolean, icon?: ReactNode, children})`: primary is the only accent-filled style; `loading` sets `aria-busy` and disables.
- `IconButton({label: string, children})`: `label` becomes `aria-label` and is required.
- `Chip({tone?: "neutral"|"accent"|"ok"|"warn"|"bad", icon?: ReactNode, children})`
- `GlassPanel({as?: ElementType, blur?: boolean, children})`: `blur` default true adds backdrop blur; false uses the flat surface (workbenches).
- `Progress({value: number, label: string})`: `role="progressbar"`, `aria-valuenow` clamped 0-100. `Skeleton({className})`: `aria-hidden`.

- [ ] **Step 1: Write failing tests** using `renderToStaticMarkup`: primary Button markup contains `bg-accent`; secondary does not; `loading` renders `aria-busy="true"` and `disabled`; `IconButton` without `label` is a type error (`// @ts-expect-error` line) and with it renders `aria-label="Retry"`; `Progress value={140}` renders `aria-valuenow="100"` and `value={-5}` renders `0`; `GlassPanel blur={false}` markup lacks `backdrop-blur`.
- [ ] **Step 2:** Run `npx tsx --test packages/ui/src/v2/__tests__/primitives.test.tsx`; expect FAIL.
- [ ] **Step 3:** Implement with Tailwind classes built only from token names; every interactive element has a visible `focus-visible` ring using `ring-accent`.
- [ ] **Step 4:** Run the test; expect PASS. Run `cd apps/desktop && npx tsc --noEmit -p .`; expect exit 0.
- [ ] **Step 5:** Commit: `feat(ui): core v2 primitives`.

### Task 4: Content primitives

**Files:**
- Create: `primitives/ListRow.tsx`, `Tile.tsx`, `EmptyState.tsx`, `ErrorState.tsx`; update `index.ts`
- Modify: `__tests__/primitives.test.tsx` (append)

**Interfaces:**
- `ListRow({icon?: ReactNode, title: string, subtitle?: string, selected?: boolean, tone?: "neutral"|"ok"|"warn"|"bad"|"info", action?: ReactNode, onSelect?: () => void})`: renders a `button` when `onSelect` is set; `selected` uses the accent fill; tone shows a status dot AND the visually hidden word (`"Needs attention"`, `"Failed"`...) so status is not colour alone.
- `Tile({title: string, subtitle?: string, imageUrl?: string, fallbackText: string, onOpen?: () => void})`: shows `fallbackText` initials on a gradient when there is no `imageUrl` (the legacy cards use `TR`-style initials).
- `EmptyState({title: string, description?: string, action?: ReactNode})`; `ErrorState({title: string, description: string, onRetry?: () => void, onBack?: () => void})`: never shows raw exception text (callers pass a sentence).

- [ ] **Step 1: Write failing tests:** `ListRow tone="bad"` markup contains the text `Failed`; `selected` row has `bg-accent`; `Tile` without `imageUrl` renders the fallback text and no `<img`; `ErrorState` renders a Retry button only when `onRetry` is given; `EmptyState` renders its action.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS and `tsc` exit 0.
- [ ] **Step 5:** Commit: `feat(ui): list, tile, empty and error primitives`.

### Task 5: Accessible overlay and form primitives (Radix)

**Files:**
- Create: `primitives/Dialog.tsx`, `Drawer.tsx`, `Menu.tsx`, `Tabs.tsx`, `Tooltip.tsx`, `Switch.tsx`, `Toast.tsx`, `Field.tsx`; update `index.ts`
- Test: `__tests__/overlays.test.tsx`

**Interfaces:**
- `Dialog({open, onOpenChange, title: string, description?: string, children, footer?})`, `Drawer(same props, side?: "right"|"left")`: built on `@radix-ui/react-dialog`; `title` is required (Radix needs an accessible name).
- `Menu({trigger: ReactNode, items: Array<{label: string; onSelect: () => void; danger?: boolean}>})`; `Tabs({value, onValueChange, tabs: Array<{value: string; label: string}>, children})`; `Tooltip({content: string, children})`; `Switch({checked, onCheckedChange, label: string})`; `ToastProvider` + `useToast(): {show(message: string, tone?: "ok"|"warn"|"bad"): void}`; `Field({label: string, error?: string, hint?: string, children})` with `Input` and `Select` using the same tokens and associating label/error by id.

- [ ] **Step 1: Write failing tests** (static markup): closed `Dialog` renders nothing; open `Dialog` renders `role="dialog"` with the title as its accessible name; `Switch` renders `role="switch"` and `aria-checked`; `Field` with `error` links it via `aria-describedby` and sets `aria-invalid`.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement (z-index: at most two floating layers; dialog overlay uses a scrim, no blur). **Step 4:** Run; expect PASS and `tsc` exit 0.
- [ ] **Step 5:** Commit: `feat(ui): overlay and form primitives`.

### Task 6: Patterns

**Files:**
- Create: `patterns/Dock.tsx`, `Stepper.tsx`, `PageHeader.tsx`, `InboxRow.tsx`, `JobCard.tsx`, `EngineStatus.tsx`; update `index.ts`
- Test: `__tests__/patterns.test.tsx`

**Interfaces:**
- `Dock({items: Array<{id: string; label: string; icon: ReactNode; href: string}>, activeId: string})`: `nav aria-label="Main"`, active item has `aria-current="page"`; items are anchors (router links are passed by the shell through `renderLink?: (item, children) => ReactNode`).
- `Stepper({steps: Array<{id: string; label: string; status: "done"|"active"|"stale"|"blocked"|"upcoming"; href?: string}>})`: status text is rendered (visually hidden for icon-only steps).
- `PageHeader({title: string, meta?: ReactNode, actions?: ReactNode})`; `InboxRow = ListRow` specialised: `InboxRow({kind: "review"|"blocked"|"publish"|"failed", title, subtitle, actionLabel: string, onAction})`; `JobCard({title, detail, progress?: number, state: "running"|"queued"|"failed", onCancel?, onRetry?})`; `EngineStatus({connected: boolean, version?: string, gpu?: string})` showing text "Engine ready" / "Engine offline".

- [ ] **Step 1: Write failing tests:** `Dock` marks exactly one `aria-current="page"` for `activeId="jobs"`; `Stepper` renders the word `Stale` for a stale step; `EngineStatus connected={false}` renders `Engine offline`; `InboxRow kind="failed"` renders its `actionLabel` as a button.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit: `feat(ui): dock, stepper and inbox patterns`.

### Task 7: Component gallery and visual check

**Files:**
- Create: `apps/desktop/ui-gallery.html`, `apps/desktop/src/ui-gallery.tsx` (same pattern as the existing `preview-narration.html`)

- [ ] **Step 1:** Render every primitive and pattern in all states (default, hover-less static, selected, disabled, loading, error, empty) on the `pf-canvas` background; include a reduced-motion note.
- [ ] **Step 2:** Run the dev server, open `http://127.0.0.1:5173/ui-gallery.html` in the browser pane at 1440x900 and 1100x700, screenshot both, and read them. Check focus rings by tabbing through. Record any defects and fix them before continuing.
- [ ] **Step 3:** Commit: `feat(ui): v2 component gallery`.

### Task 8: No-raw-colours ratchet

**Files:**
- Create: `apps/desktop/src/__tests__/noRawColors.test.ts`, `apps/desktop/src/__tests__/legacyColorAllowlist.json`

- [ ] **Step 1: Write the test:** scan `packages/ui/src/v2/**/*.tsx`, `apps/desktop/src/app/**/*.tsx` and `apps/desktop/src/features/**/*.tsx` for `#[0-9a-fA-F]{3,8}\b` and palette utilities (`(bg|text|border|ring|from|to|via)-(indigo|purple|violet|blue|sky|emerald|amber|rose|cyan|fuchsia|teal|orange|zinc|slate|gray)-\d+`). Files listed in the allowlist are legacy and may contain them; any other offending file fails. Also fail when an allowlisted file no longer contains any (so the list only shrinks).
- [ ] **Step 2:** Generate the allowlist with the current offenders under `apps/desktop/src/screens`, `components`, `context`; run `npx tsx --test apps/desktop/src/__tests__/noRawColors.test.ts`; expect PASS. Add a throwaway file in `packages/ui/src/v2` with `bg-indigo-500`, confirm FAIL, then delete it.
- [ ] **Step 3:** Commit: `test(ui): ratchet against raw colours`.

### Task 9 (M1 close): API usage audit and uncovered-areas file

**Files:**
- Create: `scripts/audit-api-usage.mjs`, `docs/UI_V2_UNCOVERED.md`

- [ ] **Step 1:** Script parses method names of the `api` class in `packages/api-client/src/index.ts` with a TypeScript AST (`typescript` is installed) and reports methods with no reference in `apps/desktop/src` (excluding tests and mocks). Run `node scripts/audit-api-usage.mjs`; it prints the list and exits 0.
- [ ] **Step 2:** For each reported method, open the call sites' neighbours and classify: dead, superseded, or missing UI. Write `docs/UI_V2_UNCOVERED.md` with sections Missing UI, Superseded or dead, To decide, seeded from spec section 10 plus the real classification, plus one entry: `stageForProject` skips the Panels stage for `NORMALIZED`/`PANELS_DETECTED` (legacy behaviour kept in M2; confirm intent).
- [ ] **Step 3:** Commit: `docs(ui): uncovered areas and API usage audit`.

---

## Milestone 2: Shell and routing

### Task 10: Routes and stage mapping

**Files:**
- Create: `apps/desktop/src/app/routes.ts`
- Test: `apps/desktop/src/app/__tests__/routes.test.ts`

**Interfaces:**
- Produces: `type Stage = "acquire"|"pages"|"panels"|"ocr"|"story"|"script"|"audio"|"motion"|"render"|"publish"`; `STAGES: readonly Stage[]`; `isChronoFlowProject(p: Pick<Project,"source_type"|"settings">): boolean`; `stageForProject(p: Pick<Project,"current_stage"|"settings">): Stage`; `paths`: `home()`, `projects()`, `project(id)`, `stage(id, stage)`, `editor(id)`, `create(kind?: "new"|"stories"|"anime"|"chronoflow"|"image")`, `chronoflow({projectId?, jobId?})`, `jobs()`, `library(kind?)`, `settings(section?: "engine"|"models"|"providers"|"youtube"|"diagnostics")`; `nextStage(s: Stage): Stage | null` and `prevStage(s: Stage): Stage | null` over `STAGES` order.
- `stageForProject` reproduces the old `handleOpenProject` exactly: NEW, RIGHTS_APPROVED -> acquire; ACQUIRED -> pages; NORMALIZED, PANELS_DETECTED -> story when `settings.visual_storytelling` else ocr; OCR_COMPLETE, OCR_APPROVED -> story; STORY_ANALYZED, STORY_APPROVED -> script; SCRIPT_GENERATED, SCRIPT_APPROVED -> audio; VOICE_GENERATED, AUDIO_APPROVED, SHOT_PLAN_GENERATED -> motion; everything else -> render.

- [ ] **Step 1: Write failing tests:** one assertion per `PipelineStage` value above (18 values) with and without `visual_storytelling`; `isChronoFlowProject` true for `source_type "CHRONOFLOW_AI"` and for `settings.workflow_type "chronoflow"`, false otherwise; `paths.stage("a b","ocr")` returns `"/projects/a%20b/ocr"`; `nextStage("render")` is `"publish"`, `nextStage("publish")` is `null`, `prevStage("acquire")` is `null`.
- [ ] **Step 2:** Run `npx tsx --test apps/desktop/src/app/__tests__/routes.test.ts`; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit: `feat(app): route table and stage mapping`.

### Task 11: Engine monitor and providers

**Files:**
- Create: `apps/desktop/src/app/engineMonitor.ts`, `apps/desktop/src/app/providers.tsx`
- Test: `apps/desktop/src/app/__tests__/engineMonitor.test.ts`

**Interfaces:**
- `engineMonitor.ts` (pure, injectable): `connectWithRetry(deps: {health: () => Promise<{status: string; version: string}>; sleep: (ms: number) => Promise<void>; start?: () => Promise<void>}, attempts = 6, delayMs = 600): Promise<{status: string; version: string} | null>` and `restartAndWait(deps: {restart: () => Promise<{instance_id?: string}>; health: ...; sleep: ...}, attempts = 60, delayMs = 1000): Promise<{status: string; version: string}>` which throws `Error("Engine did not reconnect within 60 seconds. Check the engine log or run launch_panelflow again.")` on timeout. These port `handleRetryEngine` and `handleRestartEngine` from `App.tsx`.
- `providers.tsx`: `AppProviders({children})` (QueryClientProvider with `retry: 1`, `refetchOnWindowFocus: false`, plus `ErrorProvider` and `ToastProvider`); `EngineProvider` and `useEngine(): {connected: boolean; version: string; startupGrace: boolean; retrying: boolean; restarting: boolean; retry(): Promise<void>; restart(): Promise<void>}` reproducing the old polling (8000 ms connected, 1500 ms disconnected, 7000 ms startup grace, Tauri `start_engine_cmd` and token handling, `panelflow:token-invalid` listener).

- [ ] **Step 1: Write failing tests** with fake `sleep`: `connectWithRetry` returns the health on the 3rd attempt and calls `sleep` twice; returns `null` after 6 failures; `restartAndWait` resolves only when `instance_id` differs from the previous one, and throws the exact message above after 60 unchanged attempts.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement `engineMonitor.ts`, then `providers.tsx` using it. **Step 4:** Run; expect PASS and `tsc` exit 0.
- [ ] **Step 5:** Commit: `feat(app): engine monitor and providers`.

### Task 12: Command palette

**Files:**
- Create: `apps/desktop/src/app/CommandPalette.tsx`, `apps/desktop/src/app/commands.ts`
- Test: `apps/desktop/src/app/__tests__/commands.test.ts`

**Interfaces:**
- `type Command = {id: string; label: string; group: "Go to"|"Projects"|"Actions"|"Settings"; to?: string; run?: () => void; keywords?: string[]}`; `buildCommands(input: {projects: Array<Pick<Project,"id"|"title"|"current_stage"|"settings"|"source_type">>}): Command[]` returns Go to commands for Home, Projects, Create (new, stories, anime, ChronoFlow, image), Jobs, Library, Settings sections, plus one "Open <title>" per project targeting `paths.stage(id, stageForProject(p))` or `paths.chronoflow` for ChronoFlow projects; `CommandPalette({open, onOpenChange, commands, onSelect})` using `cmdk` inside the v2 `Dialog`; the shell binds Ctrl+K / Cmd+K.

- [ ] **Step 1: Write failing tests:** every `paths` destination has a command; a ChronoFlow project's command targets ChronoFlow; labels are sentence case and start with a verb ("Open anime review"); ids are unique.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit: `feat(app): command palette`.

### Task 13: Shell, hub embedding and legacy routes

**Files:**
- Create: `apps/desktop/src/app/AppShell.tsx`, `router.tsx`, `features/legacy/LegacyStageRoute.tsx`, `features/legacy/LegacyScreens.tsx` (wrappers for new project, stories, anime, ChronoFlow, image, editor, providers, engine health), `features/legacy/HubRoute.tsx`
- Modify: `apps/desktop/src/components/dashboard/DashboardShell.tsx` and `types.ts` (add `embedded?: boolean`: when true omit `DashboardHeader` and `AppNavigationRail` and use `h-full` instead of `h-screen w-screen`; no other behaviour changes)
- Test: `apps/desktop/src/app/__tests__/legacyRoutes.test.tsx`

**Interfaces:**
- `AppShell`: top bar (greeting, `EngineStatus`, palette trigger, `ErrorNotificationBell`), `Dock` with Home, Projects, Create, Jobs, Library, Settings, `<Outlet/>`, `ErrorAlertBanner`, `ErrorDetailsModal`, and the old connecting / engine-unavailable gates from `App.tsx` (shown instead of the outlet; the URL is untouched so the route survives reconnect). Dock hides on `/editor/*`. Active dock id derives from the path prefix.
- `LegacyStageRoute`: reads `:id` and `:stage`, loads the project with `useQuery(["project", id], () => api.getProject(id))`; unknown project -> `ErrorState` ("This project no longer exists", back to Projects); unknown stage segment -> `<Navigate>` to `paths.stage(id, stageForProject(project))`; ChronoFlow project -> `<Navigate>` to `paths.chronoflow({projectId: id})`; otherwise renders the same legacy screen the old `App.tsx` rendered for that stage with `PipelineNavbar` above it (`acquire` -> `AcquisitionScreen`, `pages` -> `PageReviewScreen`, `panels` -> `PanelReviewScreen`, `ocr`, `story`, `script`, `audio`, `motion`, `render`, `publish` -> `RenderScreen` for now). `onBack` maps through `prevStage`; every `onXApproved(updated)` / `onProceedToX(proj)` writes `updated` into the query cache and navigates with `nextStage`; `onOpenStoryEditor(proj)` navigates to `paths.editor(proj.id)`; `AutoPilotModal` opens from a single header button (the duplicate in the pipeline bar is removed).
- `router.tsx`: `createHashRouter` with `/` -> redirect `/home`; `/home`, `/projects` -> `HubRoute` (embedded `DashboardShell`, callbacks mapped to `paths`); `/projects/:id` -> redirect to the current stage; `/projects/:id/:stage`; `/editor/:id` (loads project, `StoryEditorScreen`); `/create` (a simple grid of the five studios using v2 `Tile`s), `/create/new`, `/create/stories`, `/create/anime`, `/create/chronoflow/*`, `/create/image` (needs a project: pick one via `?project=`); `/jobs` and `/library/*` -> `HubRoute` pointing at the existing dashboard for now (replaced in M3); `/settings/engine` -> `ProviderHealthModal` forced open (`onClose` navigates back); `/settings/providers` -> `ProviderManagementScreen`; `/settings`, `/settings/models|youtube|diagnostics` -> redirect to `/settings/engine`; `*` -> redirect `/home`.

- [ ] **Step 1: Write failing tests** with `createMemoryRouter` and mocked `api`: `/projects/nope/ocr` renders "This project no longer exists"; `/projects/p1/xyz` redirects to the project's current stage; a ChronoFlow project at `/projects/p1/ocr` redirects to `/create/chronoflow/p1`; `/does-not-exist` lands on `/home`; shell markup contains six dock items and exactly one `aria-current="page"`.
- [ ] **Step 2:** Run `npx tsx --test apps/desktop/src/app/__tests__/legacyRoutes.test.tsx`; expect FAIL.
- [ ] **Step 3:** Implement the files above; port the old inline JSX for each legacy screen without changing its props.
- [ ] **Step 4:** Run the test; expect PASS. Run `cd apps/desktop && npx tsc --noEmit -p .`; expect exit 0.
- [ ] **Step 5:** Commit: `feat(app): shell, router and legacy route wrappers`.

### Task 14: Switch the app over and remove the old shell

**Files:**
- Modify: `apps/desktop/src/App.tsx` (replace the 693-line component with `AppProviders` + `RouterProvider`), `apps/desktop/src/main.tsx` (unchanged bootstrap; imports remain)
- Delete: `apps/desktop/src/screens/ProjectsScreen.tsx`
- Modify: `apps/desktop/src/index.css` (remove `user-select: none` from `body`; keep it only on `.pf-drag` chrome elements)

- [ ] **Step 1:** Replace `App.tsx`; run `grep -rn "ProjectsScreen\|ScreenMode" apps/desktop/src` and confirm no references remain; delete `ProjectsScreen.tsx`.
- [ ] **Step 2:** Run `cd apps/desktop && npx tsc --noEmit -p .` (exit 0) and `npm test` from the root plus `npm run test:ui` (both exit 0; if a failure is in code this plan did not touch, say it is pre-existing and list it, do not hide it).
- [ ] **Step 3: Verify in the real app** against the live engine (start `npx vite --host 127.0.0.1` in `apps/desktop`): at 1440x900 open `#/home`, each dock destination, a real project's stage URL, the stage links in the bar, the Story Editor, Original Stories, Anime Review, ChronoFlow, `#/settings/engine`; press Browser back after each. Select and copy OCR text. Screenshot Home, an OCR stage and Settings. State plainly anything that did not work or was not opened.
- [ ] **Step 4:** Commit: `feat(app): switch to routed UI v2 shell`.

### Task 15: Playwright smoke test on system Chrome

**Files:**
- Create: `apps/desktop/playwright.config.ts`, `apps/desktop/e2e/shell.spec.ts`; Modify: `apps/desktop/package.json` (`"e2e": "playwright test"`)

- [ ] **Step 1:** Config: `use: {channel: "chrome", baseURL: "http://127.0.0.1:5173"}`, `webServer: {command: "npx vite --host 127.0.0.1", url: "http://127.0.0.1:5173", reuseExistingServer: true}`. Specs (skipped with a clear message when the engine health call fails): the dock shows six links and clicking each changes the hash; Browser back returns to the previous route; Ctrl+K opens the palette, typing "jobs" and Enter goes to `#/jobs`, Escape closes it and focus returns to the trigger; `#/projects/nope/ocr` shows "This project no longer exists".
- [ ] **Step 2:** Run `npm --workspace=@panelflow/desktop run e2e`; expect all pass (or skipped with the engine-offline message).
- [ ] **Step 3:** Commit: `test(app): shell smoke test`.
- [ ] **Step 4:** Update the spec status line to "M1 and M2 implemented", list what was verified and not verified, and commit with the spec: `docs(ui): mark M1-M2 done`. Then write the M3 plan (Home inbox, Projects, Jobs).
