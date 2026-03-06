"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { Idea, IdeaListResponse, IdeaStatus, FounderProfile } from "@/lib/types";
import PipelineColumn from "@/components/PipelineColumn";

const COLUMNS: { status: IdeaStatus; label: string }[] = [
  { status: "discovery", label: "Discovery" },
  { status: "scoring", label: "Scoring" },
  { status: "validating", label: "Validating" },
  { status: "building", label: "Building" },
  { status: "retention", label: "Retention" },
  { status: "growing", label: "Growing" },
  { status: "killed", label: "Killed" },
  { status: "parked", label: "Parked" },
];

// Forward-only transitions (backward moves require confirmation)
const FORWARD_TRANSITIONS: Record<string, string[]> = {
  discovery: ["scoring", "killed", "parked"],
  scoring: ["validating", "killed", "parked"],
  validating: ["building", "killed", "parked"],
  building: ["retention", "killed", "parked"],
  retention: ["growing", "killed", "parked"],
  growing: ["killed", "parked"],
  killed: ["discovery"],
  parked: ["discovery"],
};

const STAGE_ORDER = ["discovery", "scoring", "validating", "building", "retention", "growing"];

function isBackwardMove(from: string, to: string): boolean {
  const fromIdx = STAGE_ORDER.indexOf(from);
  const toIdx = STAGE_ORDER.indexOf(to);
  if (fromIdx === -1 || toIdx === -1) return false;
  return toIdx < fromIdx;
}

export default function PipelinePage() {
  const router = useRouter();
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [dropError, setDropError] = useState<string | null>(null);
  const [profile, setProfile] = useState<FounderProfile | null>(null);

  const fetchIdeas = async () => {
    try {
      const data = await apiFetch<IdeaListResponse>("/api/ideas");
      setIdeas(data.items);
    } catch (err) {
      console.error("Failed to fetch ideas:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIdeas();
    apiFetch<FounderProfile>("/api/profile")
      .then(setProfile)
      .catch((err) => console.error("Failed to load profile:", err));
  }, []);

  // Auto-clear error after 4 seconds
  useEffect(() => {
    if (dropError) {
      const timer = setTimeout(() => setDropError(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [dropError]);

  const handleQuickAdd = async (name: string, oneLiner: string) => {
    try {
      await apiFetch<Idea>("/api/ideas", {
        method: "POST",
        body: JSON.stringify({ name, one_liner: oneLiner }),
      });
      fetchIdeas();
    } catch (err) {
      console.error("Failed to create idea:", err);
    }
  };

  const handleIdeaClick = (idea: Idea) => {
    router.push(`/ideas/${idea.id}`);
  };

  const handleDrop = async (ideaId: string, fromStatus: string, toStatus: string) => {
    // Backward move confirmation
    if (isBackwardMove(fromStatus, toStatus)) {
      const confirmed = window.confirm(
        `Move idea backward from "${fromStatus}" to "${toStatus}"? This is unusual.`
      );
      if (!confirmed) return;
    }

    try {
      await apiFetch<Idea>(`/api/ideas/${ideaId}/transition`, {
        method: "POST",
        body: JSON.stringify({ new_status: toStatus }),
      });
      setDropError(null);
      fetchIdeas();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Transition failed";
      setDropError(message);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading pipeline...</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="mb-6 text-2xl font-bold">Pipeline</h1>
      {profile?.runway_months_remaining != null &&
        profile.runway_months_remaining <= profile.runway_floor_months && (
          <div className="mb-4 rounded-lg border border-red-800 bg-red-950/30 px-4 py-2 text-sm text-red-400">
            <span className="font-semibold">Runway critical ({profile.runway_months_remaining} months).</span>{" "}
            Stop all discretionary spending and reassess.
          </div>
        )}
      {profile?.runway_months_remaining != null &&
        profile.runway_months_remaining > profile.runway_floor_months &&
        profile.runway_months_remaining <= 6 && (
          <div className="mb-4 rounded-lg border border-yellow-800 bg-yellow-950/30 px-4 py-2 text-sm text-yellow-400">
            <span className="font-semibold">Runway low ({profile.runway_months_remaining} months).</span>{" "}
            Framework recommends biasing toward offer-ladder or marketplace-distributed products.
          </div>
        )}
      {dropError && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950/50 px-4 py-2 text-sm text-red-400">
          {dropError}
        </div>
      )}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map((col) => (
          <PipelineColumn
            key={col.status}
            status={col.status}
            label={col.label}
            ideas={ideas.filter((i) => i.status === col.status)}
            onIdeaClick={handleIdeaClick}
            onQuickAdd={col.status === "discovery" ? handleQuickAdd : undefined}
            onDrop={handleDrop}
          />
        ))}
      </div>
    </div>
  );
}
