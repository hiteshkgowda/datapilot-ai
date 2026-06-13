"""Domain-level exceptions.

These errors are intentionally framework-agnostic. Service code raises them
to signal *what* went wrong; the API layer is solely responsible for mapping
them onto HTTP status codes. This keeps business logic decoupled from FastAPI.
"""

from __future__ import annotations


class DataAssistantError(Exception):
    """Base class for all application-specific errors."""


class ValidationError(DataAssistantError):
    """Raised when user input fails a business rule (e.g. bad extension)."""


class ParseError(DataAssistantError):
    """Raised when an uploaded file cannot be read into a tabular form."""


class DatasetNotFoundError(DataAssistantError):
    """Raised when a requested dataset does not exist."""


class PlanValidationError(DataAssistantError):
    """Raised when an LLM-produced query plan fails semantic validation."""


class LLMError(DataAssistantError):
    """Raised when the LLM provider is unreachable or returns invalid output."""


class ReportNotFoundError(DataAssistantError):
    """Raised when a requested report does not exist."""


class ConnectionNotFoundError(DataAssistantError):
    """Raised when a requested database connection does not exist."""


class DatabaseError(DataAssistantError):
    """Raised when a database operation (connect, inspect, query) fails."""


class ForecastValidationError(DataAssistantError):
    """Raised when a forecast plan fails semantic validation."""


class CrudPlanValidationError(DataAssistantError):
    """Raised when a CRUD plan fails schema or safety validation."""


class CrudExecutionError(DataAssistantError):
    """Raised when a CRUD DML statement fails to execute."""


class RollbackError(DataAssistantError):
    """Raised when a rollback operation cannot be completed."""


class ConfirmationError(DataAssistantError):
    """Raised when a confirmation token is missing, expired, or already used."""


class AgentPlanError(DataAssistantError):
    """Raised when the agent planner produces an invalid or unsafe plan."""


class AgentExecutionError(DataAssistantError):
    """Raised when the agent graph encounters an unrecoverable execution failure."""


class AnomalyDetectionError(DataAssistantError):
    """Raised when the anomaly detection pipeline encounters an unrecoverable error."""


class InsightGenerationError(DataAssistantError):
    """Raised when the insight generation pipeline encounters an unrecoverable error."""


class RootCauseError(DataAssistantError):
    """Raised when the root cause analysis pipeline encounters an unrecoverable error."""


class RecommendationError(DataAssistantError):
    """Raised when the recommendation engine encounters an unrecoverable error."""


class MemoryError(DataAssistantError):
    """Raised when the conversational memory system encounters an unrecoverable error."""
