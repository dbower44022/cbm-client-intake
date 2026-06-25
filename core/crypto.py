"""Symmetric encryption for secrets stored in the app database.

The Google Workspace service-account key (a high-value secret) is configured at
runtime through the Mentor-Admin setup screen and stored in Postgres, encrypted
at rest with a Fernet key held only in the environment (``APP_ENCRYPTION_KEY``).
So a database dump alone does not expose the key — you also need the app's
encryption key, which lives in the deploy secret store, never in the DB.

``APP_ENCRYPTION_KEY`` is a urlsafe-base64 32-byte Fernet key; generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(Exception):
    """The encryption key is missing/invalid, or a value could not be decrypted."""


class SecretCipher:
    """Encrypt/decrypt short secret strings with a Fernet key."""

    def __init__(self, key: str) -> None:
        if not key:
            raise CryptoError("APP_ENCRYPTION_KEY is not set")
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as exc:
            raise CryptoError(f"APP_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise CryptoError(
                "could not decrypt a stored secret — the APP_ENCRYPTION_KEY may have "
                "changed since it was written"
            ) from exc

    @staticmethod
    def generate_key() -> str:
        """A fresh urlsafe-base64 Fernet key (for operators setting up the secret)."""
        return Fernet.generate_key().decode()
