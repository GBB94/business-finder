"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getLaunch,
  updateLaunch,
  getEvents,
  getMetrics,
  getDailyLogs,
  getAuditLog,
  getPendingApprovals,
  getApprovalDetail,
  approveTask,
  rejectTask,
  triggerTask,
  getLaunchTasks,
  getSupportThreads,
  resolveThread,
} from "@/lib/api";
import type {
  LaunchInstance,
  OperationalEvent,
  ProjectMetricsDaily,
  DailyLog,
  AuditLogEntry,
  PendingApproval,
  AgentTask,
  SupportThread,
} from "@/lib/types";

const TABS = ["Overview", "Support", "Events", "Daily Logs", "Approvals", "Audit Log"] as const;
type Tab = (typeof TABS)[number];

const STATUS_COLORS: Record<string, string> = {
  provisioning: "bg-yellow-900/50 text-yellow-400",
  preview: "bg-blue-900/50 text-blue-400",
  active: "bg-green-900/50 text-green-400",
  paused: "bg-gray-700 text-gray-400",
  killed: "bg-red-900/50 text-red-400",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  deploy: "text-green-400",
  deploy_failed: "text-red-400",
  deploy_timeout: "text-yellow-400",
  email_sent: "text-blue-400",
  email_bounced: "text-red-400",
  ad_created: "text-indigo-400",
  ad_paused: "text-yellow-400",
  error: "text-red-400",
  error_spike: "text-red-500",
  metric_update: "text-gray-400",
  service_suspended: "text-red-500",
  support_received: "text-blue-400",
  support_responded: "text-green-400",
  cold_email_drafted: "text-emerald-400",
  social_post_drafted: "text-cyan-400",
  content_generated: "text-pink-400",
  support_escalated: "text-orange-400",
  feature_request_extracted: "text-violet-400",
  email_received: "text-teal-400",
};

export default function LaunchDetailPage() {
  const params = useParams();
  const router = useRouter();
  const launchId = params.id as string;

  const [launch, setLaunch] = useState<LaunchInstance | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [events, setEvents] = useState<OperationalEvent[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventFilter, setEventFilter] = useState("");
  const [metrics, setMetrics] = useState<ProjectMetricsDaily[]>([]);
  const [dailyLogs, setDailyLogs] = useState<DailyLog[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [supportThreads, setSupportThreads] = useState<SupportThread[]>([]);
  const [supportTotal, setSupportTotal] = useState(0);
  const [supportFilter, setSupportFilter] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState<string | null>(null);

  const fetchLaunch = useCallback(async () => {
    try {
      const data = await getLaunch(launchId);
      setLaunch(data);
    } catch (err) {
      console.error("Failed to fetch launch:", err);
    }
  }, [launchId]);

  const fetchEvents = useCallback(async () => {
    try {
      const data = await getEvents(launchId, eventFilter || undefined);
      setEvents(data.items);
      setEventsTotal(data.total);
    } catch (err) {
      console.error("Failed to fetch events:", err);
    }
  }, [launchId, eventFilter]);

  const fetchMetrics = useCallback(async () => {
    try {
      const data = await getMetrics(launchId);
      setMetrics(data.items);
    } catch (err) {
      console.error("Failed to fetch metrics:", err);
    }
  }, [launchId]);

  const fetchDailyLogs = useCallback(async () => {
    try {
      const data = await getDailyLogs(launchId);
      setDailyLogs(data.items);
    } catch (err) {
      console.error("Failed to fetch daily logs:", err);
    }
  }, [launchId]);

  const fetchAuditLog = useCallback(async () => {
    try {
      const data = await getAuditLog(launchId);
      setAuditEntries(data.items);
      setAuditTotal(data.total);
    } catch (err) {
      console.error("Failed to fetch audit log:", err);
    }
  }, [launchId]);

  const fetchApprovals = useCallback(async () => {
    try {
      const data = await getPendingApprovals();
      // Filter to approvals relevant to this launch
      setApprovals(data.items.filter((a) => a.launch_id === launchId));
    } catch (err) {
      console.error("Failed to fetch approvals:", err);
    }
  }, [launchId]);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await getLaunchTasks(launchId);
      setTasks(data.items);
    } catch (err) {
      console.error("Failed to fetch tasks:", err);
    }
  }, [launchId]);

  const fetchSupportThreads = useCallback(async () => {
    try {
      const data = await getSupportThreads(launchId, supportFilter || undefined);
      setSupportThreads(data.items);
      setSupportTotal(data.total);
    } catch (err) {
      console.error("Failed to fetch support threads:", err);
    }
  }, [launchId, supportFilter]);

  useEffect(() => {
    fetchLaunch();
  }, [fetchLaunch]);

  useEffect(() => {
    if (activeTab === "Events") fetchEvents();
    if (activeTab === "Overview") { fetchMetrics(); fetchTasks(); }
    if (activeTab === "Daily Logs") fetchDailyLogs();
    if (activeTab === "Audit Log") fetchAuditLog();
    if (activeTab === "Approvals") fetchApprovals();
    if (activeTab === "Support") fetchSupportThreads();
  }, [activeTab, fetchEvents, fetchMetrics, fetchTasks, fetchDailyLogs, fetchAuditLog, fetchApprovals, fetchSupportThreads]);

  const handleStatusChange = async (newStatus: string) => {
    if (!launch) return;
    const confirmMsg =
      newStatus === "killed"
        ? "Are you sure you want to kill this launch? This is irreversible."
        : newStatus === "paused"
        ? "Pause this launch?"
        : newStatus === "active"
        ? "Resume this launch?"
        : null;
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    setActionLoading(true);
    try {
      const updated = await updateLaunch(launchId, { status: newStatus });
      setLaunch(updated);
    } catch (err) {
      console.error("Status change failed:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleTrigger = async (taskType: string) => {
    if (!window.confirm(`Trigger ${taskType} task?`)) return;
    setTriggerLoading(taskType);
    try {
      await triggerTask(launchId, taskType);
      fetchTasks();
    } catch (err) {
      console.error("Trigger failed:", err);
      window.alert(
        `Trigger failed: ${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setTriggerLoading(null);
    }
  };

  // Approve-once task types: create a standing grant on first approval
  const APPROVE_ONCE_TYPES = new Set(["scaffold", "deploy"]);

  const handleApprove = async (approval: PendingApproval) => {
    // Try to get the token from the detail endpoint (Redis cache fallback)
    let token: string | null = null;
    try {
      const detail = await getApprovalDetail(approval.task_id);
      token = detail.approval_token;
    } catch {
      // Detail fetch failed, will prompt manually
    }

    // If no cached token, prompt for the token from the email
    if (!token) {
      const input = window.prompt(
        "Paste the approval token from your notification email:"
      );
      if (!input) return;
      token = input.trim();
    } else if (!window.confirm("Approve this request?")) {
      return;
    }

    try {
      await approveTask(approval.task_id, token, {
        artifact_id: approval.artifact_id ?? undefined,
        create_grant: APPROVE_ONCE_TYPES.has(approval.task_type),
      });
      fetchApprovals();
    } catch (err) {
      console.error("Approve failed:", err);
      window.alert(`Approval failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleResolveThread = async (threadId: string) => {
    if (!window.confirm("Resolve this support thread?")) return;
    try {
      await resolveThread(launchId, threadId);
      fetchSupportThreads();
    } catch (err) {
      console.error("Resolve failed:", err);
    }
  };

  const handleReject = async (taskId: string) => {
    if (!window.confirm("Reject this approval request?")) return;
    try {
      await rejectTask(taskId);
      fetchApprovals();
    } catch (err) {
      console.error("Reject failed:", err);
    }
  };

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

  const formatDateTime = (dateStr: string) =>
    new Date(dateStr).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  const formatCents = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  if (!launch) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  // Aggregate latest metrics for overview
  const latestMetrics = metrics.length > 0 ? metrics[metrics.length - 1] : null;
  const totalSignups = metrics.reduce((sum, m) => sum + m.signups, 0);
  const totalRevenue = metrics.reduce((sum, m) => sum + m.revenue_cents, 0);
  const totalSpend = metrics.reduce((sum, m) => sum + m.total_spend_cents, 0);
  const totalActivation = metrics.reduce((sum, m) => sum + m.activation_count, 0);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <button
            onClick={() => router.push("/launches")}
            className="mb-2 text-xs text-gray-500 hover:text-gray-300"
          >
            &larr; LaunchPad
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">
              {launch.idea_name ?? "Launch"}
            </h1>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${
                STATUS_COLORS[launch.status] ?? "bg-gray-700 text-gray-400"
              }`}
            >
              {launch.status}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-4 text-xs text-gray-500">
            {launch.preview_url && (
              <a
                href={launch.preview_url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-indigo-400 underline"
              >
                Preview
              </a>
            )}
            {launch.production_url && (
              <a
                href={launch.production_url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-indigo-400 underline"
              >
                Production
              </a>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {launch.status === "active" && (
            <button
              onClick={() => handleStatusChange("paused")}
              disabled={actionLoading}
              className="rounded bg-yellow-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-600 disabled:opacity-40 transition-colors"
            >
              Pause
            </button>
          )}
          {launch.status === "paused" && (
            <button
              onClick={() => handleStatusChange("active")}
              disabled={actionLoading}
              className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-40 transition-colors"
            >
              Resume
            </button>
          )}
          {launch.status !== "killed" && (
            <button
              onClick={() => handleStatusChange("killed")}
              disabled={actionLoading}
              className="rounded bg-red-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-40 transition-colors"
            >
              Kill
            </button>
          )}
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
        <div className="max-w-3xl space-y-6">
          {/* Metrics summary cards */}
          <div className="grid grid-cols-4 gap-4">
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Total Signups</p>
              <p className="text-xl font-bold">{totalSignups}</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Activations</p>
              <p className="text-xl font-bold">{totalActivation}</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Revenue</p>
              <p className="text-xl font-bold">{formatCents(totalRevenue)}</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <p className="text-[10px] uppercase text-gray-600">Total Spend</p>
              <p className="text-xl font-bold">{formatCents(totalSpend)}</p>
            </div>
          </div>

          {/* Latest day snapshot */}
          {latestMetrics && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-3">
                Latest Day ({latestMetrics.date})
              </h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Active Users:</span>{" "}
                  <span className="text-gray-200">{latestMetrics.active_users}</span>
                </div>
                <div>
                  <span className="text-gray-500">Activation Rate:</span>{" "}
                  <span className="text-gray-200">
                    {latestMetrics.activation_rate != null
                      ? `${(latestMetrics.activation_rate * 100).toFixed(1)}%`
                      : "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Errors:</span>{" "}
                  <span className="text-gray-200">{latestMetrics.error_count}</span>
                </div>
                <div>
                  <span className="text-gray-500">Support Tickets:</span>{" "}
                  <span className="text-gray-200">{latestMetrics.support_tickets_received}</span>
                </div>
                <div>
                  <span className="text-gray-500">Uptime:</span>{" "}
                  <span className="text-gray-200">
                    {latestMetrics.uptime_pct != null
                      ? `${latestMetrics.uptime_pct.toFixed(1)}%`
                      : "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">AI Cost:</span>{" "}
                  <span className="text-gray-200">{formatCents(latestMetrics.ai_cost_cents)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Launch details */}
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-2 text-sm">
            <h3 className="text-xs font-semibold uppercase text-gray-500 mb-3">
              Launch Details
            </h3>
            <div className="flex justify-between">
              <span className="text-gray-500">Created</span>
              <span className="text-gray-300">{formatDate(launch.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Daily Budget Cap</span>
              <span className="text-gray-300">
                {launch.daily_budget_cap != null
                  ? `$${launch.daily_budget_cap.toFixed(2)}/day`
                  : "No limit"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Total Spend</span>
              <span className="text-gray-300">${launch.total_spend_to_date.toFixed(2)}</span>
            </div>
            {launch.github_repo_url && (
              <div className="flex justify-between">
                <span className="text-gray-500">Repository</span>
                <a
                  href={launch.github_repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:underline"
                >
                  {launch.github_repo_url}
                </a>
              </div>
            )}
          </div>

          {/* Manual triggers */}
          {launch.status !== "killed" && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-3">
                Manual Triggers
              </h3>
              <div className="flex flex-wrap gap-2">
                {[
                  { type: "scaffold", label: "Scaffold", color: "bg-indigo-700 hover:bg-indigo-600" },
                  { type: "deploy", label: "Deploy to Preview", color: "bg-blue-700 hover:bg-blue-600" },
                  { type: "promote", label: "Promote to Prod", color: "bg-amber-700 hover:bg-amber-600" },
                  { type: "metrics_collection", label: "Collect Metrics", color: "bg-gray-700 hover:bg-gray-600" },
                  { type: "ceo_nightly", label: "Run CEO Eval", color: "bg-purple-700 hover:bg-purple-600" },
                  { type: "send_cold_emails", label: "Draft Cold Emails", color: "bg-emerald-700 hover:bg-emerald-600" },
                  { type: "post_social", label: "Draft Social Post", color: "bg-cyan-700 hover:bg-cyan-600" },
                  { type: "write_content", label: "Generate Content", color: "bg-pink-700 hover:bg-pink-600" },
                  { type: "check_escalations", label: "Check Escalations", color: "bg-orange-700 hover:bg-orange-600" },
                ].map(({ type, label, color }) => (
                  <button
                    key={type}
                    onClick={() => handleTrigger(type)}
                    disabled={triggerLoading !== null}
                    className={`rounded px-3 py-1.5 text-xs font-medium text-white ${color} disabled:opacity-40 transition-colors`}
                  >
                    {triggerLoading === type ? "..." : label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Recent tasks */}
          {tasks.length > 0 && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-3">
                Recent Tasks
              </h3>
              <div className="space-y-2">
                {tasks.slice(0, 10).map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between rounded bg-gray-800/50 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-300">
                        {task.task_type}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                          task.status === "completed"
                            ? "bg-green-900/50 text-green-400"
                            : task.status === "running" || task.status === "claimed"
                            ? "bg-blue-900/50 text-blue-400"
                            : task.status === "failed" || task.status === "dead_letter"
                            ? "bg-red-900/50 text-red-400"
                            : task.status === "queued"
                            ? "bg-yellow-900/50 text-yellow-400"
                            : "bg-gray-700 text-gray-400"
                        }`}
                      >
                        {task.status}
                      </span>
                    </div>
                    <span className="text-gray-600">
                      {formatDateTime(task.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {metrics.length === 0 && (
            <p className="py-8 text-center text-sm text-gray-600">
              No metrics data yet. Metrics appear once the project is active.
            </p>
          )}
        </div>
      )}

      {activeTab === "Support" && (
        <div className="max-w-3xl space-y-4">
          <div className="flex items-center gap-3">
            <select
              value={supportFilter}
              onChange={(e) => setSupportFilter(e.target.value)}
              className="rounded bg-gray-800 px-3 py-1.5 text-xs text-gray-300 outline-none"
            >
              <option value="">All threads</option>
              <option value="open">Open</option>
              <option value="escalated">Escalated</option>
              <option value="waiting_on_customer">Waiting on customer</option>
              <option value="resolved">Resolved</option>
            </select>
            <span className="text-xs text-gray-600">{supportTotal} threads</span>
          </div>

          {supportThreads.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-600">
              No support threads yet. Threads are created when inbound emails arrive.
            </p>
          ) : (
            <div className="space-y-3">
              {supportThreads.map((thread) => (
                <div
                  key={thread.id}
                  className={`rounded-lg border p-4 ${
                    thread.status === "escalated"
                      ? "border-orange-800/50 bg-orange-950/10"
                      : thread.status === "resolved"
                      ? "border-gray-800 bg-gray-900/50"
                      : "border-gray-800 bg-gray-900"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-200">
                        {thread.subject || "No subject"}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                          thread.status === "escalated"
                            ? "bg-orange-900/50 text-orange-400"
                            : thread.status === "open"
                            ? "bg-blue-900/50 text-blue-400"
                            : thread.status === "resolved"
                            ? "bg-green-900/50 text-green-400"
                            : "bg-gray-700 text-gray-400"
                        }`}
                      >
                        {thread.status}
                      </span>
                      {thread.feature_request_extracted && (
                        <span className="rounded bg-violet-900/30 px-1.5 py-0.5 text-[10px] text-violet-400">
                          Feature request
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-gray-600">
                      {formatDateTime(thread.created_at)}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-gray-500 mb-2">
                    <span>{thread.customer_email}</span>
                    <span>{thread.message_count} messages</span>
                    {thread.confidence_score != null && (
                      <span>
                        Confidence:{" "}
                        <span
                          className={
                            thread.confidence_score >= 0.7
                              ? "text-green-400"
                              : thread.confidence_score >= 0.4
                              ? "text-yellow-400"
                              : "text-red-400"
                          }
                        >
                          {(thread.confidence_score * 100).toFixed(0)}%
                        </span>
                      </span>
                    )}
                  </div>

                  {thread.escalation_reason && (
                    <div className="rounded bg-orange-950/20 border border-orange-900/30 p-2 mb-2">
                      <p className="text-xs text-orange-400">{thread.escalation_reason}</p>
                    </div>
                  )}

                  {/* Show last 2 messages */}
                  {thread.messages.length > 0 && (
                    <div className="space-y-1 mt-2">
                      {thread.messages.slice(-2).map((msg, i) => (
                        <div
                          key={i}
                          className={`rounded px-2 py-1.5 text-xs ${
                            msg.direction === "inbound"
                              ? "bg-gray-800 text-gray-400"
                              : "bg-indigo-950/20 text-gray-400"
                          }`}
                        >
                          <span className="text-[10px] font-medium text-gray-600 uppercase">
                            {msg.direction === "inbound" ? "Customer" : "Draft"}
                          </span>
                          <p className="mt-0.5 whitespace-pre-wrap break-all">
                            {msg.body.slice(0, 300)}
                            {msg.body.length > 300 ? "..." : ""}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {thread.status !== "resolved" && (
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() =>
                          handleTrigger("draft_support_response")
                        }
                        disabled={triggerLoading !== null}
                        className="rounded bg-indigo-700 px-3 py-1 text-[11px] font-medium text-white hover:bg-indigo-600 disabled:opacity-40 transition-colors"
                      >
                        Draft Response
                      </button>
                      <button
                        onClick={() => handleResolveThread(thread.id)}
                        className="rounded bg-green-800 px-3 py-1 text-[11px] font-medium text-white hover:bg-green-700 transition-colors"
                      >
                        Resolve
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "Events" && (
        <div className="max-w-3xl space-y-4">
          <div className="flex items-center gap-3">
            <select
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value)}
              className="rounded bg-gray-800 px-3 py-1.5 text-xs text-gray-300 outline-none"
            >
              <option value="">All event types</option>
              {[
                "deploy", "deploy_failed", "deploy_timeout",
                "email_sent", "email_bounced",
                "ad_created", "ad_paused",
                "support_received", "support_responded",
                "error", "error_spike",
                "metric_update", "service_suspended",
                "cold_email_drafted", "social_post_drafted", "content_generated",
                "email_received", "support_escalated", "feature_request_extracted",
              ].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <span className="text-xs text-gray-600">{eventsTotal} events</span>
          </div>

          {events.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-600">
              No events recorded yet.
            </p>
          ) : (
            <div className="relative border-l border-gray-800 pl-6 space-y-4">
              {events.map((event) => (
                <div key={event.id} className="relative">
                  <span className="absolute -left-[9px] h-2.5 w-2.5 rounded-full bg-gray-700" />
                  <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className={`text-xs font-medium ${
                          EVENT_TYPE_COLORS[event.event_type] ?? "text-gray-400"
                        }`}
                      >
                        {event.event_type}
                      </span>
                      <span className="text-[10px] text-gray-600">
                        {formatDateTime(event.created_at)}
                      </span>
                    </div>
                    {event.payload && (
                      <pre className="text-[11px] text-gray-500 mt-1 whitespace-pre-wrap break-all">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    )}
                    {event.promoted_to_evidence && (
                      <span className="mt-1 inline-block rounded bg-indigo-900/30 px-1.5 py-0.5 text-[10px] text-indigo-400">
                        Promoted to evidence
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "Daily Logs" && (
        <div className="max-w-3xl space-y-4">
          {dailyLogs.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-600">
              No daily logs yet. The CEO agent generates these once the project is running.
            </p>
          ) : (
            dailyLogs.map((log) => (
              <div
                key={log.id}
                className="rounded-lg border border-gray-800 bg-gray-900 p-4"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-gray-300">{log.date}</span>
                  {log.ai_cost_today != null && (
                    <span className="text-xs text-gray-600">
                      AI cost: ${log.ai_cost_today.toFixed(2)}
                    </span>
                  )}
                </div>

                {log.ceo_reasoning && (
                  <div className="mb-3">
                    <h4 className="text-[10px] uppercase text-gray-600 font-semibold mb-1">
                      CEO Reasoning
                    </h4>
                    <p className="text-sm text-gray-400 whitespace-pre-wrap">
                      {log.ceo_reasoning}
                    </p>
                  </div>
                )}

                {log.anomalies_flagged && (
                  <div className="mb-3 rounded bg-red-950/20 border border-red-900/30 p-2">
                    <h4 className="text-[10px] uppercase text-red-500 font-semibold mb-1">
                      Anomalies
                    </h4>
                    <p className="text-xs text-red-400">{log.anomalies_flagged}</p>
                  </div>
                )}

                {log.next_day_plan && (
                  <div>
                    <h4 className="text-[10px] uppercase text-gray-600 font-semibold mb-1">
                      Next Day Plan
                    </h4>
                    <p className="text-xs text-gray-500">{log.next_day_plan}</p>
                  </div>
                )}

                {log.tasks_executed && (
                  <div className="mt-2">
                    <h4 className="text-[10px] uppercase text-gray-600 font-semibold mb-1">
                      Tasks Executed
                    </h4>
                    <pre className="text-[11px] text-gray-500 whitespace-pre-wrap break-all">
                      {JSON.stringify(log.tasks_executed, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === "Approvals" && (
        <div className="max-w-3xl space-y-4">
          {approvals.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-600">
              No pending approvals.
            </p>
          ) : (
            approvals.map((approval) => (
              <div
                key={approval.id}
                className="rounded-lg border border-amber-800/50 bg-amber-950/10 p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-medium text-gray-200">
                      {approval.summary}
                    </span>
                    <span className="ml-2 rounded bg-gray-800 px-2 py-0.5 text-[10px] text-gray-500 uppercase">
                      {approval.task_type}
                    </span>
                  </div>
                  <span className="text-[10px] text-gray-600">
                    {formatDateTime(approval.created_at)}
                  </span>
                </div>

                {approval.channel_or_provider && (
                  <p className="text-xs text-gray-500 mb-2">
                    Channel: {approval.channel_or_provider}
                  </p>
                )}

                {approval.details && (
                  <pre className="text-[11px] text-gray-500 mb-3 whitespace-pre-wrap break-all bg-gray-900 rounded p-2">
                    {JSON.stringify(approval.details, null, 2)}
                  </pre>
                )}

                {approval.expires_at && (
                  <p className="text-xs text-gray-600 mb-2">
                    Expires: {formatDateTime(approval.expires_at)}
                  </p>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(approval)}
                    className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 transition-colors"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(approval.task_id)}
                    className="rounded bg-red-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === "Audit Log" && (
        <div className="max-w-3xl space-y-3">
          <span className="text-xs text-gray-600">{auditTotal} entries</span>
          {auditEntries.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-600">
              No audit log entries yet.
            </p>
          ) : (
            <div className="rounded-lg border border-gray-800 bg-gray-900 divide-y divide-gray-800">
              {auditEntries.map((entry) => (
                <div key={entry.id} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 uppercase">
                        {entry.actor}
                      </span>
                      <span className="text-sm text-gray-300">{entry.action}</span>
                      {entry.resource_type && (
                        <span className="text-xs text-gray-600">
                          on {entry.resource_type}
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-gray-600">
                      {formatDateTime(entry.created_at)}
                    </span>
                  </div>
                  {entry.details && (
                    <pre className="text-[11px] text-gray-600 mt-1 whitespace-pre-wrap break-all">
                      {JSON.stringify(entry.details, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
