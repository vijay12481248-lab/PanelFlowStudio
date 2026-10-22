import { HistoryError, historyError } from './errors.js';
import { cloneJson, jsonBytes, nonempty } from './json.js';
import { CommandRegistry } from './registry.js';
import { MemoryHistoryStorage } from './storage.js';
import { coordinate } from './coordinator.js';
import type { CommandRecord, CommandRequest, HistoryEntry, HistoryJournal, HistoryState, HistoryStorage } from './types.js';

export interface HistoryOptions<C> {
  scope: string;
  context: C;
  registry: CommandRegistry<C>;
  storage?: HistoryStorage;
  maxEntries?: number;
  maxBytes?: number;
  idFactory?: () => string;
}

/** Serial command invoker. Domain handlers and storage provide atomicity. */
export class HistoryManager<C> {
  private journal: HistoryJournal;
  private readonly storage: HistoryStorage;
  private readonly maxEntries: number;
  private readonly maxBytes: number;
  private readonly listeners = new Set<() => void>();
  private tail: Promise<unknown> = Promise.resolve();
  private pending = 0;
  private recoveryRequired = false;
  private conflicted = false;
  private error: HistoryError | null = null;
  private state: HistoryState;
  private readonly options: Readonly<HistoryOptions<C>>;

  private constructor(options: HistoryOptions<C>) {
    this.options = Object.freeze({ ...options });
    nonempty(options.scope, 'History scope');
    this.maxEntries = options.maxEntries ?? 100;
    this.maxBytes = options.maxBytes ?? 8 * 1024 * 1024;
    for (const [name, value] of [['maxEntries', this.maxEntries], ['maxBytes', this.maxBytes]] as const)
      if (!Number.isSafeInteger(value) || value < 1) throw new HistoryError('VALIDATION', `${name} must be a positive integer`);
    this.storage = options.storage ?? new MemoryHistoryStorage();
    this.journal = { schemaVersion: 1, scope: options.scope, revision: 0, cursor: 0, entries: [] };
    this.state = this.makeState();
  }

  static async open<C>(options: HistoryOptions<C>): Promise<HistoryManager<C>> {
    const manager: HistoryManager<C> = new HistoryManager(options);
    const loaded = await manager.storage.load(options.scope);
    if (loaded !== null) {
      manager.validateJournal(loaded);
      manager.journal = cloneJson(loaded);
      manager.recoveryRequired = !!loaded.recoveryRequired;
    }
    manager.publish();
    return manager;
  }

  getState = (): HistoryState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  exportJournal(): HistoryJournal { return cloneJson(this.journal); }

  execute(request: CommandRequest): Promise<boolean> {
    // Copy immediately, before queued callers can mutate inputs.
    let copy: CommandRequest;
    try { copy = cloneJson(request); } catch (error) { return Promise.reject(error); }
    return this.enqueue(async () => {
      const entry = await this.prepare(copy);
      if (!entry) return false;
      const next = this.append(entry); // Capacity checks precede side effects.
      await this.transition(entry, 'apply');
      await this.commit(next, () => this.transition(entry, 'revert'));
      return true;
    });
  }

  executeBatch(requests: CommandRequest[], label: string): Promise<boolean> {
    let copies: CommandRequest[];
    try { copies = cloneJson(requests); nonempty(label, 'Batch label'); } catch (error) { return Promise.reject(error); }
    return this.enqueue(async () => {
      const children: CommandRecord[] = [];
      const id = this.newId();
      let next: HistoryJournal;
      try {
        for (const request of copies) {
          const child = await this.prepare(request);
          if (!child) continue;
          if (child.id === id || children.some(entry => entry.id === child.id)) throw new HistoryError('VALIDATION', 'Duplicate command ID');
          // Prepare each child against the result of preceding children.
          this.append({ kind: 'batch', id, label, children: [...children, child] });
          await this.transition(child, 'apply');
          children.push(child);
        }
        if (!children.length) return false;
        next = this.append({ kind: 'batch', id, label, children });
      } catch (error) {
        if (historyError(error, 'EXECUTION').code === 'RECOVERY_REQUIRED') throw error;
        try { await this.transition({ kind: 'batch', id, label, children }, 'revert'); }
        catch (rollback) { throw new HistoryError('RECOVERY_REQUIRED', 'Batch rollback failed', { cause: rollback }); }
        throw error;
      }
      const entry = { kind: 'batch' as const, id, label, children };
      await this.commit(next, () => this.transition(entry, 'revert'));
      return true;
    });
  }

  undo(): Promise<boolean> { return this.move(-1); }
  redo(): Promise<boolean> { return this.move(1); }

  clear(): Promise<void> {
    return this.enqueue(async () => {
      await this.commit({ ...this.journal, entries: [], cursor: 0, revision: this.journal.revision + 1 });
    });
  }

  private move(delta: -1 | 1): Promise<boolean> {
    return this.enqueue(async () => {
      const index = delta === -1 ? this.journal.cursor - 1 : this.journal.cursor;
      const entry = this.journal.entries[index];
      if (!entry) return false;
      const direction = delta === -1 ? 'revert' : 'apply';
      const next = { ...this.journal, cursor: this.journal.cursor + delta, revision: this.journal.revision + 1 };
      this.checkCapacity(next);
      await this.transition(entry, direction);
      await this.commit(next,
        () => this.transition(entry, direction === 'apply' ? 'revert' : 'apply'));
      return true;
    });
  }

  private async prepare(request: CommandRequest): Promise<CommandRecord | null> {
    nonempty(request.type, 'Command type'); nonempty(request.label, 'Command label');
    const id = request.id ?? this.newId(); nonempty(id, 'Command ID');
    if (this.ids().has(id)) throw new HistoryError('VALIDATION', `Duplicate command ID: ${id}`);
    const handler = this.options.registry.get(request.type, request.version);
    const payload = await handler.prepare(cloneJson(request.input), this.options.context);
    if (payload === null) return null;
    const isolated = cloneJson(payload);
    if (!handler.validate(isolated)) throw new HistoryError('VALIDATION', `Invalid payload for ${request.type}`);
    return { kind: 'command', id, type: request.type, version: request.version, label: request.label, payload: isolated };
  }

  private newId(): string {
    const id = this.options.idFactory?.() ?? globalThis.crypto.randomUUID(); nonempty(id, 'Generated command ID');
    if (this.ids().has(id)) throw new HistoryError('VALIDATION', 'ID factory returned a duplicate ID');
    return id;
  }

  private ids(): Set<string> {
    return new Set(this.journal.entries.flatMap(entry => entry.kind === 'batch' ? [entry.id, ...entry.children.map(child => child.id)] : [entry.id]));
  }

  private append(entry: HistoryEntry): HistoryJournal {
    const base = { ...this.journal, entries: [entry], cursor: 1, revision: this.journal.revision + 1 };
    this.checkCapacity(base);
    const entries = [...this.journal.entries.slice(0, this.journal.cursor), entry];
    while (entries.length > this.maxEntries || jsonBytes({ ...base, entries, cursor: entries.length }) > this.maxBytes) entries.shift();
    return { ...base, entries, cursor: entries.length };
  }

  private checkCapacity(journal: HistoryJournal): void {
    if (!Number.isSafeInteger(journal.revision)) throw new HistoryError('CAPACITY', 'History revision limit reached');
    if (jsonBytes(journal) > this.maxBytes) throw new HistoryError('CAPACITY', 'History metadata exceeds the byte budget');
  }

  private async transition(entry: HistoryEntry, direction: 'apply' | 'revert'): Promise<void> {
    if (entry.kind === 'command') {
      const handler = this.options.registry.get(entry.type, entry.version);
      await handler[direction](this.options.context, cloneJson(entry.payload));
      return;
    }
    const ordered = direction === 'apply' ? entry.children : [...entry.children].reverse();
    const completed: CommandRecord[] = [];
    try {
      for (const child of ordered) { await this.transition(child, direction); completed.push(child); }
    } catch (error) {
      if (historyError(error, 'EXECUTION').code === 'RECOVERY_REQUIRED') throw error;
      try {
        for (const child of completed.reverse()) await this.transition(child, direction === 'apply' ? 'revert' : 'apply');
      } catch (rollback) { throw new HistoryError('RECOVERY_REQUIRED', 'Composite compensation failed', { cause: rollback }); }
      throw error;
    }
  }

  private async commit(next: HistoryJournal, compensate?: () => Promise<void>): Promise<void> {
    this.checkCapacity(next);
    try { await this.storage.save(this.options.scope, cloneJson(next), this.journal.revision); }
    catch (error) {
      const failure = historyError(error, 'PERSISTENCE');
      // Unknown commit outcomes cannot safely be compensated: the server may have committed.
      if (failure.code === 'RECOVERY_REQUIRED') throw failure;
      try { await compensate?.(); }
      catch (rollback) { throw new HistoryError('RECOVERY_REQUIRED', 'Persistence failed and application rollback failed', { cause: rollback }); }
      throw failure;
    }
    this.journal = next;
  }

  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    this.pending++;
    const result = this.tail.then(() => coordinate(this.storage, this.options.scope, async () => {
      try {
        if (this.recoveryRequired) throw new HistoryError('RECOVERY_REQUIRED', 'Reload and validate canonical state before starting fresh history');
        if (this.conflicted) throw new HistoryError('CONFLICT', 'Reload canonical state and history before continuing');
        this.error = null;
        // Detect stale managers BEFORE prepare/apply, not only after mutation.
        const current = await this.storage.load(this.options.scope);
        if (current !== null) this.validateJournal(current);
        if ((current === null ? 0 : current.revision) !== this.journal.revision)
          throw new HistoryError('CONFLICT', 'History changed; reload canonical state before editing');
        return await operation();
      } catch (error) {
        const failure = historyError(error, 'EXECUTION'); this.error = failure;
        if (failure.code === 'CONFLICT') this.conflicted = true;
        if (failure.code === 'RECOVERY_REQUIRED') {
          this.recoveryRequired = true;
          // Best effort only. Durable domain adapters must own crash recovery atomically.
          const recovery = { ...this.journal, recoveryRequired: true, revision: this.journal.revision + 1 };
          try { await this.storage.save(this.options.scope, cloneJson(recovery), this.journal.revision); this.journal = recovery; } catch { /* Keep the local lock even when storage is unavailable. */ }
        }
        throw failure;
      } finally { this.pending--; this.publish(); }
    }));
    // Reserve queue order before observers may synchronously enqueue another command.
    this.tail = result.catch(() => undefined);
    this.publish();
    return result;
  }

  private makeState(): HistoryState {
    const { cursor, entries } = this.journal;
    const blocked = this.pending > 0 || this.recoveryRequired || this.conflicted;
    return Object.freeze({ scope: this.options.scope, revision: this.journal.revision, undoCount: cursor, redoCount: entries.length - cursor,
      undoLabel: entries[cursor - 1]?.label ?? null, redoLabel: entries[cursor]?.label ?? null,
      canUndo: !blocked && cursor > 0, canRedo: !blocked && cursor < entries.length, busy: this.pending > 0,
      recoveryRequired: this.recoveryRequired, conflicted: this.conflicted,
      error: this.error ? Object.freeze({ code: this.error.code, message: this.error.message }) : null });
  }

  private publish(): void {
    this.state = this.makeState();
    for (const listener of [...this.listeners]) { try { listener(); } catch { /* An observer cannot change transaction success. */ } }
  }

  private validateJournal(value: unknown): asserts value is HistoryJournal {
    const data = cloneJson(value) as HistoryJournal;
    if (!data || data.schemaVersion !== 1) throw new HistoryError('COMPATIBILITY', 'Unsupported history journal schema');
    if (data.scope !== this.options.scope || !Number.isSafeInteger(data.revision) || data.revision < 0 ||
      !Array.isArray(data.entries) || !Number.isSafeInteger(data.cursor) || data.cursor < 0 || data.cursor > data.entries.length ||
      (data.recoveryRequired !== undefined && typeof data.recoveryRequired !== 'boolean')) throw new HistoryError('VALIDATION', 'Invalid history journal');
    if (data.entries.length > this.maxEntries || jsonBytes(data) > this.maxBytes) throw new HistoryError('CAPACITY', 'Stored history exceeds configured limits');
    const ids = new Set<string>();
    const identity = (entry: HistoryEntry) => {
      nonempty(entry.id, 'Stored command ID'); nonempty(entry.label, 'Stored command label');
      if (ids.has(entry.id)) throw new HistoryError('VALIDATION', 'Duplicate stored command ID'); ids.add(entry.id);
    };
    const command = (entry: CommandRecord) => {
      if (!entry || entry.kind !== 'command') throw new HistoryError('VALIDATION', 'Invalid stored command');
      identity(entry); nonempty(entry.type, 'Stored command type');
      if (!Number.isSafeInteger(entry.version) || entry.version < 1) throw new HistoryError('VALIDATION', 'Invalid command version');
      if (!this.options.registry.get(entry.type, entry.version).validate(cloneJson(entry.payload))) throw new HistoryError('VALIDATION', 'Invalid stored command payload');
    };
    for (const entry of data.entries) {
      if (entry?.kind === 'batch') {
        identity(entry);
        if (!Array.isArray(entry.children) || !entry.children.length) throw new HistoryError('VALIDATION', 'Invalid stored batch');
        entry.children.forEach(command);
      } else command(entry as CommandRecord);
    }
  }
}
