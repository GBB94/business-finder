from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import LoginRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email).first()
    if not user or not bcrypt.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_TTL_HOURS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        session = db.query(UserSession).filter_by(id=session_id).first()
        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie(key="session_id", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
