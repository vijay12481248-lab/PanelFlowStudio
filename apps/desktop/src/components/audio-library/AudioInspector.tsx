import React, { useState } from "react";
import type {
  AudioAsset,
  AudioPreviewState,
  AudioToTimelineContract,
} from "./AudioLibrary.types.ts";

interface AudioInspectorProps {
  asset: AudioAsset | null;
  previewState: AudioPreviewState;
  onTogglePlay: (asset: AudioAsset) => void;
  onStop: () => void;
  onSeek: (newTimeSec: number) => void;
  onChangeVolume: (volume: number) => void;
  onToggleMute: () => void;
  onToggleFavorite: (assetId: string) => void;
  onSendToTimeline?: (contract: AudioToTimelineContract) => void;
}

function formatTime(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const mins = Math.floor(sec / 60);
  const remainingSecs = Math.floor(sec % 60);
  return `${mins}:${remainingSecs.toString().padStart(2, "0")}`;
}

function formatBytes(bytes?: number): string {
  if (!bytes) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export const AudioInspector: React.FC<AudioInspectorProps> = ({
  asset,
  previewState,
  onTogglePlay,
  onStop,
  onSeek,
  onChangeVolume,
  onToggleMute,
  onToggleFavorite,
  onSendToTimeline,
}) => {
  // Timeline deployment configuration state
  const [targetTrack, setTargetTrack] = useState<"BGM" | "SFX">("BGM");
  const [trackVolume, setTrackVolume] = useState<number>(0.85);
  const [loopPlayback, setLoopPlayback] = useState<boolean>(true);
  const [fadeInSec, setFadeInSec] = useState<number>(1.0);
  const [fadeOutSec, setFadeOutSec] = useState<number>(1.5);
  const [contractSentNotice, setContractSentNotice] = useState<boolean>(false);

  // Sync default target track with asset recommendation
  React.useEffect(() => {
    if (asset) {
      setTargetTrack(asset.recommended_timeline_track);
      setLoopPlayback(asset.loopable ?? asset.type === "music");
      setFadeInSec(asset.type === "music" ? 1.0 : 0.0);
      setFadeOutSec(asset.type === "music" ? 1.5 : 0.0);
      setContractSentNotice(false);
    }
  }, [asset?.id]);

  if (!asset) {
    return (
      <aside className="w-80 bg-zinc-950 border-l border-zinc-800 flex flex-col items-center justify-center p-6 text-center select-none shrink-0 text-zinc-500">
        <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-xl mb-3">
          🎧
        </div>
        <h3 className="text-xs font-semibold text-zinc-300 mb-1">No Audio Asset Selected</h3>
        <p className="text-[11px] text-zinc-500 max-w-[200px]">
          Select any music score or sound effect from the library to inspect its waveform, specs, and timeline integration.
        </p>
      </aside>
    );
  }

  const isPlayingThisAsset =
    previewState.playing_asset_id === asset.id && previewState.is_playing;
  const isMissingFile = asset.availability === "MISSING_FILE";

  const handleSendToTimeline = () => {
    if (!asset || isMissingFile || !onSendToTimeline) return;

    const contract: AudioToTimelineContract = {
      schema_version: "6A-v1",
      exported_at: new Date().toISOString(),
      reference: {
        asset_id: asset.id,
        name: asset.name,
        type: asset.type,
        category: asset.category,
        duration_sec: asset.duration_sec,
        file_url: asset.file_url || "",
        target_track: targetTrack,
        volume: trackVolume,
        loop: loopPlayback,
        fade_in_sec: fadeInSec,
        fade_out_sec: fadeOutSec,
        bpm: asset.bpm,
        key: asset.key,
      },
    };

    onSendToTimeline(contract);
    setContractSentNotice(true);
    setTimeout(() => setContractSentNotice(false), 3000);
  };

  return (
    <aside className="w-80 bg-zinc-950 border-l border-zinc-800 flex flex-col h-full select-none shrink-0 overflow-y-auto custom-scrollbar">
      {/* Top Header */}
      <div className="p-3.5 border-b border-zinc-800 bg-zinc-950/90 flex items-start justify-between gap-2 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className={`text-[9px] uppercase font-bold px-1.5 py-0.2 rounded ${
                asset.type === "music"
                  ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                  : "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
              }`}
            >
              {asset.type}
            </span>
            <span className="text-[10px] text-zinc-400 font-mono">
              {asset.category.replace("_", " ")}
            </span>
          </div>
          <h2 className="text-xs font-bold text-zinc-100 truncate" title={asset.name}>
            {asset.name}
          </h2>
          <span className="text-[10px] text-zinc-500 font-mono truncate block">
            ID: {asset.id}
          </span>
        </div>

        <button
          type="button"
          onClick={() => onToggleFavorite(asset.id)}
          className={`p-1.5 rounded-lg text-sm shrink-0 transition-colors ${
            asset.is_favorite
              ? "text-amber-400 hover:text-amber-300"
              : "text-zinc-600 hover:text-zinc-300"
          }`}
          title={asset.is_favorite ? "Remove from favorites" : "Add to favorites"}
        >
          {asset.is_favorite ? "⭐" : "☆"}
        </button>
      </div>

      <div className="p-3.5 space-y-4 flex-1">
        {/* Missing File Warning Banner */}
        {isMissingFile && (
          <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-700/60 text-rose-200">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-base">⚠️</span>
              <span className="text-xs font-bold text-rose-300">
                Audio Master File Missing
              </span>
            </div>
            <p className="text-[11px] text-rose-200/80 leading-relaxed mb-2">
              This asset entry is registered in the PanelFlow catalog, but the corresponding audio file could not be found in the local assets cache.
            </p>
            <div className="text-[10px] bg-rose-950/80 p-1.5 rounded border border-rose-800/60 font-mono text-rose-300/90 break-all">
              Path: {asset.file_url ?? "None specified"}
            </div>
          </div>
        )}

        {/* Interactive Audio Preview Player */}
        <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-zinc-300">Preview Player</span>
            <span className="text-[11px] font-mono text-zinc-400">
              {formatTime(
                isPlayingThisAsset ? previewState.current_time_sec : 0
              )}{" "}
              / {formatTime(asset.duration_sec)}
            </span>
          </div>

          {/* Waveform Scrubber or Unmeasured Status */}
          <div className="space-y-1">
            {asset.measured_peaks && asset.measured_peaks.length > 0 ? (
              <div
                className="w-full h-12 bg-zinc-950 rounded-lg p-1.5 flex items-center gap-0.5 border border-zinc-800 cursor-pointer relative group"
                onClick={(e) => {
                  if (isMissingFile) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const clickX = e.clientX - rect.left;
                  const ratio = Math.max(0, Math.min(1, clickX / rect.width));
                  onSeek(ratio * asset.duration_sec);
                }}
                title="Click anywhere on waveform to seek"
              >
                {asset.measured_peaks.map((peak, idx) => {
                  const progress =
                    isPlayingThisAsset && previewState.duration_sec > 0
                      ? previewState.current_time_sec / previewState.duration_sec
                      : 0;
                  const barProgress = idx / asset.measured_peaks!.length;
                  const isPast = isPlayingThisAsset && barProgress <= progress;

                  return (
                    <div
                      key={idx}
                      className={`flex-1 rounded-sm transition-colors ${
                        isPast
                          ? "bg-amber-400"
                          : isPlayingThisAsset
                          ? "bg-indigo-400"
                          : "bg-zinc-600 group-hover:bg-zinc-500"
                      }`}
                      style={{
                        height: `${Math.max(15, Math.min(100, Math.round(peak * 100)))}%`,
                      }}
                    />
                  );
                })}
              </div>
            ) : (
              <div className="h-10 bg-zinc-950 rounded-lg flex items-center justify-center border border-zinc-800 text-[10px] text-zinc-500 italic">
                📊 Real waveform unmeasured (synthetic waveform suppressed)
              </div>
            )}

            {/* Seek Bar Slider */}
            <input
              type="range"
              min={0}
              max={asset.duration_sec}
              step={0.1}
              value={isPlayingThisAsset ? previewState.current_time_sec : 0}
              onChange={(e) => onSeek(parseFloat(e.target.value))}
              disabled={isMissingFile}
              className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
            />
          </div>

          {/* Transport Buttons: Play, Stop, Loop */}
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => onTogglePlay(asset)}
                disabled={isMissingFile}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 shadow-sm transition-all ${
                  isMissingFile
                    ? "bg-zinc-800/40 text-zinc-600 cursor-not-allowed"
                    : isPlayingThisAsset
                    ? "bg-amber-500 hover:bg-amber-400 text-zinc-950 font-extrabold"
                    : "bg-indigo-600 hover:bg-indigo-500 text-white"
                }`}
              >
                <span>{isPlayingThisAsset ? "⏸" : "▶"}</span>
                <span>{isPlayingThisAsset ? "Pause" : "Play"}</span>
              </button>

              <button
                type="button"
                onClick={onStop}
                disabled={!isPlayingThisAsset || isMissingFile}
                className="p-1.5 rounded-lg text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed"
                title="Stop playback"
              >
                ⏹ Stop
              </button>
            </div>

            {/* Volume & Mute Control */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={onToggleMute}
                className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                title={previewState.is_muted ? "Unmute" : "Mute"}
              >
                {previewState.is_muted || previewState.volume === 0 ? "🔇" : "🔊"}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={previewState.is_muted ? 0 : previewState.volume}
                onChange={(e) => onChangeVolume(parseFloat(e.target.value))}
                className="w-16 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                title={`Volume: ${Math.round(previewState.volume * 100)}%`}
              />
            </div>
          </div>

          {/* Playback Error Banner */}
          {previewState.playback_error && (
            <div className="p-2 rounded bg-rose-950/60 border border-rose-800 text-[10px] text-rose-300">
              Error: {previewState.playback_error}
            </div>
          )}
        </div>

        {/* Technical Specs Table */}
        <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">
            Technical Audio Specs
          </span>
          <div className="grid grid-cols-2 gap-2 text-xs pt-1">
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">Format</span>
              <span className="font-semibold text-zinc-200 uppercase font-mono">
                {asset.file_format}
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">Duration</span>
              <span className="font-semibold text-zinc-200 font-mono">
                {asset.duration_sec.toFixed(1)}s
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">Sample Rate</span>
              <span className="font-semibold text-zinc-200 font-mono">
                {asset.sample_rate_hz ? `${asset.sample_rate_hz / 1000} kHz` : "44.1 kHz"}
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">Channels</span>
              <span className="font-semibold text-zinc-200">
                {asset.channels ?? "Stereo"}
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">File Size</span>
              <span className="font-semibold text-zinc-200 font-mono">
                {formatBytes(asset.file_size_bytes)}
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded-lg border border-zinc-800/80">
              <span className="text-[10px] text-zinc-500 block">BPM / Key</span>
              <span className="font-semibold text-zinc-200 font-mono truncate block">
                {asset.bpm ? `${asset.bpm} BPM` : "—"}{" "}
                {asset.key ? `(${asset.key})` : ""}
              </span>
            </div>
          </div>
        </div>

        {/* Licensing & Source Information */}
        <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">
            Licensing & Source
          </span>
          <div className="space-y-1.5 text-xs pt-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-zinc-400">License:</span>
              <span className="font-semibold text-indigo-300 text-[11px] text-right truncate max-w-[180px]">
                {asset.license.license_type}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-zinc-400">Author:</span>
              <span className="text-zinc-200 text-[11px] text-right truncate max-w-[180px]">
                {asset.license.author_or_source}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-zinc-400">Commercial Use:</span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                  asset.license.commercial_use_allowed
                    ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                    : "bg-rose-950 text-rose-300 border border-rose-800/60"
                }`}
              >
                {asset.license.commercial_use_allowed ? "Allowed" : "Restricted"}
              </span>
            </div>
            {asset.license.notes && (
              <p className="text-[10px] text-zinc-500 italic pt-1 border-t border-zinc-800">
                &ldquo;{asset.license.notes}&rdquo;
              </p>
            )}
          </div>
        </div>

        {/* Future Timeline Integration Contract Card (Schema 6A-v1) */}
        <div className="p-3 rounded-xl bg-gradient-to-b from-indigo-950/40 to-zinc-900 border border-indigo-500/30 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-xs">🎬</span>
              <span className="text-xs font-bold text-zinc-200">
                Timeline Deployment
              </span>
            </div>
            <span className="text-[9px] bg-indigo-900/60 border border-indigo-700/60 text-indigo-300 px-1.5 py-0.2 rounded font-mono">
              Schema 6A-v1
            </span>
          </div>

          <p className="text-[10px] text-zinc-400 leading-relaxed">
            Configure placement parameters before passing this audio cue to the Story Editor timeline.
          </p>

          <div className="space-y-2 text-xs">
            {/* Target Track Selection */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-zinc-400">Target Track:</span>
              <div className="flex items-center gap-1 bg-zinc-950 p-0.5 rounded border border-zinc-800 text-[11px]">
                <button
                  type="button"
                  onClick={() => setTargetTrack("BGM")}
                  className={`px-2 py-0.5 rounded font-semibold transition-colors ${
                    targetTrack === "BGM"
                      ? "bg-purple-600 text-white"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  BGM Track
                </button>
                <button
                  type="button"
                  onClick={() => setTargetTrack("SFX")}
                  className={`px-2 py-0.5 rounded font-semibold transition-colors ${
                    targetTrack === "SFX"
                      ? "bg-emerald-600 text-white"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  SFX Track
                </button>
              </div>
            </div>

            {/* Loop Toggle */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-zinc-400">Loop on Track:</span>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={loopPlayback}
                  onChange={(e) => setLoopPlayback(e.target.checked)}
                  className="rounded bg-zinc-800 border-zinc-700 accent-indigo-500 cursor-pointer"
                />
                <span className="text-[11px] text-zinc-300">
                  {loopPlayback ? "Continuous" : "One-shot"}
                </span>
              </label>
            </div>

            {/* Fades */}
            <div className="grid grid-cols-2 gap-2 pt-1">
              <div>
                <span className="text-[10px] text-zinc-500 block">Fade In (s)</span>
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={0.5}
                  value={fadeInSec}
                  onChange={(e) => setFadeInSec(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 font-mono"
                />
              </div>
              <div>
                <span className="text-[10px] text-zinc-500 block">Fade Out (s)</span>
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={0.5}
                  value={fadeOutSec}
                  onChange={(e) => setFadeOutSec(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 font-mono"
                />
              </div>
            </div>
          </div>

          {/* Send to Timeline Button */}
          <button
            type="button"
            onClick={handleSendToTimeline}
            disabled={isMissingFile}
            className={`w-full py-2 rounded-lg text-xs font-bold shadow-md transition-all flex items-center justify-center gap-2 ${
              isMissingFile
                ? "bg-zinc-800/40 text-zinc-600 border border-zinc-800 cursor-not-allowed"
                : contractSentNotice
                ? "bg-emerald-600 text-white"
                : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-900/40"
            }`}
          >
            <span>{contractSentNotice ? "✓" : "🚀"}</span>
            <span>
              {contractSentNotice
                ? "Sent to Timeline Queue!"
                : `Send to ${targetTrack} Track`}
            </span>
          </button>
        </div>
      </div>
    </aside>
  );
};
