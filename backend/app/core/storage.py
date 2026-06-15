"""Storage path management, directory provisioning, and write-access verification.

All six filesystem storage volumes are owned here. Services still create their
own directories (via ``mkdir(parents=True, exist_ok=True)`` in __init__) as a
defence-in-depth measure, but the authoritative startup check runs through
StorageManager so a single ``assert_writable()`` call covers the whole app.

Usage (in lifespan):
    manager = StorageManager(settings)
    manager.ensure_directories()   # create all dirs
    manager.assert_writable()      # fail fast if any are read-only

Render / Railway:
    Set STORAGE_BASE_DIR to the mount path of the Persistent Disk / Volume.
    All six paths will resolve under that root automatically.
    Example: STORAGE_BASE_DIR=/data  → /data/uploads, /data/reports, …
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VolumeStatus:
    """Write-access probe result for one storage volume."""

    name: str
    path: Path
    writable: bool
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {"path": str(self.path), "writable": self.writable}
        if self.error:
            d["error"] = self.error
        return d


class StorageManager:
    """Manage all filesystem storage volumes for the application.

    Volumes are probed in the order they are defined.  Probe failures are
    collected and reported together so operators see all problems in one
    startup log line rather than fixing them one at a time.
    """

    def __init__(self, settings: Settings) -> None:
        # Ordered list of (logical_name, resolved_path) for all 6 volumes.
        self._volumes: list[tuple[str, Path]] = [
            ("uploads",        settings.upload_dir),
            ("reports",        settings.reports_dir),
            ("connections",    settings.connections_dir),
            ("crud_audit",     settings.crud_audit_dir),
            ("crud_rollback",  settings.crud_rollback_dir),
            ("agent_sessions", settings.agent_sessions_dir),
            ("memory_store",   settings.memory_store_dir),
            ("dashboards",     settings.dashboards_dir),
        ]
        self._is_production = settings.is_production
        # Persistent = operator explicitly set STORAGE_BASE_DIR, pointing to a
        # mounted disk (Render Persistent Disk / Railway Volume).
        # Ephemeral  = STORAGE_BASE_DIR not set; data lives on the container's
        # local filesystem and is lost on redeploy (Render free tier).
        self._persistent = settings.storage_base_dir is not None

    @property
    def is_ephemeral(self) -> bool:
        """True when running on ephemeral storage (no persistent disk configured)."""
        return not self._persistent

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def ensure_directories(self) -> None:
        """Create all storage directories.

        Raises OSError if any directory cannot be created (e.g. parent path
        does not exist and cannot be made, or permission denied).
        """
        errors: list[str] = []
        for name, path in self._volumes:
            try:
                path.mkdir(parents=True, exist_ok=True)
                logger.debug("Storage volume '%s' ready at %s", name, path)
            except OSError as exc:
                errors.append(f"  {name} ({path}): {exc}")
        if errors:
            raise OSError(
                "Failed to create storage directories:\n" + "\n".join(errors)
            )

    def check_write_access(self) -> list[VolumeStatus]:
        """Write a probe file to each directory and immediately remove it.

        Returns one :class:`VolumeStatus` per volume; callers decide whether
        to treat failures as fatal.
        """
        results: list[VolumeStatus] = []
        for name, path in self._volumes:
            try:
                fd, tmp = tempfile.mkstemp(prefix=".write_probe_", dir=path)
                try:
                    os.write(fd, b"probe")
                finally:
                    os.close(fd)
                os.unlink(tmp)
                results.append(VolumeStatus(name=name, path=path, writable=True))
            except OSError as exc:
                results.append(
                    VolumeStatus(name=name, path=path, writable=False, error=str(exc))
                )
        return results

    def assert_writable(self) -> None:
        """Raise RuntimeError if any storage volume fails the write probe.

        In production this is called unconditionally and causes the process to
        exit with a clear diagnostic.  In development the same check runs but
        failures are logged as warnings rather than aborting (so local dev with
        a missing mount point does not break the entire server).
        """
        results = self.check_write_access()
        failures = [v for v in results if not v.writable]

        if not failures:
            persistence = "persistent" if self._persistent else "ephemeral"
            logger.info(
                "Storage: all %d volume(s) are writable (%s).",
                len(self._volumes),
                persistence,
            )
            return

        lines = [f"  {v.name} ({v.path}): {v.error}" for v in failures]
        message = (
            "Storage health check failed — the following volumes are not writable:\n"
            + "\n".join(lines)
            + "\n\n"
            "Deployment fix:\n"
            "  Render  → attach a Persistent Disk; set STORAGE_BASE_DIR to the mount path.\n"
            "  Railway → attach a Volume;          set STORAGE_BASE_DIR to the mount path.\n"
            "  Example: STORAGE_BASE_DIR=/data"
        )

        # Fatal only when persistent storage was explicitly configured but is
        # not writable — that indicates a misconfigured disk mount.
        # On free tier (ephemeral, no STORAGE_BASE_DIR), write failures are
        # still logged as errors but do not block startup.
        if self._is_production and self._persistent:
            raise RuntimeError(message)
        else:
            logger.warning("Storage warning (non-fatal):\n%s", message)

    def health_summary(self) -> dict[str, object]:
        """Return a storage status dict for inclusion in the /health response.

        Runs the write probe on every call.  The /health handler is expected
        to call this at most once per request; it is not cached.
        """
        results = self.check_write_access()
        all_ok = all(v.writable for v in results)
        return {
            "status": "ok" if all_ok else "degraded",
            "ephemeral": self.is_ephemeral,
            "volumes": {v.name: v.to_dict() for v in results},
        }
