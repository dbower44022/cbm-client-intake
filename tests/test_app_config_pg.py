"""Integration test for the encrypted app_config store. Skipped unless
TEST_DATABASE_URL is set (same Postgres as test_store_pg.py)."""

from __future__ import annotations

import os

import pytest

from core.app_config import AppConfigStore
from core.crypto import SecretCipher

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


async def test_google_config_round_trip_encrypted():
    cipher = SecretCipher(SecretCipher.generate_key())
    store = AppConfigStore(_URL, cipher)
    await store.create_all()
    try:
        cfg = {
            "service_account_json": '{"type": "service_account", "private_key": "SECRET"}',
            "delegated_admin": "admin@cbmentors.org",
            "directory_check": True,
            "create_mailbox": True,
        }
        await store.set_google_config(cfg)
        assert await store.get_google_config() == cfg
        meta = await store.get_meta("google_workspace")
        assert meta and meta["updatedAt"]

        # Upsert overwrites in place (no duplicate row, value re-encrypted).
        cfg2 = dict(cfg, create_mailbox=False)
        await store.set_google_config(cfg2)
        assert (await store.get_google_config())["create_mailbox"] is False
    finally:
        await store.dispose()


async def test_wrong_key_cannot_decrypt():
    written = AppConfigStore(_URL, SecretCipher(SecretCipher.generate_key()))
    await written.create_all()
    try:
        await written.set_google_config({"delegated_admin": "a@b.org", "service_account_json": "{}"})
    finally:
        await written.dispose()
    # A store with a different key can't read it (decrypt fails -> None, not a crash).
    other = AppConfigStore(_URL, SecretCipher(SecretCipher.generate_key()))
    try:
        assert await other.get_google_config() is None
    finally:
        await other.dispose()
