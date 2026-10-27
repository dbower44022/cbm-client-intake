"""One mailing connection store per process (v0.290.1).

v0.290.0 built a new ConnectionStore — a new database engine with its own
pool — on every web request that talked to Constant Contact, and never
closed it. Four requests exhausted crm-test's database connections on
10-27-26 (Pick the email answered 500 with TooManyConnectionsError).
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from campaigns import list_sync
from core import mailing, mailing_sync

URL = "postgresql://u:p@db.example:5432/app"


def _settings(**over):
    base = dict(database_url=URL, app_encryption_key="", mailing_client_id="id",
                mailing_client_secret="secret", mailing_base_url=mailing.DEFAULT_BASE_URL,
                espo_base_url="https://crm.example", espo_api_key="k", request_timeout_seconds=5)
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(mailing, "_SHARED_STORES", {})


def test_repeat_calls_reuse_one_store():
    s = _settings()
    first = mailing.shared_connection_store(s)
    assert first is not None
    assert mailing.shared_connection_store(s) is first


def test_no_database_means_no_store():
    assert mailing.shared_connection_store(_settings(database_url="")) is None


def test_a_different_database_gets_its_own_store():
    a = mailing.shared_connection_store(_settings())
    b = mailing.shared_connection_store(_settings(database_url=URL + "2"))
    assert a is not b


def test_web_requests_share_the_store():
    """mail_clients runs once per web request (Sync now, sign-off, Pick the email)."""
    s = _settings()
    _, first = list_sync.mail_clients(s)
    _, second = list_sync.mail_clients(s)
    assert first is second


def test_worker_passes_share_the_store():
    s = _settings()
    _, _, first = mailing_sync._clients(s, None, None, None)
    _, _, second = mailing_sync._clients(s, None, None, None)
    assert first is second
    assert first is list_sync.mail_clients(s)[1]


def test_nothing_else_builds_a_store_directly():
    """A direct make_connection_store call is a pool nobody closes."""
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        # create_app builds the app's own store once per app, which is no leak.
        if rel.startswith((".venv/", "tests/")) or rel in ("core/mailing.py", "core/app.py"):
            continue
        if "make_connection_store(" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert offenders == []
