import React, { useRef, useState, useEffect } from "react";
import { Icons, Button } from "@panelflow/ui";
import { api } from "@panelflow/api-client";
import { fitCompositionFrame } from "./editorWorkspace";
import { sceneAtTime, sceneTimelineDuration } from "./sceneTiming";
import { resolveBackground } from "./backgroundSettings";
import { BackgroundPreview, foregroundSize, resolveBackgroundSource } from "./BackgroundPreview";
import type { VideoScene, VisualLayer, StoryEditorState } from "@panelflow/shared-types";
import {
  evaluateLayerTransform,
  evaluateCameraTransform,
  evaluateSceneTransition,
  computeMotionPathPoints,
} from "./animationEngine";

interface VideoCompositionCanvasProps {
  previewOnly?: boolean;
  state: StoryEditorState;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
  onSelectLayer: (layerId: string, sceneId: string) => void;
  projectId?: string;
}

export const VideoCompositionCanvas: React.FC<VideoCompositionCanvasProps> = ({
  state,
  onUpdateState,
  onSelectLayer,
  previewOnly = false,
  projectId,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [viewZoom, setViewZoom] = useState("fit");
  const [frameSize, setFrameSize] = useState({ width: 800, height: 450 });
  const [fullscreenError, setFullscreenError] = useState<string | null>(null);
  const [imageSizes, setImageSizes] = useState<Record<string, { width: number; height: number }>>({});
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const measure = () => setFrameSize({ width: Math.max(1, frame.clientWidth - 32), height: Math.max(1, frame.clientHeight - 32) });
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(frame);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  const [showSafeZones, setShowSafeZones] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);

  const getLayerImageUrl = (layer: VisualLayer): string => {
    const projId = projectId || state.project_id;
    if (projId && layer.source_panel_id && (!layer.image_url || layer.image_url.includes("/pages/"))) {
      return `${api.getPanelImageUrl(projId, layer.source_panel_id)}?v=${encodeURIComponent(layer.crop_filename || "detected")}`;
    }
    return layer.image_url;
  };
  type ResizeHandle = "nw" | "ne" | "se" | "sw" | "n" | "s" | "e" | "w" | "center" | "rotate";

  const [activeHandleDrag, setActiveHandleDrag] = useState<{
    handle: ResizeHandle;
    layerId: string;
    startMouseX: number;
    startMouseY: number;
    initialScale: number;
    initialX: number;
    initialY: number;
    centerX: number;
    centerY: number;
    initialDist: number;
  } | null>(null);
  const [isDraggingLayer, setIsDraggingLayer] = useState<boolean>(false);
  const [isCanvasDragOver, setIsCanvasDragOver] = useState<boolean>(false);
  const [dragStartPos, setDragStartPos] = useState<{ mouseX: number; mouseY: number; initialX: number; initialY: number } | null>(null);

  const totalDurationSec = sceneTimelineDuration(state.scenes);
  const activeScene = sceneAtTime(state.scenes, state.playhead_sec);

  // Playback timer loop
  useEffect(() => {
    if (!state.is_playing) return;

    let lastTimestamp = performance.now();
    let animFrame: number;

    const tick = (now: number) => {
      const deltaSec = ((now - lastTimestamp) / 1000) * playbackSpeed;
      lastTimestamp = now;

      onUpdateState((prev) => {
        const nextTime = prev.playhead_sec + deltaSec;
        const total = sceneTimelineDuration(prev.scenes);

        if (nextTime >= total) {
          // Loop or stop
          return {
            ...prev,
            playhead_sec: 0,
            is_playing: false,
          };
        }
        return {
          ...prev,
          playhead_sec: nextTime,
        };
      });

      animFrame = requestAnimationFrame(tick);
    };

    animFrame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animFrame);
  }, [state.is_playing, playbackSpeed, onUpdateState]);

  // Keyboard shortcut listener for canvas playback
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input
      if (e.defaultPrevented || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes((e.target as HTMLElement)?.tagName) || (e.target as HTMLElement)?.isContentEditable || (e.target as HTMLElement)?.closest?.("[role=dialog]")) {
        return;
      }
      // Space is owned by StoryEditorScreen; a second listener toggles twice.
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, playhead_sec: Math.max(0, s.playhead_sec - (e.shiftKey ? 1 : 0.1)) }));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, playhead_sec: Math.min(totalDurationSec, s.playhead_sec + (e.shiftKey ? 1 : 0.1)) }));
      } else if (!previewOnly && e.key.toLowerCase() === "m") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, show_motion_paths: !s.show_motion_paths }));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [totalDurationSec, onUpdateState, previewOnly]);

  // Format seconds to mm:ss.d
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    const ms = Math.floor((secs % 1) * 10);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}.${ms}`;
  };

  const [cropModalOpen, setCropModalOpen] = useState<boolean>(false);

  // Determine active selected layer
  const selectedLayerId = state.selected_object?.type === "layer" ? state.selected_object.id : null;

  // Rock-solid whole layer dragging with window pointer listeners
  const handleLayerPointerDown = (e: React.PointerEvent, layer: VisualLayer) => {
    e.stopPropagation();
    if (!activeScene) return;

    onSelectLayer(layer.id, activeScene.id);

    const startX = e.clientX;
    const startY = e.clientY;
    const initialLayerX = layer.transform.x || 0;
    const initialLayerY = layer.transform.y || 0;
    const container = containerRef.current;
    const containerRect = container ? container.getBoundingClientRect() : { width: 1000, height: 600 };

    const handlePointerMove = (ev: PointerEvent) => {
      ev.preventDefault();
      const deltaX = ev.clientX - startX;
      const deltaY = ev.clientY - startY;
      const percentX = (deltaX / containerRect.width) * 100;
      const percentY = (deltaY / containerRect.height) * 100;
      const newX = Math.round((initialLayerX + percentX) * 10) / 10;
      const newY = Math.round((initialLayerY + percentY) * 10) / 10;

      onUpdateState((prev) => ({
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== activeScene?.id) return sc;
          return {
            ...sc,
            layers: sc.layers.map((ly) => {
              if (ly.id !== layer.id) return ly;
              return {
                ...ly,
                transform: {
                  ...ly.transform,
                  x: newX,
                  y: newY,
                },
              };
            }),
          };
        }),
      }));
    };

    const handlePointerUp = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove, { passive: false });
    window.addEventListener("pointerup", handlePointerUp);
  };

  // Rock-solid bounding handle dragging (corner scales, edge midpoints, and center anchor)
  const handleHandlePointerDown = (
    e: React.PointerEvent,
    handle: ResizeHandle,
    layer: VisualLayer
  ) => {
    e.stopPropagation();
    e.preventDefault();
    if (!activeScene) return;

    onSelectLayer(layer.id, activeScene.id);

    const layerEl = (e.currentTarget.parentElement?.parentElement) as HTMLElement;
    const rect = layerEl?.getBoundingClientRect() || {
      left: e.clientX,
      top: e.clientY,
      width: 200,
      height: 200,
    };
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const initialDist = Math.max(15, Math.hypot(e.clientX - centerX, e.clientY - centerY));
    const startX = e.clientX;
    const startY = e.clientY;
    const initialScale = layer.transform.scale || 1.0;
    const initialLayerX = layer.transform.x || 0;
    const initialLayerY = layer.transform.y || 0;
    const initialRotation = layer.transform.rotation || 0;
    const startPointerAngle = Math.atan2(startY - centerY, startX - centerX) * (180 / Math.PI);
    const container = containerRef.current;
    const containerRect = container ? container.getBoundingClientRect() : { width: 1000, height: 600 };

    const handlePointerMove = (ev: PointerEvent) => {
      ev.preventDefault();
      if (handle === "center") {
        const deltaX = ev.clientX - startX;
        const deltaY = ev.clientY - startY;
        const percentX = (deltaX / containerRect.width) * 100;
        const percentY = (deltaY / containerRect.height) * 100;
        const newX = Math.round((initialLayerX + percentX) * 10) / 10;
        const newY = Math.round((initialLayerY + percentY) * 10) / 10;

        onUpdateState((prev) => ({
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id !== activeScene?.id) return sc;
            return {
              ...sc,
              layers: sc.layers.map((ly) => {
                if (ly.id !== layer.id) return ly;
                return {
                  ...ly,
                  transform: { ...ly.transform, x: newX, y: newY },
                };
              }),
            };
          }),
        }));
      } else if (handle === "rotate") {
        const currentPointerAngle = Math.atan2(ev.clientY - centerY, ev.clientX - centerX) * (180 / Math.PI);
        let deltaAngle = currentPointerAngle - startPointerAngle;
        let newRot = Math.round((initialRotation + deltaAngle) % 360);
        if (newRot < 0) newRot += 360;
        if (ev.shiftKey) {
          newRot = Math.round(newRot / 15) * 15;
        }

        onUpdateState((prev) => ({
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id !== activeScene?.id) return sc;
            return {
              ...sc,
              layers: sc.layers.map((ly) => {
                if (ly.id !== layer.id) return ly;
                return {
                  ...ly,
                  transform: { ...ly.transform, rotation: newRot },
                };
              }),
            };
          }),
        }));
      } else {
        const currentDist = Math.hypot(ev.clientX - centerX, ev.clientY - centerY);
        const scaleFactor = currentDist / initialDist;
        const targetScale = Math.max(0.15, Math.min(5.0, initialScale * scaleFactor));
        const newScale = Math.round(targetScale * 100) / 100;

        onUpdateState((prev) => ({
          ...prev,
          scenes: prev.scenes.map((sc) => {
            if (sc.id !== activeScene?.id) return sc;
            return {
              ...sc,
              layers: sc.layers.map((ly) => {
                if (ly.id !== layer.id) return ly;
                return {
                  ...ly,
                  transform: { ...ly.transform, scale: newScale },
                };
              }),
            };
          }),
        }));
      }
    };

    const handlePointerUp = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove, { passive: false });
    window.addEventListener("pointerup", handlePointerUp);
  };

  // Crop application handler for box, polygon, and pen cuts
  const handleApplyCropType = (
    layerId: string,
    cropType: "rect" | "polygon" | "pen",
    clipPath?: string
  ) => {
    if (!activeScene) return;
    onUpdateState((prev) => ({
      ...prev,
      scenes: prev.scenes.map((sc) => {
        if (sc.id !== activeScene?.id) return sc;
        return {
          ...sc,
          layers: sc.layers.map((ly) => {
            if (ly.id !== layerId) return ly;
            return {
              ...ly,
              crop_type: cropType,
              clip_path: clipPath || (cropType === "rect" ? undefined : ly.clip_path),
            };
          }),
        };
      }),
    }));
  };

  // Create dedicated new scene from cropped layer
  const handleCreateSceneFromCrop = () => {
    if (!activeScene || !selectedLayerObj) return;
    const newSceneId = `scene_${Date.now()}`;
    const newLayerId = `layer_${Date.now()}`;
    const newLayer: VisualLayer = {
      ...selectedLayerObj,
      id: newLayerId,
    };
    const newScene: VideoScene = {
      id: newSceneId,
      sequence: state.scenes.length + 1,
      title: `${selectedLayerObj.name || "Cropped Panel"} Scene`,
      duration_sec: 3.5,
      start_time_sec: totalDurationSec,
      layers: [newLayer],
      transition_in: "fade",
    };

    onUpdateState((prev) => ({
      ...prev,
      scenes: [...prev.scenes, newScene],
      selected_object: { type: "scene", id: newSceneId },
      playhead_sec: newScene.start_time_sec,
    }));
  };

  // Chapter 3: Handle panel drop directly onto composition canvas
  const handleCanvasDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsCanvasDragOver(false);
    const dataStr = e.dataTransfer.getData("application/panelflow-panel");
    if (!dataStr) return;
    try {
      const p = JSON.parse(dataStr);
      const targetScene = activeScene;
      if (!targetScene) return;

      const elapsedInScene = Math.max(0, state.playhead_sec - targetScene.start_time_sec);
      const layerDuration = Math.max(1.0, targetScene.duration_sec - elapsedInScene);
      const newLayerId = `layer_${Date.now()}`;
      const newLayer: VisualLayer = {
        id: newLayerId,
        source_page_id: p.pageId,
        source_panel_id: p.panelId,
        image_url: p.imageUrl,
        page_sequence: p.pageSequence,
        crop: p.crop,
        transform: {
          x: 0,
          y: 0,
          scale: 1.0,
          rotation: 0,
          opacity: 1.0,
          z_index: targetScene.layers.length + 1,
        },
        motion_preset: "slow_zoom_in",
        name: p.name || `Panel #${p.pageSequence}`,
        start_offset_sec: Math.round(elapsedInScene * 10) / 10,
        duration_sec: Math.round(layerDuration * 10) / 10,
      };

      onUpdateState((prev) => ({
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== targetScene.id) return sc;
          return {
            ...sc,
            layers: [...sc.layers, newLayer],
          };
        }),
        selected_object: { type: "layer", id: newLayerId, sceneId: targetScene.id },
      }));
    } catch (err) {
      console.error("Canvas drop parsing error:", err);
    }
  };

  const viewport = fitCompositionFrame(state.aspect_ratio, frameSize.width, frameSize.height, viewZoom === "fit" ? 100 : Number(viewZoom), state.canvas_width, state.canvas_height);
  const resolvedBackground = resolveBackground(state, activeScene);
  const background = !state.background_preview_disabled && resolvedBackground?.enabled && resolvedBackground.preset !== "none" ? resolvedBackground : undefined;
  const backgroundSource = activeScene && background ? resolveBackgroundSource(state, activeScene, background) : undefined;
  const backgroundSourceUrl = background?.source_mode === "custom_image" ? background.custom_image_url : backgroundSource ? getLayerImageUrl(backgroundSource) : undefined;
  const selectedLayerObj =
    activeScene?.layers.find((l) => l.id === selectedLayerId) || activeScene?.layers[0] || null;
  const camera = activeScene ? evaluateCameraTransform(activeScene, state.playhead_sec) : { zoom: 1.0, panX: 0, panY: 0 };
  const transition = activeScene ? evaluateSceneTransition(activeScene, state.playhead_sec) : null;

  return (
    <div className="pf-composition-workspace flex-1 min-w-0 min-h-0 flex flex-col relative overflow-hidden select-none" aria-label="Video composition workspace">
      <div ref={frameRef} className="pf-composition-frame flex-1 min-h-0 relative overflow-auto">
        <div
          ref={containerRef}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            setIsCanvasDragOver(true);
          }}
          onDragLeave={() => setIsCanvasDragOver(false)}
          onDrop={handleCanvasDrop}
          className={`pf-composition-stage relative bg-black overflow-hidden border shrink-0 ${isCanvasDragOver ? "border-cyan-400 ring-2 ring-cyan-500/30" : "border-white/10"}`}
          data-aspect-ratio={state.aspect_ratio}
          style={{ width: viewport.width, height: viewport.height }}
          onClick={() => {
            // Deselect layer if clicked on blank canvas
            if (activeScene) {
              onUpdateState((s) => ({
                ...s,
                selected_object: { type: "scene", id: activeScene.id },
              }));
            }
          }}
        >
          {activeScene && background && <BackgroundPreview key={`${activeScene.id}:${backgroundSourceUrl || "color"}`} settings={background} sourceUrl={backgroundSourceUrl} sourceLayer={backgroundSource} width={viewport.width} height={viewport.height} progress={(state.playhead_sec - activeScene.start_time_sec) / Math.max(.001, activeScene.duration_sec)} />}
          {/* Camera Viewport Stage (Separates camera zoom/pan from layer transforms) */}
          <div
            className="w-full h-full relative overflow-hidden"
            style={{
              transform: `scale(${camera.zoom}) translate(${camera.panX}%, ${camera.panY}%)`,
              clipPath: transition?.clipPath,
              filter: transition?.filter || "none",
              transition: state.is_playing ? "none" : "transform 0.05s ease-out",
            }}
          >
            {/* Active Scene Layers */}
            {activeScene && activeScene.layers.length > 0 ? (
              activeScene.layers
                .slice()
                .sort((a, b) => a.transform.z_index - b.transform.z_index)
                .map((layer) => {
                  const isSelected = selectedLayerId === layer.id;
                  const evaluated = evaluateLayerTransform(layer, activeScene, state.playhead_sec);
                  if (layer.visible === false || (state.track_states?.Visuals ?? state.track_states?.visuals)?.visible === false || (activeScene.layers.indexOf(layer) > 0 && (state.track_states?.["Layer 2"] ?? state.track_states?.layer2)?.visible === false)) return null;
                  const imageUrl = getLayerImageUrl(layer);
                  const dimensions = imageSizes[imageUrl];
                  const fitted = background && dimensions ? foregroundSize(dimensions.width, dimensions.height, viewport.width, viewport.height, background.foreground_fit) : undefined;

                  // Keep active layer or selected layer in paused mode
                  if (!evaluated.isActive && !(isSelected && !state.is_playing)) return null;

                  return (
                    <div
                      key={layer.id}
                      onPointerDown={previewOnly ? undefined : (e) => handleLayerPointerDown(e, layer)}
                      className={`absolute ${previewOnly ? "" : "cursor-move"} select-none transition-shadow ${
                        previewOnly ? "" : isSelected ? "ring-2 ring-indigo-500 shadow-xl" : "hover:ring-1 hover:ring-white/40"
                      }`}
                      style={{
                        left: `calc(${background ? background.foreground_x * 100 : 50}% + ${evaluated.x}%)`,
                        top: `calc(${background ? background.foreground_y * 100 : 50}% + ${evaluated.y}%)`,
                        transform: `translate(-50%, -50%) scale(${evaluated.scale}) rotate(${evaluated.rotation}deg)`,
                        opacity: evaluated.opacity,
                        filter: evaluated.blur > 0 ? `blur(${evaluated.blur}px)` : "none",
                        zIndex: layer.transform.z_index,
                        maxWidth: background ? "none" : "90%",
                        maxHeight: background ? "none" : "90%",
                        ...(fitted ?? {}),
                        boxShadow: background?.edge_shadow ? `0 0 ${viewport.height * .04}px rgba(0,0,0,${background.edge_shadow})` : undefined,
                      }}
                    >
                      {/* Visual Layer Image with ClipPath support for rect/polygon/pen crops */}
                      <img
                        src={imageUrl}
                        onLoad={event => { const image = event.currentTarget; if (image.naturalWidth && image.naturalHeight) setImageSizes(prev => prev[imageUrl]?.width === image.naturalWidth && prev[imageUrl]?.height === image.naturalHeight ? prev : { ...prev, [imageUrl]: { width: image.naturalWidth, height: image.naturalHeight } }); }}
                        alt={layer.name || "Scene Panel"}
                        className="block object-contain pointer-events-none rounded shadow-md max-w-full max-h-full"
                        style={{
                          ...(fitted ? { width: fitted.width, height: fitted.height, maxWidth: "none", maxHeight: "none" } : background ? { maxWidth: viewport.width, maxHeight: viewport.height } : previewOnly ? { maxWidth: viewport.width * .9, maxHeight: viewport.height * .9 } : {}),
                          clipPath: layer.clip_path
                            ? layer.clip_path
                            : layer.polygon_points && layer.polygon_points.length >= 3
                            ? `polygon(${layer.polygon_points.map((p) => `${p.x}% ${p.y}%`).join(", ")})`
                            : undefined,
                        }}
                        draggable={false}
                      />

                      {/* On-Canvas Draggable Bounding Handles & Precision Studio Controls */}
                      {!previewOnly && isSelected && !state.is_playing && (
                        <div className="absolute inset-0 pointer-events-none border-2 border-indigo-500/90 shadow-[0_0_20px_rgba(99,102,241,0.25)] ring-1 ring-cyan-400/30">
                          {/* Live Dimensions, Position & Rotation HUD Pill */}
                          <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-zinc-950/90 backdrop-blur-md border border-zinc-700/80 text-zinc-200 font-mono text-[10px] font-semibold px-2.5 py-0.5 rounded-full shadow-2xl whitespace-nowrap pointer-events-none flex items-center gap-1.5 z-30 ring-1 ring-white/10">
                            <span className="text-indigo-400 font-bold">{Math.round((layer.transform.scale || 1.0) * 100)}%</span>
                            <span className="text-zinc-600">|</span>
                            <span>{layer.transform.x}%, {layer.transform.y}%</span>
                            {(layer.transform.rotation || 0) !== 0 && (
                              <>
                                <span className="text-zinc-600">|</span>
                                <span className="text-amber-400 font-bold">{Math.round(layer.transform.rotation || 0)}°</span>
                              </>
                            )}
                            {layer.crop_type && layer.crop_type !== "rect" && (
                              <>
                                <span className="text-zinc-600">|</span>
                                <span className="text-[9px] text-cyan-400 uppercase font-bold tracking-wider bg-cyan-950/70 border border-cyan-800/80 px-1.5 py-0.2 rounded-full">
                                  {layer.crop_type}
                                </span>
                              </>
                            )}
                          </div>

                          {/* Floating Precision Crop & Cut Toolbar */}
                          <div
                            className={`absolute ${
                              (layer.transform.y || 0) < -22 ? "top-[calc(100%+14px)]" : "-top-17"
                            } left-1/2 -translate-x-1/2 bg-zinc-950/90 border border-zinc-700/80 rounded-xl shadow-2xl p-1 flex items-center gap-1 pointer-events-auto backdrop-blur-md z-30 ring-1 ring-white/10`}
                          >
                            {/* Box Crop (Rect) */}
                            <button
                              type="button"
                              onClick={() => handleApplyCropType(layer.id, "rect", undefined)}
                              className={`px-2 py-1 rounded-lg text-[10px] font-semibold flex items-center gap-1.5 transition-all ${
                                !layer.crop_type || layer.crop_type === "rect"
                                  ? "bg-indigo-600 text-white shadow-sm"
                                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80"
                              }`}
                              title="Standard Rectangle Box Frame"
                            >
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="3 3" />
                              </svg>
                              <span>Box</span>
                            </button>

                            {/* Polygon Crop */}
                            <button
                              type="button"
                              onClick={() => {
                                handleApplyCropType(
                                  layer.id,
                                  "polygon",
                                  "polygon(5% 0%, 95% 0%, 100% 90%, 85% 100%, 0% 95%)"
                                );
                              }}
                              className={`px-2 py-1 rounded-lg text-[10px] font-semibold flex items-center gap-1.5 transition-all ${
                                layer.crop_type === "polygon"
                                  ? "bg-indigo-600 text-white shadow-sm"
                                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80"
                              }`}
                              title="Multi-Point Geometric Polygon Crop"
                            >
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <polygon points="12,2 22,8.5 18,21 6,21 2,8.5" />
                              </svg>
                              <span>Polygon</span>
                            </button>

                            {/* Pen Cut */}
                            <button
                              type="button"
                              onClick={() => {
                                handleApplyCropType(
                                  layer.id,
                                  "pen",
                                  "polygon(10% 5%, 85% 2%, 98% 70%, 90% 95%, 15% 98%, 2% 65%)"
                                );
                              }}
                              className={`px-2 py-1 rounded-lg text-[10px] font-semibold flex items-center gap-1.5 transition-all ${
                                layer.crop_type === "pen"
                                  ? "bg-indigo-600 text-white shadow-sm"
                                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80"
                              }`}
                              title="Organic Contour Pen Cut"
                            >
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l7-7 3 3-7 7-3-3z" />
                                <path strokeLinecap="round" strokeLinejoin="round" d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z" />
                              </svg>
                              <span>Pen Cut</span>
                            </button>

                            <div className="w-px h-4 bg-zinc-800 mx-0.5" />

                            {/* Add to Timeline Button */}
                            <button
                              type="button"
                              onClick={() => setCropModalOpen(true)}
                              className="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1 shadow-md shadow-emerald-950 transition-all active:scale-95"
                              title="Add this cropped layer to the timeline"
                            >
                              <Icons.Plus className="w-3 h-3" />
                              <span>Add to Timeline</span>
                            </button>
                          </div>

                          {/* Rotate Handle Stalk & Knob */}
                          <div className="absolute -top-7 left-1/2 -translate-x-1/2 w-0.5 h-7 bg-indigo-500/80 pointer-events-none" />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "rotate", layer)}
                            className="absolute -top-10 left-1/2 -translate-x-1/2 w-5 h-5 bg-zinc-950 border-2 border-indigo-500 rounded-full shadow-lg flex items-center justify-center cursor-grab active:cursor-grabbing hover:scale-125 transition-transform pointer-events-auto group"
                            title="Drag to Rotate (Hold Shift to snap 15°)"
                          >
                            <svg className="w-3 h-3 text-indigo-400 group-hover:text-indigo-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          </div>

                          {/* 4 Corner Round Handles (nw, ne, sw, se) */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "nw", layer)}
                            className="absolute -top-2 -left-2 w-4 h-4 bg-white border-2 border-indigo-500 rounded-full shadow-md hover:scale-125 cursor-nwse-resize pointer-events-auto transition-transform flex items-center justify-center"
                            title="Resize Corner (NW)"
                          >
                            <span className="w-1 h-1 bg-indigo-600 rounded-full" />
                          </div>
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "ne", layer)}
                            className="absolute -top-2 -right-2 w-4 h-4 bg-white border-2 border-indigo-500 rounded-full shadow-md hover:scale-125 cursor-nesw-resize pointer-events-auto transition-transform flex items-center justify-center"
                            title="Resize Corner (NE)"
                          >
                            <span className="w-1 h-1 bg-indigo-600 rounded-full" />
                          </div>
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "sw", layer)}
                            className="absolute -bottom-2 -left-2 w-4 h-4 bg-white border-2 border-indigo-500 rounded-full shadow-md hover:scale-125 cursor-nesw-resize pointer-events-auto transition-transform flex items-center justify-center"
                            title="Resize Corner (SW)"
                          >
                            <span className="w-1 h-1 bg-indigo-600 rounded-full" />
                          </div>
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "se", layer)}
                            className="absolute -bottom-2 -right-2 w-4 h-4 bg-white border-2 border-indigo-500 rounded-full shadow-md hover:scale-125 cursor-nwse-resize pointer-events-auto transition-transform flex items-center justify-center"
                            title="Resize Corner (SE)"
                          >
                            <span className="w-1 h-1 bg-indigo-600 rounded-full" />
                          </div>

                          {/* 4 Edge Midpoint Pill Handles (n, s, w, e) */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "n", layer)}
                            className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-5 h-2 bg-white border border-indigo-500 rounded-full shadow-sm hover:scale-125 cursor-ns-resize pointer-events-auto transition-transform"
                            title="Adjust Height (Top)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "s", layer)}
                            className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-5 h-2 bg-white border border-indigo-500 rounded-full shadow-sm hover:scale-125 cursor-ns-resize pointer-events-auto transition-transform"
                            title="Adjust Height (Bottom)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "w", layer)}
                            className="absolute top-1/2 -left-1.5 -translate-y-1/2 w-2 h-5 bg-white border border-indigo-500 rounded-full shadow-sm hover:scale-125 cursor-ew-resize pointer-events-auto transition-transform"
                            title="Adjust Width (Left)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "e", layer)}
                            className="absolute top-1/2 -right-1.5 -translate-y-1/2 w-2 h-5 bg-white border border-indigo-500 rounded-full shadow-sm hover:scale-125 cursor-ew-resize pointer-events-auto transition-transform"
                            title="Adjust Width (Right)"
                          />

                          {/* Center Target Handle for Repositioning */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "center", layer)}
                            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 bg-zinc-950 border-2 border-cyan-400 rounded-md shadow-lg hover:scale-115 cursor-move pointer-events-auto transition-transform flex items-center justify-center group"
                            title="Drag to Reposition (Center Anchor)"
                          >
                            <div className="w-2 h-2 rounded-full border border-cyan-400 flex items-center justify-center">
                              <span className="w-1 h-1 bg-cyan-400 rounded-full group-hover:bg-cyan-300" />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
            ) : activeScene || state.scenes.length === 0 ? (
              /* Empty State */
              <div className="absolute inset-0 flex flex-col items-center justify-center p-8 text-center text-zinc-500">
                <div className="w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-4 text-zinc-400">
                  <Icons.Film className="w-8 h-8" />
                </div>
                <h4 className="text-base font-semibold text-zinc-300">Composition Canvas Empty</h4>
                <p className="text-xs text-zinc-500 max-w-xs mt-1">
                  Select a manga panel from the right panel and click <strong>“Add to Scene”</strong> or drag it here to begin your video.
                </p>
              </div>
            ) : null}

            {/* Transition Color Overlay */}
            {transition?.overlayColor && transition.overlayOpacity !== undefined && transition.overlayOpacity > 0 && (
              <div
                className="absolute inset-0 pointer-events-none z-30 transition-opacity duration-75"
                style={{
                  backgroundColor: transition.overlayColor,
                  opacity: transition.overlayOpacity,
                }}
              />
            )}

            {/* Motion Path Trajectory Visualization */}
            {!previewOnly && selectedLayerObj && activeScene && (state.show_motion_paths || selectedLayerId) && !state.is_playing && (() => {
              const points = computeMotionPathPoints(selectedLayerObj, activeScene, 16);
              if (points.length < 2) return null;
              const svgPoints = points.map((p) => `${50 + p.x},${50 + p.y}`).join(" ");
              const startP = points[0];
              const endP = points[points.length - 1];
              const currentEvaluated = evaluateLayerTransform(selectedLayerObj, activeScene, state.playhead_sec);

              return (
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none z-20"
                  viewBox="0 0 100 100"
                  preserveAspectRatio="none"
                >
                  <polyline
                    points={svgPoints}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="0.6"
                    strokeDasharray="1.5 1"
                    className="opacity-75"
                  />
                  {/* Start Point (Green) */}
                  <circle cx={50 + startP.x} cy={50 + startP.y} r="1.2" fill="#4ade80" stroke="#166534" strokeWidth="0.3" />
                  {/* End Point (Rose) */}
                  <circle cx={50 + endP.x} cy={50 + endP.y} r="1.2" fill="#f43f5e" stroke="#9f1239" strokeWidth="0.3" />
                  {/* Current Position Marker (Cyan Pulse) */}
                  <circle cx={50 + currentEvaluated.x} cy={50 + currentEvaluated.y} r="1.5" fill="#22d3ee" stroke="#ffffff" strokeWidth="0.4" />
                </svg>
              );
            })()}
          </div>

          {/* Canvas Drag-over Dropzone Visual Cue */}
          {isCanvasDragOver && (
            <div className="absolute inset-0 bg-cyan-950/40 border-2 border-cyan-400 border-dashed rounded-xl z-50 flex items-center justify-center pointer-events-none backdrop-blur-sm animate-pulse">
              <div className="bg-zinc-900/95 border border-cyan-400/80 px-4 py-2 rounded-lg text-cyan-300 font-semibold text-xs flex items-center gap-2 shadow-2xl">
                <Icons.Layers className="w-4 h-4 text-cyan-400" />
                <span>Drop panel to add as layer at {formatTime(state.playhead_sec)}</span>
              </div>
            </div>
          )}

          {/* Safe Zones Overlay (Rule of Thirds & Title Safe) */}
          {showSafeZones && (
            <div className="absolute inset-0 pointer-events-none">
              {/* Rule of Thirds */}
              <div className="w-full h-full grid grid-cols-3 grid-rows-3 border border-white/10">
                <div className="border-r border-b border-white/10" />
                <div className="border-r border-b border-white/10" />
                <div className="border-b border-white/10" />
                <div className="border-r border-b border-white/10" />
                <div className="border-r border-b border-white/10" />
                <div className="border-b border-white/10" />
                <div className="border-r border-white/10" />
                <div className="border-r border-white/10" />
                <div />
              </div>
              {/* 90% Title Safe Area */}
              <div className="absolute inset-[5%] border border-cyan-400/25 rounded" />
            </div>
          )}

          {/* Active Scene Overlay Badge */}
          {activeScene && (
            <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-md px-2.5 py-1 rounded-md border border-white/10 text-[11px] font-mono text-zinc-300 flex items-center gap-1.5 shadow-md">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              <span>
                Scene #{activeScene.sequence}: {activeScene.title}
              </span>
              {activeScene.layers.length > 0 && (
                <span className="text-zinc-500 ml-1">
                  ({activeScene.layers.length} {activeScene.layers.length === 1 ? "layer" : "layers"})
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Canvas-only tools. Playback and scrubbing live in the timeline below. */}
      <div className="pf-canvas-view-tools px-3 py-2 shrink-0 select-none flex items-center justify-between gap-3">
        <span className="text-[10px] text-zinc-500 truncate">{activeScene ? activeScene.title : state.scenes.length ? "Timeline gap" : "Drop a page or panel to begin"}</span>
        <div className="flex items-center gap-2" aria-label="Canvas view tools">
            {/* Fit dropdown */}
            <select
              className="bg-zinc-950 border border-zinc-800 text-[11px] font-mono text-zinc-300 rounded px-2 py-1 focus:outline-none"
              aria-label="Canvas view zoom"
              value={viewZoom}
              onChange={(event) => setViewZoom(event.target.value)}
            >
              <option value="fit">Fit</option>
              <option value="50">50%</option>
              <option value="75">75%</option>
              <option value="100">100%</option>
              <option value="150">150%</option>
            </select>

            {/* Motion Paths Toggle */}
            {!previewOnly && <button
              type="button"
              onClick={() => onUpdateState((s) => ({ ...s, show_motion_paths: !s.show_motion_paths }))}
              className={`p-1.5 rounded transition-colors ${
                state.show_motion_paths
                  ? "bg-cyan-600/20 text-cyan-400 border border-cyan-500/30"
                  : "text-zinc-400 hover:text-white"
              }`}
              title="Toggle Motion Paths & Keyframe Trajectory (M)"
              aria-label="Toggle motion paths"
              aria-pressed={!!state.show_motion_paths}
            >
              <Icons.Sparkles className="w-3.5 h-3.5" />
            </button>}

            {/* Safe Zones Toggle */}
            <button
              type="button"
              onClick={() => setShowSafeZones((v) => !v)}
              className={`p-1.5 rounded transition-colors ${
                showSafeZones ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30" : "text-zinc-400 hover:text-white"
              }`}
              title="Toggle Safe Frame Guides"
              aria-label="Toggle safe frame guides"
              aria-pressed={showSafeZones}
            >
              <Icons.Layout className="w-3.5 h-3.5" />
            </button>

            {/* Fullscreen Button */}
            <button
              type="button"
              onClick={() => {
                const el = containerRef.current;
                setFullscreenError(null);
                if (document.fullscreenElement) {
                  void document.exitFullscreen().catch(() => setFullscreenError("Could not exit fullscreen."));
                } else if (el?.requestFullscreen) {
                  void el.requestFullscreen().catch(() => setFullscreenError("Fullscreen is not available in this window."));
                } else {
                  setFullscreenError("Fullscreen is not available in this window.");
                }
              }}
              className="p-1.5 text-zinc-400 hover:text-white rounded"
              title="Fullscreen Canvas"
              aria-label="Fullscreen canvas"
            >
              <Icons.Maximize className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      {fullscreenError && <p role="status" className="px-3 pb-2 text-xs text-amber-300">{fullscreenError}</p>}
      {/* "May I add this crop to the timeline?" Confirmation Modal */}
      {cropModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
          <div className="bg-zinc-900 border border-zinc-750 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl ring-1 ring-white/10">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-950/80 border border-indigo-700/60 flex items-center justify-center text-indigo-400 shadow-inner">
                  <Icons.Scissors className="w-4 h-4 text-indigo-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-100 leading-tight">
                    Add Crop to Timeline
                  </h3>
                  <span className="text-[11px] text-zinc-400">
                    May I add this crop to the timeline?
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setCropModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded-lg hover:bg-zinc-800 transition-colors"
                title="Close (Esc)"
              >
                <Icons.X className="w-4 h-4" />
              </button>

            </div>

            <p className="text-xs text-zinc-300 leading-relaxed">
              Choose how you would like to position this cropped panel element inside your animated video story:
            </p>

            <div className="space-y-2.5 pt-1">
              <button
                type="button"
                onClick={() => {
                  setCropModalOpen(false);
                  handleCreateSceneFromCrop();
                }}
                className="w-full text-left p-3.5 rounded-xl bg-zinc-950 hover:bg-indigo-950/50 border border-zinc-800 hover:border-indigo-500/80 transition-all group flex items-start gap-3.5 shadow-sm"
              >
                <div className="w-9 h-9 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform">
                  <Icons.Film className="w-4 h-4 text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-indigo-300 flex items-center justify-between">
                    <span>Create New Scene from Crop</span>
                    <span className="text-[10px] text-zinc-500 font-mono font-normal">Enter ↵</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Appends a new scene on the timeline dedicated to this cropped element with smooth cinematic timing.
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setCropModalOpen(false);
                }}
                className="w-full text-left p-3.5 rounded-xl bg-zinc-950 hover:bg-cyan-950/50 border border-zinc-800 hover:border-cyan-500/80 transition-all group flex items-start gap-3.5 shadow-sm"
              >
                <div className="w-9 h-9 rounded-lg bg-cyan-600/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform">
                  <Icons.Layers className="w-4 h-4 text-cyan-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-cyan-300">
                    Keep on Current Scene Layer
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Preserves the crop boundary directly on the active scene layer without altering timeline duration.
                  </div>
                </div>
              </button>
            </div>

            <div className="flex justify-end pt-3 border-t border-zinc-800/80">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCropModalOpen(false)}
                className="text-xs h-8 px-4 font-semibold"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
