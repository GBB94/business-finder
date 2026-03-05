"use client";

import { useState } from "react";
import type { Idea, IdeaStatus } from "@/lib/types";
import IdeaCard from "./IdeaCard";
import QuickAddIdea from "./QuickAddIdea";

interface PipelineColumnProps {
  status: IdeaStatus;
  label: string;
  ideas: Idea[];
  onIdeaClick: (idea: Idea) => void;
  onQuickAdd?: (name: string, oneLiner: string) => void;
  onDrop?: (ideaId: string, fromStatus: string, toStatus: string) => void;
}

export default function PipelineColumn({
  status,
  label,
  ideas,
  onIdeaClick,
  onQuickAdd,
  onDrop,
}: PipelineColumnProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const ideaId = e.dataTransfer.getData("application/ideascope-id");
    const fromStatus = e.dataTransfer.getData("application/ideascope-status");
    if (ideaId && fromStatus && fromStatus !== status && onDrop) {
      onDrop(ideaId, fromStatus, status);
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex w-64 shrink-0 flex-col rounded-lg border bg-gray-900/50 transition-colors ${
        dragOver ? "border-indigo-500" : "border-gray-800"
      }`}
    >
      <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          {label}
        </h2>
        <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
          {ideas.length}
        </span>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-2">
        {status === "discovery" && onQuickAdd && (
          <QuickAddIdea onAdd={onQuickAdd} />
        )}
        {ideas.map((idea) => (
          <IdeaCard key={idea.id} idea={idea} onClick={onIdeaClick} />
        ))}
      </div>
    </div>
  );
}
