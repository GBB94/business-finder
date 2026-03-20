"""Per-project .env file management for LaunchPad deployments."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

ENVFILES_DIR = Path("/data/envfiles")
VALID_ENVIRONMENTS = {"preview", "production"}

# Maps task_type to the environment(s) it is allowed to read.
# Tasks not listed here default to preview-only access.
TASK_ENVIRONMENT_ACCESS: dict[str, set[str]] = {
    "provision": {"preview", "production"},   # writes both during setup
    "scaffold": {"preview"},
    "deploy": {"preview"},
    "promote": {"preview", "production"},     # reads preview to copy into production
    "metrics_collection": {"production"},
    "ceo_nightly": {"production"},
}


def _validate_environment(environment: str) -> None:
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError(f"Invalid environment '{environment}'. Must be one of: {VALID_ENVIRONMENTS}")


def get_env_file_path(launch_id: str, environment: str) -> str:
    """Return the canonical path for a project's env file."""
    _validate_environment(environment)
    return str(ENVFILES_DIR / f".env.project-{launch_id}.{environment}")


def write_env_file(launch_id: str, environment: str, env_vars: dict) -> str:
    """Write env vars to a per-project .env file with restricted permissions.

    Returns the file path on success.
    """
    _validate_environment(environment)
    file_path = Path(get_env_file_path(launch_id, environment))

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Build file content
    lines = []
    for key, value in env_vars.items():
        # Quote values that contain spaces or special characters
        escaped_value = str(value).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped_value}"')

    content = "\n".join(lines) + "\n"

    # Write atomically: write to temp then rename
    tmp_path = file_path.with_suffix(f".{environment}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.rename(file_path)
    except Exception:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise

    logger.info("Wrote env file for launch=%s env=%s keys=%d", launch_id, environment, len(env_vars))
    return str(file_path)


def read_env_file(
    launch_id: str,
    environment: str,
    db: Optional[Session] = None,
    actor: str = "system",
    task_type: Optional[str] = None,
) -> dict:
    """Read and parse a project .env file. Returns key-value dict.

    A db session should always be provided so the read is audit-logged.
    Callers that omit db will trigger a warning log.

    When task_type is provided, the environment is checked against
    TASK_ENVIRONMENT_ACCESS. This prevents preview tasks from reading
    production secrets.
    """
    _validate_environment(environment)

    if task_type is not None:
        allowed = TASK_ENVIRONMENT_ACCESS.get(task_type, {"preview"})
        if environment not in allowed:
            raise PermissionError(
                f"Task type '{task_type}' is not allowed to read '{environment}' credentials. "
                f"Allowed environments: {allowed}"
            )
    file_path = Path(get_env_file_path(launch_id, environment))

    if not file_path.exists():
        raise FileNotFoundError(f"Env file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    result: dict[str, str] = {}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Remove surrounding quotes
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        result[key] = value

    # Always audit-log secret reads
    if db is not None:
        audit = AuditLog(
            id=str(uuid.uuid4()),
            launch_id=launch_id,
            actor=actor,
            action="secret_accessed",
            resource_type="env_file",
            resource_id=str(file_path),
            details={"environment": environment, "keys_read": list(result.keys())},
        )
        db.add(audit)
        db.commit()
    else:
        logger.warning(
            "Secret read for launch=%s env=%s was NOT audit-logged (no db session provided)",
            launch_id, environment,
        )

    logger.info("Read env file for launch=%s env=%s keys=%d", launch_id, environment, len(result))
    return result


def resolve_credentials(environment: str) -> dict[str, str]:
    """Return the correct provider credentials for the given environment.

    Preview always gets test/sandbox keys. Production gets live keys.
    This is the single source of truth for credential selection.
    """
    from app.config import settings

    if environment == "preview":
        return {
            "STRIPE_SECRET_KEY": settings.STRIPE_TEST_SECRET_KEY or "sk_test_stub",
            "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY": (
                settings.STRIPE_TEST_PUBLISHABLE_KEY or "pk_test_stub"
            ),
            "RESEND_API_KEY": settings.RESEND_SANDBOX_API_KEY or "re_sandbox_stub",
        }
    elif environment == "production":
        return {
            "STRIPE_SECRET_KEY": settings.STRIPE_LIVE_SECRET_KEY or "sk_live_stub",
            "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY": (
                settings.STRIPE_LIVE_PUBLISHABLE_KEY or "pk_live_stub"
            ),
            "RESEND_API_KEY": settings.RESEND_API_KEY or "re_live_stub",
        }
    else:
        raise ValueError(f"Unknown environment: {environment}")


def delete_env_file(launch_id: str, environment: str) -> bool:
    """Remove a project .env file. Returns True if file was deleted."""
    _validate_environment(environment)
    file_path = Path(get_env_file_path(launch_id, environment))

    if not file_path.exists():
        logger.warning("Attempted to delete non-existent env file: %s", file_path)
        return False

    file_path.unlink()
    logger.info("Deleted env file for launch=%s env=%s", launch_id, environment)
    return True
