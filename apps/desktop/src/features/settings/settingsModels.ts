import type { ProviderHealth, SystemResourcesResponse } from "@panelflow/shared-types";

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
