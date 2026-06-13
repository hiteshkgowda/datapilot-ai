"""Enterprise tests — ownership isolation.

Verifies that user A cannot access, list, or modify resources owned by user B.
Tests span: DatasetService, ReportService, and CrudService._assert_conn_owner.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.schemas.report import ReportMetadata
from app.services.crud_service import CrudService
from app.services.dataset_service import DatasetService
from app.services.report_service import ReportService

from tests.helpers import (
    make_audit_logger,
    make_engine,
    make_executor,
    make_products_table,
    make_validator,
    mock_connection_service,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_A = "google-sub-user-a"
_USER_B = "google-sub-user-b"

_CSV_CONTENT = b"name,score\nalice,10\nbob,20\n"
_FILENAME = "data.csv"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        upload_dir=tmp_path / "uploads",
        reports_dir=tmp_path / "reports",
        agent_sessions_dir=tmp_path / "sessions",
        connections_dir=tmp_path / "connections",
        crud_audit_dir=tmp_path / "audit",
        crud_rollback_dir=tmp_path / "rollback",
    )


@pytest.fixture()
def dataset_svc(settings) -> DatasetService:
    return DatasetService(settings)


def _make_report_service(settings, dataset_svc):
    """Minimal ReportService that skips LLM/PDF generation."""
    analytics = MagicMock()
    visualization = MagicMock()
    svc = ReportService(
        dataset_service=dataset_svc,
        analytics=analytics,
        visualization=visualization,
        reports_dir=settings.reports_dir,
        report_version="1.0",
    )
    return svc


def _write_report_metadata(reports_dir: Path, report_id: str, owner_sub: str) -> None:
    """Directly write a ReportMetadata JSON sidecar (bypasses PDF generation)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    meta = ReportMetadata(
        report_id=report_id,
        report_version="1.0",
        generated_at=datetime.now(timezone.utc),
        dataset_id="some-dataset-id",
        dataset_filename="test.csv",
        size_bytes=100,
        deterministic_section_count=2,
        ai_section_count=0,
        download_url=f"/api/v1/reports/{report_id}/download",
        owner_sub=owner_sub,
    )
    # Write sidecar JSON
    (reports_dir / f"{report_id}.json").write_text(
        json.dumps(meta.model_dump(mode="json"), default=str),
        encoding="utf-8",
    )
    # Write stub PDF so get_report_path doesn't raise "not found"
    (reports_dir / f"{report_id}.pdf").write_bytes(b"%PDF-stub")


# ── DatasetService ownership ───────────────────────────────────────────────────


class TestDatasetOwnership:
    def test_owner_sees_own_dataset(self, dataset_svc):
        meta = dataset_svc.save_csv(_FILENAME, _CSV_CONTENT, owner_sub=_USER_A)
        visible = dataset_svc.list_datasets(owner_sub=_USER_A)
        assert any(d.id == meta.id for d in visible)

    def test_other_user_cannot_see_dataset(self, dataset_svc):
        meta = dataset_svc.save_csv(_FILENAME, _CSV_CONTENT, owner_sub=_USER_A)
        visible = dataset_svc.list_datasets(owner_sub=_USER_B)
        assert not any(d.id == meta.id for d in visible)

    def test_pre_auth_dataset_visible_to_all(self, dataset_svc):
        """Datasets with owner_sub='' (pre-auth) must appear for any authenticated user."""
        meta = dataset_svc.save_csv(_FILENAME, _CSV_CONTENT, owner_sub="")
        visible_a = dataset_svc.list_datasets(owner_sub=_USER_A)
        visible_b = dataset_svc.list_datasets(owner_sub=_USER_B)
        assert any(d.id == meta.id for d in visible_a)
        assert any(d.id == meta.id for d in visible_b)

    def test_list_returns_only_own_datasets(self, dataset_svc):
        meta_a = dataset_svc.save_csv("a.csv", _CSV_CONTENT, owner_sub=_USER_A)
        meta_b = dataset_svc.save_csv("b.csv", _CSV_CONTENT, owner_sub=_USER_B)
        visible = dataset_svc.list_datasets(owner_sub=_USER_A)
        ids = {d.id for d in visible}
        assert meta_a.id in ids
        assert meta_b.id not in ids

    def test_two_users_datasets_are_fully_isolated(self, dataset_svc):
        for i in range(3):
            dataset_svc.save_csv(f"a{i}.csv", _CSV_CONTENT, owner_sub=_USER_A)
        for i in range(2):
            dataset_svc.save_csv(f"b{i}.csv", _CSV_CONTENT, owner_sub=_USER_B)
        assert len(dataset_svc.list_datasets(owner_sub=_USER_A)) == 3
        assert len(dataset_svc.list_datasets(owner_sub=_USER_B)) == 2

    def test_empty_owner_list_returns_all(self, dataset_svc):
        """Passing owner_sub='' acts as admin view: returns all datasets."""
        dataset_svc.save_csv("a.csv", _CSV_CONTENT, owner_sub=_USER_A)
        dataset_svc.save_csv("b.csv", _CSV_CONTENT, owner_sub=_USER_B)
        all_datasets = dataset_svc.list_datasets(owner_sub="")
        assert len(all_datasets) >= 2


# ── ReportService ownership ───────────────────────────────────────────────────


class TestReportOwnership:
    def test_owner_sees_own_report(self, settings):
        _write_report_metadata(settings.reports_dir, "aaa000", _USER_A)
        svc = _make_report_service(settings, MagicMock())
        reports = svc.list_reports(owner_sub=_USER_A)
        assert any(r.report_id == "aaa000" for r in reports)

    def test_other_user_cannot_see_report(self, settings):
        _write_report_metadata(settings.reports_dir, "aaa111", _USER_A)
        svc = _make_report_service(settings, MagicMock())
        reports = svc.list_reports(owner_sub=_USER_B)
        assert not any(r.report_id == "aaa111" for r in reports)

    def test_pre_auth_report_visible_to_all(self, settings):
        _write_report_metadata(settings.reports_dir, "pre000", "")
        svc = _make_report_service(settings, MagicMock())
        assert any(r.report_id == "pre000" for r in svc.list_reports(owner_sub=_USER_A))
        assert any(r.report_id == "pre000" for r in svc.list_reports(owner_sub=_USER_B))

    def test_get_report_path_owner_access(self, settings):
        _write_report_metadata(settings.reports_dir, "bbb000", _USER_A)
        svc = _make_report_service(settings, MagicMock())
        path = svc.get_report_path("bbb000", owner_sub=_USER_A)
        assert path.is_file()

    def test_get_report_path_other_user_blocked(self, settings):
        from app.core.exceptions import ReportNotFoundError
        _write_report_metadata(settings.reports_dir, "bbb111", _USER_A)
        svc = _make_report_service(settings, MagicMock())
        with pytest.raises(ReportNotFoundError):
            svc.get_report_path("bbb111", owner_sub=_USER_B)

    def test_get_report_path_missing_raises(self, settings):
        from app.core.exceptions import ReportNotFoundError
        svc = _make_report_service(settings, MagicMock())
        with pytest.raises(ReportNotFoundError):
            svc.get_report_path("does-not-exist", owner_sub=_USER_A)

    def test_list_returns_only_owner_reports(self, settings):
        _write_report_metadata(settings.reports_dir, "own-a-01", _USER_A)
        _write_report_metadata(settings.reports_dir, "own-a-02", _USER_A)
        _write_report_metadata(settings.reports_dir, "own-b-01", _USER_B)
        svc = _make_report_service(settings, MagicMock())
        reports_a = svc.list_reports(owner_sub=_USER_A)
        ids = {r.report_id for r in reports_a}
        assert "own-a-01" in ids
        assert "own-a-02" in ids
        assert "own-b-01" not in ids


# ── CrudService ownership ─────────────────────────────────────────────────────


class TestCrudOwnership:
    def _make_service(self, owner_sub: str, engine, tmp_path):
        conn_svc = mock_connection_service(owner_sub, engine)
        return CrudService(
            planner=MagicMock(),
            validator=make_validator(),
            executor=make_executor(tmp_path / "rb"),
            audit_logger=make_audit_logger(tmp_path / "audit"),
            connection_service=conn_svc,
            dataset_service=MagicMock(),
        )

    def test_owner_can_access_connection(self, tmp_path):
        engine = make_engine()
        svc = self._make_service(_USER_A, engine, tmp_path)
        # Should not raise
        svc._assert_conn_owner("conn-1", _USER_A)

    def test_other_user_blocked_from_connection(self, tmp_path):
        engine = make_engine()
        svc = self._make_service(_USER_A, engine, tmp_path)
        with pytest.raises(ValidationError, match="not found"):
            svc._assert_conn_owner("conn-1", _USER_B)

    def test_empty_caller_sub_bypasses_check(self, tmp_path):
        """Pre-auth context (owner_sub='') must not block access."""
        engine = make_engine()
        svc = self._make_service(_USER_A, engine, tmp_path)
        svc._assert_conn_owner("conn-1", "")  # must not raise

    def test_pre_auth_connection_owner_sub_visible_to_all(self, tmp_path):
        """Connection with owner_sub='' must be accessible by any authenticated user."""
        engine = make_engine()
        svc = self._make_service("", engine, tmp_path)  # no owner
        svc._assert_conn_owner("conn-1", _USER_A)  # must not raise
        svc._assert_conn_owner("conn-1", _USER_B)  # must not raise

    def test_nonexistent_connection_raises(self, tmp_path):
        engine = make_engine()
        conn_svc = MagicMock()
        from app.core.exceptions import ConnectionNotFoundError
        conn_svc._read_record.side_effect = ConnectionNotFoundError("not found")
        svc = CrudService(
            planner=MagicMock(),
            validator=make_validator(),
            executor=make_executor(tmp_path / "rb"),
            audit_logger=make_audit_logger(tmp_path / "audit"),
            connection_service=conn_svc,
            dataset_service=MagicMock(),
        )
        with pytest.raises(ValidationError, match="not found"):
            svc._assert_conn_owner("missing-conn", _USER_A)

    def test_get_audit_enforces_connection_ownership(self, tmp_path):
        engine = make_engine()
        # User A owns the connection
        svc = self._make_service(_USER_A, engine, tmp_path)
        # User B tries to read its audit log
        with pytest.raises(ValidationError):
            svc.get_audit("conn-1", user_sub=_USER_B)

    def test_rollback_enforces_connection_ownership(self, tmp_path):
        from app.schemas.crud import RollbackRequest
        engine = make_engine()
        svc = self._make_service(_USER_A, engine, tmp_path)
        req = RollbackRequest(connection_id="conn-1", rollback_token="anytoken")
        with pytest.raises(ValidationError):
            svc.rollback(req, user_sub=_USER_B)
