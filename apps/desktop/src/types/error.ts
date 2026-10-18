export type ErrorSeverity = "error" | "warning" | "info";
export type ErrorSource = "job" | "network" | "engine" | "validation" | "ui" | "system";

export interface AppError {
  id: string;
  title: string;
  message: string;
  severity: ErrorSeverity;
  source: ErrorSource;
  timestamp: string; // ISO string
  jobId?: string;
  projectId?: string;
  jobType?: string;
  statusCode?: number;
  rawDetails?: string | Record<string, any>;
  stack?: string;
  suggestions?: string[];
  acknowledged?: boolean;
}
