"use client";

import { useState, useEffect } from "react";
import type { DimensionScore, WeightsResponse, SynthesisResponse, ConsistencyResponse, ScoreHistoryEntry } from "@/lib/types";
import { apiFetch } from "@/lib/api";

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
  targetPricePoint?: number | null;
  onSave: (dimensions: { dimension: string; score: number; note?: string }[]) => void;
}

export default function ScoreCard({ ideaId, score, weights, targetPricePoint, onSave }: ScoreCardProps) {
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
  const [synthesizing, setSynthesizing] = useState<string | null>(null);
  const [syntheses, setSyntheses] = useState<Record<string, SynthesisResponse>>({});
  const [synthErrors, setSynthErrors] = useState<Record<string, string>>({});
  const [checking, setChecking] = useState(false);
  const [consistency, setConsistency] = useState<ConsistencyResponse | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<ScoreHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [valueTestAnswer, setValueTestAnswer] = useState("");
  const [valueTestDismissed, setValueTestDismissed] = useState(false);
  const [showPrompts, setShowPrompts] = useState<Record<string, boolean>>({});

  const handleSynthesize = async (dimension: string) => {
    setSynthesizing(dimension);
    setSynthErrors((prev) => {
      const next = { ...prev };
      delete next[dimension];
      return next;
    });
    try {
      const result = await apiFetch<SynthesisResponse>(
        `/api/ideas/${ideaId}/scores/synthesize`,
        {
          method: "POST",
          body: JSON.stringify({ dimension }),
        }
      );
      setSyntheses((prev) => ({ ...prev, [dimension]: result }));
    } catch (err) {
      setSynthErrors((prev) => ({
        ...prev,
        [dimension]: err instanceof Error ? err.message : "Synthesis failed",
      }));
    } finally {
      setSynthesizing(null);
    }
  };

  const handleCheckConsistency = async () => {
    const autoDims = new Set(
      score?.filter((s) => s.auto_computed).map((s) => s.dimension) ?? []
    );
    const draftDimensions = allDims
      .filter((d) => values[d] !== null && !autoDims.has(d))
      .map((d) => ({
        dimension: d,
        score: values[d] as number,
        note: notes[d] || undefined,
      }));

    if (draftDimensions.length === 0) {
      setCheckError("Score at least one dimension before checking consistency.");
      return;
    }

    setChecking(true);
    setCheckError(null);
    try {
      const result = await apiFetch<ConsistencyResponse>(
        `/api/ideas/${ideaId}/scores/check-consistency`,
        {
          method: "POST",
          body: JSON.stringify({ dimensions: draftDimensions }),
        }
      );
      setConsistency(result);
    } catch (err) {
      setCheckError(err instanceof Error ? err.message : "Consistency check failed");
    } finally {
      setChecking(false);
    }
  };

  const handleToggleHistory = async () => {
    if (historyOpen) {
      setHistoryOpen(false);
      return;
    }
    setHistoryOpen(true);
    setHistoryLoading(true);
    try {
      const data = await apiFetch<{ items: ScoreHistoryEntry[]; total: number }>(
        `/api/ideas/${ideaId}/scores/history`
      );
      setHistory(data.items);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

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
    const autoDims = new Set(
      score?.filter((s) => s.auto_computed).map((s) => s.dimension) ?? []
    );
    const dims = allDims
      .filter((d) => values[d] !== null && !autoDims.has(d))
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

  const hasAnyScore = allDims.some((d) => values[d] !== null);
  const showValueTest =
    !hasAnyScore && !valueTestDismissed && targetPricePoint && targetPricePoint > 0;
  const threeXValue = targetPricePoint ? targetPricePoint * 3 : 0;

  return (
    <div className="space-y-4">
      {showValueTest && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/20 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400">
              Economic Value Test
            </span>
            <button
              onClick={() => setValueTestDismissed(true)}
              className="text-[10px] text-gray-600 hover:text-gray-400"
            >
              skip
            </button>
          </div>
          <p className="text-sm text-gray-300">
            At your target price of <span className="font-semibold">${targetPricePoint}/mo</span>,
            can you describe how this saves or earns the customer at least{" "}
            <span className="font-semibold">${threeXValue}/mo</span>?
          </p>
          <textarea
            value={valueTestAnswer}
            onChange={(e) => setValueTestAnswer(e.target.value)}
            placeholder="Describe the economic value..."
            className="w-full rounded bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-amber-500"
            rows={3}
          />
          {valueTestAnswer.length > 0 && valueTestAnswer.length < 20 && (
            <p className="text-xs text-amber-400">
              Short answer — this may be a vitamin rather than a painkiller.
            </p>
          )}
          <button
            onClick={() => setValueTestDismissed(true)}
            className="rounded bg-amber-800/50 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-800/70 transition-colors"
          >
            Continue to Scoring
          </button>
        </div>
      )}

      {disqualifiers.length > 0 && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
          Disqualifiers fired: {disqualifiers.map((d) => DIMENSION_LABELS[d]).join(", ")}
        </div>
      )}

      {consistency && (
        <div className="rounded-lg border border-purple-900/40 bg-purple-950/20 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-400">
              Consistency Check
            </span>
            <button
              onClick={() => setConsistency(null)}
              className="text-[10px] text-gray-600 hover:text-gray-400"
            >
              dismiss
            </button>
          </div>
          <p className="text-sm text-gray-300">{consistency.overall_assessment}</p>
          {consistency.inconsistencies.map((inc, i) => (
            <div
              key={i}
              className={`rounded-lg border p-3 ${
                inc.severity === "critical"
                  ? "border-red-800 bg-red-950/30"
                  : "border-yellow-800 bg-yellow-950/30"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                    inc.severity === "critical"
                      ? "bg-red-900/50 text-red-400"
                      : "bg-yellow-900/50 text-yellow-400"
                  }`}
                >
                  {inc.severity}
                </span>
                <span className="text-xs font-medium text-gray-300">
                  {DIMENSION_LABELS[inc.dimension] ?? inc.dimension}
                </span>
              </div>
              <p className="text-xs text-gray-400">{inc.message}</p>
            </div>
          ))}
          {consistency.prompt_used && (
            <>
              <button
                onClick={() =>
                  setShowPrompts((prev) => ({
                    ...prev,
                    _consistency: !prev._consistency,
                  }))
                }
                className="text-[10px] text-gray-600 hover:text-gray-400"
              >
                {showPrompts._consistency ? "hide reasoning data" : "show reasoning data"}
              </button>
              {showPrompts._consistency && (
                <pre className="mt-1 max-h-48 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-600 whitespace-pre-wrap">
                  {consistency.prompt_used}
                </pre>
              )}
            </>
          )}
        </div>
      )}

      {checkError && !checking && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
          {checkError}
        </div>
      )}

      <div className="space-y-1">
        {allDims.map((dim) => {
          const w = weights?.weights.find((x) => x.dimension === dim)?.weight ?? 0;
          const val = values[dim];
          const contrib = val !== null ? ((val / 5) * w).toFixed(1) : "—";

          const dimData = score?.find((s) => s.dimension === dim);
          const isAuto = dimData?.auto_computed ?? false;

          return (
            <div key={dim} className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-200">
                    {DIMENSION_LABELS[dim] ?? dim}
                  </span>
                  {isAuto && (
                    <span className="rounded bg-indigo-900/50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-indigo-400">
                      Auto
                    </span>
                  )}
                  <span className="text-xs text-gray-600">{w}%</span>
                  {!isAuto && (
                    <button
                      onClick={() => handleSynthesize(dim)}
                      disabled={synthesizing === dim}
                      className="rounded bg-purple-900/40 px-1.5 py-0.5 text-[10px] font-medium text-purple-400 hover:bg-purple-900/60 transition-colors disabled:opacity-50"
                    >
                      {synthesizing === dim ? "Synthesizing…" : "Synthesize"}
                    </button>
                  )}
                </div>
                <span className="text-xs text-gray-500">
                  {contrib} pts
                </span>
              </div>

              {isAuto ? (
                <div className="mt-2">
                  <div className="flex gap-2">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <div
                        key={n}
                        className={`h-8 w-8 rounded text-xs font-medium flex items-center justify-center ${
                          val === n
                            ? "bg-indigo-600 text-white"
                            : "bg-gray-800/50 text-gray-600"
                        }`}
                      >
                        {n}
                      </div>
                    ))}
                  </div>
                  {notes[dim] && (
                    <p className="mt-1.5 text-xs text-gray-500">{notes[dim]}</p>
                  )}
                </div>
              ) : (
                <>
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

                  {synthesizing === dim && (
                    <div className="mt-3 flex items-center gap-2 text-xs text-purple-400">
                      <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-purple-500" />
                      Synthesizing evidence…
                    </div>
                  )}

                  {synthErrors[dim] && synthesizing !== dim && (
                    <div className="mt-2 text-xs text-red-400">{synthErrors[dim]}</div>
                  )}

                  {syntheses[dim] && (
                    <div className="mt-3 space-y-2 rounded-lg border border-purple-900/40 bg-purple-950/20 p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-400">
                          AI Synthesis
                        </span>
                        <button
                          onClick={() =>
                            setSyntheses((prev) => {
                              const next = { ...prev };
                              delete next[dim];
                              return next;
                            })
                          }
                          className="text-[10px] text-gray-600 hover:text-gray-400"
                        >
                          dismiss
                        </button>
                      </div>
                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-300">
                        {syntheses[dim].summary}
                      </p>
                      {syntheses[dim].key_findings.length > 0 && (
                        <ul className="list-disc space-y-1 pl-4 text-xs text-gray-300">
                          {syntheses[dim].key_findings.map((f, i) => (
                            <li key={i}>{f}</li>
                          ))}
                        </ul>
                      )}
                      {syntheses[dim].gaps && (
                        <p className="text-xs italic text-gray-500">
                          Gaps: {syntheses[dim].gaps}
                        </p>
                      )}
                      {syntheses[dim].prompt_used && (
                        <>
                          <button
                            onClick={() =>
                              setShowPrompts((prev) => ({
                                ...prev,
                                [dim]: !prev[dim],
                              }))
                            }
                            className="text-[10px] text-gray-600 hover:text-gray-400"
                          >
                            {showPrompts[dim] ? "hide reasoning data" : "show reasoning data"}
                          </button>
                          {showPrompts[dim] && (
                            <pre className="mt-1 max-h-48 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-600 whitespace-pre-wrap">
                              {syntheses[dim].prompt_used}
                            </pre>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
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
        <div className="flex gap-2">
          <button
            onClick={handleToggleHistory}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-400 hover:bg-gray-800 transition-colors"
          >
            {historyOpen ? "Hide History" : "History"}
          </button>
          <button
            onClick={handleCheckConsistency}
            disabled={checking}
            className="rounded-lg border border-purple-700 px-4 py-2 text-sm font-medium text-purple-400 hover:bg-purple-900/30 transition-colors disabled:opacity-50"
          >
            {checking ? "Checking…" : "Check Consistency"}
          </button>
          <button
            onClick={handleSave}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            Save Score
          </button>
        </div>
      </div>

      {historyOpen && (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Score History
          </span>
          {historyLoading ? (
            <p className="text-xs text-gray-500">Loading…</p>
          ) : history.length === 0 ? (
            <p className="text-xs text-gray-600">No score history yet.</p>
          ) : (
            <div className="space-y-2">
              {history.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between rounded border border-gray-800 bg-gray-950 px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-gray-200">
                      {entry.weighted_total?.toFixed(1) ?? "—"}
                    </span>
                    <span className="text-xs text-gray-600">
                      {new Date(entry.snapshot_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  {entry.dimensions_snapshot && (
                    <div className="flex gap-1">
                      {Object.entries(entry.dimensions_snapshot).map(([dim, data]) => (
                        <span
                          key={dim}
                          title={`${DIMENSION_LABELS[dim] ?? dim}: ${data.score}/5`}
                          className="inline-block h-5 w-5 rounded text-[9px] font-medium flex items-center justify-center bg-gray-800 text-gray-400"
                        >
                          {data.score}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
