import { HistoryError } from './errors.js';
import type { Json } from './types.js';

/** Reject lossy serialization, getters, class instances, cycles and unsafe depth. */
export function assertJson(value: unknown, ancestors = new Set<object>(), depth = 0): asserts value is Json {
  if (depth > 100) throw new HistoryError('VALIDATION', 'History data exceeds maximum nesting depth');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object' || value === null) throw new HistoryError('VALIDATION', 'History data must be lossless JSON');
  if (ancestors.has(value)) throw new HistoryError('VALIDATION', 'History data must not contain cycles');
  if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)
    throw new HistoryError('VALIDATION', 'History data must contain only plain objects and arrays');
  ancestors.add(value);
  try {
    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(i));
        if (!descriptor || !('value' in descriptor)) throw new HistoryError('VALIDATION', 'Sparse or accessor arrays are unsupported');
        assertJson(descriptor.value, ancestors, depth + 1);
      }
      if (Reflect.ownKeys(value).length !== value.length + 1) throw new HistoryError('VALIDATION', 'Array metadata is unsupported');
    } else {
      for (const key of Reflect.ownKeys(value)) {
        const descriptor = Object.getOwnPropertyDescriptor(value, key)!;
        if (typeof key !== 'string' || !descriptor.enumerable || !('value' in descriptor))
          throw new HistoryError('VALIDATION', 'History objects cannot contain accessors, symbols or hidden fields');
        assertJson(descriptor.value, ancestors, depth + 1);
      }
    }
  } finally { ancestors.delete(value); }
}

export function cloneJson<T>(value: T): T {
  assertJson(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

export function jsonBytes(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value)).byteLength;
}

export function nonempty(value: unknown, name: string): asserts value is string {
  if (typeof value !== 'string' || !value.trim()) throw new HistoryError('VALIDATION', `${name} must be a nonempty string`);
}
