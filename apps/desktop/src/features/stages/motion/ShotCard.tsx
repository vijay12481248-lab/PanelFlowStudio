import React from "react";
import { Play } from "lucide-react";
import type { Panel } from "@panelflow/shared-types";
import { SvgCameraFramingVisualizer } from "@panelflow/ui";
import { Button, Chip, GlassPanel, Input, Select } from "@panelflow/ui-v2";
import { addTag, CAMERA_MOVES, EFFECTS, INTENSITIES, QUICK_TAGS, type ShotView } from "./motionModel";

export interface PreviewRequest { panelId: string; motion: string; prompt: string; intensity: string; fx: string }

export interface ShotCardProps {
  shot: ShotView;
  panel: Panel | undefined;
  panelImageUrl: string | undefined;
  /** Makes a short H3 preview of the shot. Returns the video address, or null when the engine sent none. Throws on failure. */
  onPreview: (request: PreviewRequest) => Promise<string | null>;
}

const SMALL = "h-8 text-xs";

/** One planned shot: its camera path, timing and caption, and an optional preview that is never saved to the plan. */
export const ShotCard: React.FC<ShotCardProps> = ({ shot, panel, panelImageUrl, onPreview }) => {
  const [motion, setMotion] = React.useState("push_in");
  const [intensity, setIntensity] = React.useState("balanced");
  const [fx, setFx] = React.useState("none");
  const [prompt, setPrompt] = React.useState("");
  const [videoUrl, setVideoUrl] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const running = React.useRef(false);

  const preview = async () => {
    if (!panel || running.current) return;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      const url = await onPreview({ panelId: panel.id, motion, prompt, intensity, fx });
      if (url) setVideoUrl(url);
    } catch {
      setError("Couldn't make the preview. Check that the video engine is running, then try again.");
    } finally { running.current = false; setBusy(false); }
  };

  return (
    <GlassPanel blur={false} data-shot-key={shot.key} className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
      <SvgCameraFramingVisualizer
        imageUrl={panelImageUrl}
        startCamera={shot.startCamera}
        endCamera={shot.endCamera}
        motionType={shot.motionType}
        durationSec={shot.durationSec}
        easing={shot.easing}
      />
      <div className="grid min-w-0 grid-cols-1 content-start gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-fg">{`Shot ${shot.index + 1}`}</span>
          {shot.title && <Chip>{shot.title}</Chip>}
          <Chip tone="accent">{shot.motionType}</Chip>
          <span className="font-data text-xs text-fg-dim">{`${shot.startSec.toFixed(2)}s to ${shot.endSec.toFixed(2)}s (${shot.durationSec.toFixed(2)}s)`}</span>
          {shot.transition && <Chip>{shot.transition}</Chip>}
          {panel && <span className="ml-auto text-xs text-fg-faint">{`Panel ${panel.sequence}`}</span>}
        </div>
        {shot.caption && (
          <p className="rounded-ctl border border-edge bg-glass p-2.5 text-sm text-fg">
            <span className="mr-2 font-semibold text-info">{shot.caption.speaker}</span>
            <span className="italic text-fg-dim">{`"${shot.caption.text}"`}</span>
          </p>
        )}
        <p className="font-data text-xs text-fg-dim">{`Zoom ${shot.startCamera.zoom.toFixed(2)}x to ${shot.endCamera.zoom.toFixed(2)}x · easing ${shot.easing}`}</p>

        <div className="grid grid-cols-1 gap-2 border-t border-edge pt-3">
          <p className="text-xs text-fg-faint">Preview only. These choices are not saved to the plan.</p>
          <div className="flex flex-wrap gap-2">
            <Select aria-label="Camera move" className={SMALL} value={motion} onChange={(e) => setMotion(e.target.value)}>
              {CAMERA_MOVES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
            <Select aria-label="Intensity" className={SMALL} value={intensity} onChange={(e) => setIntensity(e.target.value)}>
              {INTENSITIES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
            <Select aria-label="Effect" className={SMALL} value={fx} onChange={(e) => setFx(e.target.value)}>
              {EFFECTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {QUICK_TAGS.map((tag) => (
              <button key={tag} type="button" onClick={() => setPrompt((current) => addTag(current, tag))} className="rounded-full border border-edge bg-glass px-2.5 py-1 text-xs text-fg-dim hover:text-fg focus-visible:outline-2 focus-visible:outline-info">{tag}</button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input aria-label="Motion prompt" className="h-9 min-w-0 flex-1 text-xs" placeholder="Motion details, for example glowing aura or wind in hair" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            <Button variant="secondary" size="sm" icon={<Play size={12} />} loading={busy} disabled={!panel} onClick={() => void preview()}>Generate preview</Button>
          </div>
          {!panel && <p className="text-xs text-warn">No panel found for this shot, so it can't be previewed.</p>}
          {error && <p role="alert" className="text-xs text-bad">{error}</p>}
          {videoUrl && <video src={videoUrl} controls loop className="max-h-48 w-full rounded-ctl border border-edge bg-ink object-contain" />}
        </div>
      </div>
    </GlassPanel>
  );
};
