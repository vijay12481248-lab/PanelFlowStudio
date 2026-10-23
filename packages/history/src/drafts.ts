import { HistoryError } from './errors.js';
import { cloneJson } from './json.js';

export interface SnapshotHistoryState {
  readonly canUndo: boolean;
  readonly canRedo: boolean;
  readonly undoCount: number;
  readonly redoCount: number;
}

/**
 * Synchronous Memento caretaker for UNCOMMITTED local drafts. It never writes
 * application state or storage. Commit a draft as one parent command when saved.
 */
export class SnapshotHistory<S> {
  private entries: Array<{ before: S; after: S }> = [];
  private cursor = 0;
  private readonly limit: number;
  private readonly clone: (state: S) => S;
  private readonly equals: (left: S, right: S) => boolean;

  constructor(options: { limit?: number; clone?: (state: S) => S; equals?: (left: S, right: S) => boolean } = {}) {
    this.limit = options.limit ?? 100;
    if (!Number.isSafeInteger(this.limit) || this.limit < 1) throw new HistoryError('VALIDATION', 'Draft limit must be a positive integer');
    const userClone = options.clone;
    this.clone = userClone ? (state: S) => userClone(state) : cloneJson;
    const userEquals = options.equals;
    this.equals = userEquals ? (left: S, right: S) => userEquals(left, right) : ((left, right) => JSON.stringify(left) === JSON.stringify(right));
  }

  record(before: S, after: S): boolean {
    if (this.equals(before, after)) return false;
    const entry = { before: this.clone(before), after: this.clone(after) };
    this.entries = [...this.entries.slice(0, this.cursor), entry].slice(-this.limit);
    this.cursor = this.entries.length;
    return true;
  }

  undo(): S | null {
    if (this.cursor === 0) return null;
    const result = this.clone(this.entries[this.cursor - 1]!.before);
    this.cursor--; return result;
  }

  redo(): S | null {
    if (this.cursor === this.entries.length) return null;
    const result = this.clone(this.entries[this.cursor]!.after);
    this.cursor++; return result;
  }

  clear(): void { this.entries = []; this.cursor = 0; }
  getState(): SnapshotHistoryState {
    return Object.freeze({ canUndo: this.cursor > 0, canRedo: this.cursor < this.entries.length,
      undoCount: this.cursor, redoCount: this.entries.length - this.cursor });
  }
}
