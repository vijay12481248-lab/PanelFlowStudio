import React, { useState, useEffect, useRef, useCallback } from "react";
import type {
  AudioAsset,
  AudioFilterState,
  AudioPreviewState,
  AudioToTimelineContract,
  AudioLibraryProps,
} from "./AudioLibrary.types.ts";
import { MOCK_AUDIO_ASSETS } from "./AudioLibrary.mock.ts";
import { AudioCategoryNav } from "./AudioCategoryNav.tsx";
import { AudioAssetBrowser } from "./AudioAssetBrowser.tsx";
import { AudioInspector } from "./AudioInspector.tsx";
import { AIMusicStudio } from "./AIMusicStudio.tsx";

const FAVORITES_STORAGE_KEY = "panelflow_audio_favorites";

export const AudioLibrary: React.FC<AudioLibraryProps> = ({
  initialAssets,
  selectedAssetId: externalSelectedAssetId,
  initialType,
  projectId = "68711176-90f5-4a68-8520-78d6e183bf65",
  onSelectAsset: externalOnSelectAsset,
  onSendToTimeline,
  onClose,
}) => {
  const [activeWorkspace, setActiveWorkspace] = useState<"catalog" | "ai_generator">(
    initialType === "music" ? "ai_generator" : "catalog"
  );

  // Load initial assets and sync favorites from localStorage
  const [assets, setAssets] = useState<AudioAsset[]>(() => {
    const baseAssets = initialAssets && initialAssets.length > 0 ? initialAssets : MOCK_AUDIO_ASSETS;
    try {
      const stored = localStorage.getItem(FAVORITES_STORAGE_KEY);
      if (stored) {
        const favoriteIds: string[] = JSON.parse(stored);
        return baseAssets.map((a) => ({
          ...a,
          is_favorite: favoriteIds.includes(a.id) ? true : a.is_favorite,
        }));
      }
    } catch {
      // Ignore localStorage errors in non-browser/test environments
    }
    return baseAssets;
  });

  // Filter state
  const [filter, setFilter] = useState<AudioFilterState>({
    search_query: "",
    selected_category: initialType === "sfx" ? "character" : "background_music",
    selected_type: initialType ?? "all",
    sort_by: "recent",
    only_favorites: false,
    only_loopable: false,
  });

  // Selected asset
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(() => {
    return externalSelectedAssetId ?? (assets.length > 0 ? assets[0].id : null);
  });

  const activeSelectedId = externalSelectedAssetId !== undefined ? externalSelectedAssetId : internalSelectedId;
  const selectedAsset = assets.find((a) => a.id === activeSelectedId) || null;

  // Audio preview playback state
  const [previewState, setPreviewState] = useState<AudioPreviewState>({
    playing_asset_id: null,
    is_playing: false,
    current_time_sec: 0,
    duration_sec: 0,
    volume: 0.8,
    is_muted: false,
    playback_error: null,
  });

  // Audio element reference
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize or re-create audio element
  useEffect(() => {
    if (typeof window !== "undefined" && !audioRef.current) {
      const audio = new Audio();
      audio.preload = "auto";
      audioRef.current = audio;

      const handleTimeUpdate = () => {
        setPreviewState((prev) => ({
          ...prev,
          current_time_sec: audio.currentTime,
        }));
      };

      const handleLoadedMetadata = () => {
        setPreviewState((prev) => ({
          ...prev,
          duration_sec: audio.duration || prev.duration_sec,
        }));
      };

      const handleEnded = () => {
        setPreviewState((prev) => ({
          ...prev,
          is_playing: false,
          current_time_sec: 0,
        }));
      };

      const handleError = () => {
        setPreviewState((prev) => ({
          ...prev,
          is_playing: false,
          playback_error: "Unable to decode audio stream.",
        }));
      };

      audio.addEventListener("timeupdate", handleTimeUpdate);
      audio.addEventListener("loadedmetadata", handleLoadedMetadata);
      audio.addEventListener("ended", handleEnded);
      audio.addEventListener("error", handleError);

      return () => {
        audio.removeEventListener("timeupdate", handleTimeUpdate);
        audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
        audio.removeEventListener("ended", handleEnded);
        audio.removeEventListener("error", handleError);
        audio.pause();
        audio.src = "";
      };
    }
  }, []);

  // Update volume and mute on audio element
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = previewState.is_muted ? 0 : previewState.volume;
    }
  }, [previewState.volume, previewState.is_muted]);

  // Handle asset selection
  const handleSelectAsset = useCallback((asset: AudioAsset) => {
    setInternalSelectedId(asset.id);
    if (externalOnSelectAsset) {
      externalOnSelectAsset(asset);
    }
  }, [externalOnSelectAsset]);

  // Handle toggle play/pause
  const handleTogglePlay = useCallback((asset: AudioAsset) => {
    if (asset.availability === "MISSING_FILE" || !asset.file_url) {
      setPreviewState((prev) => ({
        ...prev,
        is_playing: false,
        playback_error: `File for "${asset.name}" is missing on disk.`,
      }));
      return;
    }

    if (!audioRef.current) return;
    const audio = audioRef.current;

    if (previewState.playing_asset_id === asset.id && previewState.is_playing) {
      // Pause
      audio.pause();
      setPreviewState((prev) => ({
        ...prev,
        is_playing: false,
      }));
    } else {
      // Play new or resume
      if (previewState.playing_asset_id !== asset.id) {
        audio.src = asset.file_url;
        audio.currentTime = 0;
        setPreviewState((prev) => ({
          ...prev,
          playing_asset_id: asset.id,
          current_time_sec: 0,
          duration_sec: asset.duration_sec,
          playback_error: null,
        }));
      }

      audio.play().then(() => {
        setPreviewState((prev) => ({
          ...prev,
          is_playing: true,
          playback_error: null,
        }));
      }).catch((err) => {
        // Handled gracefully without crash
        setPreviewState((prev) => ({
          ...prev,
          is_playing: false,
          playback_error: err?.message || "Playback failed to initiate.",
        }));
      });
    }
  }, [previewState.playing_asset_id, previewState.is_playing]);

  // Stop playback
  const handleStop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setPreviewState((prev) => ({
      ...prev,
      is_playing: false,
      current_time_sec: 0,
    }));
  }, []);

  // Seek playback
  const handleSeek = useCallback((newTimeSec: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = newTimeSec;
    }
    setPreviewState((prev) => ({
      ...prev,
      current_time_sec: newTimeSec,
    }));
  }, []);

  // Change volume
  const handleChangeVolume = useCallback((volume: number) => {
    const clamped = Math.max(0, Math.min(1, volume));
    setPreviewState((prev) => ({
      ...prev,
      volume: clamped,
      is_muted: clamped === 0 ? true : false,
    }));
  }, []);

  // Toggle mute
  const handleToggleMute = useCallback(() => {
    setPreviewState((prev) => ({
      ...prev,
      is_muted: !prev.is_muted,
    }));
  }, []);

  // Toggle favorite
  const handleToggleFavorite = useCallback((assetId: string) => {
    setAssets((prev) => {
      const updated = prev.map((a) =>
        a.id === assetId ? { ...a, is_favorite: !a.is_favorite } : a
      );
      try {
        const favoriteIds = updated.filter((a) => a.is_favorite).map((a) => a.id);
        localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favoriteIds));
      } catch {
        // Ignore storage errors
      }
      return updated;
    });
  }, []);

  // Quick send from browser
  const handleQuickSend = useCallback((asset: AudioAsset) => {
    if (onSendToTimeline) {
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
          target_track: asset.recommended_timeline_track,
          volume: 0.85,
          loop: asset.loopable ?? asset.type === "music",
          fade_in_sec: asset.type === "music" ? 1.0 : 0.0,
          fade_out_sec: asset.type === "music" ? 1.5 : 0.0,
          bpm: asset.bpm,
          key: asset.key,
        },
      };
      onSendToTimeline(contract);
    }
  }, [onSendToTimeline]);

  // Spacebar shortcut to toggle play/pause
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        if (selectedAsset) {
          handleTogglePlay(selectedAsset);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedAsset, handleTogglePlay]);

  return (
    <div
      data-testid="audio-library-container"
      className="flex flex-col h-full w-full bg-zinc-950 text-zinc-100 select-none overflow-hidden font-sans"
    >
      {/* Top Application Bar */}
      <header className="h-12 border-b border-zinc-800 bg-zinc-950 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/40 flex items-center justify-center font-bold text-sm shadow-sm">
              🎧
            </div>
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
              <span>PanelFlow Audio Studio</span>
            </h1>
          </div>

          {/* Workspace Tabs: Catalog vs AI Music Studio */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setActiveWorkspace("catalog")}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                activeWorkspace === "catalog"
                  ? "bg-zinc-800 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Library Catalog
            </button>
            <button
              type="button"
              onClick={() => setActiveWorkspace("ai_generator")}
              className={`px-3 py-1 text-xs font-semibold rounded-md flex items-center gap-1.5 transition-colors ${
                activeWorkspace === "ai_generator"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <span>✨ Story-Aware AI Music</span>
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-indigo-950 text-indigo-200 border border-indigo-800">
                Ch 9
              </span>
            </button>
          </div>
        </div>

        {/* Header Right: Keyboard hint & Close */}
        <div className="flex items-center gap-3 text-xs text-zinc-400">
          <span className="hidden md:inline text-[11px] bg-zinc-900 px-2 py-1 rounded border border-zinc-800 font-mono text-zinc-400">
            [Space] Play/Pause
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 transition-colors"
              title="Close Audio Library"
            >
              ✕
            </button>
          )}
        </div>
      </header>

      {/* Workspace Body */}
      {activeWorkspace === "ai_generator" ? (
        <AIMusicStudio
          projectId={projectId}
          onSendToTimeline={onSendToTimeline}
          onSaveToLibrary={(newAsset) => setAssets((prev) => [newAsset, ...prev])}
        />
      ) : (
        /* 3-Section Catalog Workspace Body */
        <div className="flex-1 flex min-h-0 overflow-hidden">
          {/* Left: Category Navigation */}
          <AudioCategoryNav
            filter={filter}
            onUpdateFilter={(updates) => setFilter((prev) => ({ ...prev, ...updates }))}
            assets={assets}
          />

          {/* Center: Audio Asset Browser */}
          <AudioAssetBrowser
            assets={assets}
            filter={filter}
            onUpdateFilter={(updates) => setFilter((prev) => ({ ...prev, ...updates }))}
            selectedAssetId={activeSelectedId}
            onSelectAsset={handleSelectAsset}
            onToggleFavorite={handleToggleFavorite}
            previewState={previewState}
            onTogglePlay={handleTogglePlay}
            onQuickSendToTimeline={handleQuickSend}
          />

          {/* Right: Audio Inspector */}
          <AudioInspector
            asset={selectedAsset}
            previewState={previewState}
            onTogglePlay={handleTogglePlay}
            onStop={handleStop}
            onSeek={handleSeek}
            onChangeVolume={handleChangeVolume}
            onToggleMute={handleToggleMute}
            onToggleFavorite={handleToggleFavorite}
            onSendToTimeline={onSendToTimeline}
          />
        </div>
      )}
    </div>
  );
};
export default AudioLibrary;
