import React, { useRef, useState, useEffect, useCallback } from "react";
import { Icons, Button } from "@panelflow/ui";
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

export const StoryEditorTimeline: React.FC<StoryEditorTimelineProps> = ({
  state,
  onUpdateState,
  onSelectScene,
  onSelectLayer,
  onAddBlankScene,
  onSplitScene,
  onDuplicateScene,
  onDeleteScene,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
  onSelectMotionBadge,
  onOpenNarrationStudio,
  onOpenAudioLibrary,
}) => {
  const rulerRef = useRef<HTMLDivElement>(null);
  const snappingEnabled = state.snapping !== false;

  // Drag and drop states
  const [dragOverInsertIndex, setDragOverInsertIndex] = useState<number | null>(null);
  const [dragOverSceneId, setDragOverSceneId] = useState<string | null>(null);

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

  const totalDurationSec = Math.max(30, state.scenes.reduce((acc, s) => acc + s.duration_sec, 0));

  // Pixels per second based on zoom slider (zoom_level 50 to 250)
  const pxPerSec = 40 * (state.zoom_level / 100);
  const totalTimelineWidthPx = Math.max(1100, totalDurationSec * pxPerSec + 200);

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

          onUpdateState((prev) => {
            const idx = prev.scenes.findIndex((s) => s.id === trimming.id);
            if (idx < 0) return prev;
            const updated = [...prev.scenes];
            updated[idx] = { ...updated[idx], duration_sec: nextDuration };

            // Ripple shift start_time_sec for all scenes
            let run = 0;
            const resynced = updated.map((sc, i) => {
              const r = { ...sc, sequence: i + 1, start_time_sec: run };
              run += sc.duration_sec;
              return r;
            });

            // Ripple shift linked narration preserving scene_offset_sec
            const resyncedNarr = prev.narration_clips.map((n) => {
              if (n.scene_id && n.linked_to_scene !== false) {
                const parent = resynced.find((s) => s.id === n.scene_id);
                if (parent) {
                  return {
                    ...n,
                    start_time_sec: Math.round((parent.start_time_sec + (n.scene_offset_sec || 0)) * 100) / 100,
                  };
                }
              }
              return n;
            });

            return {
              ...prev,
              scenes: resynced,
              narration_clips: resyncedNarr,
            };
          });
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
                  if (ly.id !== layerId) return ly;
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
            const parent = n.scene_id ? prev.scenes.find((s) => s.id === n.scene_id) : undefined;
            const newOffset = parent ? Math.max(0, Math.round((newStart - parent.start_time_sec) * 10) / 10) : (n.scene_offset_sec || 0);
            return {
              ...n,
              start_time_sec: newStart,
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
          let run = 0;
          for (const sc of state.scenes) {
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
      if (!rulerRef.current) return 0;
      const rect = rulerRef.current.getBoundingClientRect();
      const clickX = clientX - rect.left;
      let targetSec = Math.max(0, Math.min(totalDurationSec, clickX / pxPerSec));

      if (snap) {
        // Tight 0.12s threshold so snapping never feels sticky or stuttery
        let cumulative = 0;
        for (const scene of state.scenes) {
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
      const initialSec = getTimeFromClientX(e.clientX, snappingEnabled && !e.shiftKey);
      lastScrubSecRef.current = initialSec;
      onUpdateState((s) => ({ ...s, playhead_sec: initialSec }));

      const handlePointerMove = (ev: PointerEvent) => {
        ev.preventDefault();
        if (scrubRafRef.current) cancelAnimationFrame(scrubRafRef.current);
        scrubRafRef.current = requestAnimationFrame(() => {
          const sec = getTimeFromClientX(ev.clientX, snappingEnabled && !ev.shiftKey);
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
        setIsScrubbing(false);
        onUpdateState((s) => ({
          ...s,
          playhead_sec: Math.round(lastScrubSecRef.current * 100) / 100,
        }));
      };

      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [state.is_playing, getTimeFromClientX, snappingEnabled, onUpdateState]
  );

  // Reorder scenes state update
  const handleReorderScenes = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return;
    onUpdateState((prev) => {
      const copy = [...prev.scenes];
      const [moved] = copy.splice(fromIndex, 1);
      const target = toIndex > fromIndex ? toIndex - 1 : toIndex;
      copy.splice(target, 0, moved);

      let running = 0;
      const resynced = copy.map((sc, idx) => {
        const item = { ...sc, sequence: idx + 1, start_time_sec: running };
        running += sc.duration_sec;
        return item;
      });

      // Shift linked narration preserving scene_offset_sec
      const resyncedNarr = prev.narration_clips.map((n) => {
        if (n.scene_id && n.linked_to_scene !== false) {
          const parent = resynced.find((s) => s.id === n.scene_id);
          if (parent) {
            return {
              ...n,
              start_time_sec: Math.round((parent.start_time_sec + (n.scene_offset_sec || 0)) * 100) / 100,
            };
          }
        }
        return n;
      });

      return {
        ...prev,
        scenes: resynced,
        narration_clips: resyncedNarr,
        selected_object: { type: "scene", id: moved.id },
      };
    });
  };

  // Insert new scene from panel at index
  const handleInsertSceneFromPanel = (panelData: any, atIndex: number) => {
    onUpdateState((prev) => {
      const newSceneId = `scene_${Date.now()}`;
      const newLayerId = `layer_${Date.now()}`;
      const newLayer: VisualLayer = {
        id: newLayerId,
        source_page_id: panelData.pageId,
        source_panel_id: panelData.panelId,
        image_url: panelData.imageUrl,
        page_sequence: panelData.pageSequence,
        crop: panelData.crop,
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

      const updated = [...prev.scenes];
      const safeIndex = Math.max(0, Math.min(updated.length, atIndex));
      updated.splice(safeIndex, 0, newScene);

      let running = 0;
      const resynced = updated.map((sc, i) => {
        const s = { ...sc, sequence: i + 1, start_time_sec: running };
        running += sc.duration_sec;
        return s;
      });

      return {
        ...prev,
        scenes: resynced,
        selected_object: { type: "scene", id: newSceneId },
        playhead_sec: newScene.start_time_sec,
      };
    });
  };

  // Add layer to existing scene from panel
  const handleAddLayerToScene = (panelData: any, sceneId: string) => {
    onUpdateState((prev) => {
      const targetScene = prev.scenes.find((s) => s.id === sceneId);
      if (!targetScene) return prev;
      const newLayerId = `layer_${Date.now()}`;
      const newLayer: VisualLayer = {
        id: newLayerId,
        source_page_id: panelData.pageId,
        source_panel_id: panelData.panelId,
        image_url: panelData.imageUrl,
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
  const ticksCount = Math.ceil(totalDurationSec / tickIntervalSec) + 1;

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

  // Toggle track visibility or lock
  const toggleTrack = (trackName: string, prop: "visible" | "locked") => {
    onUpdateState((prev) => {
      const current = prev.track_states?.[trackName] || { visible: true, locked: false };
      return {
        ...prev,
        track_states: {
          ...prev.track_states,
          [trackName]: {
            ...current,
            [prop]: !current[prop],
          },
        },
      };
    });
  };

  // Default mock SFX cues if none provided
  const sfxList: SfxCue[] = state.sfx_cues?.length
    ? state.sfx_cues
    : [
        { id: "sfx_1", name: "Wind", category: "ambience", start_time_sec: 1.0, duration_sec: 4.0, volume: 0.7 },
        { id: "sfx_2", name: "Footsteps", category: "movement", start_time_sec: 7.5, duration_sec: 3.5, volume: 0.8 },
        { id: "sfx_3", name: "Magic", category: "magic", start_time_sec: 14.0, duration_sec: 3.0, volume: 0.9 },
        { id: "sfx_4", name: "Whoosh", category: "transition", start_time_sec: 22.0, duration_sec: 2.5, volume: 0.8 },
      ];

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
    <div className={`bg-zinc-950 border-t border-zinc-800 flex flex-col select-none shrink-0 overflow-hidden font-sans transition-all duration-200 ${
      isAdvancedMode ? "h-[320px]" : "h-[268px]"
    }`}>
      {/* 1. Timeline Toolbar */}
      <div className="h-10 px-4 bg-zinc-900/95 border-b border-zinc-800 flex items-center justify-between shrink-0">
        {/* Left Editing Tools */}
        <div className="flex items-center gap-1.5 text-zinc-400">
          <button
            type="button"
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1.5 rounded hover:text-white disabled:opacity-30 transition-colors"
            title="Undo (Ctrl+Z)"
          >
            <Icons.Undo className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1.5 rounded hover:text-white disabled:opacity-30 transition-colors"
            title="Redo (Ctrl+Y)"
          >
            <Icons.Redo className="w-3.5 h-3.5" />
          </button>

          <div className="h-4 w-px bg-zinc-800 mx-1" />

          {selectedSceneId && (
            <button
              type="button"
              onClick={() => onDeleteScene(selectedSceneId)}
              className="p-1.5 rounded hover:text-rose-400 transition-colors"
              title="Delete Selected Clip (Del)"
            >
              <Icons.Trash className="w-3.5 h-3.5" />
            </button>
          )}

          {selectedSceneId && (
            <button
              type="button"
              onClick={() => onSplitScene(selectedSceneId, state.playhead_sec)}
              className="p-1.5 rounded hover:text-indigo-400 transition-colors"
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
            title="Ripple Edit: subsequent scenes automatically slide when trimming or moving clips"
          >
            <Icons.Layers className="w-3 h-3" />
            <span>Ripple: {state.ripple_edit !== false ? "ON" : "OFF"}</span>
          </button>

          <button
            type="button"
            onClick={onAddBlankScene}
            className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 font-medium flex items-center gap-1"
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
            title="Return to Start (00:00)"
          >
            <Icons.Rotate className="w-3.5 h-3.5" />
          </button>

          {/* Step Back -0.1s */}
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: Math.max(0, s.playhead_sec - 0.1) }))}
            className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
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
                : "bg-indigo-600 hover:bg-indigo-500 text-white ring-2 ring-indigo-400/40"
            }`}
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
            title="Zoom Timeline Out"
          >
            <Icons.ZoomOut className="w-3.5 h-3.5" />
          </button>
          <input
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
            title="Zoom Timeline In"
          >
            <Icons.ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Multi-track Container (Track Headers Left + Track Canvas Right) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Track Headers Column */}
        <div className="w-44 bg-zinc-950 border-r border-zinc-800 flex flex-col shrink-0 text-xs select-none">
          {/* Header spacer for ruler */}
          <div className="h-6 border-b border-zinc-800/80 px-3 flex items-center text-[10px] font-mono text-zinc-500">
            TRACKS
          </div>

          {/* Track 1: Narration */}
          <div className="h-8 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/30">
            <span className="flex items-center gap-1.5 font-medium text-emerald-400 text-[11px]">
              <Icons.MessageSquare className="w-3.5 h-3.5" /> Narration
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              {onOpenNarrationStudio && (
                <button
                  type="button"
                  onClick={() => onOpenNarrationStudio()}
                  className="px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-800 text-[9px] font-semibold text-emerald-300 hover:bg-emerald-900 hover:text-white transition-colors"
                  title="Open Narration Studio"
                >
                  Studio
                </button>
              )}
              <button onClick={() => toggleTrack("narration", "visible")} className="hover:text-white p-0.5">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("narration", "locked")} className="hover:text-white p-0.5">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Track 2: Visuals */}
          <div className="h-10 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/40">
            <span className="flex items-center gap-1.5 font-medium text-indigo-400 text-[11px]">
              <Icons.Film className="w-3.5 h-3.5" /> Visuals
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              <button onClick={() => toggleTrack("visuals", "visible")} className="hover:text-white p-0.5">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("visuals", "locked")} className="hover:text-white p-0.5">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Track 3: Layers */}
          <div className="h-8 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/30">
            <span className="flex items-center gap-1.5 font-medium text-purple-400 text-[11px]">
              <Icons.Layers className="w-3.5 h-3.5" /> Layers
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              <button onClick={() => toggleTrack("layer2", "visible")} className="hover:text-white p-0.5">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("layer2", "locked")} className="hover:text-white p-0.5">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Track 4: Motion / FX */}
          <div className="h-8 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/30">
            <span className="flex items-center gap-1.5 font-medium text-fuchsia-400 text-[11px]">
              <Icons.Sparkles className="w-3.5 h-3.5" /> Motion / FX
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              <button onClick={() => toggleTrack("motion", "visible")} className="hover:text-white p-0.5">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("motion", "locked")} className="hover:text-white p-0.5">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Track 5: Music */}
          <div className="h-8 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/30">
            <span className="flex items-center gap-1.5 font-medium text-amber-400 text-[11px]">
              <Icons.Music className="w-3.5 h-3.5" /> Music
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              {onOpenAudioLibrary && (
                <button
                  type="button"
                  onClick={() => onOpenAudioLibrary("music")}
                  className="px-1.5 py-0.5 rounded bg-amber-950 border border-amber-800 text-[9px] font-semibold text-amber-300 hover:bg-amber-900 hover:text-white transition-colors"
                  title="Open Audio Library (Music)"
                >
                  + Add
                </button>
              )}
              <button onClick={() => toggleTrack("music", "visible")} className="hover:text-white p-0.5" title="Toggle Music Track Mute">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("music", "locked")} className="hover:text-white p-0.5" title="Toggle Music Track Lock">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Track 6: SFX */}
          <div className="h-8 border-b border-zinc-800/40 px-3 flex items-center justify-between bg-zinc-900/30">
            <span className="flex items-center gap-1.5 font-medium text-cyan-400 text-[11px]">
              <Icons.Volume className="w-3.5 h-3.5" /> SFX
            </span>
            <div className="flex items-center gap-1 text-zinc-500">
              {onOpenAudioLibrary && (
                <button
                  type="button"
                  onClick={() => onOpenAudioLibrary("sfx")}
                  className="px-1.5 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-[9px] font-semibold text-cyan-300 hover:bg-cyan-900 hover:text-white transition-colors"
                  title="Open Audio Library (SFX)"
                >
                  + Add
                </button>
              )}
              <button onClick={() => toggleTrack("sfx", "visible")} className="hover:text-white p-0.5" title="Toggle SFX Track Mute">
                <Icons.Eye className="w-3 h-3" />
              </button>
              <button onClick={() => toggleTrack("sfx", "locked")} className="hover:text-white p-0.5" title="Toggle SFX Track Lock">
                <Icons.Lock className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Right Shared Time Ruler & Synchronized Track Lanes */}
        <div className="flex-1 overflow-x-auto overflow-y-hidden bg-zinc-950 relative select-none">
          <div
            ref={rulerRef}
            onPointerDown={handleStartScrub}
            className="relative h-full cursor-pointer"
            style={{ width: `${totalTimelineWidthPx}px` }}
          >
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
              className={`absolute top-0 bottom-0 z-30 pointer-events-auto transition-opacity ${
                isScrubbing ? "opacity-100" : "opacity-95"
              }`}
              style={{ left: `${state.playhead_sec * pxPerSec}px` }}
            >
              {/* Laser line with cyan glow while scrubbing */}
              <div
                className={`w-0.5 h-full ${
                  isScrubbing
                    ? "bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.9)]"
                    : "bg-indigo-500 shadow-md"
                }`}
              />

              {/* Invisible wider grab handle along vertical line */}
              <div
                onPointerDown={handleStartScrub}
                className="absolute top-0 bottom-0 -left-2.5 w-5 cursor-ew-resize"
                title="Drag Scrubber"
              />

              {/* Diamond Playhead Handle */}
              <div
                onPointerDown={handleStartScrub}
                className={`absolute -left-[7px] -top-1.5 w-4 h-4 rounded-sm rotate-45 cursor-ew-resize shadow-lg transition-transform ${
                  isScrubbing
                    ? "bg-cyan-400 scale-125 ring-2 ring-cyan-200"
                    : "bg-indigo-500 hover:scale-115 hover:bg-indigo-400"
                }`}
              >
                {/* Live time tooltip while scrubbing */}
                {isScrubbing && (
                  <div className="absolute -top-7 left-1/2 -translate-x-1/2 -rotate-45 bg-zinc-950 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold px-1.5 py-0.5 rounded shadow-xl whitespace-nowrap pointer-events-none">
                    {formatRulerTime(state.playhead_sec)}
                  </div>
                )}
              </div>
            </div>

            {/* TRACK 1: Narration Track */}
            <div className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {state.narration_clips.map((narration) => {
                const clipLeft = narration.start_time_sec * pxPerSec;
                const clipWidth = Math.max(120, narration.duration_sec * pxPerSec);
                const isSelected =
                  state.selected_object?.type === "narration" && state.selected_object.id === narration.id;
                const isLinked = narration.linked_to_scene !== false;

                return (
                  <div
                    key={narration.id}
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
                      isSelected
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
                        <span className="px-1 py-0.2 rounded bg-emerald-950 text-emerald-400 text-[8px] font-bold border border-emerald-700/60" title="Review: Approved">
                          ✓
                        </span>
                      ) : narration.review_status === "NEEDS_REVIEW" ? (
                        <span className="px-1 py-0.2 rounded bg-amber-950 text-amber-400 text-[8px] font-bold border border-amber-700/60" title="Review: Needs Review">
                          ?
                        </span>
                      ) : (
                        <span className="px-1 py-0.2 rounded bg-zinc-900 text-zinc-400 text-[8px] font-mono border border-zinc-800" title="Review: Draft">
                          D
                        </span>
                      )}

                      {/* Audio Generation Status */}
                      {narration.status === "OUTDATED" ? (
                        <span className="px-1 py-0.2 rounded bg-amber-900 text-amber-200 font-bold border border-amber-500 text-[8px] animate-pulse" title="Audio Take Outdated">
                          ⚠
                        </span>
                      ) : narration.status === "READY" ? (
                        <span className="text-emerald-400 text-[9px] font-bold" title="Audio Take Ready">
                          ●
                        </span>
                      ) : narration.status === "PROCESSING" ? (
                        <span className="text-blue-400 text-[9px] animate-spin font-bold" title="Audio Generating">
                          ⏳
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
                        className={`px-1 py-0.2 rounded text-[8px] font-bold border transition-colors ${
                          isLinked
                            ? "bg-emerald-800/60 border-emerald-600 text-emerald-200"
                            : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-white"
                        }`}
                        title={isLinked ? "Linked to scene (shifts with scene)" : "Unlinked (independent time)"}
                      >
                        {isLinked ? "🔗" : "🔓"}
                      </button>

                      {/* Mini Waveform graphic */}
                      <div className="flex items-center gap-0.5 h-3 opacity-60 pointer-events-none">
                        <span className="w-0.5 h-2 bg-emerald-400 rounded" />
                        <span className="w-0.5 h-3 bg-emerald-400 rounded" />
                        <span className="w-0.5 h-1.5 bg-emerald-400 rounded" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* TRACK 2: Visuals Track (Filmstrip Scenes + Drop Indicators + Trim Handles) */}
            <div className="h-10 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {(() => {
                let sceneOffsetSec = 0;
                return state.scenes.map((scene, idx) => {
                  const clipLeft = sceneOffsetSec * pxPerSec;
                  const clipWidth = Math.max(90, scene.duration_sec * pxPerSec);
                  const isSelected = selectedSceneId === scene.id;
                  const isDragOverScene = dragOverSceneId === scene.id;
                  const isInsertTargetBefore = dragOverInsertIndex === idx;

                  sceneOffsetSec += scene.duration_sec;

                  return (
                    <React.Fragment key={scene.id}>
                      {/* Inter-scene drop zone BEFORE this scene */}
                      <div
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = "copy";
                          setDragOverInsertIndex(idx);
                        }}
                        onDragLeave={() => {
                          if (dragOverInsertIndex === idx) setDragOverInsertIndex(null);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOverInsertIndex(null);
                          const panelData = e.dataTransfer.getData("application/panelflow-panel");
                          const reorderData = e.dataTransfer.getData("application/panelflow-scene-reorder");
                          const layerMoveData = e.dataTransfer.getData("application/panelflow-layer-move");

                          if (panelData) {
                            try {
                              handleInsertSceneFromPanel(JSON.parse(panelData), idx);
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
                        className="absolute h-10 w-4 -ml-2 z-20 flex items-center justify-center cursor-pointer"
                        style={{ left: `${clipLeft}px` }}
                      >
                        {isInsertTargetBefore && (
                          <div className="w-1.5 h-8 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee] animate-pulse" />
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
                        draggable={!state.track_states?.["Visuals"]?.locked}
                        onDragStart={(e) => {
                          e.dataTransfer.setData(
                            "application/panelflow-scene-reorder",
                            JSON.stringify({ sceneId: scene.id, fromIndex: idx })
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = "copy";
                          setDragOverSceneId(scene.id);
                        }}
                        onDragLeave={() => {
                          if (dragOverSceneId === scene.id) setDragOverSceneId(null);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOverSceneId(null);
                          const panelData = e.dataTransfer.getData("application/panelflow-panel");
                          const layerMoveData = e.dataTransfer.getData("application/panelflow-layer-move");

                          if (panelData) {
                            try {
                              handleAddLayerToScene(JSON.parse(panelData), scene.id);
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
                            : "bg-zinc-900 border-zinc-700 hover:border-zinc-500"
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
                          title="Drag to trim left boundary"
                        />

                        {/* Filmstrip thumbnails */}
                        <div className="flex items-center h-full w-full overflow-hidden pointer-events-none px-1">
                          {scene.layers.length > 0 ? (
                            scene.layers.map((ly) => (
                              <img
                                key={ly.id}
                                src={ly.image_url}
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
                            <span className="ml-auto text-[9px] bg-cyan-500 text-black px-1.5 py-0.5 rounded font-bold shrink-0">
                              + Layer
                            </span>
                          )}
                        </div>

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
                          title="Drag to trim right boundary"
                        />
                      </div>
                    </React.Fragment>
                  );
                });
              })()}

              {/* Inter-scene drop zone AFTER the last scene */}
              {(() => {
                const totalSec = state.scenes.reduce((acc, s) => acc + s.duration_sec, 0);
                const endLeft = totalSec * pxPerSec;
                const lastIdx = state.scenes.length;
                const isTarget = dragOverInsertIndex === lastIdx;

                return (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "copy";
                      setDragOverInsertIndex(lastIdx);
                    }}
                    onDragLeave={() => {
                      if (dragOverInsertIndex === lastIdx) setDragOverInsertIndex(null);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOverInsertIndex(null);
                      const panelData = e.dataTransfer.getData("application/panelflow-panel");
                      if (panelData) {
                        try {
                          handleInsertSceneFromPanel(JSON.parse(panelData), lastIdx);
                        } catch (err) {
                          console.error(err);
                        }
                      }
                    }}
                    className="absolute h-10 w-8 flex items-center justify-center cursor-pointer z-20"
                    style={{ left: `${endLeft}px` }}
                  >
                    {isTarget && (
                      <div className="w-1.5 h-8 bg-cyan-400 rounded-full shadow-[0_0_8px_#22d3ee] animate-pulse" />
                    )}
                  </div>
                );
              })()}
            </div>

            {/* TRACK 3: Layers Track (Independent Layer Blocks + Trim Handles) */}
            <div className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {(() => {
                let sceneOffsetSec = 0;
                return state.scenes.map((scene) => {
                  const clipLeft = sceneOffsetSec * pxPerSec;
                  sceneOffsetSec += scene.duration_sec;

                  return scene.layers.map((ly) => {
                    const startOffset = ly.start_offset_sec ?? 0;
                    const duration = ly.duration_sec ?? scene.duration_sec;
                    const lLeft = clipLeft + startOffset * pxPerSec;
                    const lWidth = Math.max(50, duration * pxPerSec);
                    const isSelected =
                      state.selected_object?.type === "layer" && state.selected_object.id === ly.id;

                    return (
                      <div
                        key={ly.id}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData(
                            "application/panelflow-layer-move",
                            JSON.stringify({ layerId: ly.id, fromSceneId: scene.id })
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectLayer(ly.id, scene.id);
                        }}
                        className={`absolute h-6 rounded-md border px-1.5 flex items-center justify-between cursor-pointer shadow transition-all ${
                          isSelected
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
                            title="Trim layer start"
                          />
                        )}

                        <div className="flex items-center gap-1 overflow-hidden pointer-events-none">
                          <img src={ly.image_url} alt="Layer" className="w-3.5 h-3.5 rounded object-cover shrink-0" />
                          <span className="text-[10px] font-medium text-purple-200 truncate">
                            {ly.name || "Layer"}
                          </span>
                        </div>

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
                            title="Trim layer duration"
                          />
                        )}
                      </div>
                    );
                  });
                });
              })()}
            </div>

            {/* TRACK 4: Motion / FX Track (Clickable Badges) */}
            <div className="h-8 border-b border-zinc-800/30 relative flex items-center bg-zinc-950/40">
              {(() => {
                let sceneOffsetSec = 0;
                return state.scenes.map((scene) => {
                  const clipLeft = sceneOffsetSec * pxPerSec;
                  sceneOffsetSec += scene.duration_sec;

                  const hasCamera = scene.camera && scene.camera.preset !== "static";
                  const motionLayer = scene.layers.find(
                    (l) => (l.motion_preset && l.motion_preset !== "none") || l.animation_config?.preset === "custom"
                  );
                  if (!motionLayer && !hasCamera) return null;

                  return (
                    <div
                      key={`motion_${scene.id}`}
                      className="absolute flex items-center gap-1.5"
                      style={{ left: `${clipLeft}px` }}
                    >
                      {/* Layer Motion Badge */}
                      {motionLayer && (
                        <div
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectLayer(motionLayer.id, scene.id);
                            onSelectMotionBadge?.(scene.id, motionLayer.id);
                          }}
                          className="h-6 rounded-md px-2 flex items-center gap-1 text-[10px] font-bold text-fuchsia-200 bg-fuchsia-950/80 border border-fuchsia-800 shadow-sm hover:border-fuchsia-400 cursor-pointer transition-all"
                          title="Click to configure layer motion in Inspector"
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
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectScene(scene.id);
                            onSelectMotionBadge?.(scene.id);
                          }}
                          className="h-6 rounded-md px-2 flex items-center gap-1 text-[10px] font-bold text-cyan-200 bg-cyan-950/80 border border-cyan-800 shadow-sm hover:border-cyan-400 cursor-pointer transition-all"
                          title="Click to configure scene camera in Inspector"
                        >
                          <Icons.Film className="w-3 h-3 text-cyan-400" />
                          <span className="truncate max-w-[90px]">
                            Cam: {presetLabels[scene.camera?.preset || ""] || scene.camera?.preset}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>

            {/* TRACK 5: Music Track (Interactive BGM Clips + Trim Handles + Drag + Drop Zone) */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
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
                const isLocked = state.track_states?.["Music"]?.locked;

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
                        title="Drag to trim start"
                      />
                    )}

                    {/* Clip Body: Title, Loop badge, Volume */}
                    <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden pointer-events-none">
                      <span className="text-[10px] font-bold text-amber-100 truncate">
                        {bgm.title}
                      </span>
                      {bgm.loop && (
                        <span className="text-[8px] text-amber-400 bg-amber-900/60 px-1 rounded shrink-0">
                          🔁
                        </span>
                      )}
                      <span className="text-[8px] text-amber-400/80 font-mono shrink-0">
                        {Math.round(bgm.volume * 100)}%
                      </span>
                    </div>

                    {/* Clip Right Controls: Waveform, Duplicate, Delete */}
                    <div className="flex items-center gap-1 shrink-0 z-10">
                      {/* Real Waveform or Unmeasured Indicator */}
                      {bgm.measured_peaks && bgm.measured_peaks.length > 0 ? (
                        <div className="flex items-center gap-0.5 h-3 opacity-80 pointer-events-none">
                          {bgm.measured_peaks.slice(0, 10).map((peak, idx) => (
                            <span
                              key={idx}
                              className="w-0.5 bg-amber-400 rounded-sm"
                              style={{ height: `${Math.max(2, Math.round(peak * 12))}px` }}
                            />
                          ))}
                        </div>
                      ) : (
                        <span className="text-[9px] text-amber-500/70 pointer-events-none" title="Real waveform unmeasured">
                          ♫
                        </span>
                      )}

                      {/* Duplicate Button */}
                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => duplicateAudioClip(prev, bgm.id, "bgm"));
                          }}
                          className="hover:text-white text-amber-400/80 p-0.5 text-[9px]"
                          title="Duplicate BGM Clip"
                        >
                          ⎘
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
                          className="hover:text-rose-300 text-rose-400/80 p-0.5 text-[9px]"
                          title="Delete BGM Clip"
                        >
                          ✕
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
                        title="Drag to trim duration"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {/* TRACK 6: SFX Track (Interactive SFX Cues + Trim Handles + Drag + Drop Zone) */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
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
                const isLocked = state.track_states?.["SFX"]?.locked;

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
                          className="hover:text-white text-cyan-400/80 p-0.5 text-[9px]"
                          title="Duplicate SFX Clip"
                        >
                          ⎘
                        </button>
                      )}

                      {!isLocked && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onUpdateState((prev) => deleteAudioClip(prev, sfx.id, "sfx"));
                          }}
                          className="hover:text-rose-300 text-rose-400/80 p-0.5 text-[9px]"
                          title="Delete SFX Clip"
                        >
                          ✕
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
                        title="Drag to trim duration"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
