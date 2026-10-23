# Reusable undo/redo framework and PanelFlow integration

Status: approved for implementation by the user's request to start on 2026-10-21. Implementation progress is tracked separately.

## Intent and scope

Build an independently distributable TypeScript library, provisionally `@panelflow/history`, usable by other browser, desktop, or Node applications without React, Tauri, Python, or PanelFlow imports. Integrate it into PanelFlow rather than adding another screen-local stack. TypeScript is the implementation choice because the existing interactive application uses it; this is not a cross-language runtime library. Python participates through an application-specific API adapter.

The user requested reusable architecture, suitable design patterns, and system-wide reversible editing. Proposed defaults below are engineering choices, not previously approved requirements.

## Patterns and boundaries

- Command: a typed, serializable description of an operation, not a serialized closure.
- Memento: immutable before/after state for state-oriented editing.
- Composite: multiple related changes appear as one action and undo in reverse order.
- Strategy/Adapter: applications supply execution, snapshot, persistence, and conflict policies.
- Observer: history state subscriptions, independent of a UI framework.

Do not introduce event sourcing as a replacement for the existing application database. A history journal is a recovery aid, not the authoritative project schema or a collaborative merge engine.

## Portable core contract

`HistoryManager` owns one explicitly named scope and exposes asynchronous `execute`, `undo`, `redo`, `clear`, `getState`, and `subscribe`. The application registers versioned command handlers by type. Each handler prepares a reversible record, applies it, reverts it, and optionally supplies a deterministic redo implementation. Records contain IDs, labels, scope, schema version, and validated domain payloads. Unknown handlers or versions fail closed on restoration.

Commands are queued serially per scope. Each method returns a promise that resolves only when the operation has committed. UI subscribers receive immutable state including busy, undo/redo labels, availability, and errors. Subscribers cannot corrupt the manager if a listener throws. Application code must not recursively await the same manager from inside a command handler.

Only successful meaningful edits enter history. No-ops preserve redo. A successful new edit after undo invalidates the redo branch. Failed execution, undo, or redo must not advance the cursor. Reject actions while a scope is in an indeterminate recovery state. Provide typed errors that distinguish validation, conflict, execution, persistence, and incomplete compensation failures.

Grouping is explicit: a pointer gesture is one operation from its starting snapshot to its final snapshot. Cancellation restores the starting value and produces no entry. Composite execution reverts successfully applied children in reverse order when a later child fails; compensation failure locks the scope and exposes recovery information rather than pretending the composite was atomic. In-memory compensation alone must never be described as a database transaction.

State/snapshot commands use an injected clone/equality strategy. The default supports JSON-compatible data. Document that mutable class instances, DOM objects, credentials, live handles, and binary assets require custom strategies or asset references. Do not store arbitrary executable functions in journals.

## Persistence and restart behavior

Proposed default: durable per-project history survives application restarts. Provide a storage port and an in-memory reference implementation in the portable core. Durable adapters must load, validate, append, checkpoint the cursor, truncate redo, and prune retained records. Versioned export/import supports portability of journals, not automatic portability of application assets.

Durability is a capability, not a claim that localStorage can atomically commit backend changes. The PanelFlow engine must own the durable commit for server-backed operations: domain changes and the journal/cursor update share a database transaction. Retained asset references must be committed consistently using staged files and a recovery manifest. On startup, unfinished file work is recovered before history is exposed. Network retries use operation IDs for idempotency.

Every project has an edit revision. Undo/redo checks the expected revision; concurrent external or background writes cause a visible conflict, not silent overwriting. Unsupported legacy writes invalidate the affected history scope explicitly until migrated. Do not use last-writer-wins for recovery.

Recovery policy (proposed engineering default): retain the failed journal for diagnosis, reload canonical project state, and offer an explicit "Start fresh history" action. Never automatically discard history to conceal an error. After successful reload and recovery validation, that action establishes a new baseline and unlocks editing; it does not apply a partial or conflicting inverse. Unsupported command versions on upgrade similarly quarantine the journal, leave project data untouched, and offer a fresh baseline. Version migrations are optional registered adapters, not an obligation to execute unknown commands. An incomplete filesystem recovery remains locked until validated or repaired; clearing history is not sufficient to dismiss actual storage inconsistency.

Default retention proposal: at most 100 actions per project, additionally constrained by a configurable byte budget. Assets referenced by retained undo or redo entries cannot be physically deleted. Pruning removes only history-owned assets no longer referenced by current project data or remaining entries. Project deletion uses recoverable trash; permanent purge remains explicitly irreversible. Preserve original source files.

## PanelFlow integration

Replace disconnected Story Editor/source, Panel Review, and Narration history stacks with project-level chronological history. Focused text inputs retain native text undo; local uncommitted selector drafts use a child history scope and take shortcut priority. Committing a draft creates one parent command, clears that draft scope, and does not double-record edits. Modal editors either commit a composite on acceptance or discard on cancellation.

Text commit policy (proposed engineering default): maintain a local input draft while focused; commit its before/after value on blur, explicit Save, or before executing a different project command, whichever occurs first. Flush pending drafts in deterministic focus order before that command enters the queue. Autosave may persist a separate recoverable draft, but must not create one project-history action per keystroke. Cancel discards the draft without entering project history. Native text undo stops owning the change once the input draft has committed.

PanelFlow-specific adapters cover:

| Area | Reversible content |
| --- | --- |
| Setup / Panel Review | selectors, geometry, split/merge, panel creation/deletion, order, confirmation, crop/image edits, associated metadata |
| Source pages | reorder, rotate, recoverable removal, linked panel and text records |
| Story Editor | scenes, layers, transforms, motion/keyframes, timing, narration/audio placement, track configuration, project editing settings |
| Narration / story | editable text, segmentation, speaker assignment, chapter/script edits, acceptance of generated results |

Revert must restore database records, stable identities and relationships, crop assets, renderer manifest, and relevant saved editor state together. It must also invalidate image caches and refetch canonical data. Restoring React arrays alone is not sufficient. Avoid persisting transient playback, hover, selection, viewport navigation, job progress, or credentials in project history. View preferences may use a separate optional UI history.

The mutation inventory is an explicit deliverable. Every frontend/API mutation is classified as reversible, UI-only, or irreversible with a reason. Do not advertise complete system coverage until every in-scope path has an adapter or an explicit boundary.

Generation/export/acquisition requests and job cancellation cannot be undone in the real world. Undo may remove an accepted generated result from the project while retaining its artifact for redo; redo reattaches the same result and never repeats paid or nondeterministic generation. Undo never deletes exported files outside the project. Provider credentials, external account actions, installation changes, and permanent purge are outside reversible project editing.

Running jobs capture input IDs and an input revision/hash. Completion never blindly updates a changed or deleted input: retain the result as stale/unapplied and offer explicit review, rather than autoattaching or rerunning it. Accepting a still-valid result is its own reversible command. A changed global revision alone need not reject unrelated results when the relevant input hashes still match. Background writers without this contract must block conflicting edit operations until migrated; they cannot bypass revision enforcement.

## Packaging and examples

Separate the framework's source, tests, build configuration, and README into its own workspace package with no production dependencies. Emit JavaScript and TypeScript declarations with an explicit export map and a packable npm artifact; do not publish to a registry without a user request. Include a plain TypeScript counter/document example, a snapshot adapter example, and a backend command adapter example. React binding, if useful, is a separate entry point with React as a peer dependency, never a dependency of the core.

## Implementation sequence

1. Build and test the portable command manager, snapshots, grouping, serialization, recovery states, storage contract, and examples.
2. Implement and test the engine journal/retained-assets transaction boundary, revision checks, idempotency, and startup recovery without touching live user projects.
3. Migrate Setup/Panel Review and Story Editor as one chronological project scope; remove legacy source-first ordering and frontend-only restoration.
4. Migrate narration, pages, and remaining editable domain operations from the mutation inventory. Add global toolbar availability and keyboard scope routing.
5. Verify restart recovery, pack the library, document integration and coverage, and produce a handoff. Keep the in-progress Setup space redesign intact.

## Acceptance evidence

Tests must demonstrate execute → undo → redo, chronological mixed-operation ordering, redo invalidation, no-op behavior, history bounds, queue ordering, failed operations, composite compensation and compensation failure, immutable snapshots, unknown schema/command rejection, listener isolation, scope isolation, idempotent retries, revision conflicts, and restoration after restart.

Backend integration tests use an isolated database and temporary workspace: delete/split/save/blur/rotate → undo → reload → redo → reload, with rows, relationships, manifests and image contents verified. Inject failures around DB/file/journal transitions and verify recovery. UI tests cover native text undo, modal/draft priority, Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z, Ctrl+Y, disabled/busy controls, and one gesture per action. Tests must prove real restoration, not only button callbacks or mocked stack sizes.

Run existing desktop and engine tests, TypeScript/build checks, npm pack smoke tests, and representative browser flows. Report pre-existing failures separately. Installed desktop binaries are not updated merely by a source build.

## Constraints and remaining builder decisions

The worktree contains substantial concurrent changes. Preserve all unrelated edits. Coordinate overlapping Story Editor/API-client/backend service ownership before migration; a pending task note is advisory, not permission to overwrite. Core package and new engine history modules can start independently.

Builder may choose concrete file layout, error class names, storage schema, hash algorithm, and test organization. The proposed durability, 100-action default, and irreversible-operation boundaries should be approved together with this design before product implementation.
