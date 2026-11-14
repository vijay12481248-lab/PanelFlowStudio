import React from "react";
import { Crop, Layers, Palette, Share2, Sparkles } from "lucide-react";
import type { StudioPage } from "./types";

// Same rail as ChronoFlow's workspace. Pages that are not built yet are shown, so the whole plan is visible, but cannot be opened.
const PAGES: { id: StudioPage; label: string; Icon: React.ComponentType<{ className?: string }>; ready: boolean }[] = [
  { id: "ai", label: "AI", Icon: Sparkles, ready: true },
  { id: "cut", label: "Cut", Icon: Crop, ready: false },
  { id: "fusion", label: "Fusion", Icon: Layers, ready: false },
  { id: "color", label: "Color", Icon: Palette, ready: false },
  { id: "deliver", label: "Deliver", Icon: Share2, ready: true },
];

export const PageRail: React.FC<{ page: StudioPage; onPage: (page: StudioPage) => void }> = ({ page, onPage }) => (
  <nav aria-label="Editor pages" className="flex items-center justify-center gap-1 border-t border-edge bg-navy px-3 py-1.5">
    {PAGES.map(({ id, label, Icon, ready }) => (
      <button
        key={id}
        type="button"
        disabled={!ready}
        aria-current={page === id ? "page" : undefined}
        onClick={() => onPage(id)}
        title={ready ? label : `${label} is coming in the next phase`}
        className={`flex min-w-20 flex-col items-center gap-0.5 rounded-lg px-4 py-1.5 text-[11px] transition-colors ${
          page === id
            ? "bg-accent-soft text-fg"
            : ready
            ? "text-fg-dim hover:text-fg hover:bg-flat"
            : "cursor-not-allowed text-fg-faint/60"
        }`}
      >
        <Icon className="h-4 w-4" />
        <span>{label}</span>
      </button>
    ))}
  </nav>
);
