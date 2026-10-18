import React, { useState } from "react";
import {
  RotateCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Sparkles,
  Eye,
} from "lucide-react";
import type { Job, Project } from "@panelflow/shared-types";
import { api } from "@panelflow/api-client";
import { useError } from "../../context/ErrorContext";

interface JobQueueSidebarProps {
  jobs: Job[];
  projects: Project[];
  coversMap?: Record<string, string>;
  onRetryJob?: (jobId: string) => void;
  onCancelJob?: (jobId: string) => void;
  onNavigateProject?: (project: Project) => void;
}

export const JobQueueSidebar: React.FC<JobQueueSidebarProps> = ({
  jobs,
  projects,
  coversMap,
  onRetryJob,
  onCancelJob,
  onNavigateProject,
}) => {
  const { inspectError } = useError();
  const [collapsed, setCollapsed] = useState({
    running: false,
    queued: false,
    failed: false,
    completed: false,
  });

  const toggleSection = (section: keyof typeof collapsed) => {
    setCollapsed((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const projectMap = new Map<string, Project>();
  projects.forEach((p) => projectMap.set(p.id, p));

  const runningJobs = jobs.filter((j) => j.status === "RUNNING");
  const queuedJobs = jobs.filter((j) => j.status === "QUEUED");
  const failedJobs = jobs.filter(
    (j) => j.status === "FAILED" || j.status === "CANCELLED"
  );
  const completedJobs = jobs.filter((j) => j.status === "SUCCEEDED");

  const formatJobTitle = (jobType: string) => {
    return jobType
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const formatCompletedTime = (timeStr?: string | null) => {
    if (!timeStr) return "Just now";
    try {
      const d = new Date(timeStr);
      return `Completed ${d.toLocaleDateString("en-GB")}, ${d.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
    } catch {
      return "Completed";
    }
  };

  // Thumbnail rendering (Actual Manga Artwork or Stylized Avatar)
  const renderThumbnail = (project?: Project, sizeClass = "w-10 h-10") => {
    const coverUrl = project ? coversMap?.[project.id] : undefined;
    if (coverUrl) {
      return (
        <div
          className={`${sizeClass} rounded-lg bg-[#141828] border border-[#232b45] flex items-center justify-center flex-shrink-0 relative overflow-hidden shadow-inner group-hover:border-indigo-500/50 transition-colors`}
        >
          <img src={coverUrl} alt="" className="w-full h-full object-cover object-top" />
        </div>
      );
    }

    const title = project?.title || "Manga";
    const initials = title
      .split(/[-_ ]+/)
      .map((w) => w[0]?.toUpperCase())
      .slice(0, 2)
      .join("") || "PF";

    // Palette variants based on title
    const hash = title.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
    const hues = ["#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b"];
    const accentColor = hues[hash % hues.length];

    return (
      <div
        className={`${sizeClass} rounded-lg bg-[#141828] border border-[#232b45] flex items-center justify-center flex-shrink-0 relative overflow-hidden shadow-inner group-hover:border-indigo-500/50 transition-colors`}
      >
        <div
          className="absolute inset-0 opacity-20"
          style={{
            background: `radial-gradient(circle at 30% 30%, ${accentColor}, transparent 70%)`,
          }}
        />
        <span className="font-bold text-[11px] text-zinc-300 font-mono tracking-wider relative z-10">
          {initials}
        </span>
      </div>
    );
  };

  return (
    <aside className="w-[310px] min-w-[280px] max-w-[330px] bg-[#0c0e17]/95 border-r border-[#181c2b] flex flex-col flex-shrink-0 h-full overflow-hidden select-none">
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4 scrollbar-thin scrollbar-thumb-zinc-800">
        {/* SECTION 1: RUNNING JOBS */}
        <div className="space-y-2">
          <button
            onClick={() => toggleSection("running")}
            className="w-full flex items-center justify-between text-left py-1 text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <RotateCw className="w-3.5 h-3.5 animate-spin" />
              <span className="text-[11px] font-bold tracking-wider uppercase">
                Running Jobs ({runningJobs.length})
              </span>
            </div>
            {collapsed.running ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </button>

          {!collapsed.running && (
            <div className="space-y-2">
              {runningJobs.length === 0 ? (
                <div className="p-3 bg-[#111422]/60 border border-[#1e2538] rounded-xl text-center text-xs text-zinc-500 py-3">
                  No active jobs running
                </div>
              ) : (
                runningJobs.map((job) => {
                  const proj = projectMap.get(job.project_id);
                  const pct = Math.round((job.progress || 0) * 100);

                  return (
                    <div
                      key={job.job_id}
                      className="bg-[#111422] border border-[#1e2538] rounded-xl p-3 space-y-2 shadow-sm"
                    >
                      <div className="flex items-start gap-2.5">
                        {renderThumbnail(proj, "w-10 h-10")}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <h4 className="text-xs font-semibold text-zinc-100 truncate">
                              {formatJobTitle(job.job_type)}
                            </h4>
                            <span className="bg-[#291f58] text-[#c4b5fd] border border-[#4c3b8f] text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
                              RUNNING
                            </span>
                          </div>
                          <p
                            onClick={() => proj && onNavigateProject && onNavigateProject(proj)}
                            className="text-[11px] text-zinc-400 truncate cursor-pointer hover:text-indigo-400 transition-colors mt-0.5"
                          >
                            {proj?.title || job.project_id}
                          </p>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div className="space-y-1 pt-1">
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-zinc-500">Progress</span>
                          <span className="font-semibold text-zinc-300 font-mono">
                            {pct}%
                          </span>
                        </div>
                        <div className="w-full bg-[#181d2e] rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-[#4338ca] h-1.5 rounded-full transition-all duration-300"
                            style={{ width: `${Math.max(5, pct)}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-zinc-500 pt-0.5">
                        <span>{job.message || "Processing in progress..."}</span>
                        {onCancelJob && (
                          <button
                            onClick={() => onCancelJob(job.job_id)}
                            className="text-rose-400 hover:text-rose-300"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* SECTION 2: QUEUED JOBS */}
        <div className="space-y-2">
          <button
            onClick={() => toggleSection("queued")}
            className="w-full flex items-center justify-between text-left py-1 text-amber-400 hover:text-amber-300 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              <span className="text-[11px] font-bold tracking-wider uppercase">
                Queued Jobs ({queuedJobs.length})
              </span>
            </div>
            {collapsed.queued ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </button>

          {!collapsed.queued && (
            <div className="space-y-2">
              {queuedJobs.length === 0 ? (
                <div className="p-3 bg-[#111422]/60 border border-[#1e2538] rounded-xl text-center text-xs text-zinc-500 py-3">
                  Queue is clear
                </div>
              ) : (
                queuedJobs.map((job) => {
                  const proj = projectMap.get(job.project_id);

                  return (
                    <div
                      key={job.job_id}
                      className="bg-[#111422] border border-[#1e2538] rounded-xl p-3 space-y-2 shadow-sm"
                    >
                      <div className="flex items-start gap-2.5">
                        {renderThumbnail(proj, "w-10 h-10")}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <h4 className="text-xs font-semibold text-zinc-100 truncate">
                              {formatJobTitle(job.job_type)}
                            </h4>
                            <span className="bg-[#3f2a14] text-[#f59e0b] border border-[#784c19] text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
                              QUEUED
                            </span>
                          </div>
                          <p
                            onClick={() => proj && onNavigateProject && onNavigateProject(proj)}
                            className="text-[11px] text-zinc-400 truncate cursor-pointer hover:text-indigo-400 transition-colors mt-0.5"
                          >
                            {proj?.title || job.project_id}
                          </p>
                        </div>
                      </div>

                      {/* Zero Progress Bar */}
                      <div className="space-y-1 pt-1">
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-zinc-500">Queued</span>
                          <span className="font-semibold text-zinc-400 font-mono">0%</span>
                        </div>
                        <div className="w-full bg-[#181d2e] rounded-full h-1.5 overflow-hidden">
                          <div className="bg-amber-600/60 h-1.5 rounded-full w-0" />
                        </div>
                      </div>

                      {job.error ? (
                        <div className="flex items-center justify-between text-[10px] text-amber-300 pt-0.5">
                          <span className="truncate">⚠️ {job.error}</span>
                          <button
                            onClick={() =>
                              inspectError({
                                id: `err_job_${job.job_id}`,
                                title: `Job Alert: ${formatJobTitle(job.job_type)} Retrying`,
                                message: `${job.error} (${job.message || "Backoff retry in progress"})`,
                                severity: "warning",
                                source: "job",
                                jobId: job.job_id,
                                projectId: job.project_id,
                                jobType: job.job_type,
                                timestamp: job.created_at || new Date().toISOString(),
                                rawDetails: job,
                              })
                            }
                            className="text-cyan-400 hover:underline flex-shrink-0 ml-1 font-semibold"
                          >
                            Inspect
                          </button>
                        </div>
                      ) : (
                        <div className="text-[10px] text-zinc-500 italic pt-0.5">
                          {job.message || "Waiting for GPU slot..."}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* SECTION 3: FAILED / INTERRUPTED */}
        <div className="space-y-2">
          <button
            onClick={() => toggleSection("failed")}
            className="w-full flex items-center justify-between text-left py-1 text-rose-400 hover:text-rose-300 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span className="text-[11px] font-bold tracking-wider uppercase">
                Failed / Interrupted ({failedJobs.length})
              </span>
            </div>
            {collapsed.failed ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </button>

          {!collapsed.failed && (
            <div className="space-y-2">
              {failedJobs.length === 0 ? (
                <div className="p-3 bg-[#111422]/60 border border-[#1e2538] rounded-xl text-center text-xs text-zinc-500 py-3">
                  No failed jobs good news! 🎉
                </div>
              ) : (
                failedJobs.map((job) => {
                  const proj = projectMap.get(job.project_id);

                  return (
                    <div
                      key={job.job_id}
                      className="bg-rose-950/20 border border-rose-900/60 rounded-xl p-3 space-y-2"
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div>
                          <h4 className="text-xs font-semibold text-rose-200">
                            {formatJobTitle(job.job_type)}
                          </h4>
                          <p className="text-[11px] text-zinc-400 truncate">
                            {proj?.title || job.project_id}
                          </p>
                        </div>
                        <span className="bg-rose-950 text-rose-400 border border-rose-800 text-[9px] px-1.5 py-0.5 rounded font-bold">
                          {job.status}
                        </span>
                      </div>
                      <p className="text-[10px] text-rose-300 line-clamp-2">
                        {job.error || job.message || "Execution encountered an error."}
                      </p>
                      <div className="flex items-center gap-1.5 pt-1">
                        <button
                          onClick={() =>
                            inspectError({
                              id: `err_job_${job.job_id}`,
                              title: `Job Failed: ${formatJobTitle(job.job_type)}`,
                              message: job.error || job.message || "Execution encountered an error.",
                              severity: "error",
                              source: "job",
                              jobId: job.job_id,
                              projectId: job.project_id,
                              jobType: job.job_type,
                              timestamp: job.finished_at || job.created_at || new Date().toISOString(),
                              rawDetails: job,
                            })
                          }
                          className="flex-1 py-1 px-2 bg-[#1b172a] hover:bg-[#26203a] border border-rose-900/60 text-cyan-300 hover:text-cyan-200 text-[11px] rounded-lg flex items-center justify-center gap-1 transition-colors"
                          title="Open full error diagnostics and logs"
                        >
                          <Eye className="w-3 h-3 text-cyan-400" />
                          <span>View Details</span>
                        </button>
                        {onRetryJob && (
                          <button
                            onClick={() => onRetryJob(job.job_id)}
                            className="py-1 px-2.5 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-800 text-rose-200 text-[11px] rounded-lg flex items-center justify-center gap-1 transition-colors"
                          >
                            <RotateCcw className="w-3 h-3" />
                            <span>Retry</span>
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* SECTION 4: COMPLETED HISTORY */}
        <div className="space-y-2">
          <button
            onClick={() => toggleSection("completed")}
            className="w-full flex items-center justify-between text-left py-1 text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span className="text-[11px] font-bold tracking-wider uppercase">
                Completed History ({completedJobs.length})
              </span>
            </div>
            {collapsed.completed ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </button>

          {!collapsed.completed && (
            <div className="space-y-1.5">
              {completedJobs.length === 0 ? (
                <div className="p-3 bg-[#111422]/60 border border-[#1e2538] rounded-xl text-center text-xs text-zinc-500 py-3">
                  No completed jobs recorded yet
                </div>
              ) : (
                completedJobs.slice(0, 10).map((job) => {
                  const proj = projectMap.get(job.project_id);

                  return (
                    <div
                      key={job.job_id}
                      className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/80 rounded-xl p-2.5 transition-all flex items-center gap-2.5"
                    >
                      {renderThumbnail(proj, "w-8 h-8")}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          <h5 className="text-[11px] font-semibold text-zinc-200 truncate">
                            {formatJobTitle(job.job_type)}
                          </h5>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <span className="text-[10px] text-zinc-500 font-mono">
                              100%
                            </span>
                            <span className="bg-[#0e3322] text-[#34d399] border border-[#166534] text-[9px] px-1.5 py-0.2 rounded font-bold">
                              COMPLETED
                            </span>
                          </div>
                        </div>
                        <p
                          onClick={() => proj && onNavigateProject && onNavigateProject(proj)}
                          className="text-[10px] text-zinc-400 truncate cursor-pointer hover:text-indigo-400"
                        >
                          {proj?.title || job.project_id}
                        </p>
                        <p className="text-[9px] text-zinc-500 mt-0.5 truncate">
                          {formatCompletedTime(job.finished_at || job.created_at)}
                        </p>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
