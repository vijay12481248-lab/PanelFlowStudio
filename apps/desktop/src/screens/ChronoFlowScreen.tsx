import React, { useState, useRef, useEffect } from "react";
import { ArrowLeft, ExternalLink, RefreshCw, Film, Radio, Cpu, AlertCircle } from "lucide-react";
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

  // Compute studio URL
  const studioUrl =
    selectedPort === "7860"
      ? `http://127.0.0.1:7860/${jobId ? `?job=${encodeURIComponent(jobId)}` : ""}`
      : `http://127.0.0.1:8765/chronoflow/ui?${[token ? `token=${encodeURIComponent(token)}` : "", jobId ? `job=${encodeURIComponent(jobId)}` : ""].filter(Boolean).join("&")}`;

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
    window.open(studioUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#090d16] text-zinc-100 overflow-hidden font-sans select-none">
      {/* Top Header Bar */}
      <header className="flex-none h-14 bg-[#111726]/90 backdrop-blur-md border-b border-[#1e293b] px-4 flex items-center justify-between z-20">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white text-xs font-semibold border border-zinc-700 transition-colors"
            title="Return to PanelFlow Dashboard"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Dashboard</span>
          </button>

          <div className="h-5 w-[1px] bg-zinc-800 mx-1" />

          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Film className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold tracking-tight text-white">ChronoFlow Pro Studio</h1>
{project ? (
                  <span className="text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-purple-500/25 text-purple-200 border border-purple-500/40 truncate max-w-xs">
                    Project: {project.title}
                  </span>
                ) : (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    MiniMax H3 & FLUX.1
                  </span>
                )}
              </div>
              <p className="text-[11px] text-zinc-400">Sliding Window Video Chaining, Inpainting & AI Storyboard</p>
            </div>
          </div>
        </div>

        {/* Right Status & Actions */}
        <div className="flex items-center gap-2.5">
          {/* Port / Backend Switcher */}
          <div className="flex items-center bg-[#0d121f] rounded-lg p-0.5 border border-zinc-800 text-[11px]">
            <button
              onClick={() => {
                setSelectedPort("7860");
                setIframeLoading(true);
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-all ${
                selectedPort === "7860"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
              title="Port 7860: Standalone ChronoFlow Studio Server"
            >
              Port 7860 {detected7860 ? "●" : ""}
            </button>
            <button
              onClick={() => {
                setSelectedPort("8765");
                setIframeLoading(true);
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-all ${
                selectedPort === "8765"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
              title="Port 8765: Integrated PanelFlow Engine"
            >
              Port 8765 (Engine)
            </button>
          </div>

          <button
            onClick={handleRefresh}
            className="p-1.5 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700 transition-colors"
            title="Refresh Studio View"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleOpenBrowser}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition-colors"
            title="Open in Standalone Browser Window"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Open in Browser</span>
          </button>
        </div>
      </header>

      {/* Main Studio View Container */}
      <main className="flex-1 relative w-full h-[calc(100vh-3.5rem)] bg-[#090d16]">
        {iframeLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#090d16] z-10">
            <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-zinc-400 font-medium">
              Connecting to ChronoFlow Studio ({studioUrl})...
            </p>

            {loadTimedOut && (
              <div className="mt-4 p-4 rounded-xl bg-zinc-900/90 border border-zinc-800 max-w-md text-center space-y-3">
                <div className="flex items-center justify-center gap-2 text-amber-400 text-xs font-semibold">
                  <AlertCircle className="w-4 h-4" />
                  <span>Studio Server Not Responding Fast Enough</span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  Make sure <code className="text-purple-300">engine/chronoflow/run_studio.py</code> is running (Port 7860) or the PanelFlow Engine is active on port 8765.
                </p>
                <div className="flex justify-center gap-2 pt-1">
                  <button
                    onClick={handleOpenBrowser}
                    className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold"
                  >
                    Open Standalone in Browser
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
      </main>
    </div>
  );
};
