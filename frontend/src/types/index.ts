export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "timed_out";

export type WorkflowType = "summarize_text" | "extract_structured_data" | "classify_message";

export interface JobListItem {
  id: string;
  workflow_type: WorkflowType;
  status: JobStatus;
  retry_count: number;
  max_retries: number;
  created_at: string;
  completed_at: string | null;
  latency_ms: number | null;
}

export interface JobLog {
  id: number;
  level: string;
  message: string;
  created_at: string;
  context: Record<string, unknown> | null;
}

export interface JobRead extends JobListItem {
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  logs: JobLog[];
  correlation_id: string;
  attempt_count: number;
  error: { code: string; message: string; retryable: boolean } | null;
  retry_count: number;
  max_retries: number;
  idempotency_key: string | null;
  queue_latency_ms: number | null;
  demo_scenario: string | null;
  provider_name: string | null;
  model_name: string | null;
}

export interface MetricsSummary {
  total_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  success_rate: number;
  average_latency_ms: number;
  total_retries: number;
}
