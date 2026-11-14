import type { GradeNode } from "./grade";

/** Each look adds one node, so it can be tuned or switched off. Same looks as ChronoFlow's Color page. */
export const LOOKS: Record<string, (n: GradeNode) => void> = {
  "Teal & Orange": (n) => { n.lift = { x: -0.8, y: -0.15, m: 0 }; n.gain = { x: 0.6, y: 0.35, m: 0.02 }; n.contrast = 1.12; n.saturation = 1.12; },
  "Warm film": (n) => { n.temp = 18; n.tint = 4; n.contrast = 1.08; n.saturation = 1.05; n.lift = { x: 0.2, y: 0.15, m: 0.02 }; n.curves.y = [[0, 0.03], [0.5, 0.52], [1, 0.97]]; },
  "Cold night": (n) => { n.temp = -22; n.gamma = { x: -0.5, y: -0.4, m: -0.08 }; n.contrast = 1.1; n.saturation = 0.9; n.highlights = -10; },
  "Bleach bypass": (n) => { n.saturation = 0.55; n.contrast = 1.3; n.pivot = 0.45; n.highlights = -6; },
  "Faded matte": (n) => { n.lift = { x: 0, y: 0, m: 0.12 }; n.contrast = 0.92; n.saturation = 0.9; n.curves.y = [[0, 0.06], [1, 0.94]]; },
  "Vivid pop": (n) => { n.boost = 40; n.saturation = 1.2; n.contrast = 1.1; },
  Noir: (n) => { n.saturation = 0; n.contrast = 1.32; n.curves.y = [[0, 0], [0.3, 0.2], [0.7, 0.8], [1, 1]]; },
};
