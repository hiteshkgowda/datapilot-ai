"""Translate a validated QueryPlan into a SQLAlchemy Core SELECT.

Only the eight supported aggregate operations are translatable. Statements are
built exclusively from a fixed per-operation template over *reflected* table
columns — the plan's column strings are used solely as dictionary keys to fetch
real :class:`Column` objects, so no identifier or value is ever string-formatted
into SQL. The only bound literal is ``n`` (a validated integer).

Aggregates run over the full table (no row cap). GROUP BY keeps NULL keys as a
distinct group — a deliberate, documented difference from the pandas backend,
which drops NULL group keys.
"""

from __future__ import annotations

from sqlalchemy import Table, func, select
from sqlalchemy.sql import Select

from app.core.exceptions import PlanValidationError
from app.schemas.query import Operation

# Operations producing a single scalar value.
_SCALAR_OPS = frozenset(
    {
        Operation.ROW_COUNT,
        Operation.SUM,
        Operation.AVERAGE,
        Operation.MAX,
        Operation.MIN,
    }
)
# Operations producing grouped rows.
_GROUPED_OPS = frozenset(
    {Operation.GROUPBY_SUM, Operation.GROUPBY_COUNT, Operation.TOP_N}
)
_SUPPORTED = _SCALAR_OPS | _GROUPED_OPS


class SQLTranslator:
    """Build parameterized Core SELECT statements from query plans."""

    @staticmethod
    def supports(operation: Operation) -> bool:
        """Whether an operation can be pushed down to SQL."""
        return operation in _SUPPORTED

    @staticmethod
    def is_scalar(operation: Operation) -> bool:
        """Whether an operation returns a single scalar value."""
        return operation in _SCALAR_OPS

    def translate(self, plan, table: Table) -> Select:
        """Return a Core SELECT for ``plan`` over the reflected ``table``."""
        columns = {str(column.name): column for column in table.columns}
        op = plan.operation

        if op is Operation.ROW_COUNT:
            return select(func.count()).select_from(table)
        if op is Operation.SUM:
            return select(func.sum(self._col(columns, plan.column)))
        if op is Operation.AVERAGE:
            return select(func.avg(self._col(columns, plan.column)))
        if op is Operation.MAX:
            return select(func.max(self._col(columns, plan.column)))
        if op is Operation.MIN:
            return select(func.min(self._col(columns, plan.column)))

        if op is Operation.GROUPBY_SUM:
            group = self._col(columns, plan.group_by)
            aggregate = func.sum(self._col(columns, plan.column))
            return select(group, aggregate).group_by(group).order_by(
                aggregate.desc()
            )
        if op is Operation.GROUPBY_COUNT:
            group = self._col(columns, plan.group_by)
            aggregate = func.count()
            return select(group, aggregate).group_by(group).order_by(
                aggregate.desc()
            )
        if op is Operation.TOP_N:
            group = self._col(columns, plan.group_by)
            aggregate = func.sum(self._col(columns, plan.column))
            return (
                select(group, aggregate)
                .group_by(group)
                .order_by(aggregate.desc())
                .limit(plan.n)
            )

        raise PlanValidationError(
            f"Operation '{op.value}' cannot be pushed down to SQL."
        )

    @staticmethod
    def _col(columns: dict, name: str):
        """Resolve a plan column name to a reflected Column (allowlist gate)."""
        if name not in columns:
            raise PlanValidationError(
                f"Column '{name}' is not present in the table."
            )
        return columns[name]
