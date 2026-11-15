import React from "react";
import type { OllamaModelsResponse } from "@panelflow/shared-types";
import { Chip, EmptyState } from "@panelflow/ui-v2";

export const ModelList: React.FC<{ data: OllamaModelsResponse }> = ({ data }) => {
  const recommended = new Set(Object.values(data.recommendations ?? {}));
  if (data.models.length === 0) {
    return <EmptyState title="No models installed" description="Download a model below, and make sure Ollama is running." />;
  }
  return (
    <ul className="grid grid-cols-1 gap-2">
      {data.models.map((model) => (
        <li key={model.name} className="flex flex-wrap items-center gap-3 rounded-ctl border border-edge p-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg">{model.name}</p>
            <p className="text-xs text-fg-dim">{[model.family, model.parameter_size, model.quantization_level].filter(Boolean).join(", ")}</p>
          </div>
          {model.supports_vision && <Chip tone="accent">Vision</Chip>}
          {model.supports_tools && <Chip>Tools</Chip>}
          {model.supports_thinking && <Chip>Thinking</Chip>}
          {recommended.has(model.name) && <Chip tone="ok">Recommended</Chip>}
        </li>
      ))}
    </ul>
  );
};
