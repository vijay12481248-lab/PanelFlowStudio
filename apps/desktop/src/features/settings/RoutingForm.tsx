import React from "react";
import { api } from "@panelflow/api-client";
import type { GlobalLLMSettings, SaveGlobalLLMSettingsRequest } from "@panelflow/shared-types";
import { Button, Field, GlassPanel, Input, Select } from "@panelflow/ui-v2";
import { WORKFLOWS, localFirstWarning, routingChanged, routingFromSettings, routingToRequest, type ProviderOption, type RoutingDraft } from "./settingsModels";
import { settingsKeys, useSettingsMutation } from "./settingsQueries";

export interface RoutingFormProps {
  settings: GlobalLLMSettings;
  options: ProviderOption[];
}

export const RoutingForm: React.FC<RoutingFormProps> = ({ settings, options }) => {
  const [draft, setDraft] = React.useState<RoutingDraft>(() => routingFromSettings(settings));
  const [problem, setProblem] = React.useState<string | null>(null);
  const saving = React.useRef(false); // synchronous guard against a fast double click
  const save = useSettingsMutation<SaveGlobalLLMSettingsRequest>((request) => api.saveGlobalLLMSettings(request), "Routing saved", [settingsKeys.globalLLM]);

  const dirty = routingChanged(settings, draft);
  const warning = localFirstWarning(draft, options);
  const choices = (
    <>
      {options.map((o) => <option key={o.id} value={o.id}>{`${o.name}${o.ready ? "" : " (not set up)"}`}</option>)}
    </>
  );

  const onSave = async () => {
    if (!dirty || saving.current) return;
    saving.current = true;
    setProblem(null);
    try {
      await save.mutateAsync(routingToRequest(draft));
    } catch (error) {
      setProblem(`Couldn't save the setting. ${(error as Error).message || "Check the engine and try again."}`);
    } finally {
      saving.current = false;
    }
  };

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-4 p-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-fg">Routing</h2>
        <p className="text-sm text-fg-dim">Which provider answers each kind of job. Everything stays on this PC while the default is Local Ollama.</p>
      </div>
      <Field label="Default provider">
        <Select value={draft.provider} onChange={(event) => setDraft({ ...draft, provider: event.target.value })}>{choices}</Select>
      </Field>
      <Field label="Default model">
        <Input value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} />
      </Field>
      <div className="grid grid-cols-1 gap-3">
        {WORKFLOWS.map(({ key, label }) => {
          const current = draft.overrides[key]?.provider_id ?? "global";
          return (
            <div key={key} className="grid grid-cols-1 gap-2 rounded-ctl border border-edge p-3 md:grid-cols-2">
              <Field label={`Provider for ${label}`}>
                <Select value={current} onChange={(event) => setDraft({ ...draft, overrides: { ...draft.overrides, [key]: { provider_id: event.target.value, model_name: draft.overrides[key]?.model_name ?? "" } } })}>
                  <option value="global">Use the default</option>
                  {choices}
                </Select>
              </Field>
              {current !== "global" && (
                <Field label={`Model for ${label}`} hint="Leave empty to use the provider's default.">
                  <Input value={draft.overrides[key]?.model_name ?? ""} onChange={(event) => setDraft({ ...draft, overrides: { ...draft.overrides, [key]: { provider_id: current, model_name: event.target.value } } })} />
                </Field>
              )}
            </div>
          );
        })}
      </div>
      {warning && <p role="status" className="rounded-ctl border border-warn/40 bg-warn/10 p-3 text-sm text-warn">{warning}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" loading={save.isPending} disabled={!dirty} onClick={() => void onSave()}>Save routing</Button>
        <Button variant="ghost" disabled={!dirty} onClick={() => { setProblem(null); setDraft(routingFromSettings(settings)); }}>Discard</Button>
        {problem && <p role="alert" className="text-sm text-bad">{problem}</p>}
      </div>
    </GlassPanel>
  );
};
