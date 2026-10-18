import React from "react";
import {
  Clock,
  CheckCircle2,
  PlayCircle,
  FileText,
  AlertCircle,
  Clock3,
} from "lucide-react";
import type { Job, Project } from "@panelflow/shared-types";
import type { DashboardActivityItem } from "./types";

interface RecentActivityPanelProps {
  jobs: Job[];
  projects: Project[];
  onNavigateProject?: (project: Project) => void;
  onViewAll?: () => void;
}

export const RecentActivityPanel: React.FC<RecentActivityPanelProps> = ({
  jobs,
  projects,
  onNavigateProject,
  onViewAll,
}) => {
  const projectMap = new Map<string, Project>();
  projects.forEach((p) => projectMap.set(p.id, p));

  const getRelativeTime = (timeStr?: string | null) => {
    if (!timeStr) return "Just now";
    try {
      const now = Date.now();
      const past = new Date(timeStr).getTime();
      const diffSec = Math.max(1, Math.floor((now - past) / 1000));

      if (diffSec < 60) return `${diffSec} seconds ago`;
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin} ${diffMin === 1 ? "minute" : "minutes"} ago`;
      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return `${diffHour} ${diffHour === 1 ? "hour" : "hours"} ago`;
      const diffDays = Math.floor(diffHour / 24);
      return `${diffDays} ${diffDays === 1 ? "day" : "days"} ago`;
    } catch {
      return "Recently";
    }
  };

  const formatJobTitle = (jobType: string) => {
    return jobType
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  // Build activity feed from real jobs and project creations
  const activities: DashboardActivityItem[] = [];

  // Add jobs
  jobs.forEach((job) => {
    const proj = projectMap.get(job.project_id);
    const projName = proj?.title || "Manga Project";
    const timeStr = job.finished_at || job.started_at || job.created_at;

    if (job.status === "SUCCEEDED") {
      activities.push({
        id: `job-${job.job_id}`,
        title: `${formatJobTitle(job.job_type)} completed`,
        projectName: projName,
        projectId: job.project_id,
        timestamp: timeStr || "",
        relativeTime: getRelativeTime(timeStr),
        type: "check",
      });
    } else if (job.status === "RUNNING") {
      activities.push({
        id: `job-${job.job_id}`,
        title: `${formatJobTitle(job.job_type)} started`,
        projectName: projName,
        projectId: job.project_id,
        timestamp: timeStr || "",
        relativeTime: getRelativeTime(timeStr),
        type: "play",
      });
    } else if (job.status === "QUEUED") {
      activities.push({
        id: `job-${job.job_id}`,
        title: `${formatJobTitle(job.job_type)} queued`,
        projectName: projName,
        projectId: job.project_id,
        timestamp: timeStr || "",
        relativeTime: getRelativeTime(timeStr),
        type: "queue",
      });
    } else if (job.status === "FAILED") {
      activities.push({
        id: `job-${job.job_id}`,
        title: `${formatJobTitle(job.job_type)} failed`,
        projectName: projName,
        projectId: job.project_id,
        timestamp: timeStr || "",
        relativeTime: getRelativeTime(timeStr),
        type: "error",
      });
    }
  });

  // Add project creations
  projects.forEach((proj) => {
    activities.push({
      id: `proj-${proj.id}`,
      title: "Project created",
      projectName: proj.title,
      projectId: proj.id,
      timestamp: proj.created_at,
      relativeTime: getRelativeTime(proj.created_at),
      type: "doc",
    });
  });

  // Sort activities newest first and limit to 6
  const sortedActivities = activities
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 6);

  const renderIcon = (type: DashboardActivityItem["type"]) => {
    switch (type) {
      case "check":
        return (
          <div className="w-5 h-5 rounded-full bg-emerald-950/80 border border-emerald-800 flex items-center justify-center text-emerald-400 flex-shrink-0">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </div>
        );
      case "play":
        return (
          <div className="w-5 h-5 rounded-full bg-blue-950/80 border border-blue-800 flex items-center justify-center text-blue-400 flex-shrink-0">
            <PlayCircle className="w-3.5 h-3.5" />
          </div>
        );
      case "queue":
        return (
          <div className="w-5 h-5 rounded-full bg-amber-950/80 border border-amber-800 flex items-center justify-center text-amber-400 flex-shrink-0">
            <Clock3 className="w-3.5 h-3.5" />
          </div>
        );
      case "error":
        return (
          <div className="w-5 h-5 rounded-full bg-rose-950/80 border border-rose-800 flex items-center justify-center text-rose-400 flex-shrink-0">
            <AlertCircle className="w-3.5 h-3.5" />
          </div>
        );
      case "doc":
      default:
        return (
          <div className="w-5 h-5 rounded-full bg-indigo-950/80 border border-indigo-800 flex items-center justify-center text-indigo-400 flex-shrink-0">
            <FileText className="w-3.5 h-3.5" />
          </div>
        );
    }
  };

  return (
    <div className="space-y-3 select-none">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-blue-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-200">
            Recent Activity
          </h3>
        </div>
        <button
          onClick={onViewAll}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
        >
          View All
        </button>
      </div>

      {/* Activity List */}
      <div className="space-y-2.5">
        {sortedActivities.length === 0 ? (
          <div className="p-3 bg-[#111422]/60 border border-[#1e2538] rounded-xl text-center text-xs text-zinc-500 py-4">
            No recent activity recorded yet
          </div>
        ) : (
          sortedActivities.map((item) => {
            const proj = item.projectId ? projectMap.get(item.projectId) : undefined;

            return (
              <div
                key={item.id}
                className="flex items-start gap-2.5 group cursor-default"
              >
                {renderIcon(item.type)}
                <div className="flex-1 min-w-0">
                  <h4 className="text-xs font-semibold text-zinc-200 truncate leading-tight">
                    {item.title}
                  </h4>
                  <p
                    onClick={() => proj && onNavigateProject && onNavigateProject(proj)}
                    className="text-[11px] text-zinc-400 truncate mt-0.5 group-hover:text-zinc-300 transition-colors"
                  >
                    <span className="hover:text-indigo-400 cursor-pointer">
                      {item.projectName}
                    </span>{" "}
                    · {item.relativeTime}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
