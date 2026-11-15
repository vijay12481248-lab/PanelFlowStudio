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

// ---- review fixes
test('a text card that ends up first can render (the server renders it as text)', () => {
  const s = [wiz('text', 1)];
  assert.equal(NV.canRender(s, 0).ok, true);
});

test('relink recomputes who continues from whom after delete, move or insert', () => {
  const s = [wiz('text', 0), wiz('text', 1), wiz('first', 2)];
  s.splice(0, 1); // delete card 1
  NV.relink(s);
  assert.deepEqual(s.map((c) => c.inherits_tail), [false, true]);
  const t = [wiz('first_last', 0), wiz('first', 1)];
  t.reverse();
  NV.relink(t);
  assert.deepEqual(t.map((c) => c.inherits_tail), [false, false]); // first_last never chains; the first card never chains
  const r = [wiz('first', 0, { first_frame: 'a.png' }), wiz('first', 1, { rendered_video: 'v.mp4', state: 'approved', approved: true })];
  r.reverse();
  NV.relink(r);
  assert.equal(r[0].state, 'stale'); // its start frame changed, so the old clip no longer matches
  assert.equal(r[0].approved, false);
});

test('a new card in a wizard plan has the same shape as a planned one', () => {
  const s = [wiz('first', 0, { width: 768, height: 1344, lora_choice: '8step' })];
  const c = NV.newCard(s);
  s.push(c);
  assert.equal(c.start_mode, 'first');
  assert.equal(c.inherits_tail, true);
  assert.equal(c.state, 'empty');
  assert.equal(c.approved, false);
  assert.deepEqual([c.width, c.height, c.lora_choice], [768, 1344, '8step']);
  assert.equal(c.shot_index, 2);
  assert.ok(c.duration > 5 && c.duration < 5.2);
});

test('the last frame of a first+last card is offered as the next card\'s first frame', () => {
  const s = [wiz('first_last', 0, { last_frame: 'end1.png' }), wiz('first_last', 1), wiz('first_last', 2, { first_frame: 'mine.png' })];
  NV.chainKeyframe(s, 0);
  assert.equal(s[1].first_frame, 'end1.png');
  s[1].last_frame = 'end2.png';
  NV.chainKeyframe(s, 1);
  assert.equal(s[2].first_frame, 'mine.png'); // never overwrite a picture the user chose
  const t = [wiz('first_last', 0, { last_frame: 'x.png' }), wiz('text', 1)];
  NV.chainKeyframe(t, 0);
  assert.equal(t[1].first_frame, ''); // only into another first+last card
});

test('a render that was in flight before a reload is shown as ready, unknown states too', () => {
  assert.equal(NV.displayState({ state: 'rendering' }), 'ready');
  assert.equal(NV.displayState({ state: '"><img src=x>' }), 'ready');
  assert.equal(NV.displayState({ state: 'review' }), 'review');
});

// ---- plan import: pictures arriving from the picture job, and the Render all queue
const planCard = (i, extra = {}) => ({ start_mode: 'first_last', take_id: `t0${i + 1}`, inherits_tail: false, first_frame: '', last_frame: '', ref_images: [], prompt: 'FL2VA prompt', state: 'ready', approved: false, width: 1344, height: 768, ...extra });

test('pictures from the job fill empty slots and never overwrite the owner\'s own picture', () => {
  const s = [planCard(0), planCard(1, { first_frame: 'my_own_upload.png' }), planCard(2, { first_frame: 'slug_x_t03_start.png' })];
  const items = [
    { take_id: 't01', start: 'slug_x_t01_start.png', end: 'slug_x_t01_end.png', problems: [] },
    { take_id: 't02', start: 'slug_x_t02_start.png', end: 'slug_x_t02_end.png', problems: ['end: cat: counted 2, planned 1'] },
    { take_id: 't03', start: 'slug_x_t03_start2.png', end: 'slug_x_t03_end.png', problems: [] },
  ];
  assert.equal(NV.applyPictureItems(s, items, 'slug_x'), true);
  assert.deepEqual([s[0].first_frame, s[0].last_frame], ['slug_x_t01_start.png', 'slug_x_t01_end.png']);
  assert.equal(s[1].first_frame, 'my_own_upload.png'); // the owner's file stays
  assert.equal(s[1].last_frame, 'slug_x_t02_end.png');
  assert.equal(s[2].first_frame, 'slug_x_t03_start2.png'); // a redrawn plan picture replaces the older plan picture
  assert.deepEqual(s[1].picture_problems, ['end: cat: counted 2, planned 1']);
  assert.equal(NV.applyPictureItems(s, items, 'slug_x'), false); // nothing new
});

test('picture counts say how many takes have both pictures', () => {
  const s = [planCard(0, { first_frame: 'a', last_frame: 'b' }), planCard(1, { first_frame: 'a' }), planCard(2)];
  assert.deepEqual(NV.pictureCounts(s), { takes: 3, ready: 1 });
});

test('Render all runs what can run now and says what waits', () => {
  const s = [planCard(0, { first_frame: 'a', last_frame: 'b' }), planCard(1, { first_frame: 'b', last_frame: 'c', state: 'approved', approved: true }), planCard(2, { first_frame: 'c', last_frame: 'd', state: 'review' }),
    planCard(3, { first_frame: 'd' }), planCard(4, { first_frame: 'e', last_frame: 'f', state: 'stale' }), planCard(5, { first_frame: 'f', last_frame: 'g', prompt: ' ' })];
  const q = NV.renderAllQueue(s);
  assert.deepEqual(q.run, [0, 4]); // ready and stale cards with everything they need
  assert.deepEqual(q.waiting.map((w) => w.i), [3, 5]);
  assert.match(q.waiting[0].reason, /Last frame/);
  assert.match(q.waiting[1].reason, /prompt/i);
});
