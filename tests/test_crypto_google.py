"""Encryption helper + Google Directory account-creation mapping."""

from __future__ import annotations

import json

import httpx
import pytest

from core.crypto import CryptoError, SecretCipher
from core.google_directory import (
    GoogleDirectory,
    GoogleDirectoryError,
    MailboxStatus,
    gen_temp_password,
    resolve_google_directory,
)


# --- crypto ---

def test_cipher_round_trip():
    cipher = SecretCipher(SecretCipher.generate_key())
    token = cipher.encrypt('{"a": 1}')
    assert token != '{"a": 1}'
    assert cipher.decrypt(token) == '{"a": 1}'


def test_cipher_requires_key():
    with pytest.raises(CryptoError):
        SecretCipher("")


def test_cipher_rejects_bad_key():
    with pytest.raises(CryptoError):
        SecretCipher("not-a-fernet-key")


def test_cipher_wrong_key_fails_to_decrypt():
    token = SecretCipher(SecretCipher.generate_key()).encrypt("secret")
    with pytest.raises(CryptoError):
        SecretCipher(SecretCipher.generate_key()).decrypt(token)


# --- temp password ---

def test_temp_password_is_strong():
    pw = gen_temp_password()
    assert len(pw) >= 12
    assert any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
    assert any(c in "!@#$%^&*-_" for c in pw)
    assert gen_temp_password() != gen_temp_password()  # random


# --- Google create_user (httpx mocked) ---

def _directory():
    return GoogleDirectory({"type": "service_account"}, "admin@cbmentors.org")


def _patch(monkeypatch, handler, *, token="tok"):
    async def tok_fn(scopes=None):
        return token
    gd = _directory()
    monkeypatch.setattr(gd, "_access_token", tok_fn)
    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    return gd


@pytest.mark.asyncio
async def test_create_user_posts_expected_body(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["method"] = request.method
        return httpx.Response(200, json={"id": "1", "primaryEmail": "jane.doe@cbmentors.org"})

    gd = _patch(monkeypatch, handler)
    await gd.create_user(
        "jane.doe@cbmentors.org", "Jane", "Doe",
        recovery_email="jane@personal.com", temp_password="TempPw1!",
    )
    assert seen["method"] == "POST"
    body = seen["body"]
    assert body["primaryEmail"] == "jane.doe@cbmentors.org"
    assert body["name"] == {"givenName": "Jane", "familyName": "Doe"}
    assert body["password"] == "TempPw1!"
    assert body["changePasswordAtNextLogin"] is True
    assert body["recoveryEmail"] == "jane@personal.com"


@pytest.mark.asyncio
async def test_create_user_409_is_idempotent(monkeypatch):
    gd = _patch(monkeypatch, lambda req: httpx.Response(409, json={"error": "duplicate"}))
    await gd.create_user("x@cbmentors.org", "X", "Y", recovery_email=None, temp_password="p")  # no raise


@pytest.mark.asyncio
async def test_create_user_error_raises(monkeypatch):
    gd = _patch(monkeypatch, lambda req: httpx.Response(403, text="forbidden"))
    with pytest.raises(GoogleDirectoryError):
        await gd.create_user("x@cbmentors.org", "X", "Y", recovery_email=None, temp_password="p")


@pytest.mark.asyncio
async def test_create_user_no_token_raises(monkeypatch):
    gd = _directory()

    async def no_token(scopes=None):
        return None

    monkeypatch.setattr(gd, "_access_token", no_token)
    with pytest.raises(GoogleDirectoryError):
        await gd.create_user("x@cbmentors.org", "X", "Y", recovery_email=None, temp_password="p")


# --- config resolution ---

class _Settings:
    google_directory_check = False
    google_service_account_json = ""
    google_delegated_admin = ""
    google_create_mailbox = False
    request_timeout_seconds = 20


def test_resolve_prefers_db_config():
    db = {
        "service_account_json": json.dumps({"type": "service_account"}),
        "delegated_admin": "admin@cbmentors.org",
        "directory_check": True,
        "create_mailbox": True,
    }
    r = resolve_google_directory(_Settings(), db)
    assert r.directory is not None and r.check_enabled and r.create_enabled


def test_resolve_db_create_requires_directory():
    # Invalid JSON -> no directory -> create can't be enabled.
    db = {"service_account_json": "nope", "delegated_admin": "a@b.org", "create_mailbox": True}
    r = resolve_google_directory(_Settings(), db)
    assert r.directory is None and r.create_enabled is False


def test_resolve_falls_back_to_env_off():
    r = resolve_google_directory(_Settings(), None)
    assert r.directory is None and r.check_enabled is False and r.create_enabled is False
