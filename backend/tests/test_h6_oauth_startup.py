"""H-6: Google OAuth credential validation at startup.

Tests that _validate_production_secrets raises RuntimeError with clear messages
when GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET are missing in production, and
that development mode is unaffected.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import _validate_production_secrets


def _prod(**overrides) -> Settings:
    """Return a production Settings instance with all required secrets set by default."""
    defaults = dict(
        app_env="production",
        crud_secret_key="test-crud-secret-key-32chars-min!!",
        db_encryption_key="test-db-encryption-key-32chars!!",
        backend_jwt_secret="test-backend-jwt-secret-32chars!",
        llm_provider="ollama",
        google_client_id="123456.apps.googleusercontent.com",
        google_client_secret="GOCSPX-test-secret",
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestGoogleClientIdRequired:
    def test_missing_client_id_raises_in_production(self) -> None:
        settings = _prod(google_client_id=None)
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        assert "GOOGLE_CLIENT_ID" in str(exc_info.value)

    def test_empty_string_client_id_raises_in_production(self) -> None:
        settings = _prod(google_client_id="")
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        assert "GOOGLE_CLIENT_ID" in str(exc_info.value)

    def test_present_client_id_does_not_raise(self) -> None:
        settings = _prod(google_client_id="valid-client-id.apps.googleusercontent.com")
        # Should not raise (all other required secrets are set in _prod defaults).
        _validate_production_secrets(settings)


class TestGoogleClientSecretRequired:
    def test_missing_client_secret_raises_in_production(self) -> None:
        settings = _prod(google_client_secret=None)
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        assert "GOOGLE_CLIENT_SECRET" in str(exc_info.value)

    def test_empty_string_client_secret_raises_in_production(self) -> None:
        settings = _prod(google_client_secret="")
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        assert "GOOGLE_CLIENT_SECRET" in str(exc_info.value)

    def test_present_client_secret_does_not_raise(self) -> None:
        settings = _prod(google_client_secret="GOCSPX-valid-secret")
        _validate_production_secrets(settings)


class TestBothCredentialsRequired:
    def test_both_missing_error_mentions_both(self) -> None:
        settings = _prod(google_client_id=None, google_client_secret=None)
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        msg = str(exc_info.value)
        assert "GOOGLE_CLIENT_ID" in msg
        assert "GOOGLE_CLIENT_SECRET" in msg

    def test_error_includes_google_cloud_console_hint(self) -> None:
        settings = _prod(google_client_id=None)
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_secrets(settings)
        assert "Google Cloud Console" in str(exc_info.value)

    def test_both_present_no_error(self) -> None:
        settings = _prod()
        # Must complete without raising.
        _validate_production_secrets(settings)


class TestDevelopmentModeUnaffected:
    def test_missing_oauth_creds_ok_in_development(self) -> None:
        """Development mode never calls _validate_production_secrets via lifespan,
        but even if called directly it should raise only for production checks."""
        dev_settings = Settings(
            app_env="development",
            google_client_id=None,
            google_client_secret=None,
        )
        # is_production is False — lifespan skips the call entirely.
        assert dev_settings.is_production is False
