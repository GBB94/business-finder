"use client";

import { useState } from "react";

interface KillTrigger {
  label: string;
  fired: boolean;
  category?: string;
  state?: string;
  metric_key?: string | null;
  min_sample_size?: number;
  sample_window_days?: number;
  first_breach_at?: string | null;
}

interface KillTriggerEditorProps {
  triggers: Record<string, KillTrigger>;
  onSave: (triggers: Record<string, KillTrigger>) => void;
  editing: boolean;
  onEditToggle: () => void;
}

function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

function stateDotColor(trigger: KillTrigger): string {
  const state = trigger.state;
  if (state === "red" || trigger.fired) return "bg-red-500";
  if (state === "yellow") return "bg-yellow-500";
  return "bg-gray-600";
}

function stateTextColor(trigger: KillTrigger): string {
  const state = trigger.state;
  if (state === "red" || trigger.fired) return "text-red-400";
  if (state === "yellow") return "text-amber-400";
  return "text-gray-400";
}

function stateBorderBg(trigger: KillTrigger): string {
  const state = trigger.state;
  if (state === "red" || trigger.fired) return "border-red-800 bg-red-950/30";
  if (state === "yellow") return "border-amber-800 bg-amber-950/20";
  return "border-gray-800 bg-gray-900";
}

export default function KillTriggerEditor({
  triggers,
  onSave,
  editing,
  onEditToggle,
}: KillTriggerEditorProps) {
  const [draft, setDraft] = useState<Record<string, KillTrigger>>(() => ({
    ...triggers,
  }));

  const entries = Object.entries(editing ? draft : triggers);

  const handleToggleFired = (key: string) => {
    setDraft((prev) => {
      const t = prev[key];
      const newFired = !t.fired;
      return {
        ...prev,
        [key]: {
          ...t,
          fired: newFired,
          state: newFired ? "red" : "grey",
        },
      };
    });
  };

  const handleLabelChange = (key: string, label: string) => {
    setDraft((prev) => ({
      ...prev,
      [key]: { ...prev[key], label },
    }));
  };

  const handleDelete = (key: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleAdd = () => {
    const newKey = `custom_${Date.now()}`;
    setDraft((prev) => ({
      ...prev,
      [newKey]: { label: "", fired: false, category: "soft", state: "grey" },
    }));
  };

  const handleSave = () => {
    // Re-key any custom triggers with proper slugs
    const cleaned: Record<string, KillTrigger> = {};
    for (const [key, trigger] of Object.entries(draft)) {
      if (!trigger.label.trim()) continue;
      const finalKey = key.startsWith("custom_")
        ? slugify(trigger.label) || key
        : key;
      cleaned[finalKey] = trigger;
    }
    onSave(cleaned);
  };

  if (entries.length === 0 && !editing) {
    return (
      <div className="text-sm text-gray-600">
        No kill triggers configured.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, trigger]) => (
        <div
          key={key}
          className={`flex items-center gap-2 rounded-lg border p-2 ${
            editing
              ? trigger.fired
                ? "border-red-800 bg-red-950/30"
                : "border-gray-800 bg-gray-900"
              : stateBorderBg(trigger)
          }`}
        >
          {editing ? (
            <>
              <button
                onClick={() => handleToggleFired(key)}
                className={`shrink-0 h-4 w-4 rounded border ${
                  trigger.fired
                    ? "border-red-500 bg-red-500"
                    : "border-gray-600 bg-gray-800"
                }`}
                title={trigger.fired ? "Unflag trigger" : "Flag as fired"}
              >
                {trigger.fired && (
                  <svg
                    viewBox="0 0 12 12"
                    className="h-full w-full text-white"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M2 6l3 3 5-5" />
                  </svg>
                )}
              </button>
              <input
                value={trigger.label}
                onChange={(e) => handleLabelChange(key, e.target.value)}
                className="flex-1 rounded bg-gray-800 px-2 py-1 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="Trigger description"
              />
              <button
                onClick={() => handleDelete(key)}
                className="text-gray-500 hover:text-red-400 text-xs px-1"
              >
                &times;
              </button>
            </>
          ) : (
            <>
              <span
                className={`shrink-0 h-2.5 w-2.5 rounded-full ${stateDotColor(trigger)}`}
              />
              <span
                className={`flex-1 text-sm ${stateTextColor(trigger)}`}
              >
                {trigger.label}
              </span>
              {trigger.category && (
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                    trigger.category === "hard"
                      ? "bg-red-900/40 text-red-400"
                      : "bg-amber-900/40 text-amber-400"
                  }`}
                >
                  {trigger.category}
                </span>
              )}
              {(trigger.state === "red" || trigger.fired) && (
                <span className="text-[10px] font-medium text-red-400 uppercase">
                  Fired
                </span>
              )}
              {trigger.state === "yellow" && !trigger.fired && (
                <span className="text-[10px] font-medium text-amber-400 uppercase">
                  Warning
                </span>
              )}
            </>
          )}
        </div>
      ))}

      {editing && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleAdd}
            className="text-xs text-indigo-400 hover:text-indigo-300"
          >
            + Add trigger
          </button>
          <div className="flex-1" />
          <button
            onClick={handleSave}
            className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
          >
            Save
          </button>
          <button
            onClick={onEditToggle}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Cancel
          </button>
        </div>
      )}

      {!editing && (
        <button
          onClick={onEditToggle}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Edit triggers
        </button>
      )}
    </div>
  );
}
