import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { OcrStage } from "../OcrStage";

export const project = (stage = "PANELS_DETECTED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;
export const page = (n: number) => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.jpg`, status: "READY", width: 1920, height: 22000, byte_size: 1, error_message: null });
export const panel = (id: string, n: number) => ({ id, project_id: "p1", page_id: "pg1", sequence: n, page_sequence: n, x: 0, y: n * 1000, width: 1920, height: 900, status: "DETECTED", panel_type: "WEBTOON_SEGMENT", confidence: 0.9, detection_method: "AUTO", reading_direction: "ltr" });
// Real region shape: the crop's own coordinates, text from the engine, statuses NEEDS_REVIEW / CONFIRMED / BLURRED / IGNORED.
export const region = (id: string, panelId: string, seq: number, over: Record<string, unknown> = {}) => ({ id, project_id: "p1", page_id: "pg1", panel_id: panelId, sequence_in_panel: seq, sequence_global: seq, x: 100, y: 100 * seq, width: 400, height: 80, region_type: "SPEECH", confidence: 1, status: "NEEDS_REVIEW", detection_method: "AUTO", raw_text: "", corrected_text: "", speaker_character_id: null, ...over });
export const ENGINES = [
  { engine_id: "mock_ocr", display_name: "Mock OCR", description: "", is_available: true },
  { engine_id: "windows_media", display_name: "Windows OCR", description: "", is_available: true },
  { engine_id: "paddle_ocr", display_name: "PaddleOCR", description: "", is_available: false },
];
export const HISTORY = (over: Record<string, unknown> = {}) => ({ scope: "project", revision: 3, undoCount: 1, redoCount: 1, undoLabel: "Edit", redoLabel: "Edit", canUndo: true, canRedo: true, busy: false, recoveryRequired: false, conflicted: false, fingerprint: "f", error: null, ...over });
export const job = (status: string, over: Record<string, unknown> = {}) => ({ job_id: "jo", project_id: "p1", job_type: "OCR_EXTRACTION", status, progress: 0.5, message: "Reading", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over });

export interface Calls { detect: number; extract: any[][]; update: any[][]; confirm: number; getProject: number; listRegions: number; undo: number; contract: number; downloads: Array<[string, string]>; inFlight: number; maxInFlight: number; deletePanel: any[][]; ocrOne: any[][]; create: any[][]; deleteRegion: any[][]; blur: any[][] }
export function stub(opts: { panels?: any[]; regions?: any[]; engines?: any[]; jobs?: any[]; jobResult?: any; history?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { detect: 0, extract: [], update: [], confirm: 0, getProject: 0, listRegions: 0, undo: 0, contract: 0, downloads: [], inFlight: 0, maxInFlight: 0, deletePanel: [], ocrOne: [], create: [], deleteRegion: [], blur: [] };
  let regions = opts.regions ?? [region("r1", "pa", 1, { raw_text: "Hello" }), region("r2", "pa", 2), region("r3", "pb", 1, { status: "CONFIRMED", raw_text: "Done" })];
  Object.assign(api as any, {
    listPages: async () => [page(1)],
    listPanels: async () => opts.panels ?? [panel("pa", 1), panel("pb", 2)],
    deletePanel: async (...a: any[]) => { calls.deletePanel.push(a); },
    getPanelBlurStatus: async () => ({ is_blurred: false, blurred_regions_count: 0, has_backup: false }),
    getTextRegionImageUrl: (_p: string, id: string) => `/region/${id}.png`,
    listTextRegions: async () => { calls.listRegions++; return regions; },
    listOCREngines: async () => opts.engines ?? ENGINES,
    listProjectJobs: async () => opts.jobs ?? [],
    getJob: async () => opts.jobResult ?? (opts.jobs ?? [])[0] ?? job("SUCCEEDED", { progress: 1 }),
    listCharacters: async () => [],
    detectTextRegions: async () => { calls.detect++; return regions; },
    extractOCR: async (...a: any[]) => { calls.extract.push(a); return { job_id: "jo", message: "" }; },
    updateTextRegion: async (...a: any[]) => {
      calls.update.push(a); calls.inFlight++; calls.maxInFlight = Math.max(calls.maxInFlight, calls.inFlight);
      await new Promise((r) => setTimeout(r, 5));
      calls.inFlight--;
      regions = regions.map((r) => (r.id === a[1] ? { ...r, ...a[2] } : r));
      return regions.find((r) => r.id === a[1]);
    },
    confirmOCR: async () => { calls.confirm++; return { project_id: "p1", current_stage: "OCR_CONFIRMED", message: "" }; },
    getProject: async () => { calls.getProject++; return project("OCR_CONFIRMED"); },
    undo: async () => { calls.undo++; return { state: null, history: HISTORY({ canUndo: false }) }; },
    redo: async () => ({ state: null, history: HISTORY() }),
    getCachedProjectHistory: () => opts.history ?? HISTORY(),
    getCanonicalExportContract: async () => { calls.contract++; return { contract_version: "1", panels: [] }; },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...opts.over,
  });
  return calls;
}
export const text = (d: Document) => d.body.textContent ?? "";
export const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
export async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

export async function show(over: Partial<React.ComponentProps<typeof OcrStage>> = {}, p = project()) {
  const view = await mountPage(<OcrStage project={p} onApproved={() => {}} onContinue={() => {}} onOpenStoryEditor={() => {}} download={() => {}} {...over} />);
  await view.settle();
  await until(() => Boolean(button(view.document, "Read text")));
  await view.settle();
  return view;
}
export const engineSelect = (d: Document) => d.querySelector('select[aria-label="OCR engine"]') as HTMLSelectElement;

