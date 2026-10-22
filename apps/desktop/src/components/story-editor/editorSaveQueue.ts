type SaveStatus = "unsaved" | "saving" | "saved";
interface SaveUpdates { status: (status: SaveStatus) => void; error: (message: string | null) => void; }

// One project, one serialized writer. A slower old save cannot overwrite a newer edit.
export function createDebouncedSaveQueue<T>(write: (snapshot: T) => Promise<unknown>, updates: SaveUpdates, delayMs = 1000) {
  let disposed = false;
  let revision = 0;
  let savedRevision = 0;
  let inFlightRevision = 0;
  type Snapshot = { revision: number; snapshot: T };
  let latest: Snapshot | null = null;
  let pending: Snapshot | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running: Promise<boolean> | null = null;

  function drain(): Promise<boolean> {
    if (disposed) return Promise.resolve(false);
    if (running) return running.then(() => pending && !disposed ? drain() : !latest || savedRevision === latest.revision);
    running = (async () => {
      while (pending && !disposed) {
        const item = pending;
        pending = null;
        inFlightRevision = item.revision;
        updates.status("saving");
        try {
          await write(item.snapshot);
          savedRevision = item.revision;
          if (!disposed && revision === item.revision) { updates.error(null); updates.status("saved"); }
        } catch {
          if (!disposed && revision === item.revision) {
            updates.error("Could not save this project. Keep the editor open and retry.");
            updates.status("unsaved");
          }
        } finally { inFlightRevision = 0; }
      }
      return !latest || savedRevision === latest.revision;
    })().finally(() => { running = null; });
    return running;
  }

  return {
    schedule(snapshot: T) {
      if (disposed) return;
      latest = { revision: ++revision, snapshot };
      updates.error(null);
      updates.status("unsaved");
      clearTimeout(timer);
      timer = setTimeout(() => { pending = latest; void drain(); }, delayMs);
    },
    flush(): Promise<boolean> {
      if (disposed) return Promise.resolve(false);
      clearTimeout(timer);
      if (latest && latest.revision > savedRevision && latest.revision !== inFlightRevision) pending = latest;
      return drain();
    },
    async discardPending(): Promise<void> {
      clearTimeout(timer);
      revision++; // An older in-flight request must not publish a stale Saved status.
      latest = null;
      pending = null;
      await running;
    },
    dispose() {
      disposed = true;
      clearTimeout(timer);
      pending = null;
    },
  };
}
