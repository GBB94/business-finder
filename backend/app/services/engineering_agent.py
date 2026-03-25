"""Engineering agent for LaunchPad project scaffolding and deployment."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_task import AgentTask, AgentTaskStep
from app.models.audit_log import AuditLog
from app.services import approval_service, env_file_service
from app.services.agent_task_service import complete_step, fail_step, start_step

logger = logging.getLogger(__name__)


def _log_audit(
    db: Session,
    launch_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
) -> None:
    """Write an audit log entry for an engineering action."""
    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=launch_id,
        actor="engineering_agent",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(audit)
    db.flush()


def _get_step(task: AgentTask, step_name: str) -> Optional[AgentTaskStep]:
    """Find a step by name on a task."""
    for step in task.steps:
        if step.step_name == step_name:
            return step
    return None


async def scaffold_project(db: Session, task: AgentTask) -> dict:
    """Use Claude to generate project scaffolding code.

    This is a stub implementation. The actual Claude code generation
    will be integrated when the GitHub API layer is ready.
    """
    import anthropic

    launch_id = task.launch_id
    idea_desc = (task.input_params or {}).get("idea_description", "No description provided")
    tech_stack = (task.input_params or {}).get("tech_stack", "Next.js + Tailwind + Supabase")

    step = _get_step(task, "generate_code")
    if step:
        start_step(db, step, input_data={"idea_description": idea_desc, "tech_stack": tech_stack})

    _log_audit(db, launch_id, "task_created", "scaffold", task.id, {
        "tech_stack": tech_stack,
    })

    try:
        model = task.model_used or settings.CLAUDE_MODEL
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate a project scaffold for the following idea:\n\n"
                        f"Description: {idea_desc}\n"
                        f"Tech Stack: {tech_stack}\n\n"
                        f"Return a JSON object with a 'files' key containing a list of "
                        f"objects with 'path' and 'content' keys representing the files to create."
                    ),
                }
            ],
        )

        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        task.tokens_used = (task.tokens_used or 0) + tokens_used
        task.model_used = model

        # Write generated files to workdir if one was assigned
        workdir = (task.input_params or {}).get("workdir")
        files_written = 0
        if workdir:
            import json
            from pathlib import Path
            try:
                scaffold_json = json.loads(response.content[0].text)
                for file_entry in scaffold_json.get("files", []):
                    file_path = Path(workdir) / file_entry["path"]
                    # Prevent path traversal: ensure file stays within workdir
                    try:
                        file_path.resolve().relative_to(Path(workdir).resolve())
                    except ValueError:
                        logger.warning("Skipping path traversal attempt: %s", file_entry["path"])
                        continue
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(file_entry["content"], encoding="utf-8")
                    files_written += 1
            except (json.JSONDecodeError, KeyError):
                logger.warning("Could not parse scaffold JSON to write files for task=%s", task.id)

        result = {
            "status": "scaffolded",
            "response_length": len(response.content[0].text),
            "tokens_used": tokens_used,
            "files_written": files_written,
            "workdir": workdir,
            "note": "Scaffold generated. GitHub repo creation pending API integration.",
        }

        if step:
            complete_step(db, step, output_data=result)

        logger.info("Scaffolded project for task=%s launch=%s", task.id, launch_id)
        return result

    except Exception as e:
        error_msg = f"Scaffold failed: {str(e)[:500]}"
        if step:
            fail_step(db, step, error_msg)
        _log_audit(db, launch_id, "task_failed", "scaffold", task.id, {"error": error_msg})
        raise


async def deploy_to_preview(db: Session, task: AgentTask) -> dict:
    """Deploy a project to a Render preview environment.

    Stub implementation. Actual Render API integration comes later.
    """
    launch_id = task.launch_id

    step = _get_step(task, "push_to_preview")
    if step:
        start_step(db, step, input_data={"launch_id": launch_id})

    _log_audit(db, launch_id, "provider_mutation", "render_preview", task.id, {
        "action": "deploy_to_preview",
    })

    try:
        # Stub: In production this would call the Render API
        preview_url = f"https://preview-{launch_id[:8]}.onrender.com"

        result = {
            "status": "preview_deployed",
            "preview_url": preview_url,
            "note": "Stub deployment. Render API integration pending.",
        }

        if step:
            complete_step(db, step, output_data=result)

        logger.info("Deployed to preview for task=%s url=%s", task.id, preview_url)
        return result

    except Exception as e:
        error_msg = f"Preview deploy failed: {str(e)[:500]}"
        if step:
            fail_step(db, step, error_msg)
        _log_audit(db, launch_id, "task_failed", "deploy_preview", task.id, {"error": error_msg})
        raise


async def promote_to_production(db: Session, task: AgentTask) -> dict:
    """Promote a preview deployment to production.

    Requires founder approval (approval_status must be "approved").
    Stub implementation. Actual Render API integration comes later.
    """
    launch_id = task.launch_id

    # Check approval before proceeding
    if task.approval_status != "approved":
        # Check for a standing grant
        grant = approval_service.check_grant(db, launch_id, "promote_to_production")
        if grant is None:
            _log_audit(db, launch_id, "task_failed", "promote_production", task.id, {
                "reason": "approval_required",
            })
            raise ValueError(
                "Production promotion requires founder approval. "
                f"Current approval_status: {task.approval_status}"
            )

    step = _get_step(task, "check_approval")
    if step:
        start_step(db, step, input_data={"launch_id": launch_id})

    _log_audit(db, launch_id, "promotion_requested", "render_production", task.id, {
        "action": "promote_to_production",
    })

    try:
        # Stub: In production this would call the Render API
        production_url = f"https://project-{launch_id[:8]}.onrender.com"

        result = {
            "status": "production_deployed",
            "production_url": production_url,
            "note": "Stub promotion. Render API integration pending.",
        }

        if step:
            complete_step(db, step, output_data=result)

        logger.info("Promoted to production for task=%s url=%s", task.id, production_url)
        return result

    except Exception as e:
        error_msg = f"Production promote failed: {str(e)[:500]}"
        if step:
            fail_step(db, step, error_msg)
        _log_audit(db, launch_id, "task_failed", "promote_production", task.id, {"error": error_msg})
        raise


async def provision_project(db: Session, task: AgentTask) -> dict:
    """Full project provisioning: GitHub repo, Neon DB, Render service,
    Resend domain, Stripe product, and env files.

    Each step is recorded as an AgentTaskStep. This is a stub implementation
    with real error handling and audit logging.
    """
    launch_id = task.launch_id
    results: dict = {"steps_completed": [], "steps_failed": []}

    provision_steps = [
        ("create_github_repo", _provision_github_repo),
        ("provision_neon_db", _provision_neon_db),
        ("configure_render", _provision_render_service),
        ("setup_resend", _provision_resend),
        ("create_stripe_product", _provision_stripe_product),
        ("write_env_files", _provision_env_files),
    ]

    _log_audit(db, launch_id, "task_created", "provision", task.id, {
        "step_count": len(provision_steps),
    })

    for step_name, handler in provision_steps:
        step = _get_step(task, step_name)
        if step:
            start_step(db, step)

        try:
            step_result = await handler(db, task)
            results["steps_completed"].append(step_name)

            if step:
                complete_step(db, step, output_data=step_result)

            _log_audit(db, launch_id, "provider_mutation", step_name, task.id, step_result)

        except Exception as e:
            error_msg = f"{step_name} failed: {str(e)[:500]}"
            results["steps_failed"].append({"step": step_name, "error": error_msg})

            if step:
                if step.skippable:
                    step.status = "skipped"
                    step.error_message = error_msg
                    step.completed_at = datetime.now(timezone.utc)
                    db.commit()
                else:
                    fail_step(db, step, error_msg)

            _log_audit(db, launch_id, "task_failed", step_name, task.id, {"error": error_msg})
            logger.error("Provision step %s failed for task=%s: %s", step_name, task.id, error_msg)

            # If a non-skippable step fails, stop provisioning
            if step and not step.skippable:
                break

    logger.info(
        "Provisioning complete for task=%s: %d succeeded, %d failed",
        task.id,
        len(results["steps_completed"]),
        len(results["steps_failed"]),
    )
    return results


# --- Stub provisioning handlers ---
# Each returns a dict describing what was (or would be) created.


async def _provision_github_repo(db: Session, task: AgentTask) -> dict:
    """Create a GitHub repository from the golden path template."""
    from app.services import github_service

    launch_id = task.launch_id
    idea_name = (task.input_params or {}).get("idea_name", "")
    repo_name = f"launchpad-{launch_id[:8]}"

    if not settings.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not configured, returning stub for launch=%s", launch_id)
        return {
            "provider": "github",
            "repo_name": repo_name,
            "repo_url": f"https://github.com/{settings.GITHUB_ORG or 'org'}/{repo_name}",
            "stub": True,
        }

    result = github_service.create_repo_from_template(
        repo_name,
        description=f"LaunchPad project: {idea_name}" if idea_name else "",
    )

    # Store repo URL on the launch instance for future reference
    from app.models.launch_instance import LaunchInstance
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if launch:
        launch.github_repo_url = result["html_url"]
        db.flush()

    return {
        "provider": "github",
        "repo_name": repo_name,
        "repo_url": result["html_url"],
        "clone_url": result["clone_url"],
        "full_name": result["full_name"],
    }


async def _provision_neon_db(db: Session, task: AgentTask) -> dict:
    """Create a Neon project with a preview branch for DB isolation.

    Main branch = production. Preview branch = isolated preview environment.
    Connection URIs for both are stored in the task output and used by
    _provision_env_files to write per-environment .env files.
    """
    from app.services import neon_service

    launch_id = task.launch_id
    project_name = f"launchpad-{launch_id[:8]}"

    if not settings.NEON_API_KEY:
        logger.warning("NEON_API_KEY not configured, returning stub for launch=%s", launch_id)
        db_slug = launch_id[:8].replace("-", "_")
        return {
            "provider": "neon",
            "database_name": f"launchpad_{db_slug}",
            "main_connection_uri": f"postgresql://user:pass@neon.tech/launchpad_{db_slug}",
            "preview_connection_uri": f"postgresql://user:pass@neon.tech/launchpad_{db_slug}?options=endpoint%3Dbranch-preview",
            "stub": True,
        }

    # Step 1: Create the Neon project (gets us the main branch)
    project = neon_service.create_project(project_name)

    # Step 2: Create a preview branch off main
    branch = neon_service.create_branch(project["project_id"], "preview")

    # Store Neon IDs on the launch for later use (env files, branch cleanup)
    from app.models.launch_instance import LaunchInstance
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if launch:
        launch.neon_project_id = project["project_id"]
        launch.neon_preview_branch_id = branch["branch_id"]
        db.flush()

    return {
        "provider": "neon",
        "project_id": project["project_id"],
        "main_branch_id": project["main_branch_id"],
        "main_connection_uri": project["main_connection_uri"],
        "preview_branch_id": branch["branch_id"],
        "preview_connection_uri": branch["connection_uri"],
    }


async def _provision_render_service(db: Session, task: AgentTask) -> dict:
    """Create a Render web service connected to the project's GitHub repo.

    The service auto-deploys from the repo's default branch. Preview env
    vars are set during creation; production credentials are swapped in
    during the promote step.
    """
    from app.services import render_service

    launch_id = task.launch_id
    service_name = f"launchpad-{launch_id[:8]}"

    if not settings.RENDER_API_KEY:
        logger.warning("RENDER_API_KEY not configured, returning stub for launch=%s", launch_id)
        return {
            "provider": "render",
            "service_name": service_name,
            "preview_url": f"https://{service_name}.onrender.com",
            "stub": True,
        }

    # Get the repo URL from the launch instance (set by _provision_github_repo)
    from app.models.launch_instance import LaunchInstance
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    repo_url = launch.github_repo_url if launch else None

    if not repo_url:
        raise RuntimeError(
            f"Cannot create Render service: GitHub repo URL not set on launch {launch_id}. "
            f"Did the create_github_repo step succeed?"
        )

    # Pull preview DB URL from the Neon step output if available
    preview_db_url = None
    for step in task.steps:
        if step.step_name == "provision_neon_db" and step.output_data:
            preview_db_url = step.output_data.get("preview_connection_uri")
            break

    # Build preview env vars so the first Render deploy has credentials
    preview_creds = env_file_service.resolve_credentials("preview")
    render_env_vars = {**preview_creds, "NODE_ENV": "preview"}
    if preview_db_url:
        render_env_vars["DATABASE_URL"] = preview_db_url

    result = render_service.create_web_service(
        service_name,
        repo_url,
        env_vars=render_env_vars,
    )

    # Store the service URL and ID on the launch
    if launch:
        launch.preview_url = result["service_url"]
        launch.render_service_id = result["service_id"]
        db.flush()

    return {
        "provider": "render",
        "service_id": result["service_id"],
        "service_name": service_name,
        "preview_url": result["service_url"],
        "env_keys_set": list(render_env_vars.keys()),
    }


async def _provision_resend(db: Session, task: AgentTask) -> dict:
    """Stub: Configure Resend email domain for the project."""
    launch_id = task.launch_id
    logger.info("STUB: Would configure Resend for launch=%s", launch_id)
    return {
        "provider": "resend",
        "domain": f"mail.project-{launch_id[:8]}.com",
        "stub": True,
    }


async def _provision_stripe_product(db: Session, task: AgentTask) -> dict:
    """Stub: Create Stripe product and price for the project."""
    launch_id = task.launch_id
    logger.info("STUB: Would create Stripe product for launch=%s", launch_id)
    return {
        "provider": "stripe",
        "product_id": f"prod_stub_{launch_id[:8]}",
        "price_id": f"price_stub_{launch_id[:8]}",
        "stub": True,
    }


async def _provision_env_files(db: Session, task: AgentTask) -> dict:
    """Write env files for preview and production with isolated credentials.

    Preview uses Neon branch DB, Stripe test keys, and Resend sandbox.
    Production uses Neon main branch, Stripe live keys, and Resend live.

    Connection URIs come from the provision_neon_db step's output (stored
    in the AgentTaskStep). Falls back to stub URLs if not found.
    """
    launch_id = task.launch_id
    db_slug = launch_id[:8].replace("-", "_")

    # Pull real DB connection URIs from the Neon provisioning step
    preview_db_url = None
    production_db_url = None
    for step in task.steps:
        if step.step_name == "provision_neon_db" and step.output_data:
            preview_db_url = step.output_data.get("preview_connection_uri")
            production_db_url = step.output_data.get("main_connection_uri")
            break

    # Fallback to stub URLs if Neon step didn't produce real URIs
    if not preview_db_url:
        preview_db_url = f"postgresql://user:pass@neon.tech/launchpad_{db_slug}?options=endpoint%3Dbranch-preview"
    if not production_db_url:
        production_db_url = f"postgresql://user:pass@neon.tech/launchpad_{db_slug}"

    # Resolve provider credentials per environment (Stripe, Resend)
    preview_creds = env_file_service.resolve_credentials("preview")
    production_creds = env_file_service.resolve_credentials("production")

    preview_vars = {
        "NODE_ENV": "preview",
        "DATABASE_URL": preview_db_url,
        **preview_creds,
    }
    production_vars = {
        "NODE_ENV": "production",
        "DATABASE_URL": production_db_url,
        **production_creds,
    }

    preview_path = env_file_service.write_env_file(launch_id, "preview", preview_vars)
    production_path = env_file_service.write_env_file(launch_id, "production", production_vars)

    # Sync preview env vars to Render if the service already exists.
    # This ensures the Render deploy has the complete set of credentials
    # even if _provision_render_service ran before this step.
    render_synced = False
    from app.models.launch_instance import LaunchInstance
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if launch and launch.render_service_id and settings.RENDER_API_KEY:
        try:
            from app.services import render_service
            render_service.update_env_vars(launch.render_service_id, preview_vars)
            render_synced = True
            logger.info("Synced preview env vars to Render for launch=%s", launch_id)
        except Exception:
            logger.exception("Failed to sync preview env vars to Render for launch=%s", launch_id)

    logger.info("Wrote env files for launch=%s", launch_id)
    return {
        "preview_env_path": preview_path,
        "production_env_path": production_path,
        "preview_keys": list(preview_vars.keys()),
        "production_keys": list(production_vars.keys()),
        "render_synced": render_synced,
    }
