/** Optional Node-only strategy. Never imported by the browser entry point. */
import { mkdir, open, readFile, rename, unlink } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { join, resolve } from 'node:path';
import { HistoryError, historyError } from './errors.js';
import { cloneJson, nonempty } from './json.js';
import type { HistoryJournal, HistoryStorage } from './types.js';

const hasCode = (error: unknown, code: string) => typeof error === 'object' && error !== null && 'code' in error && error.code === code;

/**
 * Atomic journal replacement + cross-process writer exclusion on a local FS.
 * This stores history only, not application data. It is NOT a distributed lock
 * or an atomic transaction across a separate database and this journal.
 * A crashed writer leaves a .lock file: validate canonical state before manually
 * removing that exact lock. Never infer lock expiry from a timeout.
 */
export class FileHistoryStorage implements HistoryStorage {
  private readonly directory: string;
  constructor(directory: string) { nonempty(directory, 'History directory'); this.directory = resolve(directory); }

  private filename(scope: string): string {
    nonempty(scope, 'History scope');
    return join(this.directory, createHash('sha256').update(scope).digest('hex') + '.json');
  }

  async load(scope: string): Promise<unknown | null> {
    try {
      const journal: unknown = JSON.parse(await readFile(this.filename(scope), 'utf8'));
      if (journal === null) throw new HistoryError('PERSISTENCE', 'An existing null journal is corrupt');
      return journal;
    }
    catch (error) {
      if (hasCode(error, 'ENOENT')) return null;
      throw historyError(error, 'PERSISTENCE');
    }
  }

  async save(scope: string, journal: HistoryJournal, expectedRevision: number): Promise<void> {
    const data = cloneJson(journal);
    if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 0 || data.scope !== scope || data.revision !== expectedRevision + 1)
      throw new HistoryError('VALIDATION', 'Invalid journal scope or revision');
    const filename = this.filename(scope), lockname = filename + '.lock';
    await mkdir(this.directory, { recursive: true });
    let lock;
    try { lock = await open(lockname, 'wx', 0o600); }
    catch (error) {
      if (hasCode(error, 'EEXIST')) throw new HistoryError('CONFLICT', 'History is locked by another writer or interrupted operation');
      throw historyError(error, 'PERSISTENCE');
    }
    const temporary = filename + '.' + randomUUID() + '.tmp';
    try {
      const current = await this.load(scope) as HistoryJournal | null;
      if (current !== null && (!current || !Number.isSafeInteger(current.revision) || current.scope !== scope))
        throw new HistoryError('PERSISTENCE', 'Cannot overwrite a malformed journal');
      if ((current?.revision ?? 0) !== expectedRevision) throw new HistoryError('CONFLICT', 'History revision changed; reload canonical state');
      const file = await open(temporary, 'wx', 0o600);
      try { await file.writeFile(JSON.stringify(data), 'utf8'); await file.sync(); }
      finally { await file.close(); }
      await rename(temporary, filename);
    } finally {
      // Cleanup failure after rename must not misreport a committed write as failure.
      await unlink(temporary).catch(() => undefined);
      await lock.close().catch(() => undefined);
      await unlink(lockname).catch(() => undefined);
    }
  }
}
