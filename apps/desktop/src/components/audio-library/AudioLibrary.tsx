import React, { useState, useEffect, useRef, useCallback } from "react";
import type {
  AudioAsset,
  AudioCategory,
  AudioFilterState,
  AudioLicenseType,
  AudioPreviewState,
  AudioToTimelineContract,
  AudioLibraryProps,
} from "./AudioLibrary.types.ts";
import { MOCK_AUDIO_ASSETS } from "./AudioLibrary.mock.ts";
import { AudioCategoryNav } from "./AudioCategoryNav.tsx";
import { AudioAssetBrowser } from "./AudioAssetBrowser.tsx";
import { AudioInspector } from "./AudioInspector.tsx";
import { Icons } from "@panelflow/ui";
import { AIMusicStudio } from "./AIMusicStudio.tsx";
import { api } from "@panelflow/api-client";

const FAVORITES_STORAGE_KEY = "panelflow_audio_favorites";

function toAudioLicenseType(rawLicense: string): AudioLicenseType {
  const upper = (rawLicense || "").toUpperCase();
  if (upper.includes("CC0") || upper.includes("PUBLIC DOMAIN")) return "Public Domain (CC0)";
  if (upper.includes("BY") || upper.includes("ATTRIBUTION")) return "Creative Commons CC-BY 4.0";
  if (upper.includes("USER")) return "User-Supplied";
  if (upper.includes("BUILT-IN") || upper.includes("PANELFLOW")) return "PanelFlow Built-in Royalty-Free";
  return "Custom Commercial License";
}

function categorizeSound(name: string, isMusic: boolean): AudioCategory {
  const l = name.toLowerCase();
  if (isMusic) {
    if (l.includes("action") || l.includes("fight") || l.includes("battle") || l.includes("rock")) return "action";
    if (l.includes("suspense") || l.includes("dark") || l.includes("drone") || l.includes("tension")) return "suspense";
    if (l.includes("emotional") || l.includes("sad") || l.includes("piano") || l.includes("drama")) return "emotional";
    if (l.includes("fantasy") || l.includes("magic") || l.includes("fairy")) return "fantasy";
    if (l.includes("ambient") || l.includes("pad") || l.includes("atmosphere")) return "ambient";
    return "cinematic";
  }
  if (l.includes("wind") || l.includes("rain") || l.includes("thunder") || l.includes("forest") || l.includes("nature") || l.includes("weather")) return "environmental";
  if (l.includes("whoosh") || l.includes("swoosh") || l.includes("transition") || l.includes("rise") || l.includes("sweep")) return "transitions";
  if (l.includes("magic") || l.includes("spell") || l.includes("laser") || l.includes("energy") || l.includes("explosion") || l.includes("blast")) return "magic_fx";
  return "character";
}

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

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // File upload handler
  const handleFileUpload = useCallback(async (files: FileList | File[]) => {
    setIsUploading(true);
    const newLiveAssets: AudioAsset[] = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (!file.name.match(/\.(wav|mp3|flac|ogg|m4a|aac)$/i)) continue;
        const uploaded = await api.uploadAudioLibraryFile(file);
        const ext = (uploaded.name.slice(uploaded.name.lastIndexOf(".") + 1).toLowerCase() || "wav") as any;
        const isMusic = uploaded.name.toLowerCase().includes("bgm") || uploaded.name.toLowerCase().includes("music");
        const asset: AudioAsset = {
          id: `local_up_${Date.now()}_${uploaded.name.replace(/[^a-zA-Z0-9_-]/g, "_")}`,
          name: uploaded.name.replace(/\.[^/.]+$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
          type: isMusic ? "music" : "sfx",
          category: categorizeSound(uploaded.name, isMusic),
          duration_sec: 2.5,
          file_format: ext,
          file_url: `http://127.0.0.1:8765/api/audio/studio/stream?path=${encodeURIComponent(uploaded.path)}`,
          file_size_bytes: uploaded.size,
          sample_rate_hz: 48000,
          channels: "Stereo",
          tags: ["Local", "User Sound", isMusic ? "Music" : "SFX"],
          availability: "AVAILABLE",
          is_favorite: false,
          description: `Imported audio asset: ${uploaded.name}`,
          loopable: false,
          license: {
            license_type: "User-Supplied",
            author_or_source: "Local User Library",
            attribution_required: false,
            commercial_use_allowed: true,
          },
          recommended_timeline_track: isMusic ? "BGM" : "SFX",
          measured_peaks: [0.1, 0.4, 0.7, 0.5, 0.2],
          created_at: new Date().toISOString(),
        };
        newLiveAssets.push(asset);
      }
      if (newLiveAssets.length > 0) {
        setAssets((prev) => [...newLiveAssets, ...prev]);
        setInternalSelectedId(newLiveAssets[0].id);
      }
    } catch (err) {
      console.error("Failed to upload audio file:", err);
    } finally {
      setIsUploading(false);
    }
  }, []);

  // Load real backend audio assets from /api/audio/studio/library/files
  useEffect(() => {
    let active = true;
    async function fetchBackendAssets() {
      try {
        const files = await api.listAudioLibraryFiles();
        if (!active || !files || files.length === 0) return;

        const liveAssets: AudioAsset[] = files.map((f, idx) => {
          const ext = (f.name.slice(f.name.lastIndexOf(".") + 1).toLowerCase() || "wav") as any;
          const lower = f.name.toLowerCase();
          const isMusic = lower.includes("bgm") || lower.includes("music") || lower.includes("theme");
          const streamUrl = `http://127.0.0.1:8765/api/audio/studio/stream?path=${encodeURIComponent(f.path)}`;
          return {
            id: `local_${idx}_${f.name.replace(/[^a-zA-Z0-9_-]/g, "_")}`,
            name: f.name.replace(/\.[^/.]+$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
            type: isMusic ? "music" : "sfx",
            category: categorizeSound(f.name, isMusic),
            duration_sec: 2.5,
            file_format: ext,
            file_url: streamUrl,
            file_size_bytes: f.size,
            sample_rate_hz: 48000,
            channels: "Stereo",
            tags: ["Local", "User Sound", isMusic ? "Music" : "SFX"],
            availability: "AVAILABLE",
            is_favorite: false,
            description: `Imported audio asset: ${f.name}`,
            loopable: false,
            license: {
              license_type: "User-Supplied",
              author_or_source: "Local User Library",
              attribution_required: false,
              commercial_use_allowed: true,
            },
            recommended_timeline_track: isMusic ? "BGM" : "SFX",
            measured_peaks: [0.1, 0.3, 0.6, 0.8, 0.5, 0.2],
            created_at: new Date().toISOString(),
          };
        });

        setAssets((prev) => {
          const liveIds = new Set(liveAssets.map((a) => a.id));
          const filtered = prev.filter((p) => !liveIds.has(p.id));
          return [...liveAssets, ...filtered];
        });
      } catch (e) {
        // Fallback to baseAssets if backend is offline
      }
    }
    fetchBackendAssets();
    return () => { active = false; };
  }, []);

  // Dynamic search against backend catalog when query changes
  useEffect(() => {
    const q = filter.search_query.trim();
    if (q.length < 3) return;

    let active = true;
    const timeout = setTimeout(async () => {
      try {
        const results = await api.searchAudioCatalog(q, filter.selected_type === "music" ? "music" : "sfx");
        if (!active || !results || results.length === 0) return;

        const searchedAssets: AudioAsset[] = results.map((r) => {
          const isMusic = r.type === "music";
          return {
            id: `search_${r.id}`,
            name: r.name || "Sound Effect",
            type: (isMusic ? "music" : "sfx") as "music" | "sfx",
            category: categorizeSound(r.name || "", isMusic),
            duration_sec: r.duration_sec || 2.0,
            file_format: "wav",
            file_url: r.file_url.startsWith("http") ? r.file_url : `http://127.0.0.1:8765${r.file_url}`,
            file_size_bytes: 120000,
            sample_rate_hz: 48000,
            channels: "Stereo",
            tags: ["Search", r.source, r.license],
            availability: "AVAILABLE",
            is_favorite: false,
            description: `${r.name} from ${r.source} (${r.license})`,
            loopable: false,
            license: {
              license_type: toAudioLicenseType(r.license),
              author_or_source: r.source,
              attribution_required: r.license.toUpperCase().includes("BY"),
              commercial_use_allowed: true,
            },
            recommended_timeline_track: isMusic ? "BGM" : "SFX",
            measured_peaks: [0.2, 0.5, 0.8, 0.6, 0.3],
            created_at: new Date().toISOString(),
          };
        });

        setAssets((prev) => {
          const newIds = new Set(searchedAssets.map((a) => a.id));
          return [...searchedAssets, ...prev.filter((p) => !newIds.has(p.id))];
        });
      } catch (err) {
        // fallback
      }
    }, 350);

    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [filter.search_query, filter.selected_type]);

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
      className="relative flex flex-col h-full w-full bg-ink text-fg select-none overflow-hidden font-sans"
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          handleFileUpload(e.dataTransfer.files);
        }
      }}
    >
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-ink/90 border-2 border-dashed border-accent flex flex-col items-center justify-center pointer-events-none backdrop-blur-sm">
          <div className="w-14 h-14 rounded-2xl bg-accent/20 text-accent flex items-center justify-center mb-3 animate-pulse">
            <Icons.Headphones className="w-7 h-7" />
          </div>
          <p className="text-base font-bold text-white">Drop audio files to import into library</p>
          <p className="text-xs text-fg-dim mt-1.5 font-mono">Supports .wav, .mp3, .flac, .ogg, .m4a</p>
        </div>
      )}

      {/* Top Application Bar */}
      <header className="h-12 border-b border-edge bg-ink flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-accent/20 text-info border border-accent/40 flex items-center justify-center font-bold text-sm shadow-sm">
              <Icons.Headphones className="w-4 h-4" />
            </div>
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
              <span>PanelFlow Audio Studio</span>
            </h1>
          </div>

          {/* Workspace Tabs: Catalog vs AI Music Studio */}
          <div className="flex items-center bg-navy border border-edge rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setActiveWorkspace("catalog")}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                activeWorkspace === "catalog"
                  ? "bg-flat text-white shadow-sm"
                  : "text-fg-dim hover:text-fg"
              }`}
            >
              Library Catalog
            </button>
            <button
              type="button"
              onClick={() => setActiveWorkspace("ai_generator")}
              className={`px-3 py-1 text-xs font-semibold rounded-md flex items-center gap-1.5 transition-colors ${
                activeWorkspace === "ai_generator"
                  ? "bg-accent text-white shadow-sm"
                  : "text-fg-dim hover:text-fg"
              }`}
            >
              <Icons.Sparkles className="w-3.5 h-3.5" />
              <span>Story-Aware AI Music</span>
              <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-accent/20 text-info border border-accent/40">
                Ch 9
              </span>
            </button>
          </div>
        </div>

        {/* Header Right: Import, Keyboard hint & Close */}
        <div className="flex items-center gap-3 text-xs text-fg-dim">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md bg-navy hover:bg-flat border border-edge text-fg transition-colors disabled:opacity-50"
            title="Import WAV/MP3 sound files to local library"
          >
            <Icons.Plus className="w-3.5 h-3.5 text-accent" />
            <span>{isUploading ? "Importing..." : "Import Sound"}</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".wav,.mp3,.flac,.ogg,.m4a,.aac,audio/*"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                handleFileUpload(e.target.files);
                e.target.value = "";
              }
            }}
          />
          <span className="hidden md:inline text-[11px] bg-navy px-2 py-1 rounded border border-edge font-mono text-fg-dim">
            [Space] Play/Pause
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-flat text-fg-dim hover:text-fg transition-colors"
              title="Close Audio Library"
            >
              <Icons.X className="w-4 h-4" />
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
