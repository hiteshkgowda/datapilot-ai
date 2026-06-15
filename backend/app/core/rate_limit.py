"""API rate limiting via slowapi.

Authenticated callers (valid Bearer JWT): 100 requests / hour, keyed by JWT sub.
Anonymous callers (no token or invalid JWT):  20 requests / hour, keyed by client IP.

slowapi calls ``_dynamic_limit(key)`` where ``key`` is the return value of
``_rate_limit_key(request)``.  The ``key`` parameter name is load-bearing:
slowapi inspects the callable's signature and calls it as
``_dynamic_limit(key_func(request))`` only when the parameter is named ``key``.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _rate_limit_key(request: Request) -> str:
    """Return the rate-limit bucket key for this request.

    Returns ``auth:<sub>`` for a request carrying a valid JWT, or
    ``anon:<ip>`` for unauthenticated / invalid-token requests.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            settings = get_settings()
            payload = jwt.decode(
                auth[7:],
                settings.backend_jwt_secret,
                algorithms=["HS256"],
            )
            sub = payload.get("sub")
            if sub:
                return f"auth:{sub}"
        except Exception:
            pass
    ip = request.client.host if request.client else "unknown"
    return f"anon:{ip}"


def _dynamic_limit(key: str) -> str:
    """Return the rate limit string for this bucket.

    slowapi calls this as ``_dynamic_limit(key_func(request))``.
    The parameter name ``key`` is required — slowapi detects it via
    ``inspect.signature`` to decide the calling convention.
    """
    return "100/hour" if key.startswith("auth:") else "20/hour"


limiter = Limiter(key_func=_rate_limit_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                f"Rate limit exceeded: {exc.detail}. "
                "Authenticated users: 100 requests/hour. "
                "Anonymous users: 20 requests/hour."
            ),
        },
        headers={"Retry-After": "3600"},
    )
