import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { ComfyWorkflowInfo, GeneratedAsset } from "@panelflow/api-client";
import type { Job, Project } from "@panelflow/shared-types";
import { Badge, Button, Card, Icons, ProgressBar } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";

export interface ComfyImageScreenProps {
  project: Project;
  onBack: () => void;
}

export const ComfyImageScreen: React.FC<ComfyImageScreenProps> = ({ project, onBack }) => {
  const { reportError } = useError();
  const [workflows, setWorkflows] = useState<ComfyWorkflowInfo[]>([]);
  const [assets, setAssets] = useState<GeneratedAsset[]>([]);
  const [workflowId, setWorkflowId] = useState("manga_image_generation");
  const [prompt, setPrompt] = useState(
    "Original manga panel, a young adult swordswoman on a mountain bridge at sunset, flowing teal hair, crimson and ivory robes, clean ink lines, cel shading, expressive face, cinematic composition, no text, no logo, no watermark"
  );
  const [negativePrompt, setNegativePrompt] = useState("photorealism, 3D render, blurry, malformed hands, text, watermark, logo, gore");
  const [width, setWidth] = useState(512);
  const [height, setHeight] = useState(768);
  const [seed, setSeed] = useState(20261019);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const loadAssets = useCallback(async () => {
    const result = await api.listGeneratedAssets(project.id);
    setAssets(result.assets);
  }, [project.id]);

  useEffect(() => {
    Promise.all([api.listApprovedComfyWorkflows(), loadAssets()])
      .then(([registry]) => {
        setWorkflows(registry.workflows.filter((workflow) => workflow.available && workflow.purpose === "text_to_image"));
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
      .finally(() => setLoading(false));
  }, [loadAssets, project.id, reportError]);

  const handleGenerate = async () => {
    setSubmitting(true);
    try {
      const queued = await api.generateComfyImage(project.id, {
        workflow_id: workflowId,
        prompt,
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
      setSubmitting(false);
    }
  };

  const latestAsset = assets[0];
  const progress = activeJob?.progress ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-indigo-400">Milestone 1</p>
          <h1 className="text-2xl font-bold text-zinc-100">Generate Original Image</h1>
          <p className="text-sm text-zinc-400 mt-1">Project: {project.title}</p>
        </div>
        <Button variant="ghost" onClick={onBack}>
          <Icons.ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,420px)]">
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-zinc-100">Approved workflow</h2>
            <Badge variant={workflows.length ? "success" : "danger"}>{workflows.length ? "READY" : "UNAVAILABLE"}</Badge>
          </div>
          <select
            value={workflowId}
            onChange={(event) => setWorkflowId(event.target.value)}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
            disabled={loading || submitting}
          >
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>{workflow.id}</option>
            ))}
          </select>
          <label className="block text-sm text-zinc-300">
            Prompt
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={7} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" disabled={submitting} />
          </label>
          <label className="block text-sm text-zinc-300">
            Negative prompt
            <textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" disabled={submitting} />
          </label>
          <div className="grid grid-cols-3 gap-3">
            <label className="text-sm text-zinc-300">Width<input type="number" min={256} max={2048} value={width} onChange={(event) => setWidth(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" disabled={submitting} /></label>
            <label className="text-sm text-zinc-300">Height<input type="number" min={256} max={2048} value={height} onChange={(event) => setHeight(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" disabled={submitting} /></label>
            <label className="text-sm text-zinc-300">Seed<input type="number" min={0} value={seed} onChange={(event) => setSeed(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" disabled={submitting} /></label>
          </div>
          {activeJob && (
            <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
              <div className="flex justify-between text-xs text-zinc-400"><span>{activeJob.message || activeJob.status}</span><span>{Math.round(progress * 100)}%</span></div>
              <ProgressBar progress={progress} />
            </div>
          )}
          <Button variant="primary" onClick={handleGenerate} disabled={submitting || !workflows.length || prompt.trim().length < 10}>
            <Icons.Sparkles className="w-4 h-4 mr-2" />
            {submitting ? "Generating..." : "Generate image"}
          </Button>
        </Card>

        <Card className="p-5 space-y-4">
          <h2 className="font-semibold text-zinc-100">Latest generated asset</h2>
          {latestAsset ? (
            <>
              <img src={api.getGeneratedAssetUrl(project.id, latestAsset.id)} alt="Latest generated manga asset" className="w-full rounded-lg border border-zinc-700 bg-zinc-950" />
              <div className="text-xs text-zinc-400 space-y-1">
                <p>{latestAsset.width} × {latestAsset.height} · {latestAsset.byte_size.toLocaleString()} bytes</p>
                <p className="font-mono break-all">SHA-256: {latestAsset.sha256}</p>
                <p>Asset status: <span className="text-emerald-400">{latestAsset.status}</span></p>
              </div>
            </>
          ) : (
            <div className="min-h-64 rounded-lg border border-dashed border-zinc-700 flex items-center justify-center text-sm text-zinc-500 text-center px-6">
              Generated assets will appear here after verification.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
