import type { SettingsSection } from "../../app/routes";

export const SETTINGS_SECTIONS: ReadonlyArray<{ id: SettingsSection; label: string; description: string }> = [
  { id: "engine", label: "Engine", description: "Health, tools and resources" },
  { id: "models", label: "Models", description: "Local Ollama models" },
  { id: "providers", label: "Providers", description: "Default provider and routing" },
  { id: "youtube", label: "YouTube", description: "Channels and uploads" },
  { id: "diagnostics", label: "Diagnostics", description: "Hardware and export" },
];
