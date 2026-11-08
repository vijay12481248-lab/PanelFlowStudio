import React from "react";
import { api } from "@panelflow/api-client";
import type { CloudLLMConfig } from "@panelflow/shared-types";
import { Button, Field, GlassPanel, Input, Select } from "@panelflow/ui-v2";
import { validateEndpointUrl } from "./settingsModels";
import { settingsKeys, useSettingsMutation } from "./settingsQueries";

interface CloudDraft {
  provider_type: string;
  endpoint_url: string;
  model_name: string;
  /** Write-only: only what the owner types, never filled from the engine. */
  api_key: string;
}

const draftFrom = (config: CloudLLMConfig): CloudDraft => ({ provider_type: config.provider_type, endpoint_url: config.endpoint_url, model_name: config.model_name, api_key: "" });
const CLOUD_EXAMPLE = "Enter the endpoint address from your provider, for example https://openrouter.ai/api/v1.";

export const CloudProviderForm: React.FC<{ config: CloudLLMConfig }> = ({ config }) => {
  const [draft, setDraft] = React.useState<CloudDraft>(() => draftFrom(config));
  const [problem, setProblem] = React.useState<string | null>(null);
  const [connection, setConnection] = React.useState<string | null>(null);
  const saving = React.useRef(false); // synchronous guard against a fast double click
  const keyRef = React.useRef(""); // the key goes to the engine from here, never through the query or mutation cache
  keyRef.current = draft.api_key;

  const save = useSettingsMutation<Omit<CloudDraft, "api_key">>(
    (fields) => api.saveCloudLLMConfig({ ...fields, ...(keyRef.current ? { api_key: keyRef.current } : {}) }),
    "Cloud provider saved",
    [settingsKeys.cloudLLM, settingsKeys.globalLLM],
  );

  const dirty = draft.api_key !== "" || draft.provider_type !== config.provider_type || draft.endpoint_url !== config.endpoint_url || draft.model_name !== config.model_name;
  const edit = (patch: Partial<CloudDraft>) => { setProblem(null); setDraft({ ...draft, ...patch }); };

  const onSave = async () => {
    if (!dirty || saving.current) return;
    const invalid = validateEndpointUrl(draft.endpoint_url, CLOUD_EXAMPLE);
    if (invalid) { setProblem(invalid); return; }
    saving.current = true;
    setProblem(null);
    const { api_key: _key, ...fields } = draft; // the key is sent from keyRef, not stored as mutation variables
    try {
      await save.mutateAsync(fields);
      setDraft((current) => ({ ...current, api_key: "" }));
    } catch (error) {
      setProblem(`Couldn't save the setting. ${(error as Error).message || "Check the engine and try again."}`);
    } finally {
      saving.current = false;
    }
  };

  const test = async () => {
    setConnection("Testing the connection");
    try {
      const result = await api.testCloudLLMConnection({ endpoint_url: draft.endpoint_url, model_name: draft.model_name, ...(draft.api_key ? { api_key: draft.api_key } : {}) });
      setConnection(result.connected ? `Connected. ${result.models_count} models, ${result.latency_ms} ms.` : `Couldn't connect. ${result.error ?? "Check the address and the key."}`);
    } catch {
      setConnection("Couldn't connect. Check the address and the key.");
    }
  };

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-fg">Cloud provider</h2>
        <p className="text-sm text-fg-dim">Saving a cloud provider does not switch any job to it. Choose it under Routing when you want to use it.</p>
      </div>
      <Field label="Provider type">
        <Select value={draft.provider_type} onChange={(event) => edit({ provider_type: event.target.value })}>
          <option value="openrouter">OpenRouter</option>
          <option value="groq">Groq</option>
          <option value="custom_openai">Custom, OpenAI-compatible</option>
        </Select>
      </Field>
      <Field label="Endpoint address">
        <Input value={draft.endpoint_url} onChange={(event) => edit({ endpoint_url: event.target.value })} />
      </Field>
      <Field label="Model">
        <Input value={draft.model_name} onChange={(event) => edit({ model_name: event.target.value })} />
      </Field>
      <Field label="API key" hint={config.has_api_key ? `Saved: ${config.masked_api_key ?? "stored"}. Type a new key to replace it.` : "Paste the key from your provider's dashboard."}>
        <Input type="password" autoComplete="off" value={draft.api_key} onChange={(event) => edit({ api_key: event.target.value })} />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={() => void test()}>Test connection</Button>
        {connection && <p role="status" className="text-sm text-fg-dim">{connection}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" loading={save.isPending} disabled={!dirty} onClick={() => void onSave()}>Save cloud provider</Button>
        <Button variant="ghost" disabled={!dirty} onClick={() => { setProblem(null); setDraft(draftFrom(config)); }}>Discard</Button>
        {problem && <p role="alert" className="text-sm text-bad">{problem}</p>}
      </div>
    </GlassPanel>
  );
};
