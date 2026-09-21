import type { JobListItem, JobRead, MetricsSummary, WorkflowType } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchJobs(): Promise<JobListItem[]> {
  const response = await fetch(`${API_BASE_URL}/jobs`);
  if (!response.ok) throw new Error("Unable to load jobs");
  return response.json();
}

export async function fetchRuntimeConfig(): Promise<{ demo_mode: boolean }> {
  const response = await fetch(`${API_BASE_URL}/runtime-config`);
  if (!response.ok) throw new Error("Unable to load runtime configuration");
  return response.json();
}

export async function fetchMetricsSummary(): Promise<MetricsSummary> {
  const response = await fetch(`${API_BASE_URL}/metrics-summary`);
  if (!response.ok) throw new Error("Unable to load metrics");
  return response.json();
}

export async function fetchJob(jobId: string): Promise<JobRead> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
  if (!response.ok) throw new Error("Unable to load job");
  return response.json();
}

export async function submitJob(workflowType: WorkflowType, text: string, idempotencyKey: string, scenario?: string): Promise<{ job: JobRead; reused: boolean }> {
  const input_payload =
    workflowType === "classify_message" ? { message: text } : { text };
  const response = await fetch(`${API_BASE_URL}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ workflow_type: workflowType, input_payload, ...(scenario ? { demo_scenario: scenario } : {}) }),
  });
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error("That idempotency key is already associated with a different request. Use a new key or restore the original request.");
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Unable to submit job");
  }
  return { job: await response.json(), reused: response.headers.get("X-Idempotency-Reused") === "true" };
}

export async function cancelJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error("Unable to cancel job");
}

export async function retryJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/retry`, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Unable to retry job");
  }
}
