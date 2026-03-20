"""Ephemeral working directory management for engineering tasks.

Creates task-scoped temp directories for scaffolding and deploy
operations so generated files don't land in the worker's CWD.
Optionally chowns to an unprivileged builder user when
BUILDER_UID/BUILDER_GID are configured (non-zero).

Note: this provides filesystem isolation (separate directory per task,
restricted permissions, auto-cleanup). It does NOT provide process-level
sandboxing. The worker still runs as the same OS user. Full process
isolation (containers, seccomp, etc.) is a future hardening step.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def create_workdir(task_id: str) -> str:
    """Create an ephemeral working directory for a task.

    Returns the absolute path to the created directory.
    The directory name includes a random suffix to prevent collisions
    on task retries.
    """
    suffix = uuid.uuid4().hex[:8]
    workdir = Path(settings.WORKDIR_BASE) / f"task-{task_id[:12]}-{suffix}"
    workdir.mkdir(parents=True, exist_ok=True)

    # Restrict permissions: owner rwx only
    os.chmod(workdir, 0o700)

    # Chown to unprivileged builder user if configured
    if settings.BUILDER_UID > 0:
        try:
            os.chown(workdir, settings.BUILDER_UID, settings.BUILDER_GID)
        except OSError:
            logger.warning(
                "Failed to chown workdir to uid=%d gid=%d (requires root). "
                "Running as current user instead.",
                settings.BUILDER_UID,
                settings.BUILDER_GID,
            )

    logger.info(
        "Created workdir for task=%s at %s (uid=%d gid=%d)",
        task_id[:12],
        workdir,
        settings.BUILDER_UID,
        settings.BUILDER_GID,
    )
    return str(workdir)


def cleanup_workdir(workdir_path: str) -> bool:
    """Remove an ephemeral working directory and all its contents.

    Returns True if cleanup succeeded, False if the directory
    didn't exist or removal failed.
    """
    workdir = Path(workdir_path)

    if not workdir.exists():
        logger.debug("Workdir already gone: %s", workdir_path)
        return False

    # Safety check: only remove dirs under the configured base
    base = Path(settings.WORKDIR_BASE).resolve()
    try:
        workdir.resolve().relative_to(base)
    except ValueError:
        logger.error(
            "Refusing to remove workdir outside base: %s (base: %s)",
            workdir_path,
            base,
        )
        return False

    try:
        shutil.rmtree(workdir)
        logger.info("Cleaned up workdir: %s", workdir_path)
        return True
    except Exception:
        logger.exception("Failed to clean up workdir: %s", workdir_path)
        return False
