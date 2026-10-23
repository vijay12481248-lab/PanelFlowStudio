// Compiled as a real ES2020 consumer, separately from the library's own target.
import { CommandRegistry, HistoryManager, snapshotHandler, SnapshotHistory, type Json } from '@panelflow/history';
import { FileHistoryStorage } from '@panelflow/history/node';

type State = { text: string };
const context = { state: { text: '' } };
const registry = new CommandRegistry<typeof context>().register('replace', 1, snapshotHandler<typeof context, State>({
  read: c => c.state,
  write: (c, state) => { c.state = state; },
}));
const manager = await HistoryManager.open({ scope: 'consumer', context, registry });
await manager.execute({ type: 'replace', version: 1, label: 'Replace', input: { text: 'hello' } });
const serialized: Json = manager.exportJournal() as unknown as Json;
const draft = new SnapshotHistory<State>();
draft.record({ text: '' }, { text: 'hello' });
void serialized; void draft; void FileHistoryStorage;
