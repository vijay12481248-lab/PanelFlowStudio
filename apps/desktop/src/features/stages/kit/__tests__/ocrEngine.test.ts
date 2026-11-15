import test from "node:test";
import assert from "node:assert/strict";
import type { OCREngineInfo } from "@panelflow/shared-types";
import { engineProblem, pickEngine } from "../ocrEngine";

const engine = (id: string, available: boolean) => ({ engine_id: id, display_name: id, description: "", is_available: available }) as OCREngineInfo;
// The real list on this PC.
const REAL = [engine("mock_ocr", true), engine("windows_media", true), engine("paddle_ocr", false), engine("manga_ocr", false), engine("vision_llm", false)];

test("the engine is the first available real one, chosen by the order of the list and not by name", () => {
  assert.equal(pickEngine(REAL), "windows_media");
  assert.equal(pickEngine([engine("zz_engine", true), engine("windows_media", true)]), "zz_engine", "a different order gives a different choice: no engine id is preferred");
  assert.equal(pickEngine([engine("paddle_ocr", false), engine("manga_ocr", true)]), "manga_ocr");
});

test("a mock engine, an unavailable engine and an empty list are never chosen", () => {
  assert.equal(pickEngine([engine("mock_ocr", true)]), null);
  assert.equal(pickEngine([engine("MockOCR", true), engine("windows_media", false)]), null);
  assert.equal(pickEngine([]), null);
});

test("when there is no usable engine the problem is said in words", () => {
  assert.equal(engineProblem(REAL), null);
  assert.equal(engineProblem([]), "No OCR engine is available. Install one in Settings.");
  assert.equal(engineProblem([engine("paddle_ocr", false)]), "No OCR engine is available. Install one in Settings.");
  assert.equal(engineProblem([engine("mock_ocr", true), engine("paddle_ocr", false)]), "Only a test engine is available. Choose or install a real one in Settings.");
});
