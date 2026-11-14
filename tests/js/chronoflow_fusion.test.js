// Run: node --test tests/js/chronoflow_fusion.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const FG = require('../../engine/chronoflow/static/nle/fusion-graph.js');

test('a fresh graph creates MediaIn -> MediaOut identity graph', () => {
  const g = FG.newGraph();
  assert.equal(g.nodes.length, 2);
  assert.equal(g.nodes[0].type, 'mediain');
  assert.equal(g.nodes[1].type, 'mediaout');
  assert.equal(g.connections.length, 1);
  assert.equal(g.connections[0].from.nodeId, 'media_in');
  assert.equal(g.connections[0].to.nodeId, 'media_out');
  assert.ok(FG.isIdentity(g));
});

test('adding nodes creates valid structure and is no longer identity when active', () => {
  const g = FG.newGraph();
  const blurNode = FG.addNode(g, 'blur', { params: { radius: 20 } });
  assert.equal(blurNode.type, 'blur');
  assert.equal(blurNode.params.radius, 20);
  assert.equal(g.nodes.length, 3);
  assert.ok(!FG.isIdentity(g));

  // If node disabled, it is identity again
  blurNode.params.enabled = false;
  assert.ok(FG.isIdentity(g));
});

test('connect and disconnect operate cleanly on sockets', () => {
  const g = FG.newGraph();
  const xf = FG.addNode(g, 'transform');
  
  // MediaIn -> Transform
  const ok1 = FG.connect(g, 'media_in', 'output', xf.id, 'input');
  assert.ok(ok1);

  // Transform -> MediaOut
  const ok2 = FG.connect(g, xf.id, 'output', 'media_out', 'input');
  assert.ok(ok2);

  // Cycle prevention: connecting MediaOut back to MediaIn should fail
  const badCycle = FG.connect(g, 'media_out', 'output', 'media_in', 'input');
  assert.equal(badCycle, false);

  // Disconnect Transform -> MediaOut
  const disc = FG.disconnect(g, 'media_out', 'input');
  assert.ok(disc);
  assert.equal(g.connections.some((c) => c.to.nodeId === 'media_out'), false);
});

test('insertNodeInLine splices between MediaIn and MediaOut', () => {
  const g = FG.newGraph();
  const xf = FG.insertNodeInLine(g, 'transform');
  assert.equal(g.nodes.length, 3);
  
  const inToXf = g.connections.find((c) => c.from.nodeId === 'media_in');
  assert.equal(inToXf.to.nodeId, xf.id);

  const xfToOut = g.connections.find((c) => c.to.nodeId === 'media_out');
  assert.equal(xfToOut.from.nodeId, xf.id);
});

test('topologicalSort returns execution order from input to output', () => {
  const g = FG.newGraph();
  const n1 = FG.insertNodeInLine(g, 'blur');
  const n2 = FG.insertNodeInLine(g, 'glow');

  const sorted = FG.topologicalSort(g);
  assert.equal(sorted.length, 4);
  assert.equal(sorted[0].type, 'mediain');
  assert.equal(sorted[sorted.length - 1].type, 'mediaout');
});

test('removeNode safely deletes node and linked connections without breaking terminals', () => {
  const g = FG.newGraph();
  const blur = FG.insertNodeInLine(g, 'blur');
  assert.equal(g.nodes.length, 3);
  assert.equal(g.connections.length, 2);

  const removed = FG.removeNode(g, blur.id);
  assert.ok(removed);
  assert.equal(g.nodes.length, 2);
  assert.equal(g.connections.length, 0);

  // Cannot remove media_in or media_out
  assert.equal(FG.removeNode(g, 'media_in'), false);
  assert.equal(FG.removeNode(g, 'media_out'), false);
});

test('presets build complete multi-node compositions', () => {
  const presetKeys = Object.keys(FG.PRESETS);
  assert.ok(presetKeys.includes('cinematic_title'));
  assert.ok(presetKeys.includes('action_impact'));
  assert.ok(presetKeys.includes('dreamy_bloom'));
  assert.ok(presetKeys.includes('anamorphic_vignette'));
  assert.ok(presetKeys.includes('chroma_key'));

  for (const k of presetKeys) {
    const g = FG.newGraph();
    FG.applyPreset(g, k);
    assert.ok(g.nodes.length >= 3, `Preset ${k} has enough nodes`);
    assert.ok(g.connections.length >= 2, `Preset ${k} has connections`);
    assert.ok(!FG.isIdentity(g));
    const sorted = FG.topologicalSort(g);
    assert.equal(sorted[0].type, 'mediain');
    assert.equal(sorted[sorted.length - 1].type, 'mediaout');
  }
});

test('toFfmpegFilter produces valid filter chain strings for export', () => {
  const g = FG.newGraph();
  FG.insertNodeInLine(g, 'blur', { params: { radius: 10 } });
  FG.insertNodeInLine(g, 'vignette', { params: { radius: 0.8 } });
  FG.insertNodeInLine(g, 'text_plus', { params: { text: 'EPISODE 1' } });

  const filter = FG.toFfmpegFilter(g, 1920, 1080);
  assert.ok(filter.includes('gblur=sigma='));
  assert.ok(filter.includes('vignette=angle='));
  assert.ok(filter.includes('drawtext=text=\'EPISODE 1\''));
});

test('color and hex utility functions convert accurately', () => {
  const rgb = FG.hexToRgb('#ff8000');
  assert.equal(rgb.r, 255);
  assert.equal(rgb.g, 128);
  assert.equal(rgb.b, 0);

  const rgba = FG.hexToRgba('#ff8000', 0.5);
  assert.equal(rgba, 'rgba(255, 128, 0, 0.5)');
});

test('mask nodes can connect to effect mask sockets', () => {
  const g = FG.newGraph();
  const blur = FG.insertNodeInLine(g, 'blur');
  const mask = FG.addNode(g, 'ellipse_mask', { params: { x: 0.5, y: 0.4, width: 0.3, height: 0.3 } });

  const ok = FG.connect(g, mask.id, 'mask', blur.id, 'mask');
  assert.ok(ok, 'Connected mask output to blur mask input');

  assert.equal(g.connections.some((c) => c.from.nodeId === mask.id && c.to.nodeId === blur.id && c.to.socket === 'mask'), true);
});

test('face_blur preset creates masked blur composition', () => {
  const g = FG.newGraph();
  FG.applyPreset(g, 'face_blur');
  assert.equal(g.nodes.length, 4);
  assert.ok(g.nodes.some((n) => n.type === 'ellipse_mask'));
  assert.ok(g.nodes.some((n) => n.type === 'blur'));
  assert.ok(g.connections.some((c) => c.to.socket === 'mask'));
});

test('evaluate supports intermediate targetViewNodeId inspection', () => {
  const g = FG.newGraph();
  const blur = FG.insertNodeInLine(g, 'blur');
  const src = { width: 320, height: 240, getContext: () => ({ drawImage: () => {}, clearRect: () => {} }) };
  const dst = { width: 320, height: 240, getContext: () => ({ drawImage: () => {}, clearRect: () => {} }) };

  const res = FG.evaluate(g, src, dst, 0, blur.id);
  assert.equal(res, dst);
});
