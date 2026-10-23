import React, { useRef, useState, useEffect, useCallback } from "react";
import { resolveSceneTiming, sceneTimelineDuration, trimSceneTiming, insertSceneTiming, alignLinkedNarration } from "./sceneTiming";
import { Icons, Button } from "@panelflow/ui";
import { api } from "@panelflow/api-client";
import { readPanelDrag, panelInsertionIndex, type PanelDragItem } from "./panelDrag";
import type {
  StoryEditorState,
  VideoScene,
  NarrationClip,
  VisualLayer,
  SfxCue,
} from "@panelflow/shared-types";

interface StoryEditorTimelineProps {
  state: StoryEditorState;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
  onSelectScene: (sceneId: string) => void;
  onSelectLayer: (layerId: string, sceneId: string) => void;
  onAddBlankScene: () => void;
  onSplitScene: (sceneId: string, atSec: number) => void;
  onDuplicateScene: (sceneId: string) => void;
  onDeleteScene: (sceneId: string) => void;
  onDeleteLayer?: (layerId: string, sceneId: string) => void;
  projectId?: string;
  canUndo?: boolean;
  canRedo?: boolean;
  onUndo?: () => void;
  onRedo?: () => void;
  onSelectMotionBadge?: (sceneId: string, layerId?: string) => void;
  onOpenNarrationStudio?: (segmentId?: string) => void;
  onOpenAudioLibrary?: (initialType?: "music" | "sfx") => void;
}

import {
  duplicateAudioClip,
  deleteAudioClip,
  applyAudioContractToState,
} from "./audioAdapter";

const timelineTrackAliases: Record<string, string> = {
  Narration: "narration", Visuals: "visuals", "Layer 2": "layer2",
  "Motion / FX": "motion", Music: "music", SFX: "sfx",
};

export function getTimelineTrackState(tracks: StoryEditorState["track_states"], key: string) {
  return tracks?.[key] || tracks?.[timelineTrackAliases[key]] || { visible: true, locked: false };
}

// Write canonical keys for playback, retaining existing legacy aliases.
export function toggleTimelineTrackState(state: StoryEditorState, key: string, prop: "visible" | "locked"): StoryEditorState {
  const current = getTimelineTrackState(state.track_states, key);
  const next = { ...current, [prop]: !current[prop] };
  const alias = timelineTrackAliases[key];
  return {
    ...state,
    track_states: {
      ...state.track_states,
      [key]: next,
      ...(state.track_states?.[alias] ? { [alias]: next } : {}),
    },
  };
}

// Never synthesize a waveform: only measured audio amplitudes carry bars.
const AudioPeaks: React.FC<{ peaks?: number[] }> = ({ peaks }) => {
  const measured = peaks?.length && peaks.every(Number.isFinite);
  return measured ? (
    <span data-waveform="measured" role="img" aria-label="Measured audio waveform" className="pf-timeline-waveform">
      {peaks.map((peak, idx) => <span key={idx} style={{ height: `${Math.max(1, Math.min(1, Math.abs(peak)) * 18)}px` }} />)}
    </span>
  ) : (
    <span data-waveform="unmeasured" role="img" aria-label="Audio waveform not measured" title="Waveform not measured" className="pf-timeline-audio-bar" />
  );
};

export const StoryEditorTimeline: React.FC<StoryEditorTimelineProps> = ({
  state,
  onUpdateState,
  onSelectScene,
  onSelectLayer,
  onAddBlankScene,
  onSplitScene,
  onDuplicateScene,
  onDeleteScene,
  onDeleteLayer,
  projectId,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
  onSelectMotionBadge,
  onOpenNarrationStudio,
  onOpenAudioLibrary,
}) => {
  const rulerRef = useRef<HTMLDivElement>(null);
  const timelineScrollRef = useRef<HTMLDivElement>(null);
  const autoScrollRafRef = useRef<number | null>(null);
  const latestClientXRef = useRef<number>(0);
  const shiftKeyRef = useRef<boolean>(false);
  const snappingEnabled = state.snapping !== false;

  const getLayerImageUrl = (layer: VisualLayer): string => {
    const projId = projectId || state.project_id;
    if (projId && layer.source_panel_id && (!layer.image_url || layer.image_url.includes("/pages/"))) {
      return `${api.getPanelImageUrl(projId, layer.source_panel_id)}?v=${encodeURIComponent(layer.crop_filename || "detected")}`;
    }
    return layer.image_url;
  };

  // Drag and drop states
  const [dragOverInsertIndex, setDragOverInsertIndex] = useState<number | null>(null);
  const [panelInsertIndex, setPanelInsertIndex] = useState<number | null>(null);
  const [pendingPanelDrop, setPendingPanelDrop] = useState<{ items: PanelDragItem[]; index: number } | null>(null);
  const duplicateDialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!pendingPanelDrop) return;
    const dialog = duplicateDialogRef.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute("open", "");
    return () => { if (dialog?.open) dialog.close?.(); };
  }, [pendingPanelDrop]);
  useEffect(() => {
    // Source cards live outside the timeline; cancellation ends on the source.
    const clearInsertion = () => setPanelInsertIndex(null);
    window.addEventListener("dragend", clearInsertion);
    return () => window.removeEventListener("dragend", clearInsertion);
  }, []);
  const [dragOverSceneId, setDragOverSceneId] = useState<string | null>(null);
  const [dragOverLayerId, setDragOverLayerId] = useState<string | null>(null);
  const [dragOverNarrationId, setDragOverNarrationId] = useState<string | null>(null);
  const [dragOverMotionSceneId, setDragOverMotionSceneId] = useState<string | null>(null);

  // Trimming interaction state for scenes, layers, bgm, and sfx
  const [trimming, setTrimming] = useState<{
    type: "scene" | "layer" | "bgm" | "sfx";
    id: string;
    sceneId?: string;
    edge: "left" | "right";
    startMouseX: number;
    initialDuration: number;
    initialStartOffset?: number;
    initialStartTimeSec?: number;
  } | null>(null);

  // Narration drag-to-shift state
  const [draggingNarration, setDraggingNarration] = useState<{
    id: string;
    startMouseX: number;
    initialStartSec: number;
  } | null>(null);

  // Audio clip drag-to-shift state (BGM and SFX)
  const [draggingAudioClip, setDraggingAudioClip] = useState<{
    type: "bgm" | "sfx";
    id: string;
    startMouseX: number;
    initialStartSec: number;
  } | null>(null);

  const timedScenes = resolveSceneTiming(state.scenes);
  const totalDurationSec = sceneTimelineDuration(timedScenes);

  // Pixels per second based on zoom slider (zoom_level 50 to 250)
  const pxPerSec = 40 * (state.zoom_level / 100);
  const totalTimelineWidthPx = Math.max(1100, Math.max(30, totalDurationSec) * pxPerSec + 200);

  // Mouse Move listener for live trimming & narration shifting
  useEffect(() => {
    const handleWindowMouseMove = (e: MouseEvent) => {
      if (trimming) {
        const deltaPx = e.clientX - trimming.startMouseX;
        const deltaSec = deltaPx / pxPerSec;

        if (trimming.type === "scene") {
          const scene = state.scenes.find((s) => s.id === trimming.id);
          if (!scene) return;

          let nextDuration = trimming.initialDuration;
          if (trimming.edge === "right") {
            nextDuration = Math.max(0.8, Math.round((trimming.initialDuration + deltaSec) * 10) / 10);
          } else {
            nextDuration = Math.max(0.8, Math.round((trimming.initialDuration - deltaSec) * 10) / 10);
          }

          onUpdateState((prev) => trimSceneTiming(prev, trimming.id, nextDuration));
        } else if (trimming.type === "layer" && trimming.sceneId) {
          const sceneId = trimming.sceneId;
          const layerId = trimming.id;

          onUpdateState((prev) => ({
            ...prev,
            scenes: prev.scenes.map((sc) => {
              if (sc.id !== sceneId) return sc;
              return {
                ...sc,
                layers: sc.layers.map((ly) => {
                  if (ly.id !== layerId || ly.locked) return ly;
                  const currentStart = trimming.initialStartOffset ?? 0;
                  const currentDur = trimming.initialDuration;

                  if (trimming.edge === "left") {
                    const newStart = Math.max(0, Math.min(currentStart + currentDur - 0.4, currentStart + deltaSec));
                    const newDur = Math.max(0.4, currentDur - (newStart - currentStart));
                    return {
                      ...ly,
                      start_offset_sec: Math.round(newStart * 10) / 10,
                      duration_sec: Math.round(newDur * 10) / 10,
                    };
                  } else {
                    const newDur = Math.max(0.4, Math.min(sc.duration_sec - currentStart, currentDur + deltaSec));
                    return {
                      ...ly,
                      duration_sec: Math.round(newDur * 10) / 10,
                    };
                  }
                }),
              };
            }),
          }));
        } else if (trimming.type === "bgm") {
          onUpdateState((prev) => {
            const deltaPx = e.clientX - trimming.startMouseX;
            const deltaSec = deltaPx / pxPerSec;
            return {
              ...prev,
              bgm_tracks: prev.bgm_tracks.map((b) => {
                if (b.id !== trimming.id) return b;
                if (trimming.edge === "left") {
                  const initStart = trimming.initialStartTimeSec ?? b.start_time_sec;
                  const initDur = trimming.initialDuration;
                  const newStart = Math.max(0, Math.min(initStart + initDur - 0.5, initStart + deltaSec));
                  const newDur = Math.max(0.5, initDur - (newStart - initStart));
                  return {
                    ...b,
                    start_time_sec: Math.round(newStart * 10) / 10,
                    duration_sec: Math.round(newDur * 10) / 10,
                  };
                } else {
                  const newDur = Math.max(0.5, Math.round((trimming.initialDuration + deltaSec) * 10) / 10);
                  return { ...b, duration_sec: newDur };
                }
              }),
            };
          });
        } else if (trimming.type === "sfx") {
          onUpdateState((prev) => {
            const deltaPx = e.clientX - trimming.startMouseX;
            const deltaSec = deltaPx / pxPerSec;
            return {
              ...prev,
              sfx_cues: (prev.sfx_cues || []).map((s) => {
                if (s.id !== trimming.id) return s;
                if (trimming.edge === "left") {
                  const initStart = trimming.initialStartTimeSec ?? s.start_time_sec;
                  const initDur = trimming.initialDuration;
                  const newStart = Math.max(0, Math.min(initStart + initDur - 0.3, initStart + deltaSec));
                  const newDur = Math.max(0.3, initDur - (newStart - initStart));
                  return {
                    ...s,
                    start_time_sec: Math.round(newStart * 10) / 10,
                    duration_sec: Math.round(newDur * 10) / 10,
                  };
                } else {
                  const newDur = Math.max(0.3, Math.round((trimming.initialDuration + deltaSec) * 10) / 10);
                  return { ...s, duration_sec: newDur };
                }
              }),
            };
          });
        }
      } else if (draggingNarration) {
        const deltaPx = e.clientX - draggingNarration.startMouseX;
        const deltaSec = deltaPx / pxPerSec;
        const newStart = Math.max(0, Math.round((draggingNarration.initialStartSec + deltaSec) * 10) / 10);

        onUpdateState((prev) => ({
          ...prev,
          narration_clips: prev.narration_clips.map((n) => {
            if (n.id !== draggingNarration.id) return n;
            const parent = n.linked_to_scene !== false && n.scene_id ? resolveSceneTiming(prev.scenes).find((s) => s.id === n.scene_id) : undefined;
            const boundedStart = parent ? Math.max(parent.start_time_sec, newStart) : newStart;
            const newOffset = parent ? Math.round((boundedStart - parent.start_time_sec) * 10) / 10 : (n.scene_offset_sec || 0);
            return {
              ...n,
              start_time_sec: boundedStart,
              scene_offset_sec: newOffset,
            };
          }),
        }));
      } else if (draggingAudioClip) {
        const deltaPx = e.clientX - draggingAudioClip.startMouseX;
        const deltaSec = deltaPx / pxPerSec;
        let nextStart = Math.max(0, Math.round((draggingAudioClip.initialStartSec + deltaSec) * 10) / 10);

        // Magnetic snapping
        if (snappingEnabled) {
          if (Math.abs(nextStart - state.playhead_sec) < 0.25) {
            nextStart = state.playhead_sec;
          }
          for (const sc of resolveSceneTiming(state.scenes)) {
            let run = sc.start_time_sec;
            if (Math.abs(nextStart - run) < 0.25) {
              nextStart = run;
              break;
            }
            run += sc.duration_sec;
            if (Math.abs(nextStart - run) < 0.25) {
              nextStart = run;
              break;
            }
          }
        }

        if (draggingAudioClip.type === "bgm") {
          onUpdateState((prev) => ({
            ...prev,
            bgm_tracks: prev.bgm_tracks.map((b) =>
              b.id === draggingAudioClip.id ? { ...b, start_time_sec: nextStart } : b
            ),
          }));
        } else {
          onUpdateState((prev) => ({
            ...prev,
            sfx_cues: (prev.sfx_cues || []).map((s) =>
              s.id === draggingAudioClip.id ? { ...s, start_time_sec: nextStart } : s
            ),
          }));
        }
      }
    };

    const handleWindowMouseUp = () => {
      if (trimming) setTrimming(null);
      if (draggingNarration) setDraggingNarration(null);
      if (draggingAudioClip) setDraggingAudioClip(null);
    };

    if (trimming || draggingNarration || draggingAudioClip) {
      window.addEventListener("mousemove", handleWindowMouseMove);
      window.addEventListener("mouseup", handleWindowMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleWindowMouseMove);
      window.removeEventListener("mouseup", handleWindowMouseUp);
    };
  }, [trimming, draggingNarration, draggingAudioClip, snappingEnabled, state.playhead_sec, pxPerSec, state.scenes, onUpdateState]);

  // Smooth Scrubber Drag State
  const [isScrubbing, setIsScrubbing] = useState<boolean>(false);
  const wasPlayingBeforeScrubRef = useRef<boolean>(false);
  const scrubRafRef = useRef<number | null>(null);
  const lastScrubSecRef = useRef<number>(state.playhead_sec);

  // Compute precise time from pointer clientX with smooth thresholding
  const getTimeFromClientX = useCallback(
    (clientX: number, snap: boolean = snappingEnabled) => {
      const scrollContainer = timelineScrollRef.current;
      const ruler = rulerRef.current;
      let clickX = 0;
      if (scrollContainer && ruler) {
        const containerRect = scrollContainer.getBoundingClientRect();
        clickX = (clientX - containerRect.left) + scrollContainer.scrollLeft;
      } else if (ruler) {
        clickX = clientX - ruler.getBoundingClientRect().left;
      }
      let targetSec = Math.max(0, Math.min(totalDurationSec, clickX / pxPerSec));

      if (snap) {
        // Tight 0.12s threshold so snapping never feels sticky or stuttery
        for (const scene of resolveSceneTiming(state.scenes)) {
          let cumulative = scene.start_time_sec;
          if (Math.abs(targetSec - cumulative) < 0.12) {
            targetSec = cumulative;
            break;
          }
          cumulative += scene.duration_sec;
          if (Math.abs(targetSec - cumulative) < 0.12) {
            targetSec = cumulative;
            break;
          }
        }
      }
      return Math.round(targetSec * 1000) / 1000;
    },
    [totalDurationSec, pxPerSec, snappingEnabled, state.scenes]
  );

  // Smooth Scrubber Drag Handler for playhead diamond, line, and ruler
  const handleStartScrub = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return; // Only primary button
      e.preventDefault();
      e.stopPropagation();

      wasPlayingBeforeScrubRef.current = state.is_playing;
      if (state.is_playing) {
        onUpdateState((s) => ({ ...s, is_playing: false }));
      }

      setIsScrubbing(true);
      latestClientXRef.current = e.clientX;
      shiftKeyRef.current = e.shiftKey;

      const calcSec = (clientX: number, snap: boolean) => {
        const scrollContainer = timelineScrollRef.current;
        const ruler = rulerRef.current;
        let clickX = 0;
        if (scrollContainer && ruler) {
          const containerRect = scrollContainer.getBoundingClientRect();
          clickX = (clientX - containerRect.left) + scrollContainer.scrollLeft;
        } else if (ruler) {
          clickX = clientX - ruler.getBoundingClientRect().left;
        }
        let targetSec = Math.max(0, Math.min(totalDurationSec, clickX / pxPerSec));
        if (snap) {
          for (const scene of resolveSceneTiming(state.scenes)) {
            let cumulative = scene.start_time_sec;
            if (Math.abs(targetSec - cumulative) < 0.12) {
              targetSec = cumulative;
              break;
            }
            cumulative += scene.duration_sec;
            if (Math.abs(targetSec - cumulative) < 0.12) {
              targetSec = cumulative;
              break;
            }
          }
        }
        return Math.round(targetSec * 1000) / 1000;
      };

      const initialSec = calcSec(e.clientX, snappingEnabled && !e.shiftKey);
      lastScrubSecRef.current = initialSec;
      onUpdateState((s) => ({ ...s, playhead_sec: initialSec }));

      // Auto-scroll timeline while scrubbing near or past container edges
      const autoScrollLoop = () => {
        const scrollContainer = timelineScrollRef.current;
        if (scrollContainer) {
          const rect = scrollContainer.getBoundingClientRect();
          const clientX = latestClientXRef.current;
          const edgeThreshold = 60;
          let scrollDelta = 0;

          if (clientX > rect.right - edgeThreshold) {
            const distance = Math.max(1, clientX - (rect.right - edgeThreshold));
            scrollDelta = Math.min(30, Math.max(4, distance * 0.35));
          } else if (clientX < rect.left + edgeThreshold) {
            const distance = Math.max(1, (rect.left + edgeThreshold) - clientX);
            scrollDelta = -Math.min(30, Math.max(4, distance * 0.35));
          }

          if (scrollDelta !== 0) {
            const prevScroll = scrollContainer.scrollLeft;
            scrollContainer.scrollLeft += scrollDelta;
            if (scrollContainer.scrollLeft !== prevScroll) {
              const sec = calcSec(clientX, snappingEnabled && !shiftKeyRef.current);
              lastScrubSecRef.current = sec;
              onUpdateState((s) => ({ ...s, playhead_sec: sec }));
            }
          }
        }
        autoScrollRafRef.current = requestAnimationFrame(autoScrollLoop);
      };
      autoScrollRafRef.current = requestAnimationFrame(autoScrollLoop);

      const handlePointerMove = (ev: PointerEvent) => {
        ev.preventDefault();
        latestClientXRef.current = ev.clientX;
        shiftKeyRef.current = ev.shiftKey;
        if (scrubRafRef.current) cancelAnimationFrame(scrubRafRef.current);
        scrubRafRef.current = requestAnimationFrame(() => {
          const sec = calcSec(ev.clientX, snappingEnabled && !ev.shiftKey);
          lastScrubSecRef.current = sec;
          onUpdateState((s) => ({ ...s, playhead_sec: sec }));
        });
      };

      const handlePointerUp = (ev: PointerEvent) => {
        ev.preventDefault();
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
        if (scrubRafRef.current) {
          cancelAnimationFrame(scrubRafRef.current);
          scrubRafRef.current = null;
        }
        if (autoScrollRafRef.current) {
          cancelAnimationFrame(autoScrollRafRef.current);
          autoScrollRafRef.current = null;
        }
        setIsScrubbing(false);
        onUpdateState((s) => ({
          ...s,
          playhead_sec: Math.round(lastScrubSecRef.current * 100) / 100,
        }));
      };

      window.addEventListener("pointermove", handlePointerMove, { passive: false });
      window.addEventListener("pointerup", handlePointerUp);
    },
    [state.is_playing, totalDurationSec, pxPerSec, state.scenes, snappingEnabled, onUpdateState]
  );

  // Auto-scroll timeline to follow playhead during playback
  useEffect(() => {
    if (!state.is_playing || isScrubbing) return;
    const scrollEl = timelineScrollRef.current;
    if (!scrollEl) return;
    const playheadPx = state.playhead_sec * pxPerSec;
    const visibleStart = scrollEl.scrollLeft;
    const visibleEnd = visibleStart + scrollEl.clientWidth;
    if (playheadPx > visibleEnd - 80) {
      scrollEl.scrollLeft = playheadPx - 100;
    } else if (playheadPx < visibleStart) {
      scrollEl.scrollLeft = Math.max(0, playheadPx - 50);
    }
  }, [state.playhead_sec, state.is_playing, isScrubbing, pxPerSec]);

  useEffect(() => {
    return () => {
      if (scrubRafRef.current) cancelAnimationFrame(scrubRafRef.current);
      if (autoScrollRafRef.current) cancelAnimationFrame(autoScrollRafRef.current);
    };
  }, []);

  // Reorder scenes state update
  const handleReorderScenes = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return;
    onUpdateState((prev) => {
      const copy = resolveSceneTiming(prev.scenes);
      const [moved] = copy.splice(fromIndex, 1);
      if (!moved) return prev;
      const target = toIndex > fromIndex ? toIndex - 1 : toIndex;
      const resynced = insertSceneTiming(copy, moved, target, prev.ripple_edit !== false);
      const resyncedNarr = alignLinkedNarration(resynced, prev.narration_clips, prev.scenes);

      return {
        ...prev,
        scenes: resynced,
        narration_clips: resyncedNarr,
        selected_object: { type: "scene", id: moved.id },
      };
    });
  };

  // Swap positions of two scenes directly on drop
  const handleSwapScenes = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return;
    onUpdateState((prev) => {
      const copy = resolveSceneTiming(prev.scenes);
      if (!copy[fromIndex] || !copy[toIndex]) return prev;
      const sceneA = copy[fromIndex];
      const sceneB = copy[toIndex];

      if (prev.ripple_edit !== false) {
        copy[fromIndex] = sceneB;
        copy[toIndex] = sceneA;
        copy.forEach((sc, i) => {
          sc.sequence = i + 1;
        });
        let currentSec = 0;
        copy.forEach((sc) => {
          sc.start_time_sec = currentSec;
          currentSec += sc.duration_sec;
        });
      } else {
        const startA = sceneA.start_time_sec;
        const startB = sceneB.start_time_sec;
        sceneA.start_time_sec = startB;
        sceneB.start_time_sec = startA;
        copy[fromIndex] = sceneB;
        copy[toIndex] = sceneA;
        copy.sort((a, b) => a.start_time_sec - b.start_time_sec);
        copy.forEach((sc, i) => {
          sc.sequence = i + 1;
        });
      }

      const resyncedNarr = alignLinkedNarration(copy, prev.narration_clips, prev.scenes);
      return {
        ...prev,
        scenes: copy,
        narration_clips: resyncedNarr,
        selected_object: { type: "scene", id: sceneA.id },
      };
    });
  };

  // Insert new scene from panel at index
  const handleInsertSceneFromPanel = (input: PanelDragItem | PanelDragItem[], atIndex: number) => {
    const panels = Array.isArray(input) ? input : [input];
    onUpdateState((prev) => {
      const previousScenes = resolveSceneTiming(prev.scenes);
      const additions: VideoScene[] = [];
      for (const panelData of panels) {
        const projId = projectId || prev.project_id;
        const resolvedImg = panelData.panelId && projId
          ? `${api.getPanelImageUrl(projId, panelData.panelId)}?v=${encodeURIComponent(panelData.cropFilename || "detected")}`
          : panelData.imageUrl;
        const newSceneId = `scene_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const newLayerId = `layer_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const newLayer: VisualLayer = {
          id: newLayerId,
          source_page_id: panelData.pageId || "",
          source_panel_id: panelData.panelId,
          image_url: resolvedImg || "",
          page_sequence: panelData.pageSequence || 1,
          crop: panelData.crop || { x: 0, y: 0, width: 1, height: 1 },
          transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
          motion_preset: "slow_zoom_in",
          name: panelData.name || `Panel #${panelData.pageSequence}`,
          start_offset_sec: 0,
          duration_sec: 4.0,
        };

        const newScene: VideoScene = {
          id: newSceneId,
          sequence: atIndex + 1,
          title: `Scene — ${newLayer.name}`,
          duration_sec: 4.0,
          start_time_sec: 0,
          layers: [newLayer],
          transition_in: atIndex === 0 ? "fade" : "none",
        };

        additions.push(newScene);
      }
      if (!additions.length) return prev;
      const at = Math.max(0, Math.min(atIndex, previousScenes.length));
      const remaining = previousScenes;
      // Explicit insertion makes room even when trim ripple is off. Preserve gaps
      // and earlier anchors; only push following scenes that would overlap.
      const start = at > 0 ? remaining[at - 1].start_time_sec + remaining[at - 1].duration_sec : 0;
      let end = start;
      const placed = additions.map(scene => {
        const result = { ...scene, start_time_sec: end };
        end += scene.duration_sec;
        return result;
      });
      const combined = [...remaining.slice(0, at), ...placed, ...remaining.slice(at)];
      let cursor = 0;
      const resynced = combined.map((scene, index) => {
        const startTime = prev.ripple_edit !== false ? cursor : Math.max(cursor, scene.start_time_sec);
        cursor = startTime + scene.duration_sec;
        return { ...scene, sequence: index + 1, start_time_sec: startTime };
      });

      return {
        ...prev,
        scenes: resynced,
        narration_clips: alignLinkedNarration(resynced, prev.narration_clips, prev.scenes),
        selected_object: { type: "scene", id: placed[0].id },
        playhead_sec: resynced.find(scene => scene.id === placed[0].id)!.start_time_sec,
      };
    });
  };

  // Add layer to existing scene from panel
  const handleAddLayerToScene = (panelData: any, sceneId: string) => {
    onUpdateState((prev) => {
      const targetScene = prev.scenes.find((s) => s.id === sceneId);
      if (!targetScene) return prev;
      const projId = projectId || prev.project_id;
      const resolvedImg = panelData.panelId && projId
        ? `${api.getPanelImageUrl(projId, panelData.panelId)}?v=${encodeURIComponent(panelData.cropFilename || "detected")}`
        : panelData.imageUrl;
      const newLayerId = `layer_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const newLayer: VisualLayer = {
        id: newLayerId,
        source_page_id: panelData.pageId,
        source_panel_id: panelData.panelId,
        image_url: resolvedImg,
        page_sequence: panelData.pageSequence,
        crop: panelData.crop,
        transform: {
          x: 0,
          y: 0,
          scale: 1.0,
          rotation: 0,
          opacity: 1.0,
          z_index: targetScene.layers.length + 1,
        },
        motion_preset: "slow_zoom_in",
        name: panelData.name || `Panel #${panelData.pageSequence}`,
        start_offset_sec: 0,
        duration_sec: targetScene.duration_sec,
      };

      return {
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== sceneId) return sc;
          return {
            ...sc,
            layers: [...sc.layers, newLayer],
          };
        }),
        selected_object: { type: "layer", id: newLayerId, sceneId },
      };
    });
  };

  // Move layer from one scene to another
  const handleMoveLayer = (layerId: string, fromSceneId: string, toSceneId: string) => {
    onUpdateState((prev) => {
      const fromScene = prev.scenes.find((s) => s.id === fromSceneId);
      const toScene = prev.scenes.find((s) => s.id === toSceneId);
      if (!fromScene || !toScene || fromSceneId === toSceneId) return prev;
      const layer = fromScene.layers.find((l) => l.id === layerId);
      if (!layer) return prev;

      return {
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id === fromSceneId) {
            return { ...sc, layers: sc.layers.filter((l) => l.id !== layerId) };
          }
          if (sc.id === toSceneId) {
            return {
              ...sc,
              layers: [
                ...sc.layers,
                {
                  ...layer,
                  start_offset_sec: 0,
                  duration_sec: sc.duration_sec,
                  transform: { ...layer.transform, z_index: sc.layers.length + 1 },
                },
              ],
            };
          }
          return sc;
        }),
        selected_object: { type: "layer", id: layerId, sceneId: toSceneId },
      };
    });
  };

  // Replace the visual panel of an existing scene
  const handleReplaceSceneVisual = (panelData: any, sceneId: string) => {
    onUpdateState((prev) => {
      const targetScene = prev.scenes.find((s) => s.id === sceneId);
      if (!targetScene) return prev;
      const projId = projectId || prev.project_id;
      const resolvedImg =
        panelData.panelId && projId
          ? `${api.getPanelImageUrl(projId, panelData.panelId)}?v=${encodeURIComponent(panelData.cropFilename || "detected")}`
          : panelData.imageUrl;

      const newLayerName = panelData.name || `Panel #${panelData.pageSequence || 1}`;

      let updatedLayers: VisualLayer[];
      if (targetScene.layers.length > 0) {
        updatedLayers = targetScene.layers.map((ly, idx) => {
          if (idx === 0) {
            return {
              ...ly,
              source_page_id: panelData.pageId,
              source_panel_id: panelData.panelId,
              image_url: resolvedImg,
              page_sequence: panelData.pageSequence,
              crop: panelData.crop,
              name: newLayerName,
            };
          }
          return ly;
        });
      } else {
        const newLayerId = `layer_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        updatedLayers = [
          {
            id: newLayerId,
            source_page_id: panelData.pageId,
            source_panel_id: panelData.panelId,
            image_url: resolvedImg,
            page_sequence: panelData.pageSequence,
            crop: panelData.crop,
            transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
            motion_preset: "slow_zoom_in",
            name: newLayerName,
            start_offset_sec: 0,
            duration_sec: targetScene.duration_sec,
          },
        ];
      }

      return {
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== sceneId) return sc;
          return {
            ...sc,
            title: `Scene — ${newLayerName}`,
            layers: updatedLayers,
          };
        }),
        selected_object: { type: "scene", id: sceneId },
      };
    });
  };

  // Replace the image/visual data of a specific layer
  const handleReplaceLayerVisual = (panelData: any, layerId: string, sceneId: string) => {
    onUpdateState((prev) => {
      const projId = projectId || prev.project_id;
      const resolvedImg =
        panelData.panelId && projId
          ? `${api.getPanelImageUrl(projId, panelData.panelId)}?v=${encodeURIComponent(panelData.cropFilename || "detected")}`
          : panelData.imageUrl;

      return {
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== sceneId) return sc;
          return {
            ...sc,
            layers: sc.layers.map((ly) => {
              if (ly.id !== layerId) return ly;
              return {
                ...ly,
                source_page_id: panelData.pageId,
                source_panel_id: panelData.panelId,
                image_url: resolvedImg,
                page_sequence: panelData.pageSequence,
                crop: panelData.crop,
                name: panelData.name || `Panel #${panelData.pageSequence || 1}`,
              };
            }),
          };
        }),
        selected_object: { type: "layer", id: layerId, sceneId },
      };
    });
  };

  // Swap or replace two visual layers across or within scenes
  const handleSwapOrReplaceLayers = (
    fromLayerId: string,
    fromSceneId: string,
    targetLayerId: string,
    targetSceneId: string
  ) => {
    if (fromLayerId === targetLayerId) return;
    onUpdateState((prev) => {
      const fromScene = prev.scenes.find((s) => s.id === fromSceneId);
      const targetScene = prev.scenes.find((s) => s.id === targetSceneId);
      if (!fromScene || !targetScene) return prev;

      const fromLayer = fromScene.layers.find((l) => l.id === fromLayerId);
      const targetLayer = targetScene.layers.find((l) => l.id === targetLayerId);
      if (!fromLayer || !targetLayer) return prev;

      if (fromSceneId === targetSceneId) {
        return {
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id !== fromSceneId) return sc;
            const newLayers = [...sc.layers];
            const iA = newLayers.findIndex((l) => l.id === fromLayerId);
            const iB = newLayers.findIndex((l) => l.id === targetLayerId);
            if (iA >= 0 && iB >= 0) {
              const temp = newLayers[iA];
              newLayers[iA] = newLayers[iB];
              newLayers[iB] = temp;
            }
            return { ...sc, layers: newLayers };
          }),
          selected_object: { type: "layer", id: fromLayerId, sceneId: targetSceneId },
        };
      } else {
        const adjustedFromLayer: VisualLayer = {
          ...fromLayer,
          start_offset_sec: 0,
          duration_sec: targetScene.duration_sec,
        };
        const adjustedTargetLayer: VisualLayer = {
          ...targetLayer,
          start_offset_sec: 0,
          duration_sec: fromScene.duration_sec,
        };

        return {
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id === fromSceneId) {
              return {
                ...sc,
                layers: sc.layers.map((l) => (l.id === fromLayerId ? adjustedTargetLayer : l)),
              };
            }
            if (sc.id === targetSceneId) {
              return {
                ...sc,
                layers: sc.layers.map((l) => (l.id === targetLayerId ? adjustedFromLayer : l)),
              };
            }
            return sc;
          }),
          selected_object: { type: "layer", id: fromLayerId, sceneId: targetSceneId },
        };
      }
    });
  };

  // Swap positions & timing of two narration clips
  const handleSwapNarrationClips = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    onUpdateState((prev) => {
      const fromNarr = prev.narration_clips.find((n) => n.id === fromId);
      const toNarr = prev.narration_clips.find((n) => n.id === toId);
      if (!fromNarr || !toNarr) return prev;

      const fromTime = fromNarr.start_time_sec;
      const fromSceneId = fromNarr.scene_id;
      const fromOffset = fromNarr.scene_offset_sec;
      const fromLinked = fromNarr.linked_to_scene;

      const toTime = toNarr.start_time_sec;
      const toSceneId = toNarr.scene_id;
      const toOffset = toNarr.scene_offset_sec;
      const toLinked = toNarr.linked_to_scene;

      const updated = prev.narration_clips.map((n) => {
        if (n.id === fromId) {
          return {
            ...n,
            start_time_sec: toTime,
            scene_id: toSceneId,
            scene_offset_sec: toOffset,
            linked_to_scene: toLinked,
          };
        }
        if (n.id === toId) {
          return {
            ...n,
            start_time_sec: fromTime,
            scene_id: fromSceneId,
            scene_offset_sec: fromOffset,
            linked_to_scene: fromLinked,
          };
        }
        return n;
      });

      return {
        ...prev,
        narration_clips: updated.sort((a, b) => a.start_time_sec - b.start_time_sec),
        selected_object: { type: "narration", id: fromId },
      };
    });
  };

  // Attach/link narration to a scene when dropped onto a scene clip
  const handleAttachNarrationToScene = (narrationId: string, targetSceneId: string) => {
    onUpdateState((prev) => {
      const targetScene = resolveSceneTiming(prev.scenes).find((s) => s.id === targetSceneId);
      if (!targetScene) return prev;

      const updated = prev.narration_clips.map((n) => {
        if (n.id !== narrationId) return n;
        return {
          ...n,
          scene_id: targetSceneId,
          start_time_sec: targetScene.start_time_sec,
          scene_offset_sec: 0,
          linked_to_scene: true,
        };
      });

      return {
        ...prev,
        narration_clips: updated.sort((a, b) => a.start_time_sec - b.start_time_sec),
        selected_object: { type: "narration", id: narrationId },
      };
    });
  };

  // Transfer, replace, or swap motion effects between scenes
  const handleTransferOrSwapMotion = (motionData: any, targetSceneId: string) => {
    const fromSceneId = motionData.fromSceneId;
    if (fromSceneId === targetSceneId) return;

    onUpdateState((prev) => {
      const fromScene = prev.scenes.find((s) => s.id === fromSceneId);
      const targetScene = prev.scenes.find((s) => s.id === targetSceneId);
      if (!targetScene) return prev;

      if (motionData.type === "camera") {
        const sourceCamera = motionData.camera || fromScene?.camera;
        const targetCamera = targetScene.camera;

        return {
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id === targetSceneId) {
              return { ...sc, camera: sourceCamera ? { ...sourceCamera } : undefined };
            }
            if (fromScene && sc.id === fromSceneId) {
              return { ...sc, camera: targetCamera ? { ...targetCamera } : { preset: "static" as const } };
            }
            return sc;
          }),
          selected_object: { type: "scene", id: targetSceneId },
        };
      }

      // type === "layer_motion"
      const targetMotionLayer =
        targetScene.layers.find(
          (l) => (l.motion_preset && l.motion_preset !== "none") || l.animation_config?.preset === "custom"
        ) || targetScene.layers[0];

      const fromLayer = fromScene?.layers.find((l) => l.id === motionData.layerId);
      const targetPrevPreset = targetMotionLayer?.motion_preset;
      const targetPrevAnim = targetMotionLayer?.animation_config;

      return {
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id === targetSceneId) {
            if (sc.layers.length === 0) return sc;
            const targetLId = targetMotionLayer?.id || sc.layers[0].id;
            return {
              ...sc,
              layers: sc.layers.map((ly) => {
                if (ly.id !== targetLId) return ly;
                return {
                  ...ly,
                  motion_preset: motionData.motionPreset,
                  animation_config: motionData.animationConfig ? { ...motionData.animationConfig } : undefined,
                };
              }),
            };
          }
          if (fromScene && sc.id === fromSceneId && fromLayer) {
            return {
              ...sc,
              layers: sc.layers.map((ly) => {
                if (ly.id !== fromLayer.id) return ly;
                return {
                  ...ly,
                  motion_preset: targetPrevPreset || "none",
                  animation_config: targetPrevAnim ? { ...targetPrevAnim } : undefined,
                };
              }),
            };
          }
          return sc;
        }),
        selected_object: { type: "scene", id: targetSceneId },
      };
    });
  };

  // Toggle narration link
  const handleToggleNarrationLink = (narrationId: string) => {
    onUpdateState((prev) => ({
      ...prev,
      narration_clips: prev.narration_clips.map((n) => {
        if (n.id !== narrationId) return n;
        const willBeLinked = n.linked_to_scene === false;
        if (!willBeLinked) {
          // Unlinking preserves exact absolute timeline position
          return {
            ...n,
            linked_to_scene: false,
          };
        }
        // Relinking: find parent scene under or nearest start_time_sec
        const parentScene = prev.scenes.find(
          (s) => n.start_time_sec >= s.start_time_sec && n.start_time_sec < s.start_time_sec + s.duration_sec
        ) || prev.scenes[0];
        const offset = parentScene ? Math.max(0, Math.round((n.start_time_sec - parentScene.start_time_sec) * 10) / 10) : 0;
        return {
          ...n,
          linked_to_scene: true,
          scene_id: parentScene?.id,
          scene_offset_sec: offset,
        };
      }),
    }));
  };

  // Generate tick markers every 5 seconds
  const tickIntervalSec = 5;
  const ticksCount = Math.ceil(Math.max(30, totalDurationSec) / tickIntervalSec) + 1;

  const formatRulerTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const selectedSceneId =
    state.selected_object?.type === "scene"
      ? state.selected_object.id
      : state.selected_object?.type === "layer"
      ? state.selected_object.sceneId
      : null;

  const isAdvancedMode = state.mode === "advanced";

  const toggleTrack = (trackName: string, prop: "visible" | "locked") => {
    onUpdateState((prev) => toggleTimelineTrackState(prev, trackName, prop));
  };

  const visualDropEffect = (transfer: DataTransfer) =>
    transfer.types.some(
      (type) =>
        type === "application/panelflow-scene-reorder" ||
        type === "application/panelflow-layer-move" ||
        type === "application/panelflow-narration-reorder" ||
        type === "application/panelflow-motion-move"
    )
      ? "move"
      : "copy";

  const laneProps = (key: string) => {
    const track = getTimelineTrackState(state.track_states, key);
    const guardEditing = (e: React.SyntheticEvent) => {
      const mouseDown = e.type === "mousedown";
      if (track.locked || !track.visible || (mouseDown && (e as React.MouseEvent).button !== 0) || (e.type === "dragstart" && trimming)) {
        e.preventDefault();
        e.stopPropagation();
      } else if (mouseDown && (e.target as HTMLElement).closest?.("[data-timeline-trim]")) {
        // A trim is a mouse gesture, never the ancestor clip's native HTML drag.
        e.preventDefault();
      }
    };
    return {
      "data-visible": track.visible,
      "data-locked": track.locked,
      onPointerDown: (e: React.PointerEvent) => {
        // Clips keep their own editing gesture; empty lane space still scrubs.
        if (e.target !== e.currentTarget || track.locked || !track.visible) e.stopPropagation();
      },
      onMouseDownCapture: guardEditing,
      onDragStartCapture: guardEditing,
      onDropCapture: guardEditing,
      onClickCapture: guardEditing,
      onDoubleClickCapture: guardEditing,
    };
  };

  // Keep existing SFX available without inventing audio assets.
  const sfxList: SfxCue[] = state.sfx_cues || [];
  const showSfx = isAdvancedMode || sfxList.length > 0;

  const presetLabels: Record<string, string> = {
    slow_zoom_in: "Zoom In",
    slow_zoom_out: "Zoom Out",
    pan_left: "Pan Left",
    pan_right: "Pan Right",
    pan_up: "Pan Up",
    pan_down: "Pan Down",
    diagonal_pan: "Diag Pan",
    slide_in_left: "Slide L",
    slide_in_right: "Slide R",
    slide_in_top: "Slide Top",
    slide_in_bottom: "Slide Btm",
    slide_out: "Slide Out",
    fade_in: "Fade In",
    fade_out: "Fade Out",
    fade_in_out: "Fade In/Out",
    opacity_reveal: "Reveal",
    shake_impact: "Impact Shake",
    move: "Move",
    rise: "Rise",
    fall: "Fall",
    scale_up: "Scale Up",
    scale_down: "Scale Down",
    rotate: "Rotate",
    flash: "Flash",
    blur: "Blur FX",
    cross_dissolve: "Dissolve",
    wipe: "Wipe FX",
    custom: "Keyframes",
  };

  return (
    <div className="pf-editor-timeline bg-zinc-950 flex flex-col select-none shrink-0 overflow-hidden font-sans"
      style={{ height: showSfx ? 282 : 246 }}>
      {pendingPanelDrop && <dialog ref={duplicateDialogRef} aria-label="Add duplicate panels?" aria-describedby="duplicate-panel-message"
        className="fixed inset-0 m-auto w-[min(420px,90vw)] rounded-xl border border-zinc-700 bg-zinc-950 p-5 text-zinc-100 shadow-2xl backdrop:bg-black/70"
        onCancel={event => { event.preventDefault(); setPendingPanelDrop(null); }}>
        <h2 className="text-base font-semibold mb-3">{pendingPanelDrop.items.length === 1 ? "Add duplicate panel?" : "Add duplicate panels?"}</h2>
        <p id="duplicate-panel-message" className="text-sm text-zinc-300 mb-5">
          {pendingPanelDrop.items.length === 1
            ? "Are you sure you want to add this duplicate panel to the timeline?"
            : "Some selected panels are already on the timeline. Are you sure you want to add the selected panels, including duplicates?"}
        </p>
        <div className="flex justify-end gap-2">
          <button type="button" autoFocus data-cancel-duplicate-panels className="rounded-md border border-zinc-600 px-3 py-2 text-sm hover:bg-zinc-800"
            onClick={() => setPendingPanelDrop(null)}>Cancel</button>
          <button type="button" data-confirm-duplicate-panels className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500"
            onClick={() => {
              const pending = pendingPanelDrop;
              setPendingPanelDrop(null);
              handleInsertSceneFromPanel(pending.items, pending.index);
            }}>{pendingPanelDrop.items.length === 1 ? "Add duplicate panel" : "Add panels"}</button>
        </div>
      </dialog>}
      <style>{`
        .pf-editor-timeline { border: 1px solid #293044; border-radius: 14px; background: #0c1019; }
        .pf-editor-timeline .pf-timeline-track-header { height: 34px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border-bottom: 1px solid #222838; font-size: 11px; background: linear-gradient(90deg,#121823,#0d121c); }
        .pf-editor-timeline .pf-timeline-track-header button { padding: 3px; border-radius: 4px; }
        .pf-editor-timeline button:hover { filter: brightness(1.25); }
        .pf-editor-timeline button:focus-visible, .pf-editor-timeline input:focus-visible { outline: 2px solid #aa85ff; outline-offset: 2px; }
        .pf-editor-timeline .pf-timeline-track-header button[aria-pressed=true] { color: #a9b4ff; }
        .pf-editor-timeline [data-timeline-lane] { height: 34px; border-bottom: 1px solid #222838; }
        .pf-editor-timeline [data-timeline-lane][data-visible=false] > * { visibility: hidden; pointer-events: none; }
        .pf-editor-timeline [data-timeline-lane][data-locked=true] { cursor: not-allowed; }
        .pf-editor-timeline .pf-timeline-waveform { display: flex; align-items: center; gap: 2px; height: 20px; width: 90px; overflow: hidden; opacity: .7; pointer-events: none; }
        .pf-editor-timeline .pf-timeline-waveform > span { flex: 1; min-width: 1px; background: currentColor; border-radius: 1px; }
        .pf-editor-timeline .pf-timeline-audio-bar { display: block; width: 36px; height: 2px; border-radius: 2px; background: currentColor; opacity: .35; pointer-events: none; }
        .pf-editor-timeline [data-timeline-lane="Narration"] { color: #20ddbd; }
        .pf-editor-timeline [data-timeline-lane="Visuals"] { color: #5894ff; }
        .pf-editor-timeline [data-timeline-lane="Layer 2"] { color: #bc74ff; }
        .pf-editor-timeline [data-timeline-lane="Motion / FX"] { color: #ed75ef; }
        .pf-editor-timeline [data-timeline-lane="Music"] { color: #ffb73c; }
      `}</style>
      {/* 1. Timeline Toolbar */}
      <div className="h-10 px-4 bg-zinc-900/95 border-b border-zinc-800 flex items-center justify-between shrink-0">
        {/* Left Editing Tools */}
        <div className="flex items-center gap-1.5 text-zinc-400">
          <button
            type="button"
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1.5 rounded hover:text-white disabled:opacity-30 transition-colors"
            aria-label="Undo (Ctrl+Z)"
            title="Undo (Ctrl+Z)"
          >
            <Icons.Undo className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1.5 rounded hover:text-white disabled:opacity-30 transition-colors"
            aria-label="Redo (Ctrl+Y)"
            title="Redo (Ctrl+Y)"
          >
            <Icons.Redo className="w-3.5 h-3.5" />
          </button>

          <div className="h-4 w-px bg-zinc-800 mx-1" />

          {(selectedSceneId || state.selected_object?.type === "layer") && (
            <button
              type="button"
              onClick={() => {
                if (state.selected_object?.type === "layer") {
                  const { id: layerId, sceneId } = state.selected_object;
                  const sc = state.scenes.find((s) => s.id === sceneId);
                  if (sc && sc.layers.length <= 1) {
                    onDeleteScene(sceneId);
                  } else if (onDeleteLayer && sceneId) {
                    onDeleteLayer(layerId, sceneId);
                  } else if (selectedSceneId) {
                    onDeleteScene(selectedSceneId);
                  }
                } else if (selectedSceneId) {
                  onDeleteScene(selectedSceneId);
                }
              }}
              className="p-1.5 rounded hover:text-rose-400 transition-colors"
              aria-label="Delete Selected Clip (Del)"
              title="Delete Selected Clip / Panel (Del)"
            >
              <Icons.Trash className="w-3.5 h-3.5" />
            </button>
          )}

          {selectedSceneId && (
            <button
              type="button"
              onClick={() => onSplitScene(selectedSceneId, state.playhead_sec)}
              className="p-1.5 rounded hover:text-indigo-400 transition-colors"
              aria-label="Split Scene at Playhead (Scissors)"
              title="Split Scene at Playhead (Scissors)"
            >
              <Icons.Scissors className="w-3.5 h-3.5" />
            </button>
          )}

          {selectedSceneId && (
            <button
              type="button"
              onClick={() => onDuplicateScene(selectedSceneId)}
              className="p-1.5 rounded hover:text-white transition-colors"
              aria-label="Duplicate Selected Scene"
              title="Duplicate Selected Scene"
            >
              <Icons.Copy className="w-3.5 h-3.5" />
            </button>
          )}

          <div className="h-4 w-px bg-zinc-800 mx-1" />

          {/* Magnetic Snapping Toggle */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, snapping: s.snapping === false }))}
            className={`p-1.5 rounded transition-colors ${
              snappingEnabled ? "text-indigo-400 bg-zinc-800" : "hover:text-white"
            }`}
            aria-label="Toggle Magnetic Snapping"
            title="Toggle Magnetic Snapping"
          >
            <Icons.Maximize className="w-3.5 h-3.5" />
          </button>

          {/* Ripple Edit Toggle */}
          <button
            type="button"
            onClick={() =>
              onUpdateState((s) => ({
                ...s,
                ripple_edit: s.ripple_edit === false ? true : false,
              }))
            }
            className={`px-2 py-1 rounded text-[11px] font-semibold flex items-center gap-1 transition-colors ${
              state.ripple_edit !== false
                ? "bg-indigo-900/60 text-indigo-300 border border-indigo-700/60"
                : "bg-zinc-800 text-zinc-400 hover:text-white"
            }`}
            aria-label="Ripple Edit: subsequent scenes automatically slide when trimming or moving clips"
            title={state.ripple_edit === false ? "Ripple OFF: existing scene starts stay fixed. Growth stops at the next scene; inserts and moves use a free gap or append at the end." : "Ripple Edit: subsequent scenes automatically slide when trimming or moving clips"}
          >
            <Icons.Layers className="w-3 h-3" />
            <span>Ripple: {state.ripple_edit !== false ? "ON" : "OFF"}</span>
          </button>

          <button
            type="button"
            onClick={onAddBlankScene}
            className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 font-medium flex items-center gap-1"
            aria-label="Insert new blank scene"
            title="Insert new blank scene"
          >
            <Icons.Plus className="w-3.5 h-3.5" />
            <span>Scene</span>
          </button>
        </div>

        {/* Center Transport & Playback Controls */}
        <div className="flex items-center gap-2.5">
          {/* Return to Start (00:00) */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: 0 }))}
            className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            aria-label="Return to Start (00:00)"
            title="Return to Start (00:00)"
          >
            <Icons.Rotate className="w-3.5 h-3.5" />
          </button>

          {/* Step Back -0.1s */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: Math.max(0, s.playhead_sec - 0.1) }))}
            className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            aria-label="Step Back 0.1s"
            title="Step Back 0.1s"
          >
            <Icons.ChevronDown className="w-3.5 h-3.5 rotate-90" />
          </button>

          {/* Main Play / Pause Button */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, is_playing: !s.is_playing }))}
            className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 shadow-md transition-all active:scale-95 ${
              state.is_playing
                ? "bg-amber-600 hover:bg-amber-500 text-white ring-2 ring-amber-400/40"
                : "bg-violet-600 hover:bg-violet-500 text-white ring-2 ring-violet-400/40"
            }`}
            aria-label={state.is_playing ? "Pause video" : "Play video"}
            title={state.is_playing ? "Pause Video (Space)" : "Play Video (Space)"}
          >
            {state.is_playing ? (
              <>
                <Icons.Pause className="w-3.5 h-3.5 fill-current" />
                <span>Pause</span>
              </>
            ) : (
              <>
                <Icons.Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                <span>Play</span>
              </>
            )}
          </button>

          {/* Step Forward +0.1s */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: Math.min(totalDurationSec, s.playhead_sec + 0.1) }))}
            className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            aria-label="Step Forward 0.1s"
            title="Step Forward 0.1s"
          >
            <Icons.ChevronDown className="w-3.5 h-3.5 -rotate-90" />
          </button>

          {/* Timecode Readout */}
          <div className="font-mono text-xs flex items-center gap-1 bg-zinc-950/80 px-2 py-0.5 rounded border border-zinc-800 shadow-inner">
            <span className="text-zinc-100 font-bold">{formatRulerTime(state.playhead_sec)}</span>
            <span className="text-zinc-600">/</span>
            <span className="text-zinc-400">{formatRulerTime(totalDurationSec)}</span>
          </div>

          {/* Mode Indicator */}
          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-zinc-800/80 text-zinc-400 border border-zinc-750 ml-1">
            {isAdvancedMode ? "Advanced Multitrack" : "Simple Storyline"}
          </span>
        </div>

        {/* Right Zoom Controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, zoom_level: Math.max(50, s.zoom_level - 15) }))}
            className="p-1 text-zinc-400 hover:text-white"
            aria-label="Zoom Timeline Out"
            title="Zoom Timeline Out"
          >
            <Icons.ZoomOut className="w-3.5 h-3.5" />
          </button>
          <input
            aria-label="Timeline zoom"
            type="range"
            min="50"
            max="250"
            step="10"
            value={state.zoom_level}
            onChange={(e) =>
              onUpdateState((s) => ({ ...s, zoom_level: parseInt(e.target.value) || 100 }))
            }
            className="w-24 accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
          />
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, zoom_level: Math.min(250, s.zoom_level + 15) }))}
            className="p-1 text-zinc-400 hover:text-white"
            aria-label="Zoom Timeline In"
            title="Zoom Timeline In"
          >
            <Icons.ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Multi-track Container (Track Headers Left + Track Canvas Right) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Track Headers Column */}
        <div className="w-60 bg-zinc-950 border-r border-zinc-800 flex flex-col shrink-0 text-xs select-none">
          {/* Header spacer for ruler */}
          <div className="h-6 border-b border-zinc-800/80 px-3 flex items-center text-[10px] font-mono text-zinc-500">
            TRACKS
          </div>

          {[
            { key: "Narration", label: "Narration", Icon: Icons.MessageSquare, color: "#20ddbd", open: onOpenNarrationStudio ? () => onOpenNarrationStudio() : undefined },
            { key: "Visuals", label: "Visuals", Icon: Icons.Film, color: "#5894ff" },
            { key: "Layer 2", label: "Layers", Icon: Icons.Layers, color: "#bc74ff" },
            { key: "Motion / FX", label: "Motion / FX", Icon: Icons.Sparkles, color: "#ed75ef" },
            { key: "Music", label: "Music", Icon: Icons.Music, color: "#ffb73c", open: onOpenAudioLibrary ? () => onOpenAudioLibrary("music") : undefined },
            ...(showSfx ? [{ key: "SFX", label: "SFX", Icon: Icons.Volume, color: "#50d7ee", open: onOpenAudioLibrary ? () => onOpenAudioLibrary("sfx") : undefined }] : []),
          ].map(({ key, label, Icon, color, open }) => {
            const track = getTimelineTrackState(state.track_states, key);
            return (
              <div key={key} className="pf-timeline-track-header" style={{ color }}>
                <span className="flex items-center gap-2 font-semibold min-w-0"><Icon className="w-4 h-4 shrink-0" />{label}</span>
                <div className="flex items-center gap-1 text-zinc-400">
                  {open && <button type="button" onClick={open} aria-label={key === "Narration" ? "Open Narration Studio" : `Add ${label} from Audio Library`} title={key === "Narration" ? "Open Narration Studio" : `Add ${label}`}><Icons.Plus className="w-3 h-3" /></button>}
                  <button type="button" onClick={() => toggleTrack(key, "visible")} aria-label={`Toggle ${label} visibility`} aria-pressed={track.visible} title={`${track.visible ? "Hide" : "Show"} ${label}`}><Icons.Eye className="w-3.5 h-3.5" /></button>
                  <button type="button" onClick={() => toggleTrack(key, "locked")} aria-label={`Toggle ${label} lock`} aria-pressed={track.locked} title={`${track.locked ? "Unlock" : "Lock"} ${label}`}><Icons.Lock className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Shared Time Ruler & Synchronized Track Lanes */}
        <div
          onDragOverCapture={(e) => {
            if (!e.dataTransfer.types.includes("application/panelflow-panel")) return;
            const lane = (e.target as HTMLElement).closest<HTMLElement>("[data-timeline-lane]");
            const track = getTimelineTrackState(state.track_states, lane?.dataset.timelineLane || "Visuals");
            const visuals = getTimelineTrackState(state.track_states, "Visuals");
            e.stopPropagation();
            if (track.locked || !track.visible || visuals.locked || !visuals.visible) { setPanelInsertIndex(null); return; }
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            const time = (e.clientX - (rulerRef.current?.getBoundingClientRect().left ?? 0)) / pxPerSec;
            setPanelInsertIndex(panelInsertionIndex(timedScenes, time));
          }}
          onDropCapture={(e) => {
            const items = readPanelDrag(e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain"));
            if (!items.length) return;
            const lane = (e.target as HTMLElement).closest<HTMLElement>("[data-timeline-lane]");
            const track = getTimelineTrackState(state.track_states, lane?.dataset.timelineLane || "Visuals");
            const visuals = getTimelineTrackState(state.track_states, "Visuals");
            setPanelInsertIndex(null);
            // Alt-drop retains explicit layer replacement; ordinary source drops insert.
            if (e.altKey && lane?.dataset.timelineLane === "Layer 2" && items.length === 1 && lane !== e.target && !track.locked && track.visible) return;
            e.preventDefault();
            e.stopPropagation();
            if (track.locked || !track.visible || visuals.locked || !visuals.visible) return;
            const time = (e.clientX - (rulerRef.current?.getBoundingClientRect().left ?? 0)) / pxPerSec;
            const index = panelInsertionIndex(timedScenes, time);
            if (items.some(item => item.panelId && state.scenes.some(scene => scene.layers.some(layer => layer.source_panel_id === item.panelId)))) {
              setPendingPanelDrop({ items, index });
            } else {
              handleInsertSceneFromPanel(items, index);
            }
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setPanelInsertIndex(null);
          }}
          onDragEnd={() => setPanelInsertIndex(null)}
          onDragOver={(e) => {
            const hasPanel = e.dataTransfer.types.some((t) => t === "application/panelflow-panel" || t === "text/plain");
            const hasMove = e.dataTransfer.types.some(
              (t) =>
                t === "application/panelflow-scene-reorder" ||
                t === "application/panelflow-layer-move" ||
                t === "application/panelflow-motion-move" ||
                t === "application/panelflow-narration-reorder"
            );
            if (hasPanel || hasMove) {
              e.preventDefault();
              e.dataTransfer.dropEffect = hasMove ? "move" : "copy";
            }
          }}
          onDrop={(e) => {
            e.stopPropagation();
            const rawPanel = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
            if (rawPanel) {
              try {
                const parsed = JSON.parse(rawPanel);
                if (parsed.panelId || parsed.pageId) {
                  e.preventDefault();
                  handleInsertSceneFromPanel(parsed, state.scenes.length);
                }
              } catch (err) {}
            }
          }}
          ref={timelineScrollRef}
          onWheel={(e) => {
            if (e.ctrlKey || e.metaKey) {
              e.preventDefault();
              const zoomDelta = e.deltaY < 0 ? 10 : -10;
              onUpdateState((s) => ({
                ...s,
                zoom_level: Math.max(50, Math.min(250, (s.zoom_level || 100) + zoomDelta)),
              }));
            } else if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.shiftKey) {
              if (timelineScrollRef.current) {
                timelineScrollRef.current.scrollLeft += e.deltaY;
              }
            }
          }}
          className="flex-1 overflow-x-auto overflow-y-hidden bg-zinc-950 relative select-none"
        >
          <div
            ref={rulerRef}
            onPointerDown={handleStartScrub}
            className="relative h-full cursor-pointer"
            style={{ width: `${totalTimelineWidthPx}px` }}
          >
            {panelInsertIndex !== null && <div aria-label="Panel insertion position"
              className="absolute top-0 bottom-0 z-50 w-0.5 bg-cyan-400 pointer-events-none"
              style={{ left: `${(panelInsertIndex > 0 ? timedScenes[panelInsertIndex - 1].start_time_sec + timedScenes[panelInsertIndex - 1].duration_sec : 0) * pxPerSec}px` }}>
              <span className="absolute top-0 left-1 whitespace-nowrap rounded bg-cyan-950 px-2 text-[10px] text-cyan-200">Insert panels</span>
            </div>}
            {/* Top Time Ruler */}
            <div className="h-6 border-b border-zinc-800/80 relative text-[10px] font-mono text-zinc-500 pointer-events-none select-none">
              {Array.from({ length: ticksCount }).map((_, idx) => {
                const sec = idx * tickIntervalSec;
                const leftPx = sec * pxPerSec;
                return (
                  <div
                    key={sec}
                    className="absolute top-0 bottom-0 border-l border-zinc-800/80 pl-1 flex items-end pb-0.5"
                    style={{ left: `${leftPx}px` }}
                  >
                    <span>{formatRulerTime(sec)}</span>
                  </div>
                );
              })}
            </div>

            {/* Draggable Smooth Playhead Vertical Line */}
            <div
              className={`absolute top-0 bottom-0 z-10 pointer-events-auto transition-opacity ${
                isScrubbing ? "opacity-100" : "opacity-95"
              }`}
              style={{ left: `${state.playhead_sec * pxPerSec}px` }}
            >
              {/* Laser line with cyan glow while scrubbing */}
              <div
                className={`w-0.5 h-full ${
                  isScrubbing
                    ? "bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,1)]"
                    : "bg-violet-500 shadow-[0_0_8px_rgba(139,92,246,0.5)]"
                }`}
              />

              {/* Invisible wider grab handle along vertical line */}
              <div
                onPointerDown={handleStartScrub}
                className="absolute top-0 bottom-0 -left-3 w-6 cursor-ew-resize"
                title="Drag Scrubber"
              />

              {/* Sculpted Studio Playhead Cap */}
              <div
                onPointerDown={handleStartScrub}
                className="absolute -left-2.5 -top-1 cursor-ew-resize pointer-events-auto group z-40"
              >
                <svg
                  className={`w-5 h-6 drop-shadow-md transition-transform ${
                    isScrubbing
                      ? "scale-115 text-cyan-400 fill-cyan-400 stroke-cyan-200"
                      : "text-violet-500 fill-violet-500 stroke-violet-300 group-hover:scale-110 group-hover:text-violet-400"
                  }`}
                  viewBox="0 0 20 24"
                  fill="currentColor"
                  strokeWidth={1}
                >
                  <path d="M2 3a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-.586 1.414l-6 6a2 2 0 0 1-2.828 0l-6-6A2 2 0 0 1 2 15V3z" />
                </svg>

                {/* Floating live timecode tooltip badge */}
                {isScrubbing && (
                  <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-zinc-950/95 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold px-2 py-0.5 rounded shadow-2xl whitespace-nowrap pointer-events-none ring-1 ring-cyan-400/40 animate-fadeIn">
                    {formatRulerTime(state.playhead_sec)}
                  </div>
                )}
              </div>
            </div>

            {/* TRACK 1: Narration Track */}
            <div data-timeline-lane="Narration" {...laneProps("Narration")} className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {state.narration_clips.map((narration) => {
                const clipLeft = narration.start_time_sec * pxPerSec;
                const clipWidth = Math.max(48, narration.duration_sec * pxPerSec);
                const isSelected =
                  state.selected_object?.type === "narration" && state.selected_object.id === narration.id;
                const isLinked = narration.linked_to_scene !== false;

                return (
                  <div
                    key={narration.id}
                    draggable={!getTimelineTrackState(state.track_states, "Narration").locked}
                    onDragStart={(e) => {
                      setDraggingNarration(null);
                      e.dataTransfer.setData(
                        "application/panelflow-narration-reorder",
                        JSON.stringify({ narrationId: narration.id, startTimeSec: narration.start_time_sec })
                      );
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      setDragOverNarrationId(narration.id);
                    }}
                    onDragLeave={() => {
                      if (dragOverNarrationId === narration.id) setDragOverNarrationId(null);
                    }}
                    onDrop={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      setDragOverNarrationId(null);
                      const narrData = e.dataTransfer.getData("application/panelflow-narration-reorder");
                      if (narrData) {
                        try {
                          const { narrationId: fromNarrId } = JSON.parse(narrData);
                          handleSwapNarrationClips(fromNarrId, narration.id);
                        } catch (err) {
                          console.error(err);
                        }
                      }
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onUpdateState((s) => ({
                        ...s,
                        selected_object: { type: "narration", id: narration.id },
                      }));
                    }}
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      onOpenNarrationStudio?.(narration.id);
                    }}
                    onMouseDown={(e) => {
                      // Allow horizontal drag to shift unlinked narration or fine-tune
                      e.stopPropagation();
                      setDraggingNarration({
                        id: narration.id,
                        startMouseX: e.clientX,
                        initialStartSec: narration.start_time_sec,
                      });
                    }}
                    className={`absolute h-6 rounded-md px-1.5 flex items-center justify-between text-xs font-mono border transition-all cursor-move select-none ${
                      dragOverNarrationId === narration.id
                        ? "bg-emerald-700/60 border-cyan-400 ring-2 ring-cyan-400 shadow-lg"
                        : isSelected
                        ? "bg-emerald-600/30 border-emerald-400 text-emerald-200 ring-1 ring-emerald-500 shadow-md"
                        : narration.status === "OUTDATED"
                        ? "bg-amber-950/70 border-amber-600 text-amber-200 hover:bg-amber-900/70"
                        : "bg-emerald-950/60 border-emerald-800 text-emerald-300 hover:bg-emerald-900/60"
                    }`}
                    style={{
                      left: `${clipLeft}px`,
                      width: `${clipWidth}px`,
                    }}
                    title={`Double-click to open Narration Studio\nSpeaker: ${narration.speaker || "Narrator"}\nReview: ${narration.review_status || "DRAFT"}\nAudio: ${narration.status}`}
                  >
                    {/* Left: Speaker chip, Emotion tag, & Script text preview */}
                    <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden mr-1">
                      <span className="px-1 py-0.2 rounded bg-zinc-900 border border-zinc-700/80 text-[8px] font-bold text-zinc-300 shrink-0" title={`Speaker: ${narration.speaker || "Narrator"}`}>
                        {(narration.speaker || "N").slice(0, 3).toUpperCase()}
                      </span>
                      {narration.emotion && (
                        <span className="px-1 py-0.2 rounded bg-indigo-950/80 border border-indigo-700/50 text-[8px] font-semibold text-indigo-300 shrink-0 hidden sm:inline-block" title={`Emotion: ${narration.emotion}`}>
                          {narration.emotion}
                        </span>
                      )}
                      <span className="truncate text-[10px] font-medium text-emerald-200">
                        "{narration.text}"
                      </span>
                    </div>

                    {/* Right: Revision tag, Review status, Audio status dot, Link toggle, Waveform */}
                    <div className="flex items-center gap-1 shrink-0 z-10">
                      <span className="text-[8px] font-mono text-zinc-500 hidden md:inline-block" title={`Text Revision #${narration.text_revision || 1}`}>
                        r{narration.text_revision || 1}
                      </span>
                      {/* Review Status Badge */}
                      {narration.review_status === "APPROVED" ? (
                        <span className="px-1 py-0.5 rounded bg-emerald-950 text-emerald-400 text-[8px] font-bold border border-emerald-700/60 flex items-center justify-center" title="Review: Approved">
                          <Icons.Check className="w-2.5 h-2.5" />
                        </span>
                      ) : narration.review_status === "NEEDS_REVIEW" ? (
                        <span className="px-1 py-0.5 rounded bg-amber-950 text-amber-400 text-[8px] font-bold border border-amber-700/60 flex items-center justify-center" title="Review: Needs Review">
                          <Icons.AlertTriangle className="w-2.5 h-2.5" />
                        </span>
                      ) : (
                        <span className="px-1 py-0.5 rounded bg-zinc-900 text-zinc-400 text-[8px] font-mono border border-zinc-800" title="Review: Draft">
                          D
                        </span>
                      )}

                      {/* Audio Generation Status */}
                      {narration.status === "OUTDATED" ? (
                        <span className="px-1 py-0.5 rounded bg-amber-900 text-amber-200 font-bold border border-amber-500 text-[8px] animate-pulse flex items-center justify-center" title="Audio Take Outdated">
                          <Icons.AlertTriangle className="w-2.5 h-2.5 text-amber-300" />
                        </span>
                      ) : narration.status === "READY" ? (
                        <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-[0_0_6px_rgba(52,211,153,0.8)]" title="Audio Take Ready" />
                      ) : narration.status === "PROCESSING" ? (
                        <span className="text-blue-400 flex items-center" title="Audio Generating">
                          <Icons.Rotate className="w-2.5 h-2.5 animate-spin" />
                        </span>
                      ) : (
                        <span className="text-purple-400 text-[8px] font-mono" title={narration.status}>
                          Q
                        </span>
                      )}

                      {/* Link / Unlink Button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleNarrationLink(narration.id);
                        }}
                        className={`p-1 rounded text-[8px] font-bold border transition-colors flex items-center justify-center ${
                          isLinked
                            ? "bg-emerald-800/60 border-emerald-600 text-emerald-200"
                            : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-white"
                        }`}
                        aria-label={isLinked ? "Linked to scene (shifts with scene)" : "Unlinked (independent time)"}
                        title={isLinked ? "Linked to scene (shifts with scene)" : "Unlinked (independent time)"}
                      >
                        {isLinked ? (
                          <Icons.Link className="w-2.5 h-2.5 text-emerald-300" />
                        ) : (
                          <Icons.Unlink className="w-2.5 h-2.5 text-zinc-400" />
                        )}
                      </button>

                      <AudioPeaks />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* TRACK 2: Visuals Track (Filmstrip Scenes + Drop Indicators + Trim Handles) */}
            <div
              data-timeline-lane="Visuals"
              {...laneProps("Visuals")}
              onDragOver={(e) => {
                const hasPanel = e.dataTransfer.types.some((t) => t === "application/panelflow-panel" || t === "text/plain");
                const hasReorder = e.dataTransfer.types.some((t) => t === "application/panelflow-scene-reorder" || t === "application/panelflow-layer-move");
                if (hasPanel || hasReorder) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = hasReorder ? "move" : "copy";
                }
              }}
              onDrop={(e) => {
                e.stopPropagation();
                const rawPanel = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
                if (rawPanel) {
                  try {
                    const parsed = JSON.parse(rawPanel);
                    if (parsed.panelId || parsed.pageId) {
                      e.preventDefault();
                      handleInsertSceneFromPanel(parsed, state.scenes.length);
                    }
                  } catch (err) {}
                }
              }}
              className="h-10 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40"
            >
              {(() => {
                return timedScenes.map((scene, idx) => {
                  const clipLeft = scene.start_time_sec * pxPerSec;
                  const clipWidth = Math.max(1, scene.duration_sec * pxPerSec);
                  const isSelected = selectedSceneId === scene.id;
                  const isDragOverScene = dragOverSceneId === scene.id;
                  const isInsertTargetBefore = dragOverInsertIndex === idx;

                  return (
                    <React.Fragment key={scene.id}>
                      {/* Inter-scene drop zone BEFORE this scene */}
                      <div
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = visualDropEffect(e.dataTransfer);
                          setDragOverInsertIndex(idx);
                        }}
                        onDragLeave={() => {
                          if (dragOverInsertIndex === idx) setDragOverInsertIndex(null);
                        }}
                        onDrop={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          setDragOverInsertIndex(null);
                          const panelData = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
                          const reorderData = e.dataTransfer.getData("application/panelflow-scene-reorder");
                          const layerMoveData = e.dataTransfer.getData("application/panelflow-layer-move");

                          if (panelData) {
                            try {
                              const parsed = JSON.parse(panelData);
                              if (parsed.panelId || parsed.pageId) {
                                handleInsertSceneFromPanel(parsed, idx);
                              }
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (reorderData) {
                            try {
                              const { fromIndex } = JSON.parse(reorderData);
                              handleReorderScenes(fromIndex, idx);
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (layerMoveData) {
                            try {
                              const { layerId, fromSceneId } = JSON.parse(layerMoveData);
                              // Extract layer into new scene
                              const fromScene = state.scenes.find((s) => s.id === fromSceneId);
                              const targetLayer = fromScene?.layers.find((l) => l.id === layerId);
                              if (targetLayer) {
                                handleInsertSceneFromPanel(
                                  {
                                    pageId: targetLayer.source_page_id,
                                    panelId: targetLayer.source_panel_id,
                                    pageSequence: targetLayer.page_sequence,
                                    crop: targetLayer.crop,
                                    imageUrl: targetLayer.image_url,
                                    name: targetLayer.name,
                                  },
                                  idx
                                );
                                // remove from source scene
                                onUpdateState((prev) => ({
                                  ...prev,
                                  scenes: prev.scenes.map((sc) => {
                                    if (sc.id !== fromSceneId) return sc;
                                    return { ...sc, layers: sc.layers.filter((l) => l.id !== layerId) };
                                  }),
                                }));
                              }
                            } catch (err) {
                              console.error(err);
                            }
                          }
                        }}
                        className="absolute h-10 w-1 -ml-0.5 z-20 flex items-center justify-center cursor-pointer"
                        style={{ left: `${clipLeft}px` }}
                      >
                        {isInsertTargetBefore && (
                          <div className="pointer-events-none w-1.5 h-8 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee] animate-pulse" />
                        )}
                      </div>

                      {/* Transition badge if scene has entrance transition */}
                      {scene.transition_in && scene.transition_in !== "none" && (
                        <div
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectScene(scene.id);
                            onSelectMotionBadge?.(scene.id);
                          }}
                          className="absolute -top-2 z-30 px-1.5 py-0.5 rounded-full bg-zinc-950 border border-indigo-500/80 text-[9px] font-bold text-indigo-300 shadow-md flex items-center gap-1 cursor-pointer hover:bg-zinc-800 hover:border-indigo-400"
                          style={{ left: `${clipLeft + 4}px` }}
                          title={`Transition: ${scene.transition_in} (${scene.transition_duration_sec ?? 0.5}s)`}
                        >
                          <Icons.Sparkles className="w-2.5 h-2.5 text-indigo-400" />
                          <span className="capitalize">{scene.transition_in.replace(/_/g, " ")}</span>
                        </div>
                      )}

                      {/* Scene Clip */}
                      <div
                        title={scene.title}
                        draggable={!getTimelineTrackState(state.track_states, "Visuals").locked}
                        onDragStart={(e) => {
                          e.dataTransfer.setData(
                            "application/panelflow-scene-reorder",
                            JSON.stringify({ sceneId: scene.id, fromIndex: idx })
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = visualDropEffect(e.dataTransfer);
                          setDragOverSceneId(scene.id);
                        }}
                        onDragLeave={() => {
                          if (dragOverSceneId === scene.id) setDragOverSceneId(null);
                        }}
                        onDrop={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          setDragOverSceneId(null);
                          const panelData = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
                          const layerMoveData = e.dataTransfer.getData("application/panelflow-layer-move");
                          const reorderData = e.dataTransfer.getData("application/panelflow-scene-reorder");
                          const motionData = e.dataTransfer.getData("application/panelflow-motion-move");
                          const narrData = e.dataTransfer.getData("application/panelflow-narration-reorder");

                          if (panelData) {
                            try {
                              const parsed = JSON.parse(panelData);
                              if (parsed.panelId || parsed.pageId) {
                                if (e.altKey) {
                                  handleAddLayerToScene(parsed, scene.id);
                                } else {
                                  handleReplaceSceneVisual(parsed, scene.id);
                                }
                              }
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (reorderData) {
                            try {
                              const { fromIndex } = JSON.parse(reorderData);
                              handleSwapScenes(fromIndex, idx);
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (layerMoveData) {
                            try {
                              const { layerId, fromSceneId } = JSON.parse(layerMoveData);
                              handleMoveLayer(layerId, fromSceneId, scene.id);
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (motionData) {
                            try {
                              handleTransferOrSwapMotion(JSON.parse(motionData), scene.id);
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (narrData) {
                            try {
                              const { narrationId } = JSON.parse(narrData);
                              handleAttachNarrationToScene(narrationId, scene.id);
                            } catch (err) {
                              console.error(err);
                            }
                          }
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectScene(scene.id);
                        }}
                        className={`absolute h-8 rounded-lg overflow-hidden flex items-center border transition-all cursor-pointer shadow-md group ${
                          isDragOverScene
                            ? "bg-cyan-950/80 border-cyan-400 ring-2 ring-cyan-400/80"
                            : isSelected
                            ? "bg-indigo-950 border-indigo-400 ring-2 ring-indigo-500/50"
                            : "bg-blue-950/70 border-blue-600 hover:border-blue-400"
                        }`}
                        style={{
                          left: `${clipLeft}px`,
                          width: `${clipWidth}px`,
                        }}
                      >
                        {/* Left Trim Handle */}
                        <div
                          onMouseDown={(e) => {
                            e.stopPropagation();
                            setTrimming({
                              type: "scene",
                              id: scene.id,
                              edge: "left",
                              startMouseX: e.clientX,
                              initialDuration: scene.duration_sec,
                            });
                          }}
                          className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400/80 z-20 transition-colors"
                          data-timeline-trim
                          title="Drag to trim left boundary"
                        />

                        {/* Filmstrip thumbnails */}
                        <div className="flex items-center h-full w-full overflow-hidden pointer-events-none px-1">
                          {scene.layers.length > 0 ? (
                            scene.layers.map((ly) => (
                              <img
                                key={ly.id}
                                src={getLayerImageUrl(ly)}
                                alt="Scene strip"
                                className="h-full w-10 object-cover border-r border-zinc-800 shrink-0 rounded-sm mr-1"
                              />
                            ))
                          ) : (
                            <span className="text-[10px] text-zinc-500 px-2 italic">Blank scene</span>
                          )}
                          <span className="text-[10px] font-bold text-zinc-200 truncate">
                            {scene.title}
                          </span>
                          {isDragOverScene && (
                            <span className="ml-auto text-[9px] bg-cyan-400 text-black px-1.5 py-0.5 rounded font-bold shrink-0 shadow">
                              Replace Visual
                            </span>
                          )}
                        </div>

                        {/* Delete Scene / Panel Clip Button */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteScene(scene.id);
                          }}
                          className={`absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded bg-zinc-950/80 hover:bg-rose-600 text-zinc-400 hover:text-white transition-all z-30 shadow ${
                            isSelected ? "opacity-90" : "opacity-0 group-hover:opacity-100"
                          }`}
                          title={`Delete ${scene.title} from timeline (Del)`}
                          aria-label={`Delete ${scene.title}`}
                        >
                          <Icons.Trash className="w-3 h-3 pointer-events-none" />
                        </button>

                        {/* Right Trim Handle */}
                        <div
                          onMouseDown={(e) => {
                            e.stopPropagation();
                            setTrimming({
                              type: "scene",
                              id: scene.id,
                              edge: "right",
                              startMouseX: e.clientX,
                              initialDuration: scene.duration_sec,
                            });
                          }}
                          className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400/80 z-20 transition-colors"
                          data-timeline-trim
                          title="Drag to trim right boundary"
                        />
                      </div>
                    </React.Fragment>
                  );
                });
              })()}

              {/* Inter-scene drop zone AFTER the last scene */}
              {(() => {
                const totalSec = sceneTimelineDuration(timedScenes);
                const endLeft = totalSec * pxPerSec;
                const lastIdx = state.scenes.length;
                const isTarget = dragOverInsertIndex === lastIdx;

                return (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = visualDropEffect(e.dataTransfer);
                      setDragOverInsertIndex(lastIdx);
                    }}
                    onDragLeave={() => {
                      if (dragOverInsertIndex === lastIdx) setDragOverInsertIndex(null);
                    }}
                    onDrop={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      setDragOverInsertIndex(null);
                      const panelData = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
                      const reorderData = e.dataTransfer.getData("application/panelflow-scene-reorder");
                      if (panelData) {
                        try {
                          const parsed = JSON.parse(panelData);
                          if (parsed.panelId || parsed.pageId) {
                            handleInsertSceneFromPanel(parsed, lastIdx);
                          }
                        } catch (err) {
                          console.error(err);
                        }
                      } else if (reorderData) {
                        try {
                          const { fromIndex } = JSON.parse(reorderData);
                          handleReorderScenes(fromIndex, lastIdx);
                        } catch (err) {
                          console.error(err);
                        }
                      }
                    }}
                    className="absolute h-10 w-8 flex items-center justify-center cursor-pointer z-20"
                    style={{ left: `${endLeft}px` }}
                  >
                    {isTarget && (
                      <div className="pointer-events-none w-1.5 h-8 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee] animate-pulse" />
                    )}
                  </div>
                );
              })()}
            </div>

            {/* TRACK 3: Layers Track (Independent Layer Blocks + Trim Handles) */}
            <div data-timeline-lane="Layer 2" {...laneProps("Layer 2")} className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {(() => {
                return timedScenes.map((scene) => {
                  const clipLeft = scene.start_time_sec * pxPerSec;

                  return scene.layers.map((ly) => {
                    const startOffset = ly.start_offset_sec ?? 0;
                    const duration = ly.duration_sec ?? scene.duration_sec;
                    const lLeft = clipLeft + startOffset * pxPerSec;
                    const visibleDuration = Math.max(0, Math.min(duration, scene.duration_sec - startOffset));
                    if (visibleDuration <= 0) return null;
                    const lWidth = Math.max(1, visibleDuration * pxPerSec);
                    const isSelected =
                      state.selected_object?.type === "layer" && state.selected_object.id === ly.id;

                    return (
                      <div
                        key={ly.id}
                        draggable={!getTimelineTrackState(state.track_states, "Layer 2").locked && !ly.locked}
                        onDragStart={(e) => {
                          e.dataTransfer.setData(
                            "application/panelflow-layer-move",
                            JSON.stringify({ layerId: ly.id, fromSceneId: scene.id })
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = visualDropEffect(e.dataTransfer);
                          setDragOverLayerId(ly.id);
                        }}
                        onDragLeave={() => {
                          if (dragOverLayerId === ly.id) setDragOverLayerId(null);
                        }}
                        onDrop={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          setDragOverLayerId(null);
                          const panelData = e.dataTransfer.getData("application/panelflow-panel") || e.dataTransfer.getData("text/plain");
                          const layerMoveData = e.dataTransfer.getData("application/panelflow-layer-move");

                          if (panelData) {
                            try {
                              const parsed = JSON.parse(panelData);
                              if (parsed.panelId || parsed.pageId) {
                                handleReplaceLayerVisual(parsed, ly.id, scene.id);
                              }
                            } catch (err) {
                              console.error(err);
                            }
                          } else if (layerMoveData) {
                            try {
                              const { layerId: fromLayerId, fromSceneId } = JSON.parse(layerMoveData);
                              handleSwapOrReplaceLayers(fromLayerId, fromSceneId, ly.id, scene.id);
                            } catch (err) {
                              console.error(err);
                            }
                          }
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectLayer(ly.id, scene.id);
                        }}
                        className={`absolute h-6 rounded-md border px-1.5 flex items-center justify-between cursor-pointer shadow transition-all ${
                          dragOverLayerId === ly.id
                            ? "bg-purple-800 border-cyan-400 ring-2 ring-cyan-400 shadow-md"
                            : isSelected
                            ? "bg-purple-900 border-purple-400 ring-2 ring-purple-500/60"
                            : "bg-purple-950/80 border-purple-800 hover:border-purple-500"
                        }`}
                        style={{
                          left: `${lLeft}px`,
                          width: `${lWidth}px`,
                        }}
                      >
                        {/* Layer Left Trim Handle in Advanced Mode */}
                        {isAdvancedMode && (
                          <div
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              if (ly.locked) return;
                              setTrimming({
                                type: "layer",
                                id: ly.id,
                                sceneId: scene.id,
                                edge: "left",
                                startMouseX: e.clientX,
                                initialDuration: duration,
                                initialStartOffset: startOffset,
                              });
                            }}
                            className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400/80 z-20"
                            data-timeline-trim
                            title="Trim layer start"
                          />
                        )}

                        <div className="flex items-center gap-1 overflow-hidden pointer-events-none">
                          <img src={getLayerImageUrl(ly)} alt="Layer" className="w-3.5 h-3.5 rounded object-cover shrink-0" />
                          <span className="text-[10px] font-medium text-purple-200 truncate">
                            {ly.name || "Layer"}
                          </span>
                        </div>

                        {onDeleteLayer && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteLayer(ly.id, scene.id);
                            }}
                            className={`p-0.5 rounded bg-zinc-950/70 hover:bg-rose-600 text-zinc-400 hover:text-white transition-all ml-1 shrink-0 z-30 ${
                              isSelected ? "opacity-90" : "opacity-0 group-hover:opacity-100"
                            }`}
                            title={`Delete layer ${ly.name || "Layer"} (Del)`}
                            aria-label={`Delete layer ${ly.name || "Layer"}`}
                          >
                            <Icons.Trash className="w-2.5 h-2.5 pointer-events-none" />
                          </button>
                        )}

                        {/* Keyframe diamond indicators on layer chip in Advanced Mode */}
                        {isAdvancedMode && ly.animation_config?.tracks && (
                          <div className="absolute inset-0 pointer-events-none overflow-hidden">
                            {(() => {
                              const seenTimes = new Set<number>();
                              const markers: { id: string; time: number }[] = [];
                              Object.values(ly.animation_config.tracks).forEach((track) => {
                                track?.keyframes?.forEach((kf) => {
                                  const rounded = Math.round(kf.time_offset_sec * 50) / 50;
                                  if (!seenTimes.has(rounded)) {
                                    seenTimes.add(rounded);
                                    markers.push({ id: kf.id, time: kf.time_offset_sec });
                                  }
                                });
                              });
                              return markers.map((m) => (
                                <div
                                  key={m.id}
                                  className="absolute top-1/2 -translate-y-1/2 w-2 h-2 bg-amber-400 border border-amber-100 rotate-45 shadow-sm"
                                  style={{
                                    left: `${Math.min(lWidth - 8, Math.max(2, m.time * pxPerSec))}px`,
                                  }}
                                  title={`Keyframe at ${m.time.toFixed(2)}s`}
                                />
                              ));
                            })()}
                          </div>
                        )}

                        {/* Layer Right Trim Handle in Advanced Mode */}
                        {isAdvancedMode && (
                          <div
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              if (ly.locked) return;
                              setTrimming({
                                type: "layer",
                                id: ly.id,
                                sceneId: scene.id,
                                edge: "right",
                                startMouseX: e.clientX,
                                initialDuration: duration,
                                initialStartOffset: startOffset,
                              });
                            }}
                            className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400/80 z-20"
                            data-timeline-trim
                            title="Trim layer duration"
                          />
                        )}
                      </div>
                    );
                  });
                });
              })()}
            </div>

            {/* TRACK 4: Motion / FX Track (Clickable & Draggable Badges + Drop Targets) */}
            <div data-timeline-lane="Motion / FX" {...laneProps("Motion / FX")} className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {(() => {
                return timedScenes.map((scene) => {
                  const clipLeft = scene.start_time_sec * pxPerSec;
                  const clipWidth = Math.max(80, scene.duration_sec * pxPerSec);
                  const isDragOverMotion = dragOverMotionSceneId === scene.id;

                  const hasCamera = scene.camera && scene.camera.preset !== "static";
                  const motionLayer = scene.layers.find(
                    (l) => (l.motion_preset && l.motion_preset !== "none") || l.animation_config?.preset === "custom"
                  );

                  return (
                    <div
                      key={`motion_slot_${scene.id}`}
                      onDragOver={(e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        setDragOverMotionSceneId(scene.id);
                      }}
                      onDragLeave={() => {
                        if (dragOverMotionSceneId === scene.id) setDragOverMotionSceneId(null);
                      }}
                      onDrop={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        setDragOverMotionSceneId(null);
                        const motionData = e.dataTransfer.getData("application/panelflow-motion-move");
                        if (motionData) {
                          try {
                            handleTransferOrSwapMotion(JSON.parse(motionData), scene.id);
                          } catch (err) {
                            console.error(err);
                          }
                        }
                      }}
                      className={`absolute h-7 rounded flex items-center gap-1.5 px-1 transition-all ${
                        isDragOverMotion
                          ? "bg-fuchsia-950/70 border border-fuchsia-400 ring-2 ring-fuchsia-400/80 z-20"
                          : "border border-transparent"
                      }`}
                      style={{ left: `${clipLeft}px`, width: `${clipWidth}px` }}
                    >
                      {/* Layer Motion Badge */}
                      {motionLayer && (
                        <div
                          draggable={!getTimelineTrackState(state.track_states, "Motion / FX").locked}
                          onDragStart={(e) => {
                            e.dataTransfer.setData(
                              "application/panelflow-motion-move",
                              JSON.stringify({
                                fromSceneId: scene.id,
                                layerId: motionLayer.id,
                                type: "layer_motion",
                                motionPreset: motionLayer.motion_preset,
                                animationConfig: motionLayer.animation_config,
                              })
                            );
                            e.dataTransfer.effectAllowed = "move";
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectLayer(motionLayer.id, scene.id);
                            onSelectMotionBadge?.(scene.id, motionLayer.id);
                          }}
                          className="h-6 rounded-md px-2 flex items-center gap-1 text-[10px] font-bold text-fuchsia-200 bg-fuchsia-950/80 border border-fuchsia-800 shadow-sm hover:border-fuchsia-400 cursor-grab active:cursor-grabbing transition-all select-none"
                          title="Click to configure in Inspector; Drag to transfer or swap motion with another scene"
                        >
                          <Icons.Sparkles className="w-3 h-3 text-fuchsia-400" />
                          <span className="truncate max-w-[90px]">
                            {motionLayer.animation_config?.preset === "custom"
                              ? "Keyframes"
                              : presetLabels[motionLayer.motion_preset || ""] || "Motion"}
                          </span>
                        </div>
                      )}

                      {/* Scene Camera Badge */}
                      {hasCamera && (
                        <div
                          draggable={!getTimelineTrackState(state.track_states, "Motion / FX").locked}
                          onDragStart={(e) => {
                            e.dataTransfer.setData(
                              "application/panelflow-motion-move",
                              JSON.stringify({
                                fromSceneId: scene.id,
                                type: "camera",
                                camera: scene.camera,
                              })
                            );
                            e.dataTransfer.effectAllowed = "move";
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectScene(scene.id);
                            onSelectMotionBadge?.(scene.id);
                          }}
                          className="h-6 rounded-md px-2 flex items-center gap-1 text-[10px] font-bold text-cyan-200 bg-cyan-950/80 border border-cyan-800 shadow-sm hover:border-cyan-400 cursor-grab active:cursor-grabbing transition-all select-none"
                          title="Click to configure in Inspector; Drag to transfer or swap camera preset"
                        >
                          <Icons.Film className="w-3 h-3 text-cyan-400" />
                          <span className="truncate max-w-[90px]">
                            Cam: {presetLabels[scene.camera?.preset || ""] || scene.camera?.preset}
                          </span>
                        </div>
                      )}

                      {/* Empty motion slot drop placeholder */}
                      {!motionLayer && !hasCamera && isDragOverMotion && (
                        <span className="text-[9px] font-mono font-medium text-fuchsia-300 animate-pulse">
                          + Drop motion effect
                        </span>
                      )}
                    </div>
                  );
                });
              })()}
            </div>

            {/* TRACK 5: Music Track (Interactive BGM Clips + Trim Handles + Drag + Drop Zone) */}
            <div data-timeline-lane="Music" {...laneProps("Music")}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
                e.stopPropagation();
                e.preventDefault();
                const contractJson = e.dataTransfer.getData("application/panelflow-audio-contract");
                if (contractJson) {
                  try {
                    const contract = JSON.parse(contractJson);
                    const rect = e.currentTarget.getBoundingClientRect();
                    const dropSec = Math.max(0, (e.clientX - rect.left) / pxPerSec);
                    onUpdateState((prev) => applyAudioContractToState(prev, contract, dropSec));
                  } catch (err) {
                    console.error("Drop error:", err);
                  }
                }
              }}
              className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40 group/track"
            >
              {state.bgm_tracks.length === 0 && (
                <div
                  onClick={() => onOpenAudioLibrary?.("music")}
                  className="absolute inset-0 flex items-center justify-center text-[10px] text-amber-500/60 hover:text-amber-400 hover:bg-amber-950/20 cursor-pointer border border-dashed border-amber-900/40 rounded transition-colors"
                >
                  + Click to Add Background Music from Library
                </div>
              )}

              {state.bgm_tracks.map((bgm) => {
                const clipLeft = bgm.start_time_sec * pxPerSec;
                const clipWidth = Math.max(80, bgm.duration_sec * pxPerSec);
                const isSelected = state.selected_object?.type === "bgm" && state.selected_object.id === bgm.id;
                const isLocked = getTimelineTrackState(state.track_states, "Music").locked;

                return (
                  <div
                    key={bgm.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      onUpdateState((s) => ({
                        ...s,
                        selected_object: { type: "bgm", id: bgm.id },
                      }));
                    }}
                    onMouseDown={(e) => {
                      if (isLocked) return;
                      e.stopPropagation();
                      setDraggingAudioClip({
                        type: "bgm",
                        id: bgm.id,
                        startMouseX: e.clientX,
                        initialStartSec: bgm.start_time_sec,
                      });
                    }}
                    className={`absolute h-6 rounded-md px-1.5 flex items-center justify-between text-xs font-mono border transition-all cursor-move select-none ${
                      isSelected
                        ? "bg-amber-600/30 border-amber-400 text-amber-200 ring-1 ring-amber-500 shadow-md"
                        : "bg-amber-950/70 border-amber-800 text-amber-200 hover:bg-amber-900/70 hover:border-amber-600"
                    }`}
                    style={{
                      left: `${clipLeft}px`,
                      width: `${clipWidth}px`,
                    }}
                    title={`BGM: ${bgm.title}\nStart: ${bgm.start_time_sec.toFixed(1)}s | Duration: ${bgm.duration_sec.toFixed(1)}s | Volume: ${Math.round(bgm.volume * 100)}%${bgm.loop ? " | Loop" : ""}`}
                  >
                    {/* Left Trim Handle */}
                    {!isLocked && (
                      <div
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setTrimming({
                            type: "bgm",
                            id: bgm.id,
                            edge: "left",
                            startMouseX: e.clientX,
                            initialDuration: bgm.duration_sec,
                            initialStartTimeSec: bgm.start_time_sec,
                          });
                        }}
                        className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-amber-400 z-20"
                        data-timeline-trim
                        title="Drag to trim start"
                      />
                    )}

                    {/* Clip Body: Title, Loop badge, Volume */}
                    <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden pointer-events-none">
                      <span className="text-[10px] font-bold text-amber-100 truncate">
                        {bgm.title}
                      </span>
                      {bgm.loop && (
                        <span className="text-[8px] text-amber-400 bg-amber-900/60 p-0.5 rounded shrink-0 flex items-center" title="Looping">
                          <Icons.Rotate className="w-2.5 h-2.5" />
                        </span>
                      )}
                      <span className="text-[8px] text-amber-400/80 font-mono shrink-0">
                        {Math.round(bgm.volume * 100)}%
                      </span>
                    </div>

                    {/* Clip Right Controls: Waveform, Duplicate, Delete */}
                    <div className="flex items-center gap-1 shrink-0 z-10">
                      <AudioPeaks peaks={bgm.measured_peaks} />

                      {/* Duplicate Button */}
                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => duplicateAudioClip(prev, bgm.id, "bgm"));
                          }}
                          className="hover:text-white text-amber-400/80 p-0.5"
                          aria-label="Duplicate BGM Clip"
                          title="Duplicate BGM Clip"
                        >
                          <Icons.Copy className="w-2.5 h-2.5" />
                        </button>
                      )}

                      {/* Delete Button */}
                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => deleteAudioClip(prev, bgm.id, "bgm"));
                          }}
                          className="hover:text-rose-300 text-rose-400/80 p-0.5"
                          aria-label="Delete BGM Clip"
                          title="Delete BGM Clip"
                        >
                          <Icons.Trash className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>

                    {/* Right Trim Handle */}
                    {!isLocked && (
                      <div
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setTrimming({
                            type: "bgm",
                            id: bgm.id,
                            edge: "right",
                            startMouseX: e.clientX,
                            initialDuration: bgm.duration_sec,
                          });
                        }}
                        className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-amber-400 z-20"
                        data-timeline-trim
                        title="Drag to trim duration"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {/* TRACK 6: SFX Track (Interactive SFX Cues + Trim Handles + Drag + Drop Zone) */}
            {showSfx && (<div data-timeline-lane="SFX" {...laneProps("SFX")}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
                e.stopPropagation();
                e.preventDefault();
                const contractJson = e.dataTransfer.getData("application/panelflow-audio-contract");
                if (contractJson) {
                  try {
                    const contract = JSON.parse(contractJson);
                    const rect = e.currentTarget.getBoundingClientRect();
                    const dropSec = Math.max(0, (e.clientX - rect.left) / pxPerSec);
                    onUpdateState((prev) => applyAudioContractToState(prev, contract, dropSec));
                  } catch (err) {
                    console.error("Drop error:", err);
                  }
                }
              }}
              className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40 group/track"
            >
              {sfxList.length === 0 && (
                <div
                  onClick={() => onOpenAudioLibrary?.("sfx")}
                  className="absolute inset-0 flex items-center justify-center text-[10px] text-cyan-500/60 hover:text-cyan-400 hover:bg-cyan-950/20 cursor-pointer border border-dashed border-cyan-900/40 rounded transition-colors"
                >
                  + Click to Add Sound Effects from Library
                </div>
              )}

              {sfxList.map((sfx) => {
                const sLeft = sfx.start_time_sec * pxPerSec;
                const sWidth = Math.max(55, sfx.duration_sec * pxPerSec);
                const isSelected = state.selected_object?.type === "sfx" && state.selected_object.id === sfx.id;
                const isLocked = getTimelineTrackState(state.track_states, "SFX").locked;

                return (
                  <div
                    key={sfx.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      onUpdateState((s) => ({
                        ...s,
                        selected_object: { type: "sfx", id: sfx.id },
                      }));
                    }}
                    onMouseDown={(e) => {
                      if (isLocked) return;
                      e.stopPropagation();
                      setDraggingAudioClip({
                        type: "sfx",
                        id: sfx.id,
                        startMouseX: e.clientX,
                        initialStartSec: sfx.start_time_sec,
                      });
                    }}
                    className={`absolute h-6 rounded-md px-1.5 flex items-center justify-between text-xs font-mono border transition-all cursor-move select-none ${
                      isSelected
                        ? "bg-cyan-600/30 border-cyan-400 text-cyan-200 ring-1 ring-cyan-500 shadow-md"
                        : "bg-cyan-950/80 border-cyan-800 text-cyan-200 hover:bg-cyan-900/80 hover:border-cyan-600"
                    }`}
                    style={{
                      left: `${sLeft}px`,
                      width: `${sWidth}px`,
                    }}
                    title={`SFX: ${sfx.name} (${sfx.category})\nStart: ${sfx.start_time_sec.toFixed(1)}s | Duration: ${sfx.duration_sec.toFixed(1)}s | Volume: ${Math.round(sfx.volume * 100)}%`}
                  >
                    {/* Left Trim Handle */}
                    {!isLocked && (
                      <div
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setTrimming({
                            type: "sfx",
                            id: sfx.id,
                            edge: "left",
                            startMouseX: e.clientX,
                            initialDuration: sfx.duration_sec,
                            initialStartTimeSec: sfx.start_time_sec,
                          });
                        }}
                        className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400 z-20"
                        data-timeline-trim
                        title="Drag to trim start"
                      />
                    )}

                    <div className="flex items-center gap-1 overflow-hidden pointer-events-none">
                      <Icons.Volume className="w-3 h-3 text-cyan-400 shrink-0" />
                      <span className="truncate text-[10px] font-bold text-cyan-100">
                        {sfx.name}
                      </span>
                    </div>

                    <div className="flex items-center gap-1 shrink-0 z-10">
                      <span className="text-[8px] text-cyan-400/80 font-mono pointer-events-none">
                        {Math.round(sfx.volume * 100)}%
                      </span>

                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => duplicateAudioClip(prev, sfx.id, "sfx"));
                          }}
                          className="hover:text-white text-cyan-400/80 p-0.5"
                          aria-label="Duplicate SFX Clip"
                          title="Duplicate SFX Clip"
                        >
                          <Icons.Copy className="w-2.5 h-2.5" />
                        </button>
                      )}

                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => deleteAudioClip(prev, sfx.id, "sfx"));
                          }}
                          className="hover:text-rose-300 text-rose-400/80 p-0.5"
                          aria-label="Delete SFX Clip"
                          title="Delete SFX Clip"
                        >
                          <Icons.Trash className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>

                    {/* Right Trim Handle */}
                    {!isLocked && (
                      <div
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setTrimming({
                            type: "sfx",
                            id: sfx.id,
                            edge: "right",
                            startMouseX: e.clientX,
                            initialDuration: sfx.duration_sec,
                          });
                        }}
                        className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-cyan-400 z-20"
                        data-timeline-trim
                        title="Drag to trim duration"
                      />
                    )}
                  </div>
                );
              })}
            </div>)}
          </div>
        </div>
      </div>
    </div>
  );
};
