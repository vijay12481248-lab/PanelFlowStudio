import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { Project, AudioTimelineResponse, AudioInterval, CharacterEntity } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons, SvgAudioEqualizer } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";
import type { AppError } from "../types/error";

export interface AudioScreenProps {
  project: Project;
  onBack: () => void;
  onAudioApproved: (updatedProject: Project) => void;
  onProceedToMotion: (proj: Project) => void;
}

export const VOICE_PRESETS = [
  { id: "Narrator", label: "Narrator (Natural / Atmospheric)", desc: "Atmospheric and clear neutral storyteller" },
  { id: "Aria (The Narrator)", label: "Aria (Expressive Narrator)", desc: "Warm, engaging female voice" },
  { id: "Marcus (Male Deep F5-TTS)", label: "Marcus (Male Deep F5-TTS)", desc: "Resonant, baritone stoic male lead" },
  { id: "Seraphina (Cinematic)", label: "Seraphina (Cinematic)", desc: "Emotional, dynamic female lead" },
  { id: "Leon", label: "Leon (Youthful Male)", desc: "Energetic, clear tenor" },
  { id: "Kaelen", label: "Kaelen (Heroic Protagonist)", desc: "Bold, determined protagonist" },
];

export const AudioScreen: React.FC<AudioScreenProps> = ({
  project,
  onBack,
  onAudioApproved,
  onProceedToMotion,
}) => {
  const { reportError, inspectError } = useError();
  const [audioError, setAudioError] = useState<AppError | null>(null);

  const [timelineData, setTimelineData] = useState<AudioTimelineResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [jobMessage, setJobMessage] = useState("");
  const [generating, setGenerating] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  // Character voice casting state
  const [characters, setCharacters] = useState<CharacterEntity[]>([]);
  const [voiceCasting, setVoiceCasting] = useState<Record<string, string>>({
    narrator: "Narrator",
    NARRATOR: "Narrator",
    The_Narrator: "Narrator",
  });
  const [showCastingModal, setShowCastingModal] = useState<boolean>(false);

  // Continuous Master Playback State
  const [isMasterPlaying, setIsMasterPlaying] = useState<boolean>(false);
  const [activeIntervalIndex, setActiveIntervalIndex] = useState<number | null>(null);
  const [masterCurrentTime, setMasterCurrentTime] = useState<number>(0);
  const [playbackRate, setPlaybackRate] = useState<number>(1.0);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [volume, setVolume] = useState<number>(1.0);

  // Floating Toast State
  const [toast, setToast] = useState<{ message: string; type: "success" | "info" } | null>(null);
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Audio element & pause timer references
  const masterAudioRef = useRef<HTMLAudioElement | null>(null);
  const pauseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string, type: "success" | "info" = "success") => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToast({ message, type });
    toastTimeoutRef.current = setTimeout(() => {
      setToast(null);
    }, 3500);
  }, []);

  // Fetch Characters for Voice Casting
  useEffect(() => {
    let isMounted = true;
    api.listCharacters(project.id)
      .then((chars) => {
        if (isMounted) {
          setCharacters(chars);
          // Set sensible default voice mappings for detected characters
          setVoiceCasting((prev) => {
            const next = { ...prev };
            for (const c of chars) {
              const key = c.character_id || c.canonical_name;
              if (!next[key]) {
                const nameLower = (c.canonical_name || c.display_name || "").toLowerCase();
                if (nameLower.includes("marcus")) next[key] = "Marcus (Male Deep F5-TTS)";
                else if (nameLower.includes("seraphina")) next[key] = "Seraphina (Cinematic)";
                else if (nameLower.includes("leon")) next[key] = "Leon";
                else if (nameLower.includes("kaelen")) next[key] = "Kaelen";
                else if (nameLower.includes("aria") || nameLower.includes("narrator")) next[key] = "Aria (The Narrator)";
                else next[key] = "Marcus (Male Deep F5-TTS)";
              }
            }
            return next;
          });
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [project.id]);

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getAudioTimeline(project.id);
      setTimelineData(data);
      if (data.voice_casting) {
        setVoiceCasting((prev) => ({ ...prev, ...data.voice_casting }));
      }
    } catch {
      setTimelineData(null);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  // Clean up audio & timers on unmount
  useEffect(() => {
    return () => {
      if (pauseTimerRef.current) clearTimeout(pauseTimerRef.current);
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
      if (masterAudioRef.current) {
        masterAudioRef.current.pause();
        masterAudioRef.current.src = "";
      }
    };
  }, []);

  const intervals = timelineData?.timeline?.intervals || [];
  const totalDuration = timelineData?.total_duration || timelineData?.timeline?.total_duration_sec || 0;

  // Master Playback Engine: play interval at given index
  const playIntervalAtIndex = useCallback(
    (index: number) => {
      if (pauseTimerRef.current) {
        clearTimeout(pauseTimerRef.current);
        pauseTimerRef.current = null;
      }

      if (index < 0 || index >= intervals.length) {
        // Playback finished
        setIsMasterPlaying(false);
        setActiveIntervalIndex(null);
        setMasterCurrentTime(0);
        showToast("Master timeline playback finished.", "info");
        return;
      }

      setActiveIntervalIndex(index);
      setIsMasterPlaying(true);

      // Auto-scroll active card into view
      const cardEl = document.getElementById(`audio-interval-${index}`);
      if (cardEl) {
        cardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      const iv = intervals[index];
      const isSpeech = Boolean(iv.audio_file_uri && (iv as any).is_speech !== false);

      if (isSpeech && iv.audio_file_uri) {
        const audioSrc = api.getAudioFileUrl(project.id, iv.audio_file_uri);
        if (masterAudioRef.current) {
          masterAudioRef.current.src = audioSrc;
          masterAudioRef.current.playbackRate = playbackRate;
          masterAudioRef.current.muted = isMuted;
          masterAudioRef.current.volume = volume;
          masterAudioRef.current.play().catch((err) => {
            console.warn("Autoplay was prevented or audio failed:", err);
          });
        }
        setMasterCurrentTime(iv.start_time ?? 0);
      } else {
        // Pause / Gap / Transition interval
        if (masterAudioRef.current) {
          masterAudioRef.current.pause();
        }
        const dur = Math.max(0.2, (iv.end_time ?? 0) - (iv.start_time ?? 0) || iv.duration || 0.5);
        setMasterCurrentTime(iv.start_time ?? 0);

        pauseTimerRef.current = setTimeout(() => {
          playIntervalAtIndex(index + 1);
        }, (dur / playbackRate) * 1000);
      }
    },
    [intervals, project.id, playbackRate, isMuted, volume, showToast]
  );

  // Toggle Master Play / Pause
  const handleToggleMasterPlay = useCallback(() => {
    if (isMasterPlaying) {
      setIsMasterPlaying(false);
      if (pauseTimerRef.current) {
        clearTimeout(pauseTimerRef.current);
        pauseTimerRef.current = null;
      }
      masterAudioRef.current?.pause();
    } else {
      const startIndex =
        activeIntervalIndex !== null && activeIntervalIndex < intervals.length
          ? activeIntervalIndex
          : 0;
      playIntervalAtIndex(startIndex);
    }
  }, [isMasterPlaying, activeIntervalIndex, intervals.length, playIntervalAtIndex]);

  // Master Audio Event Listeners
  const handleAudioTimeUpdate = () => {
    if (activeIntervalIndex !== null && intervals[activeIntervalIndex]) {
      const iv = intervals[activeIntervalIndex];
      const currentTrackTime = masterAudioRef.current?.currentTime || 0;
      setMasterCurrentTime((iv.start_time ?? 0) + currentTrackTime);
    }
  };

  const handleAudioEnded = () => {
    if (activeIntervalIndex !== null) {
      playIntervalAtIndex(activeIntervalIndex + 1);
    }
  };

  // Skip to previous interval
  const handlePrevInterval = () => {
    const prevIdx = Math.max(0, (activeIntervalIndex ?? 0) - 1);
    playIntervalAtIndex(prevIdx);
  };

  // Skip to next interval
  const handleNextInterval = () => {
    const nextIdx = Math.min(intervals.length - 1, (activeIntervalIndex ?? 0) + 1);
    playIntervalAtIndex(nextIdx);
  };

  // Seek timeline to specific seconds
  const handleSeek = (targetSec: number) => {
    setMasterCurrentTime(targetSec);
    // Find interval containing this timestamp
    const targetIdx = intervals.findIndex(
      (iv) => (iv.start_time ?? 0) <= targetSec && targetSec <= (iv.end_time ?? 0)
    );

    if (targetIdx !== -1) {
      const iv = intervals[targetIdx];
      setActiveIntervalIndex(targetIdx);
      const isSpeech = Boolean(iv.audio_file_uri && (iv as any).is_speech !== false);

      if (isSpeech && iv.audio_file_uri) {
        const audioSrc = api.getAudioFileUrl(project.id, iv.audio_file_uri);
        if (masterAudioRef.current) {
          if (masterAudioRef.current.src !== audioSrc) {
            masterAudioRef.current.src = audioSrc;
          }
          const offset = Math.max(0, targetSec - (iv.start_time ?? 0));
          masterAudioRef.current.currentTime = offset;
          if (isMasterPlaying) {
            masterAudioRef.current.play().catch(() => {});
          }
        }
      } else {
        if (isMasterPlaying) {
          playIntervalAtIndex(targetIdx);
        }
      }
    }
  };

  // Keyboard controls (<Space> for play/pause, <Esc> to close modal)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT"
      ) {
        return;
      }

      if (e.code === "Space") {
        e.preventDefault();
        handleToggleMasterPlay();
      } else if (e.code === "Escape") {
        setShowCastingModal(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleToggleMasterPlay]);

  // Audio Generation with voice casting
  const handleGenerateAudio = async (overrideCasting?: Record<string, string>) => {
    setGenerating(true);
    setAudioError(null);
    const castingToUse = overrideCasting || voiceCasting;
    try {
      const { job_id } = await api.generateAudioJob(project.id, castingToUse);
      await api.waitForWorkflowJob(job_id, (job) =>
        setJobMessage(`${Math.round(job.progress * 100)}% · ${job.message}`)
      );
      const result = await api.getAudioTimeline(project.id);
      setTimelineData(result);
      showToast("Master audio timeline generated successfully!");
    } catch (err: any) {
      const errObj: AppError = {
        id: `err_audio_${Date.now()}`,
        title: "Audio Generation Failed",
        message: err.message || "Failed to generate audio timeline.",
        severity: "error",
        source: "job",
        projectId: project.id,
        jobType: "AUDIO_GENERATION",
        timestamp: new Date().toISOString(),
        rawDetails: err,
        suggestions: [
          "Change primary Speech Provider to 'Chatterbox Turbo' in Tools & Models.",
          "Verify the local Chatterbox environment at C:\\Tools\\Chatterbox.",
          "Check %LOCALAPPDATA%\\PanelFlow Studio\\logs\\engine.log for Python error output.",
        ],
      };
      setAudioError(errObj);
      reportError(errObj);
    } finally {
      setGenerating(false);
    }
  };

  const handleRegenerateSegment = async (segmentId: string) => {
    setRegeneratingId(segmentId);
    try {
      await api.regenerateAudioSegment(project.id, segmentId);
      await loadTimeline();
      showToast("Audio take regenerated successfully!");
    } catch (err: any) {
      reportError({
        title: "Audio Segment Regeneration Failed",
        message: err.message || "Could not regenerate dialogue voice line.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "AUDIO_GENERATION",
        rawDetails: { segmentId, error: err },
      });
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
      showToast("Audio approved! Ready for Motion Director.");
      onAudioApproved(updated);
    } catch (err: any) {
      reportError({
        title: "Audio Approval Gate Blocked",
        message: err.message || "Audio timeline verification failed.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setApproving(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const isApproved = timelineData?.status === "APPROVED" || project.current_stage === "AUDIO_APPROVED";

  return (
    <div className="space-y-6 pb-28">
      {/* Hidden Master Audio Element */}
      <audio
        ref={masterAudioRef}
        onTimeUpdate={handleAudioTimeUpdate}
        onEnded={handleAudioEnded}
        className="hidden"
      />

      {generating && (
        <div className="p-3 bg-indigo-950/40 border border-indigo-800/80 rounded-xl flex items-center justify-between animate-pulse">
          <p role="status" className="text-sm font-medium text-indigo-300">
            {jobMessage || "Synthesizing dialogue takes with local Chatterbox Turbo..."}
          </p>
          <Icons.Rotate className="w-4 h-4 text-indigo-400 animate-spin" />
        </div>
      )}

      {timelineData?.warnings?.map((warning, i) => (
        <p key={i} className="text-xs text-amber-300">
          {warning}
        </p>
      ))}

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
            Chatterbox Turbo neural dialogue synthesis with measured speech durations and optional dynamic background score.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Voice Casting Button */}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowCastingModal(true)}
            className="border-zinc-700 hover:bg-zinc-800 text-zinc-200"
          >
            <Icons.User className="w-3.5 h-3.5 mr-1.5 text-indigo-400" />
            Voice Casting
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => handleGenerateAudio()}
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

      {/* Inline Audio Error Diagnostic Card */}
      {audioError && (
        <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-800/80 text-rose-100 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-lg shadow-rose-950/40">
          <div className="flex items-start gap-3">
            <Icons.AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-rose-200">{audioError.title}</h4>
                <span className="text-[10px] bg-rose-900/60 text-rose-300 border border-rose-700 px-1.5 py-0.2 rounded font-bold uppercase">
                  ERROR
                </span>
              </div>
              <p className="text-xs text-rose-300 font-mono line-clamp-2">{audioError.message}</p>
              <p className="text-[11px] text-zinc-400">
                Click "View Error Details" for the full stack trace, provider configuration, and recovery options.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => inspectError(audioError)}
              className="text-xs border-rose-700/80 text-rose-200 hover:bg-rose-900/50"
            >
              <Icons.Eye className="w-3.5 h-3.5 mr-1 text-cyan-400" />
              View Error Details
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAudioError(null)}
              className="text-xs text-zinc-400 hover:text-zinc-200"
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      {timelineData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Total Duration
            </span>
            <div className="text-xl font-bold font-mono text-indigo-400">
              {formatDuration(totalDuration)}
              <span className="text-xs text-zinc-400 ml-1.5 font-normal">
                ({totalDuration.toFixed(1)}s)
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
              {timelineData.timeline.sample_rate_hz?.toLocaleString() || "48,000"} Hz
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Active Voice Casting
            </span>
            <div className="text-xs font-mono text-zinc-200 mt-1 truncate">
              {Object.keys(voiceCasting).length} voice roles cast
            </div>
          </Card>
        </div>
      )}

      {/* Voice Casting Drawer / Modal */}
      {showCastingModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-700/80 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-fade-in">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Icons.User className="w-5 h-5 text-indigo-400" />
                <h2 className="text-base font-bold text-zinc-100">Character Voice Casting</h2>
              </div>
              <button
                onClick={() => setShowCastingModal(false)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded-lg hover:bg-zinc-800"
              >
                <Icons.X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 flex-1 text-sm">
              <p className="text-xs text-zinc-400">
                Assign distinctive neural voice profiles to each detected speaker in your manga. Chatterbox Turbo will synthesize dialogue lines using these assigned voices.
              </p>

              {/* Narrator Casting */}
              <div className="p-3.5 bg-zinc-950/60 border border-zinc-800 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block" />
                    <span className="font-bold text-zinc-100">Story Narrator</span>
                    <Badge variant="accent" className="text-[10px]">GLOBAL</Badge>
                  </div>
                  <span className="text-xs text-zinc-500 font-mono">Narrator / Descriptions</span>
                </div>
                <select
                  value={voiceCasting["narrator"] || "Narrator"}
                  onChange={(e) => {
                    const val = e.target.value;
                    setVoiceCasting((prev) => ({
                      ...prev,
                      narrator: val,
                      NARRATOR: val,
                      The_Narrator: val,
                    }));
                  }}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                >
                  {VOICE_PRESETS.map((vp) => (
                    <option key={vp.id} value={vp.id}>
                      {vp.label} — {vp.desc}
                    </option>
                  ))}
                </select>
              </div>

              {/* Characters Casting */}
              <div className="space-y-3">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  Detected Characters ({characters.length})
                </h3>

                {characters.length === 0 ? (
                  <div className="p-4 text-center border border-dashed border-zinc-800 rounded-xl text-zinc-500 text-xs">
                    No individual character profiles detected yet. The global Narrator profile will be used for all lines.
                  </div>
                ) : (
                  characters.map((char) => {
                    const charKey = char.character_id || char.canonical_name;
                    const currentVoice = voiceCasting[charKey] || voiceCasting[char.canonical_name] || "Marcus (Male Deep F5-TTS)";

                    return (
                      <div
                        key={char.character_id}
                        className="p-3.5 bg-zinc-950/60 border border-zinc-800 rounded-xl space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 inline-block" />
                            <span className="font-bold text-zinc-100">{char.canonical_name || char.display_name}</span>
                            <Badge variant="neutral" className="text-[10px] uppercase">
                              {char.role || "Character"}
                            </Badge>
                          </div>
                          <span className="text-xs text-zinc-500 font-mono">
                            {char.aliases?.length ? `Aliases: ${char.aliases.join(", ")}` : "Direct Speaker"}
                          </span>
                        </div>

                        <select
                          value={currentVoice}
                          onChange={(e) => {
                            const val = e.target.value;
                            setVoiceCasting((prev) => ({
                              ...prev,
                              [charKey]: val,
                              [char.canonical_name]: val,
                            }));
                          }}
                          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                        >
                          {VOICE_PRESETS.map((vp) => (
                            <option key={vp.id} value={vp.id}>
                              {vp.label} — {vp.desc}
                            </option>
                          ))}
                        </select>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-zinc-800 flex items-center justify-between gap-3 bg-zinc-950/40">
              <Button variant="ghost" size="sm" onClick={() => setShowCastingModal(false)}>
                Cancel
              </Button>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setShowCastingModal(false);
                    showToast("Voice casting saved.");
                  }}
                >
                  Save Casting
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setShowCastingModal(false);
                    handleGenerateAudio(voiceCasting);
                  }}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  Save & Regenerate Audio
                </Button>
              </div>
            </div>
          </div>
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
            Speech durations are measured directly from neural WAV files with natural pause intervals.
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
              Click "Generate Master Audio" above to synthesize character dialogue with Chatterbox Turbo neural models and align the cinematic score.
            </p>
          </div>
          <Button variant="primary" onClick={() => handleGenerateAudio()} disabled={generating}>
            Generate Master Audio
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {intervals.map((iv, idx) => {
            const isRegenerating = regeneratingId === iv.script_segment_id;
            const startTime = iv.start_time ?? 0;
            const endTime = iv.end_time ?? 0;
            const duration = iv.duration ?? Math.max(0, endTime - startTime);
            const isSpeech = Boolean(iv.audio_file_uri && (iv as any).is_speech !== false);
            const isActive = activeIntervalIndex === idx;
            const isLinePlaying = isActive && isMasterPlaying;

            const charName =
              (iv as any).character_id ||
              (iv as any).speaker_character_id ||
              ((iv as any).speaker_id ? (iv as any).speaker_id : "");
            const cue = (iv as any).cue_text || (iv as any).text || "";
            const gainDb = (iv as any).gain_db ?? 0;

            // Non-speech Pause / Gap Interval
            if (!isSpeech) {
              return (
                <div
                  key={iv.interval_id || idx}
                  id={`audio-interval-${idx}`}
                  className={`px-4 py-2.5 rounded-xl border border-dashed text-xs flex items-center justify-between transition-all duration-200 ${
                    isActive
                      ? "bg-amber-950/40 border-amber-500 text-amber-200 ring-1 ring-amber-500 shadow-md"
                      : "bg-zinc-950/30 border-zinc-800 text-zinc-500 hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icons.Clock className={`w-3.5 h-3.5 ${isActive ? "text-amber-400 animate-spin" : "text-zinc-500"}`} />
                    <span className="font-mono font-semibold">
                      Natural Silence Pause · {duration.toFixed(2)}s
                    </span>
                    <span className="text-[11px] text-zinc-600 font-mono">
                      ({startTime.toFixed(2)}s - {endTime.toFixed(2)}s)
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => playIntervalAtIndex(idx)}
                      className="text-[11px] h-6 px-2.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                    >
                      {isActive && isMasterPlaying ? (
                        <>
                          <Icons.Pause className="w-3 h-3 mr-1 text-amber-400" /> Pause
                        </>
                      ) : (
                        <>
                          <Icons.Play className="w-3 h-3 mr-1 text-zinc-400" /> Play from here
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              );
            }

            // Speech Dialogue Interval
            const audioSrc = api.getAudioFileUrl(project.id, iv.audio_file_uri);

            return (
              <Card
                key={iv.interval_id || idx}
                id={`audio-interval-${idx}`}
                className={`p-4 transition-all duration-300 ${
                  isActive
                    ? "bg-indigo-950/40 border-indigo-500 shadow-[0_0_20px_rgba(99,102,241,0.25)] ring-1 ring-indigo-500"
                    : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {/* Left: Metadata & Cue Text */}
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs font-bold font-mono ${isActive ? "text-indigo-300" : "text-indigo-400"}`}>
                        #{idx + 1}
                      </span>
                      <Badge variant="accent" className="text-[10px] uppercase font-bold">
                        SPEECH
                      </Badge>
                      {charName && (
                        <span className="text-xs font-bold text-zinc-100 capitalize">
                          {charName.replace(/^char_/, "")}
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
                      <p className={`text-xs italic font-medium leading-relaxed ${isActive ? "text-zinc-100" : "text-zinc-300"}`}>
                        "{cue}"
                      </p>
                    )}
                  </div>

                  {/* Right: Audio Controls & Regenerate */}
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <SvgAudioEqualizer
                      isPlaying={isLinePlaying}
                      theme={isLinePlaying ? "cyan" : "indigo"}
                      className="transition-opacity duration-300"
                    />

                    {/* Quick Play/Pause take button */}
                    <Button
                      variant={isLinePlaying ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => {
                        if (isLinePlaying) {
                          handleToggleMasterPlay();
                        } else {
                          playIntervalAtIndex(idx);
                        }
                      }}
                      className="h-8 px-3 text-xs"
                    >
                      {isLinePlaying ? (
                        <>
                          <Icons.Pause className="w-3.5 h-3.5 mr-1" /> Pause
                        </>
                      ) : (
                        <>
                          <Icons.Play className="w-3.5 h-3.5 mr-1" /> Play Take
                        </>
                      )}
                    </Button>

                    <audio
                      controls
                      src={audioSrc}
                      preload="none"
                      className="h-8 max-w-[200px] rounded opacity-75 hover:opacity-100 transition-opacity"
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

      {/* Continuous Master Audio Player Bar (Sticky Dock) */}
      {timelineData && intervals.length > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 w-[94%] max-w-5xl bg-zinc-900/95 backdrop-blur-md border border-zinc-700/80 rounded-2xl p-3.5 shadow-2xl flex flex-col md:flex-row items-center justify-between gap-3 animate-fade-in">
          {/* Left section: Equalizer & Active Track Info */}
          <div className="flex items-center gap-3 min-w-[220px]">
            <SvgAudioEqualizer
              isPlaying={isMasterPlaying}
              theme="cyan"
              className="flex-shrink-0"
            />
            <div className="min-w-0">
              <div className="text-xs font-bold text-zinc-100 truncate flex items-center gap-1.5">
                {activeIntervalIndex !== null && intervals[activeIntervalIndex] ? (
                  <>
                    <span className="text-indigo-400 font-mono">#{activeIntervalIndex + 1}</span>
                    <span className="truncate">
                      {(intervals[activeIntervalIndex] as any).text ||
                        (intervals[activeIntervalIndex] as any).cue_text ||
                        "Natural Pause"}
                    </span>
                  </>
                ) : (
                  <span>Master Audio Timeline</span>
                )}
              </div>
              <div className="text-[11px] font-mono text-zinc-400">
                {formatDuration(masterCurrentTime)} / {formatDuration(totalDuration)}
              </div>
            </div>
          </div>

          {/* Center section: Transport Controls & Scrubber Slider */}
          <div className="flex flex-col items-center gap-1.5 flex-1 w-full max-w-lg px-2">
            <div className="flex items-center gap-3">
              <button
                onClick={handlePrevInterval}
                disabled={activeIntervalIndex === 0}
                className="text-zinc-400 hover:text-zinc-100 disabled:opacity-30 disabled:hover:text-zinc-400 transition-colors"
                title="Previous Take"
              >
                <Icons.ArrowLeft className="w-4 h-4" />
              </button>

              <button
                onClick={handleToggleMasterPlay}
                className="w-10 h-10 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center shadow-lg shadow-indigo-600/30 transition-all hover:scale-105 active:scale-95"
                title={isMasterPlaying ? "Pause (Space)" : "Play All (Space)"}
              >
                {isMasterPlaying ? (
                  <Icons.Pause className="w-5 h-5" />
                ) : (
                  <Icons.Play className="w-5 h-5 ml-0.5" />
                )}
              </button>

              <button
                onClick={handleNextInterval}
                disabled={activeIntervalIndex === intervals.length - 1}
                className="text-zinc-400 hover:text-zinc-100 disabled:opacity-30 disabled:hover:text-zinc-400 transition-colors"
                title="Next Take"
              >
                <Icons.ArrowRight className="w-4 h-4" />
              </button>
            </div>

            {/* Scrubber slider */}
            <div className="w-full flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={Math.max(1, totalDuration)}
                step={0.05}
                value={Math.min(totalDuration, masterCurrentTime)}
                onChange={(e) => handleSeek(parseFloat(e.target.value))}
                className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
            </div>
          </div>

          {/* Right section: Speed Selector & Volume Controls */}
          <div className="flex items-center gap-2.5">
            {/* Speed Pills */}
            <div className="flex items-center bg-zinc-950/70 rounded-lg p-0.5 border border-zinc-800 text-[11px] font-mono">
              {[0.75, 1.0, 1.25, 1.5].map((rate) => (
                <button
                  key={rate}
                  onClick={() => {
                    setPlaybackRate(rate);
                    if (masterAudioRef.current) {
                      masterAudioRef.current.playbackRate = rate;
                    }
                  }}
                  className={`px-2 py-0.5 rounded transition-colors ${
                    playbackRate === rate
                      ? "bg-indigo-600 text-white font-bold"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {rate}x
                </button>
              ))}
            </div>

            {/* Mute Button */}
            <button
              onClick={() => {
                const nextMuted = !isMuted;
                setIsMuted(nextMuted);
                if (masterAudioRef.current) masterAudioRef.current.muted = nextMuted;
              }}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
              title={isMuted ? "Unmute" : "Mute"}
            >
              <Icons.Volume className={`w-4 h-4 ${isMuted ? "text-rose-400" : ""}`} />
            </button>
          </div>
        </div>
      )}

      {/* Floating Toast Notification */}
      {toast && (
        <div className="fixed bottom-24 right-6 z-50 animate-fade-in">
          <div className="bg-zinc-800/95 backdrop-blur border border-zinc-700 text-zinc-100 text-xs px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2.5">
            <Icons.CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{toast.message}</span>
            <button
              onClick={() => setToast(null)}
              className="text-zinc-400 hover:text-zinc-200 ml-2"
            >
              <Icons.X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
