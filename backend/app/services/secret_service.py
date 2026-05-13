"""Per-project secret encryption and retrieval."""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.project_secret import ProjectSecret

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    key = settings.SECRETS_MASTER_KEY
    if not key:
        raise ValueError("SECRETS_MASTER_KEY not configured")
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def upsert_secret(
    db: Session,
    *,
    idea_id: str,
    user_id: str,
    environment: str,
    key_name: str,
    value: str,
) -> ProjectSecret:
    """Insert or update a project secret."""
    existing = (
        db.query(ProjectSecret)
        .filter_by(idea_id=idea_id, environment=environment, key_name=key_name)
        .first()
    )
    if existing:
        existing.encrypted_value = encrypt_value(value)
        db.flush()
        return existing

    secret = ProjectSecret(
        idea_id=idea_id,
        user_id=user_id,
        environment=environment,
        key_name=key_name,
        encrypted_value=encrypt_value(value),
    )
    db.add(secret)
    db.flush()
    return secret


def get_secrets_for_task(
    db: Session,
    idea_id: str,
    user_id: str,
    environment: str = "preview",
    *,
    actor: str = "system",
    task_id: str | None = None,
) -> dict[str, str]:
    """Load and decrypt all secrets for a task execution context."""
    secrets = (
        db.query(ProjectSecret)
        .filter_by(idea_id=idea_id, user_id=user_id, environment=environment)
        .all()
    )
    result = {s.key_name: decrypt_value(s.encrypted_value) for s in secrets}

    if result:
        db.add(AuditLog(
            actor=actor,
            action="secret_accessed",
            resource_type="project_secret",
            details={
                "idea_id": idea_id,
                "environment": environment,
                "keys_read": list(result.keys()),
                "task_id": task_id,
            },
        ))
        db.flush()

    return result
