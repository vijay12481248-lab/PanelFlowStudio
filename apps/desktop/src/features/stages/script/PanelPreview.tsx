import React from "react";
import { Button } from "@panelflow/ui-v2";

/** A source panel. When it cannot load it says so, with a retry and a link to open the panel itself. */
export const PanelPreview: React.FC<{ src: string; label: string; className?: string }> = ({ src, label, className = "h-40 max-w-60" }) => {
  const [failed, setFailed] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);
  if (failed) {
    return (
      <div role="status" className="grid min-w-40 place-items-center gap-1.5 rounded-ctl border border-edge bg-glass p-3 text-center text-xs text-fg-dim">
        <span>Panel preview unavailable</span>
        <Button size="sm" variant="ghost" onClick={() => { setAttempt((n) => n + 1); setFailed(false); }}>Retry preview</Button>
        <a href={src} target="_blank" rel="noreferrer" className="text-info underline">Open source panel</a>
      </div>
    );
  }
  return <img key={attempt} src={attempt ? `${src}?preview_retry=${attempt}` : src} alt={label} className={`${className} rounded-ctl bg-glass object-contain`} loading="lazy" onError={() => setFailed(true)} />;
};
