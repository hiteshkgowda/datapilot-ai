"""Application configuration loaded from environment variables.

All tunable values live here so nothing is hardcoded throughout the code
base. Settings are read from the process environment and an optional ``.env``
file, then cached for the lifetime of the process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Storage fields that STORAGE_BASE_DIR fans out into.
_STORAGE_FIELDS: tuple[str, ...] = (
    "upload_dir",
    "reports_dir",
    "connections_dir",
    "crud_audit_dir",
    "crud_rollback_dir",
    "agent_sessions_dir",
    "memory_store_dir",
    "dashboards_dir",
)


class Settings(BaseSettings):
    """Strongly typed application settings.

    Field names map to upper-cased environment variables, e.g. the
    ``api_port`` field is populated from the ``API_PORT`` variable.
    """

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],  # check project root first, then cwd (backend/)
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Storage base directory (Render Persistent Disk / Railway Volume)
    # ------------------------------------------------------------------ #
    # When set, all six storage paths default to subdirectories under this
    # root unless individually overridden. This is the single env var to
    # set for Render/Railway persistent storage:
    #   STORAGE_BASE_DIR=/data
    # Individual overrides still work:
    #   STORAGE_BASE_DIR=/data   UPLOAD_DIR=/mnt/uploads   (only uploads differ)
    storage_base_dir: Optional[Path] = None

    @model_validator(mode="after")
    def _apply_storage_base_dir(self) -> "Settings":
        """Prepend STORAGE_BASE_DIR to any storage path that is still relative.

        Rule: relative path → base / path.  Absolute path → left unchanged.
        This means individual overrides just need to be absolute to opt out:
            STORAGE_BASE_DIR=/data   UPLOAD_DIR=/mnt/big/uploads   ← absolute, kept
            STORAGE_BASE_DIR=/data   UPLOAD_DIR=uploads             ← relative, → /data/uploads
        """
        if self.storage_base_dir is None:
            return self
        base = self.storage_base_dir
        for field_name in _STORAGE_FIELDS:
            current: Path = getattr(self, field_name)
            if not current.is_absolute():
                object.__setattr__(self, field_name, base / current)
        return self

    # Application
    app_name: str = "Universal Data Assistant"
    # "development" (default) or "production".
    # In production mode the app enforces stricter security:
    #   - /docs and /redoc are disabled
    #   - Required secrets (CRUD_SECRET_KEY, DB_ENCRYPTION_KEY) must be set
    #   - CORS is restricted to FRONTEND_URL only
    app_env: str = "development"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ------------------------------------------------------------------ #
    # Storage paths (all configurable; derive from STORAGE_BASE_DIR above)
    # ------------------------------------------------------------------ #
    upload_dir: Path = Path("uploads")
    max_upload_size_mb: int = 50

    reports_dir: Path = Path("reports")
    report_version: str = "1.0"

    connections_dir: Path = Path("connections")

    crud_audit_dir: Path = Path("crud_audit")
    crud_rollback_dir: Path = Path("crud_rollback")

    # Agent session checkpoints (SqliteSaver writes sessions.db here).
    # Persists interrupted/resumed agent conversations across restarts.
    agent_sessions_dir: Path = Path("agent_sessions")

    # Conversational memory store (conversations.db lives here).
    memory_store_dir: Path = Path("memory_store")

    # AI Executive Dashboard Generator — saved dashboard JSON files.
    dashboards_dir: Path = Path("dashboards")

    # Frontend / CORS
    # In development, localhost:3000 is always allowed.
    # In production, set this to your deployed frontend URL, e.g.:
    #   FRONTEND_URL=https://your-app.vercel.app
    # Multiple origins can be comma-separated:
    #   FRONTEND_URL=https://app.example.com,https://staging.example.com
    frontend_url: str = "http://localhost:3000"

    # Backend self-reference (kept for compat)
    backend_url: str = "http://localhost:8000"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        """CORS allowed origins derived from FRONTEND_URL.

        Always includes localhost:3000 and localhost:8080 in development.
        In production, restricted to the explicit FRONTEND_URL value(s) only.
        """
        origins = [o.strip() for o in self.frontend_url.split(",") if o.strip()]
        if not self.is_production:
            for local in ("http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"):
                if local not in origins:
                    origins.append(local)
        return origins

    # LLM provider selection: "ollama" (default) or "groq"
    # When "groq" is selected the system tries Groq first and falls back to
    # Ollama automatically on any LLMError.
    llm_provider: str = "ollama"

    # Shared LLM HTTP client timeout (used for both Ollama and Groq requests).
    # Ollama local models may need the full 60 s; Groq cloud is typically <5 s.
    # Set OLLAMA_TIMEOUT_SECONDS in .env to tune; the same value applies to Groq.
    llm_timeout_seconds: float = 60.0
    # Back-compat alias: if OLLAMA_TIMEOUT_SECONDS is set it overrides llm_timeout_seconds.
    ollama_timeout_seconds: Optional[float] = None

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Groq (cloud, OpenAI-compatible)
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    @property
    def http_client_timeout(self) -> float:
        """Timeout in seconds for the shared LLM HTTP client.

        Prefer the generic ``LLM_TIMEOUT_SECONDS`` env var.  Falls back to the
        legacy ``OLLAMA_TIMEOUT_SECONDS`` if set, then to the built-in default.
        """
        if self.ollama_timeout_seconds is not None:
            return self.ollama_timeout_seconds
        return self.llm_timeout_seconds

    # In-memory caches (per process; bounded by entry count)
    dataframe_cache_max_entries: int = 8
    schema_cache_max_entries: int = 32

    # Visualization
    scatter_max_points: int = 1000

    # Database connectivity
    db_encryption_key: Optional[str] = None
    db_max_rows: int = 25000
    db_cache_ttl_seconds: float = 60.0
    db_pool_size: int = 5
    db_connect_timeout_seconds: int = 10
    db_pushdown_enabled: bool = True

    # Forecasting
    max_forecast_horizon: int = 36
    forecast_default_horizon: int = 12
    forecast_min_points: int = 6
    anomaly_sensitivity: float = 3.0
    forecast_in_reports: bool = True
    forecast_date_column: Optional[str] = None
    forecast_target_column: Optional[str] = None
    forecast_frequency: str = "M"
    forecast_aggregation: str = "sum"

    # Agent orchestration (Phase 9)
    agent_max_tool_calls: int = 10
    agent_max_retries: int = 2
    agent_max_reports_per_run: int = 1
    agent_max_forecasts_per_run: int = 1

    # Authentication (Phase A1)
    # Shared secret between Next.js (signs) and FastAPI (verifies) for HS256
    # backend JWTs.  Must be ≥32 random characters.  SEPARATE from NEXTAUTH_SECRET.
    # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
    backend_jwt_secret: Optional[str] = None

    # Google OAuth — consumed by Next.js NextAuth; validated here at startup so
    # the backend fails fast with a clear error rather than allowing silent auth
    # failures in production.  Not used by the backend for any API calls.
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # CRUD operations (Phase 7)
    crud_rollback_ttl_seconds: int = 3600
    crud_max_affected_rows: int = 500
    crud_max_rollback_rows: int = 1000
    # Base64-encoded secret for HMAC confirmation tokens. If unset, a
    # per-process random secret is used (tokens survive only one process restart).
    crud_secret_key: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Anomaly Detection Engine
    # ------------------------------------------------------------------ #
    anomaly_cache_ttl_seconds: float = 300.0
    anomaly_cache_max_entries: int = 30
    # Default detection thresholds (overridable per-request).
    anomaly_zscore_threshold: float = 3.0
    anomaly_iqr_multiplier: float = 1.5
    anomaly_contamination: float = 0.05

    # ------------------------------------------------------------------ #
    # Root Cause Analysis Agent
    # ------------------------------------------------------------------ #
    rca_cache_ttl_seconds: float = 300.0
    rca_cache_max_entries: int = 30
    # Maximum unique dimension values before a column is excluded from decomposition.
    rca_max_dim_cardinality: int = 50

    # ------------------------------------------------------------------ #
    # Recommendation Engine
    # ------------------------------------------------------------------ #
    recommendation_cache_ttl_seconds: float = 300.0
    recommendation_cache_max_entries: int = 30
    recommendation_max_default: int = 10

    # ------------------------------------------------------------------ #
    # Conversational Memory
    # ------------------------------------------------------------------ #
    # Redis URL for L2 cache (optional). Example: redis://localhost:6379
    # If unset, only the in-process TTLCache and SQLite are used.
    redis_url: Optional[str] = None
    # Time-to-live for session data in Redis and for SQLite expiry cleanup.
    memory_session_ttl_seconds: float = 86400.0   # 24 hours
    # In-process L1 cache size (sessions) and TTL.
    memory_l1_ttl_seconds: float = 300.0
    memory_l1_max_sessions: int = 100
    # Maximum turns kept per session (oldest are evicted first).
    memory_max_turns_per_session: int = 20
    # Maximum table_data rows stored per turn (prevents unbounded payload growth).
    memory_max_table_rows: int = 50

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # AI Executive Dashboard Generator
    # ------------------------------------------------------------------ #
    dashboard_cache_ttl_seconds: float = 300.0
    dashboard_cache_max_entries: int = 30

    # ------------------------------------------------------------------ #
    # AI Insight Generation Engine
    # ------------------------------------------------------------------ #
    # Cache: responses are keyed by sha256(dataset_id|question|table_data).
    insight_cache_ttl_seconds: float = 300.0
    insight_cache_max_entries: int = 50
    # Cap the number of rows fed to the statistical engine (performance guard).
    insight_max_table_rows: int = 1000
    # Minimum |r| for a correlation to be included in the findings.
    insight_correlation_threshold: float = 0.5
    # Top-N and bottom-N performers to surface per metric column.
    insight_top_n: int = 3

    @property
    def max_upload_size_bytes(self) -> int:
        """Maximum accepted upload size expressed in bytes."""
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Caching ensures the ``.env`` file and environment are parsed only once.
    """
    return Settings()
