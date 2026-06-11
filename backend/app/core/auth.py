"""JWT authentication for the FastAPI backend.

The frontend (Next.js / NextAuth) issues a short-lived HS256 JWT signed with
``BACKEND_JWT_SECRET`` (separate from ``NEXTAUTH_SECRET``).  Every protected
route depends on ``get_current_user``, which validates the token and returns a
``CurrentUser`` containing the caller's stable Google ``sub``, ``email``, and
``name``.

Token requirements:
  - Algorithm: HS256
  - Required claims: sub, email, iss="uda-frontend", aud="uda-api"
  - Short-lived: exp enforced by PyJWT
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

_ALGORITHM = "HS256"
_ISSUER = "uda-frontend"
_AUDIENCE = "uda-api"


def _verify_token(token: str, secret: str) -> CurrentUser:
    """Decode and validate a backend JWT.  Raises JWTError on any failure."""
    payload = jwt.decode(
        token,
        secret,
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
        audience=_AUDIENCE,
        options={"require": ["sub", "email", "exp", "iss", "aud", "jti"]},
    )
    return CurrentUser(
        sub=payload["sub"],
        email=payload["email"],
        name=payload.get("name", ""),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """FastAPI dependency that validates the bearer token and returns the caller.

    Returns HTTP 401 when:
      - No Authorization header is present
      - The token is missing, malformed, expired, or has wrong issuer/audience
      - BACKEND_JWT_SECRET is not configured

    The dependency is used directly in route function signatures for routes
    that need user identity, and via ``router = APIRouter(dependencies=[...])``
    for routes that only need auth enforcement.
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise _unauthorized

    secret = settings.backend_jwt_secret
    if not secret:
        logger.error(
            "BACKEND_JWT_SECRET is not set — all authenticated requests will be rejected."
        )
        raise _unauthorized

    try:
        return _verify_token(credentials.credentials, secret)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise _unauthorized
