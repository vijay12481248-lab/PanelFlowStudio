// Generate context-aware suggestions based on error content
export function generateSuggestions(
  title: string,
  message: string,
  jobType?: string,
  raw?: any
): string[] {
  const text = `${title} ${message} ${JSON.stringify(raw || "")}`.toLowerCase();
  const suggestions: string[] = [];

  if (text.includes("f5_tts") || text.includes("unsupported speech provider")) {
    suggestions.push(
      "Switch primary Speech Provider to 'Chatterbox Turbo' in Tools & Models or Project Settings."
    );
    suggestions.push(
      "Verify the local Chatterbox environment is present at C:\\Tools\\Chatterbox."
    );
    suggestions.push("Re-queue or retry the audio generation job.");
  } else if (text.includes("ollama") || text.includes("qwen") || jobType === "STORY_ANALYSIS") {
    suggestions.push(
      "Verify that Ollama is running locally ('ollama serve' on port 11434)."
    );
    suggestions.push(
      "Ensure the model is pulled: run 'ollama pull qwen2.5:9b' in your terminal."
    );
    suggestions.push(
      "For large chapters (15+ pages), LLM reconstruction at 80% can take 5–10 minutes on consumer hardware."
    );
  } else if (text.includes("ocr") || text.includes("windows_media") || text.includes("tesseract")) {
    suggestions.push("Ensure Windows Media OCR language pack (e.g. English US) is installed in Windows Settings.");
    suggestions.push("If Windows Media is unavailable, switch to Tesseract or RapidOCR in Tools & Models.");
    suggestions.push("Confirm that all panels have been detected and confirmed before running OCR.");
  } else if (text.includes("contamination") || text.includes("non-story") || text.includes("semantic_qa")) {
    suggestions.push("A non-story asset or credit page was assigned to a story scene shot.");
    suggestions.push("Open Story Review or Story Editor to verify panel assignments and remove credits/promo panels.");
    suggestions.push("Re-run validation or render draft to verify gate clearance.");
  } else if (text.includes("panel") || text.includes("bounding box") || text.includes("detection")) {
    suggestions.push("Verify that raw chapter pages are fully acquired and not corrupted in workspace.");
    suggestions.push("Adjust reading direction (LTR / RTL / Webtoon vertical) in Panel Review settings.");
    suggestions.push("Try running page normalization before re-triggering panel detection.");
  } else if (text.includes("approval gate") || text.includes("gate blocked") || text.includes("strict")) {
    suggestions.push("Review all items in the current stage to ensure no required fields are blank or unconfirmed.");
    suggestions.push("Inspect the gate failure message in the diagnostic modal for the specific blocking criterion.");
  } else if (text.includes("ffmpeg") || text.includes("ffprobe") || jobType?.includes("RENDER")) {
    suggestions.push(
      "Ensure FFmpeg is installed and added to system PATH ('winget install Gyan.FFmpeg')."
    );
    suggestions.push("Check that the target output directory is writable and has free disk space.");
    suggestions.push("Verify that dialogue audio stems and background music tracks exist on disk.");
  } else if (text.includes("event loop") || text.includes("500") || text.includes("asgi")) {
    suggestions.push("Restart the local Python processing engine service ('npm run engine').");
    suggestions.push("Inspect %LOCALAPPDATA%\\PanelFlow Studio\\logs\\engine.log for full stack trace.");
  } else if (text.includes("network") || text.includes("econnrefused") || text.includes("fetch")) {
    suggestions.push("Check that the local engine server is running on http://127.0.0.1:8765.");
    suggestions.push("Click 'Retry Engine Connection' in the dashboard header.");
  } else {
    suggestions.push("Inspect the detailed error stack and raw diagnostic payload below.");
    suggestions.push("Check application logs in %LOCALAPPDATA%\\PanelFlow Studio\\logs\\engine.log.");
  }

  return suggestions;
}
