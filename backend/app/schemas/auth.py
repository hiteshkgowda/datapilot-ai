"""Authentication schemas — the identity contract between auth middleware and routes."""

from __future__ import annotations

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """Validated, trusted identity extracted from a bearer token.

    Populated by ``get_current_user`` and injected into route handlers
    that require authentication.  Fields match the claims written by the
    NextAuth ``jwt`` callback.
    """

    sub: str
    """Google user ID — stable across display-name or email changes."""

    email: str
    """Primary email address.  Used for audit logs and display only."""

    name: str = ""
    """Display name — may be empty; never used for access decisions."""
