import type { JobStatus } from "../types";

const labels: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`status status-${status}`}>{labels[status]}</span>;
}
