"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, createLaunch, getLaunches, getPortfolioMetrics } from "@/lib/api";
import type { LaunchInstance, LaunchListResponse, Idea, IdeaListResponse } from "@/lib/types";
import type { PortfolioItem } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  provisioning: "bg-yellow-900/50 text-yellow-400",
  preview: "bg-blue-900/50 text-blue-400",
  active: "bg-green-900/50 text-green-400",
  paused: "bg-gray-700 text-gray-400",
  killed: "bg-red-900/50 text-red-400",
};

export default function LaunchesPage() {
  const router = useRouter();
  const [launches, setLaunches] = useState<LaunchInstance[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [selectedIdeaId, setSelectedIdeaId] = useState("");
  const [budgetCap, setBudgetCap] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLaunches = async () => {
    try {
      const [launchData, portfolioData] = await Promise.all([
        getLaunches(),
        getPortfolioMetrics(),
      ]);
      setLaunches(launchData.items);
      setPortfolio(portfolioData.items);
    } catch (err) {
      console.error("Failed to fetch launches:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLaunches();
  }, []);

  const openModal = async () => {
    try {
      const data = await apiFetch<IdeaListResponse>("/api/ideas");
      setIdeas(data.items);
      setSelectedIdeaId(data.items[0]?.id ?? "");
      setBudgetCap("");
      setError(null);
      setShowModal(true);
    } catch (err) {
      console.error("Failed to fetch ideas:", err);
    }
  };

  const handleCreate = async () => {
    if (!selectedIdeaId) return;
    setCreating(true);
    setError(null);
    try {
      const budget = budgetCap ? parseFloat(budgetCap) : undefined;
      await createLaunch(selectedIdeaId, budget);
      setShowModal(false);
      fetchLaunches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create launch");
    } finally {
      setCreating(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatCurrency = (amount: number) => {
    return `$${amount.toFixed(2)}`;
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading launches...</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">LaunchPad</h1>
        <button
          onClick={openModal}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          + Launch Idea
        </button>
      </div>

      {/* Portfolio summary */}
      {portfolio.length > 0 && (
        <div className="mb-6 grid grid-cols-4 gap-4">
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <p className="text-[10px] uppercase text-gray-600">Active Projects</p>
            <p className="text-xl font-bold">
              {portfolio.filter((p) => p.status === "active").length}
            </p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <p className="text-[10px] uppercase text-gray-600">Total Revenue</p>
            <p className="text-xl font-bold">
              {formatCurrency(
                portfolio.reduce(
                  (sum, p) => sum + (p.latest_metrics?.revenue_cents ?? 0) / 100,
                  0
                )
              )}
            </p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <p className="text-[10px] uppercase text-gray-600">Total Spend</p>
            <p className="text-xl font-bold">
              {formatCurrency(
                portfolio.reduce((sum, p) => sum + p.total_spend_to_date, 0)
              )}
            </p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <p className="text-[10px] uppercase text-gray-600">Open Support</p>
            <p className="text-xl font-bold">
              {portfolio.reduce((sum, p) => sum + p.support.open_threads, 0)}
              {portfolio.some((p) => p.support.escalated_threads > 0) && (
                <span className="ml-1 text-xs text-orange-400">
                  ({portfolio.reduce((sum, p) => sum + p.support.escalated_threads, 0)} escalated)
                </span>
              )}
            </p>
          </div>
        </div>
      )}

      {launches.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-12 text-center">
          <p className="text-gray-500 mb-4">No launches yet.</p>
          <p className="text-sm text-gray-600">
            Select an idea from your pipeline and launch it to start provisioning.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {launches.map((launch) => {
            const pm = portfolio.find((p) => p.launch_id === launch.id);
            return (
              <button
                key={launch.id}
                onClick={() => router.push(`/launches/${launch.id}`)}
                className="w-full text-left rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-700 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h3 className="font-medium text-gray-200">
                      {launch.idea_name ?? "Unnamed Idea"}
                    </h3>
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${
                        STATUS_COLORS[launch.status] ?? "bg-gray-700 text-gray-400"
                      }`}
                    >
                      {launch.status}
                    </span>
                    {pm && pm.support.escalated_threads > 0 && (
                      <span className="rounded bg-orange-900/50 px-2 py-0.5 text-[10px] font-medium text-orange-400">
                        {pm.support.escalated_threads} escalated
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-600">
                    {formatDate(launch.created_at)}
                  </span>
                </div>

                {pm?.latest_metrics ? (
                  <div className="mt-3 grid grid-cols-6 gap-4 text-xs">
                    <div>
                      <span className="text-gray-600">Users</span>
                      <p className="text-gray-300 font-medium">{pm.latest_metrics.active_users}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Revenue</span>
                      <p className="text-gray-300 font-medium">{formatCurrency(pm.latest_metrics.revenue_cents / 100)}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Spend</span>
                      <p className="text-gray-300 font-medium">{formatCurrency(launch.total_spend_to_date)}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Errors</span>
                      <p className={`font-medium ${pm.latest_metrics.error_count > 0 ? "text-red-400" : "text-gray-300"}`}>
                        {pm.latest_metrics.error_count}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-600">Support</span>
                      <p className="text-gray-300 font-medium">{pm.support.open_threads} open</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Budget</span>
                      <p className="text-gray-300 font-medium">
                        {launch.daily_budget_cap != null
                          ? `${formatCurrency(launch.daily_budget_cap)}/d`
                          : "No cap"}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 flex items-center gap-6 text-xs text-gray-500">
                    <span>Spend: {formatCurrency(launch.total_spend_to_date)}</span>
                    {launch.daily_budget_cap != null && (
                      <span>Budget cap: {formatCurrency(launch.daily_budget_cap)}/day</span>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Launch Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-lg border border-gray-800 bg-gray-900 p-6">
            <h2 className="text-lg font-bold mb-4">Launch an Idea</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Select Idea
                </label>
                <select
                  value={selectedIdeaId}
                  onChange={(e) => setSelectedIdeaId(e.target.value)}
                  className="w-full rounded bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {ideas.map((idea) => (
                    <option key={idea.id} value={idea.id}>
                      {idea.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Daily Budget Cap (optional)
                </label>
                <input
                  type="number"
                  value={budgetCap}
                  onChange={(e) => setBudgetCap(e.target.value)}
                  placeholder="e.g. 25.00"
                  step="0.01"
                  min="0"
                  className="w-full rounded bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {error && (
                <p className="text-sm text-red-400">{error}</p>
              )}

              <div className="flex gap-2 justify-end pt-2">
                <button
                  onClick={() => setShowModal(false)}
                  className="rounded bg-gray-800 px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!selectedIdeaId || creating}
                  className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40 transition-colors"
                >
                  {creating ? "Launching..." : "Launch"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
