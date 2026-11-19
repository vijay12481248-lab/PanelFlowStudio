import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  X,
  Sparkles,
  Wand2,
  Eye,
  CheckCircle2,
  AlertCircle,
  Play,
  Pause,
  RotateCcw,
  Loader2,
  ShieldCheck,
  Video,
  Upload,
  FileVideo,
  Film,
  Download,
  FolderOpen,
  Volume2,
  VolumeX,
  Save,
} from "lucide-react";

export interface WatermarkBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WatermarkRemoverModalProps {
  isOpen: boolean;
  onClose: () => void;
  videoPath?: string;
  projectId?: string;
  onComplete?: (outputPath: string) => void;
}

type WatermarkMode = "auto" | "inverse_alpha" | "flow_guided";

interface DetectionCandidate {
  box: WatermarkBox;
  confidence: number;
  detection_type: string;
  sample_frame_sec: number;
  label?: string;
}

interface PreviewResult {
  original_frame_base64: string;
  preview_frame_base64: string;
  mask_frame_base64: string;
  box: WatermarkBox;
  mode_used: string;
  time_sec: number;
}

const ENGINE = "http://127.0.0.1:8765";

export const WatermarkRemoverModal: React.FC<WatermarkRemoverModalProps> = ({
  isOpen,
  onClose,
  videoPath: initialVideoPath,
  projectId = "default",
  onComplete,
}) => {
  const [token, setToken] = useState<string>("");
  const [currentVideoPath, setCurrentVideoPath] = useState<string>("");
  const [videoSrc, setVideoSrc] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  // Playback & Frame sync
  const [duration, setDuration] = useState<number>(0);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [videoDimensions, setVideoDimensions] = useState<{ width: number; height: number }>({ width: 0, height: 0 });

  // Watermark parameters
  const [mode, setMode] = useState<WatermarkMode>("auto");
  const [featherPx, setFeatherPx] = useState<number>(3);
  const [box, setBox] = useState<WatermarkBox | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);

  // Detection & Preview
  const [isDetecting, setIsDetecting] = useState(false);
  const [candidates, setCandidates] = useState<DetectionCandidate[]>([]);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewResult | null>(null);
  const [previewTab, setPreviewTab] = useState<"compare" | "cleaned" | "original" | "mask">("compare");

  // Job Execution
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [jobMessage, setJobMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [finishedOutput, setFinishedOutput] = useState<string | null>(null);

  // Save Modal Dialog
  const [showSaveDialog, setShowSaveDialog] = useState<boolean>(false);
  const [saveDirectory, setSaveDirectory] = useState<string>("");
  const [saveFilename, setSaveFilename] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch token from storage
  useEffect(() => {
    try {
      const stored = localStorage.getItem("panelflow_engine_token") || "";
      if (stored) setToken(stored);
    } catch {}
  }, []);

  const headers = useCallback(() => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["X-PanelFlow-Token"] = token;
    return h;
  }, [token]);

  // Format seconds to mm:ss.f
  const formatTime = (secs: number) => {
    if (isNaN(secs) || secs < 0) return "0:00.0";
    const m = Math.floor(secs / 60);
    const s = (secs % 60).toFixed(1);
    return `${m}:${s.padStart(4, "0")}`;
  };

  // Upload a dropped or selected File to engine
  const uploadAndLoadFile = async (file: File) => {
    if (!file || (!file.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|avi)$/i.test(file.name))) {
      setErrorMessage("Please drop or select a valid video file (.mp4, .mov, .mkv, .webm).");
      return;
    }

    setErrorMessage(null);
    setFileName(file.name);
    setFinishedOutput(null);
    setPreviewData(null);
    setBox(null);
    setCandidates([]);
    setShowSaveDialog(false);
    setSaveSuccessMsg(null);

    // Create instant local blob URL for smooth native playback
    const localBlob = URL.createObjectURL(file);
    setVideoSrc(localBlob);

    // Upload to engine so server has absolute path on disk
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${ENGINE}/api/video/watermark/upload`, {
        method: "POST",
        headers: token ? { "X-PanelFlow-Token": token } : {},
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to upload video to engine");
      }
      const data = await res.json();
      setCurrentVideoPath(data.video_path);
    } catch (err: any) {
      console.warn("Upload notice:", err);
      setErrorMessage("Warning: Could not upload video to engine. Local preview is active.");
    } finally {
      setIsUploading(false);
    }
  };

  // Initialize or reset on open
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setFinishedOutput(null);
      setPreviewData(null);
      setBox(null);
      setCandidates([]);
      setIsProcessing(false);
      setJobId(null);
      setJobProgress(0);
      setShowSaveDialog(false);
      setSaveSuccessMsg(null);

      // If a valid path is passed from props
      if (initialVideoPath && !initialVideoPath.includes("sample.mp4") && /\.(mp4|mov|mkv|webm|avi)$/i.test(initialVideoPath)) {
        setCurrentVideoPath(initialVideoPath);
        const name = initialVideoPath.replace(/\\/g, "/").split("/").pop() || "Video";
        setFileName(name);
        const streamUrl = `${ENGINE}/api/video/watermark/stream?path=${encodeURIComponent(initialVideoPath)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
        setVideoSrc(streamUrl);
      } else {
        setCurrentVideoPath("");
        setVideoSrc("");
        setFileName("");
      }
    }
  }, [isOpen, initialVideoPath, token]);

  // Video element metadata loader
  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (!video) return;
    setDuration(video.duration || 0);
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 360;
    setVideoDimensions({ width: w, height: h });
  };

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime || 0);
  };

  // Play / Pause toggle with reliable browser handling
  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      if (video.currentTime >= (video.duration || 1) - 0.1) {
        video.currentTime = 0;
      }
      video
        .play()
        .then(() => setIsPlaying(true))
        .catch((err) => {
          console.warn("Direct play notice:", err);
          video.muted = true;
          setIsMuted(true);
          video.play().then(() => setIsPlaying(true)).catch(() => {});
        });
    } else {
      video.pause();
      setIsPlaying(false);
    }
  };

  // Toggle Mute
  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setIsMuted(video.muted);
  };

  // Scrub slider change
  const handleScrub = (newTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = newTime;
    setCurrentTime(newTime);
  };

  // Keyboard shortcut: space to play/pause
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isPlaying]);

  // Drag and drop handlers on modal container
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadAndLoadFile(e.dataTransfer.files[0]);
    }
  };

  // Preset positioning for common corners
  const applyPresetBox = (corner: "top-right" | "top-left" | "bottom-right" | "bottom-left" | "clear") => {
    if (corner === "clear") {
      setBox(null);
      return;
    }
    const w = videoDimensions.width || 640;
    const h = videoDimensions.height || 360;
    const boxW = Math.round(w * 0.22);
    const boxH = Math.round(h * 0.12);

    switch (corner) {
      case "top-right":
        setBox({ x: Math.round(w * 0.74), y: Math.round(h * 0.04), width: boxW, height: boxH });
        break;
      case "top-left":
        setBox({ x: Math.round(w * 0.04), y: Math.round(h * 0.04), width: boxW, height: boxH });
        break;
      case "bottom-right":
        setBox({ x: Math.round(w * 0.74), y: Math.round(h * 0.84), width: boxW, height: boxH });
        break;
      case "bottom-left":
        setBox({ x: Math.round(w * 0.04), y: Math.round(h * 0.84), width: boxW, height: boxH });
        break;
    }
  };

  // Mouse handlers for interactive bounding box selection directly mapped to video
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!overlayRef.current) return;
    const rect = overlayRef.current.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    const scaleX = (videoDimensions.width || 640) / rect.width;
    const scaleY = (videoDimensions.height || 360) / rect.height;

    const clickX = Math.round((e.clientX - rect.left) * scaleX);
    const clickY = Math.round((e.clientY - rect.top) * scaleY);

    setDragStart({ x: clickX, y: clickY });
    setDragCurrent({ x: clickX, y: clickY });
    setIsDrawing(true);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !dragStart || !overlayRef.current) return;
    const rect = overlayRef.current.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    const scaleX = (videoDimensions.width || 640) / rect.width;
    const scaleY = (videoDimensions.height || 360) / rect.height;

    const currX = Math.round((e.clientX - rect.left) * scaleX);
    const currY = Math.round((e.clientY - rect.top) * scaleY);

    setDragCurrent({ x: currX, y: currY });

    const x = Math.max(0, Math.min(dragStart.x, currX));
    const y = Math.max(0, Math.min(dragStart.y, currY));
    const w = Math.min((videoDimensions.width || 640) - x, Math.abs(currX - dragStart.x));
    const h = Math.min((videoDimensions.height || 360) - y, Math.abs(currY - dragStart.y));

    if (w > 4 && h > 4) {
      setBox({ x, y, width: w, height: h });
    }
  };

  const handleMouseUp = () => {
    setIsDrawing(false);
    setDragStart(null);
    setDragCurrent(null);
  };

  // Auto-detection using temporal variance
  const handleAutoDetect = async () => {
    if (!currentVideoPath) {
      setErrorMessage("No video loaded for auto-detection.");
      return;
    }
    setIsDetecting(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${ENGINE}/api/video/watermark/detect`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          video_path: currentVideoPath,
          num_samples: 80,
          max_candidates: 4,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Auto-detect request failed");
      }
      const data = await res.json();
      setCandidates(data.candidates || []);
      if (data.candidates && data.candidates.length > 0) {
        const top = data.candidates[0];
        setBox(top.box);
        if (top.sample_frame_sec !== undefined && videoRef.current) {
          videoRef.current.currentTime = top.sample_frame_sec;
          setCurrentTime(top.sample_frame_sec);
        }
      } else {
        setErrorMessage("No stationary logo detected automatically. Please drag a box manually.");
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to detect watermark");
    } finally {
      setIsDetecting(false);
    }
  };

  // Instant single-frame preview
  const handlePreview = async () => {
    if (!currentVideoPath || !box) {
      setErrorMessage("Please select a watermark region box to preview.");
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${ENGINE}/api/video/watermark/preview`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          video_path: currentVideoPath,
          box,
          mode,
          time_sec: currentTime || 1.0,
          feather_px: featherPx,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Preview failed");
      }
      const data = await res.json();
      setPreviewData(data);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to generate preview");
    } finally {
      setIsPreviewing(false);
    }
  };

  // Start watermark removal durable job
  const handleStartRemoval = async () => {
    if (!currentVideoPath || !box) {
      setErrorMessage("Please select a watermark region box before removing.");
      return;
    }
    setIsProcessing(true);
    setErrorMessage(null);
    setJobProgress(0);
    setJobMessage("Enqueuing watermark removal job...");
    setFinishedOutput(null);

    try {
      const res = await fetch(`${ENGINE}/api/video/watermark/remove`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          project_id: projectId,
          video_path: currentVideoPath,
          box,
          mode,
          feather_px: featherPx,
          use_gpu: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to enqueue watermark removal");
      }
      const data = await res.json();
      setJobId(data.job_id);
      setJobMessage("Inpainting video frames with zero blur...");
    } catch (err: any) {
      setErrorMessage(err.message || "Removal request failed");
      setIsProcessing(false);
    }
  };

  // Poll job status every 500ms
  useEffect(() => {
    if (!jobId || !isProcessing) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${ENGINE}/api/jobs/${jobId}`, {
          headers: headers(),
        });
        if (!res.ok) return;
        const job = await res.json();

        // Convert 0.0-1.0 float to 0-100%
        const rawProg = job.progress !== undefined ? job.progress : 0;
        const pct = Math.min(100, Math.max(0, rawProg <= 1.0 && rawProg > 0 ? Math.round(rawProg * 100) : Math.round(rawProg)));
        setJobProgress(pct);
        setJobMessage(job.message || (job.status === "RUNNING" ? `Inpainting video frames... (${pct}%)` : "Processing..."));

        if (job.status === "SUCCEEDED" || job.status === "COMPLETED") {
          setIsProcessing(false);
          const out = job.output?.output_path || "";
          setFinishedOutput(out);
          if (onComplete && out) onComplete(out);
          clearInterval(interval);
        } else if (job.status === "FAILED") {
          setIsProcessing(false);
          setErrorMessage(job.error || "Watermark removal job failed in engine");
          clearInterval(interval);
        }
      } catch (err) {
        console.warn("Failed to poll job status:", err);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [jobId, isProcessing, headers, onComplete]);

  // Play cleaned video directly
  const playCleanedVideo = () => {
    if (!finishedOutput) return;
    const streamUrl = `${ENGINE}/api/video/watermark/stream?path=${encodeURIComponent(finishedOutput)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
    setVideoSrc(streamUrl);
    setPreviewData(null);
    setBox(null);
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  // Save Video: open dialog & execute copy to destination
  const handleOpenSaveDialog = () => {
    if (!finishedOutput) return;
    const defName = finishedOutput.replace(/\\/g, "/").split("/").pop() || "cleaned_video.mp4";
    setSaveFilename(defName);
    // Default directory suggestion
    setSaveDirectory("C:\\Users\\user\\Videos");
    setShowSaveDialog(true);
    setSaveSuccessMsg(null);
  };

  const handleExecuteSave = async () => {
    if (!finishedOutput || !saveDirectory) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${ENGINE}/api/video/watermark/save-as`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          source_path: finishedOutput,
          target_directory: saveDirectory,
          target_filename: saveFilename || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to save file to directory");
      }
      const data = await res.json();
      setSaveSuccessMsg(`Saved to: ${data.saved_path}`);
      setTimeout(() => setShowSaveDialog(false), 2000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to save video");
    } finally {
      setIsSaving(false);
    }
  };

  // Native Browser Direct Download as immediate fallback
  const handleDirectDownload = () => {
    if (!finishedOutput) return;
    const streamUrl = `${ENGINE}/api/video/watermark/stream?path=${encodeURIComponent(finishedOutput)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
    const a = document.createElement("a");
    a.href = streamUrl;
    a.download = finishedOutput.replace(/\\/g, "/").split("/").pop() || "cleaned_video.mp4";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Open containing folder in Windows Explorer
  const handleOpenFolder = async () => {
    if (!finishedOutput) return;
    try {
      await fetch(`${ENGINE}/api/video/watermark/open-folder`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ path: finishedOutput }),
      });
    } catch (e) {
      console.warn("Could not reveal folder:", e);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in duration-200"
    >
      <input
        ref={fileInputRef}
        type="file"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            uploadAndLoadFile(e.target.files[0]);
          }
        }}
        accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/*"
        style={{ display: "none" }}
      />

      <div
        className={`bg-[#0d1430] border ${
          isDragOver ? "border-indigo-400 ring-4 ring-indigo-500/30" : "border-[#202c60]"
        } rounded-2xl w-full max-w-5xl overflow-hidden shadow-2xl flex flex-col max-h-[94vh] transition-all`}
      >
        {/* Header */}
        <div className="px-6 py-3.5 border-b border-[#1a2550] flex items-center justify-between bg-[#080d24]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  AI Watermark Remover
                </h2>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px] font-semibold flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> Zero Blur & Authentic Pixels
                </span>
              </div>
              <p className="text-xs text-[#8ca2dc]">
                Reconstructs background behind watermarks with zero blur using Navier-Stokes isophotes and algebraic backdrop inversion.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-[#141d42] hover:bg-[#1f2b60] text-[#8ca2dc] hover:text-white flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body: Two Columns */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Video Stage & Interactive Overlay (8 cols) */}
          <div className="lg:col-span-8 space-y-3 flex flex-col">
            {/* Top file indicator */}
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2 text-xs text-[#8ca2dc] truncate max-w-md">
                <Film className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                <span className="font-medium text-white truncate">
                  {fileName || "No video loaded"}
                </span>
                {videoDimensions.width > 0 && (
                  <span className="text-[#6375a6] font-mono text-[11px]">
                    ({videoDimensions.width}×{videoDimensions.height})
                  </span>
                )}
                {isUploading && (
                  <span className="text-amber-400 text-[11px] flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Uploading...
                  </span>
                )}
              </div>

              {box ? (
                <span className="text-emerald-400 text-xs font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  Target: [{box.x}, {box.y}, {box.width}×{box.height}]
                </span>
              ) : (
                <span className="text-[#6375a6] text-[11px]">
                  {videoSrc ? "" : "Drop video to start"}
                </span>
              )}
            </div>

            {/* Viewport: Interactive Native Video with Hardware Acceleration OR Preview Mode */}
            <div className="relative bg-black rounded-xl overflow-hidden border border-[#1e2a58] aspect-video max-h-[460px] flex items-center justify-center">
              {previewData ? (
                /* Preview Frame View */
                <div className="w-full h-full flex flex-col bg-[#080d24]">
                  <div className="flex items-center justify-between px-3 py-1.5 bg-[#0e163d] border-b border-[#1e2b60]">
                    <span className="text-[11px] font-semibold text-[#8ca2dc]">
                      Single-Frame Preview at {previewData.time_sec}s ({previewData.mode_used})
                    </span>
                    <div className="flex gap-1">
                      {(["compare", "cleaned", "original", "mask"] as const).map((tab) => (
                        <button
                          key={tab}
                          onClick={() => setPreviewTab(tab)}
                          className={`px-2.5 py-0.5 rounded text-[11px] font-semibold capitalize transition-colors ${
                            previewTab === tab
                              ? "bg-indigo-600 text-white"
                              : "bg-[#16214d] text-[#8aa0d6] hover:text-white"
                          }`}
                        >
                          {tab}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex-1 relative flex items-center justify-center bg-black p-2 overflow-hidden">
                    {previewTab === "compare" && (
                      <div className="grid grid-cols-2 gap-2 w-full h-full">
                        <div className="relative flex flex-col items-center justify-center border border-[#233166] rounded-lg overflow-hidden bg-neutral-950">
                          <img
                            src={`data:image/jpeg;base64,${previewData.original_frame_base64}`}
                            alt="Original"
                            className="max-h-full object-contain"
                          />
                          <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/75 text-[10px] text-neutral-300 border border-neutral-700">
                            Original (Watermarked)
                          </span>
                        </div>
                        <div className="relative flex flex-col items-center justify-center border border-emerald-500/40 rounded-lg overflow-hidden bg-neutral-950">
                          <img
                            src={`data:image/jpeg;base64,${previewData.preview_frame_base64}`}
                            alt="Cleaned"
                            className="max-h-full object-contain"
                          />
                          <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-emerald-950/85 text-[10px] text-emerald-300 border border-emerald-500/50">
                            Cleaned (Retained Authentic Pixels)
                          </span>
                        </div>
                      </div>
                    )}
                    {previewTab === "cleaned" && (
                      <img
                        src={`data:image/jpeg;base64,${previewData.preview_frame_base64}`}
                        alt="Cleaned Frame"
                        className="max-h-full object-contain"
                      />
                    )}
                    {previewTab === "original" && (
                      <img
                        src={`data:image/jpeg;base64,${previewData.original_frame_base64}`}
                        alt="Original Frame"
                        className="max-h-full object-contain"
                      />
                    )}
                    {previewTab === "mask" && (
                      <img
                        src={`data:image/png;base64,${previewData.mask_frame_base64}`}
                        alt="Mask"
                        className="max-h-full object-contain"
                      />
                    )}
                  </div>
                </div>
              ) : videoSrc ? (
                /* Native Hardware-Accelerated Video with Interactive Selection Layer (NO obscuring banners on top) */
                <div
                  className="relative max-w-full max-h-full flex items-center justify-center cursor-pointer"
                  onClick={togglePlay}
                  style={{
                    aspectRatio:
                      videoDimensions.width && videoDimensions.height
                        ? `${videoDimensions.width} / ${videoDimensions.height}`
                        : undefined,
                  }}
                >
                  <video
                    ref={videoRef}
                    src={videoSrc}
                    playsInline
                    controls={false}
                    muted={isMuted}
                    onLoadedMetadata={handleLoadedMetadata}
                    onTimeUpdate={handleTimeUpdate}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    onEnded={() => setIsPlaying(false)}
                    className="w-full h-full object-contain pointer-events-none select-none"
                  />

                  {/* Interactive Bounding Box Selection Layer */}
                  <div
                    ref={overlayRef}
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                    className="absolute inset-0 cursor-crosshair z-10 select-none"
                  >
                    {/* Bounding box visual overlay */}
                    {box && videoDimensions.width > 0 && (
                      <div
                        className="absolute border-2 border-dashed border-red-500 bg-red-500/25 pointer-events-none rounded transition-all shadow-[0_0_8px_rgba(239,68,68,0.4)]"
                        style={{
                          left: `${(box.x / videoDimensions.width) * 100}%`,
                          top: `${(box.y / videoDimensions.height) * 100}%`,
                          width: `${(box.width / videoDimensions.width) * 100}%`,
                          height: `${(box.height / videoDimensions.height) * 100}%`,
                        }}
                      >
                        <span className="absolute -top-5 left-0 px-1.5 py-0.2 rounded bg-red-600 text-[10px] text-white font-mono shadow whitespace-nowrap">
                          Target [{box.x}, {box.y}, {box.width}×{box.height}]
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* Empty Video Drop Area (only shown when no video is loaded) */
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center justify-center gap-3 p-8 border-2 border-dashed border-[#233166] hover:border-indigo-500/60 rounded-2xl cursor-pointer text-[#8ca2dc] transition-all hover:bg-indigo-500/5"
                >
                  <Upload className="w-10 h-10 text-indigo-400 opacity-80" />
                  <div className="text-center">
                    <p className="font-semibold text-white text-sm">
                      Drop a video file here or click to browse
                    </p>
                    <p className="text-xs text-[#6375a6] mt-0.5">
                      Supports MP4, MOV, MKV, WebM
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Video Timeline & Transport Controls */}
            <div className="p-2.5 bg-[#090f2b] border border-[#1b2756] rounded-xl flex items-center gap-3">
              <button
                type="button"
                onClick={togglePlay}
                disabled={!videoSrc}
                className="w-8 h-8 rounded-lg bg-[#141e47] hover:bg-[#1d2a63] disabled:opacity-40 text-white flex items-center justify-center transition-colors"
                title={isPlaying ? "Pause (Space)" : "Play (Space)"}
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </button>

              <button
                type="button"
                onClick={toggleMute}
                disabled={!videoSrc}
                className="w-8 h-8 rounded-lg bg-[#141e47] hover:bg-[#1d2a63] disabled:opacity-40 text-white flex items-center justify-center transition-colors"
                title={isMuted ? "Unmute" : "Mute"}
              >
                {isMuted ? <VolumeX className="w-4 h-4 text-amber-400" /> : <Volume2 className="w-4 h-4" />}
              </button>

              <input
                type="range"
                min="0"
                max={duration || 10}
                step="0.05"
                value={currentTime}
                disabled={!videoSrc}
                onChange={(e) => handleScrub(parseFloat(e.target.value))}
                className="flex-1 accent-indigo-500 h-1.5 bg-[#17224f] rounded-lg cursor-pointer disabled:opacity-40"
              />

              <span className="text-[11px] font-mono text-[#8aa0d6] shrink-0">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>

            {/* Quick Box Corner Presets */}
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className="text-[#6d7fae] font-semibold text-[11px] mr-1">
                Quick Corner Presets:
              </span>
              <button
                type="button"
                onClick={() => applyPresetBox("bottom-right")}
                disabled={!videoSrc}
                className="px-2.5 py-1 rounded-lg bg-[#11193f] hover:bg-[#1b275e] text-[#8ca2dc] hover:text-white border border-[#1f2b60] text-[11px] transition-colors"
              >
                Bottom-Right (Common Bug)
              </button>
              <button
                type="button"
                onClick={() => applyPresetBox("top-right")}
                disabled={!videoSrc}
                className="px-2.5 py-1 rounded-lg bg-[#11193f] hover:bg-[#1b275e] text-[#8ca2dc] hover:text-white border border-[#1f2b60] text-[11px] transition-colors"
              >
                Top-Right
              </button>
              <button
                type="button"
                onClick={() => applyPresetBox("bottom-left")}
                disabled={!videoSrc}
                className="px-2.5 py-1 rounded-lg bg-[#11193f] hover:bg-[#1b275e] text-[#8ca2dc] hover:text-white border border-[#1f2b60] text-[11px] transition-colors"
              >
                Bottom-Left
              </button>
              <button
                type="button"
                onClick={() => applyPresetBox("top-left")}
                disabled={!videoSrc}
                className="px-2.5 py-1 rounded-lg bg-[#11193f] hover:bg-[#1b275e] text-[#8ca2dc] hover:text-white border border-[#1f2b60] text-[11px] transition-colors"
              >
                Top-Left
              </button>
              {box && (
                <button
                  type="button"
                  onClick={() => applyPresetBox("clear")}
                  className="px-2.5 py-1 rounded-lg bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-500/30 text-[11px] ml-auto transition-colors"
                >
                  Clear Box
                </button>
              )}
            </div>

            {/* Detected stationary overlays */}
            {candidates.length > 0 && (
              <div className="p-3 bg-[#0a1030] border border-[#1d295e] rounded-xl space-y-1.5">
                <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Stationary Logo Candidates Detected:
                </span>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {candidates.map((c, idx) => (
                    <button
                      key={idx}
                      onClick={() => setBox(c.box)}
                      className="p-2 rounded-lg bg-[#121c45] hover:bg-[#1c2a66] border border-[#21316b] text-left text-xs transition-colors flex items-center justify-between"
                    >
                      <span className="text-neutral-200 font-mono text-[11px]">
                        [{c.box.x}, {c.box.y}, {c.box.width}×{c.box.height}]
                      </span>
                      <span className="text-indigo-400 font-semibold text-[10px]">
                        {Math.round(c.confidence * 100)}% Match
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: AI Controls, Detection, and Job Execution (4 cols) */}
          <div className="lg:col-span-4 space-y-4 flex flex-col justify-between">
            <div className="space-y-4">
              {/* Algorithm selector */}
              <div className="p-3.5 bg-[#090f2b] border border-[#1b2756] rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-[#8ca2dc]">
                    Removal Algorithm
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] font-mono">
                    Zero Blur
                  </span>
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-start gap-2.5 p-2 rounded-lg bg-[#11193d] border border-[#1f2b60] cursor-pointer hover:bg-[#17224e] transition-colors">
                    <input
                      type="radio"
                      name="wm-mode"
                      value="auto"
                      checked={mode === "auto"}
                      onChange={() => setMode("auto")}
                      className="mt-0.5 accent-indigo-500"
                    />
                    <div>
                      <div className="text-xs font-bold text-white">Auto Inpaint</div>
                      <div className="text-[10px] text-[#7d90c2] leading-tight">
                        Algebraic backdrop inversion with Navier-Stokes isophote continuation (zero blur).
                      </div>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 p-2 rounded-lg bg-[#11193d] border border-[#1f2b60] cursor-pointer hover:bg-[#17224e] transition-colors">
                    <input
                      type="radio"
                      name="wm-mode"
                      value="inverse_alpha"
                      checked={mode === "inverse_alpha"}
                      onChange={() => setMode("inverse_alpha")}
                      className="mt-0.5 accent-indigo-500"
                    />
                    <div>
                      <div className="text-xs font-bold text-white">Inverse Alpha (Bug)</div>
                      <div className="text-[10px] text-[#7d90c2] leading-tight">
                        100% mathematical zero-blur recovery for translucent channel bugs & logos.
                      </div>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 p-2 rounded-lg bg-[#11193d] border border-[#1f2b60] cursor-pointer hover:bg-[#17224e] transition-colors">
                    <input
                      type="radio"
                      name="wm-mode"
                      value="flow_guided"
                      checked={mode === "flow_guided"}
                      onChange={() => setMode("flow_guided")}
                      className="mt-0.5 accent-indigo-500"
                    />
                    <div>
                      <div className="text-xs font-bold text-white">Flow-Guided AI</div>
                      <div className="text-[10px] text-[#7d90c2] leading-tight">
                        Warps authentic pixels from neighboring frames along motion vectors.
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Edge Feathering Slider */}
              <div className="p-3 bg-[#090f2b] border border-[#1b2756] rounded-xl space-y-1.5">
                <div className="flex justify-between text-xs font-semibold text-[#8ca2dc]">
                  <span>Edge Feathering</span>
                  <span className="text-indigo-400 font-mono">{featherPx}px</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="12"
                  step="1"
                  value={featherPx}
                  onChange={(e) => setFeatherPx(parseInt(e.target.value))}
                  className="w-full accent-indigo-500"
                />
                <p className="text-[10px] text-[#6d7fae] leading-tight">
                  Smoothly blends inpainting boundary into background video without hard seams.
                </p>
              </div>

              {/* Quick Actions (Auto-detect & Preview) */}
              <div className="p-3 bg-[#090f2b] border border-[#1b2756] rounded-xl flex flex-col justify-between gap-2">
                <span className="text-xs font-semibold text-[#8ca2dc]">AI Validation</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleAutoDetect}
                    disabled={!videoSrc || isDetecting || isProcessing}
                    className="flex-1 py-1.5 px-2 bg-[#121c45] hover:bg-[#1a2861] disabled:opacity-40 text-white border border-[#21316b] rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    {isDetecting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="w-3.5 h-3.5 text-indigo-400" />
                    )}
                    Auto-Detect
                  </button>

                  <button
                    type="button"
                    onClick={handlePreview}
                    disabled={!videoSrc || !box || isPreviewing || isProcessing}
                    className="flex-1 py-1.5 px-2 bg-[#121c45] hover:bg-[#1a2861] disabled:opacity-40 text-white border border-[#21316b] rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    {isPreviewing ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Eye className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    Preview Frame
                  </button>
                </div>
              </div>
            </div>

            {/* Processing Progress Bar */}
            {isProcessing && (
              <div className="p-4 bg-indigo-950/60 border border-indigo-500/50 rounded-xl space-y-2.5 shadow-lg">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-indigo-200 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                    {jobMessage || "Processing video frames..."}
                  </span>
                  <span className="font-mono text-indigo-300 font-bold text-sm">{jobProgress}%</span>
                </div>
                <div className="w-full bg-[#0a0f2b] rounded-full h-3 overflow-hidden border border-indigo-500/30">
                  <div
                    className="bg-gradient-to-r from-indigo-500 to-emerald-400 h-3 rounded-full transition-all duration-300 shadow-[0_0_10px_rgba(99,102,241,0.5)]"
                    style={{ width: `${Math.max(4, jobProgress)}%` }}
                  />
                </div>
                <p className="text-[11px] text-[#8ca2dc]">
                  Processing with GPU-accelerated motion guidance and backdrop algebraic inversion (zero blur).
                </p>
              </div>
            )}

            {/* Success Banner & Cleaned Video Action Suite */}
            {finishedOutput && (
              <div className="p-4 bg-emerald-950/50 border border-emerald-500/50 rounded-xl space-y-3 text-xs shadow-lg">
                <div className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-emerald-200 text-sm">
                      Watermark Removal Complete!
                    </div>
                    <div className="text-[11px] text-emerald-400/90 truncate">
                      Cleaned video ready: {finishedOutput.replace(/\\/g, "/").split("/").pop()}
                    </div>
                  </div>
                </div>

                {/* Primary Action Buttons (Stacked cleanly to prevent horizontal clipping) */}
                <div className="flex flex-col gap-2 pt-1">
                  <button
                    type="button"
                    onClick={playCleanedVideo}
                    className="w-full py-2.5 px-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold flex items-center justify-center gap-2 transition-colors shadow"
                  >
                    <Play className="w-4 h-4" /> Play Cleaned Video
                  </button>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleOpenSaveDialog}
                      className="flex-1 py-2 px-2.5 bg-[#142345] hover:bg-[#1d3260] text-emerald-300 hover:text-white border border-emerald-500/30 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors text-xs"
                    >
                      <Save className="w-3.5 h-3.5 text-emerald-400" /> Save Video...
                    </button>

                    <button
                      type="button"
                      onClick={handleOpenFolder}
                      className="py-2 px-2.5 bg-[#142345] hover:bg-[#1d3260] text-emerald-300 hover:text-white border border-emerald-500/30 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors text-xs"
                      title="Reveal in Windows Explorer"
                    >
                      <FolderOpen className="w-3.5 h-3.5 text-emerald-400" /> Reveal
                    </button>

                    <button
                      type="button"
                      onClick={handleDirectDownload}
                      className="py-2 px-2.5 bg-[#142345] hover:bg-[#1d3260] text-emerald-300 hover:text-white border border-emerald-500/30 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors text-xs"
                      title="Direct Browser Download"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-400" />
                    </button>
                  </div>
                </div>

                {/* Save Dialog Popup */}
                {showSaveDialog && (
                  <div className="p-3 bg-[#0a1128] border border-emerald-500/40 rounded-lg space-y-2.5 mt-2 animate-in fade-in duration-150">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-xs flex items-center gap-1.5">
                        <Save className="w-3.5 h-3.5 text-emerald-400" /> Select Save Location
                      </span>
                      <button
                        type="button"
                        onClick={() => setShowSaveDialog(false)}
                        className="text-neutral-400 hover:text-white"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div>
                      <label className="text-[10px] text-[#8ca2dc] block mb-1">Destination Directory:</label>
                      <input
                        type="text"
                        value={saveDirectory}
                        onChange={(e) => setSaveDirectory(e.target.value)}
                        placeholder="e.g. C:\Users\user\Videos or D:\Exports"
                        className="w-full px-2.5 py-1.5 bg-[#101b38] border border-[#233566] rounded text-white text-xs font-mono outline-none focus:border-emerald-400"
                      />
                      <div className="flex gap-1.5 mt-1.5">
                        <button
                          type="button"
                          onClick={() => setSaveDirectory("C:\\Users\\user\\Videos")}
                          className="px-2 py-0.5 rounded bg-[#17254d] hover:bg-[#203366] text-[10px] text-neutral-300 border border-[#293c6f]"
                        >
                          Videos
                        </button>
                        <button
                          type="button"
                          onClick={() => setSaveDirectory("C:\\Users\\user\\Desktop")}
                          className="px-2 py-0.5 rounded bg-[#17254d] hover:bg-[#203366] text-[10px] text-neutral-300 border border-[#293c6f]"
                        >
                          Desktop
                        </button>
                        <button
                          type="button"
                          onClick={() => setSaveDirectory("C:\\Users\\user\\Downloads")}
                          className="px-2 py-0.5 rounded bg-[#17254d] hover:bg-[#203366] text-[10px] text-neutral-300 border border-[#293c6f]"
                        >
                          Downloads
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="text-[10px] text-[#8ca2dc] block mb-1">File Name:</label>
                      <input
                        type="text"
                        value={saveFilename}
                        onChange={(e) => setSaveFilename(e.target.value)}
                        className="w-full px-2.5 py-1.5 bg-[#101b38] border border-[#233566] rounded text-white text-xs font-mono outline-none focus:border-emerald-400"
                      />
                    </div>

                    {saveSuccessMsg && (
                      <p className="text-[11px] text-emerald-400 font-semibold">{saveSuccessMsg}</p>
                    )}

                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleExecuteSave}
                        disabled={isSaving || !saveDirectory}
                        className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white rounded font-bold text-xs flex items-center justify-center gap-1.5 transition-colors"
                      >
                        {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        Save Now
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowSaveDialog(false)}
                        className="px-3 py-1.5 bg-[#17224f] hover:bg-[#202e68] text-neutral-300 rounded text-xs transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Error Message */}
            {errorMessage && (
              <div className="p-3 bg-red-950/40 border border-red-500/40 rounded-xl flex items-start gap-2 text-xs text-red-300">
                <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}

            {/* Bottom Primary Execution Button */}
            <div className="pt-2">
              <button
                type="button"
                onClick={handleStartRemoval}
                disabled={!videoSrc || !box || isProcessing}
                className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-xl font-bold flex items-center justify-center gap-2 text-sm shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:cursor-not-allowed"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Removing Watermark ({jobProgress}%)...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 text-indigo-300" />
                    <span>Remove Watermark (Zero Blur)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
