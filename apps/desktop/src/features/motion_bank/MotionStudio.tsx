import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type MotionRecordResponse, type MotionSegmentResponse } from "@panelflow/api-client";
import {
  Button,
  Chip,
  Dialog,
  EmptyState,
  GlassPanel,
  Input,
  PageHeader,
  Skeleton,
  useToast,
} from "@panelflow/ui-v2";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";

/** Rights a harvest can be filed under. UNKNOWN is deliberately absent and nothing is pre-selected. */
const RIGHTS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "USER_OWNED", label: "USER_OWNED (I filmed / own it)" },
  { value: "PUBLIC_DOMAIN", label: "PUBLIC_DOMAIN (open / no rights reserved)" },
  { value: "CREATIVE_COMMONS", label: "CREATIVE_COMMONS (name the licence below)" },
  { value: "LICENSED", label: "LICENSED (I hold a licence)" },
  { value: "EXPLICIT_PERMISSION", label: "EXPLICIT_PERMISSION (the owner agreed)" },
  { value: "COMMENTARY_REVIEW", label: "COMMENTARY_REVIEW (fair-use study, needs a note)" },
];

const isSynthetic = (m: MotionRecordResponse) => Boolean(m.metadata?.synthetic);

export const MotionStudio: React.FC = () => {
  const queryClient = useQueryClient();
  const { show } = useToast();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  // Harvesting Modal State
  const [harvestModalOpen, setHarvestModalOpen] = useState(false);
  const [sourceInput, setSourceInput] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [rightsStatus, setRightsStatus] = useState("");
  const [rightsHolder, setRightsHolder] = useState("");
  const [licenseType, setLicenseType] = useState("");
  const [permissionNotes, setPermissionNotes] = useState("");
  const [detectedCuts, setDetectedCuts] = useState<MotionSegmentResponse[]>([]);
  const [ingestedPath, setIngestedPath] = useState<string | null>(null);

  // Library management
  const [renameTarget, setRenameTarget] = useState<MotionRecordResponse | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [renameTags, setRenameTags] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MotionRecordResponse | null>(null);

  // Guide Model Generator State
  const [promptInput, setPromptInput] = useState("");
  const [numFrames, setNumFrames] = useState(48);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState<string | null>(null);

  // 1. Queries
  const { data: statusData } = useQuery({
    queryKey: ["motion-bank-status"],
    queryFn: () => api.getMotionBankStatus(),
  });

  const { data: allMotions = [] } = useQuery({
    queryKey: ["motion-bank-all"],
    queryFn: () => api.listMotions({ limit: 500 }),
  });

  const { data: motions = [], isLoading: isLoadingMotions } = useQuery({
    queryKey: ["motion-bank-list", selectedTag, searchQuery],
    queryFn: () => {
      if (searchQuery.trim()) {
        return api.searchMotions(searchQuery.trim());
      }
      return api.listMotions(selectedTag ? { tag: selectedTag } : undefined);
    },
  });

  const tags = useMemo(() => {
    const seen = new Set<string>();
    allMotions.forEach((m) => m.action_tags.forEach((t) => seen.add(t)));
    return ["all", ...Array.from(seen).sort()];
  }, [allMotions]);

  const realCount = allMotions.filter((m) => !isSynthetic(m)).length;
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["motion-bank-list"] });
    queryClient.invalidateQueries({ queryKey: ["motion-bank-all"] });
    queryClient.invalidateQueries({ queryKey: ["motion-bank-status"] });
  };

  // 2. Mutations
  const ingestMutation = useMutation({
    mutationFn: async () => {
      const res = await api.ingestMotionSource({
        source: sourceInput,
        title: sourceTitle || undefined,
        rights: {
          status: rightsStatus,
          holder: rightsHolder || undefined,
          license_type: licenseType || undefined,
          permission_notes: permissionNotes || undefined,
        },
      });
      setIngestedPath(res.local_path);
      const cuts = await api.segmentMotionVideo({ local_path: res.local_path });
      setDetectedCuts(cuts);
      return { res, cuts };
    },
    onSuccess: (data) => {
      show(`Video ingested. Found ${data.cuts.length} continuous takes.`, "ok");
    },
    onError: (err: any) => {
      show(err?.message || "Could not ingest video source", "bad");
    },
  });

  const extractMutation = useMutation({
    mutationFn: async (cut: MotionSegmentResponse) => {
      if (!ingestedPath) throw new Error("No source video ingested");
      return api.extractMotion({
        video_path: ingestedPath,
        action_title: `${sourceTitle || "Action Move"} (${cut.segment_id})`,
        action_tags: ["harvested"],
        start_sec: cut.start_sec,
        end_sec: cut.end_sec,
      });
    },
    onSuccess: (rec) => {
      const found = rec.metadata?.detected_frames;
      show(`Poses extracted (${found ?? "?"} of ${rec.frame_count} frames had the actor) and added to the Motion Bank.`, "ok");
      refresh();
      setHarvestModalOpen(false);
    },
    onError: (err: any) => {
      show(err?.message || "Failed to extract poses", "bad");
    },
  });

  const renameMutation = useMutation({
    mutationFn: () =>
      api.updateMotion(renameTarget!.id, {
        action_title: renameTitle.trim(),
        action_tags: renameTags.split(",").map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      setRenameTarget(null);
      refresh();
    },
    onError: (err: any) => show(err?.message || "Could not save changes", "bad"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteMotion(deleteTarget!.id),
    onSuccess: () => {
      show("Motion deleted.", "ok");
      setDeleteTarget(null);
      refresh();
    },
    onError: (err: any) => show(err?.message || "Could not delete the motion", "bad"),
  });

  const trainGuideMutation = useMutation({
    mutationFn: () => api.trainMotionGuide({ num_epochs: 10, batch_size: 16 }),
    onSuccess: (res) => {
      show(`Trained Guide Model (${res.epochs} epochs in ${res.duration_sec}s). Loss: ${res.final_loss}`, "ok");
    },
    onError: (err: any) => {
      show(err?.message || "Failed to train guide model", "bad");
    },
  });

  const generateGuideMutation = useMutation({
    mutationFn: () =>
      api.generateMotionChoreography({
        prompt: promptInput,
        num_frames: numFrames,
        fps: 24,
        render_video: true,
      }),
    onSuccess: (res) => {
      if (res.control_video_url) {
        setGeneratedVideoUrl(api.resourceUrl(res.control_video_url));
      }
      show(`Synthesized ${res.frame_count} skeleton frames.`, "ok");
    },
    onError: (err: any) => {
      show(err?.message || "Failed to synthesize choreography", "bad");
    },
  });

  const rightsReady =
    rightsStatus !== "" && (rightsStatus !== "COMMENTARY_REVIEW" || permissionNotes.trim() !== "");
  const dwposeReady = Boolean(statusData?.dwpose_ready);
  const onCpu = dwposeReady && (statusData?.dwpose_providers ?? []).length > 0 && !(statusData?.dwpose_providers ?? []).includes("CUDAExecutionProvider");

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-slate-950 text-slate-100 p-6 space-y-6">
      <PageHeader
        title="Motion Studio & Motion Bank"
        meta={
          <span>
            Harvest whole-body character choreography from reference videos or synthesize new kinematic sequences with the Guide Model.
          </span>
        }
        actions={
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-400">
              <Cpu className={`w-3.5 h-3.5 ${dwposeReady ? "text-emerald-400" : "text-amber-400"}`} />
              <span>
                DWPose: {dwposeReady ? `Ready${onCpu ? " (CPU, ~0.2 s/frame)" : ""}` : "Models missing"}
              </span>
            </div>
            <Button
              variant="secondary"
              onClick={() => trainGuideMutation.mutate()}
              disabled={trainGuideMutation.isPending || realCount === 0}
              title={realCount === 0 ? "Needs at least one real (non-synthetic) harvested motion" : undefined}
            >
              <Sparkles className="w-4 h-4 mr-2 text-indigo-400" />
              {trainGuideMutation.isPending ? "Training Guide..." : "Train Guide Model"}
            </Button>
            <Button variant="primary" onClick={() => setHarvestModalOpen(true)} disabled={!dwposeReady}>
              <Plus className="w-4 h-4 mr-2" />
              Harvest Video Motion
            </Button>
          </div>
        }
      />

      {statusData && !dwposeReady && (
        <div className="flex items-start gap-2 p-3 rounded-xl border border-amber-900/60 bg-amber-950/30 text-xs text-amber-200">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            The DWPose pose models are not on disk, so harvesting is switched off (a fake skeleton is never stored silently). The
            expected files are listed in the engine status ({statusData.manifest.map((m) => m.filename).join(", ")}).
          </span>
        </div>
      )}

      {/* Guide Model Prompt Synthesizer Panel */}
      <GlassPanel className="p-5 border border-indigo-950/60 bg-gradient-to-r from-slate-900/90 via-indigo-950/20 to-slate-900/90 rounded-2xl">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-semibold text-slate-200">The Choreographer: AI Pose Generation</h3>
          <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono">Motion-DiT (22M)</span>
          <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">experimental</span>
        </div>
        <p className="text-xs text-slate-400 mb-4">
          Type an action description. The lightweight guide model synthesizes a 133-point skeleton sequence. It must be trained on
          harvested real motions first; with only a few motions its output is rough.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Input
            placeholder="e.g. Samurai performs a spinning reverse heel kick, then lands in low guard..."
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            className="flex-1 bg-slate-950/80 border-slate-800"
          />
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Frames:</span>
            <select
              value={numFrames}
              onChange={(e) => setNumFrames(Number(e.target.value))}
              className="bg-slate-950 border border-slate-800 text-xs rounded-lg px-2 py-2 text-slate-300"
            >
              <option value={24}>24f (1.0s)</option>
              <option value={48}>48f (2.0s)</option>
              <option value={72}>72f (3.0s)</option>
              <option value={120}>120f (5.0s)</option>
            </select>
          </div>
          <Button
            variant="primary"
            onClick={() => generateGuideMutation.mutate()}
            disabled={generateGuideMutation.isPending || !promptInput.trim()}
          >
            {generateGuideMutation.isPending ? "Synthesizing..." : "Generate Pose Sequence"}
          </Button>
        </div>

        {generatedVideoUrl && (
          <div className="mt-4 p-4 rounded-xl bg-slate-950/90 border border-slate-800 flex flex-col sm:flex-row items-center gap-4">
            <video src={generatedVideoUrl} autoPlay loop muted className="w-48 h-28 object-contain rounded-lg bg-black border border-slate-800" />
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> Synthesized skeleton video ready
              </h4>
              <p className="text-xs text-slate-400 mt-1">An OpenPose-style control video, usable as pose guidance.</p>
            </div>
          </div>
        )}
      </GlassPanel>

      {/* Library Controls & Search */}
      <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 max-w-full">
          {tags.map((tag) => (
            <Chip
              key={tag}
              tone={selectedTag === tag || (tag === "all" && !selectedTag) ? "accent" : "neutral"}
              className="cursor-pointer"
              onClick={() => setSelectedTag(tag === "all" ? null : tag)}
            >
              {tag === "all" ? "All Motions" : tag.replace("_", " ")}
            </Chip>
          ))}
        </div>
        <div className="w-full md:w-72">
          <Input
            placeholder="Search action, title, tags..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-slate-900 border-slate-800"
          />
        </div>
      </div>

      {/* Motion Bank Grid */}
      {isLoadingMotions ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-64 rounded-2xl" />
          ))}
        </div>
      ) : motions.length === 0 ? (
        <EmptyState
          title="No Motions in Library"
          description="Harvest poses from a reference video you have the rights to, or generate choreography with the guide model."
          action={
            <Button variant="primary" onClick={() => setHarvestModalOpen(true)} disabled={!dwposeReady}>
              <Plus className="w-4 h-4 mr-2" />
              Harvest Your First Motion
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {motions.map((motion) => {
            const synthetic = isSynthetic(motion);
            const found = motion.metadata?.detected_frames as number | undefined;
            const rights = motion.metadata?.rights?.status as string | undefined;
            return (
              <GlassPanel key={motion.id} className="p-4 rounded-2xl border border-slate-800 flex flex-col justify-between hover:border-slate-700 transition">
                <div>
                  <div className="relative aspect-video rounded-xl overflow-hidden bg-black mb-3 border border-slate-900 flex items-center justify-center">
                    <video
                      src={api.motionControlVideoUrl(motion.id)}
                      poster={motion.thumbnail_path ? api.motionThumbnailUrl(motion.id) : undefined}
                      autoPlay
                      loop
                      muted
                      playsInline
                      className="w-full h-full object-contain"
                    />
                    <div className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-black/70 text-[10px] text-slate-300 font-mono">
                      {motion.duration_sec}s • {motion.fps}fps
                    </div>
                    {synthetic && (
                      <div className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-amber-500/80 text-[10px] text-black font-semibold">
                        FAKE / TEST
                      </div>
                    )}
                  </div>
                  <h4 className="text-sm font-semibold text-slate-100 truncate" title={motion.action_title}>{motion.action_title}</h4>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{motion.action_summary || "Kinematic whole-body trajectory."}</p>
                  <div className="flex flex-wrap gap-1 mt-2.5">
                    {motion.action_tags.map((t) => (
                      <span key={t} className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-900 flex items-center justify-between text-xs text-slate-500">
                  <span title={rights ? `Rights: ${rights}` : undefined}>
                    {motion.resolution[0]}x{motion.resolution[1]}
                    {found !== undefined && ` • ${Math.round((100 * found) / Math.max(1, motion.frame_count))}% tracked`}
                  </span>
                  <span className="flex items-center gap-1">
                    <button
                      aria-label={`Rename ${motion.action_title}`}
                      className="p-1 rounded hover:bg-slate-800 text-slate-400"
                      onClick={() => {
                        setRenameTarget(motion);
                        setRenameTitle(motion.action_title);
                        setRenameTags(motion.action_tags.join(", "));
                      }}
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      aria-label={`Delete ${motion.action_title}`}
                      className="p-1 rounded hover:bg-slate-800 text-rose-400"
                      onClick={() => setDeleteTarget(motion)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </span>
                </div>
              </GlassPanel>
            );
          })}
        </div>
      )}

      {/* Rename dialog */}
      <Dialog open={renameTarget !== null} onOpenChange={(o) => !o && setRenameTarget(null)} title="Edit motion">
        <div className="space-y-3 p-1">
          <div>
            <label className="text-xs font-semibold text-slate-300 mb-1 block">Title</label>
            <Input value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-300 mb-1 block">Tags (comma separated)</label>
            <Input value={renameTags} onChange={(e) => setRenameTags(e.target.value)} />
          </div>
          <Button
            variant="primary"
            className="w-full"
            onClick={() => renameMutation.mutate()}
            disabled={renameMutation.isPending || !renameTitle.trim()}
          >
            Save
          </Button>
        </div>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={deleteTarget !== null} onOpenChange={(o) => !o && setDeleteTarget(null)} title="Delete motion?">
        <div className="space-y-3 p-1">
          <p className="text-xs text-slate-300">
            "{deleteTarget?.action_title}" and its skeleton data, video and thumbnail will be removed from disk. This cannot be undone.
          </p>
          <Button variant="primary" className="w-full" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
            {deleteMutation.isPending ? "Deleting..." : "Delete permanently"}
          </Button>
        </div>
      </Dialog>

      {/* Harvesting Dialog */}
      <Dialog
        open={harvestModalOpen}
        onOpenChange={setHarvestModalOpen}
        title="Harvest Character Animation & Poses"
      >
        <div className="space-y-4 p-1">
          <div>
            <label className="text-xs font-semibold text-slate-300 mb-1 block">Video Reference (URL or Local File)</label>
            <Input
              placeholder="https://youtube.com/watch?v=... or E:\path\to\video.mp4"
              value={sourceInput}
              onChange={(e) => setSourceInput(e.target.value)}
            />
            <p className="text-[11px] text-slate-500 mt-1">DWPose is built for real people on camera; drawn or animated characters track poorly.</p>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-300 mb-1 block">Action Title</label>
            <Input
              placeholder="e.g. Karate Roundhouse Kick Take"
              value={sourceTitle}
              onChange={(e) => setSourceTitle(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-300 mb-1 block">Rights Declaration (required)</label>
            <select
              value={rightsStatus}
              onChange={(e) => setRightsStatus(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
            >
              <option value="">Select how you hold the rights…</option>
              {RIGHTS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {rightsStatus !== "" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input placeholder="Rights holder / creator" value={rightsHolder} onChange={(e) => setRightsHolder(e.target.value)} />
              {(rightsStatus === "CREATIVE_COMMONS" || rightsStatus === "LICENSED") && (
                <Input placeholder="Licence (e.g. CC-BY 4.0)" value={licenseType} onChange={(e) => setLicenseType(e.target.value)} />
              )}
            </div>
          )}
          {(rightsStatus === "COMMENTARY_REVIEW" || rightsStatus === "EXPLICIT_PERMISSION" || rightsStatus === "LICENSED") && (
            <div>
              <label className="text-xs font-semibold text-slate-300 mb-1 block">
                {rightsStatus === "COMMENTARY_REVIEW" ? "Commentary basis (required)" : "Permission / licence record"}
              </label>
              <Input
                placeholder="Where the permission or the commentary basis is documented"
                value={permissionNotes}
                onChange={(e) => setPermissionNotes(e.target.value)}
              />
            </div>
          )}

          <Button
            variant="primary"
            className="w-full mt-2"
            onClick={() => ingestMutation.mutate()}
            disabled={ingestMutation.isPending || !sourceInput.trim() || !rightsReady}
          >
            {ingestMutation.isPending ? "Ingesting & Analyzing Cuts..." : "Analyze Video Takes"}
          </Button>

          {/* Cuts Selection */}
          {detectedCuts.length > 0 && (
            <div className="mt-4 border-t border-slate-800 pt-3">
              <h4 className="text-xs font-semibold text-slate-300 mb-2">Detected Continuous Takes</h4>
              <div className="max-h-48 overflow-y-auto space-y-2">
                {detectedCuts.map((cut) => (
                  <div key={cut.segment_id} className="flex items-center justify-between p-2 rounded-lg bg-slate-900 border border-slate-800 text-xs">
                    <div>
                      <span className="font-semibold text-slate-200">{cut.segment_id}</span>
                      <span className="text-slate-400 ml-2">({cut.start_sec}s - {cut.end_sec}s, {cut.duration_sec}s)</span>
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => extractMutation.mutate(cut)}
                      disabled={extractMutation.isPending}
                    >
                      {extractMutation.isPending ? "Extracting…" : "Harvest Poses"}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Dialog>
    </div>
  );
};
