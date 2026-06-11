"""Schemas for report generation (Phase 4).

A report is built from a deterministic battery of analyses plus, optionally,
AI-generated answers to user questions. The two are counted separately so the
distinction is explicit at the API/metadata level (and mirrored in the PDF).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """Incoming request to generate a report."""

    dataset_id: str = Field(..., min_length=1, description="Dataset identifier.")
    questions: list[str] = Field(
        default_factory=list,
        description="Optional natural-language questions. Each adds an "
        "AI-generated (non-deterministic) section.",
    )


class ReportMetadata(BaseModel):
    """Metadata describing a generated report (persisted as a JSON sidecar)."""

    report_id: str = Field(..., description="Unique report identifier.")
    report_version: str = Field(..., description="Report format version.")
    generated_at: datetime = Field(..., description="UTC generation timestamp.")
    dataset_id: str = Field(..., description="Source dataset identifier.")
    dataset_filename: str = Field(..., description="Source dataset file name.")
    size_bytes: int = Field(..., ge=0, description="PDF size in bytes.")
    deterministic_section_count: int = Field(
        ..., ge=0, description="Number of deterministic sections."
    )
    ai_section_count: int = Field(
        ..., ge=0, description="Number of AI-generated sections."
    )
    download_url: str = Field(..., description="Relative URL to download the PDF.")
    owner_sub: str = Field(default="", description="Google sub of the user who generated this report.")


class ReportListResponse(BaseModel):
    """Response when listing generated reports."""

    count: int = Field(..., ge=0)
    reports: list[ReportMetadata] = Field(default_factory=list)
