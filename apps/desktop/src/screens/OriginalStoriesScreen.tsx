import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { AnimeChannelPreset, OriginalSeries } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { useError } from "../context/ErrorContext";

export interface OriginalStoriesScreenProps {
  onBack: () => void;
}

const GENRES = ["bedtime", "horror", "mystery", "fantasy"];

export const OriginalStoriesScreen: React.FC<OriginalStoriesScreenProps> = ({ onBack }) => {
  const { reportError } = useError();
  const [series, setSeries] = useState<OriginalSeries[]>([]);
  const [channels, setChannels] = useState<AnimeChannelPreset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("bedtime");
  const [idea, setIdea] = useState("");
  const [channelId, setChannelId] = useState("");
  const [count, setCount] = useState(3);
  const [startDate, setStartDate] = useState("");
  const [busy, setBusy] = useState(false);

  const fail = useCallback(
    (e: unknown) => reportError({ title: "Original stories", message: e instanceof Error ? e.message : String(e) }),
    [reportError],
  );

  const refresh = useCallback(async () => {
    try {
      const [s, c, j] = await Promise.all([api.listOriginalSeries(), api.listAnimeChannels(), api.listOriginalJobs()]);
      setSeries(s);
      setChannels(c);
      setJobs(j);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const create = async () => {
    setBusy(true);
    try {
      await api.createOriginalSeries({ name: name.trim(), genre, idea: idea.trim(), channel_id: channelId });
      setName("");
      setIdea("");
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const queue = async (id: string) => {
    setBusy(true);
    try {
      await api.queueOriginalEpisodes(id, { count, ...(startDate ? { start_date: startDate } : {}) });
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 max-w-4xl mx-auto space-y-6">
      <button onClick={onBack} className="text-sm text-zinc-400 hover:text-zinc-200">
        ← Back to projects
      </button>
      <h1 className="text-xl font-bold">Original Stories</h1>
      <p className="text-sm text-zinc-400">
        A series keeps one cast, one world and the same character faces across episodes. Queue episodes and each becomes a
        story, illustrated panels, a narrated video, a comic PDF and a YouTube package, one publish slot per day. Read every
        script before you publish: these are AI-made.
      </p>

      <section className="space-y-3 rounded-lg border border-zinc-800 p-4">
        <h2 className="text-sm font-bold uppercase tracking-wide text-zinc-300">New series</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            placeholder="Series name (e.g. Moon Tales)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
          >
            {GENRES.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </div>
        <input
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
          placeholder="Idea (optional): a sleepy fox who collects lullabies"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
        />
        <select
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
        >
          <option value="">No channel preset (genre defaults)</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} — {c.voice}
            </option>
          ))}
        </select>
        <button
          disabled={busy || name.trim().length < 2}
          onClick={create}
          className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-semibold"
        >
          {busy ? "Working…" : "Create series"}
        </button>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-zinc-400">Queue</span>
          <input
            type="number"
            min={1}
            max={30}
            className="w-16 bg-zinc-900 border border-zinc-800 rounded px-2 py-1"
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
          />
          <span className="text-zinc-400">episodes, first live on</span>
          <input
            type="date"
            className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        {series.length === 0 && <p className="text-sm text-zinc-500">No series yet.</p>}
        {series.map((s) => (
          <div key={s.id} className="rounded border border-zinc-800 p-3 text-sm space-y-2">
            <div className="flex justify-between items-start gap-3">
              <div>
                <div className="font-semibold">{s.name}</div>
                <div className="text-xs text-zinc-400">
                  {s.genre} · {s.bible.premise.logline}
                </div>
                <div className="text-xs text-zinc-500">Cast: {s.bible.characters.map((c) => c.name).join(", ")}</div>
              </div>
              <button
                disabled={busy}
                onClick={() => queue(s.id)}
                className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 whitespace-nowrap"
              >
                Queue {count}
              </button>
            </div>
            {s.episodes.map((e) => (
              <div key={e.number} className="text-xs flex justify-between border-t border-zinc-800 pt-1">
                <span>
                  Ep {e.number}: {e.title || "…"}
                  {e.warnings.length > 0 && <span className="text-amber-400"> · {e.warnings.length} warnings</span>}
                </span>
                <span className="text-zinc-400">
                  {e.status}
                  {e.publish_at ? ` · live ${e.publish_at.slice(0, 16).replace("T", " ")}` : ""}
                </span>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-bold uppercase tracking-wide text-zinc-300">Jobs</h2>
        {jobs.length === 0 && <p className="text-sm text-zinc-500">No episode jobs yet.</p>}
        {jobs.map((j) => (
          <div key={j.job_id} className="rounded border border-zinc-800 p-3 text-sm">
            <div className="flex justify-between">
              <span>{(j.input as { title?: string }).title ?? j.job_id}</span>
              <span className="text-zinc-400">{j.status}</span>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded mt-2">
              <div className="h-1.5 bg-indigo-500 rounded" style={{ width: `${Math.round(j.progress * 100)}%` }} />
            </div>
            <div className="text-xs text-zinc-400 mt-1">{j.error ?? j.message}</div>
            {j.status === "SUCCEEDED" && (
              <div className="text-xs text-emerald-400 mt-1 break-all">{String((j.output as { video?: string }).video ?? "")}</div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
};
