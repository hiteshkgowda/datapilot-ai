"""CRUD operation routes (Phase 7).

Routes:
    POST /crud/preview                 — plan + validate, return preview
    POST /crud/execute                 — execute a confirmed plan
    POST /crud/rollback                — restore a pre-image snapshot
    GET  /crud/audit/{connection_id}   — list recent audit entries
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_crud_service
from app.core.auth import get_current_user
from app.core.exceptions import (
    ConfirmationError,
    CrudExecutionError,
    LLMError,
    RollbackError,
    ValidationError,
)
from app.schemas.auth import CurrentUser
from app.schemas.crud import (
    AuditListResponse,
    CrudExecuteRequest,
    CrudExecuteResponse,
    CrudPreviewResponse,
    CrudRequest,
    RollbackRequest,
    RollbackResponse,
)
from app.services.crud_service import CrudService

router = APIRouter(prefix="/crud", tags=["crud"])


@router.post(
    "/preview",
    response_model=CrudPreviewResponse,
    summary="Plan and preview a CRUD operation",
)
async def preview_crud(
    request: CrudRequest,
    service: CrudService = Depends(get_crud_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> CrudPreviewResponse:
    """Generate a CrudPlan from a natural-language instruction and return an
    affected-row preview without modifying any data."""
    try:
        return await service.preview(request, user_sub=current_user.sub)
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/execute",
    response_model=CrudExecuteResponse,
    summary="Execute a confirmed CRUD plan",
)
async def execute_crud(
    request: CrudExecuteRequest,
    service: CrudService = Depends(get_crud_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> CrudExecuteResponse:
    """Execute a previously previewed plan. Destructive operations require the
    ``confirmation_token`` returned by /crud/preview."""
    try:
        return await service.execute(request, user_sub=current_user.sub, user_email=current_user.email)
    except ConfirmationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except CrudExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/rollback",
    response_model=RollbackResponse,
    summary="Restore data from a rollback snapshot",
)
def rollback_crud(
    request: RollbackRequest,
    service: CrudService = Depends(get_crud_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> RollbackResponse:
    """Restore the pre-image captured during a previous /crud/execute call."""
    try:
        return service.rollback(request, user_sub=current_user.sub)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RollbackError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/audit/{connection_id}",
    response_model=AuditListResponse,
    summary="List recent CRUD audit entries for a connection",
)
def get_audit(
    connection_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    service: CrudService = Depends(get_crud_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> AuditListResponse:
    try:
        return service.get_audit(connection_id, user_sub=current_user.sub, limit=limit)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
