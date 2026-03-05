"use client";

import { useState } from "react";
import type { EvidenceType, GateLabel, Sentiment } from "@/lib/types";

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

const SENTIMENTS: Sentiment[] = ["positive", "negative", "neutral", "mixed"];

interface EvidenceFormProps {
  ideaId: string;
  onSubmit: (data: {
    gate: string;
    evidence_type: string;
    title: string;
    source_url?: string;
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
  const [sentiment, setSentiment] = useState<Sentiment>("neutral");
  const [tagsInput, setTagsInput] = useState("");

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
    onSubmit({
      gate,
      evidence_type: evidenceType,
      title: title.trim(),
      source_url: sourceUrl.trim() || undefined,
      sentiment,
      tags: tags.length > 0 ? tags : undefined,
    });
  };

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
