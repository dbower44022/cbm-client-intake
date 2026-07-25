"""Analytics Phase D — operational/computed metrics + the portal dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analytics.registry import MetricContext, get_metric
from analytics.service import build_time_range
from analytics.store import MemoryAnalyticsStore
from core.app import create_app
from core.config import get_settings
from forms import info_request

_ADMIN = {"userName": "an", "name": "Ana", "isAdmin": True, "userId": "u", "token": "t",
          "teams": [], "roles": []}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class SubStore:
    async def submissions_by_month(self):
        return [{"month": "2026-05", "count": 3}, {"month": "2026-06", "count": 5}]

    async def counts_by_status(self):
        return {"completed": 100, "needs_attention": 3, "pending": 2, "discarded": 9}


class FakeEspo:
    def __init__(self):
        self.data = {
            "CMentorProfile": [{"id": "m1", "mentorStatus": "Active"}, {"id": "m2", "mentorStatus": "Active"}],
            "CEngagement": [
                {"id": "e1", "engagementStatus": "Active", "createdAt": "2026-06-01 10:00:00", "name": "A"},
                {"id": "e2", "engagementStatus": "Submitted", "createdAt": "2026-06-02 10:00:00", "name": "B"},
            ],
            "CContribution": [
                {"receivedDate": "2026-06-10", "amount": 100, "status": "Received"},
                {"receivedDate": "2026-06-20", "amount": 50, "status": "Received"},
                {"receivedDate": "2026-06-25", "amount": 999, "status": "Pledged"},
            ],
        }

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        rows = list(self.data.get(entity, []))
        for c in where or []:
            a, t, v = c["attribute"], c["type"], c.get("value")
            if t == "equals":
                rows = [r for r in rows if r.get(a) == v]
            elif t == "in":
                rows = [r for r in rows if r.get(a) in set(v)]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}


# --- computed / operational metrics -----------------------------------------
@pytest.mark.asyncio
async def test_submissions_per_month():
    ctx = MetricContext(settings=get_settings(), espo=None, store=None,
                        submission_store=SubStore(), time_range=build_time_range("all"))
    r = await get_metric("submissions_per_month").compute(ctx)
    pts = {p["bucket"]: p["value"] for p in r.data["points"]}
    assert pts["2026-05"] == 3 and pts["2026-06"] == 5


@pytest.mark.asyncio
async def test_submission_queue_excludes_completed():
    ctx = MetricContext(settings=get_settings(), espo=None, store=None,
                        submission_store=SubStore(), time_range=build_time_range("all"))
    r = await get_metric("submission_queue").compute(ctx)
    labels = {i["label"]: i["value"] for i in r.data["items"]}
    assert labels["Needs attention"] == 3 and labels["Pending"] == 2
    assert "Completed" not in labels and "Discarded" not in labels


@pytest.mark.asyncio
async def test_contributions_currency_series():
    ctx = MetricContext(settings=get_settings(), espo=FakeEspo(), store=None,
                        submission_store=None, time_range=build_time_range("all"))
    r = await get_metric("contributions_received_per_month").compute(ctx)
    assert r.data["format"] == "currency"
    pts = {p["bucket"]: p["value"] for p in r.data["points"]}
    assert pts["2026-06"] == 150  # Pledged excluded, only Received counted


@pytest.mark.asyncio
async def test_store_metric_unavailable_without_store():
    ctx = MetricContext(settings=get_settings(), espo=None, store=None,
                        submission_store=None, time_range=build_time_range("all"))
    r = await get_metric("submissions_per_month").compute(ctx)
    assert r.error


# --- portal dashboard endpoint ----------------------------------------------
def _app(monkeypatch, *, user, fake=None, sub=None):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.analytics_store = MemoryAnalyticsStore()
    app.state.submission_store = sub
    monkeypatch.setattr("analytics.router.current_user", lambda r: user)
    if fake is not None:
        monkeypatch.setattr("analytics.router._system_client", lambda s: fake)
    return app


def test_portal_dashboard_renders(monkeypatch):
    app = _app(monkeypatch, user=_ADMIN, fake=FakeEspo(), sub=SubStore())
    with TestClient(app) as c:
        body = c.get("/analytics/api/portal").json()
    # the seeded system-overview page is flagged portal_dashboard=True
    assert body["available"] is True
    panels = {p["key"]: p for p in body["panels"]}
    assert panels["active_mentors"]["result"]["data"]["value"] == 2


def test_portal_dashboard_hidden_for_non_viewer(monkeypatch):
    outsider = {"userName": "x", "name": "X", "isAdmin": False, "teams": ["Mentor Team"], "roles": []}
    app = _app(monkeypatch, user=outsider, fake=FakeEspo())
    with TestClient(app) as c:
        body = c.get("/analytics/api/portal").json()
    assert body["available"] is False


def test_portal_dashboard_requires_auth(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.analytics_store = MemoryAnalyticsStore()
    monkeypatch.setattr("analytics.router.current_user", lambda r: None)
    with TestClient(app) as c:
        assert c.get("/analytics/api/portal").status_code == 401
