"""Session-bound CSRF protection middleware for FastAPI.

How it works:
1. On login, the auth router sets a `csrf_token` cookie (readable by JS)
   containing HMAC-SHA256(session_id, CSRF_SECRET).
2. The frontend reads the cookie and sends it as the X-CSRF-Token header.
3. For state-changing requests (POST, PATCH, PUT, DELETE), this middleware
   recomputes HMAC-SHA256(session_id, CSRF_SECRET) from the session cookie
   and verifies it matches the X-CSRF-Token header.
4. Safe methods (GET, HEAD, OPTIONS) are exempt.
5. Paths explicitly listed in CSRF_EXEMPT_PATHS skip validation.

This is stronger than plain double-submit cookie: an attacker who can
inject cookies (e.g. via a sibling subdomain) still cannot forge a valid
token without knowing CSRF_SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Paths that skip CSRF validation (login needs to work without a token)
CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/api/webhooks/resend",
    "/api/webhooks/stripe",
}


def generate_csrf_token(session_id: str) -> str:
    """Generate a CSRF token tied to the given session ID."""
    secret = _get_secret()
    return hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()


def _get_secret() -> str:
    """Return the CSRF signing secret, falling back to SESSION_SECRET_KEY."""
    return settings.CSRF_SECRET or settings.SESSION_SECRET_KEY


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Safe methods and exempt paths skip validation
        if request.method in SAFE_METHODS:
            return await call_next(request)

        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # No session cookie means no CSRF check needed (the auth
        # dependency will reject the request anyway).
        session_id = request.cookies.get("session_id")
        if not session_id:
            return await call_next(request)

        # Validate: X-CSRF-Token header must match the expected HMAC
        # of the session ID. This is stronger than plain double-submit
        # because an attacker who can inject cookies (e.g. via subdomain)
        # still cannot forge the correct HMAC without CSRF_SECRET.
        header_token = request.headers.get("x-csrf-token")

        if not header_token:
            logger.warning(
                "CSRF token missing in header for path=%s",
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing"},
            )

        expected = generate_csrf_token(session_id)
        if not hmac.compare_digest(expected, header_token):
            logger.warning("CSRF token mismatch on %s", request.url.path)
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token invalid"},
            )

        return await call_next(request)
