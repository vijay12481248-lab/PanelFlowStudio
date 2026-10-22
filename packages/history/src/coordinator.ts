import type { HistoryStorage } from './types.js';

// One shared storage instance coordinates all managers for a scope in this runtime.
// Cross-process/domain locking remains the application's transaction responsibility.
const queues = new WeakMap<HistoryStorage, Map<string, Promise<void>>>();

export async function coordinate<T>(storage: HistoryStorage, scope: string, operation: () => Promise<T>): Promise<T> {
  let scopes = queues.get(storage);
  if (!scopes) { scopes = new Map(); queues.set(storage, scopes); }
  const previous = scopes.get(scope) ?? Promise.resolve();
  let release!: () => void;
  const barrier = new Promise<void>(resolve => { release = resolve; });
  scopes.set(scope, barrier);
  await previous;
  try { return await operation(); }
  finally { release(); if (scopes.get(scope) === barrier) scopes.delete(scope); }
}
