import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { AnimeChannelPreset } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { useError } from "../context/ErrorContext";

export interface AnimeReviewScreenProps {
  onBack: () => void;
}

const BASES = [
  { value: "COMMENTARY_REVIEW", label: "Commentary / review (transformative, I accept responsibility)" },
  { value: "EXPLICIT_PERMISSION", label: "I have the rights holder's written permission" },
  { value: "LICENSED", label: "Licensed for this use" },
  { value: "USER_OWNED", label: "I own this footage" },
];

export const AnimeReviewScreen: React.FC<AnimeReviewScreenProps> = ({ onBack }) => {
  const { reportError } = useError();
  const [channels, setChannels] = useState<AnimeChannelPreset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [lines, setLines] = useState("");
  const [title, setTitle] = useState("");
  const [channelId, setChannelId] = useState("");
  const [basis, setBasis] = useState("COMMENTARY_REVIEW");
  const [notes, setNotes] = useState("");
  const [newChannel, setNewChannel] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [c, j] = await Promise.all([api.listAnimeChannels(), api.listAnimeReviewJobs()]);
      setChannels(c);
      setJobs(j);
      setChannelId((cur) => cur || c[0]?.id || "");
    } catch (e) {
      reportError({ title: "Anime review", message: e instanceof Error ? e.message : String(e) });
    }
  }, [reportError]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const addChannel = async () => {
    if (!newChannel.trim()) return;
    try {
      await api.saveAnimeChannel({ name: newChannel.trim() });
      setNewChannel("");
      await refresh();
    } catch (e) {
      reportError({ title: "Anime review", message: e instanceof Error ? e.message : String(e) });
    }
  };

  // One episode per line: a URL or a local path.
  const sources = lines.split("\n").map((l) => l.trim()).filter(Boolean);
  const needsNotes = basis === "COMMENTARY_REVIEW";
  const canQueue = sources.length > 0 && !!title.trim() && !!channelId && (!needsNotes || notes.trim().length > 0);

  const queue = async () => {
    setBusy(true);
    try {
      const rights = { status: basis, permission_notes: notes.trim() || null };
      await api.queueAnimeReviews(
        sources.map((source, i) => ({
          source,
          title: sources.length > 1 ? `${title.trim()} ${i + 1}` : title.trim(),
          rights,
          channel_id: channelId,
        })),
      );
      setLines("");
      await refresh();
    } catch (e) {
      reportError({ title: "Anime review", message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-ink text-fg p-6 max-w-4xl mx-auto space-y-6">
      <button onClick={onBack} className="text-sm text-fg-dim hover:text-fg">
        ← Back to projects
      </button>
      <h1 className="text-xl font-bold">Anime Review</h1>
      <p className="text-sm text-fg-dim">
        Paste episode links or file paths (one per line). Each becomes a hands-off job: analysis, short illustrative clips,
        a narrated review, render and YouTube package. Narration is the main content; clips are capped.
      </p>

      <section className="space-y-3 rounded-lg border border-edge p-4">
        <input
          className="w-full bg-navy border border-edge rounded px-3 py-2 text-sm"
          placeholder="Series title (e.g. Solo Leveling Ep 12)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="w-full h-24 bg-navy border border-edge rounded px-3 py-2 text-sm font-mono"
          placeholder={"https://… or C:\\videos\\episode.mkv"}
          value={lines}
          onChange={(e) => setLines(e.target.value)}
        />
        <div className="flex gap-2">
          <select
            className="flex-1 bg-navy border border-edge rounded px-3 py-2 text-sm"
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
          >
            {channels.length === 0 && <option value="">Create a channel preset first</option>}
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} — {c.voice}, {c.tone}
              </option>
            ))}
          </select>
          <input
            className="w-40 bg-navy border border-edge rounded px-3 py-2 text-sm"
            placeholder="New channel name"
            value={newChannel}
            onChange={(e) => setNewChannel(e.target.value)}
          />
          <button onClick={addChannel} className="px-3 rounded bg-flat hover:bg-glass-hi text-sm">
            Add
          </button>
        </div>
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-wide text-fg-dim">Rights basis (required)</label>
          <select
            className="w-full bg-navy border border-edge rounded px-3 py-2 text-sm"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
          >
            {BASES.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
          <input
            className="w-full bg-navy border border-edge rounded px-3 py-2 text-sm"
            placeholder={needsNotes ? "Required: why this is commentary/review" : "Notes (optional)"}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <button
          disabled={!canQueue || busy}
          onClick={queue}
          className="px-4 py-2 rounded bg-accent hover:bg-accent disabled:opacity-40 text-sm font-semibold"
        >
          {busy ? "Queuing…" : `Queue ${sources.length || ""} episode${sources.length === 1 ? "" : "s"}`}
        </button>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-bold uppercase tracking-wide text-fg-dim">Queue</h2>
        {jobs.length === 0 && <p className="text-sm text-fg-faint">No review jobs yet.</p>}
        {jobs.map((j) => (
          <div key={j.job_id} className="rounded border border-edge p-3 text-sm">
            <div className="flex justify-between">
              <span>{(j.input as { title?: string }).title ?? j.job_id}</span>
              <span className="text-fg-dim">{j.status}</span>
            </div>
            <div className="h-1.5 bg-flat rounded mt-2">
              <div className="h-1.5 bg-accent rounded" style={{ width: `${Math.round(j.progress * 100)}%` }} />
            </div>
            <div className="text-xs text-fg-dim mt-1">{j.error ?? j.message}</div>
            {j.status === "SUCCEEDED" && (
              <div className="text-xs text-ok mt-1 break-all">
                {String((j.output as { video?: string }).video ?? "")}
              </div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
};
