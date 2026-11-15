import React from "react";
import { api } from "@panelflow/api-client";
import { historyAvailability } from "../panels/panelsModel";
import { useProjectHistory } from "../panels/panelsData";

export interface HistoryMovesOptions {
  /** Reload whatever the undo or redo changed. A failure here is reported as the move failing. */
  onMoved: () => void | Promise<void>;
  onFailed: (which: "undo" | "redo", error: unknown) => void;
}

/** The engine's undo and redo for a project: one move at a time, and nothing is sent when the engine's own state says there is nothing to do. */
export function useHistoryMoves(projectId: string, { onMoved, onFailed }: HistoryMovesOptions) {
  const history = useProjectHistory(projectId);
  const flight = React.useRef(false);
  const [working, setWorking] = React.useState(false);

  const move = async (which: "undo" | "redo") => {
    if (flight.current) return;
    const known = api.getCachedProjectHistory(projectId);
    if (known && !(which === "undo" ? known.canUndo : known.canRedo)) { history.setHistory(known); return; }
    flight.current = true;
    setWorking(true);
    try {
      const reply = which === "undo" ? await api.undo(projectId) : await api.redo(projectId);
      history.setHistory(reply.history ?? api.getCachedProjectHistory(projectId));
      await onMoved();
    } catch (err) {
      history.refresh();
      onFailed(which, err);
    } finally { flight.current = false; setWorking(false); }
  };

  return { ...history, availability: historyAvailability(history.history, working), move };
}
