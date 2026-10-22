import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

test('file adapter restores history across independent Node processes', async () => {
  const { FileHistoryStorage } = await import('../dist/node.js').catch(() => ({}));
  assert.equal(typeof FileHistoryStorage, 'function', 'Durable file adapter is not implemented');
  const directory = await mkdtemp(join(tmpdir(), 'portable-history-'));
  const storage = new FileHistoryStorage(directory);
  const journal = { schemaVersion: 1, scope: 'document', revision: 1, cursor: 0, entries: [] };
  await storage.save('document', journal, 0);
  const program = `import {FileHistoryStorage} from ${JSON.stringify(new URL('../dist/node.js', import.meta.url).href)}; const s=new FileHistoryStorage(${JSON.stringify(directory)}); process.stdout.write(JSON.stringify(await s.load('document')));`;
  const child = spawnSync(process.execPath, ['--input-type=module', '-e', program], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr); assert.deepEqual(JSON.parse(child.stdout), journal);
  await assert.rejects(storage.save('document', journal, 0), e => e.code === 'CONFLICT');
  assert.equal((await storage.load('document')).revision, 1);
});

test('file storage isolates unsafe-looking scope strings and detects corrupt data', async () => {
  const { FileHistoryStorage } = await import('../dist/node.js');
  const directory = await mkdtemp(join(tmpdir(), 'portable-history-'));
  const storage = new FileHistoryStorage(directory);
  const scope = '../../outside';
  await storage.save(scope, { schemaVersion: 1, scope, revision: 1, cursor: 0, entries: [] }, 0);
  const files = await readdir(directory);
  assert.equal(files.length, 1); assert.match(files[0], /^[a-f0-9]{64}\.json$/);
  const filename = createHash('sha256').update(scope).digest('hex') + '.json';
  await writeFile(join(directory, filename), '{broken');
  await assert.rejects(storage.load(scope), e => e.code === 'PERSISTENCE');
});

test('overlapping file writers cannot both commit the same revision', async () => {
  const { FileHistoryStorage } = await import('../dist/node.js');
  const directory = await mkdtemp(join(tmpdir(), 'portable-history-'));
  const a = new FileHistoryStorage(directory), b = new FileHistoryStorage(directory);
  const journal = { schemaVersion: 1, scope: 'same', revision: 1, cursor: 0, entries: [] };
  const results = await Promise.allSettled([a.save('same', journal, 0), b.save('same', journal, 0)]);
  assert.equal(results.filter(x => x.status === 'fulfilled').length, 1);
  assert.equal(results.find(x => x.status === 'rejected').reason.code, 'CONFLICT');
});

test('an existing null journal is corruption, not an absent history', async () => {
  const { FileHistoryStorage } = await import('../dist/node.js');
  const directory = await mkdtemp(join(tmpdir(), 'portable-history-'));
  const filename = createHash('sha256').update('null').digest('hex') + '.json';
  await writeFile(join(directory, filename), 'null');
  await assert.rejects(new FileHistoryStorage(directory).load('null'), e => e.code === 'PERSISTENCE');
});

test('a fresh process can undo and redo the actual persisted snapshot command', async () => {
  const { FileHistoryStorage } = await import('../dist/node.js');
  const { HistoryManager, CommandRegistry, snapshotHandler } = await import('../dist/index.js');
  const directory = await mkdtemp(join(tmpdir(), 'portable-history-'));
  const storage = new FileHistoryStorage(directory);
  const context = { value: { count: 4 } };
  const registry = new CommandRegistry().register('count', 1, snapshotHandler({ read: c => c.value, write: (c, value) => { c.value = value; } }));
  const manager = await HistoryManager.open({ scope: 'count', context, registry, storage });
  await manager.execute({ type: 'count', version: 1, label: 'Count', input: { count: 10 } });
  const program = `
    import {HistoryManager,CommandRegistry,snapshotHandler} from ${JSON.stringify(new URL('../dist/index.js', import.meta.url).href)};
    import {FileHistoryStorage} from ${JSON.stringify(new URL('../dist/node.js', import.meta.url).href)};
    const context={value:{count:10}};
    const registry=new CommandRegistry().register('count',1,snapshotHandler({read:c=>c.value,write:(c,v)=>{c.value=v;}}));
    const history=await HistoryManager.open({scope:'count',context,registry,storage:new FileHistoryStorage(${JSON.stringify(directory)})});
    await history.undo(); const before=context.value.count; await history.redo();
    process.stdout.write(JSON.stringify({before,after:context.value.count,revision:history.getState().revision}));
  `;
  const child = spawnSync(process.execPath, ['--input-type=module', '-e', program], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr);
  assert.deepEqual(JSON.parse(child.stdout), { before: 4, after: 10, revision: 3 });
  assert.equal((await storage.load('count')).cursor, 1);
});
