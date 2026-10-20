import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { ProviderHealth, SystemProvidersResponse, HardwareDiagnostics } from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface ProviderHealthModalProps {
  open: boolean;
  onClose: () => void;
}

const statusColor: Record<string, string> = {
  HEALTHY: "bg-emerald-500",
  READY: "bg-emerald-500",
  DEGRADED: "bg-amber-500",
  OFFLINE: "bg-rose-500",
  STOPPED: "bg-rose-500",
  NOT_RUNNING: "bg-rose-500",
  MISSING: "bg-zinc-600",
  UNSUPPORTED: "bg-rose-600",
  ERROR: "bg-rose-600",
  BROWSER_RUNTIME_MISSING: "bg-amber-600",
};

const statusBadgeVariant = (status: string): "success" | "warning" | "danger" | "neutral" => {
  if (status === "HEALTHY" || status === "READY") return "success";
  if (status === "DEGRADED" || status === "BROWSER_RUNTIME_MISSING") return "warning";
  if (
    status === "MISSING" ||
    status === "OFFLINE" ||
    status === "NOT_RUNNING" ||
    status === "STOPPED" ||
    status === "UNSUPPORTED" ||
    status === "ERROR"
  )
    return "danger";
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
  python_runtime: "Required: Python 3.12+ (64-bit). Install via 'winget install Python.Python.3.12' or from python.org.",
  ffmpeg: "Required: Install via 'winget install Gyan.FFmpeg' or download from gyan.dev and add to PATH.",
  ffprobe: "Required: Included automatically with standard FFmpeg full distribution.",
  ollama: "Optional: Start Ollama app or run 'ollama serve'. Rule-based adaptation used if offline.",
  f5_tts: "Recommended: Zero-shot neural voice cloning with natural breathiness. Procedural voice fallback used if offline.",
  ace_step: "Recommended: Real-time neural soundtrack server on port 8001. Procedural crystal synthesizer used if offline.",
  playwright: "Optional: Run 'playwright install chromium' to crawl SPA reader websites.",
};

export const ProviderHealthModal: React.FC<ProviderHealthModalProps> = ({ open, onClose }) => {
  const [activeTab, setActiveTab] = useState<"system" | "ollama">("system");
  const [data, setData] = useState<SystemProvidersResponse | null>(null);
  const [hardware, setHardware] = useState<HardwareDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Ollama & Resources State
  const [ollamaConfig, setOllamaConfig] = useState<any>(null);
  const [ollamaModels, setOllamaModels] = useState<any[]>([]);
  const [ollamaRecommendations, setOllamaRecommendations] = useState<any>({});
  const [resources, setResources] = useState<any>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [authTokenInput, setAuthTokenInput] = useState("");
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<any>(null);

  // Setup & Onboarding Assistant State
  const [locatingFfmpeg, setLocatingFfmpeg] = useState(false);
  const [ffmpegResult, setFfmpegResult] = useState<string | null>(null);
  const [provisioningVoices, setProvisioningVoices] = useState(false);
  const [voiceResult, setVoiceResult] = useState<string | null>(null);
  const [installingPlaywright, setInstallingPlaywright] = useState(false);
  const [playwrightStatus, setPlaywrightStatus] = useState<any>(null);
  const [pullingModel, setPullingModel] = useState(false);
  const [pullModelInput, setPullModelInput] = useState("qwen2.5:7b");
  const [pullStatus, setPullStatus] = useState<any>(null);

  const handleLocateFfmpeg = async () => {
    setLocatingFfmpeg(true);
    setFfmpegResult(null);
    try {
      const res = await api.locateFfmpeg();
      if (res.found) {
        setFfmpegResult(`Found: ${res.ffmpeg_path} (${res.version})`);
        await loadHealth();
      } else {
        setFfmpegResult("FFmpeg was not located in standard paths. Please install via winget or specify path.");
      }
    } catch (err: any) {
      setFfmpegResult(`Scan failed: ${err.message}`);
    } finally {
      setLocatingFfmpeg(false);
    }
  };

  const handleProvisionVoices = async () => {
    setProvisioningVoices(true);
    setVoiceResult(null);
    try {
      const res = await api.provisionVoices();
      setVoiceResult(`Ready: ${res.total_profiles} voice profiles verified in ${res.voice_directory}`);
      await loadHealth();
    } catch (err: any) {
      setVoiceResult(`Provisioning failed: ${err.message}`);
    } finally {
      setProvisioningVoices(false);
    }
  };

  const handleInstallPlaywright = async () => {
    setInstallingPlaywright(true);
    try {
      await api.installPlaywrightBrowsers();
      const poll = setInterval(async () => {
        try {
          const st = await api.getPlaywrightInstallStatus();
          setPlaywrightStatus(st);
          if (st.status === "COMPLETED" || st.status === "FAILED") {
            clearInterval(poll);
            setInstallingPlaywright(false);
            await loadHealth();
          }
        } catch {
          clearInterval(poll);
          setInstallingPlaywright(false);
        }
      }, 1500);
    } catch (err: any) {
      alert(`Failed to start Playwright installer: ${err.message}`);
      setInstallingPlaywright(false);
    }
  };

  const handlePullModel = async (modelToPull?: string) => {
    const target = (modelToPull || pullModelInput).trim();
    if (!target) return;
    setPullingModel(true);
    setPullStatus({ status: "STARTING", status_text: `Connecting to Ollama for ${target}...`, percent: 0 });
    try {
      await api.pullOllamaModel(target, ollamaConfig?.endpoint_url);
      const poll = setInterval(async () => {
        try {
          const st = await api.getOllamaPullStatus();
          setPullStatus(st);
          if (st.status === "COMPLETED" || st.status === "FAILED") {
            clearInterval(poll);
            setPullingModel(false);
            await loadOllamaAndResources();
          }
        } catch {
          clearInterval(poll);
          setPullingModel(false);
        }
      }, 1200);
    } catch (err: any) {
      alert(`Model download request failed: ${err.message}`);
      setPullingModel(false);
    }
  };

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

  const loadOllamaAndResources = async () => {
    try {
      const [cfg, modelsRes, res] = await Promise.all([
        api.getOllamaConfig().catch(() => null),
        api.getOllamaModels().catch(() => null),
        api.getSystemResources().catch(() => null),
      ]);
      if (cfg) setOllamaConfig(cfg);
      if (modelsRes) {
        setOllamaModels(modelsRes.models || []);
        setOllamaRecommendations(modelsRes.recommendations || {});
      }
      if (res) setResources(res);
    } catch (err) {
      console.error("Failed to load Ollama telemetry:", err);
    }
  };

  const handleTestConnection = async () => {
    if (!ollamaConfig) return;
    setTestingConnection(true);
    setTestResult(null);
    try {
      const res = await api.testOllamaConnection({
        endpoint_url: ollamaConfig.endpoint_url,
        is_remote: ollamaConfig.is_remote,
        auth_token: authTokenInput.trim() ? authTokenInput.trim() : undefined,
      });
      setTestResult(res);
      if (res.connected) {
        await loadOllamaAndResources();
      }
    } catch (err: any) {
      setTestResult({ connected: false, error: err.message });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSaveOllamaConfig = async () => {
    if (!ollamaConfig) return;
    setSavingConfig(true);
    try {
      const payload: any = { ...ollamaConfig };
      if (authTokenInput.trim()) {
        payload.auth_token = authTokenInput.trim();
      }
      const saved = await api.saveOllamaConfig(payload);
      setOllamaConfig(saved);
      setAuthTokenInput("");
      await loadOllamaAndResources();
      alert("Ollama configuration and GPU concurrency saved successfully.");
    } catch (err: any) {
      alert(`Failed to save config: ${err.message}`);
    } finally {
      setSavingConfig(false);
    }
  };

  const handleRunBenchmark = async () => {
    setBenchmarking(true);
    setBenchmarkResult(null);
    try {
      const res = await api.runConcurrencyBenchmark(ollamaConfig?.narration_model);
      setBenchmarkResult(res);
    } catch (err: any) {
      alert(`Benchmark failed: ${err.message}`);
    } finally {
      setBenchmarking(false);
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
      loadOllamaAndResources();
    }
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/50 max-w-3xl w-full mx-4 max-h-[88vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 flex items-center justify-center">
              <Icons.ShieldCheck className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-zinc-100">System Diagnostics & Ollama Orchestration</h2>
              <p className="text-[11px] text-zinc-400">Hardware telemetry, model capability discovery & multi-project admission control</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose}>
              <span className="text-zinc-400 text-sm font-bold">✕</span>
            </Button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-zinc-800 px-6 bg-zinc-950/60">
          <button
            onClick={() => setActiveTab("system")}
            className={`py-2.5 px-4 text-xs font-bold border-b-2 transition-colors ${
              activeTab === "system"
                ? "border-indigo-500 text-indigo-300"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            System Dependencies & Hardware
          </button>
          <button
            onClick={() => setActiveTab("ollama")}
            className={`py-2.5 px-4 text-xs font-bold border-b-2 transition-colors ${
              activeTab === "ollama"
                ? "border-indigo-500 text-indigo-300"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Ollama Models & GPU Admission
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === "system" ? (
            <>
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

              {/* 1-Click Setup & Model Onboarding Assistant Card */}
              <Card className="p-4 bg-gradient-to-r from-indigo-950/40 via-zinc-950 to-zinc-950 border-indigo-900/40 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2">
                  <div className="flex items-center gap-2">
                    <Icons.ShieldCheck className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-indigo-200">
                      Setup & Dependency Assistant
                    </span>
                  </div>
                  <span className="text-[10px] text-zinc-400 font-mono">1-Click Local Provisioning</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {/* Action 1: Locate FFmpeg */}
                  <div className="p-3 rounded-lg bg-zinc-900/70 border border-zinc-800 flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-100">FFmpeg Discovery</span>
                        <Badge variant={data?.providers.find((p) => p.id === "ffmpeg")?.status === "HEALTHY" ? "success" : "warning"} className="text-[9px]">
                          {data?.providers.find((p) => p.id === "ffmpeg")?.status || "MISSING"}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-zinc-400 mt-1">
                        Deep scan standard directories, Winget, Scoop, and auto-inject into PATH.
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleLocateFfmpeg}
                      disabled={locatingFfmpeg}
                      className="w-full text-xs"
                    >
                      <Icons.Refresh className={`w-3.5 h-3.5 mr-1.5 ${locatingFfmpeg ? "animate-spin" : ""}`} />
                      {locatingFfmpeg ? "Scanning..." : "Auto-Locate FFmpeg"}
                    </Button>
                  </div>

                  {/* Action 2: Provision Voices */}
                  <div className="p-3 rounded-lg bg-zinc-900/70 border border-zinc-800 flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-100">Default Voice Pack</span>
                        <Badge variant="accent" className="text-[9px]">
                          AppData Sync
                        </Badge>
                      </div>
                      <p className="text-[11px] text-zinc-400 mt-1">
                        Deploys bundled neural voice profiles (Aria, Marcus, Seraphina) into user AppData.
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleProvisionVoices}
                      disabled={provisioningVoices}
                      className="w-full text-xs"
                    >
                      <Icons.Plus className="w-3.5 h-3.5 mr-1.5 text-indigo-400" />
                      {provisioningVoices ? "Provisioning..." : "Provision Voice Profiles"}
                    </Button>
                  </div>

                  {/* Action 3: Install Playwright */}
                  <div className="p-3 rounded-lg bg-zinc-900/70 border border-zinc-800 flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-100">Playwright Chromium</span>
                        <Badge variant={data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "success" : "neutral"} className="text-[9px]">
                          {data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "READY" : "INSTALL"}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-zinc-400 mt-1">
                        Downloads headless Chromium browser for crawling dynamic webtoon pages.
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleInstallPlaywright}
                      disabled={installingPlaywright || data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY"}
                      className="w-full text-xs"
                    >
                      <Icons.Globe className="w-3.5 h-3.5 mr-1.5 text-cyan-400" />
                      {installingPlaywright ? "Downloading..." : data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "Installed" : "Install Browsers"}
                    </Button>
                  </div>
                </div>

                {/* Notifications & Result banners */}
                {ffmpegResult && (
                  <p className="text-[11px] font-mono text-indigo-300 bg-indigo-950/40 border border-indigo-900/60 rounded px-2.5 py-1.5">
                    {ffmpegResult}
                  </p>
                )}
                {voiceResult && (
                  <p className="text-[11px] font-mono text-emerald-300 bg-emerald-950/40 border border-emerald-900/60 rounded px-2.5 py-1.5">
                    {voiceResult}
                  </p>
                )}
                {playwrightStatus && (
                  <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800 text-[11px] font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-300 font-bold">Playwright Installer: {playwrightStatus.status}</span>
                      {playwrightStatus.exit_code !== null && (
                        <span className="text-zinc-500">Exit Code: {playwrightStatus.exit_code}</span>
                      )}
                    </div>
                    {playwrightStatus.log_lines && playwrightStatus.log_lines.length > 0 && (
                      <p className="text-zinc-400 truncate max-w-full">
                        {playwrightStatus.log_lines[playwrightStatus.log_lines.length - 1]}
                      </p>
                    )}
                  </div>
                )}
              </Card>

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
                    const isIssue = p.status !== "HEALTHY" && p.status !== "READY";
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
            </>
          ) : (
            /* Ollama & Hardware Telemetry Tab */
            <div className="space-y-4">
              {/* Endpoint Configuration Card */}
              <Card className="p-4 bg-zinc-950 border-zinc-800 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                      Ollama Connection Settings
                    </span>
                    <Badge variant={ollamaConfig?.is_remote ? "accent" : "neutral"} className="text-[9px] uppercase">
                      {ollamaConfig?.is_remote ? "Remote Server" : "Local Host"}
                    </Badge>
                  </div>
                  <Button variant="ghost" size="sm" onClick={handleTestConnection} disabled={testingConnection}>
                    <Icons.Rotate className={`w-3.5 h-3.5 mr-1 ${testingConnection ? "animate-spin" : ""}`} />
                    Test Connection
                  </Button>
                </div>

                {testResult && (
                  <div
                    className={`p-2.5 rounded-lg text-xs font-mono flex items-center justify-between ${
                      testResult.connected
                        ? "bg-emerald-950/40 border border-emerald-800 text-emerald-300"
                        : "bg-rose-950/40 border border-rose-800 text-rose-300"
                    }`}
                  >
                    <span>
                      {testResult.connected
                        ? `Connected (${testResult.latency_ms}ms) — ${testResult.models_count} models discovered`
                        : `Connection Failed: ${testResult.error || "Cannot reach server"}`}
                    </span>
                    <Badge variant={testResult.connected ? "success" : "danger"} className="text-[9px]">
                      {testResult.status}
                    </Badge>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1">
                    <label className="text-zinc-400 font-semibold">Endpoint URL</label>
                    <input
                      type="text"
                      value={ollamaConfig?.endpoint_url || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, endpoint_url: e.target.value })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                      placeholder="http://127.0.0.1:11434"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-zinc-400 font-semibold flex items-center justify-between">
                      <span>Auth Bearer Token / API Key</span>
                      {ollamaConfig?.has_auth_token && (
                        <span className="text-[10px] text-emerald-400 font-mono">Active in Keychain</span>
                      )}
                    </label>
                    <input
                      type="password"
                      value={authTokenInput}
                      onChange={(e) => setAuthTokenInput(e.target.value)}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                      placeholder={ollamaConfig?.has_auth_token ? "•••••••• (Leave blank to keep current)" : "Optional Bearer Token"}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ollamaConfig?.is_remote || false}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, is_remote: e.target.checked })
                      }
                      className="rounded accent-indigo-500"
                    />
                    <span>Private Remote Server / Cloud Endpoint (Enforces strict SSRF filtering)</span>
                  </label>
                  <Button variant="secondary" size="sm" onClick={handleSaveOllamaConfig} disabled={savingConfig}>
                    Save Settings
                  </Button>
                </div>
              </Card>

              {/* Multi-Role Model Selectors */}
              <Card className="p-4 bg-zinc-950 border-zinc-800 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                    Multi-Role Model Assignment
                  </span>
                  <Button variant="ghost" size="sm" onClick={loadOllamaAndResources}>
                    <Icons.Rotate className="w-3.5 h-3.5 mr-1" />
                    Refresh Models
                  </Button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  {/* Vision Role */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-zinc-300 font-semibold">Vision Model</label>
                      <span className="text-[10px] text-emerald-400 font-mono">Multimodal VLM</span>
                    </div>
                    <select
                      value={ollamaConfig?.vision_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, vision_model: e.target.value })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`vis-${m.name}`} value={m.name}>
                          {m.name} {m.supports_vision ? "👁️ (Vision)" : ""} {m.name === ollamaRecommendations?.vision_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-zinc-500">Visual panel description & character detection</p>
                  </div>

                  {/* Story Reasoning Role */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-zinc-300 font-semibold">Story Reasoning</label>
                      <span className="text-[10px] text-indigo-400 font-mono">Narrative Logic</span>
                    </div>
                    <select
                      value={ollamaConfig?.reasoning_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, reasoning_model: e.target.value })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`reas-${m.name}`} value={m.name}>
                          {m.name} {m.name === ollamaRecommendations?.reasoning_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-zinc-500">Chapter-wide plot, continuity & scene synthesis</p>
                  </div>

                  {/* Narration Role */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-zinc-300 font-semibold">Narration Model</label>
                      <span className="text-[10px] text-amber-400 font-mono">Voice Script</span>
                    </div>
                    <select
                      value={ollamaConfig?.narration_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, narration_model: e.target.value })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`narr-${m.name}`} value={m.name}>
                          {m.name} {m.name === ollamaRecommendations?.narration_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-zinc-500">Emotional storyteller recap & cadence adaptation</p>
                  </div>
                </div>
              </Card>

              {/* 1-Click Model Downloader Card */}
              <Card className="p-4 bg-zinc-950 border-zinc-800 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <div className="flex items-center gap-2">
                    <Icons.Plus className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                      Download & Pull Ollama Models
                    </span>
                  </div>
                  <span className="text-[10px] text-zinc-400 font-mono">Direct Streaming via /api/pull</span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-zinc-400">Quick Recommendations:</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handlePullModel("qwen2.5:7b")}
                      disabled={pullingModel}
                      className="text-xs"
                    >
                      qwen2.5:7b (Recommended)
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handlePullModel("llama3.2:3b")}
                      disabled={pullingModel}
                      className="text-xs"
                    >
                      llama3.2:3b (Low VRAM)
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handlePullModel("qwen3.5:9b")}
                      disabled={pullingModel}
                      className="text-xs"
                    >
                      qwen3.5:9b (Thinking)
                    </Button>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={pullModelInput}
                      onChange={(e) => setPullModelInput(e.target.value)}
                      placeholder="e.g. qwen2.5:7b or mistral"
                      disabled={pullingModel}
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handlePullModel()}
                      disabled={pullingModel || !pullModelInput.trim()}
                    >
                      <Icons.Refresh className={`w-3.5 h-3.5 mr-1 ${pullingModel ? "animate-spin" : ""}`} />
                      {pullingModel ? "Pulling..." : "Pull Model"}
                    </Button>
                  </div>

                  {pullStatus && (
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono font-bold text-zinc-200">
                          {pullStatus.status_text || pullStatus.status}
                        </span>
                        <span className="font-mono text-indigo-400 font-bold">
                          {pullStatus.percent ? `${pullStatus.percent}%` : ""}
                        </span>
                      </div>
                      <ProgressBar progress={pullStatus.percent || 0} />
                      {pullStatus.total_bytes > 0 && (
                        <div className="flex justify-between text-[10px] text-zinc-500 font-mono">
                          <span>{Math.round(pullStatus.completed_bytes / (1024 * 1024))} MB</span>
                          <span>{Math.round(pullStatus.total_bytes / (1024 * 1024))} MB</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>

              {/* Discovered Models & Capability Badges */}
              <Card className="p-4 bg-zinc-950 border-zinc-800 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                    Installed Ollama Inventory ({ollamaModels.length} models)
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">Capabilities verified via POST /api/show</span>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {ollamaModels.length === 0 ? (
                    <p className="text-xs text-zinc-500 text-center py-4">No models detected. Ensure Ollama is running.</p>
                  ) : (
                    ollamaModels.map((m) => (
                      <div
                        key={m.name}
                        className="flex items-center justify-between p-2 rounded bg-zinc-900/60 border border-zinc-800/80 text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-zinc-100">{m.name}</span>
                          <span className="text-[10px] text-zinc-500 font-mono">({m.parameter_size}, {m.quantization_level})</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {m.supports_vision && (
                            <Badge variant="success" className="text-[9px]">Vision</Badge>
                          )}
                          {m.supports_tools && (
                            <Badge variant="accent" className="text-[9px]">Tools</Badge>
                          )}
                          {m.supports_thinking && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-purple-950/60 border border-purple-800 text-purple-300">
                              Thinking
                            </span>
                          )}
                          <span className="text-[10px] text-zinc-400 font-mono pl-1">{m.family}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Card>

              {/* Hardware Telemetry & Concurrency Admission Controller */}
              <Card className="p-4 bg-zinc-950 border-zinc-800 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                      GPU Admission & Memory Telemetry
                    </span>
                    <Badge variant={resources?.scheduler?.active_count > 0 ? "accent" : "success"} className="text-[9px]">
                      {resources?.scheduler?.active_count || 0} / {resources?.scheduler?.effective_limit || 1} Active Slots
                    </Badge>
                  </div>
                  <Button variant="ghost" size="sm" onClick={handleRunBenchmark} disabled={benchmarking}>
                    <Icons.Rotate className={`w-3.5 h-3.5 mr-1 ${benchmarking ? "animate-spin" : ""}`} />
                    Run Concurrency Benchmark
                  </Button>
                </div>

                {benchmarkResult && (
                  <div className="p-2.5 rounded-lg bg-zinc-900 border border-indigo-900/40 text-xs font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-indigo-300">Benchmark: {benchmarkResult.model_tested}</span>
                      <span className="text-emerald-400 font-bold">{benchmarkResult.speedup_ratio}x Throughput</span>
                    </div>
                    <p className="text-[11px] text-zinc-300">
                      Sequential: {benchmarkResult.sequential_duration_sec}s | Concurrent: {benchmarkResult.concurrent_duration_sec}s
                    </p>
                    <p className="text-[11px] text-zinc-400 italic">{benchmarkResult.recommendation}</p>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 rounded bg-zinc-900/50 border border-zinc-800">
                    <span className="text-[10px] text-zinc-500 uppercase font-semibold">Host RAM</span>
                    <p className="font-mono text-zinc-100 font-bold mt-0.5">
                      {resources?.ram?.available_gb ?? hardware?.available_ram_gb ?? 0} GB Free
                    </p>
                    <p className="text-[10px] text-zinc-500 font-mono">
                      {resources?.ram?.total_gb ?? hardware?.total_ram_gb ?? 0} GB Total ({resources?.ram?.used_percent ?? 0}%)
                    </p>
                  </div>

                  <div className="p-2.5 rounded bg-zinc-900/50 border border-zinc-800">
                    <span className="text-[10px] text-zinc-500 uppercase font-semibold">GPU Dedicated VRAM</span>
                    <p className="font-mono text-zinc-100 font-bold mt-0.5">
                      {resources?.gpu?.free_mb ? Math.round(resources.gpu.free_mb) : hardware?.vram_mb ?? 0} MB Free
                    </p>
                    <p className="text-[10px] text-zinc-500 font-mono truncate" title={resources?.gpu?.device_name}>
                      {resources?.gpu?.device_name || hardware?.gpu_name}
                    </p>
                  </div>

                  <div className="p-2.5 rounded bg-zinc-900/50 border border-zinc-800">
                    <span className="text-[10px] text-zinc-500 uppercase font-semibold">Active Ollama VRAM</span>
                    <p className="font-mono text-zinc-100 font-bold mt-0.5">
                      {resources?.ollama?.total_ollama_vram_mb ?? 0} MB
                    </p>
                    <p className="text-[10px] text-zinc-500 font-mono">
                      {resources?.ollama?.loaded_models_count ?? 0} active models in memory
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
                  <div className="space-y-1">
                    <label className="text-zinc-400 font-semibold">Admission Mode</label>
                    <select
                      value={ollamaConfig?.concurrency_mode || "MANUAL"}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, concurrency_mode: e.target.value })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    >
                      <option value="MANUAL">MANUAL (Fixed slot limit)</option>
                      <option value="AUTO">AUTO (Dynamic headroom scaling)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-zinc-400 font-semibold">Max Concurrent GPU Tasks</label>
                    <select
                      value={ollamaConfig?.max_gpu_concurrency || 1}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, max_gpu_concurrency: parseInt(e.target.value, 10) })
                      }
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 font-mono text-zinc-200 text-xs focus:outline-none focus:border-indigo-500"
                    >
                      <option value={1}>1 Task (Recommended for Single GPU / Safe Headroom)</option>
                      <option value={2}>2 Tasks (High VRAM &gt;= 16GB)</option>
                      <option value={4}>4 Tasks (Multi-GPU / High Throughput)</option>
                    </select>
                  </div>
                </div>
              </Card>
            </div>
          )}
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

