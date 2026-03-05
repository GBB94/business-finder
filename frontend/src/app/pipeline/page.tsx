"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { Idea, IdeaListResponse, IdeaStatus } from "@/lib/types";
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

export default function PipelinePage() {
  const router = useRouter();
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);

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
  }, []);

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
      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map((col) => (
          <PipelineColumn
            key={col.status}
            status={col.status}
            label={col.label}
            ideas={ideas.filter((i) => i.status === col.status)}
            onIdeaClick={handleIdeaClick}
            onQuickAdd={col.status === "discovery" ? handleQuickAdd : undefined}
          />
        ))}
      </div>
    </div>
  );
}
