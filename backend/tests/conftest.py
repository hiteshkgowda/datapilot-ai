"""Shared test fixtures.

Routes are tested via a minimal FastAPI app that includes only the routers
under test, with auth and service dependencies overridden.  This avoids the
full lifespan (SQLite, storage directories, HTTP clients) while still
exercising FastAPI's request/response pipeline and path-parameter validation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import agent, connections, datasets, reports
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser


def _fake_user() -> CurrentUser:
    return CurrentUser(sub="test-sub", email="test@example.com", name="Test User")


@pytest.fixture()
def test_app() -> FastAPI:
    """Minimal app with all route groups registered and auth stubbed out."""
    app = FastAPI()
    app.include_router(datasets.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(connections.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = _fake_user
    return app


@pytest.fixture()
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)
