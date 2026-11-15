import React from "react";
import { Pause, Play, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";
import { SvgAudioEqualizer } from "@panelflow/ui";
import { Button, GlassPanel, IconButton } from "@panelflow/ui-v2";
import { formatClock } from "../motion/motionModel";
import type { useIntervalPlayback } from "./useIntervalPlayback";

export interface MasterPlayerProps {
  playback: ReturnType<typeof useIntervalPlayback>;
  totalSeconds: number;
  /** What the active interval says, for the now-playing line. */
  nowPlaying: string | null;
  count: number;
}

const RATES = [0.75, 1, 1.25, 1.5];
const INTERACTIVE = "button, a, input, textarea, select, [role='dialog'], [contenteditable='true']";

/** Plays the whole voice track in order. The space bar toggles play, unless the person is using another control. */
export const MasterPlayer: React.FC<MasterPlayerProps> = ({ playback, totalSeconds, nowPlaying, count }) => {
  const toggleRef = React.useRef(playback.toggle);
  toggleRef.current = playback.toggle;
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      const target = event.target as Element | null;
      if (target && target.closest?.(INTERACTIVE)) return;
      event.preventDefault();
      toggleRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { playing, activeIndex, currentTime, rate, muted, volume } = playback;
  return (
    <GlassPanel blur={false} className="sticky top-2 z-10 grid grid-cols-1 gap-3 p-3 md:grid-cols-[minmax(0,220px)_minmax(0,1fr)_auto] md:items-center" role="group" aria-label="Voice track player">
      <div className="flex min-w-0 items-center gap-3">
        <SvgAudioEqualizer isPlaying={playing} theme="cyan" className="shrink-0" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-fg">{activeIndex !== null ? `Take ${activeIndex + 1}: ${nowPlaying || "Silence"}` : "Voice track"}</p>
          <p className="font-data text-xs text-fg-dim">{`${formatClock(currentTime)} / ${formatClock(totalSeconds)}`}</p>
        </div>
      </div>
      <div className="grid min-w-0 gap-2">
        <div className="flex items-center justify-center gap-2">
          <IconButton label="Previous take" disabled={activeIndex === 0} onClick={playback.previous}><SkipBack size={16} /></IconButton>
          <IconButton label={playing ? "Pause" : "Play all"} className="size-11 border-accent bg-accent text-white hover:bg-accent" onClick={playback.toggle}>{playing ? <Pause size={18} /> : <Play size={18} />}</IconButton>
          <IconButton label="Next take" disabled={activeIndex === count - 1} onClick={playback.next}><SkipForward size={16} /></IconButton>
        </div>
        <input
          type="range"
          aria-label="Position"
          min={0}
          max={Math.max(1, totalSeconds)}
          step={0.05}
          value={Math.min(totalSeconds, currentTime)}
          onChange={(e) => playback.seek(parseFloat(e.target.value))}
          className="h-1.5 w-full cursor-pointer accent-accent"
        />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <div className="flex items-center gap-1" role="group" aria-label="Speed">
          {RATES.map((r) => <Button key={r} size="sm" variant={rate === r ? "primary" : "ghost"} aria-pressed={rate === r} aria-label={`Speed ${r}x`} onClick={() => playback.setRate(r)}>{`${r}x`}</Button>)}
        </div>
        <IconButton label={muted ? "Unmute" : "Mute"} onClick={() => playback.setMuted(!muted)}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</IconButton>
        <input type="range" aria-label="Volume" min={0} max={1} step={0.05} value={volume} onChange={(e) => playback.setVolume(parseFloat(e.target.value))} className="h-1.5 w-20 cursor-pointer accent-accent" />
      </div>
    </GlassPanel>
  );
};
