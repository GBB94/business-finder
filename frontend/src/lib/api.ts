const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  // Attach CSRF token for state-changing requests
  const method = (options?.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrf = getCsrfToken();
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
  }

  const { headers: _discarded, ...restOptions } = options ?? {};
  const res = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...restOptions,
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // response wasn't JSON, fall back to statusText
    }
    throw new Error(`API error: ${res.status} — ${detail}`);
  }

  return res.json();
}

// ── Launch API ─────────────────────────────────────────────────────────────

import type {
  LaunchInstance,
  LaunchListResponse,
  OperationalEventListResponse,
  ProjectMetricsDailyListResponse,
  DailyLogListResponse,
  AuditLogListResponse,
  PendingApproval,
  PendingApprovalListResponse,
  ApprovalGrantListResponse,
} from "./types";

export function createLaunch(
  ideaId: string,
  dailyBudgetCap?: number
): Promise<LaunchInstance> {
  return apiFetch<LaunchInstance>("/api/launches", {
    method: "POST",
    body: JSON.stringify({
      idea_id: ideaId,
      daily_budget_cap: dailyBudgetCap ?? null,
    }),
  });
}

export function getLaunches(status?: string): Promise<LaunchListResponse> {
  const qs = status ? `?status=${status}` : "";
  return apiFetch<LaunchListResponse>(`/api/launches${qs}`);
}

export function getLaunch(launchId: string): Promise<LaunchInstance> {
  return apiFetch<LaunchInstance>(`/api/launches/${launchId}`);
}

export function updateLaunch(
  launchId: string,
  body: { status?: string; daily_budget_cap?: number }
): Promise<LaunchInstance> {
  return apiFetch<LaunchInstance>(`/api/launches/${launchId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getEvents(
  launchId: string,
  eventType?: string,
  limit = 50,
  offset = 0
): Promise<OperationalEventListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (eventType) params.set("event_type", eventType);
  return apiFetch<OperationalEventListResponse>(
    `/api/launches/${launchId}/events?${params}`
  );
}

export function getMetrics(
  launchId: string,
  startDate?: string,
  endDate?: string
): Promise<ProjectMetricsDailyListResponse> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString() ? `?${params}` : "";
  return apiFetch<ProjectMetricsDailyListResponse>(
    `/api/launches/${launchId}/metrics${qs}`
  );
}

export function getDailyLogs(
  launchId: string
): Promise<DailyLogListResponse> {
  return apiFetch<DailyLogListResponse>(
    `/api/launches/${launchId}/daily-logs`
  );
}

export function getAuditLog(
  launchId: string,
  limit = 50,
  offset = 0
): Promise<AuditLogListResponse> {
  return apiFetch<AuditLogListResponse>(
    `/api/launches/${launchId}/audit-log?limit=${limit}&offset=${offset}`
  );
}

// ── Portfolio / fund view ──────────────────────────────────────────────────

export interface PortfolioItem {
  launch_id: string;
  idea_name: string | null;
  status: string;
  daily_budget_cap: number | null;
  total_spend_to_date: number;
  created_at: string | null;
  preview_url: string | null;
  production_url: string | null;
  latest_metrics: {
    date: string | null;
    signups: number;
    active_users: number;
    activation_rate: number | null;
    revenue_cents: number;
    total_spend_cents: number;
    error_count: number;
  } | null;
  support: {
    open_threads: number;
    escalated_threads: number;
  };
}

export interface PortfolioResponse {
  items: PortfolioItem[];
  total: number;
}

export function getPortfolioMetrics(): Promise<PortfolioResponse> {
  return apiFetch<PortfolioResponse>("/api/launches/portfolio/metrics");
}

// ── Support threads ───────────────────────────────────────────────────────

import type { SupportThreadListResponse, SupportThread } from "./types";

export function getSupportThreads(
  launchId: string,
  status?: string,
  limit = 50,
  offset = 0
): Promise<SupportThreadListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) params.set("status", status);
  return apiFetch<SupportThreadListResponse>(
    `/api/launches/${launchId}/support-threads?${params}`
  );
}

export function getSupportThread(
  launchId: string,
  threadId: string
): Promise<SupportThread> {
  return apiFetch<SupportThread>(
    `/api/launches/${launchId}/support-threads/${threadId}`
  );
}

export function resolveThread(
  launchId: string,
  threadId: string
): Promise<SupportThread> {
  return apiFetch<SupportThread>(
    `/api/launches/${launchId}/support-threads/${threadId}/resolve`,
    { method: "POST" }
  );
}

// ── Task triggers ─────────────────────────────────────────────────────────

import type { AgentTask, AgentTaskListResponse } from "./types";

export function triggerTask(
  launchId: string,
  taskType: string,
  inputParams?: Record<string, unknown>
): Promise<AgentTask> {
  return apiFetch<AgentTask>(`/api/launches/${launchId}/trigger`, {
    method: "POST",
    body: JSON.stringify({
      task_type: taskType,
      input_params: inputParams ?? null,
    }),
  });
}

export function getLaunchTasks(
  launchId: string,
  limit = 20
): Promise<AgentTaskListResponse> {
  return apiFetch<AgentTaskListResponse>(
    `/api/launches/${launchId}/tasks?limit=${limit}`
  );
}

// ── Approvals API ──────────────────────────────────────────────────────────

export function getPendingApprovals(): Promise<PendingApprovalListResponse> {
  return apiFetch<PendingApprovalListResponse>("/api/approvals/pending");
}

export function getApprovalDetail(taskId: string): Promise<PendingApproval> {
  return apiFetch<PendingApproval>(`/api/approvals/${taskId}`);
}

export function approveTask(
  taskId: string,
  approvalToken: string,
  opts?: { artifact_id?: string; create_grant?: boolean }
): Promise<{ ok: boolean; task_id: string; status: string; grant_id?: string }> {
  return apiFetch(`/api/approvals/${taskId}/approve`, {
    method: "POST",
    body: JSON.stringify({
      approval_token: approvalToken,
      artifact_id: opts?.artifact_id ?? null,
      create_grant: opts?.create_grant ?? false,
    }),
  });
}

export function rejectTask(
  taskId: string
): Promise<{ ok: boolean; task_id: string; status: string }> {
  return apiFetch(`/api/approvals/${taskId}/reject`, { method: "POST" });
}

export function getGrants(): Promise<ApprovalGrantListResponse> {
  return apiFetch<ApprovalGrantListResponse>("/api/approvals/grants");
}

export async function revokeGrant(grantId: string): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE_URL}/api/approvals/grants/${grantId}`,
    {
      method: "DELETE",
      credentials: "include",
      headers,
    }
  );
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // 204 has no body
    }
    throw new Error(`API error: ${res.status} — ${detail}`);
  }
  // 204 No Content - don't try to parse body
}
