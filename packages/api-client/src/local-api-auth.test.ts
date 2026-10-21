import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { PanelFlowApiClient } from "./index.ts";

test("API client sends the engine token in a header and never in JSON", async () => {
  let capturedUrl = "";
  let capturedInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const client = new PanelFlowApiClient("http://127.0.0.1:8765", "secret-token");
    await client.createProject({
      title: "Token transport",
      source_type: "LOCAL_FOLDER",
      rights_status: "USER_OWNED",
    });

    const headers = capturedInit?.headers as Record<string, string>;
    assert.equal(headers["X-PanelFlow-Token"], "secret-token");
    assert.equal(capturedUrl, "http://127.0.0.1:8765/api/projects");
    assert.doesNotMatch(String(capturedInit?.body), /secret-token/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API client can receive a token after Tauri starts the engine", async () => {
  let capturedHeaders: Record<string, string> = {};
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
    capturedHeaders = init?.headers as Record<string, string>;
    return new Response(JSON.stringify({ status: "healthy", app: "PanelFlow Studio", version: "1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const client = new PanelFlowApiClient();
    client.setEngineToken("late-token");
    await client.listProjects();
    assert.equal(capturedHeaders["X-PanelFlow-Token"], "late-token");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("project DELETE sends current authentication over real fetch and handles a bodyless 204", async () => {
  // Disposable HTTP fixture, not the engine: no real project can be deleted.
  const requests: Array<{ url?: string; method?: string; token?: string; body: string }> = [];
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      requests.push({ url: request.url, method: request.method, token: request.headers["x-panelflow-token"] as string, body });
      response.writeHead(204).end();
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  try {
    const address = server.address();
    assert.ok(address && typeof address !== "string");
    const client = new PanelFlowApiClient(`http://127.0.0.1:${address.port}`, "expired-fixture");
    client.setEngineToken("current-fixture");
    assert.equal(await client.deleteProject("test-only-project"), null);
    assert.deepEqual(requests, [{
      url: "/api/projects/test-only-project", method: "DELETE", token: "current-fixture", body: "",
    }]);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("resource URLs use a path capability rather than a query string", () => {
  const client = new PanelFlowApiClient("http://127.0.0.1:8765", "resource-token");
  const url = client.getPageImageUrl("project", "page");
  assert.equal(url, "http://127.0.0.1:8765/api/projects/project/pages/page/file;pf-token=resource-token");
  assert.doesNotMatch(url, /\?/);
});
