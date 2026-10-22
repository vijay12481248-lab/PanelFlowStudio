import test from "node:test";
import assert from "node:assert/strict";
import { getAuthenticatedEngineHealth } from "../engineConnection";

const health = { status: "healthy", app: "PanelFlow Studio", version: "test" };

test("engine readiness waits until the desktop token is installed", async () => {
  let resolveToken!: (token: string) => void;
  const token = new Promise<string>((resolve) => { resolveToken = resolve; });
  const events: string[] = [];
  const client = { checkHealth: async () => health, setEngineToken: () => { events.push("token-installed"); } };
  const connecting = getAuthenticatedEngineHealth(client, () => token).then(() => { events.push("ready"); });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(events, []);
  resolveToken("test-only-token");
  await connecting;
  assert.deepEqual(events, ["token-installed", "ready"]);
});

test("desktop token failures cannot publish authenticated readiness", async () => {
  await assert.rejects(getAuthenticatedEngineHealth({ checkHealth: async () => health, setEngineToken: () => {} }, async () => { throw new Error("token unavailable"); }), /token unavailable/);
});

test("unhealthy engines do not attempt token installation", async () => {
  let read = false;
  const result = await getAuthenticatedEngineHealth({ checkHealth: async () => ({ ...health, status: "starting" }), setEngineToken: () => {} }, async () => { read = true; return "test-token"; });
  assert.equal(result.status, "starting");
  assert.equal(read, false);
});
