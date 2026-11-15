import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "./Button";

export interface TileProps {
  title: string;
  subtitle?: string;
  imageUrl?: string;
  /** Shown on a gradient when there is no image (usually the project's initials). */
  fallbackText: string;
  selected?: boolean;
  onOpen?: () => void;
  /** Called when the image fails to load, so the caller can fall back to the initials. */
  onImageError?: () => void;
}

export const Tile: React.FC<TileProps> = ({ title, subtitle, imageUrl, fallbackText, selected, onOpen, onImageError }) => {
  // A cover that 404s must never leave a broken-image icon. Remember which URL failed, so a new URL is tried again.
  const [failedUrl, setFailedUrl] = React.useState<string | undefined>();
  const showImage = Boolean(imageUrl) && imageUrl !== failedUrl;
  const content = (
    <>
      <span
        className={cx(
          "relative block aspect-square overflow-hidden rounded-card border transition-all duration-200",
          selected
            ? "border-accent ring-2 ring-accent/60 shadow-lg shadow-accent/25"
            : "border-edge bg-gradient-to-br from-info to-glow group-hover:border-glow/50"
        )}
      >
        {showImage ? (
          <img
            src={imageUrl}
            alt=""
            className="size-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
            onError={() => { setFailedUrl(imageUrl); onImageError?.(); }}
          />
        ) : (
          <span className="absolute bottom-2 left-3 font-display text-lg font-bold text-white/80">{fallbackText}</span>
        )}
      </span>
      <span className={cx("mt-2 block text-left text-[13px] leading-snug font-medium transition-colors", selected ? "text-accent" : "text-fg group-hover:text-fg-bright")}>
        {title}
      </span>
      {subtitle && <span className="block text-left text-xs text-fg-faint">{subtitle}</span>}
    </>
  );
  return onOpen ? (
    <button
      type="button"
      onClick={onOpen}
      aria-selected={selected || undefined}
      className={cx(
        "group block w-full rounded-card text-left cursor-pointer transition-transform duration-150 active:scale-[0.98]",
        FOCUS_RING
      )}
    >
      {content}
    </button>
  ) : (
    <div>{content}</div>
  );
};
