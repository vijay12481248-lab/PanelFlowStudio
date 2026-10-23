import test from 'node:test';
import assert from 'node:assert/strict';

test('exports the independently usable command framework', async () => {
  const history = await import('../dist/index.js').catch(() => ({}));
  assert.equal(typeof history.HistoryManager?.open, 'function', 'HistoryManager.open is not implemented');
});

const api = () => import('../dist/index.js');
async function fixture(options = {}) {
  const { HistoryManager, CommandRegistry, MemoryHistoryStorage, snapshotHandler } = await api();
  const context = { value: { count: 0 }, writes: [] };
  const registry = new CommandRegistry().register('document', 1, snapshotHandler({
    read: c => c.value,
    write: (c, value) => { c.value = value; c.writes.push(value.count); },
  }));
  const storage = options.storage ?? new MemoryHistoryStorage();
  const manager = await HistoryManager.open({ scope: 'project:a', context, registry, storage, ...options });
  return { manager, context, registry, storage, HistoryManager };
}
const edit = (count, extra = {}) => ({ type: 'document', version: 1, label: `Count ${count}`, input: { count }, ...extra });

test('mixed commands retain chronological order and deterministic redo', async () => {
  const f = await fixture();
  f.registry.register('offset', 1, {
    validate: p => typeof p?.before === 'number' && typeof p?.after === 'number',
    prepare: (input, c) => ({ before: c.value.count, after: c.value.count + input }),
    apply: (c, p) => { c.value = { count: p.after }; },
    revert: (c, p) => { c.value = { count: p.before }; },
  });
  await f.manager.execute(edit(3));
  await f.manager.execute({ type: 'offset', version: 1, label: 'Offset', input: 5 });
  await f.manager.execute(edit(12));
  for (const count of [8, 3, 0]) { assert.equal(await f.manager.undo(), true); assert.equal(f.context.value.count, count); }
  assert.equal(await f.manager.undo(), false);
  for (const count of [3, 8, 12]) { await f.manager.redo(); assert.equal(f.context.value.count, count); }
  assert.equal(await f.manager.redo(), false);
});

test('no-op preserves redo; a new meaningful action removes it', async () => {
  const { manager, context } = await fixture();
  await manager.execute(edit(1)); await manager.execute(edit(2)); await manager.undo();
  assert.equal(await manager.execute(edit(1)), false);
  assert.equal(manager.getState().canRedo, true);
  await manager.execute(edit(9));
  assert.equal(manager.getState().canRedo, false);
  assert.equal(context.value.count, 9);
});

test('snapshot input, output and exported journal are isolated from caller mutation', async () => {
  const { manager, context } = await fixture();
  const request = edit(1);
  await manager.execute(request);
  request.input.count = 80;
  context.value.count = 99;
  const journal = manager.exportJournal(); journal.entries[0].payload.after.count = 70;
  await manager.undo(); await manager.redo();
  assert.equal(context.value.count, 1);
});

test('serializes overlapping execute/undo calls and publishes busy status', async () => {
  const { manager, context } = await fixture();
  const events = []; manager.subscribe(() => events.push(manager.getState().busy));
  const a = manager.execute(edit(1)); const b = manager.execute(edit(2)); const c = manager.undo();
  assert.equal(manager.getState().busy, true);
  await Promise.all([a, b, c]);
  assert.equal(context.value.count, 1);
  assert.deepEqual(context.writes, [1, 2, 1]);
  assert.equal(events.at(-1), false);
});

test('reloads cursor and redo records without replaying applied commands', async () => {
  const f = await fixture();
  await f.manager.execute(edit(2)); await f.manager.execute(edit(5)); await f.manager.undo();
  const reopened = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: f.storage });
  assert.deepEqual(f.context.writes, [2, 5, 2]);
  await reopened.redo(); assert.equal(f.context.value.count, 5);
  await reopened.undo(); assert.equal(f.context.value.count, 2);
});

test('bounds retained history without losing the earliest retained baseline', async () => {
  const { manager, context } = await fixture({ maxEntries: 2 });
  for (const n of [1, 2, 3]) await manager.execute(edit(n));
  await manager.undo(); await manager.undo();
  assert.equal(context.value.count, 1);
  assert.equal(await manager.undo(), false);
});

test('rejects an oversized action before applying it or destroying redo', async () => {
  const { manager, context } = await fixture({ maxBytes: 700 });
  await manager.execute(edit(1)); await manager.undo();
  await assert.rejects(manager.execute({ ...edit(2), input: { count: 2, text: 'x'.repeat(2000) } }), e => e.code === 'CAPACITY');
  assert.equal(context.value.count, 0);
  assert.equal(manager.getState().canRedo, true);
});

test('handler validation and execution failure leave history unchanged and queue usable', async () => {
  const f = await fixture();
  f.registry.register('fail', 1, { validate: () => true, prepare: () => ({}), apply: () => { throw Error('write rejected'); }, revert: () => {} });
  await assert.rejects(f.manager.execute({ type: 'fail', version: 1, label: 'Fail', input: {} }), /write rejected/);
  assert.equal(f.manager.getState().undoCount, 0);
  await f.manager.execute(edit(4)); assert.equal(f.context.value.count, 4);
});

test('failed undo or redo never advances cursor', async () => {
  const f = await fixture(); let failUndo = true, failRedo = false;
  f.registry.register('guarded', 1, {
    validate: () => true, prepare: () => ({}),
    apply: c => { if (failRedo) throw Error('apply denied'); c.value = { count: 7 }; },
    revert: c => { if (failUndo) throw Error('undo denied'); c.value = { count: 0 }; },
  });
  await f.manager.execute({ type: 'guarded', version: 1, label: 'Guarded', input: {} });
  await assert.rejects(f.manager.undo(), /undo denied/); assert.equal(f.manager.getState().undoCount, 1);
  failUndo = false; await f.manager.undo(); failRedo = true;
  await assert.rejects(f.manager.redo(), /apply denied/); assert.equal(f.manager.getState().redoCount, 1);
});

test('persistence failure compensates application state without committing history', async () => {
  const { MemoryHistoryStorage } = await api(); const base = new MemoryHistoryStorage(); let fail = true;
  const storage = { load: scope => base.load(scope), save: (...args) => { if (fail) throw Error('disk full'); return base.save(...args); } };
  const { manager, context } = await fixture({ storage });
  await assert.rejects(manager.execute(edit(3)), e => e.code === 'PERSISTENCE');
  assert.equal(context.value.count, 0); assert.equal(manager.getState().undoCount, 0);
  fail = false; await manager.execute(edit(2)); assert.equal(context.value.count, 2);
});

test('incomplete compensation locks the scope instead of accepting further edits', async () => {
  const f = await fixture({ storage: { load: async () => null, save: async () => { throw Error('disk full'); } } });
  f.registry.register('unrecoverable', 1, { validate: () => true, prepare: () => ({}), apply: () => {}, revert: () => { throw Error('restore failed'); } });
  await assert.rejects(f.manager.execute({ type: 'unrecoverable', version: 1, label: 'Unrecoverable', input: {} }), e => e.code === 'RECOVERY_REQUIRED');
  assert.equal(f.manager.getState().recoveryRequired, true);
  await assert.rejects(f.manager.execute(edit(4)), e => e.code === 'RECOVERY_REQUIRED');
  await assert.rejects(f.manager.clear(), e => e.code === 'RECOVERY_REQUIRED');
});

test('batch is one action, prepares sequential baselines, and reverses in reverse order', async () => {
  const { manager, context } = await fixture();
  await manager.executeBatch([edit(1), edit(2), edit(3)], 'Three changes');
  assert.equal(manager.getState().undoCount, 1);
  assert.equal(manager.getState().undoLabel, 'Three changes');
  await manager.undo(); assert.deepEqual(context.writes, [1, 2, 3, 2, 1, 0]);
  await manager.redo(); assert.equal(context.value.count, 3);
});

test('batch failure compensates earlier children and preserves redo branch', async () => {
  const f = await fixture();
  await f.manager.execute(edit(9)); await f.manager.undo();
  f.registry.register('fail', 1, { validate: () => true, prepare: () => ({}), apply: () => { throw Error('child failed'); }, revert: () => {} });
  await assert.rejects(f.manager.executeBatch([edit(2), { type: 'fail', version: 1, label: 'Fail', input: {} }], 'Batch'), /child failed/);
  assert.equal(f.context.value.count, 0); assert.equal(f.manager.getState().canRedo, true);
});

test('stale storage revision fails closed and compensates the losing writer', async () => {
  const f = await fixture();
  const otherContext = { value: { count: 0 }, writes: [] };
  const other = await f.HistoryManager.open({ scope: 'project:a', context: otherContext, registry: f.registry, storage: f.storage });
  await f.manager.execute(edit(1));
  await assert.rejects(other.execute(edit(2)), e => e.code === 'CONFLICT');
  assert.equal(otherContext.value.count, 0);
  assert.equal(other.getState().conflicted, true);
  await assert.rejects(other.execute(edit(3)), e => e.code === 'CONFLICT');
  assert.equal((await f.storage.load('project:a')).cursor, 1);
});

test('scope isolation prevents undoing another document', async () => {
  const f = await fixture(); const b = await fixture({ storage: f.storage, scope: 'project:b' });
  await f.manager.execute(edit(1)); await b.manager.execute(edit(7)); await b.manager.undo();
  assert.equal(f.context.value.count, 1); assert.equal(b.context.value.count, 0);
});

test('rejects malformed journals, unknown command versions and scope mismatch before any writes', async () => {
  const f = await fixture(); await f.manager.execute(edit(1));
  for (const mutate of [j => { j.schemaVersion = 99; }, j => { j.scope = 'other'; }, j => { j.cursor = -1; }, j => { j.entries[0].version = 99; }, j => { j.entries[0].payload = 'invalid'; }]) {
    const journal = f.manager.exportJournal(); mutate(journal);
    await assert.rejects(f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: { load: async () => journal, save: async () => assert.fail('must not write') } }));
  }
  assert.deepEqual(f.context.writes, [1]);
});

test('listener errors cannot fail commands; unsubscribe removes notifications', async () => {
  const { manager, context } = await fixture(); let calls = 0;
  manager.subscribe(() => { throw Error('view failed'); }); const unsubscribe = manager.subscribe(() => calls++);
  await manager.execute(edit(1)); assert.equal(context.value.count, 1);
  unsubscribe(); const before = calls; await manager.undo(); assert.equal(calls, before);
  assert.equal(Object.isFrozen(manager.getState()), true);
});

test('rejects invalid options, duplicate IDs and non-JSON data before mutation', async () => {
  await assert.rejects(fixture({ maxEntries: 0 })); await assert.rejects(fixture({ scope: '' }));
  const f = await fixture();
  await f.manager.execute(edit(1, { id: 'fixed' }));
  await assert.rejects(f.manager.execute(edit(2, { id: 'fixed' })), e => e.code === 'VALIDATION');
  const cycle = {}; cycle.self = cycle;
  for (const input of [{ count: NaN }, { count: undefined }, cycle, { count: new Date() }]) {
    await assert.rejects(f.manager.execute({ ...edit(2), input }), e => e.code === 'VALIDATION');
  }
  assert.equal(f.context.value.count, 1);
});

test('clear persists a fresh baseline, does not revert current domain state', async () => {
  const f = await fixture(); await f.manager.execute(edit(2)); await f.manager.clear();
  assert.equal(f.context.value.count, 2); assert.equal(f.manager.getState().undoCount, 0);
  const reopened = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: f.storage });
  assert.equal(reopened.getState().undoCount, 0);
});

test('a losing manager never compensates over a winning edit to shared application state', async () => {
  const f = await fixture();
  const other = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: f.storage });
  const results = await Promise.allSettled([f.manager.execute(edit(1)), other.execute(edit(2))]);
  assert.equal(results[0].status, 'fulfilled'); assert.equal(results[1].status, 'rejected');
  assert.equal(f.context.value.count, 1);
  assert.deepEqual(f.context.writes, [1], 'stale manager must fail before applying anything');
});

test('observer-issued commands cannot overtake the operation that notified them', async () => {
  const { manager, context } = await fixture(); let nested;
  let issued = false;
  manager.subscribe(() => { if (manager.getState().busy && !issued) { issued = true; nested = manager.execute(edit(2)); } });
  await manager.execute(edit(1)); await nested;
  assert.deepEqual(context.writes, [1, 2]); assert.equal(context.value.count, 2);
});

test('revision metadata growth never persists a journal that exceeds its reopening limit', async () => {
  const f = await fixture(); await f.manager.execute(edit(1));
  const journal = f.manager.exportJournal(); journal.revision = 9;
  const limit = new TextEncoder().encode(JSON.stringify(journal)).byteLength;
  let stored = journal;
  const manager = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, maxBytes: limit,
    storage: { load: () => structuredClone(stored), save: (_scope, next) => { stored = structuredClone(next); } } });
  await assert.rejects(manager.undo(), e => e.code === 'CAPACITY');
  assert.equal(stored.revision, 9); assert.equal(f.context.value.count, 1);
});

test('manager configuration is captured rather than redirected by caller mutation', async () => {
  const f = await fixture(); const options = { scope: 'new', context: f.context, registry: f.registry, storage: f.storage };
  const manager = await f.HistoryManager.open(options); options.scope = 'redirected';
  await manager.execute(edit(3));
  assert.equal((await f.storage.load('new')).scope, 'new'); assert.equal(await f.storage.load('redirected'), null);
});

test('lossless JSON rejects hidden array metadata', async () => {
  const { manager } = await fixture(); const array = [1]; Object.defineProperty(array, 'hidden', { value: 2 });
  await assert.rejects(manager.execute({ ...edit(1), input: array }), e => e.code === 'VALIDATION');
});

test('unknown storage commit outcome locks recovery without blindly applying an inverse', async () => {
  const { HistoryError } = await api();
  const f = await fixture({ storage: { load: () => null, save: () => { throw new HistoryError('RECOVERY_REQUIRED', 'connection lost after commit'); } } });
  await assert.rejects(f.manager.execute(edit(7)), e => e.code === 'RECOVERY_REQUIRED');
  assert.equal(f.context.value.count, 7); assert.deepEqual(f.context.writes, [7]);
  assert.equal(f.manager.getState().recoveryRequired, true);
});

test('failed composite undo restores the already-reverted children before rejecting', async () => {
  const f = await fixture(); let rejectUndo = false;
  f.registry.register('guard', 1, { validate: () => true, prepare: () => ({}), apply: () => {}, revert: () => { if (rejectUndo) throw Error('guard denied'); } });
  await f.manager.executeBatch([{ type: 'guard', version: 1, label: 'Guard', input: {} }, edit(8)], 'Protected edit');
  rejectUndo = true;
  await assert.rejects(f.manager.undo(), /guard denied/);
  assert.equal(f.context.value.count, 8); assert.equal(f.manager.getState().undoCount, 1);
});

test('a persisted recovery marker remains locked after reopening', async () => {
  const f = await fixture(); const { HistoryError } = await api();
  f.registry.register('uncertain', 1, { validate: () => true, prepare: () => ({}), apply: () => { throw new HistoryError('RECOVERY_REQUIRED', 'uncertain'); }, revert: () => {} });
  await assert.rejects(f.manager.execute({ type: 'uncertain', version: 1, label: 'Uncertain', input: {} }));
  const reopened = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: f.storage });
  assert.equal(reopened.getState().recoveryRequired, true);
  await assert.rejects(reopened.execute(edit(2)), e => e.code === 'RECOVERY_REQUIRED');
});

test('revision overflow rejects before touching the application', async () => {
  const f = await fixture(); const journal = f.manager.exportJournal(); journal.revision = Number.MAX_SAFE_INTEGER;
  const manager = await f.HistoryManager.open({ scope: 'project:a', context: f.context, registry: f.registry, storage: { load: () => journal, save: () => assert.fail('must not save') } });
  await assert.rejects(manager.execute(edit(1)), e => e.code === 'CAPACITY');
  assert.equal(f.context.value.count, 0); assert.deepEqual(f.context.writes, []);
});
