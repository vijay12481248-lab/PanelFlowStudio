/**
 * ChronoFlow's Fusion renderers (`fusion-graph.js`), imported unchanged so glow, vignette, blur and text look here exactly as they
 * do on the video Fusion page. Only `processNode` is used: it draws one effect from a source canvas onto a destination canvas.
 */
import * as fusionModule from "../../../../../../engine/chronoflow/static/nle/fusion-graph.js";

export interface FusionNode {
  type: string;
  params: Record<string, any>;
}

interface FusionGraphApi {
  processNode(node: FusionNode, src: HTMLCanvasElement, dst: HTMLCanvasElement, time?: number): void;
}

// In the browser the file sets self.NLEFusionGraph; under Node (tests) it is a CommonJS module.
export const FG: FusionGraphApi = (globalThis as any).NLEFusionGraph ?? (fusionModule as any).default ?? (fusionModule as any);
