"""Report routes: generate, list and download PDF reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.dependencies import get_dataset_service, get_report_service
from app.api.params import HexId
from app.core.auth import get_current_user
from app.core.exceptions import (
    DatasetNotFoundError,
    ParseError,
    ReportNotFoundError,
)
from app.schemas.auth import CurrentUser
from app.schemas.report import ReportListResponse, ReportMetadata, ReportRequest
from app.services.dataset_service import DatasetService
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "",
    response_model=ReportMetadata,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a PDF report for a dataset",
)
async def generate_report(
    request: ReportRequest,
    service: ReportService = Depends(get_report_service),
    datasets: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportMetadata:
    # Verify the caller owns the source dataset before generating the report.
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        return await service.generate(request, owner_sub=current_user.sub)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "",
    response_model=ReportListResponse,
    summary="List generated reports",
)
async def list_reports(
    service: ReportService = Depends(get_report_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportListResponse:
    reports = service.list_reports(owner_sub=current_user.sub)
    return ReportListResponse(count=len(reports), reports=reports)


@router.get(
    "/{report_id}/download",
    summary="Download a report PDF",
    response_class=FileResponse,
)
async def download_report(
    report_id: HexId,
    service: ReportService = Depends(get_report_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    try:
        path = service.get_report_path(report_id, owner_sub=current_user.sub)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"report_{report_id}.pdf",
    )
