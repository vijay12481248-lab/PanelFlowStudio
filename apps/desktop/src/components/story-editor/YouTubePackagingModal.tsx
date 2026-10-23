import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { ComfyWorkflowInfo, GeneratedAsset } from "@panelflow/api-client";
import type { Job, Project, YouTubePackagingData } from "@panelflow/shared-types";
import { Badge, Button, Card, Icons, ProgressBar } from "@panelflow/ui";

export interface YouTubePackagingModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  profileName?: string;
}

export const YouTubePackagingModal: React.FC<YouTubePackagingModalProps> = ({
  isOpen,
  onClose,
  project,
  profileName,
}) => {
  const [activeTab, setActiveTab] = useState<"thumbnail" | "metadata">("thumbnail");
  const [loading, setLoading] = useState<boolean>(true);
  const [packaging, setPackaging] = useState<YouTubePackagingData | null>(null);
  const [workflows, setWorkflows] = useState<ComfyWorkflowInfo[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>("manga_image_generation");

  // Editable Research State
  const [selectedTitle, setSelectedTitle] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [tagsString, setTagsString] = useState<string>("");
  const [aspectRatio, setAspectRatio] = useState<"16:9" | "9:16" | "1:1">("16:9");
  const [thumbWidth, setThumbWidth] = useState<number>(1280);
  const [thumbHeight, setThumbHeight] = useState<number>(720);
  const [prompt, setPrompt] = useState<string>("");
  const [negativePrompt, setNegativePrompt] = useState<string>("");
  const [seed, setSeed] = useState<number>(20261023);
  const [styleTone, setStyleTone] = useState<"dramatic" | "action" | "mysterious" | "hype" | "emotional">("dramatic");
  const [customHook, setCustomHook] = useState<string>("");
  const [regeneratingResearch, setRegeneratingResearch] = useState<boolean>(false);

  // ComfyUI Generation State
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [generating, setGenerating] = useState<boolean>(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [generatedAssets, setGeneratedAssets] = useState<GeneratedAsset[]>([]);
  const [previewOverlay, setPreviewOverlay] = useState<boolean>(true);

  // Copy Feedback State
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const copyTimerRef = React.useRef<any>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopiedKey(null), 2000);
  };

  const loadPackaging = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const data = await api.getYoutubePackaging(project.id, refresh, profileName);
      setPackaging(data);
      setSelectedTitle(data.selected_title || data.titles[0] || project.title);
      setDescription(data.description);
      setTagsString(data.tags_string);
      setAspectRatio(data.thumbnail.aspect_ratio);
      setThumbWidth(data.thumbnail.recommended_width);
      setThumbHeight(data.thumbnail.recommended_height);
      setPrompt(data.thumbnail.prompt);
      setNegativePrompt(data.thumbnail.negative_prompt);
      setSeed(data.thumbnail.seed);
      if (data.thumbnail.workflow_id) setSelectedWorkflow(data.thumbnail.workflow_id);
    } catch (err) {
      console.error("Failed to load YouTube packaging:", err);
    } finally {
      setLoading(false);
    }
  }, [project.id, project.title, profileName]);

  const loadAssetsAndWorkflows = useCallback(async () => {
    try {
      const [registry, assetsRes] = await Promise.all([
        api.listApprovedComfyWorkflows(),
        api.listGeneratedAssets(project.id),
      ]);
      setWorkflows(registry.workflows.filter((w) => w.purpose === "text_to_image"));
      setGeneratedAssets(assetsRes.assets);
    } catch (err) {
      console.warn("Could not load ComfyUI workflows or assets:", err);
    }
  }, [project.id]);

  useEffect(() => {
    if (isOpen) {
      loadPackaging();
      loadAssetsAndWorkflows();
    }
  }, [isOpen, loadPackaging, loadAssetsAndWorkflows]);

  if (!isOpen) return null;

  const handleAspectRatioChange = (ratio: "16:9" | "9:16" | "1:1") => {
    setAspectRatio(ratio);
    if (ratio === "16:9") {
      setThumbWidth(1280);
      setThumbHeight(720);
    } else if (ratio === "9:16") {
      setThumbWidth(720);
      setThumbHeight(1280);
    } else {
      setThumbWidth(1024);
      setThumbHeight(1024);
    }
  };

  const handleRegenerateResearch = async () => {
    setRegeneratingResearch(true);
    try {
      const data = await api.generateYoutubePackaging(project.id, {
        profile_name: profileName || (aspectRatio === "9:16" ? "vertical_shorts" : "standard_1080p"),
        style_tone: styleTone,
        custom_hook: customHook || undefined,
      });
      setPackaging(data);
      setSelectedTitle(data.selected_title || data.titles[0]);
      setDescription(data.description);
      setTagsString(data.tags_string);
      setPrompt(data.thumbnail.prompt);
      setNegativePrompt(data.thumbnail.negative_prompt);
      setSeed(data.thumbnail.seed);
    } catch (err: any) {
      console.error("Regenerate research failed:", err);
    } finally {
      setRegeneratingResearch(false);
    }
  };

  const handleGenerateThumbnail = async () => {
    setGenerating(true);
    setGenerationError(null);
    try {
      const queued = await api.generateComfyImage(project.id, {
        workflow_id: selectedWorkflow,
        prompt,
        negative_prompt: negativePrompt,
        width: thumbWidth,
        height: thumbHeight,
        seed,
      });

      const completed = await api.waitForWorkflowJob(queued.job_id, setActiveJob);
      setActiveJob(completed);
      const updatedAssets = await api.listGeneratedAssets(project.id);
      setGeneratedAssets(updatedAssets.assets);
    } catch (err: any) {
      console.error("ComfyUI thumbnail generation failed:", err);
      setGenerationError(err?.message || "ComfyUI generation failed. Ensure ComfyUI is running.");
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyAllMetadata = () => {
    const fullText = `=== YOUTUBE VIDEO TITLE ===\n${selectedTitle}\n\n=== DESCRIPTION ===\n${description}\n\n=== TAGS ===\n${tagsString}\n\n=== HASHTAGS ===\n${packaging?.hashtags_string || ""}\n\n=== COMFYUI THUMBNAIL PROMPT ===\nPositive:\n${prompt}\n\nNegative:\n${negativePrompt}`;
    copyToClipboard(fullText, "all_metadata");
  };

  const latestThumbAsset = generatedAssets[0];
  const progressPercent = Math.round((activeJob?.progress ?? 0) * 100);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-label="YouTube Packaging and Thumbnail Studio"
    >
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-red-600 to-rose-700 flex items-center justify-center text-white shadow-md shadow-red-600/30">
              <Icons.Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                YouTube Packaging & ComfyUI Thumbnail Studio
                <Badge variant="accent" className="text-[10px]">AI RESEARCH</Badge>
              </h2>
              <p className="text-xs text-zinc-400">
                SEO titles, description with chapter timestamps, tags, and AI thumbnail generation for <span className="text-zinc-200 font-medium">{project.title}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCopyAllMetadata}
              className="text-xs flex items-center gap-1.5 border-zinc-700 hover:border-zinc-500"
            >
              {copiedKey === "all_metadata" ? (
                <>
                  <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400 font-bold">Copied All!</span>
                </>
              ) : (
                <>
                  <Icons.Copy className="w-3.5 h-3.5" />
                  <span>Copy Full Packaging</span>
                </>
              )}
            </Button>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
              aria-label="Close dialog"
            >
              <Icons.X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 pt-3 border-b border-zinc-800/80 bg-zinc-900/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("thumbnail")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 font-medium text-xs transition-colors ${
                activeTab === "thumbnail"
                  ? "border-indigo-500 text-indigo-400 font-bold"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Icons.Sparkles className="w-4 h-4" />
              <span>ComfyUI Thumbnail Studio</span>
              {latestThumbAsset && <span className="w-2 h-2 rounded-full bg-emerald-400" />}
            </button>
            <button
              onClick={() => setActiveTab("metadata")}
              className={`flex items-center gap-2 px-4 py-2 border-b-2 font-medium text-xs transition-colors ${
                activeTab === "metadata"
                  ? "border-indigo-500 text-indigo-400 font-bold"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Icons.Film className="w-4 h-4" />
              <span>YouTube Title, Description & Tags</span>
            </button>
          </div>

          <div className="flex items-center gap-2 pb-2">
            <Badge variant="neutral" className="text-[10px] font-mono">
              {aspectRatio} ({thumbWidth}×{thumbHeight})
            </Badge>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3">
              <Icons.Refresh className="w-8 h-8 text-indigo-400 animate-spin" />
              <p className="text-xs text-zinc-400">Researching video metadata and thumbnail art...</p>
            </div>
          ) : activeTab === "thumbnail" ? (
            /* TAB 1: THUMBNAIL STUDIO */
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: ComfyUI Configuration & Prompts (7 cols) */}
              <div className="lg:col-span-7 space-y-4">
                {/* Aspect Ratio & Format Controls */}
                <div className="bg-zinc-900/60 p-3.5 rounded-xl border border-zinc-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                      <Icons.Layers className="w-3.5 h-3.5 text-indigo-400" />
                      Thumbnail Format & Dimensions
                    </span>
                    <span className="text-[10px] text-zinc-400 font-mono">Must be multiple of 8</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => handleAspectRatioChange("16:9")}
                      className={`p-2.5 rounded-lg border text-left transition-all ${
                        aspectRatio === "16:9"
                          ? "border-indigo-500 bg-indigo-950/40 text-white"
                          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700"
                      }`}
                    >
                      <div className="font-bold text-xs">16:9 Landscape</div>
                      <div className="text-[10px] text-zinc-400 font-mono">1280 × 720 (Standard)</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleAspectRatioChange("9:16")}
                      className={`p-2.5 rounded-lg border text-left transition-all ${
                        aspectRatio === "9:16"
                          ? "border-indigo-500 bg-indigo-950/40 text-white"
                          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700"
                      }`}
                    >
                      <div className="font-bold text-xs">9:16 Vertical</div>
                      <div className="text-[10px] text-zinc-400 font-mono">720 × 1280 (Shorts)</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleAspectRatioChange("1:1")}
                      className={`p-2.5 rounded-lg border text-left transition-all ${
                        aspectRatio === "1:1"
                          ? "border-indigo-500 bg-indigo-950/40 text-white"
                          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700"
                      }`}
                    >
                      <div className="font-bold text-xs">1:1 Square</div>
                      <div className="text-[10px] text-zinc-400 font-mono">1024 × 1024</div>
                    </button>
                  </div>

                  {/* Workflow Selector */}
                  <div className="flex items-center justify-between pt-1 text-xs">
                    <span className="text-zinc-400">ComfyUI Workflow:</span>
                    <select
                      value={selectedWorkflow}
                      onChange={(e) => setSelectedWorkflow(e.target.value)}
                      className="bg-zinc-950 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200"
                      disabled={generating}
                    >
                      {workflows.length > 0 ? (
                        workflows.map((wf) => (
                          <option key={wf.id} value={wf.id}>
                            {wf.id} {wf.available ? "✓" : "(unverified)"}
                          </option>
                        ))
                      ) : (
                        <option value="manga_image_generation">manga_image_generation (default)</option>
                      )}
                    </select>
                  </div>
                </div>

                {/* ComfyUI Positive Prompt */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
                      <Icons.Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                      ComfyUI Thumbnail Prompt
                    </label>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(prompt, "prompt")}
                      className="text-[11px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                    >
                      {copiedKey === "prompt" ? (
                        <>
                          <Icons.Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Icons.Copy className="w-3 h-3" />
                          <span>Copy Prompt</span>
                        </>
                      )}
                    </button>
                  </div>
                  <textarea
                    rows={4}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    disabled={generating}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-xs text-zinc-200 font-mono focus:border-indigo-500 focus:outline-none"
                    placeholder="Anime thumbnail prompt..."
                  />
                </div>

                {/* ComfyUI Negative Prompt */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-zinc-400">
                      Negative Prompt (Removes Text, Watermarks, Distortion)
                    </label>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(negativePrompt, "negative_prompt")}
                      className="text-[11px] text-zinc-400 hover:text-zinc-300 flex items-center gap-1"
                    >
                      {copiedKey === "negative_prompt" ? (
                        <>
                          <Icons.Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Icons.Copy className="w-3 h-3" />
                          <span>Copy Negative</span>
                        </>
                      )}
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    disabled={generating}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-2.5 text-xs text-zinc-300 font-mono focus:border-indigo-500 focus:outline-none"
                  />
                </div>

                {/* Seed and Hook Tags Row */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800 flex items-center justify-between">
                    <span className="text-xs text-zinc-400 font-medium">Seed:</span>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="number"
                        value={seed}
                        onChange={(e) => setSeed(Number(e.target.value))}
                        disabled={generating}
                        className="w-24 bg-zinc-950 border border-zinc-700 rounded px-2 py-0.5 text-xs font-mono text-zinc-200"
                      />
                      <button
                        type="button"
                        onClick={() => setSeed(Math.floor(Math.random() * 2000000000))}
                        disabled={generating}
                        className="px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-[10px] text-zinc-200 font-medium"
                      >
                        Dice
                      </button>
                    </div>
                  </div>

                  <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800 flex items-center justify-between">
                    <span className="text-xs text-zinc-400 font-medium">Mock Overlay:</span>
                    <button
                      type="button"
                      onClick={() => setPreviewOverlay(!previewOverlay)}
                      className={`px-2.5 py-0.5 rounded text-xs font-medium transition-colors ${
                        previewOverlay ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      {previewOverlay ? "YouTube Frame ON" : "Off"}
                    </button>
                  </div>
                </div>

                {/* Click-to-copy Hook Text Badges */}
                {packaging?.thumbnail?.text_hooks && packaging.thumbnail.text_hooks.length > 0 && (
                  <div className="space-y-1.5 bg-zinc-900/40 p-3 rounded-xl border border-zinc-800/80">
                    <span className="text-[11px] font-semibold text-zinc-300 block">
                      Recommended Thumbnail Text Hooks (Click to copy hook):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {packaging.thumbnail.text_hooks.map((hook, hIdx) => (
                        <button
                          key={hIdx}
                          type="button"
                          onClick={() => copyToClipboard(hook, `hook_${hIdx}`)}
                          className="px-2.5 py-1 rounded-md bg-zinc-950 hover:bg-indigo-950 border border-zinc-800 hover:border-indigo-600 text-xs font-bold text-yellow-400 transition-all flex items-center gap-1"
                        >
                          {copiedKey === `hook_${hIdx}` ? (
                            <Icons.Check className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <span>{hook}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Generate Button & Progress */}
                <div className="pt-2">
                  <Button
                    variant="primary"
                    size="md"
                    onClick={handleGenerateThumbnail}
                    disabled={generating || !prompt.trim()}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 text-sm shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2"
                  >
                    {generating ? (
                      <>
                        <Icons.Refresh className="w-4 h-4 animate-spin" />
                        <span>Generating Thumbnail in ComfyUI... ({progressPercent}%)</span>
                      </>
                    ) : (
                      <>
                        <Icons.Sparkles className="w-4 h-4" />
                        <span>Generate Thumbnail with ComfyUI</span>
                      </>
                    )}
                  </Button>

                  {generating && (
                    <div className="mt-3 space-y-1">
                      <ProgressBar progress={(activeJob?.progress ?? 0)} />
                      <div className="flex justify-between text-[11px] text-zinc-400 font-mono">
                        <span>{activeJob?.message || "Submitting to ComfyUI..."}</span>
                        <span>{progressPercent}%</span>
                      </div>
                    </div>
                  )}

                  {generationError && (
                    <div className="mt-3 p-3 rounded-xl bg-rose-950/40 border border-rose-800 text-xs text-rose-300 flex items-center gap-2">
                      <Icons.AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>{generationError}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Live Thumbnail & YouTube Card Preview (5 cols) */}
              <div className="lg:col-span-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-zinc-200 uppercase tracking-wider">
                    Thumbnail Preview
                  </span>
                  {latestThumbAsset && (
                    <a
                      href={api.getGeneratedAssetUrl(project.id, latestThumbAsset.id)}
                      download={`thumbnail-${project.id}.png`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                    >
                      <Icons.Download className="w-3.5 h-3.5" />
                      Download PNG
                    </a>
                  )}
                </div>

                <div className="bg-black rounded-2xl border border-zinc-800 overflow-hidden shadow-2xl relative group">
                  {latestThumbAsset ? (
                    <div
                      className={`relative w-full ${
                        aspectRatio === "9:16" ? "aspect-[9/16] max-h-[440px]" : "aspect-video"
                      } bg-zinc-950 flex items-center justify-center overflow-hidden`}
                    >
                      <img
                        src={api.getGeneratedAssetUrl(project.id, latestThumbAsset.id)}
                        alt="Generated YouTube Thumbnail"
                        className="w-full h-full object-cover"
                      />

                      {/* YouTube Card UI Mock Overlay */}
                      {previewOverlay && (
                        <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-3">
                          {/* Top Hook Text (if any) */}
                          <div className="flex justify-start">
                            <span className="bg-yellow-400 text-black font-extrabold px-2 py-0.5 text-xs rounded uppercase tracking-wider shadow-md transform -rotate-1">
                              {packaging?.thumbnail?.text_hooks?.[0] || "NEW EPISODE"}
                            </span>
                          </div>

                          {/* Bottom Right Duration Badge */}
                          <div className="flex justify-end">
                            <span className="bg-black/85 text-white font-mono text-[11px] font-bold px-1.5 py-0.5 rounded shadow">
                              0:24
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div
                      className={`w-full ${
                        aspectRatio === "9:16" ? "aspect-[9/16] max-h-[440px]" : "aspect-video"
                      } bg-zinc-950 border-2 border-dashed border-zinc-800 flex flex-col items-center justify-center p-6 text-center space-y-2`}
                    >
                      <div className="w-12 h-12 rounded-2xl bg-zinc-900 flex items-center justify-center text-zinc-500">
                        <Icons.Sparkles className="w-6 h-6" />
                      </div>
                      <p className="text-xs font-semibold text-zinc-300">No thumbnail generated yet</p>
                      <p className="text-[11px] text-zinc-500 max-w-xs">
                        Click "Generate Thumbnail with ComfyUI" to generate a high-CTR visual for your video.
                      </p>
                    </div>
                  )}

                  {/* YouTube Card Metadata Simulation */}
                  {previewOverlay && (
                    <div className="p-3 bg-zinc-950 border-t border-zinc-800/80 flex items-start gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
                        PF
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold text-zinc-100 line-clamp-2 leading-tight">
                          {selectedTitle || project.title}
                        </p>
                        <p className="text-[10px] text-zinc-400 mt-0.5">
                          PanelFlow Studio · 12K views · 2 hours ago
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Composition Guidance */}
                {packaging?.thumbnail?.composition_guidance && (
                  <div className="p-3 bg-zinc-900/40 border border-zinc-800 rounded-xl space-y-1 text-xs text-zinc-400">
                    <span className="font-semibold text-zinc-300 flex items-center gap-1">
                      <Icons.CheckCircle className="w-3.5 h-3.5 text-indigo-400" />
                      Thumbnail CTR Strategy
                    </span>
                    <p className="text-[11px] leading-relaxed">
                      {packaging.thumbnail.composition_guidance}
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* TAB 2: YOUTUBE METADATA (TITLE, DESCRIPTION, TAGS) */
            <div className="space-y-6">
              {/* Titles Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Icons.Film className="w-4 h-4 text-indigo-400" />
                    Researched Video Titles (High CTR)
                  </h3>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(selectedTitle, "title")}
                    className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                  >
                    {copiedKey === "title" ? (
                      <>
                        <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied Title!</span>
                      </>
                    ) : (
                      <>
                        <Icons.Copy className="w-3.5 h-3.5" />
                        <span>Copy Selected Title</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {packaging?.titles.map((titleOption, tIdx) => (
                    <button
                      key={tIdx}
                      type="button"
                      onClick={() => setSelectedTitle(titleOption)}
                      className={`p-3 rounded-xl border text-left transition-all flex items-start gap-2.5 ${
                        selectedTitle === titleOption
                          ? "border-indigo-500 bg-indigo-950/40 text-white shadow-sm"
                          : "border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700"
                      }`}
                    >
                      <span className="w-5 h-5 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-300 shrink-0 mt-0.5">
                        {tIdx + 1}
                      </span>
                      <span className="text-xs font-medium leading-snug">{titleOption}</span>
                    </button>
                  ))}
                </div>

                {/* Custom Edit Title */}
                <input
                  type="text"
                  value={selectedTitle}
                  onChange={(e) => setSelectedTitle(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2 text-xs font-medium text-zinc-100 focus:border-indigo-500 focus:outline-none"
                  placeholder="Custom title..."
                />
              </div>

              {/* Description Section with Chapters */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Icons.FileText className="w-4 h-4 text-indigo-400" />
                    YouTube Description (With Timestamps & CTA)
                  </h3>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(description, "description")}
                    className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                  >
                    {copiedKey === "description" ? (
                      <>
                        <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied Description!</span>
                      </>
                    ) : (
                      <>
                        <Icons.Copy className="w-3.5 h-3.5" />
                        <span>Copy Description</span>
                      </>
                    )}
                  </button>
                </div>
                <textarea
                  rows={9}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-xs text-zinc-200 font-mono focus:border-indigo-500 focus:outline-none leading-relaxed"
                />
              </div>

              {/* Video Tags Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Icons.Sparkles className="w-4 h-4 text-indigo-400" />
                    YouTube SEO Tags (Paste into YouTube Studio)
                  </h3>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(tagsString, "tags")}
                    className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                  >
                    {copiedKey === "tags" ? (
                      <>
                        <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied Tags!</span>
                      </>
                    ) : (
                      <>
                        <Icons.Copy className="w-3.5 h-3.5" />
                        <span>Copy Tags</span>
                      </>
                    )}
                  </button>
                </div>

                <textarea
                  rows={3}
                  value={tagsString}
                  onChange={(e) => setTagsString(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-xs text-zinc-200 font-mono focus:border-indigo-500 focus:outline-none"
                  placeholder="tag1, tag2, tag3..."
                />

                {/* Tag Chips */}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {packaging?.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 font-mono"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              {/* Regenerate Research Controls */}
              <div className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-3">
                <span className="text-xs font-semibold text-zinc-200 block">
                  Regenerate Research with Custom Tone or Hook
                </span>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-[11px] text-zinc-400 block mb-1">Tone & Pacing:</label>
                    <select
                      value={styleTone}
                      onChange={(e) => setStyleTone(e.target.value as any)}
                      className="w-full bg-zinc-950 border border-zinc-700 rounded-lg p-2 text-xs text-zinc-200"
                    >
                      <option value="dramatic">Dramatic / Cinematic</option>
                      <option value="action">High-Octane Action</option>
                      <option value="mysterious">Dark Mystery / Secret</option>
                      <option value="hype">Hype / Viral Climax</option>
                      <option value="emotional">Emotional / Character Drama</option>
                    </select>
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-[11px] text-zinc-400 block mb-1">Custom Clickbait Hook / Keyword:</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={customHook}
                        onChange={(e) => setCustomHook(e.target.value)}
                        placeholder="e.g. WAIT FOR IT, HE AWAKENED, UNFORGIVABLE"
                        className="flex-1 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleRegenerateResearch}
                        disabled={regeneratingResearch}
                        className="text-xs shrink-0"
                      >
                        {regeneratingResearch ? "Researching..." : "Regenerate"}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span>All metadata and prompts are saved into project workspace.</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onClose} className="text-xs">
              Close
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCopyAllMetadata}
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-4 text-xs"
            >
              {copiedKey === "all_metadata" ? "Copied All!" : "Copy Full Release Packaging"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
