"""Filesystem persistence for saved dashboards.

Storage layout (inside ``DASHBOARDS_DIR``):
    <hex32>.json   — serialised DashboardConfig

Mirrors the pattern used by ReportService and ConnectionService: one JSON
file per record, keyed by a hex32 ID generated at save time.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.dashboard import DashboardConfig, DashboardMetadata

logger = logging.getLogger(__name__)


class DashboardNotFoundError(Exception):
    """Raised when a dashboard does not exist or does not belong to the caller."""


class DashboardStore:
    """Read/write DashboardConfig JSON files on the local filesystem."""

    def __init__(self, dashboards_dir: Path) -> None:
        self._dir = dashboards_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    def save(self, config: DashboardConfig, owner_sub: str) -> DashboardMetadata:
        """Persist ``config`` to disk and return its metadata.

        Always generates a fresh ``dashboard_id`` — callers must not assume
        the id on the incoming config is stable.
        """
        dashboard_id = secrets.token_hex(16)
        stamped = config.model_copy(
            update={
                "dashboard_id": dashboard_id,
                "owner_sub": owner_sub,
                "created_at": datetime.now(timezone.utc),
            }
        )

        path = self._dir / f"{dashboard_id}.json"
        # Atomic-ish write: write to a temp file then rename.
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(stamped.model_dump_json(), encoding="utf-8")
            tmp.rename(path)
        except OSError as exc:
            logger.error("DashboardStore.save: failed to write %s: %s", path, exc)
            raise

        logger.info(
            "DashboardStore: saved dashboard %s ('%s') for user %.8s",
            dashboard_id,
            stamped.dashboard_name,
            owner_sub,
        )
        return DashboardMetadata(
            dashboard_id=dashboard_id,
            dashboard_name=stamped.dashboard_name,
            dataset_id=stamped.dataset_id,
            score=stamped.score,
            created_at=stamped.created_at,
        )

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def get(self, dashboard_id: str, owner_sub: str) -> DashboardConfig:
        """Return the dashboard matching ``dashboard_id``.

        Raises:
            DashboardNotFoundError: if the file does not exist or the caller
                does not own it.
        """
        path = self._dir / f"{dashboard_id}.json"
        if not path.exists():
            raise DashboardNotFoundError(f"Dashboard '{dashboard_id}' not found.")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            config = DashboardConfig(**raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "DashboardStore.get: could not deserialise %s: %s", path, exc
            )
            raise DashboardNotFoundError(
                f"Dashboard '{dashboard_id}' is corrupt."
            ) from exc

        if config.owner_sub and config.owner_sub != owner_sub:
            raise DashboardNotFoundError(f"Dashboard '{dashboard_id}' not found.")

        return config

    def list_for_user(self, owner_sub: str) -> list[DashboardMetadata]:
        """Return all dashboards owned by ``owner_sub``, newest first."""
        results: list[DashboardMetadata] = []
        for path in self._dir.glob("*.json"):
            if path.suffix == ".tmp":
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                config = DashboardConfig(**raw)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if config.owner_sub and config.owner_sub != owner_sub:
                continue
            if config.dashboard_id is None:
                continue
            results.append(
                DashboardMetadata(
                    dashboard_id=config.dashboard_id,
                    dashboard_name=config.dashboard_name,
                    dataset_id=config.dataset_id,
                    score=config.score,
                    created_at=config.created_at,
                )
            )
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results
