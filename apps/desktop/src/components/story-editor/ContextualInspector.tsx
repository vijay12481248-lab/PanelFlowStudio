import React, { useState, useRef } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import type {
  StoryEditorState,
  VisualLayer,
  VideoScene,
  NarrationClip,
  NarrationEmotion,
  MotionPresetType,
  SceneCameraConfig,
  SceneCameraPreset,
  AnimationEasing,
  AnimatableProperty,
  PropertyKeyframe,
  PropertyTrack,
  LayerAnimationConfig,
  SceneTransitionType,
  BgmTrack,
  SfxCue,
} from "@panelflow/shared-types";
import {
  updateClipScriptText,
  relinkClipToScene,
  unlinkClipFromScene,
  estimateReadingDuration,
  rippleShiftLinkedNarration,
} from "./narrationAdapter";
import {
  updateBgmClip,
  updateSfxClip,
  deleteAudioClip,
  duplicateAudioClip,
} from "./audioAdapter";

export type InspectorTab = "image" | "motion" | "effects" | "timing" | "audio";

interface ContextualInspectorProps {
  state: StoryEditorState;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
  onDeleteLayer?: (layerId: string, sceneId: string) => void;
  onDeleteScene?: (sceneId: string) => void;
  onClose?: () => void;
  activeTab?: InspectorTab;
  onSelectTab?: (tab: InspectorTab) => void;
  onOpenNarrationStudio?: (segmentId?: string) => void;
  onOpenAudioLibrary?: (initialType?: "music" | "sfx") => void;
}

export const ContextualInspector: React.FC<ContextualInspectorProps> = ({
  state,
  onUpdateState,
  onDeleteLayer,
  onDeleteScene,
  onClose,
  activeTab: externalTab,
  onSelectTab,
  onOpenNarrationStudio,
  onOpenAudioLibrary,
}) => {
  const [internalTab, setInternalTab] = useState<InspectorTab>("image");
  const activeTab = externalTab ?? internalTab;
  const setActiveTab = (tab: InspectorTab) => {
    setInternalTab(tab);
    onSelectTab?.(tab);
  };

  // Motion sub-mode: Layer Motion | Camera Motion | Keyframes
  const [motionSubTab, setMotionSubTab] = useState<"layer" | "camera" | "keyframes">("layer");
  const [activeKeyframeProperty, setActiveKeyframeProperty] = useState<AnimatableProperty>("scale");

  const selection = state.selected_object;

  // Find selected layer, scene, narration, bgm, or sfx
  let selectedLayer: VisualLayer | null = null;
  let selectedScene: VideoScene | null = null;
  let selectedNarration: NarrationClip | null = null;
  let selectedBgm: BgmTrack | null = null;
  let selectedSfx: SfxCue | null = null;

  if (selection?.type === "layer") {
    selectedScene = state.scenes.find((s) => s.id === selection.sceneId) || null;
    selectedLayer = selectedScene?.layers.find((l) => l.id === selection.id) || null;
  } else if (selection?.type === "scene") {
    selectedScene = state.scenes.find((s) => s.id === selection.id) || null;
    selectedLayer = selectedScene?.layers[0] || null;
  } else if (selection?.type === "narration") {
    selectedNarration = state.narration_clips.find((n) => n.id === selection.id) || null;
  } else if (selection?.type === "bgm") {
    selectedBgm = state.bgm_tracks.find((b) => b.id === selection.id) || null;
  } else if (selection?.type === "sfx") {
    selectedSfx = (state.sfx_cues || []).find((s) => s.id === selection.id) || null;
  }

  // Audio preview & generation state for narration, bgm, and sfx inspector
  const [playingTake, setPlayingTake] = useState<string | null>(null);
  const [isGeneratingTake, setIsGeneratingTake] = useState<boolean>(false);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  const handlePlayTake = (url?: string | null, take: string = "current") => {
    if (!url) return;
    if (playingTake === take) {
      audioPlayerRef.current?.pause();
      setPlayingTake(null);
      return;
    }
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
    }
    const audio = new Audio(url);
    audioPlayerRef.current = audio;
    setPlayingTake(take);
    audio.play().catch((err) => {
      console.log("Audio playback notice:", err);
    });
    audio.onended = () => setPlayingTake(null);
    audio.onerror = () => {
      setTimeout(() => setPlayingTake(null), 1200);
    };
  };

  const handleRegenerateNarrationTake = (clipId: string) => {
    setIsGeneratingTake(true);
    setTimeout(() => {
      onUpdateState((prev) => {
        const nextClips = prev.narration_clips.map((c) => {
          if (c.id !== clipId) return c;
          return {
            ...c,
            status: "READY" as const,
            generated_audio_revision: c.text_revision || 1,
            audio_url: "/assets/demo/aria_narration_sample.mp3",
          };
        });
        const nextChapter = prev.narration_chapter
          ? {
              ...prev.narration_chapter,
              segments: prev.narration_chapter.segments.map((seg: any) => {
                if (seg.id !== clipId) return seg;
                return {
                  ...seg,
                  generation_status: "READY",
                  generated_audio_revision: seg.text_revision || 1,
                  audio_asset_uri: "/assets/demo/aria_narration_sample.mp3",
                };
              }),
            }
          : prev.narration_chapter;
        return {
          ...prev,
          narration_clips: nextClips,
          narration_chapter: nextChapter,
        };
      });
      setIsGeneratingTake(false);
    }, 500);
  };

  // Helper to update selected layer properties
  const updateSelectedLayer = (updates: Partial<VisualLayer>) => {
    if (!selectedLayer || !selectedScene) return;
    onUpdateState((prev) => ({
      ...prev,
      scenes: prev.scenes.map((sc) => {
        if (sc.id !== selectedScene?.id) return sc;
        return {
          ...sc,
          layers: sc.layers.map((ly) => {
            if (ly.id !== selectedLayer?.id) return ly;
            return { ...ly, ...updates };
          }),
        };
      }),
    }));
  };

  const updateSelectedLayerTransform = (updates: Partial<VisualLayer["transform"]>) => {
    if (!selectedLayer || !selectedScene) return;
    updateSelectedLayer({
      transform: {
        ...selectedLayer.transform,
        ...updates,
      },
    });
  };

  const updateSelectedScene = (updates: Partial<VideoScene>) => {
    if (!selectedScene) return;
    onUpdateState((prev) => ({
      ...prev,
      scenes: prev.scenes.map((sc) => {
        if (sc.id !== selectedScene?.id) return sc;
        return { ...sc, ...updates };
      }),
    }));
  };

  // Helper for updating camera configuration on the scene
  const updateSceneCamera = (updates: Partial<SceneCameraConfig>) => {
    if (!selectedScene) return;
    const currentCamera: SceneCameraConfig = selectedScene.camera || {
      id: `cam_${selectedScene.id}`,
      preset: "static",
      zoom_start: 1.0,
      zoom_end: 1.0,
      pan_x_start: 0,
      pan_x_end: 0,
      pan_y_start: 0,
      pan_y_end: 0,
      easing: "ease_in_out",
      duration_sec: selectedScene.duration_sec,
    };
    updateSelectedScene({
      camera: {
        ...currentCamera,
        ...updates,
      },
    });
  };

  // Helper for updating layer animation config / keyframes
  const updateLayerAnimationConfig = (
    updater: (prev: LayerAnimationConfig) => LayerAnimationConfig
  ) => {
    if (!selectedLayer || !selectedScene) return;
    const currentConfig: LayerAnimationConfig = selectedLayer.animation_config || {
      id: `anim_${selectedLayer.id}`,
      enabled: true,
      preset: selectedLayer.motion_preset || "none",
      direction: selectedLayer.motion_direction || "right",
      duration_sec: selectedLayer.motion_duration_sec || 2.5,
      intensity: 1.0,
      speed: 1.0,
      easing: "ease_in_out",
      tracks: {},
    };
    const updated = updater(currentConfig);
    updateSelectedLayer({
      animation_config: updated,
      motion_preset: updated.preset,
      motion_direction: updated.direction,
      motion_duration_sec: updated.duration_sec,
    });
  };

  // Calculate playhead relative to layer start
  const sceneStartSec = selectedScene?.start_time_sec ?? 0;
  const layerStartOffset = selectedLayer?.start_offset_sec ?? 0;
  const layerDuration = selectedLayer?.duration_sec ?? (selectedScene?.duration_sec ?? 4);
  const relativePlayheadSec = Math.max(
    0,
    Math.min(
      layerDuration,
      Math.round((state.playhead_sec - sceneStartSec - layerStartOffset) * 100) / 100
    )
  );

  // Keyframe operations
  const handleAddKeyframeAtPlayhead = (prop: AnimatableProperty) => {
    if (!selectedLayer) return;
    let defaultVal = 0;
    if (prop === "scale") defaultVal = selectedLayer.transform.scale;
    else if (prop === "x") defaultVal = selectedLayer.transform.x;
    else if (prop === "y") defaultVal = selectedLayer.transform.y;
    else if (prop === "rotation") defaultVal = selectedLayer.transform.rotation;
    else if (prop === "opacity") defaultVal = selectedLayer.transform.opacity;
    else if (prop === "blur") defaultVal = 0;

    updateLayerAnimationConfig((cfg) => {
      const tracks = { ...(cfg.tracks || {}) };
      const currentTrack = tracks[prop] || { property: prop, keyframes: [] };
      const existingIdx = currentTrack.keyframes.findIndex(
        (kf) => Math.abs(kf.time_offset_sec - relativePlayheadSec) < 0.05
      );

      let updatedKfs: PropertyKeyframe[];
      if (existingIdx >= 0) {
        updatedKfs = currentTrack.keyframes.map((kf, i) =>
          i === existingIdx ? { ...kf, value: defaultVal } : kf
        );
      } else {
        updatedKfs = [
          ...currentTrack.keyframes,
          {
            id: `kf_${prop}_${Date.now()}`,
            time_offset_sec: relativePlayheadSec,
            value: defaultVal,
            easing: "ease_in_out" as AnimationEasing,
          },
        ].sort((a, b) => a.time_offset_sec - b.time_offset_sec);
      }

      return {
        ...cfg,
        preset: "custom",
        tracks: {
          ...tracks,
          [prop]: {
            property: prop,
            keyframes: updatedKfs,
          },
        },
      };
    });
  };

  const handleDeleteKeyframe = (prop: AnimatableProperty, kfId: string) => {
    updateLayerAnimationConfig((cfg) => {
      const tracks = { ...(cfg.tracks || {}) };
      const currentTrack = tracks[prop];
      if (!currentTrack) return cfg;
      return {
        ...cfg,
        tracks: {
          ...tracks,
          [prop]: {
            ...currentTrack,
            keyframes: currentTrack.keyframes.filter((kf) => kf.id !== kfId),
          },
        },
      };
    });
  };

  const handleUpdateKeyframe = (
    prop: AnimatableProperty,
    kfId: string,
    updates: Partial<PropertyKeyframe>
  ) => {
    updateLayerAnimationConfig((cfg) => {
      const tracks = { ...(cfg.tracks || {}) };
      const currentTrack = tracks[prop];
      if (!currentTrack) return cfg;
      return {
        ...cfg,
        tracks: {
          ...tracks,
          [prop]: {
            ...currentTrack,
            keyframes: currentTrack.keyframes
              .map((kf) => (kf.id === kfId ? { ...kf, ...updates } : kf))
              .sort((a, b) => a.time_offset_sec - b.time_offset_sec),
          },
        },
      };
    });
  };

  // Copy / Paste animation config
  const handleCopyAnimation = () => {
    if (!selectedLayer) return;
    const configToCopy: LayerAnimationConfig = selectedLayer.animation_config || {
      id: `anim_${selectedLayer.id}`,
      enabled: true,
      preset: selectedLayer.motion_preset || "none",
      direction: selectedLayer.motion_direction || "right",
      duration_sec: selectedLayer.motion_duration_sec || 2.5,
      intensity: 1.0,
      speed: 1.0,
      easing: "ease_in_out",
      tracks: {},
    };
    onUpdateState((prev) => ({
      ...prev,
      clipboard_animation: configToCopy,
    }));
  };

  const handlePasteAnimation = () => {
    if (!selectedLayer || !state.clipboard_animation) return;
    const pasted: LayerAnimationConfig = {
      ...state.clipboard_animation,
      id: `anim_${selectedLayer.id}_${Date.now()}`,
      target_layer_id: selectedLayer.id,
    };
    updateSelectedLayer({
      animation_config: pasted,
      motion_preset: pasted.preset,
      motion_direction: pasted.direction,
      motion_duration_sec: pasted.duration_sec,
    });
  };

  return (
    <div className="h-full flex flex-col bg-zinc-900 border-l border-zinc-800 text-zinc-100 select-none overflow-hidden">
      {/* Top Header: Inspector Title and Window Controls */}
      <div className="p-3 border-b border-zinc-800 bg-zinc-950/70 flex items-center justify-between shrink-0">
        <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-1.5">
          {selectedNarration ? (
            <>
              <Icons.MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
              Narration Inspector
            </>
          ) : selectedBgm ? (
            <>
              <Icons.Music className="w-3.5 h-3.5 text-amber-400" />
              Music Inspector
            </>
          ) : selectedSfx ? (
            <>
              <Icons.Volume className="w-3.5 h-3.5 text-cyan-400" />
              SFX Inspector
            </>
          ) : (
            <>
              <Icons.Sliders className="w-3.5 h-3.5 text-indigo-400" />
              Inspector
            </>
          )}
        </h3>
        <div className="flex items-center gap-1">
          {selectedNarration && onOpenNarrationStudio && (
            <button
              type="button"
              onClick={() => onOpenNarrationStudio(selectedNarration.id)}
              className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-700/80 text-[10px] font-semibold text-emerald-300 hover:bg-emerald-900 hover:text-white transition-colors mr-1"
              title="Open full Narration Studio workspace"
            >
              Open Studio
            </button>
          )}
          {(selectedBgm || selectedSfx) && onOpenAudioLibrary && (
            <button
              type="button"
              onClick={() => onOpenAudioLibrary(selectedBgm ? "music" : "sfx")}
              className="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-700/80 text-[10px] font-semibold text-amber-300 hover:bg-amber-900 hover:text-white transition-colors mr-1"
              title="Open Audio Library"
            >
              Audio Library
            </button>
          )}
          <button
            type="button"
            className="p-1 text-zinc-400 hover:text-white rounded"
            title="Maximize Panel"
          >
            <Icons.Maximize className="w-3.5 h-3.5" />
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 text-zinc-400 hover:text-white rounded"
              title="Close Inspector"
            >
              <Icons.Minimize className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Navigation: Image | Motion | Effects | Timing (only for layers/scenes) */}
      {!selectedNarration && !selectedBgm && !selectedSfx && (
        <div className="flex items-center border-b border-zinc-800 bg-zinc-950/40 px-2 pt-1 gap-1 shrink-0">
          {(["image", "motion", "effects", "timing"] as InspectorTab[]).map((tab) => {
            const isActive = activeTab === tab;
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 text-xs font-medium capitalize rounded-t-lg transition-colors border-b-2 ${
                  isActive
                    ? "border-indigo-500 text-indigo-400 bg-zinc-900/80 font-bold"
                    : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tab}
              </button>
            );
          })}
        </div>
      )}

      {/* Selected Item Summary Card (only for layers) */}
      {!selectedNarration && selectedLayer && (
        <div className="p-3 bg-zinc-950/60 border-b border-zinc-800/80 flex items-center gap-3 shrink-0">
          <div className="w-12 h-12 rounded-lg bg-zinc-900 border border-zinc-700/80 overflow-hidden shrink-0 shadow-md">
            <img
              src={selectedLayer.image_url}
              alt="Layer thumb"
              className="w-full h-full object-cover"
            />
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold text-zinc-100 block truncate">
              {selectedLayer.name || `Panel 1`}
            </span>
            <span className="text-[10px] text-zinc-400 font-mono block">
              From Page {selectedLayer.page_sequence}
            </span>
          </div>
          {onDeleteLayer && selectedScene && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDeleteLayer(selectedLayer.id, selectedScene.id)}
              className="text-rose-400 hover:text-rose-300 p-1.5 h-7"
              title="Remove layer"
            >
              <Icons.Trash className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      )}

      {/* Main Content Area */}
      <div className="p-3 space-y-4 flex-1 overflow-y-auto min-h-0">
        {selectedNarration ? (
          <div className="space-y-4">
            {/* 1. Speaker Profile & Review Status Card */}
            <div className="p-3 bg-zinc-950/70 border border-zinc-800 rounded-xl space-y-2.5 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-emerald-950 border border-emerald-600/60 flex items-center justify-center font-bold text-xs text-emerald-300">
                    {(selectedNarration.speaker || "N").slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
                      {selectedNarration.speaker || "The Narrator"}
                      <span className="text-[9px] px-1 py-0.2 rounded bg-zinc-800 text-zinc-400 font-mono">
                        {selectedNarration.speaker_type || "NARRATOR"}
                      </span>
                    </div>
                    <div className="text-[10px] text-zinc-400 font-mono">
                      ID: {selectedNarration.id}
                    </div>
                  </div>
                </div>

                {onOpenNarrationStudio && (
                  <button
                    type="button"
                    onClick={() => onOpenNarrationStudio(selectedNarration.id)}
                    className="px-2 py-1 bg-emerald-950/90 hover:bg-emerald-900 text-emerald-300 hover:text-white border border-emerald-700/80 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition-colors shadow-sm"
                    title="Open in full Narration Studio workspace"
                  >
                    <Icons.ExternalLink className="w-3 h-3" />
                    Studio
                  </button>
                )}
              </div>

              {/* Review Status & Audio Status Row */}
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60 gap-2">
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-zinc-400">Review:</span>
                  <select
                    value={selectedNarration.review_status || "DRAFT"}
                    onChange={(e) => {
                      const nextStatus = e.target.value as "APPROVED" | "NEEDS_REVIEW" | "DRAFT";
                      onUpdateState((prev) => ({
                        ...prev,
                        narration_clips: prev.narration_clips.map((c) =>
                          c.id === selectedNarration.id ? { ...c, review_status: nextStatus } : c
                        ),
                        narration_chapter: prev.narration_chapter ? {
                          ...prev.narration_chapter,
                          segments: prev.narration_chapter.segments.map((seg: any) =>
                            seg.id === selectedNarration.id ? { ...seg, review_status: nextStatus } : seg
                          ),
                        } : prev.narration_chapter,
                      }));
                    }}
                    className={`text-[10px] font-bold rounded px-1.5 py-0.5 border bg-zinc-900 focus:outline-none ${
                      selectedNarration.review_status === "APPROVED"
                        ? "text-emerald-300 border-emerald-700"
                        : selectedNarration.review_status === "NEEDS_REVIEW"
                        ? "text-amber-300 border-amber-700"
                        : "text-zinc-400 border-zinc-700"
                    }`}
                  >
                    <option value="APPROVED">✓ Approved</option>
                    <option value="NEEDS_REVIEW">? Needs Review</option>
                    <option value="DRAFT">○ Draft</option>
                  </select>
                </div>

                {/* Audio Status Badge */}
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-zinc-400">Audio:</span>
                  {selectedNarration.status === "OUTDATED" ? (
                    <span className="px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 text-[10px] font-bold border border-amber-500 flex items-center gap-1 animate-pulse">
                      ⚠ Take Outdated
                    </span>
                  ) : selectedNarration.status === "READY" ? (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 text-[10px] font-bold border border-emerald-700 flex items-center gap-1">
                      ● Ready
                    </span>
                  ) : selectedNarration.status === "PROCESSING" ? (
                    <span className="px-1.5 py-0.5 rounded bg-blue-950/80 text-blue-300 text-[10px] font-bold border border-blue-700 flex items-center gap-1">
                      ⏳ Processing
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 text-[10px] font-bold border border-purple-700 flex items-center gap-1">
                      Queued
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* 2. Script Editor & Audio Regeneration Policy */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                  <Icons.FileText className="w-3.5 h-3.5 text-indigo-400" />
                  Narration Script
                </label>
                <div className="text-[10px] font-mono text-zinc-400">
                  Rev #{selectedNarration.text_revision || 1} • {estimateReadingDuration(selectedNarration.text, selectedNarration.speed)}s est
                </div>
              </div>

              <textarea
                value={selectedNarration.text}
                rows={4}
                onChange={(e) => {
                  const nextText = e.target.value;
                  const { updatedClip, updatedChapter } = updateClipScriptText(
                    selectedNarration,
                    nextText,
                    state.narration_chapter
                  );
                  onUpdateState((prev) => ({
                    ...prev,
                    narration_clips: prev.narration_clips.map((c) =>
                      c.id === updatedClip.id ? updatedClip : c
                    ),
                    narration_chapter: updatedChapter || prev.narration_chapter,
                  }));
                }}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-sans leading-relaxed resize-none"
                placeholder="Enter narration script text..."
              />

              {/* Outdated Notice Banner */}
              {selectedNarration.status === "OUTDATED" && (
                <div className="p-2.5 bg-amber-950/40 border border-amber-600/60 rounded-lg text-amber-200 text-xs flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5 font-bold text-[11px] text-amber-300">
                    <Icons.AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    Audio Take Outdated
                  </div>
                  <p className="text-[10px] text-amber-200/90 leading-tight">
                    Script text was modified after audio synthesis. The previous take has been preserved below for review.
                  </p>
                </div>
              )}
            </div>

            {/* 3. Audio Take Lifecycle & Player */}
            <div className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl space-y-2.5">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span>Audio Takes</span>
                <span className="text-[10px] text-zinc-500 font-mono">
                  {selectedNarration.duration_sec}s
                </span>
              </h4>

              {/* Current Active Take */}
              <div className="p-2 bg-zinc-900/80 border border-zinc-800 rounded-lg flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => handlePlayTake(selectedNarration.audio_url || "/assets/demo/aria_narration_sample.mp3", "current")}
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                      playingTake === "current"
                        ? "bg-emerald-600 text-white animate-pulse"
                        : "bg-emerald-950 text-emerald-300 hover:bg-emerald-900 border border-emerald-700/80"
                    }`}
                    title={playingTake === "current" ? "Pause" : "Play Current Take"}
                  >
                    {playingTake === "current" ? <Icons.Pause className="w-3.5 h-3.5" /> : <Icons.Play className="w-3.5 h-3.5 ml-0.5" />}
                  </button>
                  <div className="min-w-0">
                    <div className="text-[11px] font-medium text-zinc-200 truncate">
                      {selectedNarration.status === "OUTDATED" ? "Prior Take (Active)" : "Active Take"}
                    </div>
                    <div className="text-[9px] text-zinc-400 font-mono truncate">
                      {selectedNarration.duration_sec}s • {selectedNarration.speed || 1.0}x
                    </div>
                  </div>
                </div>

                {/* Regenerate Take Button */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRegenerateNarrationTake(selectedNarration.id)}
                  disabled={isGeneratingTake}
                  className="h-7 text-[10px] px-2 bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-zinc-200 font-medium shrink-0"
                >
                  {isGeneratingTake ? "Synthesizing..." : "Regenerate Take"}
                </Button>
              </div>

              {/* Preserved Previous Take (when outdated or revision > 1) */}
              {selectedNarration.previous_audio_asset_uri && (
                <div className="p-2 bg-zinc-900/40 border border-zinc-800/60 rounded-lg flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <button
                      type="button"
                      onClick={() => handlePlayTake(selectedNarration.previous_audio_asset_uri, "previous")}
                      className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                        playingTake === "previous"
                          ? "bg-amber-600 text-white animate-pulse"
                          : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-zinc-700"
                      }`}
                      title="Play Preserved Previous Take"
                    >
                      {playingTake === "previous" ? <Icons.Pause className="w-3 h-3" /> : <Icons.Play className="w-3 h-3 ml-0.5" />}
                    </button>
                    <div className="min-w-0">
                      <div className="text-[10px] font-medium text-zinc-300 truncate">
                        Preserved Take (Rev #{Math.max(1, (selectedNarration.text_revision || 2) - 1)})
                      </div>
                      <div className="text-[8px] text-zinc-500 font-mono">Reference Take</div>
                    </div>
                  </div>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                    Previous
                  </span>
                </div>
              )}
            </div>

            {/* 4. Voice & Delivery Tuning */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                <Icons.Mic className="w-3.5 h-3.5 text-indigo-400" />
                Delivery & Emotion
              </h4>

              {/* Emotion Selector */}
              <div className="space-y-1">
                <label className="text-[11px] text-zinc-400 block">Performance Emotion</label>
                <select
                  value={selectedNarration.emotion || "Neutral"}
                  onChange={(e) => {
                    const nextEmotion = e.target.value as NarrationEmotion;
                    onUpdateState((prev) => ({
                      ...prev,
                      narration_clips: prev.narration_clips.map((c) =>
                        c.id === selectedNarration.id ? { ...c, emotion: nextEmotion } : c
                      ),
                    }));
                  }}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-100 font-medium focus:outline-none focus:border-indigo-500"
                >
                  {[
                    "Neutral",
                    "Dramatic",
                    "Intense",
                    "Whisper",
                    "Shouting",
                    "Mysterious",
                    "Sarcastic",
                    "Melancholic",
                    "Joyful",
                    "Suspenseful",
                    "Breathless",
                  ].map((emo) => (
                    <option key={emo} value={emo}>
                      {emo}
                    </option>
                  ))}
                </select>
              </div>

              {/* Speech Speed Slider */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400">Speech Pace</span>
                  <span className="text-zinc-200 font-mono">{selectedNarration.speed || 1.0}x</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="60"
                    max="150"
                    step="5"
                    value={Math.round((selectedNarration.speed || 1.0) * 100)}
                    onChange={(e) => {
                      const nextSpeed = parseFloat(e.target.value) / 100;
                      const nextDuration = estimateReadingDuration(selectedNarration.text, nextSpeed);
                      onUpdateState((prev) => ({
                        ...prev,
                        narration_clips: prev.narration_clips.map((c) =>
                          c.id === selectedNarration.id ? { ...c, speed: nextSpeed, duration_sec: nextDuration } : c
                        ),
                      }));
                    }}
                    className="flex-1 accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const nextDuration = estimateReadingDuration(selectedNarration.text, 1.0);
                      onUpdateState((prev) => ({
                        ...prev,
                        narration_clips: prev.narration_clips.map((c) =>
                          c.id === selectedNarration.id ? { ...c, speed: 1.0, duration_sec: nextDuration } : c
                        ),
                      }));
                    }}
                    className="text-[9px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-400 hover:text-white"
                  >
                    Reset
                  </button>
                </div>
              </div>

              {/* Delivery Intensity */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400">Emotional Intensity</span>
                  <span className="text-zinc-200 font-mono">
                    {Math.round((selectedNarration.delivery_intensity ?? 0.6) * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={Math.round((selectedNarration.delivery_intensity ?? 0.6) * 100)}
                  onChange={(e) => {
                    const nextIntensity = parseFloat(e.target.value) / 100;
                    onUpdateState((prev) => ({
                      ...prev,
                      narration_clips: prev.narration_clips.map((c) =>
                        c.id === selectedNarration.id ? { ...c, delivery_intensity: nextIntensity } : c
                      ),
                    }));
                  }}
                  className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                />
              </div>
            </div>

            {/* 5. Smart Scene Binding Section */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Icons.Layers className="w-3.5 h-3.5 text-emerald-400" />
                  Smart Scene Binding
                </span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                  selectedNarration.linked_to_scene !== false
                    ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                    : "bg-zinc-800 text-zinc-400"
                }`}>
                  {selectedNarration.linked_to_scene !== false ? "LINKED" : "UNLINKED"}
                </span>
              </h4>

              {/* Linked Mode */}
              {selectedNarration.linked_to_scene !== false ? (
                <div className="space-y-2 text-xs">
                  {(() => {
                    const parentScene = state.scenes.find((s) => s.id === selectedNarration.scene_id);
                    return (
                      <>
                        <div className="p-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-300">
                          <div className="font-medium text-zinc-200 truncate">
                            {parentScene?.title || `Scene ID: ${selectedNarration.scene_id || "Unassigned"}`}
                          </div>
                          <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                            Scene start: {parentScene?.start_time_sec ?? 0}s • Offset: +{selectedNarration.scene_offset_sec ?? 0}s
                          </div>
                        </div>

                        {/* Speech Duration Overflow Choice UI */}
                        {parentScene && (() => {
                          const neededSec = (selectedNarration.scene_offset_sec || 0) + (selectedNarration.duration_sec || 3.5);
                          const overflowSec = Math.round((neededSec - parentScene.duration_sec) * 10) / 10;
                          if (overflowSec <= 0) return null;
                          return (
                            <div className="p-2 rounded bg-amber-950/40 border border-amber-800/80 text-amber-300 text-xs space-y-1.5">
                              <div className="flex items-center justify-between font-bold text-[11px]">
                                <span>Speech Exceeds Scene</span>
                                <span className="font-mono text-[10px]">+{overflowSec}s</span>
                              </div>
                              <p className="text-[10px] text-amber-200/80 leading-normal">
                                Narration ({selectedNarration.duration_sec}s) extends beyond scene duration ({parentScene.duration_sec}s).
                              </p>
                              <button
                                type="button"
                                onClick={() => {
                                  const newSceneDuration = Math.round((neededSec + 0.5) * 10) / 10;
                                  onUpdateState((prev) => {
                                    const updatedScenes = prev.scenes.map((s) =>
                                      s.id === parentScene.id ? { ...s, duration_sec: newSceneDuration } : s
                                    );
                                    let acc = 0;
                                    const resynced = updatedScenes.map((s) => {
                                      const st = acc;
                                      acc += s.duration_sec;
                                      return { ...s, start_time_sec: Math.round(st * 10) / 10 };
                                    });
                                    const resyncedClips = rippleShiftLinkedNarration(resynced, prev.narration_clips);
                                    return {
                                      ...prev,
                                      scenes: resynced,
                                      narration_clips: resyncedClips,
                                      timeline_duration_sec: Math.round(acc * 10) / 10,
                                    };
                                  });
                                }}
                                className="w-full py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-[10px] font-bold transition-colors"
                              >
                                Extend Scene to {Math.round((neededSec + 0.5) * 10) / 10}s
                              </button>
                            </div>
                          );
                        })()}

                        {/* Snap vs Preserve vs Unlink Controls */}
                        <div className="grid grid-cols-2 gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => {
                              if (!parentScene) return;
                              const relinked = relinkClipToScene(selectedNarration, parentScene, "snap_to_start");
                              onUpdateState((prev) => ({
                                ...prev,
                                narration_clips: prev.narration_clips.map((c) =>
                                  c.id === relinked.id ? relinked : c
                                ),
                              }));
                            }}
                            className="px-2 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 rounded text-[10px] font-semibold text-zinc-200 transition-colors"
                          >
                            Snap to Start (0s)
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (!parentScene) return;
                              const relinked = relinkClipToScene(selectedNarration, parentScene, "preserve_offset");
                              onUpdateState((prev) => ({
                                ...prev,
                                narration_clips: prev.narration_clips.map((c) =>
                                  c.id === relinked.id ? relinked : c
                                ),
                              }));
                            }}
                            className="px-2 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 rounded text-[10px] font-semibold text-zinc-200 transition-colors"
                          >
                            Preserve Offset
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            const unlinked = unlinkClipFromScene(selectedNarration);
                            onUpdateState((prev) => ({
                              ...prev,
                              narration_clips: prev.narration_clips.map((c) =>
                                c.id === unlinked.id ? unlinked : c
                              ),
                            }));
                          }}
                          className="w-full mt-1 px-2 py-1 bg-zinc-900 hover:bg-rose-950/40 hover:text-rose-300 border border-zinc-800 hover:border-rose-800/60 rounded text-[10px] font-medium text-zinc-400 transition-colors"
                        >
                          Unlink from Scene (Keep absolute time)
                        </button>
                      </>
                    );
                  })()}
                </div>
              ) : (
                /* Unlinked Independent Mode */
                <div className="space-y-2 text-xs">
                  <p className="text-[10px] text-zinc-400">
                    This narration clip operates independently on absolute timeline coordinates ({selectedNarration.start_time_sec}s). It will not shift when scenes ripple.
                  </p>

                  <div className="pt-1 space-y-1.5">
                    <label className="text-[10px] text-zinc-400 block font-medium">Relink to a Scene:</label>
                    <select
                      defaultValue=""
                      onChange={(e) => {
                        const targetSceneId = e.target.value;
                        if (!targetSceneId) return;
                        const targetScene = state.scenes.find((s) => s.id === targetSceneId);
                        if (!targetScene) return;
                        const relinked = relinkClipToScene(selectedNarration, targetScene, "snap_to_start");
                        onUpdateState((prev) => ({
                          ...prev,
                          narration_clips: prev.narration_clips.map((c) =>
                            c.id === relinked.id ? relinked : c
                          ),
                        }));
                      }}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="" disabled>Select scene to link...</option>
                      {state.scenes.map((sc) => (
                        <option key={sc.id} value={sc.id}>
                          {sc.sequence}. {sc.title} ({sc.start_time_sec}s - {sc.start_time_sec + sc.duration_sec}s)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : selectedBgm ? (
          <div className="space-y-4">
            {/* 1. Track Info & Availability */}
            <div className="p-3 bg-zinc-950/70 border border-zinc-800 rounded-xl space-y-2.5 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-indigo-950 border border-indigo-600/60 flex items-center justify-center font-bold text-xs text-indigo-300">
                    <Icons.Music className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-zinc-100 flex items-center gap-1.5 truncate">
                      <span className="truncate">{selectedBgm.title || "Background Music"}</span>
                    </div>
                    <div className="text-[10px] text-zinc-400 font-mono">
                      ID: {selectedBgm.id}
                    </div>
                  </div>
                </div>

                {onOpenAudioLibrary && (
                  <button
                    type="button"
                    onClick={() => onOpenAudioLibrary("music")}
                    className="px-2 py-1 bg-indigo-950/90 hover:bg-indigo-900 text-indigo-300 hover:text-white border border-indigo-700/80 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition-colors shadow-sm"
                    title="Browse BGM in Audio Library"
                  >
                    <Icons.ExternalLink className="w-3 h-3" />
                    Library
                  </button>
                )}
              </div>

              {/* Badges Row */}
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60 gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 font-medium">
                    {selectedBgm.category || "Background Music"}
                  </span>
                  {selectedBgm.bpm && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
                      {selectedBgm.bpm} BPM
                    </span>
                  )}
                  {selectedBgm.key && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
                      {selectedBgm.key}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  {selectedBgm.availability === "UNAVAILABLE" ? (
                    <span className="px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-300 text-[10px] font-bold border border-rose-700 flex items-center gap-1">
                      Missing Audio
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 text-[10px] font-bold border border-emerald-700 flex items-center gap-1">
                      Ready
                    </span>
                  )}
                </div>
              </div>

              {/* Audio Playback Preview */}
              <div className="p-2 bg-zinc-900/60 border border-zinc-800/80 rounded-lg flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => handlePlayTake(selectedBgm.file_url || "/assets/demo/crystal_resonance_bgm.mp3", selectedBgm.id)}
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                      playingTake === selectedBgm.id
                        ? "bg-indigo-600 text-white animate-pulse"
                        : "bg-indigo-950 text-indigo-300 hover:bg-indigo-900 border border-indigo-700/80"
                    }`}
                    title={playingTake === selectedBgm.id ? "Pause" : "Play BGM Track"}
                  >
                    {playingTake === selectedBgm.id ? <Icons.Pause className="w-3.5 h-3.5" /> : <Icons.Play className="w-3.5 h-3.5 ml-0.5" />}
                  </button>
                  <div className="min-w-0">
                    <div className="text-[11px] font-medium text-zinc-200 truncate">
                      Track Preview
                    </div>
                    <div className="text-[9px] text-zinc-400 font-mono truncate">
                      {selectedBgm.duration_sec.toFixed(1)}s • {Math.round(selectedBgm.volume * 100)}% Vol
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onUpdateState((prev) => duplicateAudioClip(prev, selectedBgm!.id, "bgm"))}
                  className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-[10px] font-medium transition-colors"
                >
                  Duplicate
                </button>
              </div>
            </div>

            {/* 2. Timing Controls */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span>Timing & Placement</span>
                <span className="text-[10px] font-mono text-zinc-400">
                  End: {(selectedBgm.start_time_sec + selectedBgm.duration_sec).toFixed(2)}s
                </span>
              </h4>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Start Time (sec)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={parseFloat(selectedBgm.start_time_sec.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { start_time_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Duration (sec)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.5"
                    value={parseFloat(selectedBgm.duration_sec.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0.5, parseFloat(e.target.value) || 0.5);
                      onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { duration_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>

            {/* 3. Audio Levels & Fades */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span>Audio Levels & Fades</span>
                <span className="text-[10px] font-mono text-indigo-400">
                  {Math.round(selectedBgm.volume * 100)}%
                </span>
              </h4>

              {/* Master Volume Slider */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400">Track Volume</span>
                  <span className="text-zinc-200 font-mono">{Math.round(selectedBgm.volume * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={Math.round(selectedBgm.volume * 100)}
                  onChange={(e) => {
                    const nextVol = parseFloat(e.target.value) / 100;
                    onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { volume: nextVol }));
                  }}
                  className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                />
              </div>

              {/* Fade In & Fade Out */}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Fade In (sec)</label>
                  <input
                    type="number"
                    step="0.25"
                    min="0"
                    max="10"
                    value={selectedBgm.fade_in_sec ?? 1.5}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { fade_in_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Fade Out (sec)</label>
                  <input
                    type="number"
                    step="0.25"
                    min="0"
                    max="10"
                    value={selectedBgm.fade_out_sec ?? 2.0}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { fade_out_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Loop Toggle */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-zinc-300">Continuous Loop</span>
                <button
                  type="button"
                  onClick={() => {
                    onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { loop: !(selectedBgm?.loop ?? true) }));
                  }}
                  className={`w-8 h-4 rounded-full transition-colors relative ${
                    (selectedBgm.loop ?? true) ? "bg-indigo-600" : "bg-zinc-800"
                  }`}
                >
                  <div
                    className={`w-3 h-3 rounded-full bg-white transition-transform absolute top-0.5 ${
                      (selectedBgm.loop ?? true) ? "left-4.5" : "left-0.5"
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* 4. Narration Ducking Settings */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Icons.Volume className="w-3.5 h-3.5 text-indigo-400" />
                  Narration Ducking
                </span>
                <button
                  type="button"
                  onClick={() => {
                    onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { ducking_enabled: !(selectedBgm?.ducking_enabled ?? true) }));
                  }}
                  className={`w-8 h-4 rounded-full transition-colors relative ${
                    (selectedBgm.ducking_enabled ?? true) ? "bg-indigo-600" : "bg-zinc-800"
                  }`}
                >
                  <div
                    className={`w-3 h-3 rounded-full bg-white transition-transform absolute top-0.5 ${
                      (selectedBgm.ducking_enabled ?? true) ? "left-4.5" : "left-0.5"
                    }`}
                  />
                </button>
              </h4>

              <p className="text-[10px] text-zinc-400 leading-relaxed">
                Automatically suppresses background music volume during active narration dialogue to preserve vocal clarity.
              </p>

              {(selectedBgm.ducking_enabled ?? true) && (
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-zinc-400">Ducking Attenuation</span>
                    <span className="text-indigo-300 font-mono">
                      {selectedBgm.ducking_amount_db ?? -12} dB
                    </span>
                  </div>
                  <input
                    type="range"
                    min="-24"
                    max="-3"
                    step="1"
                    value={selectedBgm.ducking_amount_db ?? -12}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      onUpdateState((prev) => updateBgmClip(prev, selectedBgm!.id, { ducking_amount_db: val }));
                    }}
                    className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-zinc-500 font-mono">
                    <span>-24 dB (Aggressive)</span>
                    <span>-12 dB (Standard)</span>
                    <span>-3 dB (Subtle)</span>
                  </div>
                </div>
              )}
            </div>

            {/* Delete Button */}
            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onUpdateState((prev) => deleteAudioClip(prev, selectedBgm!.id, "bgm"))}
                className="w-full bg-rose-950/20 hover:bg-rose-950/50 text-rose-300 border-rose-900/50 text-xs flex items-center justify-center gap-1.5"
              >
                <Icons.Trash className="w-3.5 h-3.5" />
                Remove BGM Track
              </Button>
            </div>
          </div>
        ) : selectedSfx ? (
          <div className="space-y-4">
            {/* 1. SFX Cue Info */}
            <div className="p-3 bg-zinc-950/70 border border-zinc-800 rounded-xl space-y-2.5 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-amber-950 border border-amber-600/60 flex items-center justify-center font-bold text-xs text-amber-300">
                    <Icons.Volume className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-zinc-100 flex items-center gap-1.5 truncate">
                      <span className="truncate">{selectedSfx.name || "Sound Effect"}</span>
                    </div>
                    <div className="text-[10px] text-zinc-400 font-mono">
                      ID: {selectedSfx.id}
                    </div>
                  </div>
                </div>

                {onOpenAudioLibrary && (
                  <button
                    type="button"
                    onClick={() => onOpenAudioLibrary("sfx")}
                    className="px-2 py-1 bg-amber-950/90 hover:bg-amber-900 text-amber-300 hover:text-white border border-amber-700/80 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition-colors shadow-sm"
                    title="Browse SFX in Audio Library"
                  >
                    <Icons.ExternalLink className="w-3 h-3" />
                    Library
                  </button>
                )}
              </div>

              {/* Badges Row */}
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60 gap-2">
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 font-medium">
                  {selectedSfx.category || "Sound Effect"}
                </span>

                <div className="flex items-center gap-1">
                  {selectedSfx.availability === "UNAVAILABLE" ? (
                    <span className="px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-300 text-[10px] font-bold border border-rose-700 flex items-center gap-1">
                      Missing Audio
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 text-[10px] font-bold border border-emerald-700 flex items-center gap-1">
                      Ready
                    </span>
                  )}
                </div>
              </div>

              {/* Audio Playback Preview */}
              <div className="p-2 bg-zinc-900/60 border border-zinc-800/80 rounded-lg flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => handlePlayTake(selectedSfx.file_url || "/assets/demo/blade_shimmer_sfx.mp3", selectedSfx.id)}
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                      playingTake === selectedSfx.id
                        ? "bg-amber-600 text-white animate-pulse"
                        : "bg-amber-950 text-amber-300 hover:bg-amber-900 border border-amber-700/80"
                    }`}
                    title={playingTake === selectedSfx.id ? "Pause" : "Play SFX Cue"}
                  >
                    {playingTake === selectedSfx.id ? <Icons.Pause className="w-3.5 h-3.5" /> : <Icons.Play className="w-3.5 h-3.5 ml-0.5" />}
                  </button>
                  <div className="min-w-0">
                    <div className="text-[11px] font-medium text-zinc-200 truncate">
                      Cue Preview
                    </div>
                    <div className="text-[9px] text-zinc-400 font-mono truncate">
                      {selectedSfx.duration_sec.toFixed(1)}s • {Math.round(selectedSfx.volume * 100)}% Vol
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onUpdateState((prev) => duplicateAudioClip(prev, selectedSfx!.id, "sfx"))}
                  className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-[10px] font-medium transition-colors"
                >
                  Duplicate
                </button>
              </div>
            </div>

            {/* 2. Timing Controls */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span>Trigger Timing</span>
                <span className="text-[10px] font-mono text-zinc-400">
                  End: {(selectedSfx.start_time_sec + selectedSfx.duration_sec).toFixed(2)}s
                </span>
              </h4>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Trigger Time (sec)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={parseFloat(selectedSfx.start_time_sec.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateSfxClip(prev, selectedSfx!.id, { start_time_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Duration (sec)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0.1"
                    value={parseFloat(selectedSfx.duration_sec.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0.1, parseFloat(e.target.value) || 0.1);
                      onUpdateState((prev) => updateSfxClip(prev, selectedSfx!.id, { duration_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>
            </div>

            {/* 3. Audio Levels & Fades */}
            <div className="space-y-3 p-3 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center justify-between">
                <span>Audio Levels & Fades</span>
                <span className="text-[10px] font-mono text-amber-400">
                  {Math.round(selectedSfx.volume * 100)}%
                </span>
              </h4>

              {/* Master Volume Slider */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400">Cue Volume</span>
                  <span className="text-zinc-200 font-mono">{Math.round(selectedSfx.volume * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={Math.round(selectedSfx.volume * 100)}
                  onChange={(e) => {
                    const nextVol = parseFloat(e.target.value) / 100;
                    onUpdateState((prev) => updateSfxClip(prev, selectedSfx!.id, { volume: nextVol }));
                  }}
                  className="w-full accent-amber-500 h-1 bg-zinc-800 rounded cursor-pointer"
                />
              </div>

              {/* Fade In & Fade Out */}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Fade In (sec)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="5"
                    value={selectedSfx.fade_in_sec ?? 0}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateSfxClip(prev, selectedSfx!.id, { fade_in_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 block font-medium">Fade Out (sec)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="5"
                    value={selectedSfx.fade_out_sec ?? 0.1}
                    onChange={(e) => {
                      const val = Math.max(0, parseFloat(e.target.value) || 0);
                      onUpdateState((prev) => updateSfxClip(prev, selectedSfx!.id, { fade_out_sec: val }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>
            </div>

            {/* Delete Button */}
            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onUpdateState((prev) => deleteAudioClip(prev, selectedSfx!.id, "sfx"))}
                className="w-full bg-rose-950/20 hover:bg-rose-950/50 text-rose-300 border-rose-900/50 text-xs flex items-center justify-center gap-1.5"
              >
                <Icons.Trash className="w-3.5 h-3.5" />
                Remove SFX Cue
              </Button>
            </div>
          </div>
        ) : selectedLayer || selectedScene ? (
          <>
            {/* TAB 1: Image & Transform */}
            {activeTab === "image" && selectedLayer && (
              <div className="space-y-4">
                {/* Transform Block */}
                <div className="space-y-3">
                  <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                    Transform
                  </h4>

                  {/* Position X / Y */}
                  <div className="grid grid-cols-2 gap-2 items-center">
                    <span className="text-xs text-zinc-300">Position</span>
                    <div className="flex items-center gap-1.5">
                      <div className="flex items-center bg-zinc-950 border border-zinc-800 rounded px-2 py-1">
                        <span className="text-[10px] text-zinc-500 font-mono mr-1">X</span>
                        <input
                          type="number"
                          value={Math.round(selectedLayer.transform.x * 6.4 + 320)}
                          onChange={(e) =>
                            updateSelectedLayerTransform({
                              x: (parseFloat(e.target.value) - 320) / 6.4,
                            })
                          }
                          className="w-12 bg-transparent text-xs font-mono text-zinc-100 text-right focus:outline-none"
                        />
                      </div>
                      <div className="flex items-center bg-zinc-950 border border-zinc-800 rounded px-2 py-1">
                        <span className="text-[10px] text-zinc-500 font-mono mr-1">Y</span>
                        <input
                          type="number"
                          value={Math.round(selectedLayer.transform.y * 3.6 + 180)}
                          onChange={(e) =>
                            updateSelectedLayerTransform({
                              y: (parseFloat(e.target.value) - 180) / 3.6,
                            })
                          }
                          className="w-12 bg-transparent text-xs font-mono text-zinc-100 text-right focus:outline-none"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Scale Slider */}
                  <div className="grid grid-cols-2 gap-2 items-center">
                    <span className="text-xs text-zinc-300">Scale</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min="50"
                        max="250"
                        step="5"
                        value={Math.round(selectedLayer.transform.scale * 100)}
                        onChange={(e) =>
                          updateSelectedLayerTransform({
                            scale: parseFloat(e.target.value) / 100,
                          })
                        }
                        className="flex-1 accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                      />
                      <span className="text-xs font-mono text-zinc-300 w-10 text-right">
                        {Math.round(selectedLayer.transform.scale * 100)}%
                      </span>
                    </div>
                  </div>

                  {/* Rotation Dropdown */}
                  <div className="grid grid-cols-2 gap-2 items-center">
                    <span className="text-xs text-zinc-300">Rotation</span>
                    <select
                      value={selectedLayer.transform.rotation}
                      onChange={(e) =>
                        updateSelectedLayerTransform({
                          rotation: parseInt(e.target.value) || 0,
                        })
                      }
                      className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="0">0°</option>
                      <option value="90">90°</option>
                      <option value="180">180°</option>
                      <option value="270">270°</option>
                    </select>
                  </div>

                  {/* Opacity Slider */}
                  <div className="grid grid-cols-2 gap-2 items-center">
                    <span className="text-xs text-zinc-300">Opacity</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min="0"
                        max="100"
                        step="5"
                        value={Math.round(selectedLayer.transform.opacity * 100)}
                        onChange={(e) =>
                          updateSelectedLayerTransform({
                            opacity: parseFloat(e.target.value) / 100,
                          })
                        }
                        className="flex-1 accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                      />
                      <span className="text-xs font-mono text-zinc-300 w-10 text-right">
                        {Math.round(selectedLayer.transform.opacity * 100)}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Crop / Frame Section */}
                <div className="space-y-2 pt-3 border-t border-zinc-800">
                  <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                    Crop / Frame
                  </h4>
                  <div className="flex items-center justify-between gap-2 p-2 bg-zinc-950 rounded-lg border border-zinc-800">
                    <button
                      type="button"
                      onClick={() =>
                        updateSelectedLayerTransform({
                          x: selectedLayer.transform.x - 5,
                        })
                      }
                      className="p-1 text-zinc-400 hover:text-white"
                      title="Nudge Left"
                    >
                      <Icons.ChevronDown className="w-4 h-4 rotate-90" />
                    </button>
                    <div className="h-10 w-16 rounded overflow-hidden border border-zinc-700">
                      <img
                        src={selectedLayer.image_url}
                        alt="Crop preview"
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        updateSelectedLayerTransform({
                          x: selectedLayer.transform.x + 5,
                        })
                      }
                      className="p-1 text-zinc-400 hover:text-white"
                      title="Nudge Right"
                    >
                      <Icons.ChevronDown className="w-4 h-4 -rotate-90" />
                    </button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        updateSelectedLayerTransform({
                          x: 0,
                          y: 0,
                          scale: 1.0,
                          rotation: 0,
                          opacity: 1.0,
                        })
                      }
                      className="text-xs h-7 px-2.5 ml-2"
                    >
                      Reset
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: Motion Workspace (Layer Motion | Camera Motion | Keyframes) */}
            {activeTab === "motion" && (
              <div className="space-y-3">
                {/* Sub-mode Segmented Switcher */}
                <div className="grid grid-cols-3 gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800 text-xs">
                  <button
                    type="button"
                    onClick={() => setMotionSubTab("layer")}
                    className={`py-1 rounded font-medium transition-colors ${
                      motionSubTab === "layer"
                        ? "bg-indigo-600 text-white font-bold"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    Layer Motion
                  </button>
                  <button
                    type="button"
                    onClick={() => setMotionSubTab("camera")}
                    className={`py-1 rounded font-medium transition-colors ${
                      motionSubTab === "camera"
                        ? "bg-indigo-600 text-white font-bold"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    Camera
                  </button>
                  <button
                    type="button"
                    onClick={() => setMotionSubTab("keyframes")}
                    className={`py-1 rounded font-medium transition-colors ${
                      motionSubTab === "keyframes"
                        ? "bg-indigo-600 text-white font-bold"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    Keyframes
                  </button>
                </div>

                {/* --- SUB-MODE A: LAYER MOTION --- */}
                {motionSubTab === "layer" && selectedLayer && (
                  <div className="space-y-3">
                    {/* Visual Preset Selector with Categories */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                          Layer Motion Preset
                        </h4>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={handleCopyAnimation}
                            className="text-[10px] text-zinc-400 hover:text-indigo-300 px-1.5 py-0.5 rounded bg-zinc-800"
                            title="Copy animation config to clipboard"
                          >
                            Copy
                          </button>
                          <button
                            type="button"
                            onClick={handlePasteAnimation}
                            disabled={!state.clipboard_animation}
                            className="text-[10px] text-zinc-400 hover:text-indigo-300 disabled:opacity-30 px-1.5 py-0.5 rounded bg-zinc-800"
                            title="Paste animation config from clipboard"
                          >
                            Paste
                          </button>
                        </div>
                      </div>

                      <select
                        value={selectedLayer.motion_preset || "slow_zoom_in"}
                        onChange={(e) => {
                          const preset = e.target.value as MotionPresetType;
                          updateSelectedLayer({ motion_preset: preset });
                          updateLayerAnimationConfig((cfg) => ({ ...cfg, preset }));
                        }}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 font-medium"
                      >
                        <optgroup label="Static">
                          <option value="none">None (Static)</option>
                        </optgroup>
                        <optgroup label="Entrances & Exits">
                          <option value="slide_in_left">Slide In Left</option>
                          <option value="slide_in_right">Slide In Right</option>
                          <option value="slide_in_top">Slide In Top</option>
                          <option value="slide_in_bottom">Slide In Bottom</option>
                          <option value="slide_out">Slide Out</option>
                          <option value="fade_in">Fade In</option>
                          <option value="fade_out">Fade Out</option>
                          <option value="fade_in_out">Fade In & Out</option>
                          <option value="opacity_reveal">Opacity Reveal</option>
                        </optgroup>
                        <optgroup label="Zoom & Pan">
                          <option value="slow_zoom_in">Slow Zoom In</option>
                          <option value="slow_zoom_out">Slow Zoom Out</option>
                          <option value="pan_left">Pan Left</option>
                          <option value="pan_right">Pan Right</option>
                          <option value="pan_up">Pan Up</option>
                          <option value="pan_down">Pan Down</option>
                          <option value="diagonal_pan">Diagonal Pan</option>
                        </optgroup>
                        <optgroup label="Motion & Transform">
                          <option value="move">Move</option>
                          <option value="rise">Rise</option>
                          <option value="fall">Fall</option>
                          <option value="scale_up">Scale Up</option>
                          <option value="scale_down">Scale Down</option>
                          <option value="rotate">Rotate</option>
                        </optgroup>
                        <optgroup label="Effects & Impacts">
                          <option value="shake_impact">Impact Shake</option>
                          <option value="flash">Flash</option>
                          <option value="blur">Blur Transition</option>
                          <option value="cross_dissolve">Cross Dissolve</option>
                          <option value="wipe">Wipe</option>
                        </optgroup>
                        <optgroup label="Custom Keyframes">
                          <option value="custom">Custom Keyframe Animation</option>
                        </optgroup>
                      </select>
                    </div>

                    {/* Motion Direction Controls */}
                    <div className="space-y-1.5 pt-2 border-t border-zinc-800">
                      <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                        Direction
                      </h4>
                      <div className="grid grid-cols-4 gap-1">
                        {[
                          { dir: "left" as const, label: "←", title: "Move Left" },
                          { dir: "right" as const, label: "→", title: "Move Right" },
                          { dir: "up" as const, label: "↑", title: "Move Up" },
                          { dir: "down" as const, label: "↓", title: "Move Down" },
                        ].map((item) => {
                          const isCurrent =
                            (selectedLayer.motion_direction || "right") === item.dir;
                          return (
                            <button
                              key={item.dir}
                              type="button"
                              onClick={() => {
                                updateSelectedLayer({ motion_direction: item.dir });
                                updateLayerAnimationConfig((cfg) => ({ ...cfg, direction: item.dir }));
                              }}
                              className={`py-1.5 rounded border text-sm font-bold transition-all ${
                                isCurrent
                                  ? "bg-indigo-600 border-indigo-500 text-white shadow-sm"
                                  : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-white"
                              }`}
                              title={item.title}
                            >
                              {item.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Duration Slider */}
                    <div className="space-y-1 pt-2 border-t border-zinc-800">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-300">Duration</span>
                        <span className="text-xs font-mono text-zinc-100 font-bold">
                          {selectedLayer.motion_duration_sec || 2.5}s
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0.2"
                        max="10.0"
                        step="0.1"
                        value={selectedLayer.motion_duration_sec || 2.5}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          updateSelectedLayer({ motion_duration_sec: val });
                          updateLayerAnimationConfig((cfg) => ({ ...cfg, duration_sec: val }));
                        }}
                        className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                      />
                    </div>

                    {/* Intensity & Speed Sliders */}
                    <div className="grid grid-cols-2 gap-2 pt-2 border-t border-zinc-800">
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-zinc-400">Intensity</span>
                          <span className="text-[10px] font-mono text-zinc-200">
                            {selectedLayer.animation_config?.intensity ?? 1.0}x
                          </span>
                        </div>
                        <input
                          type="range"
                          min="0.2"
                          max="2.5"
                          step="0.1"
                          value={selectedLayer.animation_config?.intensity ?? 1.0}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value);
                            updateLayerAnimationConfig((cfg) => ({ ...cfg, intensity: val }));
                          }}
                          className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                        />
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-zinc-400">Speed</span>
                          <span className="text-[10px] font-mono text-zinc-200">
                            {selectedLayer.animation_config?.speed ?? 1.0}x
                          </span>
                        </div>
                        <input
                          type="range"
                          min="0.5"
                          max="3.0"
                          step="0.25"
                          value={selectedLayer.animation_config?.speed ?? 1.0}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value);
                            updateLayerAnimationConfig((cfg) => ({ ...cfg, speed: val }));
                          }}
                          className="w-full accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
                        />
                      </div>
                    </div>

                    {/* Easing Function */}
                    <div className="space-y-1 pt-2 border-t border-zinc-800">
                      <label className="text-[11px] text-zinc-400 block">Easing Curve</label>
                      <select
                        value={selectedLayer.animation_config?.easing || "ease_in_out"}
                        onChange={(e) => {
                          const easing = e.target.value as AnimationEasing;
                          updateLayerAnimationConfig((cfg) => ({ ...cfg, easing }));
                        }}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
                      >
                        <option value="linear">Linear (Constant Speed)</option>
                        <option value="ease_in">Ease In (Accelerate)</option>
                        <option value="ease_out">Ease Out (Decelerate)</option>
                        <option value="ease_in_out">Ease In-Out (Smooth S-Curve)</option>
                        <option value="cubic_bezier">Cubic Bezier (Custom Smooth)</option>
                      </select>
                    </div>

                    {/* Quick Action Buttons: Preview / Reset / Remove */}
                    <div className="flex items-center gap-1.5 pt-2 border-t border-zinc-800">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          if (selectedScene) {
                            onUpdateState((s) => ({
                              ...s,
                              playhead_sec: selectedScene.start_time_sec + (selectedLayer?.start_offset_sec || 0),
                              is_playing: true,
                            }));
                          }
                        }}
                        className="flex-1 text-xs h-7 text-indigo-400 hover:text-white"
                      >
                        <Icons.Play className="w-3 h-3 mr-1" />
                        Preview
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          updateSelectedLayer({
                            motion_preset: "none",
                            motion_duration_sec: 2.5,
                            motion_direction: "right",
                            animation_config: undefined,
                          });
                        }}
                        className="text-xs h-7 px-2 text-rose-400 hover:text-rose-300"
                        title="Remove Animation"
                      >
                        Remove
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          updateLayerAnimationConfig((cfg) => ({
                            ...cfg,
                            intensity: 1.0,
                            speed: 1.0,
                            easing: "ease_in_out",
                          }));
                        }}
                        className="text-xs h-7 px-2"
                        title="Reset sliders"
                      >
                        Reset
                      </Button>
                    </div>
                  </div>
                )}

                {/* --- SUB-MODE B: CAMERA MOTION --- */}
                {motionSubTab === "camera" && selectedScene && (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                        Scene Camera Preset
                      </h4>
                      <select
                        value={selectedScene.camera?.preset || "static"}
                        onChange={(e) => {
                          const preset = e.target.value as SceneCameraPreset;
                          if (preset === "static") {
                            updateSceneCamera({
                              preset: "static",
                              zoom_start: 1.0,
                              zoom_end: 1.0,
                              pan_x_start: 0,
                              pan_x_end: 0,
                              pan_y_start: 0,
                              pan_y_end: 0,
                            });
                          } else if (preset === "slow_zoom_in") {
                            updateSceneCamera({
                              preset: "slow_zoom_in",
                              zoom_start: 1.0,
                              zoom_end: 1.25,
                              pan_x_start: 0,
                              pan_x_end: 0,
                              pan_y_start: 0,
                              pan_y_end: 0,
                            });
                          } else if (preset === "slow_zoom_out") {
                            updateSceneCamera({
                              preset: "slow_zoom_out",
                              zoom_start: 1.25,
                              zoom_end: 1.0,
                              pan_x_start: 0,
                              pan_x_end: 0,
                              pan_y_start: 0,
                              pan_y_end: 0,
                            });
                          } else if (preset === "pan_left") {
                            updateSceneCamera({
                              preset: "pan_left",
                              zoom_start: 1.15,
                              zoom_end: 1.15,
                              pan_x_start: 12,
                              pan_x_end: -12,
                              pan_y_start: 0,
                              pan_y_end: 0,
                            });
                          } else if (preset === "pan_right") {
                            updateSceneCamera({
                              preset: "pan_right",
                              zoom_start: 1.15,
                              zoom_end: 1.15,
                              pan_x_start: -12,
                              pan_x_end: 12,
                              pan_y_start: 0,
                              pan_y_end: 0,
                            });
                          } else if (preset === "pan_up") {
                            updateSceneCamera({
                              preset: "pan_up",
                              zoom_start: 1.15,
                              zoom_end: 1.15,
                              pan_x_start: 0,
                              pan_x_end: 0,
                              pan_y_start: 12,
                              pan_y_end: -12,
                            });
                          } else if (preset === "pan_down") {
                            updateSceneCamera({
                              preset: "pan_down",
                              zoom_start: 1.15,
                              zoom_end: 1.15,
                              pan_x_start: 0,
                              pan_x_end: 0,
                              pan_y_start: -12,
                              pan_y_end: 12,
                            });
                          } else if (preset === "diagonal_pan") {
                            updateSceneCamera({
                              preset: "diagonal_pan",
                              zoom_start: 1.2,
                              zoom_end: 1.2,
                              pan_x_start: -10,
                              pan_x_end: 10,
                              pan_y_start: -10,
                              pan_y_end: 10,
                            });
                          } else {
                            updateSceneCamera({ preset: "custom" });
                          }
                        }}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-100 font-medium"
                      >
                        <option value="static">Static (No Camera Move)</option>
                        <option value="slow_zoom_in">Slow Zoom In (1.0x → 1.25x)</option>
                        <option value="slow_zoom_out">Slow Zoom Out (1.25x → 1.0x)</option>
                        <option value="pan_left">Pan Left (Sweep across)</option>
                        <option value="pan_right">Pan Right (Sweep across)</option>
                        <option value="pan_up">Pan Up (Tilt upward)</option>
                        <option value="pan_down">Pan Down (Tilt downward)</option>
                        <option value="diagonal_pan">Diagonal Pan (Dynamic angle)</option>
                        <option value="custom">Custom Camera Movement</option>
                      </select>
                    </div>

                    {/* Camera Zoom Controls */}
                    <div className="space-y-2 pt-2 border-t border-zinc-800">
                      <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                        Camera Zoom Range
                      </h4>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="text-[10px] text-zinc-500 block">Start Zoom</label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              min="0.8"
                              max="2.5"
                              step="0.05"
                              value={selectedScene.camera?.zoom_start ?? 1.0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  zoom_start: parseFloat(e.target.value) || 1.0,
                                })
                              }
                              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs font-mono text-zinc-100"
                            />
                            <span className="text-[10px] text-zinc-500">x</span>
                          </div>
                        </div>
                        <div>
                          <label className="text-[10px] text-zinc-500 block">End Zoom</label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              min="0.8"
                              max="2.5"
                              step="0.05"
                              value={selectedScene.camera?.zoom_end ?? 1.0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  zoom_end: parseFloat(e.target.value) || 1.0,
                                })
                              }
                              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs font-mono text-zinc-100"
                            />
                            <span className="text-[10px] text-zinc-500">x</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Camera Pan Controls */}
                    <div className="space-y-2 pt-2 border-t border-zinc-800">
                      <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                        Camera Pan Range (%)
                      </h4>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <label className="text-[10px] text-zinc-500 block">Pan X: Start → End</label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              min="-50"
                              max="50"
                              step="2"
                              value={selectedScene.camera?.pan_x_start ?? 0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  pan_x_start: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-12 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-1 text-xs font-mono text-zinc-100 text-center"
                            />
                            <span className="text-zinc-600">→</span>
                            <input
                              type="number"
                              min="-50"
                              max="50"
                              step="2"
                              value={selectedScene.camera?.pan_x_end ?? 0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  pan_x_end: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-12 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-1 text-xs font-mono text-zinc-100 text-center"
                            />
                          </div>
                        </div>

                        <div>
                          <label className="text-[10px] text-zinc-500 block">Pan Y: Start → End</label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              min="-50"
                              max="50"
                              step="2"
                              value={selectedScene.camera?.pan_y_start ?? 0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  pan_y_start: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-12 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-1 text-xs font-mono text-zinc-100 text-center"
                            />
                            <span className="text-zinc-600">→</span>
                            <input
                              type="number"
                              min="-50"
                              max="50"
                              step="2"
                              value={selectedScene.camera?.pan_y_end ?? 0}
                              onChange={(e) =>
                                updateSceneCamera({
                                  preset: "custom",
                                  pan_y_end: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-12 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-1 text-xs font-mono text-zinc-100 text-center"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Camera Easing */}
                    <div className="space-y-1 pt-2 border-t border-zinc-800">
                      <label className="text-[11px] text-zinc-400 block">Camera Easing</label>
                      <select
                        value={selectedScene.camera?.easing || "ease_in_out"}
                        onChange={(e) =>
                          updateSceneCamera({ easing: e.target.value as AnimationEasing })
                        }
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
                      >
                        <option value="ease_in_out">Ease In-Out (Smooth Start/Stop)</option>
                        <option value="linear">Linear (Constant Speed)</option>
                        <option value="ease_in">Ease In (Accelerate)</option>
                        <option value="ease_out">Ease Out (Decelerate)</option>
                      </select>
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        updateSceneCamera({
                          preset: "static",
                          zoom_start: 1.0,
                          zoom_end: 1.0,
                          pan_x_start: 0,
                          pan_x_end: 0,
                          pan_y_start: 0,
                          pan_y_end: 0,
                        })
                      }
                      className="w-full text-xs h-7 mt-2"
                    >
                      Reset Camera to Static
                    </Button>
                  </div>
                )}

                {/* --- SUB-MODE C: KEYFRAMES --- */}
                {motionSubTab === "keyframes" && selectedLayer && (
                  <div className="space-y-3">
                    {/* Property Pills */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                          Keyframe Property
                        </h4>
                        <span className="text-[10px] font-mono text-indigo-400">
                          @{relativePlayheadSec.toFixed(2)}s
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-[11px]">
                        {(["scale", "x", "y", "rotation", "opacity", "blur"] as AnimatableProperty[]).map(
                          (prop) => {
                            const count =
                              selectedLayer?.animation_config?.tracks?.[prop]?.keyframes?.length || 0;
                            return (
                              <button
                                key={prop}
                                type="button"
                                onClick={() => setActiveKeyframeProperty(prop)}
                                className={`px-2 py-1 rounded capitalize border transition-all text-center flex items-center justify-between ${
                                  activeKeyframeProperty === prop
                                    ? "bg-indigo-600/30 border-indigo-500 text-indigo-300 font-bold"
                                    : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-white"
                                }`}
                              >
                                <span>{prop}</span>
                                {count > 0 && (
                                  <span className="w-4 h-4 rounded-full bg-amber-500/20 text-amber-300 text-[9px] flex items-center justify-center font-mono">
                                    {count}
                                  </span>
                                )}
                              </button>
                            );
                          }
                        )}
                      </div>
                    </div>

                    {/* Add Keyframe Button at Playhead */}
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleAddKeyframeAtPlayhead(activeKeyframeProperty)}
                      className="w-full text-xs h-8 text-amber-300 border-amber-800/60 hover:bg-amber-950/40"
                    >
                      <Icons.Plus className="w-3.5 h-3.5 mr-1 text-amber-400" />
                      + Keyframe at {relativePlayheadSec.toFixed(2)}s ({activeKeyframeProperty})
                    </Button>

                    {/* List of Existing Keyframes for this property */}
                    <div className="space-y-1.5 pt-2 border-t border-zinc-800">
                      <div className="flex items-center justify-between text-[11px] text-zinc-400">
                        <span>Time / Value</span>
                        <span>Easing / Del</span>
                      </div>

                      {(() => {
                        const keyframes =
                          selectedLayer.animation_config?.tracks?.[activeKeyframeProperty]
                            ?.keyframes || [];

                        if (keyframes.length === 0) {
                          return (
                            <div className="p-3 text-center text-xs text-zinc-500 bg-zinc-950 rounded border border-zinc-800/80">
                              No keyframes on <span className="font-mono text-zinc-400">{activeKeyframeProperty}</span> yet. Scrub playhead and click "+ Keyframe".
                            </div>
                          );
                        }

                        return keyframes.map((kf) => (
                          <div
                            key={kf.id}
                            className="flex items-center gap-1.5 p-1.5 rounded bg-zinc-950 border border-zinc-800 text-xs"
                          >
                            {/* Time input */}
                            <div className="flex items-center gap-0.5">
                              <input
                                type="number"
                                min="0"
                                max={layerDuration}
                                step="0.1"
                                value={kf.time_offset_sec}
                                onChange={(e) =>
                                  handleUpdateKeyframe(activeKeyframeProperty, kf.id, {
                                    time_offset_sec: Math.max(0, parseFloat(e.target.value) || 0),
                                  })
                                }
                                className="w-12 bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 font-mono text-[11px] text-right"
                              />
                              <span className="text-[10px] text-zinc-500 font-mono">s</span>
                            </div>

                            {/* Value input */}
                            <input
                              type="number"
                              step={activeKeyframeProperty === "scale" ? "0.05" : "1"}
                              value={kf.value}
                              onChange={(e) =>
                                handleUpdateKeyframe(activeKeyframeProperty, kf.id, {
                                  value: parseFloat(e.target.value) || 0,
                                })
                              }
                              className="w-14 bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 font-mono text-[11px] text-right"
                            />

                            {/* Easing */}
                            <select
                              value={kf.easing || "ease_in_out"}
                              onChange={(e) =>
                                handleUpdateKeyframe(activeKeyframeProperty, kf.id, {
                                  easing: e.target.value as AnimationEasing,
                                })
                              }
                              className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-[10px] text-zinc-300"
                            >
                              <option value="ease_in_out">Ease In-Out</option>
                              <option value="linear">Linear</option>
                              <option value="ease_in">Ease In</option>
                              <option value="ease_out">Ease Out</option>
                            </select>

                            {/* Delete button */}
                            <button
                              type="button"
                              onClick={() => handleDeleteKeyframe(activeKeyframeProperty, kf.id)}
                              className="p-1 text-zinc-500 hover:text-rose-400"
                              title="Delete Keyframe"
                            >
                              <Icons.Trash className="w-3 h-3" />
                            </button>
                          </div>
                        ));
                      })()}
                    </div>

                    {/* Copy / Paste row */}
                    <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCopyAnimation}
                        className="flex-1 text-xs h-7"
                      >
                        <Icons.Copy className="w-3 h-3 mr-1" />
                        Copy Tracks
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handlePasteAnimation}
                        disabled={!state.clipboard_animation}
                        className="flex-1 text-xs h-7"
                      >
                        <Icons.Layers className="w-3 h-3 mr-1" />
                        Paste Tracks
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Visual Effects */}
            {activeTab === "effects" && selectedLayer && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                    Comic Effects & Overlays
                  </h4>
                  <div className="space-y-1.5">
                    {[
                      { name: "Speed Lines & Motion Blur", preset: "blur" as const },
                      { name: "Impact Shake Effect", preset: "shake_impact" as const },
                      { name: "Dramatic Flash Impact", preset: "flash" as const },
                      { name: "Opacity Smooth Reveal", preset: "opacity_reveal" as const },
                    ].map((fx) => (
                      <button
                        key={fx.preset}
                        type="button"
                        onClick={() => {
                          updateSelectedLayer({ motion_preset: fx.preset });
                          updateLayerAnimationConfig((cfg) => ({ ...cfg, preset: fx.preset }));
                        }}
                        className={`w-full text-left p-2 rounded-lg border text-xs flex items-center justify-between transition-colors ${
                          selectedLayer.motion_preset === fx.preset
                            ? "bg-indigo-950 border-indigo-500 text-indigo-300 font-bold"
                            : "bg-zinc-950 border-zinc-800 hover:border-indigo-500 text-zinc-300"
                        }`}
                      >
                        <span>{fx.name}</span>
                        {selectedLayer.motion_preset === fx.preset ? (
                          <span className="text-[10px] bg-indigo-500 text-white px-1.5 py-0.5 rounded font-mono">
                            Active
                          </span>
                        ) : (
                          <Icons.Plus className="w-3.5 h-3.5 text-zinc-500" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: Timing & Scene Transitions */}
            {activeTab === "timing" && selectedScene && (
              <div className="space-y-4">
                {/* Scene Duration */}
                <div className="space-y-2">
                  <label className="text-xs text-zinc-300 block">Scene Total Duration</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="0.5"
                      max="30"
                      step="0.5"
                      value={selectedScene.duration_sec}
                      onChange={(e) =>
                        updateSelectedScene({
                          duration_sec: Math.max(0.5, parseFloat(e.target.value) || 1),
                        })
                      }
                      className="w-24 bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1 text-xs font-mono text-zinc-100"
                    />
                    <span className="text-xs text-zinc-400">seconds</span>
                  </div>
                </div>

                {/* Scene Transition Selector */}
                <div className="space-y-2 pt-2 border-t border-zinc-800">
                  <label className="text-xs text-zinc-300 block">Scene Entrance Transition</label>
                  <select
                    value={selectedScene.transition_in || "none"}
                    onChange={(e) =>
                      updateSelectedScene({
                        transition_in: e.target.value as SceneTransitionType,
                      })
                    }
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-200"
                  >
                    <option value="none">Direct Cut (None)</option>
                    <option value="fade_to_black">Fade to Black</option>
                    <option value="fade_from_black">Fade from Black</option>
                    <option value="dissolve">Cross Dissolve</option>
                    <option value="wipe_left">Wipe Left</option>
                    <option value="wipe_right">Wipe Right</option>
                    <option value="impact_flash">Impact Flash</option>
                  </select>

                  {/* Transition Duration */}
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[11px] text-zinc-400">Transition Duration</span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0.2"
                        max="2.0"
                        step="0.1"
                        value={selectedScene.transition_duration_sec ?? 0.5}
                        onChange={(e) =>
                          updateSelectedScene({
                            transition_duration_sec: Math.max(0.1, parseFloat(e.target.value) || 0.5),
                          })
                        }
                        className="w-16 bg-zinc-950 border border-zinc-800 rounded px-2 py-0.5 text-xs font-mono text-zinc-100 text-right"
                      />
                      <span className="text-[10px] text-zinc-500">s</span>
                    </div>
                  </div>
                </div>

                {/* Layer Timing (Relative to Scene) */}
                {selectedLayer && (
                  <div className="space-y-3 pt-3 border-t border-zinc-800">
                    <h4 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                      Layer Timing (Relative to Scene)
                    </h4>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[11px] text-zinc-400 block mb-1">Start Offset</label>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min="0"
                            max={selectedScene.duration_sec}
                            step="0.1"
                            value={selectedLayer.start_offset_sec ?? 0}
                            onChange={(e) =>
                              updateSelectedLayer({
                                start_offset_sec: Math.max(0, parseFloat(e.target.value) || 0),
                              })
                            }
                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs font-mono text-zinc-100"
                          />
                          <span className="text-[10px] text-zinc-500">s</span>
                        </div>
                      </div>
                      <div>
                        <label className="text-[11px] text-zinc-400 block mb-1">Duration</label>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min="0.4"
                            max={selectedScene.duration_sec}
                            step="0.1"
                            value={selectedLayer.duration_sec ?? selectedScene.duration_sec}
                            onChange={(e) =>
                              updateSelectedLayer({
                                duration_sec: Math.max(0.4, parseFloat(e.target.value) || 1),
                              })
                            }
                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs font-mono text-zinc-100"
                          />
                          <span className="text-[10px] text-zinc-500">s</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-48 text-zinc-500 text-center">
            <Icons.Sliders className="w-8 h-8 opacity-30 mb-2" />
            <p className="text-xs">Select a panel or clip to edit transform, motion, and effects.</p>
          </div>
        )}
      </div>
    </div>
  );
};
