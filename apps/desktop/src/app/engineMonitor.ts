// Pure, injectable ports of the engine reconnect logic that lived in App.tsx (handleRetryEngine / handleRestartEngine).

export interface EngineHealth {
  status: string;
  version: string;
  instance_id?: string;
}

interface Timing {
  sleep: (ms: number) => Promise<void>;
  health: () => Promise<EngineHealth>;
}

export const RESTART_TIMEOUT_MESSAGE = "Engine did not reconnect within 60 seconds. Check the engine log or run launch_panelflow again.";

/** Try to start the engine, then poll its health. Returns null when it never became healthy. */
export async function connectWithRetry(deps: Timing & { start?: () => Promise<void> }, attempts = 6, delayMs = 600): Promise<EngineHealth | null> {
  try {
    await deps.start?.();
  } catch (error) {
    console.warn("[PanelFlow] Engine start notice:", error);
  }
  for (let i = 0; i < attempts; i++) {
    await deps.sleep(delayMs);
    try {
      const health = await deps.health();
      if (health.status === "healthy") return health;
    } catch {
      // keep polling: the engine is still starting
    }
  }
  return null;
}

/** Ask the engine to restart and wait for a healthy process with a different instance id. */
export async function restartAndWait(deps: Timing & { restart: () => Promise<{ instance_id?: string }> }, attempts = 60, delayMs = 1000): Promise<EngineHealth> {
  const previous = await deps.restart();
  for (let i = 0; i < attempts; i++) {
    await deps.sleep(delayMs);
    try {
      const health = await deps.health();
      if (health.status === "healthy" && health.instance_id && health.instance_id !== previous.instance_id) return health;
    } catch {
      // expected while the engine restarts
    }
  }
  throw new Error(RESTART_TIMEOUT_MESSAGE);
}
