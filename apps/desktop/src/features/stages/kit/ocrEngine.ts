import type { OCREngineInfo } from "@panelflow/shared-types";

const isMock = (e: OCREngineInfo) => /mock/i.test(e.engine_id);

/** The first available engine that is not a test engine, by the order of the list. No engine id is preferred by name. */
export function pickEngine(engines: OCREngineInfo[]): string | null {
  return engines.find((e) => e.is_available && !isMock(e))?.engine_id ?? null;
}

/** Why no engine can be used, in words, or null when one can. */
export function engineProblem(engines: OCREngineInfo[]): string | null {
  if (pickEngine(engines)) return null;
  return engines.some((e) => e.is_available && isMock(e))
    ? "Only a test engine is available. Choose or install a real one in Settings."
    : "No OCR engine is available. Install one in Settings.";
}
