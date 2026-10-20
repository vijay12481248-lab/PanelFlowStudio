import React, { useState, useEffect } from "react";

export interface CameraBox {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  center_x?: number;
  center_y?: number;
  zoom?: number;
}

export interface SvgCameraFramingVisualizerProps {
  imageUrl?: string;
  startCamera?: CameraBox;
  endCamera?: CameraBox;
  motionType?: string;
  durationSec?: number;
  easing?: string;
  className?: string;
}

function normalizeRect(cam?: CameraBox): { x: number; y: number; w: number; h: number; cx: number; cy: number } {
  if (!cam) {
    return { x: 0.05, y: 0.05, w: 0.9, h: 0.9 * (9 / 16), cx: 0.5, cy: 0.5 };
  }

  // If center_x and zoom are defined
  if (typeof cam.center_x === "number" && typeof cam.center_y === "number") {
    const zoom = Math.max(0.5, cam.zoom || 1.0);
    const w = Math.min(1.0, 1.0 / zoom);
    const h = Math.min(1.0, w * (9 / 16));
    const cx = Math.max(w / 2, Math.min(1.0 - w / 2, cam.center_x));
    const cy = Math.max(h / 2, Math.min(1.0 - h / 2, cam.center_y));
    const x = Math.max(0, cx - w / 2);
    const y = Math.max(0, cy - h / 2);
    return { x, y, w, h, cx, cy };
  }

  // If x, y, width, height are defined
  const x = cam.x ?? 0.05;
  const y = cam.y ?? 0.05;
  const w = cam.width ?? 0.9;
  const h = cam.height ?? (w * (9 / 16));
  const cx = x + w / 2;
  const cy = y + h / 2;
  return { x, y, w, h, cx, cy };
}

export const SvgCameraFramingVisualizer: React.FC<SvgCameraFramingVisualizerProps> = ({
  imageUrl,
  startCamera,
  endCamera,
  motionType = "STATIC",
  durationSec = 3.0,
  easing = "SMOOTHSTEP",
  className = "",
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playProgress, setPlayProgress] = useState<number>(0);

  const start = normalizeRect(startCamera);
  const end = normalizeRect(endCamera);

  const isMoving =
    Math.abs(start.cx - end.cx) > 0.015 ||
    Math.abs(start.cy - end.cy) > 0.015 ||
    Math.abs(start.w - end.w) > 0.015;

  // Active interpolated rectangle during playback
  const currX = start.x + (end.x - start.x) * playProgress;
  const currY = start.y + (end.y - start.y) * playProgress;
  const currW = start.w + (end.w - start.w) * playProgress;
  const currH = start.h + (end.h - start.h) * playProgress;

  useEffect(() => {
    if (!isPlaying) return;

    let startTime = performance.now();
    const animDuration = Math.min(4000, Math.max(1500, durationSec * 1000));
    let frameId: number;

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / animDuration);

      // Smoothstep easing: 3x^2 - 2x^3
      const eased = progress * progress * (3 - 2 * progress);
      setPlayProgress(eased);

      if (progress < 1.0) {
        frameId = requestAnimationFrame(step);
      } else {
        setTimeout(() => {
          setIsPlaying(false);
          setPlayProgress(0);
        }, 300);
      }
    };

    frameId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameId);
  }, [isPlaying, durationSec]);

  const uniqueId = React.useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const markerId = `cam-arrow-${uniqueId}`;

  return (
    <div className={`relative w-44 h-32 rounded-lg overflow-hidden bg-zinc-950 border border-zinc-800 shadow-md group flex-shrink-0 select-none ${className}`}>
      {/* Background Panel Image */}
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Panel preview"
          className="w-full h-full object-cover opacity-80 group-hover:opacity-90 transition-opacity"
          onError={(e) => {
            (e.target as HTMLElement).style.display = "none";
          }}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-zinc-900 text-zinc-600 text-[10px] font-mono">
          [Panel Preview]
        </div>
      )}

      {/* SVG Viewport & Trajectory Overlay */}
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 w-full h-full overflow-visible pointer-events-none"
      >
        <defs>
          <marker
            id={markerId}
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="4"
            markerHeight="4"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 8 5 L 0 9 z" fill="#38bdf8" />
          </marker>
        </defs>

        {/* Trajectory Vector Line */}
        {isMoving && !isPlaying && (
          <line
            x1={start.cx * 100}
            y1={start.cy * 100}
            x2={end.cx * 100}
            y2={end.cy * 100}
            stroke="#38bdf8"
            strokeWidth="1.5"
            strokeDasharray="2 1.5"
            markerEnd={`url(#${markerId})`}
            opacity="0.85"
          />
        )}

        {/* Start Framing Rect (Cyan Dashed) */}
        {!isPlaying && (
          <g>
            <rect
              x={start.x * 100}
              y={start.y * 100}
              width={start.w * 100}
              height={start.h * 100}
              rx="1.5"
              stroke="#06b6d4"
              strokeWidth="1.2"
              strokeDasharray="3 1.5"
              fill="rgba(6, 182, 212, 0.12)"
            />
            <rect
              x={start.x * 100}
              y={Math.max(0, start.y * 100 - 6)}
              width="14"
              height="5.5"
              rx="1"
              fill="#06b6d4"
            />
            <text
              x={start.x * 100 + 7}
              y={Math.max(0, start.y * 100 - 2)}
              fill="#082f49"
              fontSize="3.5"
              fontWeight="bold"
              textAnchor="middle"
              fontFamily="sans-serif"
            >
              IN
            </text>
          </g>
        )}

        {/* End Framing Rect (Indigo Solid) */}
        {!isPlaying && isMoving && (
          <g>
            <rect
              x={end.x * 100}
              y={end.y * 100}
              width={end.w * 100}
              height={end.h * 100}
              rx="1.5"
              stroke="#818cf8"
              strokeWidth="1.4"
              fill="rgba(129, 140, 248, 0.18)"
            />
            <rect
              x={end.x * 100 + end.w * 100 - 16}
              y={Math.max(0, end.y * 100 - 6)}
              width="16"
              height="5.5"
              rx="1"
              fill="#6366f1"
            />
            <text
              x={end.x * 100 + end.w * 100 - 8}
              y={Math.max(0, end.y * 100 - 2)}
              fill="#ffffff"
              fontSize="3.5"
              fontWeight="bold"
              textAnchor="middle"
              fontFamily="sans-serif"
            >
              OUT
            </text>
          </g>
        )}

        {/* Active Animated Camera Rect during Playback */}
        {isPlaying && (
          <g>
            <rect
              x={currX * 100}
              y={currY * 100}
              width={currW * 100}
              height={currH * 100}
              rx="2"
              stroke="#fbbf24"
              strokeWidth="2"
              fill="rgba(251, 191, 36, 0.22)"
            />
            <circle cx={currX * 100 + currW * 50} cy={currY * 100 + currH * 50} r="2" fill="#fbbf24" />
          </g>
        )}
      </svg>

      {/* Floating Badges & Action Trigger */}
      <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
        <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-black/75 backdrop-blur-sm text-cyan-300 border border-cyan-800/60 shadow">
          {motionType}
        </span>
      </div>

      {isMoving && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setIsPlaying(true);
          }}
          className="absolute bottom-1.5 right-1.5 px-2 py-0.5 rounded bg-black/85 hover:bg-indigo-600 border border-zinc-700 hover:border-indigo-400 text-zinc-200 hover:text-white text-[10px] font-bold transition-all shadow-md flex items-center gap-1 opacity-80 group-hover:opacity-100"
          title="Simulate Camera Panning & Zoom Framing"
        >
          <span>{isPlaying ? "Seeking..." : "▶ Preview"}</span>
        </button>
      )}
    </div>
  );
};
