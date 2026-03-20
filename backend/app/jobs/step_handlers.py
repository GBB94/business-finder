"""Step handler implementations for agent tasks.

Each handler receives (db, task, step, input_data) and returns a dict of output.
Registered in STEP_HANDLERS by (task_type, step_name) tuple.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.adapters.hn_adapter import HNAdapter
from app.adapters.reddit_adapter import RedditAdapter
from app.models.agent_task import AgentTask, AgentTaskStep
from app.models.evidence import Evidence, EvidenceType, GateLabel, Sentiment, SourceType
from app.models.idea import Idea
from app.models.score import Score
from app.services.analysis_service import analyze_community_posts
from app.services.metrics_service import build_metrics_dashboard, evaluate_metric_triggers
from app.services.synthesis_service import (
    check_score_consistency,
    generate_review_summary,
    synthesize_evidence_for_dimension,
    DIMENSION_DESCRIPTIONS,
)

logger = logging.getLogger(__name__)


def _get_idea(db: Session, task: AgentTask) -> Idea:
    idea = db.query(Idea).filter_by(id=task.idea_id).first()
    if not idea:
        raise ValueError(f"Idea {task.idea_id} not found")
    return idea


def _map_sentiment(s: str) -> Sentiment:
    return {
        "positive": Sentiment.positive,
        "negative": Sentiment.negative,
        "neutral": Sentiment.neutral,
        "mixed": Sentiment.mixed,
    }.get(s, Sentiment.neutral)


# ---------------------------------------------------------------------------
# community_scan handlers
# ---------------------------------------------------------------------------


def handle_fetch_posts(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Fetch posts from HN and Reddit based on task input_params."""
    idea = _get_idea(db, task)
    params = task.input_params or {}
    queries = params.get("queries", [])
    sources = params.get("sources", ["hn", "reddit"])

    if not queries:
        queries = [idea.name]
        if idea.problem_statement:
            queries.append(idea.problem_statement[:100])

    async def _fetch():
        tasks = []
        if "hn" in sources:
            tasks.append(HNAdapter().search(queries, limit=25))
        if "reddit" in sources:
            tasks.append(RedditAdapter().search(queries, limit=25))
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(_fetch())

    all_posts = []
    errors = []
    for result in results:
        if isinstance(result, Exception):
            errors.append(str(result))
            continue
        all_posts.extend(result)

    # Deduplicate
    seen = set()
    unique_posts = []
    for p in all_posts:
        key = f"{p.source_type}:{p.source_id}"
        if key not in seen:
            seen.add(key)
            unique_posts.append(p)

    # Serialize posts for next step
    serialized = [
        {
            "source_id": p.source_id,
            "source_type": p.source_type,
            "source_url": p.source_url,
            "title": p.title,
            "body": p.body[:2000],
            "score": p.score,
            "comment_count": p.comment_count,
        }
        for p in unique_posts
    ]

    return {
        "post_count": len(serialized),
        "posts": serialized,
        "errors": errors,
    }


def handle_analyze_posts(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Analyze fetched posts using Claude."""
    idea = _get_idea(db, task)

    # Get posts from previous step output
    prev_step = next(
        (s for s in task.steps if s.step_name == "fetch_posts" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("fetch_posts step must complete first with post data")

    posts_data = prev_step.output_data.get("posts", [])
    if not posts_data:
        return {"scored_posts": [], "themes": [], "post_count": 0}

    # Reconstruct RawPost objects for the analysis service
    from app.adapters.base import RawPost
    raw_posts = [
        RawPost(
            source_id=p["source_id"],
            source_type=p["source_type"],
            source_url=p["source_url"],
            title=p["title"],
            body=p["body"],
            score=p["score"],
            comment_count=p["comment_count"],
        )
        for p in posts_data
    ]

    analysis = asyncio.run(analyze_community_posts(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        posts=raw_posts,
        model=task.model_used,
    ))

    # Serialize analysis for next step
    scored = [
        {
            "source_id": sp.source_id,
            "source_type": sp.source_type,
            "source_url": sp.source_url,
            "title": sp.title,
            "relevance_score": sp.relevance_score,
            "summary": sp.summary,
            "sentiment": sp.sentiment,
            "original_score": sp.original_score,
        }
        for sp in analysis.scored_posts
    ]

    step.tokens_used = analysis.tokens_used

    return {
        "scored_posts": scored,
        "themes": analysis.themes,
        "language_patterns": analysis.language_patterns,
        "objections": analysis.objections,
        "sales_safari_summary": analysis.sales_safari_summary,
        "model_version": analysis.model_version,
    }


def handle_create_evidence(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Create Evidence records from analyzed posts."""
    idea = _get_idea(db, task)

    prev_step = next(
        (s for s in task.steps if s.step_name == "analyze_posts" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("analyze_posts step must complete first")

    analysis = prev_step.output_data
    scored_posts = analysis.get("scored_posts", [])
    evidence_count = 0

    for sp in scored_posts:
        if sp["relevance_score"] < 5:
            continue

        source_type_val = SourceType.hn if sp["source_type"] == "hn" else SourceType.reddit
        sentiment_val = _map_sentiment(sp["sentiment"])

        ev = Evidence(
            idea_id=idea.id,
            user_id=task.user_id,
            gate=GateLabel.discovery,
            evidence_type=EvidenceType.community_signal,
            title=(sp.get("summary") or "Community Signal")[:500],
            content={
                "summary": sp.get("summary", ""),
                "relevance_score": sp["relevance_score"],
                "themes": analysis.get("themes", []),
                "original_score": sp.get("original_score", 0),
            },
            source_url=sp.get("source_url", ""),
            source_type=source_type_val,
            sentiment=sentiment_val,
            connector_version="agent_task_v1",
            model_version=analysis.get("model_version", ""),
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        evidence_count += 1

    # Create Sales Safari Report if available
    if analysis.get("sales_safari_summary"):
        report_ev = Evidence(
            idea_id=idea.id,
            user_id=task.user_id,
            gate=GateLabel.discovery,
            evidence_type=EvidenceType.community_signal,
            title=f"Sales Safari Report: {idea.name}"[:500],
            content={
                "report": analysis["sales_safari_summary"],
                "themes": analysis.get("themes", []),
                "language_patterns": analysis.get("language_patterns", []),
                "objections": analysis.get("objections", []),
            },
            source_type=SourceType.other,
            sentiment=Sentiment.neutral,
            connector_version="agent_task_v1",
            model_version=analysis.get("model_version", ""),
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(report_ev)

    db.flush()

    return {
        "evidence_created": evidence_count,
        "has_safari_report": bool(analysis.get("sales_safari_summary")),
    }


# ---------------------------------------------------------------------------
# evidence_synthesis handlers
# ---------------------------------------------------------------------------


def handle_gather_evidence(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Gather all evidence and scores for the idea."""
    idea = _get_idea(db, task)
    params = task.input_params or {}
    dimension = params.get("dimension")

    evidence_rows = db.query(Evidence).filter_by(idea_id=idea.id).all()
    evidence_items = [
        {
            "id": e.id,
            "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "title": e.title,
            "content": e.content,
            "source_type": e.source_type.value if hasattr(e.source_type, "value") else str(e.source_type),
            "sentiment": e.sentiment.value if hasattr(e.sentiment, "value") else str(e.sentiment),
            "tags": e.tags if hasattr(e, "tags") and e.tags else [],
        }
        for e in evidence_rows
    ]

    # Get current score for this dimension if specified
    score_row = db.query(Score).filter_by(idea_id=idea.id).order_by(Score.created_at.desc()).first()
    current_score = None
    current_note = None
    if score_row and dimension:
        current_score = getattr(score_row, f"{dimension}_score", None)
        current_note = getattr(score_row, f"{dimension}_note", None)

    return {
        "evidence_count": len(evidence_items),
        "evidence_items": evidence_items,
        "dimension": dimension,
        "current_score": current_score,
        "current_note": current_note,
        "idea_name": idea.name,
        "idea_audience": idea.audience or "",
        "idea_problem": idea.problem_statement or "",
        "idea_solution": idea.proposed_solution or "",
    }


def handle_run_synthesis(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Run Claude synthesis on gathered evidence."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "gather_evidence" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("gather_evidence step must complete first")

    data = prev_step.output_data
    dimension = data.get("dimension")
    if not dimension:
        raise ValueError("dimension is required in input_params for evidence_synthesis")

    dim_label = DIMENSION_DESCRIPTIONS.get(dimension, dimension)

    result = asyncio.run(synthesize_evidence_for_dimension(
        idea_name=data["idea_name"],
        idea_audience=data["idea_audience"],
        idea_problem=data["idea_problem"],
        idea_solution=data["idea_solution"],
        dimension=dimension,
        dimension_label=dim_label,
        current_score=data.get("current_score"),
        current_note=data.get("current_note"),
        evidence_items=data["evidence_items"],
        model=task.model_used,
    ))

    step.tokens_used = result.tokens_used

    return {
        "summary": result.summary,
        "key_findings": result.key_findings,
        "evidence_cited": result.evidence_cited,
        "gaps": result.gaps,
        "model_version": result.model_version,
    }


def handle_synthesis_store_result(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store synthesis result in task output (already persisted by step completion)."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "run_synthesis" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("run_synthesis step must complete first")

    return {"stored": True, "synthesis": prev_step.output_data}


# ---------------------------------------------------------------------------
# consistency_check handlers
# ---------------------------------------------------------------------------


def handle_gather_scores(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Gather scores and evidence for consistency check."""
    idea = _get_idea(db, task)

    score_row = db.query(Score).filter_by(idea_id=idea.id).order_by(Score.created_at.desc()).first()
    scores = []
    if score_row:
        for dim, desc in DIMENSION_DESCRIPTIONS.items():
            val = getattr(score_row, f"{dim}_score", None)
            note = getattr(score_row, f"{dim}_note", None)
            if val is not None:
                scores.append({
                    "dimension": dim,
                    "score": val,
                    "note": note,
                })

    evidence_rows = db.query(Evidence).filter_by(idea_id=idea.id).all()
    evidence_items = [
        {
            "id": e.id,
            "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "title": e.title,
            "content": e.content,
            "source_type": e.source_type.value if hasattr(e.source_type, "value") else str(e.source_type),
            "sentiment": e.sentiment.value if hasattr(e.sentiment, "value") else str(e.sentiment),
            "tags": e.tags if hasattr(e, "tags") and e.tags else [],
        }
        for e in evidence_rows
    ]

    return {
        "scores": scores,
        "evidence_items": evidence_items,
        "idea_name": idea.name,
        "idea_audience": idea.audience or "",
        "idea_problem": idea.problem_statement or "",
        "idea_solution": idea.proposed_solution or "",
    }


def handle_run_check(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Run Claude consistency check."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "gather_scores" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("gather_scores step must complete first")

    data = prev_step.output_data

    result = asyncio.run(check_score_consistency(
        idea_name=data["idea_name"],
        idea_audience=data["idea_audience"],
        idea_problem=data["idea_problem"],
        idea_solution=data["idea_solution"],
        scores=data["scores"],
        evidence_items=data["evidence_items"],
        model=task.model_used,
    ))

    step.tokens_used = result.tokens_used

    return {
        "inconsistencies": result.inconsistencies,
        "overall_assessment": result.overall_assessment,
        "model_version": result.model_version,
    }


def handle_check_store_result(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store consistency check result."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "run_check" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("run_check step must complete first")

    return {"stored": True, "check": prev_step.output_data}


# ---------------------------------------------------------------------------
# review_summary handlers
# ---------------------------------------------------------------------------


def handle_gather_metrics(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Gather metrics, scores, triggers, and evidence for review summary."""
    idea = _get_idea(db, task)

    # Metrics dashboard
    dashboard = build_metrics_dashboard(db, idea)

    # Scores
    score_row = db.query(Score).filter_by(idea_id=idea.id).order_by(Score.created_at.desc()).first()
    scores_summary = None
    if score_row:
        scores_summary = {}
        for dim in DIMENSION_DESCRIPTIONS:
            val = getattr(score_row, f"{dim}_score", None)
            if val is not None:
                scores_summary[dim] = val

    # Kill trigger states
    trigger_states = evaluate_metric_triggers(db, idea)

    # Recent evidence (last 20)
    evidence_rows = (
        db.query(Evidence)
        .filter_by(idea_id=idea.id)
        .order_by(Evidence.ingested_at.desc())
        .limit(20)
        .all()
    )
    recent_evidence = [
        {
            "id": e.id,
            "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "title": e.title,
            "content": e.content,
            "source_type": e.source_type.value if hasattr(e.source_type, "value") else str(e.source_type),
            "sentiment": e.sentiment.value if hasattr(e.sentiment, "value") else str(e.sentiment),
        }
        for e in evidence_rows
    ]

    # Previous reviews
    from app.models.monthly_review import MonthlyReview
    prev_reviews = (
        db.query(MonthlyReview)
        .filter_by(idea_id=idea.id)
        .order_by(MonthlyReview.review_date.desc())
        .limit(5)
        .all()
    )
    previous_reviews = [
        {
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "decision": r.decision.value if hasattr(r.decision, "value") else str(r.decision),
            "reasoning": r.reasoning or "",
        }
        for r in prev_reviews
    ]

    return {
        "idea_name": idea.name,
        "idea_audience": idea.audience or "",
        "idea_problem": idea.problem_statement or "",
        "idea_solution": idea.proposed_solution or "",
        "idea_status": idea.status.value if hasattr(idea.status, "value") else str(idea.status),
        "scores_summary": scores_summary,
        "metrics_summary": {
            "retention": [
                {"key": m["metric_key"], "value": m["latest_value"], "benchmark": m["benchmark_value"]}
                for m in dashboard.get("retention_metrics", [])
            ],
            "economics": [
                {"key": m["metric_key"], "value": m["latest_value"]}
                for m in dashboard.get("economics_metrics", [])
            ],
        },
        "trigger_states": trigger_states,
        "recent_evidence": recent_evidence,
        "previous_reviews": previous_reviews,
    }


def handle_generate_summary(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Generate review summary using Claude."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "gather_metrics" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("gather_metrics step must complete first")

    data = prev_step.output_data

    result = asyncio.run(generate_review_summary(
        idea_name=data["idea_name"],
        idea_audience=data["idea_audience"],
        idea_problem=data["idea_problem"],
        idea_solution=data["idea_solution"],
        idea_status=data["idea_status"],
        scores_summary=data.get("scores_summary"),
        metrics_summary=data.get("metrics_summary"),
        trigger_states=data.get("trigger_states", []),
        recent_evidence=data.get("recent_evidence", []),
        previous_reviews=data.get("previous_reviews", []),
        model=task.model_used,
    ))

    step.tokens_used = result.tokens_used

    return {
        "summary": result.summary,
        "metrics_assessment": result.metrics_assessment,
        "trigger_status": result.trigger_status,
        "key_developments": result.key_developments,
        "open_questions": result.open_questions,
        "model_version": result.model_version,
    }


def handle_review_store_result(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store review summary result."""
    prev_step = next(
        (s for s in task.steps if s.step_name == "generate_summary" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("generate_summary step must complete first")

    return {"stored": True, "review": prev_step.output_data}


# ---------------------------------------------------------------------------
# LaunchPad: provision handlers
# ---------------------------------------------------------------------------


def handle_provision_step(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Dispatch a provision sub-step to the engineering agent."""
    from app.services.engineering_agent import provision_project
    # The engineering agent's provision_project drives its own step tracking.
    # For the runner, we delegate to the matching stub handler by step name.
    launch_id = task.launch_id or (task.input_params or {}).get("launch_id")
    step_name = step.step_name
    logger.info("Provision step '%s' for launch=%s", step_name, launch_id)

    # Map step names to stub handlers
    from app.services import engineering_agent as eng
    handler_map = {
        "create_github_repo": eng._provision_github_repo,
        "provision_neon_db": eng._provision_neon_db,
        "configure_render": eng._provision_render_service,
        "setup_resend": eng._provision_resend,
        "create_stripe_product": eng._provision_stripe_product,
        "write_env_files": eng._provision_env_files,
    }
    handler = handler_map.get(step_name)
    if handler is None:
        raise NotImplementedError(f"No provision handler for step '{step_name}'")
    return asyncio.run(handler(db, task))


# ---------------------------------------------------------------------------
# LaunchPad: scaffold handlers
# ---------------------------------------------------------------------------


def handle_scaffold_generate(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Generate project code using Claude. Uses task workdir if available."""
    from app.services.engineering_agent import scaffold_project
    result = asyncio.run(scaffold_project(db, task))
    workdir = (task.input_params or {}).get("workdir")
    if workdir:
        result["workdir"] = workdir
    return result


def handle_scaffold_commit(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Commit generated code to a branch. Stub."""
    launch_id = task.launch_id
    logger.info("STUB: Would commit scaffold to branch for launch=%s", launch_id)
    return {"status": "committed", "branch": f"scaffold-{launch_id[:8]}", "stub": True}


def handle_scaffold_trigger_build(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Trigger a preview build on Render. Stub."""
    launch_id = task.launch_id
    logger.info("STUB: Would trigger preview build for launch=%s", launch_id)
    return {"status": "build_triggered", "stub": True}


# ---------------------------------------------------------------------------
# LaunchPad: deploy handlers
# ---------------------------------------------------------------------------


def handle_deploy_push(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Push to preview. Stub."""
    from app.services.engineering_agent import deploy_to_preview
    return asyncio.run(deploy_to_preview(db, task))


def handle_deploy_smoke(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Run smoke tests on preview. Stub."""
    logger.info("STUB: Would run smoke tests for launch=%s", task.launch_id)
    return {"status": "smoke_passed", "checks": ["health_200", "no_console_errors"], "stub": True}


def handle_deploy_record(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Record deploy event."""
    from app.models.operational_event import OperationalEvent
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="deploy",
        payload={"task_id": task.id, "environment": "preview"},
    )
    db.add(event)
    db.flush()
    return {"event_id": event.id, "event_type": "deploy"}


# ---------------------------------------------------------------------------
# LaunchPad: promote handlers
# ---------------------------------------------------------------------------


class ApprovalRequired(Exception):
    """Raised when a step requires founder approval before it can proceed.

    This is NOT a failure. The runner catches this and pauses the task
    in waiting_for_approval status instead of retrying or dead-lettering.
    """


def _cache_approval_token(task_id: str, raw_token: str, ttl_seconds: int = 86400) -> bool:
    """Store the raw approval token in Redis with a TTL matching the approval expiry.

    This is the fallback token source when email delivery fails or isn't
    configured. Redis is ephemeral (no backup leak risk) and the key
    auto-expires. The API can retrieve it for authenticated users only.
    Returns True if the token was cached successfully.
    """
    try:
        import redis as redis_lib
        from app.config import settings as app_settings
        conn = redis_lib.from_url(app_settings.REDIS_URL)
        conn.setex(f"approval_token:{task_id}", ttl_seconds, raw_token)
        return True
    except Exception:
        logger.exception("Failed to cache approval token in Redis for task=%s", task_id)
        return False


def _send_approval_notification(
    db: Session,
    task: AgentTask,
    raw_token: str,
    artifact_id: str | None = None,
) -> None:
    """Deliver the approval token to the founder.

    Primary channel: email via Resend.
    Fallback: cache in Redis (ephemeral, auto-expires with the token TTL).
    The raw token is NEVER persisted in the database.
    """
    from app.config import settings as app_settings
    from app.services.email_service import send_email
    from app.models.launch_instance import LaunchInstance
    from app.models.idea import Idea

    launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
    idea = db.query(Idea).filter_by(id=launch.idea_id).first() if launch else None
    project_name = idea.name if idea else (task.launch_id or "unknown")[:8]

    email_sent = False
    if app_settings.FOUNDER_EMAIL:
        html = f"""
        <html>
        <body style="font-family:system-ui,sans-serif;color:#e5e7eb;background:#111827;padding:24px;">
          <h2>Approval Required</h2>
          <p><strong>Project:</strong> {project_name}</p>
          <p><strong>Task:</strong> {task.task_type} (task {task.id[:8]}...)</p>
          {f'<p><strong>Artifact:</strong> {artifact_id}</p>' if artifact_id else ''}
          <p><strong>Expires:</strong> {task.approval_expires_at.isoformat() if task.approval_expires_at else 'N/A'}</p>
          <hr style="border-color:#374151;">
          <p>Use this token in the dashboard to approve:</p>
          <pre style="background:#1f2937;padding:12px;border-radius:6px;font-size:14px;word-break:break-all;">{raw_token}</pre>
          <p style="font-size:11px;color:#6b7280;">
            This token is single-use and expires in 24 hours. Do not forward this email.
          </p>
        </body>
        </html>
        """
        msg_id = send_email(
            to=app_settings.FOUNDER_EMAIL,
            subject=f"Approval needed: {task.task_type} for {project_name}",
            html=html,
        )
        email_sent = msg_id is not None

    # Always cache in Redis as a fallback. If email succeeded, the founder
    # uses the email token. If email failed, the dashboard can retrieve
    # the token from Redis via the approval detail endpoint.
    from app.services.approval_service import APPROVAL_TTL_HOURS
    cached = _cache_approval_token(task.id, raw_token, ttl_seconds=APPROVAL_TTL_HOURS * 3600)

    if not email_sent and not cached:
        logger.error(
            "CRITICAL: Approval token for task=%s could not be delivered via email "
            "or cached in Redis. The approval request will be uncompletable.",
            task.id,
        )
    elif not email_sent:
        logger.warning(
            "Email delivery failed for task=%s approval. Token cached in Redis "
            "and available via the dashboard.",
            task.id,
        )


def handle_promote_check(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Check approval status before promoting.

    If not yet approved, creates an approval request and raises
    ApprovalRequired so the runner pauses the task.
    """
    from app.services.approval_service import check_grant, create_approval_request

    # Already explicitly approved
    if task.approval_status == "approved":
        return {"approved": True, "method": "explicit_approval"}

    # Check for a standing grant
    grant = check_grant(db, task.launch_id, "promote")
    if grant:
        task.approval_status = "approved"
        db.flush()
        return {"approved": True, "method": "standing_grant", "grant_id": grant.id}

    # No approval and no grant: create an approval request and pause
    artifact_id = (task.input_params or {}).get("commit_sha")
    raw_token = create_approval_request(db, task, artifact_id=artifact_id)

    # Send the raw token via email only. Never persist raw tokens in the DB
    # (that would defeat the hashed-token security model).
    _send_approval_notification(db, task, raw_token, artifact_id)

    logger.info(
        "Promote task %s requires approval. Token generated (hash stored).",
        task.id,
    )
    raise ApprovalRequired(
        f"Production promotion requires founder approval. "
        f"Approval request created for task {task.id}."
    )


def handle_promote_merge(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Merge branch to main. Stub."""
    logger.info("STUB: Would merge to main for launch=%s", task.launch_id)
    return {"status": "merged", "branch": "main", "stub": True}


def handle_promote_swap(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Swap env to production. Stub."""
    logger.info("STUB: Would swap env to production for launch=%s", task.launch_id)
    return {"status": "env_swapped", "environment": "production", "stub": True}


def handle_promote_record(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Record promotion event."""
    from app.models.operational_event import OperationalEvent
    from app.models.launch_instance import LaunchInstance
    launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
    if launch:
        launch.status = "active"
        launch.production_url = f"https://project-{task.launch_id[:8]}.onrender.com"
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="deploy",
        payload={"task_id": task.id, "environment": "production", "promoted": True},
    )
    db.add(event)
    db.flush()
    return {"event_id": event.id, "production_url": launch.production_url if launch else None}


# ---------------------------------------------------------------------------
# LaunchPad: metrics_collection handlers
# ---------------------------------------------------------------------------


def handle_metrics_query(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Query operational events for metrics aggregation."""
    from datetime import date as date_type
    from app.models.operational_event import OperationalEvent
    launch_id = task.launch_id
    today = date_type.today()
    events = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.created_at >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
        )
        .all()
    )
    return {"event_count": len(events), "date": today.isoformat()}


def handle_metrics_compute(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Compute daily aggregates from events and check for error spikes."""
    from datetime import date as date_type
    from app.services.metrics_collector import collect_daily_metrics
    from app.services.error_spike_detector import check_error_spike
    today = date_type.today()
    metrics = collect_daily_metrics(db, task.launch_id, today)

    # Check for error spike after metrics are computed
    spike = check_error_spike(db, task.launch_id)
    spike_detected = spike is not None

    return {
        "metrics_id": metrics.id,
        "signups": metrics.signups,
        "activation_rate": metrics.activation_rate,
        "revenue_cents": metrics.revenue_cents,
        "error_count": metrics.error_count,
        "error_spike_detected": spike_detected,
    }


def handle_metrics_write(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Confirm metrics were written (already done in compute step)."""
    return {"stored": True}


# ---------------------------------------------------------------------------
# LaunchPad: ceo_nightly handlers
# ---------------------------------------------------------------------------


def handle_ceo_collect(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Collect metrics before CEO evaluation and check for error spikes."""
    from datetime import date as date_type
    from app.services.metrics_collector import collect_daily_metrics
    from app.services.error_spike_detector import check_error_spike
    today = date_type.today()
    try:
        metrics = collect_daily_metrics(db, task.launch_id, today)
        spike = check_error_spike(db, task.launch_id)
        return {
            "metrics_id": metrics.id,
            "date": today.isoformat(),
            "error_spike_detected": spike is not None,
        }
    except Exception as e:
        logger.warning("Metrics collection failed for CEO eval: %s", e)
        return {"error": str(e), "date": today.isoformat()}


def handle_ceo_context(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Build context for CEO evaluation."""
    from app.services.ceo_scheduler import build_ceo_context
    context = build_ceo_context(db, task.launch_id)
    return context


def handle_ceo_evaluate(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Run Claude CEO evaluation and track token usage."""
    from app.services.ceo_scheduler import run_nightly_evaluation
    daily_log, tokens_used = asyncio.run(run_nightly_evaluation(db, task.launch_id, model=task.model_used))

    # Write token usage to the step so the runner's budget enforcement can see it
    step.tokens_used = tokens_used

    return {"daily_log_id": daily_log.id, "date": daily_log.date.isoformat(), "tokens_used": tokens_used}


def handle_ceo_log(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Send the consolidated morning email once all active launches have today's log.

    Each ceo_nightly task calls this as its final step. Only the last task
    to complete (the one that makes the count match) actually sends the
    email. All others return early.
    """
    from app.models.daily_log import DailyLog
    from app.models.launch_instance import LaunchInstance
    from app.services.ceo_scheduler import send_morning_email
    from datetime import date as date_type

    today = date_type.today()

    # How many active launches exist?
    active_count = (
        db.query(LaunchInstance)
        .filter(LaunchInstance.status.in_(["preview", "active"]))
        .count()
    )

    # How many have a DailyLog for today?
    logs_today = (
        db.query(DailyLog)
        .filter_by(date=today)
        .join(LaunchInstance, DailyLog.launch_id == LaunchInstance.id)
        .filter(LaunchInstance.status.in_(["preview", "active"]))
        .all()
    )

    if len(logs_today) < active_count:
        logger.info(
            "DailyLogs for %d/%d active launches, waiting for others before sending email",
            len(logs_today), active_count,
        )
        return {"stored": True, "email_sent": False, "logs_ready": len(logs_today), "total": active_count}

    # All active launches have a log for today. Send the consolidated email.
    msg_id = send_morning_email(logs_today, db)
    return {
        "stored": True,
        "email_sent": bool(msg_id),
        "email_id": msg_id,
        "logs_ready": len(logs_today),
        "total": active_count,
    }


# ---------------------------------------------------------------------------
# Marketing: shared budget check handler
# ---------------------------------------------------------------------------


def handle_marketing_check_budget(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Enforce per-project daily and cross-project monthly budget before marketing spend."""
    from app.services.budget_service import enforce_budget, BudgetExceeded

    launch_id = task.launch_id
    user_id = task.user_id
    if not launch_id:
        raise ValueError("Marketing tasks require a launch_id")

    result = enforce_budget(db, launch_id, user_id)
    return {
        "budget_ok": True,
        "daily_remaining_cents": result["daily"]["remaining_cents"],
        "monthly_remaining_cents": result["monthly"]["remaining_cents"],
    }


# ---------------------------------------------------------------------------
# Marketing: send_cold_emails handlers
# ---------------------------------------------------------------------------


def handle_generate_drafts(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Generate cold email drafts using Claude (Haiku)."""
    from app.services.marketing_agent import draft_cold_emails
    idea = _get_idea(db, task)
    params = task.input_params or {}

    result = asyncio.run(draft_cold_emails(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        prospect_count=params.get("prospect_count", 5),
        model=task.model_used,
    ))

    step.tokens_used = result["tokens_used"]

    return {
        "raw_response": result["raw_response"],
        "tokens_used": result["tokens_used"],
        "model_version": result["model_version"],
        "draft_count": result["draft_count"],
    }


def handle_store_drafts(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store cold email drafts as an operational event for evidence promotion."""
    from app.models.operational_event import OperationalEvent

    prev_step = next(
        (s for s in task.steps if s.step_name == "generate_drafts" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("generate_drafts step must complete first")

    data = prev_step.output_data
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="cold_email_drafted",
        payload={
            "task_id": task.id,
            "draft_count": data["draft_count"],
            "model_version": data["model_version"],
            "tokens_used": data["tokens_used"],
            "raw_response": data["raw_response"][:5000],
        },
    )
    db.add(event)
    db.flush()

    return {"event_id": event.id, "stored": True}


# ---------------------------------------------------------------------------
# Marketing: post_social handlers
# ---------------------------------------------------------------------------


def handle_generate_post(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Generate a social media post draft using Claude (Haiku)."""
    from app.services.marketing_agent import draft_social_post
    idea = _get_idea(db, task)
    params = task.input_params or {}

    result = asyncio.run(draft_social_post(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        platform=params.get("platform", "twitter"),
        milestone=params.get("milestone"),
        model=task.model_used,
    ))

    step.tokens_used = result["tokens_used"]

    return {
        "raw_response": result["raw_response"],
        "tokens_used": result["tokens_used"],
        "model_version": result["model_version"],
        "platform": result["platform"],
    }


def handle_store_post(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store social post draft as an operational event."""
    from app.models.operational_event import OperationalEvent

    prev_step = next(
        (s for s in task.steps if s.step_name == "generate_post" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("generate_post step must complete first")

    data = prev_step.output_data
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="social_post_drafted",
        payload={
            "task_id": task.id,
            "platform": data["platform"],
            "model_version": data["model_version"],
            "tokens_used": data["tokens_used"],
            "raw_response": data["raw_response"][:5000],
        },
    )
    db.add(event)
    db.flush()

    return {"event_id": event.id, "stored": True}


# ---------------------------------------------------------------------------
# Marketing: write_content handlers
# ---------------------------------------------------------------------------


def handle_generate_content(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Generate marketing content using Claude (Sonnet)."""
    from app.services.marketing_agent import write_content
    idea = _get_idea(db, task)
    params = task.input_params or {}

    result = asyncio.run(write_content(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        content_type=params.get("content_type", "blog_post"),
        topic=params.get("topic"),
        model=task.model_used,
    ))

    step.tokens_used = result["tokens_used"]

    return {
        "raw_response": result["raw_response"],
        "tokens_used": result["tokens_used"],
        "model_version": result["model_version"],
        "content_type": result["content_type"],
    }


def handle_store_content(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store generated content as an operational event."""
    from app.models.operational_event import OperationalEvent

    prev_step = next(
        (s for s in task.steps if s.step_name == "generate_content" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("generate_content step must complete first")

    data = prev_step.output_data
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="content_generated",
        payload={
            "task_id": task.id,
            "content_type": data["content_type"],
            "model_version": data["model_version"],
            "tokens_used": data["tokens_used"],
            "raw_response": data["raw_response"][:10000],
        },
    )
    db.add(event)
    db.flush()

    return {"event_id": event.id, "stored": True}


# ---------------------------------------------------------------------------
# Support: triage_inbox handlers
# ---------------------------------------------------------------------------


def handle_support_parse_inbound(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Parse inbound email from task input_params and create/update thread."""
    from app.services.support_agent import get_or_create_thread, add_message_to_thread

    params = task.input_params or {}
    customer_email = params.get("customer_email")
    subject = params.get("subject", "")
    body = params.get("body", "")
    message_id = params.get("message_id")

    if not customer_email or not body:
        raise ValueError("triage_inbox requires customer_email and body in input_params")

    thread = get_or_create_thread(db, task.launch_id, customer_email, subject)
    add_message_to_thread(db, thread, "inbound", body, message_id)

    return {
        "thread_id": thread.id,
        "customer_email": customer_email,
        "subject": subject,
        "body": body[:5000],
        "message_count": thread.message_count,
    }


def handle_support_run_triage(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Run AI triage on the inbound email."""
    from app.services.support_agent import triage_email

    prev_step = next(
        (s for s in task.steps if s.step_name == "parse_inbound" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("parse_inbound step must complete first")

    data = prev_step.output_data
    idea = _get_idea(db, task)

    result = asyncio.run(triage_email(
        subject=data.get("subject", ""),
        body=data.get("body", ""),
        sender_email=data.get("customer_email", ""),
        product_name=idea.name,
        model=task.model_used,
    ))

    step.tokens_used = result["tokens_used"]

    return {
        "thread_id": data["thread_id"],
        "triage": result["triage"],
        "tokens_used": result["tokens_used"],
        "model_version": result["model_version"],
    }


def handle_support_store_triage(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store triage result, update thread, optionally extract feature request."""
    from app.models.operational_event import OperationalEvent
    from app.models.support_thread import SupportThread
    from app.services.support_agent import extract_feature_request, CONFIDENCE_THRESHOLD

    prev_step = next(
        (s for s in task.steps if s.step_name == "run_triage" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("run_triage step must complete first")

    data = prev_step.output_data
    triage = data.get("triage", {})
    thread_id = data["thread_id"]

    thread = db.query(SupportThread).filter_by(id=thread_id).first()
    if thread:
        thread.confidence_score = triage.get("confidence", 0.5)

    # Create operational event for support_received
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="support_received",
        payload={
            "task_id": task.id,
            "thread_id": thread_id,
            "intent": triage.get("intent"),
            "urgency": triage.get("urgency"),
            "confidence": triage.get("confidence"),
            "summary": triage.get("summary"),
        },
    )
    db.add(event)
    db.flush()

    result = {
        "event_id": event.id,
        "thread_id": thread_id,
        "intent": triage.get("intent"),
        "urgency": triage.get("urgency"),
        "confidence": triage.get("confidence"),
    }

    # Extract feature request if detected
    if triage.get("is_feature_request") and thread:
        from app.models.launch_instance import LaunchInstance
        launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
        if launch:
            evidence = extract_feature_request(
                db, thread, launch,
                triage.get("feature_description", triage.get("summary", "")),
            )
            result["feature_request_extracted"] = True
            result["evidence_id"] = evidence.id

    return result


# ---------------------------------------------------------------------------
# Support: draft_support_response handlers
# ---------------------------------------------------------------------------


def handle_support_load_thread(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Load thread history for response drafting."""
    from app.models.support_thread import SupportThread

    params = task.input_params or {}
    thread_id = params.get("thread_id")
    if not thread_id:
        raise ValueError("draft_support_response requires thread_id in input_params")

    thread = db.query(SupportThread).filter_by(id=thread_id).first()
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")

    return {
        "thread_id": thread.id,
        "customer_email": thread.customer_email,
        "subject": thread.subject,
        "messages": thread.messages or [],
        "status": thread.status,
        "message_count": thread.message_count,
    }


def handle_support_draft_response(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Draft a response using AI."""
    from app.services.support_agent import draft_response

    prev_step = next(
        (s for s in task.steps if s.step_name == "load_thread" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("load_thread step must complete first")

    data = prev_step.output_data
    idea = _get_idea(db, task)

    result = asyncio.run(draft_response(
        thread_messages=data.get("messages", []),
        product_name=idea.name,
        product_context=f"{idea.one_liner or ''}. Audience: {idea.audience or 'unknown'}",
        model=task.model_used,
    ))

    step.tokens_used = result["tokens_used"]

    return {
        "thread_id": data["thread_id"],
        "draft": result["draft"],
        "tokens_used": result["tokens_used"],
        "model_version": result["model_version"],
    }


def handle_support_store_draft(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store the drafted response and update thread."""
    from app.models.operational_event import OperationalEvent
    from app.models.support_thread import SupportThread
    from app.services.support_agent import add_message_to_thread, escalate_thread, CONFIDENCE_THRESHOLD

    prev_step = next(
        (s for s in task.steps if s.step_name == "draft_response" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("draft_response step must complete first")

    data = prev_step.output_data
    draft = data.get("draft", {})
    thread_id = data["thread_id"]

    thread = db.query(SupportThread).filter_by(id=thread_id).first()
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")

    # Update thread confidence
    confidence = draft.get("confidence", 0.5)
    thread.confidence_score = confidence

    # Store draft as outbound message (not sent yet, just drafted)
    draft_body = draft.get("draft_response", "")
    add_message_to_thread(db, thread, "outbound", f"[DRAFT] {draft_body}")

    # Check if escalation needed
    needs_escalation = draft.get("needs_escalation", False) or confidence < CONFIDENCE_THRESHOLD
    if needs_escalation and thread.status != "escalated":
        reason = draft.get("escalation_reason") or f"Low confidence ({confidence:.2f})"
        escalate_thread(db, thread, reason)

    # Update thread status
    if not needs_escalation:
        thread.status = "waiting_on_customer"
    thread.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Create operational event
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="support_responded",
        payload={
            "task_id": task.id,
            "thread_id": thread_id,
            "confidence": confidence,
            "escalated": needs_escalation,
            "draft_length": len(draft_body),
            "internal_notes": draft.get("internal_notes"),
        },
    )
    db.add(event)
    db.flush()

    return {
        "event_id": event.id,
        "thread_id": thread_id,
        "confidence": confidence,
        "escalated": needs_escalation,
        "draft_stored": True,
    }


# ---------------------------------------------------------------------------
# Support: check_escalations handlers
# ---------------------------------------------------------------------------


def handle_support_scan_threads(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Scan for threads that have breached the escalation SLA."""
    from app.services.support_agent import check_escalation_sla

    breached = check_escalation_sla(db, task.launch_id)
    return {
        "breached_thread_ids": [t.id for t in breached],
        "breached_count": len(breached),
        "threads": [
            {
                "id": t.id,
                "customer_email": t.customer_email,
                "subject": t.subject,
                "message_count": t.message_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in breached
        ],
    }


def handle_support_flag_breaches(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Flag breached threads as escalated."""
    from app.models.support_thread import SupportThread
    from app.services.support_agent import escalate_thread, ESCALATION_SLA_HOURS

    prev_step = next(
        (s for s in task.steps if s.step_name == "scan_threads" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("scan_threads step must complete first")

    data = prev_step.output_data
    thread_ids = data.get("breached_thread_ids", [])
    escalated = []

    for tid in thread_ids:
        thread = db.query(SupportThread).filter_by(id=tid).first()
        if thread and thread.status != "escalated":
            escalate_thread(db, thread, f"No response within {ESCALATION_SLA_HOURS}h SLA")
            escalated.append(tid)

    return {
        "escalated_count": len(escalated),
        "escalated_thread_ids": escalated,
    }


def handle_support_notify_founder(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Create operational events for escalated threads so the CEO agent picks them up."""
    from app.models.operational_event import OperationalEvent

    prev_step = next(
        (s for s in task.steps if s.step_name == "flag_breaches" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("flag_breaches step must complete first")

    data = prev_step.output_data
    escalated_ids = data.get("escalated_thread_ids", [])

    if not escalated_ids:
        return {"notified": False, "reason": "no_escalations"}

    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="support_escalated",
        payload={
            "task_id": task.id,
            "escalated_thread_ids": escalated_ids,
            "escalated_count": len(escalated_ids),
            "reason": "SLA breach",
        },
    )
    db.add(event)
    db.flush()

    return {
        "event_id": event.id,
        "notified": True,
        "escalated_count": len(escalated_ids),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: dict[tuple[str, str], object] = {
    # community_scan
    ("community_scan", "fetch_posts"): handle_fetch_posts,
    ("community_scan", "analyze_posts"): handle_analyze_posts,
    ("community_scan", "create_evidence"): handle_create_evidence,
    # evidence_synthesis
    ("evidence_synthesis", "gather_evidence"): handle_gather_evidence,
    ("evidence_synthesis", "run_synthesis"): handle_run_synthesis,
    ("evidence_synthesis", "store_result"): handle_synthesis_store_result,
    # consistency_check
    ("consistency_check", "gather_scores"): handle_gather_scores,
    ("consistency_check", "run_check"): handle_run_check,
    ("consistency_check", "store_result"): handle_check_store_result,
    # review_summary
    ("review_summary", "gather_metrics"): handle_gather_metrics,
    ("review_summary", "generate_summary"): handle_generate_summary,
    ("review_summary", "store_result"): handle_review_store_result,
    # LaunchPad: provision
    ("provision", "create_github_repo"): handle_provision_step,
    ("provision", "provision_neon_db"): handle_provision_step,
    ("provision", "configure_render"): handle_provision_step,
    ("provision", "setup_resend"): handle_provision_step,
    ("provision", "create_stripe_product"): handle_provision_step,
    ("provision", "write_env_files"): handle_provision_step,
    # LaunchPad: scaffold
    ("scaffold", "generate_code"): handle_scaffold_generate,
    ("scaffold", "commit_to_branch"): handle_scaffold_commit,
    ("scaffold", "trigger_preview_build"): handle_scaffold_trigger_build,
    # LaunchPad: deploy
    ("deploy", "push_to_preview"): handle_deploy_push,
    ("deploy", "run_smoke_tests"): handle_deploy_smoke,
    ("deploy", "record_deploy_event"): handle_deploy_record,
    # LaunchPad: promote
    ("promote", "check_approval"): handle_promote_check,
    ("promote", "merge_to_main"): handle_promote_merge,
    ("promote", "swap_env"): handle_promote_swap,
    ("promote", "record_promotion"): handle_promote_record,
    # LaunchPad: metrics_collection
    ("metrics_collection", "query_events"): handle_metrics_query,
    ("metrics_collection", "compute_aggregates"): handle_metrics_compute,
    ("metrics_collection", "write_daily_metrics"): handle_metrics_write,
    # LaunchPad: ceo_nightly
    ("ceo_nightly", "collect_metrics"): handle_ceo_collect,
    ("ceo_nightly", "build_context"): handle_ceo_context,
    ("ceo_nightly", "evaluate_state"): handle_ceo_evaluate,
    ("ceo_nightly", "write_daily_log"): handle_ceo_log,
    # Marketing: send_cold_emails
    ("send_cold_emails", "check_budget"): handle_marketing_check_budget,
    ("send_cold_emails", "generate_drafts"): handle_generate_drafts,
    ("send_cold_emails", "store_drafts"): handle_store_drafts,
    # Marketing: post_social
    ("post_social", "check_budget"): handle_marketing_check_budget,
    ("post_social", "generate_post"): handle_generate_post,
    ("post_social", "store_post"): handle_store_post,
    # Marketing: write_content
    ("write_content", "check_budget"): handle_marketing_check_budget,
    ("write_content", "generate_content"): handle_generate_content,
    ("write_content", "store_content"): handle_store_content,
    # Support: triage_inbox
    ("triage_inbox", "parse_inbound"): handle_support_parse_inbound,
    ("triage_inbox", "run_triage"): handle_support_run_triage,
    ("triage_inbox", "store_triage"): handle_support_store_triage,
    # Support: draft_support_response
    ("draft_support_response", "load_thread"): handle_support_load_thread,
    ("draft_support_response", "draft_response"): handle_support_draft_response,
    ("draft_support_response", "store_draft"): handle_support_store_draft,
    # Support: check_escalations
    ("check_escalations", "scan_threads"): handle_support_scan_threads,
    ("check_escalations", "flag_breaches"): handle_support_flag_breaches,
    ("check_escalations", "notify_founder"): handle_support_notify_founder,
}
