"""FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 8000
from inside the ``backend`` directory.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import (
    get_agent_orchestrator,
    get_connection_service,
    get_crud_service,
    get_forecast_planner,
    get_query_planner,
    set_checkpointer,
)
from app.api.routes import (
    agent,
    chart,
    connections,
    crud,
    datasets,
    forecast,
    query,
    reports,
)
from app.core.config import Settings, get_settings
from app.core.storage import StorageManager

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def _validate_production_secrets(settings: Settings) -> None:
    """Raise RuntimeError if required production secrets are missing.

    Called at startup when APP_ENV=production so the container fails fast
    with a clear error rather than misbehaving silently in production.
    """
    missing: list[str] = []

    if not settings.crud_secret_key:
        missing.append(
            "CRUD_SECRET_KEY — CRUD confirmation tokens will be invalidated on every "
            "restart without a stable secret. Generate with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    if not settings.db_encryption_key:
        missing.append(
            "DB_ENCRYPTION_KEY — stored database credentials cannot be encrypted. "
            "Generate with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    if not settings.backend_jwt_secret:
        missing.append(
            "BACKEND_JWT_SECRET — all authenticated API requests will be rejected without it. "
            "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    if not settings.groq_api_key and settings.llm_provider.lower() != "ollama":
        missing.append(
            "GROQ_API_KEY — LLM_PROVIDER is not 'ollama' but no Groq API key is set."
        )

    if not settings.google_client_id:
        missing.append(
            "GOOGLE_CLIENT_ID — required for Google OAuth (NextAuth). "
            "Obtain from Google Cloud Console → APIs & Services → Credentials."
        )

    if not settings.google_client_secret:
        missing.append(
            "GOOGLE_CLIENT_SECRET — required for Google OAuth (NextAuth). "
            "Obtain from Google Cloud Console → APIs & Services → Credentials."
        )

    if missing:
        lines = "\n  - ".join(missing)
        raise RuntimeError(
            f"Production startup failed — required secrets are not set:\n  - {lines}\n\n"
            "Set these in your deployment platform's secret manager (Render / Railway / Vercel). "
            "Do NOT commit them to .env files."
        )


@asynccontextmanager
async def _checkpointer_ctx(settings: Settings) -> AsyncIterator[None]:
    """Open an AsyncSqliteSaver for the server lifetime and register it.

    Falls back to MemorySaver (sessions not durable) when the package is absent.
    The context manager keeps the aiosqlite connection open across all requests.
    """
    try:
        import aiosqlite  # noqa: PLC0415
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # type: ignore[import]  # noqa: PLC0415
        db_path = str(settings.agent_sessions_dir / "sessions.db")
        # Enable WAL mode before handing the connection to AsyncSqliteSaver.
        # WAL allows concurrent reads alongside the single writer, which reduces
        # "database is locked" errors when multiple uvicorn workers share the file.
        # WAL is a persistent pragma — it only needs to be set once per database
        # file but is safe to re-apply on every startup.
        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.commit()
        await conn.close()
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            set_checkpointer(saver)
            logger.info("Agent sessions: AsyncSqliteSaver at %s (WAL mode)", db_path)
            yield
        return
    except ImportError as exc:
        if settings.is_production:
            raise RuntimeError(
                "Production startup failed — langgraph-checkpoint-sqlite is required "
                "for durable agent sessions but is not installed.\n"
                "Install with: pip install langgraph-checkpoint-sqlite aiosqlite\n"
                "Set APP_ENV=development to allow the MemorySaver fallback locally."
            ) from exc
        logger.warning(
            "Agent sessions: langgraph-checkpoint-sqlite not installed; "
            "using MemorySaver (sessions will not survive restarts). "
            "Install with: pip install langgraph-checkpoint-sqlite aiosqlite"
        )
    yield


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage startup validation, storage checks, and shared HTTP client."""
    settings = get_settings()

    # ── Secret validation (production only) ──────────────────────────────────
    if settings.is_production:
        _validate_production_secrets(settings)
        logger.info(
            "Production mode — docs disabled, CORS restricted to: %s",
            settings.allowed_origins,
        )
    else:
        logger.info(
            "Development mode — docs enabled, CORS origins: %s",
            settings.allowed_origins,
        )

    # ── Storage provisioning ──────────────────────────────────────────────────
    # Create directories first, then probe write access.
    # assert_writable() raises in production, warns in development.
    storage = StorageManager(settings)
    storage.ensure_directories()
    storage.assert_writable()

    if storage.is_ephemeral:
        logger.warning(
            "Storage is EPHEMERAL — no STORAGE_BASE_DIR is set. "
            "Uploaded files, reports, and agent sessions will be lost on redeploy. "
            "Attach a Render Persistent Disk and set STORAGE_BASE_DIR=/data to persist data."
        )

    # Attach to app state so the /health handler can re-use it.
    _app.state.storage = storage

    # ── Persistent SQLite checkpointer + HTTP client ──────────────────────────
    # AsyncSqliteSaver.from_conn_string is an asynccontextmanager; we wrap the
    # entire server lifetime inside it so the aiosqlite connection stays open.
    # set_checkpointer() must be called before get_agent_orchestrator() so the
    # @lru_cache singleton captures the correct (async) checkpointer.
    async with _checkpointer_ctx(settings):
        client = httpx.AsyncClient(timeout=settings.http_client_timeout)
        crud_planner = get_crud_service()._planner
        agent_planner = get_agent_orchestrator()._planner
        for planner in (get_query_planner(), get_forecast_planner(), crud_planner, agent_planner):
            if hasattr(planner, "set_client"):
                planner.set_client(client)
        try:
            yield
        finally:
            await client.aclose()
            get_connection_service().dispose_all()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings: Settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI-powered Universal Data Assistant API.",
        lifespan=lifespan,
        # Disable interactive API docs in production — they expose the full API
        # surface publicly. Set APP_ENV=development to re-enable locally.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # CORS: credentials require an explicit origin list — the wildcard "*" is
    # rejected by all browsers when allow_credentials=True (Fetch spec §3.2.3).
    # Origins are derived from FRONTEND_URL (comma-separated) in config.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(datasets.router, prefix=API_PREFIX)
    app.include_router(query.router, prefix=API_PREFIX)
    app.include_router(chart.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    app.include_router(connections.router, prefix=API_PREFIX)
    app.include_router(forecast.router, prefix=API_PREFIX)
    app.include_router(crud.router, prefix=API_PREFIX)
    app.include_router(agent.router, prefix=API_PREFIX)

    @app.get("/health", tags=["health"], summary="Service health check")
    def health() -> dict[str, Any]:
        """Readiness probe with storage volume status.

        Returns overall status plus per-volume write-access results.
        Load balancers and uptime monitors should check ``status == "ok"``.
        """
        storage_status: dict[str, Any] = {"status": "unknown", "volumes": {}}
        try:
            mgr: StorageManager = app.state.storage
            storage_status = mgr.health_summary()
        except AttributeError:
            # StorageManager not yet attached (e.g. called before lifespan).
            storage_status = {"status": "unavailable"}

        overall = "ok" if storage_status.get("status") == "ok" else "degraded"
        return {
            "status": overall,
            "app": settings.app_name,
            "env": settings.app_env,
            "storage": storage_status,
        }

    return app


app = create_app()
