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
