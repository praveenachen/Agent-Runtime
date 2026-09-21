import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock3,
  RotateCcw,
  RefreshCw,
  Send,
  XCircle,
  Terminal,
  Layers3,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  cancelJob,
  fetchJob,
  fetchJobs,
  fetchMetricsSummary,
  fetchRuntimeConfig,
  retryJob,
  submitJob,
} from "./api/client";
import { StatusBadge } from "./components/StatusBadge";
import {
  shouldClearForm,
  submissionNotice as getSubmissionNotice,
  terminalStatuses,
  timelineText,
} from "./uiLogic";
import type { FormSnapshot } from "./uiLogic";
import type {
  JobListItem,
  JobRead,
  MetricsSummary,
  WorkflowType,
} from "./types";
import "./styles.css";

const workflows: { value: WorkflowType; label: string }[] = [
  { value: "summarize_text", label: "Summarize text" },
  { value: "extract_structured_data", label: "Extract structured data" },
  { value: "classify_message", label: "Classify message" },
];

const defaultMetrics: MetricsSummary = {
  total_jobs: 0,
  queued_jobs: 0,
  running_jobs: 0,
  completed_jobs: 0,
  failed_jobs: 0,
  success_rate: 0,
  average_latency_ms: 0,
  total_retries: 0,
};

const scenarios = [
  ["normal", "Normal"],
  ["transient_failure", "Transient failure"],
  ["permanent_failure", "Permanent failure"],
  ["malformed_output", "Malformed output"],
  ["slow_execution", "Slow execution"],
] as const;

function duration(ms: number | null | undefined): string {
  if (ms == null) return "–";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

export default function App() {
  const [workflowType, setWorkflowType] =
    useState<WorkflowType>("summarize_text");
  const [text, setText] = useState("");
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobRead | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary>(defaultMetrics);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [scenario, setScenario] = useState("normal");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [submissionNotice, setSubmissionNotice] = useState<string | null>(null);
  const pendingSubmission = useRef<{ fingerprint: string; key: string } | null>(
    null,
  );
  const submitting = useRef(false);
  const formValues = useRef<FormSnapshot>({ text: "", key: "", workflow: "summarize_text", scenario: "normal" });
  const pendingClear = useRef<(FormSnapshot & { jobId: string }) | null>(null);

  function clearCompletedSubmission(job: JobListItem | JobRead) {
    const submitted = pendingClear.current;
    if (!submitted || submitting.current || submitted.jobId !== job.id) return;
    if (!terminalStatuses.has(job.status)) return;
    pendingClear.current = null;
    const current = formValues.current;
    if (!shouldClearForm(submitted, current, job.status)) return;
    formValues.current = { ...current, text: "", key: "" };
    setText("");
    setIdempotencyKey("");
  }

  async function loadDashboard() {
    const [nextJobs, nextMetrics] = await Promise.all([
      fetchJobs(),
      fetchMetricsSummary(),
    ]);
    setJobs(nextJobs);
    setMetrics(nextMetrics);
    const awaiting = pendingClear.current;
    if (awaiting) {
      const recent = nextJobs.find((job) => job.id === awaiting.jobId);
      clearCompletedSubmission(recent ?? await fetchJob(awaiting.jobId));
    }
    if (selectedJobId) {
      setSelectedJob(await fetchJob(selectedJobId));
    }
  }

  useEffect(() => {
    fetchRuntimeConfig().then((config) => setDemoMode(config.demo_mode)).catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    loadDashboard().catch((err) => setError(err.message));
    const interval = window.setInterval(() => {
      loadDashboard().catch((err) => setError(err.message));
    }, 3000);
    return () => window.clearInterval(interval);
  }, [selectedJobId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmissionNotice(null);
    setIsSubmitting(true);
    submitting.current = true;
    try {
      const submitted = { ...formValues.current };
      const fingerprint = JSON.stringify([submitted.workflow, submitted.text, submitted.scenario]);
      if (pendingSubmission.current?.fingerprint !== fingerprint) {
        pendingSubmission.current = { fingerprint, key: crypto.randomUUID() };
      }
      const result = await submitJob(submitted.workflow, submitted.text, submitted.key.trim() || pendingSubmission.current.key, demoMode ? submitted.scenario : undefined);
      submitting.current = false;
      pendingSubmission.current = null;
      pendingClear.current = result.reused ? null : { ...submitted, jobId: result.job.id };
      setSubmissionNotice(getSubmissionNotice(result.reused, result.job.id));
      setSelectedJobId(result.job.id);
      setSelectedJob(result.job);
      clearCompletedSubmission(result.job);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit job");
    } finally {
      submitting.current = false;
      setIsSubmitting(false);
    }
  }

  async function handleSelectJob(jobId: string) {
    setSelectedJobId(jobId);
    setSelectedJob(await fetchJob(jobId));
  }

  async function handleRetry() {
    if (!selectedJob) return;
    setError(null);
    try {
      await retryJob(selectedJob.id);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to retry job");
    }
  }

  async function handleCancel() {
    if (!selectedJob) return;
    try {
      await cancelJob(selectedJob.id);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to cancel job");
    }
  }

  const runningCount = useMemo(
    () => metrics.queued_jobs + metrics.running_jobs,
    [metrics],
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <Terminal size={24} />
          </div>
          <div>
            <p className="eyebrow">Execution / observability</p>
            <h1>Agent Runtime</h1>
          </div>
        </div>
        <button
          className="icon-button"
          onClick={() => loadDashboard()}
          title="Refresh dashboard"
          aria-label="Refresh dashboard"
        >
          <RefreshCw size={18} />
        </button>
      </header>

      <section className="metrics-grid" aria-label="Workflow metrics">
        <MetricCard
          tone="blue"
          icon={<BarChart3 />}
          label="Total jobs"
          value={metrics.total_jobs}
        />
        <MetricCard
          tone="green"
          icon={<CheckCircle2 />}
          label="Success rate"
          value={`${metrics.success_rate}%`}
        />
        <MetricCard
          tone="purple"
          icon={<XCircle />}
          label="Failures"
          value={metrics.failed_jobs}
        />
        <MetricCard
          tone="indigo"
          icon={<Clock3 />}
          label="Avg latency"
          value={duration(metrics.average_latency_ms)}
        />
        <MetricCard
          tone="cyan"
          icon={<Activity />}
          label="In flight"
          value={runningCount}
        />
      </section>

      <section className="workspace">
        <form className="submit-panel" onSubmit={handleSubmit}>
          <div className="section-heading">
            <h2>Submit workflow</h2>
            <Send size={18} />
          </div>
          <label>
            Workflow
            <select
              value={workflowType}
              onChange={(event) => {
                const value = event.target.value as WorkflowType;
                formValues.current.workflow = value;
                setWorkflowType(value);
              }}
            >
              {workflows.map((workflow) => (
                <option key={workflow.value} value={workflow.value}>
                  {workflow.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Input
            <textarea
              value={text}
              onChange={(event) => {
                formValues.current.text = event.target.value;
                setText(event.target.value);
              }}
              placeholder="Paste an incident note, customer message, or long-form text..."
              required
            />
          </label>
          {demoMode && (
            <details className="demo-controls">
              <summary>Demo controls <small>Development only</small></summary>
              <label>Execution scenario
                <select value={scenario} onChange={(event) => {
                  formValues.current.scenario = event.target.value;
                  setScenario(event.target.value);
                }}>
                  {scenarios.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label>Idempotency key
                <input value={idempotencyKey} onChange={(event) => {
                  formValues.current.key = event.target.value;
                  setIdempotencyKey(event.target.value);
                }} placeholder="Generated automatically if blank" />
              </label>
            </details>
          )}
          {submissionNotice && <p className="submission-notice">{submissionNotice}</p>}
          {error && <p className="error-text">{error}</p>}
          <button
            className="primary-button"
            disabled={isSubmitting || !text.trim()}
          >
            <Send size={15} aria-hidden="true" />
            {isSubmitting ? "Submitting" : "Queue job"}
          </button>
        </form>

        <section className="jobs-panel">
          <div className="section-heading">
            <h2>Workflow jobs</h2>
            <span>{jobs.length} recent</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Retries</th>
                  <th>Latency</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className={selectedJobId === job.id ? "selected-row" : ""}
                    onClick={() => handleSelectJob(job.id)}
                  >
                    <td className="mono">
                      <button
                        className="job-link"
                        aria-label={`View job ${job.id}`}
                        aria-current={
                          selectedJobId === job.id ? "true" : undefined
                        }
                        onClick={(event) => {
                          event.stopPropagation();
                          handleSelectJob(job.id);
                        }}
                      >
                        {job.id.slice(0, 8)}
                      </button>
                    </td>
                    <td>{job.workflow_type}</td>
                    <td>
                      <StatusBadge status={job.status} retrying={job.retry_count > 0} />
                    </td>
                    <td>
                      {job.retry_count}/{job.max_retries}
                    </td>
                    <td>{duration(job.latency_ms)}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      <div className="empty-state">
                        <Layers3 size={23} aria-hidden="true" />
                        <strong>No workflow jobs yet</strong>
                        <span>
                          Queue a workflow to begin monitoring its execution.
                        </span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      {selectedJob && (
        <section className="detail-panel">
          <div className="section-heading">
            <div>
              <h2>Job detail</h2>
              <p className="detail-id">{selectedJob.id}</p>
            </div>
            <div className="detail-actions">
              <StatusBadge status={selectedJob.status} retrying={selectedJob.retry_count > 0} />
              {(selectedJob.status === "queued" ||
                selectedJob.status === "running") && (
                <button className="secondary-button" onClick={handleCancel}>
                  Cancel
                </button>
              )}
              {selectedJob.status === "failed" &&
                selectedJob.error?.retryable &&
                selectedJob.retry_count < selectedJob.max_retries && (
                  <button className="secondary-button" onClick={handleRetry}>
                    <RotateCcw size={16} />
                    Retry
                  </button>
                )}
            </div>
          </div>

          <div className="detail-grid">
            <InfoBlock label="Workflow" value={selectedJob.workflow_type} />
            <InfoBlock
              label="Attempts / retries"
              value={`${selectedJob.attempt_count} started · ${selectedJob.retry_count}/${selectedJob.max_retries} retries`}
            />
            <InfoBlock
              label="Started"
              value={
                selectedJob.started_at
                  ? new Date(selectedJob.started_at).toLocaleString()
                  : "-"
              }
            />
            <InfoBlock
              label="Completed"
              value={
                selectedJob.completed_at
                  ? new Date(selectedJob.completed_at).toLocaleString()
                  : "-"
              }
            />
            <InfoBlock label="Provider" value={selectedJob.provider_name ?? "–"} />
            <InfoBlock label="Model" value={selectedJob.model_name ?? "–"} />
            <InfoBlock label="Queue wait" value={duration(selectedJob.queue_latency_ms)} />
            <InfoBlock label="Execution time" value={selectedJob.started_at && selectedJob.completed_at ? duration(new Date(selectedJob.completed_at).getTime() - new Date(selectedJob.started_at).getTime()) : "–"} />
            <InfoBlock label="Total time" value={selectedJob.completed_at ? duration(new Date(selectedJob.completed_at).getTime() - new Date(selectedJob.created_at).getTime()) : "–"} />
            <InfoBlock label="Idempotency key" value={selectedJob.idempotency_key ?? "–"} />
            <InfoBlock label="Correlation ID" value={selectedJob.correlation_id} />
          </div>

          <div className="artifact-grid">
            <Artifact title="Input payload" value={selectedJob.input_payload} />
            <Artifact
              title="Output payload"
              value={selectedJob.output_payload ?? {}}
            />
          </div>

          {selectedJob.error_message && (
            <div className="error-box">
              <strong>{selectedJob.error?.code ?? "Error"}</strong>
              <p>Stage: {selectedJob.error?.code === "StructuredOutputInvalid" ? "Output validation" : selectedJob.error?.code?.startsWith("Provider") ? "Provider" : "Execution"} · Attempt {selectedJob.attempt_count} · Retryable: {selectedJob.error?.retryable ? "Yes" : "No"} · Retries: {selectedJob.retry_count}/{selectedJob.max_retries}</p>
              <pre>{selectedJob.error_message}</pre>
            </div>
          )}

          <div className="logs-panel">
            <h2>Execution timeline</h2>
            {selectedJob.logs.map((log) => (
              <div className={`log-line log-${log.level}`} key={log.id}>
                <span>{new Date(log.created_at).toLocaleTimeString()}</span>
                <strong>{typeof log.context?.attempt === "number" && log.context.attempt > 0 ? `#${log.context.attempt}` : log.level}</strong>
                <p>{timelineText(log)}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function MetricCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  tone: "blue" | "green" | "purple" | "indigo" | "cyan";
}) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-icon" aria-hidden="true">
        {icon}
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function InfoBlock({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="info-block">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Artifact({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown>;
}) {
  return (
    <div className="artifact">
      <h2>{title}</h2>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
