import React, { useState } from "react";
import { AudioLibrary } from "./AudioLibrary.tsx";
import type { AudioToTimelineContract } from "./AudioLibrary.types.ts";

export const AudioLibraryPreviewHarness: React.FC = () => {
  const [receivedContracts, setReceivedContracts] = useState<AudioToTimelineContract[]>([]);
  const [showLogModal, setShowLogModal] = useState<boolean>(false);

  const handleSendToTimeline = (contract: AudioToTimelineContract) => {
    setReceivedContracts((prev) => [contract, ...prev]);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-ink text-fg overflow-hidden font-sans">
      {/* Test Harness Status Banner */}
      <div className="h-8 bg-accent/70 border-b border-accent/30 px-4 flex items-center justify-between text-xs text-info shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-ok animate-pulse" />
          <span className="font-semibold">Chapter 6A Standalone Preview Harness</span>
          <span className="text-[10px] text-info font-mono">
            [Zero modifications to StoryEditor / App.tsx]
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowLogModal(true)}
            className="px-2 py-0.5 rounded bg-accent/60 hover:bg-accent/80 border border-accent/50 text-[11px] font-semibold flex items-center gap-1.5 transition-colors"
          >
            <span>📜</span>
            <span>Timeline Contracts ({receivedContracts.length})</span>
          </button>
        </div>
      </div>

      {/* Main Isolated Audio Library Component */}
      <div className="flex-1 min-h-0 relative">
        <AudioLibrary onSendToTimeline={handleSendToTimeline} />
      </div>

      {/* Received Timeline Contracts Modal */}
      {showLogModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-6">
          <div className="bg-navy border border-edge rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-edge flex items-center justify-between bg-ink">
              <div className="flex items-center gap-2">
                <span className="text-base">🎬</span>
                <h3 className="text-sm font-bold text-fg">
                  Received Timeline Contracts (Schema 6A-v1)
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowLogModal(false)}
                className="text-fg-dim hover:text-white text-xs px-2 py-1 rounded bg-flat"
              >
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
              {receivedContracts.length === 0 ? (
                <div className="text-center py-10 text-fg-faint text-xs">
                  No audio cues sent to timeline yet. Click &ldquo;+ Timeline&rdquo; or &ldquo;Send to Track&rdquo; on any asset.
                </div>
              ) : (
                receivedContracts.map((contract, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl bg-ink border border-accent/40 text-xs font-mono space-y-2"
                  >
                    <div className="flex items-center justify-between text-info">
                      <span className="font-bold">Contract #{receivedContracts.length - i}</span>
                      <span className="text-[10px] text-fg-faint">{contract.exported_at}</span>
                    </div>
                    <pre className="text-[11px] text-ok bg-navy/80 p-2.5 rounded-lg overflow-x-auto border border-edge">
                      {JSON.stringify(contract, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>

            {receivedContracts.length > 0 && (
              <div className="p-3 border-t border-edge bg-ink flex justify-end">
                <button
                  type="button"
                  onClick={() => setReceivedContracts([])}
                  className="px-3 py-1 rounded text-xs text-bad bg-bad/60 hover:bg-bad/20 border border-bad/40"
                >
                  Clear Contracts
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
export default AudioLibraryPreviewHarness;
