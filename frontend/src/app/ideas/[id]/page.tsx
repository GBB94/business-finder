"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type {
  Idea,
  ScoreResponse,
  Evidence,
  EvidenceListResponse,
  MonthlyReview,
  MonthlyReviewListResponse,
  WeightsResponse,
  GateStatus,
} from "@/lib/types";
import ScoreCard from "@/components/ScoreCard";
import EvidenceTimeline from "@/components/EvidenceTimeline";
import EvidenceForm from "@/components/EvidenceForm";
import MonthlyReviewForm from "@/components/MonthlyReviewForm";
import KillTriggerEditor from "@/components/KillTriggerEditor";
import MetricsPanel from "@/components/MetricsPanel";

const TABS = ["Overview", "Score", "Evidence", "Metrics", "Reviews"] as const;
type Tab = (typeof TABS)[number];

const STATUS_TRANSITIONS: Record<string, { label: string; target: string }[]> = {
  discovery: [
    { label: "Move to Scoring", target: "scoring" },
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  scoring: [
    { label: "Move to Validating", target: "validating" },
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  validating: [
    { label: "Move to Building", target: "building" },
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  building: [
    { label: "Move to Retention", target: "retention" },
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  retention: [
    { label: "Move to Growing", target: "growing" },
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  growing: [
    { label: "Park", target: "parked" },
    { label: "Kill", target: "killed" },
  ],
  killed: [{ label: "Resurrect", target: "discovery" }],
  parked: [{ label: "Resurrect", target: "discovery" }],
};

const GATE_STATUSES: { value: GateStatus; label: string; color: string }[] = [
  { value: "not_started", label: "Not Started", color: "bg-gray-700 text-gray-400" },
  { value: "in_progress", label: "In Progress", color: "bg-yellow-600 text-white" },
  { value: "passed", label: "Passed", color: "bg-green-600 text-white" },
  { value: "failed", label: "Failed", color: "bg-red-600 text-white" },
];

const GATES = [
  { field: "gate_1_status" as const, label: "Gate 1 — Problem Worth Solving" },
  { field: "gate_2_status" as const, label: "Gate 2 — Solution People Pay For" },
  { field: "gate_3_status" as const, label: "Gate 3 — Repeatable Growth" },
];

export default function IdeaDetailPage() {
  const params = useParams();
  const router = useRouter();
  const ideaId = params.id as string;

  const [idea, setIdea] = useState<Idea | null>(null);
  const [score, setScore] = useState<ScoreResponse | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [reviews, setReviews] = useState<MonthlyReview[]>([]);
  const [weights, setWeights] = useState<WeightsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [showEvidenceForm, setShowEvidenceForm] = useState(false);
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [editingTriggers, setEditingTriggers] = useState(false);
  const [filterGate, setFilterGate] = useState("");
  const [filterType, setFilterType] = useState("");

  const fetchAll = useCallback(async () => {
    try {
      const [ideaData, scoreData, evidenceData, reviewsData, weightsData] =
        await Promise.all([
          apiFetch<Idea>(`/api/ideas/${ideaId}`),
          apiFetch<ScoreResponse | null>(`/api/ideas/${ideaId}/scores`),
          apiFetch<EvidenceListResponse>(`/api/ideas/${ideaId}/evidence`),
          apiFetch<MonthlyReviewListResponse>(`/api/ideas/${ideaId}/reviews`),
          apiFetch<WeightsResponse>(`/api/scoring-weights`),
        ]);
      setIdea(ideaData);
      setScore(scoreData);
      setEvidence(evidenceData.items);
      setReviews(reviewsData.items);
      setWeights(weightsData);
    } catch (err) {
      console.error("Failed to fetch idea data:", err);
    }
  }, [ideaId]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleTransition = async (target: string) => {
    try {
      const updated = await apiFetch<Idea>(`/api/ideas/${ideaId}/transition`, {
        method: "POST",
        body: JSON.stringify({ new_status: target }),
      });
      setIdea(updated);
    } catch (err) {
      console.error("Transition failed:", err);
    }
  };

  const handleArchive = async () => {
    if (!idea) return;
    const endpoint = idea.archived_at
      ? `/api/ideas/${ideaId}/unarchive`
      : `/api/ideas/${ideaId}/archive`;
    try {
      const updated = await apiFetch<Idea>(endpoint, { method: "POST" });
      setIdea(updated);
    } catch (err) {
      console.error("Archive toggle failed:", err);
    }
  };

  const handleScoreSave = async (
    dimensions: { dimension: string; score: number; note?: string }[]
  ) => {
    try {
      const method = score ? "PATCH" : "POST";
      const updated = await apiFetch<ScoreResponse>(
        `/api/ideas/${ideaId}/scores`,
        {
          method,
          body: JSON.stringify({ dimensions }),
        }
      );
      setScore(updated);
      fetchAll();
    } catch (err) {
      console.error("Score save failed:", err);
    }
  };

  const handleEvidenceSubmit = async (data: Record<string, unknown>) => {
    try {
      await apiFetch(`/api/ideas/${ideaId}/evidence`, {
        method: "POST",
        body: JSON.stringify(data),
      });
      setShowEvidenceForm(false);
      const updated = await apiFetch<EvidenceListResponse>(
        `/api/ideas/${ideaId}/evidence`
      );
      setEvidence(updated.items);
    } catch (err) {
      console.error("Evidence submit failed:", err);
    }
  };

  const handleReviewSubmit = async (data: Record<string, unknown>) => {
    try {
      await apiFetch(`/api/ideas/${ideaId}/reviews`, {
        method: "POST",
        body: JSON.stringify(data),
      });
      setShowReviewForm(false);
      const [ideaData, reviewsData] = await Promise.all([
        apiFetch<Idea>(`/api/ideas/${ideaId}`),
        apiFetch<MonthlyReviewListResponse>(`/api/ideas/${ideaId}/reviews`),
      ]);
      setIdea(ideaData);
      setReviews(reviewsData.items);
    } catch (err) {
      console.error("Review submit failed:", err);
    }
  };

  const handleGateChange = async (
    field: "gate_1_status" | "gate_2_status" | "gate_3_status",
    value: GateStatus
  ) => {
    try {
      const updated = await apiFetch<Idea>(`/api/ideas/${ideaId}`, {
        method: "PUT",
        body: JSON.stringify({ [field]: value }),
      });
      setIdea(updated);
    } catch (err) {
      console.error("Gate update failed:", err);
    }
  };

  const handleTriggersSave = async (
    triggers: Record<string, { label: string; fired: boolean }>
  ) => {
    try {
      const updated = await apiFetch<Idea>(`/api/ideas/${ideaId}`, {
        method: "PUT",
        body: JSON.stringify({ kill_triggers: triggers }),
      });
      setIdea(updated);
      setEditingTriggers(false);
    } catch (err) {
      console.error("Trigger save failed:", err);
    }
  };

  if (!idea) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  const transitions = STATUS_TRANSITIONS[idea.status] ?? [];

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <button
            onClick={() => router.push("/pipeline")}
            className="mb-2 text-xs text-gray-500 hover:text-gray-300"
          >
            &larr; Pipeline
          </button>
          <h1 className="text-2xl font-bold">{idea.name}</h1>
          {idea.one_liner && (
            <p className="mt-1 text-sm text-gray-400">{idea.one_liner}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-gray-800 px-2 py-1 text-xs font-medium text-gray-400 uppercase">
            {idea.status}
          </span>
          {transitions.length > 0 && (
            <select
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) handleTransition(e.target.value);
                e.target.value = "";
              }}
              className="rounded bg-gray-800 px-2 py-1 text-xs text-gray-300 outline-none"
            >
              <option value="" disabled>
                Transition...
              </option>
              {transitions.map((t) => (
                <option key={t.target} value={t.target}>
                  {t.label}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={handleArchive}
            className="rounded bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-gray-200"
          >
            {idea.archived_at ? "Unarchive" : "Archive"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "Overview" && (
        <div className="max-w-2xl space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Score</p>
              <p className="text-xl font-bold">
                {idea.weighted_total !== null
                  ? Math.round(idea.weighted_total)
                  : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">
                Days in Stage
              </p>
              <p className="text-xl font-bold">{idea.days_in_stage ?? "—"}</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Evidence</p>
              <p className="text-xl font-bold">{evidence.length}</p>
            </div>
          </div>

          {idea.audience && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">
                Audience
              </h3>
              <p className="text-sm text-gray-300">{idea.audience}</p>
            </div>
          )}
          {idea.problem_statement && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">
                Problem
              </h3>
              <p className="text-sm text-gray-300">{idea.problem_statement}</p>
            </div>
          )}
          {idea.proposed_solution && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">
                Solution
              </h3>
              <p className="text-sm text-gray-300">{idea.proposed_solution}</p>
            </div>
          )}

          {/* Gates Section */}
          <div>
            <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
              Gates
            </h3>
            <div className="space-y-2">
              {GATES.map((gate) => (
                <div
                  key={gate.field}
                  className="rounded-lg border border-gray-800 bg-gray-900 p-3"
                >
                  <p className="text-xs text-gray-400 mb-2">{gate.label}</p>
                  <div className="flex gap-1.5">
                    {GATE_STATUSES.map((gs) => (
                      <button
                        key={gs.value}
                        onClick={() => handleGateChange(gate.field, gs.value)}
                        className={`rounded px-2 py-1 text-[10px] font-medium transition-colors ${
                          idea[gate.field] === gs.value
                            ? gs.color
                            : "bg-gray-800 text-gray-500 hover:bg-gray-700"
                        }`}
                      >
                        {gs.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Kill Triggers Section */}
          {idea.kill_triggers && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
                Kill Triggers
              </h3>
              <KillTriggerEditor
                triggers={
                  idea.kill_triggers as Record<
                    string,
                    { label: string; fired: boolean }
                  >
                }
                onSave={handleTriggersSave}
                editing={editingTriggers}
                onEditToggle={() => setEditingTriggers(!editingTriggers)}
              />
            </div>
          )}
        </div>
      )}

      {activeTab === "Score" && (
        <div className="max-w-2xl">
          <ScoreCard
            ideaId={ideaId}
            score={score?.dimensions ?? null}
            weights={weights}
            onSave={handleScoreSave}
          />
        </div>
      )}

      {activeTab === "Evidence" && (
        <div className="max-w-2xl">
          {showEvidenceForm ? (
            <EvidenceForm
              ideaId={ideaId}
              onSubmit={handleEvidenceSubmit}
              onCancel={() => setShowEvidenceForm(false)}
            />
          ) : (
            <EvidenceTimeline
              evidence={evidence}
              onAdd={() => setShowEvidenceForm(true)}
              filterGate={filterGate}
              filterType={filterType}
              onFilterChange={(g, t) => {
                setFilterGate(g);
                setFilterType(t);
              }}
            />
          )}
        </div>
      )}

      {activeTab === "Metrics" && (
        <MetricsPanel ideaId={ideaId} />
      )}

      {activeTab === "Reviews" && (
        <div className="max-w-2xl space-y-4">
          {showReviewForm ? (
            <MonthlyReviewForm
              ideaId={ideaId}
              onSubmit={handleReviewSubmit}
              onCancel={() => setShowReviewForm(false)}
            />
          ) : (
            <>
              <button
                onClick={() => setShowReviewForm(true)}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
              >
                + New Review
              </button>
              {reviews.length === 0 && (
                <p className="py-8 text-center text-sm text-gray-600">
                  No reviews yet.
                </p>
              )}
              {reviews.map((review) => (
                <div
                  key={review.id}
                  className="rounded-lg border border-gray-800 bg-gray-900 p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-300">
                      {review.review_date}
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        review.decision === "continue"
                          ? "bg-green-900/50 text-green-400"
                          : review.decision === "kill"
                          ? "bg-red-900/50 text-red-400"
                          : review.decision === "park"
                          ? "bg-yellow-900/50 text-yellow-400"
                          : "bg-blue-900/50 text-blue-400"
                      }`}
                    >
                      {review.decision}
                    </span>
                  </div>
                  {review.reasoning && (
                    <p className="text-sm text-gray-400">{review.reasoning}</p>
                  )}
                  {review.next_hypothesis && (
                    <p className="mt-2 text-xs text-gray-600">
                      Next: {review.next_hypothesis}
                    </p>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
