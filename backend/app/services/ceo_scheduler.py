"""CEO agent nightly evaluation loop for LaunchPad projects."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_task import AgentTask
from app.models.daily_log import DailyLog
from app.models.idea import Idea
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent
from app.models.project_metrics_daily import ProjectMetricsDaily
from app.models.score import Score
from app.models.evidence import Evidence
from app.services import metrics_collector

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096

CEO_SYSTEM_PROMPT = """\
You are the CEO agent for a LaunchPad project. Your job is to evaluate the \
current state of the project nightly and make strategic decisions.

You will receive a context bundle containing:
- Project idea details and IdeaScope scores
- Kill triggers defined by the founder
- Recent operational events (deploys, errors, support tickets)
- Today's metrics (signups, activation, revenue, errors)
- Recently completed and pending agent tasks
- Pending approval requests

Your evaluation must:
1. CHECK KILL TRIGGERS: Evaluate each kill trigger against current evidence. \
If any trigger is met, recommend killing the project with clear reasoning.
2. PICK PRIORITY: Identify the single highest priority task for tomorrow. \
Explain why this is more important than alternatives.
3. LIST PENDING APPROVALS: Note any tasks blocked on founder approval.
4. PLAN NEXT DAY: Outline 2-3 concrete actions for the next day.
5. FLAG ANOMALIES: Note any unusual patterns in metrics or events.

Respond with valid JSON matching this schema:
{
  "kill_triggered": false,
  "kill_reason": null,
  "priority_task": {"task_type": "...", "reasoning": "..."},
  "pending_approvals": [{"task_id": "...", "description": "..."}],
  "next_day_plan": "...",
  "anomalies": "...",
  "overall_assessment": "..."
}
"""


def build_ceo_context(db: Session, launch_id: str) -> dict:
    """Gather all context needed for the CEO nightly evaluation."""
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if launch is None:
        raise ValueError(f"Launch not found: {launch_id}")

    # Get the linked idea
    idea = db.query(Idea).filter_by(id=launch.idea_id).first()

    # Get IdeaScope scores
    scores = []
    if idea:
        score_rows = db.query(Score).filter_by(idea_id=idea.id).all()
        for s in score_rows:
            scores.append({
                "weighted_total": s.weighted_total,
                "problem_severity": s.problem_severity_score,
                "market_evidence": s.market_evidence_score,
                "revenue_model": s.revenue_model_score,
                "build_complexity": s.build_complexity_score,
                "founder_market_fit": s.founder_market_fit_score,
            })

    # Get recent evidence
    evidence_items = []
    if idea:
        recent_evidence = (
            db.query(Evidence)
            .filter_by(idea_id=idea.id)
            .order_by(Evidence.created_at.desc())
            .limit(20)
            .all()
        )
        for e in recent_evidence:
            evidence_items.append({
                "type": str(e.evidence_type),
                "title": e.title,
                "sentiment": str(e.sentiment),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })

    # Get today's metrics
    today = date.today()
    metrics = (
        db.query(ProjectMetricsDaily)
        .filter_by(launch_id=launch_id, date=today)
        .first()
    )
    metrics_dict = None
    if metrics:
        metrics_dict = {
            "signups": metrics.signups,
            "active_users": metrics.active_users,
            "activation_count": metrics.activation_count,
            "activation_rate": metrics.activation_rate,
            "revenue_cents": metrics.revenue_cents,
            "error_count": metrics.error_count,
            "support_tickets_received": metrics.support_tickets_received,
        }

    # Recent operational events (last 48 hours)
    recent_events = (
        db.query(OperationalEvent)
        .filter(OperationalEvent.launch_id == launch_id)
        .order_by(OperationalEvent.created_at.desc())
        .limit(50)
        .all()
    )
    events_list = [
        {
            "event_type": e.event_type,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in recent_events
    ]

    # Recent completed tasks
    completed_tasks = (
        db.query(AgentTask)
        .filter_by(launch_id=launch_id, status="completed")
        .order_by(AgentTask.completed_at.desc())
        .limit(10)
        .all()
    )
    completed_list = [
        {
            "task_type": t.task_type,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "output_summary": (
                json.dumps(t.output)[:500] if t.output else None
            ),
        }
        for t in completed_tasks
    ]

    # Pending approval tasks
    pending_tasks = (
        db.query(AgentTask)
        .filter_by(launch_id=launch_id, approval_status="pending_approval")
        .all()
    )
    pending_list = [
        {
            "task_id": t.id,
            "task_type": t.task_type,
            "artifact_id": t.approval_artifact_id,
            "expires_at": t.approval_expires_at.isoformat() if t.approval_expires_at else None,
        }
        for t in pending_tasks
    ]

    # Support thread summary
    from app.models.support_thread import SupportThread
    open_threads = (
        db.query(SupportThread)
        .filter(
            SupportThread.launch_id == launch_id,
            SupportThread.status.in_(["open", "escalated"]),
        )
        .all()
    )
    support_summary = {
        "open_count": sum(1 for t in open_threads if t.status == "open"),
        "escalated_count": sum(1 for t in open_threads if t.status == "escalated"),
        "escalated_threads": [
            {
                "thread_id": t.id,
                "customer_email": t.customer_email,
                "subject": t.subject,
                "escalation_reason": t.escalation_reason,
                "message_count": t.message_count,
            }
            for t in open_threads if t.status == "escalated"
        ],
    }

    # Marketing campaign summary
    from app.models.marketing_campaign import MarketingCampaign
    campaigns = (
        db.query(MarketingCampaign)
        .filter_by(launch_id=launch_id)
        .all()
    )
    marketing_summary = {
        "total_campaigns": len(campaigns),
        "active_campaigns": sum(1 for c in campaigns if c.status == "active"),
        "paused_campaigns": sum(1 for c in campaigns if c.status == "paused"),
        "total_sent": sum(c.total_sent or 0 for c in campaigns),
        "total_replied": sum(c.total_replied or 0 for c in campaigns),
        "total_bounced": sum(c.total_bounced or 0 for c in campaigns),
        "total_unsubscribed": sum(c.total_unsubscribed or 0 for c in campaigns),
        "reply_rate": (
            sum(c.total_replied or 0 for c in campaigns) / max(sum(c.total_sent or 0 for c in campaigns), 1)
        ),
        "bounce_rate": (
            sum(c.total_bounced or 0 for c in campaigns) / max(sum(c.total_sent or 0 for c in campaigns), 1)
        ),
    }

    # Qualified replies not yet promoted to evidence
    from app.models.campaign_prospect import CampaignProspect
    unpromoted_replies = (
        db.query(CampaignProspect)
        .filter(
            CampaignProspect.launch_id == launch_id,
            CampaignProspect.replied_at.isnot(None),
            CampaignProspect.reply_promoted_to_evidence == False,
        )
        .count()
    )
    marketing_summary["unpromoted_replies"] = unpromoted_replies

    return {
        "launch_id": launch_id,
        "launch_status": launch.status,
        "preview_url": launch.preview_url,
        "production_url": launch.production_url,
        "daily_budget_cap": launch.daily_budget_cap,
        "total_spend_to_date": launch.total_spend_to_date,
        "idea": {
            "name": idea.name if idea else None,
            "one_liner": idea.one_liner if idea else None,
            "audience": idea.audience if idea else None,
            "problem_statement": idea.problem_statement if idea else None,
            "status": str(idea.status) if idea else None,
            "kill_triggers": idea.kill_triggers if idea else None,
        },
        "scores": scores,
        "evidence": evidence_items,
        "metrics_today": metrics_dict,
        "recent_events": events_list,
        "completed_tasks": completed_list,
        "pending_approvals": pending_list,
        "support_summary": support_summary,
        "marketing_summary": marketing_summary,
    }


async def run_nightly_evaluation(
    db: Session,
    launch_id: str,
    model: str | None = None,
) -> tuple[DailyLog, int]:
    """Run the CEO nightly evaluation for a single project.

    Returns (DailyLog, tokens_used) so callers can track token consumption.

    1. Collect today's metrics
    2. Build context from idea, scores, events, tasks
    3. Call Claude to evaluate and decide priority
    4. Write a DailyLog entry
    """
    today = date.today()
    model = model or settings.CLAUDE_MODEL

    # Step 1: Collect metrics first
    try:
        metrics_collector.collect_daily_metrics(db, launch_id, today)
    except Exception:
        logger.exception("Failed to collect metrics for launch=%s, continuing with evaluation", launch_id)

    # Step 2: Build context
    context = build_ceo_context(db, launch_id)

    # Step 3: Call Claude
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=CEO_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Evaluate the following project state and provide your nightly assessment:\n\n{json.dumps(context, indent=2, default=str)}",
                }
            ],
        )

        response_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        # Try to parse as JSON
        try:
            evaluation = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("CEO response was not valid JSON, storing as raw text")
            evaluation = {"raw_response": response_text}

    except Exception as e:
        logger.exception("Claude API call failed for CEO evaluation launch=%s", launch_id)
        evaluation = {"error": str(e)}
        tokens_used = 0

    # Step 4: Write DailyLog
    # Check for existing entry (upsert)
    existing_log = (
        db.query(DailyLog)
        .filter_by(launch_id=launch_id, date=today)
        .first()
    )

    if existing_log:
        existing_log.metrics_snapshot = context.get("metrics_today")
        existing_log.ceo_reasoning = evaluation.get("overall_assessment", "")
        existing_log.anomalies_flagged = evaluation.get("anomalies", "")
        existing_log.pending_approvals = evaluation.get("pending_approvals")
        existing_log.next_day_plan = evaluation.get("next_day_plan", "")
        existing_log.ai_cost_today = tokens_used * 0.00001  # rough cost estimate
        daily_log = existing_log
    else:
        daily_log = DailyLog(
            id=str(uuid.uuid4()),
            launch_id=launch_id,
            date=today,
            tasks_executed=[t["task_type"] for t in context.get("completed_tasks", [])],
            metrics_snapshot=context.get("metrics_today"),
            ceo_reasoning=evaluation.get("overall_assessment", ""),
            anomalies_flagged=evaluation.get("anomalies", ""),
            pending_approvals=evaluation.get("pending_approvals"),
            next_day_plan=evaluation.get("next_day_plan", ""),
            ai_cost_today=tokens_used * 0.00001,
        )
        db.add(daily_log)

    db.commit()
    db.refresh(daily_log)

    logger.info(
        "Completed nightly evaluation for launch=%s tokens=%d kill_triggered=%s",
        launch_id,
        tokens_used,
        evaluation.get("kill_triggered", False),
    )
    return daily_log, tokens_used


def _format_cents(cents: int | float | None) -> str:
    if cents is None:
        return "$0.00"
    return f"${cents / 100:.2f}"


def build_morning_email_html(
    daily_logs: list[DailyLog],
    db: Session,
) -> str:
    """Build the HTML body for the CEO morning email across all projects."""
    sections: list[str] = []

    for log in daily_logs:
        launch = db.query(LaunchInstance).filter_by(id=log.launch_id).first()
        idea = db.query(Idea).filter_by(id=launch.idea_id).first() if launch else None
        project_name = idea.name if idea else log.launch_id[:8]
        status = launch.status if launch else "unknown"

        # Metrics row
        m = log.metrics_snapshot or {}
        metrics_html = ""
        if m:
            metrics_html = (
                f"<tr><td>Signups</td><td>{m.get('signups', 0)}</td></tr>"
                f"<tr><td>Active Users</td><td>{m.get('active_users', 0)}</td></tr>"
                f"<tr><td>Activation Rate</td><td>"
                f"{(m.get('activation_rate') or 0) * 100:.1f}%</td></tr>"
                f"<tr><td>Revenue</td><td>{_format_cents(m.get('revenue_cents'))}</td></tr>"
                f"<tr><td>Errors</td><td>{m.get('error_count', 0)}</td></tr>"
            )

        # Marketing stats
        marketing_html = ""
        mkt = (log.metrics_snapshot or {}).get("marketing") if log.metrics_snapshot else None
        if not mkt:
            # Pull live from DB if not in snapshot
            from app.models.marketing_campaign import MarketingCampaign as MC
            mkt_campaigns = db.query(MC).filter_by(launch_id=log.launch_id).all()
            if mkt_campaigns:
                total_sent = sum(c.total_sent or 0 for c in mkt_campaigns)
                total_replied = sum(c.total_replied or 0 for c in mkt_campaigns)
                total_bounced = sum(c.total_bounced or 0 for c in mkt_campaigns)
                active = sum(1 for c in mkt_campaigns if c.status == "active")
                paused = sum(1 for c in mkt_campaigns if c.status == "paused")
                mkt = {
                    "active_campaigns": active,
                    "paused_campaigns": paused,
                    "total_sent": total_sent,
                    "total_replied": total_replied,
                    "total_bounced": total_bounced,
                    "reply_rate": total_replied / max(total_sent, 1),
                    "bounce_rate": total_bounced / max(total_sent, 1),
                }
        if mkt and mkt.get("total_sent", 0) > 0:
            reply_pct = (mkt.get("reply_rate", 0)) * 100
            bounce_pct = (mkt.get("bounce_rate", 0)) * 100
            paused_note = f' <span style="color:#d97706;">({mkt.get("paused_campaigns", 0)} paused)</span>' if mkt.get("paused_campaigns") else ""
            marketing_html = (
                f'<h4>Marketing</h4>'
                f'<table style="width:100%;font-size:13px;border-collapse:collapse;">'
                f'<tr><td>Active Campaigns</td><td>{mkt.get("active_campaigns", 0)}{paused_note}</td></tr>'
                f'<tr><td>Emails Sent</td><td>{mkt.get("total_sent", 0)}</td></tr>'
                f'<tr><td>Replies</td><td>{mkt.get("total_replied", 0)} ({reply_pct:.1f}%)</td></tr>'
                f'<tr><td>Bounces</td><td>{mkt.get("total_bounced", 0)} ({bounce_pct:.1f}%)</td></tr>'
                f'</table>'
            )

        # Pending approvals
        approvals_html = ""
        pending = log.pending_approvals or []
        if pending:
            items = "".join(
                f"<li>{a.get('description') or a.get('task_type', 'unknown')} "
                f"(task {a.get('task_id', '?')[:8]}...)</li>"
                for a in pending
            )
            approvals_html = (
                f'<h4 style="color:#d97706;">Pending Approvals</h4>'
                f"<ul>{items}</ul>"
            )

        # Anomalies
        anomalies_html = ""
        if log.anomalies_flagged:
            anomalies_html = (
                f'<h4 style="color:#dc2626;">Anomalies</h4>'
                f"<p>{log.anomalies_flagged}</p>"
            )

        # Cost
        cost_html = ""
        if log.ai_cost_today is not None:
            cost_html = f"<p><strong>AI cost today:</strong> ${log.ai_cost_today:.4f}</p>"

        section = f"""
        <div style="margin-bottom:24px;padding:16px;border:1px solid #374151;border-radius:8px;">
          <h3 style="margin:0 0 8px 0;">{project_name}
            <span style="font-size:12px;color:#9ca3af;margin-left:8px;">{status}</span>
          </h3>

          {f'<table style="width:100%;font-size:13px;border-collapse:collapse;">{metrics_html}</table>' if metrics_html else '<p style="color:#6b7280;">No metrics yet.</p>'}

          {marketing_html}
          {approvals_html}
          {anomalies_html}

          {f'<h4>CEO Assessment</h4><p>{log.ceo_reasoning}</p>' if log.ceo_reasoning else ''}
          {f'<h4>Next Day Plan</h4><p>{log.next_day_plan}</p>' if log.next_day_plan else ''}
          {cost_html}
        </div>
        """
        sections.append(section)

    body = "".join(sections) or "<p>No active projects to report on.</p>"
    today_str = date.today().isoformat()

    return f"""
    <html>
    <body style="font-family:system-ui,sans-serif;color:#e5e7eb;background:#111827;padding:24px;">
      <h2 style="margin-bottom:4px;">LaunchPad Morning Report</h2>
      <p style="color:#6b7280;margin-top:0;">{today_str}</p>
      {body}
      <hr style="border-color:#374151;margin-top:32px;">
      <p style="font-size:11px;color:#6b7280;">
        Sent by your LaunchPad CEO agent. View details in the dashboard.
      </p>
    </body>
    </html>
    """


def send_morning_email(daily_logs: list[DailyLog], db: Session) -> str | None:
    """Build and send the morning email. Returns the Resend message ID or None."""
    if not settings.FOUNDER_EMAIL:
        logger.warning("FOUNDER_EMAIL not configured, skipping morning email")
        return None

    from app.services.email_service import send_email

    html = build_morning_email_html(daily_logs, db)

    # Count pending approvals across all projects
    total_pending = sum(
        len(log.pending_approvals or []) for log in daily_logs
    )
    subject_suffix = f" ({total_pending} pending)" if total_pending else ""
    subject = f"LaunchPad Morning Report - {date.today().isoformat()}{subject_suffix}"

    return send_email(
        to=settings.FOUNDER_EMAIL,
        subject=subject,
        html=html,
    )


async def _backfill_smartlead_replies(db: Session, launch: LaunchInstance) -> int:
    """Poll Smartlead for unread replies missed by webhooks. Backfill only.

    Uses idempotency keys so duplicate enqueues are no-ops. This is a repair
    pass, not the primary ingestion path (webhooks handle that).
    """
    from app.models.marketing_campaign import MarketingCampaign
    from app.services import smartlead_service as sl
    from app.services.secret_service import get_secrets_for_task

    secrets = get_secrets_for_task(
        db, idea_id=launch.idea_id, user_id=launch.user_id,
        environment="production", actor="ceo_backfill",
    )
    account_id_str = secrets.get("SMARTLEAD_EMAIL_ACCOUNT_ID")
    if not account_id_str:
        return 0

    account_id = int(account_id_str)

    # Get active campaign IDs for this launch
    active_campaigns = (
        db.query(MarketingCampaign)
        .filter(
            MarketingCampaign.launch_id == launch.id,
            MarketingCampaign.status.in_(["active", "paused"]),
            MarketingCampaign.provider_campaign_id.isnot(None),
        )
        .all()
    )
    if not active_campaigns:
        return 0

    campaign_ids = [int(c.provider_campaign_id) for c in active_campaigns]

    try:
        unread = await sl.get_unread_replies(
            email_account_id=account_id,
            campaign_ids=campaign_ids,
        )
    except Exception:
        logger.exception("Smartlead backfill polling failed for launch=%s", launch.id)
        return 0

    ingested = 0
    for reply in unread:
        provider_event_id = f"smartlead_reply:{reply.get('id', '')}"

        # Write OperationalEvent if not already present
        existing = (
            db.query(OperationalEvent)
            .filter_by(launch_id=launch.id, provider_event_id=provider_event_id)
            .first()
        )
        if not existing:
            db.add(OperationalEvent(
                launch_id=launch.id,
                event_type="email_replied",
                provider_event_id=provider_event_id,
                payload={"source": "smartlead_backfill", **reply},
            ))
            db.flush()

        # Enqueue triage task regardless (idempotency key prevents double)
        from app.routers.webhooks import _enqueue_campaign_reply_triage
        _enqueue_campaign_reply_triage(db, launch, reply, provider_event_id)

        try:
            await sl.mark_reply_read(int(reply.get("id", 0)))
        except Exception:
            logger.warning("Failed to mark reply %s as read", reply.get("id"))

        ingested += 1

    if ingested:
        db.commit()
        logger.info("Smartlead backfill: ingested %d replies for launch=%s", ingested, launch.id)

    return ingested


async def _sync_suppressions_to_smartlead(db: Session) -> int:
    """Push unsynced EmailSuppression records to Smartlead global unsubscribe list.

    Runs once per nightly cycle across all users. Batch-sends emails then
    marks them as synced.
    """
    from app.models.email_suppression import EmailSuppression
    from app.services import smartlead_service as sl

    unsynced = (
        db.query(EmailSuppression)
        .filter_by(synced_to_smartlead=False)
        .limit(500)
        .all()
    )
    if not unsynced:
        return 0

    emails = [s.email for s in unsynced]
    try:
        await sl.add_to_global_unsubscribe(emails)
    except Exception:
        logger.exception("Failed to sync %d suppressions to Smartlead", len(emails))
        return 0

    now = datetime.now(timezone.utc)
    for s in unsynced:
        s.synced_to_smartlead = True
        s.synced_at = now

    db.commit()
    logger.info("Synced %d suppressions to Smartlead global unsubscribe", len(unsynced))
    return len(unsynced)


async def run_all_nightly(db: Session) -> list[DailyLog]:
    """Run the CEO nightly evaluation for all active launches, then send morning email.

    Also runs marketing backfill (Smartlead reply polling) and suppression sync.
    """
    active_launches = (
        db.query(LaunchInstance)
        .filter(LaunchInstance.status.in_(["preview", "active"]))
        .all()
    )

    # Phase 1: Smartlead reply backfill + suppression sync (before evaluation)
    for launch in active_launches:
        try:
            await _backfill_smartlead_replies(db, launch)
        except Exception:
            logger.exception("Smartlead backfill failed for launch=%s", launch.id)

    try:
        await _sync_suppressions_to_smartlead(db)
    except Exception:
        logger.exception("Suppression sync to Smartlead failed")

    # Phase 2: CEO evaluations
    results: list[DailyLog] = []
    for launch in active_launches:
        try:
            log, _tokens = await run_nightly_evaluation(db, launch.id)
            results.append(log)
        except Exception:
            logger.exception("Nightly evaluation failed for launch=%s", launch.id)
            continue

    logger.info("Completed nightly evaluations: %d/%d", len(results), len(active_launches))

    # Phase 3: Send the consolidated morning email
    if results:
        try:
            msg_id = send_morning_email(results, db)
            if msg_id:
                logger.info("Morning email sent: %s", msg_id)
        except Exception:
            logger.exception("Failed to send morning email")

    return results
