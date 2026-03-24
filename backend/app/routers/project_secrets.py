from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.audit_log import AuditLog
from app.models.idea import Idea
from app.models.project_secret import ProjectSecret
from app.models.user import User
from app.schemas.project_secret import (
    ProjectSecretCreate,
    ProjectSecretKeyResponse,
    ProjectSecretValueResponse,
    ProjectSecretListResponse,
)
from app.services.secret_service import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ideas/{idea_id}/secrets", tags=["project-secrets"])


def _get_idea_or_404(idea_id: str, user_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=user_id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=ProjectSecretKeyResponse, status_code=201)
def upsert_secret(
    idea_id: str,
    body: ProjectSecretCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    existing = (
        db.query(ProjectSecret)
        .filter_by(
            idea_id=idea_id,
            user_id=current_user.id,
            environment=body.environment,
            key_name=body.key_name,
        )
        .first()
    )

    if existing:
        existing.encrypted_value = encrypt_value(body.value)
        db.commit()
        db.refresh(existing)
        return ProjectSecretKeyResponse.model_validate(existing)

    secret = ProjectSecret(
        idea_id=idea_id,
        user_id=current_user.id,
        environment=body.environment,
        key_name=body.key_name,
        encrypted_value=encrypt_value(body.value),
    )
    db.add(secret)
    db.commit()
    db.refresh(secret)
    return ProjectSecretKeyResponse.model_validate(secret)


@router.get("", response_model=ProjectSecretListResponse)
def list_secrets(
    idea_id: str,
    environment: str = Query("preview"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    secrets = (
        db.query(ProjectSecret)
        .filter_by(idea_id=idea_id, user_id=current_user.id, environment=environment)
        .order_by(ProjectSecret.key_name)
        .all()
    )
    return ProjectSecretListResponse(
        items=[ProjectSecretKeyResponse.model_validate(s) for s in secrets],
        total=len(secrets),
    )


@router.get("/{key_name}", response_model=ProjectSecretValueResponse)
def get_secret(
    idea_id: str,
    key_name: str,
    environment: str = Query("preview"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    secret = (
        db.query(ProjectSecret)
        .filter_by(
            idea_id=idea_id,
            user_id=current_user.id,
            environment=environment,
            key_name=key_name,
        )
        .first()
    )
    if not secret:
        raise HTTPException(404, f"Secret '{key_name}' not found")

    plaintext = decrypt_value(secret.encrypted_value)

    # Audit-log every secret decryption
    db.add(AuditLog(
        launch_id=None,
        actor="founder",
        action="secret_accessed",
        resource_type="project_secret",
        resource_id=secret.id,
        details={
            "idea_id": idea_id,
            "environment": environment,
            "key_name": key_name,
        },
    ))
    db.commit()

    return ProjectSecretValueResponse(
        key_name=secret.key_name,
        environment=secret.environment,
        value=plaintext,
    )


@router.delete("/{key_name}", status_code=204)
def delete_secret(
    idea_id: str,
    key_name: str,
    environment: str = Query("preview"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    secret = (
        db.query(ProjectSecret)
        .filter_by(
            idea_id=idea_id,
            user_id=current_user.id,
            environment=environment,
            key_name=key_name,
        )
        .first()
    )
    if not secret:
        raise HTTPException(404, f"Secret '{key_name}' not found")

    db.delete(secret)
    db.commit()
