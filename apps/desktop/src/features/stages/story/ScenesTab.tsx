import React from "react";
import { Chip, EmptyState, GlassPanel } from "@panelflow/ui-v2";
import type { SceneBlock } from "./storyModel";
import { panelLabel } from "./storyModel";

/** Scenes with their dramatic beats and the events those beats cover. */
export const ScenesTab: React.FC<{ blocks: SceneBlock[]; panels: Array<{ id: string; sequence: number }> }> = ({ blocks, panels }) => {
  if (blocks.length === 0) return <GlassPanel blur={false}><EmptyState title="No scenes yet" description="Run the story analysis to split the chapter into scenes and beats." /></GlassPanel>;
  return (
    <div className="grid grid-cols-1 gap-4">
      {blocks.map(({ scene, beats, events }) => (
        <GlassPanel key={scene.scene_id} blur={false} data-scene-id={scene.scene_id} className="grid grid-cols-1 gap-4 p-5">
          <div className="grid gap-1 border-b border-edge pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-info">{`Scene ${scene.sequence}`}</span>
              <h3 className="font-display text-sm font-semibold text-fg">{scene.title}</h3>
              {scene.boundary_reason && <Chip>{`Boundary: ${scene.boundary_reason}`}</Chip>}
              {scene.panel_start && <span className="font-data text-xs text-fg-faint">{`${panelLabel(scene.panel_start, panels)} to ${panelLabel(scene.panel_end, panels)}`}</span>}
            </div>
            {scene.summary && <p className="text-sm text-fg-dim">{scene.summary}</p>}
          </div>
          <section className="grid grid-cols-1 gap-2" aria-label={`Beats in scene ${scene.sequence}`}>
            <h4 className="text-xs font-medium text-fg-faint">{`Dramatic beats (${beats.length})`}</h4>
            {beats.length === 0 ? <p className="text-sm text-fg-dim">No beats in this scene.</p> : (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {beats.map((beat) => (
                  <div key={beat.beat_id} className="grid gap-1.5 rounded-ctl border border-edge bg-glass p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-fg">{`Beat ${beat.sequence}`}</span>
                      <Chip tone="accent">{beat.dramatic_function}</Chip>
                    </div>
                    <p className="text-sm text-fg-dim">{beat.summary}</p>
                    <p className="text-xs text-fg-faint">{`Importance ${beat.importance} · Intensity ${Math.round((beat.intensity ?? 0) * 100)}%${beat.music_intent ? ` · Music ${beat.music_intent}` : ""}`}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
          {events.length > 0 && (
            <section className="grid grid-cols-1 gap-1.5" aria-label={`Events in scene ${scene.sequence}`}>
              <h4 className="text-xs font-medium text-fg-faint">{`Extracted events (${events.length})`}</h4>
              <ul className="grid gap-1">
                {events.map((event) => (
                  <li key={event.event_id} className="flex flex-wrap items-center gap-2 text-sm text-fg-dim">
                    <Chip>{event.event_type}</Chip>
                    <span>{event.description}</span>
                    <span className="font-data text-xs text-fg-faint">{(event.panel_ids ?? []).map((id) => panelLabel(id, panels)).join(", ")}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </GlassPanel>
      ))}
    </div>
  );
};
