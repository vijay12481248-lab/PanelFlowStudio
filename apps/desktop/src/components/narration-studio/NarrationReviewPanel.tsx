import React, { useState } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import type {
  NarrationSegment,
  CharacterProfile,
  PronunciationItem,
} from "./NarrationStudio.types";

interface NarrationReviewPanelProps {
  segment: NarrationSegment;
  characters: CharacterProfile[];
  onUpdateSegment: (updates: Partial<NarrationSegment>) => void;
  className?: string;
}

export const NarrationReviewPanel: React.FC<NarrationReviewPanelProps> = ({
  segment,
  characters,
  onUpdateSegment,
  className = "",
}) => {
  const [activeTab, setActiveTab] = useState<"matrix" | "pronunciation" | "ai_polish">("matrix");
  const [newWord, setNewWord] = useState("");
  const [newPhonetic, setNewPhonetic] = useState("");
  const [copiedTier, setCopiedTier] = useState<string | null>(null);

  // Mock AI suggestions for the current segment (strictly simulated mock data)
  const mockSuggestions = [
    {
      id: "sug_1",
      title: "Enhance Dramatic Suspense",
      description: "Shorten initial clause to heighten immediate jeopardy and tension.",
      proposed_text: segment.narration_text.replace(/\band\b/i, "—"),
      tag: "Pacing & Rhythm",
    },
    {
      id: "sug_2",
      title: "Clarify Spatial Atmosphere",
      description: "Infuse sensory description of the vault's cold obsidian stones.",
      proposed_text: `Within the freezing darkness, ${segment.narration_text.charAt(0).toLowerCase() + segment.narration_text.slice(1)}`,
      tag: "Sensory Depth",
    },
  ];

  // Copy helper
  const handleCopyTierToScript = (sourceText: string, tierName: string) => {
    onUpdateSegment({
      narration_text: sourceText,
      generation_status: segment.generation_status === "READY" ? "OUTDATED" : segment.generation_status,
      updated_at: new Date().toISOString(),
    });
    setCopiedTier(tierName);
    setTimeout(() => setCopiedTier(null), 2000);
  };

  // Add pronunciation rule
  const handleAddPronunciation = () => {
    if (!newWord.trim() || !newPhonetic.trim()) return;
    const item: PronunciationItem = {
      id: `pr_${Date.now()}`,
      word: newWord.trim(),
      phonetic: newPhonetic.trim(),
    };
    onUpdateSegment({
      delivery: {
        ...segment.delivery,
        pronunciation_guide: [...segment.delivery.pronunciation_guide, item],
      },
      updated_at: new Date().toISOString(),
    });
    setNewWord("");
    setNewPhonetic("");
  };

  const handleRemovePronunciation = (id: string) => {
    onUpdateSegment({
      delivery: {
        ...segment.delivery,
        pronunciation_guide: segment.delivery.pronunciation_guide.filter((p) => p.id !== id),
      },
      updated_at: new Date().toISOString(),
    });
  };

  return (
    <div className={`flex flex-col bg-ink border-t border-edge/80 p-4 space-y-4 select-none ${className}`}>
      {/* Tab Navigation for Story Quality Review */}
      <div className="flex items-center justify-between border-b border-edge pb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-fg-dim">
            Storytelling Quality Matrix
          </span>
          <span className="text-[10px] text-fg-faint font-medium hidden sm:inline">
            (4-Layer Manga Comparison)
          </span>
        </div>

        <div className="flex items-center gap-1 bg-navy p-0.5 rounded-lg border border-edge text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("matrix")}
            className={`px-2.5 py-1 rounded transition-colors ${
              activeTab === "matrix"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            4-Tier Matrix
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("pronunciation")}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1 ${
              activeTab === "pronunciation"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            Pronunciation
            {segment.delivery.pronunciation_guide.length > 0 && (
              <span className="w-4 h-4 rounded-full bg-flat text-[9px] font-mono flex items-center justify-center text-fg-dim">
                {segment.delivery.pronunciation_guide.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("ai_polish")}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1 ${
              activeTab === "ai_polish"
                ? "bg-accent text-white font-bold shadow-sm"
                : "text-fg-dim hover:text-fg"
            }`}
          >
            <span>Mock AI Polish</span>
            <span className="text-[9px] uppercase px-1 py-0.2 rounded bg-warn/20 text-warn font-bold border border-warn/80">
              Mock
            </span>
          </button>
        </div>
      </div>

      {/* Tab 1: 4-Tier Storytelling Quality Matrix */}
      {activeTab === "matrix" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          {/* Tier 1: Raw OCR Dialogue */}
          <div className="p-3 rounded-xl bg-navy/60 border border-edge flex flex-col justify-between space-y-2">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-info flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  1. Raw OCR Dialogue
                </span>
                <span className="text-[10px] text-fg-faint font-mono">Extracted Source</span>
              </div>
              <p className="text-fg-dim font-mono text-[11px] bg-ink/80 p-2.5 rounded-lg border border-edge/80 min-h-[50px] italic">
                {segment.source_context.raw_ocr_dialogue || "(No text bubble in source panel)"}
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                handleCopyTierToScript(segment.source_context.raw_ocr_dialogue, "OCR")
              }
              disabled={!segment.source_context.raw_ocr_dialogue}
              className="text-[10px] text-fg-dim hover:text-info font-semibold self-start flex items-center gap-1 hover:underline disabled:opacity-30"
            >
              <span>Apply verbatim to script</span>
              {copiedTier === "OCR" && (
                <span className="text-ok font-bold flex items-center gap-1">
                  <Icons.Check className="w-3 h-3" /> Copied
                </span>
              )}
            </button>
          </div>

          {/* Tier 2: Visual Scene Description */}
          <div className="p-3 rounded-xl bg-navy/60 border border-edge flex flex-col justify-between space-y-2">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ok flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-ok" />
                  2. Visual Scene Description
                </span>
                <span className="text-[10px] text-fg-faint font-mono">Camera / Art Cue</span>
              </div>
              <p className="text-fg-dim text-[11px] bg-ink/80 p-2.5 rounded-lg border border-edge/80 min-h-[50px] leading-relaxed">
                {segment.source_context.visual_description}
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                handleCopyTierToScript(segment.source_context.visual_description, "Visual")
              }
              className="text-[10px] text-fg-dim hover:text-info font-semibold self-start flex items-center gap-1 hover:underline"
            >
              <span>Convert visual description to narration</span>
              {copiedTier === "Visual" && (
                <span className="text-ok font-bold flex items-center gap-1">
                  <Icons.Check className="w-3 h-3" /> Copied
                </span>
              )}
            </button>
          </div>

          {/* Tier 3: Contextual Story Narration / Subtext */}
          <div className="p-3 rounded-xl bg-navy/60 border border-edge flex flex-col justify-between space-y-2">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-info flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  3. Contextual Story Subtext
                </span>
                <span className="text-[10px] text-fg-faint font-mono">Dramatic Intent</span>
              </div>
              <p className="text-fg-dim text-[11px] bg-ink/80 p-2.5 rounded-lg border border-edge/80 min-h-[50px] leading-relaxed">
                {segment.source_context.story_context}
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                handleCopyTierToScript(segment.source_context.story_context, "Context")
              }
              className="text-[10px] text-fg-dim hover:text-info font-semibold self-start flex items-center gap-1 hover:underline"
            >
              <span>Use story context as narration</span>
              {copiedTier === "Context" && (
                <span className="text-ok font-bold flex items-center gap-1">
                  <Icons.Check className="w-3 h-3" /> Copied
                </span>
              )}
            </button>
          </div>


          {/* Tier 4: Final Spoken Narration Script */}
          <div className="p-3 rounded-xl bg-accent/30 border border-accent/60 flex flex-col justify-between space-y-2">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-info flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  4. Final Spoken Narration Script
                </span>
                <span className="text-[10px] text-ok font-mono font-semibold">Active TTS Target</span>
              </div>
              <p className="text-fg font-medium text-[11px] bg-ink/90 p-2.5 rounded-lg border border-accent/50 min-h-[50px] leading-relaxed">
                {segment.narration_text}
              </p>
            </div>
            <div className="flex items-center justify-between text-[10px] text-fg-dim">
              <span>Delivery: <strong className="text-fg">{segment.delivery.emotion}</strong></span>
              <span className="font-mono text-info">Speaker: {segment.speaker_name}</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Pronunciation Guide */}
      {activeTab === "pronunciation" && (
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <p className="text-fg-dim text-[11px]">
              Provide explicit phonetic pronunciation rules for fantasy names, arcane terms, and places to ensure natural TTS synthesis.
            </p>
          </div>

          {/* Existing Rules */}
          <div className="space-y-1.5">
            {segment.delivery.pronunciation_guide.length === 0 ? (
              <div className="p-4 rounded-lg bg-navy/40 border border-edge text-center text-fg-faint text-xs">
                No custom pronunciation rules defined for this segment.
              </div>
            ) : (
              segment.delivery.pronunciation_guide.map((rule) => (
                <div
                  key={rule.id}
                  className="flex items-center justify-between p-2 rounded-lg bg-navy border border-edge"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-fg">{rule.word}</span>
                    <span className="text-fg-faint">→</span>
                    <span className="font-mono text-info bg-ink px-2 py-0.5 rounded border border-edge">
                      /{rule.phonetic}/
                    </span>
                    {rule.notes && <span className="text-fg-faint text-[10px]">({rule.notes})</span>}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemovePronunciation(rule.id)}
                    className="text-fg-faint hover:text-bad p-1"
                    title="Remove Rule"
                  >
                    <Icons.X className="w-3.5 h-3.5" />
                  </button>

                </div>
              ))
            )}
          </div>

          {/* Add Rule Form */}
          <div className="flex items-center gap-2 pt-2 border-t border-edge/80">
            <input
              type="text"
              placeholder="Word (e.g. Kaelen)"
              value={newWord}
              onChange={(e) => setNewWord(e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-lg bg-navy border border-edge text-xs text-fg focus:outline-none focus:border-accent"
            />
            <input
              type="text"
              placeholder="Phonetic (e.g. KAY-len)"
              value={newPhonetic}
              onChange={(e) => setNewPhonetic(e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-lg bg-navy border border-edge text-xs text-fg font-mono focus:outline-none focus:border-accent"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={handleAddPronunciation}
              disabled={!newWord.trim() || !newPhonetic.trim()}
              className="text-xs h-8"
            >
              + Add Rule
            </Button>
          </div>
        </div>
      )}

      {/* Tab 3: Mock AI Polish Suggestions */}
      {activeTab === "ai_polish" && (
        <div className="space-y-3 text-xs">
          <div className="p-2.5 rounded-lg bg-warn/30 border border-warn/60 text-warn text-[11px] flex items-center justify-between">
            <span>
              <strong>Simulated AI Storytelling Assistant:</strong> Mock data for review & evaluation only. No external LLMs or network requests are executed.
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {mockSuggestions.map((sug) => (
              <div
                key={sug.id}
                className="p-3 rounded-xl bg-navy/80 border border-edge space-y-2 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-fg">{sug.title}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-flat text-fg-dim font-mono">
                      {sug.tag}
                    </span>
                  </div>
                  <p className="text-[11px] text-fg-dim mb-2 leading-relaxed">
                    {sug.description}
                  </p>
                  <div className="p-2 rounded bg-ink border border-edge text-fg font-serif text-[11px] italic">
                    &ldquo;{sug.proposed_text}&rdquo;
                  </div>
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    onUpdateSegment({
                      narration_text: sug.proposed_text,
                      generation_status:
                        segment.generation_status === "READY" ? "OUTDATED" : segment.generation_status,
                      updated_at: new Date().toISOString(),
                    })
                  }
                  className="text-xs h-7 self-start mt-2 bg-accent hover:bg-accent"
                >
                  Apply Suggestion
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
