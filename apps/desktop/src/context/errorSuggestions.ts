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
  } else if (text.includes("ffmpeg") || text.includes("ffprobe") || jobType?.includes("RENDER")) {
    suggestions.push(
      "Ensure FFmpeg is installed and added to system PATH ('winget install Gyan.FFmpeg')."
    );
    suggestions.push("Check that the target output directory is writable and has free disk space.");
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
