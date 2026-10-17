import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type { Project, AudioTimelineResponse, AudioInterval } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons } from "@panelflow/ui";

export interface AudioScreenProps {
  project: Project;
  onBack: () => void;
  onAudioApproved: (updatedProject: Project) => void;
  onProceedToMotion: (proj: Project) => void;
}

export const AudioScreen: React.FC<AudioScreenProps> = ({
  project,
  onBack,
  onAudioApproved,
  onProceedToMotion,
}) => {
  const [timelineData, setTimelineData] = useState<AudioTimelineResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getAudioTimeline(project.id);
      setTimelineData(data);
    } catch {
      setTimelineData(null);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  const handleGenerateAudio = async () => {
    setGenerating(true);
    try {
      const result = await api.generateAudio(project.id);
      setTimelineData(result);
    } catch (err: any) {
      alert(`Audio generation failed: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleRegenerateSegment = async (segmentId: string) => {
    setRegeneratingId(segmentId);
    try {
      await api.regenerateAudioSegment(project.id, segmentId);
      await loadTimeline();
    } catch (err: any) {
      alert(`Selective regeneration failed: ${err.message}`);
    } finally {
      setRegeneratingId(null);
    }
  };

  const handleApproveAudio = async () => {
    setApproving(true);
    try {
      await api.approveAudio(project.id);
      const updated = await api.getProject(project.id);
      setTimelineData((prev) => (prev ? { ...prev, status: "APPROVED" } : null));
      onAudioApproved(updated);
    } catch (err: any) {
      alert(`Audio approval failed: ${err.message}`);
    } finally {
      setApproving(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const isApproved = timelineData?.status === "APPROVED" || project.current_stage === "AUDIO_APPROVED";

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
              Audio Director & Voice Review
            </h1>
            <Badge variant={isApproved ? "success" : "neutral"} className="uppercase font-mono">
              {timelineData?.status || "NOT_GENERATED"}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            F5-TTS neural dialogue synthesis with measured speech durations and ACE-Step dynamic background score.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGenerateAudio}
            disabled={generating}
          >
            <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${generating ? "animate-spin" : ""}`} />
            {timelineData ? "Regenerate All Audio" : "Generate Master Audio"}
          </Button>

          {timelineData && (
            <Button
              variant="primary"
              size="sm"
              onClick={handleApproveAudio}
              disabled={approving || isApproved}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              <Icons.Check className="w-3.5 h-3.5 mr-1.5" />
              {isApproved ? "Audio Approved" : "Approve Audio"}
            </Button>
          )}

          {isApproved && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onProceedToMotion(project)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Proceed to Motion <Icons.ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Stats Cards */}
      {timelineData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Total Duration
            </span>
            <div className="text-xl font-bold font-mono text-indigo-400">
              {formatDuration(timelineData.total_duration)}
              <span className="text-xs text-zinc-400 ml-1.5 font-normal">
                ({timelineData.total_duration.toFixed(1)}s)
              </span>
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Dialogue Lines
            </span>
            <div className="text-xl font-bold font-mono text-zinc-100">
              {timelineData.timeline.speech_intervals_count || 0} takes
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Sample Rate
            </span>
            <div className="text-xl font-bold font-mono text-emerald-400">
              48,000 Hz
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Background Score
            </span>
            <div className="text-sm font-bold font-mono text-zinc-200 mt-1 truncate">
              ACE-Step Master (D Dorian)
            </div>
          </Card>
        </div>
      )}

      {/* Cache & Invalidation Banner */}
      <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 flex items-start gap-3">
        <Icons.Info className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold text-zinc-200">
            Selective Invalidation & Authoritative Durations
          </p>
          <p>
            Speech durations are measured directly from neural WAV files with 0.5s pause intervals.
            Use "Regenerate Take" to re-synthesize an individual line without touching cached audio for any other segment.
          </p>
        </div>
      </div>

      {/* Intervals List */}
      {loading ? (
        <Card className="p-12 text-center bg-zinc-900 border-zinc-800 space-y-4">
          <Icons.Rotate className="w-8 h-8 text-zinc-600 animate-spin mx-auto" />
          <p className="text-xs text-zinc-400">Loading Master Audio Timeline...</p>
        </Card>
      ) : !timelineData ? (
        <Card className="p-12 text-center bg-zinc-900 border-zinc-800 space-y-4">
          <Icons.Folder className="w-10 h-10 text-zinc-600 mx-auto" />
          <div className="space-y-1">
            <h3 className="font-bold text-zinc-200">No Audio Timeline Generated Yet</h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              Click "Generate Master Audio" above to synthesize character dialogue with F5-TTS neural models and align the cinematic score.
            </p>
          </div>
          <Button variant="primary" onClick={handleGenerateAudio} disabled={generating}>
            Generate Master Audio
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {timelineData.timeline.intervals.map((iv, idx) => {
            const isRegenerating = regeneratingId === iv.script_segment_id;
            const audioSrc = api.getAudioFileUrl(project.id, iv.audio_file_uri);

            return (
              <Card
                key={iv.interval_id || idx}
                className="p-4 bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors"
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {/* Left: Metadata & Cue */}
                  <div className="space-y-1.5 flex-1 min-w-0">
                    {(() => {
                      const startTime = (iv.start_time ?? 0);
                      const endTime = (iv.end_time ?? 0);
                      const duration = (iv.duration ?? Math.max(0, endTime - startTime));
                      const charName = (iv as any).character_id || (iv as any).speaker_character_id || "";
                      const cue = (iv as any).cue_text || (iv as any).text || "";
                      const sourceType = (iv as any).timeline_source_type || ((iv as any).is_speech !== false ? "SPEECH" : "MUSIC");
                      const gainDb = (iv as any).gain_db ?? 0;

                      return (
                        <>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold text-indigo-400 font-mono">
                              #{idx + 1}
                            </span>
                            <Badge
                              variant={sourceType === "SPEECH" ? "accent" : "neutral"}
                              className="text-[10px] uppercase font-bold"
                            >
                              {sourceType}
                            </Badge>
                            {charName && (
                              <span className="text-xs font-bold text-zinc-100 capitalize">
                                {charName}
                              </span>
                            )}
                            <span className="text-[11px] font-mono text-zinc-400">
                              {startTime.toFixed(2)}s - {endTime.toFixed(2)}s ({duration.toFixed(2)}s)
                            </span>
                            <span className="text-[10px] font-mono text-zinc-500">
                              {gainDb >= 0 ? `+${gainDb}` : gainDb} dB
                            </span>
                          </div>

                          {cue && (
                            <p className="text-xs text-zinc-200 italic font-medium leading-relaxed">
                              "{cue}"
                            </p>
                          )}
                        </>
                      );
                    })()}
                  </div>

                  {/* Right: Audio Player & Regenerate */}
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <audio
                      controls
                      src={audioSrc}
                      preload="none"
                      className="h-8 max-w-[240px] rounded"
                    />

                    {iv.script_segment_id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRegenerateSegment(iv.script_segment_id!)}
                        disabled={isRegenerating}
                        className="text-xs text-zinc-400 hover:text-zinc-200"
                      >
                        <Icons.Rotate
                          className={`w-3.5 h-3.5 mr-1 ${isRegenerating ? "animate-spin" : ""}`}
                        />
                        Regenerate
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
