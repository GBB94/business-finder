"use client";

import type { Evidence, GateStatus } from "@/lib/types";

const GATE_CRITERIA: Record<
  string,
  { label: string; gate: string; criteria: { key: string; description: string; evidenceTypes: string[] }[] }
> = {
  gate_1: {
    label: "Gate 1 — Problem Worth Solving",
    gate: "1",
    criteria: [
      {
        key: "community_pain",
        description: "Community signals showing people actively describe this pain",
        evidenceTypes: ["community_signal"],
      },
      {
        key: "conversations",
        description: "Customer conversations confirming the problem exists",
        evidenceTypes: ["customer_conversation"],
      },
      {
        key: "competitor_exists",
        description: "Competitors or workarounds exist (people already spend time/money)",
        evidenceTypes: ["competitor_datapoint"],
      },
    ],
  },
  gate_2: {
    label: "Gate 2 — Solution People Pay For",
    gate: "2",
    criteria: [
      {
        key: "presales",
        description: "Pre-sale commitments or landing page conversions",
        evidenceTypes: ["pre_sale", "landing_page_metric"],
      },
      {
        key: "pricing_signal",
        description: "Evidence of willingness to pay at target price point",
        evidenceTypes: ["pre_sale", "customer_conversation"],
      },
      {
        key: "keyword_demand",
        description: "Keyword/search data showing demand",
        evidenceTypes: ["keyword_data"],
      },
    ],
  },
  gate_3: {
    label: "Gate 3 — Repeatable Growth",
    gate: "3",
    criteria: [
      {
        key: "retention",
        description: "Retention metrics meeting benchmarks",
        evidenceTypes: ["retention_metric"],
      },
      {
        key: "economics",
        description: "Unit economics are positive (LTV > CAC)",
        evidenceTypes: ["financial_metric"],
      },
      {
        key: "distribution",
        description: "Repeatable distribution channel validated",
        evidenceTypes: ["outreach_metric", "landing_page_metric"],
      },
    ],
  },
};

function getTrafficLight(
  matchingEvidence: Evidence[],
): { color: string; label: string } {
  if (matchingEvidence.length >= 2) return { color: "bg-green-500", label: "Strong" };
  if (matchingEvidence.length === 1) return { color: "bg-yellow-500", label: "Partial" };
  return { color: "bg-gray-600", label: "No evidence" };
}

function gateStatusBadge(status: GateStatus): { bg: string; label: string } {
  switch (status) {
    case "passed":
      return { bg: "bg-green-900/40 text-green-400", label: "Passed" };
    case "in_progress":
      return { bg: "bg-yellow-900/40 text-yellow-400", label: "In Progress" };
    case "failed":
      return { bg: "bg-red-900/40 text-red-400", label: "Failed" };
    default:
      return { bg: "bg-gray-800 text-gray-600", label: "Not Started" };
  }
}

interface GateSummaryProps {
  evidence: Evidence[];
  gateStatuses: {
    gate_1_status: GateStatus;
    gate_2_status: GateStatus;
    gate_3_status: GateStatus;
  };
}

export default function GateSummary({ evidence, gateStatuses }: GateSummaryProps) {
  return (
    <div className="space-y-4">
      {Object.entries(GATE_CRITERIA).map(([key, gate]) => {
        const statusKey = `${key}_status` as keyof typeof gateStatuses;
        const gateStatus = gateStatuses[statusKey];
        const badge = gateStatusBadge(gateStatus);

        return (
          <div
            key={key}
            className="rounded-lg border border-gray-800 bg-gray-900 p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-semibold uppercase text-gray-400">
                {gate.label}
              </h4>
              <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${badge.bg}`}>
                {badge.label}
              </span>
            </div>
            <div className="space-y-2">
              {gate.criteria.map((criterion) => {
                const matching = evidence.filter(
                  (ev) =>
                    criterion.evidenceTypes.includes(ev.evidence_type) &&
                    (ev.gate === gate.gate || ev.gate === "discovery" || ev.gate === "scoring")
                );
                const light = getTrafficLight(matching);

                return (
                  <div
                    key={criterion.key}
                    className="flex items-center gap-3 rounded border border-gray-800/50 bg-gray-950 px-3 py-2"
                  >
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${light.color}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-300">{criterion.description}</p>
                    </div>
                    <span className="text-[10px] text-gray-600">
                      {matching.length} item{matching.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
