import React, { useState, useRef, useEffect } from "react";
import { ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";

interface ChronoFlowScreenProps {
  onBack: () => void;
  project?: Project | null;
  /** open this ChronoFlow job in the studio (the dashboard's "Your creations" cards) */
  jobId?: string | null;
}

export const ChronoFlowScreen: React.FC<ChronoFlowScreenProps> = ({ onBack, project, jobId }) => {
  const [iframeKey, setIframeKey] = useState(0);
  const [iframeLoading, setIframeLoading] = useState(true);
  const [selectedPort, setSelectedPort] = useState<"7860" | "8765">("7860");
  const [token, setToken] = useState<string>("");
  const [detected7860, setDetected7860] = useState<boolean | null>(null);
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

  // Probe standalone server on 7860 vs integrated on 8765
  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 1200);
        const res = await fetch("http://127.0.0.1:7860/api/status", {
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (!cancelled) {
          if (res.ok) {
            setDetected7860(true);
            setSelectedPort("7860");
          } else {
            setDetected7860(false);
            setSelectedPort("8765");
          }
        }
      } catch {
        if (!cancelled) {
          setDetected7860(false);
          setSelectedPort("8765");
        }
      }
    };
    probe();
    return () => {
      cancelled = true;
    };
  }, []);

  // Compute studio URL passing embedded=1 and project name for the unified single bar
  const studioUrl =
    selectedPort === "7860"
      ? `http://127.0.0.1:7860/?embedded=1${project?.title ? `&project=${encodeURIComponent(project.title)}` : ""}${jobId ? `&job=${encodeURIComponent(jobId)}` : ""}`
      : `http://127.0.0.1:8765/chronoflow/ui?embedded=1${token ? `&token=${encodeURIComponent(token)}` : ""}${project?.title ? `&project=${encodeURIComponent(project.title)}` : ""}${jobId ? `&job=${encodeURIComponent(jobId)}` : ""}`;

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
    <div className="flex flex-col h-screen w-screen bg-[#090d16] text-zinc-100 overflow-hidden font-sans select-none">
      {/* Main Studio Viewport — Single Unified Bar (no duplicate header) */}
      <main className="flex-1 relative w-full h-full bg-[#090d16]">
        {iframeLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#090d16] z-10">
            {/* Quick exit to dashboard while connecting */}
            <button
              onClick={onBack}
              className="absolute top-3 left-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/90 hover:bg-zinc-700 text-zinc-300 hover:text-white text-xs font-semibold border border-zinc-700 shadow-md transition-colors"
              title="Return to PanelFlow Dashboard"
            >
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Dashboard</span>
            </button>

            <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-zinc-400 font-medium">
              Connecting to ChronoFlow Studio ({studioUrl})...
            </p>

            {loadTimedOut && (
              <div className="mt-4 p-4 rounded-xl bg-zinc-900/90 border border-zinc-800 max-w-md text-center space-y-3">
                <div className="flex items-center justify-center gap-2 text-amber-400 text-xs font-semibold">
                  <AlertCircle className="w-4 h-4" aria-hidden="true" />
                  <span>Studio Server Not Responding Fast Enough</span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  Make sure <code className="text-purple-300">engine/chronoflow/run_studio.py</code> is running (Port 7860) or the PanelFlow Engine is active on port 8765.
                </p>
                <div className="flex justify-center gap-2 pt-1">
                  <button
                    onClick={onBack}
                    className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold border border-zinc-700"
                  >
                    Return to Dashboard
                  </button>
                  <button
                    onClick={handleOpenBrowser}
                    className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold"
                  >
                    Open Standalone
                  </button>
                  <button
                    onClick={() => {
                      setSelectedPort(selectedPort === "7860" ? "8765" : "7860");
                      setIframeLoading(true);
                    }}
                    className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold border border-zinc-700"
                  >
                    Try Port {selectedPort === "7860" ? "8765" : "7860"}
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
            className="absolute top-3 right-3 z-20 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-900/85 hover:bg-zinc-800 text-zinc-300 hover:text-white text-xs font-semibold border border-zinc-700 shadow-md transition-colors"
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
