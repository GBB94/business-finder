"use client";

import { useState } from "react";

interface QuickAddIdeaProps {
  onAdd: (name: string, oneLiner: string) => void;
}

export default function QuickAddIdea({ onAdd }: QuickAddIdeaProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [oneLiner, setOneLiner] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) return;
    onAdd(name.trim(), oneLiner.trim());
    setName("");
    setOneLiner("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex w-full items-center justify-center rounded-lg border border-dashed border-gray-700 py-2 text-sm text-gray-500 transition-colors hover:border-gray-500 hover:text-gray-300"
      >
        + Add idea
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 p-2 space-y-2">
      <input
        autoFocus
        placeholder="Idea name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
      />
      <input
        placeholder="One-liner (optional)"
        value={oneLiner}
        onChange={(e) => setOneLiner(e.target.value)}
        className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
      />
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
        >
          Add
        </button>
        <button
          onClick={() => setOpen(false)}
          className="rounded px-3 py-1 text-xs text-gray-400 hover:text-gray-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
