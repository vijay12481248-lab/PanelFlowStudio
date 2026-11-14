import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project, StoryboardDocument, StoryboardPanelRef, StoryboardSegment, VideoScript } from "@panelflow/shared-types";
import { refusal } from "../kit/engineReason";
import { scriptKeys, type useScriptValidation } from "./scriptData";
import type { LineValues } from "./SegmentEditor";

export interface ScriptEditingOptions {
  project: Project;
  script: VideoScript | null;
  validation: ReturnType<typeof useScriptValidation>;
  onProjectUpdated: (updated: Project) => void;
}

/**
 * Every change to a script line or storyboard beat, one at a time. Each change that can alter what the faithfulness check
 * sees drops the stale report and validates once more. A failure is kept as words in `error`.
 */
export function useScriptEditing({ project, script, validation, onProjectUpdated }: ScriptEditingOptions) {
  const queryClient = useQueryClient();
  const flight = React.useRef(false); // synchronous: one change at a time across the whole screen
  const [busy, setBusy] = React.useState(false);
  const [realigning, setRealigning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = async (change: () => Promise<void>, headline: string): Promise<boolean> => {
    if (flight.current || !script) return false;
    flight.current = true;
    setBusy(true);
    setError(null);
    try {
      await change();
      return true;
    } catch (err) {
      setError(refusal(headline, err, "Try again."));
      return false;
    } finally { flight.current = false; setBusy(false); }
  };

  const patchBoard = (updated: StoryboardSegment) =>
    queryClient.setQueryData<StoryboardDocument | null>(scriptKeys.storyboard(project.id), (sb) => (sb ? { ...sb, segments: sb.segments.map((s) => (s.segment_id === updated.segment_id ? updated : s)) } : sb));

  return {
    busy,
    realigning,
    error,
    clearError: () => setError(null),

    /** One of the engine's line actions (shorten, split, remove, ...). */
    actionOn: (segmentId: string, actionId: string) => run(async () => {
      const updated = await api.editScriptSegment(project.id, script!.script_id, segmentId, actionId);
      queryClient.setQueryData(scriptKeys.script(project.id), updated);
      void queryClient.invalidateQueries({ queryKey: scriptKeys.storyboard(project.id) });
      await validation.revalidate();
    }, "Couldn't change that line."),

    saveLine: (segmentId: string, values: LineValues) => run(async () => {
      await api.updateScriptSegment(project.id, script!.script_id, segmentId, values);
      await queryClient.invalidateQueries({ queryKey: scriptKeys.script(project.id) });
      await validation.revalidate();
      onProjectUpdated(await api.getProject(project.id));
    }, "Couldn't save the line."),

    saveBeat: (segmentId: string, values: LineValues) => run(async () => {
      patchBoard(await api.updateStoryboardSegment(project.id, segmentId, { text: values.text, emotion: values.emotion, intensity: values.intensity }));
      await validation.revalidate();
    }, "Couldn't save the beat."),

    setMotion: (segmentId: string, panels: StoryboardPanelRef[]) => run(async () => {
      patchBoard(await api.updateStoryboardSegment(project.id, segmentId, { supporting_panels: panels }));
    }, "Couldn't change the camera motion."),

    realign: async () => {
      setRealigning(true);
      try {
        await run(async () => { queryClient.setQueryData(scriptKeys.storyboard(project.id), await api.realignStoryboard(project.id)); }, "Couldn't realign the frames.");
      } finally { setRealigning(false); }
    },
  };
}
