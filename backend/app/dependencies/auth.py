from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.session import UserSession
from app.models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency that extracts the session cookie and returns the authenticated User."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.query(UserSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    if session.expires_at < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter_by(id=session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
