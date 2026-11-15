import React from "react";
import { ArrowDown, ArrowUp, Dices, Plus, Redo2, Trash2, Undo2 } from "lucide-react";
import { SliderRow } from "../color/controls";
import { EFFECT_LABELS, changesPicture, newEffect, type Effect, type EffectType, type FusionState } from "./effects";

const TYPES: EffectType[] = ["glow", "vignette", "grain", "blur", "text"];

const Chip: React.FC<{ on?: boolean; onClick: () => void; children: React.ReactNode }> = ({ on, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${on ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim hover:text-fg"}`}
  >
    {children}
  </button>
);

const IconBtn: React.FC<{ title: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }> = ({ title, onClick, disabled, children }) => (
  <button
    type="button"
    title={title}
    aria-label={title}
    onClick={onClick}
    disabled={disabled}
    className="flex h-6 w-6 items-center justify-center rounded-md border border-edge bg-flat text-fg-dim transition-colors hover:text-fg disabled:pointer-events-none disabled:opacity-35"
  >
    {children}
  </button>
);

const ColorRow: React.FC<{ label: string; value: string; onChange: (v: string) => void }> = ({ label, value, onChange }) => (
  <label className="grid grid-cols-[5.5rem_1fr] items-center gap-2 text-[11px] text-fg-dim">
    <span>{label}</span>
    <input type="color" value={value} aria-label={label} onChange={(e) => onChange(e.target.value)} className="h-6 w-12 cursor-pointer rounded-md border border-edge bg-flat p-0.5" />
  </label>
);

export interface FusionInspectorProps {
  fusion: FusionState;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onChange: (next: FusionState, key: string) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
}

export const FusionInspector: React.FC<FusionInspectorProps> = ({ fusion, selectedId, onSelect, onChange, canUndo, canRedo, onUndo, onRedo }) => {
  const selected = fusion.effects.find((e) => e.id === selectedId) ?? null;

  const withEffects = (effects: Effect[], key = "") => onChange({ effects }, key);
  const edit = (key: string, patch: Record<string, any>) =>
    withEffects(fusion.effects.map((e) => (e.id === selectedId ? { ...e, params: { ...e.params, ...patch } } : e)), key);
  const add = (type: EffectType) => {
    const e = newEffect(type);
    withEffects([...fusion.effects, e]);
    onSelect(e.id);
  };
  const remove = (id: string) => {
    withEffects(fusion.effects.filter((e) => e.id !== id));
    if (selectedId === id) onSelect(null);
  };
  const toggle = (id: string) => withEffects(fusion.effects.map((e) => (e.id === id ? { ...e, enabled: !e.enabled } : e)));
  const move = (id: string, dir: -1 | 1) => {
    const i = fusion.effects.findIndex((e) => e.id === id), j = i + dir;
    if (i < 0 || j < 0 || j >= fusion.effects.length) return;
    const next = [...fusion.effects];
    [next[i], next[j]] = [next[j], next[i]];
    withEffects(next);
  };
  const label = (e: Effect) => (e.type === "text" ? `Text · ${String(e.params.text || "").split("\n")[0].slice(0, 14) || "empty"}` : EFFECT_LABELS[e.type]);

  const p = selected?.params ?? {};
  const num = (key: string) => (v: number) => edit(`s:${key}`, { [key]: v });

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex flex-col gap-2 border-b border-edge/70 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-fg-dim">Effects (run in order)</span>
          <div className="flex items-center gap-1.5">
            <IconBtn title="Undo effect change" onClick={onUndo} disabled={!canUndo}><Undo2 className="h-3.5 w-3.5" /></IconBtn>
            <IconBtn title="Redo effect change" onClick={onRedo} disabled={!canRedo}><Redo2 className="h-3.5 w-3.5" /></IconBtn>
          </div>
        </div>
        {fusion.effects.length === 0 ? (
          <p className="text-[11px] text-fg-faint">No effects yet. Add one below; they are applied to the picture after the grade and the cut.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {fusion.effects.map((e, i) => (
              <li key={e.id} className={`flex items-center gap-1 rounded-md border pl-1.5 pr-1 text-[11px] ${e.id === selectedId ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim"}`}>
                <button type="button" aria-label={`${e.enabled ? "Switch off" : "Switch on"} ${label(e)}`} title={e.enabled ? "Switch this effect off" : "Switch this effect on"} onClick={() => toggle(e.id)} className={`h-2.5 w-2.5 shrink-0 rounded-full border ${e.enabled ? "border-ok bg-ok" : "border-fg-faint"}`} />
                <button type="button" onClick={() => onSelect(e.id)} className="min-w-0 flex-1 truncate py-1.5 text-left">
                  {label(e)}
                  {e.enabled && !changesPicture(e) ? <span className="ml-1 text-fg-faint">(no effect)</span> : null}
                </button>
                <IconBtn title={`Move ${label(e)} up`} onClick={() => move(e.id, -1)} disabled={i === 0}><ArrowUp className="h-3 w-3" /></IconBtn>
                <IconBtn title={`Move ${label(e)} down`} onClick={() => move(e.id, 1)} disabled={i === fusion.effects.length - 1}><ArrowDown className="h-3 w-3" /></IconBtn>
                <IconBtn title={`Delete ${label(e)}`} onClick={() => remove(e.id)}><Trash2 className="h-3 w-3" /></IconBtn>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          <Plus className="h-3.5 w-3.5 text-fg-faint" aria-hidden="true" />
          {TYPES.map((t) => <Chip key={t} onClick={() => add(t)}>{EFFECT_LABELS[t]}</Chip>)}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {!selected && <p className="text-[11px] text-fg-faint">Select an effect to change it.</p>}

        {selected?.type === "glow" && (
          <div className="flex flex-col gap-2">
            <SliderRow label="Size" value={Number(p.size)} min={1} max={18} step={0.5} def={10} digits={1} onChange={num("size")} />
            <SliderRow label="Intensity" value={Number(p.intensity)} min={0.1} max={3} step={0.05} def={1.3} onChange={num("intensity")} />
            <p className="text-[11px] text-fg-faint">A soft bloom: a brightened, blurred copy laid over the picture (ChronoFlow's Glow).</p>
          </div>
        )}

        {selected?.type === "vignette" && (
          <div className="flex flex-col gap-2">
            <SliderRow label="Radius" value={Number(p.radius)} min={0.1} max={1.5} step={0.01} def={0.8} onChange={num("radius")} />
            <SliderRow label="Softness" value={Number(p.softness)} min={0.05} max={1} step={0.01} def={0.5} onChange={num("softness")} />
            <SliderRow label="Opacity" value={Number(p.opacity)} min={0} max={1} step={0.01} def={0.7} onChange={num("opacity")} />
            <ColorRow label="Colour" value={String(p.color)} onChange={(v) => edit("c:color", { color: v })} />
          </div>
        )}

        {selected?.type === "grain" && (
          <div className="flex flex-col gap-2">
            <SliderRow label="Amount" value={Number(p.intensity)} min={0} max={1} step={0.01} def={0.2} onChange={num("intensity")} />
            <SliderRow label="Size" value={Number(p.size)} min={1} max={6} step={0.1} def={1.5} digits={1} onChange={num("size")} />
            <button type="button" onClick={() => edit("", { seed: Math.floor(Math.random() * 100000) })} className="flex items-center gap-2 self-start rounded-md border border-edge bg-flat px-2.5 py-1 text-[11px] text-fg-dim transition-colors hover:text-fg">
              <Dices className="h-3.5 w-3.5" />
              <span>New grain pattern</span>
            </button>
            <p className="text-[11px] text-fg-faint">The pattern is fixed, so the preview and the export are the same picture.</p>
          </div>
        )}

        {selected?.type === "blur" && (
          <div className="flex flex-col gap-2">
            <SliderRow label="Radius" value={Number(p.radius)} min={0} max={24} step={0.5} def={4} digits={1} onChange={num("radius")} />
          </div>
        )}

        {selected?.type === "text" && (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-[11px] text-fg-dim">
              <span>Text (one line per row)</span>
              <textarea
                value={String(p.text)}
                rows={3}
                aria-label="Text"
                onChange={(e) => edit("t:text", { text: e.target.value })}
                className="w-full rounded-lg border border-edge bg-flat px-3 py-2 text-xs text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none"
              />
            </label>
            <p className="text-[11px] text-fg-faint">Click or drag on the picture to place the text.</p>
            <div className="flex gap-1.5">
              {(["left", "center", "right"] as const).map((a) => <Chip key={a} on={p.align === a} onClick={() => edit("", { align: a })}>{a[0].toUpperCase() + a.slice(1)}</Chip>)}
              <Chip on={!!p.box} onClick={() => edit("", { box: !p.box })}>Box</Chip>
            </div>
            <SliderRow label="Size" value={Number(p.fontSize)} min={8} max={200} step={1} def={48} digits={0} onChange={num("fontSize")} />
            <SliderRow label="Line spacing" value={Number(p.lineSpacing)} min={0.8} max={2.5} step={0.05} def={1.2} onChange={num("lineSpacing")} />
            <ColorRow label="Colour" value={String(p.color)} onChange={(v) => edit("c:color", { color: v })} />
            <SliderRow label="Outline" value={Number(p.strokeWidth)} min={0} max={12} step={0.5} def={2} digits={1} onChange={num("strokeWidth")} />
            <ColorRow label="Outline colour" value={String(p.strokeColor)} onChange={(v) => edit("c:stroke", { strokeColor: v })} />
            <SliderRow label="Glow" value={Number(p.glowSize)} min={0} max={24} step={0.5} def={0} digits={1} onChange={num("glowSize")} />
            <ColorRow label="Glow colour" value={String(p.glowColor)} onChange={(v) => edit("c:glow", { glowColor: v })} />
          </div>
        )}
      </div>
    </div>
  );
};
