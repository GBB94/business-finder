"""Per-project secret encryption and retrieval."""
from __future__ import annotations

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.models.project_secret import ProjectSecret


def _get_fernet() -> Fernet:
    key = settings.SECRETS_MASTER_KEY
    if not key:
        raise ValueError("SECRETS_MASTER_KEY not configured")
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def get_secrets_for_task(
    db: Session,
    idea_id: str,
    user_id: str,
    environment: str = "preview",
) -> dict[str, str]:
    """Load and decrypt all secrets for a task execution context."""
    secrets = (
        db.query(ProjectSecret)
        .filter_by(idea_id=idea_id, user_id=user_id, environment=environment)
        .all()
    )
    return {s.key_name: decrypt_value(s.encrypted_value) for s in secrets}
