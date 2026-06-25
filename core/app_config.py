"""Runtime app configuration stored in Postgres, encrypted at rest.

Most config is environment-driven (``core/config.py``), fixed at deploy time. A
few things must be editable from inside the running app — notably the Google
Workspace service-account credentials, which a CBM administrator configures
through the Mentor-Admin *Email Setup* screen rather than a redeploy. Those live
here: one row per logical key in an ``app_config`` table, the value encrypted
with :class:`core.crypto.SecretCipher` (Fernet, keyed by ``APP_ENCRYPTION_KEY``).

Inert without a database **and** an encryption key: :func:`make_app_config_store`
returns ``None``, and the app falls back to the env-var Google settings. The
table shares ``core.store.metadata`` so Alembic manages it alongside the
submission table.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, String, Table, Text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from .config import Settings
from .crypto import CryptoError, SecretCipher
from .store import make_async_engine, metadata

# The single logical key under which the Google Workspace config blob is stored.
GOOGLE_CONFIG_KEY = "google_workspace"

app_config = Table(
    "app_config",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value_encrypted", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AppConfigStore:
    """Read/write encrypted config rows. One instance per process is fine."""

    def __init__(self, database_url: str, cipher: SecretCipher) -> None:
        self._engine = make_async_engine(database_url)
        self._cipher = cipher

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
        """Decrypt and JSON-decode the value at ``key`` (None if absent)."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(app_config.c.value_encrypted).where(app_config.c.key == key)
                )
            ).first()
        if row is None:
            return None
        try:
            return json.loads(self._cipher.decrypt(row[0]))
        except (CryptoError, json.JSONDecodeError):
            return None

    async def set_json(self, key: str, value: dict[str, Any]) -> None:
        """Encrypt + upsert a JSON value at ``key``."""
        token = self._cipher.encrypt(json.dumps(value))
        now = _now()
        stmt = (
            pg_insert(app_config)
            .values(key=key, value_encrypted=token, updated_at=now)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value_encrypted": token, "updated_at": now},
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def get_meta(self, key: str) -> Optional[dict[str, Any]]:
        """Non-secret metadata for a key: whether it's set + when last updated.
        Used by the setup screen to show 'configured ✓' without exposing the value."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(app_config.c.updated_at).where(app_config.c.key == key)
                )
            ).first()
        if row is None:
            return None
        return {"updatedAt": row[0].isoformat() if row[0] else None}

    # --- Google Workspace config convenience ---

    async def get_google_config(self) -> Optional[dict[str, Any]]:
        return await self.get_json(GOOGLE_CONFIG_KEY)

    async def set_google_config(self, config: dict[str, Any]) -> None:
        await self.set_json(GOOGLE_CONFIG_KEY, config)

    async def dispose(self) -> None:
        await self._engine.dispose()


def make_app_config_store(settings: Settings) -> Optional[AppConfigStore]:
    """An encrypted config store when a DB + encryption key are configured, else None."""
    if not (settings.database_url and settings.app_encryption_key):
        return None
    try:
        cipher = SecretCipher(settings.app_encryption_key)
    except CryptoError:
        return None
    return AppConfigStore(settings.database_url, cipher)
