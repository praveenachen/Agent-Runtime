import type { JobStatus } from "../types";

const labels: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

export function StatusBadge({ status, retrying = false }: { status: JobStatus; retrying?: boolean }) {
  const isRetrying = status === "queued" && retrying;
  return <span className={`status status-${isRetrying ? "retrying" : status}`}>{isRetrying ? "Retrying" : labels[status]}</span>;
}
