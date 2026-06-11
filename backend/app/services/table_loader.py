"""Load database tables into pandas DataFrames, safely and capped.

Identifiers are resolved via SQLAlchemy reflection (so only real tables/columns
are referenced) and queried with ``select(table).limit(n)`` — never via string
interpolation. This keeps the loader free of SQL-injection surface.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import DatabaseError, ValidationError


class TableLoader:
    """Reflect and read a capped slice of a database table."""

    def load(
        self,
        engine: Engine,
        schema: Optional[str],
        table: str,
        limit: int,
    ) -> pd.DataFrame:
        """Return up to ``limit`` rows of ``table`` as a DataFrame.

        Raises:
            ValidationError: if the table does not exist.
            DatabaseError: if reflection or the query fails.
        """
        metadata = MetaData()
        try:
            reflected = Table(
                table, metadata, autoload_with=engine, schema=schema
            )
        except SQLAlchemyError as exc:
            # Most commonly NoSuchTableError — treat as a user input problem.
            raise ValidationError(
                f"Table '{table}' could not be found or reflected."
            ) from exc

        statement = select(reflected).limit(limit)
        try:
            with engine.connect() as connection:
                return pd.read_sql(statement, connection)
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Failed to read table '{table}'.") from exc
