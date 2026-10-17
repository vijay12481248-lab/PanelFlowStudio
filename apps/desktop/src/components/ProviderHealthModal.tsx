import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { ProviderHealth, SystemProvidersResponse, HardwareDiagnostics } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons } from "@panelflow/ui";

interface ProviderHealthModalProps {
  open: boolean;
  onClose: () => void;
}

const statusColor: Record<string, string> = {
  HEALTHY: "bg-emerald-500",
  DEGRADED: "bg-amber-500",
  OFFLINE: "bg-rose-500",
  NOT_RUNNING: "bg-rose-500",
  MISSING: "bg-zinc-600",
  BROWSER_RUNTIME_MISSING: "bg-amber-600",
};

const statusBadgeVariant = (status: string): "success" | "warning" | "danger" | "neutral" => {
  if (status === "HEALTHY") return "success";
  if (status === "DEGRADED" || status === "BROWSER_RUNTIME_MISSING") return "warning";
  if (status === "MISSING" || status === "OFFLINE" || status === "NOT_RUNNING") return "danger";
  return "neutral";
};

const tierVariant = (tier: string): "success" | "accent" | "warning" | "danger" => {
  if (tier === "GOOD") return "success";
  if (tier === "SUPPORTED") return "accent";
  if (tier === "LIMITED") return "warning";
  return "danger";
};

const categoryLabels: Record<string, string> = {
  video_engine: "Video Engine",
  audio_engine: "Audio Engine",
  story_intelligence: "Story Intelligence",
  acquisition_engine: "Acquisition Engine",
};

const providerGuidance: Record<string, string> = {
  ffmpeg: "Required: Install via 'winget install Gyan.FFmpeg' or download from gyan.dev and add to PATH.",
  ffprobe: "Required: Included automatically with standard FFmpeg full distribution.",
  ollama: "Optional: Start Ollama app or run 'ollama serve'. Rule-based adaptation used if offline.",
  f5_tts: "Recommended: Place custom voice WAVs in C:\\Tools\\generated_audio. Procedural voice fallback used if missing.",
  ace_step: "Recommended: Adaptive crystal score master track. Procedural audio used if missing.",
  playwright: "Optional: Run 'playwright install chromium' to crawl SPA reader websites.",
};

export const ProviderHealthModal: React.FC<ProviderHealthModalProps> = ({ open, onClose }) => {
  const [data, setData] = useState<SystemProvidersResponse | null>(null);
  const [hardware, setHardware] = useState<HardwareDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const loadHealth = async () => {
    setLoading(true);
    try {
      const [providersResult, hwResult] = await Promise.all([
        api.getProviderHealth(),
        api.getHardwareDiagnostics().catch(() => null),
      ]);
      setData(providersResult);
      if (hwResult) setHardware(hwResult);
    } catch (err) {
      console.error("Failed to load provider health:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleExportDiagnostics = async () => {
    setExporting(true);
    try {
      const diag = await api.exportDiagnostics();
      const blob = new Blob([JSON.stringify(diag, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `panelflow_diagnostics_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Failed to export diagnostics: ${err.message}`);
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadHealth();
    }
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/50 max-w-2xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 flex items-center justify-center">
              <Icons.ShieldCheck className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-zinc-100">System & Provider Diagnostics</h2>
              <p className="text-[11px] text-zinc-400">Dependency verification & hardware suitability for beta testing</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {data && (
              <Badge variant={data.system_ready ? "success" : "danger"} className="text-[10px] uppercase font-bold">
                {data.system_ready ? "SYSTEM READY" : "SYSTEM DEGRADED"}
              </Badge>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>
              <span className="text-zinc-400 text-sm font-bold">✕</span>
            </Button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Hardware Diagnostics Card */}
          {hardware && (
            <Card className="p-4 bg-zinc-950 border-zinc-800">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3 mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                    Hardware Environment
                  </span>
                  <Badge variant={tierVariant(hardware.neural_performance_tier)} className="text-[10px] uppercase font-mono font-bold">
                    Tier: {hardware.neural_performance_tier}
                  </Badge>
                </div>
                <span className="text-[11px] text-zinc-400 font-mono">
                  {hardware.os_name} {hardware.os_release} ({hardware.architecture})
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="space-y-0.5">
                  <span className="text-[10px] text-zinc-500 uppercase font-semibold">Memory</span>
                  <p className="font-mono text-zinc-200">{hardware.total_ram_gb} GB ({hardware.available_ram_gb} GB free)</p>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] text-zinc-500 uppercase font-semibold">Disk Storage</span>
                  <p className="font-mono text-zinc-200">{hardware.free_disk_gb} GB free</p>
                </div>
                <div className="space-y-0.5 sm:col-span-2">
                  <span className="text-[10px] text-zinc-500 uppercase font-semibold">Graphics & VRAM</span>
                  <p className="font-mono text-zinc-200 truncate" title={hardware.gpu_name}>
                    {hardware.gpu_name} {hardware.vram_mb > 0 ? `(${Math.round(hardware.vram_mb / 1024)} GB)` : ""}
                  </p>
                </div>
              </div>

              <p className="text-[11px] text-zinc-400 mt-3 pt-2.5 border-t border-zinc-800/60 leading-relaxed">
                {hardware.recommendations}
              </p>
            </Card>
          )}

          {/* Providers List */}
          <div className="space-y-2.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 px-0.5">
              Local Tools & Model Engines
            </h3>
            {loading ? (
              <div className="flex items-center justify-center py-10 text-zinc-400">
                <Icons.Rotate className="w-5 h-5 animate-spin mr-2" />
                Probing engine dependencies...
              </div>
            ) : data ? (
              data.providers.map((p) => {
                const isIssue = p.status !== "HEALTHY";
                return (
                  <Card key={p.id} className="p-3.5 bg-zinc-950 border-zinc-800 hover:border-zinc-700 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3 min-w-0">
                        <div
                          className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${
                            statusColor[p.status] || "bg-zinc-600"
                          }`}
                        />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-bold text-zinc-100">{p.name}</span>
                            <Badge variant={statusBadgeVariant(p.status)} className="text-[9px] uppercase font-bold">
                              {p.status}
                            </Badge>
                            {p.required ? (
                              <span className="text-[9px] text-amber-500/80 font-mono uppercase font-semibold">Required</span>
                            ) : (
                              <span className="text-[9px] text-zinc-500 font-mono uppercase">Optional</span>
                            )}
                          </div>
                          <p className="text-[11px] text-zinc-400 mt-0.5">{p.details}</p>
                          {isIssue && providerGuidance[p.id] && (
                            <p className="text-[11px] text-amber-400/90 mt-1.5 bg-amber-950/20 border border-amber-900/40 rounded px-2 py-1">
                              💡 {providerGuidance[p.id]}
                            </p>
                          )}
                          <div className="flex items-center gap-3 mt-1.5 text-[10px] text-zinc-500 font-mono">
                            <span>{categoryLabels[p.category] || p.category}</span>
                            <span>•</span>
                            <span className="truncate max-w-[280px]">{p.version}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })
            ) : (
              <div className="text-center text-zinc-500 py-10">
                Failed to load provider status.
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-zinc-800 flex items-center justify-between gap-3 bg-zinc-950/50">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={loadHealth} disabled={loading}>
              <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              Re-scan System
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExportDiagnostics}
              disabled={exporting}
              className="text-xs"
              title="Download sanitized diagnostic bundle for bug reports (contains no user files or tokens)"
            >
              <Icons.Download className="w-3.5 h-3.5 mr-1.5" />
              {exporting ? "Exporting..." : "Export Diagnostics"}
            </Button>
          </div>
          <Button variant="primary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
};

