import type { CommandHandler, Json } from './types.js';
import { HistoryError } from './errors.js';
import { nonempty } from './json.js';

export class CommandRegistry<C> {
  private readonly handlers = new Map<string, CommandHandler<C>>();

  register<I extends Json, P extends Json>(type: string, version: number, handler: CommandHandler<C, I, P>): this {
    nonempty(type, 'Command type');
    if (!Number.isSafeInteger(version) || version < 1) throw new HistoryError('VALIDATION', 'Command version must be a positive integer');
    const key = JSON.stringify([type, version]);
    if (this.handlers.has(key)) throw new HistoryError('VALIDATION', `Handler already registered: ${type}@${version}`);
    // Registry erasure is guarded by prepare/validate at the manager boundary.
    this.handlers.set(key, handler as unknown as CommandHandler<C>);
    return this;
  }

  get(type: string, version: number): CommandHandler<C> {
    const handler = this.handlers.get(JSON.stringify([type, version]));
    if (!handler) throw new HistoryError('COMPATIBILITY', `No handler registered for ${type}@${version}`);
    return handler;
  }
}
