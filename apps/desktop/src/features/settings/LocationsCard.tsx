import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { ToolLocation } from "@panelflow/api-client";
import { Button, Chip, ErrorState, GlassPanel, Input, Skeleton, useToast } from "@panelflow/ui-v2";
import { useEngine } from "../../app/providers";
import { useSettingsMutation } from "./settingsQueries";

const KEY = ["settings", "locations"];
const SOURCE_WORD = { saved: "Saved here", env: "From an environment variable", default: "Built-in default" } as const;

const Row: React.FC<{ item: ToolLocation; onSaved: (restart: boolean) => void }> = ({ item, onSaved }) => {
  const [draft, setDraft] = React.useState(item.value);
  React.useEffect(() => setDraft(item.value), [item.value]);
  const save = useSettingsMutation((value: string | null) => api.saveToolLocations({ [item.key]: value }), "Location saved", [KEY]);
  const run = async (value: string | null) => {
    await save.mutateAsync(value);
    if (item.restart) onSaved(true);
  };
  const dirty = draft.trim() !== item.value;
  const foundWord = item.kind === "url" ? ["Reachable", "Not reachable"] : ["Found", "Not found"];
  return (
    <div className="grid grid-cols-1 gap-2 rounded-ctl border border-edge p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-fg">{item.label}</p>
        <Chip tone={item.found ? "ok" : "bad"}>{item.found ? foundWord[0] : foundWord[1]}</Chip>
        <span className="text-xs text-fg-dim">{SOURCE_WORD[item.source]}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input className="min-w-0 flex-1 font-data" aria-label={item.label} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button size="sm" variant="primary" disabled={!dirty || !draft.trim()} loading={save.isPending} onClick={() => void run(draft.trim())}>Save</Button>
        <Button size="sm" variant="secondary" disabled={item.source !== "saved" || save.isPending} onClick={() => void run(null)}>Reset</Button>
      </div>
      <p className="text-xs text-fg-dim">{item.note} Default: <span className="font-data">{item.default}</span></p>
    </div>
  );
};

/** Where each local tool and model lives. Saved values beat environment variables, which beat the built-in defaults. */
export const LocationsCard: React.FC = () => {
  const { connected } = useEngine();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [restartNeeded, setRestartNeeded] = React.useState(false);
  const query = useQuery({ queryKey: KEY, queryFn: () => api.getToolLocations(), enabled: connected, retry: 1, refetchOnMount: "always" });
  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-sm font-semibold text-fg">Model &amp; tool locations</h2>
        <Button size="sm" variant="secondary" onClick={() => { void queryClient.invalidateQueries({ queryKey: KEY }); toast.show("Checked again", "ok"); }}>Check again</Button>
      </div>
      {restartNeeded && <p className="rounded-ctl border border-edge p-2 text-sm text-fg">Saved. Most locations are read when the engine starts, so use Restart engine above for the change to take effect.</p>}
      {query.isError ? (
        <ErrorState title="Couldn't load locations" description="Check that the engine is running, then try again." onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <Skeleton className="h-24" />
      ) : (
        query.data.items.map((item) => <Row key={item.key} item={item} onSaved={setRestartNeeded} />)
      )}
    </GlassPanel>
  );
};
