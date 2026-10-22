import { api } from "@panelflow/api-client";

type HealthClient = Pick<typeof api, "checkHealth" | "setEngineToken">;
type TokenReader = () => Promise<string>;

function desktopTokenReader(): TokenReader | undefined {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window || "__TAURI__" in window)) return undefined;
  return async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<string>("get_engine_token_cmd");
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
