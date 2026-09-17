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
  retryJob,
  submitJob,
} from "./api/client";
import { StatusBadge } from "./components/StatusBadge";
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
  const pendingSubmission = useRef<{ fingerprint: string; key: string } | null>(
    null,
  );

  async function loadDashboard() {
    const [nextJobs, nextMetrics] = await Promise.all([
      fetchJobs(),
      fetchMetricsSummary(),
    ]);
    setJobs(nextJobs);
    setMetrics(nextMetrics);
    if (selectedJobId) {
      setSelectedJob(await fetchJob(selectedJobId));
    }
  }

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
    setIsSubmitting(true);
    try {
      const fingerprint = JSON.stringify([workflowType, text]);
      if (pendingSubmission.current?.fingerprint !== fingerprint) {
        pendingSubmission.current = { fingerprint, key: crypto.randomUUID() };
      }
      await submitJob(workflowType, text, pendingSubmission.current.key);
      pendingSubmission.current = null;
      setText("");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit job");
    } finally {
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
          value={`${metrics.average_latency_ms} ms`}
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
              onChange={(event) =>
                setWorkflowType(event.target.value as WorkflowType)
              }
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
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste an incident note, customer message, or long-form text..."
              required
            />
          </label>
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
                      <StatusBadge status={job.status} />
                    </td>
                    <td>
                      {job.retry_count}/{job.max_retries}
                    </td>
                    <td>{job.latency_ms ? `${job.latency_ms} ms` : "-"}</td>
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
              <StatusBadge status={selectedJob.status} />
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
              label="Retries"
              value={`${selectedJob.retry_count}/${selectedJob.max_retries}`}
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
              <strong>Error</strong>
              <pre>{selectedJob.error_message}</pre>
            </div>
          )}

          <div className="logs-panel">
            <h2>Execution logs</h2>
            {selectedJob.logs.map((log) => (
              <div className={`log-line log-${log.level}`} key={log.id}>
                <span>{new Date(log.created_at).toLocaleTimeString()}</span>
                <strong>{log.level}</strong>
                <p>{log.message}</p>
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
