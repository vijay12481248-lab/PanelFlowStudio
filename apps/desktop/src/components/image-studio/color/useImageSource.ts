import { useEffect, useState } from "react";
import type { PixelData } from "./stats";

export interface ImageSource {
  bitmap: ImageBitmap | null;
  /** A small copy (long edge 256) for the scopes and Auto balance. */
  probe: PixelData | null;
  error: string | null;
}

const PROBE_EDGE = 256;

/**
 * The picture's pixels, read separately from the <img> on screen so a failure here (for example a blocked
 * cross-origin read) never breaks the editor: the picture stays visible, only the grade is unavailable.
 */
export function useImageSource(url: string, enabled: boolean): ImageSource {
  const [src, setSrc] = useState<ImageSource>({ bitmap: null, probe: null, error: null });

  useEffect(() => {
    if (!enabled || !url) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`The picture could not be read (${res.status}).`);
        const bitmap = await createImageBitmap(await res.blob());
        if (cancelled) {
          bitmap.close();
          return;
        }
        const scale = Math.min(1, PROBE_EDGE / Math.max(bitmap.width, bitmap.height));
        const w = Math.max(1, Math.round(bitmap.width * scale)), h = Math.max(1, Math.round(bitmap.height * scale));
        const cv = document.createElement("canvas");
        cv.width = w;
        cv.height = h;
        const ctx = cv.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(bitmap, 0, 0, w, h);
        setSrc({ bitmap, probe: ctx.getImageData(0, 0, w, h), error: null });
      } catch (err: any) {
        if (!cancelled) setSrc({ bitmap: null, probe: null, error: err?.message || "The picture could not be read." });
      }
    })();
    // Not closed on cleanup: the canvas may still be drawing the previous bitmap until the new one is in; GC frees it.
    return () => {
      cancelled = true;
    };
  }, [url, enabled]);

  return src;
}
