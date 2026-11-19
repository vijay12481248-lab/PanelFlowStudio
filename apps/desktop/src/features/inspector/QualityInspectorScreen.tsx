import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type {
  QualityDecision,
  VideoQualityDecision,
  DefectRecord,
  TemporalDefectRecord,
  ImageRepairResponse,
  VideoRepairResponse,
} from "@panelflow/api-client";
import { Button, GlassPanel, PageHeader } from "@panelflow/ui-v2";
import { DefectCanvasOverlay } from "./DefectCanvasOverlay";
import { SideBySideDiff } from "./SideBySideDiff";

export const QualityInspectorScreen: React.FC = () => {
  const [mode, setMode] = useState<"image" | "video">("image");
  const [filePath, setFilePath] = useState<string>("output/anatomy_labels/klein_cross_legged_101.png");
  const [prompt, setPrompt] = useState<string>("");
  const [isInspecting, setIsInspecting] = useState(false);
  const [isRepairing, setIsRepairing] = useState(false);
  const [imageDecision, setImageDecision] = useState<QualityDecision | null>(null);
  const [videoDecision, setVideoDecision] = useState<VideoQualityDecision | null>(null);
  const [repairResult, setRepairResult] = useState<ImageRepairResponse | null>(null);
  const [videoRepairResult, setVideoRepairResult] = useState<VideoRepairResponse | null>(null);
  const [selectedDefectId, setSelectedDefectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Inspector Health query
  const healthQuery = useQuery({
    queryKey: ["inspector-health"],
    queryFn: () => api.inspectorHealth(),
    staleTime: 60000,
  });

  const handleInspect = async () => {
    setError(null);
    setIsInspecting(true);
    setRepairResult(null);
    setVideoRepairResult(null);
    try {
      if (mode === "image") {
        const decision = await api.inspectImage(filePath, { prompt });
        setImageDecision(decision);
        if (decision.defects.length > 0) {
          setSelectedDefectId(decision.defects[0].defect_id);
        }
      } else {
        const decision = await api.inspectVideo(filePath);
        setVideoDecision(decision);
        if (decision.defects.length > 0) {
          setSelectedDefectId(decision.defects[0].defect_id);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inspection failed");
    } finally {
      setIsInspecting(false);
    }
  };

  const handleRepair = async () => {
    if (!filePath || mode !== "image") return;
    setError(null);
    setIsRepairing(true);
    try {
      const res = await api.repairImage(filePath, prompt, imageDecision ?? undefined);
      setRepairResult(res);
      setImageDecision(res.revalidated_decision);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auto-repair failed");
    } finally {
      setIsRepairing(false);
    }
  };

  const handleVideoRepair = async () => {
    if (!filePath || mode !== "video") return;
    setError(null);
    setIsRepairing(true);
    try {
      const res = await api.repairVideo(filePath, videoDecision ?? undefined);
      setVideoRepairResult(res);
      setVideoDecision(res.revalidated_decision);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Video auto-repair failed");
    } finally {
      setIsRepairing(false);
    }
  };

  const currentScore = mode === "image" ? imageDecision?.overall_score : videoDecision?.overall_score;
  const currentStatus = mode === "image" ? imageDecision?.status : videoDecision?.status;
  const defectsList = mode === "image" ? imageDecision?.defects || [] : videoDecision?.defects || [];

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6 text-zinc-100">
      <PageHeader
        title="AI Visual Quality Inspector & Auto-Correction"
        meta="Independent multi-model quality inspection & non-destructive auto-repair subsystem"
      />

      {/* Engine & Licensing Status Banner */}
      <GlassPanel className="flex flex-wrap items-center justify-between gap-4 p-4 border border-zinc-800 bg-zinc-950/60">
        <div className="flex items-center gap-3">
          <div
            className={`h-3 w-3 rounded-full ${
              healthQuery.data?.status === "ready" ? "bg-emerald-500 shadow-[0_0_8px_#10b981]" : "bg-amber-500"
            }`}
          />
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
              Inspection Engine Status: {healthQuery.data?.status || "Checking..."}
            </span>
            <span className="text-xs text-zinc-400">
              {healthQuery.data?.licensing.cv_models} &bull; VRAM: {healthQuery.data?.vram_usage || "0 MB"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/30">
            100% Monetizable / Apache 2.0
          </span>
          <span className="rounded-full bg-sky-500/10 px-3 py-1 text-xs font-semibold text-sky-400 border border-sky-500/30">
            DWPose CPU Topology
          </span>
        </div>
      </GlassPanel>

      {/* Target & Controls Section */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Inspection Target
            </label>
            <div className="flex rounded-lg bg-zinc-800 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => {
                  setMode("image");
                  setFilePath("output/anatomy_labels/klein_cross_legged_101.png");
                  setRepairResult(null);
                  setVideoRepairResult(null);
                }}
                className={`rounded px-2.5 py-1 font-medium transition-colors ${
                  mode === "image" ? "bg-zinc-700 text-white" : "text-zinc-400"
                }`}
              >
                Still Image
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("video");
                  setFilePath("output/bench_cpu.mp4");
                  setRepairResult(null);
                  setVideoRepairResult(null);
                }}
                className={`rounded px-2.5 py-1 font-medium transition-colors ${
                  mode === "video" ? "bg-zinc-700 text-white" : "text-zinc-400"
                }`}
              >
                Video Sequence
              </button>
            </div>
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="e.g. output/anatomy_labels/sample.png"
              className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-sky-500 focus:outline-none"
            />
            <Button
              variant="primary"
              onClick={handleInspect}
              disabled={isInspecting || !filePath.trim()}
            >
              {isInspecting ? "Inspecting..." : "Inspect Target"}
            </Button>
          </div>

          {/* Quick Preset Buttons */}
          <div className="flex items-center gap-2 pt-1 text-xs">
            <span className="text-zinc-500">Presets:</span>
            {mode === "image" ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setFilePath("output/anatomy_labels/klein_cross_legged_101.png");
                    setPrompt("girl sitting cross-legged");
                  }}
                  className="rounded bg-zinc-800/80 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700 hover:text-white"
                >
                  Anatomy Defect Sample
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setFilePath("output/anatomy_labels/clean_portrait.png");
                    setPrompt("masterwork anime portrait");
                  }}
                  className="rounded bg-zinc-800/80 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700 hover:text-white"
                >
                  Clean Portrait
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setFilePath("output/bench_cpu.mp4")}
                className="rounded bg-zinc-800/80 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700 hover:text-white"
              >
                Workspace Bench Video (5s)
              </button>
            )}
          </div>

          {mode === "image" && (
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Optional generation prompt context (helps detect stray text and missing subjects)"
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 focus:border-zinc-700 focus:outline-none"
            />
          )}

          {error && (
            <div className="rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20">
              {error}
            </div>
          )}
        </div>

        {/* Quality Score Gauge Card */}
        <div className="flex flex-col justify-between rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Quality Score
            </span>
            {currentStatus && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                  currentStatus === "PASS"
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : currentStatus === "RETRY"
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                    : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                }`}
              >
                {currentStatus}
              </span>
            )}
          </div>

          <div className="my-2 flex items-baseline gap-2">
            <span className="text-4xl font-extrabold tracking-tight">
              {currentScore !== undefined ? currentScore.toFixed(1) : "--"}
            </span>
            <span className="text-sm font-medium text-zinc-500">/ 100</span>
          </div>

          <div className="text-xs text-zinc-400">
            {defectsList.length === 0
              ? "No visual or anatomical defects detected."
              : `${defectsList.length} defect(s) detected across inspection passes.`}
          </div>
        </div>
      </div>

      {/* Main Inspection & Repair Workspace */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Col: Target Canvas with Overlays or A/B Diff */}
        <div className="flex flex-col gap-4 lg:col-span-8">
          {mode === "image" && repairResult ? (
            <SideBySideDiff
              originalUrl={`/outputs/${filePath.replace(/\\/g, "/")}`}
              repairedUrl={`/outputs/${repairResult.repaired_image_path.replace(/\\/g, "/")}`}
              originalScore={imageDecision?.overall_score}
              repairedScore={repairResult.revalidated_decision.overall_score}
              isVideo={false}
            />
          ) : mode === "video" && videoRepairResult ? (
            <SideBySideDiff
              originalUrl={`/outputs/${filePath.replace(/\\/g, "/")}`}
              repairedUrl={`/outputs/${videoRepairResult.repaired_video_path.replace(/\\/g, "/")}`}
              originalScore={videoDecision?.overall_score}
              repairedScore={videoRepairResult.revalidated_decision.overall_score}
              isVideo={true}
            />
          ) : mode === "image" && filePath ? (
            <div className="flex justify-center rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-4">
              <DefectCanvasOverlay
                imageUrl={`/outputs/${filePath.replace(/\\/g, "/")}`}
                defects={imageDecision?.defects || []}
                selectedDefectId={selectedDefectId}
                onSelectDefect={(id) => setSelectedDefectId(id)}
              />
            </div>
          ) : mode === "video" && filePath ? (
            <div className="flex flex-col gap-3 rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-4">
              <video
                src={`/outputs/${filePath.replace(/\\/g, "/")}`}
                controls
                className="max-h-[480px] w-full rounded-lg object-contain"
              />
              {videoDecision && videoDecision.defects.length > 0 && (
                <div className="flex flex-col gap-1.5 pt-2 border-t border-zinc-800">
                  <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                    Temporal Defect Timeline ({videoDecision.duration_sec.toFixed(1)}s total)
                  </span>
                  <div className="relative h-6 w-full rounded bg-zinc-900 border border-zinc-800">
                    {videoDecision.defects.map((d) => {
                      const leftPct = (d.start_sec / (videoDecision.duration_sec || 1)) * 100;
                      const widthPct = Math.max(2, ((d.end_sec - d.start_sec) / (videoDecision.duration_sec || 1)) * 100);
                      const isSelected = selectedDefectId === d.defect_id;
                      return (
                        <div
                          key={`timeline-${d.defect_id}`}
                          onClick={() => setSelectedDefectId(d.defect_id)}
                          style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                          title={`${d.category}: ${d.start_sec.toFixed(2)}s - ${d.end_sec.toFixed(2)}s`}
                          className={`absolute top-0 bottom-0 cursor-pointer transition-all ${
                            d.severity === "severe" ? "bg-rose-500/60" : "bg-amber-500/60"
                          } ${isSelected ? "ring-2 ring-white z-10" : "hover:brightness-125"}`}
                        />
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-64 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900/20 text-xs text-zinc-500">
              Inspect an image or video to view the interactive defect canvas
            </div>
          )}
        </div>

        {/* Right Col: Defect Breakdown and Auto-Correction Actions */}
        <div className="flex flex-col gap-4 lg:col-span-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Detected Defects ({defectsList.length})
            </h3>
            {defectsList.length > 0 && mode === "image" && !repairResult && (
              <Button
                variant="primary"
                onClick={handleRepair}
                disabled={isRepairing}
              >
                {isRepairing ? "Repairing via SDXL..." : "Auto-Repair (SDXL)"}
              </Button>
            )}
            {defectsList.length > 0 && mode === "video" && !videoRepairResult && (
              <Button
                variant="primary"
                onClick={handleVideoRepair}
                disabled={isRepairing}
              >
                {isRepairing ? "Repairing Video..." : "Auto-Repair Video"}
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-2.5 overflow-y-auto max-h-[500px]">
            {defectsList.length === 0 ? (
              <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/20 p-6 text-center text-xs text-zinc-500">
                No defects logged. Target passed validation criteria.
              </div>
            ) : (
              defectsList.map((d: any) => {
                const isSelected = selectedDefectId === d.defect_id;
                return (
                  <div
                    key={d.defect_id}
                    onClick={() => setSelectedDefectId(d.defect_id)}
                    className={`flex flex-col gap-1.5 rounded-xl border p-3 cursor-pointer transition-all ${
                      isSelected
                        ? "border-sky-500 bg-sky-950/20 shadow-md"
                        : "border-zinc-800/80 bg-zinc-900/30 hover:border-zinc-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-zinc-200">
                        {d.category.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                          d.severity === "severe"
                            ? "bg-rose-500/20 text-rose-300"
                            : "bg-amber-500/20 text-amber-300"
                        }`}
                      >
                        {d.severity} ({Math.round(d.confidence * 100)}%)
                      </span>
                    </div>

                    <p className="text-xs text-zinc-400 leading-relaxed">
                      {d.evidence || "Anatomical or temporal irregularity identified."}
                    </p>

                    <div className="mt-1 flex items-center justify-between text-[11px] text-zinc-500">
                      <span>Action: {d.recommended_action}</span>
                      {d.tile && <span>Tile: {d.tile}</span>}
                      {d.start_sec !== undefined && (
                        <span>
                          {d.start_sec.toFixed(2)}s &rarr; {d.end_sec.toFixed(2)}s
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {repairResult && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-emerald-300">
              <div className="font-bold mb-1">Image Auto-Correction Complete</div>
              <div>Actions applied: {repairResult.actions_taken.join(", ")}</div>
              <div>Attempts: {repairResult.attempts}</div>
              <div>New Score: {repairResult.revalidated_decision.overall_score.toFixed(1)} / 100</div>
            </div>
          )}

          {videoRepairResult && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-emerald-300">
              <div className="font-bold mb-1">Video Auto-Correction Complete</div>
              <div>Actions applied: {videoRepairResult.metadata?.actions_applied?.join(", ") || "Optical flow interpolation"}</div>
              <div>New Score: {videoRepairResult.revalidated_decision.overall_score.toFixed(1)} / 100</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
