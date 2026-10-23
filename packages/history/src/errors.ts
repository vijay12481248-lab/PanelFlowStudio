export type HistoryErrorCode = 'VALIDATION' | 'COMPATIBILITY' | 'CAPACITY' | 'CONFLICT' | 'EXECUTION' | 'PERSISTENCE' | 'RECOVERY_REQUIRED';

export class HistoryError extends Error {
  readonly cause?: unknown;
  constructor(readonly code: HistoryErrorCode, message: string, options?: { cause?: unknown }) {
    super(message);
    this.name = 'HistoryError';
    this.cause = options?.cause;
  }
}

export function historyError(error: unknown, code: HistoryErrorCode): HistoryError {
  return error instanceof HistoryError ? error : new HistoryError(code, error instanceof Error ? error.message : String(error), { cause: error });
}
