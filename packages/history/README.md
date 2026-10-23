# @panelflow/history

A reusable TypeScript/ESM undo/redo toolkit with **zero production dependencies**. The core has no React, browser, Tauri, database or PanelFlow imports. Node filesystem support is an optional entry point.

This package implements Command, Memento, Composite, Strategy and Observer patterns. It does **not** automatically make every application API reversible. Each application supplies domain handlers and its transaction/recovery boundary.

## Build, test, package

```sh
npm install
npm test
npm pack
```

From the PanelFlow monorepo use `npm test --workspace @panelflow/history`. The tarball includes built JavaScript, declarations, source maps and examples. Install the tarball in another project with `npm install /path/to/panelflow-history-0.1.0.tgz`. The package is not published to a registry.

Requires modern browsers or Node 20+. ESM import is supported; CommonJS `require` is not a supported entry point. Applications without `crypto.randomUUID` can inject `idFactory`.

## Snapshot commands

```ts
import { CommandRegistry, HistoryManager, snapshotHandler } from '@panelflow/history';

type Document = { text: string };
const context = { document: { text: '' } };
const registry = new CommandRegistry<typeof context>().register(
  'document.replace', 1,
  snapshotHandler<typeof context, Document>({
    read: c => c.document,
    write: (c, value) => { c.document = value; },
    validateState: (value): value is Document =>
      !!value && typeof value === 'object' && 'text' in value && typeof value.text === 'string',
  }),
);
const history = await HistoryManager.open({ scope: 'document:42', context, registry });
await history.execute({
  type: 'document.replace', version: 1, label: 'Edit text', input: { text: 'Hello' },
});
await history.undo(); // text === ''
await history.redo(); // text === 'Hello'
```

`open()` loads history, **not domain state**; it never replays already-applied commands. Reload canonical application data before opening its corresponding history. See [examples/document.mjs](examples/document.mjs).

## Custom commands

Register a versioned handler with `prepare(input, context)`, `validate(payload)`, `apply(context, payload)` and `revert(context, payload)`.

- `prepare` and `validate` must be pure with respect to domain state. Return `null` from prepare for a no-op; redo remains available.
- Capture sufficient before/after data in the payload. Redo calls `apply` on that same data, not `prepare`, network generation, or a random operation again.
- Handlers must be atomic on rejection: either complete or leave state unchanged. If partial mutation or an unknown commit outcome is possible, throw `new HistoryError('RECOVERY_REQUIRED', message)`.
- JSON payloads only: finite numbers, plain objects, dense arrays, strings, booleans, null. Undefined, accessors, hidden fields, symbols, cycles, dates and classes are rejected by the durable manager. Store asset IDs/hashes, not binary files, tokens or credentials.
- Supply real domain validation for journals received from storage. The default snapshot validator only checks the before/after envelope; use `validateState` for your schema.

`executeBatch(requests, label)` prepares children sequentially against preceding results and records them as one action. Undo reverses child order. If a child rejects, completed children are compensated; compensation failure locks the manager. This is **not** a database transaction or a guarantee across process crashes.

## Storage, revisions and recovery

The default `MemoryHistoryStorage` retains history only in memory. Share **one storage instance and one manager per domain scope**. Managers sharing a storage instance are coordinated within one runtime; stale revisions fail before mutation. Separate adapter instances, runtimes, processes and remote clients require an application-level domain lock/revision transaction. Journal CAS alone cannot make arbitrary concurrent domain handlers safe.

A `HistoryStorage` implements `load(scope)` and atomic `save(scope, journal, expectedRevision)`. Save must compare-and-swap the revision and reject with `CONFLICT` on mismatch. An ordinary save rejection must mean **no write occurred**. Throw `RECOVERY_REQUIRED` for ambiguous outcomes; the manager does not blindly apply an inverse when the write may have committed.

For local Node tools:

```js
import { FileHistoryStorage } from '@panelflow/history/node';
const storage = new FileHistoryStorage('/trusted/dedicated/history');
// Pass storage to HistoryManager.open(...).
```

The Node adapter hashes scope names to filenames, uses an exclusive writer lock, fsyncs a temporary file, then renames it. An existing corrupt journal is not treated as missing. A crashed writer may leave a `.lock` file. Stop competing writers, inspect canonical domain state, and repair/quarantine the journal before removing that exact lock. There is no unsafe timeout-based lock stealing. Atomic rename assumes a local filesystem; network filesystems and power-loss/directory-entry durability are not guaranteed. See [examples/file-journal.mjs](examples/file-journal.mjs).

The file adapter durably stores the **journal only**. For database-backed apps, commit domain changes, journal and cursor in the same server-side transaction; stage filesystem assets with explicit crash recovery. Do not save a React snapshot to localStorage and call that atomic backend undo. A remote adapter should send an idempotent operation ID and expected revision to a server-owned command endpoint, not call a destructive API and independently save this journal.

Typed error codes: `VALIDATION`, `COMPATIBILITY`, `CAPACITY`, `CONFLICT`, `EXECUTION`, `PERSISTENCE`, `RECOVERY_REQUIRED`. Failed operations never advance the local cursor. Persistence failure compensates a known noncommitted operation. Conflict locks the stale manager; incomplete compensation locks recovery. A recovery marker is persisted best-effort, but cannot guarantee crash recovery when storage itself is unavailable.

Unknown command/schema versions fail closed. Keep the journal for diagnosis; do not overwrite it automatically. Reload and validate canonical state, then explicitly archive the incompatible journal and start a new baseline through your storage/application recovery UI. `clear()` discards undo/redo records but leaves current domain state untouched; it cannot dismiss a conflict or recovery lock.

Retention defaults to 100 actions and 8 MiB of serialized journal data. `maxEntries` and `maxBytes` are configurable. Old entries are pruned on new actions, not silently during load. Oversized actions fail before mutation. Existing journals exceeding a new lower limit fail to open rather than silently lose history. Metadata growth can reject an operation under a byte-exact legacy limit; increase the budget rather than drop recovery data. Storage adapters must separately manage asset retention; the core never deletes assets.

## Local drafts and UI binding

```ts
import { SnapshotHistory } from '@panelflow/history';
const draft = new SnapshotHistory<{ x: number }>({ limit: 100 });
draft.record({ x: 0 }, { x: 20 }); // once at gesture completion
const previous = draft.undo();   // { x: 0 }, or null at boundary
const next = draft.redo();       // { x: 20 }
```

`SnapshotHistory` is a synchronous caretaker for **uncommitted drafts**. Returned snapshots are isolated copies. Inject `clone`/`equals` for non-JSON local state (for example `structuredClone`); this does not make it durably serializable. Cancellation should restore the gesture baseline without recording an action. After committing the draft as one parent command, clear its child history. Do not use it to fake undo of saved API operations.

`HistoryManager.subscribe(listener)` returns unsubscribe; `getState()` returns a frozen stable snapshot suitable for `useSyncExternalStore`. React itself is not a dependency. Render availability/labels from state and handle the promises returned by undo/redo. Busy/conflicted/recovery scopes disable controls. Observers cannot fail a transaction. Never recursively await a command on the same manager from a handler: that would wait behind itself. Native text inputs should keep their native undo; focused child editors should consume shortcuts before project history.

## PanelFlow integration status

The portable framework and Setup selector **draft** integration are implemented. Durable project-wide backend restoration, retained assets and migration of all editor/API operations remain separate integration work; this package does not claim they are complete.
