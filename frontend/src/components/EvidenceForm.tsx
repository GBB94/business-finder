"use client";

import { useState } from "react";
import type { EvidenceType, GateLabel, Sentiment, SourceType } from "@/lib/types";

const EVIDENCE_TYPES: { value: EvidenceType; label: string }[] = [
  { value: "community_signal", label: "Community Signal" },
  { value: "customer_conversation", label: "Customer Conversation" },
  { value: "landing_page_metric", label: "Landing Page" },
  { value: "pre_sale", label: "Pre-Sale" },
  { value: "competitor_datapoint", label: "Competitor" },
  { value: "keyword_data", label: "Keyword Data" },
  { value: "retention_metric", label: "Retention" },
  { value: "financial_metric", label: "Financial" },
  { value: "outreach_metric", label: "Outreach" },
  { value: "note", label: "Note" },
];

const GATES: { value: string; label: string }[] = [
  { value: "discovery", label: "Discovery" },
  { value: "scoring", label: "Scoring" },
  { value: "1", label: "Gate 1" },
  { value: "2", label: "Gate 2" },
  { value: "3", label: "Gate 3" },
];

const SOURCE_TYPES: { value: SourceType; label: string }[] = [
  { value: "reddit", label: "Reddit" },
  { value: "hn", label: "Hacker News" },
  { value: "github", label: "GitHub" },
  { value: "g2_manual", label: "G2 (Manual)" },
  { value: "capterra_manual", label: "Capterra (Manual)" },
  { value: "kw_manual", label: "Keyword (Manual)" },
  { value: "stripe", label: "Stripe" },
  { value: "conversation", label: "Conversation" },
  { value: "note", label: "Note" },
  { value: "other", label: "Other" },
];

const SENTIMENTS: Sentiment[] = ["positive", "negative", "neutral", "mixed"];

// Type-specific content field definitions
const CONTENT_FIELDS: Record<EvidenceType, { key: string; label: string; type: "text" | "textarea" | "number" }[]> = {
  customer_conversation: [
    { key: "what_have_they_tried", label: "What have they tried?", type: "textarea" },
    { key: "what_are_they_paying", label: "What are they paying?", type: "text" },
    { key: "would_they_pay", label: "Would they pay for this?", type: "text" },
  ],
  competitor_datapoint: [
    { key: "competitor_name", label: "Competitor name", type: "text" },
    { key: "pricing_tiers", label: "Pricing tiers", type: "textarea" },
    { key: "strengths", label: "Strengths", type: "textarea" },
    { key: "weaknesses", label: "Weaknesses", type: "textarea" },
    { key: "gaps", label: "Gaps", type: "textarea" },
  ],
  keyword_data: [
    { key: "keyword", label: "Keyword", type: "text" },
    { key: "search_volume", label: "Search volume", type: "number" },
    { key: "cpc", label: "CPC ($)", type: "number" },
    { key: "difficulty", label: "Difficulty", type: "number" },
    { key: "commercial_intent", label: "Commercial intent", type: "text" },
  ],
  landing_page_metric: [
    { key: "metric_name", label: "Metric name", type: "text" },
    { key: "value", label: "Value", type: "text" },
    { key: "time_period", label: "Time period", type: "text" },
  ],
  retention_metric: [
    { key: "metric_name", label: "Metric name", type: "text" },
    { key: "value", label: "Value", type: "text" },
    { key: "benchmark", label: "Benchmark", type: "text" },
  ],
  financial_metric: [
    { key: "metric_name", label: "Metric name", type: "text" },
    { key: "value", label: "Value", type: "text" },
    { key: "benchmark", label: "Benchmark", type: "text" },
  ],
  pre_sale: [
    { key: "amount", label: "Amount ($)", type: "number" },
    { key: "type", label: "Type (LOI / paid pilot / credit card)", type: "text" },
    { key: "date", label: "Date", type: "text" },
  ],
  community_signal: [
    { key: "notes", label: "Notes", type: "textarea" },
  ],
  outreach_metric: [
    { key: "notes", label: "Notes", type: "textarea" },
  ],
  note: [
    { key: "notes", label: "Notes", type: "textarea" },
  ],
};

interface EvidenceFormProps {
  ideaId: string;
  onSubmit: (data: {
    gate: string;
    evidence_type: string;
    title: string;
    source_url?: string;
    source_type?: string;
    sentiment: string;
    tags?: string[];
    content?: Record<string, unknown>;
  }) => void;
  onCancel: () => void;
}

export default function EvidenceForm({ ideaId, onSubmit, onCancel }: EvidenceFormProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [evidenceType, setEvidenceType] = useState<EvidenceType | null>(null);
  const [gate, setGate] = useState("discovery");
  const [title, setTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("other");
  const [sentiment, setSentiment] = useState<Sentiment>("neutral");
  const [tagsInput, setTagsInput] = useState("");
  const [contentFields, setContentFields] = useState<Record<string, string>>({});

  if (step === 1) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-300">
          Select evidence type
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {EVIDENCE_TYPES.map((et) => (
            <button
              key={et.value}
              onClick={() => {
                setEvidenceType(et.value);
                setContentFields({});
                setStep(2);
              }}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 hover:border-indigo-500 hover:text-indigo-400 transition-colors"
            >
              {et.label}
            </button>
          ))}
        </div>
        <button
          onClick={onCancel}
          className="mt-3 text-xs text-gray-500 hover:text-gray-300"
        >
          Cancel
        </button>
      </div>
    );
  }

  const handleSubmit = () => {
    if (!title.trim() || !evidenceType) return;
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    // Build content dict from type-specific fields
    const content: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(contentFields)) {
      if (val.trim()) {
        // Try to parse numbers for number fields
        const fieldDef = CONTENT_FIELDS[evidenceType]?.find((f) => f.key === key);
        if (fieldDef?.type === "number") {
          const num = parseFloat(val);
          content[key] = isNaN(num) ? val : num;
        } else {
          content[key] = val.trim();
        }
      }
    }

    onSubmit({
      gate,
      evidence_type: evidenceType,
      title: title.trim(),
      source_url: sourceUrl.trim() || undefined,
      source_type: sourceType,
      sentiment,
      tags: tags.length > 0 ? tags : undefined,
      content: Object.keys(content).length > 0 ? content : undefined,
    });
  };

  const fields = evidenceType ? CONTENT_FIELDS[evidenceType] ?? [] : [];

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">
          {EVIDENCE_TYPES.find((e) => e.value === evidenceType)?.label}
        </h3>
        <button
          onClick={() => setStep(1)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Change type
        </button>
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">Gate</label>
        <select
          value={gate}
          onChange={(e) => setGate(e.target.value)}
          className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 outline-none"
        >
          {GATES.map((g) => (
            <option key={g.value} value={g.value}>
              {g.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">Title</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="What did you observe?"
        />
      </div>

      {/* Type-specific content fields */}
      {fields.length > 0 && (
        <div className="space-y-2 rounded border border-gray-800 bg-gray-800/30 p-3">
          <p className="text-[10px] uppercase text-gray-600 font-semibold">Details</p>
          {fields.map((field) => (
            <div key={field.key}>
              <label className="mb-0.5 block text-xs text-gray-500">
                {field.label}
              </label>
              {field.type === "textarea" ? (
                <textarea
                  value={contentFields[field.key] ?? ""}
                  onChange={(e) =>
                    setContentFields((prev) => ({
                      ...prev,
                      [field.key]: e.target.value,
                    }))
                  }
                  rows={2}
                  className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
                />
              ) : (
                <input
                  type={field.type === "number" ? "number" : "text"}
                  value={contentFields[field.key] ?? ""}
                  onChange={(e) =>
                    setContentFields((prev) => ({
                      ...prev,
                      [field.key]: e.target.value,
                    }))
                  }
                  className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
                />
              )}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs text-gray-500">Source URL</label>
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="https://..."
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">Source Type</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as SourceType)}
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 outline-none"
          >
            {SOURCE_TYPES.map((st) => (
              <option key={st.value} value={st.value}>
                {st.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">Sentiment</label>
        <div className="flex gap-2">
          {SENTIMENTS.map((s) => (
            <button
              key={s}
              onClick={() => setSentiment(s)}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                sentiment === s
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs text-gray-500">
          Tags (comma-separated)
        </label>
        <input
          value={tagsInput}
          onChange={(e) => setTagsInput(e.target.value)}
          className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="pain-point, competitor, pricing"
        />
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleSubmit}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Save Evidence
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
