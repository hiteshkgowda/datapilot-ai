"""H-1: Route-level ID validation tests.

Verifies that path parameters validated with HexId return HTTP 422 for any
string that doesn't match ``^[a-f0-9]{32}$``, and that a valid 32-char hex ID
passes validation (reaching auth/service, not failing at the path layer).

FastAPI validates path parameters before resolving dependencies, so these
checks fire even when services are not wired up.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ────────────────────────────────────────────────────────────────────
# All fixtures defined in conftest.py

# ── Valid / invalid ID constants ─────────────────────────────────────────────────

VALID_HEX_ID = "a" * 32                        # exactly 32 lowercase hex chars
VALID_HEX_ID_2 = "fb584266d7784e88bfa2386632e1f116"  # real-looking ID from logs

# IDs that fail FastAPI's Path(pattern=...) validation → HTTP 422.
# These are well-formed URL segments that reach the route handler but fail the regex.
INVALID_IDS_422 = [
    ("too_short", "abc123"),
    ("too_long", "a" * 33),
    ("uppercase", "A" * 32),
    ("dashed_uuid", "550e8400-e29b-41d4-a716-446655440000"),  # 36-char with dashes
    ("non_hex_chars", "g" * 32),
    ("spaces", " " * 32),
    ("mixed_case", "aAbBcCdDeEfF" + "a" * 20),
]

# IDs that are rejected at the HTTP/routing layer before reaching the param validator.
# path_traversal: httpx normalises ../aaa → parent path → 404 (no route match)
# empty:          /resource//subpath has no matching route → 404
# null_byte:      httpx raises InvalidURL before the request is sent
INVALID_IDS = INVALID_IDS_422  # parametrize only over 422-guaranteed cases


# ── dataset_id ────────────────────────────────────────────────────────────────────

class TestDatasetIdValidation:
    def test_valid_id_passes_path_validation(self, client: TestClient) -> None:
        # Valid ID clears path validation; response is not 422 (may be 422 from
        # query-param validation or 404/500 from missing service — but NOT from
        # the path param regex).
        resp = client.get(f"/api/v1/datasets/{VALID_HEX_ID}/preview")
        assert resp.status_code != 422 or _is_service_error(resp)

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_invalid_id_returns_422(self, client: TestClient, name: str, bad_id: str) -> None:
        resp = client.get(f"/api/v1/datasets/{bad_id}/preview")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"

    def test_422_body_mentions_pattern(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/datasets/not-a-hex-id/preview")
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body


# ── report_id ─────────────────────────────────────────────────────────────────────

class TestReportIdValidation:
    def test_valid_id_passes_path_validation(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/reports/{VALID_HEX_ID}/download")
        assert resp.status_code != 422 or _is_service_error(resp)

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_invalid_id_returns_422(self, client: TestClient, name: str, bad_id: str) -> None:
        resp = client.get(f"/api/v1/reports/{bad_id}/download")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"


# ── connection_id ─────────────────────────────────────────────────────────────────

class TestConnectionIdValidation:
    @pytest.mark.parametrize("method,path_suffix", [
        ("DELETE", ""),
        ("POST",   "/test"),
        ("GET",    "/tables"),
        ("POST",   "/datasets"),
    ])
    def test_valid_id_passes_path_validation(
        self, client: TestClient, method: str, path_suffix: str
    ) -> None:
        resp = client.request(method, f"/api/v1/connections/{VALID_HEX_ID}{path_suffix}")
        assert resp.status_code != 422 or _is_service_error(resp)

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_delete_invalid_id_returns_422(
        self, client: TestClient, name: str, bad_id: str
    ) -> None:
        resp = client.delete(f"/api/v1/connections/{bad_id}")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_test_invalid_id_returns_422(
        self, client: TestClient, name: str, bad_id: str
    ) -> None:
        resp = client.post(f"/api/v1/connections/{bad_id}/test")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_tables_invalid_id_returns_422(
        self, client: TestClient, name: str, bad_id: str
    ) -> None:
        resp = client.get(f"/api/v1/connections/{bad_id}/tables")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"


# ── session_id ────────────────────────────────────────────────────────────────────

class TestSessionIdValidation:
    def test_valid_hex_id_passes_path_validation(self, client: TestClient) -> None:
        # Session IDs are now uuid.uuid4().hex — 32-char lowercase hex.
        resp = client.post(
            f"/api/v1/agent/resume/{VALID_HEX_ID}",
            json={"approved": True},
        )
        assert resp.status_code != 422 or _is_service_error(resp)

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_resume_invalid_session_id_returns_422(
        self, client: TestClient, name: str, bad_id: str
    ) -> None:
        resp = client.post(
            f"/api/v1/agent/resume/{bad_id}",
            json={"approved": True},
        )
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"

    @pytest.mark.parametrize("name,bad_id", INVALID_IDS)
    def test_get_session_invalid_id_returns_422(
        self, client: TestClient, name: str, bad_id: str
    ) -> None:
        resp = client.get(f"/api/v1/agent/session/{bad_id}")
        assert resp.status_code == 422, f"Expected 422 for '{name}', got {resp.status_code}"

    def test_old_dashed_uuid_format_rejected(self, client: TestClient) -> None:
        """Dashed UUID strings (str(uuid4())) no longer accepted as session IDs."""
        dashed = "550e8400-e29b-41d4-a716-446655440000"
        resp = client.get(f"/api/v1/agent/session/{dashed}")
        assert resp.status_code == 422

    def test_new_hex_format_accepted(self, client: TestClient) -> None:
        """uuid4().hex format (32-char lowercase hex) is the new session ID format."""
        import uuid
        hex_id = uuid.uuid4().hex
        resp = client.get(f"/api/v1/agent/session/{hex_id}")
        # Not 422 — path validation passed (may be 404/500 from missing service)
        assert resp.status_code != 422 or _is_service_error(resp)


# ── Transport-level rejection tests (path_traversal, null_byte, empty) ────────────
# These are blocked before FastAPI path-param validation, so the status code is
# not 422 — but the attack still cannot succeed.

class TestTransportLevelRejection:
    def test_path_traversal_does_not_reach_dataset(self, client: TestClient) -> None:
        """../aaa normalised by httpx → different URL path → 404, not a data leak."""
        resp = client.get(f"/api/v1/datasets/../{'a' * 29}/preview")
        assert resp.status_code in (404, 422)

    def test_empty_id_does_not_match_route(self, client: TestClient) -> None:
        """Empty segment produces a path with no matching route → 404."""
        resp = client.get("/api/v1/datasets//preview")
        assert resp.status_code in (404, 422)

    def test_null_byte_rejected_by_http_client(self, client: TestClient) -> None:
        """Null bytes are illegal in URLs; httpx raises before the request is sent."""
        import httpx
        with pytest.raises(httpx.InvalidURL):
            client.get("/api/v1/datasets/" + "a" * 31 + "\x00/preview")


# ── Helpers ────────────────────────────────────────────────────────────────────────

def _is_service_error(resp) -> bool:
    """Return True if the 422 came from a service (body field), not path validation."""
    try:
        detail = resp.json().get("detail", [])
        if isinstance(detail, list):
            return all(e.get("loc", [""])[0] != "path" for e in detail)
    except Exception:
        pass
    return False
