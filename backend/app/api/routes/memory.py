"""Conversational memory routes.

GET  /memory/context   — return full session context
DELETE /memory/clear   — wipe a session from all storage layers
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_memory_service
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.memory import ConversationContext, MemoryClearResponse
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get(
    "/context",
    response_model=ConversationContext,
    summary="Retrieve full conversation context for a session",
)
async def get_context(
    session_id: str = Query(..., min_length=1, description="Client-generated session UUID"),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationContext:
    """Return all stored turns and a human-readable summary for the session.

    The session is scoped to the authenticated user — you cannot retrieve
    another user's session even if you know the session_id.
    """
    return await memory.get_context(session_id=session_id, user_sub=current_user.sub)


@router.delete(
    "/clear",
    response_model=MemoryClearResponse,
    summary="Clear all turns from a conversation session",
)
async def clear_session(
    session_id: str = Query(..., min_length=1, description="Session to clear"),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> MemoryClearResponse:
    """Delete all turns for the session from L1 cache, Redis, and SQLite.

    The session is scoped to the authenticated user.
    """
    return await memory.clear_session(
        session_id=session_id, user_sub=current_user.sub
    )
