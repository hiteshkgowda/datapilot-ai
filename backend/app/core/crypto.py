"""Symmetric encryption for credentials at rest.

Wraps Fernet (AES-128-CBC + HMAC) so database passwords are never written to
disk in plaintext. The key comes from configuration (``DB_ENCRYPTION_KEY``); if
it is absent, encryption is unavailable and the service refuses to persist
secrets.
"""

from __future__ import annotations

from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import DataAssistantError


class CredentialCipher:
    """Encrypt and decrypt secret strings with a configured Fernet key."""

    def __init__(self, key: Optional[str]) -> None:
        self._fernet: Optional[Fernet] = None
        if key:
            try:
                self._fernet = Fernet(key.encode("utf-8"))
            except (ValueError, TypeError) as exc:
                raise DataAssistantError(
                    "DB_ENCRYPTION_KEY is not a valid Fernet key."
                ) from exc

    @property
    def available(self) -> bool:
        """Whether encryption is configured."""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt ``plaintext`` into a token string."""
        if self._fernet is None:
            raise DataAssistantError(
                "Cannot store a password: no DB_ENCRYPTION_KEY is configured."
            )
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Decrypt a token string back into plaintext."""
        if self._fernet is None:
            raise DataAssistantError(
                "Cannot decrypt a password: no DB_ENCRYPTION_KEY is configured."
            )
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise DataAssistantError(
                "Stored credential could not be decrypted (key mismatch?)."
            ) from exc

    @staticmethod
    def generate_key() -> str:
        """Generate a new base64 Fernet key."""
        return Fernet.generate_key().decode("utf-8")
