"use client";

import { useState } from "react";
import type { ReviewDecision, ReviewSummaryResponse } from "@/lib/types";
import { apiFetch } from "@/lib/api";

const DECISIONS: { value: ReviewDecision; label: string; color: string }[] = [
  { value: "continue", label: "Continue", color: "bg-green-600 text-white" },
  { value: "pivot", label: "Pivot", color: "bg-blue-600 text-white" },
  { value: "kill", label: "Kill", color: "bg-red-600 text-white" },
  { value: "park", label: "Park", color: "bg-yellow-600 text-white" },
];

interface MonthlyReviewFormProps {
  ideaId: string;
  onSubmit: (data: {
    review_date: string;
    decision: ReviewDecision;
    reasoning: string;
    next_hypothesis?: string;
    metrics_snapshot?: Record<string, string>;
  }) => void;
  onCancel: () => void;
}

export default function MonthlyReviewForm({
  ideaId,
  onSubmit,
  onCancel,
}: MonthlyReviewFormProps) {
  const today = new Date().toISOString().slice(0, 10);
  const [reviewDate, setReviewDate] = useState(today);
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [reasoning, setReasoning] = useState("");
  const [nextHypothesis, setNextHypothesis] = useState("");
  const [metricsRows, setMetricsRows] = useState<{ key: string; value: string }[]>([]);
  const [generating, setGenerating] = useState(false);
  const [summary, setSummary] = useState<ReviewSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryExpanded, setSummaryExpanded] = useState(true);

  const handleGenerateSummary = async () => {
    setGenerating(true);
    setSummaryError(null);
    try {
      const result = await apiFetch<ReviewSummaryResponse>(
        `/api/ideas/${ideaId}/reviews/generate-summary`,
        { method: "POST" }
      );
      setSummary(result);
      setSummaryExpanded(true);
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Summary generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const addMetricRow = () => {
    setMetricsRows([...metricsRows, { key: "", value: "" }]);
  };

  const removeMetricRow = (index: number) => {
    setMetricsRows(metricsRows.filter((_, i) => i !== index));
  };

  const updateMetricRow = (index: number, field: "key" | "value", val: string) => {
    const updated = [...metricsRows];
    updated[index] = { ...updated[index], [field]: val };
    setMetricsRows(updated);
  };

  const handleSubmit = () => {
    if (!decision || !reasoning.trim()) return;

    const metricsSnapshot: Record<string, string> = {};
    for (const row of metricsRows) {
      if (row.key.trim()) {
        metricsSnapshot[row.key.trim()] = row.value.trim();
      }
    }

    onSubmit({
      review_date: reviewDate,
      decision,
      reasoning: reasoning.trim(),
      next_hypothesis:
        (decision === "continue" || decision === "pivot") && nextHypothesis.trim()
          ? nextHypothesis.trim()
          : undefined,
      metrics_snapshot: Object.keys(metricsSnapshot).length > 0 ? metricsSnapshot : undefined,
    });
  };

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">New Monthly Review</h3>
        <button
          onClick={handleGenerateSummary}
          disabled={generating}
          className="rounded-lg border border-purple-700 px-3 py-1.5 text-xs font-medium text-purple-400 hover:bg-purple-900/30 transition-colors disabled:opacity-50"
        >
          {generating ? "Generating…" : "Generate Summary"}
        </button>
      </div>

      {generating && (
        <div className="flex items-center gap-2 text-xs text-purple-400">
          <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-purple-500" />
          Generating AI summary…
        </div>
      )}

      {summaryError && !generating && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
          {summaryError}
        </div>
      )}

      {summary && (
        <div className="rounded-lg border border-purple-900/40 bg-purple-950/20 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-400">
              AI Review Summary
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setSummaryExpanded(!summaryExpanded)}
                className="text-[10px] text-gray-600 hover:text-gray-400"
              >
                {summaryExpanded ? "collapse" : "expand"}
              </button>
              <button
                onClick={() => setSummary(null)}
                className="text-[10px] text-gray-600 hover:text-gray-400"
              >
                dismiss
              </button>
            </div>
          </div>
          {summaryExpanded && (
            <div className="space-y-3">
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-300">
                {summary.summary}
              </p>

              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Metrics Assessment
                </span>
                <p className="mt-1 text-xs text-gray-400">{summary.metrics_assessment}</p>
              </div>

              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  Kill Trigger Status
                </span>
                <p className="mt-1 text-xs text-gray-400">{summary.trigger_status}</p>
              </div>

              {summary.key_developments.length > 0 && (
                <div>
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    Key Developments
                  </span>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-gray-300">
                    {summary.key_developments.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                </div>
              )}

              {summary.open_questions.length > 0 && (
                <div>
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    Open Questions
                  </span>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-gray-400 italic">
                    {summary.open_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs text-gray-500">Review Date</label>
        <input
          type="date"
          value={reviewDate}
          onChange={(e) => setReviewDate(e.target.value)}
          className="rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">Decision</label>
        <div className="flex gap-2">
          {DECISIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => setDecision(d.value)}
              className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                decision === d.value
                  ? d.color
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
        {(decision === "kill" || decision === "park") && (
          <p className="mt-1.5 text-xs text-yellow-500">
            This will transition the idea to {decision === "kill" ? "killed" : "parked"} status.
          </p>
        )}
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">
          Reasoning <span className="text-red-400">*</span>
        </label>
        <textarea
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          rows={3}
          className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Why this decision?"
        />
      </div>

      {(decision === "continue" || decision === "pivot") && (
        <div>
          <label className="mb-1 block text-xs text-gray-500">Next Hypothesis</label>
          <textarea
            value={nextHypothesis}
            onChange={(e) => setNextHypothesis(e.target.value)}
            rows={2}
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="What will you test next?"
          />
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs text-gray-500">Metrics Snapshot (optional)</label>
          <button
            onClick={addMetricRow}
            className="text-xs text-indigo-400 hover:text-indigo-300"
          >
            + Add metric
          </button>
        </div>
        {metricsRows.map((row, i) => (
          <div key={i} className="flex gap-2 mb-1">
            <input
              value={row.key}
              onChange={(e) => updateMetricRow(i, "key", e.target.value)}
              className="flex-1 rounded bg-gray-800 px-2 py-1 text-sm text-gray-100 placeholder-gray-600 outline-none"
              placeholder="Metric name"
            />
            <input
              value={row.value}
              onChange={(e) => updateMetricRow(i, "value", e.target.value)}
              className="flex-1 rounded bg-gray-800 px-2 py-1 text-sm text-gray-100 placeholder-gray-600 outline-none"
              placeholder="Value"
            />
            <button
              onClick={() => removeMetricRow(i)}
              className="text-xs text-gray-500 hover:text-red-400 px-1"
            >
              &times;
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleSubmit}
          disabled={!decision || !reasoning.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save Review
        </button>
        <button
          onClick={onCancel}
          className="rounded px-3 py-2 text-sm text-gray-400 hover:text-gray-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
