import React, { useState, useEffect, useCallback, useMemo } from "react";
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
import { NarrationJobQueue } from "./NarrationJobQueue";

export const NarrationStudio: React.FC<NarrationStudioProps> = ({
  initialChapter,
  onChapterSave,
  onSegmentApproved,
  onExportTimelineContract,
  onClose,
}) => {
  // Main Chapter State initialized with prop or rich mock chapter
  const [chapter, setChapter] = useState<NarrationChapter>(
    () => initialChapter || MOCK_CHAPTER
  );

  // Active Selected Segment ID
  const [selectedSegmentId, setSelectedSegmentId] = useState<string>(() => {
    return (initialChapter || MOCK_CHAPTER).segments[0]?.id || "";
  });

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
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");

  // Undo / Redo History Stacks
  const [history, setHistory] = useState<NarrationChapter[]>([]);
  const [future, setFuture] = useState<NarrationChapter[]>([]);

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
        if (trackHistory && next !== prev) {
          setHistory((h) => [...h.slice(-40), prev]);
          setFuture([]);
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
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((h) => h.slice(0, -1));
    setFuture((f) => [chapter, ...f]);
    setChapter(previous);
    setSaveStatus("saved");
  }, [history, chapter]);

  const handleRedo = useCallback(() => {
    if (future.length === 0) return;
    const next = future[0];
    setFuture((f) => f.slice(1));
    setHistory((h) => [...h, chapter]);
    setChapter(next);
    setSaveStatus("saved");
  }, [future, chapter]);

  // Keyboard shortcut listener (Ctrl+Z, Ctrl+Y, ArrowUp, ArrowDown)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Do not trigger global shortcuts if typing inside an active input or textarea
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA";

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        if (e.shiftKey) {
          e.preventDefault();
          handleRedo();
        } else {
          e.preventDefault();
          handleUndo();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
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

  return (
    <div className="flex flex-col h-screen w-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden select-none">
      {/* Top Header Bar */}
      <header className="h-13 border-b border-zinc-800 bg-zinc-950 px-4 flex items-center justify-between sticky top-0 z-40 shrink-0">
        {/* Left: Branding & Chapter Breadcrumbs */}
        <div className="flex items-center gap-3">
          <div
            onClick={onClose}
            className="flex items-center gap-2 cursor-pointer group"
            title="Return to Projects Dashboard"
          >
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/30 group-hover:bg-indigo-500 transition-colors">
              P
            </div>
            <div>
              <div className="font-extrabold text-sm text-white tracking-tight leading-none flex items-center gap-1.5">
                <span>PanelFlow Studio</span>
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
                  Chapter 5A
                </span>
              </div>
              <span className="text-[10px] text-zinc-400 font-medium leading-none block mt-0.5">
                AI Narration & Storytelling Workspace
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-zinc-800 mx-1" />

          {/* Breadcrumb Path */}
          <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-medium">
            <span className="text-zinc-400">{chapter.project_title}</span>
            <span className="text-zinc-600">›</span>
            <span className="text-indigo-400 font-semibold">{chapter.chapter_title}</span>
          </div>
        </div>

        {/* Center / Right: Auto-save, Undo/Redo, View Toggles & Export */}
        <div className="flex items-center gap-3">
          {/* Save Status */}
          <div className="flex items-center gap-1 text-xs font-medium mr-1">
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
          <div className="flex items-center gap-1 text-zinc-400">
            <button
              type="button"
              onClick={handleUndo}
              disabled={history.length === 0}
              className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Icons.Undo className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={future.length === 0}
              className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
              title="Redo (Ctrl+Y)"
            >
              <Icons.Redo className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-zinc-800" />

          {/* Mode Switch: Editor vs Quality Matrix */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setCenterMode("editor")}
              className={`px-2.5 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                centerMode === "editor"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Script Editor
            </button>
            <button
              type="button"
              onClick={() => setCenterMode("quality_review")}
              className={`px-2.5 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                centerMode === "quality_review"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Quality Matrix
            </button>
          </div>

          <div className="h-4 w-px bg-zinc-800" />

          {/* Character Voice Casting Modal Launcher */}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowVoiceManagerModal(true)}
            className="text-xs h-8 px-3 border border-zinc-700 hover:border-zinc-500"
          >
            👥 Character Casting
          </Button>

          {/* Export Timeline Contract Button */}
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setShowExportModal(true);
              onExportTimelineContract?.(timelineContract);
            }}
            className="text-xs h-8 px-3.5 bg-indigo-600 hover:bg-indigo-500 font-bold shadow-md shadow-indigo-600/30"
          >
            Export Contract
          </Button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="hover:text-rose-400 p-1 text-zinc-500 ml-1"
              title="Close Workspace"
            >
              ✕
            </button>
          )}
        </div>
      </header>

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

        {/* Center Column: Story Script Editor & Quality Review (6 cols / ~50%) */}
        <div className="col-span-12 md:col-span-6 min-h-0 h-full overflow-y-auto flex flex-col border-r border-zinc-800/90 bg-zinc-950">
          <NarrationSegmentEditor
            segment={selectedSegment}
            previousSegment={previousSegment}
            nextSegment={nextSegment}
            characters={chapter.characters}
            onUpdateSegment={handleUpdateSegment}
            onDuplicateSegment={handleDuplicateSegment}
            onDeleteSegment={handleDeleteSegment}
            onSplitSegment={handleSplitSegment}
            className="flex-1"
          />

          {/* If Quality Review Matrix is toggled, display the 4-layer comparison */}
          {selectedSegment && centerMode === "quality_review" && (
            <NarrationReviewPanel
              segment={selectedSegment}
              characters={chapter.characters}
              onUpdateSegment={handleUpdateSegment}
            />
          )}
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

              {/* Simulated Generation Job Interface */}
              <NarrationJobQueue
                segment={selectedSegment}
                allSegments={chapter.segments}
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
                className="text-zinc-400 hover:text-zinc-200"
              >
                ✕
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
    </div>
  );
};
