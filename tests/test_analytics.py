"""Analytics platform Phase A — engine, router gating, caching, refresh."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from analytics.registry import MetricContext, get_metric
from analytics.service import build_time_range, render_page
from analytics.store import MemoryAnalyticsStore
from core.app import create_app
from core.config import get_settings
from forms import info_request

_ADMIN = {
    "userName": "an", "name": "Ana Lytics", "isAdmin": True,
    "userId": "u-an", "token": "tok-an", "teams": [], "roles": [],
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class FakeEspo:
    """A minimal EspoCRM list() over in-memory datasets, tracking call counts."""

    def __init__(self):
        now = datetime.now(timezone.utc)
        self.data = {
            "CMentorProfile": [
                {"id": "m1", "mentorStatus": "Active"},
                {"id": "m2", "mentorStatus": "Active"},
                {"id": "m3", "mentorStatus": "Candidate"},
            ],
            "CEngagement": [
                {"id": "e1", "name": "Alpha", "engagementStatus": "Active",
                 "createdAt": _iso(now - timedelta(days=10))},
                {"id": "e2", "name": "Bravo", "engagementStatus": "Submitted",
                 "createdAt": _iso(now - timedelta(days=40))},
                {"id": "e3", "name": "Charlie", "engagementStatus": "Submitted",
                 "createdAt": _iso(now - timedelta(days=100))},
                {"id": "e4", "name": "Delta", "engagementStatus": "Assigned",
                 "createdAt": _iso(now - timedelta(days=200))},
            ],
        }
        self.calls: dict[str, int] = {}

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        self.calls[entity] = self.calls.get(entity, 0) + 1
        rows = list(self.data.get(entity, []))
        for clause in where or []:
            attr, typ = clause["attribute"], clause["type"]
            val = clause.get("value")
            if typ == "equals":
                rows = [r for r in rows if r.get(attr) == val]
            elif typ == "in":
                rows = [r for r in rows if r.get(attr) in set(val)]
        total = len(rows)
        if order_by:
            rows.sort(key=lambda r: r.get(order_by) or "", reverse=(order == "desc"))
        return {"total": total, "list": rows[offset:offset + max_size]}


def _app(monkeypatch, *, store=None, fake=None):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.analytics_store = store
    if fake is not None:
        monkeypatch.setattr("analytics.router._system_client", lambda s: fake)
    return app


def _authed(monkeypatch, user=_ADMIN):
    monkeypatch.setattr("analytics.router.current_user", lambda request: user)


# --- gating ------------------------------------------------------------------
def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/analytics/api/session").status_code == 401


def test_gated_to_analytics_team(monkeypatch):
    outsider = {"userName": "cc", "name": "C", "isAdmin": False,
                "teams": ["Mentor Team"], "roles": []}
    _authed(monkeypatch, outsider)
    with TestClient(_app(monkeypatch, fake=FakeEspo())) as c:
        r = c.get("/analytics/api/session")
    assert r.status_code == 403
    assert "Analytics Admin Team" in r.json()["detail"]

    member = dict(outsider, teams=["Analytics Admin Team"])
    _authed(monkeypatch, member)
    with TestClient(_app(monkeypatch, fake=FakeEspo())) as c:
        assert c.get("/analytics/api/session").status_code == 200


def test_session_lists_pages(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, fake=FakeEspo())) as c:
        data = c.get("/analytics/api/session").json()
    keys = [p["key"] for p in data["pages"]]
    assert "system-overview" in keys
    assert data["isAdmin"] is True


# --- rendering ---------------------------------------------------------------
def _panels(body):
    return {p["key"]: p for p in body["panels"]}


def test_page_renders_all_four_shapes(monkeypatch):
    _authed(monkeypatch)
    fake = FakeEspo()
    with TestClient(_app(monkeypatch, fake=fake)) as c:
        body = c.get("/analytics/api/pages/system-overview").json()
    panels = _panels(body)
    # scalar — 2 active mentors, 2 active engagements (Active + Assigned)
    assert panels["active_mentors"]["result"]["data"]["value"] == 2
    assert panels["active_engagements"]["result"]["data"]["value"] == 2
    # series — monthly buckets, values sum to the 4 engagements in range
    ser = panels["engagements_per_month"]["result"]["data"]["points"]
    assert ser and all({"bucket", "label", "value"} <= set(pt) for pt in ser)
    # breakdown — engagements grouped by status
    items = {i["label"]: i["value"] for i in panels["engagements_by_status"]["result"]["data"]["items"]}
    assert items["Submitted"] == 2 and items["Active"] == 1 and items["Assigned"] == 1
    # rows — the two Submitted engagements, oldest first (Charlie before Bravo)
    rowdata = panels["oldest_unassigned"]["result"]["data"]["rows"]
    assert [r["name"] for r in rowdata] == ["Charlie", "Bravo"]
    assert rowdata[0]["recordId"] == "e3" and rowdata[0]["entity"] == "CEngagement"


def test_render_degrades_without_crm_client(monkeypatch):
    """No CRM client (dry-run / no key) => panels show an error, never a 500."""
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, fake=None)) as c:  # _system_client => None
        # dry-run app has no api key, so the real _system_client returns None
        body = c.get("/analytics/api/pages/system-overview")
    assert body.status_code == 200
    for p in body.json()["panels"]:
        assert p["result"]["error"]


def test_unknown_page_404(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, fake=FakeEspo())) as c:
        assert c.get("/analytics/api/pages/nope").status_code == 404


# --- caching + refresh -------------------------------------------------------
def test_cached_metric_served_from_cache(monkeypatch):
    _authed(monkeypatch)
    fake = FakeEspo()
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=fake)) as c:
        c.get("/analytics/api/pages/system-overview")
        calls_after_first = dict(fake.calls)
        body2 = c.get("/analytics/api/pages/system-overview").json()
    # The cached CEngagement sweeps (series/breakdown/rows) are NOT re-swept the
    # second time; only the two LIVE scalar counts hit the CRM again.
    assert fake.calls["CEngagement"] < calls_after_first["CEngagement"] + 3
    panels = _panels(body2)
    assert panels["engagements_by_status"]["result"]["cached"] is True
    # live scalars are never marked cached
    assert panels["active_mentors"]["result"]["cached"] is False


def test_refresh_invalidates_cache(monkeypatch):
    _authed(monkeypatch)
    fake = FakeEspo()
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=fake)) as c:
        c.get("/analytics/api/pages/system-overview")
        before = fake.calls["CEngagement"]
        body = c.post("/analytics/api/pages/system-overview/refresh").json()
        after = fake.calls["CEngagement"]
    # Refresh recomputes the cached sweeps => more CEngagement calls.
    assert after > before
    assert _panels(body)["engagements_by_status"]["result"]["cached"] is False


def test_live_only_without_store(monkeypatch):
    """No store attached => everything recomputes each view (no cache flag set)."""
    _authed(monkeypatch)
    fake = FakeEspo()
    with TestClient(_app(monkeypatch, store=None, fake=fake)) as c:
        b1 = c.get("/analytics/api/pages/system-overview").json()
        b2 = c.get("/analytics/api/pages/system-overview").json()
    assert all(p["result"]["cached"] is False for p in b1["panels"])
    assert all(p["result"]["cached"] is False for p in b2["panels"])


# --- time ranges -------------------------------------------------------------
def test_build_time_range_presets():
    now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert build_time_range("all", now=now).start is None
    ytd = build_time_range("ytd", now=now)
    assert ytd.start.month == 1 and ytd.start.day == 1
    q = build_time_range("quarter", now=now)
    assert q.start.month == 7  # Q3 begins in July
    d30 = build_time_range("last30d", now=now)
    assert (now - d30.start).days == 30 and d30.granularity == "day"
    d365 = build_time_range("last12mo", now=now)
    assert d365.granularity == "month"


def test_range_flows_into_render(monkeypatch):
    _authed(monkeypatch)
    fake = FakeEspo()
    with TestClient(_app(monkeypatch, fake=fake)) as c:
        body = c.get("/analytics/api/pages/system-overview?range=last30d").json()
    assert body["timeRange"]["key"] == "last30d"


# --- store + warm job --------------------------------------------------------
@pytest.mark.asyncio
async def test_memory_store_due_and_invalidate():
    store = MemoryAnalyticsStore()
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    future = datetime.now(timezone.utc) + timedelta(seconds=300)
    await store.put_cached("m", "system", "all", result={"v": 1}, expires_at=past)
    await store.put_cached("m2", "system", "all", result={"v": 2}, expires_at=future)
    due = await store.due()
    assert [d["metricKey"] for d in due] == ["m"]
    await store.invalidate("m2")
    assert await store.get_cached("m2", "system", "all") is None


@pytest.mark.asyncio
async def test_refresh_system_metrics_warms_cache(monkeypatch):
    from analytics import refresh as refresh_mod

    store = MemoryAnalyticsStore()
    fake = FakeEspo()
    monkeypatch.setattr(refresh_mod, "make_analytics_store", lambda s: store)
    monkeypatch.setattr(refresh_mod, "system_client", lambda s: fake)
    get_settings.cache_clear()
    out = await refresh_mod.refresh_system_metrics(get_settings())
    assert out["refreshed"] >= 1
    # the breakdown metric is now cached under (key, system, all)
    hit = await store.get_cached("engagements_by_status", "system", "all")
    assert hit is not None and hit["result"]["shape"] == "breakdown"


@pytest.mark.asyncio
async def test_render_page_skips_hidden_panels(monkeypatch):
    """Per-panel visibility: a panel whose team the viewer lacks is omitted."""
    from analytics.registry import PageSpec, PanelSpec

    page = PageSpec(
        key="t", title="T", panels=[
            PanelSpec("vis", "Visible", "active_mentors", "stat"),
            PanelSpec("hid", "Hidden", "active_mentors", "stat",
                      visibility=("Secret Team",)),
        ],
    )
    fake = FakeEspo()
    user = {"userName": "u", "isAdmin": False, "teams": ["Analytics Admin Team"], "roles": []}
    body = await render_page(
        page, user=user, settings=get_settings(), espo=fake, store=None,
        time_range=build_time_range("all"),
    )
    keys = [p["key"] for p in body["panels"]]
    assert keys == ["vis"]
