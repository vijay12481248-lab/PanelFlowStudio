const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const { build } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { readFileSync } = require('node:fs');

test('script review resolves saved panel references through the engine client', () => {
  const screen = readFileSync(path.resolve(__dirname, '../../apps/desktop/src/screens/ScriptReviewScreen.tsx'), 'utf8');
  assert.ok(!screen.includes('src={pRef.image_url'));
  assert.ok(screen.includes('src={api.getPanelImageUrl(project.id, pRef.panel_id)}'));
});

test('storyboard previews use the engine URL instead of saved relative URLs', async () => {
  const filename = path.resolve(__dirname, '../../apps/desktop/src/components/StoryboardPreview.tsx');
  const result = await build({ entryPoints: [filename], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] });
  const compiled = new Module(filename, module);
  compiled.paths = Module._nodeModulePaths(path.dirname(filename));
  compiled._compile(result.outputFiles[0].text, filename);
  const html = renderToStaticMarkup(React.createElement(compiled.exports.StoryboardPreview, {
    src: 'http://127.0.0.1:8765/api/projects/project/panels/panel/file', readingOrder: 1,
  }));
  assert.ok(html.includes('src="http://127.0.0.1:8765/api/projects/project/panels/panel/file"'));
  assert.ok(html.includes('alt="Source panel 1"'));
});
