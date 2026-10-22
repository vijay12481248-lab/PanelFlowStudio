import test from "node:test";
import assert from "node:assert/strict";
import { createDebouncedSaveQueue } from "../editorSaveQueue";
function deferred() { let resolve!: () => void; const promise = new Promise<void>((done) => { resolve = done; }); return { promise, resolve }; }
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("Saving resolves to Saved only after the actual save completes", async () => {
  const pending = deferred(); const statuses: string[] = [];
  const queue = createDebouncedSaveQueue(async () => pending.promise, { status: (s) => statuses.push(s), error: () => {} }, 1000);
  queue.schedule({ revision: 1 });
  const flush = queue.flush(); await tick();
  assert.deepEqual(statuses, ["unsaved", "saving"]);
  pending.resolve(); assert.equal(await flush, true);
  assert.equal(statuses.at(-1), "saved");
  queue.dispose();
});

test("rapid edits serialize writes and coalesce the latest pending snapshot", async () => {
  const pending = deferred(); const writes: number[] = []; const statuses: string[] = [];
  const queue = createDebouncedSaveQueue(async (snapshot: number) => { writes.push(snapshot); if (writes.length === 1) await pending.promise; }, { status: (s) => statuses.push(s), error: () => {} }, 1000);
  queue.schedule(1); const first = queue.flush(); await tick();
  queue.schedule(2); queue.schedule(3); const last = queue.flush();
  assert.deepEqual(writes, [1]); pending.resolve();
  assert.equal(await first, true); assert.equal(await last, true);
  assert.deepEqual(writes, [1, 3]); assert.equal(statuses.at(-1), "saved");
  queue.dispose();
});

test("failed saves are visible, retryable, and cannot navigate away as successful", async () => {
  let fail = true; const errors: (string | null)[] = [];
  const queue = createDebouncedSaveQueue(async () => { if (fail) throw new Error("private backend details"); }, { status: () => {}, error: (s) => errors.push(s) }, 1000);
  queue.schedule(1); assert.equal(await queue.flush(), false);
  assert.match(errors.at(-1)!, /Could not save/); assert.doesNotMatch(errors.at(-1)!, /private backend/);
  fail = false; assert.equal(await queue.flush(), true); assert.equal(errors.at(-1), null);
  queue.dispose();
});

test("disposal clears pending debounce and ignores callbacks from an old screen", async () => {
  const pending = deferred(); const statuses: string[] = [];
  const queue = createDebouncedSaveQueue(async () => pending.promise, { status: (s) => statuses.push(s), error: () => {} }, 1000);
  queue.schedule(1); const saving = queue.flush(); await tick(); queue.dispose();
  const before = statuses.length; pending.resolve(); await saving;
  assert.equal(statuses.length, before);
});

test("explicit recovery discard waits for the active save and never writes the queued stale draft", async () => {
  const pending = deferred(); const writes: number[] = [];
  const queue = createDebouncedSaveQueue(async (snapshot: number) => { writes.push(snapshot); await pending.promise; }, { status: () => {}, error: () => {} });
  queue.schedule(1); const saving = queue.flush(); await tick(); queue.schedule(2);
  const discarded = queue.discardPending(); pending.resolve(); await saving; await discarded;
  assert.deepEqual(writes, [1]); assert.equal(await queue.flush(), true);
  queue.dispose();
});
