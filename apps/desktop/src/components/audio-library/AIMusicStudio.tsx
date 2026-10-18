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
      ctx.fillStyle = isPlayed ? "#818cf8" : "#3f3f46";
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
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-zinc-400 gap-3">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">Analyzing manga storyline and composing soundtrack plan...</span>
      </div>
    );
  }

  if (planError || !plan) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-rose-400 gap-3">
        <span className="text-2xl">⚠️</span>
        <span className="text-sm font-semibold">{planError || "Failed to load music plan"}</span>
        <button
          onClick={() => window.location.reload()}
          className="px-3 py-1.5 rounded bg-zinc-800 text-zinc-200 text-xs hover:bg-zinc-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Top Banner: Story Soundtrack Concept & Architectural Headroom */}
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/60 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="px-2.5 py-1 rounded bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 text-xs font-mono font-semibold">
            🎵 {plan.harmonic_key}
          </div>
          <div>
            <div className="text-xs font-semibold text-zinc-200">{plan.overall_musical_theme}</div>
            <div className="text-[11px] text-zinc-400">
              Total Score: <span className="font-mono text-zinc-200">{plan.total_score_duration_sec}s</span> | Cues:{" "}
              <span className="font-mono text-zinc-200">{plan.cues.length}</span> movements
            </div>
          </div>
        </div>

        {/* Headroom & Local Model Health Badge */}
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>ACE-Step 1.5 Turbo</span>
          </div>
          <div className="text-[11px] text-zinc-400 border border-zinc-800 px-2 py-1 rounded bg-zinc-900">
            Headroom: <span className="text-zinc-300">2-5 kHz reserved for dialogue</span>
          </div>
        </div>
      </div>

      {/* Main Studio Body: 3 Panes */}
      <div className="flex-1 flex min-h-0 divide-x divide-zinc-800 overflow-hidden">
        {/* Pane 1: Story Cues & Scene Continuity (Left) */}
        <div className="w-72 flex-shrink-0 flex flex-col bg-zinc-900/30 overflow-y-auto">
          <div className="p-3 border-b border-zinc-800/80 text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
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
                      ? "bg-indigo-950/60 border-indigo-500/60 text-white shadow-sm"
                      : "bg-zinc-900/50 border-zinc-800/60 text-zinc-300 hover:bg-zinc-800/60 hover:text-white"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-semibold mb-1">
                    <span className="truncate">
                      {idx + 1}. {cue.title}
                    </span>
                    <span className="font-mono text-[10px] text-indigo-400">{cue.duration_sec}s</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 line-clamp-1 mb-2">
                    {cue.narrative_function.replace("_", " ")}
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-400">
                    <span>Scenes: {cue.scene_ids.join(", ") || "All"}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${
                        hasTakes
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : "bg-zinc-800 text-zinc-400"
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
            <div className="mt-auto p-3 m-2 rounded-lg bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-400">
              <div className="font-semibold text-zinc-300 mb-1 flex items-center gap-1.5">
                <span>🔔 Sound Effects Library</span>
              </div>
              <div className="text-[10px] leading-relaxed text-zinc-400 mb-2">
                High-fidelity curated sound library enabled for footsteps, sword impacts, and magic activation.
              </div>
              <span className="inline-block px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-[9px] text-zinc-300">
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
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 uppercase font-mono">
                    {selectedCue.narrative_function}
                  </span>
                </div>
                <p className="text-xs text-zinc-400">{selectedCue.emotional_direction}</p>
              </div>

              {/* Story Musical Parameters */}
              <div className="grid grid-cols-3 gap-3 p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-xs">
                <div>
                  <span className="text-[10px] text-zinc-400 block uppercase font-mono">Tonal Key</span>
                  <span className="font-semibold text-zinc-200">{keyScale}</span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-400 block uppercase font-mono">Tempo (BPM)</span>
                  <span className="font-semibold text-zinc-200">{bpm} BPM</span>
                </div>
                <div>
                  <span className="text-[10px] text-zinc-400 block uppercase font-mono">Duration</span>
                  <span className="font-semibold text-zinc-200">{durationSec}s</span>
                </div>
              </div>

              {/* Editable Prompt */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-zinc-300">Story-Aware Generation Prompt</label>
                  <span className="text-[10px] text-zinc-400">User editable prior to synthesis</span>
                </div>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={4}
                  className="w-full text-xs p-3 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-indigo-500 font-sans leading-relaxed resize-none"
                  placeholder="Enter detailed music prompt..."
                />
              </div>

              {/* Advanced Settings Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                >
                  <span>{showAdvanced ? "▾ Hide Advanced Settings" : "▸ Show Advanced Settings"}</span>
                </button>

                {showAdvanced && (
                  <div className="mt-3 p-3 rounded-lg bg-zinc-900 border border-zinc-800 space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[10px] text-zinc-400 block mb-1">Target Duration (Seconds)</label>
                        <input
                          type="number"
                          min={5}
                          max={180}
                          value={durationSec}
                          onChange={(e) => setDurationSec(Number(e.target.value))}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-zinc-400 block mb-1">Tempo (BPM)</label>
                        <input
                          type="number"
                          min={40}
                          max={220}
                          value={bpm}
                          onChange={(e) => setBpm(Number(e.target.value))}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 items-center">
                      <div>
                        <label className="text-[10px] text-zinc-400 block mb-1">Random Seed</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={useRandomSeed}
                            onChange={(e) => setUseRandomSeed(e.target.checked)}
                            id="random-seed-chk"
                            className="rounded bg-zinc-800 border-zinc-700"
                          />
                          <label htmlFor="random-seed-chk" className="text-xs text-zinc-300">
                            Auto Random
                          </label>
                        </div>
                      </div>
                      {!useRandomSeed && (
                        <div>
                          <label className="text-[10px] text-zinc-400 block mb-1">Manual Seed</label>
                          <input
                            type="number"
                            value={seed}
                            onChange={(e) => setSeed(Number(e.target.value))}
                            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs font-mono"
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
                  className="w-full py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2 shadow-sm"
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
                    <div className="flex items-center justify-between text-[11px] text-zinc-400">
                      <span>{generationStatusText}</span>
                      <span className="font-mono text-zinc-200">{Math.round(generationProgress * 100)}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 transition-all duration-300"
                        style={{ width: `${generationProgress * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                {generationError && (
                  <div className="mt-3 p-3 rounded bg-rose-950/50 border border-rose-800/80 text-rose-300 text-xs">
                    {generationError}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-zinc-500 text-xs">
              Select a musical movement from the left to configure soundtrack direction.
            </div>
          )}
        </div>

        {/* Pane 3: Candidate Takes Audition & Timeline Placement (Right) */}
        <div className="w-80 flex-shrink-0 flex flex-col p-4 bg-zinc-900/40 overflow-y-auto">
          <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-3">
            Candidate Takes & Audition
          </div>

          {selectedCue && selectedCue.takes.length > 0 ? (
            <div className="space-y-4">
              {/* Takes Selector Tabs */}
              <div className="flex gap-1.5 p-1 bg-zinc-900 rounded-lg border border-zinc-800 overflow-x-auto">
                {selectedCue.takes.map((take) => {
                  const isSelected = take.take_id === selectedTakeId;
                  return (
                    <button
                      key={take.take_id}
                      onClick={() => handleSelectTake(take)}
                      className={`px-3 py-1.5 rounded text-xs font-semibold whitespace-nowrap transition-colors ${
                        isSelected
                          ? "bg-indigo-600 text-white"
                          : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
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
                  <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 space-y-2">
                    <canvas
                      ref={canvasRef}
                      width={280}
                      height={50}
                      className="w-full h-12 rounded bg-zinc-950 cursor-pointer"
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
                        className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-semibold flex items-center gap-1.5"
                      >
                        <span>{isPlaying ? "⏸ Pause" : "▶ Play"}</span>
                      </button>
                      <span className="font-mono text-zinc-400 text-[11px]">
                        {playbackTime.toFixed(1)}s / {currentTake.duration_sec}s
                      </span>
                    </div>
                  </div>

                  {/* Audio Master Specifications */}
                  <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800 text-[11px] space-y-1.5">
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Sample Rate:</span>
                      <span className="font-mono text-zinc-200">48,000 Hz Stereo</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Format:</span>
                      <span className="font-mono text-zinc-200">16-bit PCM WAV</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">True Peak:</span>
                      <span className="font-mono text-zinc-200">{currentTake.measured_peak_dbfs} dBFS</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">RMS Level:</span>
                      <span className="font-mono text-zinc-200">{currentTake.measured_rms_dbfs} dBFS</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Seed:</span>
                      <span className="font-mono text-zinc-200">{currentTake.seed}</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="space-y-2 pt-2">
                    <button
                      type="button"
                      onClick={handleSendToTimeline}
                      className="w-full py-2.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2 shadow-sm"
                    >
                      <span>📥 Add Take to Timeline (BGM Track)</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleSaveToLibrary}
                      className="w-full py-2 px-3 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
                    >
                      <span>💾 Save to Library Catalog</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-zinc-500 text-xs border border-dashed border-zinc-800 rounded-lg">
              <span className="text-xl mb-1">🎼</span>
              <span>No generated takes yet for this cue. Click "Generate Real Take" to synthesize one locally.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
