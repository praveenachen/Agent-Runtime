import type { JobLog, JobStatus, WorkflowType } from "./types";

export type FormSnapshot = {
  text: string;
  key: string;
  workflow: WorkflowType;
  scenario: string;
};

export const terminalStatuses = new Set<JobStatus>([
  "completed",
  "failed",
  "cancelled",
  "timed_out",
]);

export function submissionNotice(reused: boolean, jobId: string): string {
  return reused
    ? `Existing execution reused — no new job was created. (${jobId.slice(0, 8)})`
    : `Job queued: ${jobId.slice(0, 8)}`;
}

export function shouldClearForm(
  submitted: FormSnapshot,
  current: FormSnapshot,
  status: JobStatus,
): boolean {
  return terminalStatuses.has(status) &&
    submitted.text === current.text &&
    submitted.key === current.key &&
    submitted.workflow === current.workflow &&
    submitted.scenario === current.scenario;
}

export function timelineText(log: JobLog): string {
  const context = log.context;
  let value = log.message;
  if (log.message === "Retry scheduled" && typeof context?.retry_delay_seconds === "number") {
    value += ` in ${context.retry_delay_seconds}s`;
  }
  if (typeof context?.provider_latency_ms === "number") {
    const latency = context.provider_latency_ms;
    value += latency < 1000 ? ` · ${Math.round(latency)} ms` : ` · ${(latency / 1000).toFixed(2)} s`;
  }
  const error = context?.error as { code?: unknown; message?: unknown } | undefined;
  if (typeof error?.code === "string") value += ` · ${error.code}`;
  if (typeof error?.message === "string") value += `: ${error.message}`;
  return value;
}
