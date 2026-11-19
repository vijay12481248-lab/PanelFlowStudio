import React, { useRef, useState, useEffect } from "react";
import type { DefectRecord } from "@panelflow/api-client";

interface DefectCanvasOverlayProps {
  imageUrl: string;
  defects: DefectRecord[];
  selectedDefectId?: string | null;
  onSelectDefect?: (defectId: string) => void;
  className?: string;
}

const SEVERITY_COLORS: Record<string, { stroke: string; fill: string; badge: string }> = {
  minor: {
    stroke: "#38bdf8", // Sky 400
    fill: "rgba(56, 189, 248, 0.15)",
    badge: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  },
  moderate: {
    stroke: "#f59e0b", // Amber 500
    fill: "rgba(245, 158, 11, 0.18)",
    badge: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  },
  severe: {
    stroke: "#ef4444", // Red 500
    fill: "rgba(239, 68, 68, 0.22)",
    badge: "bg-red-500/20 text-red-300 border-red-500/40",
  },
};

export const DefectCanvasOverlay: React.FC<DefectCanvasOverlayProps> = ({
  imageUrl,
  defects,
  selectedDefectId,
  onSelectDefect,
  className = "",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });

  return (
    <div
      ref={containerRef}
      className={`relative inline-block overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/80 shadow-2xl ${className}`}
    >
      <img
        src={imageUrl}
        alt="Inspected target"
        className="block max-h-[560px] w-auto max-w-full object-contain"
        onLoad={(e) => {
          const img = e.currentTarget;
          setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
        }}
      />

      {/* SVG Overlay layer for bounding boxes */}
      <svg
        className="absolute inset-0 h-full w-full pointer-events-none"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        {defects.map((defect) => {
          if (!defect.bbox) return null;
          const [x1, y1, x2, y2] = defect.bbox;
          const isSelected = selectedDefectId === defect.defect_id;
          const styling = SEVERITY_COLORS[defect.severity] || SEVERITY_COLORS.moderate;

          // Normalize to percentage coordinates
          const left = x1 * 100;
          const top = y1 * 100;
          const width = (x2 - x1) * 100;
          const height = (y2 - y1) * 100;

          return (
            <g key={defect.defect_id} className="pointer-events-auto cursor-pointer" onClick={() => onSelectDefect?.(defect.defect_id)}>
              <rect
                x={left}
                y={top}
                width={width}
                height={height}
                fill={isSelected ? styling.fill.replace("0.18", "0.35") : styling.fill}
                stroke={styling.stroke}
                strokeWidth={isSelected ? 1.5 : 0.8}
                strokeDasharray={isSelected ? "2 1" : undefined}
                className="transition-all duration-200"
              />
            </g>
          );
        })}
      </svg>

      {/* HTML interactive badges positioned over boxes */}
      {defects.map((defect) => {
        if (!defect.bbox) return null;
        const [x1, y1] = defect.bbox;
        const isSelected = selectedDefectId === defect.defect_id;
        const styling = SEVERITY_COLORS[defect.severity] || SEVERITY_COLORS.moderate;

        return (
          <button
            key={`badge-${defect.defect_id}`}
            type="button"
            onClick={() => onSelectDefect?.(defect.defect_id)}
            style={{
              left: `${Math.min(90, Math.max(2, x1 * 100))}%`,
              top: `${Math.min(90, Math.max(2, y1 * 100))}%`,
            }}
            className={`absolute -translate-y-full transform rounded-md px-1.5 py-0.5 text-[11px] font-medium tracking-tight border backdrop-blur-md shadow-lg transition-transform ${
              styling.badge
            } ${isSelected ? "scale-110 ring-2 ring-white/50 z-20" : "hover:scale-105 z-10"}`}
          >
            {defect.category.replace(/_/g, " ")} ({Math.round(defect.confidence * 100)}%)
          </button>
        );
      })}
    </div>
  );
};
