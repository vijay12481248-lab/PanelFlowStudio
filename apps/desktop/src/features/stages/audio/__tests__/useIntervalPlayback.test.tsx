import { mount } from "../../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { useIntervalPlayback, type AudioLike, type PlaybackInterval } from "../useIntervalPlayback";

class FakeAudio implements AudioLike {
  src = ""; playbackRate = 1; muted = false; volume = 1; currentTime = 0;
  played: string[] = []; pauses = 0;
  private listeners: Record<string, Array<() => void>> = {};
  play() { this.played.push(this.src); return Promise.resolve(); }
  pause() { this.pauses++; }
  addEventListener(type: string, fn: () => void) { (this.listeners[type] ??= []).push(fn); }
  removeEventListener(type: string, fn: () => void) { this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn); }
  emit(type: string) { for (const fn of [...(this.listeners[type] ?? [])]) fn(); }
  listenerCount() { return Object.values(this.listeners).reduce((n, l) => n + l.length, 0); }
}

/** A manual timer queue: nothing fires until the test says so. */
function fakeTimers() {
  let next = 1;
  const pending: Array<{ id: number; fn: () => void; ms: number }> = [];
  return {
    pending,
    set: (fn: () => void, ms: number) => { const id = next++; pending.push({ id, fn, ms }); return id; },
    clear: (id: unknown) => { const i = pending.findIndex((t) => t.id === id); if (i >= 0) pending.splice(i, 1); },
    fireNext: () => { const t = pending.shift(); t?.fn(); },
  };
}

const SPEECH_A: PlaybackInterval = { start_time: 0, end_time: 2, duration: 2, audio_file_uri: "a.wav" };
const GAP: PlaybackInterval = { start_time: 2, end_time: 3, duration: 1 };
const SPEECH_B: PlaybackInterval = { start_time: 3, end_time: 5, duration: 2, audio_file_uri: "b.wav" };
const NOT_SPEECH: PlaybackInterval = { start_time: 5, end_time: 6, duration: 1, audio_file_uri: "music.wav", is_speech: false };
const INTERVALS = [SPEECH_A, GAP, SPEECH_B];

async function setup(intervals: PlaybackInterval[] = INTERVALS) {
  const audio = new FakeAudio();
  const timers = fakeTimers();
  let finished = 0;
  let hook!: ReturnType<typeof useIntervalPlayback>;
  const Probe: React.FC = () => {
    hook = useIntervalPlayback(intervals, { urlFor: (iv) => `/audio/${iv.audio_file_uri}`, createAudio: () => audio, timers, onFinished: () => { finished++; } });
    return null;
  };
  const view = await mount(<Probe />);
  const run = (fn: () => void) => act(async () => { fn(); });
  return { audio, timers, hook: () => hook, run, finished: () => finished, view };
}

test("playing from the first interval starts its file at the current rate, mute and volume", async () => {
  const t = await setup();
  await t.run(() => { t.hook().setRate(1.5); t.hook().setMuted(true); t.hook().setVolume(0.4); });
  await t.run(() => t.hook().playFrom(0));
  assert.deepEqual(t.audio.played, ["/audio/a.wav"]);
  assert.equal(t.audio.playbackRate, 1.5);
  assert.equal(t.audio.muted, true);
  assert.equal(t.audio.volume, 0.4);
  assert.equal(t.hook().playing, true);
  assert.equal(t.hook().activeIndex, 0);
  await t.view.cleanup();
});

test("when a speech file ends the next interval starts; a silent gap waits its length, then the next file plays", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(0));
  await t.run(() => t.audio.emit("ended"));
  assert.equal(t.hook().activeIndex, 1, "the gap is active");
  assert.ok(t.audio.pauses >= 1, "audio is paused during the gap");
  assert.equal(t.timers.pending.length, 1);
  assert.equal(t.timers.pending[0].ms, 1000);
  await t.run(() => t.timers.fireNext());
  assert.equal(t.hook().activeIndex, 2);
  assert.deepEqual(t.audio.played, ["/audio/a.wav", "/audio/b.wav"]);
  await t.view.cleanup();
});

test("the gap waits less at a faster rate and never less than 0.2 seconds", async () => {
  const t = await setup();
  await t.run(() => t.hook().setRate(2));
  await t.run(() => t.hook().playFrom(1));
  assert.equal(t.timers.pending[0].ms, 500);
  await t.view.cleanup();
  const short = await setup([{ start_time: 0, end_time: 0.05, duration: 0.05 }]);
  await short.run(() => short.hook().playFrom(0));
  assert.equal(short.timers.pending[0].ms, 200);
  await short.view.cleanup();
});

test("an interval flagged as not speech is treated as a gap even if it has a file", async () => {
  const t = await setup([NOT_SPEECH]);
  await t.run(() => t.hook().playFrom(0));
  assert.deepEqual(t.audio.played, []);
  assert.equal(t.timers.pending.length, 1);
  await t.view.cleanup();
});

test("after the last interval, playing stops, the position resets and the finish callback fires", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(2));
  await t.run(() => t.audio.emit("ended"));
  assert.equal(t.hook().playing, false);
  assert.equal(t.hook().activeIndex, null);
  assert.equal(t.hook().currentTime, 0);
  assert.equal(t.finished(), 1);
  await t.view.cleanup();
});

test("the position follows the file: the interval's start plus how far the file has played", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(2));
  t.audio.currentTime = 1.25;
  await t.run(() => t.audio.emit("timeupdate"));
  assert.equal(t.hook().currentTime, 4.25);
  await t.view.cleanup();
});

test("pausing stops the file and the gap timer; playing again restarts the active interval", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(1));
  assert.equal(t.timers.pending.length, 1);
  await t.run(() => t.hook().toggle());
  assert.equal(t.hook().playing, false);
  assert.equal(t.timers.pending.length, 0, "the gap timer is cancelled");
  await t.run(() => t.hook().toggle());
  assert.equal(t.hook().playing, true);
  assert.equal(t.hook().activeIndex, 1);
  await t.view.cleanup();
});

test("toggling with nothing active starts from the first interval", async () => {
  const t = await setup();
  await t.run(() => t.hook().toggle());
  assert.equal(t.hook().activeIndex, 0);
  assert.deepEqual(t.audio.played, ["/audio/a.wav"]);
  await t.view.cleanup();
});

test("rate, mute and volume reach the file while it plays", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(0));
  await t.run(() => { t.hook().setRate(0.75); t.hook().setMuted(true); t.hook().setVolume(0.2); });
  assert.deepEqual([t.audio.playbackRate, t.audio.muted, t.audio.volume], [0.75, true, 0.2]);
  assert.deepEqual([t.hook().rate, t.hook().muted, t.hook().volume], [0.75, true, 0.2]);
  await t.view.cleanup();
});

test("previous never goes before the first interval and next never past the last", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(0));
  await t.run(() => t.hook().previous());
  assert.equal(t.hook().activeIndex, 0);
  await t.run(() => t.hook().playFrom(2));
  await t.run(() => t.hook().next());
  assert.equal(t.hook().activeIndex, 2);
  await t.view.cleanup();
});

test("seeking into a speech interval loads its file and jumps to the offset; into a gap while playing it starts that gap", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(0));
  await t.run(() => t.hook().seek(4));
  assert.equal(t.hook().activeIndex, 2);
  assert.equal(t.audio.src, "/audio/b.wav");
  assert.equal(t.audio.currentTime, 1);
  assert.equal(t.hook().currentTime, 4);
  await t.run(() => t.hook().seek(2.5));
  assert.equal(t.hook().activeIndex, 1);
  assert.equal(t.timers.pending.length, 1, "the gap is running");
  await t.view.cleanup();
});

test("unmounting stops the file, clears the timer and removes the listeners", async () => {
  const t = await setup();
  await t.run(() => t.hook().playFrom(1));
  assert.equal(t.timers.pending.length, 1);
  await t.view.cleanup();
  assert.equal(t.timers.pending.length, 0);
  assert.equal(t.audio.src, "");
  assert.equal(t.audio.listenerCount(), 0);
  assert.ok(t.audio.pauses >= 1);
});
