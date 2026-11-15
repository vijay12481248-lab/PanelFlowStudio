import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { useToast } from "@panelflow/ui-v2";
import { useError } from "../../context/ErrorContext";
import { useEngine } from "../../app/providers";

export const settingsKeys = {
  providerHealth: ["settings", "providerHealth"],
  ffmpeg: ["settings", "ffmpeg"],
  playwright: ["settings", "playwright"],
  hardware: ["settings", "hardware"],
  ollamaConfig: ["settings", "ollamaConfig"],
  ollamaModels: ["settings", "ollamaModels"],
  globalLLM: ["settings", "globalLLM"],
  cloudLLM: ["settings", "cloudLLM"],
  llmProviders: ["settings", "llmProviders"],
} as const;

function useRead<T>(key: QueryKey, fn: () => Promise<T>, refetchInterval?: number | ((data: T | undefined) => number | false)) {
  const { connected } = useEngine();
  return useQuery<T>({
    queryKey: key,
    queryFn: fn,
    enabled: connected,
    retry: 1,
    refetchOnMount: "always",
    refetchInterval: typeof refetchInterval === "function" ? (query) => refetchInterval(query.state.data as T | undefined) : refetchInterval,
  });
}

export const useProviderHealth = () => useRead(settingsKeys.providerHealth, () => api.getProviderHealth());
export const useFfmpeg = () => useRead(settingsKeys.ffmpeg, () => api.locateFfmpeg());
/** Polls every 2 seconds only while the install is running. */
export const usePlaywrightStatus = () => useRead(settingsKeys.playwright, () => api.getPlaywrightInstallStatus(), (data) => (data?.status === "RUNNING" ? 2000 : false));
export const useHardware = () => useRead(settingsKeys.hardware, () => api.getHardwareDiagnostics());
export const useOllamaConfig = () => useRead(settingsKeys.ollamaConfig, () => api.getOllamaConfig());
export const useOllamaModels = () => useRead(settingsKeys.ollamaModels, () => api.getOllamaModels());
export const useGlobalLLM = () => useRead(settingsKeys.globalLLM, () => api.getGlobalLLMSettings());
export const useCloudLLM = () => useRead(settingsKeys.cloudLLM, () => api.getCloudLLMConfig());
export const useLLMProviders = () => useRead(settingsKeys.llmProviders, () => api.listLLMProviders());

/** A settings write that toasts on success and reports failures in words (never the raw exception alone). */
export function useSettingsMutation<TVars, TResult = unknown>(fn: (vars: TVars) => Promise<TResult>, successMessage: string, invalidate: QueryKey[] = []) {
  const toast = useToast();
  const { reportError } = useError();
  const queryClient = useQueryClient();
  return useMutation<TResult, Error, TVars>({
    mutationFn: fn,
    onSuccess: () => {
      toast.show(successMessage, "ok");
      for (const key of invalidate) void queryClient.invalidateQueries({ queryKey: key });
    },
    onError: (error) =>
      reportError({ title: "Couldn't save the setting", message: error.message || "The engine did not accept the change. Check the engine and try again.", severity: "error", source: "engine" }),
  });
}
