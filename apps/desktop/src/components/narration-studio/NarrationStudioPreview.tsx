import React, { useState } from "react";
import { Icons } from "@panelflow/ui";
import { NarrationStudio } from "./NarrationStudio";
import { MOCK_CHAPTER } from "./NarrationStudio.mock";
import type { NarrationChapter, NarrationToTimelineContract } from "./NarrationStudio.types";

export const NarrationStudioPreview: React.FC = () => {
  const [chapter, setChapter] = useState<NarrationChapter>(MOCK_CHAPTER);
  const [lastExportedContract, setLastExportedContract] = useState<NarrationToTimelineContract | null>(null);
  const [eventLogs, setEventLogs] = useState<string[]>([]);
  const [showLogDrawer, setShowLogDrawer] = useState<boolean>(false);

  const addLog = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setEventLogs((logs) => [`[${timestamp}] ${msg}`, ...logs.slice(0, 49)]);
  };

  const handleReset = () => {
    setChapter({ ...MOCK_CHAPTER, updated_at: new Date().toISOString() });
    addLog("Reset workspace to initial mock chapter (Chapter 14: Whispers in the Obsidian Vault).");
  };

  const handleScenarioChange = (scenario: "default" | "drafts" | "climax") => {
    if (scenario === "default") {
      setChapter(MOCK_CHAPTER);
      addLog("Loaded Scenario A: Balanced standard multi-character chapter.");
    } else if (scenario === "drafts") {
      setChapter({
        ...MOCK_CHAPTER,
        segments: MOCK_CHAPTER.segments.map((s) => ({
          ...s,
          review_status: "DRAFT",
          generation_status: "OUTDATED",
        })),
      });
      addLog("Loaded Scenario B: All segments marked DRAFT & OUTDATED (Stress Testing Review Flow).");
    } else if (scenario === "climax") {
      setChapter({
        ...MOCK_CHAPTER,
        segments: MOCK_CHAPTER.segments.slice(4), // Segments 5-8
      });
      addLog("Loaded Scenario C: High-intensity boss climax sequence (Segments 5 to 8).");
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-zinc-950 overflow-hidden">
      {/* Top Testing Banner */}
      <div className="h-8 bg-zinc-900 border-b border-zinc-800 px-3 flex items-center justify-between text-xs select-none shrink-0 z-50">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-bold text-zinc-200">
            Narration Studio Independent Preview Harness
          </span>
          <span className="text-[10px] text-zinc-500 font-mono hidden sm:inline">
            (Isolated from Timeline & App.tsx)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Preset Scenarios */}
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-zinc-500">Scenario:</span>
            <select
              onChange={(e) => handleScenarioChange(e.target.value as any)}
              className="bg-zinc-950 border border-zinc-800 rounded px-1.5 py-0.5 text-zinc-300 focus:outline-none focus:border-indigo-500 cursor-pointer text-xs"
            >
              <option value="default">Standard Chapter (8 Segments)</option>
              <option value="drafts">Unreviewed Drafts (Stress Test)</option>
              <option value="climax">Boss Climax Sequence</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleReset}
            className="text-[11px] font-semibold text-zinc-400 hover:text-white px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 transition-colors"
          >
            Reset Chapter
          </button>

          <button
            type="button"
            onClick={() => setShowLogDrawer((v) => !v)}
            className="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded bg-indigo-950/80 border border-indigo-800 transition-colors flex items-center gap-1"
          >
            <span>Activity Log</span>
            <span className="font-mono text-[9px] bg-indigo-900 px-1 rounded">
              {eventLogs.length}
            </span>
          </button>
        </div>
      </div>

      {/* Main Workspace Component */}
      <div className="flex-1 min-h-0 relative">
        <NarrationStudio
          initialChapter={chapter}
          onChapterSave={(updated) => {
            setChapter(updated);
            addLog(`Chapter saved (${updated.segments.length} segments).`);
          }}
          onSegmentApproved={(seg) => {
            addLog(`Segment #${seg.sequence} marked APPROVED.`);
          }}
          onExportTimelineContract={(contract) => {
            setLastExportedContract(contract);
            addLog(`Exported Timeline Contract (${contract.clips.length} clips serialized).`);
          }}
        />

        {/* Activity Log Drawer */}
        {showLogDrawer && (
          <div className="absolute top-0 right-0 w-80 h-full bg-zinc-900/95 border-l border-zinc-800 p-3 shadow-2xl z-50 flex flex-col text-xs select-none">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-2">
              <span className="font-bold text-zinc-200 uppercase tracking-wider text-[11px]">
                Preview Activity Log
              </span>
              <button
                type="button"
                onClick={() => setShowLogDrawer(false)}
                className="text-zinc-400 hover:text-zinc-200 p-0.5 rounded hover:bg-zinc-800 transition-colors"
                title="Close Log"
              >
                <Icons.X className="w-3.5 h-3.5" />
              </button>

            </div>

            <div className="flex-1 overflow-y-auto space-y-1 font-mono text-[10px]">
              {eventLogs.length === 0 ? (
                <div className="text-zinc-500 italic p-4 text-center">
                  No interactions recorded yet. Edit a script or approve a segment to see events.
                </div>
              ) : (
                eventLogs.map((log, idx) => (
                  <div key={idx} className="p-1 rounded bg-zinc-950/80 text-zinc-300 border border-zinc-800/60 leading-normal">
                    {log}
                  </div>
                ))
              )}
            </div>

            {lastExportedContract && (
              <div className="pt-2 border-t border-zinc-800 text-[10px] text-zinc-400">
                <span className="font-semibold text-emerald-400">Contract Ready:</span>{" "}
                {lastExportedContract.clips.length} clips in payload.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
