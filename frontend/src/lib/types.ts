// Enum unions
export type IdeaStatus =
  | "discovery"
  | "scoring"
  | "validating"
  | "building"
  | "retention"
  | "growing"
  | "killed"
  | "parked";

export type GateStatus = "not_started" | "in_progress" | "passed" | "failed";

export type OfferLadderRung = "service" | "productized_service" | "software";
export type ProductUseFrequency = "daily" | "weekly" | "monthly";
export type PaymentModel =
  | "stripe_direct"
  | "paddle_mor"
  | "lemonsqueezy_mor"
  | "other";

export type GateLabel = "1" | "2" | "3" | "discovery" | "scoring";
export type EvidenceType =
  | "community_signal"
  | "customer_conversation"
  | "landing_page_metric"
  | "pre_sale"
  | "competitor_datapoint"
  | "keyword_data"
  | "retention_metric"
  | "financial_metric"
  | "outreach_metric"
  | "note";

export type SourceType =
  | "reddit"
  | "hn"
  | "github"
  | "g2_manual"
  | "capterra_manual"
  | "kw_manual"
  | "stripe"
  | "conversation"
  | "note"
  | "other";

export type Sentiment = "positive" | "negative" | "neutral" | "mixed";
export type ValidationMode = "standard" | "speed";
export type ConfidenceLevel = "low" | "medium" | "high";
export type ReviewDecision = "continue" | "pivot" | "kill" | "park" | "graduate_to_standard";
export type ReviewType = "monthly" | "biweekly";

// Response interfaces
export interface Idea {
  id: string;
  user_id: string;
  name: string;
  one_liner: string;
  audience: string;
  problem_statement: string;
  proposed_solution: string;
  offer_ladder_rung: OfferLadderRung;
  target_price_point: number | null;
  product_use_frequency: ProductUseFrequency | null;
  activation_event: string | null;
  payment_model: PaymentModel | null;
  expected_international_pct: number | null;
  validation_mode: ValidationMode;
  status: IdeaStatus;
  gate_1_status: GateStatus;
  gate_2_status: GateStatus;
  gate_3_status: GateStatus;
  kill_date: string | null;
  kill_triggers: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  archive_note: string | null;
  weighted_total: number | null;
  days_in_stage: number | null;
}

export interface IdeaListResponse {
  items: Idea[];
  total: number;
}

export interface DimensionScoreCreate {
  dimension: string;
  score: number;
  note?: string;
  confidence?: ConfidenceLevel;
}

export interface DimensionScore {
  dimension: string;
  score: number | null;
  note: string | null;
  weight: number;
  weighted_contribution: number | null;
  auto_computed?: boolean;
  confidence: ConfidenceLevel;
}

export interface ScoreResponse {
  id: string;
  idea_id: string;
  user_id: string;
  weighted_total: number | null;
  disqualifiers_checked: string[] | null;
  low_confidence_count: number;
  scored_at: string;
  updated_at: string;
  dimensions: DimensionScore[];
}

export interface Evidence {
  id: string;
  idea_id: string;
  user_id: string;
  gate: string;
  evidence_type: EvidenceType;
  title: string;
  content: Record<string, unknown> | null;
  content_purged: boolean;
  source_url: string | null;
  source_type: SourceType;
  sentiment: Sentiment;
  created_at: string;
  tags: string[] | null;
}

export interface EvidenceListResponse {
  items: Evidence[];
  total: number;
}

export interface FounderProfile {
  id: string;
  user_id: string;
  monthly_burn_rate: number;
  current_savings: number;
  runway_floor_months: number;
  available_hours_per_week_building: number;
  available_hours_per_week_selling: number;
  marketing_budget_monthly: number;
  stop_spend_trigger: string | null;
  skills: string[] | null;
  audiences_familiar_with: string[] | null;
  updated_at: string;
  runway_months_remaining: number | null;
}

export interface MonthlyReview {
  id: string;
  idea_id: string;
  user_id: string;
  review_date: string;
  review_type: ReviewType;
  score_confidence_snapshot: Record<string, ConfidenceLevel> | null;
  metrics_snapshot: Record<string, unknown> | null;
  gate_1_status_at_review: string | null;
  gate_2_status_at_review: string | null;
  gate_3_status_at_review: string | null;
  kill_triggers_fired: string[] | null;
  decision: ReviewDecision;
  reasoning: string | null;
  next_hypothesis: string | null;
  created_at: string;
}

export interface MonthlyReviewListResponse {
  items: MonthlyReview[];
  total: number;
}

export interface ScoringWeight {
  dimension: string;
  weight: number;
}

export interface WeightsResponse {
  weights: ScoringWeight[];
  total_weight: number;
}

// Metrics types
export type MetricCategory = "retention" | "economics";

export interface MetricEntry {
  id: string;
  idea_id: string;
  user_id: string;
  category: MetricCategory;
  metric_key: string;
  value: number;
  sample_size: number | null;
  period_start: string;
  period_end: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface MetricEntryListResponse {
  items: MetricEntry[];
  total: number;
}

export interface MetricWithBenchmark {
  metric_key: string;
  label: string;
  unit: string;
  category: string;
  latest_value: number | null;
  sample_size: number | null;
  benchmark_value: number | null;
  benchmark_direction: string | null;
  passes_benchmark: boolean | null;
  history: MetricEntry[];
}

export interface ComputedMetric {
  metric_key: string;
  label: string;
  unit: string;
  value: number | null;
  note: string | null;
}

export interface TriggerState {
  key: string;
  label: string;
  category: string;
  state: string;
  fired: boolean;
  metric_key: string | null;
}

export interface MetricsDashboardResponse {
  retention_metrics: MetricWithBenchmark[];
  economics_metrics: MetricWithBenchmark[];
  computed_metrics: ComputedMetric[];
  trigger_states: TriggerState[];
}

// Research types
export interface ResearchJob {
  id: string;
  idea_id: string | null;
  job_type: string;
  status: "queued" | "running" | "completed" | "failed" | "dead_letter";
  retry_count: number;
  input_params: Record<string, unknown> | null;
  results: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ResearchJobListResponse {
  items: ResearchJob[];
  total: number;
}

export interface SynthesisResponse {
  dimension: string;
  summary: string;
  key_findings: string[];
  evidence_cited: string[];
  gaps: string;
  model_version: string;
  prompt_used?: string;
}

export interface InconsistencyItem {
  dimension: string;
  severity: "warning" | "critical";
  message: string;
  evidence_ids: string[];
}

export interface ConsistencyResponse {
  inconsistencies: InconsistencyItem[];
  overall_assessment: string;
  model_version: string;
  prompt_used?: string;
}

export interface ScoreHistoryEntry {
  id: string;
  weighted_total: number | null;
  dimensions_snapshot: Record<string, { score: number; note: string | null; weight: number }> | null;
  snapshot_at: string;
}

export interface ScoreHistoryResponse {
  items: ScoreHistoryEntry[];
  total: number;
}

export interface ReviewSummaryResponse {
  summary: string;
  metrics_assessment: string;
  trigger_status: string;
  key_developments: string[];
  open_questions: string[];
  model_version: string;
  prompt_used?: string;
}

// Launch types
export type LaunchStatus =
  | "provisioning"
  | "preview"
  | "active"
  | "paused"
  | "killed";

export interface LaunchInstance {
  id: string;
  idea_id: string;
  user_id: string;
  status: LaunchStatus;
  github_repo_url: string | null;
  preview_url: string | null;
  production_url: string | null;
  secret_ref: string | null;
  daily_budget_cap: number | null;
  total_spend_to_date: number;
  created_at: string;
  updated_at: string | null;
  idea_name: string | null;
}

export interface LaunchListResponse {
  items: LaunchInstance[];
  total: number;
}

export interface OperationalEvent {
  id: string;
  launch_id: string;
  event_type: string;
  payload: Record<string, unknown> | null;
  promoted_to_evidence: boolean;
  evidence_id: string | null;
  created_at: string;
}

export interface OperationalEventListResponse {
  items: OperationalEvent[];
  total: number;
}

export interface ProjectMetricsDaily {
  id: string;
  launch_id: string;
  date: string;
  signups: number;
  active_users: number;
  activation_count: number;
  activation_rate: number | null;
  revenue_cents: number;
  ad_spend_cents: number;
  ai_cost_cents: number;
  total_spend_cents: number;
  error_count: number;
  support_tickets_received: number;
  uptime_pct: number | null;
  created_at: string;
}

export interface ProjectMetricsDailyListResponse {
  items: ProjectMetricsDaily[];
  total: number;
}

export interface DailyLog {
  id: string;
  launch_id: string;
  date: string;
  tasks_executed: Record<string, unknown>[] | null;
  metrics_snapshot: Record<string, unknown> | null;
  ceo_reasoning: string | null;
  anomalies_flagged: string | null;
  pending_approvals: Record<string, unknown>[] | null;
  next_day_plan: string | null;
  ai_cost_today: number | null;
  created_at: string;
}

export interface DailyLogListResponse {
  items: DailyLog[];
  total: number;
}

export interface AuditLogEntry {
  id: string;
  launch_id: string | null;
  actor: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
}

export interface PendingApproval {
  id: string;
  task_id: string;
  launch_id: string;
  task_type: string;
  channel_or_provider: string | null;
  summary: string;
  details: Record<string, unknown> | null;
  artifact_id: string | null;
  expires_at: string | null;
  approval_token: string | null;
  created_at: string;
}

export interface PendingApprovalListResponse {
  items: PendingApproval[];
  total: number;
}

export interface ApprovalGrant {
  id: string;
  launch_id: string;
  task_type: string;
  channel_or_provider: string | null;
  granted_at: string;
  granted_by: string;
  original_task_id: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
}

export interface ApprovalGrantListResponse {
  items: ApprovalGrant[];
  total: number;
}

// Support types
export type SupportThreadStatus = "open" | "waiting_on_customer" | "escalated" | "resolved";

export interface SupportThread {
  id: string;
  launch_id: string;
  customer_email: string;
  subject: string | null;
  status: SupportThreadStatus;
  messages: { direction: string; body: string; timestamp: string; message_id?: string }[];
  confidence_score: number | null;
  escalated_at: string | null;
  escalation_reason: string | null;
  feature_request_extracted: boolean;
  evidence_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface SupportThreadListResponse {
  items: SupportThread[];
  total: number;
}

// Agent Task types
export type AgentTaskStatus =
  | "queued"
  | "claimed"
  | "running"
  | "completed"
  | "failed"
  | "dead_letter"
  | "cancelled";

export type AgentTaskStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export interface AgentTaskStep {
  id: string;
  task_id: string;
  step_order: number;
  step_name: string;
  status: AgentTaskStepStatus;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentTask {
  id: string;
  idea_id: string | null;
  user_id: string;
  task_type: string;
  status: AgentTaskStatus;
  priority: number;
  idempotency_key: string | null;
  input_params: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  claimed_by: string | null;
  claimed_at: string | null;
  steps: AgentTaskStep[];
}

export interface AgentTaskListResponse {
  items: AgentTask[];
  total: number;
}
