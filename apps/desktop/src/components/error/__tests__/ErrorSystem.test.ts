import test from "node:test";
import assert from "node:assert/strict";
import { generateSuggestions } from "../../../context/errorSuggestions.ts";
import type { AppError } from "../../../types/error.ts";

test("Error System: Context-aware suggestion generator identifies speech provider errors", () => {
  const suggestions = generateSuggestions(
    "Job Failed: AUDIO_GENERATION",
    "Unsupported speech provider: f5_tts. Use 'chatterbox_turbo' (MIT).",
    "AUDIO_GENERATION"
  );

  assert.ok(suggestions.length >= 2, "Should provide actionable suggestions");
  assert.ok(
    suggestions.some((s) => s.includes("Chatterbox Turbo")),
    "Should suggest switching to Chatterbox Turbo"
  );
  assert.ok(
    suggestions.some((s) => s.includes("C:\\Tools\\Chatterbox")),
    "Should suggest checking Chatterbox tools directory"
  );
});

test("Error System: Suggestion generator identifies Ollama and Story Understanding stalls", () => {
  const suggestions = generateSuggestions(
    "Story Understanding Stalled",
    "Reconstructing chapter story, character continuity and connected scene groups...",
    "STORY_ANALYSIS"
  );

  assert.ok(suggestions.length >= 2, "Should provide actionable suggestions");
  assert.ok(
    suggestions.some((s) => s.includes("ollama serve")),
    "Should suggest checking if ollama is serving"
  );
  assert.ok(
    suggestions.some((s) => s.includes("qwen2.5:9b")),
    "Should suggest pulling qwen2.5:9b model"
  );
});

test("Error System: Suggestion generator identifies FFmpeg video render errors", () => {
  const suggestions = generateSuggestions(
    "Video Render Failed",
    "ffmpeg executable not found in PATH",
    "RENDER_JOB"
  );

  assert.ok(
    suggestions.some((s) => s.includes("FFmpeg")),
    "Should suggest installing or verifying FFmpeg in PATH"
  );
});

test("Error System: Suggestion generator identifies ASGI event loop / engine crash errors", () => {
  const suggestions = generateSuggestions(
    "Internal Server Error",
    "RuntimeError: There is no current event loop in thread 'AnyIO worker thread'",
    "OCR_EXTRACTION"
  );

  assert.ok(
    suggestions.some((s) => s.includes("engine")),
    "Should suggest restarting local Python engine"
  );
});

test("Error System: Diagnostic Report serialization produces complete markdown bundle", () => {
  const sampleError: AppError = {
    id: "err_test_123",
    title: "Job Failed: AUDIO_GENERATION",
    message: "Unsupported speech provider: f5_tts. Use 'chatterbox_turbo' (MIT).",
    severity: "error",
    source: "job",
    timestamp: "2026-10-18T15:40:31.940Z",
    jobId: "d3c62cfc-473b-4e0c-b492-31bed2304502",
    projectId: "741a1c5c-cb8f-44ef-bc2e-f3503fda4da2",
    jobType: "AUDIO_GENERATION",
    rawDetails: {
      status: "QUEUED",
      retry_count: 1,
      max_retries: 3,
    },
    suggestions: [
      "Switch primary Speech Provider to 'Chatterbox Turbo' in Tools & Models.",
      "Verify the local Chatterbox environment at C:\\Tools\\Chatterbox.",
    ],
  };

  const diagnosticReport = [
    `# PanelFlow Studio — Error Diagnostic Report`,
    `**Timestamp**: ${new Date(sampleError.timestamp).toLocaleString()} (${sampleError.timestamp})`,
    `**Title**: ${sampleError.title}`,
    `**Severity**: ${sampleError.severity.toUpperCase()}`,
    `**Source**: ${sampleError.source}`,
    `**Job ID**: \`${sampleError.jobId}\``,
    `**Project ID**: \`${sampleError.projectId}\``,
    `**Job Type**: \`${sampleError.jobType}\``,
    ``,
    `## Error Message`,
    sampleError.message,
    ``,
    `## Recommended Troubleshooting Actions`,
    ...sampleError.suggestions!.map((s, i) => `${i + 1}. ${s}`),
    ``,
    `## Raw Diagnostic Payload`,
    "```json",
    JSON.stringify(sampleError.rawDetails, null, 2),
    "```",
  ].join("\n");

  assert.ok(diagnosticReport.includes("PanelFlow Studio — Error Diagnostic Report"));
  assert.ok(diagnosticReport.includes(sampleError.jobId!));
  assert.ok(diagnosticReport.includes(sampleError.projectId!));
  assert.ok(diagnosticReport.includes("Chatterbox Turbo"));
  assert.ok(diagnosticReport.includes("Unsupported speech provider: f5_tts"));
});
