import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  NarrativeDocument,
  CharacterEntity,
  SceneEntity,
  StoryBeatEntity,
  EventEntity,
  UtteranceEntity,
  ContinuityWarningEntity,
  LLMProviderInfo,
} from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface StoryReviewScreenProps {
  project: Project;
  onBack: () => void;
  onStoryApproved: (updatedProject: Project) => void;
  onProceedToScript?: (project: Project) => void;
}

export const StoryReviewScreen: React.FC<StoryReviewScreenProps> = ({
  project,
  onBack,
  onStoryApproved,
  onProceedToScript,
}) => {
  const [narrative, setNarrative] = useState<NarrativeDocument | null>(null);
  const [characters, setCharacters] = useState<CharacterEntity[]>([]);
  const [scenes, setScenes] = useState<SceneEntity[]>([]);
  const [providers, setProviders] = useState<LLMProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>(project.settings?.visual_storytelling ? "ollama" : "mock");

  const [loading, setLoading] = useState<boolean>(true);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [progressMsg, setProgressMsg] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"characters" | "scenes" | "utterances" | "continuity">("characters");

  // Character edit state
  const [editingCharacter, setEditingCharacter] = useState<CharacterEntity | null>(null);
  const [editCharForm, setEditCharForm] = useState({
    display_name: "",
    canonical_name: "",
    role: "SUPPORTING",
    aliases: "",
    description: "",
    status: "CONFIRMED",
  });

  // Merge & Split Modals
  const [showMergeModal, setShowMergeModal] = useState<boolean>(false);
  const [mergeSourceId, setMergeSourceId] = useState<string>("");
  const [mergeTargetId, setMergeTargetId] = useState<string>("");

  const [showSplitModal, setShowSplitModal] = useState<boolean>(false);
  const [splitCharId, setSplitCharId] = useState<string>("");
  const [splitNewName, setSplitNewName] = useState<string>("");
  const [splitPanelIds, setSplitPanelIds] = useState<string>("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [provList, doc, charList, sceneList] = await Promise.all([
        api.listLLMProviders().catch(() => []),
        api.getNarrative(project.id).catch(() => null),
        api.listCharacters(project.id).catch(() => []),
        api.listScenes(project.id).catch(() => []),
      ]);

      setProviders(provList);
      if (provList.length > 0 && !selectedProvider) {
        setSelectedProvider(provList[0].provider_id);
      }
      setNarrative(doc);
      setCharacters(charList);
      setScenes(sceneList);
    } catch (err: any) {
      console.error("Failed to load narrative data:", err);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleStartAnalysis = async () => {
    setAnalyzing(true);
    setProgress(0.1);
    setProgressMsg("Queuing story analysis...");

    try {
      const res = await api.analyzeStory(project.id, selectedProvider);
      const jobId = res.job_id;

      // Poll job
      const pollInterval = setInterval(async () => {
        try {
          const j = await api.getJob(jobId);
          if (j.status === "RUNNING") {
            setProgress(j.progress);
            setProgressMsg(j.message || "Analyzing comic narrative...");
          } else if (j.status === "SUCCEEDED") {
            clearInterval(pollInterval);
            setAnalyzing(false);
            setProgress(1.0);
            setProgressMsg("Story analysis completed!");
            await loadData();
          } else if (j.status === "FAILED") {
            clearInterval(pollInterval);
            setAnalyzing(false);
            alert(`Story analysis failed: ${j.error || "Unknown error"}`);
          }
        } catch {
          // ignore transient poll error
        }
      }, 1000);
    } catch (err: any) {
      setAnalyzing(false);
      alert(`Failed to start story analysis: ${err.message}`);
    }
  };

  const handleConfirmStory = async () => {
    try {
      const res = await api.confirmStory(project.id);
      const updated = await api.getProject(project.id);
      alert(res.message || "Story Narrative IR approved successfully!");
      onStoryApproved(updated);
    } catch (err: any) {
      alert(`Approval Gate Blocked: ${err.message}`);
    }
  };

  const handleSaveCharacter = async () => {
    if (!editingCharacter) return;
    try {
      const aliasArray = editCharForm.aliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean);

      await api.updateCharacter(project.id, editingCharacter.character_id, {
        display_name: editCharForm.display_name,
        canonical_name: editCharForm.canonical_name,
        role: editCharForm.role,
        aliases: aliasArray,
        description: editCharForm.description,
        status: editCharForm.status,
      });

      setEditingCharacter(null);
      await loadData();
    } catch (err: any) {
      alert(`Failed to update character: ${err.message}`);
    }
  };

  const handleMergeCharacters = async () => {
    if (!mergeSourceId || !mergeTargetId || mergeSourceId === mergeTargetId) {
      alert("Please select distinct source and target characters.");
      return;
    }
    try {
      await api.mergeCharacters(project.id, mergeSourceId, mergeTargetId);
      setShowMergeModal(false);
      setMergeSourceId("");
      setMergeTargetId("");
      await loadData();
    } catch (err: any) {
      alert(`Failed to merge characters: ${err.message}`);
    }
  };

  const handleSplitCharacter = async () => {
    if (!splitCharId || !splitNewName.trim()) {
      alert("Please select a character and enter a new identity name.");
      return;
    }
    const panelArray = splitPanelIds
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);

    try {
      await api.splitCharacter(project.id, splitCharId, splitNewName.trim(), panelArray);
      setShowSplitModal(false);
      setSplitCharId("");
      setSplitNewName("");
      setSplitPanelIds("");
      await loadData();
    } catch (err: any) {
      alert(`Failed to split character identity: ${err.message}`);
    }
  };

  const isApproved = project.current_stage === "STORY_APPROVED" || project.current_stage === "SCRIPT_GENERATED" || project.current_stage === "SCRIPT_APPROVED";
  const blockingWarnings = (narrative?.continuity_warnings || []).filter((w) => w.severity === "ERROR" && !w.resolved);

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <Icons.ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Story Understanding & Narrative IR
            </h1>
            <Badge variant={isApproved ? "success" : "neutral"} className="uppercase font-mono">
              {project.current_stage}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Layer B canonical representation: Character registry, scene boundaries, dramatic beats, and grounded dialogue.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Provider Selector */}
          <select
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
            disabled={analyzing}
            className="bg-zinc-900 border border-zinc-700 text-xs text-zinc-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-mono"
          >
            {providers.filter(p => !project.settings?.visual_storytelling || p.provider_id !== "mock_llm").map((p) => (
              <option key={p.provider_id} value={p.provider_id}>
                {p.provider_name} {p.is_local ? "(Local)" : ""} {p.is_healthy ? "✓" : "✗"}
              </option>
            ))}
          </select>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleStartAnalysis}
            disabled={analyzing}
          >
            <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${analyzing ? "animate-spin" : ""}`} />
            {narrative ? "Re-Analyze Story" : "Run Story Analysis"}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleConfirmStory}
            disabled={analyzing || !narrative || blockingWarnings.length > 0}
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
          >
            <Icons.Check className="w-3.5 h-3.5 mr-1.5" />
            Approve Narrative IR
          </Button>

          {isApproved && onProceedToScript && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onProceedToScript(project)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Proceed to Script <Icons.ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Analysis Progress */}
      {analyzing && (
        <Card className="p-4 bg-indigo-950/30 border-indigo-800 space-y-2">
          <div className="flex justify-between text-xs text-indigo-300 font-medium">
            <span>{progressMsg}</span>
            <span>{Math.round(progress * 100)}%</span>
          </div>
          <ProgressBar progress={progress} />
        </Card>
      )}

      {/* Continuity Warnings Banner */}
      {narrative && narrative.continuity_warnings && narrative.continuity_warnings.length > 0 && (
        <div className="space-y-2">
          {blockingWarnings.length > 0 && (
            <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-700/80 text-rose-200 text-xs flex items-center gap-2">
              <Icons.AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>
                <strong>Blocking Continuity Errors:</strong> {blockingWarnings.length} critical issues must be resolved before Narrative IR can be approved.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-zinc-800 text-xs font-semibold">
        <button
          onClick={() => setActiveTab("characters")}
          className={`pb-2.5 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === "characters"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Icons.User className="w-3.5 h-3.5" />
          Characters ({characters.length})
        </button>

        <button
          onClick={() => setActiveTab("scenes")}
          className={`pb-2.5 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === "scenes"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Icons.Folder className="w-3.5 h-3.5" />
          Scenes & Beats ({scenes.length})
        </button>

        <button
          onClick={() => setActiveTab("utterances")}
          className={`pb-2.5 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === "utterances"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Icons.MessageSquare className="w-3.5 h-3.5" />
          Utterances ({narrative?.utterances?.length || 0})
        </button>

        <button
          onClick={() => setActiveTab("continuity")}
          className={`pb-2.5 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === "continuity"
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          <Icons.AlertTriangle className="w-3.5 h-3.5" />
          Continuity ({narrative?.continuity_warnings?.length || 0})
        </button>
      </div>

      {/* Tab 1: Character Registry */}
      {activeTab === "characters" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">
              Tracked characters and aliases across panels. Merge duplicates or split misattributed entities.
            </span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => setShowMergeModal(true)}>
                Merge Identities
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowSplitModal(true)}>
                Split Identity
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {characters.map((char, index) => (
              <Card key={char.character_id ? `${char.character_id}-${index}` : `char-${index}`} className="p-4 bg-zinc-900 border-zinc-800 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-zinc-100 text-sm flex items-center gap-2">
                      {char.canonical_name}
                      {char.manual_override && (
                        <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1 rounded">MANUAL</span>
                      )}
                    </h3>
                    <p className="text-xs text-zinc-400 font-mono">ID: {char.character_id}</p>
                  </div>
                  <Badge variant={char.role === "PROTAGONIST" ? "accent" : "neutral"} className="text-[10px]">
                    {char.role}
                  </Badge>
                </div>

                <p className="text-xs text-zinc-300 line-clamp-2">{char.description || "No description provided."}</p>

                {char.aliases && char.aliases.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {char.aliases.map((a, i) => (
                      <span key={i} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                        {a}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-between pt-2 border-t border-zinc-800/80 text-[11px] text-zinc-500">
                  <span>Status: <strong className="text-zinc-300">{char.status}</strong></span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs text-indigo-400 hover:text-indigo-300"
                    onClick={() => {
                      setEditingCharacter(char);
                      setEditCharForm({
                        display_name: char.display_name,
                        canonical_name: char.canonical_name,
                        role: char.role,
                        aliases: (char.aliases || []).join(", "),
                        description: char.description || "",
                        status: char.status,
                      });
                    }}
                  >
                    Edit
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Scenes & Story Beats */}
      {activeTab === "scenes" && (
        <div className="space-y-4">
          <div className="space-y-3">
            {scenes.map((scene) => {
              const sceneBeats = (narrative?.beats || []).filter((b) => b.scene_id === scene.scene_id);
              const sceneEvents = (narrative?.events || []).filter((e) =>
                sceneBeats.some((b) => b.event_ids.includes(e.event_id))
              );

              return (
                <Card key={scene.scene_id} className="p-5 bg-zinc-900 border-zinc-800 space-y-4">
                  <div className="flex items-start justify-between border-b border-zinc-800 pb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-indigo-400">Scene #{scene.sequence}</span>
                        <h3 className="font-bold text-zinc-100 text-sm">{scene.title}</h3>
                      </div>
                      <p className="text-xs text-zinc-400 mt-0.5">{scene.summary}</p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge variant="neutral" className="text-[10px]">
                        Boundary: {scene.boundary_reason}
                      </Badge>
                      <span className="text-xs font-mono text-zinc-500">
                        Panels: {scene.panel_start} → {scene.panel_end}
                      </span>
                    </div>
                  </div>

                  {/* Beats in Scene */}
                  <div className="space-y-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                      Dramatic Beats ({sceneBeats.length})
                    </span>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {sceneBeats.map((beat) => (
                        <div key={beat.beat_id} className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/80 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-zinc-200">Beat #{beat.sequence}</span>
                            <Badge variant="accent" className="text-[9px]">
                              {beat.dramatic_function}
                            </Badge>
                          </div>
                          <p className="text-xs text-zinc-400">{beat.summary}</p>
                          <div className="flex items-center gap-3 text-[10px] text-zinc-500 pt-1">
                            <span>Importance: <strong className="text-zinc-300">{beat.importance}</strong></span>
                            <span>Intensity: <strong className="text-zinc-300">{Math.round(beat.intensity * 100)}%</strong></span>
                            {beat.music_intent && <span>Music: <em>{beat.music_intent}</em></span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Events in Scene */}
                  {sceneEvents.length > 0 && (
                    <div className="space-y-1.5 pt-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                        Extracted Events ({sceneEvents.length})
                      </span>
                      <div className="space-y-1">
                        {sceneEvents.map((ev) => (
                          <div key={ev.event_id} className="text-xs text-zinc-300 flex items-center gap-2">
                            <span className="text-[10px] bg-zinc-800 text-indigo-300 px-1.5 py-0.5 rounded font-mono">
                              {ev.event_type}
                            </span>
                            <span>{ev.description}</span>
                            <span className="text-[10px] text-zinc-500 font-mono">
                              (Panels: {ev.panel_ids.join(", ")})
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 3: Utterances & Speaker Attribution */}
      {activeTab === "utterances" && (
        <div className="space-y-3">
          <div className="text-xs text-zinc-400">
            Source-grounded dialogue, narration, and onomatopoeia extracted from OCR regions. Reassign speakers as needed.
          </div>

          <div className="space-y-2">
            {(narrative?.utterances || []).map((u) => (
              <Card key={u.utterance_id} className="p-3.5 bg-zinc-900 border-zinc-800 flex items-center justify-between gap-4">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant={u.utterance_type === "NARRATION" ? "neutral" : "accent"} className="text-[10px]">
                      {u.utterance_type}
                    </Badge>
                    <span className="text-xs font-bold text-indigo-400">
                      {characters.find((c) => c.character_id === u.speaker_character_id)?.canonical_name || u.speaker_character_id || "UNKNOWN"}
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono">Panel #{u.panel_id.slice(-4)}</span>
                  </div>
                  <p className="text-xs text-zinc-200 font-mono">"{u.corrected_text || u.source_text}"</p>
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={u.speaker_character_id || "UNKNOWN"}
                    onChange={async (e) => {
                      const newSpeaker = e.target.value;
                      try {
                        await api.updateTextRegion(project.id, u.text_region_id, {
                          speaker_character_id: newSpeaker,
                          speaker_assignment_method: "MANUAL",
                        });
                        await loadData();
                      } catch (err: any) {
                        alert(`Failed to update speaker: ${err.message}`);
                      }
                    }}
                    className="bg-zinc-950 border border-zinc-700 text-xs text-zinc-200 rounded px-2 py-1 font-mono"
                  >
                    <option value="UNKNOWN">UNKNOWN</option>
                    <option value="NARRATOR">NARRATOR</option>
                    <option value="SFX">SFX</option>
                    {characters.map((c) => (
                      <option key={c.character_id} value={c.character_id}>
                        {c.canonical_name} ({c.role})
                      </option>
                    ))}
                  </select>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Continuity Warnings */}
      {activeTab === "continuity" && (
        <div className="space-y-3">
          {(narrative?.continuity_warnings || []).length === 0 ? (
            <div className="p-8 text-center text-zinc-500 text-xs">
              No continuity warnings detected. Narrative IR is internally consistent.
            </div>
          ) : (
            narrative?.continuity_warnings?.map((w) => (
              <Card
                key={w.warning_id}
                className={`p-4 border ${
                  w.severity === "ERROR"
                    ? "bg-rose-950/30 border-rose-800 text-rose-200"
                    : "bg-amber-950/30 border-amber-800 text-amber-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant={w.severity === "ERROR" ? "danger" : "warning"} className="text-[10px]">
                      {w.severity}
                    </Badge>
                    <span className="text-xs font-bold">{w.warning_type}</span>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-400">Entity: {w.entity_id}</span>
                </div>
                <p className="text-xs mt-1.5">{w.message}</p>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Character Edit Modal */}
      {editingCharacter && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-6 bg-zinc-900 border-zinc-700 space-y-4">
            <h3 className="text-sm font-bold text-zinc-100">Edit Character Identity</h3>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-zinc-400 block mb-1">Canonical Name</label>
                <input
                  type="text"
                  value={editCharForm.canonical_name}
                  onChange={(e) => setEditCharForm({ ...editCharForm, canonical_name: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Display Name</label>
                <input
                  type="text"
                  value={editCharForm.display_name}
                  onChange={(e) => setEditCharForm({ ...editCharForm, display_name: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Role</label>
                <select
                  value={editCharForm.role}
                  onChange={(e) => setEditCharForm({ ...editCharForm, role: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                >
                  <option value="PROTAGONIST">PROTAGONIST</option>
                  <option value="ANTAGONIST">ANTAGONIST</option>
                  <option value="SUPPORTING">SUPPORTING</option>
                  <option value="MINOR">MINOR</option>
                  <option value="UNKNOWN">UNKNOWN</option>
                </select>
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Aliases (comma separated)</label>
                <input
                  type="text"
                  value={editCharForm.aliases}
                  onChange={(e) => setEditCharForm({ ...editCharForm, aliases: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Description</label>
                <textarea
                  value={editCharForm.description}
                  onChange={(e) => setEditCharForm({ ...editCharForm, description: e.target.value })}
                  rows={2}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setEditingCharacter(null)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={handleSaveCharacter}>
                Save Identity
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Merge Modal */}
      {showMergeModal && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-6 bg-zinc-900 border-zinc-700 space-y-4">
            <h3 className="text-sm font-bold text-zinc-100">Merge Character Identities</h3>
            <p className="text-xs text-zinc-400">
              Merge a duplicate character into a primary canonical identity. All text regions and events will be reassigned.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-zinc-400 block mb-1">Source Character (to be merged & removed)</label>
                <select
                  value={mergeSourceId}
                  onChange={(e) => setMergeSourceId(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                >
                  <option value="">Select source character...</option>
                  {characters.map((c) => (
                    <option key={c.character_id} value={c.character_id}>
                      {c.canonical_name} ({c.character_id})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Target Character (to keep)</label>
                <select
                  value={mergeTargetId}
                  onChange={(e) => setMergeTargetId(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                >
                  <option value="">Select target character...</option>
                  {characters.map((c) => (
                    <option key={c.character_id} value={c.character_id}>
                      {c.canonical_name} ({c.character_id})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setShowMergeModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={handleMergeCharacters}>
                Confirm Merge
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Split Modal */}
      {showSplitModal && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-6 bg-zinc-900 border-zinc-700 space-y-4">
            <h3 className="text-sm font-bold text-zinc-100">Split Character Identity</h3>
            <p className="text-xs text-zinc-400">
              Split off a portion of dialogue and appearances into a new character identity.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-zinc-400 block mb-1">Original Character</label>
                <select
                  value={splitCharId}
                  onChange={(e) => setSplitCharId(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                >
                  <option value="">Select character...</option>
                  {characters.map((c) => (
                    <option key={c.character_id} value={c.character_id}>
                      {c.canonical_name} ({c.character_id})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">New Character Name</label>
                <input
                  type="text"
                  value={splitNewName}
                  onChange={(e) => setSplitNewName(e.target.value)}
                  placeholder="e.g. Mysterious Stranger"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>

              <div>
                <label className="text-zinc-400 block mb-1">Panel IDs to reassign (comma separated)</label>
                <input
                  type="text"
                  value={splitPanelIds}
                  onChange={(e) => setSplitPanelIds(e.target.value)}
                  placeholder="e.g. p_001, p_002"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-zinc-100"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setShowSplitModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={handleSplitCharacter}>
                Confirm Split
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
