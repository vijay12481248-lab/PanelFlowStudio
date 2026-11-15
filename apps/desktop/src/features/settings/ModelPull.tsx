import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { Button, Field, Input, Progress } from "@panelflow/ui-v2";
import { useEngine } from "../../app/providers";
import { pullPercent } from "./settingsModels";
import { settingsKeys, useSettingsMutation } from "./settingsQueries";

const POLL_MS = 1500;
const PULL_KEY = ["settings", "ollamaPull"] as const;

/** Downloads a model with Ollama. One pull at a time; the progress poll runs only while this section is mounted and a pull is active. */
export const ModelPull: React.FC = () => {
  const { connected } = useEngine();
  const [name, setName] = React.useState("");
  const watching = React.useRef(false);
  const starting = React.useRef(false); // synchronous guard against a fast double click

  const status = useQuery({
    queryKey: PULL_KEY,
    queryFn: () => api.getOllamaPullStatus(),
    enabled: connected,
    retry: false,
    refetchInterval: (query) => {
      const state = query.state.data?.status;
      if (state === "COMPLETED" || state === "FAILED") watching.current = false;
      return watching.current || state === "PULLING" ? POLL_MS : false;
    },
  });
  const pull = useSettingsMutation((model: string) => api.pullOllamaModel(model), "Download started", [settingsKeys.ollamaModels]);

  const data = status.data;
  const pulling = data?.status === "PULLING";
  const start = async () => {
    const model = name.trim();
    if (!model || starting.current || pulling) return;
    starting.current = true;
    watching.current = true;
    try {
      await pull.mutateAsync(model);
      await status.refetch();
    } catch {
      watching.current = false;
    } finally {
      starting.current = false;
    }
  };

  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Field label="Model to download" hint="For example qwen3.5:9b. Downloads can be several gigabytes.">
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="qwen3.5:9b" />
          </Field>
        </div>
        <Button variant="secondary" loading={pull.isPending} disabled={!name.trim() || pulling} onClick={() => void start()}>Pull model</Button>
      </div>
      {pulling && data && (
        <div className="grid grid-cols-1 gap-1.5">
          <p className="text-sm text-fg-dim">{`Downloading ${data.model_name}: ${data.status_text}`}</p>
          <Progress value={pullPercent(data)} label="Download progress" />
        </div>
      )}
      {data?.status === "FAILED" && <p role="alert" className="text-sm text-bad">{`The download of ${data.model_name} failed. ${data.error_message ?? "Check that Ollama is running and the model name is right."}`}</p>}
      {data?.status === "COMPLETED" && <p className="text-sm text-ok">{`${data.model_name} is downloaded.`}</p>}
    </div>
  );
};
