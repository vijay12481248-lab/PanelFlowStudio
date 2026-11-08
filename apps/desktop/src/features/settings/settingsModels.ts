import type { FlowOverrideConfig, GlobalLLMSettings, LLMProviderInfo, OllamaConfig, OllamaModelCapability, ProviderHealth, SaveGlobalLLMSettingsRequest, SystemResourcesResponse } from "@panelflow/shared-types";

export interface Gauge {
  id: "gpu" | "ram";
  label: string;
  usedLabel: string;
  percent: number;
  tone: "ok" | "warn" | "bad";
}

const gb = (megabytes: number) => (megabytes / 1024).toFixed(1);
const toneFor = (percent: number): Gauge["tone"] => (percent >= 95 ? "bad" : percent >= 85 ? "warn" : "ok");

export function resourceGauges(resources: SystemResourcesResponse): Gauge[] {
  const gauges: Gauge[] = [];
  const { gpu, ram } = resources;
  if (gpu.available) {
    const percent = Math.round((gpu.used_mb / gpu.total_mb) * 100);
    gauges.push({ id: "gpu", label: "GPU memory", usedLabel: `${gb(gpu.used_mb)} of ${gb(gpu.total_mb)} GB`, percent, tone: toneFor(percent) });
  }
  const percent = Math.round(ram.used_percent);
  gauges.push({ id: "ram", label: "RAM", usedLabel: `${(ram.total_gb - ram.available_gb).toFixed(1)} of ${ram.total_gb.toFixed(1)} GB`, percent, tone: toneFor(percent) });
  return gauges;
}

export interface ToolRow {
  id: string;
  label: string;
  state: "ready" | "missing" | "problem";
  detail: string;
}

const STATUS_WORD: Record<string, string> = {
  HEALTHY: "Healthy", READY: "Ready", DEGRADED: "Degraded", OFFLINE: "Offline", STOPPED: "Stopped", NOT_RUNNING: "Not running",
  MISSING: "Missing", UNSUPPORTED: "Not supported", ERROR: "Error", BROWSER_RUNTIME_MISSING: "Browser runtime missing",
};
const statusWord = (status: string) => STATUS_WORD[status] ?? status.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());

export function toolRows(input: { ffmpeg?: { found: boolean; version: string | null }; providers?: ProviderHealth[] }): ToolRow[] {
  const rows: ToolRow[] = [];
  if (input.ffmpeg) {
    rows.push({
      id: "ffmpeg",
      label: "FFmpeg",
      state: input.ffmpeg.found ? "ready" : "missing",
      detail: input.ffmpeg.found ? `Found${input.ffmpeg.version ? `, version ${input.ffmpeg.version}` : ""}` : "Not found",
    });
  }
  for (const provider of input.providers ?? []) {
    const state: ToolRow["state"] = provider.status === "HEALTHY" || provider.status === "READY" ? "ready" : provider.status === "DEGRADED" ? "problem" : "missing";
    rows.push({ id: provider.id, label: provider.name, state, detail: provider.details ? `${statusWord(provider.status)}. ${provider.details}` : statusWord(provider.status) });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Ollama (Models section)
// ---------------------------------------------------------------------------

export interface OllamaDraft {
  endpoint_url: string;
  is_remote: boolean;
  vision_model: string;
  reasoning_model: string;
  narration_model: string;
  num_ctx: number;
  concurrency_mode: "AUTO" | "MANUAL";
  max_gpu_concurrency: number;
  /** Write-only: never filled from the engine, only from what the owner types. */
  auth_token: string;
}

const OLLAMA_FIELDS = ["endpoint_url", "is_remote", "vision_model", "reasoning_model", "narration_model", "num_ctx", "concurrency_mode", "max_gpu_concurrency"] as const;

export function draftFromConfig(config: OllamaConfig): OllamaDraft {
  return {
    endpoint_url: config.endpoint_url, is_remote: config.is_remote, vision_model: config.vision_model, reasoning_model: config.reasoning_model,
    narration_model: config.narration_model, num_ctx: config.num_ctx, concurrency_mode: config.concurrency_mode, max_gpu_concurrency: config.max_gpu_concurrency,
    auth_token: "",
  };
}

/** Only the fields that differ from what is saved; the token only when one was typed. */
export function changedOllamaFields(saved: OllamaConfig, draft: OllamaDraft): Partial<OllamaConfig> & { auth_token?: string } {
  const changed: Record<string, unknown> = {};
  for (const key of OLLAMA_FIELDS) if (draft[key] !== saved[key]) changed[key] = draft[key];
  if (draft.auth_token) changed.auth_token = draft.auth_token;
  return changed as Partial<OllamaConfig> & { auth_token?: string };
}

const EXAMPLE_ADDRESS = "Enter the address of your Ollama server, for example http://127.0.0.1:11434.";

export function validateEndpointUrl(value: string, example: string = EXAMPLE_ADDRESS): string | null {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    return example;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return "Use an http or https address.";
  if (url.username || url.password) return "Remove the username and password from the address and use the token field.";
  return null;
}

export function modelsForRole(models: OllamaModelCapability[], role: "vision" | "reasoning" | "narration"): OllamaModelCapability[] {
  if (role === "vision") return models.filter((m) => m.supports_vision);
  return models.filter((m) => m.capabilities.length === 0 || m.capabilities.includes("completion"));
}

export function pullPercent(status: { completed_bytes: number; total_bytes: number; percent?: number }): number {
  const raw = status.total_bytes > 0 ? (status.completed_bytes / status.total_bytes) * 100 : status.percent ?? 0;
  return Math.max(0, Math.min(100, Math.round(raw)));
}

// ---------------------------------------------------------------------------
// Providers and routing
// ---------------------------------------------------------------------------

export const WORKFLOWS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "story_narration", label: "Story narration" },
  { key: "story_script", label: "Script writing" },
  { key: "character_analysis", label: "Character profiling" },
  { key: "vision_inspection", label: "Panel and OCR inspection" },
];

export interface RoutingDraft {
  provider: string;
  model: string;
  overrides: Record<string, FlowOverrideConfig>;
}

export function routingFromSettings(settings: GlobalLLMSettings): RoutingDraft {
  return { provider: settings.global_default_provider, model: settings.global_default_model, overrides: { ...settings.flow_overrides } };
}

/** "Use the default" rows are not overrides, and a missing model is the same as an empty one. */
function effectiveOverrides(overrides: Record<string, FlowOverrideConfig>): Record<string, FlowOverrideConfig> {
  return Object.fromEntries(
    Object.entries(overrides)
      .filter(([, value]) => value.provider_id !== "global")
      .map(([key, value]) => [key, value.model_name ? { provider_id: value.provider_id, model_name: value.model_name } : { provider_id: value.provider_id }])
      .sort(([a], [b]) => (a as string).localeCompare(b as string)),
  );
}

export function routingChanged(saved: GlobalLLMSettings, draft: RoutingDraft): boolean {
  return (
    saved.global_default_provider !== draft.provider ||
    saved.global_default_model !== draft.model ||
    JSON.stringify(effectiveOverrides(saved.flow_overrides)) !== JSON.stringify(effectiveOverrides(draft.overrides))
  );
}

export function routingToRequest(draft: RoutingDraft): SaveGlobalLLMSettingsRequest {
  return { global_default_provider: draft.provider, global_default_model: draft.model, flow_overrides: effectiveOverrides(draft.overrides) };
}

export interface ProviderOption {
  id: string;
  name: string;
  local: boolean;
  ready: boolean;
}

export function providerOptions(settings: GlobalLLMSettings, info: LLMProviderInfo[]): ProviderOption[] {
  const options: ProviderOption[] = (settings.providers ?? []).map((p) => ({ id: p.id, name: p.name, local: p.type === "local", ready: p.is_configured && p.is_healthy }));
  for (const provider of info) {
    if (!options.some((o) => o.id === provider.provider_id)) {
      options.push({ id: provider.provider_id, name: provider.provider_name, local: provider.is_local, ready: provider.is_healthy });
    }
  }
  return options;
}

/** A sentence for the owner when any job would send text to a cloud provider; null while everything stays local. */
export function localFirstWarning(draft: RoutingDraft, options: ProviderOption[]): string | null {
  const used = [draft.provider, ...Object.values(draft.overrides).map((o) => o.provider_id)].filter((id) => id !== "global");
  const cloud = [...new Set(used)].flatMap((id) => {
    const option = options.find((o) => o.id === id);
    return option?.local ? [] : [option?.name ?? id];
  });
  if (cloud.length === 0) return null;
  const names = cloud.length === 1 ? cloud[0] : `${cloud.slice(0, -1).join(", ")} and ${cloud.at(-1)}`;
  return `Cloud routing sends your text to ${names}. Keep Local Ollama as the default unless you mean to.`;
}
