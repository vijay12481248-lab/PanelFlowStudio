// Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../../engine/chronoflow/static/nle/model.js');

const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);
function three() {
  const tl = M.create(24);
  for (const n of ['a', 'b', 'c']) M.addClip(tl, { src: `${n}.mp4`, srcDur: 4 });
  return tl;
}

test('layout is gapless and total is the sum of durations (speed applied)', () => {
  const tl = three();
  M.setSpeed(tl, tl.clips[1].id, 2);
  assert.deepEqual(M.layout(tl).map((l) => [l.start, l.end]), [[0, 4], [4, 6], [6, 10]]);
  near(M.total(tl), 10);
});

test('locate maps timeline time to source time, honouring in-point and speed', () => {
  const tl = three();
  tl.clips[1].in = 1; tl.clips[1].speed = 2;           // 3 source seconds -> 1.5 timeline seconds
  const hit = M.locate(tl, 4.75);                      // 0.75 s into clip b -> src 1 + 1.5
  assert.equal(hit.index, 1);
  near(hit.srcTime, 2.5);
  assert.equal(M.locate(tl, M.total(tl)).index, 2);     // the end frame belongs to the last clip
  assert.equal(M.locate(tl, 99), null);
});

test('split cuts the source at the playhead and keeps total duration', () => {
  const tl = three();
  const before = M.total(tl);
  const { left, right } = M.splitAt(tl, 5);
  assert.equal(tl.clips.length, 4);
  near(left.out, 1); near(right.in, 1);
  near(M.total(tl), before);
  assert.equal(M.splitAt(tl, 4), null);                // exactly on an edit: nothing to cut
  assert.equal(M.splitAt(tl, 4 + 0.01), null);         // under 2 frames from the edge
});

test('trim ripples later clips and never inverts or exceeds the source', () => {
  const tl = three();
  const b = tl.clips[1];
  M.trimEdge(tl, b.id, 'out', 3);
  near(M.layout(tl)[2].start, 7);
  M.trimEdge(tl, b.id, 'in', 99);                      // clamped to leave 2 frames
  near(M.clipDur(b), 2 / 24);
  M.trimEdge(tl, b.id, 'out', 99);                     // clamped to the source length
  assert.equal(b.out, 4);
});

test('move reorders, remove ripples, duplicate inserts after', () => {
  const tl = three();
  const [a, b, c] = tl.clips.map((x) => x.id);
  M.moveClip(tl, a, 2);
  assert.deepEqual(tl.clips.map((x) => x.id), [b, c, a]);
  M.removeClip(tl, c);
  near(M.total(tl), 8);
  const d = M.duplicateClip(tl, b);
  assert.deepEqual(tl.clips.map((x) => x.id), [b, d.id, a]);
});

test('speed and volume are clamped', () => {
  const tl = three();
  assert.equal(M.setSpeed(tl, tl.clips[0].id, 99).speed, 4);
  assert.equal(M.setSpeed(tl, tl.clips[0].id, 0.01).speed, 0.25);
  assert.equal(M.setVolume(tl, tl.clips[0].id, 9).volume, 2);
});

test('snap picks the nearest edit point within tolerance only', () => {
  const tl = three();
  M.addMarker(tl, 2.5, 'beat');
  const pts = M.snapPoints(tl);
  assert.equal(M.snap(3.96, pts, 0.1), 4);
  assert.equal(M.snap(2.45, pts, 0.1), 2.5);
  assert.equal(M.snap(3.0, pts, 0.1), 3.0);
  assert.equal(M.neighbour(tl, 4, 1), 8);
  assert.equal(M.neighbour(tl, 4, -1), 2.5);
});

test('timecode is HH:MM:SS:FF and frame() quantises to the frame grid', () => {
  assert.equal(M.toTimecode(3661.5, 24), '01:01:01:12');
  assert.equal(M.toTimecode(0, 24), '00:00:00:00');
  near(M.frame(1.01, 24), 24 / 24);
  near(M.frame(1.03, 24), 25 / 24);
});

test('overlays enforce a minimum length; EDL carries clips and overlays', () => {
  const tl = three();
  const o = M.addOverlay(tl, { src: 'fix.png', start: 5, dur: 0 });
  assert.ok(o.dur >= 2 / 24);
  M.updateOverlay(tl, o.id, { dur: 2 });
  const edl = M.toEdl(tl);
  assert.equal(edl.clips.length, 3);
  assert.deepEqual(edl.overlays, [{ filename: 'fix.png', start: 5, duration: 2 }]);
});

test('history undoes and redoes in place', () => {
  const tl = three();
  const h = M.createHistory(tl);
  h.checkpoint(); M.removeClip(tl, tl.clips[0].id);
  h.checkpoint(); M.splitAt(tl, 1);
  assert.equal(tl.clips.length, 3);
  assert.ok(h.undo()); assert.equal(tl.clips.length, 2);
  assert.ok(h.undo()); assert.equal(tl.clips.length, 3);
  assert.equal(h.undo(), false);
  assert.ok(h.redo()); assert.equal(tl.clips.length, 2);
  h.checkpoint();                                      // a new edit clears redo
  assert.equal(h.canRedo, false);
  h.reset();                                           // switching jobs drops the old job's undo stack
  assert.equal(h.canUndo, false);
  assert.equal(h.undo(), false);
});
