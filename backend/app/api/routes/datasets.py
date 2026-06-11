"""Dataset API routes: upload CSV, upload Excel and list datasets."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_dataset_service
from app.api.params import HexId
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, ParseError, ValidationError
from app.schemas.auth import CurrentUser
from app.schemas.dataset import (
    DatasetListResponse,
    DatasetPreview,
    UploadResponse,
)
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post(
    "/upload/csv",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV dataset",
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file to upload."),
    service: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    content = await file.read()
    try:
        metadata = await run_in_threadpool(
            service.save_csv, file.filename or "", content, current_user.sub
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return UploadResponse(message="CSV uploaded successfully.", dataset=metadata)


@router.post(
    "/upload/excel",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an Excel dataset",
)
async def upload_excel(
    file: UploadFile = File(..., description="Excel (.xlsx/.xls) file to upload."),
    service: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    content = await file.read()
    try:
        metadata = await run_in_threadpool(
            service.save_excel, file.filename or "", content, current_user.sub
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return UploadResponse(message="Excel uploaded successfully.", dataset=metadata)


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List datasets owned by the current user",
)
async def list_datasets(
    service: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> DatasetListResponse:
    datasets = await run_in_threadpool(service.list_datasets, current_user.sub)
    return DatasetListResponse(count=len(datasets), datasets=datasets)


@router.get(
    "/{dataset_id}/preview",
    response_model=DatasetPreview,
    summary="Preview a dataset",
)
async def preview_dataset(
    dataset_id: HexId,
    limit: int = Query(10, ge=1, le=100, description="Number of rows to preview."),
    service: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> DatasetPreview:
    try:
        # Ownership is enforced inside list_datasets; for direct access by ID
        # we verify the caller owns the dataset before loading it.
        meta = await run_in_threadpool(service.get_metadata, dataset_id)
        if meta.owner_sub and meta.owner_sub != current_user.sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
        return await run_in_threadpool(service.get_preview, dataset_id, limit)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
