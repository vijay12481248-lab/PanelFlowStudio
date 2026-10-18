import React, { useState, useEffect, useRef } from "react";
import { Icons, Button, Badge } from "@panelflow/ui";
import type {
  NarrationSegment,
  VoiceProfile,
} from "./NarrationStudio.types";

interface AudioPreviewPlayerProps {
  segment: NarrationSegment;
  voiceProfile?: VoiceProfile;
  onApproveAudio?: (segmentId: string) => void;
  onRequestRetake?: (segmentId: string) => void;
  className?: string;
}

export const AudioPreviewPlayer: React.FC<AudioPreviewPlayerProps> = ({
  segment,
  voiceProfile,
  onApproveAudio,
  onRequestRetake,
  className = "",
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackTime, setPlaybackTime] = useState<number>(0);
  const [volume, setVolume] = useState<number>(0.8);
  const [activePlaybackMode, setActivePlaybackMode] = useState<"audio_asset" | "browser_speech" | "synth_chime" | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const oscillatorRef = useRef<OscillatorNode | null>(null);
  const timerRef = useRef<any>(null);

  // Check if browser has speech synthesis
  const hasBrowserSpeech = typeof window !== "undefined" && "speechSynthesis" in window;

  // Active audio take or preserved previous audio take
  const activeAudioUri = segment.audio_asset_uri;
  const previousAudioUri = segment.previous_audio_asset_uri;
  const isOutdated = segment.generation_status === "OUTDATED";
  const hasPlayableAsset = !!activeAudioUri || (isOutdated && !!previousAudioUri);

  const audioElementRef = useRef<HTMLAudioElement | null>(null);

  // Clean up audio on unmount or segment change
  useEffect(() => {
    stopPlayback();
    return () => {
      stopPlayback();
    };
  }, [segment.id]);

  const stopPlayback = () => {
    setIsPlaying(false);
    setPlaybackTime(0);
    setActivePlaybackMode(null);

    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (audioElementRef.current) {
      audioElementRef.current.pause();
      audioElementRef.current.currentTime = 0;
      audioElementRef.current = null;
    }

    if (hasBrowserSpeech) {
      window.speechSynthesis?.cancel();
    }

    if (oscillatorRef.current) {
      try {
        oscillatorRef.current.stop();
        oscillatorRef.current.disconnect();
      } catch {
        // Ignore if already stopped
      }
      oscillatorRef.current = null;
    }
  };

  // Real Local Audio Asset Playback
  const handlePlayRealAudio = () => {
    const uri = activeAudioUri || previousAudioUri;
    if (!uri) return;

    if (isPlaying && activePlaybackMode === "audio_asset") {
      stopPlayback();
      return;
    }

    stopPlayback();

    try {
      const audio = new Audio(uri);
      audioElementRef.current = audio;
      audio.volume = volume;

      audio.onended = () => {
        stopPlayback();
      };
      audio.onerror = (e) => {
        console.warn("Audio element playback error, falling back to tone:", e);
        handlePlayDemonstrationTone();
      };

      audio.play().then(() => {
        setIsPlaying(true);
        setActivePlaybackMode("audio_asset");
        timerRef.current = setInterval(() => {
          if (audioElementRef.current) {
            setPlaybackTime(Math.round(audioElementRef.current.currentTime * 10) / 10);
          }
        }, 50);
      }).catch((err) => {
        console.warn("Audio play prevented or failed:", err);
        handlePlayDemonstrationTone();
      });
    } catch (e) {
      console.warn("Failed to instantiate Audio:", e);
      handlePlayDemonstrationTone();
    }
  };

  // Browser Speech Synthesis Scratch Preview (strictly labeled as neutral Web Speech API, not local neural TTS)
  const handlePlayBrowserSpeech = () => {
    if (isPlaying && activePlaybackMode === "browser_speech") {
      stopPlayback();
      return;
    }

    stopPlayback();

    if (!hasBrowserSpeech) {
      alert("Browser SpeechSynthesis API is not supported in this environment.");
      return;
    }

    try {
      const utterance = new SpeechSynthesisUtterance(segment.narration_text);
      utterance.rate = Math.max(0.75, Math.min(1.5, segment.delivery.speech_speed || 1.0));
      utterance.volume = volume;

      utterance.onend = () => {
        stopPlayback();
      };

      utterance.onerror = () => {
        stopPlayback();
      };

      window.speechSynthesis.speak(utterance);
      setIsPlaying(true);
      setActivePlaybackMode("browser_speech");

      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        setPlaybackTime(Math.round(elapsed * 10) / 10);
      }, 100);
    } catch (e) {
      console.warn("Browser SpeechSynthesis failed:", e);
      stopPlayback();
    }
  };

  // Demonstration preview tone (Web Audio API Chime — explicit acoustic demonstration, not speech)
  const handlePlayDemonstrationTone = () => {
    if (isPlaying && activePlaybackMode === "synth_chime") {
      stopPlayback();
      return;
    }

    stopPlayback();

    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) {
        alert("Web Audio API not supported in this environment.");
        return;
      }

      const ctx = audioContextRef.current || new AudioCtx();
      audioContextRef.current = ctx;

      if (ctx.state === "suspended") {
        ctx.resume();
      }

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      // D-Minor frequency reference
      const freq = segment.delivery.emotion === "Suspenseful" ? 293.66 : 349.23;
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, ctx.currentTime);

      gain.gain.setValueAtTime(volume * 0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + Math.min(segment.estimated_duration_sec, 3.5));

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      oscillatorRef.current = osc;
      setIsPlaying(true);
      setActivePlaybackMode("synth_chime");

      const maxDuration = Math.min(segment.estimated_duration_sec, 3.5);
      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        if (elapsed >= maxDuration) {
          stopPlayback();
        } else {
          setPlaybackTime(Math.round(elapsed * 10) / 10);
        }
      }, 100);
    } catch (e) {
      console.warn("Failed to play preview tone:", e);
      stopPlayback();
    }
  };

  return (
    <div className={`p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-3 select-none text-xs ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="w-5 h-5 rounded-md bg-indigo-600/80 text-white flex items-center justify-center font-bold text-[10px]">
            🔊
          </span>
          <span className="font-bold text-zinc-200 uppercase tracking-wider text-[11px]">
            Audio Preview
          </span>
        </div>

        {/* State Badge */}
        {segment.generation_status === "READY" ? (
          <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-950/70 border border-emerald-800 px-2 py-0.5 rounded-full flex items-center gap-1">
            <Icons.Check className="w-2.5 h-2.5" />
            Audio Generated (Rev #{segment.generated_audio_revision || segment.text_revision})
          </span>
        ) : segment.generation_status === "OUTDATED" ? (
          <span className="text-[10px] font-semibold text-amber-400 bg-amber-950/70 border border-amber-800 px-2 py-0.5 rounded-full flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            Audio Outdated (Take Preserved)
          </span>
        ) : (
          <span className="text-[10px] font-semibold text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded-full">
            Not Generated
          </span>
        )}
      </div>

      {/* Voice & Emotion Tags */}
      <div className="flex items-center justify-between text-[11px] p-2 rounded-lg bg-zinc-950/80 border border-zinc-800/80">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-zinc-200">
            {voiceProfile?.name.split("—")[0].trim() || "Default Voice"}
          </span>
          <span className="text-zinc-600">•</span>
          <span className="text-indigo-400 font-medium">
            {segment.delivery.emotion} ({segment.delivery.speech_speed}x)
          </span>
        </div>
        <span className="font-mono text-zinc-500 text-[10px]">
          {segment.measured_duration_sec
            ? `${segment.measured_duration_sec}s measured`
            : `~${segment.estimated_duration_sec}s est.`}
        </span>
      </div>

      {/* Decision 2: Preserved Previous Take Banner (if outdated) */}
      {isOutdated && previousAudioUri && (
        <div className="p-2 rounded bg-amber-950/40 border border-amber-800/60 text-[11px] text-amber-300 space-y-1">
          <div className="flex items-center justify-between font-semibold">
            <span>Preserved Previous Audio Take:</span>
            <span className="font-mono text-[10px]">Rev #{segment.generated_audio_revision || 1}</span>
          </div>
          <p className="text-[10px] text-amber-200/80 leading-normal">
            Script was modified (now Rev #{segment.text_revision}). You can listen to the previous audio take below until you explicitly regenerate.
          </p>
        </div>
      )}

      {/* Playback Controls Area */}
      {hasPlayableAsset ? (
        <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handlePlayRealAudio}
                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                  isPlaying && (activePlaybackMode === "audio_asset" || activePlaybackMode === "synth_chime")
                    ? "bg-rose-600 text-white animate-pulse"
                    : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-950"
                }`}
                title={isPlaying ? "Stop Preview" : "Play Audio Take"}
              >
                {isPlaying ? (
                  <Icons.Pause className="w-4 h-4" />
                ) : (
                  <Icons.Play className="w-4 h-4 ml-0.5" />
                )}
              </button>

              <div className="flex flex-col">
                <span className="text-xs font-bold text-zinc-100">
                  {isPlaying ? "Playing Voiceover..." : isOutdated ? "Previous Audio Take" : "Current Voice Take"}
                </span>
                <span className="text-[10px] text-zinc-400">
                  {isOutdated ? "Archived previous take" : "Local Chatterbox Turbo Take"}
                </span>
              </div>
            </div>

            <span className="font-mono text-xs text-indigo-400 font-bold">
              {playbackTime.toFixed(1)}s / {(segment.measured_duration_sec || segment.estimated_duration_sec || 3.5).toFixed(1)}s
            </span>
          </div>

          {/* Progress scrubber visual */}
          <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-indigo-500 h-1.5 rounded-full transition-all duration-100 ease-linear"
              style={{
                width: `${Math.min(100, (playbackTime / Math.max(0.1, segment.measured_duration_sec || segment.estimated_duration_sec || 3.5)) * 100)}%`,
              }}
            />
          </div>

          {/* Volume Control */}
          <div className="flex items-center justify-between pt-1 text-[10px] text-zinc-400">
            <span className="flex items-center gap-1">
              <Icons.Volume className="w-3 h-3 text-zinc-400" />
              Volume
            </span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={volume}
              onChange={(e) => setVolume(parseFloat(e.target.value))}
              className="w-24 accent-indigo-500 h-1 bg-zinc-800 rounded cursor-pointer"
            />
          </div>
        </div>
      ) : (
        /* Explicit "Audio preview unavailable" State */
        <div className="p-3.5 rounded-lg bg-zinc-950 border border-zinc-800 text-center space-y-2">
          <div className="flex items-center justify-center gap-1.5 text-zinc-400 font-bold text-xs">
            <span>🔇</span>
            <span>Audio preview unavailable</span>
          </div>
          <p className="text-[10px] text-zinc-500 leading-normal max-w-xs mx-auto">
            Neural TTS speech has not been synthesized for this revision yet.
          </p>
        </div>
      )}

      {/* Audio Preview Verification Options */}
      <div className="pt-2 border-t border-zinc-800/80 space-y-2">
        <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-zinc-500">
          <span>Scratch Listening Options</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {/* Option A: Browser Speech Preview (strictly labeled) */}
          <button
            type="button"
            onClick={handlePlayBrowserSpeech}
            className={`py-1.5 px-2 rounded-lg border text-left flex flex-col justify-between transition-colors ${
              isPlaying && activePlaybackMode === "browser_speech"
                ? "bg-indigo-950 border-indigo-600 text-indigo-200"
                : "bg-zinc-950 hover:bg-zinc-900 border-zinc-800 text-zinc-300"
            }`}
          >
            <span className="font-bold text-[11px] flex items-center gap-1">
              <span>🗣️</span>
              <span>{isPlaying && activePlaybackMode === "browser_speech" ? "Stop Speech" : "Browser Speech"}</span>
            </span>
            <span className="text-[9px] text-zinc-500 mt-0.5 leading-tight">
              Neutral Web Speech API (Pacing preview only)
            </span>
          </button>

          {/* Option B: Audio Interface Demo Tone */}
          <button
            type="button"
            onClick={handlePlayDemonstrationTone}
            className={`py-1.5 px-2 rounded-lg border text-left flex flex-col justify-between transition-colors ${
              isPlaying && activePlaybackMode === "synth_chime"
                ? "bg-indigo-950 border-indigo-600 text-indigo-200"
                : "bg-zinc-950 hover:bg-zinc-900 border-zinc-800 text-zinc-300"
            }`}
          >
            <span className="font-bold text-[11px] flex items-center gap-1">
              <span>🎵</span>
              <span>{isPlaying && activePlaybackMode === "synth_chime" ? "Stop Tone" : "Demo Tone"}</span>
            </span>
            <span className="text-[9px] text-zinc-500 mt-0.5 leading-tight">
              Web Audio Synth Chime (Interface test only)
            </span>
          </button>
        </div>

        {/* Verification Notice */}
        <p className="text-[9px] text-zinc-500 leading-normal bg-zinc-950 p-1.5 rounded border border-zinc-800/60">
          ℹ️ <span className="font-semibold text-zinc-400">Audio Verification Note:</span> Web Speech API and Web Audio tones do not represent local neural TTS models (F5-TTS, Chatterbox) or nuanced emotional delivery.
        </p>
      </div>

      {/* Review Actions */}
      <div className="flex items-center justify-between pt-2 border-t border-zinc-800/80">
        <button
          type="button"
          onClick={() => onRequestRetake?.(segment.id)}
          className="text-[10px] text-zinc-400 hover:text-amber-300 font-semibold flex items-center gap-1"
        >
          <span>Flag for Voice Revision</span>
        </button>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => onApproveAudio?.(segment.id)}
          disabled={segment.generation_status !== "READY"}
          className="text-xs h-7 disabled:opacity-40"
        >
          ✓ Mark Audio Approved
        </Button>
      </div>
    </div>
  );
};
