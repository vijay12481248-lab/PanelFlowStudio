import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  VideoScript,
  ScriptSegment,
  ScriptValidationReport,
  AdaptationProfile,
  CharacterEntity,
} from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface ScriptReviewScreenProps {
  project: Project;
  onBack: () => void;
  onScriptApproved: (updatedProject: Project) => void;
  onProceedToAudio?: (proj: Project) => void;
  onProjectUpdated?: (updatedProject: Project) => void;
}

export const ScriptReviewScreen: React.FC<ScriptReviewScreenProps> = ({
  project,
  onBack,
  onScriptApproved,
  onProceedToAudio,
  onProjectUpdated,
}) => {
  const [script, setScript] = useState<VideoScript | null>(null);
  const [characters, setCharacters] = useState<CharacterEntity[]>([]);
  const [validationReport, setValidationReport] = useState<ScriptValidationReport | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<AdaptationProfile>("FAITHFUL");

  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [validating, setValidating] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);

  // Active segment for inline editing
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [segmentText, setSegmentText] = useState<string>("");
  const [segmentEmotion, setSegmentEmotion] = useState<string>("NEUTRAL");
  const [segmentIntensity, setSegmentIntensity] = useState<number>(0.5);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, chars] = await Promise.all([
        api.getScript(project.id).catch(() => null),
        api.listCharacters(project.id).catch(() => []),
      ]);
      setScript(s);
      setCharacters(chars);
      if (s) {
        setSelectedProfile(s.adaptation_profile);
      }
    } catch (err: any) {
      console.error("Failed to load script:", err);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleGenerateScript = async () => {
    setGenerating(true);
    try {
      const newScript = await api.generateScript(project.id, selectedProfile);
      setScript(newScript);
      const val = await api.validateScript(project.id, newScript.script_id);
      setValidationReport(val);
    } catch (err: any) {
      alert(`Failed to adapt script: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleValidateScript = async () => {
    if (!script) return;
    setValidating(true);
    try {
      const report = await api.validateScript(project.id, script.script_id);
      setValidationReport(report);
    } catch (err: any) {
      alert(`Validation failed: ${err.message}`);
    } finally {
      setValidating(false);
    }
  };

  const handleSaveSegment = async (segId: string) => {
    if (!script) return;
    try {
      await api.updateScriptSegment(project.id, script.script_id, segId, {
        text: segmentText,
        emotion: segmentEmotion,
        intensity: segmentIntensity,
      });
      setEditingSegmentId(null);
      await loadData();
      if (script) {
        try {
          const val = await api.validateScript(project.id, script.script_id);
          setValidationReport(val);
        } catch (valErr) {
          console.warn("Validation skipped or unavailable:", valErr);
        }
      }
      if (onProjectUpdated) {
        const updatedProj = await api.getProject(project.id);
        onProjectUpdated(updatedProj);
      }
    } catch (err: any) {
      alert(`Failed to save script segment: ${err.message}`);
    }
  };

  const handleApproveScript = async () => {
    if (!script) return;
    setApproving(true);
    try {
      const res = await api.approveScript(project.id, script.script_id);
      const updated = await api.getProject(project.id);
      alert(res.message || "Script approved successfully! Project advanced to SCRIPT_APPROVED.");
      onScriptApproved(updated);
    } catch (err: any) {
      alert(`Approval Gate Blocked: ${err.message}`);
    } finally {
      setApproving(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const isApproved = project.current_stage === "SCRIPT_APPROVED" || script?.status === "APPROVED";

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
              Video Script Adaptation & Review
            </h1>
            <Badge variant={isApproved ? "success" : "neutral"} className="uppercase font-mono">
              {script?.status || "DRAFT"}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Layer C presentation representation: Synthesized narrator lines, character dialogue, pacing timing, and advisory production intent.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Adaptation Profile Selector */}
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value as AdaptationProfile)}
            disabled={generating}
            className="bg-zinc-900 border border-zinc-700 text-xs text-zinc-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-mono"
          >
            <option value="FAITHFUL">Faithful (Direct Source)</option>
            <option value="CONDENSED">Condensed (Paced Recap)</option>
            <option value="DRAMATIC_NARRATION">Dramatic Narration</option>
            <option value="ACCESSIBLE_RECAP">Accessible Recap</option>
          </select>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleGenerateScript}
            disabled={generating}
          >
            <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${generating ? "animate-spin" : ""}`} />
            {script ? "Re-Adapt Script" : "Generate Script"}
          </Button>

          {script && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleValidateScript}
              disabled={validating}
            >
              <Icons.Check className="w-3.5 h-3.5 mr-1.5" />
              Validate Faithfulness
            </Button>
          )}

          <Button
            variant="primary"
            size="sm"
            onClick={handleApproveScript}
            disabled={approving || !script}
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
          >
            <Icons.Check className="w-3.5 h-3.5 mr-1.5" />
            Approve Script
          </Button>

          {isApproved && onProceedToAudio && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onProceedToAudio(project)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Proceed to Audio <Icons.ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Script Metrics Overview */}
      {script && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Estimated Duration
            </span>
            <div className="text-xl font-bold font-mono text-indigo-400">
              {formatDuration(script.estimated_duration)}
              <span className="text-xs text-zinc-400 ml-1.5 font-normal">
                ({Math.round(script.estimated_duration)}s)
              </span>
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Total Segments
            </span>
            <div className="text-xl font-bold font-mono text-zinc-100">
              {script.segments.length} lines
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Faithfulness Coverage
            </span>
            <div className="text-xl font-bold font-mono text-emerald-400">
              {validationReport ? `${Math.round(validationReport.coverage_score * 100)}%` : "100%"}
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Adaptation Profile
            </span>
            <div className="text-sm font-bold font-mono text-zinc-200 mt-1">
              {script.adaptation_profile}
            </div>
          </Card>
        </div>
      )}

      {/* Strict Milestone Guardrail Banner */}
      <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 flex items-start gap-3">
        <Icons.Info className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold text-zinc-200">
            Milestone 4 Boundary Guard Active
          </p>
          <p>
            Script adaptation produces semantic presentation metadata (dialogue, cadence durations, emotion, and motion intent).
            Downstream voice generation (TTS), musical composition, and FFmpeg video rendering remain locked until subsequent milestones.
          </p>
        </div>
      </div>

      {/* Script Segments List */}
      {!script ? (
        <Card className="p-12 text-center bg-zinc-900 border-zinc-800 space-y-4">
          <Icons.FileText className="w-10 h-10 text-zinc-600 mx-auto" />
          <div className="space-y-1">
            <h3 className="font-bold text-zinc-200">No Video Script Adapted Yet</h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              Click "Generate Script" above to synthesize an adapted spoken script from the approved Narrative IR.
            </p>
          </div>
          <Button variant="primary" onClick={handleGenerateScript} disabled={generating}>
            Generate Script
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {script.segments.map((seg) => {
            const isEditing = editingSegmentId === seg.segment_id;
            const speakerName =
              seg.type === "NARRATOR"
                ? "NARRATOR"
                : characters.find((c) => c.character_id === seg.speaker_character_id)?.canonical_name ||
                  seg.speaker_character_id ||
                  "SPEAKER";

            return (
              <Card
                key={seg.segment_id}
                className={`p-4 border transition-all ${
                  isEditing
                    ? "bg-zinc-900 border-indigo-600 shadow-lg shadow-indigo-950/30"
                    : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  {/* Segment Details & Text */}
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-indigo-400 font-mono">
                        #{seg.sequence}
                      </span>

                      <Badge
                        variant={seg.type === "NARRATOR" ? "neutral" : "accent"}
                        className="text-[10px] uppercase font-bold"
                      >
                        {seg.type}
                      </Badge>

                      <span className="text-xs font-bold text-zinc-100">
                        {speakerName}
                      </span>

                      <span className="text-[11px] font-mono text-zinc-400">
                        {seg.estimated_start}s - {seg.estimated_end}s ({seg.estimated_duration}s)
                      </span>

                      <Badge
                        variant={
                          seg.faithfulness_status === "SUPPORTED"
                            ? "success"
                            : seg.faithfulness_status === "WEAKLY_SUPPORTED"
                            ? "warning"
                            : "danger"
                        }
                        className="text-[9px]"
                      >
                        {seg.faithfulness_status}
                      </Badge>

                      {seg.manual_override && (
                        <span className="text-[9px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded font-mono">
                          EDITED
                        </span>
                      )}
                    </div>

                    {isEditing ? (
                      <div className="space-y-3 pt-2">
                        <textarea
                          value={segmentText}
                          onChange={(e) => setSegmentText(e.target.value)}
                          rows={2}
                          className="w-full bg-zinc-950 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-100 font-mono focus:outline-none focus:border-indigo-500"
                        />

                        <div className="flex flex-wrap items-center gap-4 text-xs">
                          <div className="flex items-center gap-2">
                            <label className="text-zinc-400">Emotion:</label>
                            <select
                              value={segmentEmotion}
                              onChange={(e) => setSegmentEmotion(e.target.value)}
                              className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-zinc-200 font-mono"
                            >
                              <option value="NEUTRAL">NEUTRAL</option>
                              <option value="DETERMINED">DETERMINED</option>
                              <option value="TENSE">TENSE</option>
                              <option value="CALM">CALM</option>
                              <option value="JOYFUL">JOYFUL</option>
                              <option value="SAD">SAD</option>
                              <option value="ANGRY">ANGRY</option>
                              <option value="FEARFUL">FEARFUL</option>
                              <option value="SURPRISED">SURPRISED</option>
                            </select>
                          </div>

                          <div className="flex items-center gap-2">
                            <label className="text-zinc-400">Intensity:</label>
                            <input
                              type="range"
                              min={0.1}
                              max={1.0}
                              step={0.1}
                              value={segmentIntensity}
                              onChange={(e) => setSegmentIntensity(parseFloat(e.target.value))}
                              className="w-24 accent-indigo-500"
                            />
                            <span className="font-mono text-zinc-300">
                              {Math.round(segmentIntensity * 100)}%
                            </span>
                          </div>
                        </div>

                        <div className="flex justify-end gap-2 pt-2">
                          <Button variant="ghost" size="sm" onClick={() => setEditingSegmentId(null)}>
                            Cancel
                          </Button>
                          <Button variant="primary" size="sm" onClick={() => handleSaveSegment(seg.segment_id)}>
                            Save Line
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-200 font-medium leading-relaxed">
                        "{seg.text}"
                      </p>
                    )}

                    {/* Metadata tags */}
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-zinc-400">
                      <span>Emotion: <strong className="text-zinc-300">{seg.emotion} ({Math.round(seg.intensity * 100)}%)</strong></span>
                      {seg.motion_intent && <span>Motion: <em className="text-zinc-300">{seg.motion_intent}</em></span>}
                      {seg.music_intent && <span>Music: <em className="text-zinc-300">{seg.music_intent}</em></span>}
                      {seg.sfx_intent && <span>SFX: <em className="text-zinc-300">{seg.sfx_intent}</em></span>}
                    </div>

                    {/* Evidence Provenance */}
                    <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono">
                      <span>Evidence:</span>
                      {seg.source_evidence.panel_ids.map((pid, idx) => (
                        <span key={idx} className="bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                          Panel #{pid.slice(-4)}
                        </span>
                      ))}
                      {seg.source_evidence.text_region_ids.map((rid, idx) => (
                        <span key={idx} className="bg-zinc-800 text-indigo-400 px-1.5 py-0.5 rounded">
                          Region #{rid.slice(-4)}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Edit Button */}
                  {!isEditing && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingSegmentId(seg.segment_id);
                        setSegmentText(seg.text);
                        setSegmentEmotion(seg.emotion);
                        setSegmentIntensity(seg.intensity);
                      }}
                      className="text-xs text-zinc-400 hover:text-zinc-200 flex-shrink-0"
                    >
                      Edit
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
