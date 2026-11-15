// Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const NV = require('../../engine/chronoflow/static/nle/newvideo.js');

const card = (extra = {}) => ({ start_mode: 'first', inherits_tail: false, first_frame: '', approved: false, state: 'ready', ...extra });
const chained = (extra = {}) => card({ inherits_tail: true, ...extra });

test('segment count matches the server rule', () => {
  assert.equal(NV.segmentCount(300), 58);
  assert.equal(NV.segmentCount(15), 3);
  assert.equal(NV.segmentCount(1), 1);
  assert.match(NV.lengthLabel(300), /5 min = 58 segments/);
  assert.match(NV.lengthLabel(15), /15 s = 3 segments/);
});

test('slots per mode match the server table', () => {
  assert.deepEqual(NV.slotsFor('text'), []);
  assert.deepEqual(NV.slotsFor('first'), ['first']);
  assert.deepEqual(NV.slotsFor('from_video'), ['first']);
  assert.deepEqual(NV.slotsFor('first_last'), ['first', 'last']);
  assert.deepEqual(NV.slotsFor('last'), ['last']);
  assert.deepEqual(NV.slotsFor('reference'), ['ref1', 'ref2']);
  assert.throws(() => NV.slotsFor('sideways'));
});

test('a chained card waits for the previous card to be approved', () => {
  const s = [card(), chained(), chained()];
  assert.equal(NV.canRender(s, 0).ok, true);
  const blocked = NV.canRender(s, 1);
  assert.equal(blocked.ok, false);
  assert.match(blocked.reason, /Shot 1/);
  NV.approve(s, 0);
  assert.equal(NV.canRender(s, 1).ok, true);
  assert.equal(NV.canRender(s, 2).ok, false);
});

test('a card with its own frame renders any time', () => {
  const s = [card(), chained({ first_frame: 'mine.png' })];
  assert.equal(NV.canRender(s, 1).ok, true);
});

test('a deleted dependency never leaves a card waiting on something that is gone', () => {
  const s = [card({ approved: true }), chained()];
  assert.equal(NV.canRender(s, 1).ok, true); // its previous card is whatever is before it now
  const orphan = [chained()];
  const r = NV.canRender(orphan, 0);
  assert.equal(r.ok, false);
  assert.match(r.reason, /first frame/i); // nothing to continue from: says what to add, not "wait"
});

test('redo marks only the chained followers stale', () => {
  const s = [card({ approved: true, state: 'approved', rendered_video: 'a.mp4' }), chained({ approved: true, state: 'approved' }), chained({ approved: true, state: 'approved' }),
    card({ first_frame: 'own.png', approved: true, state: 'approved' }), chained({ approved: true, state: 'approved' })];
  NV.markRedo(s, 0);
  assert.equal(s[0].approved, false);
  assert.equal(s[0].state, 'ready');
  assert.equal(s[0].rendered_video, '');
  assert.deepEqual(s.map((c) => c.state), ['ready', 'stale', 'stale', 'approved', 'approved']);
  assert.equal(s[1].approved, false);
});

test('the previous tail follows the current order', () => {
  const s = [card({ tail_frame: 'a.png' }), card({ tail_frame: 'b.png' }), chained()];
  assert.equal(NV.prevTail(s, 2), 'b.png');
  s.splice(1, 1); // delete the middle card
  assert.equal(NV.prevTail(s, 1), 'a.png');
  assert.equal(NV.prevTail(s, 0), '');
});

test('recording a render puts the card in review and keeps its tail frame', () => {
  const s = [card(), chained()];
  NV.markRendered(s, 0, { video_url: '/chronoflow/outputs/x.mp4', filename: 'x.mp4', tail_frame: 't.png' });
  assert.equal(s[0].state, 'review');
  assert.equal(s[0].rendered_video, '/chronoflow/outputs/x.mp4');
  assert.equal(s[0].tail_frame, 't.png');
  assert.equal(s[0].approved, false);
});

// ---- card helpers
const wiz = (mode, i, extra = {}) => ({ start_mode: mode, inherits_tail: i >= 1 && ['text', 'first', 'from_video'].includes(mode), first_frame: '', last_frame: '', ref_images: [], prompt: 'x', width: 1344, height: 768, ...extra });

test('slots read and write the right scene fields', () => {
  const s = wiz('reference', 0);
  NV.setSlot(s, 'ref1', 'a.png');
  NV.setSlot(s, 'ref2', 'b.png');
  assert.deepEqual(s.ref_images, ['a.png', 'b.png']);
  assert.equal(NV.getSlot(s, 'ref2'), 'b.png');
  NV.setSlot(s, 'first', 'f.png');
  NV.setSlot(s, 'last', 'l.png');
  assert.equal(s.first_frame, 'f.png');
  assert.equal(s.last_frame, 'l.png');
  assert.throws(() => NV.setSlot(wiz('reference', 0), 'ref2', 'b.png'), /reference 1/); // the second reference needs the first
  NV.setSlot(s, 'ref1', '');
  assert.deepEqual(s.ref_images, ['b.png']); // clearing the first reference shifts the second up (a hole would break the server)
});

test('effective mode matches the server', () => {
  assert.equal(NV.effectiveMode(wiz('text', 0), 0), 'text');
  assert.equal(NV.effectiveMode(wiz('text', 2), 2), 'first');
  assert.equal(NV.effectiveMode(wiz('from_video', 0), 0), 'first');
  assert.equal(NV.effectiveMode(wiz('first_last', 3), 3), 'first_last');
});

test('missing inputs match the server rules', () => {
  assert.deepEqual(NV.missingInputs(wiz('first_last', 0, { first_frame: 'a.png' }), 0), ['last']);
  assert.deepEqual(NV.missingInputs(wiz('reference', 0), 0), ['ref1']);
  assert.deepEqual(NV.missingInputs(wiz('reference', 0, { ref_images: ['a.png'] }), 0), []);
  assert.deepEqual(NV.missingInputs(wiz('first', 1), 1), []); // chained: the tail frame arrives at render time
  assert.deepEqual(NV.missingInputs(wiz('from_video', 0), 0), ['first']);
  assert.deepEqual(NV.missingInputs(wiz('text', 0, { prompt: '  ' }), 0), ['prompt']);
});

test('text and reference cards warn about the smaller canvas, others do not', () => {
  assert.match(NV.sizeWarning(wiz('text', 0), 0), /960.544/);
  assert.match(NV.sizeWarning(wiz('text', 0, { width: 768, height: 1344 }), 0), /544.960/);
  assert.match(NV.sizeWarning(wiz('reference', 0), 0), /960.544/);
  assert.equal(NV.sizeWarning(wiz('first_last', 0), 0), '');
  assert.equal(NV.sizeWarning(wiz('text', 2), 2), ''); // chained text renders as first-frame at full size
});

test('changing a rendered card to another mode invalidates it and its chained followers', () => {
  const s = [wiz('first', 0, { first_frame: 'a.png', state: 'approved', approved: true, rendered_video: 'v.mp4' }), wiz('first', 1, { state: 'approved', approved: true })];
  NV.setMode(s, 0, 'text');
  assert.equal(s[0].start_mode, 'text');
  assert.equal(s[0].approved, false);
  assert.equal(s[1].state, 'stale');
  NV.setMode(s, 1, 'first_last');
  assert.equal(s[1].inherits_tail, false);
  assert.equal(s[1].start_mode, 'first_last');
});
