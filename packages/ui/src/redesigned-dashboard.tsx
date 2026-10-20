/**
 * Redesigned Dashboard Shell - Improved UI/UX
 * Features:
 * - Better visual hierarchy with glassmorphism
 * - Improved information density
 * - Enhanced interactions
 * - Better mobile responsiveness
 * - Stitch-generated design patterns
 */

import React, { useState, useEffect } from "react";
import { 
  LayoutDashboard, 
  FolderKanban, 
  Settings, 
  Plus, 
  Search,
  Bell,
  ChevronDown,
  Sparkles,
  Zap,
  BarChart3,
  Users,
  Clock,
  TrendingUp
} from "lucide-react";

// Enhanced System Overview with better visual design
export const RedesignedSystemOverview: React.FC<{
  metrics: Array<{
    icon: React.ReactNode;
    title: string;
    value: string;
    subvalue?: string;
    trend?: string;
    status: "healthy" | "warning" | "error";
    color: string;
  }>;
}> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric, index) => (
        <MetricCard key={index} {...metric} />
      ))}
    </div>
  );
};

const MetricCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  value: string;
  subvalue?: string;
  trend?: string;
  status: "healthy" | "warning" | "error";
  color: string;
}> = ({ icon, title, value, subvalue, trend, status, color }) => {
  const statusConfig = {
    healthy: {
      gradient: "from-emerald-500/10 to-emerald-500/5",
      border: "border-emerald-500/20",
      iconBg: "bg-emerald-500/10",
    },
    warning: {
      gradient: "from-amber-500/10 to-amber-500/5",
      border: "border-amber-500/20",
      iconBg: "bg-amber-500/10",
    },
    error: {
      gradient: "from-rose-500/10 to-rose-500/5",
      border: "border-rose-500/20",
      iconBg: "bg-rose-500/10",
    },
  };

  const config = statusConfig[status];

  return (
    <div className="group relative">
      {/* Glow effect */}
      <div className={`absolute -inset-0.5 bg-gradient-to-r ${config.gradient} rounded-2xl blur opacity-0 group-hover:opacity-100 transition-opacity`} />
      
      <div className="relative bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl p-5 hover:border-zinc-700 transition-all duration-300">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className={`p-3 rounded-xl ${config.iconBg} border ${config.border}`}>
            <div className="text-zinc-200">
              {icon}
            </div>
          </div>
          {trend && (
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-zinc-800 text-zinc-400">
              {trend}
            </span>
          )}
        </div>

        {/* Content */}
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            {title}
          </p>
          <p className="text-2xl font-bold text-zinc-100 tracking-tight">
            {value}
          </p>
          {subvalue && (
            <p className="text-sm text-zinc-400">
              {subvalue}
            </p>
          )}
        </div>

        {/* Progress bar for certain metrics */}
        <div className="mt-4">
          <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
            <div className={`h-full bg-gradient-to-r ${color} transition-all duration-500`} style={{ width: "68%" }} />
          </div>
        </div>
      </div>
    </div>
  );
};

// Redesigned Project Card with enhanced visuals
export const RedesignedProjectCard: React.FC<{
  project: {
    id: string;
    name: string;
    description: string;
    stage: string;
    progress: number;
    coverImage?: string;
    lastModified: string;
    teamMembers: number;
    tags: string[];
  };
  onClick?: () => void;
}> = ({ project, onClick }) => {
  const [isHovered, setIsHovered] = useState(false);

  const stageColors = {
    acquisition: "from-indigo-500 to-violet-500",
    panels: "from-violet-500 to-purple-500",
    ocr: "from-cyan-500 to-blue-500",
    story: "from-emerald-500 to-teal-500",
    script: "from-amber-500 to-orange-500",
    render: "from-rose-500 to-pink-500",
  };

  const stageGradient = stageColors[project.stage as keyof typeof stageColors] || stageColors.acquisition;

  return (
    <div
      className="group relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      {/* Card glow */}
      <div className={`absolute -inset-[1px] bg-gradient-to-r ${stageGradient} rounded-2xl opacity-0 group-hover:opacity-20 blur transition-opacity`} />
      
      <div className="relative bg-zinc-900/90 backdrop-blur-xl border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-700 transition-all duration-300">
        {/* Image / Visual */}
        <div className="relative h-48 overflow-hidden">
          {project.coverImage ? (
            <img
              src={project.coverImage}
              alt={project.name}
              className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
            />
          ) : (
            <div className={`w-full h-full bg-gradient-to-br ${stageGradient} opacity-20`} />
          )}
          
          {/* Overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 via-zinc-900/50 to-transparent" />
          
          {/* Stage indicator */}
          <div className="absolute top-4 left-4">
            <div className={`px-3 py-1.5 rounded-full bg-zinc-900/80 backdrop-blur-md border border-zinc-700 text-xs font-bold uppercase tracking-wider`}>
              <span className={`bg-gradient-to-r ${stageGradient} bg-clip-text text-transparent`}>
                {project.stage}
              </span>
            </div>
          </div>

          {/* Progress indicator */}
          <div className="absolute top-4 right-4">
            <div className="w-12 h-12 relative">
              <svg className="w-12 h-12 transform -rotate-90">
                <circle cx="24" cy="24" r="20" stroke="rgba(39,39,42,0.5)" strokeWidth="3" fill="none" />
                <circle
                  cx="24"
                  cy="24"
                  r="20"
                  stroke="url(#progressGradient)"
                  strokeWidth="3"
                  fill="none"
                  strokeLinecap="round"
                  strokeDasharray={`${project.progress * 1.256} 125.6`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xs font-bold text-zinc-100">{project.progress}%</span>
              </div>
            </div>
          </div>

          {/* Quick actions (on hover) */}
          <div className={`absolute bottom-4 right-4 flex gap-2 transition-all duration-300 ${isHovered ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"}`}>
            <button className="p-2 bg-zinc-900/80 backdrop-blur-md rounded-lg border border-zinc-700 hover:bg-zinc-800 transition-colors">
              <Sparkles className="w-4 h-4 text-zinc-300" />
            </button>
            <button className="p-2 bg-zinc-900/80 backdrop-blur-md rounded-lg border border-zinc-700 hover:bg-zinc-800 transition-colors">
              <Zap className="w-4 h-4 text-zinc-300" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 space-y-3">
          <div>
            <h3 className="text-lg font-bold text-zinc-100 group-hover:text-indigo-400 transition-colors">
              {project.name}
            </h3>
            <p className="text-sm text-zinc-400 line-clamp-2 mt-1">
              {project.description}
            </p>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-2">
            {project.tags.slice(0, 3).map((tag, index) => (
              <span key={index} className="px-2.5 py-1 rounded-full bg-zinc-800 text-xs text-zinc-400 border border-zinc-700">
                {tag}
              </span>
            ))}
          </div>

          {/* Footer metadata */}
          <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {project.lastModified}
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3" />
                {project.teamMembers}
              </span>
            </div>
            <ChevronDown className={`w-4 h-4 text-zinc-600 transition-transform duration-300 ${isHovered ? "rotate-180" : ""}`} />
          </div>
        </div>
      </div>
    </div>
  );
};

// Enhanced Dashboard Header with improved UX
export const RedesignedDashboardHeader: React.FC<{
  onNewProject: () => void;
  onSearch: () => void;
}> = ({ onNewProject, onSearch }) => {
  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-zinc-950/80 border-b border-zinc-800">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Logo & Navigation */}
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                <span className="text-white font-black text-lg">P</span>
              </div>
              <div>
                <h1 className="text-xl font-bold text-zinc-100">PanelFlow</h1>
                <p className="text-xs text-zinc-500 -mt-0.5">Studio Pro</p>
              </div>
            </div>

            <nav className="hidden lg:flex items-center gap-1">
              {[
                { icon: LayoutDashboard, label: "Dashboard" },
                { icon: FolderKanban, label: "Projects" },
                { icon: BarChart3, label: "Analytics" },
                { icon: Settings, label: "Settings" },
              ].map((item, index) => (
                <button
                  key={index}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 transition-colors"
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={onSearch}
              className="hidden sm:flex items-center gap-2 px-4 py-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-sm text-zinc-400 hover:text-zinc-100 transition-colors"
            >
              <Search className="w-4 h-4" />
              <span className="hidden lg:inline">Search</span>
              <kbd className="hidden lg:inline ml-2 px-2 py-0.5 rounded bg-zinc-800 text-xs">⌘K</kbd>
            </button>

            <button className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-100 transition-colors relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-rose-500 rounded-full" />
            </button>

            <button
              onClick={onNewProject}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-medium text-sm hover:shadow-lg hover:shadow-indigo-500/20 transition-all hover:scale-[1.02]"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">New Project</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

// Main Dashboard Layout
export const RedesignedDashboard: React.FC = () => {
  const systemMetrics = [
    {
      icon: <Zap className="w-5 h-5" />,
      title: "GPU Utilization",
      value: "68%",
      subvalue: "15.2 GB / 22 GB",
      trend: "+12%",
      status: "healthy" as const,
      color: "from-emerald-500 to-teal-500",
    },
    {
      icon: <BarChart3 className="w-5 h-5" />,
      title: "Active Jobs",
      value: "12",
      subvalue: "3 running • 9 queued",
      trend: "+4",
      status: "healthy" as const,
      color: "from-indigo-500 to-violet-500",
    },
    {
      icon: <TrendingUp className="w-5 h-5" />,
      title: "Throughput",
      value: "2.4x",
      subvalue: "Pages per minute",
      trend: "+18%",
      status: "healthy" as const,
      color: "from-cyan-500 to-blue-500",
    },
    {
      icon: <Users className="w-5 h-5" />,
      title: "Team Active",
      value: "8",
      subvalue: "5 editing now",
      trend: "Stable",
      status: "warning" as const,
      color: "from-amber-500 to-orange-500",
    },
  ];

  return (
    <div className="min-h-screen bg-[#080b12] text-zinc-100">
      <RedesignedDashboardHeader
        onNewProject={() => console.log("New project")}
        onSearch={() => console.log("Search")}
      />
      
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Hero Section */}
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/10 via-violet-500/10 to-cyan-500/10 rounded-3xl blur-3xl" />
          <div className="relative bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-3xl p-8">
            <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-6">
              <div>
                <h2 className="text-3xl font-bold text-zinc-100 mb-2">
                  Welcome back, <span className="text-transparent bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text">Creator</span>
                </h2>
                <p className="text-zinc-400">You have 3 active projects and 12 jobs processing</p>
              </div>
              <div className="flex gap-3">
                <button className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors">
                  Quick Start
                </button>
                <button className="px-6 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-medium transition-colors">
                  View Tutorials
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* System Overview */}
        <div>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold text-zinc-100">System Overview</h3>
            <button className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
              View details →
            </button>
          </div>
          <RedesignedSystemOverview metrics={systemMetrics} />
        </div>

        {/* Projects Grid */}
        <div>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold text-zinc-100">Recent Projects</h3>
            <div className="flex gap-2">
              <button className="px-4 py-2 rounded-xl bg-zinc-900 border border-zinc-800 text-sm text-zinc-400 hover:text-zinc-100">
                Filter
              </button>
              <button className="px-4 py-2 rounded-xl bg-zinc-900 border border-zinc-800 text-sm text-zinc-400 hover:text-zinc-100">
                Sort
              </button>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Project cards will be mapped here */}
            <RedesignedProjectCard
              project={{
                id: "1",
                name: "Manga Series: Cyber Samurai",
                description: "Futuristic cyberpunk manga with advanced motion effects and dynamic camera work",
                stage: "render",
                progress: 87,
                lastModified: "2 hours ago",
                teamMembers: 4,
                tags: ["Motion", "Cyberpunk", "Series"],
              }}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

export default RedesignedDashboard;
