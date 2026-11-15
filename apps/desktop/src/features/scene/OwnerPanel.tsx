import React from "react";
import { api } from "@panelflow/api-client";
import type { SceneRun } from "@panelflow/api-client";
import { Button, GlassPanel, Switch } from "@panelflow/ui-v2";
import { ownerCanSubmit, TAGS } from "./sceneView";

const toggle = (list: string[], tag: string) => (list.includes(tag) ? list.filter((t) => t !== tag) : [...list, tag]);

/** The owner's side: how much they liked it, whether they agree with the AI review, what was good, what went wrong, and their own words. */
export const OwnerPanel: React.FC<{ run: SceneRun; choices: Record<string, string>; usable: boolean; onSaved: (run: SceneRun) => void; onDismissed: () => void }> = ({ run, choices, usable, onSaved, onDismissed }) => {
  const fb = run.feedback ?? null;
  const [liked, setLiked] = React.useState<number | null>(fb ? fb.liked : null);
  const [agrees, setAgrees] = React.useState(usable && (fb?.agrees_with_ai ?? false));
  const [goodTags, setGoodTags] = React.useState<string[]>(fb?.good_tags ?? []);
  const [wrongTags, setWrongTags] = React.useState<string[]>(fb?.wrong_tags ?? []);
  const [note, setNote] = React.useState(fb?.note ?? "");
  const [busy, setBusy] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const ok = ownerCanSubmit({ liked, agrees: usable && agrees, note, goodTags, wrongTags, choices });

  const submit = async () => {
    if (!ok || busy || liked === null) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.submitSceneFeedback(run.id, { liked, agrees_with_ai: usable && agrees, good_tags: goodTags, wrong_tags: wrongTags, item_verdicts: choices, note: note.trim() });
      setSaved(true);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your review");
    } finally {
      setBusy(false);
    }
  };
  const dismiss = async () => {
    setBusy(true);
    try {
      await api.dismissSceneRun(run.id);
      onDismissed();
    } finally {
      setBusy(false);
    }
  };

  const chip = (kind: "good" | "wrong", tag: string, active: boolean, set: () => void) => (
    <button
      key={`${kind}-${tag}`}
      type="button"
      aria-pressed={active}
      onClick={set}
      className={`rounded-full border px-3 py-1 text-xs ${active ? (kind === "good" ? "border-ok/60 bg-ok/20 text-ok" : "border-bad/60 bg-bad/20 text-bad") : "border-edge bg-glass text-fg-dim hover:text-fg"}`}
    >
      {kind}: {tag}
    </button>
  );

  return (
    <GlassPanel className="grid gap-4 p-4" aria-label="Your verdict">
      <h2 className="font-display text-base font-semibold text-fg">Your verdict</h2>
      <label className="grid gap-1 text-sm text-fg">
        <span>How much did you like it? <strong className="font-data">{liked === null ? "choose a value" : `${liked}%`}</strong></span>
        <input
          type="range" min={0} max={100} step={1} value={liked ?? 50} aria-label="How much did you like it"
          onChange={(e) => setLiked(Number(e.currentTarget.value))}
          onClick={(e) => setLiked(Number((e.currentTarget as HTMLInputElement).value))}
        />
      </label>
      {usable ? <Switch checked={agrees} onCheckedChange={setAgrees} label="I agree with the AI review" /> : <p className="text-sm text-fg-dim">There is no AI review to agree with, so your own words are what counts.</p>}
      <div className="grid gap-2">
        <span className="text-sm text-fg">What was good</span>
        <div className="flex flex-wrap gap-2">{TAGS.map((t) => chip("good", t, goodTags.includes(t), () => setGoodTags(toggle(goodTags, t))))}</div>
        <span className="text-sm text-fg">What went wrong</span>
        <div className="flex flex-wrap gap-2">{TAGS.map((t) => chip("wrong", t, wrongTags.includes(t), () => setWrongTags(toggle(wrongTags, t))))}</div>
      </div>
      <textarea
        aria-label="Your comments" rows={3} maxLength={4000} value={note} onChange={(e) => setNote(e.currentTarget.value)}
        placeholder="Anything the AI missed or got wrong? Your own words help the most."
        className="w-full rounded-ctl border border-edge bg-glass px-3 py-2 text-sm text-fg placeholder:text-fg-faint"
      />
      {error && <p className="text-sm text-bad" role="alert">{error}</p>}
      {saved && <p className="text-sm text-ok" role="status">Thanks, your review is saved.</p>}
      <div className="flex gap-2">
        <Button disabled={!ok || busy} onClick={() => void submit()}>Save my review</Button>
        <Button variant="ghost" disabled={busy} onClick={() => void dismiss()}>Dismiss</Button>
      </div>
    </GlassPanel>
  );
};
