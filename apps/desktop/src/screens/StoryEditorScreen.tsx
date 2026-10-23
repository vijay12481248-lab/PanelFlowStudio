import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@panelflow/api-client";
import { Icons } from "@panelflow/ui";
import type {
  Project,
  Page,
  Panel,
  StoryEditorState,
  VideoScene,
  VisualLayer,
  NarrationClip,
  TextRegion,
  ProjectHistoryState,
} from "@panelflow/shared-types";
import { StoryEditorTopBar } from "../components/story-editor/StoryEditorTopBar";
import { StoryEditorLeftRail, LeftRailTab } from "../components/story-editor/StoryEditorLeftRail";
import { VideoCompositionCanvas } from "../components/story-editor/VideoCompositionCanvas";
import { SourcePageBrowser } from "../components/story-editor/SourcePageBrowser";
import { SourceSetupCanvas } from "../components/story-editor/SourceSetupCanvas";
import type { SetupDraft } from "../components/story-editor/SourceSetupCanvas";
import { ContextualInspector, InspectorTab } from "../components/story-editor/ContextualInspector";
import { StoryEditorTimeline } from "../components/story-editor/StoryEditorTimeline";
import { useError } from "../context/ErrorContext";
import { WorkflowStepperRibbon, WorkflowStepId } from "../components/story-editor/WorkflowStepperRibbon";
import { NarrationStudio } from "../components/narration-studio/NarrationStudio";
import type { NarrationSegment } from "../components/narration-studio/NarrationStudio.types";
import {
  buildInitialNarrationChapter,
  syncChapterToTimelineClips,
  syncTimelineContractToState,
} from "../components/story-editor/narrationAdapter";
import { AudioLibrary } from "../components/audio-library";
import type { AudioToTimelineContract } from "../components/audio-library/AudioLibrary.types";
import { useTimelineAudioPlayback } from "../components/story-editor/useTimelineAudioPlayback";
import { applyAudioContractToState, deleteAudioClip } from "../components/story-editor/audioAdapter";
import { ExportVideoModal } from "../components/story-editor/ExportVideoModal";
import { EngineJobStatus } from "../components/JobActivityPanel";
import { createEmptyEditorState } from "../components/story-editor/editorWorkspace";
import { resolveSceneTiming, sceneTimelineDuration, reconcileSceneDurationEdit, alignLinkedNarration, packSceneTiming, insertSceneTiming } from "../components/story-editor/sceneTiming";
import { createDebouncedSaveQueue } from "../components/story-editor/editorSaveQueue";
import { EditorSettingsDialog } from "../components/story-editor/EditorSettingsDialog";
import { historyShortcut } from "../history/shortcuts";
import "../components/story-editor/motion-editor.css";

interface StoryEditorScreenProps {
  project: Project;
  onBack: () => void;
  onExport: () => void;
  engineConnected?: boolean;
  initialTab?: LeftRailTab;
  initialWorkflowStep?: WorkflowStepId;
  initialOpenModal?: "narration" | "audio" | "export";
}

export const StoryEditorScreen: React.FC<StoryEditorScreenProps> = ({
  project,
  onBack,
  onExport,
  engineConnected,
  initialTab,
  initialWorkflowStep,
  initialOpenModal,
}) => {
  const [pages, setPages] = useState<Page[]>([]);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [textRegions, setTextRegions] = useState<TextRegion[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveQueueRef = useRef<ReturnType<typeof createDebouncedSaveQueue<StoryEditorState>> | null>(null);
  // Engine & job status — integrates EngineJobStatus into toolbar
  const { engineHealthy, jobs, cancelJob: cancelJobContext } = useError();
  const [showEditorSettings, setShowEditorSettings] = useState(false);
  const [activeLeftTab, setActiveLeftTab] = useState<LeftRailTab>(initialTab ?? "story");
  const [workflowStep, setWorkflowStep] = useState<WorkflowStepId>(initialWorkflowStep ?? 3);
  const [rightSidebarTab, setRightSidebarTab] = useState<"source" | "inspector">("source");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("image");
  const [sourceSubTab, setSourceSubTab] = useState<"pages" | "panels">("pages");
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);
  const [canvasMode, setCanvasMode] = useState<"setup" | "player">("player");
  const [setupSourcesOpen, setSetupSourcesOpen] = useState(false);
  const [setupTimelineOpen, setSetupTimelineOpen] = useState(false);
  const setupDrafts = useRef<Record<string, SetupDraft>>({});
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");
  const [showNarrationStudio, setShowNarrationStudio] = useState<boolean>(initialOpenModal === "narration");
  const [showAudioLibrary, setShowAudioLibrary] = useState<boolean>(initialOpenModal === "audio");
  const [audioLibraryInitialType, setAudioLibraryInitialType] = useState<"music" | "sfx" | undefined>(
    initialOpenModal === "audio" ? "music" : undefined
  );
  const [showExportModal, setShowExportModal] = useState<boolean>(initialOpenModal === "export");
  const [panelSyncAlert, setPanelSyncAlert] = useState<{ show: boolean; message: string; removedCount?: number }>({ show: false, message: "" });

  // Main Editor State
  const [editorState, setEditorState] = useState<StoryEditorState>(() => createEmptyEditorState(project.id));

  // All playback entry points (timeline, Space, and source auto-play) use Player.
  useEffect(() => {
    if (editorState.is_playing) setCanvasMode("player");
  }, [editorState.is_playing]);

  // Synchronized Timeline HTML5 Audio Playback Hook
  useTimelineAudioPlayback(project.id, editorState);

  // The engine owns saved history. Selector drafts have their own child scope.
  const [projectHistory, setProjectHistory] = useState<ProjectHistoryState | null>(null);
  const [historyBusy, setHistoryBusy] = useState(false);
  const historyAction = useRef(false);

  // Update state with automatic undo tracking
  const updateEditorState = useCallback(
    (updater: (prev: StoryEditorState) => StoryEditorState) => {
      setEditorState((prev) => {
        // An undo/redo response is authoritative. Do not let incidental UI
        // events (playback, focus, or selection changes) replace its state
        // while it is being applied.
        if (historyAction.current) return prev;
        const next = reconcileSceneDurationEdit(prev, updater(prev));
        // Only push to history if meaningful state changed
        if (
          next.scenes !== prev.scenes ||
          next.narration_clips !== prev.narration_clips ||
          next.narration_chapter !== prev.narration_chapter ||
          next.bgm_tracks !== prev.bgm_tracks ||
          next.sfx_cues !== prev.sfx_cues ||
          next.aspect_ratio !== prev.aspect_ratio ||
          next.background_default !== prev.background_default ||
          next.canvas_width !== prev.canvas_width ||
          next.canvas_height !== prev.canvas_height ||
          next.mode !== prev.mode ||
          next.track_states !== prev.track_states ||
          next.zoom_level !== prev.zoom_level ||
          next.snapping !== prev.snapping ||
          next.ripple_edit !== prev.ripple_edit ||
          next.show_motion_paths !== prev.show_motion_paths ||
          next.clipboard_animation !== prev.clipboard_animation
        ) {
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

  const applyHistoryReply = (reply: { state: StoryEditorState | null; history: ProjectHistoryState }) => {
    const restored = { ...createEmptyEditorState(project.id), ...reply.state, is_playing: false };
    setEditorState(restored); setProjectHistory(reply.history); setSaveStatus("saved"); setSaveError(null);
    try { localStorage.setItem(`panelflow_story_editor_${project.id}`, JSON.stringify(api.sanitizeStoryEditorState(project.id, restored))); }
    catch { /* Engine transaction is authoritative. */ }
  };

  const moveHistory = async (direction: "undo" | "redo") => {
    if (historyAction.current || loading || showNarrationStudio || showAudioLibrary) return;
    historyAction.current = true; setHistoryBusy(true);
    try {
      if (await saveQueueRef.current?.flush() === false) return;
      const known = api.getCachedProjectHistory(project.id);
      if (known && !(direction === "undo" ? known.canUndo : known.canRedo)) { setProjectHistory(known); return; }
      applyHistoryReply(await api.moveProjectHistory(project.id, direction));
    } catch (error) {
      setProjectHistory(api.getCachedProjectHistory(project.id));
      setSaveError(error instanceof Error ? error.message : "Could not restore saved history. Reload the project before retrying.");
    } finally { historyAction.current = false; setHistoryBusy(false); }
  };
  const handleUndo = () => { void moveHistory("undo"); };
  const handleRedo = () => { void moveHistory("redo"); };
  const canUndo = !historyBusy && !loading && !projectHistory?.conflicted && !projectHistory?.recoveryRequired && (saveStatus !== "saved" || !!projectHistory?.canUndo);
  const canRedo = !historyBusy && !loading && saveStatus === "saved" && !!projectHistory?.canRedo;

  const startFreshHistory = async () => {
    if (historyAction.current || !window.confirm("Reload the saved project, discard local unsaved edits, and archive the old undo history?")) return;
    historyAction.current = true; setHistoryBusy(true);
    try {
      await saveQueueRef.current?.discardPending();
      const canonical = await api.getProjectHistory(project.id);
      applyHistoryReply(await api.resetProjectHistory(project.id, canonical.history.fingerprint));
    } catch (error) { setSaveError(error instanceof Error ? error.message : "History recovery failed; no local edits were saved."); }
    finally { historyAction.current = false; setHistoryBusy(false); }
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
    } else if (tab === "settings") {
      setShowEditorSettings(true);
    }
  };

  // Global Editor Keyboard Shortcuts (Space: Play/Pause, Ctrl+Z: Undo, Ctrl+Y: Redo)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        e.defaultPrevented ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
        target.isContentEditable || target.closest?.("[role=dialog], dialog")
      ) {
        return;
      }

      const action = historyShortcut(e);
      if (action) {
        if (action === "undo") handleUndo(); else handleRedo();
        e.preventDefault();
      } else if (e.code === "Space") {
        updateEditorState((prev) => ({ ...prev, is_playing: !prev.is_playing }));
        e.preventDefault();
      } else if (e.code === "Delete" || e.code === "Backspace") {
        if (editorState.selected_object?.type === "scene") {
          handleDeleteScene(editorState.selected_object.id);
          e.preventDefault();
        } else if (editorState.selected_object?.type === "layer") {
          const { id: layerId, sceneId } = editorState.selected_object;
          if (sceneId) handleDeleteLayer(layerId, sceneId);
          e.preventDefault();
        } else if (editorState.selected_object?.type === "bgm" || editorState.selected_object?.type === "sfx") {
          const audioType = editorState.selected_object.type;
          const audioId = editorState.selected_object.id;
          updateEditorState((prev) => deleteAudioClip(prev, audioId, audioType));
          e.preventDefault();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [projectHistory, historyBusy, loading, showNarrationStudio, showAudioLibrary, editorState.is_playing, updateEditorState]);

  useEffect(() => {
    const queue = createDebouncedSaveQueue<StoryEditorState>(async (snapshot) => {
      try {
        const response = await api.saveStoryEditorState(project.id, snapshot);
        setProjectHistory(response?.history ?? api.getCachedProjectHistory(project.id));
      } catch (error) {
        setProjectHistory(api.getCachedProjectHistory(project.id));
        throw error;
      }
      finally {
        try { localStorage.setItem(`panelflow_story_editor_${project.id}`, JSON.stringify(api.sanitizeStoryEditorState(project.id, snapshot))); }
        catch { /* Recovery is best-effort; engine persistence is authoritative. */ }
      }
    }, { status: setSaveStatus, error: setSaveError });
    saveQueueRef.current = queue;
    return () => { queue.dispose(); if (saveQueueRef.current === queue) saveQueueRef.current = null; };
  }, [project.id]);

  // Status updates must not cancel or restart the request that produced them.
  // Transient preview playback is never persisted as playing on the next open.
  useEffect(() => {
    if (!loading && saveStatus === "unsaved") saveQueueRef.current?.schedule({ ...editorState, is_playing: false });
  }, [editorState, project.id, loading]);

  const handleBackToProjects = async () => {
    const saved = await saveQueueRef.current?.flush();
    if (saved !== false) onBack();
  };

  // Load project assets and initialize story scenes
  useEffect(() => {
    let mounted = true;
    const loadProjectData = async () => {
      try {
        setLoading(true);
        const [loadedPages, loadedPanels, loadedScript, loadedStoryboard, loadedCharacters, loadedTextRegions] = await Promise.all([
          api.listPages(project.id).catch(() => []),
          api.listPanels(project.id).catch(() => []),
          api.getScript(project.id).catch(() => null),
          api.getStoryboard(project.id).catch(() => null),
          api.listCharacters(project.id).catch(() => []),
          api.listTextRegions(project.id).catch(() => []),
        ]);

        if (!mounted) return;
        setPages(loadedPages);
        setPanels(loadedPanels);
        setTextRegions(loadedTextRegions);

        if (loadedPages.length > 0) {
          setSelectedPageId(loadedPages[0].id);
        }

        // Restore the backend state first. Local storage is a recovery path for an interrupted save.
        const storageKey = `panelflow_story_editor_${project.id}`;
        const backendState = await api.getStoryEditorState(project.id).then((response) => {
          if (mounted) setProjectHistory(response.history ?? api.getCachedProjectHistory(project.id));
          return response.state;
        }).catch(() => null);
        const savedData = backendState ? JSON.stringify(backendState) : localStorage.getItem(storageKey);
        if (savedData) {
          try {
            let parsed = JSON.parse(savedData) as StoryEditorState;
            if (parsed && parsed.project_id === project.id && Array.isArray(parsed.scenes)) {
              parsed = api.hydrateStoryEditorState(project.id, parsed);
              const migratedScenes = resolveSceneTiming(parsed.scenes).map((sc, scIdx) => ({
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
                layers: (sc.layers || []).map((ly) => {
                  let imgUrl = ly.image_url;
                  if (ly.source_panel_id && (!imgUrl || imgUrl.includes("/pages/"))) {
                    const matched = loadedPanels.find((p: Panel) => p.id === ly.source_panel_id);
                    imgUrl = `${api.getPanelImageUrl(project.id, ly.source_panel_id)}?v=${encodeURIComponent(matched?.crop_filename || "detected")}`;
                  }
                  return {
                    ...ly,
                    image_url: imgUrl,
                    start_offset_sec: ly.start_offset_sec ?? 0,
                    duration_sec: ly.duration_sec ?? sc.duration_sec,
                  };
                }),
              }));

              const hasMockArtifacts = parsed.narration_chapter?.segments?.some(
                (s: any) =>
                  s.narration_text?.includes("obsidian halls") ||
                  s.narration_text?.includes("crystal matrix") ||
                  s.audio_asset_uri?.includes("aria_narration_sample.mp3")
              );

              const restoredChapter = (parsed.narration_chapter && !hasMockArtifacts)
                ? parsed.narration_chapter
                : buildInitialNarrationChapter(project.id, project.title, migratedScenes, undefined, loadedScript, loadedStoryboard, loadedCharacters, loadedTextRegions);
              const migratedNarration = (parsed.narration_clips && parsed.narration_clips.length > 0 && !hasMockArtifacts)
                ? parsed.narration_clips.map((n) => ({
                    ...n,
                    linked_to_scene: n.linked_to_scene ?? true,
                  }))
                : syncChapterToTimelineClips(restoredChapter, migratedScenes);

              setEditorState({
                ...parsed,
                is_playing: false,
                schema_version: 2,
                ripple_edit: parsed.ripple_edit ?? true,
                scenes: migratedScenes,
                narration_chapter: restoredChapter,
                narration_clips: alignLinkedNarration(migratedScenes, migratedNarration),
              });
              
              // Check for panel sync issues
              const panelSync = (parsed as any).panel_review_sync;
              if (panelSync?.removed_layers_count > 0) {
                setPanelSyncAlert({
                  show: true,
                  message: `${panelSync.removed_layers_count} source panel(s) were deleted or replaced. Their video layers are preserved; remove or replace those layers before exporting.`,
                  removedCount: panelSync.removed_layers_count,
                });
              }
              if (panelSync?.panels_stale && !panelSync?.removed_layers_count) {
                setPanelSyncAlert({
                  show: true,
                  message: "Panels have been modified in Panel Review. Consider reviewing changes in Story Editor.",
                });
              }
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
              image_url: `${api.getPanelImageUrl(project.id, panel.id)}?v=${encodeURIComponent(panel.crop_filename || "detected")}`,
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

          const initialChapter = buildInitialNarrationChapter(
            project.id,
            project.title,
            initialScenes,
            undefined,
            loadedScript,
            loadedStoryboard,
            loadedCharacters,
            loadedTextRegions
          );
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
                JSON.stringify(api.sanitizeStoryEditorState(project.id, initialEditorState))
              );
            } catch (e) {
              console.warn("Failed to save initial state:", e);
            }

            setSaveStatus("unsaved");

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

          const initialChapter = buildInitialNarrationChapter(
            project.id,
            project.title,
            [initialScene],
            undefined,
            loadedScript,
            loadedStoryboard,
            loadedCharacters,
            loadedTextRegions
          );
          const initialNarration = syncChapterToTimelineClips(initialChapter, [initialScene]);

          setEditorState((prev) => ({
            ...prev,
            scenes: [initialScene],
            narration_chapter: initialChapter,
            narration_clips: initialNarration,
            selected_object: { type: "scene", id: initialScene.id },
          }));
          setSaveStatus("unsaved");
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
    customCrop?: {
      x: number;
      y: number;
      width: number;
      height: number;
      crop_type?: "rect" | "polygon" | "pen";
      polygon_points?: Array<{ x: number; y: number }>;
      clip_path?: string;
    },
    asNewScene: boolean = false,
    autoPlay: boolean = false
  ) => {
    const crop = customCrop || (panel
      ? { x: panel.x, y: panel.y, width: panel.width, height: panel.height }
      : { x: 0, y: 0, width: page.width || 1200, height: Math.min(page.height || 1800, 1400) });

    let cropType = customCrop?.crop_type;
    let polygonPoints = customCrop?.polygon_points;
    let clipPath = customCrop?.clip_path;

    if (!customCrop && panel?.polygon_json) {
      try {
        const parsed = JSON.parse(panel.polygon_json);
        const pts: Array<{ x: number; y: number }> = Array.isArray(parsed)
          ? parsed.map((p: any) => (Array.isArray(p) ? { x: p[0], y: p[1] } : p))
          : [];
        if (pts.length >= 3 && panel.width > 0 && panel.height > 0) {
          cropType = "polygon";
          const relPts = pts.map((p) => ({
            x: Math.max(0, Math.min(100, Math.round(((p.x - panel.x) / panel.width) * 1000) / 10)),
            y: Math.max(0, Math.min(100, Math.round(((p.y - panel.y) / panel.height) * 1000) / 10)),
          }));
          polygonPoints = relPts;
          clipPath = `polygon(${relPts.map((p) => `${p.x}% ${p.y}%`).join(", ")})`;
        }
      } catch {
        // Fallback to standard rectangular bounds
      }
    }

    const newLayerId = `layer_${Date.now()}`;
    const newLayer: VisualLayer = {
      id: newLayerId,
      source_page_id: page.id,
      source_panel_id: panel?.id,
      image_url: panel
        ? `${api.getPanelImageUrl(project.id, panel.id)}?v=${encodeURIComponent(panel.crop_filename || "detected")}`
        : api.getPageImageUrl(project.id, page.id),
      page_sequence: page.sequence,
      crop,
      crop_type: cropType,
      clip_path: clipPath,
      polygon_points: polygonPoints,
      transform: {
        x: 0,
        y: 0,
        scale: 1.0,
        rotation: 0,
        opacity: 1.0,
        z_index: 1,
      },
      motion_preset: "slow_zoom_in",
      name: panel
        ? `Panel #${panel.page_sequence}`
        : `Page #${page.sequence} ${customCrop?.crop_type ? `(${customCrop.crop_type})` : "Region"}`,
    };

    if (asNewScene || editorState.scenes.length === 0) {
      // Append as new scene
      const newSceneId = `scene_${Date.now()}`;
      const totalDuration = sceneTimelineDuration(editorState.scenes);

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
        is_playing: autoPlay ? true : prev.is_playing,
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
        is_playing: autoPlay ? true : prev.is_playing,
      }));
    }
  };

  // Handler: Add blank scene
  const handleAddBlankScene = () => {
    const newSceneId = `scene_${Date.now()}`;
    const totalDuration = sceneTimelineDuration(editorState.scenes);

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

      const resyncedScenes = prev.ripple_edit === false ? resolveSceneTiming(updatedScenes) : packSceneTiming(updatedScenes);

      const resyncedClips = alignLinkedNarration(resyncedScenes, prev.narration_clips, prev.scenes);

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
      const resyncedScenes = insertSceneTiming(prev.scenes, dupScene, idx + 1, prev.ripple_edit !== false);

      const resyncedClips = alignLinkedNarration(resyncedScenes, prev.narration_clips, prev.scenes);

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
    updateEditorState((prev) => {
      const remaining = resolveSceneTiming(prev.scenes).filter((scene) => scene.id !== sceneId);
      const remainingScenes = remaining.length === 0
        ? [
            {
              id: `scene_empty_${Date.now()}`,
              sequence: 1,
              title: "Scene 1",
              duration_sec: 4.0,
              start_time_sec: 0,
              layers: [],
              transition_in: "none" as const,
            },
          ]
        : (prev.ripple_edit === false ? resolveSceneTiming(remaining) : packSceneTiming(remaining));

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

      const resyncedClips = alignLinkedNarration(remainingScenes, preservedClips, prev.scenes);

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

      const nextSelected = remainingScenes.length > 0
        ? (remainingScenes[0].layers.length > 0
            ? { type: "layer" as const, id: remainingScenes[0].layers[0].id, sceneId: remainingScenes[0].id }
            : { type: "scene" as const, id: remainingScenes[0].id })
        : null;

      const nextPlayhead = remainingScenes.length > 0 ? remainingScenes[0].start_time_sec : 0;

      return {
        ...prev,
        scenes: remainingScenes,
        narration_chapter: updatedChapter,
        narration_clips: resyncedClips,
        selected_object: nextSelected,
        playhead_sec: nextPlayhead,
      };
    });
  };

  // Handler: Delete layer
  const handleDeleteLayer = (layerId: string, sceneId: string) => {
    const targetScene = editorState.scenes.find((sc) => sc.id === sceneId);
    if (targetScene && targetScene.layers.length <= 1) {
      handleDeleteScene(sceneId);
      return;
    }
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
    <div className="pf-motion-editor h-screen w-screen flex flex-col text-zinc-100 overflow-hidden font-sans">
      {/* Panel Sync Alert */}
      {panelSyncAlert.show && (
        <div className="absolute top-16 left-1/2 transform -translate-x-1/2 z-50 w-full max-w-2xl px-4">
          <div className="bg-amber-950/90 border border-amber-600/50 rounded-lg p-3 flex items-center gap-3 shadow-xl backdrop-blur">
            <span className="text-amber-400 text-lg">⚠️</span>
            <div className="flex-1 text-sm text-amber-100">
              {panelSyncAlert.message}
            </div>
            <button className="px-3 py-2 rounded bg-amber-700 text-white text-sm" onClick={async () => {
              if (!window.confirm("Align single-panel scenes with Panel Review? This adds new panels, removes deleted-panel scenes, and follows panel order. Surviving scene edits are kept. Custom multi-layer scenes need manual review.")) return;
              try {
                const response = await api.saveStoryEditorState(project.id, editorState, true);
                updateEditorState(() => response.state);
                setPanelSyncAlert({ show: false, message: "" });
              } catch (error: any) {
                setPanelSyncAlert({ show: true, message: error.message || "Could not align panels." });
              }
            }}>Align panel scenes</button>
            <button
              onClick={() => setPanelSyncAlert({ show: false, message: "" })}
              className="text-amber-300 hover:text-amber-100 text-lg leading-none"
            >
              ×
            </button>
          </div>
        </div>
      )}
      
      {/* 1. Top Bar */}
      <StoryEditorTopBar
        project={project}
        state={editorState}
        onUpdateState={updateEditorState}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onBackToDashboard={handleBackToProjects}
        onExportClick={() => setShowExportModal(true)}
        saveStatus={saveStatus}
        onOpenNarrationStudio={() => setShowNarrationStudio(true)}
        onOpenAudioLibrary={() => handleOpenAudioLibrary()}
      />

      {saveError && (
        <div role="alert" className="shrink-0 flex items-center justify-between gap-3 border-b border-red-800 bg-red-950 px-4 py-2 text-sm text-red-100">
          <span>{saveError}</span>
          <button
            type="button"
            onClick={() => { void saveQueueRef.current?.flush(); }}
            disabled={saveStatus === "saving"}
            className="shrink-0 rounded border border-red-400 px-3 py-1 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-300 disabled:opacity-50"
          >
            Retry save
          </button>
        </div>
      )}

      {(projectHistory?.conflicted || projectHistory?.recoveryRequired) && <div role="alert" className="shrink-0 flex flex-wrap items-center gap-3 border-b border-amber-800 bg-amber-950 px-4 py-2 text-sm text-amber-100">
        <span>Saved history cannot safely restore this project because it changed outside the journal. Reload the saved project before starting fresh history.</span>
        <button type="button" disabled={historyBusy} className="rounded border border-amber-400 px-3 py-1 disabled:opacity-50" onClick={() => void startFreshHistory()}>Reload and start fresh history</button>
      </div>}
      {historyBusy && <div role="status" className="shrink-0 px-4 py-1 text-xs text-indigo-200">Restoring saved project history…</div>}

      {/* 2. Middle Main Workspace (Left Rail + Central Player + Right Panels) */}
      <div className="pf-editor-main flex-1 min-h-0 flex overflow-hidden">
        {/* Left Narrow Rail */}
        <div hidden={canvasMode === "setup"} className="pf-editor-rail shrink-0 min-h-0">
        <StoryEditorLeftRail
          activeTab={activeLeftTab}
          onSelectTab={handleLeftRailSelect}
          engineConnected={engineConnected}
        />
        </div>

        {/* Center: 16:9 Composition Canvas */}
        <div className="flex flex-col flex-1 min-w-0 min-h-0">
          <div role="group" aria-label="Canvas mode" className="flex items-center gap-2 px-2 py-1 border-b border-zinc-800 bg-zinc-950 shrink-0">
            <button type="button" aria-pressed={canvasMode === "setup"} disabled={!pages.length}
              onClick={() => { setCanvasMode("setup"); updateEditorState(s => ({ ...s, is_playing: false })); }}
              className={`px-3 py-1 rounded text-xs ${canvasMode === "setup" ? "bg-indigo-600 text-white" : "text-zinc-400"}`}>Setup</button>
            <button type="button" aria-pressed={canvasMode === "player"} onClick={() => setCanvasMode("player")}
              className={`px-3 py-1 rounded text-xs ${canvasMode === "player" ? "bg-indigo-600 text-white" : "text-zinc-400"}`}>Player</button>
            {canvasMode === "setup" && <div className="ml-auto flex items-center gap-2">
              <button type="button" className="pf-setup-control" aria-expanded={setupSourcesOpen} onClick={() => setSetupSourcesOpen(open => !open)}>{setupSourcesOpen ? "Hide sources" : "Show sources"}</button>
              <button type="button" className="pf-setup-control" aria-expanded={setupTimelineOpen} onClick={() => setSetupTimelineOpen(open => !open)}>{setupTimelineOpen ? "Hide timeline" : "Show timeline"}</button>
            </div>}
          </div>
          {/* Engine & Job Status — toolbar-integrated, fixed positioning removed */}
          <EngineJobStatus
            engineHealthy={engineHealthy}
            jobs={jobs}
            onCancel={(id) => cancelJobContext(id)}
            onOpenManager={() => {/* placeholder: could open a dedicated page */}}
          />
        {canvasMode === "setup" ? <SourceSetupCanvas
          key={project.id}
          projectId={project.id}
          drafts={setupDrafts}
          page={pages.find(page => page.id === selectedPageId) || pages[0] || null}
          pages={pages}
          onSelectPage={pageId => {
            setSelectedPageId(pageId);
            setSelectedPanelId(panels.filter(p => p.page_id === pageId).sort((a, b) => a.page_sequence - b.page_sequence)[0]?.id || null);
          }}
          panels={panels} selectedPanelId={selectedPanelId}
          onSelectPanel={panel => setSelectedPanelId(panel.id)}
          onPanelSaved={panel => setPanels(previous => previous.map(existing => existing.id === panel.id ? panel : existing))}
          onPanelsChanged={all => {
            setPanels(all);
            void api.getProjectHistory(project.id).then(reply => setProjectHistory(reply.history)).catch(() => {});
          }}
          onAddPanel={(page, panel, customCrop) => { handleAddPanelToScene(page, panel, customCrop, true, false); setCanvasMode("player"); }}
          onBeforeSave={async () => {
            if (historyAction.current || await saveQueueRef.current?.flush() === false) throw new Error("Save the current editor changes before modifying source panels.");
          }}
        /> : <VideoCompositionCanvas
          previewOnly
          projectId={project.id}
          state={editorState}
          onUpdateState={updateEditorState}
          onSelectLayer={(layerId, sceneId) => {
            updateEditorState((s) => {
              const sc = s.scenes.find((item) => item.id === sceneId);
              const layer = sc?.layers.find((l) => l.id === layerId);
              const layerOffset = layer?.start_offset_sec ?? 0;
              return {
                ...s,
                selected_object: { type: "layer", id: layerId, sceneId },
                playhead_sec: sc ? sc.start_time_sec + layerOffset : s.playhead_sec,
              };
            });
          }}
        />}
        </div>

        {/* Unified Right Sidebar: Tabbed container with "Source Pages" and "Inspector" */}
        <div hidden={canvasMode === "setup" && !setupSourcesOpen} data-setup={canvasMode === "setup"} className="pf-editor-sidebar shrink-0 min-h-0 flex flex-col h-full overflow-hidden">
          {/* Top Tab Bar: Source Pages | Inspector */}
          {canvasMode !== "setup" && (
            <div className="flex items-center gap-1 p-1 bg-zinc-950/80 border-b border-zinc-800 shrink-0 rounded-t-xl select-none" role="tablist" aria-label="Sidebar Sections">
              <button
                type="button"
                role="tab"
                aria-selected={rightSidebarTab === "source"}
                onClick={() => setRightSidebarTab("source")}
                className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                  rightSidebarTab === "source"
                    ? "bg-violet-600 text-white shadow-sm shadow-violet-600/30 ring-1 ring-violet-400/40"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                }`}
              >
                <Icons.Layers className="w-3.5 h-3.5" />
                <span>Source Pages</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={rightSidebarTab === "inspector"}
                onClick={() => setRightSidebarTab("inspector")}
                className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                  rightSidebarTab === "inspector"
                    ? "bg-violet-600 text-white shadow-sm shadow-violet-600/30 ring-1 ring-violet-400/40"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                }`}
              >
                <Icons.Sliders className="w-3.5 h-3.5" />
                <span>Inspector</span>
              </button>
            </div>
          )}

          {/* Active Tab Content (Full Height) */}
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {canvasMode === "setup" || rightSidebarTab === "source" ? (
              <div className="pf-editor-source flex-1 overflow-hidden flex flex-col min-h-0 h-full">
                <SourcePageBrowser
                  compact
                  hideEditingTools
                  projectId={project.id}
                  pages={pages}
                  panels={panels}
                  selectedPageId={selectedPageId}
                  onSelectPage={(pageId) => {
                    setSelectedPageId(pageId);
                    setSelectedPanelId(panels.filter(panel => panel.page_id === pageId).sort((a, b) => a.page_sequence - b.page_sequence)[0]?.id || null);
                    if (canvasMode === "setup") {
                      updateEditorState(s => ({ ...s, is_playing: false }));
                    }
                  }}
                  selectedPanelId={selectedPanelId}
                  onSelectPanel={(panel) => {
                    setSelectedPanelId(panel?.id || null);
                    if (panel) {
                      setSelectedPageId(panel.page_id);
                    }
                    if (canvasMode === "setup") {
                      updateEditorState(s => ({ ...s, is_playing: false }));
                    }
                  }}
                  onAddPanelToScene={handleAddPanelToScene}
                  activeSubTab={sourceSubTab}
                  onSubTabChange={setSourceSubTab}
                />
              </div>
            ) : (
              <div className="pf-editor-inspector flex-1 overflow-hidden flex flex-col min-h-0 h-full">
                <ContextualInspector
                  projectId={project.id}
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
            )}
          </div>
        </div>
      </div>

      {loading && <div role="status" className="pf-editor-loading">Loading saved scenes and source pages…</div>}
      {/* 3. Bottom Timeline */}
      <div hidden={canvasMode === "setup" && !setupTimelineOpen} className="pf-editor-timeline-region">
      <StoryEditorTimeline
        projectId={project.id}
        state={editorState}
        onUpdateState={updateEditorState}
        onDeleteLayer={handleDeleteLayer}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onSelectScene={(sceneId) => {
          setCanvasMode("player");
          updateEditorState((s) => {
            const sc = s.scenes.find((item) => item.id === sceneId);
            return {
              ...s,
              selected_object: { type: "scene", id: sceneId },
              playhead_sec: sc ? sc.start_time_sec : s.playhead_sec,
            };
          });
        }}
        onSelectLayer={(layerId, sceneId) => {
          setCanvasMode("player");
          updateEditorState((s) => {
            const sc = s.scenes.find((item) => item.id === sceneId);
            const layer = sc?.layers.find((l) => l.id === layerId);
            const layerOffset = layer?.start_offset_sec ?? 0;
            return {
              ...s,
              selected_object: { type: "layer", id: layerId, sceneId },
              playhead_sec: sc ? sc.start_time_sec + layerOffset : s.playhead_sec,
            };
          });
        }}
        onSelectMotionBadge={(sceneId, layerId) => {
          updateEditorState((s) => ({
            ...s,
            selected_object: layerId ? { type: "layer", id: layerId, sceneId } : { type: "scene", id: sceneId },
          }));
          setRightSidebarTab("inspector");
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

      </div>
      {/* Guided production steps remain available in Advanced mode. */}
      {editorState.mode === "advanced" && <WorkflowStepperRibbon currentStep={workflowStep} onSelectStep={handleSelectWorkflowStep} />}
      {showEditorSettings && <EditorSettingsDialog state={editorState} onUpdateState={updateEditorState} onClose={() => { setShowEditorSettings(false); setActiveLeftTab("story"); }} />}

      {/* 5. Full-Screen Narration Studio Workspace Overlay */}
      {showNarrationStudio && (
        <div className="fixed inset-0 z-50 bg-zinc-950 flex flex-col">
          <NarrationStudio
            initialChapter={
              editorState.narration_chapter ||
              buildInitialNarrationChapter(project.id, project.title, editorState.scenes, undefined, undefined, undefined, undefined, textRegions)
            }
            initialSegmentId={
              editorState.selected_object?.type === "narration"
                ? editorState.selected_object.id
                : editorState.selected_object?.type === "scene"
                ? editorState.narration_clips.find((c) => c.scene_id === editorState.selected_object?.id)?.id
                : undefined
            }
            projectId={project.id}
            scenes={editorState.scenes}
            pages={pages}
            panels={panels}
            onClose={() => setShowNarrationStudio(false)}
            onAddToTimeline={(mode: "all" | "selected", segmentId?: string) => {
              if (mode === "all") {
                updateEditorState((prev) => {
                  const ch =
                    prev.narration_chapter ||
                    buildInitialNarrationChapter(project.id, project.title, prev.scenes, undefined, undefined, undefined, undefined, textRegions);
                  const syncedClips = syncChapterToTimelineClips(
                    ch,
                    prev.scenes,
                    prev.narration_clips
                  );
                  return {
                    ...prev,
                    narration_clips: syncedClips,
                  };
                });
                setShowNarrationStudio(false);
              } else if (mode === "selected" && segmentId) {
                updateEditorState((prev) => {
                  const ch =
                    prev.narration_chapter ||
                    buildInitialNarrationChapter(project.id, project.title, prev.scenes, undefined, undefined, undefined, undefined, textRegions);
                  const seg = ch.segments.find((s: any) => s.id === segmentId);
                  if (!seg) return prev;
                  const newClipId = `clip_${Date.now()}`;
                  const matchingScene =
                    prev.scenes.find((s) => s.id === seg.scene_id) || prev.scenes[0];
                  const newClip: NarrationClip = {
                    id: newClipId,
                    narration_segment_id: seg.id,
                    scene_id: matchingScene?.id,
                    linked_to_scene: true,
                    scene_offset_sec: Math.max(0, prev.playhead_sec - (matchingScene?.start_time_sec ?? 0)),
                    start_time_sec: Math.max(matchingScene?.start_time_sec ?? 0, prev.playhead_sec),
                    duration_sec: seg.measured_duration_sec || seg.estimated_duration_sec || 3.0,
                    speaker: seg.speaker_name,
                    speaker_id: seg.speaker_id,
                    text: seg.narration_text,
                    emotion: seg.performance_notes || "Neutral",
                    speed: 1.0,
                    audio_url: seg.audio_asset_uri || undefined,
                    status: seg.audio_asset_uri ? "READY" : "UNQUEUED",
                  };
                  return {
                    ...prev,
                    narration_clips: [
                      ...prev.narration_clips.filter((c) => c.narration_segment_id !== seg.id),
                      newClip,
                    ],
                    selected_object: { type: "narration" as const, id: newClipId },
                  };
                });
                setShowNarrationStudio(false);
              }
            }}
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
