import React from "react";
import { api } from "@panelflow/api-client";
import type { OllamaConfig } from "@panelflow/shared-types";
import { Button, ErrorState, Field, GlassPanel, Input, Select, Skeleton, Switch } from "@panelflow/ui-v2";
import { ModelList } from "./ModelList";
import { ModelPull } from "./ModelPull";
import { changedOllamaFields, draftFromConfig, modelsForRole, validateEndpointUrl, type OllamaDraft } from "./settingsModels";
import { settingsKeys, useOllamaConfig, useOllamaModels, useSettingsMutation } from "./settingsQueries";

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
    <h2 className="font-display text-sm font-semibold text-fg">{title}</h2>
    {children}
  </GlassPanel>
);

const ROLES: Array<{ role: "vision" | "reasoning" | "narration"; field: "vision_model" | "reasoning_model" | "narration_model"; label: string; hint: string }> = [
  { role: "vision", field: "vision_model", label: "Vision model", hint: "Reads panels and describes characters." },
  { role: "reasoning", field: "reasoning_model", label: "Story reasoning model", hint: "Follows the plot across a chapter." },
  { role: "narration", field: "narration_model", label: "Narration model", hint: "Writes the spoken recap." },
];

export const ModelsSection: React.FC = () => {
  const config = useOllamaConfig();
  const models = useOllamaModels();
  const [draft, setDraft] = React.useState<OllamaDraft | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [connection, setConnection] = React.useState<string | null>(null);
  const saving = React.useRef(false); // synchronous guard against a fast double click
  const tokenRef = React.useRef(""); // the token goes to the engine from here, never through the query or mutation cache

  const saved = config.data;
  React.useEffect(() => { if (saved && draft === null) setDraft(draftFromConfig(saved)); }, [saved, draft]);
  tokenRef.current = draft?.auth_token ?? "";

  const save = useSettingsMutation<Partial<OllamaConfig>>(
    (fields) => api.saveOllamaConfig({ ...fields, ...(tokenRef.current ? { auth_token: tokenRef.current } : {}) }),
    "Model settings saved",
    [settingsKeys.ollamaConfig, settingsKeys.ollamaModels],
  );

  if (config.isError) {
    return <ErrorState title="Couldn't reach Ollama's settings" description="Check that the engine is running, then try again." onRetry={() => void config.refetch()} />;
  }
  if (!saved || !draft) return <Skeleton className="h-64" />;

  const changed = changedOllamaFields(saved, draft);
  const dirty = Object.keys(changed).length > 0;
  const set = <K extends keyof OllamaDraft>(key: K, value: OllamaDraft[K]) => { setProblem(null); setDraft({ ...draft, [key]: value }); };

  const onSave = async () => {
    if (!dirty || saving.current) return;
    if ("endpoint_url" in changed) {
      const error = validateEndpointUrl(draft.endpoint_url);
      if (error) { setProblem(error); return; }
    }
    saving.current = true;
    setProblem(null);
    const { auth_token: _token, ...fields } = changed; // the token is sent from tokenRef, not stored as mutation variables
    try {
      await save.mutateAsync(fields);
      setDraft((current) => (current ? { ...current, auth_token: "" } : current));
    } catch (error) {
      setProblem(`Couldn't save the setting. ${(error as Error).message || "Check the engine and try again."}`);
    } finally {
      saving.current = false;
    }
  };

  const testConnection = async () => {
    setConnection("Testing the connection");
    try {
      const result = await api.testOllamaConnection({ endpoint_url: draft.endpoint_url, is_remote: draft.is_remote, ...(draft.auth_token ? { auth_token: draft.auth_token } : {}) });
      setConnection(result?.connected ? "Connected" : `Couldn't connect. ${result?.message ?? result?.error ?? "Check the address and that Ollama is running."}`);
    } catch {
      setConnection("Couldn't connect. Check the address and that Ollama is running.");
    }
  };

  const installed = models.data?.models ?? [];
  return (
    <div className="grid grid-cols-1 gap-5">
      <Card title="Connection">
        <Field label="Server address" hint="Ollama runs on this PC by default.">
          <Input value={draft.endpoint_url} onChange={(event) => set("endpoint_url", event.target.value)} />
        </Field>
        <Switch checked={draft.is_remote} onCheckedChange={(value) => set("is_remote", value)} label="This is a remote server" />
        <Field label="Access token (optional)" hint={saved.has_auth_token ? "Saved in the system keychain. Type a new one to replace it." : "Only needed for a remote server that asks for one."}>
          <Input type="password" autoComplete="off" value={draft.auth_token} onChange={(event) => set("auth_token", event.target.value)} />
        </Field>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={() => void testConnection()}>Test connection</Button>
          {connection && <p role="status" className="text-sm text-fg-dim">{connection}</p>}
        </div>
      </Card>

      <Card title="Models for each job">
        {models.isError && <p className="text-sm text-warn">Couldn't load the installed models, so only the saved choices are listed.</p>}
        {ROLES.map(({ role, field, label, hint }) => {
          const options = modelsForRole(installed, role);
          const current = draft[field];
          return (
            <Field key={role} label={label} hint={hint}>
              <Select value={current} onChange={(event) => set(field, event.target.value)}>
                {!options.some((m) => m.name === current) && <option value={current}>{`${current} (not installed)`}</option>}
                {options.map((m) => <option key={m.name} value={m.name}>{`${m.name}, ${m.parameter_size} ${m.quantization_level}`.trim()}</option>)}
              </Select>
            </Field>
          );
        })}
      </Card>

      <Card title="GPU use">
        <Field label="Admission mode" hint="Automatic starts as many GPU jobs as free memory allows.">
          <Select value={draft.concurrency_mode} onChange={(event) => set("concurrency_mode", event.target.value as OllamaDraft["concurrency_mode"])}>
            <option value="AUTO">Automatic, based on free GPU memory</option>
            <option value="MANUAL">Manual, a fixed number of jobs</option>
          </Select>
        </Field>
        <Field label="Max concurrent GPU tasks">
          <Input type="number" min={1} max={8} disabled={draft.concurrency_mode === "AUTO"} value={draft.max_gpu_concurrency} onChange={(event) => set("max_gpu_concurrency", Math.max(1, Math.min(8, Number(event.target.value) || 1)))} />
        </Field>
        <Field label="Context window (tokens)">
          <Input type="number" min={2048} step={1024} value={draft.num_ctx} onChange={(event) => set("num_ctx", Number(event.target.value) || saved.num_ctx)} />
        </Field>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" loading={save.isPending} disabled={!dirty} onClick={() => void onSave()}>Save changes</Button>
        <Button variant="ghost" disabled={!dirty} onClick={() => { setProblem(null); setDraft(draftFromConfig(saved)); }}>Discard</Button>
        {dirty && !problem && <span className="text-sm text-fg-dim">You have unsaved changes.</span>}
        {problem && <p role="alert" className="text-sm text-bad">{problem}</p>}
      </div>

      <Card title="Installed models">
        {models.isError ? (
          <ErrorState title="Couldn't load installed models" description="Check that Ollama is running, then try again." onRetry={() => void models.refetch()} />
        ) : models.data ? <ModelList data={models.data} /> : <Skeleton className="h-16" />}
        <ModelPull />
      </Card>
    </div>
  );
};
