"""Awaiting-processing attention counts: the shared definitions
(core/attention), the portal tile-badge endpoint (GET /api/portal/attention),
and the analytics "Items awaiting processing" rows metric."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core import attention
from core.app import create_app
from core.config import get_settings
from forms import info_request, volunteer


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


_NOW = datetime.now(timezone.utc)


class FakeEspo:
    """In-memory list() supporting equals / isNull, as the definitions need."""

    def __init__(self):
        self.data = {
            "CEngagement": [
                {"id": "e1", "name": "Alpha", "engagementStatus": "Submitted",
                 "createdAt": _iso(_NOW - timedelta(days=12))},
                {"id": "e2", "name": "Bravo", "engagementStatus": "Active",
                 "createdAt": _iso(_NOW - timedelta(days=40))},
            ],
            "CMentorProfile": [
                {"id": "m1", "name": "Cand One", "mentorStatus": "Candidate",
                 "createdAt": _iso(_NOW - timedelta(days=3))},
                {"id": "m2", "name": "Act One", "mentorStatus": "Active",
                 "createdAt": _iso(_NOW - timedelta(days=99))},
            ],
            "CPartnerProfile": [
                {"id": "p1", "name": "New Partner", "partnershipStatus": "Candidate",
                 "createdAt": _iso(_NOW - timedelta(days=7))},
                {"id": "p2", "name": "Old Partner", "partnershipStatus": "Active",
                 "createdAt": _iso(_NOW - timedelta(days=300))},
            ],
            "CSponsorProfile": [
                {"id": "s1", "name": "Managed Funder", "cBMSponsorManagerId": "mgr",
                 "createdAt": _iso(_NOW - timedelta(days=30))},
                {"id": "s2", "name": "Orphan Funder", "cBMSponsorManagerId": None,
                 "createdAt": _iso(_NOW - timedelta(days=60))},
            ],
        }

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        rows = list(self.data.get(entity, []))
        for clause in where or []:
            attr, typ = clause["attribute"], clause["type"]
            if typ == "equals":
                rows = [r for r in rows if r.get(attr) == clause.get("value")]
            elif typ == "isNull":
                rows = [r for r in rows if r.get(attr) is None]
        total = len(rows)
        if order_by:
            rows.sort(key=lambda r: r.get(order_by) or "", reverse=(order == "desc"))
        return {"total": total, "list": rows[offset:offset + max_size]}


class FakeStore:
    """Just the open-review surface the endpoint + metric use."""

    def __init__(self, count=2, rows=None):
        self._count = count
        self._rows = rows if rows is not None else [
            {"id": "sub-1", "form_slug": "info-request", "status": "completed",
             "received_at": _NOW - timedelta(days=20), "email": "jane@x.org"},
            {"id": "sub-2", "form_slug": "info-email", "status": "held_review",
             "received_at": _NOW - timedelta(days=1), "email": "bob@y.org"},
        ]

    async def open_review_count(self):
        return self._count

    async def list_open_review(self, *, limit=25):
        return self._rows[:limit]


# --- the shared definitions --------------------------------------------------

@pytest.mark.anyio
async def test_crm_counts_filter_each_category():
    espo = FakeEspo()
    assert await attention.crm_count(espo, attention.ENGAGEMENTS) == 1
    assert await attention.crm_count(espo, attention.MENTORS) == 1
    assert await attention.crm_count(espo, attention.PARTNERS) == 1
    assert await attention.crm_count(espo, attention.FUNDERS) == 1  # the null-manager one


@pytest.mark.anyio
async def test_crm_records_oldest_first():
    espo = FakeEspo()
    recs = await attention.crm_records(espo, attention.FUNDERS)
    assert [r["id"] for r in recs] == ["s2"]  # only the unmanaged funder


# --- the portal badge endpoint -----------------------------------------------

def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _user(**overrides):
    base = {"userId": "u1", "userName": "jdoe", "name": "Jane Doe", "token": "tok",
            "isAdmin": False, "teams": [], "roles": []}
    base.update(overrides)
    return base


def _login(monkeypatch, c, user):
    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return user

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    r = c.post("/api/portal/login", json={"username": "x", "password": "y"})
    assert r.status_code == 200


def test_attention_requires_login(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/api/portal/attention").status_code == 401


def test_attention_counts_only_entitled_apps(monkeypatch):
    monkeypatch.setattr("portal.router.client_for", lambda settings, user: FakeEspo())
    with TestClient(_app(monkeypatch)) as c:
        _login(monkeypatch, c, _user(teams=["Client Administration Team"]))
        data = c.get("/api/portal/attention").json()
    assert data["items"] == [
        {"url": "/assignments/", "count": 1, "label": "Clients awaiting mentor assignment"}
    ]


def test_attention_admin_gets_all_including_ops(monkeypatch):
    monkeypatch.setattr("portal.router.client_for", lambda settings, user: FakeEspo())
    app = _app(monkeypatch)
    app.state.submission_store = FakeStore(count=3)
    with TestClient(app) as c:
        _login(monkeypatch, c, _user(isAdmin=True))
        data = c.get("/api/portal/attention").json()
    by_url = {i["url"]: i["count"] for i in data["items"]}
    assert by_url == {
        "/assignments/": 1, "/mentoradmin/": 1,
        "/partnersessions/": 1, "/sponsorsessions/": 1, "/ops/": 3,
    }


def test_attention_without_store_omits_ops(monkeypatch):
    monkeypatch.setattr("portal.router.client_for", lambda settings, user: FakeEspo())
    with TestClient(_app(monkeypatch)) as c:
        _login(monkeypatch, c, _user(teams=["Marketing Admin Team"]))
        data = c.get("/api/portal/attention").json()
    assert data["items"] == []  # no durable store on this deployment


def test_attention_failed_count_is_omitted_not_fatal(monkeypatch):
    class BoomEspo:
        async def list(self, *a, **kw):
            raise RuntimeError("CRM down")

    monkeypatch.setattr("portal.router.client_for", lambda settings, user: BoomEspo())
    with TestClient(_app(monkeypatch)) as c:
        _login(monkeypatch, c, _user(teams=["Client Administration Team"]))
        r = c.get("/api/portal/attention")
    assert r.status_code == 200
    assert r.json()["items"] == []


# --- the analytics rows metric -----------------------------------------------

@pytest.mark.anyio
async def test_attention_queue_metric_blends_crm_and_store():
    from analytics.computed import _attention_queue
    from analytics.registry import MetricContext

    ctx = MetricContext(settings=None, espo=FakeEspo(), submission_store=FakeStore())
    result = await _attention_queue.compute(ctx)
    assert result.shape == "rows"
    rows = result.data["rows"]
    by_type = {r["type"]: r for r in rows}
    # CRM categories: engagements/mentors link to the CRM record; partner/funder
    # rows carry app record-page hrefs.
    assert by_type["Client awaiting mentor"]["entity"] == "CEngagement"
    assert by_type["Client awaiting mentor"]["recordId"] == "e1"
    assert by_type["Mentor application"]["entity"] == "CMentorProfile"
    assert by_type["Partner application"]["href"] == "/partnersessions/record/p1"
    assert by_type["Funder without a manager"]["href"] == "/sponsorsessions/record/s2"
    # Store categories: /ops deep links + plain-language reason labels.
    assert by_type["Submission — reply owed"]["href"] == "/ops/?submission=sub-1"
    assert by_type["Submission — awaiting approval"]["name"].endswith("bob@y.org")
    # Oldest waiting first, across categories.
    days = [r["days"] for r in rows]
    assert days == sorted(days, reverse=True)


@pytest.mark.anyio
async def test_attention_queue_metric_survives_a_failing_source():
    from analytics.computed import _attention_queue
    from analytics.registry import MetricContext

    class HalfBroken(FakeEspo):
        async def list(self, entity, **kw):
            if entity == "CMentorProfile":
                raise RuntimeError("forbidden")
            return await super().list(entity, **kw)

    ctx = MetricContext(settings=None, espo=HalfBroken(), submission_store=None)
    result = await _attention_queue.compute(ctx)
    types = {r["type"] for r in result.data["rows"]}
    assert "Mentor application" not in types
    assert "Client awaiting mentor" in types  # the rest still render


def test_attention_queue_seeded_on_system_page():
    """The panel ships on the System Analytics page out of the box (Doug's
    ruling 2026-07-26) — no Manage-→-Pages step needed to see it."""
    import analytics  # noqa: F401 — registers metrics + the seeded page
    from analytics.registry import get_metric, get_page

    page = get_page("system-overview")
    seeded = [p for p in page.panels if p.metric_key == "attention_queue"]
    assert seeded and seeded[0].viz == "table"
    assert get_metric("attention_queue") is not None


@pytest.mark.anyio
async def test_attention_queue_metric_unavailable_when_everything_fails():
    from analytics.computed import _attention_queue
    from analytics.registry import MetricContext

    class Broken:
        async def list(self, *a, **kw):
            raise RuntimeError("no CRM")

    ctx = MetricContext(settings=None, espo=Broken(), submission_store=None)
    result = await _attention_queue.compute(ctx)
    assert result.error and not result.data
