// Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const G = require('../../engine/chronoflow/static/nle/grade.js');

const near = (a, b, eps = 1e-4) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);
const grade = (patch) => { const g = G.newGrade(); Object.assign(g.nodes[0], patch); return g; };
/** Run one colour through a grade the way the export does (bake, then sample the table). */
const through = (g, rgb) => G.sampleLut(G.bake(g, 33), 33, rgb[0], rgb[1], rgb[2], [0, 0, 0]);

test('a fresh grade is the identity and bakes to an identity table', () => {
  const g = G.newGrade();
  assert.ok(G.isIdentity(g));
  const N = 17, t = G.bake(g, N);
  for (let b = 0; b < N; b++) for (let gg = 0; gg < N; gg++) for (let r = 0; r < N; r++) {
    const k = ((b * N + gg) * N + r) * 3;
    near(t[k], r / (N - 1)); near(t[k + 1], gg / (N - 1)); near(t[k + 2], b / (N - 1));
  }
});

test('gain master halves every channel; lift raises black; offset shifts', () => {
  const half = through(grade({ gain: { x: 0, y: 0, m: -0.5 } }), [0.8, 0.4, 0.2]);
  near(half[0], 0.4); near(half[1], 0.2); near(half[2], 0.1);
  near(through(grade({ lift: { x: 0, y: 0, m: 0.2 } }), [0, 0, 0])[0], 0.1);          // m 0.2 * 0.5 scale
  near(through(grade({ lift: { x: 0, y: 0, m: 0.2 } }), [1, 1, 1])[0], 1);            // white stays white
  assert.ok(through(grade({ offset: { x: 0, y: 0, m: 0.5 } }), [0.2, 0.2, 0.2])[0] > 0.2);
});

test('contrast turns about the pivot', () => {
  const g = grade({ contrast: 2, pivot: 0.5 });
  near(through(g, [0.5, 0.5, 0.5])[0], 0.5);
  near(through(g, [0.4, 0.4, 0.4])[0], 0.3);
  near(through(g, [0.7, 0.7, 0.7])[0], 0.9);
});

test('saturation 0 gives Rec.709 luma and 1 changes nothing', () => {
  const grey = through(grade({ saturation: 0 }), [1, 0, 0]);
  near(grey[0], 0.2126, 2e-3); near(grey[1], 0.2126, 2e-3); near(grey[2], 0.2126, 2e-3);
  const same = through(grade({ saturation: 1 }), [0.6, 0.3, 0.1]);
  near(same[0], 0.6); near(same[1], 0.3); near(same[2], 0.1);
});

test('temperature warms (red up, blue down) and keeps luma-ish balance on grey', () => {
  const warm = through(grade({ temp: 50 }), [0.5, 0.5, 0.5]);
  assert.ok(warm[0] > 0.5 && warm[2] < 0.5);
  const cool = through(grade({ temp: -50 }), [0.5, 0.5, 0.5]);
  assert.ok(cool[0] < 0.5 && cool[2] > 0.5);
});

test('hue rotation moves red towards green at +120 degrees and keeps grey grey', () => {
  const out = through(grade({ hue: 120 }), [1, 0, 0]);
  assert.ok(out[1] > out[0] && out[1] > out[2], JSON.stringify(out));
  const grey = through(grade({ hue: 90 }), [0.5, 0.5, 0.5]);
  near(grey[0], 0.5, 2e-3); near(grey[1], 0.5, 2e-3); near(grey[2], 0.5, 2e-3);
});

test('hue vs sat pulls only the chosen hue', () => {
  const g = grade({ hueVsSat: [[0, -1], [0.1, 0], [0.9, 0]] });               // red wraps to desaturated, everything else untouched
  const red = through(g, [0.9, 0.2, 0.2]), green = through(g, [0.2, 0.9, 0.2]);
  assert.ok(Math.max(red[0], red[1], red[2]) - Math.min(red[0], red[1], red[2]) < 0.1, `red kept colour: ${red}`);
  near(green[0], 0.2, 0.02); near(green[1], 0.9, 0.02);
});

test('curves pass through their points, stay monotone, and apply per channel', () => {
  const f = G.curveFn([[0, 0], [0.25, 0.4], [0.75, 0.6], [1, 1]]);
  near(f(0.25), 0.4); near(f(0.75), 0.6);
  let prev = -1; for (let i = 0; i <= 100; i++) { const y = f(i / 100); assert.ok(y >= prev - 1e-9); prev = y; }
  const g = grade({ curves: { y: G.tone0(), r: [[0, 0], [0.5, 0.8], [1, 1]], g: G.tone0(), b: G.tone0() } });
  const o = through(g, [0.5, 0.5, 0.5]);
  near(o[0], 0.8, 5e-3); near(o[1], 0.5); near(o[2], 0.5);
});

test('CDL slope, offset and power follow the ASC formula', () => {
  const g = grade({ cdl: { slope: [2, 1, 1], offset: [0, 0.1, 0], power: [1, 1, 2] } });
  const o = through(g, [0.3, 0.3, 0.5]);
  near(o[0], 0.6); near(o[1], 0.4); near(o[2], 0.25);
});

test('output is always clamped to 0..1', () => {
  const o = through(grade({ gain: { x: 0, y: 0, m: 1 }, offset: { x: 0, y: 0, m: -1 } }), [1, 0, 0.5]);
  assert.ok(o.every((x) => x >= 0 && x <= 1));
});

test('a disabled node or a disabled grade does nothing', () => {
  const g = grade({ saturation: 0 }); g.nodes[0].enabled = false;
  assert.ok(G.isIdentity(g));
  const h = grade({ saturation: 0 }); h.on = false;
  assert.ok(G.isIdentity(h));
});

test('nodes run in order: gain then a second node saturates what is left', () => {
  const g = G.newGrade(); g.nodes[0].gain.m = -0.5; g.nodes.push(G.newNode('b')); g.nodes[1].saturation = 0;
  const o = through(g, [1, 0, 0]);
  near(o[0], o[1], 3e-3);                                                        // grey
  assert.ok(o[0] < 0.2126 * 0.6 + 0.02);                                         // and dark, because the first node halved it
});

test('.cube round trip keeps the table, and bad files give readable errors', () => {
  const g = grade({ saturation: 1.4, temp: 20, contrast: 1.2 });
  const t = G.bake(g, 17), back = G.parseCube(G.toCube(t, 17, 'x'));
  assert.equal(back.size, 17);
  for (let i = 0; i < t.length; i++) near(t[i], back.table[i], 2e-6);
  assert.throws(() => G.parseCube('hello'), /Not a \.cube/);
  assert.throws(() => G.parseCube('LUT_3D_SIZE 2\n0 0 0\n'), /expected 8/);
});

test('a 65-point identity .cube is resampled to 33 and stays an identity', () => {
  const t = G.bake(G.newGrade(), 65), lut = G.parseCube(G.toCube(t, 65, 'big'));
  assert.equal(lut.size, 33);
  const o = G.sampleLut(lut.table, lut.size, 0.37, 0.52, 0.91, [0, 0, 0]);
  near(o[0], 0.37, 1e-4); near(o[1], 0.52, 1e-4); near(o[2], 0.91, 1e-4);
});

test('an imported LUT node mixes by strength', () => {
  const lutGrade = grade({ saturation: 0 });
  const lutTable = G.bake(lutGrade, 17), lib = { L1: { title: 'grey', size: 17, table: lutTable } };
  const mk = (s) => { const g = G.newGrade(); g.nodes[0].lut = { id: 'L1', strength: s }; return G.sampleLut(G.bake(g, 33, lib), 33, 1, 0, 0, [0, 0, 0]); };
  near(mk(1)[0], 0.2126, 3e-3);
  near(mk(0.5)[0], 0.6063, 6e-3);
});

test('identical grades hash alike; any change gives a new hash', () => {
  const a = grade({ saturation: 1.2 }), b = grade({ saturation: 1.2 }), c = grade({ saturation: 1.3 });
  assert.equal(G.hashGrade(a), G.hashGrade(b));
  assert.notEqual(G.hashGrade(a), G.hashGrade(c));
});
