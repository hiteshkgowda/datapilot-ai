"""Analytics service: plan validation and safe pandas execution.

This module turns a natural-language question into a result WITHOUT ever
executing model-generated code. The flow is:

    question -> planner (LLM) -> raw dict
             -> QueryPlan (structural validation via Pydantic)
             -> semantic validation against the real DataFrame
             -> fixed pandas dispatch table -> answer string

There is no ``eval``, no ``exec``, and no string-to-pandas evaluation anywhere.
Column names from the plan are only ever used as dictionary keys to look up the
real column objects of the DataFrame.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import DatabaseError, PlanValidationError
from app.schemas.dataset import DatasetMetadata, DatasetSource
from app.schemas.query import Operation, QueryPlan, QueryResponse
from app.services.analytics_results import (
    ExecutionResult,
    grouped_answer,
    scalar_answer,
    xy_answer,
)
from app.services.dataset_service import DatasetSchema, DatasetService
from app.services.llm_provider import QueryPlanner
from app.services.sql_executor import SqlExecutor

logger = logging.getLogger(__name__)

# Operations that require a target ``column``.
_COLUMN_OPS = frozenset(
    {
        Operation.SUM,
        Operation.AVERAGE,
        Operation.MAX,
        Operation.MIN,
        Operation.GROUPBY_SUM,
        Operation.TOP_N,
    }
)
# Operations whose target ``column`` must be numeric.
_NUMERIC_OPS = _COLUMN_OPS
# Operations that require a ``group_by`` column.
_GROUP_OPS = frozenset(
    {Operation.GROUPBY_SUM, Operation.GROUPBY_COUNT, Operation.TOP_N}
)


# ``ExecutionResult`` is defined in analytics_results and re-exported here for
# backward compatibility with existing imports.
__all__ = ["AnalyticsService", "AnalysisResult", "ExecutionResult"]


@dataclass(frozen=True)
class AnalysisResult:
    """A full analysis: the plan, its structured result and timings."""

    plan: QueryPlan
    result: ExecutionResult
    execution_time_ms: float
    total_time_ms: float


class AnalyticsService:
    """Answer natural-language questions over a stored dataset."""

    def __init__(
        self,
        dataset_service: DatasetService,
        planner: QueryPlanner,
        sql_executor: Optional[SqlExecutor] = None,
        scatter_max_points: int = 1000,
        pushdown_enabled: bool = True,
    ) -> None:
        self._datasets = dataset_service
        self._planner = planner
        self._sql_executor = sql_executor
        self._scatter_max_points = scatter_max_points
        self._pushdown_enabled = pushdown_enabled

    async def analyze(self, dataset_id: str, question: str) -> AnalysisResult:
        """Run the full pipeline and return the structured analysis.

        Shared by both the analytics (``/query``) and visualization
        (``/chart``) endpoints so the LLM call and execution happen once.

        Raises:
            DatasetNotFoundError: if the dataset is missing.
            ParseError: if the stored file cannot be read.
            LLMError: if the planner is unreachable or returns bad output.
            PlanValidationError: if the plan is semantically invalid.
        """
        total_start = time.perf_counter()

        # 1. Fetch metadata + schema WITHOUT loading data (tables: from stored
        #    column info), so a pushed-down query never materializes the table.
        metadata = await run_in_threadpool(self._datasets.get_metadata, dataset_id)
        schema = await run_in_threadpool(self._datasets.get_schema, dataset_id)

        # 2. Ask the LLM for a plan (may raise LLMError).
        raw_plan = await self._planner.generate_plan(question, schema.dtypes)

        # 3. Structural + semantic validation against the schema.
        plan = self._parse_plan(raw_plan)
        self._validate_plan(plan, schema)

        # 4. Execute via the appropriate backend (SQL pushdown or pandas).
        exec_start = time.perf_counter()
        result = await self._run(dataset_id, metadata, plan, schema)
        execution_time_ms = (time.perf_counter() - exec_start) * 1000.0

        total_time_ms = (time.perf_counter() - total_start) * 1000.0
        return AnalysisResult(
            plan=plan,
            result=result,
            execution_time_ms=round(execution_time_ms, 3),
            total_time_ms=round(total_time_ms, 3),
        )

    async def execute_plan(
        self, dataset_id: str, plan: QueryPlan
    ) -> AnalysisResult:
        """Validate and execute a caller-supplied plan deterministically.

        No LLM is involved — used by report generation to reuse the executor
        for a fixed battery of plans.

        Raises:
            DatasetNotFoundError: if the dataset is missing.
            ParseError: if the stored file cannot be read.
            PlanValidationError: if the plan is semantically invalid.
        """
        total_start = time.perf_counter()
        metadata = await run_in_threadpool(self._datasets.get_metadata, dataset_id)
        schema = await run_in_threadpool(self._datasets.get_schema, dataset_id)
        self._validate_plan(plan, schema)

        exec_start = time.perf_counter()
        result = await self._run(dataset_id, metadata, plan, schema)
        execution_time_ms = (time.perf_counter() - exec_start) * 1000.0

        total_time_ms = (time.perf_counter() - total_start) * 1000.0
        return AnalysisResult(
            plan=plan,
            result=result,
            execution_time_ms=round(execution_time_ms, 3),
            total_time_ms=round(total_time_ms, 3),
        )

    async def _run(
        self,
        dataset_id: str,
        metadata: DatasetMetadata,
        plan: QueryPlan,
        schema: DatasetSchema,
    ) -> ExecutionResult:
        """Dispatch execution to the SQL or pandas backend.

        - ``column_count`` is answered from the schema (no data load).
        - Table datasets push supported aggregates down to SQL (full table);
          on SQL failure they fall back to pandas (a capped frame).
        - Everything else runs in pandas (files, ``xy_select``, fallback).
        """
        if plan.operation is Operation.COLUMN_COUNT:
            return scalar_answer(plan, len(schema.column_names))

        if (
            metadata.source is DatasetSource.TABLE
            and self._pushdown_enabled
            and self._sql_executor is not None
            and self._sql_executor.supports(plan.operation)
        ):
            try:
                return await run_in_threadpool(
                    self._sql_executor.execute, metadata, plan
                )
            except DatabaseError as exc:
                logger.warning(
                    "SQL pushdown failed for dataset %s; falling back to "
                    "pandas: %s",
                    dataset_id,
                    exc,
                )

        frame, _metadata = await run_in_threadpool(
            self._datasets.load_dataframe, dataset_id
        )
        return self._execute(plan, frame)

    async def answer_question(
        self, dataset_id: str, question: str
    ) -> QueryResponse:
        """Plan, validate and execute a question, returning the text answer."""
        analysis = await self.analyze(dataset_id, question)
        return QueryResponse(
            answer=analysis.result.answer,
            query_plan=analysis.plan,
            execution_time_ms=analysis.execution_time_ms,
            total_time_ms=analysis.total_time_ms,
        )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_plan(raw_plan: dict[str, Any]) -> QueryPlan:
        """Validate the raw plan's structure via Pydantic (the op allowlist)."""
        try:
            return QueryPlan.model_validate(raw_plan)
        except ValidationError as exc:
            raise PlanValidationError(
                f"The generated query plan is malformed: {exc}"
            ) from exc

    def _validate_plan(self, plan: QueryPlan, schema: DatasetSchema) -> None:
        """Enforce per-operation rules against the cached dataset schema."""
        columns = set(schema.column_names)
        numeric_columns = schema.numeric_columns
        op = plan.operation

        # Column requirement and existence.
        if op in _COLUMN_OPS:
            if not plan.column:
                raise PlanValidationError(
                    f"Operation '{op.value}' requires a 'column'."
                )
            if plan.column not in columns:
                raise PlanValidationError(
                    f"Unknown column '{plan.column}'. "
                    f"Available columns: {sorted(columns)}."
                )
            if op in _NUMERIC_OPS and plan.column not in numeric_columns:
                raise PlanValidationError(
                    f"Operation '{op.value}' requires a numeric column, "
                    f"but '{plan.column}' is not numeric."
                )

        # Group-by requirement and existence.
        if op in _GROUP_OPS:
            if not plan.group_by:
                raise PlanValidationError(
                    f"Operation '{op.value}' requires a 'group_by' column."
                )
            if plan.group_by not in columns:
                raise PlanValidationError(
                    f"Unknown group_by column '{plan.group_by}'. "
                    f"Available columns: {sorted(columns)}."
                )

        # top_n needs a positive 'n'.
        if op is Operation.TOP_N and plan.n is None:
            raise PlanValidationError("Operation 'top_n' requires 'n'.")

        # xy_select needs two existing, numeric columns.
        if op is Operation.XY_SELECT:
            for field_name, value in (
                ("x_column", plan.x_column),
                ("y_column", plan.y_column),
            ):
                if not value:
                    raise PlanValidationError(
                        f"Operation 'xy_select' requires '{field_name}'."
                    )
                if value not in columns:
                    raise PlanValidationError(
                        f"Unknown column '{value}'. "
                        f"Available columns: {sorted(columns)}."
                    )
                if value not in numeric_columns:
                    raise PlanValidationError(
                        f"Operation 'xy_select' requires numeric columns, "
                        f"but '{value}' is not numeric."
                    )

    # ------------------------------------------------------------------ #
    # Execution (fixed dispatch — no dynamic code)
    # ------------------------------------------------------------------ #
    def _execute(self, plan: QueryPlan, frame: pd.DataFrame) -> ExecutionResult:
        """Execute a validated plan with pandas via the shared formatters."""
        # Resolve plan column names to the real DataFrame columns. Validation
        # guarantees these keys exist when required.
        lookup = {str(col): col for col in frame.columns}
        op = plan.operation

        if op is Operation.ROW_COUNT:
            return scalar_answer(plan, int(frame.shape[0]))

        if op is Operation.COLUMN_COUNT:
            return scalar_answer(plan, int(frame.shape[1]))

        if op is Operation.SUM:
            return scalar_answer(plan, frame[lookup[plan.column]].sum())

        if op is Operation.AVERAGE:
            return scalar_answer(plan, frame[lookup[plan.column]].mean())

        if op is Operation.MAX:
            return scalar_answer(plan, frame[lookup[plan.column]].max())

        if op is Operation.MIN:
            return scalar_answer(plan, frame[lookup[plan.column]].min())

        if op is Operation.GROUPBY_SUM:
            grouped = (
                frame.groupby(lookup[plan.group_by])[lookup[plan.column]]
                .sum()
                .sort_values(ascending=False)
            )
            return grouped_answer(plan, grouped.items(), value_field=plan.column)

        if op is Operation.GROUPBY_COUNT:
            grouped = (
                frame.groupby(lookup[plan.group_by])
                .size()
                .sort_values(ascending=False)
            )
            return grouped_answer(plan, grouped.items(), value_field="count")

        if op is Operation.TOP_N:
            grouped = (
                frame.groupby(lookup[plan.group_by])[lookup[plan.column]]
                .sum()
                .nlargest(plan.n)
            )
            return grouped_answer(plan, grouped.items(), value_field=plan.column)

        if op is Operation.XY_SELECT:
            x_col, y_col = lookup[plan.x_column], lookup[plan.y_column]
            subset = frame[[x_col, y_col]].dropna().head(self._scatter_max_points)
            return xy_answer(plan, zip(subset[x_col], subset[y_col]))

        # Unreachable: Operation is an exhaustive enum validated upstream.
        raise PlanValidationError(f"Unsupported operation '{op}'.")
