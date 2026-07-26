"""Analytics Phase B — the authoring layer (builder metrics, pages, gating)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analytics.builder import execute
from analytics.registry import MetricContext
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


class FakeEspo:
    def __init__(self):
        self.data = {
            "CMentorProfile": [
                {"id": "m1", "mentorStatus": "Active", "yearsOfExperience": 10},
                {"id": "m2", "mentorStatus": "Active", "yearsOfExperience": 20},
                {"id": "m3", "mentorStatus": "Candidate", "yearsOfExperience": 0},
            ],
            "CEngagement": [
                {"id": "e1", "name": "Alpha", "engagementStatus": "Active", "createdAt": "2026-01-05 10:00:00"},
                {"id": "e2", "name": "Bravo", "engagementStatus": "Submitted", "createdAt": "2026-02-11 10:00:00"},
                {"id": "e3", "name": "Charlie", "engagementStatus": "Submitted", "createdAt": "2026-02-20 10:00:00"},
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
        if order_by:
            rows.sort(key=lambda r: r.get(order_by) or "", reverse=(order == "desc"))
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def metadata(self, key):
        # entityDefs.{entity}.fields
        return {
            "mentorStatus": {"type": "enum", "options": ["Active", "Candidate", "Inactive"]},
            "yearsOfExperience": {"type": "int"},
            "createdAt": {"type": "datetime"},
            "name": {"type": "varchar"},
            "someLink": {"type": "link"},  # filtered out
        }


def _app(monkeypatch, *, store=None, fake=None, admin_team="Analytics Admin Team", view_team="Analytics Admin Team"):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("ANALYTICS_ADMIN_ALLOWED_TEAMS", admin_team)
    monkeypatch.setenv("ANALYTICS_VIEW_ALLOWED_TEAMS", view_team)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.analytics_store = store
    if fake is not None:
        monkeypatch.setattr("analytics.router._system_client", lambda s: fake)
    return app


def _authed(monkeypatch, user=_ADMIN):
    monkeypatch.setattr("analytics.router.current_user", lambda r: user)


# --- gating ------------------------------------------------------------------
def test_authoring_needs_store(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store=None, fake=FakeEspo())) as c:
        assert c.get("/analytics/api/admin/metrics").status_code == 503


def test_authoring_admin_only(monkeypatch):
    viewer = {"userName": "v", "name": "Vic", "isAdmin": False, "teams": ["Viewers"], "roles": []}
    _authed(monkeypatch, viewer)
    app = _app(monkeypatch, store=MemoryAnalyticsStore(), fake=FakeEspo(),
               admin_team="Authors", view_team="Viewers")
    with TestClient(app) as c:
        assert c.get("/analytics/api/session").status_code == 200      # can view
        assert c.get("/analytics/api/admin/metrics").status_code == 403  # can't author


def test_entities_and_fields(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store=MemoryAnalyticsStore(), fake=FakeEspo())) as c:
        ents = c.get("/analytics/api/admin/entities").json()["entities"]
        assert any(e["entity"] == "CEngagement" for e in ents)
        flds = c.get("/analytics/api/admin/fields?entity=CMentorProfile").json()["fields"]
    names = {f["name"]: f for f in flds}
    assert "someLink" not in names                       # unsupported type filtered
    assert names["yearsOfExperience"]["numeric"] is True
    assert names["createdAt"]["date"] is True
    assert names["mentorStatus"]["enum"] and names["mentorStatus"]["options"]


# --- metric CRUD -------------------------------------------------------------
def _count_metric(name="Active Mentor Count", entity="CMentorProfile"):
    return {
        "name": name, "entity": entity,
        "definition": {"aggregation": {"kind": "count"},
                       "filters": [{"type": "equals", "attribute": "mentorStatus", "value": "Active"}]},
    }


def test_create_metric_derives_shape_and_key(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        r = c.post("/analytics/api/admin/metrics", json=_count_metric())
    assert r.status_code == 200
    m = r.json()["metric"]
    assert m["key"] == "active_mentor_count" and m["result_shape"] == "scalar"
    assert m["default_viz"] == "stat" and m["time_aware"] is False


def test_create_metric_validation(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store=MemoryAnalyticsStore(), fake=FakeEspo())) as c:
        bad_entity = c.post("/analytics/api/admin/metrics",
                            json={"name": "x", "entity": "User", "definition": {"aggregation": {"kind": "count"}}})
        bad_kind = c.post("/analytics/api/admin/metrics",
                          json={"name": "y", "entity": "CEngagement", "definition": {"aggregation": {"kind": "nope"}}})
        no_field = c.post("/analytics/api/admin/metrics",
                          json={"name": "z", "entity": "CMentorProfile", "definition": {"aggregation": {"kind": "avg"}}})
    assert bad_entity.status_code == 422
    assert bad_kind.status_code == 422
    assert no_field.status_code == 422


def test_duplicate_metric_key_conflicts(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        c.post("/analytics/api/admin/metrics", json=_count_metric())
        dup = c.post("/analytics/api/admin/metrics", json=_count_metric())
        # a name colliding with a CODE metric key is also rejected
        code_dup = c.post("/analytics/api/admin/metrics",
                          json=_count_metric(name="Active engagements"))
    assert dup.status_code == 409
    assert code_dup.status_code == 409  # collides with code key active_engagements


def test_update_and_delete_metric(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        mid = c.post("/analytics/api/admin/metrics", json=_count_metric()).json()["metric"]["id"]
        upd = c.put(f"/analytics/api/admin/metrics/{mid}",
                    json=_count_metric(name="Active Mentor Count")).json()["metric"]
        assert upd["updated_by"] == "an"
        d = c.delete(f"/analytics/api/admin/metrics/{mid}")
    assert d.status_code == 200


def test_delete_metric_in_use_blocked(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        m = c.post("/analytics/api/admin/metrics", json=_count_metric()).json()["metric"]
        c.post("/analytics/api/admin/pages", json={
            "title": "My Page",
            "panels": [{"title": "Mentors", "metric_key": m["key"], "viz": "stat"}],
        })
        blocked = c.delete(f"/analytics/api/admin/metrics/{m['id']}")
    assert blocked.status_code == 409
    assert "My Page".lower().replace(" ", "_") in blocked.json()["detail"] or "my_page" in blocked.json()["detail"]


def test_preview(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store=MemoryAnalyticsStore(), fake=FakeEspo())) as c:
        r = c.post("/analytics/api/admin/preview", json={
            "entity": "CEngagement",
            "definition": {"aggregation": {"kind": "group_by", "field": "engagementStatus"}},
        }).json()
    assert r["shape"] == "breakdown"
    items = {i["label"]: i["value"] for i in r["result"]["data"]["items"]}
    assert items["Submitted"] == 2 and items["Active"] == 1


# --- authored page renders in the viewer ------------------------------------
def test_authored_page_renders(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        m = c.post("/analytics/api/admin/metrics", json=_count_metric()).json()["metric"]
        page = c.post("/analytics/api/admin/pages", json={
            "title": "Mentor Overview", "subtitle": "just mentors",
            "panels": [{"title": "Active mentors", "metric_key": m["key"], "viz": "stat", "width": 4}],
        }).json()["page"]
        # appears in the viewer's page list
        sess = c.get("/analytics/api/session").json()
        assert any(p["key"] == page["key"] for p in sess["pages"])
        # and renders with the builder-computed value (2 active mentors)
        body = c.get(f"/analytics/api/pages/{page['key']}").json()
    panel = body["panels"][0]
    assert panel["result"]["data"]["value"] == 2
    assert panel["viz"] == "stat"


def test_page_unknown_metric_rejected(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store=MemoryAnalyticsStore(), fake=FakeEspo())) as c:
        r = c.post("/analytics/api/admin/pages", json={
            "title": "Bad", "panels": [{"title": "x", "metric_key": "does_not_exist"}]})
    assert r.status_code == 422


# --- builder unit tests ------------------------------------------------------
@pytest.mark.asyncio
async def test_builder_execute_shapes():
    fake = FakeEspo()
    ctx = MetricContext(settings=get_settings(), espo=fake, store=None,
                        time_range=build_time_range("all"))

    def row(kind, **agg):
        a = {"kind": kind, **agg}
        return {"key": "k", "name": "n", "entity": "CEngagement", "result_shape": "scalar",
                "definition": {"aggregation": a}, "time_field": "createdAt"}

    r_count = await execute(row("count"), ctx)
    assert r_count.data["value"] == 3
    r_group = await execute(row("group_by", field="engagementStatus"), ctx)
    assert {i["label"]: i["value"] for i in r_group.data["items"]}["Submitted"] == 2
    r_bucket = await execute(row("bucket"), ctx)
    assert sum(p["value"] for p in r_bucket.data["points"]) == 3
    r_list = await execute(row("list", orderBy="createdAt", order="asc", limit=2), ctx)
    assert len(r_list.data["rows"]) == 2 and r_list.data["rows"][0]["recordId"] == "e1"

    ment_ctx = MetricContext(settings=get_settings(), espo=fake, store=None,
                             time_range=build_time_range("all"))
    r_avg = await execute(
        {"key": "k", "entity": "CMentorProfile", "result_shape": "scalar",
         "definition": {"aggregation": {"kind": "avg", "field": "yearsOfExperience"}}}, ment_ctx)
    assert r_avg.data["value"] == 10  # (10+20+0)/3


def test_resolve_relative_filters():
    from datetime import datetime, timezone

    from analytics.builder import resolve_filters
    now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    out = resolve_filters([
        {"type": "relativeAfter", "attribute": "createdAt", "value": 30, "unit": "day"},
        {"type": "equals", "attribute": "status", "value": "Active"},
    ], now=now)
    assert out[0] == {"type": "after", "attribute": "createdAt", "value": "2026-06-25 12:00:00"}
    assert out[1]["type"] == "equals"  # non-relative clause untouched
    older = resolve_filters(
        [{"type": "relativeBefore", "attribute": "createdAt", "value": 2, "unit": "month"}], now=now)
    assert older[0] == {"type": "before", "attribute": "createdAt", "value": "2026-05-25 12:00:00"}


@pytest.mark.asyncio
async def test_relative_date_filter_count():
    """A count with a relative-date filter queries a server-side date bound."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")

    class DateEspo:
        async def list(self, entity, *, where=None, select=None, max_size=50,
                       offset=0, order_by=None, order=None):
            rows = [{"id": "1", "createdAt": recent}, {"id": "2", "createdAt": old}]
            for c in where or []:
                if c["type"] == "after":
                    rows = [r for r in rows if (r.get(c["attribute"]) or "") >= c["value"]]
                elif c["type"] == "before":
                    rows = [r for r in rows if (r.get(c["attribute"]) or "") < c["value"]]
            return {"total": len(rows), "list": rows[offset:offset + max_size]}

    ctx = MetricContext(settings=get_settings(), espo=DateEspo(), store=None,
                        time_range=build_time_range("all"))
    row = {"key": "k", "entity": "CSession", "result_shape": "scalar",
           "definition": {"aggregation": {"kind": "count"},
                          "filters": [{"type": "relativeAfter", "attribute": "createdAt",
                                       "value": 30, "unit": "day"}]}}
    r = await execute(row, ctx)
    assert r.data["value"] == 1  # only the record from 5 days ago, not 100


# --- customizing built-ins (make the seeded page + metrics editable) --------
def test_customize_page_makes_it_editable(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        bi = [p for p in c.get("/analytics/api/admin/pages").json()["builtins"]
              if p["key"] == "system-overview"][0]
        assert bi["customizable"] and not bi["customized"]
        # customize -> a DB page (same key) with the built-in's panels copied
        page = c.post("/analytics/api/admin/pages/customize/system-overview").json()["page"]
        assert page["key"] == "system-overview" and len(page["panels"]) >= 1
        listed = c.get("/analytics/api/admin/pages").json()
        assert any(p["key"] == "system-overview" and p.get("overridesBuiltin") for p in listed["pages"])
        assert [p for p in listed["builtins"] if p["key"] == "system-overview"][0]["customized"] is True
        # idempotent
        again = c.post("/analytics/api/admin/pages/customize/system-overview").json()
        assert again.get("alreadyCustomized")
        # the DB override now drives the viewer (edit: keep one panel), then reset
        one = dict(page); one["panels"] = page["panels"][:1]
        c.put("/analytics/api/admin/pages/" + page["id"], json={
            "title": page["title"], "scope": "system",
            "panels": [{"title": one["panels"][0]["title"],
                        "metric_key": one["panels"][0]["metric_key"],
                        "viz": one["panels"][0]["viz"]}]})
        body = c.get("/analytics/api/pages/system-overview").json()
        assert len(body["panels"]) == 1  # the customized (trimmed) page rendered
        c.delete("/analytics/api/admin/pages/" + page["id"])  # reset to default
        assert not [p for p in c.get("/analytics/api/admin/pages").json()["pages"]
                    if p["key"] == "system-overview"]


def test_customize_metric(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        m = c.post("/analytics/api/admin/metrics/customize/active_mentors").json()["metric"]
        assert m["key"] == "active_mentors" and m["entity"] == "CMentorProfile"
        assert m["definition"]["aggregation"]["kind"] == "count"
        # a store/computed built-in isn't builder-expressible => 400
        assert c.post("/analytics/api/admin/metrics/customize/submissions_per_month").status_code == 400
        ml = c.get("/analytics/api/admin/metrics").json()
        assert any(x["key"] == "active_mentors" and x.get("overridesBuiltin") for x in ml["metrics"])
        assert [b for b in ml["builtins"] if b["key"] == "active_mentors"][0]["customized"] is True


def test_reset_customized_metric_even_when_used(monkeypatch):
    _authed(monkeypatch)
    store = MemoryAnalyticsStore()
    with TestClient(_app(monkeypatch, store=store, fake=FakeEspo())) as c:
        m = c.post("/analytics/api/admin/metrics/customize/active_mentors").json()["metric"]
        c.post("/analytics/api/admin/pages", json={
            "title": "P", "panels": [{"title": "x", "metric_key": "active_mentors", "viz": "stat"}]})
        # reset is allowed even in use (the built-in takes over)
        assert c.delete("/analytics/api/admin/metrics/" + m["id"]).status_code == 200
