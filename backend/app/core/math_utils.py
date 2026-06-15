"""Small helpers shared across service modules."""

from __future__ import annotations

import hashlib
from typing import Any, Optional

import numpy as np


def strip_json_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def dataset_cache_key(dataset_id: str) -> str:
    """16-char hex key derived from dataset_id — used for in-process TTL caches."""
    return hashlib.sha256(dataset_id.encode()).hexdigest()[:16]


def safe_float(val: Any) -> Optional[float]:
    """Return a JSON-safe float rounded to 6 places, or None for NaN / Inf / unparseable."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None
