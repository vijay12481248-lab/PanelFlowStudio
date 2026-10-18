import React, { useRef, useState, useEffect } from "react";
import { Icons, Button } from "@panelflow/ui";
import type { VideoScene, VisualLayer, StoryEditorState } from "@panelflow/shared-types";
import {
  evaluateLayerTransform,
  evaluateCameraTransform,
  evaluateSceneTransition,
  computeMotionPathPoints,
} from "./animationEngine";

interface VideoCompositionCanvasProps {
  state: StoryEditorState;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
  onSelectLayer: (layerId: string, sceneId: string) => void;
}

export const VideoCompositionCanvas: React.FC<VideoCompositionCanvasProps> = ({
  state,
  onUpdateState,
  onSelectLayer,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showSafeZones, setShowSafeZones] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  type ResizeHandle = "nw" | "ne" | "se" | "sw" | "n" | "s" | "e" | "w" | "center";

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

  // Compute total duration of all scenes
  const totalDurationSec = state.scenes.reduce((acc, s) => acc + s.duration_sec, 0);

  // Find active scene at current playhead position
  let cumulativeTime = 0;
  let activeScene: VideoScene | null = null;
  let sceneProgress = 0; // 0.0 to 1.0 within the active scene

  for (const scene of state.scenes) {
    if (state.playhead_sec >= cumulativeTime && state.playhead_sec <= cumulativeTime + scene.duration_sec) {
      activeScene = scene;
      const elapsedInScene = state.playhead_sec - cumulativeTime;
      sceneProgress = scene.duration_sec > 0 ? Math.min(1, Math.max(0, elapsedInScene / scene.duration_sec)) : 0;
      break;
    }
    cumulativeTime += scene.duration_sec;
  }

  // Fallback to first scene if playhead is 0 or before
  if (!activeScene && state.scenes.length > 0) {
    activeScene = state.scenes[0];
    sceneProgress = 0;
  }

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
        const total = prev.scenes.reduce((acc, s) => acc + s.duration_sec, 0);

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
      if (["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }
      if (e.code === "Space") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, is_playing: !s.is_playing }));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, playhead_sec: Math.max(0, s.playhead_sec - (e.shiftKey ? 1 : 0.1)) }));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, playhead_sec: Math.min(totalDurationSec, s.playhead_sec + (e.shiftKey ? 1 : 0.1)) }));
      } else if (e.key.toLowerCase() === "m") {
        e.preventDefault();
        onUpdateState((s) => ({ ...s, show_motion_paths: !s.show_motion_paths }));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [totalDurationSec, onUpdateState]);

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
      const targetScene = activeScene || state.scenes[0];
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

  const isPortrait = state.aspect_ratio === "9:16";
  const selectedLayerObj =
    activeScene?.layers.find((l) => l.id === selectedLayerId) || activeScene?.layers[0] || null;
  const camera = activeScene ? evaluateCameraTransform(activeScene, state.playhead_sec) : { zoom: 1.0, panX: 0, panY: 0 };
  const transition = activeScene ? evaluateSceneTransition(activeScene, state.playhead_sec) : null;

  return (
    <div className="flex-1 flex flex-col bg-zinc-950 relative overflow-hidden select-none">
      {/* 16:9 Central Composition Area */}
      <div className="flex-1 flex items-center justify-center p-6 relative">
        <div
          ref={containerRef}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            setIsCanvasDragOver(true);
          }}
          onDragLeave={() => setIsCanvasDragOver(false)}
          onDrop={handleCanvasDrop}
          className={`relative bg-black rounded-xl overflow-hidden shadow-2xl border transition-all duration-200 ${
            isCanvasDragOver
              ? "border-cyan-400 ring-4 ring-cyan-500/30 scale-[1.01]"
              : "border-zinc-800"
          } ${
            isPortrait
              ? "aspect-[9/16] h-[70vh] max-w-full"
              : "aspect-[16/9] w-full max-w-[1020px] max-h-[66vh]"
          }`}
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

                  // Keep active layer or selected layer in paused mode
                  if (!evaluated.isActive && !(isSelected && !state.is_playing)) return null;

                  return (
                    <div
                      key={layer.id}
                      onPointerDown={(e) => handleLayerPointerDown(e, layer)}
                      className={`absolute cursor-move select-none transition-shadow ${
                        isSelected ? "ring-2 ring-indigo-500 shadow-xl" : "hover:ring-1 hover:ring-white/40"
                      }`}
                      style={{
                        left: `calc(50% + ${evaluated.x}%)`,
                        top: `calc(50% + ${evaluated.y}%)`,
                        transform: `translate(-50%, -50%) scale(${evaluated.scale}) rotate(${evaluated.rotation}deg)`,
                        opacity: evaluated.opacity,
                        filter: evaluated.blur > 0 ? `blur(${evaluated.blur}px)` : "none",
                        zIndex: layer.transform.z_index,
                        maxWidth: "90%",
                        maxHeight: "90%",
                      }}
                    >
                      {/* Visual Layer Image with ClipPath support for rect/polygon/pen crops */}
                      <img
                        src={layer.image_url}
                        alt={layer.name || "Scene Panel"}
                        className="block object-contain pointer-events-none rounded shadow-md max-w-full max-h-full"
                        style={{
                          clipPath: layer.clip_path
                            ? layer.clip_path
                            : layer.polygon_points && layer.polygon_points.length >= 3
                            ? `polygon(${layer.polygon_points.map((p) => `${p.x}% ${p.y}%`).join(", ")})`
                            : undefined,
                        }}
                        draggable={false}
                      />

                      {/* On-Canvas Draggable Bounding Handles matching user description */}
                      {isSelected && !state.is_playing && (
                        <div className="absolute inset-0 pointer-events-none border-2 border-cyan-400 shadow-lg">
                          {/* Live Dimensions & Scale Readout HUD */}
                          <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-zinc-950/95 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold px-2 py-0.5 rounded shadow-xl whitespace-nowrap pointer-events-none flex items-center gap-1.5">
                            <span>Scale: {Math.round((layer.transform.scale || 1.0) * 100)}%</span>
                            <span className="text-zinc-600">|</span>
                            <span>Pos: {layer.transform.x}%, {layer.transform.y}%</span>
                            {layer.crop_type && (
                              <span className="text-[9px] text-amber-400 uppercase bg-amber-950/70 px-1 rounded">
                                {layer.crop_type}
                              </span>
                            )}
                          </div>

                          {/* Floating Crop & Cut Toolbar */}
                          <div className="absolute -top-16 left-1/2 -translate-x-1/2 bg-zinc-900/95 border border-cyan-400/80 rounded-lg shadow-2xl p-1 flex items-center gap-1 pointer-events-auto backdrop-blur-md z-30">
                            {/* Box Crop (Rect) */}
                            <button
                              type="button"
                              onClick={() => {
                                handleApplyCropType(layer.id, "rect", undefined);
                              }}
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition-colors ${
                                !layer.crop_type || layer.crop_type === "rect"
                                  ? "bg-cyan-600 text-white shadow-sm"
                                  : "text-zinc-300 hover:text-white hover:bg-zinc-800"
                              }`}
                              title="Standard Rectangle Box Crop"
                            >
                              <span>🔲</span>
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
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition-colors ${
                                layer.crop_type === "polygon"
                                  ? "bg-cyan-600 text-white shadow-sm"
                                  : "text-zinc-300 hover:text-white hover:bg-zinc-800"
                              }`}
                              title="Multi-Point Polygon Crop"
                            >
                              <span>🔷</span>
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
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition-colors ${
                                layer.crop_type === "pen"
                                  ? "bg-cyan-600 text-white shadow-sm"
                                  : "text-zinc-300 hover:text-white hover:bg-zinc-800"
                              }`}
                              title="Organic Pen / Contour Cut"
                            >
                              <span>✒️</span>
                              <span>Pen Cut</span>
                            </button>

                            <div className="w-px h-3.5 bg-zinc-700 mx-0.5" />

                            {/* Add to Timeline Button */}
                            <button
                              type="button"
                              onClick={() => setCropModalOpen(true)}
                              className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1 shadow-sm transition-all active:scale-95"
                              title="Add this cropped layer to the timeline"
                            >
                              <span>➕</span>
                              <span>Add to Timeline</span>
                            </button>
                          </div>

                          {/* 4 Corner Round Handles (nw, ne, sw, se) */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "nw", layer)}
                            className="absolute -top-2 -left-2 w-4 h-4 bg-white border-2 border-cyan-400 rounded-full shadow hover:scale-125 cursor-nwse-resize pointer-events-auto transition-transform"
                            title="Resize Corner (NW)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "ne", layer)}
                            className="absolute -top-2 -right-2 w-4 h-4 bg-white border-2 border-cyan-400 rounded-full shadow hover:scale-125 cursor-nesw-resize pointer-events-auto transition-transform"
                            title="Resize Corner (NE)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "sw", layer)}
                            className="absolute -bottom-2 -left-2 w-4 h-4 bg-white border-2 border-cyan-400 rounded-full shadow hover:scale-125 cursor-nesw-resize pointer-events-auto transition-transform"
                            title="Resize Corner (SW)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "se", layer)}
                            className="absolute -bottom-2 -right-2 w-4 h-4 bg-white border-2 border-cyan-400 rounded-full shadow hover:scale-125 cursor-nwse-resize pointer-events-auto transition-transform"
                            title="Resize Corner (SE)"
                          />

                          {/* 4 Edge Midpoint Square Handles (n, s, w, e) */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "n", layer)}
                            className="absolute -top-2 left-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-white border-2 border-cyan-400 rounded-sm shadow hover:scale-125 cursor-ns-resize pointer-events-auto transition-transform"
                            title="Adjust Height (Top)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "s", layer)}
                            className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-white border-2 border-cyan-400 rounded-sm shadow hover:scale-125 cursor-ns-resize pointer-events-auto transition-transform"
                            title="Adjust Height (Bottom)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "w", layer)}
                            className="absolute top-1/2 -left-2 -translate-y-1/2 w-3.5 h-3.5 bg-white border-2 border-cyan-400 rounded-sm shadow hover:scale-125 cursor-ew-resize pointer-events-auto transition-transform"
                            title="Adjust Width (Left)"
                          />
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "e", layer)}
                            className="absolute top-1/2 -right-2 -translate-y-1/2 w-3.5 h-3.5 bg-white border-2 border-cyan-400 rounded-sm shadow hover:scale-125 cursor-ew-resize pointer-events-auto transition-transform"
                            title="Adjust Width (Right)"
                          />

                          {/* Center Square Handle for Positioning */}
                          <div
                            onPointerDown={(e) => handleHandlePointerDown(e, "center", layer)}
                            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 bg-white border-2 border-cyan-500 rounded-sm shadow-md hover:scale-115 cursor-move pointer-events-auto transition-transform flex items-center justify-center group"
                            title="Drag to Reposition (Center Anchor)"
                          >
                            <span className="w-1.5 h-1.5 bg-cyan-500 rounded-full group-hover:bg-cyan-600" />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
            ) : (
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
            )}

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
            {selectedLayerObj && activeScene && (state.show_motion_paths || selectedLayerId) && !state.is_playing && (() => {
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

      {/* Floating Canvas Playback Bar */}
      <div className="bg-zinc-900/90 backdrop-blur-md border-t border-zinc-800/80 px-4 py-2 shrink-0 select-none flex flex-col gap-1.5">
        {/* Scrubber Progress Bar */}
        <div
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const clickPct = (e.clientX - rect.left) / rect.width;
            onUpdateState((s) => ({
              ...s,
              playhead_sec: Math.max(0, Math.min(totalDurationSec, clickPct * totalDurationSec)),
            }));
          }}
          className="w-full bg-zinc-800/80 h-1.5 rounded-full cursor-pointer relative overflow-hidden group"
        >
          <div
            className="bg-indigo-500 h-full rounded-full relative group-hover:bg-indigo-400 transition-all"
            style={{
              width: `${totalDurationSec > 0 ? (state.playhead_sec / totalDurationSec) * 100 : 0}%`,
            }}
          />
        </div>

        <div className="flex items-center justify-between">
          {/* Timecode Readout */}
          <div className="font-mono text-xs flex items-center gap-1 text-zinc-400">
            <span className="text-zinc-100 font-bold">{formatTime(state.playhead_sec)}</span>
            <span className="text-zinc-600">/</span>
            <span>{formatTime(totalDurationSec)}</span>
          </div>

          {/* Centered Transport Controls */}
          <div className="flex items-center gap-3">
            {/* Frame Step Back */}
            <button
              type="button"
              onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: Math.max(0, s.playhead_sec - 0.1) }))}
              title="Previous Frame"
              className="text-zinc-400 hover:text-white p-1"
            >
              <Icons.ChevronDown className="w-4 h-4 rotate-90" />
            </button>

            {/* Play / Pause Toggle */}
            <button
              type="button"
              onClick={() => onUpdateState((s) => ({ ...s, is_playing: !s.is_playing }))}
              className="w-8 h-8 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30 flex items-center justify-center transition-transform active:scale-95"
              title={state.is_playing ? "Pause (Space)" : "Play Video (Space)"}
            >
              {state.is_playing ? (
                <Icons.Pause className="w-4 h-4 text-white" />
              ) : (
                <Icons.Play className="w-4 h-4 text-white ml-0.5" />
              )}
            </button>

            {/* Frame Step Forward */}
            <button
              type="button"
              onClick={() => onUpdateState((s) => ({ ...s, playhead_sec: Math.min(totalDurationSec, s.playhead_sec + 0.1) }))}
              title="Next Frame"
              className="text-zinc-400 hover:text-white p-1"
            >
              <Icons.ChevronDown className="w-4 h-4 -rotate-90" />
            </button>
          </div>

          {/* Viewport & Quality Tools */}
          <div className="flex items-center gap-2">
            {/* Fit dropdown */}
            <select
              className="bg-zinc-950 border border-zinc-800 text-[11px] font-mono text-zinc-300 rounded px-2 py-1 focus:outline-none"
              defaultValue="Fit"
            >
              <option value="Fit">Fit</option>
              <option value="100%">100%</option>
              <option value="50%">50%</option>
            </select>

            {/* Motion Paths Toggle */}
            <button
              type="button"
              onClick={() => onUpdateState((s) => ({ ...s, show_motion_paths: !s.show_motion_paths }))}
              className={`p-1.5 rounded transition-colors ${
                state.show_motion_paths
                  ? "bg-cyan-600/20 text-cyan-400 border border-cyan-500/30"
                  : "text-zinc-400 hover:text-white"
              }`}
              title="Toggle Motion Paths & Keyframe Trajectory (M)"
            >
              <Icons.Sparkles className="w-3.5 h-3.5" />
            </button>

            {/* Safe Zones Toggle */}
            <button
              type="button"
              onClick={() => setShowSafeZones((v) => !v)}
              className={`p-1.5 rounded transition-colors ${
                showSafeZones ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30" : "text-zinc-400 hover:text-white"
              }`}
              title="Toggle Safe Frame Guides"
            >
              <Icons.Layout className="w-3.5 h-3.5" />
            </button>

            {/* Fullscreen Button */}
            <button
              type="button"
              onClick={() => {
                const el = containerRef.current;
                if (el?.requestFullscreen) el.requestFullscreen();
              }}
              className="p-1.5 text-zinc-400 hover:text-white rounded"
              title="Fullscreen Canvas"
            >
              <Icons.Maximize className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* "May I add this crop to the timeline?" Confirmation Modal */}
      {cropModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                <span>✂️</span>
                <span>Add Crop to Timeline</span>
              </h3>
              <button
                type="button"
                onClick={() => setCropModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-zinc-300 leading-relaxed">
              May I add this crop to the timeline? You can create a new scene for this cropped element or keep the crop adjustments on the current scene layer.
            </p>

            <div className="space-y-2.5 pt-2">
              <button
                type="button"
                onClick={() => {
                  setCropModalOpen(false);
                  handleCreateSceneFromCrop();
                }}
                className="w-full text-left p-3.5 rounded-lg bg-zinc-950 hover:bg-indigo-950/50 border border-zinc-800 hover:border-indigo-500/60 transition-colors group flex items-start gap-3"
              >
                <span className="text-xl mt-0.5">🎬</span>
                <div>
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-indigo-300">
                    Create New Scene from Crop
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Adds a new scene containing this cropped panel element on the timeline with dedicated motion pacing.
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setCropModalOpen(false);
                }}
                className="w-full text-left p-3.5 rounded-lg bg-zinc-950 hover:bg-cyan-950/50 border border-zinc-800 hover:border-cyan-500/60 transition-colors group flex items-start gap-3"
              >
                <span className="text-xl mt-0.5">🔄</span>
                <div>
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-cyan-300">
                    Keep on Current Scene Layer
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Saves the crop adjustments directly onto the active scene layer.
                  </div>
                </div>
              </button>
            </div>

            <div className="flex justify-end pt-3 border-t border-zinc-800">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCropModalOpen(false)}
                className="text-xs h-8 px-3"
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
