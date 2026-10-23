# Reusable History Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. Checkboxes track verified deliverables, not intended behavior.

**Goal:** Deliver a portable history library and progressively replace PanelFlow's disconnected histories with genuine persistent restoration.

**Architecture:** Dependency-free TypeScript Command/Memento/Composite core. Storage, domain state, and server transactions are ports; PanelFlow-specific adapters stay outside the package.

**Tech Stack:** TypeScript, Node test runner, existing React/Python/SQLite application.

**Spec:** ../specs/2026-10-21-reusable-history-design.md

## Global constraints

- No React, database, engine, or PanelFlow imports in the core.
- Default retention 100 actions; configurable byte budget.
- Preserve existing uncommitted work. User explicitly chose current workspace.
- No publication, live project writes, installer changes, or paid generation.
- Document real coverage; do not claim system-wide completion before migration.

## Review focus

1. Persistence failure after application mutation must compensate or lock recovery.
2. Mixed command types undo in chronological order, including after reopening.
3. Unknown versions or corrupt journals cannot execute unvalidated payloads.
4. Overlapping calls and two managers sharing storage cannot silently overwrite history.
5. Native text editing must not trigger project history shortcuts.

## Task 1: Portable command library

Files: packages/history/src/{types,errors,json,storage,registry,manager,snapshot,index}.ts; packages/history/test/history.test.mjs; package.json; tsconfig.json.

Interfaces: HistoryManager.open(options), execute(request), executeBatch(requests,label), undo(), redo(), clear(), getState(), subscribe(listener). CommandRegistry.register(type, version, handler). HistoryStorage.load(scope), save(scope,journal,expectedRevision). Snapshot handler read/write strategies.

- [x] Write executable tests for missing exported manager, then ordering, redo invalidation/no-op, bounds, concurrency, compensation, immutable snapshots, reload, scope/version validation and listener isolation.
- [x] Run Node tests and observe missing implementation failure.
- [x] Implement registry, JSON validation, revisioned storage, serial command manager, Composite compensation, snapshot adapter.
- [x] Build declarations/JavaScript and run all package tests; 37 passed, including Node storage and draft cases added in subsequent tasks.

## Task 2: Reusable distribution and examples

Files: packages/history/README.md, examples/*.mjs, test/package.test.mjs.

- [x] Write failing consumer tests importing the built export, performing undo/redo and loading durable records in a separate Node process.
- [x] Add exports, npm scripts, standalone examples and contracts for atomic handlers/storage and indeterminate failures.
- [x] Run npm pack and execute the plain JS example with no application imports. Installed the real tarball in an independent temporary consumer; public core and Node exports, undo and redo passed with zero runtime dependencies.

## Task 3: Draft UI adapters

Files: apps/desktop/src/history/{draftHistory,shortcuts}.ts and tests; SourceSetupCanvas.tsx; NarrationStudio.tsx.

- [x] Add tests for immutable bounded snapshot history, redo invalidation, source-coordinate restoration and native-input shortcut exclusion.
- [x] Implement synchronous immutable draft history using the core snapshot journal reducer; migrate isolated draft stacks without falsely advertising backend restoration.
- [x] Verify existing selector/narration UI tests and desktop build.

## Task 4: Durable engine adapter and project migration

Files to resolve after mutation inventory: engine/history/*, engine API integration, API-client, shared project history provider, screens.

- [ ] Inventory all mutation routes and their file/DB/job side effects. Resolve concurrent backend ownership before editing overlapping service files.
- [ ] Add isolated DB/workspace failure-injection tests for revisioned journaling, retained assets, atomic restoration and restart recovery.
- [ ] Implement server-owned domain+journal commits and staged file recovery; legacy direct writes must invalidate/block conflicting history.
- [ ] Migrate persisted Setup/Panel Review/pages/editor/narration/script operations, with explicit irreversible boundaries and gesture/text commit semantics.
- [ ] Run full desktop/engine suites and real isolated reload/undo/redo scenarios; no completion claim without evidence.

## Progress / rulings

- User approved starting implementation and explicitly chose the current dirty workspace. Work in place; do not copy or reset other edits.
- Execute inline; the user's explicit start request takes precedence over another plan-approval round. No automatic commits in the shared dirty workspace.
- Task 4 is intentionally gated by the actual mutation inventory and safe restoration tests, not by frontend stack migration alone.
- Task 1 review: four Important findings reproduced RED and fixed GREEN: shared-context losing-writer rollback, subscriber queue reentrancy, byte-limit metadata growth, existing null journal corruption. Also fixed mutable manager configuration and hidden array metadata. Added regression coverage for unknown commit outcomes, composite undo compensation, recovery reload and revision overflow.
- Task 1 ruling: coordinate managers sharing one storage instance in this runtime, and preflight revisions before applying. Cross-process domain atomicity still belongs to the application's server transaction; a file journal CAS alone cannot protect arbitrary shared domain state. Cost if ignored: concurrent backend edits could be overwritten.
- Task 2 ruling: ship an optional Node-only file journal strategy and source in the tarball, without importing Node into the browser entry point. File journal durability is not a transaction with a separate DB. Power-loss/directory-entry durability is not claimed.
- Task 3 complete: Setup selector drafts and Narration Studio chapter drafts use `SnapshotHistory`; shared shortcut routing preserves native text undo. Narration restores mark the chapter unsaved so the parent durable Story Editor save callback records the edit. No claim that source-first parent history or saved panel APIs are fixed.
- Broad frontend run: 179 passed, 20 failed in existing SourceBrowser custom-dispatcher and StoryEditor missing-provider harnesses. Targeted backend run: 18 passed, four known inventory-sync failures. Desktop build succeeds. Do not merge/publish or call the whole application complete with these outstanding results.
- Review minors: hidden array metadata and mutable options fixed with RED→GREEN tests. Interrupted-writer/cleanup-failure fault injection remains deferred. Reviewer did not judge backend integration, package distribution, machine-crash durability or stale-lock reclamation; these boundaries are explicitly documented, with distribution additionally smoke-tested here.
