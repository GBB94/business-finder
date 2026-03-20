"""Per-project and cross-project budget enforcement for LaunchPad.

Budget controls are fail-closed: if we cannot verify spend is within
limits, marketing tasks are blocked. Providers report with delay,
so internal caps use a 20% safety margin (cap at 80% of stated limit).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent
from app.models.project_metrics_daily import ProjectMetricsDaily

logger = logging.getLogger(__name__)

# Safety margin: internal enforcement triggers at 80% of stated cap
SAFETY_MARGIN = 0.80

# Cross-project monthly ceiling (configurable via env, but default here)
DEFAULT_MONTHLY_CEILING_CENTS = 50_000  # $500


class BudgetExceeded(Exception):
    """Raised when a task would exceed budget limits."""


def check_daily_budget(
    db: Session,
    launch_id: str,
    today: date | None = None,
) -> dict:
    """Check if the project's daily spend is within its budget cap.

    Returns a dict with budget status. Raises BudgetExceeded if over limit.
    """
    today = today or date.today()
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        raise ValueError(f"Launch {launch_id} not found")

    if launch.daily_budget_cap is None:
        return {"status": "no_cap", "launch_id": launch_id}

    # Get today's spend from metrics (baseline from last collection run)
    metrics = (
        db.query(ProjectMetricsDaily)
        .filter_by(launch_id=launch_id, date=today)
        .first()
    )
    metrics_ad = (metrics.ad_spend_cents or 0) if metrics else 0
    metrics_ai = (metrics.ai_cost_cents or 0) if metrics else 0
    today_spend_cents = metrics_ad + metrics_ai

    # Realtime ad spend from events (may include events added after last collection)
    realtime_ad_cents = 0
    ad_events_today = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type.in_(["ad_created", "ad_spend"]),
            func.date(OperationalEvent.created_at) == today,
        )
        .all()
    )
    for event in ad_events_today:
        if event.payload and "spend_cents" in event.payload:
            realtime_ad_cents += event.payload["spend_cents"]
    # Only add the delta not yet captured in the metrics row
    today_spend_cents += max(realtime_ad_cents - metrics_ad, 0)

    # Realtime AI cost from today's completed tasks.
    # Uses the same blended rate as metrics_collector: $0.80/1K tokens.
    ai_tokens_today = (
        db.query(func.coalesce(func.sum(AgentTask.tokens_used), 0))
        .filter(
            AgentTask.launch_id == launch_id,
            func.date(AgentTask.completed_at) == today,
            AgentTask.status == "completed",
        )
        .scalar()
    ) or 0
    realtime_ai_cents = int(ai_tokens_today * 0.08 / 100)
    # Only add the delta not yet captured in the metrics row
    today_spend_cents += max(realtime_ai_cents - metrics_ai, 0)

    cap_cents = int(launch.daily_budget_cap * 100)
    effective_cap = int(cap_cents * SAFETY_MARGIN)

    result = {
        "status": "ok" if today_spend_cents < effective_cap else "exceeded",
        "launch_id": launch_id,
        "today_spend_cents": today_spend_cents,
        "daily_cap_cents": cap_cents,
        "effective_cap_cents": effective_cap,
        "remaining_cents": max(0, effective_cap - today_spend_cents),
    }

    if result["status"] == "exceeded":
        raise BudgetExceeded(
            f"Daily budget exceeded for launch {launch_id}: "
            f"spent {today_spend_cents} cents, cap {effective_cap} cents "
            f"(80% of {cap_cents} cents)"
        )

    return result


def _realtime_today_spend_cents(db: Session, user_id: str, today: date) -> int:
    """Compute today's realtime spend across all of a user's launches.

    Returns the delta between realtime AI + ad spend and what the metrics
    row already captured, so callers can add this to the metrics-based total
    without double-counting.
    """
    # Realtime AI cost from today's completed tasks across all user's launches.
    # Join through LaunchInstance so IdeaScope-only tasks (community_scan, etc.)
    # are excluded -- they have no launch_id and don't belong in marketing budget.
    ai_tokens = (
        db.query(func.coalesce(func.sum(AgentTask.tokens_used), 0))
        .join(LaunchInstance, AgentTask.launch_id == LaunchInstance.id)
        .filter(
            LaunchInstance.user_id == user_id,
            func.date(AgentTask.completed_at) == today,
            AgentTask.status == "completed",
        )
        .scalar()
    ) or 0
    realtime_ai_cents = int(ai_tokens * 0.08 / 100)

    # Realtime ad spend from today's events across all user launches
    ad_events = (
        db.query(func.coalesce(func.sum(
            OperationalEvent.payload["spend_cents"].as_integer()
        ), 0))
        .join(LaunchInstance, OperationalEvent.launch_id == LaunchInstance.id)
        .filter(
            LaunchInstance.user_id == user_id,
            OperationalEvent.event_type.in_(["ad_created", "ad_spend"]),
            func.date(OperationalEvent.created_at) == today,
        )
        .scalar()
    ) or 0

    # What today's metrics row already has (to avoid double-counting)
    metrics_today = (
        db.query(
            func.coalesce(func.sum(ProjectMetricsDaily.ai_cost_cents), 0),
            func.coalesce(func.sum(ProjectMetricsDaily.ad_spend_cents), 0),
        )
        .join(LaunchInstance, ProjectMetricsDaily.launch_id == LaunchInstance.id)
        .filter(
            LaunchInstance.user_id == user_id,
            ProjectMetricsDaily.date == today,
        )
        .one()
    )
    metrics_ai = metrics_today[0] or 0
    metrics_ad = metrics_today[1] or 0

    # Delta: realtime spend not yet in the metrics row
    ai_delta = max(realtime_ai_cents - metrics_ai, 0)
    ad_delta = max(ad_events - metrics_ad, 0)
    return ai_delta + ad_delta


def check_monthly_ceiling(
    db: Session,
    user_id: str,
    ceiling_cents: int | None = None,
) -> dict:
    """Check cross-project monthly spend against the ceiling.

    Returns budget status. Raises BudgetExceeded if over ceiling.
    """
    ceiling = ceiling_cents or DEFAULT_MONTHLY_CEILING_CENTS
    effective_ceiling = int(ceiling * SAFETY_MARGIN)

    today = date.today()
    first_of_month = today.replace(day=1)

    # Sum all project spend this month from metrics rows
    monthly_totals = (
        db.query(func.sum(ProjectMetricsDaily.ad_spend_cents + ProjectMetricsDaily.ai_cost_cents))
        .join(LaunchInstance, ProjectMetricsDaily.launch_id == LaunchInstance.id)
        .filter(
            LaunchInstance.user_id == user_id,
            ProjectMetricsDaily.date >= first_of_month,
        )
        .scalar()
    ) or 0

    # Add today's realtime spend not yet captured in metrics
    monthly_totals += _realtime_today_spend_cents(db, user_id, today)

    result = {
        "status": "ok" if monthly_totals < effective_ceiling else "exceeded",
        "monthly_spend_cents": monthly_totals,
        "monthly_ceiling_cents": ceiling,
        "effective_ceiling_cents": effective_ceiling,
        "remaining_cents": max(0, effective_ceiling - monthly_totals),
    }

    if result["status"] == "exceeded":
        raise BudgetExceeded(
            f"Monthly spending ceiling exceeded: "
            f"spent {monthly_totals} cents, ceiling {effective_ceiling} cents "
            f"(80% of {ceiling} cents)"
        )

    return result


def enforce_budget(db: Session, launch_id: str, user_id: str) -> dict:
    """Run both daily and monthly budget checks. Raises BudgetExceeded on failure.

    Call this before any marketing task that spends money.
    """
    daily = check_daily_budget(db, launch_id)
    monthly = check_monthly_ceiling(db, user_id)
    return {"daily": daily, "monthly": monthly}


def record_ad_spend(
    db: Session,
    launch_id: str,
    spend_cents: int,
    provider: str,
    details: dict | None = None,
) -> OperationalEvent:
    """Record an ad spend event for budget tracking."""
    event = OperationalEvent(
        launch_id=launch_id,
        event_type="ad_created",
        payload={
            "provider": provider,
            "spend_cents": spend_cents,
            **(details or {}),
        },
    )
    db.add(event)
    db.flush()
    return event
