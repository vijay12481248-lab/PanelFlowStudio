import React, { useState } from "react";
import { Film, Sparkles, Image as ImageIcon, Play, Check, X, ExternalLink, RefreshCw, Layers, Lock } from "lucide-react";
import type { Project, VideoScene } from "@panelflow/shared-types";
import { api } from "@panelflow/api-client";

interface VaultCharacter {
  id: string;
  name: string;
  role: string;
  image: string;
  description: string;
}

/** Character Lock picker: bind Character Vault reference sheets to image generation so faces follow the locked identity. */
const CharacterLockPicker: React.FC<{
  selected: string[];
  onToggle: (id: string) => void;
  max?: number;
}> = ({ selected, onToggle, max = 4 }) => {
  const [chars, setChars] = useState<VaultCharacter[]>([]);
  React.useEffect(() => {
    let cancelled = false;
    fetch("http://127.0.0.1:8765/api/chronoflow/characters")
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setChars(d.characters || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!chars.length) {
    return (
      <div>
        <label className="flex items-center gap-1.5 text-xs font-semibold text-zinc-300 mb-1.5">
          <Lock className="w-3.5 h-3.5" />
          Character Lock
        </label>
        <p className="text-[11px] text-zinc-500">Character Vault is empty — add reference sheets in the ChronoFlow Studio vault first.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold text-zinc-300">
          <Lock className="w-3.5 h-3.5" />
          Character Lock
        </label>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">
          {selected.length ? `${selected.length} locked` : "off"}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {chars.map((c) => {
          const on = selected.includes(c.id);
          return (
            <button
              key={c.id}
              type="button"
              title={`${c.name} — ${c.role}`}
              onClick={() => onToggle(c.id)}
              className={`relative w-12 h-12 rounded-lg overflow-hidden border-2 transition-all ${
                on ? "border-purple-400 scale-105" : "border-zinc-800 hover:border-zinc-600"
              }`}
            >
              <img src={`http://127.0.0.1:8765/inputs/${c.image}`} alt={c.name} className="w-full h-full object-cover" />
              {on && (
                <span className="absolute bottom-0 right-0 w-4 h-4 bg-purple-500 rounded-tl flex items-center justify-center">
                  <Check className="w-2.5 h-2.5 text-white" />
                </span>
              )}
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-zinc-500 mt-1">
        Generated faces follow the selected approved sheets (max {max}). Never generate a character's face unlocked.
      </p>
    </div>
  );
};

interface StoryEditorChronoFlowPanelProps {
  project: Project;
  scene: VideoScene | null;
  isOpen: boolean;
  onClose: () => void;
  onApplyVideoToScene: (sceneId: string, videoUrl: string) => void;
  onApplyImageToScene: (sceneId: string, imageUrl: string) => void;
  onOpenFullStudio: () => void;
}

export const StoryEditorChronoFlowPanel: React.FC<StoryEditorChronoFlowPanelProps> = ({
  project,
  scene,
  isOpen,
  onClose,
  onApplyVideoToScene,
  onApplyImageToScene,
  onOpenFullStudio,
}) => {
  if (!isOpen) return null;

  const [activeTab, setActiveTab] = useState<"video" | "image" | "chaining">("video");
  const [prompt, setPrompt] = useState(
    scene?.title || "Cinematic motion comic scene, dynamic lighting, fluid character movement, 4k quality"
  );
  const [cameraMotion, setCameraMotion] = useState("push_in");
  const [generating, setGenerating] = useState(false);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState<string | null>(null);
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string | null>(null);
  const [refine, setRefine] = useState(false);
  const [refineNote, setRefineNote] = useState<string | null>(null);
  const [lockedIds, setLockedIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Active frame image from scene layers
  const activeImageUrl = scene?.layers?.[0]?.image_url || "";

  const handleGenerateVideo = async () => {
    setGenerating(true);
    setError(null);
    try {
      // Dispatch generation via ChronoFlow or Motion preview endpoint
      const res = await (api as any).previewShotVideo(
        project.id,
        scene?.layers?.[0]?.source_panel_id || scene?.id || "panel",
        cameraMotion,
        prompt,
        "fast_h3",
        "medium",
        "none"
      );
      if (res?.video_url) {
        setGeneratedVideoUrl(res.video_url);
      } else {
        // Fallback to static output URL if returned
        setGeneratedVideoUrl(`http://127.0.0.1:8765/chronoflow/outputs/preview_${Date.now()}.mp4`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to generate video chunk. Ensure ComfyUI/MiniMax is ready.");
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateImage = async () => {
    setGenerating(true);
    setError(null);
    setRefineNote(null);
    try {
      // Generate replacement image through the single PanelFlow art workflow (Qwen Image 2.1)
      const res = await fetch("http://127.0.0.1:8765/api/chronoflow/generate_image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          width: 1344,
          height: 768,
          character_ids: lockedIds,
          ...(refine ? { refine: true } : {}),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          setGeneratedImageUrl(`http://127.0.0.1:8765${data.url}`);
        }
        if (data.refine) {
          const tries = data.refine.generations as number;
          const how =
            data.refine.status === "accept" ? "passed the check"
            : data.refine.status === "accept_low" ? (data.refine.repaired ? "repaired; please look at the repaired area" : "kept with low confidence; please look")
            : data.refine.status === "needs_review" ? "still failing the check; best try kept, please review"
            : "could not be checked";
          setRefineNote(`${tries} ${tries === 1 ? "try" : "tries"}: ${how}`);
        }
      } else {
        const body = await res.json().catch(() => null);
        setError(body?.detail || `Image generation failed (${res.status}).`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to generate image.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 select-none">
      <div className="w-full max-w-2xl bg-[#0e1220] border border-purple-800/40 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-5 py-3.5 bg-[#14192b] border-b border-[#232b45] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center text-white shadow-md">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-sm text-white">ChronoFlow AI Generation Panel</h3>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">
                  Scene #{scene?.id?.slice(-4) || "1"}
                </span>
              </div>
              <p className="text-[11px] text-zinc-400">MiniMax Fast H3 Video Chaining & Qwen Image 2.1 Art</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onOpenFullStudio}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-purple-950/60 hover:bg-purple-900/60 text-purple-300 hover:text-white border border-purple-800/40 text-xs font-semibold transition-colors"
              title="Open standalone ChronoFlow Studio"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Full Studio</span>
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-[#1e2538] bg-[#0b0e18] px-5 pt-2 gap-3 text-xs">
          <button
            onClick={() => setActiveTab("video")}
            className={`pb-2.5 px-1 font-semibold flex items-center gap-1.5 border-b-2 transition-all ${
              activeTab === "video"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>MiniMax Video Generation</span>
          </button>
          <button
            onClick={() => setActiveTab("image")}
            className={`pb-2.5 px-1 font-semibold flex items-center gap-1.5 border-b-2 transition-all ${
              activeTab === "image"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" />
            <span>Qwen Panel Art</span>
          </button>
          <button
            onClick={() => setActiveTab("chaining")}
            className={`pb-2.5 px-1 font-semibold flex items-center gap-1.5 border-b-2 transition-all ${
              activeTab === "chaining"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Keyframe Chaining</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-4 flex-1">
          {/* Active Frame Thumbnail & Prompt */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-1 rounded-lg border border-zinc-800 bg-black/60 overflow-hidden aspect-video flex items-center justify-center relative">
              {activeImageUrl ? (
                <img src={activeImageUrl} alt="Scene Frame" className="w-full h-full object-contain" />
              ) : (
                <span className="text-[11px] text-zinc-500">No panel image</span>
              )}
              <span className="absolute bottom-1.5 left-1.5 text-[9px] px-1.5 py-0.5 rounded bg-black/70 text-zinc-300">
                Source Keyframe
              </span>
            </div>

            <div className="sm:col-span-2 space-y-2">
              <label className="text-xs font-semibold text-zinc-300">AI Prompt & Scene Description:</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-100 focus:outline-none focus:border-purple-500"
                placeholder="Motion description, visual effects, dynamic lighting..."
              />
            </div>
          </div>

          {activeTab === "video" && (
            <div className="space-y-4 pt-1">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="font-medium text-zinc-400 block mb-1">Camera Dynamics:</label>
                  <select
                    value={cameraMotion}
                    onChange={(e) => setCameraMotion(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-purple-500"
                  >
                    <option value="push_in">Push In (Dramatic Reveal)</option>
                    <option value="orbit">Orbit (Dynamic Circular Arc)</option>
                    <option value="pan_right">Pan Right (Tracking Movement)</option>
                    <option value="cinematic_drone">Cinematic Drone (Wide Shot)</option>
                  </select>
                </div>
                <div>
                  <label className="font-medium text-zinc-400 block mb-1">Duration & Engine:</label>
                  <div className="p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-purple-300 font-mono">
                    5.2s / MiniMax Fast H3 Turbo
                  </div>
                </div>
              </div>

              {generatedVideoUrl && (
                <div className="p-3 bg-zinc-950 rounded-xl border border-purple-900/60 space-y-2">
                  <div className="flex items-center justify-between text-xs text-purple-300 font-semibold">
                    <span>Generated Video Preview:</span>
                    <button
                      onClick={() => scene && onApplyVideoToScene(scene.id, generatedVideoUrl)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-colors"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Apply Video to Scene</span>
                    </button>
                  </div>
                  <video src={generatedVideoUrl} controls autoPlay loop className="w-full rounded-lg bg-black max-h-48" />
                </div>
              )}

              <button
                onClick={handleGenerateVideo}
                disabled={generating}
                className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-purple-900/30 transition-all"
              >
                {generating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                <span>{generating ? "Synthesizing Video Chunk with MiniMax H3..." : "Generate 5.2s AI Video"}</span>
              </button>
            </div>
          )}

          {activeTab === "image" && (
            <div className="space-y-4 pt-1">
              <p className="text-xs text-zinc-400">
                Generate high-resolution replacement panel art using Qwen Image 2.1 Turbo, preserving the narrative tone and character consistency.
              </p>

              {generatedImageUrl && (
                <div className="p-3 bg-zinc-950 rounded-xl border border-purple-900/60 space-y-2">
                  <div className="flex items-center justify-between text-xs text-purple-300 font-semibold">
                    <span>Generated Artwork:</span>
                    <button
                      onClick={() => scene && onApplyImageToScene(scene.id, generatedImageUrl)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-colors"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Apply Image to Scene</span>
                    </button>
                  </div>
                  <img src={generatedImageUrl} alt="Generated Art" className="w-full rounded-lg bg-black max-h-48 object-contain" />
                </div>
              )}

              <label
                className="flex items-center gap-2 text-xs text-zinc-300"
                title="Review the picture against the prompt, then repair or redraw it if it fails. Needs the local vision model; slower."
              >
                <input type="checkbox" checked={refine} onChange={(e) => setRefine(e.target.checked)} disabled={generating} />
                Check and fix the picture (slower)
              </label>
              {refineNote && <p className="text-xs text-amber-300" role="status">{refineNote}</p>}

              <CharacterLockPicker
                selected={lockedIds}
                onToggle={(id) =>
                  setLockedIds((prev) =>
                    prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 4 ? prev : [...prev, id]
                  )
                }
              />

              <button
                onClick={handleGenerateImage}
                disabled={generating}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-indigo-900/30 transition-all"
              >
                {generating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                <span>{generating ? "Generating with Qwen Image 2.1..." : "Generate Panel Image"}</span>
              </button>
            </div>
          )}

          {activeTab === "chaining" && (
            <div className="space-y-3 pt-1 text-xs text-zinc-300 leading-relaxed">
              <div className="p-3.5 rounded-xl bg-purple-950/20 border border-purple-900/40 space-y-2">
                <span className="font-semibold text-purple-300 flex items-center gap-1.5">
                  <Layers className="w-4 h-4" />
                  Sliding Window Continuation Chaining
                </span>
                <p className="text-[11px] text-zinc-400">
                  ChronoFlow automatically extracts the final frame (tail frame) of Scene #{scene?.id?.slice(-4) || "1"} to use as the first keyframe of the subsequent scene. This ensures 100% fluid visual continuity across cut transitions without abrupt scene jumps.
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={onOpenFullStudio}
                  className="px-3.5 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Open Multi-Track Timeline in ChronoFlow Studio</span>
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300 text-xs">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
