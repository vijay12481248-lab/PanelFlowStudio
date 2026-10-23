import type { Awaitable, CommandHandler, Json } from './types.js';
import { cloneJson } from './json.js';

export type SnapshotPayload<S extends Json> = { before: S; after: S };

/** Memento strategy. write must either complete or leave the domain unchanged. */
export function snapshotHandler<C, S extends Json>(strategy: {
  read(context: C): Awaitable<S>;
  write(context: C, state: S): Awaitable<void>;
  validateState?(value: unknown): value is S;
  clone?(state: S): S;
  equals?(left: S, right: S): boolean;
}): CommandHandler<C, S, SnapshotPayload<S>> {
  const clone = strategy.clone ?? cloneJson;
  const equals = strategy.equals ?? ((a, b) => JSON.stringify(a) === JSON.stringify(b));
  const validState = strategy.validateState ?? ((_value: unknown): _value is S => true);
  return {
    validate(value): value is SnapshotPayload<S> {
      return typeof value === 'object' && value !== null && 'before' in value && 'after' in value &&
        validState(value.before) && validState(value.after);
    },
    async prepare(input, context) {
      const before = clone(await strategy.read(context)); const after = clone(input);
      if (!validState(before) || !validState(after)) throw new TypeError('Invalid snapshot state');
      return equals(before, after) ? null : { before, after };
    },
    apply: (context, payload) => strategy.write(context, clone(payload.after)),
    revert: (context, payload) => strategy.write(context, clone(payload.before)),
  };
}
