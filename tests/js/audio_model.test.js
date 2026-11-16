// Run: node --test tests/js/audio_model.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const A = require('../../engine/chronoflow/static/nle/audio-model.js');

const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);
const plan = (over) => Object.assign({ fps: 24, duration: 10 }, over || {});
const take = (over) => Object.assign({ id: 't', onset_s: 0.2, peak_s: 0.5, duration_s: 1.5 }, over || {});
const hitCue = (over) => Object.assign({ id: 'c', track: 'sfx', hit_t: 3, anchor: 'onset', t_in: 0, t_out: null, takes: [take()], chosen_take: 't', status: 'ready' }, over || {});

test('time code is hh:mm:ss:ff, non-drop at the nominal rate', () => {
  assert.equal(A.fmtTC(1, 24), '00:00:01:00');
  assert.equal(A.fmtTC(61.5, 24), '00:01:01:12');
  assert.equal(A.fmtTC(1.001, 29.97), '00:00:01:00');
  assert.equal(A.fmtTC(-3, 24), '00:00:00:00');
});

test('snapFrame rounds to the nearest frame', () => {
  near(A.snapFrame(1.013, 24), 24 / 24 + 0);
  near(A.snapFrame(1.03, 24), 25 / 24);
  near(A.snapFrame(1.0, 29.97), 30 / 29.97);
});

test('time and x are inverse, zoomAt keeps the anchor time under the cursor and respects limits', () => {
  const v = { t0: 2, pps: 100 };
  near(A.timeToX(5, v), 300);
  near(A.xToTime(300, v), 5);
  const z = A.zoomAt(v, 2, 5, { minPps: 5, maxPps: 800 });
  near(A.timeToX(5, z), A.timeToX(5, v));
  assert.equal(z.pps, 200);
  assert.equal(A.zoomAt(v, 100, 5, { minPps: 5, maxPps: 800 }).pps, 800);
  assert.equal(A.zoomAt(v, 0.001, 5, { minPps: 5, maxPps: 800 }).pps, 5);
  assert.ok(A.zoomAt({ t0: 0, pps: 100 }, 0.5, 0, { minPps: 5, maxPps: 800 }).t0 >= 0);
});

test('ruler ticks: major step is the smallest that keeps labels 60 px apart', () => {
  assert.equal(A.rulerStep(100, 24), 1);
  assert.equal(A.rulerStep(10, 24), 10);
  near(A.rulerStep(2000, 24), 1 / 24);
  const t = A.rulerTicks({ t0: 0, pps: 100 }, 400, 24);
  assert.deepEqual(t.filter((x) => x.major).map((x) => x.t), [0, 1, 2, 3, 4]);
});

test('lanes and stems', () => {
  assert.deepEqual(A.LANES.map((l) => l.id), ['dialogue', 'music', 'sfx', 'ambience', 'foley']);
  assert.equal(A.stemOf('dialogue'), 'dialogue');
  assert.equal(A.stemOf('music'), 'music');
  for (const t of ['sfx', 'ambience', 'foley']) assert.equal(A.stemOf(t), 'effects');
});

test('cueSpan: a hit cue starts anchor-seconds before its hit and is trimmed at 0; beds use t_in/t_out; empty cues get a small block', () => {
  let s = A.cueSpan(hitCue(), plan());
  near(s.start, 2.8); near(s.end, 2.8 + 1.5);
  s = A.cueSpan(hitCue({ hit_t: 0.1 }), plan());
  near(s.start, 0); near(s.end, 1.4);
  s = A.cueSpan(hitCue({ anchor: 'peak', hit_t: 3 }), plan());
  near(s.start, 2.5);
  s = A.cueSpan({ id: 'b', track: 'ambience', t_in: 1, t_out: 6, hit_t: null, takes: [], status: 'draft' }, plan());
  assert.deepEqual([s.start, s.end], [1, 6]);
  s = A.cueSpan({ id: 'd', track: 'sfx', hit_t: 4, takes: [], status: 'draft' }, plan());
  assert.deepEqual([s.start, s.end], [4, 4.4]);
});

test('dragCue moves the hit by frames, snaps to a nearby cut, and clamps to the video', () => {
  const p = hitCue();
  near(A.dragCue(p, 0.5, plan(), [], 0.1).hit_t, 3.5);
  near(A.dragCue(p, 0.513, plan(), [], 0.1).hit_t, A.snapFrame(3.513, 24));
  near(A.dragCue(p, 0.95, plan(), [4], 0.1).hit_t, 4);          // within 0.1 s of the cut at 4
  near(A.dragCue(p, 0.7, plan(), [4], 0.1).hit_t, A.snapFrame(3.7, 24)); // 0.3 s away: no snap
  assert.equal(A.dragCue(p, -50, plan(), [], 0.1).hit_t, 0);
  assert.equal(A.dragCue(p, 50, plan(), [], 0.1).hit_t, 10);
});

test('dragCue moves a bed as one piece and keeps its length inside the video', () => {
  const bed = { id: 'b', track: 'ambience', t_in: 1, t_out: 4, hit_t: null, takes: [], status: 'draft' };
  let patch = A.dragCue(bed, 2, plan(), [], 0.1);
  near(patch.t_in, 3); near(patch.t_out, 6);
  patch = A.dragCue(bed, 50, plan(), [], 0.1);
  near(patch.t_out, 10); near(patch.t_in, 7);
  patch = A.dragCue(bed, -50, plan(), [], 0.1);
  near(patch.t_in, 0); near(patch.t_out, 3);
});

test('decibels and gains', () => {
  near(A.dbToGain(0), 1); near(A.dbToGain(-6), 0.501187, 1e-5); near(A.gainToDb(1), 0);
  assert.equal(A.gainToDb(0), -Infinity);
  near(A.gainToDb(A.dbToGain(-12.5)), -12.5, 1e-9);
});

test('effectiveGains: mute silences a stem, solo silences the others, solo wins over mute', () => {
  const g = { dialogue: 0, music: -6, effects: 0 };
  let e = A.effectiveGains(g, new Set(), new Set());
  near(e.music, A.dbToGain(-6)); near(e.dialogue, 1);
  e = A.effectiveGains(g, new Set(['music']), new Set());
  assert.equal(e.music, 0); near(e.dialogue, 1);
  e = A.effectiveGains(g, new Set(['dialogue']), new Set(['dialogue']));
  near(e.dialogue, 1); assert.equal(e.music, 0); assert.equal(e.effects, 0);
});

test('driftAction: nothing inside the tolerance, otherwise the time to seek the stem to', () => {
  assert.equal(A.driftAction(10, 10.05, 0.06), null);
  assert.equal(A.driftAction(10, 10.2, 0.06), 10);
  assert.equal(A.driftAction(10, 9.9), 10);
});

test('statusChip', () => {
  assert.deepEqual(A.statusChip({ status: 'draft' }), { text: 'draft', tone: 'muted' });
  assert.deepEqual(A.statusChip({ status: 'needs_pick' }), { text: 'pick one', tone: 'warn' });
  assert.deepEqual(A.statusChip({ status: 'failed' }), { text: 'failed', tone: 'bad' });
  assert.deepEqual(A.statusChip({ status: 'ready', placement_error_ms: 2 }), { text: 'ready', tone: 'ok' });
  assert.deepEqual(A.statusChip({ status: 'ready', placement_error_ms: 25 }), { text: 'ready · 25 ms', tone: 'warn' });
  assert.deepEqual(A.statusChip({ status: 'ready', placement_error_ms: 63.4 }), { text: 'ready · 63 ms', tone: 'bad' });
});

test('peaksToBars takes the max of each pixel column over the chosen slice', () => {
  assert.deepEqual(A.peaksToBars([0, 1, 0, 0], 2, 0, 1), [1, 0]);
  assert.deepEqual(A.peaksToBars([0.1, 0.2, 0.9, 0.3], 2, 0.5, 1), [0.9, 0.3]);
  assert.deepEqual(A.peaksToBars([], 3, 0, 1), [0, 0, 0]);
  assert.equal(A.peaksToBars([0.5, 0.5], 5, 0, 1).length, 5);
});

test('nextVersionSeen: a newer plan version from the server means refresh', () => {
  assert.equal(A.needsRefresh(3, 3), false);
  assert.equal(A.needsRefresh(3, 4), true);
  assert.equal(A.needsRefresh(null, 1), true);
});

test('safeUrl lets only http(s) links through (a source page link comes from a third-party catalogue)', () => {
  assert.equal(A.safeUrl('https://freesound.org/people/x/sounds/1'), 'https://freesound.org/people/x/sounds/1');
  assert.equal(A.safeUrl('HTTP://example.com/a'), 'HTTP://example.com/a');
  for (const bad of ['javascript:alert(1)', ' javascript:alert(1)', 'data:text/html,<script>', 'file:///C:/x', '//evil.example/x', '', null, undefined, 42]) assert.equal(A.safeUrl(bad), null, String(bad));
});

test('estimateSeconds matches the engine: words at 3 per second plus pauses for punctuation, divided by speed', () => {
  const w26 = Array(26).fill('word').join(' ');
  near(A.estimateSeconds(w26, 1), 26 / 3, 0.01);
  near(A.estimateSeconds(w26, 2), 13 / 3, 0.01);
  assert.ok(A.estimateSeconds('One. Two. Three.', 1) > A.estimateSeconds('One Two Three', 1));
  near(A.estimateSeconds('At dawn, the gate opened, and a small cat followed the pilot into the clouds.', 1), 15 / 3 + 0.35 + 0.15 * 2, 0.01);
  assert.equal(A.estimateSeconds('   ', 1), 0);
});

test('loudness presets are the targets creators use', () => {
  assert.deepEqual(A.LOUDNESS.map((p) => p.lufs), [-14, -14, -16, -23]);
  assert.ok(A.LOUDNESS.every((p) => p.id && p.label && p.hint));
});

test('splitScript: paragraphs are lines, one paragraph is split into sentences (same rule as the engine)', () => {
  assert.deepEqual(A.splitScript('First line here.\n\nSecond line here.\n\n\nThird.'), ['First line here.', 'Second line here.', 'Third.']);
  assert.deepEqual(A.splitScript('One. Two? Three! Four'), ['One.', 'Two?', 'Three!', 'Four']);
  assert.deepEqual(A.splitScript('A single paragraph\nthat wraps over two lines, with one sentence.'), ['A single paragraph that wraps over two lines, with one sentence.']);
  assert.deepEqual(A.splitScript('  \n \n'), []);
});

test('an unspoken narration cue is drawn as long as its estimated speech; a spoken one as long as its take', () => {
  const words = Array(30).fill('word').join(' ');
  const draft = { id: 'v', track: 'dialogue', kind: 'narration', text: words, speed: 1, t_in: 5, t_out: null, hit_t: null, takes: [], status: 'draft' };
  near(A.cueSpan(draft, plan()).end - 5, 30 / 3, 0.01);
  const spoken = { ...draft, takes: [take({ duration_s: 4.2 })], chosen_take: 't', status: 'ready' };
  near(A.cueSpan(spoken, plan()).end - 5, 4.2, 0.001);
});

test('the voice lane is labelled VO', () => {
  assert.equal(A.LANES.find((l) => l.id === 'dialogue').label, 'VO');
});
