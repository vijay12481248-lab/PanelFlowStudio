import React, { useEffect, useState, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { YouTubeStatus } from "@panelflow/api-client";
import type {
  ProviderHealth,
  SystemProvidersResponse,
  HardwareDiagnostics,
  CloudLLMConfig,
  CloudLLMTestResponse,
  CloudLLMChatResponse,
  GlobalLLMSettings,
  FlowOverrideConfig,
  ProviderCatalogItem,
} from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

const YoutubeIcon: React.FC<React.SVGProps<SVGSVGElement>> = (props) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);

interface ProviderHealthModalProps {
  open: boolean;
  onClose: () => void;
  initialTab?: "global" | "cloud_llm" | "ollama" | "system" | "youtube";
}

const statusColor: Record<string, string> = {
  HEALTHY: "bg-ok",
  READY: "bg-ok",
  DEGRADED: "bg-warn",
  OFFLINE: "bg-bad",
  STOPPED: "bg-bad",
  NOT_RUNNING: "bg-bad",
  MISSING: "bg-fg-faint",
  UNSUPPORTED: "bg-bad",
  ERROR: "bg-bad",
  BROWSER_RUNTIME_MISSING: "bg-warn",
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
  qwen3_tts: "Recommended: Qwen3-TTS 1.7B zero-shot neural voice cloning on CUDA.",
  f5_tts: "Recommended: Zero-shot neural voice cloning with natural breathiness. Procedural voice fallback used if offline.",
  ace_step: "Recommended: Real-time neural soundtrack server on port 8001. Procedural crystal synthesizer used if offline.",
  playwright: "Optional: Run 'playwright install chromium' to crawl SPA reader websites.",
};

export const ProviderHealthModal: React.FC<ProviderHealthModalProps> = ({ open, onClose, initialTab = "global" }) => {
  const [activeTab, setActiveTab] = useState<"global" | "cloud_llm" | "ollama" | "system" | "youtube">(initialTab);

  // YouTube OAuth, Multi-Channel & Publishing State
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [ytClientId, setYtClientId] = useState<string>("");
  const [ytClientSecret, setYtClientSecret] = useState<string>("");
  const [ytBusy, setYtBusy] = useState<boolean>(false);
  const [ytError, setYtError] = useState<string | null>(null);
  const [ytSuccessMsg, setYtSuccessMsg] = useState<string | null>(null);
  const [newChannelName, setNewChannelName] = useState<string>("");
  const [showAddChannel, setShowAddChannel] = useState<boolean>(false);
  const [showInfoModal, setShowInfoModal] = useState<boolean>(false);
  const [agentUploadEnabled, setAgentUploadEnabled] = useState<boolean>(true);
  const [agentDefaultPrivacy, setAgentDefaultPrivacy] = useState<"private" | "unlisted" | "public">("private");
  const [agentPublishTime, setAgentPublishTime] = useState<string>("18:00");
  const [agentLeadTimeMin, setAgentLeadTimeMin] = useState<number>(20);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadYoutubeStatus = async (channelId?: string) => {
    try {
      const status = await api.youtubeStatus(channelId);
      setYtStatus(status);
      if (status.agent_settings) {
        setAgentUploadEnabled(status.agent_settings.enabled);
        setAgentDefaultPrivacy(status.agent_settings.default_privacy || "private");
        if (status.agent_settings.publish_time) {
          setAgentPublishTime(status.agent_settings.publish_time);
        }
        if (typeof status.agent_settings.lead_time_min === "number") {
          setAgentLeadTimeMin(status.agent_settings.lead_time_min);
        }
      }
      if (status.masked_client_id && !ytClientId) {
        setYtClientId(status.masked_client_id);
      }
      if (status.error) setYtError(status.error);
    } catch (err: any) {
      console.warn("Could not load YouTube status:", err);
    }
  };

  const handleConnectYoutube = async (channelId?: string) => {
    setYtBusy(true);
    setYtError(null);
    setYtSuccessMsg(null);
    try {
      const targetChannel = channelId || ytStatus?.active_channel_id;
      if (ytClientId.trim() && ytClientSecret.trim()) {
        await api.saveYoutubeClient(ytClientId.trim(), ytClientSecret.trim(), targetChannel);
        setYtClientSecret("");
      }
      const { auth_url } = await api.youtubeConnect(targetChannel);
      window.open(auth_url, "_blank", "noopener");
      await loadYoutubeStatus(targetChannel);
      setYtSuccessMsg("Opened Google authorization in your browser. Complete sign-in, then return to PanelFlow Studio.");
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleSaveCredentialsOnly = async () => {
    if (!ytClientId.trim() || !ytClientSecret.trim()) {
      setYtError("Please enter both OAuth Client ID and OAuth Client Secret.");
      return;
    }
    setYtBusy(true);
    setYtError(null);
    setYtSuccessMsg(null);
    try {
      const targetChannel = ytStatus?.active_channel_id;
      await api.saveYoutubeClient(ytClientId.trim(), ytClientSecret.trim(), targetChannel);
      setYtClientSecret("");
      await loadYoutubeStatus(targetChannel);
      setYtSuccessMsg("OAuth credentials saved and encoded securely on local disk.");
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleDisconnectYoutube = async (channelId?: string) => {
    setYtBusy(true);
    setYtError(null);
    setYtSuccessMsg(null);
    try {
      const targetChannel = channelId || ytStatus?.active_channel_id;
      const updated = await api.youtubeDisconnect(targetChannel);
      setYtStatus(updated);
      setYtSuccessMsg("Disconnected channel and removed stored tokens.");
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleConfigFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setYtBusy(true);
    setYtError(null);
    setYtSuccessMsg(null);
    try {
      const text = await file.text();
      let parsed: any;
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new Error(`"${file.name}" is not a valid JSON file.`);
      }

      const source = parsed.installed || parsed.web || parsed;
      const cid = (typeof source?.client_id === "string" ? source.client_id : "").trim();
      const csecret = (typeof source?.client_secret === "string" ? source.client_secret : "").trim();

      if (!cid || !csecret) {
        throw new Error(
          `The selected file "${file.name}" contains empty credentials ("client_id" or "client_secret" is missing or blank). Please download your OAuth 2.0 Client ID JSON from Google Cloud Console (Credentials > OAuth 2.0 Client IDs for Desktop app), or enter them manually in the fields below.`
        );
      }

      setYtClientId(cid);
      setYtClientSecret(csecret);

      const targetChannel = ytStatus?.active_channel_id;
      try {
        const updated = await api.uploadYoutubeClientFile(parsed, targetChannel);
        setYtStatus(updated);
      } catch {
        await api.saveYoutubeClient(cid, csecret, targetChannel);
        await loadYoutubeStatus(targetChannel);
      }
      setYtClientSecret("");
      setYtSuccessMsg(`Imported and encoded Google OAuth credentials from "${file.name}" successfully.`);
    } catch (err: any) {
      setYtError(`Failed to import OAuth credentials file: ${err.message || String(err)}`);
    } finally {
      setYtBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleCreateChannel = async () => {
    if (!newChannelName.trim()) return;
    setYtBusy(true);
    setYtError(null);
    try {
      const res = await api.createYoutubeChannel(newChannelName.trim());
      setNewChannelName("");
      setShowAddChannel(false);
      await loadYoutubeStatus(res.created.id);
      setYtSuccessMsg(`Created channel profile "${res.created.name}". You can now connect it.`);
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleActivateChannel = async (channelId: string) => {
    setYtBusy(true);
    setYtError(null);
    try {
      const updated = await api.activateYoutubeChannel(channelId);
      setYtStatus(updated);
      const activeName = updated.channels?.find((c) => c.id === channelId)?.name || channelId;
      setYtSuccessMsg(`Active channel switched to "${activeName}". Agent uploads will use this channel.`);
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleDeleteChannel = async (channelId: string) => {
    const target = ytStatus?.channels?.find((c) => c.id === channelId);
    if (!confirm(`Are you sure you want to remove the channel profile "${target?.name || channelId}"?`)) return;
    setYtBusy(true);
    setYtError(null);
    try {
      const updated = await api.deleteYoutubeChannel(channelId);
      setYtStatus(updated);
      setYtSuccessMsg("Removed channel profile.");
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };

  const handleSaveAgentSettings = async () => {
    setYtBusy(true);
    setYtError(null);
    try {
      const updated = await api.updateYoutubeAgentSettings({
        enabled: agentUploadEnabled,
        default_privacy: agentDefaultPrivacy,
        publish_time: agentPublishTime,
        lead_time_min: agentLeadTimeMin,
      });
      setAgentUploadEnabled(updated.enabled);
      setAgentDefaultPrivacy(updated.default_privacy);
      if (updated.publish_time) setAgentPublishTime(updated.publish_time);
      if (typeof updated.lead_time_min === "number") setAgentLeadTimeMin(updated.lead_time_min);
      setYtSuccessMsg("Updated Agent & Scheduler publishing settings successfully.");
    } catch (err: any) {
      setYtError(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  };
  const [data, setData] = useState<SystemProvidersResponse | null>(null);
  const [hardware, setHardware] = useState<HardwareDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Centralized Global LLM Routing State
  const [globalSettings, setGlobalSettings] = useState<GlobalLLMSettings | null>(null);
  const [selectedGlobalProvider, setSelectedGlobalProvider] = useState<string>("ollama");
  const [selectedGlobalModel, setSelectedGlobalModel] = useState<string>("qwen3.5:9b");
  const [flowOverrides, setFlowOverrides] = useState<Record<string, FlowOverrideConfig>>({
    story_narration: { provider_id: "global", model_name: "" },
    story_script: { provider_id: "global", model_name: "" },
    character_analysis: { provider_id: "global", model_name: "" },
    vision_inspection: { provider_id: "global", model_name: "" },
  });
  const [savingGlobalSettings, setSavingGlobalSettings] = useState<boolean>(false);
  const [globalSaveMessage, setGlobalSaveMessage] = useState<string | null>(null);

  const loadGlobalSettings = async () => {
    try {
      const res = await api.getGlobalLLMSettings();
      if (res) {
        setGlobalSettings(res);
        setSelectedGlobalProvider(res.global_default_provider || "ollama");
        setSelectedGlobalModel(res.global_default_model || "qwen3.5:9b");
        if (res.flow_overrides) {
          setFlowOverrides(res.flow_overrides);
        }
      }
    } catch (err) {
      console.error("Failed to load global LLM settings:", err);
    }
  };

  const handleSaveGlobalSettings = async () => {
    setSavingGlobalSettings(true);
    setGlobalSaveMessage(null);
    try {
      await api.saveGlobalLLMSettings({
        global_default_provider: selectedGlobalProvider,
        global_default_model: selectedGlobalModel,
        flow_overrides: flowOverrides,
      });
      setGlobalSaveMessage("Global LLM Routing & Defaults saved successfully!");
      setTimeout(() => setGlobalSaveMessage(null), 3500);
      loadGlobalSettings();
    } catch (err: any) {
      alert(`Failed to save global settings: ${err.message}`);
    } finally {
      setSavingGlobalSettings(false);
    }
  };

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

  // Cloud & Free LLM State
  const [cloudConfig, setCloudConfig] = useState<CloudLLMConfig | null>(null);
  const [cloudProviderType, setCloudProviderType] = useState<string>("openrouter");
  const [cloudEndpointUrl, setCloudEndpointUrl] = useState<string>("https://openrouter.ai/api/v1");
  const [cloudApiKey, setCloudApiKey] = useState<string>("");
  const [cloudShowApiKey, setCloudShowApiKey] = useState<boolean>(false);
  const [cloudModelName, setCloudModelName] = useState<string>("meta-llama/llama-3.3-70b-instruct:free");
  const [cloudTesting, setCloudTesting] = useState<boolean>(false);
  const [cloudTestResult, setCloudTestResult] = useState<CloudLLMTestResponse | null>(null);
  const [cloudSaving, setCloudSaving] = useState<boolean>(false);
  const [cloudSaveMessage, setCloudSaveMessage] = useState<string | null>(null);
  const [cloudSectionTab, setCloudSectionTab] = useState<"configuration" | "chat">("configuration");
  const [chatPrompt, setChatPrompt] = useState<string>("");
  const [chatSending, setChatSending] = useState<boolean>(false);
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant" | "error"; text: string; meta?: string }>>([]);

  const selectedProviderHealth = globalSettings?.providers?.find((provider) => provider.id === selectedGlobalProvider);

  const loadCloudConfig = async () => {
    try {
      const cfg = await api.getCloudLLMConfig();
      if (cfg) {
        setCloudConfig(cfg);
        setCloudProviderType(cfg.provider_type || "openrouter");
        setCloudEndpointUrl(cfg.endpoint_url || "https://openrouter.ai/api/v1");
        setCloudModelName(cfg.model_name || "meta-llama/llama-3.3-70b-instruct:free");
        if (cfg.has_api_key && cfg.masked_api_key) {
          setCloudApiKey(cfg.masked_api_key);
        }
      }
    } catch (err) {
      console.error("Failed to load cloud LLM config:", err);
    }
  };

  const handleApplyPreset = (preset: "openrouter" | "groq" | "freellmapi" | "custom") => {
    setCloudProviderType(preset);
    setCloudTestResult(null);
    setCloudSaveMessage(null);
    if (preset === "openrouter") {
      setCloudEndpointUrl("https://openrouter.ai/api/v1");
      setCloudModelName("meta-llama/llama-3.3-70b-instruct:free");
    } else if (preset === "groq") {
      setCloudEndpointUrl("https://api.groq.com/openai/v1");
      setCloudModelName("llama-3.3-70b-versatile");
    } else if (preset === "freellmapi") {
      setCloudEndpointUrl("http://localhost:3001/v1");
      setCloudModelName("auto");
    } else {
      setCloudEndpointUrl("http://127.0.0.1:1234/v1");
      setCloudModelName("default");
    }
  };

  const handleTestCloudConnection = async () => {
    setCloudTesting(true);
    setCloudTestResult(null);
    try {
      const res = await api.testCloudLLMConnection({
        endpoint_url: cloudEndpointUrl,
        api_key: cloudApiKey,
        model_name: cloudModelName,
      });
      setCloudTestResult(res);
    } catch (err: any) {
      setCloudTestResult({
        status: "ERROR",
        connected: false,
        latency_ms: 0,
        models_count: 0,
        models: [],
        error: err.message,
      });
    } finally {
      setCloudTesting(false);
    }
  };

  const handleSaveCloudConfig = async () => {
    setCloudSaving(true);
    setCloudSaveMessage(null);
    try {
      const res = await api.saveCloudLLMConfig({
        provider_type: cloudProviderType,
        endpoint_url: cloudEndpointUrl,
        api_key: cloudApiKey,
        model_name: cloudModelName,
        custom_models: cloudConfig?.custom_models || [
          "meta-llama/llama-3.3-70b-instruct:free",
          "google/gemini-2.0-flash-exp:free",
          "deepseek/deepseek-r1:free",
          "qwen/qwen-2.5-vl-72b-instruct:free",
          "google/gemini-2.0-pro-exp-02-05:free",
          "llama-3.3-70b-versatile",
          "llama-3.1-8b-instant",
        ],
        is_active: true,
      });
      setCloudConfig(res);
      const nextFlowOverrides = { ...flowOverrides };
      await api.saveGlobalLLMSettings({
        global_default_provider: cloudProviderType,
        global_default_model: cloudModelName,
        flow_overrides: nextFlowOverrides,
      });
      setSelectedGlobalProvider(cloudProviderType);
      setSelectedGlobalModel(cloudModelName);
      setCloudSaveMessage("Configuration saved. This provider is now active and verified.");
      await loadHealth();
      await loadGlobalSettings();
    } catch (err: any) {
      setCloudSaveMessage(`Save failed: ${err.message}`);
    } finally {
      setCloudSaving(false);
    }
  };

  const handleSendTestChat = async () => {
    const prompt = chatPrompt.trim();
    if (!prompt || chatSending) return;
    setChatMessages((current) => [...current, { role: "user", text: prompt }]);
    setChatPrompt("");
    setChatSending(true);
    try {
      const result: CloudLLMChatResponse = await api.chatWithCloudLLM({
        prompt,
        model_name: cloudConfig?.model_name || cloudModelName,
      });
      if (result.status === "OK") {
        setChatMessages((current) => [...current, {
          role: "assistant",
          text: result.response,
          meta: `${result.provider_type} · ${result.model_name} · ${result.latency_ms} ms`,
        }]);
      } else {
        setChatMessages((current) => [...current, { role: "error", text: result.error || "The provider returned no response." }]);
      }
    } catch (err: any) {
      setChatMessages((current) => [...current, { role: "error", text: err.message || "The chat request failed." }]);
    } finally {
      setChatSending(false);
    }
  };

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
      await loadYoutubeStatus();
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
      if (initialTab) setActiveTab(initialTab);
      loadGlobalSettings();
      loadHealth();
      loadOllamaAndResources();
      loadCloudConfig();
      loadYoutubeStatus();
    }
  }, [open, initialTab]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-navy border border-edge rounded-2xl shadow-2xl shadow-black/50 max-w-5xl w-full mx-3 h-[calc(100vh-1.5rem)] max-h-[900px] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-edge">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
              <Icons.ShieldCheck className="w-4 h-4 text-info" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-fg">AI connections</h2>
              <p className="text-xs text-fg-dim">Connect a provider, verify a model, then choose where PanelFlow uses it.</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose}>
              <span className="text-fg-dim text-sm font-bold">✕</span>
            </Button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="shrink-0 grid grid-cols-5 border-b border-edge px-2 sm:px-6 bg-ink/60">
          <button
            onClick={() => setActiveTab("global")}
            className={`min-w-0 py-2.5 px-1 sm:px-3 text-[11px] sm:text-xs font-bold border-b-2 transition-colors flex items-center justify-center gap-1.5 ${
              activeTab === "global"
                ? "border-accent text-info"
                : "border-transparent text-fg-dim hover:text-fg"
            }`}
          >
            <Icons.Sliders className="w-3.5 h-3.5 text-info" />
            Routing
          </button>
          <button
            onClick={() => setActiveTab("cloud_llm")}
            className={`min-w-0 py-2.5 px-1 sm:px-3 text-[11px] sm:text-xs font-bold border-b-2 transition-colors flex items-center justify-center gap-1.5 ${
              activeTab === "cloud_llm"
                ? "border-accent text-info"
                : "border-transparent text-fg-dim hover:text-fg"
            }`}
          >
            <Icons.Sparkles className="w-3.5 h-3.5 text-warn" />
            Cloud & gateways
          </button>
          <button
            onClick={() => setActiveTab("ollama")}
            className={`min-w-0 py-2.5 px-1 sm:px-3 text-[11px] sm:text-xs font-bold border-b-2 transition-colors flex items-center justify-center ${
              activeTab === "ollama"
                ? "border-accent text-info"
                : "border-transparent text-fg-dim hover:text-fg"
            }`}
          >
            Local Ollama
          </button>
          <button
            onClick={() => setActiveTab("youtube")}
            className={`min-w-0 py-2.5 px-1 sm:px-3 text-[11px] sm:text-xs font-bold border-b-2 transition-colors flex items-center justify-center gap-1.5 ${
              activeTab === "youtube"
                ? "border-bad text-bad"
                : "border-transparent text-fg-dim hover:text-fg"
            }`}
          >
            <YoutubeIcon className={`w-3.5 h-3.5 ${activeTab === "youtube" ? "text-bad" : "text-fg-dim"}`} />
            YouTube
            {ytStatus?.connected && (
              <span className="w-1.5 h-1.5 rounded-full bg-ok shrink-0" title="Connected" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("system")}
            className={`min-w-0 py-2.5 px-1 sm:px-3 text-[11px] sm:text-xs font-bold border-b-2 transition-colors flex items-center justify-center ${
              activeTab === "system"
                ? "border-accent text-info"
                : "border-transparent text-fg-dim hover:text-fg"
            }`}
          >
            System
          </button>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 sm:p-6 space-y-4">
          {activeTab === "global" && (
            <div className="space-y-4">
              {/* Header Guidance */}
              <div className="flex items-center justify-between p-3.5 bg-gradient-to-r from-accent/40 via-navy to-ink rounded-xl border border-accent/40">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center text-info">
                    <Icons.Sliders className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-fg">Centralized LLM Provider & Routing Cockpit</h3>
                    <p className="text-[11px] text-fg-dim">
                      Configure your default provider and assign specialized models per workflow (Narration, Script, Characters, Vision).
                    </p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSaveGlobalSettings}
                  disabled={savingGlobalSettings}
                  className="text-xs"
                >
                  {savingGlobalSettings ? "Saving Settings..." : "Save Global Configuration"}
                </Button>
              </div>

              {globalSaveMessage && (
                <div className="p-2.5 bg-ok/40 border border-ok/80 rounded-lg text-xs font-semibold text-ok">
                  ✓ {globalSaveMessage}
                </div>
              )}

              {/* Global Default Section */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge/80 pb-2">
                  <div>
                    <h4 className="text-xs font-bold text-fg uppercase tracking-wider">
                      1. Application-Wide Default LLM Provider
                    </h4>
                    <p className="text-[11px] text-fg-dim">
                      Used by all features unless an explicit flow override is configured.
                    </p>
                  </div>
                  <Badge variant={selectedProviderHealth?.is_healthy ? "success" : "warning"}>
                    {selectedProviderHealth?.is_healthy ? "Ready" : "Not verified"}: {selectedGlobalProvider}
                  </Badge>
                </div>

                {/* Provider Selector Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 pt-1">
                  {[
                    { id: "ollama", name: "Local Ollama", icon: "🖥️", note: "Offline Local GPU", tag: "Local" },
                    { id: "freellmapi", name: "FreeLLMAPI", icon: "⚡", note: "Multi-Provider Gateway", tag: "Gateway" },
                    { id: "openrouter", name: "OpenRouter", icon: "☁️", note: "Free Llama 3.3 & Gemini", tag: "Free Tier" },
                    { id: "groq", name: "Groq Cloud", icon: "🚀", note: "Ultra-Fast LPU", tag: "Free Tier" },
                    { id: "custom", name: "Custom API", icon: "💻", note: "OpenAI-Compatible", tag: "Custom" },
                  ].map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedGlobalProvider(p.id)}
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        selectedGlobalProvider === p.id
                          ? "border-accent bg-accent/30 shadow-sm shadow-accent/20"
                          : "border-edge bg-navy/60 hover:border-edge"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-bold text-fg flex items-center gap-1">
                          <span>{p.icon}</span> {p.name}
                        </span>
                        <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-flat text-fg-dim">
                          {p.tag}
                        </span>
                      </div>
                      <p className="text-[10px] text-fg-dim leading-tight">{p.note}</p>
                    </button>
                  ))}
                </div>

                {/* Global Default Model Selection */}
                <div className="space-y-1 pt-2">
                  <label className="text-fg-dim font-semibold text-xs">Global Default Model Name</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={selectedGlobalModel}
                      onChange={(e) => setSelectedGlobalModel(e.target.value)}
                      placeholder="e.g. qwen3.5:9b, gemini-2.0-flash, meta-llama/llama-3.3-70b-instruct:free"
                      className="flex-1 bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    />
                    <select
                      onChange={(e) => {
                        if (e.target.value) setSelectedGlobalModel(e.target.value);
                      }}
                      className="bg-navy border border-edge rounded px-2 py-1.5 text-fg text-xs focus:outline-none focus:border-accent cursor-pointer"
                      value=""
                    >
                      <option value="">Quick Presets...</option>
                      <option value="qwen3.5:9b">Local Ollama: qwen3.5:9b</option>
                      <option value="qwen3.8:27b">Local Ollama: qwen3.8:27b</option>
                      <option value="auto">FreeLLMAPI: Automatic healthy route</option>
                      <option value="gemini-3.8-flash">FreeLLMAPI: Gemini 3.8 Flash</option>
                      <option value="meta-llama/llama-3.3-70b-instruct:free">OpenRouter: Llama 3.3 70B (Free)</option>
                      <option value="google/gemini-2.0-flash-exp:free">OpenRouter: Gemini 2.0 Flash (Free)</option>
                      <option value="deepseek/deepseek-r1:free">OpenRouter: DeepSeek R1 (Free)</option>
                      <option value="llama-3.3-70b-versatile">Groq: Llama 3.3 70B Versatile</option>
                    </select>
                  </div>
                  {selectedGlobalProvider !== "ollama" && !selectedProviderHealth?.is_healthy && (
                    <button
                      type="button"
                      onClick={() => {
                        if (["freellmapi", "openrouter", "groq", "custom"].includes(selectedGlobalProvider)) {
                          handleApplyPreset(selectedGlobalProvider as "freellmapi" | "openrouter" | "groq" | "custom");
                        }
                        setActiveTab("cloud_llm");
                      }}
                      className="text-xs font-semibold text-warn hover:text-warn"
                    >
                      Configure and verify this provider
                    </button>
                  )}
                </div>
              </Card>

              {/* Per-Workflow Routing Matrix Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="border-b border-edge/80 pb-2">
                  <h4 className="text-xs font-bold text-fg uppercase tracking-wider">
                    2. Per-Workflow Routing Matrix (Freedom & Fine Control)
                  </h4>
                  <p className="text-[11px] text-fg-dim">
                    Set whether each workflow inherits the Global Default or routes to a specialized model.
                  </p>
                </div>

                <div className="space-y-3">
                  {[
                    {
                      key: "story_narration",
                      label: "🎬 Story Narration (Narration Studio)",
                      desc: "Full-page macro scene analysis and panel-level audio narration drafting.",
                      defaultModel: "gemini-2.0-flash",
                    },
                    {
                      key: "story_script",
                      label: "📜 Screenplay & Scriptwriting",
                      desc: "Scene dialogue extraction, cinematic timing, and action beat generation.",
                      defaultModel: "llama-3.3-70b-versatile",
                    },
                    {
                      key: "character_analysis",
                      label: "👥 Character Roster & Profiling",
                      desc: "Detecting character identities, visual traits, and naming continuity.",
                      defaultModel: "qwen3.5:9b",
                    },
                    {
                      key: "vision_inspection",
                      label: "👁️ Visual Panel & OCR Inspection",
                      desc: "Multimodal inspection of uncropped manga pages and speech bubbles.",
                      defaultModel: "llama3.2-vision",
                    },
                  ].map((flow) => {
                    const currentFlowConfig = flowOverrides[flow.key] || { provider_id: "global", model_name: "" };
                    return (
                      <div
                        key={flow.key}
                        className="p-3 bg-navy/60 rounded-xl border border-edge/80 flex flex-col md:flex-row md:items-center justify-between gap-3"
                      >
                        <div className="space-y-0.5 max-w-sm">
                          <span className="text-xs font-bold text-fg">{flow.label}</span>
                          <p className="text-[11px] text-fg-dim">{flow.desc}</p>
                        </div>

                        <div className="flex items-center gap-2 flex-wrap">
                          <select
                            value={currentFlowConfig.provider_id || "global"}
                            onChange={(e) => {
                              const newPid = e.target.value;
                              setFlowOverrides({
                                ...flowOverrides,
                                [flow.key]: {
                                  provider_id: newPid,
                                  model_name: newPid === "global" ? "" : (currentFlowConfig.model_name || flow.defaultModel),
                                },
                              });
                            }}
                            className="bg-ink border border-edge rounded px-2.5 py-1.5 text-xs text-fg focus:outline-none focus:border-accent font-medium"
                          >
                            <option value="global">🌐 Use Global Default</option>
                            <option value="ollama">🖥️ Local Ollama</option>
                            <option value="freellmapi">⚡ FreeLLMAPI Gateway</option>
                            <option value="openrouter">☁️ OpenRouter Free</option>
                            <option value="groq">🚀 Groq Cloud Free</option>
                            <option value="custom">💻 Custom OpenAI</option>
                          </select>

                          {currentFlowConfig.provider_id && currentFlowConfig.provider_id !== "global" && (
                            <input
                              type="text"
                              value={currentFlowConfig.model_name || ""}
                              onChange={(e) =>
                                setFlowOverrides({
                                  ...flowOverrides,
                                  [flow.key]: {
                                    ...currentFlowConfig,
                                    model_name: e.target.value,
                                  },
                                })
                              }
                              placeholder={flow.defaultModel}
                              className="bg-ink border border-edge rounded px-2.5 py-1.5 text-xs font-mono text-fg w-44 focus:outline-none focus:border-accent"
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="flex justify-end pt-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSaveGlobalSettings}
                    disabled={savingGlobalSettings}
                  >
                    Save Routing Matrix
                  </Button>
                </div>
              </Card>
            </div>
          )}
          {activeTab === "system" && (
            <>
              {/* Hardware Diagnostics Card */}
              {hardware && (
                <Card className="p-4 bg-ink border-edge">
                  <div className="flex items-center justify-between border-b border-edge/80 pb-3 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-fg-dim">
                        Hardware Environment
                      </span>
                      <Badge variant={tierVariant(hardware.neural_performance_tier)} className="text-[10px] uppercase font-mono font-bold">
                        Tier: {hardware.neural_performance_tier}
                      </Badge>
                    </div>
                    <span className="text-[11px] text-fg-dim font-mono">
                      {hardware.os_name} {hardware.os_release} ({hardware.architecture})
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div className="space-y-0.5">
                      <span className="text-[10px] text-fg-faint uppercase font-semibold">Memory</span>
                      <p className="font-mono text-fg">{hardware.total_ram_gb} GB ({hardware.available_ram_gb} GB free)</p>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-[10px] text-fg-faint uppercase font-semibold">Disk Storage</span>
                      <p className="font-mono text-fg">{hardware.free_disk_gb} GB free</p>
                    </div>
                    <div className="space-y-0.5 sm:col-span-2">
                      <span className="text-[10px] text-fg-faint uppercase font-semibold">Graphics & VRAM</span>
                      <p className="font-mono text-fg truncate" title={hardware.gpu_name}>
                        {hardware.gpu_name} {hardware.vram_mb > 0 ? `(${Math.round(hardware.vram_mb / 1024)} GB)` : ""}
                      </p>
                    </div>
                  </div>

                  <p className="text-[11px] text-fg-dim mt-3 pt-2.5 border-t border-edge/60 leading-relaxed">
                    {hardware.recommendations}
                  </p>
                </Card>
              )}

              {/* 1-Click Setup & Model Onboarding Assistant Card */}
              <Card className="p-4 bg-gradient-to-r from-accent/40 via-ink to-ink border-accent/40 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-edge/80 pb-2">
                  <div className="flex items-center gap-2">
                    <Icons.ShieldCheck className="w-4 h-4 text-info" />
                    <span className="text-xs font-bold uppercase tracking-wider text-info">
                      Setup & Dependency Assistant
                    </span>
                  </div>
                  <span className="text-[10px] text-fg-dim font-mono">1-Click Local Provisioning</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {/* Action 1: Locate FFmpeg */}
                  <div className="p-3 rounded-lg bg-navy/70 border border-edge flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-fg">FFmpeg Discovery</span>
                        <Badge variant={data?.providers.find((p) => p.id === "ffmpeg")?.status === "HEALTHY" ? "success" : "warning"} className="text-[9px]">
                          {data?.providers.find((p) => p.id === "ffmpeg")?.status || "MISSING"}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-fg-dim mt-1">
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
                  <div className="p-3 rounded-lg bg-navy/70 border border-edge flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-fg">Default Voice Pack</span>
                        <Badge variant="accent" className="text-[9px]">
                          AppData Sync
                        </Badge>
                      </div>
                      <p className="text-[11px] text-fg-dim mt-1">
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
                      <Icons.Plus className="w-3.5 h-3.5 mr-1.5 text-info" />
                      {provisioningVoices ? "Provisioning..." : "Provision Voice Profiles"}
                    </Button>
                  </div>

                  {/* Action 3: Install Playwright */}
                  <div className="p-3 rounded-lg bg-navy/70 border border-edge flex flex-col justify-between space-y-2">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-fg">Playwright Chromium</span>
                        <Badge variant={data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "success" : "neutral"} className="text-[9px]">
                          {data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "READY" : "INSTALL"}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-fg-dim mt-1">
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
                      <Icons.Globe className="w-3.5 h-3.5 mr-1.5 text-info" />
                      {installingPlaywright ? "Downloading..." : data?.providers.find((p) => p.id === "playwright")?.status === "HEALTHY" ? "Installed" : "Install Browsers"}
                    </Button>
                  </div>
                </div>

                {/* Notifications & Result banners */}
                {ffmpegResult && (
                  <p className="text-[11px] font-mono text-info bg-accent/40 border border-accent/60 rounded px-2.5 py-1.5">
                    {ffmpegResult}
                  </p>
                )}
                {voiceResult && (
                  <p className="text-[11px] font-mono text-ok bg-ok/40 border border-ok/60 rounded px-2.5 py-1.5">
                    {voiceResult}
                  </p>
                )}
                {playwrightStatus && (
                  <div className="p-2.5 rounded bg-navy border border-edge text-[11px] font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-fg-dim font-bold">Playwright Installer: {playwrightStatus.status}</span>
                      {playwrightStatus.exit_code !== null && (
                        <span className="text-fg-faint">Exit Code: {playwrightStatus.exit_code}</span>
                      )}
                    </div>
                    {playwrightStatus.log_lines && playwrightStatus.log_lines.length > 0 && (
                      <p className="text-fg-dim truncate max-w-full">
                        {playwrightStatus.log_lines[playwrightStatus.log_lines.length - 1]}
                      </p>
                    )}
                  </div>
                )}
              </Card>

              {/* Providers List */}
              <div className="space-y-2.5">
                <h3 className="text-xs font-bold uppercase tracking-wider text-fg-dim px-0.5">
                  Local Tools & Model Engines
                </h3>
                {loading ? (
                  <div className="flex items-center justify-center py-10 text-fg-dim">
                    <Icons.Rotate className="w-5 h-5 animate-spin mr-2" />
                    Probing engine dependencies...
                  </div>
                ) : data ? (
                  data.providers.map((p) => {
                    const isIssue = p.status !== "HEALTHY" && p.status !== "READY";
                    return (
                      <Card key={p.id} className="p-3.5 bg-ink border-edge hover:border-edge transition-colors">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3 min-w-0">
                            <div
                              className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${
                                statusColor[p.status] || "bg-fg-faint"
                              }`}
                            />
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-bold text-fg">{p.name}</span>
                                <Badge variant={statusBadgeVariant(p.status)} className="text-[9px] uppercase font-bold">
                                  {p.status}
                                </Badge>
                                {p.required ? (
                                  <span className="text-[9px] text-warn/80 font-mono uppercase font-semibold">Required</span>
                                ) : (
                                  <span className="text-[9px] text-fg-faint font-mono uppercase">Optional</span>
                                )}
                              </div>
                              <p className="text-[11px] text-fg-dim mt-0.5">{p.details}</p>
                              {isIssue && providerGuidance[p.id] && (
                                <p className="text-[11px] text-warn/90 mt-1.5 bg-warn/20 border border-warn/40 rounded px-2 py-1">
                                  💡 {providerGuidance[p.id]}
                                </p>
                              )}
                              <div className="flex items-center gap-3 mt-1.5 text-[10px] text-fg-faint font-mono">
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
                  <div className="text-center text-fg-faint py-10">
                    Failed to load provider status.
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === "ollama" && (
            /* Ollama & Hardware Telemetry Tab */
            <div className="space-y-4">
              {/* Endpoint Configuration Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
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
                        ? "bg-ok/40 border border-ok/40 text-ok"
                        : "bg-bad/40 border border-bad/40 text-bad"
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
                    <label className="text-fg-dim font-semibold">Endpoint URL</label>
                    <input
                      type="text"
                      value={ollamaConfig?.endpoint_url || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, endpoint_url: e.target.value })
                      }
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                      placeholder="http://127.0.0.1:11434"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-fg-dim font-semibold flex items-center justify-between">
                      <span>Auth Bearer Token / API Key</span>
                      {ollamaConfig?.has_auth_token && (
                        <span className="text-[10px] text-ok font-mono">Active in Keychain</span>
                      )}
                    </label>
                    <input
                      type="password"
                      value={authTokenInput}
                      onChange={(e) => setAuthTokenInput(e.target.value)}
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                      placeholder={ollamaConfig?.has_auth_token ? "•••••••• (Leave blank to keep current)" : "Optional Bearer Token"}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 text-xs text-fg-dim cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ollamaConfig?.is_remote || false}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, is_remote: e.target.checked })
                      }
                      className="rounded accent-accent"
                    />
                    <span>Private Remote Server / Cloud Endpoint (Enforces strict SSRF filtering)</span>
                  </label>
                  <Button variant="secondary" size="sm" onClick={handleSaveOllamaConfig} disabled={savingConfig}>
                    Save Settings
                  </Button>
                </div>
              </Card>

              {/* Multi-Role Model Selectors */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-fg">
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
                      <label className="text-fg-dim font-semibold">Vision Model</label>
                      <span className="text-[10px] text-ok font-mono">Multimodal VLM</span>
                    </div>
                    <select
                      value={ollamaConfig?.vision_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, vision_model: e.target.value })
                      }
                      className="w-full bg-navy border border-edge rounded px-2 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`vis-${m.name}`} value={m.name}>
                          {m.name} {m.supports_vision ? "👁️ (Vision)" : ""} {m.name === ollamaRecommendations?.vision_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-fg-faint">Visual panel description & character detection</p>
                  </div>

                  {/* Story Reasoning Role */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-fg-dim font-semibold">Story Reasoning</label>
                      <span className="text-[10px] text-info font-mono">Narrative Logic</span>
                    </div>
                    <select
                      value={ollamaConfig?.reasoning_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, reasoning_model: e.target.value })
                      }
                      className="w-full bg-navy border border-edge rounded px-2 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`reas-${m.name}`} value={m.name}>
                          {m.name} {m.name === ollamaRecommendations?.reasoning_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-fg-faint">Chapter-wide plot, continuity & scene synthesis</p>
                  </div>

                  {/* Narration Role */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-fg-dim font-semibold">Narration Model</label>
                      <span className="text-[10px] text-warn font-mono">Voice Script</span>
                    </div>
                    <select
                      value={ollamaConfig?.narration_model || ""}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, narration_model: e.target.value })
                      }
                      className="w-full bg-navy border border-edge rounded px-2 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    >
                      {ollamaModels.map((m) => (
                        <option key={`narr-${m.name}`} value={m.name}>
                          {m.name} {m.name === ollamaRecommendations?.narration_model ? "★ Recommended" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-fg-faint">Emotional storyteller recap & cadence adaptation</p>
                  </div>
                </div>
              </Card>

              {/* 1-Click Model Downloader Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <Icons.Plus className="w-4 h-4 text-info" />
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
                      Download & Pull Ollama Models
                    </span>
                  </div>
                  <span className="text-[10px] text-fg-dim font-mono">Direct Streaming via /api/pull</span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-fg-dim">Quick Recommendations:</span>
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
                      className="flex-1 bg-navy border border-edge rounded px-3 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
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
                    <div className="p-3 rounded-lg bg-navy border border-edge space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono font-bold text-fg">
                          {pullStatus.status_text || pullStatus.status}
                        </span>
                        <span className="font-mono text-info font-bold">
                          {pullStatus.percent ? `${pullStatus.percent}%` : ""}
                        </span>
                      </div>
                      <ProgressBar progress={pullStatus.percent || 0} />
                      {pullStatus.total_bytes > 0 && (
                        <div className="flex justify-between text-[10px] text-fg-faint font-mono">
                          <span>{Math.round(pullStatus.completed_bytes / (1024 * 1024))} MB</span>
                          <span>{Math.round(pullStatus.total_bytes / (1024 * 1024))} MB</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>

              {/* Discovered Models & Capability Badges */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-fg">
                    Installed Ollama Inventory ({ollamaModels.length} models)
                  </span>
                  <span className="text-[10px] text-fg-faint font-mono">Capabilities verified via POST /api/show</span>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {ollamaModels.length === 0 ? (
                    <p className="text-xs text-fg-faint text-center py-4">No models detected. Ensure Ollama is running.</p>
                  ) : (
                    ollamaModels.map((m) => (
                      <div
                        key={m.name}
                        className="flex items-center justify-between p-2 rounded bg-navy/60 border border-edge/80 text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-fg">{m.name}</span>
                          <span className="text-[10px] text-fg-faint font-mono">({m.parameter_size}, {m.quantization_level})</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {m.supports_vision && (
                            <Badge variant="success" className="text-[9px]">Vision</Badge>
                          )}
                          {m.supports_tools && (
                            <Badge variant="accent" className="text-[9px]">Tools</Badge>
                          )}
                          {m.supports_thinking && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-accent/60 border border-accent/40 text-info">
                              Thinking
                            </span>
                          )}
                          <span className="text-[10px] text-fg-dim font-mono pl-1">{m.family}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Card>

              {/* Hardware Telemetry & Concurrency Admission Controller */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
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
                  <div className="p-2.5 rounded-lg bg-navy border border-accent/40 text-xs font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-info">Benchmark: {benchmarkResult.model_tested}</span>
                      <span className="text-ok font-bold">{benchmarkResult.speedup_ratio}x Throughput</span>
                    </div>
                    <p className="text-[11px] text-fg-dim">
                      Sequential: {benchmarkResult.sequential_duration_sec}s | Concurrent: {benchmarkResult.concurrent_duration_sec}s
                    </p>
                    <p className="text-[11px] text-fg-dim italic">{benchmarkResult.recommendation}</p>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 rounded bg-navy/50 border border-edge">
                    <span className="text-[10px] text-fg-faint uppercase font-semibold">Host RAM</span>
                    <p className="font-mono text-fg font-bold mt-0.5">
                      {resources?.ram?.available_gb ?? hardware?.available_ram_gb ?? 0} GB Free
                    </p>
                    <p className="text-[10px] text-fg-faint font-mono">
                      {resources?.ram?.total_gb ?? hardware?.total_ram_gb ?? 0} GB Total ({resources?.ram?.used_percent ?? 0}%)
                    </p>
                  </div>

                  <div className="p-2.5 rounded bg-navy/50 border border-edge">
                    <span className="text-[10px] text-fg-faint uppercase font-semibold">GPU Dedicated VRAM</span>
                    <p className="font-mono text-fg font-bold mt-0.5">
                      {resources?.gpu?.free_mb ? Math.round(resources.gpu.free_mb) : hardware?.vram_mb ?? 0} MB Free
                    </p>
                    <p className="text-[10px] text-fg-faint font-mono truncate" title={resources?.gpu?.device_name}>
                      {resources?.gpu?.device_name || hardware?.gpu_name}
                    </p>
                  </div>

                  <div className="p-2.5 rounded bg-navy/50 border border-edge">
                    <span className="text-[10px] text-fg-faint uppercase font-semibold">Active Ollama VRAM</span>
                    <p className="font-mono text-fg font-bold mt-0.5">
                      {resources?.ollama?.total_ollama_vram_mb ?? 0} MB
                    </p>
                    <p className="text-[10px] text-fg-faint font-mono">
                      {resources?.ollama?.loaded_models_count ?? 0} active models in memory
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
                  <div className="space-y-1">
                    <label className="text-fg-dim font-semibold">Admission Mode</label>
                    <select
                      value={ollamaConfig?.concurrency_mode || "MANUAL"}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, concurrency_mode: e.target.value })
                      }
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    >
                      <option value="MANUAL">MANUAL (Fixed slot limit)</option>
                      <option value="AUTO">AUTO (Dynamic headroom scaling)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-fg-dim font-semibold">Max Concurrent GPU Tasks</label>
                    <select
                      value={ollamaConfig?.max_gpu_concurrency || 1}
                      onChange={(e) =>
                        setOllamaConfig({ ...ollamaConfig, max_gpu_concurrency: parseInt(e.target.value, 10) })
                      }
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
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

          {activeTab === "youtube" && (
            <div className="space-y-4">
              {/* Header Status Banner */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-gradient-to-r from-bad/30 via-navy to-ink rounded-xl border border-bad/40 gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-bad/20 border border-bad/30 flex items-center justify-center text-bad shrink-0">
                    <YoutubeIcon className="w-5 h-5 fill-current" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-fg">YouTube Studio & Video Publishing</h3>
                      {ytStatus?.connected ? (
                        <Badge variant="success" className="text-[10px] font-mono">
                          Connected: {ytStatus.channels?.find((c) => c.is_active)?.name || "Active Channel"}
                        </Badge>
                      ) : ytStatus?.pending ? (
                        <Badge variant="warning" className="text-[10px] font-mono">Authorization Pending</Badge>
                      ) : (
                        <Badge variant="neutral" className="text-[10px] font-mono">Not Connected</Badge>
                      )}
                    </div>
                    <p className="text-xs text-fg-dim mt-0.5">
                      {ytStatus?.connected
                        ? "Active channel authorized. Videos, custom thumbnails and metadata upload directly to YouTube via resumable chunks."
                        : ytStatus?.pending
                        ? "Waiting for you to authorize access in your browser window."
                        : "Connect your channel using a Google Cloud OAuth Desktop client (scope: youtube.upload)."}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button variant="ghost" size="sm" onClick={() => loadYoutubeStatus()} disabled={ytBusy}>
                    <Icons.Rotate className={`w-3.5 h-3.5 mr-1 ${ytBusy ? "animate-spin" : ""}`} />
                    Refresh
                  </Button>
                  {ytStatus?.connected && (
                    <Button variant="destructive" size="sm" onClick={() => handleDisconnectYoutube()} disabled={ytBusy}>
                      Disconnect Active
                    </Button>
                  )}
                </div>
              </div>

              {/* Status Alert Messages */}
              {(ytError || ytStatus?.error) && (
                <div className="p-3 rounded-lg bg-bad/40 border border-bad/40 text-bad text-xs flex items-center justify-between">
                  <span>{ytError || ytStatus?.error}</span>
                  <button onClick={() => setYtError(null)} className="text-bad hover:text-bad ml-2">✕</button>
                </div>
              )}
              {ytSuccessMsg && (
                <div className="p-3 rounded-lg bg-ok/40 border border-ok/40 text-ok text-xs flex items-center justify-between">
                  <span>{ytSuccessMsg}</span>
                  <button onClick={() => setYtSuccessMsg(null)} className="text-ok hover:text-ok ml-2">✕</button>
                </div>
              )}

              {/* Multi-Channel Management Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
                      Configured YouTube Channels
                    </span>
                    <Badge variant="accent" className="text-[9px] uppercase">
                      {ytStatus?.channels?.length || 1} Channel Profiles
                    </Badge>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowAddChannel(!showAddChannel)}
                    className="text-xs"
                  >
                    {showAddChannel ? "Cancel" : "+ Add Channel Profile"}
                  </Button>
                </div>

                {showAddChannel && (
                  <div className="p-3 rounded-lg bg-navy border border-edge space-y-2">
                    <label className="text-xs font-semibold text-fg-dim">New Channel Profile Name</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newChannelName}
                        onChange={(e) => setNewChannelName(e.target.value)}
                        placeholder="e.g. Manga Recap Studio, Gaming Highlights"
                        className="flex-1 bg-ink border border-edge rounded px-2.5 py-1.5 text-xs text-fg focus:outline-none focus:border-accent"
                      />
                      <Button variant="primary" size="sm" onClick={handleCreateChannel} disabled={ytBusy || !newChannelName.trim()}>
                        Create Profile
                      </Button>
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  {ytStatus?.channels?.map((channel) => (
                    <div
                      key={channel.id}
                      className={`p-3 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors ${
                        channel.is_active
                          ? "border-accent/60 bg-accent/20"
                          : "border-edge bg-navy/40 hover:border-edge"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                            channel.is_active ? "bg-accent text-white" : "bg-flat text-fg-dim"
                          }`}
                        >
                          {channel.is_active ? "★" : "YT"}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-fg">{channel.name}</span>
                            {channel.is_active && (
                              <Badge variant="success" className="text-[9px] uppercase font-mono">
                                Active Target
                              </Badge>
                            )}
                            <Badge variant={channel.connected ? "success" : "neutral"} className="text-[9px] uppercase font-mono">
                              {channel.connected ? "Connected" : "Disconnected"}
                            </Badge>
                          </div>
                          <span className="text-[11px] text-fg-faint font-mono">ID: {channel.id}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {!channel.is_active && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleActivateChannel(channel.id)}
                            disabled={ytBusy}
                            className="text-xs"
                          >
                            Set as Active
                          </Button>
                        )}
                        {!channel.connected ? (
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => handleConnectYoutube(channel.id)}
                            disabled={ytBusy}
                            className="bg-bad hover:bg-bad text-white text-xs"
                          >
                            Connect
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDisconnectYoutube(channel.id)}
                            disabled={ytBusy}
                            className="text-xs text-fg-dim hover:text-bad"
                          >
                            Disconnect
                          </Button>
                        )}
                        {(ytStatus?.channels?.length || 0) > 1 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteChannel(channel.id)}
                            disabled={ytBusy}
                            className="text-xs text-fg-faint hover:text-bad"
                            title="Delete channel profile"
                          >
                            ✕
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              {/* File Config Upload & OAuth Credentials Card */}
              <Card className="p-4 bg-ink border-edge space-y-4">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
                      OAuth 2.0 Credentials & Config Import
                    </span>
                    <Badge variant={ytStatus?.configured ? "accent" : "neutral"} className="text-[9px] uppercase">
                      {ytStatus?.configured ? "Client Configured" : "Credentials Required"}
                    </Badge>
                  </div>
                </div>

                <p className="text-xs text-fg-dim leading-relaxed">
                  Provide Google Cloud OAuth 2.0 credentials for Desktop apps. Upload the downloaded{" "}
                  <code>client_secret_*.json</code> file, or enter your Client ID and Client Secret manually below.
                </p>

                {/* File Upload Dropzone / Action Button */}
                <div className="p-3.5 rounded-xl border border-dashed border-edge bg-navy/50 flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div className="space-y-0.5 text-center sm:text-left">
                    <span className="text-xs font-bold text-fg block">Import Google Cloud JSON File</span>
                    <span className="text-[11px] text-fg-dim">
                      Auto-populates and securely encodes Client ID and Secret from your downloaded file.
                    </span>
                  </div>
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".json,application/json"
                    onChange={handleConfigFileUpload}
                    className="hidden"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={ytBusy}
                    className="shrink-0 bg-accent hover:bg-accent text-white font-semibold"
                  >
                    Upload client_secret.json
                  </Button>
                </div>

                {/* Permanent Credentials Inputs (Always Visible) */}
                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg-dim">
                      OAuth Client Credentials
                    </span>
                    {ytStatus?.configured && (
                      <span className="text-[11px] text-ok font-mono flex items-center gap-1">
                        ✓ Stored on disk (enc:v1)
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="space-y-1">
                      <label className="text-fg-dim font-semibold flex items-center justify-between">
                        <span>OAuth Client ID</span>
                        {ytStatus?.masked_client_id && (
                          <span className="text-[10px] text-fg-faint font-mono">Current: {ytStatus.masked_client_id}</span>
                        )}
                      </label>
                      <input
                        type="text"
                        value={ytClientId}
                        onChange={(e) => setYtClientId(e.target.value)}
                        className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                        placeholder="e.g. 123456789-abcdef.apps.googleusercontent.com"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-fg-dim font-semibold flex items-center justify-between">
                        <span>OAuth Client Secret</span>
                        <span className="text-[10px] text-fg-faint">Base64 encoded on disk</span>
                      </label>
                      <input
                        type="password"
                        value={ytClientSecret}
                        onChange={(e) => setYtClientSecret(e.target.value)}
                        className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                        placeholder={
                          ytStatus?.configured
                            ? "•••••••• (Encoded & Saved — enter new to replace)"
                            : "e.g. GOCSPX-xxxxxxxxxxxx"
                        }
                      />
                    </div>
                  </div>

                  <p className="text-[11px] text-fg-faint">
                    Credentials are stored locally in encoded format (<code>enc:v1:&lt;base64&gt;</code>) with restricted permissions. Secrets are never logged or exposed in API responses.
                  </p>

                  <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-edge">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleSaveCredentialsOnly}
                      disabled={ytBusy || (!ytClientId.trim() || !ytClientSecret.trim())}
                      className="text-xs"
                    >
                      Save Credentials Only
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleConnectYoutube()}
                      disabled={ytBusy || (!ytStatus?.configured && (!ytClientId.trim() || !ytClientSecret.trim()))}
                      className="bg-bad hover:bg-bad text-white text-xs"
                    >
                      <YoutubeIcon className="w-3.5 h-3.5 mr-1.5 fill-current" />
                      {ytBusy
                        ? "Connecting..."
                        : ytStatus?.connected
                        ? "Re-authorize Active Channel"
                        : "Save & Authorize Channel"}
                    </Button>
                  </div>
                </div>
              </Card>

              {/* AI Agents & Scheduler Settings Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-fg">
                      AI Agents & Scheduler Settings
                    </span>
                    <Badge variant={agentUploadEnabled ? "success" : "neutral"} className="text-[9px] uppercase">
                      {agentUploadEnabled ? "Agent Uploads Enabled" : "Manual Only"}
                    </Badge>
                  </div>
                  <Button variant="secondary" size="sm" onClick={handleSaveAgentSettings} disabled={ytBusy} className="text-xs">
                    Save Agent Permissions
                  </Button>
                </div>

                <p className="text-xs text-fg-dim leading-relaxed">
                  Configure autonomous video publishing permissions, daily release slots, and default privacy for AI Agents and Autopilot jobs.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs pt-1">
                  <div className="p-3 rounded-lg border border-edge bg-navy/40 space-y-2">
                    <label className="flex items-center gap-2 font-semibold text-fg cursor-pointer">
                      <input
                        type="checkbox"
                        checked={agentUploadEnabled}
                        onChange={(e) => setAgentUploadEnabled(e.target.checked)}
                        className="rounded accent-accent w-4 h-4"
                      />
                      <span>Allow Agent Uploads</span>
                    </label>
                    <p className="text-[11px] text-fg-dim leading-relaxed pl-6">
                      Target: <strong>{ytStatus?.channels?.find((c) => c.is_active)?.name || "Active Channel"}</strong>. When off, agents render locally without uploading.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg border border-edge bg-navy/40 space-y-2">
                    <label className="font-semibold text-fg block">Default Privacy</label>
                    <select
                      value={agentDefaultPrivacy}
                      onChange={(e) => setAgentDefaultPrivacy(e.target.value as any)}
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 text-xs text-fg focus:outline-none focus:border-accent"
                    >
                      <option value="private">Private (Recommended)</option>
                      <option value="unlisted">Unlisted (Link only)</option>
                      <option value="public">Public (Instant release)</option>
                    </select>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Initial visibility applied to automated uploads.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg border border-edge bg-navy/40 space-y-2">
                    <label className="font-semibold text-fg block">Scheduled Release Time</label>
                    <input
                      type="time"
                      value={agentPublishTime}
                      onChange={(e) => setAgentPublishTime(e.target.value)}
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 text-xs text-fg font-mono focus:outline-none focus:border-accent"
                    />
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Daily time for scheduled public video releases.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg border border-edge bg-navy/40 space-y-2">
                    <label className="font-semibold text-fg block">Pre-Publish Lead Time</label>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="number"
                        min="20"
                        max="1440"
                        step="5"
                        value={agentLeadTimeMin}
                        onChange={(e) => setAgentLeadTimeMin(Math.max(20, parseInt(e.target.value) || 20))}
                        className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 text-xs text-fg font-mono focus:outline-none focus:border-accent"
                      />
                      <span className="text-fg-faint text-[11px]">min</span>
                    </div>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Min 20m for YouTube HD/4K processing before live.
                    </p>
                  </div>
                </div>
              </Card>

              {/* Info Card Trigger (Replaces the two old static bottom cards) */}
              <div className="p-3.5 rounded-xl border border-accent/40 bg-accent/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center text-info font-bold text-xs shrink-0">
                    i
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-fg block">
                      Google Cloud Setup Guide & Publishing Policies
                    </span>
                    <span className="text-[11px] text-fg-dim">
                      Step-by-step console setup, OAuth scope, quota limits, and synthetic media policies.
                    </span>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowInfoModal(true)}
                  className="text-xs shrink-0 flex items-center gap-1.5 border-accent/60 hover:bg-accent/40"
                >
                  <span className="w-4 h-4 rounded-full bg-accent/20 border border-accent flex items-center justify-center text-[10px] text-info font-bold">
                    i
                  </span>
                  Open Setup Guide & Policies
                </Button>
              </div>

              {/* Info Dialog Modal */}
              {showInfoModal && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
                  <div className="bg-navy border border-edge rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-y-auto flex flex-col">
                    {/* Header */}
                    <div className="flex items-center justify-between px-6 py-4 border-b border-edge shrink-0">
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center text-info font-bold text-xs">
                          i
                        </div>
                        <h4 className="text-sm font-bold text-fg">
                          YouTube Publishing Setup Guide & Policies
                        </h4>
                      </div>
                      <button
                        onClick={() => setShowInfoModal(false)}
                        className="text-fg-dim hover:text-fg text-sm p-1 rounded hover:bg-flat"
                        title="Close guide"
                      >
                        ✕
                      </button>
                    </div>

                    {/* Body */}
                    <div className="p-6 space-y-6">
                      {/* Section 1: Google Cloud Console Setup */}
                      <div className="space-y-3">
                        <span className="text-xs font-bold uppercase tracking-wider text-fg block">
                          Google Cloud Console Setup (One-Time)
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1.5">
                            <div className="flex items-center gap-2 text-fg font-semibold">
                              <span className="w-5 h-5 rounded-full bg-flat text-info text-[10px] font-bold flex items-center justify-center">1</span>
                              Enable YouTube API
                            </div>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              In Google Cloud Console, open <strong>APIs & Services &gt; Library</strong>, search for <strong>YouTube Data API v3</strong>, and click <strong>Enable</strong>.
                            </p>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1.5">
                            <div className="flex items-center gap-2 text-fg font-semibold">
                              <span className="w-5 h-5 rounded-full bg-flat text-info text-[10px] font-bold flex items-center justify-center">2</span>
                              Consent Screen & Scope
                            </div>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              Set User Type to <strong>External</strong>. Under Scopes, add:
                            </p>
                            <code className="block break-all bg-navy border border-edge px-2 py-1 rounded text-[10px] font-mono text-info">
                              https://www.googleapis.com/auth/youtube.upload
                            </code>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1.5">
                            <div className="flex items-center gap-2 text-fg font-semibold">
                              <span className="w-5 h-5 rounded-full bg-flat text-info text-[10px] font-bold flex items-center justify-center">3</span>
                              Add Test User (Fix 403 access_denied)
                            </div>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              Under <strong>OAuth consent screen &gt; Test users</strong>, click <strong>+ Add Users</strong> and enter the exact Google/Gmail address of your channel. In browser sign-in, click <em>Advanced &gt; Go to PanelFlow Studio (unsafe)</em> to authorize.
                            </p>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1.5">
                            <div className="flex items-center gap-2 text-fg font-semibold">
                              <span className="w-5 h-5 rounded-full bg-flat text-info text-[10px] font-bold flex items-center justify-center">4</span>
                              Download Desktop JSON
                            </div>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              Go to <strong>Credentials &gt; Create Credentials &gt; OAuth client ID</strong>. Select Application Type <strong>Desktop app</strong>, download the JSON, and upload it in PanelFlow.
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* Section 2: Policies & Security */}
                      <div className="space-y-3">
                        <span className="text-xs font-bold uppercase tracking-wider text-fg block">
                          PanelFlow Publishing Safety & Policies
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1">
                            <span className="font-semibold text-fg block">Private by Default</span>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              All video uploads default to <code>private</code> status. Transitioning to public requires explicit confirmation or an automated scheduled release slot to prevent accidental publishing.
                            </p>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1">
                            <span className="font-semibold text-fg block">AI Synthetic Media Disclosure</span>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              All video uploads automatically declare <code>containsSyntheticMedia: true</code> in compliance with YouTube community guidelines for AI-generated content.
                            </p>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1">
                            <span className="font-semibold text-fg block">Encoded Credential Security</span>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              Client secrets and refresh tokens are encoded (<code>enc:v1:&lt;base64&gt;</code>) and stored exclusively in your local app data config directory. Secrets are never logged or exposed via API.
                            </p>
                          </div>

                          <div className="p-3.5 rounded-xl border border-edge bg-ink/60 space-y-1">
                            <span className="font-semibold text-fg block">API Quota Management</span>
                            <p className="text-[11px] text-fg-dim leading-relaxed">
                              Standard YouTube Data API quota provides 10,000 units/day. Each video upload uses ~1,600 units, allowing ~6 full video uploads per calendar day before quota reset.
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="px-6 py-3 border-t border-edge flex justify-end shrink-0">
                      <Button variant="secondary" size="sm" onClick={() => setShowInfoModal(false)}>
                        Close Guide
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "cloud_llm" && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 rounded-xl border border-edge bg-ink p-1" role="tablist" aria-label="Provider tools">
                <button
                  type="button"
                  role="tab"
                  aria-selected={cloudSectionTab === "configuration"}
                  onClick={() => setCloudSectionTab("configuration")}
                  className={`rounded-lg px-4 py-2 text-xs font-bold transition-colors ${cloudSectionTab === "configuration" ? "bg-accent text-white" : "text-fg-dim hover:bg-navy hover:text-fg"}`}
                >
                  Configuration
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={cloudSectionTab === "chat"}
                  onClick={() => setCloudSectionTab("chat")}
                  className={`rounded-lg px-4 py-2 text-xs font-bold transition-colors ${cloudSectionTab === "chat" ? "bg-accent text-white" : "text-fg-dim hover:bg-navy hover:text-fg"}`}
                >
                  Test chat
                </button>
              </div>

              {cloudSectionTab === "configuration" ? (
                <>
              <div className="grid grid-cols-3 gap-2" aria-label="Provider setup progress">
                {[
                  ["1", "Connection", Boolean(cloudEndpointUrl)],
                  ["2", "Model test", Boolean(cloudTestResult?.connected && cloudTestResult?.model_verified)],
                  ["3", "Activated", Boolean(cloudConfig?.is_active && cloudConfig?.provider_type === cloudProviderType)],
                ].map(([step, label, complete]) => (
                  <div key={String(step)} className={`rounded-lg border px-3 py-2 ${complete ? "border-ok/40 bg-ok/20" : "border-edge bg-ink"}`}>
                    <span className={`mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${complete ? "bg-ok text-ink" : "bg-flat text-fg-dim"}`}>{complete ? "✓" : step}</span>
                    <span className={complete ? "text-xs font-semibold text-ok" : "text-xs font-semibold text-fg-dim"}>{label}</span>
                  </div>
                ))}
              </div>

              {/* Preset Selector Card */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div className="flex items-center justify-between border-b border-edge/80 pb-3">
                  <div className="flex items-center gap-2">
                    <Icons.Sparkles className="w-4 h-4 text-warn" />
                    <h3 className="text-sm font-bold text-fg">Choose a connection</h3>
                  </div>
                  <Badge variant={cloudTestResult?.connected ? "success" : cloudConfig?.is_active ? "warning" : "neutral"}>
                    {cloudTestResult?.connected ? "Verified now" : cloudConfig?.is_active ? "Saved, not verified" : "Setup needed"}
                  </Badge>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                  <button
                    type="button"
                    onClick={() => handleApplyPreset("openrouter")}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      cloudProviderType === "openrouter"
                        ? "border-accent bg-accent/20 shadow-sm shadow-accent/20"
                        : "border-edge bg-navy/60 hover:border-edge"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-fg">OpenRouter (Free)</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-ok/10 text-ok border border-ok/20">Free Models</span>
                    </div>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Llama 3.3 70B, Gemini 2.0 Flash, DeepSeek R1 with 0 cost.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleApplyPreset("groq")}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      cloudProviderType === "groq"
                        ? "border-info bg-info/20 shadow-sm shadow-info/20"
                        : "border-edge bg-navy/60 hover:border-edge"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-fg">Groq Cloud (Free)</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-info/10 text-info border border-info/20">Ultra-Fast</span>
                    </div>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Instant LPU inference on Llama 3.3 70B Versatile and Llama 3.1 8B.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleApplyPreset("freellmapi")}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      cloudProviderType === "freellmapi"
                        ? "border-ok bg-ok/20 shadow-sm shadow-ok/20"
                        : "border-edge bg-navy/60 hover:border-edge"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-fg">FreeLLMAPI</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-ok/10 text-ok border border-ok/20">Gateway</span>
                    </div>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Aggregates Gemini, Groq, Cerebras & Mistral via http://localhost:3001/v1.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleApplyPreset("custom")}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      cloudProviderType === "custom"
                        ? "border-accent bg-accent/20 shadow-sm shadow-accent/20"
                        : "border-edge bg-navy/60 hover:border-edge"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-fg">Custom OpenAI</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-flat text-fg-dim">Custom</span>
                    </div>
                    <p className="text-[11px] text-fg-dim leading-relaxed">
                      Any OpenAI endpoint (LM Studio, vLLM, DeepSeek, Mistral).
                    </p>
                  </button>
                </div>

                {/* Provider-specific setup guide */}
                <div className="p-3 bg-navy/80 rounded-xl border border-edge/80 text-xs text-fg-dim space-y-1">
                  <p className="font-semibold text-fg flex items-center gap-1.5">
                    <Icons.Info className="w-3.5 h-3.5" />
                    {cloudProviderType === "freellmapi" ? "FreeLLMAPI setup" : "What you need"}
                  </p>
                  <ul className="list-disc list-inside space-y-0.5 text-[11px] text-fg-dim pl-1">
                    {cloudProviderType === "openrouter" && (
                      <>
                        <li>Sign up at <span className="font-mono text-info">openrouter.ai</span> and generate a free API key under Account Settings.</li>
                        <li>Models with the <span className="font-mono text-ok">:free</span> tag (e.g. Llama 3.3 70B, Gemini 2.0 Flash) have zero usage charges.</li>
                      </>
                    )}
                    {cloudProviderType === "groq" && (
                      <>
                        <li>Sign up at <span className="font-mono text-info">console.groq.com</span> and generate a free API key.</li>
                        <li>Generous free daily rate limits for rapid screenplay and dialogue drafting.</li>
                      </>
                    )}
                    {cloudProviderType === "freellmapi" && (
                      <>
                        <li>Start the FreeLLMAPI gateway first. PanelFlow expects its OpenAI-compatible address at <span className="font-mono text-ok">http://localhost:3001/v1</span>.</li>
                        <li>Add at least one upstream provider key inside FreeLLMAPI, then copy the <span className="font-mono text-ok">freellmapi-…</span> unified key from its Keys page.</li>
                        <li>Enter the exact model exposed by the gateway, then use <strong className="text-fg">Test selected model</strong>. A green result means a real completion was returned.</li>
                      </>
                    )}
                    {cloudProviderType === "custom" && (
                      <>
                        <li>Point to any OpenAI-compatible base URL ending in <span className="font-mono text-info">/v1</span> (e.g. local LM Studio on port 1234 or remote server).</li>
                      </>
                    )}
                  </ul>
                </div>
              </Card>

              {/* Endpoint & Key Configuration Form */}
              <Card className="p-4 bg-ink border-edge space-y-3">
                <div>
                  <h4 className="text-sm font-bold text-fg">Connection details</h4>
                  <p className="text-[11px] text-fg-dim">Testing sends one short prompt to the selected model. Saving is enabled only after that succeeds.</p>
                </div>
                
                <div className="space-y-3 text-xs">
                  <div className="space-y-1">
                    <label className="text-fg-dim font-semibold">Endpoint Base URL (OpenAI /v1 format)</label>
                    <input
                      type="text"
                      value={cloudEndpointUrl}
                      onChange={(e) => { setCloudEndpointUrl(e.target.value); setCloudTestResult(null); }}
                      placeholder="https://openrouter.ai/api/v1"
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-fg-dim font-semibold">{cloudProviderType === "freellmapi" ? "FreeLLMAPI unified key" : "API secret key"}</label>
                      <button
                        type="button"
                        onClick={() => setCloudShowApiKey(!cloudShowApiKey)}
                        className="text-[11px] text-info hover:text-info"
                      >
                        {cloudShowApiKey ? "Hide Key" : "Show Key"}
                      </button>
                    </div>
                    <input
                      type={cloudShowApiKey ? "text" : "password"}
                      value={cloudApiKey}
                      onChange={(e) => { setCloudApiKey(e.target.value); setCloudTestResult(null); }}
                      placeholder={cloudProviderType === "freellmapi" ? "freellmapi-… (required)" : "Paste your provider key"}
                      className="w-full bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                    />
                    {cloudProviderType === "freellmapi" && !cloudApiKey && (
                      <p className="text-[11px] text-warn">Required. This gateway is running, but its API currently rejects requests without a unified key.</p>
                    )}
                  </div>

                  <div className="space-y-1">
                    <label className="text-fg-dim font-semibold">Model Name</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={cloudModelName}
                        onChange={(e) => { setCloudModelName(e.target.value); setCloudTestResult(null); }}
                        placeholder="meta-llama/llama-3.3-70b-instruct:free"
                        className="flex-1 bg-navy border border-edge rounded px-2.5 py-1.5 font-mono text-fg text-xs focus:outline-none focus:border-accent"
                      />
                      <select
                        onChange={(e) => {
                          if (e.target.value) { setCloudModelName(e.target.value); setCloudTestResult(null); }
                        }}
                        className="bg-navy border border-edge rounded px-2 py-1.5 text-fg text-xs focus:outline-none focus:border-accent cursor-pointer"
                        value=""
                      >
                        <option value="">Quick Presets...</option>
                        <option value="meta-llama/llama-3.3-70b-instruct:free">Llama 3.3 70B (Free)</option>
                        <option value="google/gemini-2.0-flash-exp:free">Gemini 2.0 Flash (Free)</option>
                        <option value="deepseek/deepseek-r1:free">DeepSeek R1 (Free)</option>
                        <option value="qwen/qwen-2.5-vl-72b-instruct:free">Qwen 2.5 VL 72B (Free Multimodal)</option>
                        <option value="llama-3.3-70b-versatile">Groq Llama 3.3 70B Versatile</option>
                        <option value="llama-3.1-8b-instant">Groq Llama 3.1 8B Instant</option>
                        <option value="auto">Automatic healthy route (FreeLLMAPI)</option>
                        <option value="gemini-3.8-flash">Gemini 3.8 Flash (FreeLLMAPI)</option>
                        <option value="cerebras/llama3.1-70b">Cerebras Llama 3.1 70B (FreeLLMAPI)</option>
                        <option value="mistralai/mistral-large">Mistral Large (FreeLLMAPI)</option>
                      </select>
                    </div>
                    {cloudTestResult?.models && cloudTestResult.models.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap pt-1.5">
                        <span className="text-[10px] text-fg-dim font-medium">Discovered from endpoint:</span>
                        {cloudTestResult.models.slice(0, 8).map((m) => (
                          <button
                            key={m}
                            type="button"
                            onClick={() => setCloudModelName(m)}
                            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                              cloudModelName === m
                                ? "bg-accent/30 text-info border-accent"
                                : "bg-navy text-fg-dim border-edge hover:text-fg hover:border-edge"
                            }`}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions & Test Result */}
                <div className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-edge/80">
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleTestCloudConnection}
                      disabled={cloudTesting || !cloudEndpointUrl || (cloudProviderType === "freellmapi" && !cloudApiKey)}
                      className="text-xs"
                    >
                      {cloudTesting ? (
                        <>
                          <span className="w-3 h-3 border-2 border-fg-faint/30 border-t-zinc-400 rounded-full animate-spin mr-1.5" />
                          Testing model...
                        </>
                      ) : (
                        <>
                          <Icons.Activity className="w-3.5 h-3.5 mr-1.5 text-info" />
                          Test selected model
                        </>
                      )}
                    </Button>

                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleSaveCloudConfig}
                      disabled={cloudSaving || !cloudTestResult?.connected || !cloudTestResult?.model_verified}
                      className="text-xs"
                    >
                    {cloudSaving ? "Activating..." : "Save, activate & use as default"}
                    </Button>
                  </div>

                </div>

                {cloudTestResult && (
                  <div role="status" className={`rounded-xl border p-3 ${cloudTestResult.connected ? "border-ok/70 bg-ok/25" : "border-bad/70 bg-bad/20"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className={`text-sm font-bold ${cloudTestResult.connected ? "text-ok" : "text-bad"}`}>
                          {cloudTestResult.connected ? "Selected model responded" : "Connection test failed"}
                        </p>
                        <p className="mt-1 text-[11px] text-fg-dim">
                          {cloudTestResult.connected
                            ? `${cloudTestResult.models_count} models discovered · ${cloudTestResult.latency_ms} ms · response: ${cloudTestResult.response_preview || "received"}`
                            : cloudTestResult.error || "The endpoint did not return a usable response."}
                        </p>
                      </div>
                      <Badge variant={cloudTestResult.connected ? "success" : "danger"}>{cloudTestResult.connected ? "Working" : "Needs attention"}</Badge>
                    </div>
                    {!cloudTestResult.connected && cloudProviderType === "freellmapi" && (
                      <p className="mt-2 text-[11px] text-warn">Check that FreeLLMAPI is running on port 3001, the URL ends in /v1, and the selected model appears in its /v1/models response.</p>
                    )}
                  </div>
                )}

                {cloudSaveMessage && (
                  <p className="text-xs font-semibold text-ok pt-1">
                    {cloudSaveMessage}
                  </p>
                )}
              </Card>
                </>
              ) : (
                <Card className="p-0 bg-ink border-edge overflow-hidden">
                  <div className="flex items-center justify-between gap-3 border-b border-edge px-4 py-3">
                    <div>
                      <h3 className="text-sm font-bold text-fg">Provider test chat</h3>
                      <p className="text-[11px] text-fg-dim">Messages use the saved active provider and model, exactly as PanelFlow workflows do.</p>
                    </div>
                    <Badge variant={cloudConfig?.is_active ? "success" : "warning"}>
                      {cloudConfig?.is_active ? `${cloudConfig.provider_type} · ${cloudConfig.model_name}` : "No active provider"}
                    </Badge>
                  </div>

                  <div className="min-h-[280px] max-h-[48vh] overflow-y-auto space-y-3 p-4" aria-live="polite">
                    {chatMessages.length === 0 && (
                      <div className="flex min-h-[240px] items-center justify-center text-center">
                        <div className="max-w-sm">
                          <Icons.Sparkles className="mx-auto mb-3 h-6 w-6 text-info" />
                          <p className="text-sm font-semibold text-fg">Send a prompt through PanelFlow</p>
                          <p className="mt-1 text-xs text-fg-faint">Try “Summarize a dramatic manga scene in two sentences.”</p>
                        </div>
                      </div>
                    )}
                    {chatMessages.map((message, index) => (
                      <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[82%] rounded-xl px-3 py-2 text-xs leading-relaxed ${
                          message.role === "user"
                            ? "bg-accent text-white"
                            : message.role === "error"
                              ? "border border-bad/40 bg-bad/30 text-bad"
                              : "border border-edge bg-navy text-fg"
                        }`}>
                          <p className="whitespace-pre-wrap">{message.text}</p>
                          {message.meta && <p className="mt-2 text-[10px] text-fg-faint">{message.meta}</p>}
                        </div>
                      </div>
                    ))}
                    {chatSending && <p className="text-xs text-fg-faint">Waiting for the provider…</p>}
                  </div>

                  <div className="border-t border-edge p-3">
                    <div className="flex gap-2">
                      <textarea
                        value={chatPrompt}
                        onChange={(event) => setChatPrompt(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.shiftKey) {
                            event.preventDefault();
                            handleSendTestChat();
                          }
                        }}
                        rows={2}
                        placeholder="Type a test prompt. Enter to send, Shift+Enter for a new line."
                        className="min-h-[52px] flex-1 resize-none rounded-lg border border-edge bg-navy px-3 py-2 text-xs text-fg outline-none focus:border-accent"
                      />
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleSendTestChat}
                        disabled={chatSending || !chatPrompt.trim() || !cloudConfig?.is_active}
                      >
                        {chatSending ? "Sending…" : "Send"}
                      </Button>
                    </div>
                    {!cloudConfig?.is_active && (
                      <p className="mt-2 text-[11px] text-warn">Configure, test and activate a provider before using chat.</p>
                    )}
                  </div>
                </Card>
              )}
            </div>
          )}
        </div>


        {/* Footer */}
        <div className="shrink-0 px-4 sm:px-6 py-3 border-t border-edge flex items-center justify-between gap-3 bg-ink/50">
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

