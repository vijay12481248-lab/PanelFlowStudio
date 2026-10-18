import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  VideoScript,
  ScriptSegment,
  ScriptValidationReport,
  AdaptationProfile,
  CharacterEntity,
  StoryboardDocument,
  StoryboardSegment,
  StoryboardPanelRef,
} from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";

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
  const { reportError, inspectError } = useError();
  const [viewMode, setViewMode] = useState<"storyboard" | "script">("storyboard");
  const [script, setScript] = useState<VideoScript | null>(null);
  const [storyboard, setStoryboard] = useState<StoryboardDocument | null>(null);
  const [characters, setCharacters] = useState<CharacterEntity[]>([]);
  const [validationReport, setValidationReport] = useState<ScriptValidationReport | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<AdaptationProfile>(project.settings?.visual_storytelling ? "DRAMATIC_NARRATION" : "FAITHFUL");

  const [loading, setLoading] = useState<boolean>(true);
  const [jobMessage, setJobMessage] = useState("");
  const [generating, setGenerating] = useState<boolean>(false);
  const [validating, setValidating] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [realigning, setRealigning] = useState<boolean>(false);

  // Active segment for inline editing
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [segmentDuration, setSegmentDuration] = useState(2);
  const [segmentText, setSegmentText] = useState<string>("");
  const [segmentEmotion, setSegmentEmotion] = useState<string>("NEUTRAL");
  const [segmentIntensity, setSegmentIntensity] = useState<number>(0.5);
  const [filterUnsupportedOnly, setFilterUnsupportedOnly] = useState<boolean>(false);

  const getUnsupportedIssue = (segId: string) => {
    if (!validationReport?.issues) return null;
    return validationReport.issues.find(
      (iss) => iss.segment_id === segId && (iss.status === "UNSUPPORTED" || (iss.reasons && iss.reasons.length > 0))
    );
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, chars, sb] = await Promise.all([
        api.getScript(project.id).catch(() => null),
        api.listCharacters(project.id).catch(() => []),
        api.getStoryboard(project.id).catch(() => null),
      ]);
      setScript(s);
      setCharacters(chars);
      if (sb) setStoryboard(sb);
      if (s) {
        setSelectedProfile(s.adaptation_profile);
        api.validateScript(project.id, s.script_id)
          .then((val) => setValidationReport(val))
          .catch((err) => console.warn("Auto-validation skipped:", err));
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

  const handleRealignStoryboard = async () => {
    setRealigning(true);
    try {
      const sb = await api.realignStoryboard(project.id);
      setStoryboard(sb);
    } catch (err: any) {
      reportError({
        title: "Storyboard Realignment Failed",
        message: err.message || "Failed to realign storyboard segments.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setRealigning(false);
    }
  };

  const handleUpdateStoryboardSegment = async (segmentId: string, patch: any) => {
    try {
      const updated = await api.updateStoryboardSegment(project.id, segmentId, patch);
      if (storyboard) {
        setStoryboard({
          ...storyboard,
          segments: storyboard.segments.map(s => s.segment_id === segmentId ? updated : s),
        });
      }
      if (script) {
        api.validateScript(project.id, script.script_id)
          .then((val) => setValidationReport(val))
          .catch(() => {});
      }
    } catch (err: any) {
      reportError({
        title: "Storyboard Update Failed",
        message: err.message || "Could not update storyboard segment.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: { segmentId, patch, error: err },
      });
    }
  };

  const handleSegmentAction = async (segmentId: string, action: string) => {
    if (!script) return;
    setGenerating(true);
    try {
      setScript(await api.editScriptSegment(project.id, script.script_id, segmentId, action));
      setValidationReport(null);
      const sb = await api.getStoryboard(project.id).catch(() => null);
      if (sb) setStoryboard(sb);
    } catch (err: any) {
      reportError({
        title: "Script Action Failed",
        message: err.message || "Script action execution failed.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: { segmentId, action, error: err },
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateScript = async () => {
    setGenerating(true);
    try {
      const { job_id } = await api.generateScriptJob(project.id, selectedProfile);
      await api.waitForWorkflowJob(job_id, job => setJobMessage(`${Math.round(job.progress * 100)}% · ${job.message}`));
      const newScript = await api.getScript(project.id);
      setScript(newScript);
      const val = await api.validateScript(project.id, newScript.script_id);
      setValidationReport(val);
      const sb = await api.getStoryboard(project.id).catch(() => null);
      if (sb) setStoryboard(sb);
    } catch (err: any) {
      reportError({
        title: "Script Adaptation Failed",
        message: err.message || "Failed to adapt and generate video script.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "SCRIPT_GENERATION",
        rawDetails: err,
      });
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
      reportError({
        title: "Script Validation Failed",
        message: err.message || "Validation checks encountered an unexpected error.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
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
        estimated_duration: segmentDuration,
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
      reportError({
        title: "Failed to Save Script Segment",
        message: err.message || "Could not save segment changes to disk.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: { segId, error: err },
      });
    }
  };

  const handleApproveScript = async () => {
    if (!script) return;
    setApproving(true);
    try {
      const res = await api.approveScript(project.id, script.script_id);
      const updated = await api.getProject(project.id);
      onScriptApproved(updated);
    } catch (err: any) {
      try {
        const val = await api.validateScript(project.id, script.script_id);
        setValidationReport(val);
      } catch (valErr) {
        console.warn("Validation fetch on approve failure:", valErr);
      }
      reportError({
        title: "Approval Gate Blocked",
        message: err.message || "Strict script approval conditions were not satisfied.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: { scriptId: script.script_id, error: err },
      });
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

      {/* Unsupported Claims Attention Banner */}
      {validationReport && validationReport.unsupported_segments > 0 && script && (
        <Card className="p-4 bg-rose-950/30 border-rose-800/80 text-rose-200 space-y-3 shadow-lg shadow-rose-950/20">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-rose-900/40 pb-2.5">
            <div className="flex items-center gap-2">
              <Icons.AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0" />
              <h3 className="font-bold text-sm text-rose-100">
                Approval Gate Blocked: {validationReport.unsupported_segments} Unsupported Statement{validationReport.unsupported_segments > 1 ? "s" : ""}
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant={filterUnsupportedOnly ? "primary" : "secondary"}
                size="sm"
                onClick={() => setFilterUnsupportedOnly(!filterUnsupportedOnly)}
                className={`text-xs ${filterUnsupportedOnly ? "bg-rose-600 hover:bg-rose-500 text-white" : "border-rose-700/60 text-rose-300 hover:bg-rose-900/40"}`}
              >
                {filterUnsupportedOnly ? "Show All Lines" : "Filter: Show Unsupported Only"}
              </Button>
            </div>
          </div>
          <p className="text-xs text-rose-300/90 leading-relaxed">
            The faithfulness validator detected statements lacking sufficient grounding evidence in source panels, OCR text, or registered characters. Review and fix the flagged lines below to satisfy the milestone gate:
          </p>
          <div className="space-y-2 pt-1">
            {validationReport.issues
              .filter((iss) => iss.status === "UNSUPPORTED" || (iss.reasons && iss.reasons.length > 0))
              .map((iss, idx) => {
                const segMatch = script.segments.find((s) => s.segment_id === iss.segment_id);
                const segSeq = segMatch ? segMatch.sequence : idx + 1;
                const reasons = iss.reasons || iss.issues || [
                  "Line makes claims with negligible lexical or semantic grounding in source panels, text, or events.",
                ];

                return (
                  <div
                    key={iss.segment_id || idx}
                    className="bg-zinc-950/80 border border-rose-900/60 rounded-lg p-3 text-xs space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-bold font-mono text-rose-400">
                          Statement #{segSeq}
                        </span>
                        <span className="text-[10px] uppercase font-bold bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded">
                          {segMatch?.type || "LINE"}
                        </span>
                        <span className="text-xs text-zinc-300">
                          {segMatch?.speaker_character_id || "SPEAKER"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (iss.segment_id) {
                            setEditingSegmentId(iss.segment_id);
                            if (segMatch) {
                              setSegmentText(segMatch.text);
                              setSegmentEmotion(segMatch.emotion || "NEUTRAL");
                              setSegmentIntensity(segMatch.intensity || 0.5);
                              setSegmentDuration(segMatch.estimated_duration || 2.0);
                            }
                            const el = document.getElementById(`seg-${iss.segment_id}`);
                            if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                          }
                        }}
                        className="text-[11px] font-medium bg-rose-900/60 hover:bg-rose-800 text-rose-200 px-2.5 py-1 rounded transition-colors"
                      >
                        Edit This Line
                      </button>
                    </div>

                    <p className="font-mono text-zinc-100 bg-zinc-900/80 p-2 rounded border border-zinc-800">
                      "{iss.text || segMatch?.text}"
                    </p>

                    <div className="space-y-1 text-[11px] text-rose-300/80">
                      <span className="font-semibold text-rose-400">Failure Reason:</span>
                      {reasons.map((r, rIdx) => (
                        <div key={rIdx} className="flex items-start gap-1.5 pl-1">
                          <span className="text-rose-400">•</span>
                          <span>{r}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>
        </Card>
      )}

      {generating && <p role="status" className="text-sm text-indigo-300">{jobMessage || "Updating narration…"}</p>}
      {/* View Mode Toggle & Storyboard Actions */}
      {script && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === "storyboard" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setViewMode("storyboard")}
            >
              <Icons.Layout className="w-3.5 h-3.5 mr-1.5" />
              Visual Storyboard (Two-Pane)
            </Button>
            <Button
              variant={viewMode === "script" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setViewMode("script")}
            >
              <Icons.FileText className="w-3.5 h-3.5 mr-1.5" />
              Spoken Script List
            </Button>
          </div>

          {viewMode === "storyboard" && (
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-zinc-400 font-mono">
                Duration: <strong>{storyboard?.total_duration_sec ?? script.estimated_duration}s</strong>
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleRealignStoryboard}
                disabled={realigning || generating}
                title="Recalculates frame alignment while strictly preserving manual edits"
              >
                <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${realigning ? "animate-spin" : ""}`} />
                {realigning ? "Realigning..." : "Realign Frames"}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Script / Storyboard Content */}
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
      ) : viewMode === "storyboard" && storyboard && storyboard.segments.length > 0 ? (
        /* Two-Pane Visual Storyboard View */
        <div className="space-y-4">
          {(filterUnsupportedOnly
            ? storyboard.segments.filter((s) => Boolean(getUnsupportedIssue(s.segment_id)))
            : storyboard.segments
          ).map((sbSeg) => {
            const isEditing = editingSegmentId === sbSeg.segment_id;
            const issue = getUnsupportedIssue(sbSeg.segment_id);
            const isUnsupported = Boolean(issue);
            return (
              <Card
                key={sbSeg.segment_id}
                id={`seg-${sbSeg.segment_id}`}
                className={`p-4 transition-colors ${
                  isUnsupported
                    ? "bg-rose-950/20 border-rose-600/80 shadow-lg shadow-rose-950/30"
                    : isEditing
                    ? "bg-zinc-950 border-indigo-600"
                    : "bg-zinc-950 border border-zinc-800 hover:border-zinc-700"
                }`}
              >
                <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
                  {/* Left Column: Manga Visuals (5 cols) */}
                  <div className="md:col-span-5 space-y-2.5 border-b md:border-b-0 md:border-r border-zinc-800/80 pb-4 md:pb-0 md:pr-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-indigo-400 font-mono">
                        Beat #{sbSeg.sequence} · Scene {sbSeg.scene_id.slice(-6)}
                      </span>
                      <Badge variant="accent" className="text-[9px] uppercase font-bold">
                        {sbSeg.supporting_panels.length} {sbSeg.supporting_panels.length === 1 ? "Frame" : "Frames"}
                      </Badge>
                    </div>

                    {/* Supporting Panel Crops */}
                    <div className="space-y-3">
                      {sbSeg.supporting_panels.map((pRef, pIdx) => (
                        <div key={`${pRef.panel_id}-${pIdx}`} className="space-y-1.5">
                          <div className="relative group rounded-lg overflow-hidden border border-zinc-800 bg-zinc-900 aspect-video flex items-center justify-center">
                            <img
                              src={pRef.image_url || api.getPanelImageUrl(project.id, pRef.panel_id)}
                              alt={`Manga panel ${pRef.panel_id}`}
                              className="w-full h-full object-contain"
                              loading="lazy"
                            />
                            <div className="absolute top-2 left-2 flex items-center gap-1.5">
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-black/75 text-zinc-200">
                                #{pRef.reading_order}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-indigo-950/80 border border-indigo-700 text-indigo-300">
                                {pRef.role}
                              </span>
                            </div>
                            <div className="absolute bottom-2 right-2">
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/80 text-emerald-400">
                                {pRef.sub_duration_sec}s
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono px-1">
                            <span>Camera Motion:</span>
                            <select
                              value={pRef.camera_motion?.type || "SLOW_PUSH"}
                              onChange={(e) => {
                                const newPanels = sbSeg.supporting_panels.map((p, idx) =>
                                  idx === pIdx
                                    ? {
                                        ...p,
                                        camera_motion: {
                                          ...p.camera_motion,
                                          type: e.target.value,
                                        },
                                      }
                                    : p
                                );
                                handleUpdateStoryboardSegment(sbSeg.segment_id, {
                                  supporting_panels: newPanels,
                                });
                              }}
                              className="bg-zinc-900 border border-zinc-700 rounded px-1.5 py-0.5 text-zinc-200 text-[10px]"
                            >
                              <option value="SLOW_PUSH">SLOW_PUSH (Pan/Zoom)</option>
                              <option value="CHARACTER_FOCUS">CHARACTER_FOCUS</option>
                              <option value="REACTION_CLOSEUP">REACTION_CLOSEUP</option>
                              <option value="IMPACT">IMPACT (Combat Shake)</option>
                              <option value="PAN">PAN (Horizontal/Vertical)</option>
                              <option value="STATIC">STATIC</option>
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right Column: Spoken Narration & Audio Lock (7 cols) */}
                  <div className="md:col-span-7 space-y-3 flex flex-col justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                          <Badge variant="neutral" className="text-[10px] uppercase font-bold">
                            NARRATOR
                          </Badge>
                          <Badge variant={sbSeg.emotion === "TENSE" || sbSeg.emotion === "ANGRY" ? "danger" : "neutral"} className="text-[10px]">
                            {sbSeg.emotion} ({Math.round(sbSeg.intensity * 100)}%)
                          </Badge>
                          {isUnsupported && (
                            <Badge variant="danger" className="text-[9px] font-bold">
                              ⚠️ UNSUPPORTED CLAIM
                            </Badge>
                          )}
                          {sbSeg.manual_override && (
                            <span className="text-[9px] bg-amber-950/60 border border-amber-800 text-amber-300 px-1.5 py-0.5 rounded font-mono font-bold">
                              LOCKED OVERRIDE
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono text-zinc-300 font-bold">
                            {sbSeg.measured_duration_sec}s
                          </span>
                          <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold ${
                            sbSeg.audio_clip_path
                              ? "bg-emerald-950/60 border border-emerald-800 text-emerald-300"
                              : "bg-zinc-800 text-zinc-400"
                          }`}>
                            {sbSeg.audio_clip_path ? "🔊 TTS LOCKED" : "⏱️ ESTIMATED"}
                          </span>
                        </div>
                      </div>

                      {/* Narration Text Content / Editing */}
                      {isEditing ? (
                        <div className="space-y-2 pt-1">
                          <textarea
                            value={segmentText}
                            onChange={(e) => setSegmentText(e.target.value)}
                            rows={3}
                            className="w-full bg-zinc-900 border border-indigo-600 rounded-lg p-2.5 text-xs text-zinc-100 font-mono focus:outline-none"
                          />
                          <div className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-3">
                              <label className="text-zinc-400">Emotion:</label>
                              <select
                                value={segmentEmotion}
                                onChange={(e) => setSegmentEmotion(e.target.value)}
                                className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-zinc-200 text-xs font-mono"
                              >
                                <option value="NEUTRAL">NEUTRAL</option>
                                <option value="TENSE">TENSE</option>
                                <option value="CALM">CALM</option>
                                <option value="DETERMINED">DETERMINED</option>
                                <option value="SURPRISED">SURPRISED</option>
                                <option value="ANGRY">ANGRY</option>
                                <option value="SAD">SAD</option>
                              </select>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button variant="ghost" size="sm" onClick={() => setEditingSegmentId(null)}>
                                Cancel
                              </Button>
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={async () => {
                                  await handleUpdateStoryboardSegment(sbSeg.segment_id, {
                                    text: segmentText,
                                    emotion: segmentEmotion,
                                    intensity: segmentIntensity,
                                  });
                                  setEditingSegmentId(null);
                                }}
                              >
                                Save Beat
                              </Button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-zinc-200 font-medium leading-relaxed bg-zinc-900/60 p-3 rounded-lg border border-zinc-800/80">
                          "{sbSeg.text}"
                        </p>
                      )}

                      {isUnsupported && (
                        <div className="p-2.5 rounded-lg bg-rose-950/50 border border-rose-900/60 text-xs text-rose-200 space-y-1">
                          <span className="font-semibold text-rose-300 flex items-center gap-1.5">
                            <Icons.AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                            Why this claim is blocked:
                          </span>
                          {(issue?.reasons || issue?.issues || [
                            "Negligible lexical or semantic grounding in source panels, text, or events.",
                          ]).map((r, rIdx) => (
                            <p key={rIdx} className="text-[11px] text-rose-300/90 pl-5">
                              • {r}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Audio & Ducking Directives */}
                    <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between text-[11px] text-zinc-400 font-mono">
                      <div className="flex items-center gap-3">
                        <span>🎵 Music: <strong className="text-zinc-300">{sbSeg.music_cue?.intent || "CALM"}</strong></span>
                        <span>Ducking: <strong className="text-amber-400">{sbSeg.music_cue?.ducking_gain_db ?? -14.0} dB</strong></span>
                        <span>SFX: <strong className="text-zinc-300">{sbSeg.sfx_cue?.type || "NONE"}</strong></span>
                      </div>

                      {!isEditing && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingSegmentId(sbSeg.segment_id);
                            setSegmentText(sbSeg.text);
                            setSegmentEmotion(sbSeg.emotion);
                            setSegmentIntensity(sbSeg.intensity);
                          }}
                          className="text-xs text-zinc-400 hover:text-zinc-200"
                        >
                          Edit Line
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        /* Original Spoken Script List */
        <div className="space-y-3">
          {(filterUnsupportedOnly
            ? script.segments.filter(
                (s) => Boolean(getUnsupportedIssue(s.segment_id)) || s.faithfulness_status === "UNSUPPORTED"
              )
            : script.segments
          ).map((seg) => {
            const isEditing = editingSegmentId === seg.segment_id;
            const issue = getUnsupportedIssue(seg.segment_id);
            const isUnsupported = Boolean(issue) || seg.faithfulness_status === "UNSUPPORTED";
            const speakerName =
              seg.type === "NARRATOR"
                ? "NARRATOR"
                : characters.find((c) => c.character_id === seg.speaker_character_id)?.canonical_name ||
                  seg.speaker_character_id ||
                  "SPEAKER";

            return (
              <Card
                key={seg.segment_id}
                id={`seg-${seg.segment_id}`}
                className={`p-4 border transition-all ${
                  isUnsupported
                    ? "bg-rose-950/20 border-rose-600/80 shadow-lg shadow-rose-950/30"
                    : isEditing
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

                    {seg.source_evidence.panel_ids.length > 0 && (
                      <div className="flex gap-2 overflow-x-auto py-2" aria-label="Narration source panels">
                        {seg.source_evidence.panel_ids.map(panelId => (
                          <a key={panelId} href={api.getPanelImageUrl(project.id, panelId)} target="_blank" rel="noreferrer" title="Open source panel">
                            <img src={api.getPanelImageUrl(project.id, panelId)} alt={`Source panel ${panelId}`} className="h-48 max-w-60 object-contain rounded bg-zinc-950" loading="lazy" />
                          </a>
                        ))}
                      </div>
                    )}
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

                        <label className="flex items-center gap-2 text-xs text-zinc-400">Estimated seconds
                          <input type="number" min="0.1" step="0.1" value={segmentDuration} onChange={e => setSegmentDuration(Number(e.target.value))} className="w-24 rounded bg-zinc-950 border border-zinc-700 p-1" />
                        </label>
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

                    {isUnsupported && (
                      <div className="p-2.5 rounded-lg bg-rose-950/50 border border-rose-900/60 text-xs text-rose-200 space-y-1">
                        <span className="font-semibold text-rose-300 flex items-center gap-1.5">
                          <Icons.AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                          Why this claim is blocked:
                        </span>
                        {(issue?.reasons || issue?.issues || [
                          "Negligible lexical or semantic grounding in source panels, text, or events.",
                        ]).map((r, rIdx) => (
                          <p key={rIdx} className="text-[11px] text-rose-300/90 pl-5">
                            • {r}
                          </p>
                        ))}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-1" aria-label="Narration editing actions">
                      {[["regenerate", "Regenerate"], ["shorten", "Shorten"], ["expand", "Expand"], ["more_drama", "More drama"], ["less_drama", "Less drama"], ["split", "Split"], ["merge_next", "Merge next"], ["move_up", "Move up"], ["move_down", "Move down"], ["remove", "Remove"]].map(([action, label]) => (
                        <Button key={action} variant="ghost" size="sm" disabled={generating} onClick={() => handleSegmentAction(seg.segment_id, action)}>{label}</Button>
                      ))}
                    </div>
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
                        setSegmentDuration(seg.estimated_duration);
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
