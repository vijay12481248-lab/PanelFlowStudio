import React from "react";

export interface SvgProductionTrophyProps {
  status?: "PRODUCTION_READY" | "VALID" | "WARNING" | "FAILED";
  title?: string;
  subtitle?: string;
  className?: string;
}

export const SvgProductionTrophy: React.FC<SvgProductionTrophyProps> = ({
  status = "PRODUCTION_READY",
  title = "Production Certified",
  subtitle = "100% QA Passed · Zero Defects",
  className = "",
}) => {
  const isPass = status === "PRODUCTION_READY" || status === "VALID";
  const isWarning = status === "WARNING";

  const primaryColor = isPass ? "#46d6a3" : isWarning ? "#f0b35a" : "#f2667a";
  const goldColor = isPass ? "#f0b35a" : isWarning ? "#f0b35a" : "#f2667a";

  return (
    <div className={`relative flex items-center gap-4 p-4 rounded-xl border bg-ink/80 backdrop-blur-md ${
      isPass
        ? "border-ok/40 shadow-lg shadow-ok/30 ring-1 ring-ok/20"
        : isWarning
        ? "border-warn/40 shadow-lg shadow-warn/30 ring-1 ring-warn/20"
        : "border-bad/40 shadow-lg shadow-bad/30"
    } ${className}`}>
      {/* SVG Shimmer Trophy Seal */}
      <div className="relative flex-shrink-0 w-14 h-14 flex items-center justify-center">
        <svg
          viewBox="0 0 64 64"
          className="w-full h-full overflow-visible"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <filter id="trophy-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#f0b35a" />
              <stop offset="50%" stopColor={goldColor} />
              <stop offset="100%" stopColor="#f0b35a" />
            </linearGradient>

            <linearGradient id="emerald-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#46d6a3" />
              <stop offset="50%" stopColor={primaryColor} />
              <stop offset="100%" stopColor="#123d36" />
            </linearGradient>
          </defs>

          <style>{`
            @keyframes starTwinkle {
              0%, 100% { opacity: 0.3; transform: scale(0.85); }
              50% { opacity: 1; transform: scale(1.2); }
            }
            .star-sparkle {
              animation: starTwinkle 2.5s ease-in-out infinite;
              transform-origin: center;
              transform-box: fill-box;
            }
            @keyframes haloRotate {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
            .halo-spin {
              animation: haloRotate 20s linear infinite;
              transform-origin: 32px 32px;
            }
          `}</style>

          {/* Ambient Glow Halo */}
          <circle
            cx="32"
            cy="32"
            r="28"
            stroke={`url(#${isPass ? "emerald-grad" : "gold-grad"})`}
            strokeWidth="1.5"
            strokeDasharray="6 4"
            opacity="0.5"
            className="halo-spin"
            filter="url(#trophy-glow)"
          />

          {/* Solid Shield Background */}
          <path
            d="M32 8L48 15V31C48 41.5 41.2 51.2 32 54C22.8 51.2 16 41.5 16 31V15L32 8Z"
            fill="#0c1433"
            stroke={`url(#${isPass ? "emerald-grad" : "gold-grad"})`}
            strokeWidth="2"
          />

          {/* Inner Trophy Graphic */}
          {isPass ? (
            <>
              {/* Checkmark Ribbon & Star */}
              <path
                d="M26 31.5L30 35.5L38 27.5"
                stroke={`url(#gold-grad)`}
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                filter="url(#trophy-glow)"
              />
              <path
                d="M32 18L33.5 22L37.5 22.5L34.5 25.2L35.5 29.5L32 27L28.5 29.5L29.5 25.2L26.5 22.5L30.5 22L32 18Z"
                fill={`url(#gold-grad)`}
                className="star-sparkle"
              />
            </>
          ) : (
            <path
              d="M32 22V34M32 40H32.02"
              stroke={primaryColor}
              strokeWidth="3"
              strokeLinecap="round"
            />
          )}

          {/* Corner Sparkles */}
          <polygon
            points="50,14 52,19 57,21 52,23 50,28 48,23 43,21 48,19"
            fill="#f0b35a"
            opacity="0.8"
            className="star-sparkle"
          />
        </svg>
      </div>

      {/* Text & Metadata */}
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-bold text-fg tracking-wide">
            {title}
          </h4>
          <span className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
            isPass
              ? "bg-ok/80 text-ok border-ok/60"
              : isWarning
              ? "bg-warn/80 text-warn border-warn/60"
              : "bg-bad/80 text-bad border-bad/60"
          }`}>
            {status}
          </span>
        </div>
        <p className="text-xs text-fg-dim font-medium leading-relaxed">
          {subtitle}
        </p>
      </div>
    </div>
  );
};
