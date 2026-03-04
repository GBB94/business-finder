"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ideas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("one_liner", sa.Text, nullable=False, server_default=""),
        sa.Column("audience", sa.Text, nullable=False, server_default=""),
        sa.Column("problem_statement", sa.Text, nullable=False, server_default=""),
        sa.Column("proposed_solution", sa.Text, nullable=False, server_default=""),
        sa.Column("offer_ladder_rung", sa.String(30), nullable=False, server_default="software"),
        sa.Column("target_price_point", sa.Float, nullable=True),
        sa.Column("product_use_frequency", sa.String(20), nullable=True),
        sa.Column("activation_event", sa.Text, nullable=True),
        sa.Column("payment_model", sa.String(30), nullable=True),
        sa.Column("expected_international_pct", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="discovery"),
        sa.Column("gate_1_status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("gate_2_status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("gate_3_status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("kill_date", sa.DateTime, nullable=True),
        sa.Column("kill_triggers", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("archived_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("problem_severity_score", sa.Integer, nullable=True),
        sa.Column("problem_severity_note", sa.Text, nullable=True),
        sa.Column("market_evidence_score", sa.Integer, nullable=True),
        sa.Column("market_evidence_note", sa.Text, nullable=True),
        sa.Column("revenue_model_score", sa.Integer, nullable=True),
        sa.Column("revenue_model_note", sa.Text, nullable=True),
        sa.Column("distribution_feasibility_score", sa.Integer, nullable=True),
        sa.Column("distribution_feasibility_note", sa.Text, nullable=True),
        sa.Column("purchaser_quality_score", sa.Integer, nullable=True),
        sa.Column("purchaser_quality_note", sa.Text, nullable=True),
        sa.Column("build_complexity_score", sa.Integer, nullable=True),
        sa.Column("build_complexity_note", sa.Text, nullable=True),
        sa.Column("founder_market_fit_score", sa.Integer, nullable=True),
        sa.Column("founder_market_fit_note", sa.Text, nullable=True),
        sa.Column("time_to_revenue_score", sa.Integer, nullable=True),
        sa.Column("time_to_revenue_note", sa.Text, nullable=True),
        sa.Column("founder_constraints_score", sa.Integer, nullable=True),
        sa.Column("founder_constraints_note", sa.Text, nullable=True),
        sa.Column("competition_level_score", sa.Integer, nullable=True),
        sa.Column("competition_level_note", sa.Text, nullable=True),
        sa.Column("defensibility_potential_score", sa.Integer, nullable=True),
        sa.Column("defensibility_potential_note", sa.Text, nullable=True),
        sa.Column("weighted_total", sa.Float, nullable=True),
        sa.Column("disqualifiers_checked", sa.JSON, nullable=True),
        sa.Column("scored_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("gate", sa.String(20), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.JSON, nullable=True),
        sa.Column("content_purged", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("purge_reason", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="other"),
        sa.Column("sentiment", sa.String(20), nullable=False, server_default="neutral"),
        sa.Column("connector_version", sa.String(50), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("ingested_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("tags", sa.JSON, nullable=True),
    )

    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=True, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_params", sa.JSON, nullable=True),
        sa.Column("results", sa.JSON, nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("idempotency_key", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "founder_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), unique=True, nullable=False),
        sa.Column("monthly_burn_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("current_savings", sa.Float, nullable=False, server_default="0"),
        sa.Column("runway_floor_months", sa.Integer, nullable=False, server_default="3"),
        sa.Column("available_hours_per_week_building", sa.Integer, nullable=False, server_default="0"),
        sa.Column("available_hours_per_week_selling", sa.Integer, nullable=False, server_default="0"),
        sa.Column("marketing_budget_monthly", sa.Float, nullable=False, server_default="0"),
        sa.Column("stop_spend_trigger", sa.Text, nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("audiences_familiar_with", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "monthly_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("review_date", sa.Date, nullable=False),
        sa.Column("metrics_snapshot", sa.JSON, nullable=True),
        sa.Column("gate_1_status_at_review", sa.String(20), nullable=True),
        sa.Column("gate_2_status_at_review", sa.String(20), nullable=True),
        sa.Column("gate_3_status_at_review", sa.String(20), nullable=True),
        sa.Column("kill_triggers_fired", sa.JSON, nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("next_hypothesis", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "scoring_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("scoring_weights")
    op.drop_table("monthly_reviews")
    op.drop_table("founder_profiles")
    op.drop_table("research_jobs")
    op.drop_table("evidence")
    op.drop_table("scores")
    op.drop_table("ideas")
