import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { GlobalLLMSettings, ProviderCatalogItem } from "@panelflow/shared-types";
import { Icons, Badge } from "@panelflow/ui";

export interface GlobalLLMSelectorProps {
  flowId?: string; // e.g., "story_narration", "story_script", "character_analysis"
  selectedProviderId: string; // "global" | "ollama" | "freellmapi" | "openrouter" | "groq" | "custom"
  selectedModel: string;
  onChange: (providerId: string, model: string) => void;
  onOpenSettings?: () => void;
  className?: string;
  compact?: boolean;
}

export const GlobalLLMSelector: React.FC<GlobalLLMSelectorProps> = ({
  flowId = "story_narration",
  selectedProviderId,
  selectedModel,
  onChange,
  onOpenSettings,
  className = "",
  compact = false,
}) => {
  const [globalSettings, setGlobalSettings] = useState<GlobalLLMSettings | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;
    const fetchSettings = async () => {
      try {
        const res = await api.getGlobalLLMSettings();
        if (isMounted && res) {
          setGlobalSettings(res);
        }
      } catch (err) {
        console.error("Failed to load global LLM settings:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchSettings();
    return () => {
      isMounted = false;
    };
  }, []);

  const providers: ProviderCatalogItem[] = globalSettings?.providers || [
    {
      id: "ollama",
      name: "Local Ollama",
      type: "local",
      is_configured: true,
      is_healthy: true,
      models: ["qwen3.5:9b", "qwen2.5:7b"],
      default_model: "qwen3.5:9b",
    },
    {
      id: "freellmapi",
      name: "FreeLLMAPI Gateway",
      type: "gateway",
      is_configured: false,
      is_healthy: false,
      models: ["auto"],
      default_model: "auto",
    },
    {
      id: "openrouter",
      name: "OpenRouter (Free)",
      type: "cloud",
      is_configured: false,
      is_healthy: false,
      models: ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"],
      default_model: "meta-llama/llama-3.3-70b-instruct:free",
    },
    {
      id: "groq",
      name: "Groq Cloud (Free)",
      type: "cloud",
      is_configured: false,
      is_healthy: false,
      models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
      default_model: "llama-3.3-70b-versatile",
    },
    {
      id: "custom",
      name: "Custom OpenAI",
      type: "custom",
      is_configured: false,
      is_healthy: false,
      models: ["default"],
      default_model: "default",
    },
  ];

  const globalDefaultProviderId = globalSettings?.global_default_provider || "ollama";
  const globalDefaultModel = globalSettings?.global_default_model || "qwen3.5:9b";
  const globalProviderObj = providers.find((p) => p.id === globalDefaultProviderId);

  // Flow-level configured override from backend
  const flowOverride = globalSettings?.flow_overrides?.[flowId];
  const effectiveFlowProvider = flowOverride?.provider_id || "global";

  // Determine active provider obj
  const activeProviderId =
    selectedProviderId === "global"
      ? (effectiveFlowProvider === "global" ? globalDefaultProviderId : effectiveFlowProvider)
      : selectedProviderId;

  const currentProviderObj = providers.find((p) => p.id === activeProviderId) || globalProviderObj;
  const availableModels = currentProviderObj?.models || [];

  const handleProviderChange = (newPid: string) => {
    if (newPid === "global") {
      onChange("global", "");
    } else {
      const targetProv = providers.find((p) => p.id === newPid);
      const defaultMod = targetProv?.default_model || targetProv?.models[0] || "default";
      onChange(newPid, defaultMod);
    }
  };

  const handleModelChange = (newModel: string) => {
    onChange(selectedProviderId, newModel);
  };

  const getProviderIcon = (pid: string) => {
    switch (pid) {
      case "ollama":
        return "🖥️";
      case "freellmapi":
        return "⚡";
      case "openrouter":
        return "☁️";
      case "groq":
        return "🚀";
      case "custom":
        return "💻";
      default:
        return "🌐";
    }
  };

  return (
    <div
      className={`inline-flex items-center gap-1.5 bg-zinc-950/80 border border-zinc-800 rounded-lg px-2 py-1 shadow-inner whitespace-nowrap shrink-0 ${className}`}
    >
      {/* Provider Selector */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-xs shrink-0" role="img" aria-label="provider-icon">
          {selectedProviderId === "global" ? "🌐" : getProviderIcon(selectedProviderId)}
        </span>
        <select
          value={selectedProviderId}
          onChange={(e) => handleProviderChange(e.target.value)}
          className="bg-transparent text-[11px] font-semibold text-zinc-200 focus:outline-none cursor-pointer border-r border-zinc-800/80 pr-1.5 mr-0.5 max-w-[130px] sm:max-w-[155px] truncate"
          title="Select active LLM Provider (Inherit Global Default or Choose Flow Override)"
        >
          <option value="global" className="bg-zinc-900 text-zinc-200">
            🌐 Global Default ({globalProviderObj?.name || globalDefaultProviderId})
          </option>
          {providers.map((p) => (
            <option key={p.id} value={p.id} className="bg-zinc-900 text-zinc-200">
              {getProviderIcon(p.id)} {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Model Selector */}
      <div className="flex items-center gap-1 shrink-0">
        <select
          value={selectedModel || (selectedProviderId === "global" ? "" : currentProviderObj?.default_model || "")}
          onChange={(e) => handleModelChange(e.target.value)}
          className="bg-transparent text-xs text-zinc-300 font-mono focus:outline-none cursor-pointer max-w-[110px] sm:max-w-[140px] truncate"
          title="Select LLM model for this operation"
        >
          {selectedProviderId === "global" && (
            <option value="" className="bg-zinc-900 text-zinc-400">
              Auto: {globalDefaultModel}
            </option>
          )}
          {availableModels.map((m) => (
            <option key={m} value={m} className="bg-zinc-900 text-zinc-200 font-mono">
              {m}
            </option>
          ))}
          {selectedModel && !availableModels.includes(selectedModel) && (
            <option value={selectedModel} className="bg-zinc-900 text-zinc-200 font-mono">
              {selectedModel}
            </option>
          )}
        </select>
      </div>

      {/* Status indicator */}
      <div className="flex items-center pl-0.5 shrink-0">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            currentProviderObj?.is_healthy ? "bg-emerald-400" : "bg-amber-400"
          }`}
          title={currentProviderObj?.is_healthy ? "Provider online & ready" : "Provider unverified or offline"}
        />
      </div>

      {/* Settings Action Button */}
      {onOpenSettings && (
        <button
          type="button"
          onClick={onOpenSettings}
          className="ml-0.5 p-1 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded transition-colors shrink-0"
          title="Configure Global LLM Routing & Provider Endpoints"
        >
          <Icons.Settings className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
};
