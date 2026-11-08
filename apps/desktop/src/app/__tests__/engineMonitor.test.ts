import test from "node:test";
import assert from "node:assert/strict";
import { RESTART_TIMEOUT_MESSAGE, connectWithRetry, restartAndWait } from "../engineMonitor";

const healthy = { status: "healthy", version: "1.0.0-beta.2", instance_id: "new" };

function recorder() {
  const sleeps: number[] = [];
  return { sleeps, sleep: async (ms: number) => { sleeps.push(ms); } };
}

test("connectWithRetry starts the engine once, then waits before each health check", async () => {
  const { sleeps, sleep } = recorder();
  let starts = 0;
  let checks = 0;
  const result = await connectWithRetry({
    start: async () => { starts++; },
    sleep,
    health: async () => { if (++checks < 3) throw new Error("refused"); return healthy; },
  });
  assert.deepEqual(result, healthy);
  assert.equal(starts, 1);
  assert.deepEqual(sleeps, [600, 600, 600]);
});

test("connectWithRetry treats an unhealthy status as not ready and gives up after 6 attempts", async () => {
  const { sleeps, sleep } = recorder();
  const result = await connectWithRetry({ sleep, health: async () => ({ status: "starting", version: "" }) });
  assert.equal(result, null);
  assert.equal(sleeps.length, 6);
});

test("connectWithRetry still polls when starting the engine fails", async () => {
  const { sleep } = recorder();
  const result = await connectWithRetry({ sleep, start: async () => { throw new Error("no tauri"); }, health: async () => healthy });
  assert.deepEqual(result, healthy);
});

test("restartAndWait resolves only once the engine reports a different instance id", async () => {
  const { sleeps, sleep } = recorder();
  const seen = [{ ...healthy, instance_id: "old" }, { ...healthy, instance_id: "old" }, healthy];
  const result = await restartAndWait({ sleep, restart: async () => ({ instance_id: "old" }), health: async () => seen.shift() ?? healthy });
  assert.equal(result.instance_id, "new");
  assert.deepEqual(sleeps, [1000, 1000, 1000]);
});

test("restartAndWait keeps polling through connection errors", async () => {
  const { sleep } = recorder();
  let calls = 0;
  const result = await restartAndWait({
    sleep,
    restart: async () => ({ instance_id: "old" }),
    health: async () => { if (++calls < 3) throw new Error("down"); return healthy; },
  });
  assert.equal(result.instance_id, "new");
});

test("restartAndWait throws the documented message after 60 attempts without a new instance", async () => {
  const { sleeps, sleep } = recorder();
  await assert.rejects(
    restartAndWait({ sleep, restart: async () => ({ instance_id: "old" }), health: async () => ({ ...healthy, instance_id: "old" }) }),
    { message: RESTART_TIMEOUT_MESSAGE },
  );
  assert.equal(sleeps.length, 60);
  assert.equal(RESTART_TIMEOUT_MESSAGE, "Engine did not reconnect within 60 seconds. Check the engine log or run launch_panelflow again.");
});
