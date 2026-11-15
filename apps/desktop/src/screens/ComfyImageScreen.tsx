import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type {
  BrowserBridgeResult,
  BrowserBridgeStatus,
  ComfyWorkflowInfo,
  GeneratedAsset,
} from "@panelflow/api-client";
import type { Job, Project } from "@panelflow/shared-types";
import { Badge, Button, Card, Icons, ProgressBar } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";
import { ImageEditorModal } from "../components/ImageEditorModal";

export interface ComfyImageScreenProps {
  project: Project;
  onBack: () => void;
}

type GenerationMode = "web_ai" | "comfy_local" | "chrono";

type ChronoGenType = "text2img" | "charlock" | "refupload";

const PRESETS = [
  { id: "chatgpt", name: "ChatGPT / DALL-E", url: "https://chatgpt.com" },
  { id: "gemini", name: "Google Gemini / Imagen", url: "https://gemini.google.com" },
  { id: "meta_ai", name: "Meta AI / Imagine", url: "https://www.meta.ai" },
  { id: "claude", name: "Anthropic Claude", url: "https://claude.ai" },
  { id: "custom", name: "Custom Web Tool", url: "" },
];

const SAMPLE_PROMPTS = [
  "Original manga panel: a celestial martial emperor descending with golden lightning, dynamic perspective, sharp ink lines, expressive face, cinematic manga composition",
  "Heroic swordswoman in flowing robes standing on a mountain peak at sunset, cel shaded anime aesthetic, highly detailed, clean lines",
  "Dramatic anime confrontation in a rain-soaked neon cyberpunk alley, volumetric lighting, rich color palette, wallpaper quality",
];

export const ComfyImageScreen: React.FC<ComfyImageScreenProps> = ({ project, onBack }) => {
  const { reportError } = useError();
  const [mode, setMode] = useState<GenerationMode>("web_ai");

  // Web AI Bridge state
  const [selectedPreset, setSelectedPreset] = useState("chatgpt");
  const [webUrl, setWebUrl] = useState("https://chatgpt.com");
  const [webPrompt, setWebPrompt] = useState(SAMPLE_PROMPTS[0]);
  const [extractType, setExtractType] = useState<"images" | "text" | "all">("all");
  const [headless, setHeadless] = useState(true);
  const [webSubmitting, setWebSubmitting] = useState(false);
  const [webStep, setWebStep] = useState<string | null>(null);
  const [webResult, setWebResult] = useState<BrowserBridgeResult | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<BrowserBridgeStatus | null>(null);
  const [copiedText, setCopiedText] = useState(false);

  // Local ComfyUI state
  const [workflows, setWorkflows] = useState<ComfyWorkflowInfo[]>([]);
  const [assets, setAssets] = useState<GeneratedAsset[]>([]);
  const [workflowId, setWorkflowId] = useState("qwen_image_21");
  const [comfyPrompt, setComfyPrompt] = useState(SAMPLE_PROMPTS[1]);
  const [negativePrompt, setNegativePrompt] = useState("photorealism, 3D render, blurry, malformed hands, text, watermark, logo, gore");
  const [width, setWidth] = useState(512);
  const [height, setHeight] = useState(768);
  const [seed, setSeed] = useState(20261019);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [comfyLoading, setComfyLoading] = useState(true);
  const [comfySubmitting, setComfySubmitting] = useState(false);
  const [selectedAssetForModal, setSelectedAssetForModal] = useState<GeneratedAsset | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // ChronoFlow character-locked generation (§16 parity with the web studio)
  const [chronoType, setChronoType] = useState<ChronoGenType>("text2img");
  const [chronoPrompt, setChronoPrompt] = useState(SAMPLE_PROMPTS[0]);
  const [chronoNegative, setChronoNegative] = useState("blurry, low quality, distorted, extra limbs, bad anatomy, deformed");
  const [chronoAspect, setChronoAspect] = useState("768x1344");
  const [chronoSeed, setChronoSeed] = useState("");
  const [chronoRefine, setChronoRefine] = useState(false);
  const [chronoLockedIds, setChronoLockedIds] = useState<string[]>([]);
  const [chronoVault, setChronoVault] = useState<Array<{ id: string; name: string; role: string; image: string }>>([]);
  const [chronoRefs, setChronoRefs] = useState<string[]>([]);
  const [chronoBusy, setChronoBusy] = useState(false);
  const [chronoResult, setChronoResult] = useState<{ url: string; lockedNote?: string; refineNote?: string } | null>(null);

  useEffect(() => {
    api.listChronoFlowCharacters()
      .then((d) => setChronoVault(d.characters || []))
      .catch(() => {});
  }, []);

  const toggleChronoLock = (id: string) => {
    setChronoLockedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
  };

  const handleChronoRefUpload = async (files: FileList | null) => {
    if (!files || !files.length) return;
    const room = 4 - chronoRefs.length;
    if (room <= 0) {
      reportError({ title: "Reference limit reached", message: "Max 4 reference images. Remove one first.", severity: "warning", source: "pipeline", projectId: project.id });
      return;
    }
    const picked = Array.from(files).slice(0, room);
    const uploaded: string[] = [];
    for (const file of picked) {
      try {
        const bytes = await file.arrayBuffer();
        const safe = `ref_${Date.now()}_${file.name.replace(/[^\w.\-]/g, "_")}`;
        const res = await api.uploadChronoFlowReferenceImage(bytes, safe);
        if (res?.filename) uploaded.push(res.filename);
      } catch (err: any) {
        reportError({
          title: "Reference Upload Failed",
          message: err.message || `Could not upload ${file.name}.`,
          severity: "error",
          source: "pipeline",
          projectId: project.id,
          rawDetails: err,
        });
      }
    }
    if (uploaded.length) setChronoRefs((prev) => [...prev, ...uploaded].slice(0, 4));
  };

  const handleChronoGenerate = async () => {
    if (chronoType === "charlock" && !chronoLockedIds.length) {
      reportError({ title: "Character-Locked needs references", message: "Select at least one Character Vault sheet, or switch to Text → Image.", severity: "warning", source: "pipeline", projectId: project.id });
      return;
    }
    if (chronoType === "refupload" && !chronoRefs.length) {
      reportError({ title: "Custom Reference needs uploads", message: "Upload at least one reference image, or switch to Text → Image.", severity: "warning", source: "pipeline", projectId: project.id });
      return;
    }
    setChronoBusy(true);
    setChronoResult(null);
    const [w, h] = chronoAspect.split("x").map((n) => parseInt(n, 10));
    const seedNum = chronoSeed.trim() !== "" && !isNaN(parseInt(chronoSeed, 10)) ? parseInt(chronoSeed, 10) : undefined;
    try {
      const data = await api.generateChronoFlowImage({
        prompt: chronoPrompt,
        negative_prompt: chronoNegative,
        width: w,
        height: h,
        ...(seedNum !== undefined ? { seed: seedNum } : {}),
        ...(chronoRefine ? { refine: true } : {}),
        ...(chronoType === "charlock" ? { character_ids: chronoLockedIds } : {}),
        ...(chronoType === "refupload" ? { ref_images: chronoRefs } : {}),
      });
      if (data.success && data.url) {
        const names = (data.character_lock?.characters || []).map((c) => c.name).filter(Boolean);
        setChronoResult({
          url: data.url,
          lockedNote: data.character_lock
            ? `Locked to ${names.length ? names.join(", ") : `${(data.character_lock.ref_images || []).length} reference image(s)`}`
            : undefined,
          refineNote: data.refine
            ? `${data.refine.generations} ${data.refine.generations === 1 ? "try" : "tries"}: ${
                data.refine.status === "accept" ? "passed the check"
                : data.refine.status === "accept_low" ? (data.refine.repaired ? "repaired" : "kept with low confidence")
                : data.refine.status === "needs_review" ? "still failing the check; best try kept — please review"
                : "could not be checked"
              }`
            : undefined,
        });
        await loadAssets();
      }
    } catch (error: any) {
      reportError({
        title: "ChronoFlow Image Generation Failed",
        message: error.message || "The character-locked generation job failed.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: error,
      });
    } finally {
      setChronoBusy(false);
    }
  };

  const handleOpenAssetModal = (assetToOpen: GeneratedAsset) => {
    setSelectedAssetForModal(assetToOpen);
    setIsModalOpen(true);
  };

  const loadAssets = useCallback(async () => {
    try {
      const result = await api.listGeneratedAssets(project.id);
      setAssets(result.assets);
    } catch {
      // Ignored if offline
    }
  }, [project.id]);

  useEffect(() => {
    // Load ComfyUI registry & assets
    Promise.all([api.listApprovedComfyWorkflows(), loadAssets()])
      .then(([registry]) => {
        setWorkflows(registry.workflows.filter((w) => w.available && w.purpose === "text_to_image"));
      })
      .catch((error: any) => {
        reportError({
          title: "Unable to Load ComfyUI Workflows",
          message: error.message || "The approved ComfyUI workflow registry could not be read.",
          severity: "warning",
          source: "pipeline",
          projectId: project.id,
          rawDetails: error,
        });
      })
      .finally(() => setComfyLoading(false));

    // Load Browser Bridge status
    api.getBrowserBridgeStatus()
      .then((st) => setBridgeStatus(st))
      .catch(() => {});
  }, [loadAssets, project.id, reportError]);

  const handleSelectPreset = (preset: typeof PRESETS[0]) => {
    setSelectedPreset(preset.id);
    if (preset.url) {
      setWebUrl(preset.url);
    }
  };

  const handleOpenBrowserSession = async () => {
    try {
      await api.openBrowserBridgeSession(webUrl || "https://chatgpt.com");
    } catch (err: any) {
      reportError({
        title: "Could Not Launch Browser Session",
        message: err.message || "Unable to open interactive browser session.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
      });
    }
  };

  const handleExecuteWebAI = async () => {
    if (!webUrl || !webPrompt.trim()) return;
    setWebSubmitting(true);
    setWebResult(null);
    setWebStep("Connecting to browser session...");

    try {
      setWebStep(`Navigating to ${webUrl}...`);
      const res = await api.executeBrowserBridgePrompt({
        url: webUrl,
        prompt: webPrompt,
        extract_type: extractType,
        project_id: project.id,
        headless,
        timeout_sec: 120.0,
      });
      setWebResult(res);
      await loadAssets();
    } catch (err: any) {
      reportError({
        title: "Web AI Prompt Execution Failed",
        message: err.message || "The browser AI interaction encountered an error.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setWebSubmitting(false);
      setWebStep(null);
    }
  };

  const handleComfyGenerate = async () => {
    setComfySubmitting(true);
    try {
      const queued = await api.generateComfyImage(project.id, {
        workflow_id: workflowId,
        prompt: comfyPrompt,
        negative_prompt: negativePrompt,
        width,
        height,
        seed,
      });
      const completed = await api.waitForWorkflowJob(queued.job_id, setActiveJob);
      setActiveJob(completed);
      await loadAssets();
    } catch (error: any) {
      reportError({
        title: "ComfyUI Image Generation Failed",
        message: error.message || "The image generation job failed.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobId: activeJob?.job_id,
        jobType: "COMFYUI_IMAGE_GENERATION",
        rawDetails: error,
      });
    } finally {
      setComfySubmitting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const latestAsset = assets[0];
  const progress = activeJob?.progress ?? 0;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs uppercase tracking-widest text-info font-semibold">AI Creation Studio</p>
            <Badge variant="neutral" className="text-[10px]">Playwright Connected</Badge>
          </div>
          <h1 className="text-2xl font-bold text-fg mt-0.5">Generate Original Images & Panels</h1>
          <p className="text-sm text-fg-dim">Project: {project.title}</p>
        </div>
        <Button variant="ghost" onClick={onBack}>
          <Icons.ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex border-b border-edge gap-2">
        <button
          type="button"
          onClick={() => setMode("web_ai")}
          className={`flex items-center gap-2 px-4 py-2.5 font-medium text-sm border-b-2 transition-colors ${
            mode === "web_ai"
              ? "border-accent text-info bg-accent/10 rounded-t-lg"
              : "border-transparent text-fg-dim hover:text-fg"
          }`}
        >
          <Icons.Globe className="w-4 h-4" />
          Web AI Browser Tool (ChatGPT, Gemini, Meta AI)
        </button>
        <button
          type="button"
          onClick={() => setMode("comfy_local")}
          className={`flex items-center gap-2 px-4 py-2.5 font-medium text-sm border-b-2 transition-colors ${
            mode === "comfy_local"
              ? "border-accent text-info bg-accent/10 rounded-t-lg"
              : "border-transparent text-fg-dim hover:text-fg"
          }`}
        >
          <Icons.Sparkles className="w-4 h-4" />
          Local ComfyUI Pipeline
        </button>
        <button
          type="button"
          onClick={() => setMode("chrono")}
          className={`flex items-center gap-2 px-4 py-2.5 font-medium text-sm border-b-2 transition-colors ${
            mode === "chrono"
              ? "border-accent text-info bg-accent/10 rounded-t-lg"
              : "border-transparent text-fg-dim hover:text-fg"
          }`}
        >
          🔒
          ChronoFlow Art (ref2image)
        </button>
      </div>

      {/* Mode 1: Web AI Browser Tool */}
      {mode === "web_ai" && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,460px)]">
          {/* Left: Input & Control Panel */}
          <Card className="p-5 space-y-5">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-fg-dim mb-2">
                1. Target AI Platform Preset
              </label>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSelectPreset(p)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                      selectedPreset === p.id
                        ? "bg-accent border-accent text-white shadow-sm"
                        : "bg-navy border-edge text-fg-dim hover:bg-flat"
                    }`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-fg-dim">
                  Target Website URL
                </label>
                <button
                  type="button"
                  onClick={handleOpenBrowserSession}
                  className="text-xs text-info hover:text-info flex items-center gap-1 font-medium underline"
                  title="Opens a visible browser with your persistent session profile so you can log into your account"
                >
                  Sign In / Manage Session ↗
                </button>
              </div>
              <input
                type="url"
                value={webUrl}
                onChange={(e) => setWebUrl(e.target.value)}
                placeholder="https://chatgpt.com or https://gemini.google.com"
                className="w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
                disabled={webSubmitting}
              />
              <p className="text-[11px] text-fg-faint mt-1">
                Your login cookies & session are saved persistently so future generations execute automatically.
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-fg-dim">
                  Prompt
                </label>
                <span className="text-[11px] text-fg-faint">{webPrompt.length} chars</span>
              </div>
              <textarea
                value={webPrompt}
                onChange={(e) => setWebPrompt(e.target.value)}
                rows={5}
                placeholder="Enter prompt for the AI to execute..."
                className="w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
                disabled={webSubmitting}
              />

              {/* Quick sample prompt chips */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="text-[11px] text-fg-faint self-center mr-1">Suggestions:</span>
                {SAMPLE_PROMPTS.map((sample, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setWebPrompt(sample)}
                    className="text-[11px] px-2 py-0.5 rounded bg-flat/80 text-fg-dim hover:bg-glass-hi border border-edge/60"
                  >
                    Sample {idx + 1}
                  </button>
                ))}
              </div>
            </div>

            {/* Execution Options */}
            <div className="grid grid-cols-2 gap-4 pt-1 border-t border-edge">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-fg-dim mb-1">
                  Extract Type
                </label>
                <select
                  value={extractType}
                  onChange={(e) => setExtractType(e.target.value as any)}
                  className="w-full rounded-lg border border-edge bg-navy px-3 py-1.5 text-xs text-fg"
                  disabled={webSubmitting}
                >
                  <option value="all">All (Images & Text Response)</option>
                  <option value="images">Images Only</option>
                  <option value="text">Text Response Only</option>
                </select>
              </div>

              <div className="flex items-center pt-5">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-fg-dim">
                  <input
                    type="checkbox"
                    checked={headless}
                    onChange={(e) => setHeadless(e.target.checked)}
                    className="rounded border-edge text-accent focus:ring-0"
                    disabled={webSubmitting}
                  />
                  <span>Run Headless (Background)</span>
                </label>
              </div>
            </div>

            {/* Live Progress Bar when executing */}
            {webSubmitting && (
              <div className="space-y-2 rounded-lg border border-accent/60 bg-accent/40 p-3">
                <div className="flex items-center justify-between text-xs text-info font-medium">
                  <span className="animate-pulse">{webStep || "Executing prompt on web tool..."}</span>
                  <Badge variant="neutral" className="text-[10px]">Processing</Badge>
                </div>
                <div className="w-full h-1.5 bg-flat rounded-full overflow-hidden">
                  <div className="h-full bg-accent animate-pulse rounded-full w-2/3" />
                </div>
              </div>
            )}

            {/* Submit Action */}
            <Button
              variant="primary"
              onClick={handleExecuteWebAI}
              disabled={webSubmitting || !webUrl || webPrompt.trim().length < 2}
              className="w-full justify-center py-2.5 font-semibold text-sm"
            >
              <Icons.Sparkles className="w-4 h-4 mr-2" />
              {webSubmitting ? "Executing & Extracting Results..." : "Execute Prompt on Web AI"}
            </Button>
          </Card>

          {/* Right: Extracted Result Panel */}
          <div className="space-y-4">
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-fg">Extracted Results</h2>
                {webResult && (
                  <Badge variant={webResult.success ? "success" : "danger"}>
                    {webResult.success ? `Done (${webResult.execution_time_sec}s)` : "Failed"}
                  </Badge>
                )}
              </div>

              {/* If webResult has error */}
              {webResult && !webResult.success && (
                <div className="p-3 bg-bad/50 border border-bad/40 rounded-lg text-xs text-bad space-y-1">
                  <p className="font-bold">Execution Error</p>
                  <p className="break-words">{webResult.error}</p>
                  <p className="text-fg-dim mt-2">
                    Tip: If login is required, click <span className="text-info font-medium">Sign In / Manage Session</span> above to log in to your account.
                  </p>
                </div>
              )}

              {/* Extracted Images Gallery */}
              {webResult && webResult.images && webResult.images.length > 0 && (
                <div className="space-y-3">
                  <p className="text-xs font-semibold text-fg-dim">
                    Generated Images ({webResult.images.length})
                  </p>
                  <div className="grid gap-3">
                    {webResult.images.map((img, i) => (
                      <div key={i} className="rounded-lg border border-edge bg-ink overflow-hidden space-y-2 p-2">
                        <img
                          src={img.url.startsWith("/api") ? api.resourceUrl(img.url) : img.url}
                          alt={`Extracted result ${i + 1}`}
                          className="w-full max-h-80 object-contain rounded bg-black/40"
                        />
                        <div className="flex items-center justify-between text-[11px] text-fg-dim px-1">
                          <span>{img.width} × {img.height} · {(img.byte_size / 1024).toFixed(0)} KB</span>
                          <span className="text-ok font-medium">Saved as Asset</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Extracted Text */}
              {webResult && webResult.text_response && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-fg-dim">Response Text</p>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(webResult.text_response)}
                      className="text-[11px] text-info hover:text-info underline"
                    >
                      {copiedText ? "Copied!" : "Copy Text"}
                    </button>
                  </div>
                  <div className="max-h-48 overflow-y-auto p-3 rounded-lg border border-edge bg-ink text-xs text-fg whitespace-pre-wrap font-sans leading-relaxed">
                    {webResult.text_response}
                  </div>
                </div>
              )}

              {/* Empty state when no result yet */}
              {!webResult && (
                <div className="min-h-64 rounded-lg border border-dashed border-edge flex flex-col items-center justify-center text-sm text-fg-faint text-center px-6 space-y-2">
                  <Icons.Globe className="w-8 h-8 text-fg-faint mb-1" />
                  <p className="font-medium text-fg-dim">No Web AI Output Yet</p>
                  <p className="text-xs text-fg-faint max-w-xs">
                    Choose a website, enter a prompt, and click execute. The tool will input the prompt, wait for generation, and collect the images & text here automatically.
                  </p>
                </div>
              )}
            </Card>

            {/* Existing Project Assets */}
            <Card className="p-4 space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-dim">Project Assets ({assets.length})</h3>
              {latestAsset ? (
                <div
                  onClick={() => handleOpenAssetModal(latestAsset)}
                  className="flex items-center gap-3 p-2 rounded-lg bg-navy border border-edge hover:border-accent cursor-pointer transition-all hover:scale-[1.01] active:scale-[0.99]"
                  title="Click to view full & inpaint"
                >
                  <img
                    src={api.getGeneratedAssetUrl(project.id, latestAsset.id)}
                    alt="Latest asset thumbnail"
                    className="w-12 h-12 object-cover rounded border border-edge bg-black"
                  />
                  <div className="text-xs text-fg-dim overflow-hidden flex-1">
                    <p className="text-fg font-medium truncate">{latestAsset.filename}</p>
                    <p>{latestAsset.width} × {latestAsset.height} · {latestAsset.asset_type}</p>
                  </div>
                  <span className="text-[11px] text-info font-medium pr-1">Edit ↗</span>
                </div>
              ) : (
                <p className="text-xs text-fg-faint">No previous project assets recorded.</p>
              )}
            </Card>
          </div>
        </div>
      )}

      {/* Mode 2: Local ComfyUI Pipeline */}
      {mode === "comfy_local" && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,420px)]">
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Approved workflow</h2>
              <Badge variant={workflows.length ? "success" : "danger"}>{workflows.length ? "READY" : "UNAVAILABLE"}</Badge>
            </div>
            <select
              value={workflowId}
              onChange={(event) => setWorkflowId(event.target.value)}
              className="w-full rounded-lg border border-edge bg-navy px-3 py-2 text-sm text-fg"
              disabled={comfyLoading || comfySubmitting}
            >
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>{workflow.id}</option>
              ))}
            </select>
            <label className="block text-sm text-fg-dim">
              Prompt
              <textarea value={comfyPrompt} onChange={(event) => setComfyPrompt(event.target.value)} rows={6} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg" disabled={comfySubmitting} />
            </label>
            <label className="block text-sm text-fg-dim">
              Negative prompt
              <textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg" disabled={comfySubmitting} />
            </label>
            <div className="grid grid-cols-3 gap-3">
              <label className="text-sm text-fg-dim">Width<input type="number" min={256} max={2048} value={width} onChange={(event) => setWidth(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm" disabled={comfySubmitting} /></label>
              <label className="text-sm text-fg-dim">Height<input type="number" min={256} max={2048} value={height} onChange={(event) => setHeight(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm" disabled={comfySubmitting} /></label>
              <label className="text-sm text-fg-dim">Seed<input type="number" min={0} value={seed} onChange={(event) => setSeed(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm" disabled={comfySubmitting} /></label>
            </div>
            {activeJob && (
              <div className="space-y-2 rounded-lg border border-edge bg-ink/60 p-3">
                <div className="flex justify-between text-xs text-fg-dim"><span>{activeJob.message || activeJob.status}</span><span>{Math.round(progress * 100)}%</span></div>
                <ProgressBar progress={progress} />
              </div>
            )}
            <Button variant="primary" onClick={handleComfyGenerate} disabled={comfySubmitting || !workflows.length || comfyPrompt.trim().length < 10}>
              <Icons.Sparkles className="w-4 h-4 mr-2" />
              {comfySubmitting ? "Generating..." : "Generate image with ComfyUI"}
            </Button>
          </Card>

          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Latest generated asset</h2>
              {latestAsset && (
                <button
                  type="button"
                  onClick={() => handleOpenAssetModal(latestAsset)}
                  className="text-xs text-info hover:text-info font-semibold flex items-center gap-1 hover:underline active:scale-95 transition-all"
                >
                  <Icons.Sparkles className="w-3.5 h-3.5" />
                  <span>Open Inpainter & Studio ↗</span>
                </button>
              )}
            </div>
            {latestAsset ? (
              <>
                <div
                  onClick={() => handleOpenAssetModal(latestAsset)}
                  className="group relative cursor-pointer overflow-hidden rounded-xl border border-edge bg-ink transition-all duration-200 hover:border-accent hover:shadow-2xl hover:shadow-accent/25 active:scale-[0.99]"
                  title="Click to view full image, brush mask & inpaint"
                >
                  <img
                    src={api.getGeneratedAssetUrl(project.id, latestAsset.id)}
                    alt="Latest generated manga asset"
                    className="w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
                  />
                  {/* Animated Hover Overlay with Glass Effect */}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-all duration-200 flex flex-col items-center justify-center gap-2.5 p-4 text-center backdrop-blur-[2px]">
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-accent to-accent text-white flex items-center justify-center shadow-lg shadow-accent/40 transform group-hover:scale-110 transition-transform duration-200">
                      <Icons.Sparkles className="w-6 h-6 animate-pulse" />
                    </div>
                    <p className="text-sm font-bold text-white drop-shadow">Click to Open Full View & Inpaint</p>
                    <p className="text-xs text-fg-dim max-w-xs drop-shadow">
                      Dual-layer brush masking, instant inpainting with Qwen 2.1 Turbo, outfit and prompt presets
                    </p>
                  </div>
                </div>
                <div className="text-xs text-fg-dim space-y-1">
                  <p>{latestAsset.width} × {latestAsset.height} · {latestAsset.byte_size.toLocaleString()} bytes</p>
                  <p className="font-mono break-all">SHA-256: {latestAsset.sha256}</p>
                  <p>Asset status: <span className="text-ok">{latestAsset.status}</span></p>
                </div>

                {/* Project Assets Bin Reel */}
                {assets.length > 1 && (
                  <div className="space-y-2 pt-2 border-t border-edge/80">
                    <div className="flex items-center justify-between text-xs text-fg-dim">
                      <span className="font-semibold uppercase tracking-wider">Project Assets ({assets.length})</span>
                      <span className="text-[11px] text-fg-faint">Click any asset to edit</span>
                    </div>
                    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
                      {assets.map((item) => (
                        <div
                          key={item.id}
                          onClick={() => handleOpenAssetModal(item)}
                          className={`shrink-0 w-16 h-20 rounded-lg overflow-hidden border cursor-pointer transition-all hover:scale-105 active:scale-95 ${
                            item.id === latestAsset.id
                              ? "border-accent ring-2 ring-accent/40 shadow-md"
                              : "border-edge hover:border-edge opacity-70 hover:opacity-100"
                          }`}
                          title={`${item.filename} (${item.width}x${item.height})`}
                        >
                          <img
                            src={api.getGeneratedAssetUrl(project.id, item.id)}
                            alt={item.filename}
                            className="w-full h-full object-cover bg-black"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="min-h-64 rounded-lg border border-dashed border-edge flex items-center justify-center text-sm text-fg-faint text-center px-6">
                Generated assets will appear here after verification.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Mode 3: ChronoFlow character-locked generation (§16 parity) */}
      {mode === "chrono" && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,420px)]">
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Generation type</h2>
              <Badge variant="success">QWEN IMAGE 2.1</Badge>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {([
                { t: "text2img", icon: "✍️", name: "Text → Image", desc: "Pure prompt, no references" },
                { t: "charlock", icon: "🔒", name: "Character-Locked", desc: "ref2image from vault sheets" },
                { t: "refupload", icon: "🖼️", name: "Custom Reference", desc: "ref2image with uploads" },
              ] as const).map((opt) => (
                <button
                  key={opt.t}
                  type="button"
                  onClick={() => setChronoType(opt.t)}
                  className={`rounded-lg border p-3 text-center transition-all ${
                    chronoType === opt.t
                      ? "border-accent bg-accent/10 shadow-sm"
                      : "border-edge bg-navy/60 hover:border-fg-faint"
                  }`}
                >
                  <div className="text-lg">{opt.icon}</div>
                  <div className={`text-xs font-bold mt-1 ${chronoType === opt.t ? "text-info" : "text-fg"}`}>{opt.name}</div>
                  <div className="text-[10px] text-fg-faint mt-0.5 leading-tight">{opt.desc}</div>
                </button>
              ))}
            </div>

            <label className="block text-sm text-fg-dim">
              ✅ Positive prompt
              <textarea value={chronoPrompt} onChange={(e) => setChronoPrompt(e.target.value)} rows={5} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg" disabled={chronoBusy} />
            </label>
            <label className="block text-sm text-fg-dim">
              🚫 Negative prompt
              <textarea value={chronoNegative} onChange={(e) => setChronoNegative(e.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg" disabled={chronoBusy} />
            </label>

            {chronoType === "charlock" && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-fg-dim">🔒 Character Lock (max 4)</label>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-info border border-accent/30 font-semibold">
                    {chronoLockedIds.length ? `${chronoLockedIds.length} locked` : "off"}
                  </span>
                </div>
                {chronoVault.length ? (
                  <>
                    <div className="flex flex-wrap gap-2">
                      {chronoVault.map((c) => {
                        const on = chronoLockedIds.includes(c.id);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            title={`${c.name} — ${c.role}`}
                            onClick={() => toggleChronoLock(c.id)}
                            className={`relative w-12 h-12 rounded-lg overflow-hidden border-2 transition-all ${
                              on ? "border-accent scale-105" : "border-edge hover:border-edge"
                            }`}
                          >
                            <img src={api.resourceUrl(`/inputs/${c.image}`)} alt={c.name} className="w-full h-full object-cover" />
                            {on && (
                              <span className="absolute bottom-0 right-0 w-4 h-4 bg-accent rounded-tl flex items-center justify-center text-white text-[9px]">✓</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-[10px] text-fg-faint mt-1">Generated faces follow the selected approved sheets (max 4). Never generate a character's face unlocked.</p>
                  </>
                ) : (
                  <p className="text-[11px] text-fg-faint">Character Vault is empty or unreachable — add reference sheets in the ChronoFlow Studio vault first.</p>
                )}
              </div>
            )}

            {chronoType === "refupload" && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-fg-dim">🖼️ Reference images</label>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-info border border-accent/30 font-semibold">
                    {chronoRefs.length}/4
                  </span>
                </div>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={(e) => { handleChronoRefUpload(e.target.files); e.target.value = ""; }}
                  className="block w-full text-xs text-fg-dim file:mr-3 file:rounded-lg file:border-0 file:bg-flat file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-fg hover:file:bg-glass-hi"
                  disabled={chronoBusy}
                />
                {chronoRefs.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {chronoRefs.map((fn, i) => (
                      <div key={fn} className="relative w-12 h-12 rounded-lg overflow-hidden border-2 border-edge">
                        <img src={api.resourceUrl(`/chronoflow/inputs/${fn}`)} alt={fn} className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setChronoRefs((prev) => prev.filter((_, idx) => idx !== i))}
                          title="Remove"
                          className="absolute bottom-0 right-0 w-4 h-4 bg-bad rounded-tl flex items-center justify-center text-white text-[9px]"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-fg-faint mt-1">Upload 1–4 reference images (faces, sheets, style frames) — identity follows them.</p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 pt-1 border-t border-edge">
              <label className="text-sm text-fg-dim">
                Aspect ratio
                <select value={chronoAspect} onChange={(e) => setChronoAspect(e.target.value)} className="mt-1 w-full rounded-lg border border-edge bg-navy px-3 py-2 text-sm text-fg" disabled={chronoBusy}>
                  <option value="1344x768">16:9 Landscape (1344×768)</option>
                  <option value="768x1344">9:16 Portrait (768×1344)</option>
                  <option value="1024x1024">1:1 Square (1024×1024)</option>
                </select>
              </label>
              <label className="text-sm text-fg-dim">
                Seed <span className="text-fg-faint text-xs">(optional)</span>
                <input type="number" min={0} value={chronoSeed} onChange={(e) => setChronoSeed(e.target.value)} placeholder="Random" className="mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm" disabled={chronoBusy} />
              </label>
            </div>
            <label className="flex items-center gap-2 text-xs text-fg-dim cursor-pointer">
              <input type="checkbox" checked={chronoRefine} onChange={(e) => setChronoRefine(e.target.checked)} className="rounded border-edge text-accent focus:ring-0" disabled={chronoBusy} />
              <span>🛠️ Auto-Refine — AI reviews the picture, then repairs or redraws it (slower)</span>
            </label>

            {chronoBusy && (
              <div className="space-y-2 rounded-lg border border-accent/60 bg-accent/40 p-3">
                <div className="flex items-center justify-between text-xs text-info font-medium">
                  <span className="animate-pulse">Generating with Qwen Image 2.1{chronoType !== "text2img" ? " (reference-locked)" : ""}...</span>
                  <Badge variant="neutral" className="text-[10px]">9–25s typical</Badge>
                </div>
                <div className="w-full h-1.5 bg-flat rounded-full overflow-hidden">
                  <div className="h-full bg-accent animate-pulse rounded-full w-2/3" />
                </div>
              </div>
            )}

            <Button variant="primary" onClick={handleChronoGenerate} disabled={chronoBusy || chronoPrompt.trim().length < 5} className="w-full justify-center py-2.5 font-semibold text-sm">
              <Icons.Sparkles className="w-4 h-4 mr-2" />
              {chronoBusy ? "Generating..." : "✨ Generate"}
            </Button>
          </Card>

          <Card className="p-5 space-y-4">
            <h2 className="font-semibold text-fg">Result</h2>
            {chronoResult ? (
              <div className="space-y-3">
                <img src={api.resourceUrl(chronoResult.url)} alt="Generated result" className="w-full rounded-xl border border-edge bg-black/40 object-contain" />
                {chronoResult.lockedNote && (
                  <p className="text-[11px] text-info bg-accent/10 border border-accent/30 rounded-lg px-3 py-2">🔒 {chronoResult.lockedNote}</p>
                )}
                {chronoResult.refineNote && (
                  <p className="text-[11px] text-ok bg-ok/10 border border-ok/30 rounded-lg px-3 py-2">🛠️ Auto-refine: {chronoResult.refineNote}</p>
                )}
                {latestAsset && (
                  <button
                    type="button"
                    onClick={() => handleOpenAssetModal(latestAsset)}
                    className="text-xs text-info hover:text-info font-semibold flex items-center gap-1 hover:underline"
                  >
                    <Icons.Sparkles className="w-3.5 h-3.5" />
                    <span>Open Inpainter &amp; Studio ↗</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="min-h-64 rounded-lg border border-dashed border-edge flex flex-col items-center justify-center text-sm text-fg-faint text-center px-6 space-y-2">
                <span className="text-2xl">🔒</span>
                <p className="font-medium text-fg-dim">No Character-Locked Output Yet</p>
                <p className="text-xs text-fg-faint max-w-xs">
                  Pick a generation type, write the positive/negative prompt, choose references if applicable, and generate. Results appear here and join the project assets.
                </p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Interactive Full-Image Editor & Inpainter Modal */}
      <ImageEditorModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        projectId={project.id}
        asset={selectedAssetForModal}
        onAssetUpdated={(newAsset) => {
          loadAssets();
          setSelectedAssetForModal(newAsset);
        }}
      />
    </div>
  );
};
