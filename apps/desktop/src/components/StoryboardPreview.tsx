import { useState } from "react";

export function StoryboardPreview({ src, readingOrder }: { src: string; readingOrder: number }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  if (failed) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-12 text-center text-xs text-zinc-400" role="status">
        <span>Panel preview unavailable</span>
        <button type="button" className="text-indigo-300 underline" onClick={() => { setAttempt(attempt + 1); setFailed(false); }}>
          Retry preview
        </button>
        <a href={src} target="_blank" rel="noreferrer" className="text-indigo-300 underline">Open source panel</a>
      </div>
    );
  }
  return <img key={attempt} src={attempt ? `${src}?preview_retry=${attempt}` : src} alt={`Source panel ${readingOrder}`} className="w-full h-full object-contain" loading="lazy" onError={() => setFailed(true)} />;
}
