import React from "react";
import { api } from "@panelflow/api-client";
import { Button } from "@panelflow/ui-v2";
import { refusal } from "../kit/engineReason";
import type { Review } from "./ContentCleanup";
import { ReviewError, runDetectAndReview } from "./detectAndReview";

const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export interface DetectAndReviewProps {
  projectId: string;
  direction: "ltr" | "rtl";
  onReview: (review: Review) => void;
  onPanelsChanged: () => void;
  /** Only tests pass this, so polling does not wait a real second. */
  sleep?: (ms: number) => Promise<void>;
}

/** One button for detect panels, find and read text, look for promotional text. Shows the step, can be cancelled, and stops when the screen is left. */
export const DetectAndReview: React.FC<DetectAndReviewProps> = ({ projectId, direction, onReview, onPanelsChanged, sleep = realSleep }) => {
  const [step, setStep] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const cancelled = React.useRef(false);
  const mounted = React.useRef(true);
  const busy = React.useRef(false);
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; cancelled.current = true; }; }, []);

  const start = async () => {
    if (busy.current) return;
    busy.current = true;
    cancelled.current = false;
    setRunning(true);
    setError(null);
    try {
      const review = await runDetectAndReview({
        projectId, direction, deps: { api, sleep },
        isCancelled: () => cancelled.current,
        onStep: (s) => { if (mounted.current) setStep(s); },
      });
      if (!mounted.current) return;
      onPanelsChanged();
      onReview(review);
    } catch (err) {
      if (mounted.current) setError(err instanceof ReviewError ? err.message : refusal("Detect and review stopped.", err));
    } finally {
      busy.current = false;
      if (mounted.current) { setRunning(false); setStep(null); }
    }
  };

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={running} onClick={() => void start()}>Detect and review</Button>
        {running && <Button size="sm" variant="ghost" onClick={() => { cancelled.current = true; }}>Cancel</Button>}
      </div>
      {step && <p role="status" className="text-sm text-fg-dim">{step}</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
    </div>
  );
};
