import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { YouTubeStatus } from "@panelflow/api-client";
import { Button, Chip, ErrorState, GlassPanel, Skeleton } from "@panelflow/ui-v2";
import { useEngine } from "../../app/providers";

// Loaded only when opened: the existing settings window is large, and it is replaced in M4b.
const LegacySettingsWindow = React.lazy(async () => ({ default: (await import("../../components/ProviderHealthModal")).ProviderHealthModal }));

export interface YouTubeSectionProps {
  /** Injected in tests. */
  ModalComponent?: React.ComponentType<{ open: boolean; onClose: () => void }>;
}

function describe(status: YouTubeStatus): { word: string; tone: "ok" | "warn" | "neutral" } {
  if (status.pending) return { word: "Waiting for you to finish signing in", tone: "warn" };
  if (status.connected) return { word: "Connected", tone: "ok" };
  if (status.configured) return { word: "Not connected", tone: "warn" };
  return { word: "Not set up", tone: "neutral" };
}

/**
 * Channel setup stays in the existing settings window until the new multi-channel settings land (M4b).
 * The status is read without a channel id so it works with both the committed and the in-progress API client.
 */
export const YouTubeSection: React.FC<YouTubeSectionProps> = ({ ModalComponent = LegacySettingsWindow }) => {
  const { connected: engineUp } = useEngine();
  const status = useQuery({ queryKey: ["settings", "youtube"], queryFn: () => api.youtubeStatus(), enabled: engineUp, retry: 1 });
  const [open, setOpen] = React.useState(false);
  const summary = status.data ? describe(status.data) : null;

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
      <h2 className="font-display text-sm font-semibold text-fg">YouTube</h2>
      {status.isError ? (
        <ErrorState title="Couldn't read the YouTube connection" description="Check that the engine is running, then try again." onRetry={() => void status.refetch()} />
      ) : !summary ? (
        <Skeleton className="h-10" />
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <Chip tone={summary.tone}>{summary.word}</Chip>
          {status.data?.error && <p className="text-sm text-warn">{status.data.error}</p>}
        </div>
      )}
      <p className="text-sm text-fg-dim">Uploads are private by default. Nothing on this page publishes or schedules a video.</p>
      <p className="text-sm text-fg-dim">Channel setup and uploads live in the existing YouTube settings until the new ones are ready. Open them, then choose the YouTube tab.</p>
      <div><Button variant="primary" onClick={() => setOpen(true)}>Open YouTube settings</Button></div>
      {open && (
        <React.Suspense fallback={null}>
          <ModalComponent open onClose={() => setOpen(false)} />
        </React.Suspense>
      )}
    </GlassPanel>
  );
};
