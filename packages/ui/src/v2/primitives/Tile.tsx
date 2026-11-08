import React from "react";
import { cx } from "../cx";
import { FOCUS_RING } from "./Button";

export interface TileProps {
  title: string;
  subtitle?: string;
  imageUrl?: string;
  /** Shown on a gradient when there is no image (usually the project's initials). */
  fallbackText: string;
  onOpen?: () => void;
  /** Called when the image fails to load, so the caller can fall back to the initials. */
  onImageError?: () => void;
}

export const Tile: React.FC<TileProps> = ({ title, subtitle, imageUrl, fallbackText, onOpen, onImageError }) => {
  const content = (
    <>
      <span className="relative block aspect-square overflow-hidden rounded-card border border-edge bg-gradient-to-br from-info to-glow">
        {imageUrl ? (
          <img src={imageUrl} alt="" className="size-full object-cover" loading="lazy" onError={onImageError} />
        ) : (
          <span className="absolute bottom-2 left-3 font-display text-lg font-bold text-white/80">{fallbackText}</span>
        )}
      </span>
      <span className="mt-2 block text-left text-[13px] leading-snug text-fg">{title}</span>
      {subtitle && <span className="block text-left text-xs text-fg-faint">{subtitle}</span>}
    </>
  );
  return onOpen ? (
    <button type="button" onClick={onOpen} className={cx("block w-full rounded-card", FOCUS_RING)}>{content}</button>
  ) : (
    <div>{content}</div>
  );
};
