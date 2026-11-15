export type StudioPage = "ai" | "cut" | "fusion" | "color" | "deliver";
export type AiMode = "edit" | "pose" | "inpaint";
export type ToolMode = "brush" | "eraser";

/** One picture in the Versions strip: the original and every result made in this session. */
export interface StudioVersion {
  key: string;
  label: string;
  src: string;
}

export const INPUT_CLASS =
  "w-full rounded-lg border border-edge bg-flat px-3 py-2 text-xs text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none transition-colors disabled:opacity-50";
