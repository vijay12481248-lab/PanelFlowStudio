type Rgba = { r: number; g: number; b: number; a: number };

function parse(color: string): Rgba {
  const value = color.trim().toLowerCase();
  const rgba = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(value);
  if (rgba) return { r: +rgba[1], g: +rgba[2], b: +rgba[3], a: rgba[4] === undefined ? 1 : +rgba[4] };
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(value);
  if (!hex) throw new Error(`Unsupported colour: ${color}`);
  const digits = hex[1].length === 3 ? hex[1].replace(/./g, (c) => c + c) : hex[1];
  return {
    r: parseInt(digits.slice(0, 2), 16),
    g: parseInt(digits.slice(2, 4), 16),
    b: parseInt(digits.slice(4, 6), 16),
    a: 1,
  };
}

const toHex = (n: number) => Math.round(n).toString(16).padStart(2, "0");

/** Blend `fg` (hex or rgba) onto the opaque colour `bg`; returns #rrggbb. */
export function compositeOver(fg: string, bg: string): string {
  const top = parse(fg);
  const base = parse(bg);
  const mix = (f: number, b: number) => f * top.a + b * (1 - top.a);
  return `#${toHex(mix(top.r, base.r))}${toHex(mix(top.g, base.g))}${toHex(mix(top.b, base.b))}`;
}

function luminance(color: string): number {
  const { r, g, b } = parse(color);
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast ratio; a translucent `fg` is composited over `bg` first. */
export function contrastRatio(fg: string, bg: string): number {
  const [light, dark] = [luminance(compositeOver(fg, bg)), luminance(bg)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
