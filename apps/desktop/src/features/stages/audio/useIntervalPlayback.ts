import React from "react";

/** The parts of an audio interval that playback needs. */
export interface PlaybackInterval {
  start_time?: number;
  end_time?: number;
  duration?: number;
  audio_file_uri?: string;
  is_speech?: boolean;
}

/** The parts of HTMLAudioElement the hook uses, so tests can supply a stand-in. */
export interface AudioLike {
  src: string;
  playbackRate: number;
  muted: boolean;
  volume: number;
  currentTime: number;
  play(): Promise<void>;
  pause(): void;
  addEventListener(type: "timeupdate" | "ended", listener: () => void): void;
  removeEventListener(type: "timeupdate" | "ended", listener: () => void): void;
}

export interface Timers {
  set(fn: () => void, ms: number): unknown;
  clear(handle: unknown): void;
}

export interface PlaybackOptions {
  urlFor: (interval: PlaybackInterval, index: number) => string;
  createAudio?: () => AudioLike;
  timers?: Timers;
  /** Called when the last interval has finished. */
  onFinished?: () => void;
}

const BROWSER_TIMERS: Timers = { set: (fn, ms) => window.setTimeout(fn, ms), clear: (h) => window.clearTimeout(h as number) };

const isSpeech = (iv: PlaybackInterval) => Boolean(iv.audio_file_uri && iv.is_speech !== false);

/**
 * The master player: plays the intervals of an audio timeline one after another with one audio element.
 * A speech interval plays its file and the next interval starts when the file ends; a silent interval waits for its
 * length (at the current rate, at least 0.2 seconds). Everything is released when the component unmounts.
 */
export function useIntervalPlayback(intervals: PlaybackInterval[], options: PlaybackOptions) {
  const [playing, setPlayingState] = React.useState(false);
  const [activeIndex, setActiveState] = React.useState<number | null>(null);
  const [currentTime, setCurrentTime] = React.useState(0);
  const [rate, setRateState] = React.useState(1);
  const [volume, setVolumeState] = React.useState(1);
  const [muted, setMutedState] = React.useState(false);

  // Handlers fire later (a file ends, a timer elapses), so they read the latest values from here.
  const live = React.useRef({ intervals, options, playing: false, active: null as number | null, rate: 1, volume: 1, muted: false });
  live.current.intervals = intervals;
  live.current.options = options;

  const audioRef = React.useRef<AudioLike | null>(null);
  const timerRef = React.useRef<unknown>(null);
  const playAtRef = React.useRef<(index: number) => void>(() => {});
  const timers = () => live.current.options.timers ?? BROWSER_TIMERS;

  const setPlaying = (value: boolean) => { live.current.playing = value; setPlayingState(value); };
  const setActive = (value: number | null) => { live.current.active = value; setActiveState(value); };
  const clearTimer = () => { if (timerRef.current !== null) { timers().clear(timerRef.current); timerRef.current = null; } };

  playAtRef.current = (index: number) => {
    clearTimer();
    const list = live.current.intervals;
    if (index < 0 || index >= list.length) {
      setPlaying(false);
      setActive(null);
      setCurrentTime(0);
      live.current.options.onFinished?.();
      return;
    }
    setActive(index);
    setPlaying(true);
    const iv = list[index];
    const audio = audioRef.current;
    setCurrentTime(iv.start_time ?? 0);
    if (isSpeech(iv) && audio) {
      audio.src = live.current.options.urlFor(iv, index);
      audio.playbackRate = live.current.rate;
      audio.muted = live.current.muted;
      audio.volume = live.current.volume;
      audio.play().catch(() => {}); // the browser may refuse to start sound until the person has interacted
    } else {
      audio?.pause();
      const seconds = Math.max(0.2, (iv.end_time ?? 0) - (iv.start_time ?? 0) || iv.duration || 0.5);
      timerRef.current = timers().set(() => { timerRef.current = null; playAtRef.current(index + 1); }, (seconds / live.current.rate) * 1000);
    }
  };

  React.useEffect(() => {
    const audio = (live.current.options.createAudio ?? (() => new Audio() as unknown as AudioLike))();
    audioRef.current = audio;
    const onTime = () => {
      const index = live.current.active;
      const iv = index === null ? undefined : live.current.intervals[index];
      if (iv) setCurrentTime((iv.start_time ?? 0) + (audio.currentTime || 0));
    };
    const onEnded = () => { if (live.current.active !== null) playAtRef.current(live.current.active + 1); };
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("ended", onEnded);
      clearTimer();
      audio.pause();
      audio.src = "";
      audioRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const pause = () => {
    setPlaying(false);
    clearTimer();
    audioRef.current?.pause();
  };
  const toggle = () => {
    if (live.current.playing) { pause(); return; }
    const active = live.current.active;
    playAtRef.current(active !== null && active < live.current.intervals.length ? active : 0);
  };
  const seek = (seconds: number) => {
    setCurrentTime(seconds);
    const list = live.current.intervals;
    const index = list.findIndex((iv) => (iv.start_time ?? 0) <= seconds && seconds <= (iv.end_time ?? 0));
    if (index === -1) return;
    const iv = list[index];
    setActive(index);
    const audio = audioRef.current;
    if (isSpeech(iv) && audio) {
      const url = live.current.options.urlFor(iv, index);
      if (audio.src !== url) audio.src = url;
      audio.currentTime = Math.max(0, seconds - (iv.start_time ?? 0));
      if (live.current.playing) audio.play().catch(() => {});
    } else if (live.current.playing) {
      playAtRef.current(index);
    }
  };

  return {
    playing, activeIndex, currentTime, rate, volume, muted,
    play: () => { if (!live.current.playing) toggle(); },
    pause,
    toggle,
    playFrom: (index: number) => playAtRef.current(index),
    next: () => playAtRef.current(Math.min(live.current.intervals.length - 1, (live.current.active ?? 0) + 1)),
    previous: () => playAtRef.current(Math.max(0, (live.current.active ?? 0) - 1)),
    seek,
    setRate: (value: number) => { live.current.rate = value; setRateState(value); if (audioRef.current) audioRef.current.playbackRate = value; },
    setVolume: (value: number) => { live.current.volume = value; setVolumeState(value); if (audioRef.current) audioRef.current.volume = value; },
    setMuted: (value: boolean) => { live.current.muted = value; setMutedState(value); if (audioRef.current) audioRef.current.muted = value; },
  };
}
