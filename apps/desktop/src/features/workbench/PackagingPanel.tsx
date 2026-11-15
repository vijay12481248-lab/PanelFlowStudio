import React from "react";
import { api } from "@panelflow/api-client";
import type { YouTubePackagingData } from "@panelflow/shared-types";
import { Button, Dialog, EmptyState, ErrorState, GlassPanel, Skeleton } from "@panelflow/ui-v2";
import { chaptersText, packagingBundle } from "./publishModel";

export interface PackagingPanelProps {
  projectId: string;
  /** False while a publish check has failed: the text can be read but not copied. */
  canCopy: boolean;
  copy: (text: string) => Promise<void>;
}

type Load = { state: "idle" } | { state: "loading" } | { state: "error" } | { state: "loaded"; data: YouTubePackagingData };

const Section: React.FC<{ title: string; copyLabel?: string; onCopy?: () => void; disabled: boolean; children: React.ReactNode }> = ({ title, copyLabel, onCopy, disabled, children }) => (
  <section className="grid grid-cols-1 gap-2">
    <div className="flex items-center justify-between gap-3">
      <h3 className="text-xs font-medium text-fg-faint">{title}</h3>
      {onCopy && <Button size="sm" variant="ghost" aria-label={copyLabel} disabled={disabled} onClick={onCopy}>Copy</Button>}
    </div>
    {children}
  </section>
);

const FIELD = "w-full rounded-ctl border border-edge bg-glass p-3 text-sm text-fg focus-visible:outline-2 focus-visible:outline-info";

/**
 * Packaging is only requested when a button is pressed: the engine writes new packaging with the local model
 * when none is saved, which is a slow job, so opening Publish must never trigger it.
 */
export const PackagingPanel: React.FC<PackagingPanelProps> = ({ projectId, canCopy, copy }) => {
  const [load, setLoad] = React.useState<Load>({ state: "idle" });
  const [title, setTitle] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState<string | null>(null);
  const [confirmRefresh, setConfirmRefresh] = React.useState(false);
  const busy = React.useRef(false); // synchronous guard: one request at a time, even on a fast double click

  const request = async (refresh: boolean) => {
    if (busy.current) return;
    busy.current = true;
    setLoad({ state: "loading" });
    setCopied(null);
    try {
      const data = await api.getYoutubePackaging(projectId, refresh);
      setTitle(data.selected_title ?? data.titles[0] ?? "");
      setLoad({ state: "loaded", data });
    } catch {
      setLoad({ state: "error" }); // never show the raw exception: it can contain local paths
    } finally {
      busy.current = false;
    }
  };

  const doCopy = async (what: string, text: string) => {
    try { await copy(text); setCopied(what); } catch { setCopied(null); }
  };

  let body: React.ReactNode;
  if (load.state === "idle") {
    body = (
      <EmptyState
        title="Packaging isn't loaded"
        description="Loading saved packaging, or writing it if none is saved, can take a minute because the local model writes it."
        action={<Button variant="primary" onClick={() => void request(false)}>Get packaging</Button>}
      />
    );
  } else if (load.state === "loading") {
    body = (
      <div className="grid grid-cols-1 gap-2">
        <p role="status" className="text-sm text-fg-dim">Loading packaging. This can take a minute.</p>
        <Skeleton className="h-24" />
      </div>
    );
  } else if (load.state === "error") {
    body = <ErrorState title="Couldn't load packaging" description="Couldn't load packaging. Check that the engine and Ollama are running, then try again." onRetry={() => void request(false)} />;
  } else {
    const { data } = load;
    const chosen = title ?? data.titles[0] ?? "";
    const hold = !canCopy;
    const hashtagsLine = data.hashtags_string;
    body = (
      <div className="grid grid-cols-1 gap-5">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" size="sm" disabled={hold} onClick={() => void doCopy("everything", packagingBundle(data, chosen))}>Copy everything</Button>
          <Button variant="secondary" size="sm" onClick={() => setConfirmRefresh(true)}>Refresh packaging</Button>
          {copied && <p role="status" className="text-sm text-ok">{`Copied ${copied}`}</p>}
          {hold && <p className="text-sm text-warn">Copying is held until the failed checks are fixed.</p>}
        </div>
        <Section title="Title" disabled={hold} copyLabel="Copy title" onCopy={() => void doCopy("title", chosen)}>
          <fieldset className="grid grid-cols-1 gap-1">
            <legend className="sr-only">Choose a title</legend>
            {data.titles.map((t) => (
              <label key={t} className="flex items-center gap-2 rounded-ctl border border-edge p-2 text-sm text-fg">
                <input type="radio" name="packaging-title" value={t} checked={chosen === t} onChange={() => setTitle(t)} />
                <span className="min-w-0 flex-1">{t}</span>
              </label>
            ))}
          </fieldset>
        </Section>
        <Section title="Description" disabled={hold} copyLabel="Copy description" onCopy={() => void doCopy("description", data.description)}>
          <textarea readOnly rows={6} value={data.description} aria-label="Description" className={FIELD} />
        </Section>
        {data.chapters.length > 0 && (
          <Section title="Chapters" disabled={hold} copyLabel="Copy chapters" onCopy={() => void doCopy("chapters", chaptersText(data.chapters))}>
            <pre className={`${FIELD} whitespace-pre-wrap font-data`}>{chaptersText(data.chapters)}</pre>
          </Section>
        )}
        {data.tags_string && (
          <Section title="Tags" disabled={hold} copyLabel="Copy tags" onCopy={() => void doCopy("tags", data.tags_string)}>
            <p className={FIELD}>{data.tags_string}</p>
          </Section>
        )}
        {hashtagsLine && (
          <Section title="Hashtags" disabled={hold} copyLabel="Copy hashtags" onCopy={() => void doCopy("hashtags", hashtagsLine)}>
            <p className={FIELD}>{hashtagsLine}</p>
          </Section>
        )}
        <Section title="Thumbnail" disabled={hold} copyLabel="Copy thumbnail prompt" onCopy={() => void doCopy("thumbnail prompt", data.thumbnail.prompt)}>
          <textarea readOnly rows={3} value={data.thumbnail.prompt} aria-label="Thumbnail prompt" className={FIELD} />
          <p className="text-xs text-fg-dim">{`${data.thumbnail.aspect_ratio}, ${data.thumbnail.recommended_width} by ${data.thumbnail.recommended_height}. ${data.thumbnail.composition_guidance}`}</p>
          {data.thumbnail.text_hooks.length > 0 && <p className="text-xs text-fg-dim">{`Text ideas: ${data.thumbnail.text_hooks.join(", ")}`}</p>}
        </Section>
      </div>
    );
  }

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
      <h2 className="font-display text-sm font-semibold text-fg">YouTube packaging</h2>
      {body}
      <Dialog
        open={confirmRefresh}
        onOpenChange={setConfirmRefresh}
        title="Replace the saved packaging?"
        description="This asks the local model to write new packaging. It can take a minute and replaces the saved version."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmRefresh(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => { setConfirmRefresh(false); void request(true); }}>Write new packaging</Button>
          </>
        }
      >
        Your current titles, description and tags are replaced.
      </Dialog>
    </GlassPanel>
  );
};
