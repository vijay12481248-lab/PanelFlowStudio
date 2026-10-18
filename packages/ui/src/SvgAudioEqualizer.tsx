import React from "react";

export interface SvgAudioEqualizerProps {
  isPlaying?: boolean;
  barCount?: number;
  className?: string;
  theme?: "indigo" | "emerald" | "cyan" | "rose";
}

export const SvgAudioEqualizer: React.FC<SvgAudioEqualizerProps> = ({
  isPlaying = true,
  barCount = 5,
  className = "",
  theme = "indigo",
}) => {
  const themeColors = {
    indigo: { start: "#818cf8", end: "#4f46e5", glow: "rgba(99, 102, 241, 0.4)" },
    emerald: { start: "#34d399", end: "#059669", glow: "rgba(16, 185, 129, 0.4)" },
    cyan: { start: "#22d3ee", end: "#0891b2", glow: "rgba(6, 182, 212, 0.4)" },
    rose: { start: "#fb7185", end: "#e11d48", glow: "rgba(244, 63, 94, 0.4)" },
  }[theme];

  const barConfigs = [
    { duration: "0.85s", minH: 4, maxH: 16, delay: "0.0s" },
    { duration: "0.7s", minH: 3, maxH: 22, delay: "0.15s" },
    { duration: "0.95s", minH: 6, maxH: 20, delay: "0.3s" },
    { duration: "0.65s", minH: 2, maxH: 18, delay: "0.45s" },
    { duration: "0.8s", minH: 5, maxH: 24, delay: "0.2s" },
    { duration: "0.75s", minH: 3, maxH: 15, delay: "0.35s" },
    { duration: "0.9s", minH: 4, maxH: 21, delay: "0.1s" },
  ];

  const bars = barConfigs.slice(0, barCount);
  const totalWidth = bars.length * 5 + (bars.length - 1) * 3;

  return (
    <div className={`inline-flex items-center justify-center ${className}`}>
      <svg
        viewBox={`0 0 ${totalWidth} 26`}
        className="h-5 w-auto overflow-visible"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id={`eq-grad-${theme}`} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={themeColors.end} />
            <stop offset="100%" stopColor={themeColors.start} />
          </linearGradient>
        </defs>

        <style>{`
          @keyframes eqBounce {
            0%, 100% { transform: scaleY(0.25); }
            50% { transform: scaleY(1.0); }
          }
          .eq-bar-animated {
            transform-box: fill-box;
            transform-origin: bottom;
            animation: eqBounce var(--eq-dur) ease-in-out infinite;
            animation-delay: var(--eq-del);
          }
        `}</style>

        {bars.map((b, idx) => {
          const x = idx * 8;
          return (
            <rect
              key={idx}
              x={x}
              y={2}
              width={4}
              height={22}
              rx={2}
              fill={`url(#eq-grad-${theme})`}
              className={isPlaying ? "eq-bar-animated" : undefined}
              style={
                isPlaying
                  ? ({
                      "--eq-dur": b.duration,
                      "--eq-del": b.delay,
                    } as React.CSSProperties)
                  : {
                      transformBox: "fill-box",
                      transformOrigin: "bottom",
                      transform: `scaleY(${b.minH / 22})`,
                      opacity: 0.5,
                    }
              }
            />
          );
        })}
      </svg>
    </div>
  );
};
