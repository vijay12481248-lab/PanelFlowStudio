import React from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, BookOpen, FolderKanban, Home, Search, SlidersHorizontal, Sparkles } from "lucide-react";
import { api } from "@panelflow/api-client";
import { Button, Dock, EngineStatus, ErrorState, IconButton, type DockItem } from "@panelflow/ui-v2";
import { ErrorAlertBanner, ErrorDetailsModal, ErrorNotificationBell } from "../components/error";
import { useError } from "../context/ErrorContext";
import { CommandPalette } from "./CommandPalette";
import { buildCommands } from "./commands";
import { useEngine } from "./providers";
import { paths } from "./routes";

const DOCK_ITEMS: DockItem[] = [
  { id: "home", label: "Home", icon: <Home size={20} />, href: paths.home() },
  { id: "projects", label: "Projects", icon: <FolderKanban size={20} />, href: paths.projects() },
  { id: "create", label: "Create", icon: <Sparkles size={20} />, href: paths.create() },
  { id: "jobs", label: "Jobs", icon: <Activity size={20} />, href: paths.jobs() },
  { id: "library", label: "Library", icon: <BookOpen size={20} />, href: paths.library() },
  { id: "settings", label: "Settings", icon: <SlidersHorizontal size={20} />, href: paths.settings() },
];

/** Routes that take the whole window (their screens bring their own toolbar and back button). */
export function isImmersive(pathname: string): boolean {
  return pathname.startsWith("/editor/") || pathname.startsWith("/create/chronoflow");
}

/** The dock destination is the first path segment ("/settings/providers" belongs to Settings); the editor belongs to Projects. */
function activeDockId(pathname: string): string {
  const segment = pathname.split("/")[1];
  if (segment === "editor") return "projects";
  return DOCK_ITEMS.some((item) => item.id === segment) ? segment : "home";
}

const EngineGate: React.FC = () => {
  const engine = useEngine();
  if (engine.startupGrace) {
    return (
      <div role="status" className="grid h-full place-items-center text-center">
        <div className="grid gap-2">
          <h2 className="font-display text-xl font-semibold text-fg">Connecting to the PanelFlow engine</h2>
          <p className="text-sm text-fg-dim">Starting the local AI pipeline on 127.0.0.1:8765. This takes a few seconds.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="grid h-full place-items-center">
      <ErrorState
        title="Processing engine unavailable"
        description="The local engine on 127.0.0.1:8765 is not responding. Start it to continue; you stay on this page."
        onRetry={engine.retrying ? undefined : () => void engine.retry()}
      />
    </div>
  );
};

export const AppShell: React.FC = () => {
  const engine = useEngine();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { selectedError, closeInspector, dismissError, retryJob } = useError();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const immersive = isImmersive(pathname);

  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects(), enabled: engine.connected && paletteOpen });
  const commands = React.useMemo(() => buildCommands({ projects: projects.data ?? [] }), [projects.data]);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="pf-canvas flex h-screen flex-col overflow-hidden">
      {!immersive && (
        <header className="flex items-center gap-3 px-6 py-3">
          <Link to={paths.home()} className="font-display text-base font-bold tracking-tight text-fg">PanelFlow Studio</Link>
          <span className="flex-1" />
          <EngineStatus connected={engine.connected} version={engine.connected ? `v${engine.version}` : undefined} />
          <Button variant="ghost" size="sm" disabled={!engine.connected || engine.restarting || engine.retrying} loading={engine.restarting} onClick={() => void engine.restart()}>
            {engine.restarting ? "Restarting" : "Restart engine"}
          </Button>
          <ErrorNotificationBell />
          <IconButton label="Open command palette (Ctrl K)" onClick={() => setPaletteOpen(true)}><Search size={16} /></IconButton>
        </header>
      )}

      <main className="min-h-0 flex-1 overflow-y-auto">{engine.connected ? <Outlet /> : <EngineGate />}</main>

      {!immersive && (
        <div className="px-4 pb-4 pt-2">
          <Dock items={DOCK_ITEMS} activeId={activeDockId(pathname)} renderLink={(item, children) => <Link to={item.href}>{children}</Link>} />
        </div>
      )}

      <ErrorAlertBanner />
      <ErrorDetailsModal error={selectedError} onClose={closeInspector} onDismissAlert={dismissError} onRetryJob={retryJob} />
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        commands={commands}
        onSelect={(command) => { setPaletteOpen(false); navigate(command.to); }}
      />
    </div>
  );
};
