"""Symmetric encryption for secrets stored in the app database.

The Google Workspace service-account key (a high-value secret) is configured at
runtime through the Mentor-Admin setup screen and stored in Postgres, encrypted
at rest with a Fernet key held only in the environment (``APP_ENCRYPTION_KEY``).
So a database dump alone does not expose the key — you also need the app's
encryption key, which lives in the deploy secret store, never in the DB.

``APP_ENCRYPTION_KEY`` is a urlsafe-base64 32-byte Fernet key; generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

**Rotating the key** (OPEN-ITEMS #33, Doug's option B, 11-04-26): the setting
may hold several keys separated by commas, newest first — ``NEW,OLD``. New
values are encrypted with the first; a value encrypted with any of them still
decrypts. ``scripts/rotate_encryption_key.py`` then re-encrypts every stored
secret with the first key, after which the old key can be removed and opens
nothing that is stored.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CryptoError(Exception):
    """The encryption key is missing/invalid, or a value could not be decrypted."""


def split_keys(key) -> list[str]:
    """The keys in an ``APP_ENCRYPTION_KEY`` value, newest first."""
    if isinstance(key, bytes):
        key = key.decode()
    return [k.strip() for k in str(key or "").split(",") if k.strip()]


class SecretCipher:
    """Encrypt/decrypt short secret strings with a Fernet key — or, while a
    key is being rotated, several (``NEW,OLD``): encrypt with the first,
    decrypt with any."""

    def __init__(self, key: str) -> None:
        keys = split_keys(key)
        if not keys:
            raise CryptoError("APP_ENCRYPTION_KEY is not set")
        try:
            fernets = [Fernet(k.encode()) for k in keys]
        except (ValueError, TypeError) as exc:
            raise CryptoError(f"APP_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc
        self._primary = fernets[0]
        self.key_count = len(fernets)
        self._fernet = MultiFernet(fernets) if len(fernets) > 1 else fernets[0]

    def is_current(self, token: str) -> bool:
        """True when ``token`` is already encrypted with the first (newest) key."""
        try:
            self._primary.decrypt(token.encode())
            return True
        except InvalidToken:
            return False

    def rotate(self, token: str) -> str:
        """``token`` re-encrypted with the first key (it must decrypt with one)."""
        return self.encrypt(self.decrypt(token))

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
