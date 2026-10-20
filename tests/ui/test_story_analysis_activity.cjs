const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const { build } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

let component;
async function render(job) {
  if (!component) {
    const filename = path.resolve(__dirname, '../../apps/desktop/src/components/StoryAnalysisActivity.tsx');
    const result = await build({ entryPoints: [filename], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] });
    const compiled = new Module(filename, module);
    compiled.paths = Module._nodeModulePaths(path.dirname(filename));
    compiled._compile(result.outputFiles[0].text, filename);
    component = compiled.exports.StoryAnalysisActivity;
  }
  return renderToStaticMarkup(React.createElement(component, { job }));
}
const job = {
  status: 'RUNNING', progress: 0.8, input: { total_panels: 48 }, output: {},
  created_at: new Date(Date.now() - 180000).toISOString(),
  lease_expires_at: new Date(Date.now() + 60000).toISOString(),
  retry_count: 1, max_retries: 3, message: 'Reconstructing chapter', error: 'Invalid JSON from previous attempt',
};

test('existing worker shows elapsed time, panel completion and retry without inventing token usage', async () => {
  const html = await render(job);
  assert.match(html, /Elapsed/);
  assert.match(html, /Panels checked: 48\/48/);
  assert.match(html, /Worker heartbeat is current/);
  assert.match(html, /Live token details are unavailable/);
  assert.match(html, /Previous attempt failed/);
  assert.doesNotMatch(html, /Output tokens/);
});

test('live output clearly labels estimated tokens', async () => {
  const html = await render({ ...job, output: { model_activity: {
    model: 'qwen3.5:9b', phase: 'generating', output_characters: 400,
    updated_at: new Date().toISOString(), attempt: 2, max_attempts: 3, output_token_limit: 8192,
  } } });
  assert.match(html, /Receiving model output/);
  assert.match(html, /~100 \(estimate\)/);
  assert.match(html, /repairing invalid output/);
  assert.match(html, /Reported when request finishes/);
});

test('final model metadata replaces estimates with exact usage', async () => {
  const html = await render({ ...job, output: { model_activity: {
    model: 'qwen3.5:9b', phase: 'validating', output_characters: 400,
    input_tokens: 84, output_tokens: 12, tokens_per_second: 6,
    updated_at: new Date(Date.now() - 40000).toISOString(),
  } } });
  assert.match(html, /Validating generated structure/);
  assert.match(html, /6 tokens\/s/);
  assert.match(html, /No new model output recently/);
  assert.doesNotMatch(html, /~100/);
});
