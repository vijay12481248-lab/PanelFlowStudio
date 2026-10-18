import React, { useState, useEffect, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  Page,
  Panel,
  StoryEditorState,
  VideoScene,
  VisualLayer,
  NarrationClip,
} from "@panelflow/shared-types";
import { StoryEditorTopBar } from "../components/story-editor/StoryEditorTopBar";
import { StoryEditorLeftRail, LeftRailTab } from "../components/story-editor/StoryEditorLeftRail";
import { VideoCompositionCanvas } from "../components/story-editor/VideoCompositionCanvas";
import { SourcePageBrowser } from "../components/story-editor/SourcePageBrowser";
import { ContextualInspector, InspectorTab } from "../components/story-editor/ContextualInspector";
import { StoryEditorTimeline } from "../components/story-editor/StoryEditorTimeline";
import { WorkflowStepperRibbon, WorkflowStepId } from "../components/story-editor/WorkflowStepperRibbon";
import { NarrationStudio } from "../components/narration-studio/NarrationStudio";
import type { NarrationSegment } from "../components/narration-studio/NarrationStudio.types";
import {
  buildInitialNarrationChapter,
  syncChapterToTimelineClips,
  syncTimelineContractToState,
  rippleShiftLinkedNarration,
} from "../components/story-editor/narrationAdapter";
import { AudioLibrary } from "../components/audio-library";
import type { AudioToTimelineContract } from "../components/audio-library/AudioLibrary.types";
import { useTimelineAudioPlayback } from "../components/story-editor/useTimelineAudioPlayback";
import { applyAudioContractToState } from "../components/story-editor/audioAdapter";
import { ExportVideoModal } from "../components/story-editor/ExportVideoModal";

interface StoryEditorScreenProps {
  project: Project;
  onBack: () => void;
  onExport: () => void;
  initialTab?: LeftRailTab;
  initialWorkflowStep?: WorkflowStepId;
  initialOpenModal?: "narration" | "audio" | "export";
}

export const StoryEditorScreen: React.FC<StoryEditorScreenProps> = ({
  project,
  onBack,
  onExport,
  initialTab,
  initialWorkflowStep,
  initialOpenModal,
}) => {
  const [pages, setPages] = useState<Page[]>([]);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeLeftTab, setActiveLeftTab] = useState<LeftRailTab>(initialTab ?? "story");
  const [workflowStep, setWorkflowStep] = useState<WorkflowStepId>(initialWorkflowStep ?? 3);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("image");
  const [sourceSubTab, setSourceSubTab] = useState<"pages" | "panels">("pages");
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");
  const [showNarrationStudio, setShowNarrationStudio] = useState<boolean>(initialOpenModal === "narration");
  const [showAudioLibrary, setShowAudioLibrary] = useState<boolean>(initialOpenModal === "audio");
  const [audioLibraryInitialType, setAudioLibraryInitialType] = useState<"music" | "sfx" | undefined>(
    initialOpenModal === "audio" ? "music" : undefined
  );
  const [showExportModal, setShowExportModal] = useState<boolean>(initialOpenModal === "export");

  // Main Editor State
  const [editorState, setEditorState] = useState<StoryEditorState>({
    schema_version: 2,
    ripple_edit: true,
    project_id: project.id,
    aspect_ratio: "16:9",
    mode: "simple",
    scenes: [],
    narration_clips: [],
    bgm_tracks: [
      {
        id: "bgm_default",
        title: "Ambient Discovery (D-Minor)",
        file_url: "/assets/demo/crystal_resonance_bgm.mp3",
        volume: 0.6,
        start_time_sec: 0,
        duration_sec: 25,
        loop: true,
        ducking_enabled: true,
        ducking_amount_db: -12,
      },
    ],
    sfx_cues: [
      { id: "sfx_1", name: "Energy Burst", category: "magic", file_url: "/assets/demo/blade_shimmer_sfx.mp3", start_time_sec: 1.0, duration_sec: 2.2, volume: 0.8 },
      { id: "sfx_2", name: "Footsteps", category: "movement", file_url: "/assets/demo/blade_shimmer_sfx.mp3", start_time_sec: 7.5, duration_sec: 2.2, volume: 0.8 },
      { id: "sfx_3", name: "Magic Shimmer", category: "magic", file_url: "/assets/demo/blade_shimmer_sfx.mp3", start_time_sec: 14.0, duration_sec: 2.2, volume: 0.9 },
      { id: "sfx_4", name: "Whoosh", category: "transition", file_url: "/assets/demo/blade_shimmer_sfx.mp3", start_time_sec: 22.0, duration_sec: 2.2, volume: 0.8 },
    ],
    track_states: {
      Narration: { visible: true, locked: false },
      Visuals: { visible: true, locked: false },
      "Layer 2": { visible: true, locked: false },
      "Motion / FX": { visible: true, locked: false },
      Music: { visible: true, locked: false },
      SFX: { visible: true, locked: false },
    },
    selected_object: null,
    playhead_sec: 0,
    is_playing: false,
    zoom_level: 100,
  });

  // Synchronized Timeline HTML5 Audio Playback Hook
  useTimelineAudioPlayback(editorState);

  // Undo / Redo History Stacks
  const [history, setHistory] = useState<StoryEditorState[]>([]);
  const [future, setFuture] = useState<StoryEditorState[]>([]);

  // Update state with automatic undo tracking
  const updateEditorState = useCallback(
    (updater: (prev: StoryEditorState) => StoryEditorState) => {
      setEditorState((prev) => {
        const next = updater(prev);
        // Only push to history if meaningful state changed
        if (
          next.scenes !== prev.scenes ||
          next.narration_clips !== prev.narration_clips ||
          next.bgm_tracks !== prev.bgm_tracks ||
          next.sfx_cues !== prev.sfx_cues ||
          next.aspect_ratio !== prev.aspect_ratio ||
          next.mode !== prev.mode
        ) {
          setHistory((h) => [...h.slice(-40), prev]);
          setFuture([]);
          setSaveStatus("unsaved");
        }
        return next;
      });
    },
    []
  );

  const handleOpenAudioLibrary = (type?: "music" | "sfx") => {
    setAudioLibraryInitialType(type);
    setShowAudioLibrary(true);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setFuture((f) => [editorState, ...f]);
    setHistory((h) => h.slice(0, h.length - 1));
    setEditorState(previous);
  };

  const handleRedo = () => {
    if (future.length === 0) return;
    const next = future[0];
    setHistory((h) => [...h, editorState]);
    setFuture((f) => f.slice(1));
    setEditorState(next);
  };

  // Workflow step orchestrator
  const handleSelectWorkflowStep = (step: WorkflowStepId) => {
    setWorkflowStep(step);
    switch (step) {
      case 1: // Import Manga
        setActiveLeftTab("pages");
        setSourceSubTab("pages");
        break;
      case 2: // Select Panels
        setActiveLeftTab("pages");
        setSourceSubTab("panels");
        break;
      case 3: // Arrange Story
        setActiveLeftTab("story");
        break;
      case 4: // Edit Motion & Effects
        setActiveLeftTab("motion");
        setInspectorTab("motion");
        break;
      case 5: // Add Narration
        setActiveLeftTab("narration");
        setShowNarrationStudio(true);
        if (editorState.narration_clips.length > 0 && !editorState.selected_object) {
          updateEditorState((s) => ({
            ...s,
            selected_object: { type: "narration", id: s.narration_clips[0].id },
          }));
        }
        break;
      case 6: // Add Music & SFX
        setActiveLeftTab("audio");
        handleOpenAudioLibrary();
        break;
      case 7: // Preview & Export
        setShowExportModal(true);
        break;
    }
  };

  // Synchronize left rail navigation with workflow ribbon
  const handleLeftRailSelect = (tab: LeftRailTab) => {
    setActiveLeftTab(tab);
    if (tab === "pages") {
      setSourceSubTab("pages");
      setWorkflowStep(sourceSubTab === "panels" ? 2 : 1);
    } else if (tab === "story") {
      setWorkflowStep(3);
    } else if (tab === "motion") {
      setWorkflowStep(4);
      setInspectorTab("motion");
    } else if (tab === "narration") {
      setWorkflowStep(5);
      setShowNarrationStudio(true);
    } else if (tab === "audio") {
      setWorkflowStep(6);
      handleOpenAudioLibrary();
    }
  };

  // Global Editor Keyboard Shortcuts (Space: Play/Pause, Ctrl+Z: Undo, Ctrl+Y: Redo)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        if (e.shiftKey) {
          handleRedo();
        } else {
          handleUndo();
        }
        e.preventDefault();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        handleRedo();
        e.preventDefault();
      } else if (e.code === "Space") {
        updateEditorState((prev) => ({ ...prev, is_playing: !prev.is_playing }));
        e.preventDefault();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [history.length, future.length, editorState.is_playing, updateEditorState]);

  // Real autosave to localStorage
  useEffect(() => {
    if (saveStatus !== "unsaved") return;
    const timer = setTimeout(() => {
      setSaveStatus("saving");
      try {
        localStorage.setItem(`panelflow_story_editor_${project.id}`, JSON.stringify(editorState));
      } catch (err) {
        console.warn("Failed to persist editor state:", err);
      }
      setTimeout(() => {
        setSaveStatus("saved");
      }, 400);
    }, 1000);
    return () => clearTimeout(timer);
  }, [saveStatus, editorState, project.id]);

  // Load project assets and initialize story scenes
  useEffect(() => {
    let mounted = true;
    const loadProjectData = async () => {
      try {
        setLoading(true);
        const [loadedPages, loadedPanels] = await Promise.all([
          api.listPages(project.id).catch(() => []),
          api.listPanels(project.id).catch(() => []),
        ]);

        if (!mounted) return;
        setPages(loadedPages);
        setPanels(loadedPanels);

        if (loadedPages.length > 0) {
          setSelectedPageId(loadedPages[0].id);
        }

        // Restore saved editor state from localStorage if it exists with Schema v2 migration
        const storageKey = `panelflow_story_editor_${project.id}`;
        const savedData = localStorage.getItem(storageKey);
        if (savedData) {
          try {
            const parsed = JSON.parse(savedData) as StoryEditorState;
            if (parsed && Array.isArray(parsed.scenes) && parsed.scenes.length > 0) {
              const migratedScenes = parsed.scenes.map((sc, scIdx) => ({
                ...sc,
                sequence: sc.sequence || scIdx + 1,
                transition_in: sc.transition_in || "none",
                transition_duration_sec: sc.transition_duration_sec ?? 0.5,
                camera: sc.camera || {
                  id: `cam_${sc.id}`,
                  preset: "static",
                  zoom_start: 1.0,
                  zoom_end: 1.0,
                  pan_x_start: 0,
                  pan_x_end: 0,
                  pan_y_start: 0,
                  pan_y_end: 0,
                  easing: "ease_in_out",
                  duration_sec: sc.duration_sec,
                },
                layers: (sc.layers || []).map((ly) => ({
                  ...ly,
                  start_offset_sec: ly.start_offset_sec ?? 0,
                  duration_sec: ly.duration_sec ?? sc.duration_sec,
                })),
              }));

              const restoredChapter = parsed.narration_chapter || buildInitialNarrationChapter(project.id, project.title, migratedScenes);
              const migratedNarration = (parsed.narration_clips && parsed.narration_clips.length > 0)
                ? parsed.narration_clips.map((n) => ({
                    ...n,
                    linked_to_scene: n.linked_to_scene ?? true,
                  }))
                : syncChapterToTimelineClips(restoredChapter, migratedScenes);

              setEditorState({
                ...parsed,
                schema_version: 2,
                ripple_edit: parsed.ripple_edit ?? true,
                scenes: migratedScenes,
                narration_chapter: restoredChapter,
                narration_clips: migratedNarration,
              });
              return;
            }
          } catch (e) {
            console.warn("Failed to parse saved editor state:", e);
          }
        }

        // Initialize default video scenes from detected panels or seed starter scene
        if (loadedPanels.length > 0) {
          let runningTime = 0;
          const initialScenes: VideoScene[] = [];

          // Group panels into sequential storytelling scenes (first 6 panels as initial scenes)
          const seedPanels = loadedPanels.slice(0, 6);
          seedPanels.forEach((panel: Panel, idx: number) => {
            const page = loadedPages.find((p: Page) => p.id === panel.page_id);
            const duration = 4.0;

            const layer: VisualLayer = {
              id: `layer_${panel.id}`,
              source_page_id: panel.page_id,
              source_panel_id: panel.id,
              image_url: api.getPageImageUrl(project.id, panel.page_id),
              page_sequence: panel.page_sequence,
              crop: {
                x: panel.x,
                y: panel.y,
                width: panel.width,
                height: panel.height,
              },
              transform: {
                x: 0,
                y: 0,
                scale: 1.0,
                rotation: 0,
                opacity: 1.0,
                z_index: 1,
              },
              motion_preset: idx % 2 === 0 ? "slow_zoom_in" : "pan_right",
              motion_duration_sec: duration,
              start_offset_sec: 0,
              duration_sec: duration,
              name: `Panel #${panel.page_sequence}`,
            };

            const sceneId = `scene_${panel.id}`;
            initialScenes.push({
              id: sceneId,
              sequence: idx + 1,
              title: `Scene ${idx + 1} — Panel #${panel.page_sequence}`,
              duration_sec: duration,
              start_time_sec: runningTime,
              layers: [layer],
              transition_in: idx === 0 ? "fade_from_black" : "none",
              transition_duration_sec: 0.5,
              camera: {
                id: `cam_${sceneId}`,
                preset: "static",
                zoom_start: 1.0,
                zoom_end: 1.0,
                pan_x_start: 0,
                pan_x_end: 0,
                pan_y_start: 0,
                pan_y_end: 0,
                easing: "ease_in_out",
                duration_sec: duration,
              },
            });

            runningTime += duration;
          });

          const initialChapter = buildInitialNarrationChapter(project.id, project.title, initialScenes);
          const initialNarration = syncChapterToTimelineClips(initialChapter, initialScenes);

          setEditorState((prev) => {
            const initialEditorState: StoryEditorState = {
              ...prev,
              scenes: initialScenes,
              narration_chapter: initialChapter,
              narration_clips: initialNarration,
              selected_object: initialScenes.length > 0 ? { type: "scene", id: initialScenes[0].id } : null,
            };

            try {
              localStorage.setItem(
                `panelflow_story_editor_${project.id}`,
                JSON.stringify(initialEditorState)
              );
            } catch (e) {
              console.warn("Failed to save initial state:", e);
            }

            return initialEditorState;
          });
        } else if (loadedPages.length > 0) {
          // If no detected panels yet, seed 1 initial scene using page 1
          const firstPage = loadedPages[0];
          const initialLayer: VisualLayer = {
            id: `layer_page_${firstPage.id}`,
            source_page_id: firstPage.id,
            image_url: api.getPageImageUrl(project.id, firstPage.id),
            page_sequence: firstPage.sequence,
            crop: { x: 0, y: 0, width: firstPage.width || 1200, height: firstPage.height || 1800 },
            transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
            motion_preset: "slow_zoom_in",
            name: `Page 1 Opening`,
          };

          const initialScene: VideoScene = {
            id: "scene_initial_1",
            sequence: 1,
            title: "Scene 1 — Opening",
            duration_sec: 5.0,
            start_time_sec: 0,
            layers: [initialLayer],
            transition_in: "fade",
          };

          const initialChapter = buildInitialNarrationChapter(project.id, project.title, [initialScene]);
          const initialNarration = syncChapterToTimelineClips(initialChapter, [initialScene]);

          setEditorState((prev) => ({
            ...prev,
            scenes: [initialScene],
            narration_chapter: initialChapter,
            narration_clips: initialNarration,
            selected_object: { type: "scene", id: initialScene.id },
          }));
        }
      } catch (err) {
        console.error("Failed to load project editor data:", err);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadProjectData();
    return () => {
      mounted = false;
    };
  }, [project.id]);

  // Handler: Add panel to current scene or as a new scene
  const handleAddPanelToScene = (
    page: Page,
    panel: Panel | null,
    customCrop?: { x: number; y: number; width: number; height: number },
    asNewScene: boolean = false
  ) => {
    const crop = customCrop || (panel
      ? { x: panel.x, y: panel.y, width: panel.width, height: panel.height }
      : { x: 0, y: 0, width: page.width || 1200, height: Math.min(page.height || 1800, 1400) });

    const newLayerId = `layer_${Date.now()}`;
    const newLayer: VisualLayer = {
      id: newLayerId,
      source_page_id: page.id,
      source_panel_id: panel?.id,
      image_url: api.getPageImageUrl(project.id, page.id),
      page_sequence: page.sequence,
      crop,
      transform: {
        x: 0,
        y: 0,
        scale: 1.0,
        rotation: 0,
        opacity: 1.0,
        z_index: 1,
      },
      motion_preset: "slow_zoom_in",
      name: panel ? `Panel #${panel.page_sequence}` : `Page #${page.sequence} Region`,
    };

    if (asNewScene || editorState.scenes.length === 0) {
      // Append as new scene
      const newSceneId = `scene_${Date.now()}`;
      const totalDuration = editorState.scenes.reduce((acc, s) => acc + s.duration_sec, 0);

      updateEditorState((prev) => ({
        ...prev,
        scenes: [
          ...prev.scenes,
          {
            id: newSceneId,
            sequence: prev.scenes.length + 1,
            title: `Scene ${prev.scenes.length + 1} — ${newLayer.name}`,
            duration_sec: 4.0,
            start_time_sec: totalDuration,
            layers: [newLayer],
            transition_in: "none",
          },
        ],
        selected_object: { type: "layer", id: newLayerId, sceneId: newSceneId },
        playhead_sec: totalDuration,
      }));
    } else {
      // Add as layer into currently selected or active scene
      const activeSceneId =
        editorState.selected_object?.type === "scene"
          ? editorState.selected_object.id
          : editorState.selected_object?.type === "layer"
          ? editorState.selected_object.sceneId
          : editorState.scenes[0].id;

      updateEditorState((prev) => ({
        ...prev,
        scenes: prev.scenes.map((sc) => {
          if (sc.id !== activeSceneId) return sc;
          const nextZ = sc.layers.length + 1;
          return {
            ...sc,
            layers: [...sc.layers, { ...newLayer, transform: { ...newLayer.transform, z_index: nextZ } }],
          };
        }),
        selected_object: { type: "layer", id: newLayerId, sceneId: activeSceneId },
      }));
    }
  };

  // Handler: Add blank scene
  const handleAddBlankScene = () => {
    const newSceneId = `scene_${Date.now()}`;
    const totalDuration = editorState.scenes.reduce((acc, s) => acc + s.duration_sec, 0);

    updateEditorState((prev) => ({
      ...prev,
      scenes: [
        ...prev.scenes,
        {
          id: newSceneId,
          sequence: prev.scenes.length + 1,
          title: `Scene ${prev.scenes.length + 1}`,
          duration_sec: 3.5,
          start_time_sec: totalDuration,
          layers: [],
          transition_in: "none",
        },
      ],
      selected_object: { type: "scene", id: newSceneId },
      playhead_sec: totalDuration,
    }));
  };

  // Handler: Split scene at playhead
  const handleSplitScene = (sceneId: string, atSec: number) => {
    const sceneIdx = editorState.scenes.findIndex((s) => s.id === sceneId);
    if (sceneIdx < 0) return;

    const targetScene = editorState.scenes[sceneIdx];
    const splitPointInScene = atSec - targetScene.start_time_sec;

    if (splitPointInScene <= 0.5 || splitPointInScene >= targetScene.duration_sec - 0.5) {
      alert("Position playhead inside the scene to split.");
      return;
    }

    const firstDuration = Math.round(splitPointInScene * 10) / 10;
    const secondDuration = Math.round((targetScene.duration_sec - splitPointInScene) * 10) / 10;

    const secondSceneId = `scene_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const secondScene: VideoScene = {
      ...targetScene,
      id: secondSceneId,
      sequence: targetScene.sequence + 1,
      title: `${targetScene.title} (Part 2)`,
      duration_sec: secondDuration,
      start_time_sec: targetScene.start_time_sec + firstDuration,
      layers: targetScene.layers.map((l, i) => ({
        ...l,
        id: `layer_${Date.now()}_${i}_${Math.random().toString(36).substring(2, 7)}`,
      })),
    };

    updateEditorState((prev) => {
      const updatedScenes = [...prev.scenes];
      updatedScenes[sceneIdx] = {
        ...targetScene,
        duration_sec: firstDuration,
      };
      updatedScenes.splice(sceneIdx + 1, 0, secondScene);

      let running = 0;
      const resyncedScenes = updatedScenes.map((sc, idx) => {
        const s = { ...sc, sequence: idx + 1, start_time_sec: running };
        running += sc.duration_sec;
        return s;
      });

      const resyncedClips = rippleShiftLinkedNarration(resyncedScenes, prev.narration_clips);

      return {
        ...prev,
        scenes: resyncedScenes,
        narration_clips: resyncedClips,
        selected_object: { type: "scene", id: secondSceneId },
      };
    });
  };

  // Handler: Duplicate scene
  const handleDuplicateScene = (sceneId: string) => {
    const scene = editorState.scenes.find((s) => s.id === sceneId);
    if (!scene) return;

    const dupSceneId = `scene_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const dupScene: VideoScene = {
      ...scene,
      id: dupSceneId,
      sequence: scene.sequence + 1,
      title: `${scene.title} (Copy)`,
      layers: scene.layers.map((l, i) => ({
        ...l,
        id: `layer_${Date.now()}_${i}_${Math.random().toString(36).substring(2, 7)}`,
      })),
    };

    updateEditorState((prev) => {
      const idx = prev.scenes.findIndex((s) => s.id === sceneId);
      const copy = [...prev.scenes];
      copy.splice(idx + 1, 0, dupScene);

      let running = 0;
      const resyncedScenes = copy.map((sc, i) => {
        const s = { ...sc, sequence: i + 1, start_time_sec: running };
        running += sc.duration_sec;
        return s;
      });

      const resyncedClips = rippleShiftLinkedNarration(resyncedScenes, prev.narration_clips);

      return {
        ...prev,
        scenes: resyncedScenes,
        narration_clips: resyncedClips,
        selected_object: { type: "scene", id: dupSceneId },
      };
    });
  };

  // Handler: Delete scene
  const handleDeleteScene = (sceneId: string) => {
    if (editorState.scenes.length <= 1) {
      alert("At least one scene must remain in the story editor.");
      return;
    }
    updateEditorState((prev) => {
      let running = 0;
      const remainingScenes = prev.scenes
        .filter((s) => s.id !== sceneId)
        .map((sc, idx) => {
          const s = { ...sc, sequence: idx + 1, start_time_sec: running };
          running += sc.duration_sec;
          return s;
        });

      // Orphaned narration safety: unbind clips linked to the deleted scene so they become floating unlinked audio
      const preservedClips = prev.narration_clips.map((clip) => {
        if (clip.scene_id === sceneId) {
          return {
            ...clip,
            linked_to_scene: false,
          };
        }
        return clip;
      });

      const resyncedClips = rippleShiftLinkedNarration(remainingScenes, preservedClips);

      let updatedChapter = prev.narration_chapter;
      if (updatedChapter) {
        updatedChapter = {
          ...updatedChapter,
          segments: updatedChapter.segments.map((seg: NarrationSegment) => {
            if (seg.scene_id === sceneId) {
              return {
                ...seg,
                linked_to_scene: false,
              };
            }
            return seg;
          }),
        };
      }

      return {
        ...prev,
        scenes: remainingScenes,
        narration_chapter: updatedChapter,
        narration_clips: resyncedClips,
        selected_object: null,
      };
    });
  };

  // Handler: Delete layer
  const handleDeleteLayer = (layerId: string, sceneId: string) => {
    updateEditorState((prev) => ({
      ...prev,
      scenes: prev.scenes.map((sc) => {
        if (sc.id !== sceneId) return sc;
        return {
          ...sc,
          layers: sc.layers.filter((l) => l.id !== layerId),
        };
      }),
      selected_object: { type: "scene", id: sceneId },
    }));
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-zinc-950 text-zinc-100 overflow-hidden font-sans">
      {/* 1. Top Bar */}
      <StoryEditorTopBar
        project={project}
        state={editorState}
        onUpdateState={updateEditorState}
        canUndo={history.length > 0}
        canRedo={future.length > 0}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onBackToDashboard={onBack}
        onExportClick={() => setShowExportModal(true)}
        saveStatus={saveStatus}
        onOpenNarrationStudio={() => setShowNarrationStudio(true)}
        onOpenAudioLibrary={() => handleOpenAudioLibrary()}
      />

      {/* 2. Middle Main Workspace (Left Rail + Central Player + Right Panels) */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left Narrow Rail */}
        <StoryEditorLeftRail
          activeTab={activeLeftTab}
          onSelectTab={handleLeftRailSelect}
        />

        {/* Center: 16:9 Composition Canvas */}
        <VideoCompositionCanvas
          state={editorState}
          onUpdateState={updateEditorState}
          onSelectLayer={(layerId, sceneId) => {
            updateEditorState((s) => ({
              ...s,
              selected_object: { type: "layer", id: layerId, sceneId },
            }));
          }}
        />

        {/* Right Split: Source Manga Browser (top) & Contextual Inspector (bottom) */}
        <div className="w-96 flex flex-col border-l border-zinc-800 bg-zinc-900 shrink-0 overflow-hidden">
          {/* Upper Half: Manga Source Browser & Panel Selection */}
          <div className="h-1/2 overflow-hidden border-b border-zinc-800 flex flex-col min-h-0">
            <SourcePageBrowser
              projectId={project.id}
              pages={pages}
              panels={panels}
              selectedPageId={selectedPageId}
              onSelectPage={(pageId) => setSelectedPageId(pageId)}
              selectedPanelId={selectedPanelId}
              onSelectPanel={(panel) => setSelectedPanelId(panel?.id || null)}
              onAddPanelToScene={handleAddPanelToScene}
              activeSubTab={sourceSubTab}
              onSubTabChange={setSourceSubTab}
            />
          </div>

          {/* Lower Half: Contextual Inspector */}
          <div className="h-1/2 overflow-hidden flex flex-col min-h-0">
            <ContextualInspector
              state={editorState}
              onUpdateState={updateEditorState}
              onDeleteLayer={handleDeleteLayer}
              onDeleteScene={handleDeleteScene}
              activeTab={inspectorTab}
              onSelectTab={setInspectorTab}
              onOpenNarrationStudio={(segmentId) => {
                if (segmentId) {
                  updateEditorState((s) => ({
                    ...s,
                    selected_object: { type: "narration", id: segmentId },
                  }));
                }
                setShowNarrationStudio(true);
              }}
              onOpenAudioLibrary={handleOpenAudioLibrary}
            />
          </div>
        </div>
      </div>

      {/* 3. Bottom Timeline */}
      <StoryEditorTimeline
        state={editorState}
        onUpdateState={updateEditorState}
        canUndo={history.length > 0}
        canRedo={future.length > 0}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onSelectScene={(sceneId) => {
          updateEditorState((s) => ({
            ...s,
            selected_object: { type: "scene", id: sceneId },
          }));
        }}
        onSelectLayer={(layerId, sceneId) => {
          updateEditorState((s) => ({
            ...s,
            selected_object: { type: "layer", id: layerId, sceneId },
          }));
        }}
        onSelectMotionBadge={(sceneId, layerId) => {
          updateEditorState((s) => ({
            ...s,
            selected_object: layerId ? { type: "layer", id: layerId, sceneId } : { type: "scene", id: sceneId },
          }));
          setInspectorTab("motion");
        }}
        onOpenNarrationStudio={(segmentId) => {
          if (segmentId) {
            updateEditorState((s) => ({
              ...s,
              selected_object: { type: "narration", id: segmentId },
            }));
          }
          setShowNarrationStudio(true);
        }}
        onOpenAudioLibrary={handleOpenAudioLibrary}
        onAddBlankScene={handleAddBlankScene}
        onSplitScene={handleSplitScene}
        onDuplicateScene={handleDuplicateScene}
        onDeleteScene={handleDeleteScene}
      />

      {/* 4. Bottom 7-Step Workflow Ribbon */}
      <WorkflowStepperRibbon
        currentStep={workflowStep}
        onSelectStep={handleSelectWorkflowStep}
      />

      {/* 5. Full-Screen Narration Studio Workspace Overlay */}
      {showNarrationStudio && (
        <div className="fixed inset-0 z-50 bg-zinc-950 flex flex-col">
          <NarrationStudio
            initialChapter={
              editorState.narration_chapter ||
              buildInitialNarrationChapter(project.id, project.title, editorState.scenes)
            }
            initialSegmentId={
              editorState.selected_object?.type === "narration"
                ? editorState.selected_object.id
                : editorState.selected_object?.type === "scene"
                ? editorState.narration_clips.find((c) => c.scene_id === editorState.selected_object?.id)?.id
                : undefined
            }
            onClose={() => setShowNarrationStudio(false)}
            onChapterSave={(updatedChapter) => {
              updateEditorState((prev) => {
                const syncedClips = syncChapterToTimelineClips(
                  updatedChapter,
                  prev.scenes,
                  prev.narration_clips
                );
                return {
                  ...prev,
                  narration_chapter: updatedChapter,
                  narration_clips: syncedClips,
                };
              });
            }}
            onExportTimelineContract={(contract) => {
              updateEditorState((prev) => {
                const syncedClips = syncTimelineContractToState(
                  contract,
                  prev.scenes,
                  prev.narration_clips
                );
                return {
                  ...prev,
                  narration_clips: syncedClips,
                };
              });
              setShowNarrationStudio(false);
            }}
          />
        </div>
      )}

      {/* 6. Full-Screen Audio Library Workspace Overlay */}
      {showAudioLibrary && (
        <div className="fixed inset-0 z-50 bg-zinc-950 flex flex-col">
          <AudioLibrary
            projectId={project?.id}
            initialType={audioLibraryInitialType}
            onClose={() => setShowAudioLibrary(false)}
            onSendToTimeline={(contract: AudioToTimelineContract) => {
              updateEditorState((prev) => applyAudioContractToState(prev, contract));
              setShowAudioLibrary(false);
            }}
          />
        </div>
      )}

      {/* 7. Full Production Video Export Modal (Chapter 8) */}
      <ExportVideoModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        project={project}
        editorState={editorState}
        onOpenNarrationStudio={() => setShowNarrationStudio(true)}
      />
    </div>
  );
};
