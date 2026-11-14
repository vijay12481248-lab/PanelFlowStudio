import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { AudioTimelineResponse, CharacterEntity, Project } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel, Skeleton, useToast } from "@panelflow/ui-v2";
import { useEngine } from "../../../app/providers";
import { useError } from "../../../context/ErrorContext";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { JobProgress } from "../kit/JobProgress";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { isActiveJob, stageKeys, useJob, useProjectJobs } from "../kit/stageData";
import { formatClock } from "../motion/motionModel";
import { castingValue, defaultCasting, voicesFromProviders, type Casting } from "./casting";
import { IntervalList } from "./IntervalList";
import { MasterPlayer } from "./MasterPlayer";
import { VoiceCastingDialog } from "./VoiceCastingDialog";
import { useIntervalPlayback, type PlaybackOptions } from "./useIntervalPlayback";

export interface AudioStageProps {
  project: Project;
  /** Called with the reloaded project after the audio is approved. */
  onApproved: (updated: Project) => void;
  /** Move on to Motion (already approved). */
  onContinue: (project: Project) => void;
  /** Replaces the browser's audio element and timers in tests. */
  playback?: Pick<PlaybackOptions, "createAudio" | "timers">;
}

const timelineKey = (projectId: string) => ["stages", "audio", projectId] as const;
const GENERATE_ADVICE = "Open Settings and check that the speech provider is ready, then try again. The engine log in Diagnostics has the details.";

/** Audio: generate the voice track, choose voices, listen through every take, approve. */
export const AudioStage: React.FC<AudioStageProps> = ({ project, onApproved, onContinue, playback: playbackOptions }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { connected } = useEngine();
  const { reportError } = useError();

  const timelineQuery = useQuery<AudioTimelineResponse | null>({ queryKey: timelineKey(project.id), queryFn: () => api.getAudioTimeline(project.id).catch(() => null), enabled: connected, retry: false });
  const charactersQuery = useQuery<CharacterEntity[]>({ queryKey: ["stages", "characters", project.id], queryFn: () => api.listCharacters(project.id).catch(() => []), enabled: connected, retry: false });
  const providersQuery = useQuery({ queryKey: ["stages", "audio-providers"], queryFn: () => api.getAudioProviders(), enabled: connected, retry: false });
  const jobsQuery = useProjectJobs(project.id);

  const timeline = timelineQuery.data ?? null;
  const characters = charactersQuery.data ?? [];
  const voices = React.useMemo(() => voicesFromProviders(providersQuery.data), [providersQuery.data]);
  const intervals = timeline?.timeline?.intervals ?? [];
  const totalSeconds = timeline?.total_duration || timeline?.timeline?.total_duration_sec || 0;
  const speechCount = timeline?.timeline?.speech_intervals_count ?? intervals.filter((iv) => iv.audio_file_uri && (iv as any).is_speech !== false).length;
  const sampleRate: number | undefined = timeline?.timeline?.sample_rate_hz ?? (timeline?.timeline as any)?.sample_rate;
  const approved = timeline?.status === "APPROVED" || project.current_stage === "AUDIO_APPROVED";

  // The casting sent with the next generation: the engine's saved choices, then generic defaults for anyone left out, then edits.
  const [edited, setEdited] = React.useState<Casting | null>(null);
  const casting = React.useMemo(() => edited ?? defaultCasting(characters, voices, timeline?.voice_casting ?? {}), [edited, characters, voices, timeline?.voice_casting]);
  const castCount = characters.filter((c) => castingValue(casting, c)).length;

  const [castingOpen, setCastingOpen] = React.useState(false);
  const [confirmReplace, setConfirmReplace] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [approving, setApproving] = React.useState(false);
  const [starting, setStarting] = React.useState(false);
  const [regenerating, setRegenerating] = React.useState<ReadonlySet<string>>(new Set());
  const busy = React.useRef(false);
  const regenBusy = React.useRef(new Set<string>());

  // Follow a generation job: one started here, or one already running when the stage opened.
  const [jobId, setJobId] = React.useState<string | undefined>();
  const handled = React.useRef(new Set<string>());
  const latestAudioJob = jobsQuery.data?.find((j) => j.job_type === "AUDIO_GENERATION");
  React.useEffect(() => {
    if (!jobId && latestAudioJob && isActiveJob(latestAudioJob) && !handled.current.has(latestAudioJob.job_id)) setJobId(latestAudioJob.job_id);
  }, [jobId, latestAudioJob?.job_id, latestAudioJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const job = useJob(jobId);
  React.useEffect(() => {
    const finished = job.data;
    if (!jobId || !finished || isActiveJob(finished)) return;
    handled.current.add(jobId);
    setJobId(undefined);
    void queryClient.invalidateQueries({ queryKey: stageKeys.jobs(project.id) });
    if (finished.status === "SUCCEEDED") {
      void queryClient.invalidateQueries({ queryKey: timelineKey(project.id) });
      toast.show("Voice track generated.");
    } else {
      setError(refusal("Couldn't generate the audio.", new Error(finished.error ?? ""), GENERATE_ADVICE));
    }
  }, [jobId, job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const generating = starting || jobId !== undefined;

  const generate = async (withCasting: Casting) => {
    if (busy.current || generating) return;
    busy.current = true;
    setStarting(true);
    setError(null);
    try {
      setJobId((await api.generateAudioJob(project.id, withCasting)).job_id);
    } catch (err: any) {
      setError(refusal("Couldn't generate the audio.", err, GENERATE_ADVICE));
      reportError({
        title: "Audio Generation Failed", message: "Failed to generate audio timeline.", severity: "error", source: "job", projectId: project.id, jobType: "AUDIO_GENERATION", rawDetails: err,
        suggestions: ["Open Settings and check that the speech provider is ready.", "Open Diagnostics for the engine log."],
      });
    } finally { busy.current = false; setStarting(false); }
  };

  const regenerate = async (segmentId: string) => {
    if (regenBusy.current.has(segmentId)) return;
    regenBusy.current.add(segmentId);
    setRegenerating(new Set(regenBusy.current));
    setError(null);
    try {
      await api.regenerateAudioSegment(project.id, segmentId);
      await queryClient.invalidateQueries({ queryKey: timelineKey(project.id) });
      toast.show("Take regenerated.");
    } catch (err: any) {
      setError(refusal("Couldn't regenerate that take.", err, "Try again in a moment."));
      reportError({ title: "Audio Segment Regeneration Failed", message: "Could not regenerate dialogue voice line.", severity: "error", source: "pipeline", projectId: project.id, jobType: "AUDIO_GENERATION", rawDetails: { segmentId, error: err } });
    } finally { regenBusy.current.delete(segmentId); setRegenerating(new Set(regenBusy.current)); }
  };

  const approve = async () => {
    if (busy.current || !timeline || approved) return;
    busy.current = true;
    setApproving(true);
    setError(null);
    try {
      await api.approveAudio(project.id);
      const updated = await api.getProject(project.id);
      queryClient.setQueryData<AudioTimelineResponse | null>(timelineKey(project.id), (prev) => (prev ? { ...prev, status: "APPROVED" } : prev));
      toast.show("Audio approved.");
      onApproved(updated);
    } catch (err: any) {
      setError(refusal("Audio can't be approved yet.", err, "Generate the audio again, then try approving."));
      reportError({ title: "Audio Approval Gate Blocked", message: "Audio timeline verification failed.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { busy.current = false; setApproving(false); }
  };

  const player = useIntervalPlayback(intervals, {
    urlFor: (iv) => api.getAudioFileUrl(project.id, iv.audio_file_uri ?? ""),
    onFinished: () => toast.show("Playback finished."),
    ...playbackOptions,
  });

  // Keep the active take in view while the track plays.
  React.useEffect(() => {
    if (player.playing && player.activeIndex !== null) document.getElementById(`audio-interval-${player.activeIndex}`)?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [player.playing, player.activeIndex]);

  const active = player.activeIndex !== null ? intervals[player.activeIndex] : undefined;
  const nowPlaying = active ? ((active as any).text || active.cue_text || "") : null;
  const statusChip = approved ? <Chip tone="ok">Approved</Chip> : timeline ? <Chip tone="accent">Draft</Chip> : <Chip>Not generated</Chip>;

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review the voice track"
        description="Generate the voices, listen to every take, redo any line that is wrong, then approve."
        status={statusChip}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setCastingOpen(true)}>Voice casting</Button>
            <Button variant="secondary" size="sm" loading={generating} onClick={() => (timeline ? setConfirmReplace(true) : void generate(casting))}>{timeline ? "Regenerate audio" : "Generate audio"}</Button>
            {timeline && !approved && <Button variant="primary" size="sm" loading={approving} onClick={() => void approve()}>Approve audio</Button>}
            {approved && <Button variant="secondary" size="sm" disabled>Audio approved</Button>}
            {approved && <Button variant="primary" size="sm" onClick={() => onContinue(project)}>Continue to motion</Button>}
          </>
        }
      />

      {generating && <GlassPanel blur={false} className="p-4" role="status"><JobProgress job={job.data} idleLabel="Starting the voice generation." /></GlassPanel>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {timeline?.warnings?.map((warning, i) => <p key={i} className="text-sm text-warn">{warning}</p>)}

      {timeline && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Total length" value={formatClock(totalSeconds)} detail={`${totalSeconds.toFixed(1)}s`} />
          <Stat label="Dialogue lines" value={`${speechCount} takes`} />
          <Stat label="Sample rate" value={sampleRate ? `${sampleRate.toLocaleString("en-US")} Hz` : "Not reported"} />
          <Stat label="Voices cast" value={`${castCount} of ${characters.length} characters`} />
        </div>
      )}

      {timelineQuery.isLoading ? (
        <Skeleton className="h-64" />
      ) : !timeline ? (
        <GlassPanel blur={false}>
          <EmptyState title="No voice track yet" description="Generate audio to turn the script into spoken takes. You can choose voices first with Voice casting." />
        </GlassPanel>
      ) : (
        <>
          {intervals.length > 0 && <MasterPlayer playback={player} totalSeconds={totalSeconds} nowPlaying={nowPlaying} count={intervals.length} />}
          <p className="text-sm text-fg-dim">Each take's length is measured from its audio file. Regenerate a take to redo that one line without touching the others.</p>
          <IntervalList
            intervals={intervals}
            characters={characters}
            activeIndex={player.activeIndex}
            playing={player.playing}
            regenerating={regenerating}
            onPlay={player.playFrom}
            onPause={player.pause}
            onRegenerate={(segmentId) => void regenerate(segmentId)}
          />
        </>
      )}

      <VoiceCastingDialog
        open={castingOpen}
        characters={characters}
        voices={voices}
        voicesFailed={providersQuery.isError}
        casting={casting}
        onClose={() => setCastingOpen(false)}
        onSave={(next) => { setEdited(next); setCastingOpen(false); toast.show("Voice casting saved."); }}
        onSaveAndGenerate={(next) => { setEdited(next); setCastingOpen(false); void generate(next); }}
      />
      <ConfirmDialog
        open={confirmReplace}
        title="Replace the voice track?"
        description="Regenerating makes every line again and replaces the current takes."
        confirmLabel="Replace voice track"
        onConfirm={() => { setConfirmReplace(false); void generate(casting); }}
        onCancel={() => setConfirmReplace(false)}
      />
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; detail?: string }> = ({ label, value, detail }) => (
  <GlassPanel blur={false} className="grid gap-1 p-3">
    <p className="text-xs text-fg-faint">{label}</p>
    <p className="font-display text-lg font-semibold text-fg">{value}{detail && <span className="ml-1.5 text-xs font-normal text-fg-dim">{`(${detail})`}</span>}</p>
  </GlassPanel>
);
