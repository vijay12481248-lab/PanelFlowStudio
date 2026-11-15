import React, { useEffect, useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Plus, Redo2, RotateCcw, Trash2, Undo2, Upload } from "lucide-react";
import { SCOPE_SIZE, TONE_COLORS, HUE_CURVE_COLOR, drawScope, type CurveSpec, type ScopeKind } from "./canvasDraw";
import { CurveEditor, SliderRow, WheelControl } from "./controls";
import { G, cloneGrade, type CurvePoints, type Grade, type GradeNode, type HueCurveKey, type LutLibrary, type ToneKey, type WheelKey } from "./grade";
import { LOOKS } from "./looks";
import { lutId } from "./lutLibrary";
import { autoBalanceCdl, type PixelData } from "./stats";

type Tab = "primaries" | "curves" | "hue" | "lut" | "scopes";
const TABS: { id: Tab; label: string }[] = [
  { id: "primaries", label: "Primaries" },
  { id: "curves", label: "Curves" },
  { id: "hue", label: "Hue / Sat" },
  { id: "lut", label: "LUT & Looks" },
  { id: "scopes", label: "Scopes" },
];

const TONES: { id: ToneKey; label: string }[] = [
  { id: "y", label: "Luma" },
  { id: "r", label: "Red" },
  { id: "g", label: "Green" },
  { id: "b", label: "Blue" },
];

const HUE_ANCHORS = [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6];
const HUE_CURVES: { id: HueCurveKey; label: string; cyclic: boolean; seed: number[]; hint: string }[] = [
  { id: "hueVsHue", label: "Hue vs Hue", cyclic: true, seed: HUE_ANCHORS, hint: "Move one colour towards another." },
  { id: "hueVsSat", label: "Hue vs Sat", cyclic: true, seed: HUE_ANCHORS, hint: "Raise or lower the saturation of one colour range." },
  { id: "hueVsLum", label: "Hue vs Lum", cyclic: true, seed: HUE_ANCHORS, hint: "Brighten or darken one colour range." },
  { id: "lumVsSat", label: "Lum vs Sat", cyclic: false, seed: [0, 0.25, 0.5, 0.75, 1], hint: "Saturate or desaturate by brightness (left shadows, right highlights)." },
];

const WHEELS: { id: WheelKey; label: string }[] = [
  { id: "lift", label: "Lift" },
  { id: "gamma", label: "Gamma" },
  { id: "gain", label: "Gain" },
  { id: "offset", label: "Offset" },
];

export interface ColorInspectorProps {
  grade: Grade;
  nodeIndex: number;
  onNodeIndex: (index: number) => void;
  onChange: (next: Grade, key: string) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  lib: LutLibrary;
  onLib: (lib: LutLibrary) => void;
  /** Show the picture without the grade. */
  bypass: boolean;
  onBypass: (value: boolean) => void;
  /** Small copy of the clean picture, for the scopes and Auto balance; null while it loads or when it cannot be read. */
  probe: PixelData | null;
  sourceError: string | null;
  table: Float32Array | null;
  onToast: (message: string) => void;
}

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
    className="flex h-7 w-7 items-center justify-center rounded-md border border-edge bg-flat text-fg-dim transition-colors hover:text-fg disabled:pointer-events-none disabled:opacity-35"
  >
    {children}
  </button>
);

export const ColorInspector: React.FC<ColorInspectorProps> = (p) => {
  const [tab, setTab] = useState<Tab>("primaries");
  const [tone, setTone] = useState<ToneKey>("y");
  const [hueCurve, setHueCurve] = useState<HueCurveKey>("hueVsHue");
  const [scope, setScope] = useState<ScopeKind>("waveform");
  const scopeCanvas = useRef<HTMLCanvasElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const index = Math.min(p.nodeIndex, p.grade.nodes.length - 1);
  const node = p.grade.nodes[index];

  // One place that edits the open node: copy the grade, change the copy, hand it back with a key so a drag is one undo step.
  const edit = (key: string, fn: (n: GradeNode) => void) => {
    const g = cloneGrade(p.grade);
    fn(g.nodes[index]);
    p.onChange(g, key);
  };
  const num = (key: keyof GradeNode & ("contrast" | "pivot" | "saturation" | "hue" | "temp" | "tint" | "boost" | "shadows" | "highlights")) =>
    (v: number) => edit(`s:${key}`, (n) => { n[key] = v; });

  const addNode = (label = "", init?: (n: GradeNode) => void) => {
    const g = cloneGrade(p.grade);
    const n = G.newNode(label);
    init?.(n);
    g.nodes.push(n);
    p.onChange(g, "");
    p.onNodeIndex(g.nodes.length - 1);
  };
  const removeNode = () => {
    if (p.grade.nodes.length <= 1) return;
    const g = cloneGrade(p.grade);
    g.nodes.splice(index, 1);
    p.onChange(g, "");
    p.onNodeIndex(Math.max(0, index - 1));
  };
  const toggleNode = (i: number) => {
    const g = cloneGrade(p.grade);
    g.nodes[i].enabled = !g.nodes[i].enabled;
    p.onChange(g, "");
  };
  const resetNode = () => edit("", (n) => { Object.assign(n, G.newNode(n.label), { id: n.id }); });

  const autoBalance = () => {
    if (!p.probe) return p.onToast(p.sourceError || "The picture is still loading.");
    const { cdl, summary } = autoBalanceCdl(p.probe);
    const g = cloneGrade(p.grade);
    let at = g.nodes.findIndex((n) => n.label === "Auto Balance");
    if (at < 0) { g.nodes.unshift(G.newNode("Auto Balance")); at = 0; }
    g.nodes[at].cdl = cdl;
    p.onChange(g, "");
    p.onNodeIndex(at);
    p.onToast(`Auto balance: ${summary}`);
  };

  const importCube = async (file: File) => {
    try {
      const lut = G.parseCube(await file.text());
      if (lut.title === "Imported LUT") lut.title = file.name.replace(/\.cube$/i, "");
      const id = lutId(lut.table);
      p.onLib({ ...p.lib, [id]: lut });
      edit("", (n) => { n.lut = { id, strength: 1 }; });
      p.onToast(`Imported LUT "${lut.title}" (${lut.size}³)`);
    } catch (err: any) {
      p.onToast(`Could not read that LUT: ${err.message}`);
    }
  };

  // Scopes show the graded picture: a small copy with the baked table applied on the CPU.
  const graded = useMemo(() => {
    if (!p.probe) return null;
    const data = new Uint8ClampedArray(p.probe.data);
    if (p.table) G.applyToPixels(data, p.table, G.LUT_SIZE);
    return { data, width: p.probe.width, height: p.probe.height };
  }, [p.probe, p.table]);
  useEffect(() => {
    if (tab === "scopes" && graded && scopeCanvas.current) drawScope(scope, scopeCanvas.current, graded);
  }, [tab, scope, graded]);

  const tonePoints = node.curves[tone];
  const toneSpec: CurveSpec = { tone: true, ymin: 0, ymax: 1, color: TONE_COLORS[tone] };
  const hueKind = HUE_CURVES.find((h) => h.id === hueCurve) ?? HUE_CURVES[0];
  const hueSpec: CurveSpec = { tone: false, ymin: -1, ymax: 1, cyclic: hueKind.cyclic, hueBar: hueKind.cyclic, seed: hueKind.seed, color: HUE_CURVE_COLOR };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Nodes: the grade is a stack that runs in order; each can be switched off */}
      <div className="flex flex-col gap-2 border-b border-edge/70 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-fg-dim">Nodes</span>
          <div className="flex items-center gap-1.5">
            <IconBtn title="Undo grade change" onClick={p.onUndo} disabled={!p.canUndo}><Undo2 className="h-3.5 w-3.5" /></IconBtn>
            <IconBtn title="Redo grade change" onClick={p.onRedo} disabled={!p.canRedo}><Redo2 className="h-3.5 w-3.5" /></IconBtn>
            <IconBtn title={p.bypass ? "Show the grade" : "Show the picture without the grade"} onClick={() => p.onBypass(!p.bypass)}>
              {p.bypass ? <EyeOff className="h-3.5 w-3.5 text-warn" /> : <Eye className="h-3.5 w-3.5" />}
            </IconBtn>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {p.grade.nodes.map((n, i) => (
            <div key={n.id} className={`flex items-center gap-1 rounded-md border pl-1.5 pr-1 text-[11px] ${i === index ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim"}`}>
              <button type="button" aria-label={`${n.enabled ? "Switch off" : "Switch on"} node ${i + 1}`} title={n.enabled ? "Switch this node off" : "Switch this node on"} onClick={() => toggleNode(i)} className={`h-2.5 w-2.5 rounded-full border ${n.enabled ? "border-ok bg-ok" : "border-fg-faint"}`} />
              <button type="button" onClick={() => p.onNodeIndex(i)} className="max-w-24 truncate py-1 pr-1">
                {i + 1}{n.label ? ` · ${n.label}` : ""}
              </button>
            </div>
          ))}
          <IconBtn title="Add a node" onClick={() => addNode()}><Plus className="h-3.5 w-3.5" /></IconBtn>
          <IconBtn title="Reset this node" onClick={resetNode}><RotateCcw className="h-3.5 w-3.5" /></IconBtn>
          <IconBtn title="Delete this node" onClick={removeNode} disabled={p.grade.nodes.length <= 1}><Trash2 className="h-3.5 w-3.5" /></IconBtn>
        </div>
        {p.sourceError && <p className="text-[11px] text-warn">The grade cannot be previewed: {p.sourceError}</p>}
      </div>

      <div role="tablist" aria-label="Colour tools" className="flex gap-0.5 border-b border-edge/70 px-2 py-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`min-w-0 flex-1 truncate rounded-md px-1.5 py-1 text-[11px] font-medium transition-colors ${tab === t.id ? "bg-accent text-white" : "text-fg-dim hover:text-fg"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {tab === "primaries" && (
          <div className="flex flex-col gap-4">
            <button type="button" onClick={autoBalance} className="self-start rounded-lg border border-edge bg-flat px-3 py-1.5 text-[11px] font-medium text-fg transition-colors hover:bg-glass-hi" title="Neutralise the colour cast on the mid tones and set black and white points">
              Auto balance
            </button>
            <div className="grid grid-cols-2 justify-items-center gap-3">
              {WHEELS.map((w) => (
                <WheelControl key={w.id} title={w.label} wheel={node[w.id]} onChange={(next, key) => edit(key, (n) => { n[w.id] = next; })} />
              ))}
            </div>
            <div className="flex flex-col gap-2">
              <SliderRow label="Contrast" value={node.contrast} min={0} max={2} step={0.01} def={1} onChange={num("contrast")} />
              <SliderRow label="Pivot" value={node.pivot} min={0} max={1} step={0.005} def={0.435} onChange={num("pivot")} />
              <SliderRow label="Saturation" value={node.saturation} min={0} max={2} step={0.01} def={1} onChange={num("saturation")} />
              <SliderRow label="Hue" value={node.hue} min={-180} max={180} step={0.5} def={0} digits={1} onChange={num("hue")} />
              <SliderRow label="Temp" value={node.temp} min={-100} max={100} step={0.5} def={0} digits={1} onChange={num("temp")} />
              <SliderRow label="Tint" value={node.tint} min={-100} max={100} step={0.5} def={0} digits={1} onChange={num("tint")} />
              <SliderRow label="Colour boost" value={node.boost} min={0} max={100} step={0.5} def={0} digits={1} onChange={num("boost")} />
              <SliderRow label="Shadows" value={node.shadows} min={-100} max={100} step={0.5} def={0} digits={1} onChange={num("shadows")} />
              <SliderRow label="Highlights" value={node.highlights} min={-100} max={100} step={0.5} def={0} digits={1} onChange={num("highlights")} />
            </div>
          </div>
        )}

        {tab === "curves" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              {TONES.map((t) => <Chip key={t.id} on={tone === t.id} onClick={() => setTone(t.id)}>{t.label}</Chip>)}
              <Chip onClick={() => edit("", (n) => { n.curves[tone] = G.tone0(); })}>Reset curve</Chip>
            </div>
            <CurveEditor spec={toneSpec} points={tonePoints} keyName={`c:${tone}`} onChange={(pts, key) => edit(key, (n) => { n.curves[tone] = pts; })} />
            <p className="text-[11px] text-fg-faint">Click to add a point, drag to move, double-click or right-click a point to remove it. Luma moves all three channels; R, G, B bend one.</p>
          </div>
        )}

        {tab === "hue" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              {HUE_CURVES.map((h) => <Chip key={h.id} on={hueCurve === h.id} onClick={() => setHueCurve(h.id)}>{h.label}</Chip>)}
              <Chip onClick={() => edit("", (n) => { n[hueCurve] = []; })}>Reset curve</Chip>
            </div>
            <CurveEditor spec={hueSpec} points={node[hueCurve] as CurvePoints} keyName={`h:${hueCurve}`} onChange={(pts, key) => edit(key, (n) => { n[hueCurve] = pts; })} />
            <p className="text-[11px] text-fg-faint">{hueKind.hint} The first click lays down a flat set of anchors; drag to move, double-click to remove.</p>
          </div>
        )}

        {tab === "lut" && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <span className="text-[11px] font-medium text-fg-dim">3D LUTs</span>
              <input ref={fileInput} type="file" accept=".cube" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importCube(f); e.target.value = ""; }} />
              <button type="button" onClick={() => fileInput.current?.click()} className="flex items-center justify-center gap-2 rounded-lg border border-edge bg-flat px-3 py-2 text-[11px] text-fg transition-colors hover:bg-glass-hi">
                <Upload className="h-3.5 w-3.5" />
                <span>Import a .cube LUT</span>
              </button>
              {Object.keys(p.lib).length === 0 ? (
                <p className="text-[11px] text-fg-faint">No LUTs yet. A .cube file (3D or 1D) is kept in this browser and baked into exports.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {Object.entries(p.lib).map(([id, l]) => (
                    <li key={id} className="flex items-center gap-1">
                      <button type="button" onClick={() => edit("", (n) => { n.lut = { id, strength: 1 }; })} className={`flex-1 truncate rounded-md border px-2 py-1 text-left text-[11px] ${node.lut?.id === id ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim hover:text-fg"}`}>
                        {l.title} · {l.size}³
                      </button>
                      <button type="button" aria-label={`Remove ${l.title} from the library`} title="Remove from the library" onClick={() => { const { [id]: _gone, ...rest } = p.lib; p.onLib(rest); }} className="rounded-md px-1.5 text-fg-faint hover:text-bad">×</button>
                    </li>
                  ))}
                </ul>
              )}
              {node.lut && p.lib[node.lut.id] && (
                <>
                  <SliderRow label="LUT strength" value={node.lut.strength} min={0} max={1} step={0.01} def={1} onChange={(v) => edit("s:lut", (n) => { if (n.lut) n.lut.strength = v; })} />
                  <button type="button" onClick={() => edit("", (n) => { n.lut = null; })} className="self-start rounded-md border border-edge bg-flat px-2.5 py-1 text-[11px] text-fg-dim hover:text-fg">Remove LUT from this node</button>
                </>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-[11px] font-medium text-fg-dim">Looks (each adds a node)</span>
              <div className="flex flex-wrap gap-1.5">
                {Object.keys(LOOKS).map((name) => <Chip key={name} onClick={() => addNode(name, LOOKS[name])}>{name}</Chip>)}
              </div>
            </div>
          </div>
        )}

        {tab === "scopes" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              {(["waveform", "parade", "vector", "histogram"] as ScopeKind[]).map((k) => (
                <Chip key={k} on={scope === k} onClick={() => setScope(k)}>{k === "vector" ? "Vectorscope" : k[0].toUpperCase() + k.slice(1)}</Chip>
              ))}
            </div>
            {graded ? (
              <canvas ref={scopeCanvas} width={SCOPE_SIZE[scope][0]} height={SCOPE_SIZE[scope][1]} aria-label={`${scope} scope`} className="w-full rounded-lg border border-edge" />
            ) : (
              <p className="text-[11px] text-fg-faint">{p.sourceError || "Reading the picture…"}</p>
            )}
            <p className="text-[11px] text-fg-faint">Scopes show the graded picture (a small copy of it), Rec.709 display values.</p>
          </div>
        )}
      </div>
    </div>
  );
};
