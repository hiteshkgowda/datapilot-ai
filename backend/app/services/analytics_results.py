"""Shared construction of :class:`ExecutionResult` values.

Both execution backends — the pandas executor (files / fallback) and the SQL
pushdown executor (database tables) — build their results through these
functions. Centralising the answer templates and table shaping here is what
keeps the two backends behaviourally identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional

import numpy as np

from app.schemas.query import Operation, QueryPlan


@dataclass(frozen=True)
class ExecutionResult:
    """The structured outcome of executing a query plan.

    ``x_field``/``y_field`` name the columns to plot; they are ``None`` for
    scalar operations, which are not chartable.
    """

    answer: str
    table: list[dict[str, Any]] = field(default_factory=list)
    x_field: Optional[str] = None
    y_field: Optional[str] = None


def to_native(value: Any) -> Any:
    """Coerce numpy / Decimal scalars to native Python types for JSON safety.

    Decimals (returned by some DB drivers) become floats so that numeric
    formatting matches the pandas backend.
    """
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def scalar_answer(plan: QueryPlan, value: Any) -> ExecutionResult:
    """Build a result for a single-value (non-chartable) operation."""
    native = to_native(value)
    op = plan.operation
    templates = {
        Operation.ROW_COUNT: f"The dataset has {native} row(s).",
        Operation.COLUMN_COUNT: f"The dataset has {native} column(s).",
        Operation.SUM: f"The sum of '{plan.column}' is {native}.",
        Operation.AVERAGE: f"The average of '{plan.column}' is {native}.",
        Operation.MAX: f"The maximum of '{plan.column}' is {native}.",
        Operation.MIN: f"The minimum of '{plan.column}' is {native}.",
    }
    return ExecutionResult(
        answer=templates[op],
        table=[{"metric": op.value, "value": native}],
        x_field=None,
        y_field=None,
    )


def grouped_answer(
    plan: QueryPlan,
    pairs: Iterable[tuple[Any, Any]],
    value_field: str,
) -> ExecutionResult:
    """Build a result for a grouped (chartable) operation."""
    group_field = plan.group_by
    op = plan.operation
    headers = {
        Operation.GROUPBY_SUM: f"Sum of '{plan.column}' by '{group_field}'",
        Operation.GROUPBY_COUNT: f"Count by '{group_field}'",
        Operation.TOP_N: f"Top {plan.n} '{group_field}' by total '{plan.column}'",
    }
    header = headers[op]
    table = [
        {group_field: to_native(key), value_field: to_native(value)}
        for key, value in pairs
    ]
    if not table:
        answer = f"{header}: no data available."
    else:
        lines = "\n".join(
            f"  {row[group_field]}: {row[value_field]}" for row in table
        )
        answer = f"{header}:\n{lines}"
    return ExecutionResult(
        answer=answer, table=table, x_field=group_field, y_field=value_field
    )


def xy_answer(
    plan: QueryPlan, pairs: Iterable[tuple[Any, Any]]
) -> ExecutionResult:
    """Build a result for an xy_select (scatter) operation."""
    table = [
        {plan.x_column: to_native(x), plan.y_column: to_native(y)}
        for x, y in pairs
    ]
    answer = (
        f"Showing {len(table)} point(s) of "
        f"'{plan.y_column}' vs '{plan.x_column}'."
    )
    return ExecutionResult(
        answer=answer, table=table, x_field=plan.x_column, y_field=plan.y_column
    )
