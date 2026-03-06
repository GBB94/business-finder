"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";
import type { ResearchJob, ResearchJobListResponse, Evidence, EvidenceListResponse } from "@/lib/types";

interface Props {
  ideaId: string;
  audience: string;
  problemStatement: string;
}

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-gray-700 text-gray-300",
  running: "bg-indigo-600 text-white animate-pulse",
  completed: "bg-green-700 text-green-200",
  failed: "bg-red-700 text-red-200",
  dead_letter: "bg-red-900 text-red-300",
};

export default function ResearchPanel({ ideaId, audience, problemStatement }: Props) {
  const [queryInput, setQueryInput] = useState("");
  const [sourceHN, setSourceHN] = useState(true);
  const [sourceReddit, setSourceReddit] = useState(true);
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [safariReport, setSafariReport] = useState<{
    report?: string;
    themes?: string[];
    language_patterns?: string[];
    objections?: string[];
    post_count?: number;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Pre-fill queries from idea context
  useEffect(() => {
    if (!queryInput) {
      const keywords: string[] = [];
      if (audience) {
        const words = audience.split(/\s+/).filter((w) => w.length > 3).slice(0, 2);
        keywords.push(...words);
      }
      if (problemStatement) {
        const words = problemStatement.split(/\s+/).filter((w) => w.length > 3).slice(0, 2);
        keywords.push(...words);
      }
      if (keywords.length > 0) {
        setQueryInput(keywords.join(", "));
      }
    }
    // Only on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await apiFetch<ResearchJobListResponse>(
        `/api/ideas/${ideaId}/research/jobs`
      );
      setJobs(data.items);
    } catch {
      // silent
    }
  }, [ideaId]);

  const fetchSafariReport = useCallback(async () => {
    try {
      const data = await apiFetch<EvidenceListResponse>(
        `/api/ideas/${ideaId}/evidence?evidence_type=community_signal`
      );
      const report = data.items.find((e: Evidence) =>
        e.title.startsWith("Sales Safari Report:")
      );
      if (report?.content) {
        setSafariReport(report.content as {
          report?: string;
          themes?: string[];
          language_patterns?: string[];
          objections?: string[];
          post_count?: number;
        });
      }
    } catch {
      // silent
    }
  }, [ideaId]);

  useEffect(() => {
    fetchJobs();
    fetchSafariReport();
  }, [fetchJobs, fetchSafariReport]);

  const STALE_MS = 2 * 60 * 1000; // 2 minutes
  const isJobActive = (j: ResearchJob) => {
    if (j.status === "running") return true;
    if (j.status === "queued") {
      return Date.now() - new Date(j.created_at).getTime() < STALE_MS;
    }
    return false;
  };

  const hasActiveJob = jobs.some(isJobActive);

  // Auto-poll while jobs are active (not stale)
  useEffect(() => {
    if (hasActiveJob) {
      if (!pollRef.current) {
        pollRef.current = setInterval(() => {
          fetchJobs();
          fetchSafariReport();
        }, 5000);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [hasActiveJob, fetchJobs, fetchSafariReport]);

  const handleScan = async () => {
    setError("");
    const queries = queryInput
      .split(",")
      .map((q) => q.trim())
      .filter(Boolean)
      .slice(0, 5);

    if (queries.length === 0) {
      setError("Enter at least one search query.");
      return;
    }

    const sources: string[] = [];
    if (sourceHN) sources.push("hn");
    if (sourceReddit) sources.push("reddit");
    if (sources.length === 0) {
      setError("Select at least one source.");
      return;
    }

    setSubmitting(true);
    try {
      await apiFetch(`/api/ideas/${ideaId}/research/scan`, {
        method: "POST",
        body: JSON.stringify({ queries, sources }),
      });
      await fetchJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-8">
      {/* Section 1: Scan Form */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          Community Scan
        </h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">
              Search queries (comma-separated, max 5)
            </label>
            <input
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="saas pricing, indie hacker tools"
              className="w-full rounded bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-1.5 text-xs text-gray-400">
              <input
                type="checkbox"
                checked={sourceHN}
                onChange={(e) => setSourceHN(e.target.checked)}
                className="rounded"
              />
              Hacker News
            </label>
            <label className="flex items-center gap-1.5 text-xs text-gray-400">
              <input
                type="checkbox"
                checked={sourceReddit}
                onChange={(e) => setSourceReddit(e.target.checked)}
                className="rounded"
              />
              Reddit
            </label>
          </div>
          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}
          <button
            onClick={handleScan}
            disabled={submitting || hasActiveJob}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting
              ? "Starting..."
              : hasActiveJob
              ? "Scan in progress..."
              : "Run Scan"}
          </button>
        </div>
      </div>

      {/* Section 2: Job History */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          Scan History
        </h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-gray-600">No scans yet.</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => {
              const queries = (
                (job.input_params?.queries as string[]) ?? []
              ).join(", ");
              const isExpanded = expandedJob === job.id;

              return (
                <div
                  key={job.id}
                  className="rounded-lg border border-gray-800 bg-gray-900"
                >
                  <button
                    onClick={() =>
                      setExpandedJob(isExpanded ? null : job.id)
                    }
                    className="w-full px-4 py-3 flex items-center justify-between text-left"
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                          STATUS_STYLES[job.status] ?? "bg-gray-700 text-gray-300"
                        }`}
                      >
                        {job.status}
                      </span>
                      <span className="text-xs text-gray-400 truncate max-w-[300px]">
                        {queries || "—"}
                      </span>
                    </div>
                    <span className="text-[10px] text-gray-600">
                      {new Date(job.created_at).toLocaleDateString()}
                    </span>
                  </button>

                  {isExpanded && job.status === "completed" && job.results && (
                    <div className="px-4 pb-3 border-t border-gray-800 pt-2 text-xs text-gray-400 space-y-1">
                      <p>
                        Posts found:{" "}
                        <span className="text-gray-200">
                          {(job.results as Record<string, unknown>).post_count as number}
                        </span>
                      </p>
                      <p>
                        Evidence created:{" "}
                        <span className="text-gray-200">
                          {(job.results as Record<string, unknown>).evidence_created as number}
                        </span>
                      </p>
                      {((job.results as Record<string, unknown>).themes as string[] | undefined)?.length ? (
                        <p>
                          Themes:{" "}
                          <span className="text-gray-200">
                            {((job.results as Record<string, unknown>).themes as string[]).join(", ")}
                          </span>
                        </p>
                      ) : null}
                    </div>
                  )}

                  {isExpanded && job.status === "failed" && job.error_message && (
                    <div className="px-4 pb-3 border-t border-gray-800 pt-2">
                      <p className="text-xs text-red-400">{job.error_message}</p>
                    </div>
                  )}

                  {isExpanded && job.status === "dead_letter" && (
                    <div className="px-4 pb-3 border-t border-gray-800 pt-2">
                      <p className="text-xs text-red-400">
                        Job permanently failed after {job.retry_count} retries.
                        {job.error_message ? ` Last error: ${job.error_message}` : ""}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Section 3: Sales Safari Report */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          Sales Safari Report
        </h3>
        {safariReport ? (
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-4">
            {safariReport.report && (
              <p className="text-sm text-gray-300 whitespace-pre-wrap">
                {safariReport.report}
              </p>
            )}

            {safariReport.themes?.length ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                  Themes
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {safariReport.themes.map((theme, i) => (
                    <span
                      key={i}
                      className="rounded-full bg-indigo-900/50 px-2.5 py-0.5 text-xs text-indigo-300"
                    >
                      {theme}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {safariReport.language_patterns?.length ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                  Language Patterns
                </h4>
                <ul className="space-y-1">
                  {safariReport.language_patterns.map((p, i) => (
                    <li key={i} className="text-xs text-gray-400">
                      &ldquo;{p}&rdquo;
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {safariReport.objections?.length ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                  Objections
                </h4>
                <ol className="list-decimal list-inside space-y-1">
                  {safariReport.objections.map((obj, i) => (
                    <li key={i} className="text-xs text-gray-400">
                      {obj}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-gray-600">
            Run a community scan to generate a Sales Safari Report.
          </p>
        )}
      </div>
    </div>
  );
}
