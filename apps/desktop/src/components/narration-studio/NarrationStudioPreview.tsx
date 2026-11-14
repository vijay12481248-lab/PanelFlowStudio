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
    <div className="flex flex-col h-screen w-screen bg-ink overflow-hidden">
      {/* Top Testing Banner */}
      <div className="h-8 bg-navy border-b border-edge px-3 flex items-center justify-between text-xs select-none shrink-0 z-50">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-ok animate-pulse" />
          <span className="font-bold text-fg">
            Narration Studio Independent Preview Harness
          </span>
          <span className="text-[10px] text-fg-faint font-mono hidden sm:inline">
            (Isolated from Timeline & App.tsx)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Preset Scenarios */}
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-fg-faint">Scenario:</span>
            <select
              onChange={(e) => handleScenarioChange(e.target.value as any)}
              className="bg-ink border border-edge rounded px-1.5 py-0.5 text-fg-dim focus:outline-none focus:border-accent cursor-pointer text-xs"
            >
              <option value="default">Standard Chapter (8 Segments)</option>
              <option value="drafts">Unreviewed Drafts (Stress Test)</option>
              <option value="climax">Boss Climax Sequence</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleReset}
            className="text-[11px] font-semibold text-fg-dim hover:text-white px-2 py-0.5 rounded bg-flat hover:bg-glass-hi transition-colors"
          >
            Reset Chapter
          </button>

          <button
            type="button"
            onClick={() => setShowLogDrawer((v) => !v)}
            className="text-[11px] font-semibold text-info hover:text-info px-2 py-0.5 rounded bg-accent/80 border border-accent/40 transition-colors flex items-center gap-1"
          >
            <span>Activity Log</span>
            <span className="font-mono text-[9px] bg-accent/20 px-1 rounded">
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
          <div className="absolute top-0 right-0 w-80 h-full bg-navy/95 border-l border-edge p-3 shadow-2xl z-50 flex flex-col text-xs select-none">
            <div className="flex items-center justify-between border-b border-edge pb-2 mb-2">
              <span className="font-bold text-fg uppercase tracking-wider text-[11px]">
                Preview Activity Log
              </span>
              <button
                type="button"
                onClick={() => setShowLogDrawer(false)}
                className="text-fg-dim hover:text-fg p-0.5 rounded hover:bg-flat transition-colors"
                title="Close Log"
              >
                <Icons.X className="w-3.5 h-3.5" />
              </button>

            </div>

            <div className="flex-1 overflow-y-auto space-y-1 font-mono text-[10px]">
              {eventLogs.length === 0 ? (
                <div className="text-fg-faint italic p-4 text-center">
                  No interactions recorded yet. Edit a script or approve a segment to see events.
                </div>
              ) : (
                eventLogs.map((log, idx) => (
                  <div key={idx} className="p-1 rounded bg-ink/80 text-fg-dim border border-edge/60 leading-normal">
                    {log}
                  </div>
                ))
              )}
            </div>

            {lastExportedContract && (
              <div className="pt-2 border-t border-edge text-[10px] text-fg-dim">
                <span className="font-semibold text-ok">Contract Ready:</span>{" "}
                {lastExportedContract.clips.length} clips in payload.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
