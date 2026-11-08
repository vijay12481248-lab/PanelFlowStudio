import React from "react";
import { Chip, ErrorState, GlassPanel, Skeleton } from "@panelflow/ui-v2";
import { CloudProviderForm } from "./CloudProviderForm";
import { RoutingForm } from "./RoutingForm";
import { providerOptions } from "./settingsModels";
import { useCloudLLM, useGlobalLLM, useLLMProviders } from "./settingsQueries";

export const ProvidersSection: React.FC = () => {
  const global = useGlobalLLM();
  const info = useLLMProviders();
  const cloud = useCloudLLM();
  const options = global.data ? providerOptions(global.data, info.data ?? []) : [];

  return (
    <div className="grid grid-cols-1 gap-5">
      <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
        <h2 className="font-display text-sm font-semibold text-fg">Providers</h2>
        {global.isError ? null : !global.data ? <Skeleton className="h-16" /> : (
          <ul className="grid grid-cols-1 gap-2">
            {options.map((option) => (
              <li key={option.id} className="flex items-center gap-3 rounded-ctl border border-edge p-3">
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-fg">{option.name}</span>
                <Chip>{option.local ? "Local" : "Cloud"}</Chip>
                <Chip tone={option.ready ? "ok" : "warn"}>{option.ready ? "Ready" : "Not ready"}</Chip>
              </li>
            ))}
          </ul>
        )}
        {info.isError && <p className="text-xs text-warn">Couldn't load the full provider list, so only configured providers are shown.</p>}
      </GlassPanel>

      {global.isError ? (
        <ErrorState title="Couldn't load routing settings" description="Check that the engine is running, then try again." onRetry={() => void global.refetch()} />
      ) : global.data ? (
        <RoutingForm key={JSON.stringify(global.data)} settings={global.data} options={options} />
      ) : null}

      {cloud.isError ? (
        <ErrorState title="Couldn't load the cloud provider" description="Check that the engine is running, then try again." onRetry={() => void cloud.refetch()} />
      ) : cloud.data ? (
        <CloudProviderForm key={`${cloud.data.provider_type}|${cloud.data.endpoint_url}|${cloud.data.model_name}|${cloud.data.has_api_key}`} config={cloud.data} />
      ) : (
        <Skeleton className="h-48" />
      )}
    </div>
  );
};
