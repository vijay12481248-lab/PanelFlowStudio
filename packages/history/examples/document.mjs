import { CommandRegistry, HistoryManager, snapshotHandler } from '@panelflow/history';

const document = { value: { title: 'Untitled', paragraphs: [] } };
const registry = new CommandRegistry().register('document.replace', 1, snapshotHandler({
  read: context => context.value,
  write: (context, value) => { context.value = value; },
  validateState: value => !!value && typeof value.title === 'string' && Array.isArray(value.paragraphs),
}));
const history = await HistoryManager.open({ scope: 'document:example', context: document, registry });
await history.execute({ type: 'document.replace', version: 1, label: 'Write title', input: { title: 'First chapter', paragraphs: [] } });
await history.undo();
console.log(document.value.title); // Untitled
await history.redo();
console.log(document.value.title); // First chapter
