import React from "react";
import type { TextRegion } from "@panelflow/shared-types";
import { Button } from "@panelflow/ui-v2";
import { needsReview } from "./ocrModel";

/** How many regions still need a decision, and a way to reach the next one. */
export const GateBanner: React.FC<{ regions: TextRegion[]; onJump: () => void }> = ({ regions, onJump }) => {
  const open = needsReview(regions).length;
  if (regions.length === 0) return null;
  return open === 0
    ? <p role="status" className="text-sm text-ok">Every region is reviewed.</p>
    : (
      <div role="status" className="flex flex-wrap items-center gap-3 text-sm text-warn">
        <span>{`${open} ${open === 1 ? "region needs" : "regions need"} review.`}</span>
        <Button size="sm" variant="secondary" onClick={onJump}>Jump to next flagged</Button>
      </div>
    );
};
