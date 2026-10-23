import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { SnapshotHistory } from "@panelflow/history";
import { Icons, Button, Badge } from "@panelflow/ui";
import {
  type NarrationChapter,
  type NarrationSegment,
  type NarrationFilterState,
  type NarrationStudioProps,
  type NarrationToTimelineContract,
  type CharacterProfile,
  type SpeakerType,
  computeContentHash,
} from "./NarrationStudio.types";
import { MOCK_CHAPTER } from "./NarrationStudio.mock";
import { NarrationStoryPanel } from "./NarrationStoryPanel";
import { NarrationSegmentEditor } from "./NarrationSegmentEditor";
import { NarrationReviewPanel } from "./NarrationReviewPanel";
import { EmotionDeliveryControls } from "./EmotionDeliveryControls";
import { CharacterVoiceManager } from "./CharacterVoiceManager";
import { AudioPreviewPlayer } from "./AudioPreviewPlayer";
import { api } from "@panelflow/api-client";
import { NarrationJobQueue } from "./NarrationJobQueue";
import { historyShortcut } from "../../history/shortcuts";
import { ProviderHealthModal } from "../ProviderHealthModal";
import { GlobalLLMSelector } from "../GlobalLLMSelector";
import type { CloudLLMConfig } from "@panelflow/shared-types";

export const NarrationStudio: React.FC<NarrationStudioProps> = ({
  initialChapter,
  initialSegmentId,
  projectId = "",
  scenes = [],
  pages = [],
  panels = [],
  onChapterSave,
  onSegmentApproved,
  onExportTimelineContract,
  onAddToTimeline,
  onClose,
}) => {
  // Main Chapter State initialized with prop or rich mock chapter
  const [chapter, setChapter] = useState<NarrationChapter>(
    () => initialChapter || MOCK_CHAPTER
  );

  // Active Selected Segment ID
  const [selectedSegmentId, setSelectedSegmentId] = useState<string>(() => {
    const ch = initialChapter || MOCK_CHAPTER;
    if (initialSegmentId) {
      const match = ch.segments.find((s) => s.id === initialSegmentId || s.scene_id === initialSegmentId);
      if (match) return match.id;
    }
    return ch.segments[0]?.id || "";
  });

  // Keep segment in sync if initialSegmentId changes
  useEffect(() => {
    if (initialSegmentId) {
      const match = chapter.segments.find((s) => s.id === initialSegmentId || s.scene_id === initialSegmentId);
      if (match) {
        setSelectedSegmentId(match.id);
      }
    }
  }, [initialSegmentId, chapter.segments]);

  // Filter State
  const [filter, setFilter] = useState<NarrationFilterState>({
    search_query: "",
    selected_character_id: null,
    selected_status: "ALL",
    selected_speaker_type: "ALL",
  });

  // Center Column View Mode: "editor" | "quality_review"
  const [centerMode, setCenterMode] = useState<"editor" | "quality_review">("editor");

  // Right Column Inspector Tab: "delivery" | "casting"
  const [rightInspectorTab, setRightInspectorTab] = useState<"delivery" | "casting">("delivery");

  // Modals & Panels
  const [showVoiceManagerModal, setShowVoiceManagerModal] = useState<boolean>(false);
  const [showExportModal, setShowExportModal] = useState<boolean>(false);
  const [timelineModalOpen, setTimelineModalOpen] = useState<boolean>(false);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");

  // Ollama Live Model Discovery & Generation States
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaDetailedModels, setOllamaDetailedModels] = useState<any[]>([]);
  const [selectedOllamaModel, setSelectedOllamaModel] = useState<string>("qwen3.5:9b");
  const [isOllamaOnline, setIsOllamaOnline] = useState<boolean>(true);
  const [isDraftingNarration, setIsDraftingNarration] = useState<boolean>(false);
  const [generationStep, setGenerationStep] = useState<string>("");
  const [showTierDropdown, setShowTierDropdown] = useState<boolean>(false);
  const [isSynthesizingAll, setIsSynthesizingAll] = useState<boolean>(false);
  const [showOllamaGuideModal, setShowOllamaGuideModal] = useState<boolean>(false);
  const [postDraftPrompt, setPostDraftPrompt] = useState<boolean>(false);
  const [targetSceneId, setTargetSceneId] = useState<string>(() => scenes?.[0]?.id || "");

  // Global & Flow-Wise LLM Selection
  const [selectedProviderId, setSelectedProviderId] = useState<string>("global");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [showProviderSettingsModal, setShowProviderSettingsModal] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    const fetchProviders = async () => {
      try {
        const ollamaRes = await api.getOllamaModels().catch(() => null);

        if (isMounted && ollamaRes) {
          const res = ollamaRes;
          const modelList = res.models?.map((m: any) => m.name || m) || [];
          setOllamaModels(modelList);
          setOllamaDetailedModels(res.models || []);
          setIsOllamaOnline(res.healthy !== false && modelList.length > 0);
          if (modelList.length > 0 && !modelList.includes(selectedOllamaModel)) {
            const preferred =
              modelList.find(
                (m: string) =>
                  m.includes("qwen3.5") || m.includes("gemma4") || m.includes("qwen3.6")
              ) || modelList[0];
            setSelectedOllamaModel(preferred);
          }
          if (scenes && scenes.length > 0 && !targetSceneId) {
            setTargetSceneId(scenes[0].id);
          }
        } else if (isMounted) {
          setIsOllamaOnline(false);
        }
      } catch (err) {
        if (isMounted) setIsOllamaOnline(false);
      }
    };
    fetchProviders();
    return () => {
      isMounted = false;
    };
  }, [scenes, targetSceneId, selectedOllamaModel]);

  // Local draft history is deliberately separate from the persisted project
  // journal. The parent receives the restored chapter through autosave and
  // records that durable change as one project command.
  const historyRef = useRef(new SnapshotHistory<NarrationChapter>({ limit: 40 }));
  const [historyState, setHistoryState] = useState(() => historyRef.current.getState());

  // Find currently selected segment and adjacent neighbors
  const selectedIndex = chapter.segments.findIndex((s) => s.id === selectedSegmentId);
  const selectedSegment = selectedIndex !== -1 ? chapter.segments[selectedIndex] : null;
  const previousSegment = selectedIndex > 0 ? chapter.segments[selectedIndex - 1] : null;
  const nextSegment =
    selectedIndex >= 0 && selectedIndex < chapter.segments.length - 1
      ? chapter.segments[selectedIndex + 1]
      : null;

  // Selected character and voice profile
  const selectedCharacter = useMemo(() => {
    if (!selectedSegment) return null;
    return chapter.characters.find((c) => c.id === selectedSegment.speaker_id) || null;
  }, [selectedSegment, chapter.characters]);

  const selectedVoiceProfile = useMemo(() => {
    if (!selectedSegment) return undefined;
    return chapter.voice_profiles.find(
      (v) => v.id === selectedSegment.voice_profile_id
    );
  }, [selectedSegment, chapter.voice_profiles]);

  // Update chapter state with undo tracking
  const updateChapterState = useCallback(
    (updater: (prev: NarrationChapter) => NarrationChapter, trackHistory = true) => {
      setChapter((prev) => {
        const next = updater(prev);
        if (trackHistory && historyRef.current.record(prev, next)) {
          setHistoryState(historyRef.current.getState());
          setSaveStatus("unsaved");
        }
        return next;
      });
    },
    []
  );

  // Simulated auto-save effect
  useEffect(() => {
    if (saveStatus === "unsaved") {
      const timer = setTimeout(() => {
        setSaveStatus("saving");
        setTimeout(() => {
          setSaveStatus("saved");
          onChapterSave?.(chapter);
        }, 500);
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [saveStatus, chapter, onChapterSave]);

  // Undo / Redo Handlers
  const handleUndo = useCallback(() => {
    const previous = historyRef.current.undo();
    if (previous === null) return;
    setChapter(previous);
    setHistoryState(historyRef.current.getState());
    setSaveStatus("unsaved");
  }, []);

  const handleRedo = useCallback(() => {
    const next = historyRef.current.redo();
    if (next === null) return;
    setChapter(next);
    setHistoryState(historyRef.current.getState());
    setSaveStatus("unsaved");
  }, []);

  // Keyboard shortcut listener (Ctrl+Z, Ctrl+Y, ArrowUp, ArrowDown)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Do not trigger global shortcuts if typing inside an active input or textarea
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA";

      const action = historyShortcut(e);
      if (action === "undo") {
        e.preventDefault();
        handleUndo();
      } else if (action === "redo") {
        e.preventDefault();
        handleRedo();
      } else if (!isInput && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        if (selectedIndex !== -1) {
          e.preventDefault();
          const targetIndex =
            e.key === "ArrowUp"
              ? Math.max(0, selectedIndex - 1)
              : Math.min(chapter.segments.length - 1, selectedIndex + 1);
          const targetSeg = chapter.segments[targetIndex];
          if (targetSeg) {
            setSelectedSegmentId(targetSeg.id);
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleUndo, handleRedo, selectedIndex, chapter.segments]);

  // Update active segment properties with stale async rejection guard
  const handleUpdateSegment = (
    updates: Partial<NarrationSegment> & { target_revision?: number; content_hash?: string }
  ) => {
    if (!selectedSegmentId) return;
    updateChapterState((prev) => ({
      ...prev,
      updated_at: new Date().toISOString(),
      segments: prev.segments.map((seg) => {
        if (seg.id !== selectedSegmentId) return seg;

        // Decision 2: Guard against stale async synthesis results replacing newer script revisions
        if (
          updates.target_revision !== undefined &&
          updates.target_revision !== seg.text_revision
        ) {
          return {
            ...seg,
            generation_status: "OUTDATED",
            generation_progress: 0,
            generation_error: `Stale generation rejected: Script was updated to Rev #${seg.text_revision} while Rev #${updates.target_revision} was processing.`,
            updated_at: new Date().toISOString(),
          };
        }

        const updatedSeg = { ...seg, ...updates };
        if (updates.review_status === "APPROVED" && seg.review_status !== "APPROVED") {
          onSegmentApproved?.(updatedSeg);
        }
        return updatedSeg;
      }),
    }));
  };

  // Reorder Segment in story order
  const handleReorderSegment = (segmentId: string, direction: "up" | "down") => {
    updateChapterState((prev) => {
      const idx = prev.segments.findIndex((s) => s.id === segmentId);
      if (idx === -1) return prev;
      const targetIdx = direction === "up" ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= prev.segments.length) return prev;

      const newSegments = [...prev.segments];
      const temp = newSegments[idx];
      newSegments[idx] = newSegments[targetIdx];
      newSegments[targetIdx] = temp;

      // Re-assign sequence numbers based on new story order
      return {
        ...prev,
        updated_at: new Date().toISOString(),
        segments: newSegments.map((seg, i) => ({
          ...seg,
          sequence: i + 1,
        })),
      };
    });
  };

  // Add new story segment
  const handleAddSegment = (speakerType: SpeakerType) => {
    const isNarrator = speakerType === "NARRATOR";
    const defaultSpeaker = isNarrator
      ? chapter.characters.find((c) => c.role === "NARRATOR") || chapter.characters[0]
      : chapter.characters.find((c) => c.role !== "NARRATOR") || chapter.characters[0];

    const newId = `seg_${Date.now()}`;
    const newSequence = chapter.segments.length + 1;

    const text = isNarrator
      ? "The silence settled once more over the shattered stone corridor."
      : "Wait... do you hear that sound coming from the corridor?";
    const emotion = isNarrator ? "Mysterious" : "Suspenseful";

    const newSegment: NarrationSegment = {
      id: newId,
      sequence: newSequence,
      scene_id: `scene_${Math.ceil(newSequence / 3)}`,
      scene_title: `Scene ${Math.ceil(newSequence / 3)}: The Next Discovery`,
      linked_to_scene: true,
      scene_offset_sec: 0.0,
      speaker_id: defaultSpeaker?.id || "char_narrator",
      speaker_name: defaultSpeaker?.name || "The Narrator",
      speaker_type: speakerType,
      narration_text: text,
      text_revision: 1,
      content_hash: computeContentHash(text, emotion, 1.0, "short"),
      source_context: {
        page_id: `page_${Math.ceil(newSequence / 3)}`,
        page_number: Math.ceil(newSequence / 3),
        panel_ids: [`panel_${newSequence}`],
        panel_labels: [`Page ${Math.ceil(newSequence / 3)} • Panel ${newSequence}`],
        raw_ocr_dialogue: isNarrator ? "" : "Look out!",
        visual_description: "New manga panel scene framing characters reacting to newly discovered chamber.",
        story_context: "Narrative development expanding chapter progression.",
      },
      delivery: {
        emotion,
        intensity: 0.6,
        speech_speed: 1.0,
        pause: {
          preset: "short",
          duration_ms: 300,
          placement: "after_first_sentence",
        },
        performance_notes: "Natural narrative pacing.",
        pronunciation_guide: [],
      },
      review_status: "DRAFT",
      generation_status: "UNQUEUED",
      estimated_duration_sec: 4.5,
      voice_profile_id: defaultSpeaker?.default_voice_profile_id || chapter.voice_profiles[0]?.id || "",
      updated_at: new Date().toISOString(),
    };

    updateChapterState((prev) => ({
      ...prev,
      updated_at: new Date().toISOString(),
      segments: [...prev.segments, newSegment],
    }));

    setSelectedSegmentId(newId);
  };

  // Duplicate Segment
  const handleDuplicateSegment = (segmentId: string) => {
    const seg = chapter.segments.find((s) => s.id === segmentId);
    if (!seg) return;

    const newId = `seg_${Date.now()}`;
    const insertIdx = chapter.segments.findIndex((s) => s.id === segmentId) + 1;
    const copyText = `${seg.narration_text} (Copy)`;

    const duplicatedSeg: NarrationSegment = {
      ...seg,
      id: newId,
      narration_text: copyText,
      text_revision: 1,
      content_hash: computeContentHash(
        copyText,
        seg.delivery.emotion,
        seg.delivery.speech_speed,
        seg.delivery.pause?.preset
      ),
      review_status: "DRAFT",
      generation_status: "UNQUEUED",
      generation_progress: 0,
      audio_asset_uri: null,
      previous_audio_asset_uri: null,
      updated_at: new Date().toISOString(),
    };

    updateChapterState((prev) => {
      const newSegments = [...prev.segments];
      newSegments.splice(insertIdx, 0, duplicatedSeg);
      return {
        ...prev,
        updated_at: new Date().toISOString(),
        segments: newSegments.map((s, i) => ({ ...s, sequence: i + 1 })),
      };
    });

    setSelectedSegmentId(newId);
  };

  // Split Segment at Cursor
  const handleSplitSegment = (segmentId: string, splitIndex: number) => {
    const seg = chapter.segments.find((s) => s.id === segmentId);
    if (!seg) return;

    const textA = seg.narration_text.slice(0, splitIndex).trim();
    const textB = seg.narration_text.slice(splitIndex).trim();

    if (!textA || !textB) return;

    const newId = `seg_${Date.now()}`;
    const idx = chapter.segments.findIndex((s) => s.id === segmentId);

    const segmentB: NarrationSegment = {
      ...seg,
      id: newId,
      narration_text: textB,
      text_revision: 1,
      content_hash: computeContentHash(
        textB,
        seg.delivery.emotion,
        seg.delivery.speech_speed,
        seg.delivery.pause?.preset
      ),
      review_status: "DRAFT",
      generation_status: "UNQUEUED",
      generation_progress: 0,
      audio_asset_uri: null,
      previous_audio_asset_uri: null,
      estimated_duration_sec: Math.max(1.5, Math.round((seg.estimated_duration_sec / 2) * 10) / 10),
      updated_at: new Date().toISOString(),
    };

    updateChapterState((prev) => {
      const newSegments = [...prev.segments];
      // Update first half
      newSegments[idx] = {
        ...seg,
        narration_text: textA,
        text_revision: (seg.text_revision || 1) + 1,
        content_hash: computeContentHash(
          textA,
          seg.delivery.emotion,
          seg.delivery.speech_speed,
          seg.delivery.pause?.preset
        ),
        estimated_duration_sec: Math.max(1.5, Math.round((seg.estimated_duration_sec / 2) * 10) / 10),
        generation_status: "OUTDATED",
        previous_audio_asset_uri: seg.audio_asset_uri || seg.previous_audio_asset_uri || null,
        audio_asset_uri: null,
        updated_at: new Date().toISOString(),
      };
      // Insert second half
      newSegments.splice(idx + 1, 0, segmentB);
      return {
        ...prev,
        updated_at: new Date().toISOString(),
        segments: newSegments.map((s, i) => ({ ...s, sequence: i + 1 })),
      };
    });
  };

  // Delete Segment
  const handleDeleteSegment = (segmentId: string) => {
    updateChapterState((prev) => {
      const filtered = prev.segments.filter((s) => s.id !== segmentId);
      return {
        ...prev,
        updated_at: new Date().toISOString(),
        segments: filtered.map((s, i) => ({ ...s, sequence: i + 1 })),
      };
    });

    if (selectedSegmentId === segmentId) {
      const remaining = chapter.segments.filter((s) => s.id !== segmentId);
      setSelectedSegmentId(remaining[0]?.id || "");
    }
  };

  // Character & Voice Profile Handlers
  const handleUpdateCharacter = (charId: string, updates: Partial<CharacterProfile>) => {
    updateChapterState((prev) => ({
      ...prev,
      characters: prev.characters.map((c) => (c.id === charId ? { ...c, ...updates } : c)),
      // Also sync speaker name if changed
      segments: updates.name
        ? prev.segments.map((s) => (s.speaker_id === charId ? { ...s, speaker_name: updates.name! } : s))
        : prev.segments,
    }));
  };

  const handleApplyVoiceToAllSegments = (
    characterId: string,
    voiceProfileId: string,
    overwriteCustomOverrides: boolean = false
  ) => {
    updateChapterState((prev) => ({
      ...prev,
      segments: prev.segments.map((s) => {
        if (s.speaker_id !== characterId) return s;
        // Decision: Protect manual customizations unless user explicitly requested overwrite
        if (s.has_custom_voice_override && !overwriteCustomOverrides) {
          return s;
        }
        return {
          ...s,
          voice_profile_id: voiceProfileId,
          has_custom_voice_override: false,
          generation_status: s.generation_status === "READY" ? "OUTDATED" : s.generation_status,
          updated_at: new Date().toISOString(),
        };
      }),
    }));
  };

  // Batch Update Segments (e.g. from job queue)
  const handleBatchUpdateSegments = (segmentIds: string[], updates: Partial<NarrationSegment>) => {
    updateChapterState((prev) => ({
      ...prev,
      segments: prev.segments.map((s) => (segmentIds.includes(s.id) ? { ...s, ...updates } : s)),
    }));
  };

  // Generate serialized Timeline Integration Contract (Schema 5A-v2)
  const timelineContract: NarrationToTimelineContract = useMemo(() => {
    return {
      schema_version: "5A-v2",
      project_id: chapter.project_id,
      chapter_id: chapter.chapter_id,
      exported_at: new Date().toISOString(),
      clips: chapter.segments.map((s) => ({
        narration_segment_id: s.id,
        sequence: s.sequence,
        scene_id: s.scene_id,
        linked_to_scene: s.linked_to_scene ?? true,
        scene_offset_sec: s.scene_offset_sec ?? 0.0,
        speaker: s.speaker_name,
        text: s.narration_text,
        text_revision: s.text_revision ?? 1,
        content_hash: s.content_hash,
        emotion: s.delivery.emotion,
        speed: s.delivery.speech_speed,
        estimated_duration_sec: s.estimated_duration_sec,
        measured_duration_sec: s.measured_duration_sec,
        audio_asset_uri: s.audio_asset_uri,
        previous_audio_asset_uri: s.previous_audio_asset_uri,
        generated_audio_revision: s.generated_audio_revision,
        review_status: s.review_status,
        generation_status: s.generation_status,
        source_panel_ids: s.source_context.panel_ids,
        voice_profile_id: s.voice_profile_id,
        performance_intent: s.delivery.performance_notes,
      })),
    };
  }, [chapter]);

  // 3-Tier AI Narration Generation (Page Recap 5-10 Lines -> Panel Micro -> Final Synced Script)
  const handleGenerateAiNarration = async (
    mode: "full" | "page_only" | "panel_only" | "harmonize" = "full"
  ) => {
    if (!projectId && !chapter.segments.length) return;
    setIsDraftingNarration(true);
    setGenerationStep(
      mode === "page_only"
        ? "Drafting 5-10 line page stories..."
        : mode === "panel_only"
        ? "Analyzing panel micro beats..."
        : mode === "harmonize"
        ? "Comparing and harmonizing scripts..."
        : "Executing 3-Tier Narration Pipeline (Page -> Panel -> Harmonize)..."
    );

    try {
      const scenesPayload = (scenes && scenes.length > 0 ? scenes : chapter.segments).map(
        (s: any, idx: number) => {
          const matchingSegment = chapter.segments.find((seg) => seg.scene_id === s.id) || chapter.segments[idx];
          const ocrText =
            matchingSegment?.source_context?.raw_ocr_dialogue ||
            s.ocr_text ||
            matchingSegment?.narration_text ||
            "";
          const panelIds =
            s.layers?.map((l: any) => l.source_panel_id).filter(Boolean) ||
            matchingSegment?.source_context?.panel_ids ||
            s.source_context?.panel_ids ||
            [];
          const speakerName = matchingSegment?.speaker_name || s.speaker || "The Narrator";
          return {
            id: s.id || `scene_${idx + 1}`,
            sequence: s.sequence || idx + 1,
            title: s.title || `Scene ${idx + 1}`,
            visual_description:
              s.layers?.[0]?.name || s.visual_description || `Scene ${idx + 1} manga visual framing`,
            ocr_text: ocrText,
            panel_ids: panelIds,
            page_id: s.page_id || matchingSegment?.source_context?.page_id,
            page_sequence: s.page_sequence || matchingSegment?.source_context?.page_number || 1,
            speaker: speakerName,
            characters: [speakerName],
          };
        }
      );

      const draftResult = await api.draftNarration(
        projectId,
        scenesPayload,
        selectedProviderId === "global" ? undefined : selectedProviderId,
        selectedModel || undefined,
        mode,
        undefined,
        chapter.page_scripts
      );

      if (draftResult?.beats && draftResult.beats.length > 0) {
        const nextScripts = {
          ...(chapter.page_scripts || {}),
          ...(draftResult.page_scripts || {}),
        };

        const updatedSegments: NarrationSegment[] = draftResult.beats.map(
          (beat: any, bIdx: number) => {
            const matchingScene = scenes.find((sc) => sc.id === beat.scene_id) || scenes[bIdx];
            const primaryLayer = matchingScene?.layers?.[0];
            const text = beat.proposed_narration_text || "";
            const emotion = beat.recommended_emotion || "Neutral";
            const speed = beat.recommended_speed || 1.0;
            const characterName = beat.character_name || beat.speaker || "The Narrator";
            const estDuration =
              beat.estimated_duration_sec ||
              Math.max(2.0, Math.round(text.split(" ").filter(Boolean).length / 2.33));

            return {
              id: `narr_${beat.scene_id || bIdx + 1}`,
              sequence: bIdx + 1,
              scene_id: matchingScene?.id || beat.scene_id,
              scene_title: matchingScene?.title || `Scene ${bIdx + 1}`,
              linked_to_scene: !!matchingScene,
              scene_offset_sec: 0.0,
              speaker_id: "char_narrator",
              speaker_name: characterName,
              speaker_type: beat.speaker_type || "NARRATOR",
              voice_profile_id: "voice_aria_female_narrator",
              narration_text: text,
              page_narration_text: beat.page_narration_text,
              panel_narration_text: beat.panel_narration_text,
              synthesis_notes: beat.synthesis_notes,
              text_revision: 1,
              content_hash: computeContentHash(text, emotion, speed, "short"),
              source_context: {
                page_id: primaryLayer?.source_page_id || `page_${bIdx + 1}`,
                page_number: primaryLayer?.page_sequence || bIdx + 1,
                panel_ids: beat.panel_ids?.length
                  ? beat.panel_ids
                  : primaryLayer?.source_panel_id
                  ? [primaryLayer.source_panel_id]
                  : [],
                panel_labels: [primaryLayer?.name || `Panel #${bIdx + 1}`],
                panel_preview_url: (projectId && (beat.panel_ids?.[0] || primaryLayer?.source_panel_id))
                  ? api.getPanelImageUrl(projectId, beat.panel_ids?.[0] || primaryLayer?.source_panel_id)
                  : primaryLayer?.image_url,
                image_url: (projectId && (beat.panel_ids?.[0] || primaryLayer?.source_panel_id))
                  ? api.getPanelImageUrl(projectId, beat.panel_ids?.[0] || primaryLayer?.source_panel_id)
                  : primaryLayer?.image_url,
                raw_ocr_dialogue: beat.observed_ocr_dialogue || "",
                visual_description:
                  beat.observed_visual_evidence || primaryLayer?.name || `Scene ${bIdx + 1}`,
                story_context: beat.inferred_subtext || `Story beat ${bIdx + 1}`,
                page_context_summary: beat.page_context_summary,
                character_name: characterName,
                page_narration_text: beat.page_narration_text,
                panel_narration_text: beat.panel_narration_text,
                synthesis_notes: beat.synthesis_notes,
                panel_duration_budget_sec: beat.target_panel_time_sec || estDuration,
              },
              delivery: {
                emotion: emotion as any,
                intensity: 0.6,
                speech_speed: speed,
                pause: { preset: "short", duration_ms: 300, placement: "after_first_sentence" },
                performance_notes: beat.synthesis_notes || "Emotionally grounded manga narration.",
                pronunciation_guide: [],
              },
              review_status: "DRAFT",
              generation_status: "UNQUEUED",
              generation_progress: 0,
              audio_asset_uri: null,
              previous_audio_asset_uri: null,
              generated_audio_revision: null,
              estimated_duration_sec: estDuration,
              measured_duration_sec: null,
              updated_at: new Date().toISOString(),
            };
          }
        );

        const nextChapter = {
          ...chapter,
          page_scripts: nextScripts,
          segments: updatedSegments,
          updated_at: new Date().toISOString(),
        };
        setChapter(nextChapter);
        onChapterSave?.(nextChapter);
        setSelectedSegmentId(updatedSegments[0]?.id || "");
        setPostDraftPrompt(true);
      }
    } catch (err: any) {
      console.error("AI Narration generation failed:", err);
      alert(`Narration Generation: ${err.message || "Failed to generate narration"}`);
    } finally {
      setIsDraftingNarration(false);
      setGenerationStep("");
    }
  };

  // Single-Click Voices Synthesis via Chatterbox Turbo (MIT)
  const handleSynthesizeAllVoices = async () => {
    if (!projectId) return;
    setIsSynthesizingAll(true);
    try {
      const updatedSegments = [...chapter.segments];
      for (let i = 0; i < updatedSegments.length; i++) {
        const seg = updatedSegments[i];
        try {
          const res = await api.synthesizeNarrationSegment(projectId, {
            segment_id: seg.id,
            text: seg.narration_text,
            voice: seg.speaker_name,
            emotion: seg.delivery.emotion,
            intensity: seg.delivery.intensity,
            speed: seg.delivery.speech_speed,
            text_revision: seg.text_revision,
            content_hash: seg.content_hash,
            force: true,
          });
          if (res) {
            updatedSegments[i] = {
              ...seg,
              audio_asset_uri: res.audio_url,
              measured_duration_sec: res.measured_duration_sec,
              generation_status: "READY",
              generated_audio_revision: seg.text_revision,
            };
          }
        } catch (sErr) {
          console.warn(`Segment ${seg.id} synthesis skipped:`, sErr);
        }
      }
      const nextChapter = {
        ...chapter,
        segments: updatedSegments,
        updated_at: new Date().toISOString(),
      };
      setChapter(nextChapter);
      onChapterSave?.(nextChapter);
    } finally {
      setIsSynthesizingAll(false);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden select-none">
      {/* Top Header Bar */}
      <header className="h-14 min-h-[56px] border-b border-zinc-800 bg-zinc-950 px-4 flex items-center justify-between sticky top-0 z-40 shrink-0">
        {/* Left: Branding & Chapter Breadcrumbs */}
        <div className="flex items-center gap-2.5 min-w-0 shrink">
          {onClose && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onClose}
              className="text-xs h-8 px-2.5 bg-zinc-900 border border-zinc-700 hover:bg-zinc-800 text-zinc-300 font-medium flex items-center gap-1.5 whitespace-nowrap shrink-0"
              title="Return to Story Editor"
            >
              <Icons.ArrowLeft className="w-3.5 h-3.5 shrink-0" />
              <span>Back to Story Editor</span>
            </Button>
          )}

          <div
            onClick={onClose}
            className="flex items-center gap-2 cursor-pointer group shrink-0"
            title="Return to Story Editor"
          >
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/30 group-hover:bg-indigo-500 transition-colors shrink-0">
              P
            </div>
            <div className="flex flex-col justify-center">
              <div className="font-extrabold text-sm text-white tracking-tight leading-none flex items-center gap-1.5 whitespace-nowrap">
                <h1 className="text-sm font-extrabold text-white whitespace-nowrap">Narration Studio</h1>
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800 whitespace-nowrap">
                  AI Storyteller
                </span>
              </div>
              <span className="hidden xl:block text-[10px] text-zinc-400 font-medium leading-none mt-1 whitespace-nowrap">
                Grounded Manga Narration & Emotional Voice Engine
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-zinc-800 mx-1 shrink-0 hidden md:block" />

          {/* Breadcrumb Path */}
          <div className="hidden md:flex items-center gap-1.5 text-xs text-zinc-400 font-medium min-w-0">
            <span
              className="text-zinc-400 truncate max-w-[120px] lg:max-w-[180px] whitespace-nowrap"
              title={chapter.project_title}
            >
              {chapter.project_title}
            </span>
            <span className="text-zinc-600 shrink-0">›</span>
            <span
              className="text-indigo-400 font-semibold truncate max-w-[140px] lg:max-w-[200px] whitespace-nowrap"
              title={chapter.chapter_title}
            >
              {chapter.chapter_title}
            </span>
          </div>
        </div>

        {/* Center / Right: Live Ollama Selector & High-Utility Action Buttons */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Save Status */}
          <div className="flex items-center gap-1 text-xs font-medium mr-1 shrink-0 whitespace-nowrap">
            {saveStatus === "saving" ? (
              <span className="text-amber-400 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                Saving...
              </span>
            ) : saveStatus === "unsaved" ? (
              <span className="text-zinc-400 flex items-center gap-1.5" title="Changes auto-save shortly">
                <span className="w-2 h-2 rounded-full bg-amber-500/80" />
                Unsaved
              </span>
            ) : (
              <span className="text-emerald-400 flex items-center gap-1.5">
                <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                Saved
              </span>
            )}
          </div>

          {/* Undo / Redo */}
          <div className="flex items-center gap-1 text-zinc-400 shrink-0">
            <button
              type="button"
              onClick={handleUndo}
              disabled={!historyState.canUndo}
              className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Icons.Undo className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={!historyState.canRedo}
              className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
              title="Redo (Ctrl+Y)"
            >
              <Icons.Redo className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-zinc-800 shrink-0" />

          {/* Centralized Global & Flow-Wise LLM Selector */}
          <GlobalLLMSelector
            flowId="story_narration"
            selectedProviderId={selectedProviderId}
            selectedModel={selectedModel}
            onChange={(pid, model) => {
              setSelectedProviderId(pid);
              setSelectedModel(model);
            }}
            onOpenSettings={() => setShowProviderSettingsModal(true)}
          />

          {/* 3-Tier AI Narration Multi-Action Generator */}
          <div className="relative flex items-center shrink-0">
            <button
              type="button"
              onClick={() => handleGenerateAiNarration("full")}
              disabled={isDraftingNarration}
              className="text-xs h-8 px-3 rounded-l-lg bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-bold shadow-md shadow-indigo-600/30 flex items-center gap-1.5 transition-all active:scale-95 disabled:opacity-50 whitespace-nowrap shrink-0"
              title="Execute full 3-tier narration workflow (Page Recap -> Panel Breakdown -> Harmonize & Sync)"
            >
              {isDraftingNarration ? (
                <>
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin shrink-0" />
                  <span className="whitespace-nowrap">{generationStep || "Drafting 3-Tier..."}</span>
                </>
              ) : (
                <>
                  <Icons.Sparkles className="w-3.5 h-3.5 text-indigo-200 shrink-0" />
                  <span className="whitespace-nowrap">Generate 3-Tier Narration</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => setShowTierDropdown((v) => !v)}
              disabled={isDraftingNarration}
              className="text-xs h-8 px-1.5 rounded-r-lg bg-violet-700 hover:bg-violet-600 border-l border-violet-500 text-white font-bold transition-all disabled:opacity-50 shrink-0"
              title="Select specific narration stage"
            >
              <Icons.ChevronDown className="w-3 h-3" />
            </button>

            {/* Dropdown Menu */}
            {showTierDropdown && (
              <div
                className="absolute right-0 top-10 w-64 rounded-xl bg-zinc-900 border border-zinc-700 shadow-2xl p-1.5 z-50 space-y-1 text-xs"
                onClick={() => setShowTierDropdown(false)}
              >
                <button
                  type="button"
                  onClick={() => handleGenerateAiNarration("full")}
                  className="w-full text-left p-2 rounded-lg hover:bg-indigo-950/80 text-zinc-100 hover:text-indigo-200 flex items-start gap-2"
                >
                  <Icons.Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Run Full 3-Tier Workflow</span>
                    <span className="text-[10px] text-zinc-400">Page Story (5-10 lines) ➔ Panel Micro ➔ Harmonize</span>
                  </div>
                </button>

                <div className="h-px bg-zinc-800" />

                <button
                  type="button"
                  onClick={() => handleGenerateAiNarration("page_only")}
                  className="w-full text-left p-2 rounded-lg hover:bg-amber-950/60 text-zinc-100 hover:text-amber-200 flex items-start gap-2"
                >
                  <Icons.BookOpen className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Tier 1: Page Stories (5-10 Lines)</span>
                    <span className="text-[10px] text-zinc-400">Full page image analysis with witty recap</span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleGenerateAiNarration("panel_only")}
                  className="w-full text-left p-2 rounded-lg hover:bg-emerald-950/60 text-zinc-100 hover:text-emerald-200 flex items-start gap-2"
                >
                  <Icons.Eye className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Tier 2: Panel Breakdown Only</span>
                    <span className="text-[10px] text-zinc-400">Micro visual framing & OCR extraction</span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleGenerateAiNarration("harmonize")}
                  className="w-full text-left p-2 rounded-lg hover:bg-purple-950/60 text-zinc-100 hover:text-purple-200 flex items-start gap-2"
                >
                  <Icons.Layout className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Tier 3: Compare & Harmonize</span>
                    <span className="text-[10px] text-zinc-400">Sync witty page lines with panel durations</span>
                  </div>
                </button>
              </div>
            )}
          </div>

          {/* Single-Click Voices Generation via Chatterbox Turbo */}
          <button
            type="button"
            onClick={handleSynthesizeAllVoices}
            disabled={isSynthesizingAll || chapter.segments.length === 0}
            className="text-xs h-8 px-3 rounded-lg bg-zinc-900 border border-zinc-700/80 hover:border-cyan-500/50 hover:bg-zinc-800 text-zinc-100 font-semibold shadow-sm flex items-center gap-1.5 transition-all active:scale-95 disabled:opacity-50 whitespace-nowrap shrink-0"
            title="Synthesize audio for all segments via Chatterbox Turbo (MIT)"
          >
            {isSynthesizingAll ? (
              <>
                <span className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin shrink-0" />
                <span className="whitespace-nowrap">Synthesizing...</span>
              </>
            ) : (
              <>
                <Icons.Mic className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <span className="whitespace-nowrap">Generate Voices</span>
              </>
            )}
          </button>

          {/* Confirmation Modal Launcher: Add to Timeline */}
          <button
            type="button"
            onClick={() => setTimelineModalOpen(true)}
            disabled={chapter.segments.length === 0}
            className="text-xs h-8 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold shadow-md shadow-emerald-600/30 flex items-center gap-1.5 transition-all active:scale-95 disabled:opacity-50 whitespace-nowrap shrink-0"
            title="Confirm adding narration to video timeline"
          >
            <Icons.Plus className="w-3.5 h-3.5 shrink-0" />
            <span className="whitespace-nowrap">Add to Timeline</span>
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="hover:text-rose-400 p-1 text-zinc-500 hover:bg-zinc-800 rounded-lg transition-colors ml-1 shrink-0"
              title="Close Workspace"
            >
              <Icons.X className="w-4 h-4" />
            </button>
          )}
        </div>
      </header>

      {/* 3-Tier Storyteller Workflow Progression Bar */}
      <div className="bg-zinc-900/90 border-b border-zinc-800/80 px-4 py-2 flex items-center justify-between text-xs shrink-0 select-none overflow-x-auto no-scrollbar gap-4">
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 bg-indigo-950/80 border border-indigo-800/60 px-2 py-0.5 rounded flex items-center gap-1 whitespace-nowrap shrink-0">
            <Icons.Layers className="w-3 h-3" />
            3-Tier Storyteller Flow
          </span>

          <div className="flex items-center gap-2 text-xs shrink-0">
            {/* Step 1 */}
            <div className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border whitespace-nowrap shrink-0 ${
              Object.keys(chapter.page_scripts || {}).length > 0
                ? "bg-amber-950/60 border-amber-800/80 text-amber-300 font-semibold"
                : "bg-zinc-950 border-zinc-800 text-zinc-400"
            }`}>
              <span className="w-3.5 h-3.5 rounded-full bg-amber-500/20 text-amber-300 font-mono text-[9px] flex items-center justify-center font-bold shrink-0">1</span>
              <span>Page Story (5-10 Lines)</span>
              {Object.keys(chapter.page_scripts || {}).length > 0 && (
                <Icons.Check className="w-3 h-3 text-amber-400 shrink-0" />
              )}
            </div>

            <Icons.ArrowRight className="w-3 h-3 text-zinc-600 shrink-0" />

            {/* Step 2 */}
            <div className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border whitespace-nowrap shrink-0 ${
              chapter.segments.some((s) => s.panel_narration_text)
                ? "bg-emerald-950/60 border-emerald-800/80 text-emerald-300 font-semibold"
                : "bg-zinc-950 border-zinc-800 text-zinc-400"
            }`}>
              <span className="w-3.5 h-3.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono text-[9px] flex items-center justify-center font-bold shrink-0">2</span>
              <span>Panel Breakdown</span>
              {chapter.segments.some((s) => s.panel_narration_text) && (
                <Icons.Check className="w-3 h-3 text-emerald-400 shrink-0" />
              )}
            </div>

            <Icons.ArrowRight className="w-3 h-3 text-zinc-600 shrink-0" />

            {/* Step 3 */}
            <div className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border whitespace-nowrap shrink-0 ${
              chapter.segments.some((s) => s.synthesis_notes || s.review_status === "APPROVED")
                ? "bg-purple-950/60 border-purple-800/80 text-purple-300 font-semibold"
                : "bg-zinc-950 border-zinc-800 text-zinc-400"
            }`}>
              <span className="w-3.5 h-3.5 rounded-full bg-purple-500/20 text-purple-300 font-mono text-[9px] flex items-center justify-center font-bold shrink-0">3</span>
              <span>Harmonized & Synced Script</span>
              {chapter.segments.some((s) => s.synthesis_notes || s.review_status === "APPROVED") && (
                <Icons.Check className="w-3 h-3 text-purple-400 shrink-0" />
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 whitespace-nowrap">
          {isDraftingNarration ? (
            <div className="flex items-center gap-2 text-indigo-300 font-semibold text-xs whitespace-nowrap">
              <span className="w-3 h-3 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin shrink-0" />
              <span>{generationStep || "Running 3-tier narration..."}</span>
            </div>
          ) : (
            <span className="text-[11px] text-zinc-400 whitespace-nowrap">
              {chapter.segments.length} panels • {Object.keys(chapter.page_scripts || {}).length} page stories ready
            </span>
          )}
        </div>
      </div>

      {/* Post-Draft Action Notification Banner */}
      {postDraftPrompt && (
        <div className="bg-gradient-to-r from-indigo-950/90 via-zinc-900 to-emerald-950/90 border-b border-indigo-700/60 px-4 py-2 flex items-center justify-between text-xs animate-fadeIn shrink-0">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold text-zinc-100">
              AI Narration Drafted ({chapter.segments.length} grounded beats via {selectedOllamaModel})
            </span>
            <span className="text-zinc-400 hidden sm:inline">• Ready for emotional voice synthesis and timeline integration.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setPostDraftPrompt(false);
                handleSynthesizeAllVoices();
              }}
              className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold flex items-center gap-1 shadow-sm transition-all"
            >
              <Icons.Mic className="w-3.5 h-3.5" />
              <span>Generate Voices Now</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setPostDraftPrompt(false);
                setTimelineModalOpen(true);
              }}
              className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold flex items-center gap-1 shadow-sm transition-all"
            >
              <Icons.Plus className="w-3.5 h-3.5" />
              <span>Add to Timeline</span>
            </button>
            <button
              type="button"
              onClick={() => setPostDraftPrompt(false)}
              className="p-1 rounded text-zinc-400 hover:text-white"
            >
              <Icons.X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Main Professional 3-Column Narration Workspace */}
      <div className="flex-1 grid grid-cols-12 min-h-0 overflow-hidden">
        {/* Left Column: Story & Source Context (3 cols / ~25%) */}
        <div className="col-span-12 md:col-span-3 min-h-0 h-full overflow-hidden">
          <NarrationStoryPanel
            chapter={chapter}
            selectedSegmentId={selectedSegmentId}
            filter={filter}
            onSelectSegment={(id) => setSelectedSegmentId(id)}
            onFilterChange={(updates) => setFilter((f) => ({ ...f, ...updates }))}
            onReorderSegment={handleReorderSegment}
            onAddSegment={handleAddSegment}
            onDuplicateSegment={handleDuplicateSegment}
            onDeleteSegment={handleDeleteSegment}
          />
        </div>

        {/* Center Column: Story Script Editor (6 cols / ~50%) */}
        <div className="col-span-12 md:col-span-6 min-h-0 h-full overflow-y-auto flex flex-col border-r border-zinc-800/90 bg-zinc-950">
          <NarrationSegmentEditor
            segment={selectedSegment}
            previousSegment={previousSegment}
            nextSegment={nextSegment}
            characters={chapter.characters}
            projectId={projectId}
            pageScript={
              chapter.page_scripts?.[selectedSegment?.source_context?.page_id || ""] ||
              chapter.page_scripts?.[String(selectedSegment?.source_context?.page_number || 1)] ||
              null
            }
            allPageScripts={chapter.page_scripts}
            onUpdateSegment={handleUpdateSegment}
            onDuplicateSegment={handleDuplicateSegment}
            onDeleteSegment={handleDeleteSegment}
            onSplitSegment={handleSplitSegment}
            onHarmonizeSegment={async () => {
              await handleGenerateAiNarration("harmonize");
            }}
            onSynthesizeSceneVoice={async (seg) => {
              if (!projectId) return;
              try {
                const res = await api.synthesizeNarrationSegment(projectId, {
                  segment_id: seg.id,
                  text: seg.narration_text,
                  voice: seg.speaker_name,
                  emotion: seg.delivery.emotion,
                  intensity: seg.delivery.intensity,
                  speed: seg.delivery.speech_speed,
                  text_revision: seg.text_revision,
                  content_hash: seg.content_hash,
                  force: true,
                });
                if (res) {
                  handleUpdateSegment({
                    audio_asset_uri: res.audio_url,
                    measured_duration_sec: res.measured_duration_sec,
                    generation_status: "READY",
                    generated_audio_revision: seg.text_revision,
                  });
                }
              } catch (err: any) {
                console.error("Synthesize segment failed:", err);
                alert(`Voice Synthesis: ${err.message || "Failed"}`);
              }
            }}
            onAddToTimeline={(seg: NarrationSegment) => {
              onAddToTimeline?.("selected", seg.id);
            }}
            className="flex-1"
          />
        </div>

        {/* Right Column: Voice & Delivery Inspector (3 cols / ~25%) */}
        <div className="col-span-12 md:col-span-3 min-h-0 h-full overflow-y-auto bg-zinc-950 p-3 space-y-3.5 select-none">
          {selectedSegment ? (
            <>
              {/* Speaker & Voice Assignment Bar */}
              <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                    Speaker & Voice
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowVoiceManagerModal(true)}
                    className="text-[10px] text-indigo-400 hover:text-indigo-300 font-semibold underline"
                  >
                    Edit Casting
                  </button>
                </div>

                {/* Speaker Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 font-medium block">
                    Speaker Assignment:
                  </label>
                  <select
                    value={selectedSegment.speaker_id}
                    onChange={(e) => {
                      const newChar = chapter.characters.find((c) => c.id === e.target.value);
                      if (newChar) {
                        handleUpdateSegment({
                          speaker_id: newChar.id,
                          speaker_name: newChar.name,
                          speaker_type: newChar.role === "NARRATOR" ? "NARRATOR" : "CHARACTER",
                          voice_profile_id: newChar.default_voice_profile_id,
                        });
                      }
                    }}
                    className="w-full p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer"
                  >
                    {chapter.characters.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.role})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Voice Profile Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-400 font-medium block">
                    Voice Profile:
                  </label>
                  <select
                    value={selectedSegment.voice_profile_id}
                    onChange={(e) => {
                      const isOverride = selectedCharacter ? e.target.value !== selectedCharacter.default_voice_profile_id : true;
                      handleUpdateSegment({
                        voice_profile_id: e.target.value,
                        has_custom_voice_override: isOverride,
                        generation_status:
                          selectedSegment.generation_status === "READY"
                            ? "OUTDATED"
                            : selectedSegment.generation_status,
                      });
                    }}
                    className="w-full p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer"
                  >
                    {chapter.voice_profiles.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} ({v.model_family})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Emotional Delivery Editor */}
              <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800">
                <EmotionDeliveryControls
                  delivery={selectedSegment.delivery}
                  onChangeDelivery={(updates) => {
                    handleUpdateSegment({
                      delivery: { ...selectedSegment.delivery, ...updates },
                      generation_status:
                        selectedSegment.generation_status === "READY"
                          ? "OUTDATED"
                          : selectedSegment.generation_status,
                    });
                  }}
                />
              </div>

              {/* Audio Preview Player */}
              <AudioPreviewPlayer
                segment={selectedSegment}
                voiceProfile={selectedVoiceProfile}
                onApproveAudio={() => {
                  handleUpdateSegment({ review_status: "APPROVED" });
                }}
                onRequestRetake={() => {
                  handleUpdateSegment({
                    generation_status: "OUTDATED",
                    review_status: "NEEDS_REVIEW",
                  });
                }}
              />

              {/* Real Local Generation Job Interface */}
              <NarrationJobQueue
                segment={selectedSegment}
                allSegments={chapter.segments}
                projectId={chapter.project_id}
                onUpdateSegment={handleUpdateSegment}
                onBatchUpdateSegments={handleBatchUpdateSegments}
              />
            </>
          ) : (
            <div className="p-8 text-center text-zinc-500 text-xs">
              Select a segment to inspect voice delivery
            </div>
          )}
        </div>
      </div>

      {/* Character Voice Manager Modal */}
      {showVoiceManagerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="max-w-3xl w-full">
            <CharacterVoiceManager
              characters={chapter.characters}
              voiceProfiles={chapter.voice_profiles}
              segments={chapter.segments}
              selectedCharacterId={selectedSegment?.speaker_id}
              onUpdateCharacter={handleUpdateCharacter}
              onApplyVoiceToAllSegments={handleApplyVoiceToAllSegments}
              onClose={() => setShowVoiceManagerModal(false)}
            />
          </div>
        </div>
      )}

      {/* Export Timeline Integration Contract Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                  <span>Export Chapter 3 Timeline Contract</span>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
                    Schema 5A-v2
                  </span>
                </h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Pre-formatted JSON ready for ingestion by future Chapter 3 timeline adapters
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowExportModal(false)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded-lg hover:bg-zinc-800 transition-colors"
              >
                <Icons.X className="w-4 h-4" />
              </button>

            </div>

            <div className="space-y-2">
              <span className="text-xs font-semibold text-zinc-300">
                Generated Serializable Payload ({timelineContract.clips.length} Clips):
              </span>
              <pre className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-[11px] font-mono text-zinc-300 max-h-64 overflow-y-auto leading-relaxed select-all">
                {JSON.stringify(timelineContract, null, 2)}
              </pre>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-zinc-800 text-xs">
              <span className="text-zinc-500 text-[11px]">
                Contract verified: Compatible with Chapter 3 Timeline Clip schema
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard?.writeText(JSON.stringify(timelineContract, null, 2));
                    alert("Contract JSON copied to clipboard!");
                  }}
                  className="text-xs h-8"
                >
                  Copy JSON
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setShowExportModal(false)}
                  className="text-xs h-8 bg-indigo-600 hover:bg-indigo-500"
                >
                  Done
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* "May I add this narration to the timeline?" Confirmation Modal */}
      {timelineModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
          <div className="bg-zinc-900 border border-zinc-750 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl ring-1 ring-white/10">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-emerald-950/80 border border-emerald-700/60 flex items-center justify-center text-emerald-400 shadow-inner">
                  <Icons.Mic className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-100 leading-tight">
                    Add Narration to Timeline
                  </h3>
                  <span className="text-[11px] text-zinc-400">
                    May I add this narration to the timeline?
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setTimelineModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded-lg hover:bg-zinc-800 transition-colors"
                title="Close (Esc)"
              >
                <Icons.X className="w-4 h-4" />
              </button>

            </div>

            <p className="text-xs text-zinc-300 leading-relaxed">
              Choose how you would like to synchronize your narrative voice takes into the active video project:
            </p>

            <div className="space-y-2.5 pt-1">
              <button
                type="button"
                onClick={() => {
                  setTimelineModalOpen(false);
                  onAddToTimeline?.("all");
                }}
                className="w-full text-left p-3.5 rounded-xl bg-zinc-950 hover:bg-indigo-950/50 border border-zinc-800 hover:border-indigo-500/80 transition-all group flex items-start gap-3.5 shadow-sm"
              >
                <div className="w-9 h-9 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform">
                  <Icons.Sparkles className="w-4 h-4 text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-indigo-300 flex items-center justify-between">
                    <span>Auto-Sync All Segments to Scenes</span>
                    <span className="text-[10px] text-zinc-500 font-mono font-normal">Enter ↵</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Synchronizes all {chapter.segments.length} narration clips directly into corresponding scenes across the timeline with ripple timing.
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setTimelineModalOpen(false);
                  onAddToTimeline?.("selected", selectedSegmentId);
                }}
                className="w-full text-left p-3.5 rounded-xl bg-zinc-950 hover:bg-cyan-950/50 border border-zinc-800 hover:border-cyan-500/80 transition-all group flex items-start gap-3.5 shadow-sm"
              >
                <div className="w-9 h-9 rounded-lg bg-cyan-600/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform">
                  <Icons.Play className="w-4 h-4 text-cyan-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold text-zinc-100 group-hover:text-cyan-300">
                    Insert Selected Segment at Playhead
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5 leading-normal">
                    Places segment #{selectedSegment?.sequence || 1} (&ldquo;{selectedSegment?.scene_title || "Scene"}&rdquo;) at the current timeline playhead cursor.
                  </div>
                </div>
              </button>

              {/* Option 3: Target Specific Timeline Scene */}
              {scenes && scenes.length > 0 && (
                <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2">
                  <div className="flex items-center justify-between text-xs font-bold text-zinc-200">
                    <span className="flex items-center gap-1.5">
                      <Icons.Layers className="w-3.5 h-3.5 text-emerald-400" />
                      Attach Selected to Specific Scene
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono font-normal">Direct Target</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      value={targetSceneId}
                      onChange={(e) => setTargetSceneId(e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                    >
                      {scenes.map((sc, scIdx) => (
                        <option key={sc.id} value={sc.id}>
                          Scene #{sc.sequence || scIdx + 1}: {sc.title || `Scene ${scIdx + 1}`}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => {
                        setTimelineModalOpen(false);
                        // Also update segment's scene_id
                        handleUpdateSegment({ scene_id: targetSceneId });
                        onAddToTimeline?.("selected", selectedSegmentId);
                      }}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold h-8 px-3 shrink-0"
                    >
                      Attach
                    </Button>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-3 border-t border-zinc-800/80">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setTimelineModalOpen(false)}
                className="text-xs h-8 px-4 font-semibold"
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Ollama Real-Time Engine & Model Diagnostics Guide Modal */}
      {showOllamaGuideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fadeIn">
          <div className="bg-zinc-900 border border-zinc-750 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl ring-1 ring-white/10 max-h-[85vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-950/80 border border-indigo-700/60 flex items-center justify-center text-indigo-400 shadow-inner">
                  <Icons.Cpu className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                    <span>Ollama Real-Time Engine & Models</span>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${isOllamaOnline ? "bg-emerald-950 text-emerald-300 border border-emerald-800" : "bg-rose-950 text-rose-300 border border-rose-800"}`}>
                      {isOllamaOnline ? "127.0.0.1:11434 Connected" : "Ollama Offline"}
                    </span>
                  </h3>
                  <span className="text-[11px] text-zinc-400">
                    Multimodal vision understanding & cinematic storytelling model inventory
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowOllamaGuideModal(false)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded-lg hover:bg-zinc-800 transition-colors"
                title="Close (Esc)"
              >
                <Icons.X className="w-4 h-4" />
              </button>
            </div>

            {/* Guidance Explainer */}
            <div className="p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-800/50 text-xs text-zinc-300 space-y-1.5 leading-relaxed">
              <h4 className="font-bold text-indigo-300 flex items-center gap-1.5 text-xs">
                <Icons.Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                How PanelFlow Works With Ollama Models
              </h4>
              <p className="text-[11px]">
                <strong>1. Multimodal Vision:</strong> Ollama vision models inspect manga panels directly to observe character presence, actions, and atmosphere.
              </p>
              <p className="text-[11px]">
                <strong>2. Grounded Narration:</strong> Translates observed actions and OCR dialogue bubbles into emotionally paced cinematic motion comic narration.
              </p>
              <p className="text-[11px]">
                <strong>3. Voice Generation:</strong> Generated lines are converted to natural audio via local Chatterbox Turbo (MIT) on your GPU.
              </p>
            </div>

            {/* Installed Models Grid */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              <h4 className="text-xs font-bold text-zinc-200 uppercase tracking-wider">
                Installed Models ({ollamaDetailedModels.length || ollamaModels.length})
              </h4>

              <div className="grid grid-cols-1 gap-2.5">
                {(ollamaDetailedModels.length > 0
                  ? ollamaDetailedModels
                  : ollamaModels.map((m) => ({
                      name: m,
                      supports_vision:
                        m.includes("qwen3.5") ||
                        m.includes("gemma4") ||
                        m.includes("qwen3.6") ||
                        m.includes("vision"),
                    }))
                ).map((model: any) => {
                  const name = model.name || model;
                  const isSelected = selectedOllamaModel === name;
                  const supportsVision =
                    model.supports_vision ||
                    name.includes("qwen3.5") ||
                    name.includes("gemma4") ||
                    name.includes("qwen3.6") ||
                    name.includes("vision");
                  const isCoder = name.includes("coder");

                  return (
                    <div
                      key={name}
                      className={`p-3 rounded-xl border flex items-center justify-between gap-3 transition-all ${
                        isSelected
                          ? "bg-zinc-850 border-indigo-500 shadow-md ring-1 ring-indigo-500/30"
                          : "bg-zinc-950 border-zinc-800 hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center font-mono font-bold text-xs shrink-0 ${
                            isSelected ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-300"
                          }`}
                        >
                          {name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-zinc-100 truncate">
                              {name}
                            </span>
                            {supportsVision && (
                              <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                                Vision Capable
                              </span>
                            )}
                            {!isCoder && (
                              <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                                Narration
                              </span>
                            )}
                            {isCoder && (
                              <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800">
                                Code
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-zinc-500 font-mono block mt-0.5">
                            {model.details?.parameter_size ? `Params: ${model.details.parameter_size} • ` : ""}
                            {model.details?.quantization_level ? `Quant: ${model.details.quantization_level} • ` : ""}
                            {supportsVision ? "Supports vision panel inspection" : "Text & script generation"}
                          </span>
                        </div>
                      </div>

                      <div className="shrink-0">
                        {isSelected ? (
                          <span className="px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-bold text-xs flex items-center gap-1 shadow-sm">
                            <Icons.Check className="w-3.5 h-3.5" />
                            Active Model
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedOllamaModel(name);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold text-xs border border-zinc-700 transition-colors"
                          >
                            Select Model
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="border-t border-zinc-800 pt-3 flex items-center justify-between text-xs">
              <span className="text-zinc-500 font-mono text-[11px]">
                Install additional models: <code className="text-zinc-300">ollama run qwen3.5:9b</code>
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowOllamaGuideModal(false)}
                className="text-xs h-8 px-4 font-semibold"
              >
                Done
              </Button>
            </div>
          </div>
        </div>
      )}

      {showProviderSettingsModal && (
        <ProviderHealthModal
          open={showProviderSettingsModal}
          onClose={() => {
            setShowProviderSettingsModal(false);
          }}
          initialTab="global"
        />
      )}
    </div>
  );
};
