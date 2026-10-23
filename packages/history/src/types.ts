export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Awaitable<T> = T | Promise<T>;

/** A handler must be atomic on rejection, or throw RECOVERY_REQUIRED. */
export interface CommandHandler<C, I extends Json = Json, P extends Json = Json> {
  prepare(input: I, context: C): Awaitable<P | null>;
  validate(payload: unknown): payload is P;
  apply(context: C, payload: P): Awaitable<void>;
  revert(context: C, payload: P): Awaitable<void>;
}

export interface CommandRequest<I extends Json = Json> {
  type: string;
  version: number;
  label: string;
  input: I;
  id?: string;
}

export interface CommandRecord {
  kind: 'command';
  id: string;
  type: string;
  version: number;
  label: string;
  payload: Json;
}
export interface BatchRecord {
  kind: 'batch';
  id: string;
  label: string;
  children: CommandRecord[];
}
export type HistoryEntry = CommandRecord | BatchRecord;
export interface HistoryJournal {
  schemaVersion: 1;
  scope: string;
  revision: number;
  cursor: number;
  entries: HistoryEntry[];
  /** Fail closed after a known incomplete rollback. */
  recoveryRequired?: boolean;
}

/**
 * save must atomically compare revision and replace the journal.
 * Rejection MUST mean no write occurred. Unknown commit outcomes must throw
 * HistoryError('RECOVERY_REQUIRED', ...), never an ordinary persistence error.
 */
export interface HistoryStorage {
  load(scope: string): Awaitable<unknown | null>;
  save(scope: string, journal: HistoryJournal, expectedRevision: number): Awaitable<void>;
}

export interface HistoryState {
  readonly scope: string;
  readonly revision: number;
  readonly undoCount: number;
  readonly redoCount: number;
  readonly undoLabel: string | null;
  readonly redoLabel: string | null;
  readonly canUndo: boolean;
  readonly canRedo: boolean;
  readonly busy: boolean;
  readonly recoveryRequired: boolean;
  readonly conflicted: boolean;
  readonly error: Readonly<{ code: string; message: string }> | null;
}
