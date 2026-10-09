"""The per-request timing line and Server-Timing header (v0.248.0)."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from core.app import create_app
from forms import info_request


def test_api_requests_carry_server_timing_and_a_log_line(caplog):
    with TestClient(create_app([info_request.SPEC])) as c:
        with caplog.at_level(logging.INFO, logger="cbm_intake"):
            r = c.post("/api/info-request/intake", json={})
        assert r.status_code in (400, 422)
        st = r.headers.get("server-timing", "")
        assert st.startswith("app;dur=") and "crm;dur=" in st and "0 calls" in st
        lines = [m for m in caplog.messages if m.startswith("timing POST /api/info-request/intake")]
        assert len(lines) == 1 and "crm=0/0ms" in lines[0]
        # Pages, assets and /healthz are not timed.
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="cbm_intake"):
            h = c.get("/healthz")
        assert "server-timing" not in h.headers
        assert not any(m.startswith("timing ") for m in caplog.messages)


def test_threshold_silences_fast_requests(monkeypatch, caplog):
    from core.config import get_settings

    with TestClient(create_app([info_request.SPEC])) as c:
        monkeypatch.setattr(get_settings(), "request_timing_log_ms", 60_000)
        with caplog.at_level(logging.INFO, logger="cbm_intake"):
            r = c.post("/api/info-request/intake", json={})
        assert "server-timing" in r.headers, "the header always rides"
        assert not any(m.startswith("timing ") for m in caplog.messages)
