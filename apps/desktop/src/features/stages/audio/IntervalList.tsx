import React from "react";
import { Pause, Play, RotateCw } from "lucide-react";
import type { AudioInterval, CharacterEntity } from "@panelflow/shared-types";
import { SvgAudioEqualizer } from "@panelflow/ui";
import { Button, Chip, GlassPanel } from "@panelflow/ui-v2";

export interface IntervalListProps {
  intervals: AudioInterval[];
  characters: CharacterEntity[];
  activeIndex: number | null;
  playing: boolean;
  /** Segment ids being regenerated right now. */
  regenerating: ReadonlySet<string>;
  onPlay: (index: number) => void;
  onPause: () => void;
  onRegenerate: (segmentId: string) => void;
}

const isSpeech = (iv: AudioInterval) => Boolean(iv.audio_file_uri && (iv as any).is_speech !== false);

/** Who speaks: the character's name when known, otherwise the id without its "char_" prefix. */
function speakerName(iv: AudioInterval, characters: CharacterEntity[]): string {
  const id: string = (iv as any).character_id || (iv as any).speaker_character_id || (iv as any).speaker_id || "";
  if (!id) return "";
  const known = characters.find((c) => c.character_id === id || (c as { id?: string }).id === id);
  return known?.display_name || known?.canonical_name || id.replace(/^char_/, "");
}

export const IntervalList: React.FC<IntervalListProps> = ({ intervals, characters, activeIndex, playing, regenerating, onPlay, onPause, onRegenerate }) => (
  <ol className="grid grid-cols-1 gap-3" aria-label="Takes">
    {intervals.map((iv, index) => {
      const start = iv.start_time ?? 0;
      const end = iv.end_time ?? 0;
      const duration = iv.duration ?? Math.max(0, end - start);
      const active = activeIndex === index;
      const linePlaying = active && playing;
      const ring = active ? "border-accent ring-1 ring-accent" : "";
      if (!isSpeech(iv)) {
        return (
          <li key={iv.interval_id || index} id={`audio-interval-${index}`}>
            <div className={`flex flex-wrap items-center justify-between gap-2 rounded-card border border-dashed border-edge px-4 py-2.5 text-sm text-fg-dim ${ring}`}>
              <span>{`Silence · ${duration.toFixed(2)}s`}<span className="ml-2 font-data text-xs text-fg-faint">{`${start.toFixed(2)}s to ${end.toFixed(2)}s`}</span></span>
              <Button size="sm" variant="ghost" aria-label={`Play from take ${index + 1}`} icon={<Play size={12} />} onClick={() => onPlay(index)}>Play from here</Button>
            </div>
          </li>
        );
      }
      const cue: string = (iv as any).cue_text || (iv as any).text || "";
      const speaker = speakerName(iv, characters);
      const gain = iv.gain_db ?? 0;
      const busy = Boolean(iv.script_segment_id && regenerating.has(iv.script_segment_id));
      return (
        <li key={iv.interval_id || index} id={`audio-interval-${index}`}>
          <GlassPanel blur={false} className={`grid grid-cols-1 gap-3 p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center ${ring}`}>
            <div className="grid min-w-0 gap-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-fg">{`Take ${index + 1}`}</span>
                {speaker && <Chip tone="accent">{speaker}</Chip>}
                <span className="font-data text-xs text-fg-dim">{`${start.toFixed(2)}s to ${end.toFixed(2)}s (${duration.toFixed(2)}s)`}</span>
                <span className="font-data text-xs text-fg-faint">{`${gain >= 0 ? "+" : ""}${gain} dB`}</span>
              </div>
              {cue && <p className="text-sm italic text-fg">{`"${cue}"`}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SvgAudioEqualizer isPlaying={linePlaying} theme={linePlaying ? "cyan" : "indigo"} />
              {linePlaying ? (
                <Button size="sm" variant="primary" aria-label={`Pause take ${index + 1}`} icon={<Pause size={12} />} onClick={onPause}>Pause</Button>
              ) : (
                <Button size="sm" variant="secondary" aria-label={`Play take ${index + 1}`} icon={<Play size={12} />} onClick={() => onPlay(index)}>Play take</Button>
              )}
              {iv.script_segment_id && (
                <Button size="sm" variant="ghost" aria-label={`Regenerate take ${index + 1}`} loading={busy} icon={<RotateCw size={12} />} onClick={() => onRegenerate(iv.script_segment_id as string)}>Regenerate</Button>
              )}
            </div>
          </GlassPanel>
        </li>
      );
    })}
  </ol>
);
