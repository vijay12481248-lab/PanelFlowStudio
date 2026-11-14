import React, { useState, useRef, useEffect } from "react";
import { ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";

interface ChronoFlowScreenProps {
  onBack: () => void;
  project?: Project | null;
  /** open this ChronoFlow job in the studio (the dashboard's "Your creations" cards) */
  jobId?: string | null;
  /** open a specific studio tab (e.g. "image-studio", "director", "vault") */
  tab?: string | null;
  /** open a specific story workspace (e.g. "mahabharata_adi_parva") */
  story?: string | null;
}

export const ChronoFlowScreen: React.FC<ChronoFlowScreenProps> = ({ onBack, project, jobId, tab, story }) => {
  const [iframeKey, setIframeKey] = useState(0);
  const [iframeLoading, setIframeLoading] = useState(true);
  const [token, setToken] = useState<string>("");
  const [loadTimedOut, setLoadTimedOut] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Listen for navigation messages from the embedded studio header
  useEffect(() => {
    const handleMsg = (e: MessageEvent) => {
      if (e.data?.type === "panelflow_back_to_dashboard") {
        onBack();
      }
    };
    window.addEventListener("message", handleMsg);
    return () => window.removeEventListener("message", handleMsg);
  }, [onBack]);

  // Read engine token from client, local storage, or Tauri
  useEffect(() => {
    const fetchToken = async () => {
      try {
        let t = (api as any).engineToken || "";
        if (!t && typeof window !== "undefined") {
          t = localStorage.getItem("panelflow_engine_token") || "";
          if (!t && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)) {
            const { invoke } = await import("@tauri-apps/api/core");
            t = await invoke<string>("get_engine_token_cmd");
          }
        }
        if (t) setToken(t);
      } catch (err) {
        console.warn("[ChronoFlow] Could not retrieve engine token:", err);
      }
    };
    fetchToken();
  }, []);

  // Compute studio URL passing embedded=1 and project name for the unified single bar
  const extraParams = `${tab ? `&tab=${encodeURIComponent(tab)}` : ""}${story ? `&story=${encodeURIComponent(story)}` : ""}`;
  // ChronoFlow is part of the PanelFlow engine: one server on port 8765 serves the studio UI and its API.
  const studioUrl = `http://127.0.0.1:8765/chronoflow/ui?embedded=1${token ? `&token=${encodeURIComponent(token)}` : ""}${project?.title ? `&project=${encodeURIComponent(project.title)}` : ""}${jobId ? `&job=${encodeURIComponent(jobId)}` : ""}${extraParams}`;

  // Loading timeout fallback
  useEffect(() => {
    setLoadTimedOut(false);
    const timer = setTimeout(() => {
      if (iframeLoading) {
        setLoadTimedOut(true);
      }
    }, 7000);
    return () => clearTimeout(timer);
  }, [iframeKey, iframeLoading, studioUrl]);

  const handleRefresh = () => {
    setIframeLoading(true);
    setLoadTimedOut(false);
    setIframeKey((prev) => prev + 1);
  };

  const handleOpenBrowser = () => {
    const rawUrl = studioUrl.replace("?embedded=1&", "?").replace("?embedded=1", "");
    window.open(rawUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#070b1c] text-fg overflow-hidden font-sans select-none">
      {/* Main Studio Viewport — Single Unified Bar (no duplicate header) */}
      <main className="flex-1 relative w-full h-full bg-[#070b1c]">
        {iframeLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#070b1c] z-10">
            {/* Quick exit to dashboard while connecting */}
            <button
              onClick={onBack}
              className="absolute top-3 left-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-flat/90 hover:bg-glass-hi text-fg-dim hover:text-white text-xs font-semibold border border-edge shadow-md transition-colors"
              title="Return to PanelFlow Dashboard"
            >
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Dashboard</span>
            </button>

            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-fg-dim font-medium">
              Connecting to ChronoFlow Studio ({studioUrl})...
            </p>

            {loadTimedOut && (
              <div className="mt-4 p-4 rounded-xl bg-navy/90 border border-edge max-w-md text-center space-y-3">
                <div className="flex items-center justify-center gap-2 text-warn text-xs font-semibold">
                  <AlertCircle className="w-4 h-4" aria-hidden="true" />
                  <span>Studio Server Not Responding Fast Enough</span>
                </div>
                <p className="text-[11px] text-fg-dim leading-relaxed">
                  Make sure the PanelFlow Engine is running (port 8765). ChronoFlow is part of the engine, there is no separate server to start.
                </p>
                <div className="flex justify-center gap-2 pt-1">
                  <button
                    onClick={onBack}
                    className="px-3 py-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg text-xs font-semibold border border-edge"
                  >
                    Return to Dashboard
                  </button>
                  <button
                    onClick={handleOpenBrowser}
                    className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent text-white text-xs font-semibold"
                  >
                    Open in browser
                  </button>
                  <button
                    onClick={handleRefresh}
                    className="px-3 py-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg text-xs font-semibold border border-edge"
                  >
                    Try again
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <iframe
          ref={iframeRef}
          key={`${iframeKey}-${studioUrl}`}
          src={studioUrl}
          title="ChronoFlow Studio"
          onLoad={() => setIframeLoading(false)}
          className="w-full h-full border-none outline-none"
          allow="camera; microphone; clipboard-read; clipboard-write; display-capture"
        />

        {/* Always-visible reload so engine UI updates can be picked up without leaving the screen */}
        {!iframeLoading && (
          <button
            onClick={handleRefresh}
            className="absolute bottom-3 right-3 z-20 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-navy/85 hover:bg-flat text-fg-dim hover:text-white text-xs font-semibold border border-edge shadow-md transition-colors"
            title="Reload the studio UI from the engine (picks up engine-side UI updates)"
          >
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Reload UI</span>
          </button>
        )}
      </main>
    </div>
  );
};
