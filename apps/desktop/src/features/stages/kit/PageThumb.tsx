import React from "react";
import { cx, FOCUS_RING } from "@panelflow/ui-v2";

export interface PageThumbProps {
  src?: string;
  label: string;
  failed?: boolean;
  /** Why it failed, when the engine said. */
  reason?: string | null;
  selected?: boolean;
  onOpen?: () => void;
}

/** A 3:4 page tile. A missing or failed image shows the label and the word Failed, never a broken-image icon. */
export const PageThumb: React.FC<PageThumbProps> = ({ src, label, failed, reason, selected, onOpen }) => {
  const [brokenSrc, setBrokenSrc] = React.useState<string | undefined>();
  const showImage = !failed && Boolean(src) && src !== brokenSrc;
  const body = (
    <span className={cx("relative grid aspect-[3/4] w-full place-items-center overflow-hidden rounded-ctl border bg-glass", selected ? "border-accent" : failed ? "border-bad/50" : "border-edge")}>
      {showImage ? (
        <img src={src} alt={label} className="size-full object-contain" loading="lazy" onError={() => setBrokenSrc(src)} />
      ) : (
        <span className="grid justify-items-center gap-1 p-2 text-center">
          <span className="text-sm font-semibold text-fg">{label}</span>
          <span className="text-xs font-medium text-bad">Failed</span>
          {reason && <span className="line-clamp-3 text-[11px] text-fg-faint">{reason}</span>}
        </span>
      )}
    </span>
  );
  return onOpen ? (
    <button type="button" onClick={onOpen} aria-label={`Open ${label}`} className={cx("block w-full rounded-ctl", FOCUS_RING)}>{body}</button>
  ) : (
    <div>{body}</div>
  );
};
