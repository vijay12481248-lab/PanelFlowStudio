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

  const primaryColor = isPass ? "#10b981" : isWarning ? "#f59e0b" : "#f43f5e";
  const goldColor = isPass ? "#fbbf24" : isWarning ? "#d97706" : "#e11d48";

  return (
    <div className={`relative flex items-center gap-4 p-4 rounded-xl border bg-zinc-950/80 backdrop-blur-md ${
      isPass
        ? "border-emerald-500/40 shadow-lg shadow-emerald-950/30 ring-1 ring-emerald-500/20"
        : isWarning
        ? "border-amber-500/40 shadow-lg shadow-amber-950/30 ring-1 ring-amber-500/20"
        : "border-rose-500/40 shadow-lg shadow-rose-950/30"
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
              <stop offset="0%" stopColor="#fef08a" />
              <stop offset="50%" stopColor={goldColor} />
              <stop offset="100%" stopColor="#b45309" />
            </linearGradient>

            <linearGradient id="emerald-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#6ee7b7" />
              <stop offset="50%" stopColor={primaryColor} />
              <stop offset="100%" stopColor="#047857" />
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
            fill="#18181b"
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
            fill="#fef08a"
            opacity="0.8"
            className="star-sparkle"
          />
        </svg>
      </div>

      {/* Text & Metadata */}
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-bold text-zinc-100 tracking-wide">
            {title}
          </h4>
          <span className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
            isPass
              ? "bg-emerald-950/80 text-emerald-400 border-emerald-700/60"
              : isWarning
              ? "bg-amber-950/80 text-amber-400 border-amber-700/60"
              : "bg-rose-950/80 text-rose-400 border-rose-700/60"
          }`}>
            {status}
          </span>
        </div>
        <p className="text-xs text-zinc-400 font-medium leading-relaxed">
          {subtitle}
        </p>
      </div>
    </div>
  );
};
