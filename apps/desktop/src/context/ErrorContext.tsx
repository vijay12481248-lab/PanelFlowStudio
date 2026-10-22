import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import type { AppError } from "../types/error";
import { api } from "@panelflow/api-client";
import type { Job } from "@panelflow/shared-types";
import { generateSuggestions } from "./errorSuggestions";

// Local helper copied from JobActivityPanel.tsx to avoid circular imports
const isActiveJob = (job: Job) => job.status === "QUEUED" || job.status === "RUNNING";

export { generateSuggestions };

interface ErrorContextValue {
  activeErrors: AppError[];
  historyErrors: AppError[];
  selectedError: AppError | null;
  reportError: (
    err: Partial<AppError> & { title: string; message: string }
  ) => string;
  dismissError: (id: string) => void;
  clearAllErrors: () => void;
  inspectError: (err: AppError) => void;
  closeInspector: () => void;
  retryJob: (jobId: string) => Promise<boolean>;
  cancelJob: (jobId: string) => Promise<boolean>;
  engineHealthy: boolean;
  jobs: Job[];
}

const ErrorContext = createContext<ErrorContextValue | undefined>(undefined);

export const ErrorProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [activeErrors, setActiveErrors] = useState<AppError[]>([]);
  const [historyErrors, setHistoryErrors] = useState<AppError[]>([]);
  const [selectedError, setSelectedError] = useState<AppError | null>(null);
  const [jobSnapshots, setJobSnapshots] = useState<Job[]>([]);
  const [engineHealthy, setEngineHealthy] = useState(false);

  // Track known failed/alerted jobs to prevent duplicate alerts
  const alertedJobStatesRef = useRef<Map<string, string>>(new Map());
  const recentReportKeysRef = useRef<Map<string, number>>(new Map());
  const sessionStartTimeRef = useRef<number>(Date.now());

  const reportError = useCallback(
    (err: Partial<AppError> & { title: string; message: string }): string => {
      // Deduplicate rapid identical reports (within 4 seconds)
      const dedupKey = `${err.title}::${err.message}::${err.jobId || ""}`;
      const now = Date.now();
      const lastReported = recentReportKeysRef.current.get(dedupKey) || 0;
      if (now - lastReported < 4000) {
        return "";
      }
      recentReportKeysRef.current.set(dedupKey, now);

      const id = err.id || `err_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      const timestamp = err.timestamp || new Date().toISOString();
      const severity = err.severity || "error";
      const source = err.source || "system";

      const suggestions =
        err.suggestions && err.suggestions.length > 0
          ? err.suggestions
          : generateSuggestions(err.title, err.message, err.jobType, err.rawDetails);

      const newError: AppError = {
        id,
        title: err.title,
        message: err.message,
        severity,
        source,
        timestamp,
        jobId: err.jobId,
        projectId: err.projectId,
        jobType: err.jobType,
        statusCode: err.statusCode,
        rawDetails: err.rawDetails,
        stack: err.stack,
        suggestions,
        acknowledged: false,
      };

      console.error("[PanelFlow Error Alert]", newError);

      setActiveErrors((prev) => [newError, ...prev.filter((e) => e.id !== id)]);
      setHistoryErrors((prev) => [newError, ...prev.filter((e) => e.id !== id)].slice(0, 50));

      return id;
    },
    []
  );

  const dismissError = useCallback((id: string) => {
    setActiveErrors((prev) => prev.filter((e) => e.id !== id));
    setHistoryErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, acknowledged: true } : e))
    );
  }, []);

  const clearAllErrors = useCallback(() => {
    setActiveErrors([]);
  }, []);

  const inspectError = useCallback((err: AppError) => {
    setSelectedError(err);
  }, []);

  const closeInspector = useCallback(() => {
    setSelectedError(null);
  }, []);

  const retryJob = useCallback(
    async (jobId: string): Promise<boolean> => {
      try {
        const current = await api.getJob(jobId);
        if (isActiveJob(current)) {
          reportError({ title: "Job already active", message: `This job is ${current.status.toLowerCase()}; automatic processing is already in progress.`, severity: "info", source: "job", jobId, projectId: current.project_id, jobType: current.job_type, rawDetails: current });
          return true;
        }
        await api.retryJob(jobId);
        // Clear active error for this job
        setActiveErrors((prev) => prev.filter((e) => e.jobId !== jobId));
        if (selectedError?.jobId === jobId) {
          setSelectedError(null);
        }
        return true;
      } catch (e: any) {
        reportError({
          title: "Retry Failed",
          message: e.message || "Failed to trigger retry on server.",
          severity: "error",
          source: "job",
          jobId,
          rawDetails: e,
        });
        return false;
      }
    },
    [reportError, selectedError]
  );

  const cancelJob = useCallback(async (jobId: string): Promise<boolean> => {
    try {
      const current = await api.getJob(jobId);
      if (!isActiveJob(current)) {
        reportError({ title: "Job already finished", message: `Current job status: ${current.status}.`, severity: "info", source: "job", jobId, rawDetails: current });
        return true;
      }
      await api.cancelJob(jobId);
      const updated = await api.getJob(jobId);
      setJobSnapshots((jobs) => jobs.map((job) => job.job_id === jobId ? updated : job));
      reportError({ title: "Cancellation requested", message: "The engine accepted the request. Model or render cleanup may take a moment.", severity: "info", source: "job", jobId, projectId: current.project_id, jobType: current.job_type, rawDetails: updated });
      return true;
    } catch (error: any) {
      reportError({ title: "Job cancellation failed", message: error.message || "Could not request cancellation.", severity: "error", source: "job", jobId });
      return false;
    }
  }, [reportError]);

  // Global uncaught exception and promise rejection listeners
  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const message =
        reason instanceof Error
          ? reason.message
          : typeof reason === "string"
          ? reason
          : JSON.stringify(reason || "Unhandled Promise Rejection");

      // Ignore standard user cancellations or intentional aborts
      if (message.includes("abort") || message.includes("cancelled")) return;

      reportError({
        title: "Unhandled Asynchronous Error",
        message,
        severity: "error",
        source: "ui",
        stack: reason instanceof Error ? reason.stack : undefined,
        rawDetails: reason,
      });
    };

    const handleError = (event: ErrorEvent) => {
      if (event.message?.includes("ResizeObserver")) return; // benign browser warning
      reportError({
        title: "Client Application Error",
        message: event.message || "An unexpected error occurred in the desktop UI.",
        severity: "error",
        source: "ui",
        stack: event.error?.stack,
        rawDetails: {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
        },
      });
    };

    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    window.addEventListener("error", handleError);

    return () => {
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
      window.removeEventListener("error", handleError);
    };
  }, [reportError]);

  // Periodic Job Queue Monitor to detect failed/stalled jobs and alert user
  useEffect(() => {
    let mounted = true;

    let polling = false;
    const checkJobAlerts = async () => {
      if (polling) return;
      polling = true;
      try {
        const [jobs, health] = await Promise.all([api.listJobs(undefined, undefined, 200).catch(() => null), api.checkHealth().catch(() => null)]);
        if (!mounted) return;
        setEngineHealthy(health?.status === "healthy");
        if (!jobs) return;
        setJobSnapshots(jobs);
        const refreshDetails = (error: AppError) => {
          const job = jobs.find((item) => item.job_id === error.jobId);
          return job ? { ...error, rawDetails: job } : error;
        };
        setSelectedError((error) => error ? refreshDetails(error) : null);
        setActiveErrors((errors) => errors.map(refreshDetails));

        for (const job of jobs) {
          const stateKey = `${job.job_id}::${job.status}::${job.retry_count || 0}::${job.error || ""}`;
          const previousState = alertedJobStatesRef.current.get(job.job_id);

          if (job.status === "FAILED" || job.status === "CANCELLED") {
            if (previousState !== stateKey) {
              alertedJobStatesRef.current.set(job.job_id, stateKey);
              const jobTime = job.finished_at || job.started_at || job.created_at;
              const jobTs = jobTime ? Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(jobTime) ? jobTime : `${jobTime}Z`) : 0;
              // Only trigger active popup alert if job failed during current session
              if (jobTs >= sessionStartTimeRef.current - 15000) {
                const jobTitle = (job.job_type || "TASK").replace(/_/g, " ");
                reportError({
                  title: `Job ${job.status === "CANCELLED" ? "Cancelled" : "Failed"}: ${jobTitle}`,
                  message:
                    job.error ||
                    job.message ||
                    "The background processing job encountered an error.",
                  severity: job.status === "CANCELLED" ? "info" : "error",
                  source: "job",
                  jobId: job.job_id,
                  projectId: job.project_id,
                  jobType: job.job_type,
                  rawDetails: job,
                });
              }
            }
          } else if (
            job.status === "QUEUED" &&
            job.error &&
            job.error.trim().length > 0
          ) {
            // Retrying backoff state
            if (previousState !== stateKey) {
              alertedJobStatesRef.current.set(job.job_id, stateKey);
              const jobTitle = (job.job_type || "TASK").replace(/_/g, " ");
              reportError({
                title: `Job Warning: ${jobTitle} Retrying`,
                message: `${job.error} (${job.message || "Backoff retry in progress"})`,
                severity: "warning",
                source: "job",
                jobId: job.job_id,
                projectId: job.project_id,
                jobType: job.job_type,
                rawDetails: job,
              });
            }
          } else {
            if (previousState !== stateKey) {
              const eventTime = job.finished_at || job.started_at || job.created_at;
              const eventMs = eventTime ? Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(eventTime) ? eventTime : `${eventTime}Z`) : 0;
              if (isActiveJob(job) || eventMs >= sessionStartTimeRef.current - 15000) {
                const label = job.status === "RUNNING" ? "Started" : job.status === "QUEUED" ? "Queued" : "Completed";
                reportError({ title: `Job ${label}: ${job.job_type.replace(/_/g, " ")}`, message: job.message || `Job is ${job.status.toLowerCase()}.`, severity: "info", source: "job", jobId: job.job_id, projectId: job.project_id, jobType: job.job_type, rawDetails: job });
              }
            }
            alertedJobStatesRef.current.set(job.job_id, stateKey);
          }
        }
      } catch {
        if (mounted) setEngineHealthy(false);
      } finally {
        polling = false;
      }
    };

    // Run immediately then poll every 5 seconds
    checkJobAlerts();
    const interval = setInterval(checkJobAlerts, 5000);
    const onSubmitted = async (event: Event) => {
      const jobId = (event as CustomEvent<{jobId: string}>).detail?.jobId;
      if (!jobId) return;
      try {
        const job = await api.getJob(jobId);
        if (!mounted) return;
        setJobSnapshots((jobs) => [job, ...jobs.filter((item) => item.job_id !== jobId)]);
        reportError({ title: `Job submitted: ${job.job_type.replace(/_/g, " ")}`, message: job.message, severity: "info", source: "job", jobId, projectId: job.project_id, jobType: job.job_type, rawDetails: job });
        checkJobAlerts();
      } catch { /* The normal monitor retries the lookup. */ }
    };
    window.addEventListener("panelflow:job-submitted", onSubmitted);

    return () => {
      mounted = false;
      clearInterval(interval);
      window.removeEventListener("panelflow:job-submitted", onSubmitted);
    };
  }, [reportError]);

  return (
    <ErrorContext.Provider
      value={{
        activeErrors,
        historyErrors,
        selectedError,
        reportError,
        dismissError,
        clearAllErrors,
        inspectError,
        closeInspector,
        retryJob,
        cancelJob,
        engineHealthy,
        jobs: jobSnapshots,
      }}
    >
      {children}
      {/* EngineJobStatus is now rendered in workspace toolbars (StoryEditorScreen, PanelReviewScreen) via useError() */}
    </ErrorContext.Provider>
  );
};

export const useError = (): ErrorContextValue => {
  const context = useContext(ErrorContext);
  if (!context) {
    throw new Error("useError must be used within an ErrorProvider");
  }
  return context;
};
