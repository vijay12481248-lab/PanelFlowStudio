import React, { useEffect, useRef, useState } from "react";
import { api } from "@panelflow/api-client";
import type { LLMProviderInfo, OllamaModelCapability } from "@panelflow/shared-types";
import { Badge, Button, Card } from "@panelflow/ui";

type Section = "overview" | "models" | "routing" | "usage" | "diagnostics";
// The engine's failed /api/show probe omits these fields.
type InventoryModel = Omit<OllamaModelCapability, "capabilities" | "format"> &
  Partial<Pick<OllamaModelCapability, "capabilities" | "format">>;
interface ProviderManagementData {
  providers: LLMProviderInfo[];
  models: InventoryModel[];
  errors: string[];
}
type InventoryClient = Pick<typeof api, "listLLMProviders" | "getOllamaModels">;

// Use the authenticated desktop client, never import Python registries into React.
export async function loadProviderManagementData(client: InventoryClient = api): Promise<ProviderManagementData> {
  const [providers, models] = await Promise.allSettled([
    client.listLLMProviders(), client.getOllamaModels(),
  ]);
  return {
    providers: providers.status === "fulfilled" ? providers.value : [],
    models: models.status === "fulfilled" ? models.value.models : [],
    errors: [
      ...(providers.status === "rejected" ? ["Provider inventory could not be loaded."] : []),
      ...(models.status === "rejected" ? ["Ollama model inventory could not be loaded."] : []),
    ],
  };
}

const sections: Record<Section, string> = {
  overview: "Provider Overview", models: "Model Explorer", routing: "Intelligent Routing",
  usage: "Usage Dashboard", diagnostics: "Gateway Diagnostics",
};

export function ProviderManagementContent({ data, section, query }: {
  data: ProviderManagementData; section: Section; query: string;
}) {
  const search = query.trim().toLowerCase();
  const providers = data.providers.filter((provider) =>
    `${provider.provider_name} ${provider.provider_id}`.toLowerCase().includes(search));
  const models = data.models.filter((model) =>
    `${model.name} ${model.family} ${(model.capabilities ?? []).join(" ")}`.toLowerCase().includes(search));
  return (
    <div className="space-y-4">
      {data.errors.length > 0 && (
        <div role="alert" className="rounded-xl border border-amber-800 bg-amber-950/30 p-4 text-amber-200">
          {data.errors.map((message) => <p key={message}>{message}</p>)}
          <p className="text-sm mt-2">Check the engine connection and refresh to retry.</p>
        </div>
      )}
      {section === "overview" && (
        <>
          <p className="text-sm text-zinc-400">Providers registered with the story engine. Availability is reported by the engine; it does not imply gateway routing is configured.</p>
          <div className="grid gap-4 md:grid-cols-2">
            {providers.map((provider) => (
              <Card key={provider.provider_id} className="p-4 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">{provider.provider_name}</h3>
                  <Badge variant={provider.is_healthy ? "success" : "warning"}>{provider.is_healthy ? "Available" : "Unavailable"}</Badge>
                </div>
                <p className="text-xs font-mono text-zinc-400">{provider.provider_id}</p>
                <p className="text-sm text-zinc-300">{provider.is_multimodal ? "Multimodal" : "Text"}</p>
                {provider.context_window != null && <p className="text-sm text-zinc-400">Context: {provider.context_window.toLocaleString()} tokens</p>}
              </Card>
            ))}
          </div>
          {providers.length === 0 && !data.errors.includes("Provider inventory could not be loaded.") && (
            <p className="text-zinc-400">{search ? "No providers match your search." : "No providers registered."}</p>
          )}
        </>
      )}
      {section === "models" && (
        <>
          <p className="text-sm text-zinc-400">Installed Ollama models reported by the engine. Cloud gateway model inventory and pricing are not available through the desktop API.</p>
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-900 text-zinc-400"><tr>
                <th className="p-3">Model</th><th className="p-3">Family</th><th className="p-3">Parameters</th><th className="p-3">Quantization</th><th className="p-3">Capabilities</th>
              </tr></thead>
              <tbody>{models.map((model) => (
                <tr key={model.name} className="border-t border-zinc-800">
                  <td className="p-3 font-mono">{model.name}</td><td className="p-3">{model.family}</td>
                  <td className="p-3">{model.parameter_size}</td><td className="p-3">{model.quantization_level}</td>
                  <td className="p-3">{(model.capabilities ?? []).join(", ") || "Not reported"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {models.length === 0 && !data.errors.includes("Ollama model inventory could not be loaded.") && (
            <p className="text-zinc-400">{search ? "No models match your search." : "No installed Ollama models reported."}</p>
          )}
        </>
      )}
      {(section === "routing" || section === "usage" || section === "diagnostics") && (
        <Card className="p-5 space-y-2">
          <h3 className="font-semibold">{sections[section]} not available</h3>
          <p className="text-sm text-zinc-400">The desktop API does not expose gateway {section === "routing" ? "routing or budget configuration" : section === "usage" ? "usage and cost records" : "routing decisions, cooldowns or health records"} yet. No sample data or unsaved settings are shown.</p>
          <p className="text-sm text-zinc-400">Use Tools &amp; Models for the existing local configuration and system diagnostics.</p>
        </Card>
      )}
    </div>
  );
}

export default function ProviderManagementScreen({ onBack, onOpenToolsModels }: {
  onBack: () => void; onOpenToolsModels: () => void;
}) {
  const [section, setSection] = useState<Section>("overview");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ProviderManagementData>({ providers: [], models: [], errors: [] });
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const refresh = async () => {
    const request = ++generation.current;
    setLoading(true);
    const next = await loadProviderManagementData();
    if (request === generation.current) { setData(next); setLoading(false); }
  };
  useEffect(() => {
    void refresh();
    return () => { generation.current++; };
  }, []);
  return (
    <section aria-label="AI Provider Management" className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">AI Provider Management</h1>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={onBack}>Back to Dashboard</Button>
          <Button variant="secondary" onClick={onOpenToolsModels}>Tools &amp; Models</Button>
          <Button onClick={() => void refresh()} disabled={loading}>Refresh</Button>
        </div>
      </div>
      <nav aria-label="Provider management sections" className="flex flex-wrap gap-2">
        {(Object.keys(sections) as Section[]).map((key) => (
          <Button key={key} variant={section === key ? "primary" : "ghost"} aria-current={section === key ? "page" : undefined} onClick={() => setSection(key)}>{sections[key]}</Button>
        ))}
      </nav>
      {(section === "overview" || section === "models") && (
        <label className="block text-sm text-zinc-400">Search {section === "overview" ? "providers" : "models"}
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} className="block mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2 text-zinc-100 focus:outline-none focus:border-indigo-500" />
        </label>
      )}
      {loading ? <p role="status" className="text-zinc-400">Loading provider and model inventory…</p> : <ProviderManagementContent data={data} section={section} query={query} />}
    </section>
  );
}
