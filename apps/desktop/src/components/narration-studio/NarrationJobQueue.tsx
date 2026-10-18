import React, { useState, useEffect, useRef } from "react";
import { Icons, Button, ProgressBar } from "@panelflow/ui";
import type {
  NarrationSegment,
  JobStatus,
} from "./NarrationStudio.types";

interface NarrationJobQueueProps {
  segment: NarrationSegment;
  allSegments: NarrationSegment[];
  onUpdateSegment: (updates: Partial<NarrationSegment>) => void;
  onBatchUpdateSegments: (segmentIds: string[], updates: Partial<NarrationSegment>) => void;
  className?: string;
}

export const NarrationJobQueue: React.FC<NarrationJobQueueProps> = ({
  segment,
  allSegments,
  onUpdateSegment,
  onBatchUpdateSegments,
  className = "",
}) => {
  const [showQueueList, setShowQueueList] = useState<boolean>(false);
  const simulationTimerRef = useRef<any>(null);
  const segmentRef = useRef(segment);
  segmentRef.current = segment;

  // Clean up simulation timer
  useEffect(() => {
    return () => {
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
      }
    };
  }, []);

  // Summary counts
  const statusCounts = {
    ready: allSegments.filter((s) => s.generation_status === "READY").length,
    queued: allSegments.filter((s) => s.generation_status === "QUEUED" || s.generation_status === "PROCESSING").length,
    outdated: allSegments.filter((s) => s.generation_status === "OUTDATED").length,
    unqueued: allSegments.filter((s) => s.generation_status === "UNQUEUED").length,
  };

  // Simulate local job execution through realistic state transitions with stale revision rejection
  const startLocalSimulation = (targetSegmentId: string) => {
    // Capture snapshot of target revision and hash when job is queued
    const targetRevision = segment.text_revision || 1;
    const targetHash = segment.content_hash;

    // 1. Set to QUEUED
    onUpdateSegment({
      generation_status: "QUEUED",
      generation_progress: 10,
      generation_error: null,
      updated_at: new Date().toISOString(),
    });

    // 2. Advance to PROCESSING after 700ms
    setTimeout(() => {
      // Check if user edited text while job was queued
      if (segmentRef.current.text_revision !== targetRevision) {
        onUpdateSegment({
          generation_status: "OUTDATED",
          generation_progress: 0,
          generation_error: `Stale synthesis rejected: Text modified to Rev #${segmentRef.current.text_revision} while Rev #${targetRevision} was queued.`,
          updated_at: new Date().toISOString(),
        });
        return;
      }

      onUpdateSegment({
        generation_status: "PROCESSING",
        generation_progress: 45,
        updated_at: new Date().toISOString(),
      });

      // 3. Complete to READY after another 1200ms
      setTimeout(() => {
        // Check if user edited text or delivery while job was processing
        if (
          segmentRef.current.text_revision !== targetRevision ||
          segmentRef.current.content_hash !== targetHash
        ) {
          onUpdateSegment({
            generation_status: "OUTDATED",
            generation_progress: 0,
            generation_error: `Stale synthesis rejected: Text was modified to Rev #${segmentRef.current.text_revision} while Rev #${targetRevision} was synthesizing.`,
            updated_at: new Date().toISOString(),
          });
          return;
        }

        // Clean completion matching current script revision
        onUpdateSegment({
          generation_status: "READY",
          generation_progress: 100,
          measured_duration_sec: Math.round((segmentRef.current.estimated_duration_sec + 0.2) * 10) / 10,
          audio_asset_uri: `/assets/demo/${targetSegmentId}_generated.mp3`,
          generated_audio_revision: targetRevision,
          generation_error: null,
          updated_at: new Date().toISOString(),
        });
      }, 1200);
    }, 700);
  };

  const handleCancelJob = () => {
    if (simulationTimerRef.current) {
      clearInterval(simulationTimerRef.current);
    }
    onUpdateSegment({
      generation_status: "UNQUEUED",
      generation_progress: 0,
      generation_error: null,
      updated_at: new Date().toISOString(),
    });
  };

  const handleSimulateFailure = () => {
    onUpdateSegment({
      generation_status: "FAILED",
      generation_progress: 0,
      generation_error: "Mock Error: Simulated VRAM allocation threshold reached (Error #408).",
      updated_at: new Date().toISOString(),
    });
  };

  const handleQueueAllOutdated = () => {
    const outdatedIds = allSegments
      .filter((s) => s.generation_status === "OUTDATED" || s.generation_status === "UNQUEUED")
      .map((s) => s.id);

    if (outdatedIds.length === 0) return;

    onBatchUpdateSegments(outdatedIds, {
      generation_status: "QUEUED",
      generation_progress: 15,
      updated_at: new Date().toISOString(),
    });

    // Simulate batch progression
    setTimeout(() => {
      onBatchUpdateSegments(outdatedIds, {
        generation_status: "READY",
        generation_progress: 100,
        updated_at: new Date().toISOString(),
      });
    }, 1800);
  };

  // Helper for status styling
  const renderStatusDetails = () => {
    switch (segment.generation_status) {
      case "PROCESSING":
        return (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-semibold text-indigo-400">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                Synthesizing speech with voice profile...
              </span>
              <span>{segment.generation_progress || 45}%</span>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${segment.generation_progress || 45}%` }}
              />
            </div>
          </div>
        );

      case "QUEUED":
        return (
          <div className="flex items-center justify-between text-xs p-2 rounded bg-zinc-950 border border-zinc-800 text-zinc-300">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-indigo-400" />
              Queued in local background scheduler
            </span>
            <span className="text-[10px] font-mono text-zinc-500">Position #1</span>
          </div>
        );

      case "READY":
        return (
          <div className="flex items-center justify-between text-xs p-2 rounded bg-emerald-950/40 border border-emerald-800/60 text-emerald-300">
            <span className="flex items-center gap-1.5">
              <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
              Generated audio ready for preview
            </span>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">100%</span>
          </div>
        );

      case "OUTDATED":
        return (
          <div className="space-y-1 p-2 rounded bg-amber-950/40 border border-amber-800/60 text-amber-300 text-xs">
            <div className="flex items-center justify-between font-bold text-[11px]">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                Audio is Outdated
              </span>
              <span className="text-[10px] uppercase font-mono">Regen Needed</span>
            </div>
            <p className="text-[10px] text-amber-200/80 leading-normal">
              {segment.generation_error || "Script text was modified after generation. Regenerate to align speech with current text."}
            </p>
          </div>
        );

      case "FAILED":
        return (
          <div className="space-y-1 p-2 rounded bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs">
            <span className="font-bold text-[11px] flex items-center gap-1">
              <Icons.XCircle className="w-3.5 h-3.5 text-rose-400" />
              Generation Failed (Simulated)
            </span>
            <p className="text-[10px] text-rose-200/80 font-mono">
              {segment.generation_error || "Unknown synthesis failure."}
            </p>
          </div>
        );

      case "UNQUEUED":
      default:
        return (
          <div className="text-zinc-500 text-xs p-2 rounded bg-zinc-950 border border-zinc-800 flex items-center justify-between">
            <span>No audio generated for this segment yet</span>
            <span className="text-[10px] uppercase font-mono text-zinc-600">Idle</span>
          </div>
        );
    }
  };

  return (
    <div className={`p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-3 select-none text-xs ${className}`}>
      {/* Header & Simulation Badge */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <div className="flex items-center gap-1.5">
          <span className="w-5 h-5 rounded-md bg-indigo-600/80 text-white flex items-center justify-center font-bold text-[10px]">
            ⚙️
          </span>
          <span className="font-bold text-zinc-200 uppercase tracking-wider text-[11px]">
            Narration Job Engine
          </span>
        </div>

        <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-bold border border-zinc-700">
          Simulated Local UI State
        </span>
      </div>

      {/* Segment Status Card */}
      {renderStatusDetails()}

      {/* Simulated Actions */}
      <div className="flex items-center gap-2 pt-1">
        {segment.generation_status === "QUEUED" || segment.generation_status === "PROCESSING" ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleCancelJob}
            className="text-xs h-7 flex-1"
          >
            Cancel Job
          </Button>
        ) : segment.generation_status === "OUTDATED" ? (
          <Button
            variant="primary"
            size="sm"
            onClick={() => startLocalSimulation(segment.id)}
            className="text-xs h-7 flex-1 bg-amber-600 hover:bg-amber-500 text-white font-bold"
          >
            Regenerate Audio
          </Button>
        ) : segment.generation_status === "READY" ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => startLocalSimulation(segment.id)}
            className="text-xs h-7 flex-1 border border-zinc-700"
          >
            Re-synthesize
          </Button>
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={() => startLocalSimulation(segment.id)}
            className="text-xs h-7 flex-1 bg-indigo-600 hover:bg-indigo-500 font-bold"
          >
            Queue Generation
          </Button>
        )}

        <button
          type="button"
          onClick={handleSimulateFailure}
          className="text-[10px] text-zinc-500 hover:text-rose-400 px-2 py-1 rounded hover:bg-zinc-800"
          title="Simulate error state for UI verification"
        >
          Simulate Error
        </button>
      </div>

      {/* Chapter Batch Stats Bar */}
      <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between text-[11px] text-zinc-400">
        <div className="flex items-center gap-2">
          <span>Ready: <strong className="text-emerald-400 font-mono">{statusCounts.ready}</strong></span>
          <span>•</span>
          <span>Outdated: <strong className="text-amber-400 font-mono">{statusCounts.outdated}</strong></span>
        </div>

        <button
          type="button"
          onClick={() => setShowQueueList((v) => !v)}
          className="text-[10px] text-indigo-400 hover:underline font-semibold"
        >
          {showQueueList ? "Hide Queue" : `View Chapter Queue (${allSegments.length})`}
        </button>
      </div>

      {/* Expandable Chapter Queue Overview */}
      {showQueueList && (
        <div className="p-2 rounded-lg bg-zinc-950 border border-zinc-800 space-y-2 max-h-48 overflow-y-auto">
          <div className="flex items-center justify-between text-[10px] font-bold uppercase text-zinc-500">
            <span>All Segments</span>
            {statusCounts.outdated > 0 && (
              <button
                type="button"
                onClick={handleQueueAllOutdated}
                className="text-indigo-400 hover:text-indigo-300 font-bold underline"
              >
                Queue Outdated ({statusCounts.outdated})
              </button>
            )}
          </div>

          <div className="space-y-1">
            {allSegments.map((s) => (
              <div
                key={s.id}
                className={`p-1.5 rounded flex items-center justify-between text-[10px] ${
                  s.id === segment.id ? "bg-indigo-950/60 border border-indigo-800/80" : "bg-zinc-900"
                }`}
              >
                <div className="flex items-center gap-1.5 truncate">
                  <span className="font-mono text-zinc-500">#{s.sequence}</span>
                  <span className="text-zinc-200 truncate max-w-[140px]">{s.speaker_name}</span>
                </div>
                <span
                  className={`font-mono text-[9px] font-bold px-1.5 py-0.2 rounded ${
                    s.generation_status === "READY"
                      ? "bg-emerald-950 text-emerald-400"
                      : s.generation_status === "OUTDATED"
                      ? "bg-amber-950 text-amber-400"
                      : s.generation_status === "FAILED"
                      ? "bg-rose-950 text-rose-400"
                      : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {s.generation_status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
