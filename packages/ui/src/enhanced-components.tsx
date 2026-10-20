/**
 * Enhanced System Overview Cards - Generated with Google Stitch MCP
 * Improved version with better visual hierarchy, animations, and information density
 */

import React, { useState, useEffect } from "react";
import { Cpu, CircuitBoard, Activity, CheckCircle } from "lucide-react";

interface EnhancedSystemCardProps {
  icon: React.ReactNode;
  title: string;
  primaryMetric: string;
  secondaryMetric?: string;
  trend?: "up" | "down" | "stable";
  trendValue?: string;
  status?: "healthy" | "warning" | "error";
  onClick?: () => void;
  variant?: "glass" | "solid" | "minimal";
}

export const EnhancedSystemCard: React.FC<EnhancedSystemCardProps> = ({
  icon,
  title,
  primaryMetric,
  secondaryMetric,
  trend,
  trendValue,
  status = "healthy",
  onClick,
  variant = "glass",
}) => {
  const [isHovered, setIsHovered] = useState(false);

  const statusColors = {
    healthy: {
      bg: "from-emerald-500/10 to-emerald-500/5",
      border: "border-emerald-500/30",
      icon: "text-emerald-400",
      glow: "shadow-emerald-500/20",
    },
    warning: {
      bg: "from-amber-500/10 to-amber-500/5",
      border: "border-amber-500/30",
      icon: "text-amber-400",
      glow: "shadow-amber-500/20",
    },
    error: {
      bg: "from-rose-500/10 to-rose-500/5",
      border: "border-rose-500/30",
      icon: "text-rose-400",
      glow: "shadow-rose-500/20",
    },
  };

  const cardStyles = {
    glass: "bg-zinc-900/60 backdrop-blur-xl border border-zinc-800/50",
    solid: "bg-zinc-900 border border-zinc-800",
    minimal: "bg-transparent border border-zinc-800/30",
  };

  return (
    <div
      className={`
        relative group cursor-pointer transition-all duration-300
        ${cardStyles[variant]}
        hover:scale-[1.02] hover:border-zinc-700
        rounded-2xl p-5
        ${isHovered ? "shadow-2xl" : "shadow-xl"}
        ${statusColors[status].glow}
      `}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      {/* Background Gradient */}
      <div className={`absolute inset-0 rounded-2xl bg-gradient-to-br ${statusColors[status].bg} opacity-50`} />
      
      {/* Icon Container */}
      <div className="relative flex items-start justify-between mb-4">
        <div className={`
          w-12 h-12 rounded-xl flex items-center justify-center
          ${statusColors[status].bg}
          border ${statusColors[status].border}
          transition-transform duration-300
          ${isHovered ? "scale-110 rotate-3" : ""}
        `}>
          <div className={`${statusColors[status].icon} transition-all duration-300`}>
            {icon}
          </div>
        </div>

        {/* Trend Indicator */}
        {trend && (
          <div className="flex items-center gap-1 text-xs font-medium">
            <span className={`
              px-2 py-1 rounded-full
              ${trend === "up" ? "bg-emerald-500/10 text-emerald-400" : ""}
              ${trend === "down" ? "bg-rose-500/10 text-rose-400" : ""}
              ${trend === "stable" ? "bg-zinc-700 text-zinc-400" : ""}
            `}>
              {trendValue}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="relative space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          {title}
        </h3>
        
        <div className="space-y-1">
          <div className="text-2xl font-bold text-zinc-100 tracking-tight">
            {primaryMetric}
          </div>
          {secondaryMetric && (
            <div className="text-sm text-zinc-400">
              {secondaryMetric}
            </div>
          )}
        </div>

        {/* Progress Bar (if applicable) */}
        <div className="pt-2">
          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div 
              className={`h-full bg-gradient-to-r ${statusColors[status].bg} transition-all duration-500`}
              style={{ width: `${isHovered ? "75%" : "60%"}` }}
            />
          </div>
        </div>
      </div>

      {/* Hover Effect Overlay */}
      <div className={`
        absolute inset-0 rounded-2xl bg-gradient-to-t from-indigo-500/5 to-transparent
        opacity-0 group-hover:opacity-100 transition-opacity duration-300
        pointer-events-none
      `} />
    </div>
  );
};

/**
 * Enhanced Project Card with better information density
 */
interface EnhancedProjectCardProps {
  project: {
    id: string;
    name: string;
    stage: string;
    progress: number;
    coverUrl?: string;
    lastActivity: string;
    collaborators: number;
  };
  onClick?: () => void;
}

export const EnhancedProjectCard: React.FC<EnhancedProjectCardProps> = ({
  project,
  onClick,
}) => {
  const stageConfig = {
    ACQUIRED: { color: "indigo", label: "Acquisition" },
    NORMALIZED: { color: "violet", label: "Normalization" },
    OCR_COMPLETE: { color: "cyan", label: "OCR Review" },
    STORY_ANALYZED: { color: "emerald", label: "Story Analysis" },
    SCRIPT_GENERATED: { color: "amber", label: "Scripting" },
    RENDER_COMPLETE: { color: "rose", label: "Rendering" },
  };

  const config = stageConfig[project.stage as keyof typeof stageConfig] || stageConfig.ACQUIRED;

  return (
    <div
      className="group relative bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-700 transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl hover:shadow-indigo-500/10 cursor-pointer"
      onClick={onClick}
    >
      {/* Cover Image */}
      <div className="relative h-48 overflow-hidden bg-zinc-800">
        {project.coverUrl ? (
          <img
            src={project.coverUrl}
            alt={project.name}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-zinc-800 to-zinc-900">
            <div className="text-zinc-600">No Cover</div>
          </div>
        )}
        
        {/* Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 via-zinc-900/50 to-transparent" />
        
        {/* Stage Badge */}
        <div className="absolute top-3 left-3">
          <span className={`px-3 py-1 rounded-full text-xs font-bold bg-${config.color}-500/20 text-${config.color}-300 border border-${config.color}-500/30 backdrop-blur-md`}>
            {config.label}
          </span>
        </div>

        {/* Progress Ring */}
        <div className="absolute top-3 right-3">
          <div className="relative w-12 h-12">
            <svg className="w-12 h-12 transform -rotate-90">
              <circle
                cx="24"
                cy="24"
                r="20"
                stroke="rgba(39, 39, 42, 0.5)"
                strokeWidth="3"
                fill="none"
              />
              <circle
                cx="24"
                cy="24"
                r="20"
                stroke="url(#gradient)"
                strokeWidth="3"
                fill="none"
                strokeLinecap="round"
                strokeDasharray={`${project.progress * 125.6} 125.6`}
                className="transition-all duration-500"
              />
              <defs>
                <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-xs font-bold text-zinc-100">{project.progress}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        <h3 className="font-semibold text-zinc-100 group-hover:text-indigo-400 transition-colors">
          {project.name}
        </h3>
        
        {/* Metadata */}
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>Last activity: {project.lastActivity}</span>
          <span className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            {project.collaborators} active
          </span>
        </div>

        {/* Quick Actions (visible on hover) */}
        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button className="flex-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-xs font-medium text-zinc-300 transition-colors">
            Open
          </button>
          <button className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-xs font-medium text-zinc-300 transition-colors">
            ⋯
          </button>
        </div>
      </div>
    </div>
  );
};

export default { EnhancedSystemCard, EnhancedProjectCard };
