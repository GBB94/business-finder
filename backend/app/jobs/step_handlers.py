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
    """Commit generated scaffold code to a feature branch on GitHub.

    Creates the branch on GitHub from the scaffold output in the workdir,
    then persists the branch name on LaunchInstance so promote knows
    which ref to merge. Falls back to stub mode if GitHub is not configured.
    """
    from app.models.launch_instance import LaunchInstance
    from app.config import settings as app_settings

    launch_id = task.launch_id
    branch_name = f"scaffold-{launch_id[:8]}"

    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()

    if app_settings.GITHUB_TOKEN and launch and launch.github_repo_url:
        import subprocess
        from pathlib import Path

        workdir = (task.input_params or {}).get("workdir")
        repo_url = launch.github_repo_url
        # Use token-authenticated URL for push
        auth_url = repo_url.replace(
            "https://github.com/",
            f"https://x-access-token:{app_settings.GITHUB_TOKEN}@github.com/",
        )

        if workdir and Path(workdir).exists():
            # Clone, create branch, copy scaffold files, commit, push
            clone_dir = Path(workdir) / "_repo"
            subprocess.run(
                ["git", "clone", "--depth=1", auth_url, str(clone_dir)],
                check=True, capture_output=True, timeout=60,
            )
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=clone_dir, check=True, capture_output=True,
            )

            # Copy scaffold output into the repo (skip the _repo dir itself)
            import shutil
            for item in Path(workdir).iterdir():
                if item.name == "_repo":
                    continue
                dest = clone_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            subprocess.run(
                ["git", "add", "-A"],
                cwd=clone_dir, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"scaffold: initial project from template (task {task.id[:8]})"],
                cwd=clone_dir, check=True, capture_output=True,
                env={**__import__("os").environ, "GIT_AUTHOR_NAME": "LaunchPad", "GIT_AUTHOR_EMAIL": "launchpad@system", "GIT_COMMITTER_NAME": "LaunchPad", "GIT_COMMITTER_EMAIL": "launchpad@system"},
            )
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=clone_dir, check=True, capture_output=True, timeout=60,
            )

            logger.info("Pushed scaffold to branch '%s' for launch=%s", branch_name, launch_id)
        else:
            logger.warning("No workdir for scaffold commit, branch '%s' not created on GitHub", branch_name)
    else:
        logger.info("STUB: Would commit scaffold to branch '%s' for launch=%s", branch_name, launch_id)

    # Always persist the branch name so promote can find it
    if launch:
        launch.working_branch = branch_name
        db.flush()

    is_stub = not (app_settings.GITHUB_TOKEN and launch and launch.github_repo_url)
    return {"status": "committed", "branch": branch_name, "stub": is_stub}


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

    Promote is an always-approve task type. The pre-execution gate in
    the task runner already pauses and creates an approval request
    before any steps run. This handler is a safety check: if the task
    somehow reached this step without approval, it raises
    ApprovalRequired. Grants are never checked because promote must
    always require explicit human confirmation.
    """
    from app.services.approval_service import create_approval_request

    if task.approval_status == "approved":
        return {"approved": True, "method": "explicit_approval"}

    # Should not reach here (pre-execution gate handles it), but
    # defend in depth: create an approval request and pause.
    artifact_id = (task.input_params or {}).get("commit_sha")
    raw_token = create_approval_request(db, task, artifact_id=artifact_id)
    _send_approval_notification(db, task, raw_token, artifact_id)

    logger.info(
        "Promote task %s requires approval (safety check). Token generated.",
        task.id,
    )
    raise ApprovalRequired(
        f"Production promotion requires founder approval. "
        f"Approval request created for task {task.id}."
    )


def handle_promote_merge(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Merge the project's working branch into main on GitHub."""
    from app.models.launch_instance import LaunchInstance
    from app.config import settings as app_settings

    launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
    if not launch or not launch.github_repo_url:
        logger.warning("No GitHub repo for launch=%s, skipping merge", task.launch_id)
        return {"status": "skipped", "reason": "no_repo_url"}

    if not app_settings.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not configured, returning stub for launch=%s", task.launch_id)
        return {"status": "merged", "branch": "main", "stub": True}

    from app.services import github_service

    # Extract full_name from URL (e.g. "https://github.com/GBB94/launchpad-abc123" -> "GBB94/launchpad-abc123")
    repo_full_name = "/".join(launch.github_repo_url.rstrip("/").split("/")[-2:])

    # Read the working branch from the launch (set by scaffold commit step).
    # Fall back to input_params for manual overrides.
    head_branch = (
        launch.working_branch
        or (task.input_params or {}).get("branch")
    )
    if not head_branch:
        raise RuntimeError(
            f"Cannot promote launch {task.launch_id}: no working_branch set. "
            f"Did the scaffold commit step run?"
        )

    result = github_service.merge_branch(
        repo_full_name,
        head=head_branch,
        base="main",
        commit_message=f"Promote to production (task {task.id[:8]})",
    )

    logger.info("Merge result for launch=%s: %s", task.launch_id, result["status"])
    return {
        "status": result["status"],
        "sha": result.get("sha"),
        "branch": "main",
    }


def handle_promote_swap(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Swap the Render service's env vars from preview to production credentials.

    Reads the production .env file and pushes those variables to Render.
    This is the key credential isolation step: after this, the service
    uses live Stripe keys, production Neon DB, and production Resend config.
    """
    from app.models.launch_instance import LaunchInstance
    from app.services import env_file_service
    from app.config import settings as app_settings

    launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
    if not launch:
        raise RuntimeError(f"Launch {task.launch_id} not found")

    # Read the production env file (contains live credentials)
    prod_env = env_file_service.read_env_file(
        task.launch_id,
        "production",
        db=db,
        actor="engineering_agent",
        task_type="promote",
    )

    if not launch.render_service_id:
        logger.warning("No Render service_id for launch=%s, skipping env swap", task.launch_id)
        return {
            "status": "env_swapped",
            "environment": "production",
            "keys_updated": list(prod_env.keys()),
            "stub": True,
            "note": "No Render service ID. Env file written but not pushed to Render.",
        }

    if not app_settings.RENDER_API_KEY:
        logger.warning("RENDER_API_KEY not configured, returning stub for launch=%s", task.launch_id)
        return {
            "status": "env_swapped",
            "environment": "production",
            "keys_updated": list(prod_env.keys()),
            "stub": True,
        }

    from app.services import render_service

    # Push production credentials to Render (replaces all env vars)
    result = render_service.update_env_vars(launch.render_service_id, prod_env)

    # Trigger a redeploy so the new env vars take effect
    deploy_result = render_service.trigger_deploy(launch.render_service_id)

    logger.info(
        "Swapped env to production for launch=%s, triggered redeploy %s",
        task.launch_id, deploy_result.get("deploy_id"),
    )
    return {
        "status": "env_swapped",
        "environment": "production",
        "keys_updated": result["keys_updated"],
        "deploy_id": deploy_result.get("deploy_id"),
    }


def handle_promote_record(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Record promotion event and transition launch to active."""
    from app.models.operational_event import OperationalEvent
    from app.models.launch_instance import LaunchInstance
    from app.models.audit_log import AuditLog

    launch = db.query(LaunchInstance).filter_by(id=task.launch_id).first()
    if launch:
        launch.status = "active"
        # Use the preview URL as production URL (same Render service, now
        # running with production credentials after env swap)
        if not launch.production_url:
            launch.production_url = launch.preview_url or f"https://project-{task.launch_id[:8]}.onrender.com"

    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="deploy",
        payload={
            "task_id": task.id,
            "environment": "production",
            "promoted": True,
            "production_url": launch.production_url if launch else None,
        },
    )
    db.add(event)

    # Audit: the actual promotion (not just task creation)
    db.add(AuditLog(
        launch_id=task.launch_id,
        actor="engineering_agent",
        action="deploy_promoted",
        resource_type="launch_instance",
        resource_id=task.launch_id,
        details={
            "task_id": task.id,
            "production_url": launch.production_url if launch else None,
        },
    ))

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
# Smartlead reply backfill (called by CEO nightly collect step)
# ---------------------------------------------------------------------------


def _backfill_smartlead_replies(db: Session, launch_id: str, user_id: str) -> int:
    """Poll Smartlead for unread replies and enqueue triage tasks for any missed by webhooks.

    Uses idempotency keys to prevent double-triaging replies already processed
    via the webhook path. Returns the number of new triage tasks enqueued.
    """
    from app.models.marketing_campaign import MarketingCampaign
    from app.models.launch_instance import LaunchInstance
    from app.services import smartlead_service as sl
    from app.services.agent_task_service import create_task
    from app.services.task_enqueue import enqueue_task

    campaigns = (
        db.query(MarketingCampaign)
        .filter_by(launch_id=launch_id)
        .filter(
            MarketingCampaign.status.in_(["active", "paused"]),
            MarketingCampaign.provider_campaign_id.isnot(None),
        )
        .all()
    )

    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        return 0

    # Group campaigns by mailbox (email_account_id) to avoid duplicate API calls
    mailbox_campaigns: dict[str, list] = {}
    for campaign in campaigns:
        acct_id = campaign.smartlead_email_account_id
        if not acct_id:
            continue
        mailbox_campaigns.setdefault(acct_id, []).append(campaign)

    enqueued = 0
    for acct_id, acct_campaigns in mailbox_campaigns.items():
        try:
            campaign_ids = [int(c.provider_campaign_id) for c in acct_campaigns]
            replies = asyncio.run(sl.get_unread_replies(
                int(acct_id), campaign_ids=campaign_ids,
            ))

            # Build a lookup from provider_campaign_id to our campaign
            sl_to_campaign = {c.provider_campaign_id: c for c in acct_campaigns}

            for reply in replies:
                reply_id = reply.get("id") or reply.get("message_id") or ""
                if not reply_id:
                    continue

                # Match reply to campaign via Smartlead campaign_id in the reply
                reply_sl_campaign = str(reply.get("campaign_id") or "")
                campaign = sl_to_campaign.get(reply_sl_campaign) or acct_campaigns[0]

                idem_key = f"triage_reply:{campaign.id}:{reply_id}"
                # Use the same key names the triage handler reads:
                # from_email, reply_body, subject
                task = create_task(
                    db,
                    idea_id=campaign.idea_id,
                    user_id=user_id,
                    task_type="triage_campaign_reply",
                    idempotency_key=idem_key,
                    input_params={
                        "campaign_id": campaign.id,
                        "from_email": (reply.get("from_email") or reply.get("email") or "").lower(),
                        "reply_body": reply.get("body") or reply.get("text") or "",
                        "subject": reply.get("subject") or "",
                        "provider_event_id": str(reply_id),
                        "source": "backfill",
                    },
                )
                task.launch_id = launch_id
                task.agent_type = "marketing"

                if task.status == "queued":
                    if enqueue_task(db, task):
                        enqueued += 1

                # Mark as read on Smartlead to prevent re-fetching
                # mark_reply_read() takes only reply_id (not campaign_id)
                try:
                    asyncio.run(sl.mark_reply_read(int(reply_id)))
                except Exception:
                    pass  # non-critical

        except Exception:
            logger.warning("Reply backfill failed for mailbox %s", acct_id)

    return enqueued


# ---------------------------------------------------------------------------
# LaunchPad: ceo_nightly handlers
# ---------------------------------------------------------------------------


def handle_ceo_collect(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Collect metrics before CEO evaluation, check for error spikes, and
    backfill any Smartlead replies that webhooks may have missed."""
    from datetime import date as date_type
    from app.services.metrics_collector import collect_daily_metrics
    from app.services.error_spike_detector import check_error_spike
    today = date_type.today()

    reply_backfill_count = 0
    try:
        reply_backfill_count = _backfill_smartlead_replies(db, task.launch_id, task.user_id)
    except Exception as e:
        logger.warning("Smartlead reply backfill failed for launch=%s: %s", task.launch_id, e)

    try:
        metrics = collect_daily_metrics(db, task.launch_id, today)
        spike = check_error_spike(db, task.launch_id)
        return {
            "metrics_id": metrics.id,
            "date": today.isoformat(),
            "error_spike_detected": spike is not None,
            "reply_backfill_count": reply_backfill_count,
        }
    except Exception as e:
        logger.warning("Metrics collection failed for CEO eval: %s", e)
        return {"error": str(e), "date": today.isoformat(), "reply_backfill_count": reply_backfill_count}


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
# Provision: Smartlead mailbox + ShellMail inbox
# ---------------------------------------------------------------------------


def handle_provision_smartlead_mailbox(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Register a sending mailbox with Smartlead and store credentials.

    Reads SMTP credentials from ProjectSecret, registers the mailbox
    with Smartlead (warmup enabled), and stores the Smartlead account ID.
    """
    from app.models.project_secret import ProjectSecret
    from app.services.secret_service import decrypt_value, upsert_secret
    from app.services import smartlead_service as sl
    from app.config import settings as app_settings

    launch_id = task.launch_id
    idea_id = task.idea_id
    if not idea_id:
        raise ValueError("Provision task requires an idea_id")

    # Read SMTP credentials from project secrets
    env = (task.input_params or {}).get("environment", "production")

    def _get_secret(key: str) -> str:
        secret = (
            db.query(ProjectSecret)
            .filter_by(idea_id=idea_id, environment=env, key_name=key)
            .first()
        )
        if not secret:
            raise ValueError(f"Missing project secret: {key} (env={env})")
        return decrypt_value(secret.encrypted_value)

    smtp_host = _get_secret("SMTP_HOST") if not app_settings.SMTP_HOST else app_settings.SMTP_HOST
    smtp_port = int(_get_secret("SMTP_PORT")) if not app_settings.SMTP_PORT else app_settings.SMTP_PORT
    smtp_user = _get_secret("SMTP_USERNAME")
    smtp_pass = _get_secret("SMTP_PASSWORD")
    from_email = _get_secret("SENDING_EMAIL")
    from_name = (task.input_params or {}).get("from_name", "Support")

    result = asyncio.run(sl.add_email_account(
        from_name=from_name,
        from_email=from_email,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        username=smtp_user,
        password=smtp_pass,
        warmup_enabled=True,
        warmup_limit=app_settings.WARMUP_EMAILS_PER_DAY,
    ))

    account_id = result.get("id") or result.get("email_account_id")
    if account_id:
        upsert_secret(db, idea_id=idea_id, user_id=task.user_id,
                       environment=env, key_name="SMARTLEAD_EMAIL_ACCOUNT_ID",
                       value=str(account_id))

    return {
        "provider": "smartlead",
        "account_id": account_id,
        "from_email": from_email,
        "warmup_enabled": True,
    }


def handle_provision_shellmail_inbox(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Create a ShellMail support inbox for the project.

    Creates the inbox on ShellMail with our webhook URL, and stores
    the inbox address and ID in ProjectSecret.
    """
    from app.services import shellmail_service as sm
    from app.services.secret_service import upsert_secret
    from app.config import settings as app_settings

    launch_id = task.launch_id
    idea_id = task.idea_id
    if not idea_id:
        raise ValueError("Provision task requires an idea_id")

    env = (task.input_params or {}).get("environment", "production")
    project_name = (task.input_params or {}).get("project_name", f"project-{idea_id[:8]}")
    domain = app_settings.SENDING_ROOT_DOMAIN or "mail.example.com"
    inbox_address = f"support@{project_name}.{domain}"
    webhook_base = (task.input_params or {}).get("webhook_base_url", "")
    webhook_url = f"{webhook_base}/api/webhooks/shellmail" if webhook_base else None

    result = asyncio.run(sm.create_inbox(
        address=inbox_address,
        display_name=f"{project_name} Support",
        webhook_url=webhook_url,
    ))

    inbox_id = result.get("id") or result.get("inbox_id")
    if inbox_id:
        upsert_secret(db, idea_id=idea_id, user_id=task.user_id,
                       environment=env, key_name="SHELLMAIL_SUPPORT_INBOX_ID",
                       value=str(inbox_id))
    upsert_secret(db, idea_id=idea_id, user_id=task.user_id,
                   environment=env, key_name="SHELLMAIL_SUPPORT_ADDRESS",
                   value=inbox_address)

    return {
        "provider": "shellmail",
        "inbox_id": inbox_id,
        "inbox_address": inbox_address,
        "webhook_url": webhook_url,
    }


# ---------------------------------------------------------------------------
# Marketing: shared budget check handler
# ---------------------------------------------------------------------------


def handle_marketing_check_budget(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Enforce outbound pause and budget before marketing spend.

    Checks two gates in order:
    1. Outbound pause: if the project's bounce rate exceeded the threshold,
       all outbound email is blocked until manually unpaused.
    2. Budget: per-project daily and cross-project monthly caps.
    """
    from app.services.bounce_detector import is_outbound_paused
    from app.services.budget_service import enforce_budget, BudgetExceeded

    launch_id = task.launch_id
    user_id = task.user_id
    if not launch_id:
        raise ValueError("Marketing tasks require a launch_id")

    # Gate 1: bounce rate pause
    if is_outbound_paused(db, launch_id):
        from app.models.launch_instance import LaunchInstance
        from app.services.bounce_detector import OutboundPausedError
        launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
        reason = launch.outbound_pause_reason if launch else "unknown"
        raise OutboundPausedError(
            f"Outbound email is paused for this project: {reason}. "
            f"Review bounce logs and unpause from the dashboard before retrying."
        )

    # Gate 2: budget enforcement
    result = enforce_budget(db, launch_id, user_id)
    return {
        "budget_ok": True,
        "outbound_paused": False,
        "daily_remaining_cents": result["daily"]["remaining_cents"],
        "monthly_remaining_cents": result["monthly"]["remaining_cents"],
    }


# ---------------------------------------------------------------------------
# Marketing: activate_campaign handlers
# ---------------------------------------------------------------------------


def handle_activate_bind_mailbox(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Load the provisioned SMARTLEAD_EMAIL_ACCOUNT_ID and bind it to the campaign.

    Smartlead is mailbox-centric: campaigns cannot send without a bound
    sending account. This step reads the account ID from ProjectSecret
    (written by handle_provision_smartlead_mailbox) and attaches it.
    """
    from app.models.project_secret import ProjectSecret
    from app.services.secret_service import decrypt_value
    from app.services import smartlead_service as sl
    from app.models.marketing_campaign import MarketingCampaign

    params = task.input_params or {}
    campaign_id = params.get("campaign_id")
    if not campaign_id:
        raise ValueError("activate_campaign task requires campaign_id in input_params")

    campaign = db.query(MarketingCampaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    idea_id = task.idea_id or campaign.idea_id
    env = params.get("environment", "production")

    # Load SMARTLEAD_EMAIL_ACCOUNT_ID from project secrets
    secret = (
        db.query(ProjectSecret)
        .filter_by(idea_id=idea_id, environment=env, key_name="SMARTLEAD_EMAIL_ACCOUNT_ID")
        .first()
    )
    if not secret:
        raise ValueError(
            f"No SMARTLEAD_EMAIL_ACCOUNT_ID found in project secrets for idea={idea_id} env={env}. "
            f"Run the provision task with setup_smartlead_mailbox first."
        )

    account_id = int(decrypt_value(secret.encrypted_value))

    # Store the account ID on the campaign so push_to_smartlead can bind
    # it after creating the Smartlead campaign but before starting it.
    campaign.smartlead_email_account_id = str(account_id)
    db.commit()

    return {
        "smartlead_account_id": account_id,
        "campaign_id": campaign_id,
    }


def handle_activate_verify_compliance(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Verify all 8 compliance checklist flags before activation.

    Fails the step (and therefore the task) if any flag is missing,
    if cold_email_allowed is False, or if no mailbox is bound.
    """
    from app.services.marketing_agent import run_cold_email_campaign

    params = task.input_params or {}
    campaign_id = params.get("campaign_id")
    if not campaign_id:
        raise ValueError("activate_campaign task requires campaign_id in input_params")

    result = asyncio.run(run_cold_email_campaign(db, campaign_id))
    if not result["ready"]:
        raise ValueError(
            "Campaign failed compliance verification: " + "; ".join(result["errors"])
        )

    return result


def handle_activate_push_to_smartlead(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Create the Smartlead campaign, bind mailbox, upload leads, and start sending.

    Order: create campaign -> bind mailbox -> upload leads -> start campaign.
    The mailbox MUST be bound before the campaign starts.
    """
    from app.services.marketing_agent import activate_campaign_on_smartlead
    from app.services import smartlead_service as sl
    from app.models.marketing_campaign import MarketingCampaign

    params = task.input_params or {}
    campaign_id = params.get("campaign_id")
    sequences = params.get("sequences", [])
    if not campaign_id:
        raise ValueError("activate_campaign task requires campaign_id in input_params")

    # Read the account ID stored by bind_mailbox on the campaign
    campaign = db.query(MarketingCampaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    account_id = campaign.smartlead_email_account_id
    if not account_id:
        raise ValueError(
            "No smartlead_email_account_id on campaign. "
            "The bind_mailbox step must complete first."
        )

    # activate_campaign_on_smartlead creates the campaign, saves sequences,
    # uploads leads, but we intercept BEFORE it starts the campaign so we
    # can bind the mailbox first.
    result = asyncio.run(activate_campaign_on_smartlead(
        db, campaign_id, sequences, skip_start=True,
    ))

    # Bind the mailbox BEFORE starting the campaign
    sl_campaign_id = result.get("provider_campaign_id")
    if not sl_campaign_id:
        raise RuntimeError("activate_campaign_on_smartlead did not return provider_campaign_id")

    asyncio.run(sl.add_email_account_to_campaign(int(sl_campaign_id), int(account_id)))

    # NOW start the campaign
    asyncio.run(sl.update_campaign_status(int(sl_campaign_id), "START"))

    # Update local status
    campaign.status = "active"
    db.commit()

    result["status"] = "active"
    return result


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
# Marketing: triage_campaign_reply handlers
# ---------------------------------------------------------------------------


def handle_classify_reply(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Classify a cold outreach reply by intent using Claude Haiku.

    Intent categories:
    - interested: wants to learn more, asks about pricing, requests demo
    - objection: not now, wrong timing, not relevant
    - unsubscribe: explicit opt-out request
    - out_of_office: auto-reply, OOO
    """
    import anthropic
    from app.config import settings

    params = task.input_params or {}
    from_email = params.get("from_email", "")
    reply_body = params.get("reply_body", "")
    subject = params.get("subject", "")

    model = task.model_used or settings.CLAUDE_MODEL_HAIKU
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Classify this cold email reply by intent. Return JSON with "
                "'intent' (one of: interested, objection, unsubscribe, out_of_office) "
                "and 'confidence' (0.0-1.0) and 'summary' (one sentence).\n\n"
                f"From: {from_email}\n"
                f"Subject: {subject}\n"
                f"Body:\n{reply_body[:2000]}\n\n"
                "JSON only, no explanation."
            ),
        }],
    )

    step.tokens_used = response.usage.input_tokens + response.usage.output_tokens

    import json
    try:
        result = json.loads(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        result = {"intent": "objection", "confidence": 0.5, "summary": "Could not parse reply"}

    return {
        "intent": result.get("intent", "objection"),
        "confidence": result.get("confidence", 0.5),
        "summary": result.get("summary", ""),
        "from_email": from_email,
        "tokens_used": step.tokens_used,
    }


def handle_reply_execute_action(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Execute the action for a classified campaign reply.

    - interested: flag as qualified lead, promote reply to IdeaScope evidence
    - objection: log, do not escalate
    - unsubscribe: add to suppression list, update prospect status
    - out_of_office: ignore, do not create thread
    """
    prev_step = next(
        (s for s in task.steps if s.step_name == "classify_reply" and s.status == "completed"),
        None,
    )
    if not prev_step or not prev_step.output_data:
        raise ValueError("classify_reply step must complete first")

    classification = prev_step.output_data
    intent = classification.get("intent", "objection")
    from_email = classification.get("from_email", "")
    params = task.input_params or {}
    campaign_id = params.get("campaign_id")

    action_taken = intent  # default

    if intent == "unsubscribe" and from_email:
        from app.services.suppression_service import add_suppression
        add_suppression(
            db,
            user_id=task.user_id,
            email=from_email,
            reason="unsubscribe",
            source_provider="smartlead",
            source_campaign_id=campaign_id,
        )
        db.commit()
        action_taken = "unsubscribed_and_suppressed"

    if intent == "interested" and from_email and campaign_id:
        # Mark prospect as qualified for evidence promotion
        from app.models.campaign_prospect import CampaignProspect
        prospect = (
            db.query(CampaignProspect)
            .filter_by(campaign_id=campaign_id, email=from_email)
            .first()
        )
        if prospect:
            prospect.reply_promoted_to_evidence = True
            db.commit()
        action_taken = "flagged_as_qualified"

    return {
        "intent": intent,
        "action_taken": action_taken,
        "from_email": from_email,
        "campaign_id": campaign_id,
    }


def handle_reply_store_result(db: Session, task: AgentTask, step: AgentTaskStep, input_data: dict | None) -> dict:
    """Store campaign reply classification as an OperationalEvent."""
    from app.models.operational_event import OperationalEvent

    classify_step = next(
        (s for s in task.steps if s.step_name == "classify_reply" and s.status == "completed"),
        None,
    )
    action_step = next(
        (s for s in task.steps if s.step_name == "execute_action" and s.status == "completed"),
        None,
    )

    classification = classify_step.output_data if classify_step else {}
    action = action_step.output_data if action_step else {}

    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="campaign_reply_triaged",
        payload={
            "task_id": task.id,
            "intent": classification.get("intent"),
            "confidence": classification.get("confidence"),
            "summary": classification.get("summary"),
            "action_taken": action.get("action_taken"),
            "from_email": action.get("from_email"),
            "campaign_id": action.get("campaign_id"),
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
    shellmail_thread_id = params.get("shellmail_thread_id")

    if not customer_email or not body:
        raise ValueError("triage_inbox requires customer_email and body in input_params")

    thread = get_or_create_thread(db, task.launch_id, customer_email, subject)
    add_message_to_thread(db, thread, "inbound", body, message_id, shellmail_thread_id=shellmail_thread_id)

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

    # Store the draft as a "draft" direction so it does not look like an
    # actual outbound reply.  Using direction="outbound" would make the
    # SLA timer think we already responded and stop escalation scanning.
    # Phase 3 is draft-only: the founder reviews and sends manually.
    draft_body = draft.get("draft_response", "")
    add_message_to_thread(db, thread, "draft", f"{draft_body}")

    # Check if escalation needed
    needs_escalation = draft.get("needs_escalation", False) or confidence < CONFIDENCE_THRESHOLD
    if needs_escalation and thread.status != "escalated":
        reason = draft.get("escalation_reason") or f"Low confidence ({confidence:.2f})"
        escalate_thread(db, thread, reason)

    # Phase 3 is draft-only (human sends). Do NOT flip to waiting_on_customer
    # here because the customer has not actually received a response yet.
    # The thread stays open so it remains visible to SLA scanning and
    # portfolio counts. Status transitions to waiting_on_customer will be
    # added when the send step is implemented.
    thread.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Create operational event. Use "support_draft_created" (not
    # "support_responded") because Phase 3 is draft-only. The customer
    # has not received anything yet. "support_responded" should only be
    # emitted when a response is actually sent (future send step).
    event = OperationalEvent(
        launch_id=task.launch_id,
        event_type="support_draft_created",
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
    ("provision", "setup_smartlead_mailbox"): handle_provision_smartlead_mailbox,
    ("provision", "setup_shellmail_inbox"): handle_provision_shellmail_inbox,
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
    # Marketing: activate_campaign
    ("activate_campaign", "check_budget"): handle_marketing_check_budget,
    ("activate_campaign", "bind_mailbox"): handle_activate_bind_mailbox,
    ("activate_campaign", "verify_compliance"): handle_activate_verify_compliance,
    ("activate_campaign", "push_to_smartlead"): handle_activate_push_to_smartlead,
    # Marketing: triage_campaign_reply
    ("triage_campaign_reply", "classify_reply"): handle_classify_reply,
    ("triage_campaign_reply", "execute_action"): handle_reply_execute_action,
    ("triage_campaign_reply", "store_result"): handle_reply_store_result,
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
    # Marketing: provision_marketing (separate from core provision)
    ("provision_marketing", "setup_smartlead_mailbox"): handle_provision_smartlead_mailbox,
    ("provision_marketing", "setup_shellmail_inbox"): handle_provision_shellmail_inbox,
}
