import React from "react";

export interface SvgPipelineConnectorProps {
  fromStatus: "COMPLETE" | "ACTIVE" | "STALE" | "UPCOMING" | "NOT_STARTED";
  toStatus: "COMPLETE" | "ACTIVE" | "STALE" | "UPCOMING" | "NOT_STARTED";
  className?: string;
}

export const SvgPipelineConnector: React.FC<SvgPipelineConnectorProps> = ({
  fromStatus,
  toStatus,
  className = "",
}) => {
  const isMoving =
    (fromStatus === "COMPLETE" && toStatus === "ACTIVE") ||
    fromStatus === "ACTIVE" ||
    toStatus === "ACTIVE";

  const isComplete = fromStatus === "COMPLETE" && toStatus === "COMPLETE";
  const isStale = toStatus === "STALE" || fromStatus === "STALE";

  const strokeColor = isStale
    ? "#f59e0b"
    : isComplete
    ? "#10b981"
    : isMoving
    ? "#818cf8"
    : "#3f3f46";

  const glowId = `connector-glow-${fromStatus}-${toStatus}`;

  return (
    <div className={`relative flex items-center justify-center flex-shrink-0 w-6 h-5 ${className}`}>
      <svg
        viewBox="0 0 24 16"
        className="w-full h-full overflow-visible"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <filter id={glowId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <style>{`
          @keyframes pipeFlow {
            from { stroke-dashoffset: 16; }
            to { stroke-dashoffset: 0; }
          }
          .pipe-flowing {
            animation: pipeFlow 1.2s linear infinite;
          }
          @keyframes pipePulse {
            0%, 100% { opacity: 0.4; transform: scale(0.9); }
            50% { opacity: 1; transform: scale(1.15); }
          }
          .pipe-pulse-dot {
            animation: pipePulse 1.8s ease-in-out infinite;
            transform-origin: center;
          }
        `}</style>

        {/* Base Track */}
        <line
          x1="0"
          y1="8"
          x2="24"
          y2="8"
          stroke={strokeColor}
          strokeWidth="1.5"
          strokeOpacity={isComplete ? "0.6" : isMoving ? "0.4" : "0.2"}
          strokeLinecap="round"
        />

        {/* Animated Flow Particles */}
        {isMoving && (
          <line
            x1="0"
            y1="8"
            x2="24"
            y2="8"
            stroke={strokeColor}
            strokeWidth="2"
            strokeDasharray="4 4"
            className="pipe-flowing"
            filter={`url(#${glowId})`}
            strokeLinecap="round"
          />
        )}

        {/* Pulse Beacon in the center of active transition */}
        {isMoving && (
          <circle
            cx="12"
            cy="8"
            r="2"
            fill={strokeColor}
            className="pipe-pulse-dot"
            filter={`url(#${glowId})`}
          />
        )}

        {/* Subtle arrow tip */}
        <path
          d="M19 5.5L22.5 8L19 10.5"
          stroke={strokeColor}
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity={isComplete || isMoving ? "0.9" : "0.3"}
        />
      </svg>
    </div>
  );
};
