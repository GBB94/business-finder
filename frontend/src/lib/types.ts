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
export type ReviewDecision = "continue" | "pivot" | "kill" | "park";

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
  status: IdeaStatus;
  gate_1_status: GateStatus;
  gate_2_status: GateStatus;
  gate_3_status: GateStatus;
  kill_date: string | null;
  kill_triggers: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  weighted_total: number | null;
  days_in_stage: number | null;
}

export interface IdeaListResponse {
  items: Idea[];
  total: number;
}

export interface DimensionScore {
  dimension: string;
  score: number | null;
  note: string | null;
  weight: number;
  weighted_contribution: number | null;
}

export interface ScoreResponse {
  id: string;
  idea_id: string;
  user_id: string;
  weighted_total: number | null;
  disqualifiers_checked: string[] | null;
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
