"""Add LaunchPad models and extend agent_tasks/agent_task_steps

Revision ID: 007
Revises: 006
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    # --- New tables ---

    op.create_table(
        "launch_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idea_id", sa.String(36), sa.ForeignKey("ideas.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="provisioning"),
        sa.Column("github_repo_url", sa.String(500), nullable=True),
        sa.Column("preview_url", sa.String(500), nullable=True),
        sa.Column("production_url", sa.String(500), nullable=True),
        sa.Column("secret_ref", sa.String(255), nullable=True),
        sa.Column("daily_budget_cap", sa.Float, nullable=True),
        sa.Column("total_spend_to_date", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "operational_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("promoted_to_evidence", sa.Boolean, server_default="0"),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=True, index=True),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "daily_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("tasks_executed", sa.JSON, nullable=True),
        sa.Column("metrics_snapshot", sa.JSON, nullable=True),
        sa.Column("ceo_reasoning", sa.Text, nullable=True),
        sa.Column("anomalies_flagged", sa.Text, nullable=True),
        sa.Column("pending_approvals", sa.JSON, nullable=True),
        sa.Column("next_day_plan", sa.Text, nullable=True),
        sa.Column("ai_cost_today", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("launch_id", "date", name="uq_daily_log_launch_date"),
    )

    op.create_table(
        "approval_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=False, index=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("channel_or_provider", sa.String(100), nullable=True),
        sa.Column("granted_at", sa.DateTime, nullable=False),
        sa.Column("granted_by", sa.String(36), nullable=False),
        sa.Column("original_task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
    )

    op.create_table(
        "project_metrics_daily",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("signups", sa.Integer, server_default="0"),
        sa.Column("active_users", sa.Integer, server_default="0"),
        sa.Column("activation_count", sa.Integer, server_default="0"),
        sa.Column("activation_rate", sa.Float, nullable=True),
        sa.Column("revenue_cents", sa.Integer, server_default="0"),
        sa.Column("ad_spend_cents", sa.Integer, server_default="0"),
        sa.Column("ai_cost_cents", sa.Integer, server_default="0"),
        sa.Column("total_spend_cents", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("support_tickets_received", sa.Integer, server_default="0"),
        sa.Column("uptime_pct", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("launch_id", "date", name="uq_project_metrics_daily_launch_date"),
    )

    # --- Extend agent_tasks ---

    op.add_column("agent_tasks", sa.Column("launch_id", sa.String(36), sa.ForeignKey("launch_instances.id"), nullable=True))
    op.create_index("ix_agent_tasks_launch_id", "agent_tasks", ["launch_id"])
    op.add_column("agent_tasks", sa.Column("agent_type", sa.String(20), nullable=True))
    op.add_column("agent_tasks", sa.Column("approval_status", sa.String(20), nullable=True, server_default="auto"))
    op.add_column("agent_tasks", sa.Column("approval_token_hash", sa.String(64), nullable=True))
    op.add_column("agent_tasks", sa.Column("approval_expires_at", sa.DateTime, nullable=True))
    op.add_column("agent_tasks", sa.Column("approval_used_at", sa.DateTime, nullable=True))
    op.add_column("agent_tasks", sa.Column("approval_artifact_id", sa.String(255), nullable=True))
    op.add_column("agent_tasks", sa.Column("tokens_used", sa.Integer, nullable=True))
    op.add_column("agent_tasks", sa.Column("token_budget", sa.Integer, nullable=True))
    op.add_column("agent_tasks", sa.Column("model_used", sa.String(50), nullable=True))

    # --- Extend agent_task_steps ---

    op.add_column("agent_task_steps", sa.Column("skippable", sa.Boolean, server_default="0"))
    op.add_column("agent_task_steps", sa.Column("provider_idempotency_key", sa.String(255), nullable=True))
    op.add_column("agent_task_steps", sa.Column("provider_object_id", sa.String(255), nullable=True))
    op.add_column("agent_task_steps", sa.Column("tokens_used", sa.Integer, nullable=True))
    op.add_column("agent_task_steps", sa.Column("retry_count", sa.Integer, server_default="0"))


def downgrade():
    # --- Revert agent_task_steps ---
    op.drop_column("agent_task_steps", "retry_count")
    op.drop_column("agent_task_steps", "tokens_used")
    op.drop_column("agent_task_steps", "provider_object_id")
    op.drop_column("agent_task_steps", "provider_idempotency_key")
    op.drop_column("agent_task_steps", "skippable")

    # --- Revert agent_tasks ---
    op.drop_column("agent_tasks", "model_used")
    op.drop_column("agent_tasks", "token_budget")
    op.drop_column("agent_tasks", "tokens_used")
    op.drop_column("agent_tasks", "approval_artifact_id")
    op.drop_column("agent_tasks", "approval_used_at")
    op.drop_column("agent_tasks", "approval_expires_at")
    op.drop_column("agent_tasks", "approval_token_hash")
    op.drop_column("agent_tasks", "approval_status")
    op.drop_column("agent_tasks", "agent_type")
    op.drop_index("ix_agent_tasks_launch_id", "agent_tasks")
    op.drop_column("agent_tasks", "launch_id")

    # --- Drop new tables (reverse order of creation) ---
    op.drop_table("project_metrics_daily")
    op.drop_table("approval_grants")
    op.drop_table("daily_logs")
    op.drop_table("audit_logs")
    op.drop_table("operational_events")
    op.drop_table("launch_instances")
