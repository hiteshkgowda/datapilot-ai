"""Anomaly Detection Service — orchestrates engine, cache, and chart builder."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

import pandas as pd

from analytics.anomaly_detector import (
    AnomalyChartBuilder,
    AnomalyDetectionEngine,
    _overall_severity,
)
from app.core.cache import TTLCache
from app.schemas.anomaly import AnomalyResponse

logger = logging.getLogger(__name__)


class AnomalyDetectionService:
    """Process-wide singleton that coordinates detection, caching, and chart building."""

    def __init__(
        self,
        cache_ttl: float = 300.0,
        cache_max_entries: int = 30,
    ) -> None:
        self._cache: TTLCache[str, AnomalyResponse] = TTLCache(
            ttl_seconds=cache_ttl,
            max_entries=cache_max_entries,
        )
        self._chart_builder = AnomalyChartBuilder()

    async def detect(
        self,
        df: pd.DataFrame,
        request_dict: dict[str, Any],
    ) -> AnomalyResponse:
        """Full detection pipeline: engine → chart → cache."""
        dataset_id: str = request_dict["dataset_id"]
        columns: Optional[list[str]] = request_dict.get("columns")
        methods: list[str] = request_dict.get("methods") or [
            "zscore", "iqr", "isolation_forest", "seasonal"
        ]
        zscore_threshold: float = float(request_dict.get("zscore_threshold", 3.0))
        iqr_multiplier: float = float(request_dict.get("iqr_multiplier", 1.5))
        contamination: float = float(request_dict.get("contamination", 0.05))
        seasonal_period: Optional[int] = request_dict.get("seasonal_period")
        time_col: Optional[str] = request_dict.get("time_column")
        merge: bool = bool(request_dict.get("merge_methods", True))

        cache_key = _cache_key(dataset_id, columns, methods, zscore_threshold, iqr_multiplier, contamination, seasonal_period)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})

        start = time.perf_counter()
        try:
            engine = AnomalyDetectionEngine(
                zscore_threshold=zscore_threshold,
                iqr_multiplier=iqr_multiplier,
                contamination=contamination,
                seasonal_period=seasonal_period,
                merge_methods=merge,
            )
            col_anomalies, reasons = engine.analyze(df, columns, methods, time_col)
            chart_spec = self._chart_builder.build(df, col_anomalies, time_col)
        except Exception as exc:
            logger.error("AnomalyDetectionService: detection failed: %s", exc)
            col_anomalies, reasons, chart_spec = [], [f"Detection error: {exc}"], None

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

        methods_used = sorted({m for ca in col_anomalies for m in ca.methods}) or methods
        affected = [ca.column for ca in col_anomalies]

        result = AnomalyResponse(
            anomalies=col_anomalies,
            severity=_overall_severity(col_anomalies),
            affected_metrics=affected,
            possible_reasons=reasons,
            total_anomaly_count=sum(ca.anomaly_count for ca in col_anomalies),
            chart_spec=chart_spec,
            detection_time_ms=elapsed_ms,
            methods_used=methods_used,
            cache_hit=False,
        )
        self._cache.put(cache_key, result)
        return result


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _cache_key(
    dataset_id: str,
    columns: Optional[list[str]],
    methods: list[str],
    zscore_threshold: float,
    iqr_multiplier: float,
    contamination: float,
    seasonal_period: Optional[int],
) -> str:
    parts: dict[str, Any] = {
        "dataset_id": dataset_id,
        "columns": sorted(columns) if columns else None,
        "methods": sorted(methods),
        "zscore_threshold": zscore_threshold,
        "iqr_multiplier": iqr_multiplier,
        "contamination": contamination,
        "seasonal_period": seasonal_period,
    }
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
