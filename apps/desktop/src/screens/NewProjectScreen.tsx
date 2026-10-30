import React, { useState, useEffect, useRef } from "react";
import { api } from "@panelflow/api-client";
import type {
  Project,
  RightsStatus,
  SourceType,
  SourceInspection,
  SeriesInspectResponse,
  BatchJobStatusInfo,
  AnimeInspectResponse,
  AnimeJobStatusInfo,
} from "@panelflow/shared-types";
import { Button, Card, Input, Select, Badge, ProgressBar, Icons } from "@panelflow/ui";

interface NewProjectScreenProps {
  onBack: () => void;
  onProjectCreated: (project: Project) => void;
}

export const NewProjectScreen: React.FC<NewProjectScreenProps> = ({
  onBack,
  onProjectCreated,
}) => {
  // Common metadata
  const [title, setTitle] = useState<string>("");
  const [sourceType, setSourceType] = useState<SourceType>("LOCAL_FOLDER");
  const [sourcePath, setSourcePath] = useState<string>("");
  const [destinationPath, setDestinationPath] = useState<string>("");
  const [rightsStatus, setRightsStatus] = useState<RightsStatus | "">("");
  const [licenseNotes, setLicenseNotes] = useState<string>("");

  // Single Chapter Storytelling settings
  const [storyStyle, setStoryStyle] = useState("Cinematic");
  const [narrationLength, setNarrationLength] = useState("Medium");
  const [language, setLanguage] = useState("en");
  const [autoMusic, setAutoMusic] = useState(false);
  const [autoSfx, setAutoSfx] = useState(false);
  const [musicPath, setMusicPath] = useState("");
  const [sfxPath, setSfxPath] = useState("");
  const [ttsProvider, setTtsProvider] = useState("kokoro_82m");

  // Multi-Chapter Manga / Series settings
  const [inspectingSeries, setInspectingSeries] = useState(false);
  const [seriesMeta, setSeriesMeta] = useState<SeriesInspectResponse | null>(null);
  const [seriesInspectError, setSeriesInspectError] = useState<string | null>(null);
  const [chapterStart, setChapterStart] = useState<string>("");
  const [chapterEnd, setChapterEnd] = useState<string>("");
  const [compilationMode, setCompilationMode] = useState<"compiled" | "individual">("compiled");
  const [targetDuration, setTargetDuration] = useState<number>(25);
  const [seriesVoice, setSeriesVoice] = useState("am_michael");
  const [seriesSubtitles, setSeriesSubtitles] = useState(true);
  const [batchJob, setBatchJob] = useState<BatchJobStatusInfo | null>(null);
  const [batchStarting, setBatchStarting] = useState(false);

  // Video / Anime Review settings
  const [inspectingVideo, setInspectingVideo] = useState(false);
  const [videoInspect, setVideoInspect] = useState<AnimeInspectResponse | null>(null);
  const [videoInspectError, setVideoInspectError] = useState<string | null>(null);
  const [episodeNumber, setEpisodeNumber] = useState<number>(1);
  const [episodeTitle, setEpisodeTitle] = useState<string>("");
  const [videoVoice, setVideoVoice] = useState("am_michael");
  const [minCut, setMinCut] = useState<number>(2.0);
  const [maxCut, setMaxCut] = useState<number>(4.5);
  const [duckDb, setDuckDb] = useState<number>(-18.0);
  const [antiCopyright, setAntiCopyright] = useState(true);
  const [animeJob, setAnimeJob] = useState<AnimeJobStatusInfo | null>(null);
  const [animeStarting, setAnimeStarting] = useState(false);

  // Standard Source Inspection
  const [inspecting, setInspecting] = useState<boolean>(false);
  const [inspection, setInspection] = useState<SourceInspection | null>(null);
  const [inspectError, setInspectError] = useState<string | null>(null);

  // Form Submission
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Timers for live job tracking
  const batchPollRef = useRef<number | null>(null);
  const animePollRef = useRef<number | null>(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (batchPollRef.current) clearInterval(batchPollRef.current);
      if (animePollRef.current) clearInterval(animePollRef.current);
    };
  }, []);

  // Poll batch generation status
  useEffect(() => {
    if (batchJob && (batchJob.status === "QUEUED" || batchJob.status === "RUNNING")) {
      batchPollRef.current = window.setInterval(async () => {
        try {
          const updated = await api.getBatchJobStatus(batchJob.job_id);
          setBatchJob(updated);
          if (updated.status === "COMPLETED" || updated.status === "FAILED" || updated.status === "CANCELLED") {
            if (batchPollRef.current) clearInterval(batchPollRef.current);
          }
        } catch (e) {
          console.error("Batch poll error:", e);
        }
      }, 1500);
    }
    return () => {
      if (batchPollRef.current) clearInterval(batchPollRef.current);
    };
  }, [batchJob?.status]);

  // Poll anime review generation status
  useEffect(() => {
    if (animeJob && (animeJob.status === "QUEUED" || animeJob.status === "RUNNING")) {
      animePollRef.current = window.setInterval(async () => {
        try {
          const updated = await api.getAnimeJobStatus(animeJob.job_id);
          setAnimeJob(updated);
          if (updated.status === "COMPLETED" || updated.status === "FAILED") {
            if (animePollRef.current) clearInterval(animePollRef.current);
          }
        } catch (e) {
          console.error("Anime review poll error:", e);
        }
      }, 1500);
    }
    return () => {
      if (animePollRef.current) clearInterval(animePollRef.current);
    };
  }, [animeJob?.status]);

  // Handler: Inspect Standard Source
  const handleInspect = async () => {
    if (!sourcePath.trim()) return;
    setInspecting(true);
    setInspectError(null);
    setInspection(null);
    try {
      const res = await api.inspectSource(sourcePath.trim());
      setInspection(res);
      if (res.is_valid && (res.source_type === "LOCAL_FOLDER" || res.source_type === "ZIP_ARCHIVE" || res.source_type === "AUTHORIZED_WEB")) {
        setSourceType(res.source_type);
      }
      if (res.title_suggestion && !title.trim()) {
        setTitle(res.title_suggestion);
      }
      if (!res.is_valid && res.error) {
        setInspectError(res.error);
      }
    } catch (err: any) {
      setInspectError(err.message || "Failed to inspect source.");
    } finally {
      setInspecting(false);
    }
  };

  // Handler: Inspect Multi-Chapter Manga Series
  const handleInspectSeries = async () => {
    if (!sourcePath.trim()) return;
    setInspectingSeries(true);
    setSeriesInspectError(null);
    setSeriesMeta(null);
    try {
      const res = await api.inspectSeries(sourcePath.trim());
      setSeriesMeta(res);
      if (res.title && !title.trim()) {
        setTitle(res.title);
      }
      if (res.detected_range && res.detected_range.length === 2) {
        setChapterStart(String(res.detected_range[0]));
        setChapterEnd(String(res.detected_range[1]));
      }
    } catch (err: any) {
      setSeriesInspectError(err.message || "Failed to discover series chapters.");
    } finally {
      setInspectingSeries(false);
    }
  };

  // Handler: Inspect Video File
  const handleInspectVideo = async () => {
    if (!sourcePath.trim()) return;
    setInspectingVideo(true);
    setVideoInspectError(null);
    setVideoInspect(null);
    try {
      const res = await api.inspectAnimeVideo(
        sourcePath.trim(),
        title.trim() || "Anime Series",
        episodeNumber
      );
      setVideoInspect(res);
      if (!res.valid && res.error) {
        setVideoInspectError(res.error);
      }
    } catch (err: any) {
      setVideoInspectError(err.message || "Failed to inspect video stream.");
    } finally {
      setInspectingVideo(false);
    }
  };

  // Handler: Trigger Batch Multi-Chapter Video Generation
  const handleStartBatchGeneration = async () => {
    if (!sourcePath.trim()) return;
    setBatchStarting(true);
    setSubmitError(null);
    try {
      const res = await api.startBatchGeneration({
        source_url: sourcePath.trim(),
        compilation_mode: compilationMode,
        target_duration_minutes: targetDuration,
        chapter_start: chapterStart ? parseFloat(chapterStart) : undefined,
        chapter_end: chapterEnd ? parseFloat(chapterEnd) : undefined,
        tts_voice: seriesVoice,
        subtitles: seriesSubtitles,
        video_profile: "standard_1080p",
      });
      if (res.job_id) {
        const initialStatus = await api.getBatchJobStatus(res.job_id);
        setBatchJob(initialStatus);
      }
    } catch (err: any) {
      setSubmitError(err.message || "Failed to schedule batch generation.");
    } finally {
      setBatchStarting(false);
    }
  };

  // Handler: Trigger Automated Anime Review Video Generation
  const handleStartAnimeReview = async () => {
    if (!sourcePath.trim()) return;
    setAnimeStarting(true);
    setSubmitError(null);
    try {
      const res = await api.startAnimeReview({
        source_video: sourcePath.trim(),
        series_title: title.trim() || "Anime Series",
        episode_number: episodeNumber,
        episode_title: episodeTitle.trim() || undefined,
        tts_voice: videoVoice,
        min_cut_length_sec: minCut,
        max_cut_length_sec: maxCut,
        original_audio_duck_db: duckDb,
        anti_copyright_transform: antiCopyright,
        crop_to_1080p: true,
        subtitles: true,
      });
      if (res.job_id) {
        const initialStatus = await api.getAnimeJobStatus(res.job_id);
        setAnimeJob(initialStatus);
      }
    } catch (err: any) {
      setSubmitError(err.message || "Failed to start anime review pipeline.");
    } finally {
      setAnimeStarting(false);
    }
  };

  // Handler: Standard Project Creation & Proceed to Acquisition Screen
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (!title.trim()) {
      setSubmitError("Please enter a project title.");
      return;
    }
    if (!sourcePath.trim()) {
      setSubmitError("Please provide a valid source folder, archive, video, or URL.");
      return;
    }
    if (!rightsStatus || rightsStatus === "UNKNOWN") {
      setSubmitError(
        "A valid, verified Rights Status is required. Projects with UNKNOWN rights cannot proceed into the acquisition pipeline."
      );
      return;
    }

    setSubmitting(true);
    try {
      const proj = await api.createProject({
        title: title.trim(),
        source_type: sourceType,
        source_url: sourcePath.trim(),
        rights_status: rightsStatus as RightsStatus,
        license_info: licenseNotes.trim(),
        settings: {
          ...(destinationPath.trim() ? { project_path: destinationPath.trim() } : {}),
          ...(sourceType === "AUTHORIZED_WEB"
            ? {
                visual_storytelling: true,
                story_style: storyStyle,
                narration_length: narrationLength,
                language,
                tts_provider: ttsProvider,
                auto_music: autoMusic,
                auto_sfx: autoSfx,
                chapter_music_path: musicPath,
                sfx_library_path: sfxPath,
              }
            : {}),
          ...(sourceType === "MANGA_SERIES"
            ? {
                series_mode: true,
                compilation_mode: compilationMode,
                target_duration_minutes: targetDuration,
                chapter_start: chapterStart ? parseFloat(chapterStart) : undefined,
                chapter_end: chapterEnd ? parseFloat(chapterEnd) : undefined,
                tts_voice: seriesVoice,
              }
            : {}),
          ...(sourceType === "VIDEO_FILE"
            ? {
                video_review: true,
                episode_number: episodeNumber,
                episode_title: episodeTitle,
                tts_voice: videoVoice,
                min_cut: minCut,
                max_cut: maxCut,
                duck_db: duckDb,
              }
            : {}),
        },
      });
      onProjectCreated(proj);
    } catch (err: any) {
      setSubmitError(err.message || "Failed to create project.");
    } finally {
      setSubmitting(false);
    }
  };

  const getSourcePlaceholder = () => {
    switch (sourceType) {
      case "LOCAL_FOLDER":
        return "e.g. C:\\Comics\\Volume_01 or D:\\Comics\\Issue_1";
      case "ZIP_ARCHIVE":
        return "e.g. C:\\Comics\\chapter_01.cbz or D:\\Comics\\volume_01.zip";
      case "AUTHORIZED_WEB":
        return "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-923/";
      case "MANGA_SERIES":
        return "https://manhuaplus.com/manga/demon-magic-emperor01/ or chapter URL";
      case "VIDEO_FILE":
        return "e.g. C:\\Videos\\Solo_Leveling_EP01.mp4 or episode video file";
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <Icons.ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Create New Project</h2>
          <p className="text-xs text-zinc-400">
            Define project metadata, select ingestion mode, and inspect acquisition & video generation options.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Source Ingestion Card */}
        <Card className="space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <Icons.Folder className="w-4 h-4 text-indigo-400" />
              1. Source Ingestion & Production Mode
            </h3>
            <span className="text-[11px] text-zinc-500">Select pipeline target</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              {
                type: "LOCAL_FOLDER",
                label: "Local Folder",
                icon: Icons.Folder,
                desc: "Folder of raw comic/manga image files",
              },
              {
                type: "ZIP_ARCHIVE",
                label: "ZIP / CBZ Archive",
                icon: Icons.Archive,
                desc: ".zip or .cbz comic book archive",
              },
              {
                type: "AUTHORIZED_WEB",
                label: "Manga Chapter URL",
                icon: Icons.Globe,
                desc: "Single chapter visual storytelling",
              },
              {
                type: "MANGA_SERIES",
                label: "Multi-Chapter Manga",
                icon: Icons.Layers,
                desc: "Series catalog discovery & batch compilation",
              },
              {
                type: "VIDEO_FILE",
                label: "Video Review & Recap",
                icon: Icons.Film,
                desc: "Anime / video cut detection & review voiceover",
              },
            ].map((s) => {
              const IconComp = s.icon;
              const isSelected = sourceType === s.type;
              return (
                <button
                  type="button"
                  key={s.type}
                  onClick={() => {
                    setSourceType(s.type as SourceType);
                    setInspection(null);
                    setSeriesMeta(null);
                    setVideoInspect(null);
                    setInspectError(null);
                    setSeriesInspectError(null);
                    setVideoInspectError(null);
                  }}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? "border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50 shadow-md shadow-indigo-950/40"
                      : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"
                  }`}
                >
                  <IconComp className={`w-5 h-5 mb-2 ${isSelected ? "text-indigo-400" : "text-zinc-400"}`} />
                  <div className="font-semibold text-sm text-zinc-200">{s.label}</div>
                  <div className="text-xs text-zinc-500 mt-0.5">{s.desc}</div>
                </button>
              );
            })}
          </div>

          {/* Source Input & Action */}
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                label={
                  sourceType === "VIDEO_FILE"
                    ? "Video File Path (.mp4, .mkv, .webm)"
                    : sourceType === "MANGA_SERIES"
                    ? "Manga Series Index or Chapter URL"
                    : "Source Path or URL"
                }
                placeholder={getSourcePlaceholder()}
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                required
              />
              <div className="flex items-end">
                {sourceType === "MANGA_SERIES" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    onClick={handleInspectSeries}
                    loading={inspectingSeries}
                    disabled={!sourcePath.trim()}
                    className="whitespace-nowrap bg-indigo-900/40 hover:bg-indigo-900/60 border-indigo-700/50 text-indigo-200"
                  >
                    <Icons.Globe className="w-4 h-4 mr-1.5" />
                    Inspect Series
                  </Button>
                ) : sourceType === "VIDEO_FILE" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    onClick={handleInspectVideo}
                    loading={inspectingVideo}
                    disabled={!sourcePath.trim()}
                    className="whitespace-nowrap bg-amber-900/40 hover:bg-amber-900/60 border-amber-700/50 text-amber-200"
                  >
                    <Icons.Film className="w-4 h-4 mr-1.5" />
                    Inspect Video
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    onClick={handleInspect}
                    loading={inspecting}
                    disabled={!sourcePath.trim()}
                    className="whitespace-nowrap"
                  >
                    Inspect Source
                  </Button>
                )}
              </div>
            </div>
          </div>

          {/* Standard Inspection Error */}
          {inspectError && (
            <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-center gap-2">
              <Icons.AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{inspectError}</span>
            </div>
          )}

          {/* Standard Inspection Result */}
          {inspection && inspection.is_valid && (
            <div className="p-3.5 bg-zinc-950 border border-zinc-800 rounded-lg space-y-2 text-xs">
              <div className="flex items-center justify-between text-emerald-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <Icons.CheckCircle className="w-4 h-4" />
                  Source verified successfully
                </span>
                <Badge variant="success">{inspection.total_pages_detected} pages discovered</Badge>
              </div>
              {inspection.title_suggestion && (
                <div className="text-zinc-300">
                  <span className="text-zinc-500">Suggested Title:</span> {inspection.title_suggestion}
                </div>
              )}
            </div>
          )}
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* PANEL: MULTI-CHAPTER MANGA REVIEW & BATCH VIDEO GENERATION         */}
        {/* ------------------------------------------------------------------ */}
        {sourceType === "MANGA_SERIES" && (
          <Card className="space-y-5 border-indigo-500/30 bg-indigo-950/10">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Icons.Layers className="w-5 h-5 text-indigo-400" />
                <h3 className="text-sm font-bold text-zinc-100">
                  Multi-Chapter Manga Review & Batch Video Generation Panel
                </h3>
              </div>
              <Badge variant="accent">Multi-Chapter Pipeline</Badge>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              Discovers the entire manga catalog across web sources, extracts structured chapter lists, and enables single-click batch generation of individual episodes or compiled multi-chapter movie cuts.
            </p>

            {seriesInspectError && (
              <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-center gap-2">
                <Icons.AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{seriesInspectError}</span>
              </div>
            )}

            {seriesMeta && (
              <div className="p-4 bg-zinc-950/80 border border-indigo-900/50 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-bold text-zinc-100">{seriesMeta.title}</h4>
                    <span className="text-xs text-indigo-400 font-mono">{seriesMeta.source_domain}</span>
                  </div>
                  <Badge variant="success">
                    {seriesMeta.total_chapters_detected} Chapters Detected
                  </Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs text-zinc-400">
                  <div>
                    <span className="text-zinc-500">Detected Range:</span>{" "}
                    <span className="text-zinc-200 font-mono">
                      Ch {seriesMeta.detected_range[0]} - Ch {seriesMeta.detected_range[1]}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Strategy:</span>{" "}
                    <span className="text-zinc-200">{seriesMeta.discovery_strategy}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Pattern:</span>{" "}
                    <span className="text-zinc-200 font-mono truncate block" title={seriesMeta.url_pattern || "N/A"}>
                      {seriesMeta.url_pattern || "Inferred from index"}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Compilation & Production Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <Select
                label="Production Mode"
                value={compilationMode}
                onChange={(e) => setCompilationMode(e.target.value as any)}
              >
                <option value="compiled">Compiled Multi-Chapter Movie Cut (e.g. 25-min cut)</option>
                <option value="individual">Individual Chapter Episodes (1 video per chapter)</option>
              </Select>

              {compilationMode === "compiled" && (
                <Input
                  label="Target Compilation Duration (Minutes)"
                  type="number"
                  min="5"
                  max="120"
                  value={targetDuration}
                  onChange={(e) => setTargetDuration(parseFloat(e.target.value) || 25)}
                />
              )}

              <Input
                label="Chapter Start Number"
                placeholder={seriesMeta ? String(seriesMeta.detected_range[0]) : "e.g. 921"}
                value={chapterStart}
                onChange={(e) => setChapterStart(e.target.value)}
              />

              <Input
                label="Chapter End Number"
                placeholder={seriesMeta ? String(seriesMeta.detected_range[1]) : "e.g. 927"}
                value={chapterEnd}
                onChange={(e) => setChapterEnd(e.target.value)}
              />

              <Select
                label="Neural Voice Profile"
                value={seriesVoice}
                onChange={(e) => setSeriesVoice(e.target.value)}
              >
                <option value="am_michael">am_michael (American Male - Storyteller)</option>
                <option value="am_adam">am_adam (American Male - Deep Narrator)</option>
                <option value="af_bella">af_bella (American Female - Dynamic)</option>
                <option value="af_nicole">af_nicole (American Female - Expressive)</option>
                <option value="bf_alice">bf_alice (British Female - Calm)</option>
                <option value="bm_george">bm_george (British Male - Dramatic)</option>
              </Select>

              <div className="flex items-center pt-6">
                <label className="text-xs text-zinc-300 flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={seriesSubtitles}
                    onChange={(e) => setSeriesSubtitles(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-indigo-500"
                  />
                  Burn synchronized 1080p subtitles
                </label>
              </div>
            </div>

            {/* Batch Generation Direct Action */}
            <div className="pt-2 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-zinc-400">
                You can start multi-chapter batch video production directly or proceed to create the project workspace below.
              </div>
              <Button
                type="button"
                variant="primary"
                onClick={handleStartBatchGeneration}
                loading={batchStarting}
                disabled={!sourcePath.trim()}
                className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-md shadow-indigo-600/30"
              >
                <Icons.Zap className="w-4 h-4 mr-1.5 text-amber-300" />
                Start Batch Video Generation
              </Button>
            </div>

            {/* Live Batch Job Progress Tracker */}
            {batchJob && (
              <div className="p-4 bg-zinc-950 border border-indigo-700/60 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse" />
                    <span className="text-xs font-bold text-zinc-200 uppercase">
                      Batch Production: {batchJob.status}
                    </span>
                  </div>
                  <Badge variant={batchJob.status === "COMPLETED" ? "success" : "accent"}>
                    {batchJob.completed_chapters} / {batchJob.total_chapters} chapters
                  </Badge>
                </div>

                <ProgressBar progress={batchJob.progress} label={batchJob.current_step || "Processing..."} />

                {batchJob.current_chapter && (
                  <div className="text-xs text-indigo-300">
                    <span className="text-zinc-500">Current Chapter:</span> {batchJob.current_chapter}
                  </div>
                )}

                {batchJob.generated_videos && batchJob.generated_videos.length > 0 && (
                  <div className="space-y-1.5 pt-2">
                    <div className="text-xs font-semibold text-emerald-400">Generated Episode Videos:</div>
                    <div className="max-h-28 overflow-y-auto space-y-1 text-xs text-zinc-300 font-mono bg-zinc-900/80 p-2.5 rounded-lg border border-zinc-800">
                      {batchJob.generated_videos.map((vid, idx) => (
                        <div key={idx} className="truncate flex items-center gap-1.5">
                          <Icons.Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                          <span title={vid}>{vid}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* PANEL: VIDEO REVIEW & ANIME RECAP GENERATION                       */}
        {/* ------------------------------------------------------------------ */}
        {sourceType === "VIDEO_FILE" && (
          <Card className="space-y-5 border-amber-500/30 bg-amber-950/10">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Icons.Film className="w-5 h-5 text-amber-400" />
                <h3 className="text-sm font-bold text-zinc-100">
                  Video Review & Anime Recap Generation Panel
                </h3>
              </div>
              <Badge variant="warning">Video Ingestion Pipeline</Badge>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              Ingests raw anime or episode video files (.mp4/.mkv), automatically detects scene transitions and dynamic keyframe cuts, writes a 4-act recap and commentary review script, synthesizes neural voiceover, and produces a copyright-safe 1080p recap video.
            </p>

            {videoInspectError && (
              <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-center gap-2">
                <Icons.AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{videoInspectError}</span>
              </div>
            )}

            {videoInspect && videoInspect.valid && (
              <div className="p-4 bg-zinc-950/80 border border-amber-900/50 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-bold text-zinc-100">{videoInspect.series_title}</h4>
                    <span className="text-xs text-amber-400">Episode {videoInspect.episode_number} Stream</span>
                  </div>
                  <Badge variant="success">Stream Validated</Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-zinc-400">
                  <div>
                    <span className="text-zinc-500">Resolution:</span>{" "}
                    <span className="text-zinc-200 font-mono">{videoInspect.resolution}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Duration:</span>{" "}
                    <span className="text-zinc-200 font-mono">{videoInspect.duration_formatted}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Frame Rate:</span>{" "}
                    <span className="text-zinc-200 font-mono">{videoInspect.fps} fps</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Est. Scene Cuts:</span>{" "}
                    <span className="text-amber-400 font-mono font-bold">~{videoInspect.estimated_cuts} cuts</span>
                  </div>
                </div>
              </div>
            )}

            {/* Video Review Parameters */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <Input
                label="Episode Number"
                type="number"
                step="0.5"
                value={episodeNumber}
                onChange={(e) => setEpisodeNumber(parseFloat(e.target.value) || 1)}
              />

              <Input
                label="Episode Title / Subtitle (Optional)"
                placeholder="e.g. I'm Used to It, or Awakened Hunter"
                value={episodeTitle}
                onChange={(e) => setEpisodeTitle(e.target.value)}
              />

              <Select
                label="Narrator / Reviewer Voice Profile"
                value={videoVoice}
                onChange={(e) => setVideoVoice(e.target.value)}
              >
                <option value="am_michael">am_michael (Fast, engaging male review voice)</option>
                <option value="am_adam">am_adam (Deep cinematic male tone)</option>
                <option value="af_bella">af_bella (Energetic female anime commentator)</option>
                <option value="af_nicole">af_nicole (Emotional storytelling tone)</option>
                <option value="bm_george">bm_george (Analytical British reviewer)</option>
              </Select>

              <div className="space-y-1">
                <label className="text-xs font-medium text-zinc-300">
                  Original Audio Ducking: <span className="font-mono text-amber-400">{duckDb} dB</span>
                </label>
                <input
                  type="range"
                  min="-30"
                  max="-6"
                  step="1"
                  value={duckDb}
                  onChange={(e) => setDuckDb(parseFloat(e.target.value))}
                  className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <span className="text-[10px] text-zinc-500 block">
                  Preserves original BGM and battle SFX beneath narrator commentary.
                </span>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-zinc-300">
                  Scene Cut Pacing: <span className="font-mono text-zinc-200">{minCut}s - {maxCut}s</span>
                </label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    step="0.5"
                    min="1.0"
                    max="4.0"
                    value={minCut}
                    onChange={(e) => setMinCut(parseFloat(e.target.value) || 2.0)}
                    placeholder="Min Cut"
                  />
                  <Input
                    type="number"
                    step="0.5"
                    min="2.5"
                    max="10.0"
                    value={maxCut}
                    onChange={(e) => setMaxCut(parseFloat(e.target.value) || 4.5)}
                    placeholder="Max Cut"
                  />
                </div>
              </div>

              <div className="flex items-center pt-6">
                <label className="text-xs text-zinc-300 flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={antiCopyright}
                    onChange={(e) => setAntiCopyright(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-900 text-amber-600 focus:ring-amber-500"
                  />
                  Anti-Copyright dynamic reframing & subtle scaling
                </label>
              </div>
            </div>

            {/* Direct Action */}
            <div className="pt-2 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-zinc-400">
                Produce a full automated anime review video or create the project workspace to edit scenes manually.
              </div>
              <Button
                type="button"
                variant="primary"
                onClick={handleStartAnimeReview}
                loading={animeStarting}
                disabled={!sourcePath.trim()}
                className="bg-amber-600 hover:bg-amber-500 text-white font-semibold shadow-md shadow-amber-600/30"
              >
                <Icons.Play className="w-4 h-4 mr-1.5" />
                Generate Video Review & Recap
              </Button>
            </div>

            {/* Live Anime Review Job Progress */}
            {animeJob && (
              <div className="p-4 bg-zinc-950 border border-amber-700/60 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
                    <span className="text-xs font-bold text-zinc-200 uppercase">
                      Video Review: {animeJob.status}
                    </span>
                  </div>
                  <Badge variant={animeJob.status === "COMPLETED" ? "success" : "warning"}>
                    {animeJob.status}
                  </Badge>
                </div>

                <ProgressBar progress={animeJob.progress} label={animeJob.current_step || "Processing..."} />

                {animeJob.result && (
                  <div className="p-3 bg-zinc-900 border border-emerald-800/60 rounded-lg space-y-2 text-xs">
                    <div className="text-emerald-400 font-bold flex items-center gap-1.5">
                      <Icons.CheckCircle className="w-4 h-4" />
                      Anime Review Video Generated Successfully!
                    </div>
                    <div className="text-zinc-300 font-mono truncate" title={animeJob.result.output_video_path}>
                      Output: {animeJob.result.output_video_path}
                    </div>
                    <div className="flex gap-4 text-zinc-400 text-[11px]">
                      <span>Duration: {animeJob.result.video_duration_sec.toFixed(1)}s</span>
                      <span>Total Cuts: {animeJob.result.total_scene_cuts}</span>
                      <span>Review Beats: {animeJob.result.total_review_beats}</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* PANEL: SINGLE CHAPTER VISUAL STORYTELLING                         */}
        {/* ------------------------------------------------------------------ */}
        {sourceType === "AUTHORIZED_WEB" && (
          <Card className="space-y-4">
            <h3 className="text-sm font-semibold text-zinc-200">Chapter Storytelling</h3>
            <p className="text-xs text-zinc-400">
              Analyze source panels with a vision model, review the chapter story, then approve original narration before voice generation.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select label="Story style" value={storyStyle} onChange={(e) => setStoryStyle(e.target.value)}>
                {[
                  "Cinematic",
                  "Dramatic",
                  "Neutral recap",
                  "Emotional",
                  "Fast YouTube recap",
                  "Detailed storyteller",
                ].map((style) => (
                  <option key={style}>{style}</option>
                ))}
              </Select>
              <Select label="Narration length" value={narrationLength} onChange={(e) => setNarrationLength(e.target.value)}>
                {["Short", "Medium", "Detailed"].map((length) => (
                  <option key={length}>{length}</option>
                ))}
              </Select>
              <Input label="Narration language" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="en, hi, ja…" />
              <Input label="Chapter music file (optional)" value={musicPath} onChange={(e) => setMusicPath(e.target.value)} placeholder="Path to a local music track" />
              <Input label="SFX library folder (optional)" value={sfxPath} onChange={(e) => setSfxPath(e.target.value)} placeholder="Folder containing sword_draw.wav, wind.wav…" />
              <label className="text-xs text-zinc-300 flex items-center gap-2">
                <input type="checkbox" checked={autoMusic} onChange={(e) => setAutoMusic(e.target.checked)} />
                Generate chapter music with local Lumina / ACE-Step
              </label>
              <label className="text-xs text-zinc-300 flex items-center gap-2">
                <input type="checkbox" checked={autoSfx} onChange={(e) => setAutoSfx(e.target.checked)} />
                Select sparse effects from the local SFX library
              </label>
              <Select label="Installed speech adapter" value={ttsProvider} onChange={(e) => setTtsProvider(e.target.value)}>
                <option value="kokoro_82m">Kokoro-82M (Neural Fast Voice)</option>
                <option value="chatterbox_turbo">Chatterbox Turbo</option>
                <option value="f5_tts">F5-TTS</option>
              </Select>
            </div>
          </Card>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* PANEL: LOCAL FOLDER / ARCHIVE ACQUISITION PREVIEW                  */}
        {/* ------------------------------------------------------------------ */}
        {(sourceType === "LOCAL_FOLDER" || sourceType === "ZIP_ARCHIVE") && (
          <div className="p-3.5 bg-zinc-900/60 border border-zinc-800 rounded-xl text-xs text-zinc-400 flex items-center gap-3">
            <Icons.Info className="w-5 h-5 text-indigo-400 flex-shrink-0" />
            <div>
              <span className="font-semibold text-zinc-200">Pipeline Ingestion Flow:</span> When you click{" "}
              <span className="text-indigo-300 font-medium">"Create & Proceed to Acquisition"</span> below, this project will advance to the dedicated Acquisition Screen to extract pages, normalize resolution, and detect comic panels.
            </div>
          </div>
        )}

        {/* 2. Project Information & Storage */}
        <Card className="space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
            2. Project Information & Storage
          </h3>

          <Input
            label="Project Title"
            placeholder="e.g. The Adventures of Captain Freedom #1"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />

          <Input
            label="Project Destination Directory (Optional)"
            placeholder="e.g. C:\My PanelFlow Projects\Captain Freedom (defaults to Windows user workspace)"
            value={destinationPath}
            onChange={(e) => setDestinationPath(e.target.value)}
          />
        </Card>

        {/* 3. Rights & Licensing Card */}
        <Card className="space-y-4 border-amber-900/40 bg-zinc-900/80">
          <div className="flex items-center gap-2 text-amber-400 text-sm font-semibold uppercase tracking-wider">
            <Icons.ShieldCheck className="w-5 h-5" />
            3. Legal & Rights Verification (Mandatory)
          </div>

          <p className="text-xs text-zinc-400 leading-relaxed">
            PanelFlow Studio is designed exclusively for public domain, licensed, user-owned, or explicitly permitted material.
            Material marked <span className="text-rose-400 font-semibold">UNKNOWN</span> cannot be processed.
          </p>

          <Select
            label="Rights Status"
            value={rightsStatus}
            onChange={(e) => setRightsStatus(e.target.value as RightsStatus)}
            required
          >
            <option value="" disabled>-- Select Verified Rights Classification --</option>
            <option value="PUBLIC_DOMAIN">PUBLIC DOMAIN (Verified in public domain / expired copyright)</option>
            <option value="CREATIVE_COMMONS">CREATIVE COMMONS (CC-BY, CC0, CC-BY-SA, etc.)</option>
            <option value="USER_OWNED">USER OWNED (Original work created by user)</option>
            <option value="LICENSED">LICENSED (Commercial or private license held)</option>
            <option value="EXPLICIT_PERMISSION">EXPLICIT PERMISSION (Written authorization from creator)</option>
          </Select>

          <Input
            label="License / Permission Notes (Optional)"
            placeholder="e.g. Public Domain Mark 1.0 (US pre-1928), or Author written email permission dated 2026-03-01"
            value={licenseNotes}
            onChange={(e) => setLicenseNotes(e.target.value)}
            helperText="Documenting license terms or author attribution helps ensure automated downstream publishing compliance."
          />
        </Card>

        {/* Submit Error */}
        {submitError && (
          <div className="p-3.5 bg-rose-950/60 border border-rose-800 rounded-lg text-sm text-rose-200 flex items-center gap-2.5">
            <Icons.XCircle className="w-5 h-5 flex-shrink-0" />
            <span>{submitError}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={onBack}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={submitting}
            disabled={!rightsStatus || rightsStatus === "UNKNOWN"}
          >
            Create & Proceed to Acquisition
          </Button>
        </div>
      </form>
    </div>
  );
};
