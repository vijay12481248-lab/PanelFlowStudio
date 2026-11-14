import React, { useCallback, useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type {
  AnimeChannelPreset,
  OriginalSeries,
  YouTubeStatus,
  StoryboardBeatCard,
  StoryboardWorkbenchData,
} from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { useError } from "../context/ErrorContext";
import { CandidateInspectorModal } from "../components/CandidateInspectorModal";
import { ImageEditorModal, ImageEditorTarget } from "../components/ImageEditorModal";
import {
  Layers,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Sparkles,
  Wand2,
  CheckCircle2,
  AlertCircle,
  Eye,
  ZoomIn,
  AlertTriangle,
  Check,
  RotateCcw,
  Maximize2,
  Clock,
  Play,
  Film,
} from "lucide-react";

export interface OriginalStoriesScreenProps {
  onBack: () => void;
}

const GENRES = ["bedtime", "horror", "mystery", "fantasy"];

export const OriginalStoriesScreen: React.FC<OriginalStoriesScreenProps> = ({ onBack }) => {
  const { reportError } = useError();
  const [series, setSeries] = useState<OriginalSeries[]>([]);
  const [channels, setChannels] = useState<AnimeChannelPreset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("bedtime");
  const [idea, setIdea] = useState("");
  const [channelId, setChannelId] = useState("");
  const [count, setCount] = useState(3);
  const [startDate, setStartDate] = useState("");
  const [refine, setRefine] = useState(false);
  const [animate, setAnimate] = useState(false);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [yt, setYt] = useState<YouTubeStatus | null>(null);
  const [ytId, setYtId] = useState("");
  const [ytSecret, setYtSecret] = useState("");
  const [forKids, setForKids] = useState<boolean | null>(null);

  // Storyboard Workbench State
  const [activeStoryboard, setActiveStoryboard] = useState<{
    slug: string;
    episode?: string;
    title: string;
  } | null>(null);
  const [isWorkbenchOpen, setIsWorkbenchOpen] = useState(true);
  const [workbenchData, setWorkbenchData] = useState<StoryboardWorkbenchData | null>(null);
  const [loadingWorkbench, setLoadingWorkbench] = useState(false);
  const [inspectingBeat, setInspectingBeat] = useState<StoryboardBeatCard | null>(null);
  const [inpaintTarget, setInpaintTarget] = useState<ImageEditorTarget | null>(null);
  const [cacheBuster, setCacheBuster] = useState<number>(Date.now());
  const [operatingPanelId, setOperatingPanelId] = useState<string | null>(null);
  const [scalingAll, setScalingAll] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fail = useCallback(
    (e: unknown) =>
      reportError({
        title: "Original stories",
        message: e instanceof Error ? e.message : String(e),
      }),
    [reportError]
  );

  const refresh = useCallback(async () => {
    try {
      const [s, c, j, y] = await Promise.all([
        api.listOriginalSeries(),
        api.listAnimeChannels(),
        api.listOriginalJobs(),
        api.youtubeStatus(),
      ]);
      setYt(y);
      setSeries(s);
      setChannels(c);
      setJobs(j);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const loadWorkbench = useCallback(
    async (slug: string, episode?: string, title?: string) => {
      setLoadingWorkbench(true);
      setStatusMessage(null);
      try {
        const data = await api.getOriginalStoryWorkbench(slug, episode);
        setWorkbenchData(data);
        setActiveStoryboard({
          slug,
          episode,
          title: title || data.title || slug,
        });
        setIsWorkbenchOpen(true);
        setCacheBuster(Date.now());

        // Check if any panels need review and trigger Notification
        const needsReviewCount = data.beats.filter((b) => b.status === "needs_review").length;
        if (needsReviewCount > 0 && typeof window !== "undefined" && "Notification" in window) {
          if (Notification.permission === "granted") {
            new Notification("PanelFlow Studio: Review Needed", {
              body: `${needsReviewCount} panel(s) flagged for creator review in ${data.title || slug}`,
            });
          } else if (Notification.permission !== "denied") {
            void Notification.requestPermission();
          }
        }
      } catch (e) {
        fail(e);
      } finally {
        setLoadingWorkbench(false);
      }
    },
    [fail]
  );

  const handleApprovePanel = async (panelId: string) => {
    if (!activeStoryboard) return;
    setOperatingPanelId(panelId);
    try {
      await api.approveOriginalPanel(activeStoryboard.slug, panelId, {
        episode: activeStoryboard.episode,
      });
      setStatusMessage(`Panel ${panelId} approved as-is.`);
      await loadWorkbench(activeStoryboard.slug, activeStoryboard.episode, activeStoryboard.title);
    } catch (e) {
      fail(e);
    } finally {
      setOperatingPanelId(null);
    }
  };

  const handleRerollPanel = async (panelId: string) => {
    if (!activeStoryboard) return;
    setOperatingPanelId(panelId);
    try {
      setStatusMessage(`Regenerating candidate for panel ${panelId}...`);
      await api.rerollOriginalPanel(activeStoryboard.slug, panelId, {
        episode: activeStoryboard.episode,
      });
      setStatusMessage(`Panel ${panelId} re-rolled successfully.`);
      await loadWorkbench(activeStoryboard.slug, activeStoryboard.episode, activeStoryboard.title);
    } catch (e) {
      fail(e);
    } finally {
      setOperatingPanelId(null);
    }
  };

  const handleScalePanel = async (panelId: string) => {
    if (!activeStoryboard) return;
    setOperatingPanelId(panelId);
    try {
      setStatusMessage(`Scaling panel ${panelId} (Lanczos 2x + Refiner pass)...`);
      await api.scaleOriginalPanel(activeStoryboard.slug, panelId, {
        episode: activeStoryboard.episode,
      });
      setStatusMessage(`Panel ${panelId} scaled to full 2x resolution.`);
      await loadWorkbench(activeStoryboard.slug, activeStoryboard.episode, activeStoryboard.title);
    } catch (e) {
      fail(e);
    } finally {
      setOperatingPanelId(null);
    }
  };

  const handleScaleStory = async () => {
    if (!activeStoryboard) return;
    setScalingAll(true);
    try {
      setStatusMessage(`Scaling all draft panels for ${activeStoryboard.title}...`);
      const res = await api.scaleOriginalStory(activeStoryboard.slug, {
        episode: activeStoryboard.episode,
      });
      setStatusMessage(`Batch scale complete: ${res.scaled_panels} panels scaled.`);
      await loadWorkbench(activeStoryboard.slug, activeStoryboard.episode, activeStoryboard.title);
    } catch (e) {
      fail(e);
    } finally {
      setScalingAll(false);
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      await api.createOriginalSeries({
        name: name.trim(),
        genre,
        idea: idea.trim(),
        channel_id: channelId,
      });
      setName("");
      setIdea("");
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const connectYoutube = async () => {
    setBusy(true);
    try {
      if (ytId.trim() && ytSecret.trim()) {
        await api.saveYoutubeClient(ytId.trim(), ytSecret.trim());
        setYtSecret("");
      }
      const { auth_url } = await api.youtubeConnect();
      window.open(auth_url, "_blank", "noopener");
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  // Upload is always a deliberate click per episode; the default is a private upload.
  const upload = async (seriesId: string, episode: number, schedule: boolean) => {
    if (forKids === null) {
      fail(
        new Error(
          "Choose whether your videos are made for kids first (a legal declaration only you can make)."
        )
      );
      return;
    }
    if (
      schedule &&
      !window.confirm("This schedules the video to become PUBLIC at its publish slot. Continue?")
    )
      return;
    setBusy(true);
    try {
      await api.uploadOriginalEpisode(seriesId, episode, {
        made_for_kids: forKids,
        schedule,
        confirm_public: schedule,
      });
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const queue = async (id: string) => {
    setBusy(true);
    try {
      await api.queueOriginalEpisodes(id, {
        count,
        ...(startDate ? { start_date: startDate } : {}),
        ...(refine ? { refine: true } : {}),
        ...(animate ? { animate: true } : {}),
        ...(preview ? { preview: true } : {}),
      });
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const needsReviewBeats = workbenchData?.beats.filter((b) => b.status === "needs_review") || [];

  return (
    <div className="min-h-screen bg-ink text-fg p-6 max-w-6xl mx-auto space-y-6">
      <button onClick={onBack} className="text-sm text-fg-dim hover:text-fg">
        ← Back to projects
      </button>
      <h1 className="text-xl font-bold">Original Stories</h1>
      <p className="text-sm text-fg-dim">
        A series keeps one cast, one world and the same character faces across episodes. Queue
        episodes and each becomes a story, illustrated panels, a narrated video, a comic PDF and a
        YouTube package, one publish slot per day. Read every script before you publish: these are
        AI-made.
      </p>

      {/* Storyboard Workbench (Collapsible Grid) */}
      {workbenchData && activeStoryboard && (
        <section className="rounded-2xl border border-edge bg-navy/40 p-5 space-y-4 shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-edge pb-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent/10 text-info border border-accent/20">
                <Film className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-fg">
                    Storyboard Workbench — {activeStoryboard.title}
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-flat text-fg-dim font-mono">
                    {workbenchData.beats.length} beats
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-accent/60 text-info border border-accent/40 font-medium capitalize">
                    {workbenchData.genre}
                  </span>
                </div>
                <p className="text-xs text-fg-dim mt-0.5">
                  Visual beat cards in narrative order. Click inspect for candidate iterations or
                  inpaint to surgically fix defective regions.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleScaleStory}
                disabled={scalingAll || loadingWorkbench}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent text-white text-xs font-semibold shadow transition-colors disabled:opacity-50"
                title="Scale all draft panels via 2x Lanczos + partial-denoise refiner"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{scalingAll ? "Scaling all..." : "Scale All Drafts (2x + Refiner)"}</span>
              </button>

              <button
                type="button"
                onClick={() =>
                  loadWorkbench(
                    activeStoryboard.slug,
                    activeStoryboard.episode,
                    activeStoryboard.title
                  )
                }
                disabled={loadingWorkbench}
                className="p-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg-dim text-xs transition-colors"
                title="Refresh workbench"
              >
                <RefreshCw className={`w-4 h-4 ${loadingWorkbench ? "animate-spin" : ""}`} />
              </button>

              <button
                type="button"
                onClick={() => setIsWorkbenchOpen(!isWorkbenchOpen)}
                className="p-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg-dim text-xs transition-colors"
                title={isWorkbenchOpen ? "Collapse workbench" : "Expand workbench"}
              >
                {isWorkbenchOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Status Alert / Feedback */}
          {statusMessage && (
            <div className="text-xs px-3 py-2 rounded-lg bg-accent/50 border border-accent/40 text-info flex items-center justify-between">
              <span>{statusMessage}</span>
              <button
                onClick={() => setStatusMessage(null)}
                className="text-fg-dim hover:text-fg"
              >
                ✕
              </button>
            </div>
          )}

          {/* Interactive Review Notification Banner */}
          {needsReviewBeats.length > 0 && (
            <div className="rounded-xl border border-bad/60 bg-bad/30 p-4 space-y-3">
              <div className="flex items-center gap-2 text-bad font-semibold text-xs uppercase tracking-wide">
                <AlertTriangle className="w-4 h-4 text-bad" />
                <span>Creator Review Needed — {needsReviewBeats.length} panel(s) flagged</span>
              </div>
              <p className="text-xs text-fg-dim">
                The assisted quality inspector paused auto-retry on these panels. Review and choose
                an action:
              </p>
              <div className="space-y-2">
                {needsReviewBeats.map((beat) => (
                  <div
                    key={beat.panel_id}
                    className="flex flex-wrap items-center justify-between gap-3 bg-ink/70 p-3 rounded-lg border border-bad/40 text-xs"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-14 h-9 rounded overflow-hidden bg-black flex-shrink-0 border border-edge">
                        <img
                          src={`${api.getOriginalPanelImageUrl(
                            workbenchData.slug,
                            beat.panel_id,
                            workbenchData.episode
                          )}?t=${cacheBuster}`}
                          alt={beat.panel_id}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div>
                        <div className="font-semibold text-fg">
                          #{beat.order} ({beat.panel_id}) — {beat.shot}
                        </div>
                        <div className="text-[11px] text-fg-dim line-clamp-1 max-w-md">
                          {beat.caption || beat.action}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleApprovePanel(beat.panel_id)}
                        disabled={operatingPanelId === beat.panel_id}
                        className="px-2.5 py-1 rounded-md bg-ok hover:bg-ok text-white font-medium text-[11px] transition-colors disabled:opacity-50"
                      >
                        Approve As-Is
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRerollPanel(beat.panel_id)}
                        disabled={operatingPanelId === beat.panel_id}
                        className="px-2.5 py-1 rounded-md bg-flat hover:bg-glass-hi text-fg border border-edge font-medium text-[11px] transition-colors disabled:opacity-50"
                      >
                        Reroll Seed
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setInpaintTarget({
                            mode: "story",
                            storySlug: workbenchData.slug,
                            episodeSlug: workbenchData.episode,
                            panelId: beat.panel_id,
                            imageSrc: api.getOriginalPanelImageUrl(
                              workbenchData.slug,
                              beat.panel_id,
                              workbenchData.episode
                            ),
                            onPanelUpdated: () =>
                              loadWorkbench(
                                activeStoryboard.slug,
                                activeStoryboard.episode,
                                activeStoryboard.title
                              ),
                          })
                        }
                        className="px-2.5 py-1 rounded-md bg-accent hover:bg-accent text-white font-medium text-[11px] transition-colors"
                      >
                        Inpaint Region
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Collapsible Beat Cards Grid */}
          {isWorkbenchOpen && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 pt-2">
              {workbenchData.beats.map((beat) => {
                const imgUrl = `${api.getOriginalPanelImageUrl(
                  workbenchData.slug,
                  beat.panel_id,
                  workbenchData.episode
                )}?t=${cacheBuster}`;

                const isOperating = operatingPanelId === beat.panel_id;

                return (
                  <div
                    key={beat.panel_id}
                    className="flex flex-col rounded-xl border border-edge bg-ink/80 overflow-hidden shadow hover:border-edge transition-all group"
                  >
                    {/* Beat Card Header */}
                    <div className="flex items-center justify-between px-3 py-2 bg-navy/60 border-b border-edge text-xs">
                      <div className="font-semibold text-fg-dim font-mono">
                        #{beat.order} ({beat.panel_id})
                      </div>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                          beat.status === "accept"
                            ? "bg-ok/20 text-ok border border-ok/60"
                            : beat.status === "accept_low"
                            ? "bg-warn/20 text-warn border border-warn/60"
                            : beat.status === "needs_review"
                            ? "bg-bad/20 text-bad border border-bad/60"
                            : beat.status === "repaired"
                            ? "bg-accent/20 text-info border border-accent/60"
                            : "bg-flat text-fg-dim border border-edge"
                        }`}
                      >
                        {(beat.status || "unverified").replace("_", " ").toUpperCase()}
                      </span>
                    </div>

                    {/* Thumbnail Image Container */}
                    <div className="relative aspect-video w-full bg-black overflow-hidden group">
                      <img
                        src={imgUrl}
                        alt={`Panel ${beat.panel_id}`}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />

                      {/* Audio Duration Chip */}
                      <div className="absolute bottom-2 left-2 flex items-center gap-1 bg-black/70 backdrop-blur-sm px-2 py-0.5 rounded text-[10px] text-fg-dim font-mono border border-white/10">
                        <Clock className="w-3 h-3 text-fg-dim" />
                        <span>
                          {beat.audio_duration ? `${beat.audio_duration}s` : "Est. 3.0s"}
                        </span>
                      </div>

                      {/* Iterations Count Chip */}
                      {beat.candidate_count > 1 && (
                        <div className="absolute top-2 right-2 flex items-center gap-1 bg-accent/80 backdrop-blur-sm px-2 py-0.5 rounded text-[10px] text-info font-mono border border-accent/50">
                          <Layers className="w-3 h-3" />
                          <span>{beat.candidate_count} cands</span>
                        </div>
                      )}
                    </div>

                    {/* Caption & Metadata */}
                    <div className="p-3 flex-1 flex flex-col justify-between space-y-2">
                      <p
                        className="text-xs text-fg-dim line-clamp-2 leading-relaxed"
                        title={beat.caption || beat.action}
                      >
                        {beat.caption || beat.action || "No narrative caption"}
                      </p>

                      {/* Action Buttons */}
                      <div className="pt-2 border-t border-edge/80 flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setInspectingBeat(beat)}
                          className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg text-[11px] font-medium transition-colors"
                          title="Inspect candidate iterations & defect bboxes"
                        >
                          <Eye className="w-3 h-3 text-fg-dim" />
                          <span>Inspect</span>
                        </button>

                        <button
                          type="button"
                          onClick={() =>
                            setInpaintTarget({
                              mode: "story",
                              storySlug: workbenchData.slug,
                              episodeSlug: workbenchData.episode,
                              panelId: beat.panel_id,
                              imageSrc: imgUrl,
                              onPanelUpdated: () =>
                                loadWorkbench(
                                  activeStoryboard.slug,
                                  activeStoryboard.episode,
                                  activeStoryboard.title
                                ),
                            })
                          }
                          className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-accent/80 hover:bg-accent text-white text-[11px] font-medium transition-colors"
                          title="Inpaint mask on panel"
                        >
                          <Wand2 className="w-3 h-3" />
                          <span>Inpaint</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleScalePanel(beat.panel_id)}
                          disabled={isOperating}
                          className="px-2 py-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg-dim text-[11px] font-medium transition-colors disabled:opacity-50"
                          title="Scale 2x with refiner denoise"
                        >
                          <Sparkles
                            className={`w-3 h-3 text-info ${
                              isOperating ? "animate-spin" : ""
                            }`}
                          />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* YouTube Section */}
      <section className="space-y-2 rounded-lg border border-edge p-4 text-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-fg-dim">YouTube</h2>
        <div className="text-fg-dim">
          {yt?.connected
            ? "Connected. Uploads are private unless you schedule a public release."
            : yt?.pending
            ? "Waiting for you to approve access in the browser…"
            : "Not connected. Create an OAuth client (Desktop app) in your Google Cloud project with the YouTube Data API enabled, then paste its id and secret."}
          {yt?.error && <span className="text-warn"> {yt.error}</span>}
        </div>
        {!yt?.connected && (
          <div className="flex gap-2">
            <input
              className="flex-1 bg-navy border border-edge rounded px-3 py-2"
              placeholder="OAuth client id"
              value={ytId}
              onChange={(e) => setYtId(e.target.value)}
            />
            <input
              className="flex-1 bg-navy border border-edge rounded px-3 py-2"
              type="password"
              placeholder="OAuth client secret"
              value={ytSecret}
              onChange={(e) => setYtSecret(e.target.value)}
            />
            <button
              disabled={busy}
              onClick={connectYoutube}
              className="px-3 rounded bg-accent hover:bg-accent disabled:opacity-40"
            >
              Connect
            </button>
          </div>
        )}
        {yt?.connected && (
          <button
            onClick={() => api.youtubeDisconnect().then(setYt).catch(fail)}
            className="px-3 py-1 rounded bg-flat hover:bg-glass-hi"
          >
            Disconnect
          </button>
        )}
        <div className="flex gap-4 text-fg-dim">
          <span>Made for kids?</span>
          <label>
            <input
              type="radio"
              name="kids"
              checked={forKids === true}
              onChange={() => setForKids(true)}
            />{" "}
            Yes
          </label>
          <label>
            <input
              type="radio"
              name="kids"
              checked={forKids === false}
              onChange={() => setForKids(false)}
            />{" "}
            No
          </label>
        </div>
      </section>

      {/* New Series Section */}
      <section className="space-y-3 rounded-lg border border-edge p-4">
        <h2 className="text-sm font-bold uppercase tracking-wide text-fg-dim">New series</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 bg-navy border border-edge rounded px-3 py-2 text-sm"
            placeholder="Series name (e.g. Moon Tales)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="bg-navy border border-edge rounded px-3 py-2 text-sm"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
          >
            {GENRES.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </div>
        <input
          className="w-full bg-navy border border-edge rounded px-3 py-2 text-sm"
          placeholder="Idea (optional): a sleepy fox who collects lullabies"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
        />
        <select
          className="w-full bg-navy border border-edge rounded px-3 py-2 text-sm"
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
        >
          <option value="">No channel preset (genre defaults)</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} — {c.voice}
            </option>
          ))}
        </select>
        <button
          disabled={busy || name.trim().length < 2}
          onClick={create}
          className="px-4 py-2 rounded bg-accent hover:bg-accent disabled:opacity-40 text-sm font-semibold"
        >
          {busy ? "Working…" : "Create series"}
        </button>
      </section>

      {/* Series & Episodes Queue Section */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-fg-dim">Queue</span>
          <input
            type="number"
            min={1}
            max={30}
            className="w-16 bg-navy border border-edge rounded px-2 py-1"
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
          />
          <span className="text-fg-dim">episodes, first live on</span>
          <input
            type="date"
            className="bg-navy border border-edge rounded px-2 py-1"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <label
            className="flex items-center gap-1.5 text-fg-dim cursor-pointer"
            title="Review every picture against its narration, then repair or redraw the ones that fail. Slower (about a minute more per picture); every try is kept, and repaired pictures are flagged for a look."
          >
            <input
              type="checkbox"
              checked={refine}
              onChange={(e) => setRefine(e.target.checked)}
            />
            check and fix pictures (slower)
          </label>
          <label
            className="flex items-center gap-1.5 text-fg-dim cursor-pointer"
            title="Move about one picture in five with the fast H3 video model (about a minute each). The rest stay still. If a clip fails, that picture just stays still."
          >
            <input
              type="checkbox"
              checked={animate}
              onChange={(e) => setAnimate(e.target.checked)}
            />
            animate key moments (slower)
          </label>
          <label
            className="flex items-center gap-1.5 text-info font-medium cursor-pointer"
            title="Fast 0.25 MP draft pass (8-11s sampling). Skips final TTS/video render so you can inspect beats in the Storyboard Studio before full scaling."
          >
            <input
              type="checkbox"
              checked={preview}
              onChange={(e) => setPreview(e.target.checked)}
            />
            preview drafts only (fast 0.25 MP)
          </label>
        </div>

        {series.length === 0 && <p className="text-sm text-fg-faint">No series yet.</p>}
        {series.map((s) => (
          <div key={s.id} className="rounded-xl border border-edge p-4 text-sm space-y-3 bg-navy/30">
            <div className="flex justify-between items-start gap-3">
              <div>
                <div className="font-semibold text-base text-fg">{s.name}</div>
                <div className="text-xs text-fg-dim">
                  {s.genre} · {s.bible.premise.logline}
                </div>
                <div className="text-xs text-fg-faint">
                  Cast: {s.bible.characters.map((c) => c.name).join(", ")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => loadWorkbench(s.id, undefined, `${s.name} (Latest)`)}
                  className="px-3 py-1.5 rounded-lg bg-flat hover:bg-glass-hi text-fg text-xs font-medium border border-edge"
                >
                  Workbench
                </button>
                <button
                  disabled={busy}
                  onClick={() => queue(s.id)}
                  className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent text-white text-xs font-semibold disabled:opacity-40 whitespace-nowrap"
                >
                  Queue {count}
                </button>
              </div>
            </div>

            {s.episodes.map((e) => (
              <div
                key={e.number}
                className="text-xs flex flex-wrap items-center justify-between border-t border-edge/80 pt-2 gap-2"
              >
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      loadWorkbench(s.id, e.number.toString(), `${s.name} — Ep ${e.number}`)
                    }
                    className="font-medium text-info hover:text-info hover:underline text-left"
                  >
                    Ep {e.number}: {e.title || "…"}
                  </button>
                  {e.warnings.length > 0 && (
                    <span className="text-warn"> · {e.warnings.length} warnings</span>
                  )}
                </div>

                <div className="text-fg-dim flex items-center gap-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-mono ${
                      e.status === "done"
                        ? "bg-ok/20 text-ok"
                        : e.status === "draft"
                        ? "bg-accent/20 text-info border border-accent/40"
                        : "bg-flat text-fg-dim"
                    }`}
                  >
                    {e.status}
                  </span>
                  {e.publish_at ? (
                    <span className="text-fg-faint">
                      slot {e.publish_at.slice(0, 16).replace("T", " ")}
                    </span>
                  ) : null}
                  {e.youtube_url ? (
                    <a
                      className="text-ok hover:underline"
                      href={e.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {e.youtube_privacy}
                    </a>
                  ) : null}
                  {e.upload_status === "uploading" && <span>uploading…</span>}
                  {e.upload_status === "failed" && (
                    <span className="text-warn" title={e.upload_error}>
                      upload failed
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={() =>
                      loadWorkbench(s.id, e.number.toString(), `${s.name} — Ep ${e.number}`)
                    }
                    className="px-2 py-0.5 rounded bg-flat hover:bg-glass-hi text-fg-dim text-[11px]"
                  >
                    Open Storyboard
                  </button>

                  {e.status === "done" &&
                    !e.youtube_url &&
                    yt?.connected &&
                    e.upload_status !== "uploading" && (
                      <>
                        <button
                          disabled={busy}
                          onClick={() => upload(s.id, e.number, false)}
                          className="px-2 py-0.5 rounded bg-flat hover:bg-glass-hi text-fg-dim"
                        >
                          Upload private
                        </button>
                        <button
                          disabled={busy || !e.publish_at}
                          onClick={() => upload(s.id, e.number, true)}
                          className="px-2 py-0.5 rounded bg-flat hover:bg-glass-hi text-fg-dim"
                        >
                          Schedule public
                        </button>
                      </>
                    )}
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>

      {/* Jobs Section */}
      <section className="space-y-2">
        <h2 className="text-sm font-bold uppercase tracking-wide text-fg-dim">Jobs</h2>
        {jobs.length === 0 && <p className="text-sm text-fg-faint">No episode jobs yet.</p>}
        {jobs.map((j) => (
          <div key={j.job_id} className="rounded-xl border border-edge p-3 text-sm bg-navy/30">
            <div className="flex justify-between">
              <span>{(j.input as { title?: string }).title ?? j.job_id}</span>
              <span className="text-fg-dim font-mono text-xs">{j.status}</span>
            </div>
            <div className="h-1.5 bg-flat rounded mt-2 overflow-hidden">
              <div
                className="h-1.5 bg-accent rounded transition-all duration-300"
                style={{ width: `${Math.round(j.progress * 100)}%` }}
              />
            </div>
            <div className="text-xs text-fg-dim mt-1">{j.error ?? j.message}</div>
            {j.status === "SUCCEEDED" && (
              <div className="text-xs text-ok mt-1 break-all">
                {String((j.output as { video?: string }).video ?? "")}
              </div>
            )}
          </div>
        ))}
      </section>

      {/* Candidate Inspector Drawer / Modal */}
      {inspectingBeat && activeStoryboard && (
        <CandidateInspectorModal
          isOpen={!!inspectingBeat}
          onClose={() => setInspectingBeat(null)}
          storySlug={activeStoryboard.slug}
          episodeSlug={activeStoryboard.episode}
          beat={inspectingBeat}
          onSelectCandidate={async () => {
            await handleApprovePanel(inspectingBeat.panel_id);
          }}
          onOpenInpaint={(target) => {
            if (target.mode === "story") {
              setInpaintTarget({
                ...target,
                onPanelUpdated: () =>
                  loadWorkbench(
                    activeStoryboard.slug,
                    activeStoryboard.episode,
                    activeStoryboard.title
                  ),
              });
            } else {
              setInpaintTarget(target);
            }
          }}
        />
      )}

      {/* Image Editor Modal (Inpaint Bridge) */}
      {inpaintTarget && (
        <ImageEditorModal
          isOpen={!!inpaintTarget}
          onClose={() => setInpaintTarget(null)}
          target={inpaintTarget}
        />
      )}
    </div>
  );
};
