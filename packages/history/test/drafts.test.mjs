import test from 'node:test';
import assert from 'node:assert/strict';

test('synchronous draft history supports bounded undo and redo without a UI framework', async () => {
  const { SnapshotHistory } = await import('../dist/index.js');
  assert.equal(typeof SnapshotHistory, 'function', 'Draft history is not implemented');
  const history = new SnapshotHistory({ limit: 2 });
  history.record({ x: 0 }, { x: 1 }); history.record({ x: 1 }, { x: 2 }); history.record({ x: 2 }, { x: 3 });
  assert.deepEqual(history.undo(), { x: 2 }); assert.deepEqual(history.undo(), { x: 1 }); assert.equal(history.undo(), null);
  assert.deepEqual(history.redo(), { x: 2 });
  history.record({ x: 2 }, { x: 2 }); assert.equal(history.getState().canRedo, true);
  history.record({ x: 2 }, { x: 9 }); assert.equal(history.getState().canRedo, false);
});

test('draft history captures one gesture baseline and isolates returned snapshots', async () => {
  const { SnapshotHistory } = await import('../dist/index.js');
  const h = new SnapshotHistory();
  const before = [{ x: 10, width: 200 }], after = [{ x: 25, width: 185 }];
  h.record(before, after); before[0].x = 900; after[0].width = 900;
  const restored = h.undo(); assert.deepEqual(restored, [{ x: 10, width: 200 }]); restored[0].x = 50;
  assert.deepEqual(h.redo(), [{ x: 25, width: 185 }]); assert.deepEqual(h.undo(), [{ x: 10, width: 200 }]);
  h.clear(); assert.equal(h.redo(), null);
});

test('draft history validates limits and supports application clone/equality strategies', async () => {
  const { SnapshotHistory } = await import('../dist/index.js');
  assert.throws(() => new SnapshotHistory({ limit: 0 }));
  const h = new SnapshotHistory({ clone: structuredClone, equals: (a, b) => a.at.getTime() === b.at.getTime() });
  h.record({ at: new Date(0) }, { at: new Date(1) });
  assert.equal(h.undo().at.getTime(), 0); assert.equal(h.redo().at.getTime(), 1);
});
