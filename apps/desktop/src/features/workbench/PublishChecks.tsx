import React from "react";
import { Chip, GlassPanel } from "@panelflow/ui-v2";
import type { CheckState, PublishCheck } from "./publishModel";

const STATE: Record<CheckState, { word: string; tone: "ok" | "bad" | "neutral" }> = {
  pass: { word: "Passed", tone: "ok" },
  fail: { word: "Failed", tone: "bad" },
  pending: { word: "Waiting", tone: "neutral" },
};

export const PublishChecks: React.FC<{ checks: PublishCheck[] }> = ({ checks }) => (
  <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
    <h2 className="font-display text-sm font-semibold text-fg">Before you upload</h2>
    <ul className="grid grid-cols-1 gap-2">
      {checks.map((check) => (
        <li key={check.id} data-check={check.id} data-state={check.state} className="flex items-center gap-3 rounded-ctl border border-edge p-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">{check.label}</p>
            <p className="text-xs text-fg-dim">{check.detail}</p>
          </div>
          <Chip tone={STATE[check.state].tone}>{STATE[check.state].word}</Chip>
        </li>
      ))}
    </ul>
    <p className="text-sm text-fg-dim">
      PanelFlow does not upload pipeline videos yet. Copy the details below and upload in YouTube Studio, with the video set to Private first.
      Original Stories episodes upload from Create.
    </p>
  </GlassPanel>
);
