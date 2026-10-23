import type { HistoryJournal, HistoryStorage } from './types.js';
import { cloneJson } from './json.js';
import { HistoryError } from './errors.js';

/** Single-runtime reference storage, not cross-process durable storage. */
export class MemoryHistoryStorage implements HistoryStorage {
  private readonly journals = new Map<string, HistoryJournal>();

  load(scope: string): HistoryJournal | null {
    const journal = this.journals.get(scope);
    return journal ? cloneJson(journal) : null;
  }

  save(scope: string, journal: HistoryJournal, expectedRevision: number): void {
    if ((this.journals.get(scope)?.revision ?? 0) !== expectedRevision)
      throw new HistoryError('CONFLICT', 'History changed in another manager; reload canonical state');
    if (journal.scope !== scope || journal.revision !== expectedRevision + 1)
      throw new HistoryError('VALIDATION', 'Invalid journal scope or revision');
    this.journals.set(scope, cloneJson(journal));
  }
}
