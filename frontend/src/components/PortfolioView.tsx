"use client";

import type { Idea } from "@/lib/types";

function scoreBadgeColor(score: number | null): string {
  if (score === null) return "bg-gray-700 text-gray-400";
  if (score >= 70) return "bg-green-900/50 text-green-400";
  if (score >= 40) return "bg-yellow-900/50 text-yellow-400";
  return "bg-red-900/50 text-red-400";
}

function gateCell(status: string): { bg: string; label: string } {
  switch (status) {
    case "passed":
      return { bg: "bg-green-900/40 text-green-400", label: "Pass" };
    case "in_progress":
      return { bg: "bg-yellow-900/40 text-yellow-400", label: "WIP" };
    case "failed":
      return { bg: "bg-red-900/40 text-red-400", label: "Fail" };
    default:
      return { bg: "bg-gray-800 text-gray-600", label: "—" };
  }
}

interface PortfolioViewProps {
  ideas: Idea[];
  onIdeaClick: (idea: Idea) => void;
}

export default function PortfolioView({ ideas, onIdeaClick }: PortfolioViewProps) {
  const active = ideas.filter(
    (i) => !["killed", "parked"].includes(i.status) && !i.archived_at
  );

  const sorted = [...active].sort((a, b) => {
    const sa = a.weighted_total ?? -1;
    const sb = b.weighted_total ?? -1;
    return sb - sa;
  });

  if (sorted.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-600">
        No active ideas to compare.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            <th className="px-3 py-2">Idea</th>
            <th className="px-3 py-2 text-center">Score</th>
            <th className="px-3 py-2 text-center">Stage</th>
            <th className="px-3 py-2 text-center">G1</th>
            <th className="px-3 py-2 text-center">G2</th>
            <th className="px-3 py-2 text-center">G3</th>
            <th className="px-3 py-2 text-center">Days</th>
            <th className="px-3 py-2 text-center">Triggers</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((idea) => {
            const g1 = gateCell(idea.gate_1_status);
            const g2 = gateCell(idea.gate_2_status);
            const g3 = gateCell(idea.gate_3_status);

            const triggersObj = idea.kill_triggers as Record<
              string,
              { label: string; fired: boolean }
            > | null;
            const firedCount = triggersObj
              ? Object.values(triggersObj).filter((t) => t?.fired).length
              : 0;

            return (
              <tr
                key={idea.id}
                onClick={() => onIdeaClick(idea)}
                className="cursor-pointer border-b border-gray-800/50 hover:bg-gray-900/60 transition-colors"
              >
                <td className="px-3 py-3">
                  <div className="font-medium text-gray-200">{idea.name}</div>
                  {idea.one_liner && (
                    <div className="text-xs text-gray-600 line-clamp-1 mt-0.5">
                      {idea.one_liner}
                    </div>
                  )}
                </td>
                <td className="px-3 py-3 text-center">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${scoreBadgeColor(
                      idea.weighted_total
                    )}`}
                  >
                    {idea.weighted_total !== null
                      ? Math.round(idea.weighted_total)
                      : "—"}
                  </span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span className="rounded bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-400 uppercase">
                    {idea.status}
                  </span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-medium ${g1.bg}`}
                  >
                    {g1.label}
                  </span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-medium ${g2.bg}`}
                  >
                    {g2.label}
                  </span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-medium ${g3.bg}`}
                  >
                    {g3.label}
                  </span>
                </td>
                <td className="px-3 py-3 text-center text-xs text-gray-500">
                  {idea.days_in_stage ?? "—"}
                </td>
                <td className="px-3 py-3 text-center">
                  {firedCount > 0 ? (
                    <span className="rounded bg-red-900/50 px-2 py-0.5 text-[10px] font-semibold text-red-400">
                      {firedCount} fired
                    </span>
                  ) : (
                    <span className="text-xs text-gray-600">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
