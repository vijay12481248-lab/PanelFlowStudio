import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { ToastProvider } from "@panelflow/ui-v2";
import { ErrorProvider, useError } from "../context/ErrorContext";
import { getAuthenticatedEngineHealth } from "../engineConnection";
import { connectWithRetry, restartAndWait } from "./engineMonitor";

const isTauri = () => typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Launch the bundled engine (desktop build only) and pick up its auth token. */
async function startDesktopEngine(): Promise<void> {
  if (!isTauri()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("start_engine_cmd");
  api.setEngineToken(await invoke<string>("get_engine_token_cmd"));
}

export interface EngineState {
  connected: boolean;
  version: string;
  /** True for the first seconds after launch, so the shell shows "connecting" rather than "unavailable". */
  startupGrace: boolean;
  retrying: boolean;
  restarting: boolean;
  retry: () => Promise<void>;
  restart: () => Promise<void>;
}

const EngineContext = React.createContext<EngineState | null>(null);

export function useEngine(): EngineState {
  const value = React.useContext(EngineContext);
  if (!value) throw new Error("useEngine must be used inside AppProviders");
  return value;
}

export const EngineProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { reportError } = useError();
  const [connected, setConnected] = React.useState(false);
  const [version, setVersion] = React.useState("");
  const [startupGrace, setStartupGrace] = React.useState(true);
  const [retrying, setRetrying] = React.useState(false);
  const [restarting, setRestarting] = React.useState(false);
  const restartingRef = React.useRef(false);

  const check = React.useCallback(async () => {
    if (restartingRef.current) return;
    try {
      const health = await getAuthenticatedEngineHealth();
      if (health.status === "healthy") {
        setConnected(true);
        setVersion(health.version);
        setStartupGrace(false);
      } else {
        setConnected(false);
      }
    } catch {
      setConnected(false);
    }
  }, []);

  const retry = React.useCallback(async () => {
    setRetrying(true);
    try {
      const health = await connectWithRetry({ start: startDesktopEngine, sleep, health: getAuthenticatedEngineHealth });
      if (health) {
        setConnected(true);
        setVersion(health.version);
      }
    } finally {
      await check();
      setRetrying(false);
    }
  }, [check]);

  const restart = React.useCallback(async () => {
    if (restartingRef.current) return;
    restartingRef.current = true;
    setRestarting(true);
    try {
      const health = await restartAndWait({ restart: () => api.restartEngine(), sleep, health: getAuthenticatedEngineHealth });
      setConnected(true);
      setVersion(health.version);
    } catch (error: any) {
      reportError({ title: "Engine restart failed", message: error?.message || "Could not restart the engine.", severity: "error", source: "engine" });
    } finally {
      restartingRef.current = false;
      setRestarting(false);
      await check();
    }
  }, [check, reportError]);

  React.useEffect(() => {
    void check();
    startDesktopEngine().catch((error) => console.warn("[PanelFlow] Auto-start notice:", error));
    const grace = setTimeout(() => setStartupGrace(false), 7000);
    const onTokenInvalid = () => void check();
    window.addEventListener("panelflow:token-invalid", onTokenInvalid);
    return () => {
      clearTimeout(grace);
      window.removeEventListener("panelflow:token-invalid", onTokenInvalid);
    };
  }, [check]);

  React.useEffect(() => {
    const timer = setInterval(() => void check(), connected ? 8000 : 1500);
    return () => clearInterval(timer);
  }, [connected, check]);

  const value = React.useMemo(
    () => ({ connected, version, startupGrace, retrying, restarting, retry, restart }),
    [connected, version, startupGrace, retrying, restarting, retry, restart],
  );
  return <EngineContext.Provider value={value}>{children}</EngineContext.Provider>;
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export const AppProviders: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ErrorProvider>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <EngineProvider>{children}</EngineProvider>
      </ToastProvider>
    </QueryClientProvider>
  </ErrorProvider>
);
