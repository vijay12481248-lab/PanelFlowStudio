# UI v2 Settings Implementation Plan (M4a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the engine/models/providers settings that are spread over a 2,614-line modal and a second provider screen with one Settings area: a section list (Engine, Models, Providers, YouTube, Diagnostics) and a detail pane, built from `@panelflow/ui-v2`.

**Architecture:** `/settings/*` becomes a layout route (`SettingsLayout`: section list plus `<Outlet/>`). Each section is a thin component over React Query hooks (`features/settings/settingsQueries.ts`) and pure helpers (`settingsModels.ts`) that hold the decisions (what changed, what is valid, how full a resource is). Forms keep a local draft, send only changed fields, and never display or store secrets.

**Tech Stack:** React 18, `@panelflow/ui-v2`, react-router 7, `@tanstack/react-query` 5, `tsx --test`, Playwright on installed Chrome. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-08-ui-v2-design.md` (sections 5, 6, 7 row M4). Builds on the M1 to M3 plans (done on `feat/ui-v2`). Open items: `docs/UI_V2_UNCOVERED.md`.

## Scope and one hard constraint

- **In M4a:** Engine, Models (Ollama), Providers (default provider, per-workflow routing, cloud/gateway config, provider list), Diagnostics, plus a YouTube section that shows status and opens the existing YouTube settings.
- **Deferred to M4b (YouTube):** the multi-channel YouTube settings now being built in the owner's **uncommitted** changes to `components/ProviderHealthModal.tsx`, `packages/api-client/src/index.ts` and the `engine/youtube/*` files. This plan must **not edit, move or delete** those files, and `git diff HEAD --stat` for them must be identical before and after every task. `ProviderHealthModal` also stays because `NarrationStudio` opens it. After the owner commits that work, M4b rebuilds the YouTube section on it.
- Settings that exist only in the old modal and have an engine endpoint but no UI today (`setConcurrencySettings`, `getAllAvailableLLMProviders`) are listed in `docs/UI_V2_UNCOVERED.md`, not wired unless a task below says so.

## Global Constraints

- Engine (`engine/`) is not changed; no new dependencies; semantic tokens only (the colour ratchet enforces it); sentence case, verb-first buttons, errors say what happened and what to do, empty states invite an action; status is never colour alone. Local-first: nothing here falls back to cloud silently, and a cloud provider is only used when the owner selects it.
- Secrets (Ollama auth token, cloud API key) are write-only: inputs are `type="password"` with `autoComplete="off"`; the UI shows only the engine's `has_auth_token` / `masked_api_key`; after a save the input is cleared; secrets never appear in query keys, query cache data, URLs, `localStorage`, console output or error text.
- Forms: local draft, a "Save changes" button that is disabled until something changed and while saving (guard with a ref so two fast clicks cannot submit twice), a "Discard" button, and only changed fields are sent. A failed save keeps the draft and says what failed.
- Test commands: `npm run test:ui`, `cd apps/desktop && npx tsc --noEmit -p .`, `cd apps/desktop && npx playwright test`; tests run with `--tsconfig apps/desktop/tsconfig.json`; page tests use `features/__tests__/pageHarness.tsx` (`mountPage`, `view.settle`, `view.press`, `view.clickTwice`, `view.setValue`).
- Commit only the files a task touches (explicit paths, never `git add -A` on a folder: the tree holds the owner's uncommitted work). Check each section in the real app at 1440x900 and 1100x700 against the live engine; do not press Save, Pull, Install or Restart on the owner's real settings in checks: verify forms only to the point of an enabled Save button, and say what was not exercised.

## Review Focus

1. A typed Ollama token or cloud API key is never visible after typing, is cleared after a successful save, and never appears in the DOM text, the React Query cache, the URL or storage. (Tasks 3, 4)
2. Engine or Ollama offline: each section shows an `ErrorState` with a next step (not a blank pane or a raw exception) and Save is not offered for data that did not load. (Tasks 2, 3, 4, 5)
3. A save sends only the changed fields, a failed save keeps the draft, and a fast double click saves once. (Tasks 3, 4)
4. A model pull shows progress, allows only one pull at a time, and stops polling when the page is left. (Task 3)
5. The owner's uncommitted files are untouched and the YouTube tab of the old modal is still reachable from Settings. (Tasks 1, 6, 7)

---

### Task 1: Settings layout and routes

**Files:**
- Create: `apps/desktop/src/features/settings/sections.ts`, `SettingsLayout.tsx`
- Modify: `apps/desktop/src/app/router.tsx`, `apps/desktop/src/app/routes.ts` (add `"models"` is already a `SettingsSection`; no change expected)
- Test: `apps/desktop/src/features/settings/__tests__/settingsLayout.test.tsx`

**Interfaces:**
- Produces: `SETTINGS_SECTIONS: ReadonlyArray<{ id: SettingsSection; label: string; description: string }>` in this order: engine "Engine" (health, tools, resources), models "Models" (local Ollama models), providers "Providers" (default provider and routing), youtube "YouTube" (channels and uploads), diagnostics "Diagnostics" (hardware and export); `SettingsLayout: React.FC` (nav `aria-label="Settings sections"` with links to `paths.settings(id)` marking the current one `aria-current="page"`, `<Outlet/>` beside it; at widths under 900 px the list stacks above the pane).
- Router: `settings` redirects to `/settings/engine` (unchanged); children `engine`, `models`, `providers`, `youtube`, `diagnostics` render a lazy `Component` each (temporary `SectionPlaceholder` until their tasks); `settings/*` still redirects to `/settings/engine`.

- [ ] **Step 1: Write failing tests:** the layout renders five links in the order above; at `/settings/providers` exactly that link has `aria-current="page"`; `matchRoutes(appRoutes, "/settings/models")` and `/settings/diagnostics` now match a child route that is not the redirect; `/settings/unknown` still redirects to `/settings/engine`.
- [ ] **Step 2:** Run `npx tsx --tsconfig apps/desktop/tsconfig.json --test apps/desktop/src/features/settings/__tests__/settingsLayout.test.tsx`; expect FAIL.
- [ ] **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): settings layout and routes`.

### Task 2: Settings data hooks and the Engine section

**Files:**
- Create: `apps/desktop/src/features/settings/settingsModels.ts` (first helpers), `settingsQueries.ts`, `EngineSection.tsx`
- Test: `apps/desktop/src/features/settings/__tests__/settingsModels.test.ts`, `engineSection.test.tsx`

**Interfaces:**
- Produces in `settingsModels.ts`: `type Gauge = { id: "gpu" | "ram"; label: string; usedLabel: string; percent: number; tone: "ok" | "warn" | "bad" }`; `resourceGauges(r: SystemResourcesResponse): Gauge[]` (GPU from `gpu.used_mb / total_mb` shown as GB with one decimal, RAM from `ram.total_gb` and `available_gb`; `percent` rounded, tone `warn` at 85 and above, `bad` at 95 and above; when `gpu.available` is false the GPU gauge is omitted); `type ToolRow = { id: string; label: string; state: "ready" | "missing" | "problem"; detail: string }`; `toolRows(input: { ffmpeg?: { found: boolean; version: string | null }; providers?: ProviderHealth[] }): ToolRow[]` (FFmpeg row "Found, version X" or "Not found"; one row per provider, `HEALTHY` and `READY` map to ready, `DEGRADED` to problem, every other status to missing, `detail` is the provider's status in words).
- Produces in `settingsQueries.ts`: `settingsKeys` (`providerHealth`, `ffmpeg`, `playwright`, `hardware`, `ollamaConfig`, `ollamaModels`, `globalLLM`, `cloudLLM`, `llmProviders` as `["settings", name]`), and read hooks `useProviderHealth()`, `useFfmpeg()`, `usePlaywrightStatus()`, `useHardware()`, `useOllamaConfig()`, `useOllamaModels()`, `useGlobalLLM()`, `useCloudLLM()`, `useLLMProviders()` over the matching `api` methods, all `enabled: useEngine().connected`, `retry: 1`, no polling except `usePlaywrightStatus` (2000 ms while its status is `running`), plus `useSettingsMutation<T>(fn, successMessage)` returning a mutation that toasts the message on success and calls `useError().reportError({ severity: "error", source: "engine", title: "Couldn't save the setting", message })` on failure.
- `EngineSection: React.FC`: engine version and status (`useEngine`), a Restart engine button (`useEngine().restart`), GPU and RAM gauges as `Progress` bars with their numbers as text, tool rows (FFmpeg, then each provider), a Playwright Chromium row with an Install button only when not installed (calls `api.installPlaywrightBrowsers`, shows the log tail from `usePlaywrightStatus` while running), a Default voices row with a Provision button (`api.provisionVoices`, shows "N voices copied"). Each read failing shows its own `ErrorState` row, not a blank section.

- [ ] **Step 1: Write failing tests:** `resourceGauges` rounds and sets tone at 84/85/94/95 percent and omits the GPU gauge when unavailable; `toolRows` maps statuses as above and handles undefined input as an empty list; `EngineSection` with stubbed `api` shows version, both gauges with `aria-valuenow`, FFmpeg "Found, version 6.1", and a provider row "Offline" for an `OFFLINE` provider; with `getProviderHealth` rejecting the section shows "Couldn't load tool status" and a Retry button while the other rows still render; Restart calls `useEngine().restart` once on a fast double click.
- [ ] **Step 2:** Run both files; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): Engine section`.

### Task 3: Models section (Ollama)

**Files:**
- Create: `apps/desktop/src/features/settings/ModelsSection.tsx`, `OllamaConnectionForm.tsx`, `ModelList.tsx`, `ModelPull.tsx`
- Modify: `settingsModels.ts`; Test: `settingsModels.test.ts` (append), `modelsSection.test.tsx`

**Interfaces:**
- Produces in `settingsModels.ts`: `type OllamaDraft = { endpoint_url: string; is_remote: boolean; vision_model: string; reasoning_model: string; narration_model: string; num_ctx: number; concurrency_mode: "AUTO" | "MANUAL"; max_gpu_concurrency: number; auth_token: string }`; `draftFromConfig(c: OllamaConfig): OllamaDraft` (`auth_token` empty); `changedOllamaFields(saved: OllamaConfig, draft: OllamaDraft): Partial<OllamaConfig> & { auth_token?: string }` (only fields that differ; `auth_token` only when non-empty); `validateEndpointUrl(value: string): string | null` (null when valid; messages: `"Enter the address of your Ollama server, for example http://127.0.0.1:11434."` for empty or unparsable, `"Use an http or https address."` for other protocols, `"Remove the username and password from the address and use the token field."` when the URL has credentials); `modelsForRole(models: OllamaModelCapability[], role: "vision" | "reasoning" | "narration"): OllamaModelCapability[]` (vision keeps `supports_vision`; the others drop models whose `capabilities` lack `"completion"` when that list is non-empty, else keep all); `pullPercent(s: { completed_bytes: number; total_bytes: number; percent?: number }): number` (0 to 100, uses bytes when `total_bytes > 0`).
- `ModelsSection`: connection form (endpoint, remote switch, token field with the note "Saved in the system keychain" when `has_auth_token`, never the value; Test connection button calling `api.testOllamaConnection` with the draft endpoint and showing Connected or the failure in words), role selects (vision, story reasoning, narration; options from `modelsForRole`, each showing parameter size and quantization), concurrency (mode select; max slots number input 1 to 8 enabled only for MANUAL), Save changes / Discard per Global Constraints calling `api.saveOllamaConfig(changedOllamaFields(...))`, then clearing `auth_token` in the draft and invalidating `settingsKeys.ollamaConfig`; `ModelList` (name, family, size, quantization, capability chips: Vision, Tools, Thinking) from `useOllamaModels()` with the engine's recommendations as a "Recommended" chip; `ModelPull` (input plus Pull model button calling `api.pullOllamaModel`; while status is not idle shows `Progress` from `pullPercent` and the status text, polls `api.getOllamaPullStatus` every 1500 ms only while mounted and active, disables the button while a pull runs).

- [ ] **Step 1: Write failing tests:** `changedOllamaFields` returns `{}` for an untouched draft, only `vision_model` when only that changed, and includes `auth_token` only when typed; `validateEndpointUrl` for `""`, `"ftp://x"`, `"http://user:pw@host"`, `"not a url"`, `"http://127.0.0.1:11434"`, `"https://ollama.example.com"`; `modelsForRole` vision filter; `pullPercent` from bytes and clamped; section test with stubbed `api`: Save is disabled until a role select changes, then enabled, and clicking it twice quickly calls `saveOllamaConfig` once with only the changed field; typing a token then saving clears the input and the token string appears nowhere in `document.body.innerHTML` nor in `JSON.stringify` of the query cache; a failed save keeps the draft and shows "Couldn't save the setting"; with `getOllamaConfig` rejecting the section shows an `ErrorState` ("Couldn't reach Ollama's settings") and no Save button; a running pull shows its percent and disables Pull model; unmounting during a pull stops the polling (no further `getOllamaPullStatus` calls after cleanup).
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): Models section`.

### Task 4: Providers section

**Files:**
- Create: `apps/desktop/src/features/settings/ProvidersSection.tsx`, `RoutingForm.tsx`, `CloudProviderForm.tsx`
- Modify: `settingsModels.ts`; Test: `settingsModels.test.ts` (append), `providersSection.test.tsx`

**Interfaces:**
- Produces in `settingsModels.ts`: `WORKFLOWS: ReadonlyArray<{ key: string; label: string }>` = `story_narration` "Story narration", `story_script` "Script writing", `character_analysis` "Character profiling", `vision_inspection` "Panel and OCR inspection"; `type RoutingDraft = { provider: string; model: string; overrides: Record<string, FlowOverrideConfig> }`; `routingFromSettings(s: GlobalLLMSettings): RoutingDraft`; `routingChanged(saved: GlobalLLMSettings, draft: RoutingDraft): boolean`; `routingToRequest(draft: RoutingDraft): SaveGlobalLLMSettingsRequest` (drops overrides whose `provider_id` is `"global"`); `providerOptions(s: GlobalLLMSettings, info: LLMProviderInfo[]): Array<{ id: string; name: string; local: boolean; ready: boolean }>` (union by id, `ready` is configured and healthy); `localFirstWarning(draft: RoutingDraft, options): string | null` (a sentence such as `"Cloud routing sends your text to OpenRouter. Keep Local Ollama as the default unless you mean to."` when the default or any override is a non-local provider, else null).
- `ProvidersSection`: provider list (name, Local/Cloud chip, Ready or Not ready as words) from `useLLMProviders()` and `useGlobalLLM()`; `RoutingForm` (default provider select, default model input, one row per workflow with a provider select including "Use the default" and an optional model input; shows `localFirstWarning` as a visible note; Save changes / Discard; saves with `api.saveGlobalLLMSettings(routingToRequest(draft))`); `CloudProviderForm` (provider type select, endpoint, model, API key password field with `masked_api_key` shown as the placeholder, Test connection via `api.testCloudLLMConnection` showing success or failure in words, Save via `api.saveCloudLLMConfig` sending `api_key` only when typed; same secret rules).

- [ ] **Step 1: Write failing tests:** `routingToRequest` omits "global" overrides and keeps real ones; `routingChanged` false for an untouched draft and true after one override changes; `providerOptions` merges and marks readiness; `localFirstWarning` is null for Ollama only and a sentence naming the provider for an OpenRouter override; section tests: workflow rows render in `WORKFLOWS` order, choosing a cloud provider shows the warning, Save is disabled until a change and saves once on a double click, the cloud API key never appears in the DOM or cache after saving and the field is cleared, `getGlobalLLMSettings` rejecting shows an `ErrorState` and no Save.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): Providers section`.

### Task 5: Diagnostics section

**Files:**
- Create: `apps/desktop/src/features/settings/DiagnosticsSection.tsx`
- Modify: `settingsModels.ts`; Test: `settingsModels.test.ts` (append), `diagnosticsSection.test.tsx`

**Interfaces:**
- Produces in `settingsModels.ts`: `hardwareRows(h: HardwareDiagnostics): Array<{ label: string; value: string }>` (OS and release, CPU cores, RAM available of total in GB, disk free of total in GB, GPU name and VRAM in GB, CUDA yes/no, FFmpeg yes/no with hardware accelerators joined by comma, performance tier in words: GOOD "Good", SUPPORTED "Supported", LIMITED "Limited", UNSUPPORTED "Not supported"); `diagnosticsFilename(d: { generated_at: string }): string` (`"panelflow-diagnostics-2026-11-08T12-00-00Z.json"`: colons and fractions removed).
- `DiagnosticsSection`: hardware rows from `useHardware()`; "Export diagnostics" calls `api.exportDiagnostics()` and offers the sanitized JSON as a download through a `Blob` anchor named by `diagnosticsFilename`, with a visible sentence "This file has paths and secrets removed. Review it before you share it."; a Copy button copying the same JSON with a "Copied" confirmation; the concurrency benchmark (`api.runConcurrencyBenchmark`) is not added here (it stays in Models as a follow-up noted in the uncovered file).

- [ ] **Step 1: Write failing tests:** `hardwareRows` values for a fixture (`total_ram_gb 31.9`, `available_ram_gb 18.2` gives "18.2 of 31.9 GB free"), tier words, CUDA yes/no; `diagnosticsFilename` for `"2026-11-08T12:00:00.123Z"`; section test: rows render; Export calls `api.exportDiagnostics` once and creates a download whose text parses as JSON (stub `URL.createObjectURL` and the anchor click); the sanitised-file sentence is shown; with `getHardwareDiagnostics` rejecting an `ErrorState` shows and Export is still offered.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): Diagnostics section`.

### Task 6: YouTube section (status only) and the legacy window

**Files:**
- Create: `apps/desktop/src/features/settings/YouTubeSection.tsx`
- Test: `apps/desktop/src/features/settings/__tests__/youtubeSection.test.tsx`

**Interfaces:**
- `YouTubeSection: React.FC`: reads `api.youtubeStatus()` through a local `useQuery` (key `["settings","youtube"]`, no `channelId` argument so it works against HEAD's client and the owner's in-progress one); shows "Connected", "Not connected" or "Not set up" in words with the engine's `error` text when present; a primary button "Open YouTube settings" that opens the existing `ProviderHealthModal` (imported unchanged, `open` state local, closes with `onClose`), and a sentence: "Channel setup and uploads live here until the new YouTube settings are ready." Uploads stay private by default and nothing here publishes or schedules.
- The modal opens on its default tab; the section's note names the YouTube tab so the owner can click it (passing `initialTab="youtube"` is deliberately avoided because that literal exists only in the uncommitted version of the modal).

- [ ] **Step 1: Write failing tests:** status words for the three states (stub `youtubeStatus`); the error text is shown when present; pressing Open YouTube settings shows the modal (stub the modal module with a small marker component through a dependency-injected `Modal` prop defaulting to the real `ProviderHealthModal`); `youtubeStatus` rejecting shows an `ErrorState` and the Open button is still available.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement (the section takes an optional `ModalComponent` prop for tests). **Step 4:** Run; expect PASS; `tsc` exit 0. **Step 5:** Commit: `feat(settings): YouTube section opens the existing YouTube settings`.

### Task 7: Wire the routes and retire the duplicates

**Files:**
- Modify: `apps/desktop/src/app/router.tsx`, `apps/desktop/src/features/legacy/LegacyScreens.tsx` (remove `EngineSettingsRoute` and `ProvidersRoute`), `apps/desktop/src/app/commands.ts` only if a label changes, `apps/desktop/src/__tests__/legacyColorAllowlist.json` (regenerate), `docs/UI_V2_UNCOVERED.md`
- Delete: `apps/desktop/src/components/ai-gateway/` (screen and its two tests)

- [ ] **Step 1:** `grep -rn "ai-gateway\|ProviderManagementScreen\|EngineSettingsRoute\|ProvidersRoute\|state: { open: true }" apps/desktop/src` and list every hit; `ProviderHealthModal` must keep at least its `NarrationStudio` and `YouTubeSection` users.
- [ ] **Step 2: Write a failing route test** (append to `legacyRoutes.test.tsx`): `/settings/engine`, `/settings/models`, `/settings/providers`, `/settings/youtube`, `/settings/diagnostics` each resolve their section component, and none resolves a legacy route component; legacy buttons that navigated to `/settings/engine` with `{ state: { open: true } }` (none remain after the dashboard was deleted; confirm by grep) need no change.
- [ ] **Step 3:** Point the five child routes at the real sections, delete the placeholders, the two legacy route components and the `ai-gateway` folder; regenerate the colour allowlist and confirm the diff only removes deleted files.
- [ ] **Step 4:** Run `npm run test:ui`, `npm test`, `npx tsc --noEmit -p .`; all exit 0. **Step 5:** In `UI_V2_UNCOVERED.md` mark the duplicate provider screens fixed, list `setConcurrencySettings`, `getAllAvailableLLMProviders` and the concurrency benchmark as still unwired, and add "YouTube multi-channel settings wait for the owner's uncommitted work (M4b)". Commit with explicit paths: `refactor(settings): route Settings sections and remove the duplicate provider screens`.
- [ ] **Step 6:** `git diff HEAD --stat -- apps/desktop/src/components/ProviderHealthModal.tsx packages/api-client/src/index.ts` is byte-for-byte the same as before Task 1 (record both outputs in the ledger).

### Task 8: Verify and close M4a

**Files:**
- Create: `apps/desktop/e2e/settings.spec.ts`; Modify: spec status line in `docs/superpowers/specs/2026-11-08-ui-v2-design.md`

- [ ] **Step 1: Playwright (engine required, skipped otherwise; read and navigate only, never Save, Pull, Install, Restart or Export):** the Settings list has five links and each changes the route; Engine shows a GPU gauge or a no-GPU note and a tool list; Models shows the connection form with a password-type token field whose value is empty, and a `Save changes` button that is disabled; Providers shows the four workflows; typing in a Models role select enables Save and Discard returns it to disabled; `main` never scrolls sideways at 1440 and 1100 px on each section; one `h1` per section. Run `npx playwright test`; expect all pass.
- [ ] **Step 2: Real app at 1440x900 and 1100x700:** open each section, screenshot, read; check no console errors and no secret-looking text in the DOM (`document.body.innerText` has no `sk-`, `Bearer ` or `gsk_`); confirm the YouTube section opens the old window and its YouTube tab is reachable. State what was not exercised (saves, pulls, installs, restart, export on real settings).
- [ ] **Step 3:** Update the spec status to "M1 to M4a implemented (YouTube settings M4b waits for the owner's commit)" with what was verified and not; commit `docs(ui): M4a done`.
- [ ] **Step 4:** Do not write the M4b or M5 plan in this task; report and ask.
