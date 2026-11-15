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
      gradient: "from-ok/10 to-ok/5",
      border: "border-ok/20",
      iconBg: "bg-ok/10",
    },
    warning: {
      gradient: "from-warn/10 to-warn/5",
      border: "border-warn/20",
      iconBg: "bg-warn/10",
    },
    error: {
      gradient: "from-bad/10 to-bad/5",
      border: "border-bad/20",
      iconBg: "bg-bad/10",
    },
  };

  const config = statusConfig[status];

  return (
    <div className="group relative">
      {/* Glow effect */}
      <div className={`absolute -inset-0.5 bg-gradient-to-r ${config.gradient} rounded-2xl blur opacity-0 group-hover:opacity-100 transition-opacity`} />
      
      <div className="relative bg-navy/80 backdrop-blur-xl border border-edge rounded-2xl p-5 hover:border-edge transition-all duration-300">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className={`p-3 rounded-xl ${config.iconBg} border ${config.border}`}>
            <div className="text-fg">
              {icon}
            </div>
          </div>
          {trend && (
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-flat text-fg-dim">
              {trend}
            </span>
          )}
        </div>

        {/* Content */}
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-fg-faint">
            {title}
          </p>
          <p className="text-2xl font-bold text-fg tracking-tight">
            {value}
          </p>
          {subvalue && (
            <p className="text-sm text-fg-dim">
              {subvalue}
            </p>
          )}
        </div>

        {/* Progress bar for certain metrics */}
        <div className="mt-4">
          <div className="h-1 bg-flat rounded-full overflow-hidden">
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
    acquisition: "from-accent to-accent",
    panels: "from-accent to-accent",
    ocr: "from-info to-accent",
    story: "from-ok to-info",
    script: "from-warn to-warn",
    render: "from-bad to-accent",
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
      
      <div className="relative bg-navy/90 backdrop-blur-xl border border-edge rounded-2xl overflow-hidden hover:border-edge transition-all duration-300">
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
          <div className="absolute inset-0 bg-gradient-to-t from-navy via-navy/50 to-transparent" />
          
          {/* Stage indicator */}
          <div className="absolute top-4 left-4">
            <div className={`px-3 py-1.5 rounded-full bg-navy/80 backdrop-blur-md border border-edge text-xs font-bold uppercase tracking-wider`}>
              <span className={`bg-gradient-to-r ${stageGradient} bg-clip-text text-transparent`}>
                {project.stage}
              </span>
            </div>
          </div>

          {/* Progress indicator */}
          <div className="absolute top-4 right-4">
            <div className="w-12 h-12 relative">
              <svg className="w-12 h-12 transform -rotate-90">
                <circle cx="24" cy="24" r="20" stroke="rgba(16,26,61,0.5)" strokeWidth="3" fill="none" />
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
                <span className="text-xs font-bold text-fg">{project.progress}%</span>
              </div>
            </div>
          </div>

          {/* Quick actions (on hover) */}
          <div className={`absolute bottom-4 right-4 flex gap-2 transition-all duration-300 ${isHovered ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"}`}>
            <button className="p-2 bg-navy/80 backdrop-blur-md rounded-lg border border-edge hover:bg-flat transition-colors">
              <Sparkles className="w-4 h-4 text-fg-dim" />
            </button>
            <button className="p-2 bg-navy/80 backdrop-blur-md rounded-lg border border-edge hover:bg-flat transition-colors">
              <Zap className="w-4 h-4 text-fg-dim" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 space-y-3">
          <div>
            <h3 className="text-lg font-bold text-fg group-hover:text-info transition-colors">
              {project.name}
            </h3>
            <p className="text-sm text-fg-dim line-clamp-2 mt-1">
              {project.description}
            </p>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-2">
            {project.tags.slice(0, 3).map((tag, index) => (
              <span key={index} className="px-2.5 py-1 rounded-full bg-flat text-xs text-fg-dim border border-edge">
                {tag}
              </span>
            ))}
          </div>

          {/* Footer metadata */}
          <div className="flex items-center justify-between pt-3 border-t border-edge">
            <div className="flex items-center gap-3 text-xs text-fg-faint">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {project.lastModified}
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3" />
                {project.teamMembers}
              </span>
            </div>
            <ChevronDown className={`w-4 h-4 text-fg-faint transition-transform duration-300 ${isHovered ? "rotate-180" : ""}`} />
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
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-ink/80 border-b border-edge">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Logo & Navigation */}
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-accent flex items-center justify-center shadow-lg shadow-accent/20">
                <span className="text-white font-black text-lg">P</span>
              </div>
              <div>
                <h1 className="text-xl font-bold text-fg">PanelFlow</h1>
                <p className="text-xs text-fg-faint -mt-0.5">Studio Pro</p>
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
                  className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-fg-dim hover:text-fg hover:bg-navy transition-colors"
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
              className="hidden sm:flex items-center gap-2 px-4 py-2 rounded-xl bg-navy border border-edge hover:border-edge text-sm text-fg-dim hover:text-fg transition-colors"
            >
              <Search className="w-4 h-4" />
              <span className="hidden lg:inline">Search</span>
              <kbd className="hidden lg:inline ml-2 px-2 py-0.5 rounded bg-flat text-xs">⌘K</kbd>
            </button>

            <button className="p-2.5 rounded-xl bg-navy border border-edge hover:border-edge text-fg-dim hover:text-fg transition-colors relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-bad rounded-full" />
            </button>

            <button
              onClick={onNewProject}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-accent to-accent text-white font-medium text-sm hover:shadow-lg hover:shadow-accent/20 transition-all hover:scale-[1.02]"
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
      color: "from-ok to-info",
    },
    {
      icon: <BarChart3 className="w-5 h-5" />,
      title: "Active Jobs",
      value: "12",
      subvalue: "3 running • 9 queued",
      trend: "+4",
      status: "healthy" as const,
      color: "from-accent to-accent",
    },
    {
      icon: <TrendingUp className="w-5 h-5" />,
      title: "Throughput",
      value: "2.4x",
      subvalue: "Pages per minute",
      trend: "+18%",
      status: "healthy" as const,
      color: "from-info to-accent",
    },
    {
      icon: <Users className="w-5 h-5" />,
      title: "Team Active",
      value: "8",
      subvalue: "5 editing now",
      trend: "Stable",
      status: "warning" as const,
      color: "from-warn to-warn",
    },
  ];

  return (
    <div className="min-h-screen bg-[#070b1c] text-fg">
      <RedesignedDashboardHeader
        onNewProject={() => console.log("New project")}
        onSearch={() => console.log("Search")}
      />
      
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Hero Section */}
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-accent/10 via-accent/10 to-info/10 rounded-3xl blur-3xl" />
          <div className="relative bg-navy/50 backdrop-blur-xl border border-edge rounded-3xl p-8">
            <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-6">
              <div>
                <h2 className="text-3xl font-bold text-fg mb-2">
                  Welcome back, <span className="text-transparent bg-gradient-to-r from-accent to-accent bg-clip-text">Creator</span>
                </h2>
                <p className="text-fg-dim">You have 3 active projects and 12 jobs processing</p>
              </div>
              <div className="flex gap-3">
                <button className="px-6 py-3 rounded-xl bg-accent hover:bg-accent text-white font-medium transition-colors">
                  Quick Start
                </button>
                <button className="px-6 py-3 rounded-xl bg-flat hover:bg-glass-hi text-fg-dim font-medium transition-colors">
                  View Tutorials
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* System Overview */}
        <div>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold text-fg">System Overview</h3>
            <button className="text-sm text-fg-dim hover:text-fg transition-colors">
              View details →
            </button>
          </div>
          <RedesignedSystemOverview metrics={systemMetrics} />
        </div>

        {/* Projects Grid */}
        <div>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold text-fg">Recent Projects</h3>
            <div className="flex gap-2">
              <button className="px-4 py-2 rounded-xl bg-navy border border-edge text-sm text-fg-dim hover:text-fg">
                Filter
              </button>
              <button className="px-4 py-2 rounded-xl bg-navy border border-edge text-sm text-fg-dim hover:text-fg">
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
