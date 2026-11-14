import React from "react";
import { api } from "@panelflow/api-client";
import { Button, Chip, EngineStatus, ErrorState, GlassPanel, Progress, Skeleton } from "@panelflow/ui-v2";
import { useEngine } from "../../app/providers";
import { useResources } from "../data/queries";
import { resourceGauges, toolRows, type ToolRow } from "./settingsModels";
import { settingsKeys, useFfmpeg, usePlaywrightStatus, useProviderHealth, useSettingsMutation } from "./settingsQueries";

const STATE_CHIP: Record<ToolRow["state"], { word: string; tone: "ok" | "warn" | "bad" }> = {
  ready: { word: "Ready", tone: "ok" },
  problem: { word: "Needs attention", tone: "warn" },
  missing: { word: "Missing", tone: "bad" },
};

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
    <h2 className="font-display text-sm font-semibold text-fg">{title}</h2>
    {children}
  </GlassPanel>
);

const RowShell: React.FC<{ label: string; detail?: string; chip?: React.ReactNode; action?: React.ReactNode }> = ({ label, detail, chip, action }) => (
  <div className="flex items-center gap-3 rounded-ctl border border-edge p-3">
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-medium text-fg">{label}</p>
      {detail && <p className="text-xs text-fg-dim">{detail}</p>}
    </div>
    {chip}
    {action}
  </div>
);

export const EngineSection: React.FC = () => {
  const engine = useEngine();
  const resources = useResources();
  const health = useProviderHealth();
  const ffmpeg = useFfmpeg();
  const playwright = usePlaywrightStatus();

  const install = useSettingsMutation(() => api.installPlaywrightBrowsers(), "Chromium install started", [settingsKeys.playwright, settingsKeys.providerHealth]);
  const provision = useSettingsMutation(() => api.provisionVoices(), "Voices ready", []);
  const [voiceResult, setVoiceResult] = React.useState<string | null>(null);
  const busy = React.useRef({ install: false, provision: false, restart: false }); // synchronous guards against a fast double click

  const once = async (key: keyof typeof busy.current, action: () => Promise<unknown>) => {
    if (busy.current[key]) return;
    busy.current[key] = true;
    try { await action(); } finally { busy.current[key] = false; }
  };

  const gauges = resources.data ? resourceGauges(resources.data) : [];
  const rows = toolRows({ ffmpeg: ffmpeg.data, providers: health.data?.providers });
  const chromium = health.data?.providers.find((p) => p.id === "playwright");
  const chromiumMissing = Boolean(chromium) && chromium!.status !== "HEALTHY" && chromium!.status !== "READY";
  const installing = playwright.data?.status === "RUNNING";

  return (
    <div className="grid grid-cols-1 gap-5">
      <Card title="Engine">
        <div className="flex flex-wrap items-center gap-3">
          <EngineStatus connected={engine.connected} version={engine.connected ? `v${engine.version}` : undefined} />
          <Button size="sm" variant="secondary" loading={engine.restarting} disabled={!engine.connected || engine.retrying} onClick={() => void once("restart", () => engine.restart())}>
            Restart engine
          </Button>
        </div>
      </Card>

      <Card title="Resources">
        {resources.isError ? (
          <ErrorState title="Couldn't load resource use" description="Check that the engine is running, then try again." onRetry={() => void resources.refetch()} />
        ) : !resources.data ? (
          <Skeleton className="h-12" />
        ) : (
          gauges.map((gauge) => (
            <div key={gauge.id} className="grid grid-cols-1 gap-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-fg">{gauge.label}</span>
                <span className="font-data text-xs text-fg-dim">{`${gauge.usedLabel}, ${gauge.percent}%`}{gauge.tone !== "ok" ? (gauge.tone === "bad" ? " (almost full)" : " (getting full)") : ""}</span>
              </div>
              <Progress value={gauge.percent} label={`${gauge.label} in use`} />
            </div>
          ))
        )}
        {resources.data && !resources.data.gpu.available && <p className="text-sm text-fg-dim">No GPU was found, so GPU jobs cannot run on this PC.</p>}
      </Card>

      <Card title="Tools">
        {health.isError && <ErrorState title="Couldn't load tool status" description="Check that the engine is running, then try again." onRetry={() => void health.refetch()} />}
        {ffmpeg.isError && !ffmpeg.data && <p className="text-sm text-fg-dim">Couldn't check FFmpeg.</p>}
        {!health.isError && !health.data && !ffmpeg.data && <Skeleton className="h-12" />}
        {rows.map((row, index) => {
          const chip = STATE_CHIP[row.state];
          const isChromium = row.id === "playwright" && chromiumMissing;
          return (
            <RowShell
              key={`${index}-${row.id}`}
              label={row.label}
              detail={isChromium && installing ? `Installing. ${playwright.data?.log_lines.at(-1) ?? ""}`.trim() : row.detail}
              chip={<Chip tone={chip.tone}>{chip.word}</Chip>}
              action={isChromium ? <Button size="sm" variant="primary" loading={installing || install.isPending} onClick={() => void once("install", () => install.mutateAsync(undefined))}>Install Chromium</Button> : undefined}
            />
          );
        })}
      </Card>

      <Card title="Voices">
        <RowShell
          label="Default voices"
          detail={voiceResult ?? "Copies the built-in narration voices into your workspace."}
          action={
            <Button size="sm" variant="secondary" loading={provision.isPending} onClick={() => void once("provision", async () => {
              const result = await provision.mutateAsync(undefined);
              setVoiceResult(`${(result as { copied_count: number }).copied_count} voices copied`);
            })}>
              Provision voices
            </Button>
          }
        />
      </Card>
    </div>
  );
};
