import { api } from "@panelflow/api-client";

type HealthClient = Pick<typeof api, "checkHealth" | "setEngineToken">;
type TokenReader = () => Promise<string>;

function desktopTokenReader(): TokenReader | undefined {
  if (typeof window === "undefined") return undefined;
  if ("__TAURI_INTERNALS__" in window || "__TAURI__" in window) {
    return async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      return invoke<string>("get_engine_token_cmd");
    };
  }

  // Standalone / Browser development mode token reader
  return async () => {
    // 1. Vite build/dev injected environment variable
    const envToken = (import.meta as any).env?.VITE_PANELFLOW_ENGINE_TOKEN;
    if (envToken && typeof envToken === "string" && envToken.trim()) return envToken.trim();

    // 2. Query param (?token=...)
    try {
      const params = new URLSearchParams(window.location.search);
      const queryToken = params.get("token");
      if (queryToken && queryToken.trim()) {
        try { localStorage.setItem("panelflow_engine_token", queryToken.trim()); } catch {}
        return queryToken.trim();
      }
    } catch {}

    // 3. Persisted in localStorage
    try {
      const stored = localStorage.getItem("panelflow_engine_token");
      if (stored && stored.trim()) return stored.trim();
    } catch {}

    // 4. Vite dev server endpoint
    try {
      const res = await fetch("/__engine_token");
      if (res.ok) {
        const text = await res.text();
        if (text.trim()) {
          try { localStorage.setItem("panelflow_engine_token", text.trim()); } catch {}
          return text.trim();
        }
      }
    } catch {}

    return "";
  };
}

// A public health response alone is not readiness for authenticated project APIs.
export async function getAuthenticatedEngineHealth(
  client: HealthClient = api,
  readToken: TokenReader | undefined = desktopTokenReader(),
) {
  const health = await client.checkHealth();
  if (health.status === "healthy" && readToken) {
    const token = await readToken();
    if (!token?.trim()) throw new Error("Desktop engine authentication is not ready.");
    client.setEngineToken(token);
  }
  return health;
}
