import { Activity, BarChart3, CheckCircle2, Clock3, RefreshCw, Send, XCircle } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { fetchJobs, fetchMetricsSummary, submitJob } from "./api/client";
import { StatusBadge } from "./components/StatusBadge";
import type { JobListItem, MetricsSummary, WorkflowType } from "./types";
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
  const [workflowType, setWorkflowType] = useState<WorkflowType>("summarize_text");
  const [text, setText] = useState("");
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [metrics, setMetrics] = useState<MetricsSummary>(defaultMetrics);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard() {
    const [nextJobs, nextMetrics] = await Promise.all([fetchJobs(), fetchMetricsSummary()]);
    setJobs(nextJobs);
    setMetrics(nextMetrics);
  }

  useEffect(() => {
    loadDashboard().catch((err) => setError(err.message));
    const interval = window.setInterval(() => {
      loadDashboard().catch((err) => setError(err.message));
    }, 3000);
    return () => window.clearInterval(interval);
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await submitJob(workflowType, text);
      setText("");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit job");
    } finally {
      setIsSubmitting(false);
    }
  }

  const runningCount = useMemo(() => metrics.queued_jobs + metrics.running_jobs, [metrics]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI workflow operations</p>
          <h1>Agent Runtime</h1>
        </div>
        <button className="icon-button" onClick={() => loadDashboard()} title="Refresh dashboard">
          <RefreshCw size={18} />
        </button>
      </header>

      <section className="metrics-grid" aria-label="Workflow metrics">
        <MetricCard icon={<BarChart3 />} label="Total jobs" value={metrics.total_jobs} />
        <MetricCard icon={<CheckCircle2 />} label="Success rate" value={`${metrics.success_rate}%`} />
        <MetricCard icon={<XCircle />} label="Failures" value={metrics.failed_jobs} />
        <MetricCard icon={<Clock3 />} label="Avg latency" value={`${metrics.average_latency_ms} ms`} />
        <MetricCard icon={<Activity />} label="In flight" value={runningCount} />
      </section>

      <section className="workspace">
        <form className="submit-panel" onSubmit={handleSubmit}>
          <div className="section-heading">
            <h2>Submit workflow</h2>
            <Send size={18} />
          </div>
          <label>
            Workflow
            <select value={workflowType} onChange={(event) => setWorkflowType(event.target.value as WorkflowType)}>
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
          <button className="primary-button" disabled={isSubmitting || !text.trim()}>
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
                  <tr key={job.id}>
                    <td className="mono">{job.id.slice(0, 8)}</td>
                    <td>{job.workflow_type}</td>
                    <td><StatusBadge status={job.status} /></td>
                    <td>{job.retry_count}/{job.max_retries}</td>
                    <td>{job.latency_ms ? `${job.latency_ms} ms` : "-"}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty-cell">No workflow jobs yet</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

