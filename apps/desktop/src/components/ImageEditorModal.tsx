import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@panelflow/api-client";
import type { GeneratedAsset } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import {
  Paintbrush,
  Eraser,
  Undo2,
  Redo2,
  Trash2,
  Eye,
  EyeOff,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Download,
  Copy,
  Check,
  Sparkles,
  Wand2,
  X,
  Sliders,
  RefreshCw,
  Layers,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

export type ImageEditorTarget =
  | { mode: 'project'; projectId: string; asset: GeneratedAsset; onAssetUpdated?: (newAsset: GeneratedAsset) => void }
  | { mode: 'story'; storySlug: string; episodeSlug?: string; panelId: string; imageSrc: string; onPanelUpdated?: (newImagePath: string) => void };

export interface ImageEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  target?: ImageEditorTarget;
  projectId?: string;
  asset?: GeneratedAsset | null;
  onAssetUpdated?: (newAsset: GeneratedAsset) => void;
}

type ToolMode = "brush" | "eraser";

interface InpaintPreset {
  label: string;
  prompt: string;
  icon: string;
}

const INPAINT_PRESETS: InpaintPreset[] = [
  { label: "Fix Hands & Fingers", prompt: "highly detailed realistic anime hands, perfect fingers, correct anatomy, clean lines", icon: "✋" },
  { label: "Change Outfit", prompt: "elaborate ornate dark assassin robes with silver trim, highly detailed fabric folds, elegant silhouette", icon: "👘" },
  { label: "Magical Aura", prompt: "intense glowing azure energy aura, crackling ethereal mana particles, dynamic lighting, cinematic", icon: "✨" },
  { label: "Enhance Face & Eyes", prompt: "striking detailed anime face, luminous expressive eyes, clean intricate facial features, masterpiece", icon: "👁️" },
  { label: "Mystical Blade", prompt: "holding a glowing translucent crystal dagger with golden runes, sharp gleaming edge, dynamic weapon", icon: "⚔️" },
  { label: "Remove / Clean Up", prompt: "seamless clean background matching the surrounding scene, flawless continuity, no artifacts", icon: "🧹" },
];

const MASK_COLORS = [
  { id: "rose", label: "Hot Rose", color: "rgba(242,102,122, 0.6)", hex: "#f2667a" },
  { id: "cyan", label: "Neon Cyan", color: "rgba(122,162,255, 0.6)", hex: "#7aa2ff" },
  { id: "amber", label: "Electric Gold", color: "rgba(240,179,90, 0.6)", hex: "#f0b35a" },
];

export const ImageEditorModal: React.FC<ImageEditorModalProps> = ({
  isOpen,
  onClose,
  target,
  projectId,
  asset,
  onAssetUpdated,
}) => {
  const effectiveTarget: ImageEditorTarget | null = useMemo(() => {
    if (target) return target;
    if (projectId && asset) {
      return { mode: 'project', projectId, asset, onAssetUpdated };
    }
    return null;
  }, [target, projectId, asset?.id, asset?.sha256, onAssetUpdated]);

  if (!isOpen || !effectiveTarget) return null;

  // Active asset / story image
  const [currentAsset, setCurrentAsset] = useState<GeneratedAsset | null>(
    effectiveTarget.mode === 'project' ? effectiveTarget.asset : null
  );
  const [previousAsset, setPreviousAsset] = useState<GeneratedAsset | null>(null);
  const [currentImageSrc, setCurrentImageSrc] = useState<string>(
    effectiveTarget.mode === 'story' ? effectiveTarget.imageSrc : ''
  );
  const [previousImageSrc, setPreviousImageSrc] = useState<string | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [imageNaturalSize, setImageNaturalSize] = useState<{ width: number; height: number }>({ width: 1024, height: 1024 });

  // Tool states
  const [tool, setTool] = useState<ToolMode>("brush");
  const [brushSize, setBrushSize] = useState<number>(40);
  const [brushOpacity, setBrushOpacity] = useState<number>(0.85);
  const [maskColorIndex, setMaskColorIndex] = useState<number>(0);
  const [showMask, setShowMask] = useState<boolean>(true);
  const [hasMaskContent, setHasMaskContent] = useState<boolean>(false);

  // Canvas zoom & view
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [fitMode, setFitMode] = useState<"contain" | "actual">("contain");

  // Inpaint parameters
  const [prompt, setPrompt] = useState<string>("");
  const [negativePrompt, setNegativePrompt] = useState<string>(
    "photorealism, 3D render, blurry, malformed hands, text, watermark, logo, gore"
  );
  const [seed, setSeed] = useState<number>(Math.floor(Math.random() * 900000000) + 100000000);
  const [isInpainting, setIsInpainting] = useState<boolean>(false);
  const [inpaintProgress, setInpaintProgress] = useState<number>(0);
  const [inpaintStatusText, setInpaintStatusText] = useState<string>("");
  const [inpaintError, setInpaintError] = useState<string | null>(null);

  // Micro-feedback state
  const [copiedSha, setCopiedSha] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Cursor state
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const [isCursorInside, setIsCursorInside] = useState<boolean>(false);

  // History stack for Undo / Redo
  const historyRef = useRef<ImageData[]>([]);
  const historyStepRef = useRef<number>(-1);

  // Canvas & Image refs
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const isDrawingRef = useRef<boolean>(false);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);

  // Track active session key to prevent wiping comparison history (Hold to Compare)
  // on subsequent renders or after an inpaint operation updates the active asset.
  const activeSessionKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isOpen || !effectiveTarget) {
      activeSessionKeyRef.current = null;
      return;
    }

    const sessionKey =
      effectiveTarget.mode === "story"
        ? `story:${effectiveTarget.storySlug}:${effectiveTarget.panelId}`
        : `project:${effectiveTarget.projectId}:${effectiveTarget.asset.id}`;

    // Already tracking this session; keep current inpaint/compare state
    if (activeSessionKeyRef.current === sessionKey) {
      return;
    }

    // When an inpaint operation finishes in project mode, currentAsset has already
    // been set to the newly created asset and previousAsset holds the pre-inpaint asset.
    if (
      effectiveTarget.mode === "project" &&
      currentAsset &&
      effectiveTarget.asset.id === currentAsset.id &&
      previousAsset
    ) {
      activeSessionKeyRef.current = sessionKey;
      return;
    }

    activeSessionKeyRef.current = sessionKey;
    if (effectiveTarget.mode === "story") {
      setCurrentImageSrc(effectiveTarget.imageSrc);
      setPreviousImageSrc(null);
    } else {
      setCurrentAsset(effectiveTarget.asset);
      setPreviousAsset(null);
    }
  }, [
    isOpen,
    effectiveTarget?.mode,
    effectiveTarget?.mode === "story"
      ? effectiveTarget.panelId
      : effectiveTarget?.mode === "project"
      ? effectiveTarget.asset.id
      : undefined,
  ]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 2500);
  };

  // Initialize and clear canvas when asset loads
  const initCanvas = useCallback(() => {
    const canvas = maskCanvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return;

    const w = img.naturalWidth || currentAsset?.width || 1024;
    const h = img.naturalHeight || currentAsset?.height || 1024;
    setImageNaturalSize({ width: w, height: h });
    canvas.width = w;
    canvas.height = h;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);

    // Save initial blank state
    const blankData = ctx.getImageData(0, 0, w, h);
    historyRef.current = [blankData];
    historyStepRef.current = 0;
    setHasMaskContent(false);
  }, [currentAsset]);

  const pushHistory = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Prune redo tree
    const newHistory = historyRef.current.slice(0, historyStepRef.current + 1);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    newHistory.push(data);
    if (newHistory.length > 25) newHistory.shift();

    historyRef.current = newHistory;
    historyStepRef.current = newHistory.length - 1;
    setHasMaskContent(true);
  };

  const handleUndo = () => {
    if (historyStepRef.current <= 0) return;
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    historyStepRef.current -= 1;
    const state = historyRef.current[historyStepRef.current];
    ctx.putImageData(state, 0, 0);
    setHasMaskContent(historyStepRef.current > 0);
  };

  const handleRedo = () => {
    if (historyStepRef.current >= historyRef.current.length - 1) return;
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    historyStepRef.current += 1;
    const state = historyRef.current[historyStepRef.current];
    ctx.putImageData(state, 0, 0);
    setHasMaskContent(true);
  };

  const handleClearMask = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pushHistory();
    setHasMaskContent(false);
    showToast("Mask cleared");
  };

  // Coordinate mapping from mouse event to canvas pixels
  const getCanvasCoordinates = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const drawStroke = (x1: number, y1: number, x2: number, y2: number) => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = brushSize;

    if (tool === "eraser") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = MASK_COLORS[maskColorIndex].color;
      ctx.globalAlpha = brushOpacity;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
    ctx.restore();
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    isDrawingRef.current = true;
    const pt = getCanvasCoordinates(e);
    lastPointRef.current = pt;
    drawStroke(pt.x, pt.y, pt.x, pt.y);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    // Track cursor location for preview ring
    const rect = e.currentTarget.getBoundingClientRect();
    setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });

    if (!isDrawingRef.current || !lastPointRef.current) return;
    const pt = getCanvasCoordinates(e);
    drawStroke(lastPointRef.current.x, lastPointRef.current.y, pt.x, pt.y);
    lastPointRef.current = pt;
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawingRef.current) return;
    isDrawingRef.current = false;
    lastPointRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // Ignored
    }
    pushHistory();
  };

  // Generate binary B&W mask for ComfyUI: Pure White (255) for painted pixels, Black (0) for background
  const exportBinaryMaskDataUrl = (): string | null => {
    const displayCanvas = maskCanvasRef.current;
    if (!displayCanvas) return null;

    const w = displayCanvas.width;
    const h = displayCanvas.height;
    const displayCtx = displayCanvas.getContext("2d");
    if (!displayCtx) return null;

    const imgData = displayCtx.getImageData(0, 0, w, h);
    const pixels = imgData.data;

    // Check if any pixel has mask alpha > 0
    let hasPainted = false;
    const binaryCanvas = document.createElement("canvas");
    binaryCanvas.width = w;
    binaryCanvas.height = h;
    const bCtx = binaryCanvas.getContext("2d")!;
    const binaryImgData = bCtx.createImageData(w, h);
    const bPixels = binaryImgData.data;

    for (let i = 0; i < pixels.length; i += 4) {
      const alpha = pixels[i + 3];
      if (alpha > 8) {
        hasPainted = true;
        // White = Inpaint region
        bPixels[i] = 255;
        bPixels[i + 1] = 255;
        bPixels[i + 2] = 255;
        bPixels[i + 3] = 255;
      } else {
        // Black = Preserve
        bPixels[i] = 0;
        bPixels[i + 1] = 0;
        bPixels[i + 2] = 0;
        bPixels[i + 3] = 255;
      }
    }

    if (!hasPainted) return null;

    bCtx.putImageData(binaryImgData, 0, 0);
    return binaryCanvas.toDataURL("image/png");
  };

  const handleInpaintSubmit = async () => {
    if (!prompt.trim()) {
      setInpaintError("Please enter an inpainting prompt describing what to draw.");
      return;
    }

    const maskData = exportBinaryMaskDataUrl();
    if (!maskData) {
      setInpaintError("No masked area selected. Brush over the region you want to inpaint first.");
      return;
    }

    setInpaintError(null);
    setIsInpainting(true);
    setInpaintProgress(0.05);

    try {
      if (effectiveTarget.mode === 'project') {
        setInpaintStatusText("Uploading image & mask to ComfyUI...");
        const activeAsset = currentAsset || effectiveTarget.asset;
        const queued = await api.inpaintComfyImage(effectiveTarget.projectId, {
          asset_id: activeAsset.id,
          mask_data: maskData,
          prompt: prompt.trim(),
          negative_prompt: negativePrompt.trim(),
          seed,
          timeout_s: 900,
        });

        setInpaintStatusText("ComfyUI inpainting with Qwen 2.1 Turbo...");

        const completedJob = await api.waitForWorkflowJob(queued.job_id, (job: Job) => {
          if (job.progress != null) setInpaintProgress(job.progress);
          if (job.message) setInpaintStatusText(job.message);
        });

        if (completedJob.status === "FAILED") {
          throw new Error(completedJob.error || "Inpainting job failed in engine.");
        }

        setInpaintStatusText("Retrieving newly generated asset...");
        setInpaintProgress(0.95);

        // Refresh project assets
        const assetList = await api.listGeneratedAssets(effectiveTarget.projectId);
        if (assetList.assets && assetList.assets.length > 0) {
          const newest = assetList.assets[0];
          setPreviousAsset(currentAsset || effectiveTarget.asset);
          setCurrentAsset(newest);
          if (effectiveTarget.onAssetUpdated) effectiveTarget.onAssetUpdated(newest);
          showToast("✨ Inpainting complete! New asset created.");
        }
      } else {
        setInpaintStatusText("Inpainting story panel with Qwen 2.1 inpaint workflow...");
        setInpaintProgress(0.3);
        const res = await api.inpaintOriginalPanel(effectiveTarget.storySlug, effectiveTarget.panelId, {
          mask_png_base64: maskData,
          prompt: prompt.trim(),
          negative_prompt: negativePrompt.trim(),
          seed,
          episode: effectiveTarget.episodeSlug,
        });
        setInpaintProgress(0.95);
        const updatedUrl = api.getOriginalPanelImageUrl(
          effectiveTarget.storySlug,
          effectiveTarget.panelId,
          effectiveTarget.episodeSlug,
        ) + `?t=${Date.now()}`;
        setPreviousImageSrc(currentImageSrc);
        setCurrentImageSrc(updatedUrl);
        if (effectiveTarget.onPanelUpdated) {
          effectiveTarget.onPanelUpdated(res.candidate_file || updatedUrl);
        }
        showToast("✨ Story panel inpainted successfully!");
      }

      // Reset mask canvas for further edits
      initCanvas();
    } catch (err: any) {
      setInpaintError(err.message || "Failed to execute inpainting.");
    } finally {
      setIsInpainting(false);
      setInpaintProgress(0);
      setInpaintStatusText("");
    }
  };

  const handleEditSubmit = async () => {
    if (!prompt.trim()) {
      setInpaintError("Please enter an instruction describing what the picture should become.");
      return;
    }
    if (effectiveTarget.mode !== 'project') {
      setInpaintError("Editing with words needs a project picture.");
      return;
    }

    setInpaintError(null);
    setIsInpainting(true);
    setInpaintProgress(0.05);

    try {
      setInpaintStatusText("Sending the picture and the instruction to ComfyUI...");
      const activeAsset = currentAsset || effectiveTarget.asset;
      const queued = await api.editComfyImage(effectiveTarget.projectId, {
        asset_id: activeAsset.id,
        prompt: prompt.trim(),
        seed,
        timeout_s: 1800,
      });

      setInpaintStatusText("Editing with MiniMax H3 Image...");

      const completedJob = await api.waitForWorkflowJob(queued.job_id, (job: Job) => {
        if (job.progress != null) setInpaintProgress(job.progress);
        if (job.message) setInpaintStatusText(job.message);
      });

      if (completedJob.status === "FAILED") {
        throw new Error(completedJob.error || "Edit job failed in engine.");
      }

      setInpaintStatusText("Retrieving the edited asset...");
      setInpaintProgress(0.95);

      const assetList = await api.listGeneratedAssets(effectiveTarget.projectId);
      if (assetList.assets && assetList.assets.length > 0) {
        const newest = assetList.assets[0];
        setPreviousAsset(currentAsset || effectiveTarget.asset);
        setCurrentAsset(newest);
        if (effectiveTarget.onAssetUpdated) effectiveTarget.onAssetUpdated(newest);
        showToast("✨ Edit complete! New asset created.");
      }
    } catch (err: any) {
      setInpaintError(err.message || "Failed to execute the edit.");
    } finally {
      setIsInpainting(false);
      setInpaintProgress(0);
      setInpaintStatusText("");
    }
  };

  const copyShaToClipboard = () => {
    const sha = effectiveTarget.mode === 'project'
      ? (currentAsset || effectiveTarget.asset).sha256
      : effectiveTarget.panelId;
    if (sha) {
      navigator.clipboard.writeText(sha);
      setCopiedSha(true);
      showToast("Identifier copied to clipboard");
      setTimeout(() => setCopiedSha(false), 2000);
    }
  };

  const imageUrl = effectiveTarget.mode === 'project'
    ? api.getGeneratedAssetUrl(
        effectiveTarget.projectId,
        (isComparing && previousAsset ? previousAsset : (currentAsset || effectiveTarget.asset)).id
      )
    : (isComparing && previousImageSrc ? previousImageSrc : currentImageSrc);

  const displayWidth = currentAsset?.width ?? imageNaturalSize.width;
  const displayHeight = currentAsset?.height ?? imageNaturalSize.height;
  const displayFilename = effectiveTarget.mode === 'project'
    ? (currentAsset?.filename || "asset.png")
    : `story-panel-${effectiveTarget.panelId}.png`;
  const displaySubtext = effectiveTarget.mode === 'project'
    ? (currentAsset ? `${(currentAsset.byte_size / 1024).toFixed(1)} KB` : "")
    : `Panel ${effectiveTarget.panelId}`;
  const hasInpainted = effectiveTarget.mode === 'project' ? !!previousAsset : !!previousImageSrc;

  const handleDownload = () => {
    const link = document.createElement("a");
    link.href = imageUrl;
    link.download = displayFilename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("Image downloaded");
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) handleRedo();
        else handleUndo();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        handleRedo();
      } else if (e.key.toLowerCase() === "b") {
        setTool("brush");
      } else if (e.key.toLowerCase() === "e") {
        setTool("eraser");
      } else if (e.key === "[") {
        setBrushSize((s) => Math.max(8, s - 6));
      } else if (e.key === "]") {
        setBrushSize((s) => Math.min(200, s + 6));
      } else if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-3 md:p-6 animate-in fade-in duration-200 select-none"
      role="dialog"
      aria-modal="true"
      aria-label="Image Editor & Inpainter"
    >
      <div className="bg-ink border border-edge rounded-2xl w-full max-w-[96vw] h-[94vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Top Header Bar */}
        <div className="px-5 py-3 border-b border-edge/90 bg-navy/70 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent via-accent to-accent flex items-center justify-center text-white shadow-lg shadow-accent/30">
              <Sparkles className="w-5 h-5 animate-pulse" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-fg truncate">
                  Visual Asset Editor & Inpaint Studio
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent/20 border border-accent/60 text-info">
                  {displayWidth} × {displayHeight}
                </span>
                {hasInpainted && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-ok/20 border border-ok/60 text-ok">
                    INPAINTED
                  </span>
                )}
              </div>
              <p className="text-xs text-fg-dim truncate font-mono">
                {displayFilename} · {displaySubtext}
              </p>
            </div>
          </div>

          {/* Quick Header Actions */}
          <div className="flex items-center gap-2">
            {hasInpainted && (
              <button
                type="button"
                onMouseDown={() => setIsComparing(true)}
                onMouseUp={() => setIsComparing(false)}
                onMouseLeave={() => setIsComparing(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-flat hover:bg-glass-hi text-fg border border-edge active:scale-95 transition-all flex items-center gap-1.5"
                title="Hold to see original image before inpainting"
              >
                <Layers className="w-3.5 h-3.5 text-info" />
                <span>{isComparing ? "Showing Original" : "Hold to Compare"}</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleDownload}
              className="p-2 rounded-lg text-fg-dim hover:text-white bg-flat/80 hover:bg-glass-hi border border-edge/60 active:scale-95 transition-all"
              title="Download full resolution image"
            >
              <Download className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={copyShaToClipboard}
              className="p-2 rounded-lg text-fg-dim hover:text-white bg-flat/80 hover:bg-glass-hi border border-edge/60 active:scale-95 transition-all"
              title="Copy SHA-256 hash"
            >
              {copiedSha ? <Check className="w-4 h-4 text-ok" /> : <Copy className="w-4 h-4" />}
            </button>

            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-fg-dim hover:text-white hover:bg-flat active:scale-95 transition-all"
              aria-label="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Main Workspace: Left Canvas + Right Grouped Inspector */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Canvas Viewport */}
          <div
            ref={canvasContainerRef}
            className="flex-1 bg-ink/90 relative overflow-hidden flex flex-col items-center justify-center p-4"
            style={{
              backgroundImage:
                "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.05) 1px, transparent 0)",
              backgroundSize: "24px 24px",
            }}
          >
            {/* Floating Top Canvas Toolbar */}
            <div className="absolute top-4 left-4 z-20 flex items-center gap-1.5 p-1.5 rounded-xl bg-navy/90 backdrop-blur-md border border-edge shadow-xl">
              <button
                type="button"
                onClick={handleUndo}
                disabled={historyStepRef.current <= 0}
                className="p-2 rounded-lg text-fg-dim hover:text-white hover:bg-flat disabled:opacity-30 disabled:pointer-events-none active:scale-95 transition-all"
                title="Undo (Ctrl+Z)"
              >
                <Undo2 className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={handleRedo}
                disabled={historyStepRef.current >= historyRef.current.length - 1}
                className="p-2 rounded-lg text-fg-dim hover:text-white hover:bg-flat disabled:opacity-30 disabled:pointer-events-none active:scale-95 transition-all"
                title="Redo (Ctrl+Y)"
              >
                <Redo2 className="w-4 h-4" />
              </button>
              <div className="w-px h-5 bg-flat mx-1" />
              <button
                type="button"
                onClick={handleClearMask}
                disabled={!hasMaskContent}
                className="p-2 rounded-lg text-fg-dim hover:text-bad hover:bg-flat disabled:opacity-30 disabled:pointer-events-none active:scale-95 transition-all"
                title="Clear mask"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setShowMask((prev) => !prev)}
                className={`p-2 rounded-lg text-fg-dim hover:text-white hover:bg-flat active:scale-95 transition-all ${
                  !showMask ? "text-warn bg-warn/40" : ""
                }`}
                title={showMask ? "Hide mask overlay" : "Show mask overlay"}
              >
                {showMask ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </button>
              <div className="w-px h-5 bg-flat mx-1" />
              <button
                type="button"
                onClick={() => setZoomLevel((z) => Math.max(0.4, Number((z - 0.2).toFixed(1))))}
                className="p-2 rounded-lg text-fg-dim hover:text-white hover:bg-flat active:scale-95 transition-all"
                title="Zoom Out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-xs font-mono text-fg-dim px-1 font-medium min-w-10 text-center">
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                type="button"
                onClick={() => setZoomLevel((z) => Math.min(3, Number((z + 0.2).toFixed(1))))}
                className="p-2 rounded-lg text-fg-dim hover:text-white hover:bg-flat active:scale-95 transition-all"
                title="Zoom In"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setZoomLevel(1);
                  setFitMode((m) => (m === "contain" ? "actual" : "contain"));
                }}
                className={`px-2 py-1 rounded-lg text-xs font-medium border transition-all ${
                  fitMode === "actual"
                    ? "bg-accent border-accent text-white"
                    : "bg-flat border-edge text-fg-dim hover:bg-glass-hi"
                }`}
                title="Toggle 100% size or Fit to screen"
              >
                {fitMode === "actual" ? "100%" : "Fit"}
              </button>
            </div>

            {/* Canvas Stage */}
            <div
              className="relative max-w-full max-h-full flex items-center justify-center transition-transform duration-150 ease-out"
              style={{
                transform: `scale(${zoomLevel})`,
                transformOrigin: "center center",
              }}
              onMouseEnter={() => setIsCursorInside(true)}
              onMouseLeave={() => {
                setIsCursorInside(false);
                setCursorPos(null);
              }}
            >
              {/* Underlying Original / Inpainted Art Image */}
              <img
                ref={imageRef}
                src={imageUrl}
                alt="Asset preview for inpainting"
                onLoad={initCanvas}
                className="max-h-[80vh] max-w-[80vw] object-contain rounded-lg border border-edge/80 shadow-2xl pointer-events-none transition-opacity duration-300"
                style={{ imageRendering: "auto" }}
              />

              {/* Foreground Mask Drawing Canvas */}
              <canvas
                ref={maskCanvasRef}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                className={`absolute inset-0 w-full h-full rounded-lg touch-none ${
                  showMask ? "opacity-100" : "opacity-0 pointer-events-none"
                }`}
                style={{ cursor: "none" }}
              />

              {/* Dynamic Animated Brush / Eraser Circular Cursor Tracker */}
              {isCursorInside && cursorPos && (
                <div
                  className="pointer-events-none absolute rounded-full border-2 transition-transform duration-75 ease-out"
                  style={{
                    left: `${cursorPos.x}px`,
                    top: `${cursorPos.y}px`,
                    width: `${brushSize * (maskCanvasRef.current ? maskCanvasRef.current.clientWidth / maskCanvasRef.current.width : 1)}px`,
                    height: `${brushSize * (maskCanvasRef.current ? maskCanvasRef.current.clientHeight / maskCanvasRef.current.height : 1)}px`,
                    transform: "translate(-50%, -50%)",
                    borderColor:
                      tool === "eraser"
                        ? "#7aa2ff"
                        : MASK_COLORS[maskColorIndex].hex,
                    backgroundColor:
                      tool === "eraser"
                        ? "rgba(122,162,255, 0.2)"
                        : MASK_COLORS[maskColorIndex].color.replace("0.6", "0.25"),
                    boxShadow:
                      tool === "eraser"
                        ? "0 0 12px rgba(122,162,255, 0.5)"
                        : `0 0 14px ${MASK_COLORS[maskColorIndex].hex}88`,
                  }}
                />
              )}
            </div>

            {/* Quick helper tip badge at bottom of canvas */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1.5 rounded-full bg-navy/90 backdrop-blur-md border border-edge/80 text-[11px] text-fg-dim shadow-lg">
              <span className="w-2 h-2 rounded-full bg-accent animate-ping" />
              <span>
                {tool === "brush"
                  ? "Paint over any area you want to replace or edit"
                  : "Erasing mask from canvas"}
              </span>
              <span className="text-fg-faint">|</span>
              <span className="font-mono text-fg-faint">Shortcuts: B (Brush), E (Eraser), [ ] (Size)</span>
            </div>
          </div>

          {/* Right Sidebar: Grouped Tools & Settings */}
          <div className="w-80 md:w-96 border-l border-edge bg-navy/60 overflow-y-auto p-5 space-y-6 flex flex-col">
            {/* GROUP 1: Drawing & Masking Tools */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-info flex items-center gap-1.5">
                  <Paintbrush className="w-3.5 h-3.5" />
                  1. Drawing Tool
                </span>
                <span className="text-[11px] text-fg-faint font-mono">
                  {hasMaskContent ? "Mask active" : "No mask"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTool("brush")}
                  className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl border font-semibold text-xs transition-all active:scale-95 ${
                    tool === "brush"
                      ? "bg-accent border-accent text-white shadow-lg shadow-accent/30"
                      : "bg-ink border-edge text-fg-dim hover:bg-flat"
                  }`}
                >
                  <Paintbrush className="w-4 h-4" />
                  <span>Brush Tool [B]</span>
                </button>

                <button
                  type="button"
                  onClick={() => setTool("eraser")}
                  className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl border font-semibold text-xs transition-all active:scale-95 ${
                    tool === "eraser"
                      ? "bg-info border-info text-white shadow-lg shadow-info/30"
                      : "bg-ink border-edge text-fg-dim hover:bg-flat"
                  }`}
                >
                  <Eraser className="w-4 h-4" />
                  <span>Eraser Tool [E]</span>
                </button>
              </div>

              {/* Mask Tint Color Selector */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] text-fg-dim">Mask Overlay Tint:</span>
                <div className="flex items-center gap-1.5">
                  {MASK_COLORS.map((mc, idx) => (
                    <button
                      key={mc.id}
                      type="button"
                      onClick={() => setMaskColorIndex(idx)}
                      className={`w-5 h-5 rounded-full border-2 transition-transform ${
                        maskColorIndex === idx ? "scale-125 border-white shadow-md" : "border-transparent opacity-60 hover:opacity-100"
                      }`}
                      style={{ backgroundColor: mc.hex }}
                      title={mc.label}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* GROUP 2: Brush Settings */}
            <div className="space-y-3 p-4 rounded-xl bg-ink/70 border border-edge/80">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-fg-dim flex items-center gap-1.5">
                  <Sliders className="w-3.5 h-3.5 text-info" />
                  2. Brush Settings
                </span>
                <span className="text-xs font-mono font-bold text-info bg-accent/60 px-2 py-0.5 rounded border border-accent/50">
                  {brushSize}px
                </span>
              </div>

              {/* Dynamic Brush Size Slider + Live Ring Preview */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={8}
                    max={180}
                    value={brushSize}
                    onChange={(e) => setBrushSize(Number(e.target.value))}
                    className="w-full h-1.5 bg-flat rounded-lg appearance-none cursor-pointer accent-accent"
                  />
                  {/* Miniature animated circle preview */}
                  <div className="w-8 h-8 rounded-lg bg-navy border border-edge flex items-center justify-center shrink-0">
                    <div
                      className="rounded-full bg-accent transition-all duration-100"
                      style={{
                        width: `${Math.max(4, Math.min(24, (brushSize / 180) * 24))}px`,
                        height: `${Math.max(4, Math.min(24, (brushSize / 180) * 24))}px`,
                      }}
                    />
                  </div>
                </div>

                {/* Quick Size Preset Chips */}
                <div className="flex gap-1.5 pt-1">
                  {[
                    { label: "Fine", size: 16 },
                    { label: "Med", size: 40 },
                    { label: "Wide", size: 80 },
                    { label: "Huge", size: 140 },
                  ].map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => setBrushSize(preset.size)}
                      className={`flex-1 py-1 rounded text-[11px] font-medium border transition-all active:scale-95 ${
                        brushSize === preset.size
                          ? "bg-accent border-accent text-white"
                          : "bg-navy border-edge text-fg-dim hover:text-fg"
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Opacity Slider */}
              <div className="pt-2 border-t border-edge/80 space-y-1">
                <div className="flex justify-between text-[11px] text-fg-dim">
                  <span>Mask Opacity</span>
                  <span className="font-mono">{Math.round(brushOpacity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min={0.3}
                  max={1.0}
                  step={0.05}
                  value={brushOpacity}
                  onChange={(e) => setBrushOpacity(Number(e.target.value))}
                  className="w-full h-1.5 bg-flat rounded-lg appearance-none cursor-pointer accent-accent"
                />
              </div>
            </div>

            {/* GROUP 3: Inpaint Parameters & Action */}
            <div className="space-y-3 p-4 rounded-xl bg-ink/70 border border-edge/80">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-info flex items-center gap-1.5">
                  <Wand2 className="w-3.5 h-3.5" />
                  3. Inpaint &amp; Edit Options
                </span>
                <span className="text-[10px] text-fg-faint">qwen_image_21_inpaint / minimax_h3_image_edit</span>
              </div>

              {/* Prompt Textarea */}
              <div>
                <label className="block text-xs font-medium text-fg-dim mb-1">
                  Prompt (inpaint: what to draw in the mask. edit: what the picture should become)
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  placeholder="e.g. a stormy sky over the street, golden sparks around the sword"
                  className="w-full rounded-lg border border-edge bg-navy px-3 py-2 text-xs text-fg focus:border-accent focus:outline-none placeholder:text-fg-faint transition-colors"
                  disabled={isInpainting}
                />
              </div>

              {/* Quick Preset Prompt Chips */}
              <div className="space-y-1.5">
                <span className="text-[11px] text-fg-dim font-medium">Quick Inpaint Presets:</span>
                <div className="flex flex-wrap gap-1.5">
                  {INPAINT_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => setPrompt(p.prompt)}
                      className="px-2 py-1 rounded-md text-[11px] bg-navy border border-edge text-fg-dim hover:text-white hover:bg-flat hover:border-accent/50 hover:-translate-y-0.5 active:scale-95 transition-all flex items-center gap-1"
                    >
                      <span>{p.icon}</span>
                      <span>{p.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Negative Prompt (Collapsible / Compact) */}
              <div>
                <label className="block text-[11px] text-fg-dim mb-1">Negative Prompt</label>
                <input
                  type="text"
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  className="w-full rounded-lg border border-edge bg-navy px-2.5 py-1.5 text-xs text-fg-dim focus:border-accent focus:outline-none"
                  disabled={isInpainting}
                />
              </div>

              {/* Seed with Randomizer */}
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <label className="block text-[11px] text-fg-dim mb-0.5">Seed</label>
                  <input
                    type="number"
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                    className="w-full rounded-lg border border-edge bg-navy px-2.5 py-1 text-xs text-fg font-mono"
                    disabled={isInpainting}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setSeed(Math.floor(Math.random() * 900000000) + 100000000)}
                  disabled={isInpainting}
                  className="mt-4 p-2 rounded-lg bg-navy hover:bg-flat border border-edge text-fg-dim hover:text-info active:scale-95 transition-all"
                  title="Randomize seed"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Error Alert */}
              {inpaintError && (
                <div className="p-2.5 rounded-lg bg-bad/40 border border-bad/80 text-bad text-xs flex items-start gap-2 animate-in fade-in">
                  <AlertCircle className="w-4 h-4 shrink-0 text-bad mt-0.5" />
                  <span className="break-words">{inpaintError}</span>
                </div>
              )}

              {/* Progress Feedback during Inpainting */}
              {isInpainting && (
                <div className="space-y-2 p-3 rounded-xl bg-accent/40 border border-accent/60 animate-in fade-in">
                  <div className="flex items-center justify-between text-xs text-info font-medium">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-info animate-spin" />
                      {inpaintStatusText || "Inpainting with ComfyUI..."}
                    </span>
                    <span className="font-mono font-bold">{Math.round(inpaintProgress * 100)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-navy rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-accent via-accent to-accent rounded-full transition-all duration-300"
                      style={{ width: `${Math.max(10, inpaintProgress * 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Inpaint Action Button */}
              <button
                type="button"
                onClick={handleInpaintSubmit}
                disabled={isInpainting || !prompt.trim() || !hasMaskContent}
                className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all duration-200 ${
                  isInpainting
                    ? "bg-flat text-fg-faint border border-edge cursor-not-allowed"
                    : !hasMaskContent
                    ? "bg-navy text-fg-faint border border-edge cursor-not-allowed"
                    : "bg-gradient-to-r from-accent via-accent to-accent hover:from-accent hover:via-accent hover:to-accent text-white shadow-lg shadow-accent/30 hover:shadow-accent/50 active:scale-[0.98] border border-accent/30"
                }`}
              >
                <Sparkles className={`w-4 h-4 ${isInpainting ? "animate-spin" : ""}`} />
                <span>
                  {isInpainting
                    ? "Inpainting..."
                    : !hasMaskContent
                    ? "Paint a mask on image to inpaint"
                    : "Inpaint Masked Area with ComfyUI"}
                </span>
              </button>

              {/* Edit with words (MiniMax-H3-Image): no mask needed, the instruction says what to change */}
              {effectiveTarget.mode === 'project' && (
                <button
                  type="button"
                  onClick={handleEditSubmit}
                  disabled={isInpainting || !prompt.trim()}
                  className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all duration-200 ${
                    isInpainting
                      ? "bg-flat text-fg-faint border border-edge cursor-not-allowed"
                      : !prompt.trim()
                      ? "bg-navy text-fg-faint border border-edge cursor-not-allowed"
                      : "bg-gradient-to-r from-ok via-info to-info hover:from-ok hover:via-info hover:to-info text-white shadow-lg shadow-info/30 hover:shadow-info/50 active:scale-[0.98] border border-ok/30"
                  }`}
                >
                  <Wand2 className={`w-4 h-4 ${isInpainting ? "animate-spin" : ""}`} />
                  <span>
                    {isInpainting
                      ? "Editing..."
                      : "Edit Whole Picture from Instructions (H3 Image)"}
                  </span>
                </button>
              )}
            </div>

            {/* Toast Feedback */}
            {toastMessage && (
              <div className="p-2.5 rounded-lg bg-ok/80 border border-ok/80 text-ok text-xs flex items-center gap-2 animate-in fade-in duration-150">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" />
                <span>{toastMessage}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
