from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint

from app.database import Base


class ProjectSecret(Base):
    __tablename__ = "project_secrets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id = Column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    environment = Column(String(20), nullable=False)  # preview, prod
    key_name = Column(String(255), nullable=False)
    encrypted_value = Column(String(2000), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("idea_id", "environment", "key_name", name="uq_secret_idea_env_key"),
    )
