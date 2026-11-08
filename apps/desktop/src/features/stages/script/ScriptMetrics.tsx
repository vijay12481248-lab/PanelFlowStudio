import React from "react";
import type { ScriptValidationReport, VideoScript } from "@panelflow/shared-types";
import { GlassPanel } from "@panelflow/ui-v2";
import { formatClock } from "../motion/motionModel";
import { PROFILES, coverageLabel } from "./scriptModel";

const Stat: React.FC<{ label: string; value: string; detail?: string }> = ({ label, value, detail }) => (
  <GlassPanel blur={false} className="grid gap-1 p-3">
    <p className="text-xs text-fg-faint">{label}</p>
    <p className="font-display text-lg font-semibold text-fg">{value}{detail && <span className="ml-1.5 text-xs font-normal text-fg-dim">{`(${detail})`}</span>}</p>
  </GlassPanel>
);

export const ScriptMetrics: React.FC<{ script: VideoScript; report: ScriptValidationReport | null }> = ({ script, report }) => (
  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
    <Stat label="Estimated length" value={formatClock(script.estimated_duration)} detail={`${Math.round(script.estimated_duration)}s`} />
    <Stat label="Total lines" value={`${script.segments.length} lines`} />
    <Stat label="Faithfulness coverage" value={coverageLabel(report)} />
    <Stat label="Adaptation profile" value={PROFILES.find((p) => p.value === script.adaptation_profile)?.label ?? script.adaptation_profile} />
  </div>
);
