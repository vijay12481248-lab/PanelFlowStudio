import React from "react";
import { Film, FolderOpen } from "lucide-react";
import { Button, GlassPanel, Input, Select, Switch } from "@panelflow/ui-v2";
import { EFFECTS, VIDEO_ENGINES } from "../motion/motionModel";
import type { ProfileOption, RenderSettings } from "./renderModel";

export interface RenderSettingsPanelProps {
  settings: RenderSettings;
  onChange: (patch: Partial<RenderSettings>) => void;
  profiles: ProfileOption[];
  destinations: Array<{ id: string; label: string; path: string }>;
  onBrowseFolder: () => void;
  onBrowseFile: () => void;
  pickerError: string | null;
}

const PACING = [{ label: "Brisk", seconds: 2 }, { label: "Standard", seconds: 3 }, { label: "Comfortable", seconds: 4 }, { label: "Relaxed", seconds: 5.5 }];
const SPEEDS = [0.85, 0.92, 1, 1.1, 1.2];

const Section: React.FC<{ title: string; hint?: string; children: React.ReactNode }> = ({ title, hint, children }) => (
  <GlassPanel blur={false} className="grid grid-cols-1 content-start gap-3 p-4">
    <div className="grid gap-0.5"><h3 className="font-display text-sm font-semibold text-fg">{title}</h3>{hint && <p className="text-xs text-fg-dim">{hint}</p>}</div>
    {children}
  </GlassPanel>
);

const Choice: React.FC<{ pressed: boolean; onClick: () => void; children: string; hint?: string }> = ({ pressed, onClick, children, hint }) => (
  <Button size="sm" variant={pressed ? "primary" : "secondary"} aria-label={children} aria-pressed={pressed} onClick={onClick} className="h-auto flex-col items-start py-1.5">
    <span>{children}</span>{hint && <span className="text-[11px] font-normal opacity-80">{hint}</span>}
  </Button>
);

/** Everything that shapes the output: where it goes, pacing, framing, voice speed, motion and the audio mix. */
export const RenderSettingsPanel: React.FC<RenderSettingsPanelProps> = ({ settings, onChange, profiles, destinations, onBrowseFolder, onBrowseFile, pickerError }) => (
  <div className="grid grid-cols-1 gap-4">
    <Section title="Where the video is saved" hint="Choose a folder or an exact file. Leave it empty to keep the video in the project.">
      <div className="flex flex-wrap items-center gap-2">
        <Input aria-label="Save location" className="min-w-0 flex-1 font-data text-xs" value={settings.saveLocation} placeholder="Choose or paste a folder or file path" onChange={(e) => onChange({ saveLocation: e.target.value })} />
        <Button variant="secondary" size="sm" icon={<FolderOpen size={14} />} onClick={onBrowseFolder}>Browse folder</Button>
        <Button variant="secondary" size="sm" icon={<Film size={14} />} onClick={onBrowseFile}>Save as file</Button>
      </div>
      {destinations.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-fg-faint">Quick folders</span>
          {destinations.map((d) => <Button key={d.id} size="sm" variant={settings.saveLocation === d.path ? "primary" : "ghost"} aria-pressed={settings.saveLocation === d.path} title={d.path} onClick={() => onChange({ saveLocation: d.path })}>{d.label}</Button>)}
        </div>
      )}
      {pickerError && <p role="alert" className="text-sm text-bad">{pickerError}</p>}
    </Section>

    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Section title="Panel display time" hint="Each panel stays on screen at least this long.">
        <div className="flex flex-wrap gap-2">{PACING.map((p) => <Choice key={p.label} pressed={settings.minPanelDuration === p.seconds} hint={`${p.seconds}s`} onClick={() => onChange({ minPanelDuration: p.seconds })}>{p.label}</Choice>)}</div>
        <label className="grid gap-1 text-xs text-fg-dim">
          {`${settings.minPanelDuration.toFixed(1)}s per panel`}
          <input type="range" aria-label="Panel display time" min={1.5} max={8} step={0.5} value={settings.minPanelDuration} onChange={(e) => onChange({ minPanelDuration: parseFloat(e.target.value) })} className="h-1.5 w-full accent-accent" />
        </label>
      </Section>
      <Section title="Panel framing and voice speed">
        <div className="flex flex-wrap gap-2">
          <Choice pressed={settings.panelZoomMode === "fit"} hint="No crop, dialogue never cut off" onClick={() => onChange({ panelZoomMode: "fit" })}>Fit entire artwork</Choice>
          <Choice pressed={settings.panelZoomMode === "motion"} hint="Slow zoom and pan on each panel" onClick={() => onChange({ panelZoomMode: "motion" })}>Cinematic zoom</Choice>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Narration speed">
          {SPEEDS.map((s) => <Button key={s} size="sm" variant={settings.narrationSpeed === s ? "primary" : "secondary"} aria-pressed={settings.narrationSpeed === s} onClick={() => onChange({ narrationSpeed: s })}>{`${s.toFixed(2)}x`}</Button>)}
        </div>
      </Section>
    </div>

    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Section title="Motion">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">Motion engine
          <Select aria-label="Motion engine" className="h-9 text-sm" value={settings.videoEngine} onChange={(e) => onChange({ videoEngine: e.target.value as RenderSettings["videoEngine"] })}>{VIDEO_ENGINES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
        </label>
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">Motion graphics overlay
          <Select aria-label="Motion graphics overlay" className="h-9 text-sm" value={settings.motionFx} onChange={(e) => onChange({ motionFx: e.target.value })}>{EFFECTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
        </label>
      </Section>
      <Section title="Output and audio">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">Output profile
          <Select aria-label="Output profile" className="h-9 text-sm" value={settings.profile} disabled={profiles.length === 0} onChange={(e) => onChange({ profile: e.target.value })}>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.hint ? `${p.label} (${p.hint})` : p.label}</option>)}
          </Select>
        </label>
        <label className="grid gap-1 text-xs text-fg-dim">{`Music volume ${settings.bgmVolumeDb} dB`}
          <input type="range" aria-label="Music volume" min={-30} max={0} step={1} value={settings.bgmVolumeDb} onChange={(e) => onChange({ bgmVolumeDb: parseFloat(e.target.value) })} className="h-1.5 w-full accent-accent" />
        </label>
        <label className="grid gap-1 text-xs text-fg-dim">{`Dialogue gain ${settings.dialogueGainDb >= 0 ? "+" : ""}${settings.dialogueGainDb} dB`}
          <input type="range" aria-label="Dialogue gain" min={-6} max={6} step={0.5} value={settings.dialogueGainDb} onChange={(e) => onChange({ dialogueGainDb: parseFloat(e.target.value) })} className="h-1.5 w-full accent-accent" />
        </label>
        <Switch checked={settings.subtitles} onCheckedChange={(subtitles) => onChange({ subtitles })} label="Subtitles" />
      </Section>
    </div>
  </div>
);
