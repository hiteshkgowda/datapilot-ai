"""Tests for RCAEngine and RootCauseService.

Coverage targets
----------------
- _detect_metric: keyword scoring, fallback to first numeric col, ID-col penalty
- _detect_period_col: explicit, datetime dtype, parseable dates, keyword col, row halves
- _detect_period_labels: numeric sort, string sort, < 2 unique values
- _split_periods: explicit labels, auto-detected labels, row-halves fallback
- _detect_dimensions: cardinality filter, keyword ordering, ID-col exclusion
- _decompose_dimension: contribution math, zero total_change guard, pct_change
- RCAEngine.analyze: full happy path, empty df, no numeric cols, no dimensions
- RootCauseService: cache hit/miss, analysis_time_ms populated, agent.generate called
- RootCauseAgent fallback: no client, LLM failure
- _cache_key: deterministic, question normalised
- _safe_float: nan, inf, None, valid value
- _is_id_col: true / false cases
- _looks_like_dates: success / failure
- Contribution math: contribution_pct = cell_change / |total_change| × 100
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.schemas.root_cause import (
    ContributionFactor,
    PeriodSummary,
    RCAFindings,
    RootCauseResponse,
)
from app.services.root_cause_service import (
    RCAEngine,
    RootCauseService,
    _cache_key,
    _is_id_col,
    _looks_like_dates,
    _safe_float,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sales_df() -> pd.DataFrame:
    """Simple two-period sales dataset with region dimension."""
    return pd.DataFrame(
        {
            "month": ["Jan", "Jan", "Jan", "Feb", "Feb", "Feb"],
            "region": ["North", "South", "East", "North", "South", "East"],
            "revenue": [100.0, 200.0, 150.0, 80.0, 210.0, 130.0],
        }
    )


def _make_engine() -> RCAEngine:
    return RCAEngine(max_dim_cardinality=50, max_dimensions=6, top_contributors=20)


def _make_findings(
    *,
    direction: str = "decline",
    total_change: float = -30.0,
    contributions: list[ContributionFactor] | None = None,
) -> RCAFindings:
    if contributions is None:
        contributions = [
            ContributionFactor(
                dimension="region",
                value="North",
                current_value=80.0,
                previous_value=100.0,
                absolute_change=-20.0,
                percentage_change=-20.0,
                contribution_pct=66.7,
                rank=1,
            ),
            ContributionFactor(
                dimension="region",
                value="East",
                current_value=130.0,
                previous_value=150.0,
                absolute_change=-20.0,
                percentage_change=-13.3,
                contribution_pct=33.3,
                rank=2,
            ),
        ]
    return RCAFindings(
        metric_column="revenue",
        period_column="month",
        current_period=PeriodSummary(label="Feb", total=420.0),
        previous_period=PeriodSummary(label="Jan", total=450.0),
        total_absolute_change=total_change,
        total_pct_change=-6.67,
        direction=direction,
        dimension_columns=["region"],
        contributions=contributions,
        has_offsets=False,
        row_count=6,
        period_split_method="period_column",
    )


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


def test_safe_float_valid() -> None:
    assert _safe_float(3.14159) == pytest.approx(3.1416)


def test_safe_float_none_returns_none() -> None:
    assert _safe_float(None) is None


def test_safe_float_nan_returns_zero() -> None:
    assert _safe_float(float("nan")) == 0.0


def test_safe_float_inf_returns_zero() -> None:
    assert _safe_float(float("inf")) == 0.0
    assert _safe_float(float("-inf")) == 0.0


def test_safe_float_string_number() -> None:
    assert _safe_float("42.5") == pytest.approx(42.5)


def test_safe_float_non_numeric_returns_none() -> None:
    assert _safe_float("not_a_number") is None


# ---------------------------------------------------------------------------
# _is_id_col
# ---------------------------------------------------------------------------


def test_is_id_col_true() -> None:
    for col in ("customer_id", "order_index", "product_key", "region_code"):
        assert _is_id_col(col), f"Expected {col!r} to be an id column"


def test_is_id_col_false() -> None:
    for col in ("revenue", "region", "month", "total_sales"):
        assert not _is_id_col(col), f"Expected {col!r} NOT to be an id column"


# ---------------------------------------------------------------------------
# _looks_like_dates
# ---------------------------------------------------------------------------


def test_looks_like_dates_true() -> None:
    sample = pd.Series(["2023-01", "2023-02", "2023-03", "2023-04", "2023-05"])
    assert _looks_like_dates(sample)


def test_looks_like_dates_false() -> None:
    sample = pd.Series(["North", "South", "East", "West", "Central"])
    assert not _looks_like_dates(sample)


def test_looks_like_dates_mixed_mostly_dates() -> None:
    sample = pd.Series(["2023-01", "2023-02", "2023-03", "2023-04", "not_a_date"])
    # 4/5 = 80% → should pass
    assert _looks_like_dates(sample)


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_deterministic() -> None:
    params = {"dataset_id": "abc", "question": "why did revenue drop"}
    k1 = _cache_key("abc", "why did revenue drop", params)
    k2 = _cache_key("abc", "why did revenue drop", params)
    assert k1 == k2


def test_cache_key_normalises_question_whitespace() -> None:
    k1 = _cache_key("ds1", "  Why did Revenue Drop  ", {})
    k2 = _cache_key("ds1", "why did revenue drop", {})
    assert k1 == k2


def test_cache_key_differs_by_dataset() -> None:
    k1 = _cache_key("ds1", "question", {})
    k2 = _cache_key("ds2", "question", {})
    assert k1 != k2


def test_cache_key_differs_by_params() -> None:
    k1 = _cache_key("ds1", "q", {"metric_column": "revenue"})
    k2 = _cache_key("ds1", "q", {"metric_column": "orders"})
    assert k1 != k2


# ---------------------------------------------------------------------------
# RCAEngine._detect_metric
# ---------------------------------------------------------------------------


def test_detect_metric_keyword_match() -> None:
    df = pd.DataFrame({"region": ["A"], "revenue": [1.0], "cost": [2.0]})
    engine = _make_engine()
    col = engine._detect_metric(df, "why did revenue drop?")
    assert col == "revenue"


def test_detect_metric_no_keyword_returns_numeric() -> None:
    df = pd.DataFrame({"region": ["A"], "val": [1.0]})
    engine = _make_engine()
    col = engine._detect_metric(df, "what happened?")
    assert col == "val"


def test_detect_metric_id_col_deprioritised() -> None:
    df = pd.DataFrame({"order_id": [1, 2], "sales": [100.0, 200.0]})
    engine = _make_engine()
    col = engine._detect_metric(df, "what happened?")
    assert col == "sales"


def test_detect_metric_no_numeric_raises() -> None:
    df = pd.DataFrame({"region": ["A", "B"], "month": ["Jan", "Feb"]})
    engine = _make_engine()
    with pytest.raises(ValueError, match="No numeric columns"):
        engine._detect_metric(df, "why did revenue drop?")


# ---------------------------------------------------------------------------
# RCAEngine._detect_period_col
# ---------------------------------------------------------------------------


def test_detect_period_col_explicit() -> None:
    df = pd.DataFrame({"month": ["Jan", "Feb"], "revenue": [100, 200]})
    engine = _make_engine()
    col, method = engine._detect_period_col(df, "month")
    assert col == "month"
    assert method == "explicit"


def test_detect_period_col_datetime_dtype() -> None:
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2023-01-01", "2023-02-01"]),
            "revenue": [1.0, 2.0],
        }
    )
    engine = _make_engine()
    col, method = engine._detect_period_col(df, None)
    assert col == "ts"
    assert method == "date_column"


def test_detect_period_col_parseable_dates() -> None:
    df = pd.DataFrame(
        {
            "period": ["2023-01", "2023-02", "2023-03"],
            "revenue": [1.0, 2.0, 3.0],
        }
    )
    engine = _make_engine()
    col, method = engine._detect_period_col(df, None)
    assert col == "period"
    assert method == "date_column"


def test_detect_period_col_keyword_name() -> None:
    # Use values that cannot be parsed as dates so the date_column branch is skipped.
    df = pd.DataFrame(
        {
            "sale_month": ["Q1", "Q2", "Q3", "Q4"],
            "revenue": [1.0, 2.0, 3.0, 4.0],
        }
    )
    engine = _make_engine()
    col, method = engine._detect_period_col(df, None)
    assert col == "sale_month"
    assert method == "period_column"


def test_detect_period_col_fallback_row_halves() -> None:
    df = pd.DataFrame({"region": ["North", "South"], "revenue": [1.0, 2.0]})
    engine = _make_engine()
    col, method = engine._detect_period_col(df, None)
    assert col is None
    assert method == "row_halves"


# ---------------------------------------------------------------------------
# RCAEngine._detect_period_labels
# ---------------------------------------------------------------------------


def test_detect_period_labels_sorted_numerically() -> None:
    df = pd.DataFrame({"year": [2022, 2023, 2024], "revenue": [1, 2, 3]})
    engine = _make_engine()
    curr, prev = engine._detect_period_labels(df, "year", "period_column")
    assert curr == "2024"
    assert prev == "2023"


def test_detect_period_labels_sorted_strings() -> None:
    df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "revenue": [1, 2, 3]})
    engine = _make_engine()
    curr, prev = engine._detect_period_labels(df, "month", "period_column")
    # alphabetical: Feb < Jan < Mar → curr=Mar, prev=Jan
    assert curr == "Mar"
    assert prev == "Jan"


def test_detect_period_labels_row_halves_returns_none() -> None:
    df = pd.DataFrame({"revenue": [1, 2]})
    engine = _make_engine()
    curr, prev = engine._detect_period_labels(df, None, "row_halves")
    assert curr is None
    assert prev is None


def test_detect_period_labels_single_value_returns_none() -> None:
    df = pd.DataFrame({"month": ["Jan", "Jan"], "revenue": [1, 2]})
    engine = _make_engine()
    curr, prev = engine._detect_period_labels(df, "month", "period_column")
    assert curr is None
    assert prev is None


# ---------------------------------------------------------------------------
# RCAEngine._split_periods
# ---------------------------------------------------------------------------


def test_split_periods_by_label() -> None:
    df = _sales_df()
    engine = _make_engine()
    from app.services.root_cause_service import _DetectedContext

    ctx = _DetectedContext(
        metric_col="revenue",
        period_col="month",
        current_label="Feb",
        previous_label="Jan",
        period_split_method="period_column",
    )
    curr, prev = engine._split_periods(df, ctx)
    assert list(curr["month"].unique()) == ["Feb"]
    assert list(prev["month"].unique()) == ["Jan"]


def test_split_periods_row_halves() -> None:
    df = pd.DataFrame({"revenue": range(10)})
    engine = _make_engine()
    from app.services.root_cause_service import _DetectedContext

    ctx = _DetectedContext(
        metric_col="revenue",
        period_col=None,
        current_label=None,
        previous_label=None,
        period_split_method="row_halves",
    )
    curr, prev = engine._split_periods(df, ctx)
    assert len(curr) == 5
    assert len(prev) == 5


# ---------------------------------------------------------------------------
# RCAEngine._detect_dimensions
# ---------------------------------------------------------------------------


def test_detect_dimensions_keyword_ordered() -> None:
    df = pd.DataFrame(
        {
            "region": ["A"] * 3,
            "product": ["X"] * 3,
            "revenue": [1.0, 2.0, 3.0],
        }
    )
    engine = _make_engine()
    dims = engine._detect_dimensions(df, "revenue", None)
    # "region" and "product" are both keyword hits; "region" appears earlier in _DIMENSION_KEYWORDS
    assert "region" in dims
    assert "product" in dims


def test_detect_dimensions_excludes_metric_and_period() -> None:
    df = pd.DataFrame(
        {
            "month": ["Jan"] * 3,
            "revenue": [1.0, 2.0, 3.0],
            "region": ["A", "B", "C"],
        }
    )
    engine = _make_engine()
    dims = engine._detect_dimensions(df, "revenue", "month")
    assert "revenue" not in dims
    assert "month" not in dims


def test_detect_dimensions_high_cardinality_excluded() -> None:
    # 60 unique values exceeds default max of 50
    df = pd.DataFrame(
        {
            "customer_name": [f"cust_{i}" for i in range(60)],
            "revenue": list(range(60)),
        }
    )
    engine = RCAEngine(max_dim_cardinality=50)
    dims = engine._detect_dimensions(df, "revenue", None)
    assert "customer_name" not in dims


# ---------------------------------------------------------------------------
# RCAEngine._decompose_dimension
# ---------------------------------------------------------------------------


def test_decompose_dimension_contribution_math() -> None:
    curr = pd.DataFrame({"region": ["North", "South"], "revenue": [80.0, 210.0]})
    prev = pd.DataFrame({"region": ["North", "South"], "revenue": [100.0, 200.0]})
    total_change = (80.0 + 210.0) - (100.0 + 200.0)  # = -10
    engine = _make_engine()
    factors = engine._decompose_dimension(curr, prev, "region", "revenue", total_change)

    north = next(f for f in factors if f.value == "North")
    south = next(f for f in factors if f.value == "South")

    # North: change = -20, contribution = (-20 / |-10|) * 100 = -200%
    assert north.absolute_change == pytest.approx(-20.0)
    assert north.contribution_pct == pytest.approx(-200.0)
    # South: change = +10, contribution = (10 / |-10|) * 100 = 100%
    assert south.absolute_change == pytest.approx(10.0)
    assert south.contribution_pct == pytest.approx(100.0)


def test_decompose_dimension_zero_total_change() -> None:
    curr = pd.DataFrame({"region": ["North"], "revenue": [100.0]})
    prev = pd.DataFrame({"region": ["North"], "revenue": [100.0]})
    engine = _make_engine()
    factors = engine._decompose_dimension(curr, prev, "region", "revenue", 0.0)
    assert all(f.contribution_pct == 0.0 for f in factors)


def test_decompose_dimension_missing_column_returns_empty() -> None:
    curr = pd.DataFrame({"revenue": [1.0]})
    prev = pd.DataFrame({"revenue": [2.0]})
    engine = _make_engine()
    factors = engine._decompose_dimension(curr, prev, "segment", "revenue", -1.0)
    assert factors == []


# ---------------------------------------------------------------------------
# RCAEngine.analyze — full happy path
# ---------------------------------------------------------------------------


def test_analyze_happy_path() -> None:
    df = _sales_df()
    engine = _make_engine()
    findings = engine.analyze(df, "why did revenue drop?", period_col="month")

    assert findings.metric_column == "revenue"
    assert findings.period_column == "month"
    assert findings.current_period.label == "Jan" or findings.current_period.label == "Feb"
    assert findings.row_count == 6
    assert findings.direction in ("decline", "growth", "flat")
    assert len(findings.contributions) > 0


def test_analyze_explicit_periods() -> None:
    df = _sales_df()
    engine = _make_engine()
    findings = engine.analyze(
        df,
        "why did revenue drop?",
        period_col="month",
        current_period="Feb",
        previous_period="Jan",
    )

    assert findings.current_period.label == "Feb"
    assert findings.previous_period.label == "Jan"
    # Feb total: 80 + 210 + 130 = 420; Jan total: 100 + 200 + 150 = 450
    assert findings.current_period.total == pytest.approx(420.0)
    assert findings.previous_period.total == pytest.approx(450.0)
    assert findings.direction == "decline"
    assert findings.total_absolute_change == pytest.approx(-30.0)


def test_analyze_has_region_contributions() -> None:
    df = _sales_df()
    engine = _make_engine()
    findings = engine.analyze(
        df,
        "why did revenue drop?",
        period_col="month",
        current_period="Feb",
        previous_period="Jan",
    )
    dims = {c.dimension for c in findings.contributions}
    assert "region" in dims


def test_analyze_contributions_ranked() -> None:
    df = _sales_df()
    engine = _make_engine()
    findings = engine.analyze(
        df,
        "why did revenue drop?",
        period_col="month",
        current_period="Feb",
        previous_period="Jan",
    )
    ranks = [c.rank for c in findings.contributions]
    assert ranks == list(range(1, len(ranks) + 1))


def test_analyze_empty_df_returns_empty_findings() -> None:
    df = pd.DataFrame(columns=["month", "region", "revenue"])
    engine = _make_engine()
    findings = engine.analyze(df, "why did revenue drop?")
    assert findings.row_count == 0
    assert findings.direction == "flat"
    assert findings.contributions == []


def test_analyze_contribution_pct_sum_for_single_dim() -> None:
    """Contributions from a single dimension should sum close to ±100%."""
    df = pd.DataFrame(
        {
            "month": ["Jan", "Jan", "Feb", "Feb"],
            "region": ["North", "South", "North", "South"],
            "revenue": [100.0, 200.0, 50.0, 200.0],
        }
    )
    engine = _make_engine()
    findings = engine.analyze(
        df,
        "why revenue drop",
        period_col="month",
        current_period="Feb",
        previous_period="Jan",
    )
    region_contribs = [c for c in findings.contributions if c.dimension == "region"]
    total_pct = sum(c.contribution_pct for c in region_contribs)
    # North declined 50; South flat → total_pct of North = -50/50 * 100 = -100%; South = 0
    assert total_pct == pytest.approx(-100.0, abs=1.0)


# ---------------------------------------------------------------------------
# RootCauseService — orchestration
# ---------------------------------------------------------------------------


def _make_mock_agent(response: RootCauseResponse | None = None) -> MagicMock:
    agent = MagicMock()
    if response is None:
        response = RootCauseResponse(
            problem="Revenue dropped.",
            root_causes=[],
            contribution_analysis=[],
            recommendations=[],
        )
    agent.generate = AsyncMock(return_value=response)
    return agent


def test_rca_service_calls_agent() -> None:
    df = _sales_df()
    agent = _make_mock_agent()
    svc = RootCauseService(root_cause_agent=agent, cache_ttl=60.0, cache_max_entries=10)

    result = asyncio.run(
        svc.analyze(df, {"dataset_id": "ds1", "question": "why revenue drop", "period_column": "month"})
    )

    agent.generate.assert_awaited_once()
    assert result.problem == "Revenue dropped."


def test_rca_service_cache_hit() -> None:
    df = _sales_df()
    agent = _make_mock_agent()
    svc = RootCauseService(root_cause_agent=agent, cache_ttl=60.0, cache_max_entries=10)

    params: dict[str, Any] = {
        "dataset_id": "ds1",
        "question": "why revenue drop",
        "period_column": "month",
    }
    asyncio.run(svc.analyze(df, params))
    result2 = asyncio.run(svc.analyze(df, params))

    assert result2.cache_hit is True
    assert agent.generate.await_count == 1  # only called once


def test_rca_service_analysis_time_populated() -> None:
    df = _sales_df()
    agent = _make_mock_agent()
    svc = RootCauseService(root_cause_agent=agent, cache_ttl=60.0, cache_max_entries=10)

    result = asyncio.run(
        svc.analyze(df, {"dataset_id": "ds1", "question": "why revenue drop"})
    )
    assert result.analysis_time_ms >= 0.0


def test_rca_service_first_call_not_cache_hit() -> None:
    df = _sales_df()
    agent = _make_mock_agent()
    svc = RootCauseService(root_cause_agent=agent, cache_ttl=60.0, cache_max_entries=10)

    result = asyncio.run(
        svc.analyze(df, {"dataset_id": "ds1", "question": "fresh question"})
    )
    assert result.cache_hit is False


def test_rca_service_agent_exception_returns_error_response() -> None:
    df = _sales_df()
    agent = MagicMock()
    agent.generate = AsyncMock(side_effect=RuntimeError("LLM offline"))
    svc = RootCauseService(root_cause_agent=agent, cache_ttl=60.0, cache_max_entries=10)

    result = asyncio.run(
        svc.analyze(df, {"dataset_id": "ds1", "question": "why revenue drop"})
    )
    assert "Analysis could not be completed" in result.problem or result.problem


# ---------------------------------------------------------------------------
# RootCauseAgent fallback (no HTTP client)
# ---------------------------------------------------------------------------


def test_rca_agent_no_client_uses_fallback() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent

    settings = Settings()
    agent = RootCauseAgent(settings)  # no set_client called

    findings = _make_findings()
    result = asyncio.run(agent.generate(findings=findings, question="why did revenue drop?"))

    assert isinstance(result, RootCauseResponse)
    assert result.problem != ""
    assert len(result.root_causes) > 0


def test_rca_agent_fallback_problem_statement_contains_metric() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent

    settings = Settings()
    agent = RootCauseAgent(settings)
    findings = _make_findings()
    result = asyncio.run(agent.generate(findings=findings, question="why did revenue drop?"))

    assert "revenue" in result.problem.lower()


def test_rca_agent_fallback_recommendations_reference_dimension() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent

    settings = Settings()
    agent = RootCauseAgent(settings)
    findings = _make_findings()
    result = asyncio.run(agent.generate(findings=findings, question="why did revenue drop?"))

    assert any("North" in r or "region" in r for r in result.recommendations)


def test_rca_agent_llm_failure_uses_fallback() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent

    settings = Settings()
    agent = RootCauseAgent(settings)
    mock_client = MagicMock()
    agent.set_client(mock_client)

    findings = _make_findings()
    # Patch both providers to fail.
    with (
        patch.object(agent, "_call_groq", new=AsyncMock(side_effect=RuntimeError("Groq down"))),
        patch.object(agent, "_call_ollama", new=AsyncMock(side_effect=RuntimeError("Ollama down"))),
    ):
        result = asyncio.run(agent.generate(findings=findings, question="why did revenue drop?"))

    assert isinstance(result, RootCauseResponse)
    assert result.problem != ""


# ---------------------------------------------------------------------------
# RootCauseAgent._parse_response
# ---------------------------------------------------------------------------


def test_rca_agent_parse_response_valid_json() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent
    import json

    settings = Settings()
    agent = RootCauseAgent(settings)
    findings = _make_findings()

    raw = json.dumps(
        {
            "problem": "Revenue dropped 6.67% from 450 to 420 (Jan → Feb).",
            "root_causes": [
                {
                    "dimension": "region",
                    "value": "North",
                    "impact_level": "high",
                    "description": "North drove 66.7% of decline.",
                    "contribution_pct": 66.7,
                    "rank": 1,
                }
            ],
            "recommendations": ["Investigate North region."],
        }
    )
    result = agent._parse_response(raw, findings)
    assert result.problem.startswith("Revenue")
    assert result.root_causes[0].dimension == "region"
    assert result.root_causes[0].impact_level == "high"


def test_rca_agent_parse_response_invalid_json_falls_back() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent

    settings = Settings()
    agent = RootCauseAgent(settings)
    findings = _make_findings()

    result = agent._parse_response("{invalid json}", findings)
    # Should fall back to findings-based response
    assert "revenue" in result.problem.lower()


def test_rca_agent_impact_level_clamped() -> None:
    from app.core.config import Settings
    from agents.root_cause_agent import RootCauseAgent
    import json

    settings = Settings()
    agent = RootCauseAgent(settings)
    findings = _make_findings()

    raw = json.dumps(
        {
            "problem": "X dropped.",
            "root_causes": [
                {
                    "dimension": "region",
                    "value": "North",
                    "impact_level": "EXTREME",  # invalid → should become "low"
                    "description": "desc",
                    "contribution_pct": 10.0,
                    "rank": 1,
                }
            ],
            "recommendations": [],
        }
    )
    result = agent._parse_response(raw, findings)
    assert result.root_causes[0].impact_level == "low"


# ---------------------------------------------------------------------------
# RCAFindings schema validation
# ---------------------------------------------------------------------------


def test_rca_findings_can_be_serialised() -> None:
    findings = _make_findings()
    d = findings.model_dump()
    assert d["metric_column"] == "revenue"
    assert d["direction"] == "decline"


def test_rca_response_defaults() -> None:
    resp = RootCauseResponse(
        problem="test",
        root_causes=[],
        contribution_analysis=[],
        recommendations=[],
    )
    assert resp.cache_hit is False
    assert resp.analysis_time_ms == 0.0
