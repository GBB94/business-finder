"use client";

import { useState, useEffect } from "react";
import type { DimensionScore, WeightsResponse } from "@/lib/types";

const DIMENSION_LABELS: Record<string, string> = {
  problem_severity: "Problem Severity",
  market_evidence: "Market Evidence",
  revenue_model: "Revenue Model",
  distribution_feasibility: "Distribution Feasibility",
  purchaser_quality: "Purchaser Quality",
  build_complexity: "Build Complexity",
  founder_market_fit: "Founder-Market Fit",
  time_to_revenue: "Time to Revenue",
  founder_constraints: "Founder Constraints",
  competition_level: "Competition Level",
  defensibility_potential: "Defensibility Potential",
};

interface ScoreCardProps {
  ideaId: string;
  score: DimensionScore[] | null;
  weights: WeightsResponse | null;
  onSave: (dimensions: { dimension: string; score: number; note?: string }[]) => void;
}

export default function ScoreCard({ ideaId, score, weights, onSave }: ScoreCardProps) {
  const allDims = weights?.weights.map((w) => w.dimension) ?? Object.keys(DIMENSION_LABELS);

  const [values, setValues] = useState<Record<string, number | null>>(() => {
    const m: Record<string, number | null> = {};
    for (const dim of allDims) {
      const existing = score?.find((s) => s.dimension === dim);
      m[dim] = existing?.score ?? null;
    }
    return m;
  });

  const [notes, setNotes] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const dim of allDims) {
      const existing = score?.find((s) => s.dimension === dim);
      m[dim] = existing?.note ?? "";
    }
    return m;
  });

  const [expandedNote, setExpandedNote] = useState<string | null>(null);

  // Resync local state when props change (e.g. after async fetch)
  useEffect(() => {
    const newValues: Record<string, number | null> = {};
    const newNotes: Record<string, string> = {};
    for (const dim of allDims) {
      const existing = score?.find((s) => s.dimension === dim);
      newValues[dim] = existing?.score ?? null;
      newNotes[dim] = existing?.note ?? "";
    }
    setValues(newValues);
    setNotes(newNotes);
  }, [score, weights]);

  const handleSave = () => {
    const dims = allDims
      .filter((d) => values[d] !== null)
      .map((d) => ({
        dimension: d,
        score: values[d] as number,
        note: notes[d] || undefined,
      }));
    onSave(dims);
  };

  const totalWeight = weights?.total_weight ?? 100;
  const computedTotal = allDims.reduce((sum, dim) => {
    const val = values[dim];
    const w = weights?.weights.find((x) => x.dimension === dim)?.weight ?? 0;
    if (val !== null && w > 0) return sum + (val / 5) * w;
    return sum;
  }, 0);

  const disqualifiers = allDims.filter((dim) => {
    const val = values[dim];
    return (
      val !== null &&
      val <= 2 &&
      ["problem_severity", "revenue_model", "distribution_feasibility"].includes(dim)
    );
  });

  return (
    <div className="space-y-4">
      {disqualifiers.length > 0 && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
          Disqualifiers fired: {disqualifiers.map((d) => DIMENSION_LABELS[d]).join(", ")}
        </div>
      )}

      <div className="space-y-1">
        {allDims.map((dim) => {
          const w = weights?.weights.find((x) => x.dimension === dim)?.weight ?? 0;
          const val = values[dim];
          const contrib = val !== null ? ((val / 5) * w).toFixed(1) : "—";

          return (
            <div key={dim} className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-200">
                    {DIMENSION_LABELS[dim] ?? dim}
                  </span>
                  <span className="ml-2 text-xs text-gray-600">{w}%</span>
                </div>
                <span className="text-xs text-gray-500">
                  {contrib} pts
                </span>
              </div>

              <div className="mt-2 flex gap-2">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() =>
                      setValues((prev) => ({ ...prev, [dim]: prev[dim] === n ? null : n }))
                    }
                    className={`h-8 w-8 rounded text-xs font-medium transition-colors ${
                      val === n
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                    }`}
                  >
                    {n}
                  </button>
                ))}
                <button
                  onClick={() =>
                    setExpandedNote(expandedNote === dim ? null : dim)
                  }
                  className="ml-auto text-xs text-gray-600 hover:text-gray-400"
                >
                  {expandedNote === dim ? "hide note" : "note"}
                </button>
              </div>

              {expandedNote === dim && (
                <textarea
                  value={notes[dim]}
                  onChange={(e) =>
                    setNotes((prev) => ({ ...prev, [dim]: e.target.value }))
                  }
                  placeholder="Add a note..."
                  className="mt-2 w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
                  rows={2}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-900 p-3">
        <div>
          <span className="text-lg font-bold text-gray-100">
            {computedTotal.toFixed(1)}
          </span>
          <span className="ml-1 text-sm text-gray-500">/ {totalWeight}</span>
        </div>
        <button
          onClick={handleSave}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          Save Score
        </button>
      </div>
    </div>
  );
}
