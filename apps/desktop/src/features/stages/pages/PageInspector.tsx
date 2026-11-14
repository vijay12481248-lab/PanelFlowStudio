import React from "react";
import { ChevronLeft, ChevronRight, RotateCw, ZoomIn, ZoomOut } from "lucide-react";
import type { Page } from "@panelflow/shared-types";
import { Button, Drawer, IconButton } from "@panelflow/ui-v2";
import { clampZoom, defaultViewMode, type ViewMode } from "./pagesModel";

export interface PageInspectorProps {
  pages: Page[];
  /** The page being inspected, or null when closed. */
  openId: string | null;
  imageUrl: (page: Page) => string;
  onOpen: (pageId: string) => void;
  onClose: () => void;
  onRotate: (page: Page) => void;
}

const MODES: Array<{ mode: ViewMode; label: string; text: string }> = [
  { mode: "fit-width", label: "Fit width", text: "Fit width" },
  { mode: "fit-page", label: "Fit page", text: "Fit page" },
  { mode: "original", label: "Original size", text: "Original" },
];

/** A page at reading size: view modes, zoom, previous and next (also with the arrow keys), and rotate. */
export const PageInspector: React.FC<PageInspectorProps> = ({ pages, openId, imageUrl, onOpen, onClose, onRotate }) => {
  const index = openId ? pages.findIndex((p) => p.id === openId) : -1;
  const page = index >= 0 ? pages[index] : null;
  const [mode, setMode] = React.useState<ViewMode>("fit-page");
  const [zoom, setZoom] = React.useState(100);

  // Each page opens in its natural mode at 100 percent.
  React.useEffect(() => {
    if (page) { setMode(defaultViewMode(page)); setZoom(100); }
  }, [page?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const step = (delta: number) => {
    const next = pages[index + delta];
    if (next) onOpen(next.id);
  };
  const stepRef = React.useRef(step);
  stepRef.current = step;
  React.useEffect(() => {
    if (!page) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") stepRef.current(-1);
      else if (event.key === "ArrowRight") stepRef.current(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const src = page ? imageUrl(page) : "";
  const image =
    !page ? null : mode === "fit-width" ? (
      <div className="mx-auto" style={{ width: `${zoom}%` }}><img src={src} alt={`Page ${page.sequence}`} className="block h-auto w-full rounded-ctl" /></div>
    ) : mode === "fit-page" ? (
      <div className="grid min-h-full w-full place-items-center">
        <img src={src} alt={`Page ${page.sequence}`} style={{ maxHeight: `${Math.round(58 * (zoom / 100))}vh`, maxWidth: `${zoom}%` }} className="block h-auto w-auto rounded-ctl object-contain" />
      </div>
    ) : (
      <div className="mx-auto" style={{ width: `${Math.round(page.width * (zoom / 100))}px`, maxWidth: "none" }}><img src={src} alt={`Page ${page.sequence}`} className="block h-auto w-full rounded-ctl" /></div>
    );

  return (
    <Drawer open={Boolean(page)} onOpenChange={(open) => { if (!open) onClose(); }} size="wide" title={page ? `Page ${index + 1} of ${pages.length}` : "Page"} description={page ? page.filename : undefined}>
      {page && (
        <div className="grid grid-cols-1 gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1">
              <IconButton label="Previous page" disabled={index <= 0} onClick={() => step(-1)}><ChevronLeft size={16} /></IconButton>
              <IconButton label="Next page" disabled={index >= pages.length - 1} onClick={() => step(1)}><ChevronRight size={16} /></IconButton>
            </div>
            <div className="flex items-center gap-1" role="group" aria-label="View mode">
              {MODES.map((m) => (
                <Button key={m.mode} size="sm" variant={mode === m.mode ? "primary" : "ghost"} aria-label={m.label} aria-pressed={mode === m.mode} onClick={() => { setMode(m.mode); setZoom(100); }}>{m.text}</Button>
              ))}
            </div>
            <div className="flex items-center gap-1">
              <IconButton label="Zoom out" onClick={() => setZoom((z) => clampZoom(z, -25))}><ZoomOut size={16} /></IconButton>
              <Button size="sm" variant="ghost" aria-label="Reset zoom" onClick={() => setZoom(100)}>{`${zoom}%`}</Button>
              <IconButton label="Zoom in" onClick={() => setZoom((z) => clampZoom(z, 25))}><ZoomIn size={16} /></IconButton>
              <IconButton label="Rotate this page" onClick={() => onRotate(page)}><RotateCw size={16} /></IconButton>
            </div>
          </div>
          <div className="h-[62vh] overflow-auto rounded-ctl border border-edge bg-glass p-3">{image}</div>
          <p className="text-xs text-fg-dim">{`${page.width} × ${page.height} px · ${(page.byte_size / (1024 * 1024)).toFixed(2)} MB · ${page.height > page.width * 2 ? "Webtoon strip" : "Standard page"}`}</p>
        </div>
      )}
    </Drawer>
  );
};
