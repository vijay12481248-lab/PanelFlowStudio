const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const { build } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

let card;
async function render(job, engineHealthy = true) {
  if (!card) {
    const filename = path.resolve(__dirname, '../../apps/desktop/src/components/JobActivityPanel.tsx');
    const result = await build({ entryPoints: [filename], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] });
    const compiled = new Module(filename, module);
    compiled.paths = Module._nodeModulePaths(path.dirname(filename));
    compiled._compile(result.outputFiles[0].text, filename);
    card = compiled.exports.JobActivityCard;
  }
  return renderToStaticMarkup(React.createElement(card, { job, engineHealthy, onCancel: async () => true }));
}
const job = { job_id: 'job-123', project_id: 'project-456', job_type: 'STORY_ANALYSIS', status: 'RUNNING', progress: 0.8,
  created_at: '2026-10-19T22:00:00', started_at: '2026-10-19T22:01:00', message: 'Reconstructing chapter', retry_count: 2, max_retries: 3,
  lease_expires_at: new Date(Date.now() + 60000).toISOString(),
};

test('running job includes identity, timing, progress, status, health and cancellation', async () => {
  const html = await render(job);
  for (const value of ['job-123', 'project-456', 'STORY ANALYSIS', 'RUNNING', '80%', 'Started (current attempt)', 'Engine connection', 'Healthy', 'Worker heartbeat', 'Current', '2/3', 'Cancel job']) assert.ok(html.includes(value), value);
});

test('queued jobs show waiting and do not claim a healthy worker', async () => {
  const html = await render({ ...job, status: 'QUEUED', started_at: null, lease_expires_at: null });
  assert.ok(html.includes('Not started'));
  assert.ok(html.includes('Not applicable'));
  assert.ok(html.includes('Cancel job'));
});

test('terminal jobs have no cancellation control', async () => {
  for (const status of ['SUCCEEDED', 'FAILED', 'CANCELLED']) {
    assert.ok(!(await render({ ...job, status })).includes('Cancel job'));
  }
});

test('unreachable engine disables cancellation and expired worker lease is distinguished', async () => {
  const html = await render({ ...job, lease_expires_at: '2020-01-01T00:00:00Z' }, false);
  assert.ok(html.includes('Unavailable'));
  assert.ok(html.includes('Delayed / unavailable'));
  assert.match(html, /disabled=""/);
});
