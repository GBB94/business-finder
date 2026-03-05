"use client";

import type { Idea } from "@/lib/types";

function scoreBadgeColor(score: number | null): string {
  if (score === null) return "bg-gray-700 text-gray-400";
  if (score >= 70) return "bg-green-900/50 text-green-400";
  if (score >= 40) return "bg-yellow-900/50 text-yellow-400";
  return "bg-red-900/50 text-red-400";
}

function gateDot(status: string): string {
  switch (status) {
    case "passed":
      return "bg-green-500";
    case "in_progress":
      return "bg-yellow-500";
    case "failed":
      return "bg-red-500";
    default:
      return "bg-gray-600";
  }
}

interface IdeaCardProps {
  idea: Idea;
  onClick: (idea: Idea) => void;
}

export default function IdeaCard({ idea, onClick }: IdeaCardProps) {
  const hasDisqualifier =
    idea.kill_triggers &&
    Object.values(idea.kill_triggers).some(
      (t) => typeof t === "object" && t !== null && (t as Record<string, unknown>).fired
    );

  return (
    <button
      onClick={() => onClick(idea)}
      className={`w-full text-left rounded-lg border p-3 transition-colors hover:border-gray-600 ${
        hasDisqualifier ? "border-red-800" : "border-gray-800"
      } bg-gray-900`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-100 truncate">
          {idea.name}
        </h3>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${scoreBadgeColor(
            idea.weighted_total
          )}`}
        >
          {idea.weighted_total !== null
            ? Math.round(idea.weighted_total)
            : "—"}
        </span>
      </div>

      {idea.one_liner && (
        <p className="mt-1 text-xs text-gray-500 line-clamp-2">
          {idea.one_liner}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <span className={`h-2 w-2 rounded-full ${gateDot(idea.gate_1_status)}`} />
          <span className={`h-2 w-2 rounded-full ${gateDot(idea.gate_2_status)}`} />
          <span className={`h-2 w-2 rounded-full ${gateDot(idea.gate_3_status)}`} />
        </div>
        {idea.days_in_stage !== null && (
          <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
            {idea.days_in_stage}d
          </span>
        )}
      </div>
    </button>
  );
}
