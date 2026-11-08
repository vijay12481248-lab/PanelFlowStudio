import React from "react";

/** Fit an image to the width of its container, in percent. Before the container can be measured (and in tests) a fixed value is used. */
export function useFitZoom(imageWidth: number, min = 5) {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = React.useState(0);
  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);
  return { ref, zoom: width > 0 ? Math.max(min, Math.floor((width / imageWidth) * 100)) : 40 };
}
