import React, { useState } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import type {
  CharacterProfile,
  VoiceProfile,
  NarrationSegment,
  NarrationEmotion,
} from "./NarrationStudio.types";

interface CharacterVoiceManagerProps {
  characters: CharacterProfile[];
  voiceProfiles: VoiceProfile[];
  segments: NarrationSegment[];
  selectedCharacterId?: string | null;
  onUpdateCharacter: (characterId: string, updates: Partial<CharacterProfile>) => void;
  onApplyVoiceToAllSegments: (
    characterId: string,
    voiceProfileId: string,
    overwriteCustomOverrides?: boolean
  ) => void;
  onAddCharacter?: (character: Omit<CharacterProfile, "id" | "segment_count">) => void;
  onClose?: () => void;
  className?: string;
}

export const CharacterVoiceManager: React.FC<CharacterVoiceManagerProps> = ({
  characters,
  voiceProfiles,
  segments,
  selectedCharacterId: initialSelectedId,
  onUpdateCharacter,
  onApplyVoiceToAllSegments,
  onAddCharacter,
  onClose,
  className = "",
}) => {
  const [activeCharId, setActiveCharId] = useState<string>(
    initialSelectedId || characters[0]?.id || ""
  );
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showOverridePrompt, setShowOverridePrompt] = useState<boolean>(false);
  const [newCharName, setNewCharName] = useState("");
  const [newCharRole, setNewCharRole] = useState<CharacterProfile["role"]>("SUPPORTING");
  const [newCharColor, setNewCharColor] = useState("#8b5cf6");
  const [newCharVoice, setNewCharVoice] = useState(voiceProfiles[0]?.id || "");
  const [copiedMessage, setCopiedMessage] = useState<string | null>(null);

  const activeCharacter = characters.find((c) => c.id === activeCharId) || characters[0];
  const activeVoiceProfile = voiceProfiles.find(
    (v) => v.id === activeCharacter?.default_voice_profile_id
  );

  // Segments voiced by active character
  const characterSegments = segments.filter(
    (s) => s.speaker_id === activeCharacter?.id
  );
  const overriddenSegments = characterSegments.filter(
    (s) => s.has_custom_voice_override
  );

  const handleApplyVoice = () => {
    if (!activeCharacter || !activeCharacter.default_voice_profile_id) return;
    if (overriddenSegments.length > 0) {
      setShowOverridePrompt(true);
      return;
    }
    onApplyVoiceToAllSegments(activeCharacter.id, activeCharacter.default_voice_profile_id, false);
    setCopiedMessage(`Voice applied to all ${characterSegments.length} segments!`);
    setTimeout(() => setCopiedMessage(null), 3000);
  };

  const handleConfirmApply = (overwrite: boolean) => {
    if (!activeCharacter || !activeCharacter.default_voice_profile_id) return;
    onApplyVoiceToAllSegments(activeCharacter.id, activeCharacter.default_voice_profile_id, overwrite);
    setShowOverridePrompt(false);
    if (overwrite) {
      setCopiedMessage(`Overwrote all ${characterSegments.length} segments!`);
    } else {
      setCopiedMessage(
        `Applied to ${characterSegments.length - overriddenSegments.length} segments (preserved ${overriddenSegments.length} custom overrides)!`
      );
    }
    setTimeout(() => setCopiedMessage(null), 3000);
  };

  const handleCreateNewCharacter = () => {
    if (!newCharName.trim()) return;
    onAddCharacter?.({
      name: newCharName.trim(),
      role: newCharRole,
      color_accent: newCharColor,
      avatar_initials: newCharName.slice(0, 2).toUpperCase(),
      default_voice_profile_id: newCharVoice,
      default_emotion: "Neutral",
      default_speed: 1.0,
      notes: "Custom character created in Narration Studio.",
    });
    setNewCharName("");
    setShowAddModal(false);
  };

  return (
    <div className={`flex flex-col bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden select-none shadow-2xl ${className}`}>
      {/* Header */}
      <div className="p-3.5 border-b border-zinc-800 bg-zinc-900/60 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 rounded-lg bg-indigo-600/90 text-white flex items-center justify-center font-bold text-xs shadow-sm">
            👥
          </span>
          <div>
            <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
              Character Voice Manager
            </h3>
            <p className="text-[10px] text-zinc-400">
              Manage character casting & assign consistent voice profiles
            </p>
          </div>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
            title="Close Character Manager"
            aria-label="Close Character Voice Manager"
          >
            ✕
          </button>
        )}
      </div>

      {/* Main Split: Left Characters List, Right Voice Details */}
      <div className="grid grid-cols-1 md:grid-cols-3 flex-1 min-h-[380px] overflow-hidden">
        {/* Left: Character List */}
        <div className="border-r border-zinc-800/80 bg-zinc-950/60 p-2 space-y-1.5 overflow-y-auto">
          <div className="flex items-center justify-between px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
            <span>Story Characters ({characters.length})</span>
            {onAddCharacter && (
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="text-indigo-400 hover:text-indigo-300 font-bold"
              >
                + Add
              </button>
            )}
          </div>

          {characters.map((char) => {
            const isSelected = char.id === activeCharacter?.id;
            const segCount = segments.filter((s) => s.speaker_id === char.id).length;
            const assignedVoice = voiceProfiles.find((v) => v.id === char.default_voice_profile_id);

            return (
              <button
                key={char.id}
                type="button"
                onClick={() => setActiveCharId(char.id)}
                className={`w-full p-2 rounded-lg text-left transition-all border flex items-center justify-between gap-2 ${
                  isSelected
                    ? "bg-zinc-900 border-indigo-500 shadow-sm"
                    : "bg-zinc-900/40 border-zinc-800/80 hover:bg-zinc-900 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold font-mono text-white shrink-0 shadow-sm"
                    style={{ backgroundColor: char.color_accent }}
                  >
                    {char.avatar_initials}
                  </div>
                  <div className="min-w-0">
                    <span className="text-xs font-bold text-zinc-100 block truncate">
                      {char.name}
                    </span>
                    <span className="text-[10px] text-zinc-400 block truncate">
                      {assignedVoice?.name.split("—")[0].trim() || "No Voice"}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col items-end shrink-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-500">
                    {char.role}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {segCount} lines
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right: Character & Voice Profile Settings */}
        {activeCharacter ? (
          <div className="md:col-span-2 p-4 space-y-4 overflow-y-auto bg-zinc-950">
            {/* Active Character Header */}
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2.5">
                <div
                  className="w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm text-white font-mono shadow-md"
                  style={{ backgroundColor: activeCharacter.color_accent }}
                >
                  {activeCharacter.avatar_initials}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold text-zinc-100">
                      {activeCharacter.name}
                    </h4>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {activeCharacter.role}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    {activeCharacter.notes || "Story Character"}
                  </p>
                </div>
              </div>

              {/* Character Color Picker */}
              <div className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-xs">
                <span className="text-[10px] text-zinc-400">Color:</span>
                <input
                  type="color"
                  value={activeCharacter.color_accent}
                  onChange={(e) =>
                    onUpdateCharacter(activeCharacter.id, { color_accent: e.target.value })
                  }
                  className="w-4 h-4 rounded cursor-pointer bg-transparent border-0"
                />
              </div>
            </div>

            {/* Voice Profile Selector */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                  Assigned Voice Profile
                </span>
                <span className="text-[10px] font-mono text-indigo-400">
                  ID: {activeCharacter.default_voice_profile_id}
                </span>
              </div>

              <select
                value={activeCharacter.default_voice_profile_id}
                onChange={(e) =>
                  onUpdateCharacter(activeCharacter.id, {
                    default_voice_profile_id: e.target.value,
                  })
                }
                className="w-full p-2 rounded-lg bg-zinc-900 border border-zinc-700 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 font-semibold cursor-pointer"
              >
                {voiceProfiles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} ({v.gender}, {v.age_group}) — {v.model_family}
                  </option>
                ))}
              </select>
            </div>

            {/* Selected Voice Card Details */}
            {activeVoiceProfile && (
              <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-zinc-100 text-sm">
                      {activeVoiceProfile.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
                      {activeVoiceProfile.model_family}
                    </span>
                  </div>
                  <span className="text-[10px] uppercase font-bold text-emerald-400 bg-emerald-950/70 border border-emerald-800 px-2 py-0.5 rounded-full">
                    Mock Profile
                  </span>
                </div>

                <p className="text-[11px] text-zinc-300 leading-relaxed italic">
                  &ldquo;{activeVoiceProfile.sample_quote}&rdquo;
                </p>

                <div className="p-2 rounded bg-zinc-950/80 border border-zinc-800 text-[11px] space-y-1">
                  <div className="text-zinc-400">
                    <strong className="text-zinc-300">Timbre & Cadence:</strong> {activeVoiceProfile.timbre}
                  </div>
                  <div className="text-zinc-400 flex items-center gap-1.5 pt-0.5">
                    <strong className="text-zinc-300">Recommended for:</strong>
                    <div className="flex items-center gap-1">
                      {activeVoiceProfile.recommended_emotions.map((emo) => (
                        <span key={emo} className="px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-300 text-[10px]">
                          {emo}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 1-Click Sync Across All Lines */}
            <div className="p-3 rounded-lg bg-indigo-950/30 border border-indigo-800/60 flex items-center justify-between text-xs">
              <div>
                <p className="font-bold text-zinc-200">
                  Propagate Voice to All Lines
                </p>
                <p className="text-[11px] text-zinc-400">
                  Update {characterSegments.length} narration segment(s) assigned to {activeCharacter.name}.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {copiedMessage && (
                  <span className="text-xs font-bold text-emerald-400 animate-pulse">
                    {copiedMessage}
                  </span>
                )}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleApplyVoice}
                  className="text-xs h-8 bg-indigo-600 hover:bg-indigo-500 font-semibold"
                >
                  Apply to All ({characterSegments.length})
                </Button>
              </div>
            </div>

            {/* Custom Override Confirmation Prompt */}
            {showOverridePrompt && (
              <div className="p-3 rounded-xl bg-amber-950/60 border border-amber-700/80 text-amber-200 text-xs space-y-2.5 shadow-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-bold text-amber-300 text-xs">
                    <span>⚠️</span>
                    <span>Custom Voice Overrides Detected</span>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-amber-900/60 text-amber-300 border border-amber-700">
                    {overriddenSegments.length} Protected
                  </span>
                </div>
                <p className="text-[11px] text-amber-200/90 leading-relaxed">
                  <strong>{overriddenSegments.length}</strong> segment(s) assigned to <strong>{activeCharacter.name}</strong> have manual voice overrides:
                  {" "}
                  <span className="font-mono text-[10px] text-amber-300">
                    {overriddenSegments.map((s) => `#${s.sequence}`).join(", ")}
                  </span>.
                  Choose whether to preserve individual customization or update all lines:
                </p>
                <div className="flex items-center gap-2 pt-1">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleConfirmApply(false)}
                    className="text-xs h-7 border border-amber-600/70 text-amber-200 hover:bg-amber-900/50"
                  >
                    Skip Customized Lines ({characterSegments.length - overriddenSegments.length})
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleConfirmApply(true)}
                    className="text-xs h-7 bg-amber-600 hover:bg-amber-500 text-white font-bold"
                  >
                    Overwrite All Lines ({characterSegments.length})
                  </Button>
                  <button
                    type="button"
                    onClick={() => setShowOverridePrompt(false)}
                    className="text-[11px] text-zinc-400 hover:text-zinc-200 ml-1 underline"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Lines Voiced by this Character */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider">
                Lines in this Chapter ({characterSegments.length})
              </span>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {characterSegments.map((seg) => (
                  <div
                    key={seg.id}
                    className="p-2 rounded bg-zinc-900 border border-zinc-800 text-[11px] flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="font-mono text-[10px] text-indigo-400 font-bold shrink-0">
                        #{seg.sequence}
                      </span>
                      <span className="text-zinc-200 truncate">{seg.narration_text}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {seg.has_custom_voice_override && (
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/80 border border-amber-800 text-amber-400 font-mono">
                          Custom
                        </span>
                      )}
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-950 text-zinc-400 font-medium">
                        {seg.delivery.emotion}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="md:col-span-2 p-8 text-center text-zinc-500 text-xs">
            Select a character to view settings
          </div>
        )}
      </div>

      {/* Add Character Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-sm w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <h4 className="text-sm font-bold text-zinc-100">Add Story Character</h4>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="text-zinc-400 hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-zinc-400 mb-1">
                  Character Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Master Vance"
                  value={newCharName}
                  onChange={(e) => setNewCharName(e.target.value)}
                  className="w-full p-2 rounded bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-zinc-400 mb-1">
                  Dramatic Role
                </label>
                <select
                  value={newCharRole}
                  onChange={(e) => setNewCharRole(e.target.value as any)}
                  className="w-full p-2 rounded bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="PROTAGONIST">Protagonist</option>
                  <option value="ANTAGONIST">Antagonist</option>
                  <option value="SUPPORTING">Supporting</option>
                  <option value="MINOR">Minor</option>
                  <option value="NARRATOR">Narrator</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-zinc-400 mb-1">
                  Initial Voice Profile
                </label>
                <select
                  value={newCharVoice}
                  onChange={(e) => setNewCharVoice(e.target.value)}
                  className="w-full p-2 rounded bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500"
                >
                  {voiceProfiles.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-zinc-400 mb-1">
                  Theme Color Accent
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={newCharColor}
                    onChange={(e) => setNewCharColor(e.target.value)}
                    className="w-8 h-8 rounded cursor-pointer bg-transparent border-0"
                  />
                  <span className="text-zinc-400 font-mono text-xs">{newCharColor}</span>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowAddModal(false)}
                className="text-xs h-8"
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleCreateNewCharacter}
                disabled={!newCharName.trim()}
                className="text-xs h-8 bg-indigo-600 hover:bg-indigo-500"
              >
                Create Character
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
