"use client";

import { useState } from "react";
import type { ReviewDecision } from "@/lib/types";

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
      <h3 className="text-sm font-semibold text-gray-300">New Monthly Review</h3>

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
