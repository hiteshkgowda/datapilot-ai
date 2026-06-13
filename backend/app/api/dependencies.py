"""FastAPI dependency providers.

Centralising construction here lets routes depend on abstractions while keeping
wiring in one place. Overriding these in tests swaps real implementations for
fakes without touching route code.

Provider selection
------------------
Groq is selected as primary (with Ollama fallback) when EITHER condition is met:
  - ``LLM_PROVIDER=groq`` is set explicitly, OR
  - ``GROQ_API_KEY`` is present (key presence beats the default provider name).

This means you never need to set both; setting ``GROQ_API_KEY`` alone is enough.
``LLM_PROVIDER=ollama`` (default) with no ``GROQ_API_KEY`` → pure Ollama.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Checkpointer registry
# ---------------------------------------------------------------------------
# AsyncSqliteSaver requires an async context manager (aiosqlite connection),
# so it cannot be opened inside a synchronous @lru_cache factory.  Instead,
# main.py's lifespan() opens the connection, calls set_checkpointer(), and
# then get_agent_orchestrator() picks it up on first call.
#
# Fallback: if set_checkpointer() was never called (tests that bypass lifespan,
# or an environment where the package is unavailable), get_checkpointer()
# returns a fresh MemorySaver so callers always receive a valid object.

_checkpointer: Any = None


def set_checkpointer(cp: Any) -> None:
    """Register the process-wide checkpointer.  Called once from lifespan()."""
    global _checkpointer
    _checkpointer = cp
    logger.info("Agent sessions: checkpointer set to %s", type(cp).__name__)


def get_checkpointer() -> Any:
    """Return the registered checkpointer, or a MemorySaver if none was set."""
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415
        return MemorySaver()
    return _checkpointer
from app.core.crypto import CredentialCipher
from app.services.agent_graph import build_agent_graph
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.agent_planner import (
    FallbackAgentPlanner,
    GroqAgentPlanner,
    OllamaAgentPlanner,
)
from app.services.agent_tools import build_registry
from app.services.analytics_service import AnalyticsService
from app.services.connection_service import ConnectionService
from app.services.crud_audit import JsonlAuditLogger
from app.services.crud_executor import CrudExecutor
from app.services.crud_planner import (
    CrudPlanner,
    FallbackCrudPlanner,
    GroqCrudPlanner,
    OllamaCrudPlanner,
)
from app.services.crud_service import CrudService
from app.services.crud_validator import ConfirmationTokenService, CrudValidator
from app.services.dataset_service import DatasetService
from app.services.forecast_planner import ForecastPlanner, OllamaForecastPlanner
from app.services.forecast_service import ForecastService
from app.services.groq_provider import (
    FallbackForecastPlanner,
    FallbackQueryPlanner,
    GroqForecastPlanner,
    GroqQueryPlanner,
)
from app.services.llm_provider import OllamaQueryPlanner, QueryPlanner
from app.services.anomaly_service import AnomalyDetectionService
from app.services.insight_service import InsightGenerationService
from app.services.memory_service import MemoryService
from app.services.recommendation_service import RecommendationService
from app.services.root_cause_service import RootCauseService
from app.services.report_service import ReportForecastConfig, ReportService
from app.services.sql_executor import SqlExecutor
from app.services.sql_translator import SQLTranslator
from app.services.visualization_service import VisualizationService


# ---------------------------------------------------------------------------
# Provider factories (not cached — called once by the cached wrappers below)
# ---------------------------------------------------------------------------

def _use_groq(settings: Settings) -> bool:
    """Return True if Groq should be used as the primary LLM provider.

    Groq wins when LLM_PROVIDER=groq OR when GROQ_API_KEY is present.
    The key-presence check lets operators add the key without also updating
    LLM_PROVIDER, reducing the chance of a misconfiguration.
    """
    return settings.llm_provider.lower() == "groq" or bool(settings.groq_api_key)


def _make_query_planner(settings: Settings) -> QueryPlanner:
    """Return the correct QueryPlanner implementation for the configured provider."""
    if _use_groq(settings) and settings.groq_api_key:
        return FallbackQueryPlanner(
            primary=GroqQueryPlanner(settings),
            secondary=OllamaQueryPlanner(settings),
        )
    return OllamaQueryPlanner(settings)


def _make_crud_planner(settings: Settings) -> CrudPlanner:
    """Return the correct CrudPlanner implementation for the configured provider."""
    if _use_groq(settings) and settings.groq_api_key:
        return FallbackCrudPlanner(
            primary=GroqCrudPlanner(settings),
            secondary=OllamaCrudPlanner(settings),
        )
    return OllamaCrudPlanner(settings)


def _make_forecast_planner(settings: Settings) -> ForecastPlanner:
    """Return the correct ForecastPlanner implementation for the configured provider."""
    if _use_groq(settings) and settings.groq_api_key:
        return FallbackForecastPlanner(
            primary=GroqForecastPlanner(settings),
            secondary=OllamaForecastPlanner(settings),
        )
    return OllamaForecastPlanner(settings)


# ---------------------------------------------------------------------------
# Cached process-wide singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_connection_service() -> ConnectionService:
    """Provide a process-wide :class:`ConnectionService` instance."""
    settings = get_settings()
    return ConnectionService(settings, CredentialCipher(settings.db_encryption_key))


@lru_cache(maxsize=1)
def get_dataset_service() -> DatasetService:
    """Provide a process-wide :class:`DatasetService` instance."""
    return DatasetService(get_settings(), get_connection_service())


@lru_cache(maxsize=1)
def get_query_planner() -> QueryPlanner:
    """Provide the configured LLM-backed query planner."""
    return _make_query_planner(get_settings())


@lru_cache(maxsize=1)
def get_sql_executor() -> SqlExecutor:
    """Provide a process-wide :class:`SqlExecutor` for SQL pushdown."""
    return SqlExecutor(get_connection_service(), SQLTranslator())


@lru_cache(maxsize=1)
def get_analytics_service() -> AnalyticsService:
    """Provide a process-wide :class:`AnalyticsService` instance."""
    settings = get_settings()
    return AnalyticsService(
        get_dataset_service(),
        get_query_planner(),
        sql_executor=get_sql_executor(),
        scatter_max_points=settings.scatter_max_points,
        pushdown_enabled=settings.db_pushdown_enabled,
    )


@lru_cache(maxsize=1)
def get_visualization_service() -> VisualizationService:
    """Provide a process-wide :class:`VisualizationService` instance."""
    return VisualizationService(get_analytics_service())


@lru_cache(maxsize=1)
def get_forecast_planner() -> ForecastPlanner:
    """Provide the configured forecast planner."""
    return _make_forecast_planner(get_settings())


@lru_cache(maxsize=1)
def get_forecast_service() -> ForecastService:
    """Provide a process-wide :class:`ForecastService` instance."""
    return ForecastService(
        get_dataset_service(), get_forecast_planner(), get_settings()
    )


@lru_cache(maxsize=1)
def get_crud_service() -> CrudService:
    """Provide a process-wide :class:`CrudService` instance."""
    settings = get_settings()
    token_svc = ConfirmationTokenService(
        secret_key=settings.crud_secret_key,
        ttl_seconds=300,
    )
    return CrudService(
        planner=_make_crud_planner(settings),
        validator=CrudValidator(
            max_affected_rows=settings.crud_max_affected_rows,
            confirmation_service=token_svc,
        ),
        executor=CrudExecutor(
            rollback_dir=settings.crud_rollback_dir,
            rollback_ttl_seconds=settings.crud_rollback_ttl_seconds,
            max_rollback_rows=settings.crud_max_rollback_rows,
        ),
        audit_logger=JsonlAuditLogger(settings.crud_audit_dir),
        connection_service=get_connection_service(),
        dataset_service=get_dataset_service(),
    )


def _make_agent_planner(settings: Settings) -> Any:
    """Return the correct AgentPlanner implementation for the configured provider."""
    if _use_groq(settings) and settings.groq_api_key:
        return FallbackAgentPlanner(
            primary=GroqAgentPlanner(settings),
            secondary=OllamaAgentPlanner(settings),
        )
    return OllamaAgentPlanner(settings)


@lru_cache(maxsize=1)
def get_agent_orchestrator() -> AgentOrchestrator:
    """Provide a process-wide :class:`AgentOrchestrator` instance."""
    settings = get_settings()
    planner = _make_agent_planner(settings)
    registry = build_registry(
        dataset_service=get_dataset_service(),
        analytics_service=get_analytics_service(),
        visualization_service=get_visualization_service(),
        forecast_service=get_forecast_service(),
        report_service=get_report_service(),
        crud_service=get_crud_service(),
        anomaly_service=get_anomaly_service(),
        root_cause_service=get_root_cause_service(),
        recommendation_service=get_recommendation_service(),
    )
    graph = build_agent_graph(
        tools=registry,
        planner=planner,
        settings=settings,
        checkpointer=get_checkpointer(),
    )
    return AgentOrchestrator(graph=graph, planner=planner, max_retries=settings.agent_max_retries)


@lru_cache(maxsize=1)
def get_anomaly_service() -> AnomalyDetectionService:
    """Provide a process-wide :class:`AnomalyDetectionService` instance."""
    settings = get_settings()
    return AnomalyDetectionService(
        cache_ttl=settings.anomaly_cache_ttl_seconds,
        cache_max_entries=settings.anomaly_cache_max_entries,
    )


@lru_cache(maxsize=1)
def get_root_cause_service() -> RootCauseService:
    """Provide a process-wide :class:`RootCauseService` instance."""
    from agents.root_cause_agent import RootCauseAgent  # local import — agents/ pkg lives outside app/

    settings = get_settings()
    agent = RootCauseAgent(settings)
    return RootCauseService(
        root_cause_agent=agent,
        cache_ttl=settings.rca_cache_ttl_seconds,
        cache_max_entries=settings.rca_cache_max_entries,
    )


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    """Provide a process-wide :class:`MemoryService` instance."""
    from memory.conversation_store import ConversationStore  # noqa: PLC0415
    from memory.session_memory import SessionMemory  # noqa: PLC0415
    from memory.context_builder import ContextBuilder  # noqa: PLC0415

    settings = get_settings()
    store = ConversationStore(settings.memory_store_dir / "conversations.db")
    session_mem = SessionMemory(
        ttl_seconds=settings.memory_l1_ttl_seconds,
        max_sessions=settings.memory_l1_max_sessions,
        redis_url=settings.redis_url,
        redis_ttl_seconds=settings.memory_session_ttl_seconds,
    )
    return MemoryService(
        store=store,
        session_memory=session_mem,
        context_builder=ContextBuilder(),
        max_turns_per_session=settings.memory_max_turns_per_session,
        max_table_rows=settings.memory_max_table_rows,
        session_ttl_seconds=settings.memory_session_ttl_seconds,
    )


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    """Provide a process-wide :class:`RecommendationService` instance."""
    from agents.recommendation_agent import RecommendationAgent  # local import — avoids circular

    settings = get_settings()
    agent = RecommendationAgent(settings)
    return RecommendationService(
        recommendation_agent=agent,
        cache_ttl=settings.recommendation_cache_ttl_seconds,
        cache_max_entries=settings.recommendation_cache_max_entries,
    )


@lru_cache(maxsize=1)
def get_insight_service() -> InsightGenerationService:
    """Provide a process-wide :class:`InsightGenerationService` instance."""
    from agents.insight_agent import InsightAgent  # local import — agents/ pkg lives outside app/

    settings = get_settings()
    agent = InsightAgent(settings)
    return InsightGenerationService(
        insight_agent=agent,
        cache_ttl=settings.insight_cache_ttl_seconds,
        cache_max_entries=settings.insight_cache_max_entries,
        max_table_rows=settings.insight_max_table_rows,
        top_n=settings.insight_top_n,
        correlation_threshold=settings.insight_correlation_threshold,
    )


@lru_cache(maxsize=1)
def get_report_service() -> ReportService:
    """Provide a process-wide :class:`ReportService` instance."""
    settings = get_settings()
    forecast_config = ReportForecastConfig(
        enabled=settings.forecast_in_reports,
        date_column=settings.forecast_date_column,
        target_column=settings.forecast_target_column,
        frequency=settings.forecast_frequency,
        aggregation=settings.forecast_aggregation,
        horizon=settings.forecast_default_horizon,
    )
    return ReportService(
        get_dataset_service(),
        get_analytics_service(),
        get_visualization_service(),
        reports_dir=settings.reports_dir,
        report_version=settings.report_version,
        forecast_service=get_forecast_service(),
        forecast_config=forecast_config,
    )
