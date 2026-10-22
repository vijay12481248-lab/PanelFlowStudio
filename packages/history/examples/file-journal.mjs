import { CommandRegistry, HistoryManager, snapshotHandler } from '@panelflow/history';
import { FileHistoryStorage } from '@panelflow/history/node';

// Supply a dedicated, trusted directory; do not point at a project asset folder.
if (!process.argv[2]) throw Error('Usage: node file-journal.mjs <journal-directory>');
const storage = new FileHistoryStorage(process.argv[2]);
const scope = 'example:counter';
const journal = await storage.load(scope);
// This example owns its entire small document in snapshot payloads. Real apps
// reload canonical domain state independently, not by guessing from arbitrary commands.
const applied = journal?.entries?.[journal.cursor - 1];
const context = { value: applied?.kind === 'command' ? applied.payload.after : { count: 0 } };
const registry = new CommandRegistry().register('counter', 1, snapshotHandler({
  read: c => c.value, write: (c, value) => { c.value = value; },
  validateState: value => !!value && Number.isSafeInteger(value.count),
}));
const history = await HistoryManager.open({ scope, context, registry, storage });
await history.execute({ type: 'counter', version: 1, label: 'Increment', input: { count: context.value.count + 1 } });
console.log(context.value.count);
await history.undo(); console.log('Undo:', context.value.count);
await history.redo(); console.log('Redo:', context.value.count);
