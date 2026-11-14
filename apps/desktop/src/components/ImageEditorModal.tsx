import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@panelflow/api-client";
import type { ComfyEditRequest, GeneratedAsset } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { Check, Copy, Download, Layers, Sparkles, X } from "lucide-react";
import { AiInspector } from "./image-studio/AiInspector";
import { DeliverInspector } from "./image-studio/DeliverInspector";
import { PageRail } from "./image-studio/PageRail";
import { ToolRail } from "./image-studio/ToolRail";
import type { AiMode, StudioPage, StudioVersion, ToolMode } from "./image-studio/types";
import { VersionsStrip } from "./image-studio/VersionsStrip";
import { ColorInspector } from "./image-studio/color/ColorInspector";
import { GradeCanvas } from "./image-studio/color/GradeCanvas";
import { G, isNeutral, type LutLibrary } from "./image-studio/color/grade";
import { pushGrade, redoGrade, startHistory, undoGrade } from "./image-studio/color/history";
import { loadLutLibrary, saveLutLibrary } from "./image-studio/color/lutLibrary";
import { CutInspector } from "./image-studio/cut/CutInspector";
import { CutStage } from "./image-studio/cut/CutStage";
import { cutGeometry, isCutIdentity, newCut, type CutState } from "./image-studio/cut/geometry";
import { renderEditedBlob } from "./image-studio/cut/render";
import { useImageSource } from "./image-studio/color/useImageSource";

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

  // Studio layout: the page on the bottom rail, the AI mode, and the pictures made in this session
  const [page, setPage] = useState<StudioPage>("ai");
  const [aiMode, setAiMode] = useState<AiMode>(effectiveTarget.mode === "project" ? "edit" : "inpaint");
  const [versions, setVersions] = useState<GeneratedAsset[]>(effectiveTarget.mode === "project" ? [effectiveTarget.asset] : []);

  // Colour grade: a non-destructive node stack on the view. AI always runs on the clean pixels; the grade follows onto the new result.
  const [gradeHistory, setGradeHistory] = useState(() => startHistory(G.newGrade()));
  const [nodeIndex, setNodeIndex] = useState(0);
  const [lutLib, setLutLib] = useState<LutLibrary>(() => loadLutLibrary());
  const [gradeBypass, setGradeBypass] = useState(false);
  // Cut: crop, straighten, turns, flips, resize. Also a view-level state: shown on the Cut page, applied when you export or save.
  const [cutHistory, setCutHistory] = useState(() => startHistory(newCut()));

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

  // Pose & camera transfer: the picture the poses and the camera angle are taken from (a data URL read from disk)
  const [poseImageData, setPoseImageData] = useState<string | null>(null);
  const [poseFileName, setPoseFileName] = useState<string>("");
  const [transferNote, setTransferNote] = useState<string>("");

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
      setVersions([effectiveTarget.asset]);
    }
    setGradeHistory(startHistory(G.newGrade()));
    setCutHistory(startHistory(newCut()));
    setNodeIndex(0);
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
          setVersions((v) => (v.some((x) => x.id === newest.id) ? v : [...v, newest]));
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

  const handlePoseFile = (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setInpaintError("Choose an image file for the pose picture.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setInpaintError("The pose picture is larger than 20 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setPoseImageData(String(reader.result));
      setPoseFileName(file.name);
      setInpaintError(null);
    };
    reader.readAsDataURL(file);
  };

  const handleEditSubmit = () => {
    if (!prompt.trim()) {
      setInpaintError("Please enter an instruction describing what the picture should become.");
      return;
    }
    return runEdit({ prompt: prompt.trim() }, "Editing with MiniMax H3 Image...", "Edit complete! New asset created.");
  };

  const handleTransferSubmit = () => {
    if (!poseImageData) {
      setInpaintError("Choose the picture whose poses and camera angle should be used.");
      return;
    }
    return runEdit(
      { pose_image_data: poseImageData, prompt: transferNote.trim() },
      "Transferring the poses and camera angle with MiniMax H3 Image...",
      "Pose and camera transferred! New asset created.",
    );
  };

  const runEdit = async (request: Partial<ComfyEditRequest>, runningText: string, doneToast: string) => {
    if (effectiveTarget.mode !== 'project') {
      setInpaintError("Editing with words needs a project picture.");
      return;
    }

    setInpaintError(null);
    setIsInpainting(true);
    setInpaintProgress(0.05);

    try {
      setInpaintStatusText("Sending the pictures and the instruction to ComfyUI...");
      const activeAsset = currentAsset || effectiveTarget.asset;
      const queued = await api.editComfyImage(effectiveTarget.projectId, {
        asset_id: activeAsset.id,
        ...request,
        seed,
        timeout_s: 1800,
      });

      setInpaintStatusText(runningText);

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
        setVersions((v) => (v.some((x) => x.id === newest.id) ? v : [...v, newest]));
        if (effectiveTarget.onAssetUpdated) effectiveTarget.onAssetUpdated(newest);
        showToast(`✨ ${doneToast}`);
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

  const grade = gradeHistory.present;
  const gradeActive = grade.on && !isNeutral(grade);
  const cleanUrl =
    effectiveTarget.mode === "project"
      ? api.getGeneratedAssetUrl(effectiveTarget.projectId, (currentAsset || effectiveTarget.asset).id)
      : currentImageSrc;
  const cut = cutHistory.present;
  const cutActive = !isCutIdentity(cut);
  const source = useImageSource(cleanUrl, page === "color" || page === "cut" || gradeActive || cutActive);
  const bakedTable = useMemo(() => (gradeActive ? G.bake(grade, G.LUT_SIZE, lutLib) : null), [grade, lutLib, gradeActive]);
  const shownTable = gradeBypass || isComparing ? null : bakedTable; // comparing and bypass show the picture as it is
  const changeGrade = (next: typeof grade, key: string) => setGradeHistory((h) => pushGrade(h, next, key, Date.now()));
  const changeLib = (lib: LutLibrary) => {
    setLutLib(lib);
    if (!saveLutLibrary(lib)) showToast("The LUT library could not be remembered (browser storage is full)");
  };
  const changeCut = (next: CutState, key: string) => setCutHistory((h) => pushGrade(h, next, key, Date.now()));
  const sourceW = source.bitmap?.width ?? displayWidth, sourceH = source.bitmap?.height ?? displayHeight;
  const cutGeo = cutActive ? cutGeometry(cut, sourceW, sourceH) : null;
  // What Deliver bakes in: the grade first (full size), then the cut.
  const bakedForExport =
    (gradeActive || cutActive) && source.bitmap
      ? { bitmap: source.bitmap, table: gradeActive ? bakedTable : null, size: G.LUT_SIZE, cut: cutActive ? cut : null }
      : null;

  // Keep the edited picture (grade and/or cut) as a new project asset; both are then in the pixels, so the stacks are cleared.
  const saveEdited = async () => {
    if (effectiveTarget.mode !== "project" || !bakedForExport) return;
    try {
      const was = currentAsset || effectiveTarget.asset;
      const blob = await renderEditedBlob(bakedForExport, "image/png");
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result));
        r.onerror = () => reject(new Error("Could not read the edited picture."));
        r.readAsDataURL(blob);
      });
      const saved = await api.saveGradedImage(effectiveTarget.projectId, {
        image_data: dataUrl,
        source_asset_id: was.id,
        ...(gradeActive ? { grade } : {}),
        ...(cutActive ? { cut } : {}),
      });
      setPreviousAsset(was);
      setCurrentAsset(saved);
      setVersions((v) => (v.some((x) => x.id === saved.id) ? v : [...v, saved]));
      if (effectiveTarget.onAssetUpdated) effectiveTarget.onAssetUpdated(saved);
      setGradeHistory(startHistory(G.newGrade()));
      setCutHistory(startHistory(newCut()));
      setNodeIndex(0);
      showToast("Edited picture saved as a new asset");
    } catch (err: any) {
      showToast(err?.message || "The edited picture could not be saved");
    }
  };

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
  // The key handler is registered once, so what it needs to know about the page lives in a ref.
  const live = useRef({ page, undo: () => {}, redo: () => {} });
  live.current = {
    page,
    undo: () => (page === "cut" ? setCutHistory((h) => undoGrade(h)) : setGradeHistory((h) => undoGrade(h))),
    redo: () => (page === "cut" ? setCutHistory((h) => redoGrade(h)) : setGradeHistory((h) => redoGrade(h))),
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const onColor = live.current.page === "color" || live.current.page === "cut";

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (onColor) (e.shiftKey ? live.current.redo : live.current.undo)();
        else if (e.shiftKey) handleRedo();
        else handleUndo();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        if (onColor) live.current.redo();
        else handleRedo();
      } else if (e.key.toLowerCase() === "b") {
        setPage("ai");
        setAiMode("inpaint");
        setTool("brush");
      } else if (e.key.toLowerCase() === "e") {
        setPage("ai");
        setAiMode("inpaint");
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

  const maskTools = page === "ai" && aiMode === "inpaint";
  const projectIdForUrls = effectiveTarget.mode === "project" ? effectiveTarget.projectId : "";
  const versionLabel = (a: GeneratedAsset, i: number) => {
    if (i === 0) return "Original";
    const prov = a.provenance || {};
    if (prov.role === "color_grade") return `v${i} · Grade`;
    if (prov.role === "cut") return `v${i} · Cut`;
    if (prov.mode === "pose_camera_transfer") return `v${i} · Pose`;
    if (String(prov.workflow_id || "").includes("inpaint")) return `v${i} · Inpaint`;
    return `v${i} · Edit`;
  };
  const versionItems: StudioVersion[] =
    effectiveTarget.mode === "project"
      ? versions.map((a, i) => ({ key: a.id, label: versionLabel(a, i), src: api.getGeneratedAssetUrl(projectIdForUrls, a.id) }))
      : [
          ...(previousImageSrc ? [{ key: "prev", label: "Before", src: previousImageSrc }] : []),
          { key: "cur", label: previousImageSrc ? "Current" : "Original", src: currentImageSrc },
        ];
  const activeVersionKey = effectiveTarget.mode === "project" ? (currentAsset || effectiveTarget.asset).id : "cur";
  const selectVersion = (key: string) => {
    const i = versions.findIndex((a) => a.id === key);
    if (i < 0) return;
    setCurrentAsset(versions[i]);
    setPreviousAsset(i > 0 ? versions[i - 1] : null);
  };
  const shownAsset = effectiveTarget.mode === "project" ? currentAsset || effectiveTarget.asset : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-3 backdrop-blur-md select-none animate-in fade-in duration-200 md:p-5"
      role="dialog"
      aria-modal="true"
      aria-label="Image Editor & Inpainter"
    >
      <div className="flex h-[95vh] w-full max-w-[98vw] flex-col overflow-hidden rounded-2xl border border-edge bg-ink shadow-2xl">
        {/* Header: what is open, and the actions that apply to every page */}
        <header className="flex items-center justify-between gap-4 border-b border-edge bg-navy px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <Sparkles className="h-5 w-5 shrink-0 text-info" />
            <h2 className="shrink-0 text-sm font-semibold text-fg">Image Studio</h2>
            <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[10px] text-info">
              {displayWidth} × {displayHeight}
            </span>
            {hasInpainted && (
              <span className="shrink-0 rounded-full border border-ok/50 bg-ok/10 px-2 py-0.5 text-[10px] font-medium text-ok">EDITED</span>
            )}
            {gradeActive && (
              <span className="shrink-0 rounded-full border border-info/50 bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-info">GRADED</span>
            )}
            {cutActive && (
              <span
                className="shrink-0 rounded-full border border-info/50 bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-info"
                title="The cut is applied when you export or save from Deliver"
              >
                CUT {cutGeo ? `${cutGeo.outW} × ${cutGeo.outH}` : ""}
              </span>
            )}
            <p className="truncate font-mono text-xs text-fg-dim">
              {displayFilename} · {displaySubtext}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {hasInpainted && (
              <button
                type="button"
                onMouseDown={() => setIsComparing(true)}
                onMouseUp={() => setIsComparing(false)}
                onMouseLeave={() => setIsComparing(false)}
                className="flex items-center gap-1.5 rounded-lg border border-edge bg-flat px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-glass-hi"
                title="Hold to see the version before this one"
              >
                <Layers className="h-3.5 w-3.5 text-info" />
                <span>{isComparing ? "Showing Original" : "Hold to Compare"}</span>
              </button>
            )}
            <button type="button" onClick={handleDownload} className="rounded-lg border border-edge/60 bg-flat/80 p-2 text-fg-dim transition-colors hover:bg-glass-hi hover:text-fg" title="Download full resolution image">
              <Download className="h-4 w-4" />
            </button>
            <button type="button" onClick={copyShaToClipboard} className="rounded-lg border border-edge/60 bg-flat/80 p-2 text-fg-dim transition-colors hover:bg-glass-hi hover:text-fg" title="Copy SHA-256 hash">
              {copiedSha ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
            </button>
            <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-dim transition-colors hover:bg-flat hover:text-fg" aria-label="Close modal">
              <X className="h-5 w-5" />
            </button>
          </div>
        </header>

        {/* Workspace: tool rail, canvas with the versions strip, and the inspector of the open page */}
        <div className="flex min-h-0 flex-1">
          <ToolRail
            maskTools={maskTools}
            tool={tool}
            onTool={setTool}
            canUndo={historyStepRef.current > 0}
            canRedo={historyStepRef.current < historyRef.current.length - 1}
            hasMask={hasMaskContent}
            showMask={showMask}
            onUndo={handleUndo}
            onRedo={handleRedo}
            onClearMask={handleClearMask}
            onToggleMask={() => setShowMask((prev) => !prev)}
            zoom={zoomLevel}
            fitMode={fitMode}
            onZoomOut={() => setZoomLevel((z) => Math.max(0.4, Number((z - 0.2).toFixed(1))))}
            onZoomIn={() => setZoomLevel((z) => Math.min(3, Number((z + 0.2).toFixed(1))))}
            onFit={() => {
              setZoomLevel(1);
              setFitMode((m) => (m === "contain" ? "actual" : "contain"));
            }}
          />

          <div className="flex min-w-0 flex-1 flex-col">
            <div
              ref={canvasContainerRef}
              className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-ink p-4"
              style={{ backgroundImage: "radial-gradient(circle at 1px 1px, rgba(150,175,255,0.07) 1px, transparent 0)", backgroundSize: "24px 24px" }}
            >
              <div
                className={`relative flex max-h-full max-w-full items-center justify-center transition-transform duration-150 ease-out ${page === "cut" ? "hidden" : ""}`}
                style={{ transform: `scale(${zoomLevel})`, transformOrigin: "center center" }}
                onMouseEnter={() => setIsCursorInside(true)}
                onMouseLeave={() => {
                  setIsCursorInside(false);
                  setCursorPos(null);
                }}
              >
                <img
                  ref={imageRef}
                  src={imageUrl}
                  alt="Asset preview for inpainting"
                  onLoad={initCanvas}
                  className="pointer-events-none max-h-[68vh] max-w-[62vw] rounded-lg border border-edge/80 object-contain shadow-2xl"
                  style={{ imageRendering: "auto" }}
                />
                <GradeCanvas bitmap={source.bitmap} table={shownTable} size={G.LUT_SIZE} onError={showToast} />
                <canvas
                  ref={maskCanvasRef}
                  onPointerDown={handlePointerDown}
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerUp}
                  onPointerCancel={handlePointerUp}
                  className={`absolute inset-0 h-full w-full touch-none rounded-lg ${
                    showMask && maskTools ? "opacity-100" : "opacity-0"
                  } ${maskTools ? "" : "pointer-events-none"}`}
                  style={{ cursor: maskTools ? "none" : "default" }}
                />
                {maskTools && isCursorInside && cursorPos && (
                  <div
                    className="pointer-events-none absolute rounded-full border-2 transition-transform duration-75 ease-out"
                    style={{
                      left: `${cursorPos.x}px`,
                      top: `${cursorPos.y}px`,
                      width: `${brushSize * (maskCanvasRef.current ? maskCanvasRef.current.clientWidth / maskCanvasRef.current.width : 1)}px`,
                      height: `${brushSize * (maskCanvasRef.current ? maskCanvasRef.current.clientHeight / maskCanvasRef.current.height : 1)}px`,
                      transform: "translate(-50%, -50%)",
                      borderColor: tool === "eraser" ? "#7aa2ff" : MASK_COLORS[maskColorIndex].hex,
                      backgroundColor: tool === "eraser" ? "rgba(122,162,255, 0.2)" : MASK_COLORS[maskColorIndex].color.replace("0.6", "0.25"),
                    }}
                  />
                )}
              </div>
              {page === "cut" && (
                <div style={{ transform: `scale(${zoomLevel})`, transformOrigin: "center center" }} className="transition-transform duration-150 ease-out">
                  <CutStage bitmap={source.bitmap} table={shownTable} size={G.LUT_SIZE} cut={cut} onChange={changeCut} error={source.error} />
                </div>
              )}
              {maskTools && (
                <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-edge/80 bg-navy/90 px-3 py-1 text-[11px] text-fg-dim">
                  {tool === "brush" ? "Paint over the area to replace" : "Erasing the mask"} · B brush · E eraser · [ ] size
                </div>
              )}
              {toastMessage && (
                <div className="absolute right-3 top-3 flex items-center gap-2 rounded-lg border border-ok/50 bg-navy/95 px-3 py-2 text-xs text-ok animate-in fade-in duration-150">
                  <Check className="h-4 w-4" />
                  <span>{toastMessage}</span>
                </div>
              )}
            </div>
            <VersionsStrip
              versions={versionItems}
              activeKey={activeVersionKey}
              onSelect={effectiveTarget.mode === "project" ? selectVersion : undefined}
              busy={isInpainting}
            />
          </div>

          <aside className="w-80 shrink-0 border-l border-edge bg-navy/60 md:w-[22rem]" aria-label={page === "deliver" ? "Deliver" : page === "color" ? "Color" : page === "cut" ? "Cut" : "AI"}>
            {page === "cut" ? (
              <CutInspector
                cut={cut}
                sourceWidth={sourceW}
                sourceHeight={sourceH}
                onChange={changeCut}
                canUndo={cutHistory.past.length > 0}
                canRedo={cutHistory.future.length > 0}
                onUndo={() => setCutHistory((h) => undoGrade(h))}
                onRedo={() => setCutHistory((h) => redoGrade(h))}
              />
            ) : page === "color" ? (
              <ColorInspector
                grade={grade}
                nodeIndex={nodeIndex}
                onNodeIndex={setNodeIndex}
                onChange={changeGrade}
                canUndo={gradeHistory.past.length > 0}
                canRedo={gradeHistory.future.length > 0}
                onUndo={() => setGradeHistory((h) => undoGrade(h))}
                onRedo={() => setGradeHistory((h) => redoGrade(h))}
                lib={lutLib}
                onLib={changeLib}
                bypass={gradeBypass}
                onBypass={setGradeBypass}
                probe={source.probe}
                sourceError={source.error}
                table={bakedTable}
                onToast={showToast}
              />
            ) : page === "deliver" ? (
              <DeliverInspector
                imageUrl={imageUrl}
                filename={displayFilename}
                dimensions={`${displayWidth} × ${displayHeight}`}
                sha256={shownAsset?.sha256}
                provenance={shownAsset?.provenance}
                baked={bakedForExport}
                outputSize={cutGeo ? `${cutGeo.outW} × ${cutGeo.outH}` : `${displayWidth} × ${displayHeight}`}
                onSaveEdited={effectiveTarget.mode === "project" ? saveEdited : undefined}
                onToast={showToast}
              />
            ) : (
              <AiInspector
                mode={aiMode}
                onMode={setAiMode}
                isProject={effectiveTarget.mode === "project"}
                busy={isInpainting}
                progress={inpaintProgress}
                statusText={inpaintStatusText}
                error={inpaintError}
                prompt={prompt}
                onPrompt={setPrompt}
                seed={seed}
                onSeed={setSeed}
                onEdit={handleEditSubmit}
                pose={{
                  imageData: poseImageData,
                  fileName: poseFileName,
                  note: transferNote,
                  onNote: setTransferNote,
                  onFile: handlePoseFile,
                  onSubmit: handleTransferSubmit,
                }}
                inpaint={{
                  tool,
                  onTool: setTool,
                  brushSize,
                  onBrushSize: setBrushSize,
                  brushOpacity,
                  onBrushOpacity: setBrushOpacity,
                  maskColors: MASK_COLORS,
                  maskColorIndex,
                  onMaskColor: setMaskColorIndex,
                  presets: INPAINT_PRESETS,
                  negativePrompt,
                  onNegativePrompt: setNegativePrompt,
                  hasMask: hasMaskContent,
                  onSubmit: handleInpaintSubmit,
                }}
              />
            )}
          </aside>
        </div>

        <PageRail page={page} onPage={setPage} />
      </div>
    </div>
  );
};
