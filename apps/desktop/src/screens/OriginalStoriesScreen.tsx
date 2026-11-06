import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { AnimeChannelPreset, OriginalSeries, YouTubeStatus } from "@panelflow/api-client";
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
  const [refine, setRefine] = useState(false);
  const [busy, setBusy] = useState(false);
  const [yt, setYt] = useState<YouTubeStatus | null>(null);
  const [ytId, setYtId] = useState("");
  const [ytSecret, setYtSecret] = useState("");
  const [forKids, setForKids] = useState<boolean | null>(null);

  const fail = useCallback(
    (e: unknown) => reportError({ title: "Original stories", message: e instanceof Error ? e.message : String(e) }),
    [reportError],
  );

  const refresh = useCallback(async () => {
    try {
      const [s, c, j, y] = await Promise.all([api.listOriginalSeries(), api.listAnimeChannels(), api.listOriginalJobs(), api.youtubeStatus()]);
      setYt(y);
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

  const connectYoutube = async () => {
    setBusy(true);
    try {
      if (ytId.trim() && ytSecret.trim()) {
        await api.saveYoutubeClient(ytId.trim(), ytSecret.trim());
        setYtSecret("");
      }
      const { auth_url } = await api.youtubeConnect();
      window.open(auth_url, "_blank", "noopener");
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  // Upload is always a deliberate click per episode; the default is a private upload.
  const upload = async (seriesId: string, episode: number, schedule: boolean) => {
    if (forKids === null) {
      fail(new Error("Choose whether your videos are made for kids first (a legal declaration only you can make)."));
      return;
    }
    if (schedule && !window.confirm("This schedules the video to become PUBLIC at its publish slot. Continue?")) return;
    setBusy(true);
    try {
      await api.uploadOriginalEpisode(seriesId, episode, { made_for_kids: forKids, schedule, confirm_public: schedule });
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
      await api.queueOriginalEpisodes(id, { count, ...(startDate ? { start_date: startDate } : {}), ...(refine ? { refine: true } : {}) });
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

      <section className="space-y-2 rounded-lg border border-zinc-800 p-4 text-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-zinc-300">YouTube</h2>
        <div className="text-zinc-400">
          {yt?.connected
            ? "Connected. Uploads are private unless you schedule a public release."
            : yt?.pending
              ? "Waiting for you to approve access in the browser…"
              : "Not connected. Create an OAuth client (Desktop app) in your Google Cloud project with the YouTube Data API enabled, then paste its id and secret."}
          {yt?.error && <span className="text-amber-400"> {yt.error}</span>}
        </div>
        {!yt?.connected && (
          <div className="flex gap-2">
            <input className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2" placeholder="OAuth client id" value={ytId} onChange={(e) => setYtId(e.target.value)} />
            <input className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2" type="password" placeholder="OAuth client secret" value={ytSecret} onChange={(e) => setYtSecret(e.target.value)} />
            <button disabled={busy} onClick={connectYoutube} className="px-3 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40">Connect</button>
          </div>
        )}
        {yt?.connected && (
          <button onClick={() => api.youtubeDisconnect().then(setYt).catch(fail)} className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700">Disconnect</button>
        )}
        <div className="flex gap-4 text-zinc-300">
          <span>Made for kids?</span>
          <label><input type="radio" name="kids" checked={forKids === true} onChange={() => setForKids(true)} /> Yes</label>
          <label><input type="radio" name="kids" checked={forKids === false} onChange={() => setForKids(false)} /> No</label>
        </div>
      </section>

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
          <label
            className="flex items-center gap-1.5 text-zinc-400"
            title="Review every picture against its narration, then repair or redraw the ones that fail. Slower (about a minute more per picture); every try is kept, and repaired pictures are flagged for a look."
          >
            <input type="checkbox" checked={refine} onChange={(e) => setRefine(e.target.checked)} />
            check and fix pictures (slower)
          </label>
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
                <span className="text-zinc-400 flex items-center gap-2">
                  {e.status}
                  {e.publish_at ? ` · slot ${e.publish_at.slice(0, 16).replace("T", " ")}` : ""}
                  {e.youtube_url ? <a className="text-emerald-400" href={e.youtube_url} target="_blank" rel="noreferrer">{e.youtube_privacy}</a> : null}
                  {e.upload_status === "uploading" && <span>uploading…</span>}
                  {e.upload_status === "failed" && <span className="text-amber-400" title={e.upload_error}>upload failed</span>}
                  {e.status === "done" && !e.youtube_url && yt?.connected && e.upload_status !== "uploading" && (
                    <>
                      <button disabled={busy} onClick={() => upload(s.id, e.number, false)} className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700">Upload private</button>
                      <button disabled={busy || !e.publish_at} onClick={() => upload(s.id, e.number, true)} className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700">Schedule public</button>
                    </>
                  )}
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
