"""The browser's own failures reach the server log (v0.260.0, Doug's ruling
10-17-26 after a "Failed to fetch" on the Phase 2 live pass left no trace).

Pinned: the endpoint always answers 204 and writes one WARNING
``client-error`` line per report; it reads only the fields it names, strips
query strings and other sites' addresses, cannot have a log line forged
through it, has its own limit, and names the signed-in user from the session
only. The timing line writes every 5xx at WARNING and a crash at ERROR. The
shared busy.js reports network failures, timeouts, 5xx answers and script
errors, and never reports itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import client_errors

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_limits():
    client_errors._hits.clear()
    client_errors._warned.clear()
    yield
    client_errors._hits.clear()
    client_errors._warned.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(client_errors.router)
    return TestClient(app)


def _lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "cbm_intake.client_errors" and r.getMessage().startswith("client-error kind=")]


def test_a_network_failure_becomes_one_warning_line(caplog):
    caplog.set_level(logging.WARNING, logger="cbm_intake.client_errors")
    res = _client().post(client_errors.PATH, json={"reports": [{
        "kind": "network", "method": "put",
        "url": "https://evil.example/campaigns/api/campaigns/abc/relations?token=secret",
        "status": 0, "ms": 1234.6, "page": "/campaigns/record/abc?x=1",
        "message": "Failed to fetch", "queued": 7,
    }]}, headers={"user-agent": "Chrome/141"})
    assert res.status_code == 204
    line, = _lines(caplog)
    assert line.startswith("client-error kind=network page=/campaigns/record/abc ")
    assert "request=PUT /campaigns/api/campaigns/abc/relations " in line
    assert "secret" not in line and "evil.example" not in line
    assert "status=0 ms=1234 " in line and "queued=7s" in line
    assert "user=- " in line and "agent=Chrome/141" in line
    assert line.endswith("message=Failed to fetch")


def test_a_report_cannot_forge_a_log_line(caplog):
    caplog.set_level(logging.WARNING, logger="cbm_intake.client_errors")
    _client().post(client_errors.PATH, json={"kind": "script",
                                             "message": "boom\nINFO fake line\r\x00", "method": "GET;rm"})
    line, = _lines(caplog)
    assert "\n" not in line and "\r" not in line and "\x00" not in line
    assert "request=- " in line


def test_unknown_kinds_and_garbage_write_nothing_and_still_answer_204(caplog):
    caplog.set_level(logging.WARNING, logger="cbm_intake.client_errors")
    c = _client()
    assert c.post(client_errors.PATH, json={"kind": "nonsense"}).status_code == 204
    assert c.post(client_errors.PATH, content=b"not json", headers={"content-type": "application/json"}).status_code == 204
    assert c.post(client_errors.PATH, content=b"x" * (client_errors.MAX_BODY + 10)).status_code == 204
    assert _lines(caplog) == []


def test_the_limit_is_its_own_and_says_so_once(caplog):
    caplog.set_level(logging.WARNING, logger="cbm_intake.client_errors")
    c = _client()
    for _ in range(client_errors.LIMIT_PER_WINDOW + 5):
        assert c.post(client_errors.PATH, json={"kind": "http", "status": 502}).status_code == 204
    assert len(_lines(caplog)) == client_errors.LIMIT_PER_WINDOW
    over = [r for r in caplog.records if "over the limit" in r.getMessage()]
    assert len(over) == 1


def test_the_user_comes_from_the_session_never_the_report(caplog):
    from starlette.middleware.sessions import SessionMiddleware

    caplog.set_level(logging.WARNING, logger="cbm_intake.client_errors")
    app = FastAPI()
    app.include_router(client_errors.router)

    @app.get("/login")
    def login(request: __import__("fastapi").Request):
        request.session["staff_user"] = {"userName": "mark"}
        return {}

    app.add_middleware(SessionMiddleware, secret_key="s")
    c = TestClient(app)
    c.get("/login")
    c.post(client_errors.PATH, json={"kind": "network", "user": "someone-else"})
    line, = _lines(caplog)
    assert "user=mark " in line and "someone-else" not in line


def test_timing_line_writes_5xx_at_warning_and_a_crash_at_error(monkeypatch, caplog):
    from core.app import create_app
    from core.config import get_settings

    monkeypatch.setenv("REQUEST_TIMING_LOG_MS", "999999")
    get_settings.cache_clear()
    try:
        app = create_app([])

        @app.get("/api/test-boom")
        def boom():
            raise RuntimeError("kaboom")

        @app.get("/api/test-503")
        def unavailable():
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="down")

        caplog.set_level(logging.INFO)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/api/test-503").status_code == 503
        assert c.get("/api/test-boom").status_code == 500
    finally:
        get_settings.cache_clear()
    warn = [r for r in caplog.records if r.getMessage().startswith("timing GET /api/test-503 503")]
    assert warn and warn[0].levelno == logging.WARNING
    crash = [r for r in caplog.records if "timing GET /api/test-boom 500" in r.getMessage()]
    assert crash and crash[0].levelno == logging.ERROR and "CRASHED" in crash[0].getMessage()
    assert crash[0].exc_info is not None


def test_the_endpoint_is_mounted_on_every_app():
    from core.app import create_app

    paths = {getattr(r, "path", "") for r in create_app([]).routes}
    assert client_errors.PATH in paths


def test_busy_js_reports_failures_and_never_itself():
    js = (ROOT / "frontend" / "shared" / "busy.js").read_text(encoding="utf-8")
    assert 'var REPORT_PATH = "/api/client-errors";' in js
    for kind in ('kind: "http"', 'kind: aborted ? "timeout" : "network"', 'kind: "script"', 'kind: "rejection"'):
        assert kind in js, kind
    assert "path === REPORT_PATH" in js and "_cbmPath !== REPORT_PATH" in js
    assert "keepalive: true" in js            # survives the page closing
    assert "sessionStorage" in js             # a report a broken connection could not send waits
    assert "REPORT_MAX = 20" in js
    # never a request body
    assert "init.body" not in js and "body: body" in js
