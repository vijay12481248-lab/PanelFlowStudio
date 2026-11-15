import React from "react";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Panel, TextRegion } from "@panelflow/shared-types";
import { Button } from "@panelflow/ui-v2";
import type { Box } from "../kit/canvas/geometry";
import { PageCanvas, type CanvasBox } from "../kit/canvas/PageCanvas";
import { useFitZoom } from "../kit/canvas/useFitZoom";
import { regionTone } from "./ocrModel";

const MIN = 25;
const MAX = 300;
const clamp = (zoom: number) => Math.min(MAX, Math.max(MIN, Math.round(zoom)));

export interface RegionCanvasProps {
  projectId: string;
  panel: Panel;
  regions: TextRegion[];
  selectedRegionId: string | null;
  onSelectRegion: (id: string | null) => void;
  cropBuster: number;
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  /** Drawing a new box on the crop (a manual region or a blur area). */
  drawMode?: boolean;
  onDraw?: (box: Box) => void;
  /** More tools beside the zoom buttons. */
  tools?: React.ReactNode;
  /** An extra layer of boxes drawn over the regions, such as a pending blur area. */
  extraBoxes?: CanvasBox[];
}

/** A panel's crop with its text regions over it. Regions are selected, not moved. Zoom is 25 to 300 percent. */
export const RegionCanvas: React.FC<RegionCanvasProps> = ({ projectId, panel, regions, selectedRegionId, onSelectRegion, cropBuster, hasPrevious, hasNext, onPrevious, onNext, drawMode = false, onDraw, tools, extraBoxes = [] }) => {
  const fit = useFitZoom(panel.width, MIN);
  const [zoomMode, setZoomMode] = React.useState<"fit" | number>("fit");
  const zoom = zoomMode === "fit" ? clamp(fit.zoom) : zoomMode;
  const zoomRef = React.useRef(zoom);
  zoomRef.current = zoom;

  // Ctrl + wheel zooms; a plain wheel scrolls the crop. The listener is not passive so the page does not zoom as well.
  const area = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    const el = area.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      setZoomMode(clamp(zoomRef.current * (event.deltaY > 0 ? 0.9 : 1.1)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const boxes: CanvasBox[] = [
    ...regions.map((r) => ({ id: r.id, box: { x: r.x, y: r.y, w: r.width, h: r.height }, label: `Region ${r.sequence_in_panel}`, tone: regionTone(r) as CanvasBox["tone"], fixed: true })),
    ...extraBoxes,
  ];

  return (
    <div className="grid min-w-0 content-start gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" icon={<ChevronLeft size={14} />} disabled={!hasPrevious} onClick={onPrevious}>Previous panel</Button>
        <Button size="sm" variant="ghost" icon={<ChevronRight size={14} />} disabled={!hasNext} onClick={onNext}>Next panel</Button>
        <Button size="sm" variant="ghost" icon={<ZoomOut size={14} />} onClick={() => setZoomMode(clamp(zoom * 0.8))}>Zoom out</Button>
        <Button size="sm" variant="ghost" onClick={() => setZoomMode("fit")}>Fit</Button>
        <Button size="sm" variant="ghost" icon={<ZoomIn size={14} />} onClick={() => setZoomMode(clamp(zoom * 1.25))}>Zoom in</Button>
        <span data-zoom-label className="font-data text-xs text-fg-faint">{`${zoom}%`}</span>
        {tools}
      </div>
      <div ref={(el) => { area.current = el; fit.ref.current = el; }} data-region-canvas className="min-w-0">
        <PageCanvas
          key={panel.id}
          className="h-[60vh]"
          image={{ src: `${api.getPanelImageUrl(projectId, panel.id)}?t=${cropBuster}`, width: panel.width, height: panel.height, alt: `Panel ${panel.sequence}` }}
          boxes={boxes}
          selectedId={selectedRegionId}
          zoom={zoom}
          drawMode={drawMode}
          unavailableLabel="Panel image unavailable"
          onSelect={(id) => onSelectRegion(id)}
          onDraw={onDraw}
        />
      </div>
    </div>
  );
};
