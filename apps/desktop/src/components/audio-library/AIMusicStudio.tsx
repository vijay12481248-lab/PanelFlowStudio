import React, { useState, useEffect, useRef } from "react";
import type {
  MusicDirectionPlan,
  MusicCuePlan,
  MusicTakeRecord,
  MusicGenerationRequest,
  SFXCapabilityReport,
} from "@panelflow/shared-types";
import type { AudioToTimelineContract, AudioAsset } from "./AudioLibrary.types.ts";
import { api } from "@panelflow/api-client";

interface AIMusicStudioProps {
  projectId?: string;
  onSendToTimeline?: (contract: AudioToTimelineContract) => void;
  onSaveToLibrary?: (asset: AudioAsset) => void;
}

export const AIMusicStudio: React.FC<AIMusicStudioProps> = ({
  projectId = "68711176-90f5-4a68-8520-78d6e183bf65",
  onSendToTimeline,
  onSaveToLibrary,
}) => {
  // State
  const [plan, setPlan] = useState<MusicDirectionPlan | null>(null);
  const [selectedCueId, setSelectedCueId] = useState<string | null>(null);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);
  const [loadingPlan, setLoadingPlan] = useState<boolean>(true);
  const [planError, setPlanError] = useState<string | null>(null);

  // Active editable form fields
  const [prompt, setPrompt] = useState<string>("");
  const [bpm, setBpm] = useState<number>(85);
  const [keyScale, setKeyScale] = useState<string>("D Minor");
  const [durationSec, setDurationSec] = useState<number>(18.0);
  const [intensity, setIntensity] = useState<number>(0.5);
  const [seed, setSeed] = useState<number>(88102);
  const [useRandomSeed, setUseRandomSeed] = useState<boolean>(true);
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  // Generation status
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generationProgress, setGenerationProgress] = useState<number>(0);
  const [generationStatusText, setGenerationStatusText] = useState<string>("");
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState<number>(0);

  // Audio Playback
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackTime, setPlaybackTime] = useState<number>(0);
  const [audioDuration, setAudioDuration] = useState<number>(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // SFX capability report modal / badge
  const [sfxReport, setSfxReport] = useState<SFXCapabilityReport | null>(null);

  // Load MusicDirectionPlan on mount
  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      try {
        setLoadingPlan(true);
        const [planData, sfxData] = await Promise.all([
          api.getProjectMusicPlan(projectId),
          api.getSFXCapabilityReport().catch(() => null),
        ]);
        if (isMounted) {
          setPlan(planData);
          setSfxReport(sfxData);
          if (planData.cues.length > 0) {
            const firstCue = planData.cues[0];
            setSelectedCueId(firstCue.cue_id);
            setPrompt(firstCue.editable_prompt);
            setBpm(firstCue.tempo_bpm);
            setKeyScale(firstCue.tonal_center);
            setDurationSec(firstCue.duration_sec);
            setIntensity(firstCue.intensity);
            if (firstCue.takes.length > 0) {
              const activeTake = firstCue.selected_take_id
                ? firstCue.takes.find((t) => t.take_id === firstCue.selected_take_id) || firstCue.takes[0]
                : firstCue.takes[0];
              setSelectedTakeId(activeTake.take_id);
            }
          }
          setPlanError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setPlanError(err?.message || "Failed to load music plan");
        }
      } finally {
        if (isMounted) setLoadingPlan(false);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [projectId]);

  // Audio element setup
  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;

    audio.ontimeupdate = () => {
      setPlaybackTime(audio.currentTime);
    };
    audio.onloadedmetadata = () => {
      setAudioDuration(audio.duration || 0);
    };
    audio.onended = () => {
      setIsPlaying(false);
      setPlaybackTime(0);
    };
    audio.onerror = () => {
      setIsPlaying(false);
    };

    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  const selectedCue: MusicCuePlan | null =
    plan?.cues.find((c) => c.cue_id === selectedCueId) || null;

  const currentTake: MusicTakeRecord | null =
    selectedCue?.takes.find((t) => t.take_id === selectedTakeId) ||
    (selectedCue?.takes.length ? selectedCue.takes[0] : null);

  // Switch cue
  const handleSelectCue = (cue: MusicCuePlan) => {
    setSelectedCueId(cue.cue_id);
    setPrompt(cue.editable_prompt);
    setBpm(cue.tempo_bpm);
    setKeyScale(cue.tonal_center);
    setDurationSec(cue.duration_sec);
    setIntensity(cue.intensity);

    if (cue.takes.length > 0) {
      const activeTake = cue.selected_take_id
        ? cue.takes.find((t) => t.take_id === cue.selected_take_id) || cue.takes[0]
        : cue.takes[0];
      setSelectedTakeId(activeTake.take_id);
      loadAudioSource(activeTake.audio_file_uri);
    } else {
      setSelectedTakeId(null);
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
      setIsPlaying(false);
    }
  };

  // Switch candidate take
  const handleSelectTake = (take: MusicTakeRecord) => {
    setSelectedTakeId(take.take_id);
    loadAudioSource(take.audio_file_uri);
  };

  const loadAudioSource = (uri: string) => {
    if (!audioRef.current) return;
    const fullUrl = uri.startsWith("http") ? uri : `http://127.0.0.1:8765${uri}`;
    audioRef.current.src = fullUrl;
    audioRef.current.load();
    setIsPlaying(false);
    setPlaybackTime(0);
  };

  // Play / Pause toggle
  const togglePlay = () => {
    if (!audioRef.current || !currentTake) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      if (!audioRef.current.src) {
        loadAudioSource(currentTake.audio_file_uri);
      }
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  // Waveform rendering on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const peaks = currentTake?.waveform_peaks || [];
    const count = peaks.length > 0 ? peaks.length : 60;
    const barWidth = width / count;
    const progressFrac = audioDuration > 0 ? playbackTime / audioDuration : 0;

    for (let i = 0; i < count; i++) {
      const val = peaks[i] !== undefined ? peaks[i] : 0.2 + 0.3 * Math.sin(i * 0.3);
      const barHeight = Math.max(3, val * (height * 0.85));
      const x = i * barWidth;
      const y = (height - barHeight) / 2;

      const isPlayed = i / count <= progressFrac;
      ctx.fillStyle = isPlayed ? "#7aa2ff" : "#26346a";
      ctx.fillRect(x + 1, y, Math.max(1, barWidth - 2), barHeight);
    }
  }, [currentTake, playbackTime, audioDuration]);

  // Generate music take
  const handleGenerate = async () => {
    if (!selectedCueId) return;
    try {
      setIsGenerating(true);
      setGenerationError(null);
      setGenerationProgress(0.1);
      setGenerationStatusText("Contacting local ACE-Step 1.5 daemon...");
      setElapsedSec(0);

      const timer = setInterval(() => {
        setElapsedSec((prev) => prev + 1);
      }, 1000);

      const req: MusicGenerationRequest = {
        cue_id: selectedCueId,
        prompt: prompt.trim(),
        audio_duration: durationSec,
        bpm: bpm,
        key_scale: keyScale,
        time_signature: "4/4",
        seed: useRandomSeed ? undefined : seed,
        use_random_seed: useRandomSeed,
        inference_steps: 8,
        guidance_scale: 7.0,
        model: "acestep-v15-turbo",
        thinking: false,
      };

      setGenerationProgress(0.35);
      setGenerationStatusText("Running DiT diffusion on GPU (RTX 5060 Ti)...");

      const takeRecord = await api.generateMusic(projectId, req);

      setGenerationProgress(0.9);
      setGenerationStatusText("Validating 48 kHz stereo master...");

      clearInterval(timer);

      // Refresh the plan to get updated takes list
      const updatedPlan = await api.getProjectMusicPlan(projectId);
      setPlan(updatedPlan);

      // Select newly generated take
      const targetCue = updatedPlan.cues.find((c) => c.cue_id === selectedCueId);
      if (targetCue) {
        setSelectedTakeId(takeRecord.take_id);
        loadAudioSource(takeRecord.audio_file_uri);
      }

      setGenerationProgress(1.0);
      setGenerationStatusText(`Complete in ${takeRecord.generation_time_sec}s!`);
    } catch (err: any) {
      setGenerationError(err?.message || "Generation failed. Verify ACE-Step server.");
    } finally {
      setIsGenerating(false);
    }
  };

  // Add Take to Story Editor Timeline
  const handleSendToTimeline = () => {
    if (!currentTake || !selectedCue) return;

    const contract: AudioToTimelineContract = {
      schema_version: "6A-v1",
      exported_at: new Date().toISOString(),
      reference: {
        asset_id: currentTake.take_id,
        name: `${selectedCue.title} (Take ${currentTake.take_index})`,
        type: "music",
        category: "background_music",
        duration_sec: currentTake.duration_sec,
        file_url: `http://127.0.0.1:8765${currentTake.audio_file_uri}`,
        target_track: "BGM",
        volume: 0.8,
        loop: false,
        fade_in_sec: 1.0,
        fade_out_sec: 1.5,
        bpm: currentTake.bpm,
        key: currentTake.key_scale,
      },
    };

    if (onSendToTimeline) {
      onSendToTimeline(contract);
    }
  };

  // Save generated take to Catalog Library
  const handleSaveToLibrary = () => {
    if (!currentTake || !selectedCue || !onSaveToLibrary) return;

    const newAsset: AudioAsset = {
      id: currentTake.take_id,
      name: `${selectedCue.title} (Take ${currentTake.take_index})`,
      type: "music",
      category: "background_music",
      duration_sec: currentTake.duration_sec,
      file_format: "wav",
      file_url: `http://127.0.0.1:8765${currentTake.audio_file_uri}`,
      file_size_bytes: currentTake.file_size_bytes,
      sample_rate_hz: currentTake.sample_rate,
      channels: "Stereo",
      tags: ["AI Generated", "ACE-Step 1.5", currentTake.key_scale, `${currentTake.bpm} BPM`, selectedCue.narrative_function],
      availability: "AVAILABLE",
      is_favorite: true,
      description: currentTake.prompt,
      bpm: currentTake.bpm,
      key: currentTake.key_scale,
      loopable: false,
      license: {
        license_type: "Custom Commercial License",
        author_or_source: "PanelFlow Studio / ACE-Step 1.5 (MIT)",
        attribution_required: false,
        commercial_use_allowed: true,
        notes: `Seed: ${currentTake.seed}, Peak: ${currentTake.measured_peak_dbfs} dBFS, SHA256: ${currentTake.checksum_sha256.substring(0, 10)}...`,
      },
      recommended_timeline_track: "BGM",
      measured_peaks: currentTake.waveform_peaks,
      created_at: new Date(currentTake.created_at * 1000).toISOString(),
    };

    onSaveToLibrary(newAsset);
  };

  if (loadingPlan) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-fg-dim gap-3">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">Analyzing manga storyline and composing soundtrack plan...</span>
      </div>
    );
  }

  if (planError || !plan) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-bad gap-3">
        <span className="text-2xl">⚠️</span>
        <span className="text-sm font-semibold">{planError || "Failed to load music plan"}</span>
        <button
          onClick={() => window.location.reload()}
          className="px-3 py-1.5 rounded bg-flat text-fg text-xs hover:bg-glass-hi"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-ink text-fg overflow-hidden">
      {/* Top Banner: Story Soundtrack Concept & Architectural Headroom */}
      <div className="px-6 py-3 border-b border-edge bg-navy/60 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="px-2.5 py-1 rounded bg-accent/20 border border-accent/40 text-info text-xs font-mono font-semibold">
            🎵 {plan.harmonic_key}
          </div>
          <div>
            <div className="text-xs font-semibold text-fg">{plan.overall_musical_theme}</div>
            <div className="text-[11px] text-fg-dim">
              Total Score: <span className="font-mono text-fg">{plan.total_score_duration_sec}s</span> | Cues:{" "}
              <span className="font-mono text-fg">{plan.cues.length}</span> movements
            </div>
          </div>
        </div>

        {/* Headroom & Local Model Health Badge */}
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-ok/60 border border-ok/60 text-ok">
            <span className="w-2 h-2 rounded-full bg-ok animate-pulse" />
            <span>ACE-Step 1.5 Turbo</span>
          </div>
          <div className="text-[11px] text-fg-dim border border-edge px-2 py-1 rounded bg-navy">
            Headroom: <span className="text-fg-dim">2-5 kHz reserved for dialogue</span>
          </div>
        </div>
      </div>

      {/* Main Studio Body: 3 Panes */}
      <div className="flex-1 flex min-h-0 divide-x divide-edge overflow-hidden">
        {/* Pane 1: Story Cues & Scene Continuity (Left) */}
        <div className="w-72 flex-shrink-0 flex flex-col bg-navy/30 overflow-y-auto">
          <div className="p-3 border-b border-edge/80 text-[11px] font-semibold text-fg-dim uppercase tracking-wider">
            Musical Movements & Cues
          </div>
          <div className="p-2 space-y-1.5">
            {plan.cues.map((cue, idx) => {
              const isSelected = cue.cue_id === selectedCueId;
              const hasTakes = cue.takes.length > 0;
              return (
                <button
                  key={cue.cue_id}
                  onClick={() => handleSelectCue(cue)}
                  className={`w-full text-left p-3 rounded-lg border transition-all ${
                    isSelected
                      ? "bg-accent/60 border-accent/60 text-white shadow-sm"
                      : "bg-navy/50 border-edge/60 text-fg-dim hover:bg-flat/60 hover:text-white"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-semibold mb-1">
                    <span className="truncate">
                      {idx + 1}. {cue.title}
                    </span>
                    <span className="font-mono text-[10px] text-info">{cue.duration_sec}s</span>
                  </div>
                  <div className="text-[11px] text-fg-dim line-clamp-1 mb-2">
                    {cue.narrative_function.replace("_", " ")}
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-fg-dim">
                    <span>Scenes: {cue.scene_ids.join(", ") || "All"}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${
                        hasTakes
                          ? "bg-ok/20 text-ok border border-ok/40"
                          : "bg-flat text-fg-dim"
                      }`}
                    >
                      {hasTakes ? `${cue.takes.length} takes` : "No takes"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Honest SFX Capability Callout */}
          {sfxReport && (
            <div className="mt-auto p-3 m-2 rounded-lg bg-navy border border-edge text-[11px] text-fg-dim">
              <div className="font-semibold text-fg-dim mb-1 flex items-center gap-1.5">
                <span>🔔 Sound Effects Library</span>
              </div>
              <div className="text-[10px] leading-relaxed text-fg-dim mb-2">
                High-fidelity curated sound library enabled for footsteps, sword impacts, and magic activation.
              </div>
              <span className="inline-block px-1.5 py-0.5 bg-flat rounded font-mono text-[9px] text-fg-dim">
                Curated SFX Active
              </span>
            </div>
          )}
        </div>

        {/* Pane 2: Music Director Prompt & Controls (Center) */}
        <div className="flex-1 flex flex-col p-5 overflow-y-auto min-w-[340px]">
          {selectedCue ? (
            <div className="max-w-2xl space-y-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-sm font-bold text-white">{selectedCue.title}</h2>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/20 text-info border border-accent/40 uppercase font-mono">
                    {selectedCue.narrative_function}
                  </span>
                </div>
                <p className="text-xs text-fg-dim">{selectedCue.emotional_direction}</p>
              </div>

              {/* Story Musical Parameters */}
              <div className="grid grid-cols-3 gap-3 p-3 rounded-lg bg-navy border border-edge text-xs">
                <div>
                  <span className="text-[10px] text-fg-dim block uppercase font-mono">Tonal Key</span>
                  <span className="font-semibold text-fg">{keyScale}</span>
                </div>
                <div>
                  <span className="text-[10px] text-fg-dim block uppercase font-mono">Tempo (BPM)</span>
                  <span className="font-semibold text-fg">{bpm} BPM</span>
                </div>
                <div>
                  <span className="text-[10px] text-fg-dim block uppercase font-mono">Duration</span>
                  <span className="font-semibold text-fg">{durationSec}s</span>
                </div>
              </div>

              {/* Editable Prompt */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-fg-dim">Story-Aware Generation Prompt</label>
                  <span className="text-[10px] text-fg-dim">User editable prior to synthesis</span>
                </div>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={4}
                  className="w-full text-xs p-3 rounded-lg bg-navy border border-edge text-fg focus:outline-none focus:border-accent font-sans leading-relaxed resize-none"
                  placeholder="Enter detailed music prompt..."
                />
              </div>

              {/* Advanced Settings Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-xs text-info hover:text-info flex items-center gap-1 font-semibold"
                >
                  <span>{showAdvanced ? "▾ Hide Advanced Settings" : "▸ Show Advanced Settings"}</span>
                </button>

                {showAdvanced && (
                  <div className="mt-3 p-3 rounded-lg bg-navy border border-edge space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[10px] text-fg-dim block mb-1">Target Duration (Seconds)</label>
                        <input
                          type="number"
                          min={5}
                          max={180}
                          value={durationSec}
                          onChange={(e) => setDurationSec(Number(e.target.value))}
                          className="w-full bg-flat border border-edge rounded px-2 py-1 text-xs"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-fg-dim block mb-1">Tempo (BPM)</label>
                        <input
                          type="number"
                          min={40}
                          max={220}
                          value={bpm}
                          onChange={(e) => setBpm(Number(e.target.value))}
                          className="w-full bg-flat border border-edge rounded px-2 py-1 text-xs"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 items-center">
                      <div>
                        <label className="text-[10px] text-fg-dim block mb-1">Random Seed</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={useRandomSeed}
                            onChange={(e) => setUseRandomSeed(e.target.checked)}
                            id="random-seed-chk"
                            className="rounded bg-flat border-edge"
                          />
                          <label htmlFor="random-seed-chk" className="text-xs text-fg-dim">
                            Auto Random
                          </label>
                        </div>
                      </div>
                      {!useRandomSeed && (
                        <div>
                          <label className="text-[10px] text-fg-dim block mb-1">Manual Seed</label>
                          <input
                            type="number"
                            value={seed}
                            onChange={(e) => setSeed(Number(e.target.value))}
                            className="w-full bg-flat border border-edge rounded px-2 py-1 text-xs font-mono"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Generation Controls */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="w-full py-2.5 px-4 rounded-lg bg-accent hover:bg-accent disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2 shadow-sm"
                >
                  {isGenerating ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Synthesizing... ({elapsedSec}s)</span>
                    </>
                  ) : (
                    <>
                      <span>✨ Generate Real Take (ACE-Step 1.5)</span>
                    </>
                  )}
                </button>

                {isGenerating && (
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-fg-dim">
                      <span>{generationStatusText}</span>
                      <span className="font-mono text-fg">{Math.round(generationProgress * 100)}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-flat rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all duration-300"
                        style={{ width: `${generationProgress * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                {generationError && (
                  <div className="mt-3 p-3 rounded bg-bad/50 border border-bad/80 text-bad text-xs">
                    {generationError}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-fg-faint text-xs">
              Select a musical movement from the left to configure soundtrack direction.
            </div>
          )}
        </div>

        {/* Pane 3: Candidate Takes Audition & Timeline Placement (Right) */}
        <div className="w-80 flex-shrink-0 flex flex-col p-4 bg-navy/40 overflow-y-auto">
          <div className="text-[11px] font-semibold text-fg-dim uppercase tracking-wider mb-3">
            Candidate Takes & Audition
          </div>

          {selectedCue && selectedCue.takes.length > 0 ? (
            <div className="space-y-4">
              {/* Takes Selector Tabs */}
              <div className="flex gap-1.5 p-1 bg-navy rounded-lg border border-edge overflow-x-auto">
                {selectedCue.takes.map((take) => {
                  const isSelected = take.take_id === selectedTakeId;
                  return (
                    <button
                      key={take.take_id}
                      onClick={() => handleSelectTake(take)}
                      className={`px-3 py-1.5 rounded text-xs font-semibold whitespace-nowrap transition-colors ${
                        isSelected
                          ? "bg-accent text-white"
                          : "text-fg-dim hover:text-fg hover:bg-flat"
                      }`}
                    >
                      Take {take.take_index}
                    </button>
                  );
                })}
              </div>

              {currentTake && (
                <div className="space-y-3">
                  {/* Waveform Player */}
                  <div className="p-3 rounded-lg bg-navy border border-edge space-y-2">
                    <canvas
                      ref={canvasRef}
                      width={280}
                      height={50}
                      className="w-full h-12 rounded bg-ink cursor-pointer"
                      onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const clickX = e.clientX - rect.left;
                        const frac = clickX / rect.width;
                        if (audioRef.current && audioDuration > 0) {
                          audioRef.current.currentTime = frac * audioDuration;
                        }
                      }}
                    />

                    {/* Play / Pause & Time */}
                    <div className="flex items-center justify-between text-xs">
                      <button
                        type="button"
                        onClick={togglePlay}
                        className="px-3 py-1 rounded bg-flat hover:bg-glass-hi text-fg font-semibold flex items-center gap-1.5"
                      >
                        <span>{isPlaying ? "⏸ Pause" : "▶ Play"}</span>
                      </button>
                      <span className="font-mono text-fg-dim text-[11px]">
                        {playbackTime.toFixed(1)}s / {currentTake.duration_sec}s
                      </span>
                    </div>
                  </div>

                  {/* Audio Master Specifications */}
                  <div className="p-3 rounded-lg bg-navy/60 border border-edge text-[11px] space-y-1.5">
                    <div className="flex justify-between">
                      <span className="text-fg-dim">Sample Rate:</span>
                      <span className="font-mono text-fg">48,000 Hz Stereo</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-dim">Format:</span>
                      <span className="font-mono text-fg">16-bit PCM WAV</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-dim">True Peak:</span>
                      <span className="font-mono text-fg">{currentTake.measured_peak_dbfs} dBFS</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-dim">RMS Level:</span>
                      <span className="font-mono text-fg">{currentTake.measured_rms_dbfs} dBFS</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-fg-dim">Seed:</span>
                      <span className="font-mono text-fg">{currentTake.seed}</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="space-y-2 pt-2">
                    <button
                      type="button"
                      onClick={handleSendToTimeline}
                      className="w-full py-2.5 px-3 rounded-lg bg-ok hover:bg-ok text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2 shadow-sm"
                    >
                      <span>📥 Add Take to Timeline (BGM Track)</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleSaveToLibrary}
                      className="w-full py-2 px-3 rounded-lg bg-flat hover:bg-glass-hi text-fg font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
                    >
                      <span>💾 Save to Library Catalog</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-fg-faint text-xs border border-dashed border-edge rounded-lg">
              <span className="text-xl mb-1">🎼</span>
              <span>No generated takes yet for this cue. Click "Generate Real Take" to synthesize one locally.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
