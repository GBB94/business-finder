"""Deterministic daily metrics aggregation for LaunchPad projects."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent
from app.models.project_metrics_daily import ProjectMetricsDaily

logger = logging.getLogger(__name__)

# Event type categories for counting
DEPLOY_EVENTS = {"deploy", "deploy_failed", "deploy_timeout"}
EMAIL_EVENTS = {"email_sent", "email_bounced"}
ERROR_EVENTS = {"error", "error_spike"}
SUPPORT_EVENTS = {"support_received", "support_responded"}


def collect_daily_metrics(
    db: Session,
    launch_id: str,
    target_date: date,
) -> ProjectMetricsDaily:
    """Query OperationalEvents for the given date, compute aggregates,
    and upsert a ProjectMetricsDaily row.
    """
    # Fetch all events for this launch on the target date
    events = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            func.date(OperationalEvent.created_at) == target_date,
        )
        .all()
    )

    # Count by category
    deploy_count = sum(1 for e in events if e.event_type in DEPLOY_EVENTS)
    email_count = sum(1 for e in events if e.event_type in EMAIL_EVENTS)
    error_count = sum(1 for e in events if e.event_type in ERROR_EVENTS)
    support_count = sum(1 for e in events if e.event_type in SUPPORT_EVENTS)

    # Extract signup / activation / revenue from metric_update events
    signups = 0
    activation_count = 0
    revenue_cents = 0
    active_users = 0

    for e in events:
        if e.event_type == "metric_update" and e.payload:
            signups += e.payload.get("signups", 0)
            activation_count += e.payload.get("activation_count", 0)
            revenue_cents += e.payload.get("revenue_cents", 0)
            active_users += e.payload.get("active_users", 0)

    # Sum ad spend from ad_created/ad_spend events
    ad_spend_cents = 0
    for e in events:
        if e.event_type in ("ad_created", "ad_spend") and e.payload:
            ad_spend_cents += e.payload.get("spend_cents", 0)

    # Sum AI cost from completed agent tasks for this launch on this date.
    # tokens_used is tracked per task; we estimate cost at $0.25/1K input +
    # $1.25/1K output for Sonnet, but since we only have total tokens we use
    # a blended rate of ~$0.80/1K tokens as a rough ceiling.
    ai_tokens_today = (
        db.query(func.coalesce(func.sum(AgentTask.tokens_used), 0))
        .filter(
            AgentTask.launch_id == launch_id,
            func.date(AgentTask.completed_at) == target_date,
            AgentTask.status == "completed",
        )
        .scalar()
    ) or 0
    # Convert tokens to cents: $0.80 per 1K tokens = 0.08 cents per token
    ai_cost_cents = int(ai_tokens_today * 0.08 / 100)

    total_spend_cents = ad_spend_cents + ai_cost_cents

    # Compute activation rate
    activation_rate = (activation_count / signups) if signups > 0 else None

    # Upsert: check for existing row
    existing = (
        db.query(ProjectMetricsDaily)
        .filter_by(launch_id=launch_id, date=target_date)
        .first()
    )

    if existing:
        existing.signups = signups
        existing.active_users = active_users
        existing.activation_count = activation_count
        existing.activation_rate = activation_rate
        existing.revenue_cents = revenue_cents
        existing.ad_spend_cents = ad_spend_cents
        existing.ai_cost_cents = ai_cost_cents
        existing.total_spend_cents = total_spend_cents
        existing.error_count = error_count
        existing.support_tickets_received = support_count
        metrics = existing
    else:
        metrics = ProjectMetricsDaily(
            id=str(uuid.uuid4()),
            launch_id=launch_id,
            date=target_date,
            signups=signups,
            active_users=active_users,
            activation_count=activation_count,
            activation_rate=activation_rate,
            revenue_cents=revenue_cents,
            ad_spend_cents=ad_spend_cents,
            ai_cost_cents=ai_cost_cents,
            total_spend_cents=total_spend_cents,
            error_count=error_count,
            support_tickets_received=support_count,
        )
        db.add(metrics)

    db.commit()
    db.refresh(metrics)

    logger.info(
        "Collected metrics for launch=%s date=%s: signups=%d errors=%d deploys=%d emails=%d support=%d",
        launch_id,
        target_date,
        signups,
        error_count,
        deploy_count,
        email_count,
        support_count,
    )
    return metrics


def collect_all_active_projects(
    db: Session,
    target_date: date,
) -> list[ProjectMetricsDaily]:
    """Run metrics collection for all active LaunchInstances."""
    active_launches = (
        db.query(LaunchInstance)
        .filter(LaunchInstance.status.in_(["provisioning", "preview", "active"]))
        .all()
    )

    results: list[ProjectMetricsDaily] = []
    for launch in active_launches:
        try:
            metrics = collect_daily_metrics(db, launch.id, target_date)
            results.append(metrics)
        except Exception:
            logger.exception("Failed to collect metrics for launch=%s", launch.id)
            continue

    logger.info("Collected metrics for %d/%d active projects", len(results), len(active_launches))
    return results
