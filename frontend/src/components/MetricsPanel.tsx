"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { MetricsDashboardResponse, MetricWithBenchmark, ComputedMetric, TriggerState } from "@/lib/types";

const METRIC_OPTIONS: { value: string; label: string; category: string }[] = [
  // Retention
  { value: "day_30_retention", label: "Day-30 Retention (%)", category: "retention" },
  { value: "monthly_churn", label: "Monthly Churn (%)", category: "retention" },
  { value: "activation_rate", label: "Activation Rate (%)", category: "retention" },
  { value: "nrr", label: "Net Revenue Retention (%)", category: "retention" },
  // Economics
  { value: "mrr", label: "MRR ($)", category: "economics" },
  { value: "gross_margin", label: "Gross Margin (%)", category: "economics" },
  { value: "cac", label: "CAC ($)", category: "economics" },
  { value: "ltv", label: "LTV ($)", category: "economics" },
  { value: "payment_processing_cost", label: "Payment Processing Cost (%)", category: "economics" },
  { value: "ai_inference_cost_pct", label: "AI Inference Cost (%)", category: "economics" },
];

function formatValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "—";
  if (unit === "$") return `$${value.toLocaleString()}`;
  if (unit === "%") return `${value}%`;
  if (unit === "x") return `${value}x`;
  if (unit === "months") return `${value} mo`;
  return String(value);
}

function benchmarkColor(passes: boolean | null | undefined): string {
  if (passes === null || passes === undefined) return "bg-gray-700";
  return passes ? "bg-green-600" : "bg-red-600";
}

function triggerDot(state: string): string {
  if (state === "red") return "bg-red-500";
  if (state === "yellow") return "bg-yellow-500";
  return "bg-gray-600";
}

function triggerTextColor(state: string): string {
  if (state === "red") return "text-red-400";
  if (state === "yellow") return "text-amber-400";
  return "text-gray-500";
}

function defaultPeriod(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 7);
  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

interface MetricsPanelProps {
  ideaId: string;
}

export default function MetricsPanel({ ideaId }: MetricsPanelProps) {
  const [dashboard, setDashboard] = useState<MetricsDashboardResponse | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [metricKey, setMetricKey] = useState(METRIC_OPTIONS[0].value);
  const [value, setValue] = useState("");
  const [sampleSize, setSampleSize] = useState("");
  const [periodStart, setPeriodStart] = useState(defaultPeriod().start);
  const [periodEnd, setPeriodEnd] = useState(defaultPeriod().end);
  const [note, setNote] = useState("");

  const fetchDashboard = useCallback(async () => {
    try {
      const data = await apiFetch<MetricsDashboardResponse>(
        `/api/ideas/${ideaId}/metrics/dashboard`
      );
      setDashboard(data);
    } catch (err) {
      console.error("Failed to fetch metrics dashboard:", err);
    }
  }, [ideaId]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value) return;

    const selectedOption = METRIC_OPTIONS.find((o) => o.value === metricKey);
    const category = selectedOption?.category ?? "retention";

    setSaving(true);
    try {
      await apiFetch(`/api/ideas/${ideaId}/metrics`, {
        method: "POST",
        body: JSON.stringify({
          category,
          metric_key: metricKey,
          value: parseFloat(value),
          sample_size: sampleSize ? parseInt(sampleSize, 10) : null,
          period_start: periodStart,
          period_end: periodEnd,
          note: note || null,
        }),
      });
      setShowForm(false);
      setValue("");
      setSampleSize("");
      setNote("");
      const d = defaultPeriod();
      setPeriodStart(d.start);
      setPeriodEnd(d.end);
      fetchDashboard();
    } catch (err) {
      console.error("Failed to save metric:", err);
    } finally {
      setSaving(false);
    }
  };

  const renderMetricRow = (m: MetricWithBenchmark) => (
    <div
      key={m.metric_key}
      className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 px-3 py-2"
    >
      <div className="flex-1">
        <span className="text-sm text-gray-300">{m.label}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-gray-100">
          {formatValue(m.latest_value, m.unit)}
        </span>
        {m.sample_size !== null && m.sample_size !== undefined && (
          <span className="text-[10px] text-gray-600">n={m.sample_size}</span>
        )}
        {m.benchmark_value !== null && m.benchmark_value !== undefined && (
          <div className="flex items-center gap-1.5">
            <div
              className={`h-2 w-2 rounded-full ${benchmarkColor(m.passes_benchmark)}`}
            />
            <span className="text-[10px] text-gray-600">
              {m.benchmark_direction === "floor" ? ">" : "<"}{" "}
              {formatValue(m.benchmark_value, m.unit)}
            </span>
          </div>
        )}
      </div>
    </div>
  );

  const renderComputedMetric = (c: ComputedMetric) => (
    <div
      key={c.metric_key}
      className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 px-3 py-2"
    >
      <div>
        <span className="text-sm text-gray-300">{c.label}</span>
        {c.note && (
          <p className="text-[10px] text-gray-600">{c.note}</p>
        )}
      </div>
      <span className="text-sm font-medium text-gray-100">
        {formatValue(c.value, c.unit)}
      </span>
    </div>
  );

  const renderTrigger = (t: TriggerState) => (
    <div
      key={t.key}
      className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
        t.state === "red"
          ? "border-red-800 bg-red-950/30"
          : t.state === "yellow"
          ? "border-amber-800 bg-amber-950/20"
          : "border-gray-800 bg-gray-900"
      }`}
    >
      <span className={`shrink-0 h-2.5 w-2.5 rounded-full ${triggerDot(t.state)}`} />
      <span className={`flex-1 text-sm ${triggerTextColor(t.state)}`}>
        {t.label}
      </span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
          t.category === "hard"
            ? "bg-red-900/40 text-red-400"
            : "bg-amber-900/40 text-amber-400"
        }`}
      >
        {t.category}
      </span>
      {t.state === "red" && (
        <span className="text-[10px] font-medium text-red-400 uppercase">
          Fired
        </span>
      )}
      {t.state === "yellow" && (
        <span className="text-[10px] font-medium text-amber-400 uppercase">
          Warning
        </span>
      )}
      {t.state === "grey" && (
        <span className="text-[10px] text-gray-600 uppercase">
          Insufficient data
        </span>
      )}
    </div>
  );

  if (!dashboard) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-gray-500">Loading metrics...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Entry form toggle */}
      {showForm ? (
        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-3"
        >
          <h4 className="text-sm font-semibold text-gray-300">Add Metric Entry</h4>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Metric</label>
            <select
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <optgroup label="Retention & Product">
                {METRIC_OPTIONS.filter((o) => o.category === "retention").map(
                  (o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  )
                )}
              </optgroup>
              <optgroup label="Economics">
                {METRIC_OPTIONS.filter((o) => o.category === "economics").map(
                  (o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  )
                )}
              </optgroup>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Value</label>
              <input
                type="number"
                step="any"
                required
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="e.g. 42.5"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Sample Size (optional)
              </label>
              <input
                type="number"
                value={sampleSize}
                onChange={(e) => setSampleSize(e.target.value)}
                className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="e.g. 100"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Period Start
              </label>
              <input
                type="date"
                required
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Period End
              </label>
              <input
                type="date"
                required
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Note (optional)
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
              placeholder="Context about this measurement..."
            />
          </div>

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + Add Metric
        </button>
      )}

      {/* Retention & Product section */}
      <div>
        <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
          Retention &amp; Product
        </h3>
        <div className="space-y-1.5">
          {dashboard.retention_metrics.map(renderMetricRow)}
        </div>
      </div>

      {/* Economics section */}
      <div>
        <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
          Economics
        </h3>
        <div className="space-y-1.5">
          {dashboard.economics_metrics.map(renderMetricRow)}
        </div>
      </div>

      {/* Computed metrics */}
      {dashboard.computed_metrics.some((c) => c.value !== null) && (
        <div>
          <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
            Computed
          </h3>
          <div className="space-y-1.5">
            {dashboard.computed_metrics
              .filter((c) => c.value !== null)
              .map(renderComputedMetric)}
          </div>
        </div>
      )}

      {/* Kill trigger states */}
      {dashboard.trigger_states.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
            Kill Trigger States
          </h3>
          <div className="space-y-1.5">
            {dashboard.trigger_states.map(renderTrigger)}
          </div>
        </div>
      )}
    </div>
  );
}
