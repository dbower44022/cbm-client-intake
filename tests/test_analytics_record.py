"""Analytics Phase C — record-scoped metrics + the embedded record endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


class FakeEspo:
    def __init__(self):
        self.data = {
            "CMentorProfile": [{"id": "m1", "name": "Mentor One"}, {"id": "m2", "name": "Mentor Two"}],
            # CInformationRequest is used here as an unseeded BUILDER_ENTITIES scope
            # for the record-endpoint injection tests. Account was used originally
            # but now carries the record-company starter dashboard.
            "CInformationRequest": [{"id": "r1", "name": "Info request 1"},
                                    {"id": "r2", "name": "Info request 2"}],
            "CEngagement": [
                {"id": "e1", "name": "Alpha", "mentorProfileId": "m1", "informationRequestId": "r1",
                 "engagementStatus": "Active"},
                {"id": "e2", "name": "Bravo", "mentorProfileId": "m1", "informationRequestId": "r1",
                 "engagementStatus": "Submitted"},
                {"id": "e3", "name": "Charlie", "mentorProfileId": "m2", "informationRequestId": "r2",
                 "engagementStatus": "Active"},
            ],
        }
        self.list_calls = 0
        self.forbid = False

    async def get(self, entity, record_id, select=None):
        if self.forbid:
            from core.espo import EspoError
            raise EspoError("get failed: HTTP 403 Forbidden")
        for r in self.data.get(entity, []):
            if r["id"] == record_id:
                return dict(r)
        from core.espo import EspoError
        raise EspoError("get failed: HTTP 404 Not Found")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        self.list_calls += 1
        rows = list(self.data.get(entity, []))
        for c in where or []:
            a, t, v = c["attribute"], c["type"], c.get("value")
            if t == "equals":
                rows = [r for r in rows if r.get(a) == v]
            elif t == "in":
                rows = [r for r in rows if r.get(a) in set(v)]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def metadata(self, key):
        return {}


def _app(monkeypatch, store, fake):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.analytics_store = store
    monkeypatch.setattr("analytics.router.current_user", lambda r: _ADMIN)
    monkeypatch.setattr("analytics.router._system_client", lambda s: fake)
    monkeypatch.setattr("analytics.router.client_for", lambda s, u: fake)
    return app


def _record_metric():
    return {
        "name": "Engagements for info request", "entity": "CEngagement",
        "definition": {"aggregation": {"kind": "count"}, "filters": []},
        "applies_to": ["CInformationRequest"], "context_param": "informationRequestId",
    }


# --- authoring validation ----------------------------------------------------
def test_record_metric_requires_context_param(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    with TestClient(_app(monkeypatch, MemoryAnalyticsStore(), FakeEspo())) as c:
        bad = c.post("/analytics/api/admin/metrics", json={
            "name": "x", "entity": "CEngagement",
            "definition": {"aggregation": {"kind": "count"}}, "applies_to": ["CMentorProfile"]})
    assert bad.status_code == 422


def test_record_page_rejects_system_metric(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    with TestClient(_app(monkeypatch, MemoryAnalyticsStore(), FakeEspo())) as c:
        # active_mentors is a code metric scoped to system only
        r = c.post("/analytics/api/admin/pages", json={
            "title": "Mentor page", "scope": "CMentorProfile",
            "panels": [{"title": "x", "metric_key": "active_mentors"}]})
    assert r.status_code == 422


# --- the record endpoint -----------------------------------------------------
def _seed_record_page(c):
    m = c.post("/analytics/api/admin/metrics", json=_record_metric()).json()["metric"]
    page = c.post("/analytics/api/admin/pages", json={
        "title": "Info Request Analytics", "scope": "CInformationRequest",
        "panels": [{"title": "Engagements", "metric_key": m["key"], "viz": "stat"}],
    }).json()["page"]
    return m, page


def test_record_view_injects_context(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    store, fake = MemoryAnalyticsStore(), FakeEspo()
    with TestClient(_app(monkeypatch, store, fake)) as c:
        _seed_record_page(c)
        body = c.get("/analytics/api/record/CInformationRequest/r1").json()
    assert body["available"] is True
    assert body["record"]["name"] == "Info request 1"
    # r1 has 2 engagements (e1, e2); r2's e3 is excluded by the injected filter
    assert body["panels"][0]["result"]["data"]["value"] == 2


def test_record_view_other_record(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    store, fake = MemoryAnalyticsStore(), FakeEspo()
    with TestClient(_app(monkeypatch, store, fake)) as c:
        _seed_record_page(c)
        body = c.get("/analytics/api/record/CInformationRequest/r2").json()
    assert body["panels"][0]["result"]["data"]["value"] == 1  # only e3


def test_record_view_no_pages(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    with TestClient(_app(monkeypatch, MemoryAnalyticsStore(), FakeEspo())) as c:
        # CInformationRequest is a BUILDER_ENTITIES record type that intentionally
        # carries no starter dashboard, so the endpoint returns available=False.
        body = c.get("/analytics/api/record/CInformationRequest/r1").json()
    assert body["available"] is False and body["pages"] == []


def test_record_view_unknown_entity(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    with TestClient(_app(monkeypatch, MemoryAnalyticsStore(), FakeEspo())) as c:
        assert c.get("/analytics/api/record/User/x").status_code == 404


def test_record_view_forbidden_record(monkeypatch):
    from analytics.store import MemoryAnalyticsStore
    store, fake = MemoryAnalyticsStore(), FakeEspo()
    fake.forbid = True
    with TestClient(_app(monkeypatch, store, fake)) as c:
        r = c.get("/analytics/api/record/CMentorProfile/m1")
    assert r.status_code == 403


def test_record_metric_not_cached(monkeypatch):
    """A record-scoped metric recomputes on every view (never cached), so ACL
    scope can't leak between viewers."""
    from analytics.store import MemoryAnalyticsStore
    store, fake = MemoryAnalyticsStore(), FakeEspo()
    with TestClient(_app(monkeypatch, store, fake)) as c:
        _seed_record_page(c)
        c.get("/analytics/api/record/CInformationRequest/r1")
        first = fake.list_calls
        c.get("/analytics/api/record/CInformationRequest/r1")
        second = fake.list_calls
    assert second > first  # re-computed, not served from cache
