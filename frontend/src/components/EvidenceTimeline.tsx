"use client";

import type { Evidence, GateLabel, EvidenceType, Sentiment } from "@/lib/types";

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  community_signal: "Community Signal",
  customer_conversation: "Customer Conversation",
  landing_page_metric: "Landing Page Metric",
  pre_sale: "Pre-Sale",
  competitor_datapoint: "Competitor Datapoint",
  keyword_data: "Keyword Data",
  retention_metric: "Retention Metric",
  financial_metric: "Financial Metric",
  outreach_metric: "Outreach Metric",
  note: "Note",
};

const GATE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All gates" },
  { value: "discovery", label: "Discovery" },
  { value: "scoring", label: "Scoring" },
  { value: "1", label: "Gate 1" },
  { value: "2", label: "Gate 2" },
  { value: "3", label: "Gate 3" },
];

const TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All types" },
  ...Object.entries(EVIDENCE_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l })),
];

function sentimentBadge(sentiment: Sentiment) {
  const colors: Record<Sentiment, string> = {
    positive: "bg-green-900/50 text-green-400",
    negative: "bg-red-900/50 text-red-400",
    neutral: "bg-gray-800 text-gray-400",
    mixed: "bg-yellow-900/50 text-yellow-400",
  };
  return colors[sentiment] ?? colors.neutral;
}

interface EvidenceTimelineProps {
  evidence: Evidence[];
  onAdd: () => void;
  filterGate: string;
  filterType: string;
  onFilterChange: (gate: string, type: string) => void;
}

export default function EvidenceTimeline({
  evidence,
  onAdd,
  filterGate,
  filterType,
  onFilterChange,
}: EvidenceTimelineProps) {
  // Apply client-side filters
  const filtered = evidence.filter((ev) => {
    if (filterGate && ev.gate !== filterGate) return false;
    if (filterType && ev.evidence_type !== filterType) return false;
    return true;
  });

  // Group by date
  const grouped = filtered.reduce<Record<string, Evidence[]>>((acc, ev) => {
    const date = ev.created_at.slice(0, 10);
    if (!acc[date]) acc[date] = [];
    acc[date].push(ev);
    return acc;
  }, {});

  const sortedDates = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <select
          value={filterGate}
          onChange={(e) => onFilterChange(e.target.value, filterType)}
          className="rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 outline-none"
        >
          {GATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={filterType}
          onChange={(e) => onFilterChange(filterGate, e.target.value)}
          className="rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 outline-none"
        >
          {TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={onAdd}
          className="ml-auto rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + Add Evidence
        </button>
      </div>

      {/* Timeline */}
      {sortedDates.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-600">
          No evidence yet. Start collecting signals.
        </p>
      )}
      {sortedDates.map((date) => (
        <div key={date}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
            {date}
          </h3>
          <div className="space-y-2">
            {grouped[date].map((ev) => (
              <div
                key={ev.id}
                className="rounded-lg border border-gray-800 bg-gray-900 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] uppercase text-gray-500">
                      {EVIDENCE_TYPE_LABELS[ev.evidence_type] ?? ev.evidence_type}
                    </span>
                    <h4 className="text-sm font-medium text-gray-200">
                      {ev.title}
                    </h4>
                  </div>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${sentimentBadge(
                      ev.sentiment
                    )}`}
                  >
                    {ev.sentiment}
                  </span>
                </div>
                {ev.source_url && (
                  <a
                    href={ev.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block text-xs text-indigo-400 hover:underline truncate"
                  >
                    {ev.source_type !== "other" ? ev.source_type : "source"}
                  </a>
                )}
                {ev.tags && ev.tags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {ev.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
