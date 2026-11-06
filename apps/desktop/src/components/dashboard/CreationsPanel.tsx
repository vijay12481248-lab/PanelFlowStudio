import React, { useCallback, useEffect, useState } from "react";
import { BookOpen, Film, FolderOpen, Play } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { ChronoFlowJobSummary, OriginalStorySummary } from "@panelflow/api-client";

interface CreationsPanelProps {
  onOpenOriginalStories?: () => void;
  onOpenChronoFlowJob?: (jobId: string) => void;
}

const PREVIEW = 6;
const shortDate = (seconds?: number) => (seconds ? new Date(seconds * 1000).toLocaleDateString() : "");

/** File-based creations (Original Stories, ChronoFlow videos) have no database row, so the project list cannot show them. */
export const CreationsPanel: React.FC<CreationsPanelProps> = ({ onOpenOriginalStories, onOpenChronoFlowJob }) => {
  const [stories, setStories] = useState<OriginalStorySummary[]>([]);
  const [jobs, setJobs] = useState<ChronoFlowJobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState({ stories: false, jobs: false });

  const load = useCallback(async () => {
    const [s, j] = await Promise.allSettled([api.listOriginalStories(), api.listChronoFlowJobs()]);
    if (s.status === "fulfilled") setStories(s.value);
    // a job with no rendered clip yet (cancelled, test) has nothing to open
    if (j.status === "fulfilled") setJobs(j.value.filter((job) => (job.chunks ?? []).some(Boolean) || job.master_video));
    const failed = [s, j].filter((r) => r.status === "rejected");
    setError(failed.length ? "Could not load some creations — is the engine running?" : null);
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  const openStory = (slug: string, target: "folder" | "video") =>
    api.openOriginalStory(slug, target).catch((e) => setError(e instanceof Error ? e.message : String(e)));

  if (!stories.length && !jobs.length && !error) return null;
  const shownStories = showAll.stories ? stories : stories.slice(0, PREVIEW);
  const shownJobs = showAll.jobs ? jobs : jobs.slice(0, PREVIEW);

  return (
    <section className="mt-6" aria-label="Your creations">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold text-white">Your creations</h2>
          <p className="text-xs text-zinc-400">Original Stories and ChronoFlow videos, saved as files next to your projects.</p>
        </div>
        {error && <span className="text-xs text-amber-400">{error}</span>}
      </div>

      {stories.length > 0 && (
        <div className="mb-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-indigo-300 uppercase tracking-wide">Original Stories ({stories.length})</h3>
            {onOpenOriginalStories && (
              <button onClick={onOpenOriginalStories} className="text-xs text-zinc-300 hover:text-white">
                Open Original Stories studio →
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {shownStories.map((s) => (
              <div key={s.slug} className="rounded-xl border border-[#1f2437] bg-[#10131f] p-3 flex flex-col gap-2">
                <div className="flex items-start gap-2">
                  <BookOpen className="w-4 h-4 mt-0.5 text-indigo-400 flex-shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-zinc-100 truncate" title={s.title}>{s.title}</div>
                    <div className="text-[11px] text-zinc-500">
                      {s.genre} · {s.panels} panels · {shortDate(s.updated_at)}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-auto">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.has_video ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-700/40 text-zinc-400"}`}>
                    {s.has_video ? "Video ready" : "No video yet"}
                  </span>
                  <span className="flex-1" />
                  {s.has_video && (
                    <button onClick={() => void openStory(s.slug, "video")} className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white" title="Play the finished video">
                      <Play className="w-3 h-3" aria-hidden="true" /> Play
                    </button>
                  )}
                  <button onClick={() => void openStory(s.slug, "folder")} className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200" title="Open the story folder">
                    <FolderOpen className="w-3 h-3" aria-hidden="true" /> Folder
                  </button>
                </div>
              </div>
            ))}
          </div>
          {stories.length > PREVIEW && (
            <button onClick={() => setShowAll((v) => ({ ...v, stories: !v.stories }))} className="mt-2 text-xs text-zinc-400 hover:text-white">
              {showAll.stories ? "Show fewer" : `Show all ${stories.length}`}
            </button>
          )}
        </div>
      )}

      {jobs.length > 0 && (
        <div className="mb-2">
          <h3 className="text-xs font-semibold text-purple-300 uppercase tracking-wide mb-2">ChronoFlow videos ({jobs.length})</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {shownJobs.map((j) => (
              <div key={j.id} className="rounded-xl border border-[#1f2437] bg-[#10131f] p-3 flex flex-col gap-2">
                <div className="flex items-start gap-2">
                  <Film className="w-4 h-4 mt-0.5 text-purple-400 flex-shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-zinc-100 line-clamp-2" title={j.prompt}>{j.prompt || `Job ${j.id}`}</div>
                    <div className="text-[11px] text-zinc-500">
                      {(j.chunks ?? []).filter(Boolean).length} shots · {j.status} · {shortDate(j.created_at)}
                    </div>
                  </div>
                </div>
                <div className="flex justify-end mt-auto">
                  <button
                    onClick={() => onOpenChronoFlowJob?.(j.id)}
                    disabled={!onOpenChronoFlowJob}
                    className="text-xs px-2 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
                  >
                    Open in ChronoFlow
                  </button>
                </div>
              </div>
            ))}
          </div>
          {jobs.length > PREVIEW && (
            <button onClick={() => setShowAll((v) => ({ ...v, jobs: !v.jobs }))} className="mt-2 text-xs text-zinc-400 hover:text-white">
              {showAll.jobs ? "Show fewer" : `Show all ${jobs.length}`}
            </button>
          )}
        </div>
      )}
    </section>
  );
};
