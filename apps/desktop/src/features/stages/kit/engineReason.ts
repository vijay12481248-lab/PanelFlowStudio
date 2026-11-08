const HIDDEN = /[A-Za-z]:\\|\/[\w.-]+\/[\w.-]+|Traceback|\bat\s+\S+\s*\(|\bENOENT\b|\bECONN\w*|Failed to fetch|NetworkError|TypeError|ReferenceError|SyntaxError/i;

/**
 * The engine's own explanation for refusing something ("No pages are ready"), when it is short and safe to show.
 * Messages that look like exceptions, stack frames, file paths or network noise return null.
 */
export function engineReason(err: unknown): string | null {
  const message = typeof err === "object" && err !== null && typeof (err as { message?: unknown }).message === "string" ? (err as { message: string }).message.trim() : "";
  if (!message || message.length > 200 || HIDDEN.test(message)) return null;
  return message;
}

/** A headline plus the engine's reason, or plain advice when there is no safe reason. */
export function refusal(headline: string, err: unknown): string {
  return `${headline} ${engineReason(err) ?? "Check that the engine is running, then try again."}`;
}
