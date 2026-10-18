import React, { useState, useMemo } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import {
  type NarrationSegment,
  type CharacterProfile,
  type ReviewStatus,
  type ContinuityCheckResult,
  computeContentHash,
} from "./NarrationStudio.types";

interface NarrationSegmentEditorProps {
  segment: NarrationSegment | null;
  previousSegment: NarrationSegment | null;
  nextSegment: NarrationSegment | null;
  characters: CharacterProfile[];
  projectId?: string;
  onUpdateSegment: (updates: Partial<NarrationSegment>) => void;
  onDuplicateSegment: (segmentId: string) => void;
  onDeleteSegment: (segmentId: string) => void;
  onSplitSegment: (segmentId: string, splitIndex: number) => void;
  onSynthesizeSceneVoice?: (segment: NarrationSegment) => void;
  onAddToTimeline?: (segment: NarrationSegment) => void;
  isSynthesizing?: boolean;
  className?: string;
}

export const NarrationSegmentEditor: React.FC<NarrationSegmentEditorProps> = ({
  segment,
  previousSegment,
  nextSegment,
  characters,
  projectId = "",
  onUpdateSegment,
  onDuplicateSegment,
  onDeleteSegment,
  onSplitSegment,
  onSynthesizeSceneVoice,
  onAddToTimeline,
  isSynthesizing = false,
  className = "",
}) => {
  // Typography presentation settings
  const [fontFamily, setFontFamily] = useState<"sans" | "serif">("serif");
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");
  const [showContinuityDetails, setShowContinuityDetails] = useState<boolean>(false);

  // Character mapping
  const currentCharacter = useMemo(() => {
    if (!segment) return null;
    return characters.find((c) => c.id === segment.speaker_id) || null;
  }, [segment, characters]);

  // Live calculation of word count and reading duration
  const wordCount = useMemo(() => {
    if (!segment) return 0;
    return segment.narration_text.trim().split(/\s+/).filter(Boolean).length;
  }, [segment?.narration_text]);

  const estimatedDuration = useMemo(() => {
    if (!segment) return 0;
    // Standard conversational narration rate: ~140 words per minute (2.33 words/sec)
    // Adjusted by speech speed factor
    const baseWps = 2.33;
    const speed = segment.delivery.speech_speed || 1.0;
    const effectiveWps = baseWps * speed;
    const pauseBonus = (segment.delivery.pause?.duration_ms || 0) / 1000;
    const calculated = (wordCount / (effectiveWps || 1)) + pauseBonus;
    return Math.max(1.2, Math.round(calculated * 10) / 10);
  }, [wordCount, segment?.delivery.speech_speed, segment?.delivery.pause]);

  // Continuity analysis check between adjacent segments
  const continuityAlert: ContinuityCheckResult | null = useMemo(() => {
    if (!segment) return null;

    // Check 1: Sudden emotional jump
    if (previousSegment) {
      const prevEmo = previousSegment.delivery.emotion;
      const curEmo = segment.delivery.emotion;
      if (
        (prevEmo === "Happy" && curEmo === "Fearful") ||
        (prevEmo === "Whispering" && curEmo === "Excited") ||
        (prevEmo === "Fearful" && curEmo === "Happy")
      ) {
        return {
          has_issue: true,
          severity: "warning",
          message: `Sharp tone transition from ${previousSegment.speaker_name}'s "${prevEmo}" to "${curEmo}".`,
          suggested_action: "Consider smoothing the transition or adding a pause.",
          previous_speaker: previousSegment.speaker_name,
          previous_emotion: prevEmo,
        };
      }

      // Check 2: Repetitive starting words
      const prevStart = previousSegment.narration_text.trim().split(/\s+/)[0]?.toLowerCase();
      const curStart = segment.narration_text.trim().split(/\s+/)[0]?.toLowerCase();
      if (prevStart && curStart && prevStart === curStart && prevStart.length > 3) {
        return {
          has_issue: true,
          severity: "info",
          message: `Consecutive segments start with the same word ("${curStart}").`,
          suggested_action: "Vary the sentence structure for better storytelling flow.",
          previous_speaker: previousSegment.speaker_name,
        };
      }
    }

    // Check 3: Missing speech pacing instruction
    if (wordCount > 35 && (!segment.delivery.pause || segment.delivery.pause.preset === "none")) {
      return {
        has_issue: true,
        severity: "info",
        message: "Long narration segment without designated pauses.",
        suggested_action: "Add an intentional breath pause to improve TTS pacing.",
      };
    }

    return null;
  }, [segment, previousSegment, wordCount]);

  // Handle text edit: increments text_revision, updates content_hash, and marks audio OUTDATED while preserving previous take
  const handleTextChange = (newText: string) => {
    if (!segment) return;
    const newRevision = (segment.text_revision || 1) + 1;
    const newHash = computeContentHash(
      newText,
      segment.delivery.emotion,
      segment.delivery.speech_speed,
      segment.delivery.pause?.preset
    );

    onUpdateSegment({
      narration_text: newText,
      text_revision: newRevision,
      content_hash: newHash,
      estimated_duration_sec: estimatedDuration,
      // Decision 2: Mark audio OUTDATED while preserving previous audio take
      generation_status:
        segment.generation_status === "READY" ? "OUTDATED" : segment.generation_status,
      previous_audio_asset_uri:
        segment.audio_asset_uri || segment.previous_audio_asset_uri || null,
      audio_asset_uri: null, // Active generated take cleared until regenerated
      updated_at: new Date().toISOString(),
    });
  };

  if (!segment) {
    return (
      <div className={`flex flex-col items-center justify-center p-12 text-zinc-500 h-full ${className}`}>
        <span className="text-4xl mb-3">🎙️</span>
        <h3 className="text-base font-semibold text-zinc-300">No Story Segment Selected</h3>
        <p className="text-xs text-zinc-400 mt-1 max-w-sm text-center">
          Select a story segment from the left panel to review its manga context, edit the narration script, and direct emotional delivery.
        </p>
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full bg-zinc-950 select-none overflow-y-auto ${className}`}>
      {/* Segment Header */}
      <div className="p-4 border-b border-zinc-800/80 bg-zinc-900/50 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-md bg-indigo-600/90 text-white font-mono font-bold text-xs shadow-sm">
              #{segment.sequence}
            </span>
            <div className="flex flex-col">
              <span className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
                <span>{segment.scene_title || `Scene ${segment.sequence}`}</span>
                <span className="text-zinc-600">•</span>
                <span className="text-zinc-400 font-normal">
                  {segment.source_context.panel_labels?.join(", ") || `Page ${segment.source_context.page_number}`}
                </span>
              </span>
              <span className="text-[11px] text-zinc-400">
                Speaker:{" "}
                <strong className="text-zinc-200">{segment.speaker_name}</strong> ({segment.speaker_type})
              </span>
            </div>
          </div>

          {/* Review State Buttons */}
          <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800/80">
            {(["DRAFT", "NEEDS_REVIEW", "APPROVED"] as ReviewStatus[]).map((status) => {
              const isActive = segment.review_status === status;
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => onUpdateSegment({ review_status: status })}
                  className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
                    isActive
                      ? status === "APPROVED"
                        ? "bg-emerald-600 text-white shadow-sm"
                        : status === "NEEDS_REVIEW"
                        ? "bg-amber-600 text-white shadow-sm"
                        : "bg-zinc-700 text-white shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                  }`}
                >
                  {status === "APPROVED"
                    ? "✓ Approved"
                    : status === "NEEDS_REVIEW"
                    ? "⚠ Needs Review"
                    : "Draft"}
                </button>
              );
            })}
          </div>
        </div>

        {/* Decision 1: Smart Scene Binding & Timing Offset */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-zinc-950/80 border border-zinc-800 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">
              Scene Binding:
            </span>
            <button
              type="button"
              onClick={() => onUpdateSegment({ linked_to_scene: !segment.linked_to_scene })}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold border transition-colors ${
                segment.linked_to_scene
                  ? "bg-indigo-950 text-indigo-300 border-indigo-800 shadow-sm"
                  : "bg-zinc-900 text-zinc-400 border-zinc-700"
              }`}
              title="Toggle between anchored to scene start vs unlinked floating narration"
            >
              {segment.linked_to_scene ? "🔗 Linked to Scene Start" : "🔓 Unlinked (Floating)"}
            </button>
          </div>

          <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
            <span>Scene Offset:</span>
            <input
              type="number"
              step="0.1"
              min="-10"
              max="60"
              value={segment.scene_offset_sec ?? 0}
              onChange={(e) => onUpdateSegment({ scene_offset_sec: parseFloat(e.target.value) || 0 })}
              className="w-14 bg-zinc-900 border border-zinc-700 rounded px-1.5 py-0.5 font-mono text-zinc-200 text-center focus:outline-none focus:border-indigo-500"
            />
            <span className="text-zinc-500 font-mono text-[10px]">sec</span>
          </div>
        </div>

        {/* Continuity Alert Banner (if any) */}
        {continuityAlert && (
          <div
            className={`flex items-start justify-between p-2.5 rounded-lg border text-xs ${
              continuityAlert.severity === "warning"
                ? "bg-amber-950/40 border-amber-800/80 text-amber-300"
                : "bg-indigo-950/40 border-indigo-800/80 text-indigo-300"
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="text-sm mt-0.5">
                {continuityAlert.severity === "warning" ? "⚠️" : "💡"}
              </span>
              <div>
                <p className="font-semibold">{continuityAlert.message}</p>
                {continuityAlert.suggested_action && (
                  <p className="text-[11px] opacity-80 mt-0.5">
                    Suggestion: {continuityAlert.suggested_action}
                  </p>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowContinuityDetails((v) => !v)}
              className="text-[10px] underline font-semibold opacity-75 hover:opacity-100 shrink-0 ml-2"
            >
              {showContinuityDetails ? "Hide Flow" : "Flow Context"}
            </button>
          </div>
        )}

        {/* Expandable Adjacent Flow Details */}
        {showContinuityDetails && (
          <div className="p-3 bg-zinc-950 rounded-lg border border-zinc-800/80 space-y-2 text-xs">
            <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider">
              Adjacent Story Continuity Flow
            </span>
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                <span className="text-[10px] text-zinc-400 block font-semibold mb-0.5">
                  ← Previous Segment {previousSegment ? `#${previousSegment.sequence} (${previousSegment.speaker_name})` : "(Beginning)"}
                </span>
                <p className="text-zinc-300 italic line-clamp-2">
                  {previousSegment?.narration_text || "Opening chapter introduction."}
                </p>
                {previousSegment && (
                  <span className="text-[9px] text-indigo-400 block mt-1 font-mono">
                    Tone: {previousSegment.delivery.emotion} ({Math.round(previousSegment.delivery.intensity * 100)}%)
                  </span>
                )}
              </div>

              <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                <span className="text-[10px] text-zinc-400 block font-semibold mb-0.5">
                  Next Segment → {nextSegment ? `#${nextSegment.sequence} (${nextSegment.speaker_name})` : "(End of Chapter)"}
                </span>
                <p className="text-zinc-300 italic line-clamp-2">
                  {nextSegment?.narration_text || "End of chapter climax."}
                </p>
                {nextSegment && (
                  <span className="text-[9px] text-indigo-400 block mt-1 font-mono">
                    Tone: {nextSegment.delivery.emotion} ({Math.round(nextSegment.delivery.intensity * 100)}%)
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main Working Area: Script Editor */}
      <div className="p-5 space-y-4 flex-1">
        {/* Editor Controls Ribbon */}
        <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 text-xs">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
              Narration Script
            </span>

            {/* Typography Selector */}
            <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setFontFamily("sans")}
                className={`px-1.5 py-0.5 rounded font-sans ${
                  fontFamily === "sans" ? "bg-zinc-800 text-white font-bold" : "text-zinc-400"
                }`}
              >
                Sans
              </button>
              <button
                type="button"
                onClick={() => setFontFamily("serif")}
                className={`px-1.5 py-0.5 rounded font-serif ${
                  fontFamily === "serif" ? "bg-zinc-800 text-white font-bold" : "text-zinc-400"
                }`}
              >
                Serif
              </button>
              <span className="text-zinc-700">|</span>
              <button
                type="button"
                onClick={() => setFontSize("sm")}
                className={`px-1 py-0.5 rounded ${
                  fontSize === "sm" ? "bg-zinc-800 text-white font-bold" : "text-zinc-400"
                }`}
              >
                A-
              </button>
              <button
                type="button"
                onClick={() => setFontSize("lg")}
                className={`px-1 py-0.5 rounded ${
                  fontSize === "lg" ? "bg-zinc-800 text-white font-bold" : "text-zinc-400"
                }`}
              >
                A+
              </button>
            </div>
          </div>

          {/* Word Count & Live Runtime Stats */}
          <div className="flex items-center gap-3 text-xs font-mono text-zinc-400">
            <span>{wordCount} words</span>
            <span>•</span>
            <span className="text-indigo-400 font-semibold">~{estimatedDuration}s audio runtime</span>
          </div>
        </div>

        {/* Rich Narration Script Textarea */}
        <div className="relative group">
          <textarea
            value={segment.narration_text}
            onChange={(e) => handleTextChange(e.target.value)}
            rows={5}
            className={`w-full p-4 rounded-xl bg-zinc-900/90 border border-zinc-700/80 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 leading-relaxed transition-all shadow-inner ${
              fontFamily === "serif" ? "font-serif" : "font-sans"
            } ${
              fontSize === "sm"
                ? "text-sm"
                : fontSize === "lg"
                ? "text-lg"
                : "text-base"
            }`}
            placeholder="Type or refine narration script for this scene..."
          />
          {segment.generation_status === "OUTDATED" && (
            <div className="absolute top-3 right-3 bg-amber-950/90 border border-amber-800/80 text-amber-300 text-[10px] font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              Script modified (Audio outdated)
            </div>
          )}
        </div>

        {/* Story Continuity Notes & Character Context */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-xs font-bold text-zinc-400">
            <span className="uppercase tracking-wider">Story Continuity & Performance Notes</span>
            <span className="text-[10px] font-normal text-zinc-500">
              Preserved across narration lifecycle
            </span>
          </div>

          <textarea
            value={segment.continuity_notes || ""}
            onChange={(e) => onUpdateSegment({ continuity_notes: e.target.value })}
            rows={2}
            className="w-full p-3 rounded-lg bg-zinc-900/60 border border-zinc-800 text-xs text-zinc-300 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
            placeholder="Add storytelling notes, character motivations, or continuity reminders..."
          />
        </div>

        {/* Action Buttons: Split at cursor, Duplicate, Delete */}
        <div className="flex items-center justify-between pt-3 border-t border-zinc-800/80 text-xs">
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onDuplicateSegment(segment.id)}
              className="text-xs h-8 border border-zinc-700"
            >
              <Icons.Copy className="w-3.5 h-3.5 mr-1 text-zinc-400" />
              Duplicate Segment
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const halfway = Math.floor(segment.narration_text.length / 2);
                onSplitSegment(segment.id, halfway);
              }}
              className="text-xs h-8 border border-zinc-700"
              title="Split this segment into two consecutive story segments"
            >
              <Icons.Scissors className="w-3.5 h-3.5 mr-1 text-zinc-400" />
              Split Segment
            </Button>
          </div>

          <button
            type="button"
            onClick={() => {
              if (confirm(`Delete Segment #${segment.sequence}? This action can be undone with Ctrl+Z.`)) {
                onDeleteSegment(segment.id);
              }
            }}
            className="flex items-center gap-1 text-xs text-zinc-400 hover:text-rose-400 px-2 py-1.5 rounded hover:bg-zinc-900 transition-colors"
          >
            <Icons.Trash className="w-3.5 h-3.5" />
            <span>Delete</span>
          </button>
        </div>
      </div>
    </div>
  );
};
