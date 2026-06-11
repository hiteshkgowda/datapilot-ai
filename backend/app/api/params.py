"""Reusable FastAPI path-parameter annotations.

All resource IDs in this API are 32-character lowercase hex strings
(UUID without dashes, generated via ``uuid.uuid4().hex``).

Using a single ``Annotated`` alias for every path parameter means:
  - The regex is defined once and can be tightened without touching routes.
  - FastAPI returns HTTP 422 before any auth or service code runs when an
    ID does not match, preventing path-traversal and injection attempts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path

# 32 lowercase hex chars — the canonical format for all resource IDs.
HexId = Annotated[
    str,
    Path(
        pattern=r"^[a-f0-9]{32}$",
        description="32-character lowercase hex resource identifier.",
        min_length=32,
        max_length=32,
    ),
]
