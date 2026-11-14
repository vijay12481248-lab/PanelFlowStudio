import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Panel } from "@panelflow/shared-types";
import { Button, Switch } from "@panelflow/ui-v2";
import { refusal } from "../kit/engineReason";

type Suggestions = Awaited<ReturnType<typeof api.getPanelContentSuggestions>>;
export type Review = Suggestions;
type Suggestion = Suggestions["suggestions"][number];

/** What the engine's cleanup report says it did with each panel, in the order shown. */
const ACTIONS = [["blur", "blurred"], ["exclude", "excluded"], ["review", "need review"], ["keep", "kept"]] as const;
const AREA = "min-h-24 w-full rounded-ctl border border-edge bg-glass p-3 text-sm text-fg";
const lines = (text: string) => text.split("\n").map((l) => l.trim()).filter(Boolean);

export interface ContentCleanupProps {
  projectId: string;
  panels: Panel[];
  /** The last scan, or null before one. Owned by the stage so Detect and review can fill it too. */
  review: Review | null;
  onReview: (review: Review | null) => void;
  /** A panel was excluded: reload the panels. */
  onPanelsChanged: () => void;
  /** Text was blurred on a panel: read the blur state again. */
  onBlurred: () => void;
}

/** Shared cleanup rules, a scan for promotional text, and a one-click blur or exclusion for each finding. */
export const ContentCleanup: React.FC<ContentCleanupProps> = ({ projectId, panels, review, onReview, onPanelsChanged, onBlurred }) => {
  const rules = useQuery({ queryKey: ["stages", "panels", "cleanup-rules", projectId], queryFn: () => api.getContentCleanupRules(projectId), retry: false });
  const report = useQuery({ queryKey: ["stages", "panels", "cleanup-report", projectId], queryFn: () => api.getContentCleanupReport(projectId).catch(() => null), retry: false });

  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState(false);
  const busy = React.useRef(false);
  const run = async (task: () => Promise<void>) => {
    if (busy.current) return;
    busy.current = true;
    setWorking(true);
    setError(null);
    setNotice(null);
    try { await task(); } finally { busy.current = false; setWorking(false); }
  };

  const [enabled, setEnabled] = React.useState<boolean | null>(null);
  const [sharedText, setSharedText] = React.useState<string | null>(null);
  const ready = rules.data ? { enabled: enabled ?? rules.data.enabled, text: sharedText ?? rules.data.labels.join("\n") } : null;

  const labelsKey = review?.labels.join("\n") ?? "";
  const [projectText, setProjectText] = React.useState(labelsKey);
  React.useEffect(() => { setProjectText(labelsKey); }, [labelsKey]);

  const saveRules = () => run(async () => {
    if (!ready) return;
    try {
      const saved = await api.saveContentCleanupRules(projectId, { enabled: ready.enabled, labels: lines(ready.text) });
      setEnabled(saved?.enabled ?? ready.enabled);
      setSharedText((saved?.labels ?? lines(ready.text)).join("\n"));
      setNotice("Saved for all episodes.");
    } catch (err) { setError(refusal("Couldn't save the cleanup rules.", err)); }
  });

  const scan = async () => {
    try { onReview(await api.getPanelContentSuggestions(projectId)); }
    catch (err) { setError(refusal("Couldn't scan for promotional text.", err)); }
  };
  const runScan = () => run(scan);
  const saveLabelsAndScan = () => run(async () => {
    try { await api.savePanelContentLabels(projectId, lines(projectText)); }
    catch (err) { setError(refusal("Couldn't save the labels.", err)); return; }
    await scan();
  });

  const dropSuggestions = (keep: (s: Suggestion) => boolean) => { if (review) onReview({ ...review, suggestions: review.suggestions.filter(keep) }); };
  const blurText = (s: Suggestion) => run(async () => {
    try {
      const done = await api.blurPanelText(projectId, s.panel_id, { region_ids: [s.region_id] });
      if (!done.success) throw new Error("The engine did not blur it.");
      dropSuggestions((x) => x.region_id !== s.region_id);
      onBlurred();
    } catch (err) { setError(refusal("Couldn't blur that text.", err)); }
  });
  const excludePanel = (s: Suggestion) => run(async () => {
    const panel = panels.find((p) => p.id === s.panel_id);
    if (!panel) { setError("That panel is no longer in the project."); return; }
    try {
      await api.updatePanel(projectId, panel.id, panel.x, panel.y, panel.width, panel.height, "IGNORED");
      dropSuggestions((x) => x.panel_id !== s.panel_id);
      onPanelsChanged();
    } catch (err) { setError(refusal("Couldn't exclude that panel.", err)); }
  });

  const checked = report.data ? Object.values(report.data.panels) : null;
  const summary = checked ? ACTIONS.map(([action, word]) => [checked.filter((p) => p.action.toLowerCase() === action).length, word] as const).filter(([n]) => n > 0).map(([n, word]) => `${n} ${word}`).join(", ") : "";

  return (
    <section aria-label="Content cleanup" className="grid gap-4">
      <div className="grid gap-2">
        <h3 className="text-[13px] font-medium text-fg">Cleanup rules for every episode</h3>
        {rules.isError && <p role="alert" className="text-sm text-bad">{refusal("Couldn't load the cleanup rules.", rules.error)}</p>}
        {ready && (
          <>
            <Switch checked={ready.enabled} onCheckedChange={setEnabled} label="Clean promotional content automatically" />
            <textarea aria-label="Shared exclusion labels" className={AREA} value={ready.text} onChange={(e) => setSharedText(e.target.value)} placeholder="One label per line, for example a site name" />
            <div><Button size="sm" variant="secondary" disabled={working} onClick={() => void saveRules()}>Save for all episodes</Button></div>
          </>
        )}
        {checked && <p className="text-xs text-fg-dim">{checked.length === 0 ? "No panels have been checked automatically yet." : `${checked.length} ${checked.length === 1 ? "panel was" : "panels were"} checked automatically: ${summary}.`}</p>}
      </div>

      <div className="grid gap-2 border-t border-edge pt-3">
        <h3 className="text-[13px] font-medium text-fg">Promotional text in this project</h3>
        <textarea aria-label="Labels for this project" className={AREA} value={projectText} onChange={(e) => setProjectText(e.target.value)} placeholder="Extra words or site names to look for, one per line" />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" disabled={working} onClick={() => void runScan()}>Scan for promotional text</Button>
          <Button size="sm" variant="secondary" disabled={working} onClick={() => void saveLabelsAndScan()}>Save labels and scan</Button>
        </div>
        {review?.ocr_required && <p className="text-sm text-fg-dim">Read the text in OCR first, then scan again to find website links and credits.</p>}
        {review && !review.ocr_required && <p role="status" className="text-sm text-fg-dim">{`Checked ${review.regions_checked} text ${review.regions_checked === 1 ? "region" : "regions"}. ${review.suggestions.length === 0 ? "No suggestions." : `${review.suggestions.length} ${review.suggestions.length === 1 ? "suggestion" : "suggestions"}.`}`}</p>}
        {notice && <p role="status" className="text-sm text-fg-dim">{notice}</p>}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>

      {review && review.suggestions.length > 0 && (
        <ul className="grid gap-3">
          {review.suggestions.map((s) => <SuggestionRow key={s.region_id} projectId={projectId} s={s} disabled={working} onBlur={() => void blurText(s)} onExclude={() => void excludePanel(s)} />)}
        </ul>
      )}
    </section>
  );
};

const SuggestionRow: React.FC<{ projectId: string; s: Suggestion; disabled: boolean; onBlur: () => void; onExclude: () => void }> = ({ projectId, s, disabled, onBlur, onExclude }) => {
  const [open, setOpen] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);
  const preview = api.getTextBlurPreviewUrl(projectId, s.panel_id, s.region_id);
  const afterUrl = attempt ? `${preview}${preview.includes("?") ? "&" : "?"}retry=${attempt}` : preview;
  return (
    <li data-suggestion={s.region_id} className="grid gap-2 rounded-ctl border border-edge p-3">
      <p className="text-sm font-medium text-fg">{s.text}</p>
      <p className="text-xs text-fg-dim">{s.reason}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" aria-expanded={open} onClick={() => { setOpen(!open); setFailed(false); }}>Before and after</Button>
        <Button size="sm" variant="primary" disabled={disabled} onClick={onBlur}>Blur this text</Button>
        <Button size="sm" variant="secondary" disabled={disabled} onClick={onExclude}>Exclude promotional panel</Button>
      </div>
      {open && (
        <div className="grid grid-cols-2 gap-2">
          <figure className="grid gap-1"><img src={api.getPanelImageUrl(projectId, s.panel_id)} alt="The panel as it is now" className="w-full rounded-ctl" /><figcaption className="text-xs text-fg-dim">Before</figcaption></figure>
          <figure className="grid gap-1"><img src={afterUrl} alt="The panel with this text blurred" onError={() => setFailed(true)} className="w-full rounded-ctl" /><figcaption className="text-xs text-fg-dim">After</figcaption></figure>
          {failed && (
            <div className="col-span-2 flex flex-wrap items-center gap-2">
              <p role="alert" className="text-sm text-bad">Preview unavailable. Retry before applying cleanup.</p>
              <Button size="sm" variant="secondary" onClick={() => { setFailed(false); setAttempt(attempt + 1); }}>Retry preview</Button>
            </div>
          )}
        </div>
      )}
    </li>
  );
};
