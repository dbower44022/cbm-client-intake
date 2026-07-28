"""Analytics Phase E — the starter dashboards on the record views.

Covers the three things that make the feature real: a dashboard ships for each
record type, a record type can hold only one dashboard (Doug 2026-07-27), and
the host apps show the tab only where analytics is switched on.
"""

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
    """Enough CRM for the starter metrics: one record of each type, with the
    children they aggregate."""

    def __init__(self):
        self.data = {
            "CMentorProfile": [{"id": "m1", "name": "Mentor One"}],
            "CEngagement": [
                {"id": "e1", "name": "Alpha", "mentorProfileId": "m1",
                 "engagementStatus": "Active", "lastContactDate": "2026-07-01",
                 "createdAt": "2026-06-01 10:00:00", "referringPartnerId": "p1",
                 "engagementClientId": "cp1", "clientOrganizationId": "a1"},
                {"id": "e2", "name": "Bravo", "mentorProfileId": "m1",
                 "engagementStatus": "Completed", "lastContactDate": None,
                 "createdAt": "2026-05-01 10:00:00",
                 "engagementClientId": "cp1", "clientOrganizationId": "a1"},
            ],
            "CPartnerProfile": [{"id": "p1", "name": "Partner One"}],
            "CSponsorProfile": [{"id": "s1", "name": "Funder One"}],
            "CClientProfile": [{"id": "cp1", "name": "Client Business One"}],
            "Account": [{"id": "a1", "name": "Acme Co."}],
            "Contact": [
                {"id": "c1", "name": "Cass Contact", "accountId": "a1",
                 "title": "CEO", "createdAt": "2026-05-15 10:00:00"},
            ],
            "CSession": [
                {"id": "x1", "name": "Session 1", "dateStart": "2026-07-02 15:00:00",
                 "status": "Completed", "engagementId": "e1"},
                {"id": "x2", "name": "Session 2", "dateStart": "2026-07-09 15:00:00",
                 "status": "Scheduled", "engagementId": "e1"},
                {"id": "x3", "name": "Partner sync", "dateStart": "2026-06-11 15:00:00",
                 "status": "Completed", "partnerSessionId": "p1"},
            ],
            "CContribution": [
                {"id": "k1", "name": "Grant", "amount": 5000, "status": "Received",
                 "contributionType": "Grant", "receivedDate": "2026-06-15",
                 "sponsorProfileId": "s1"},
                {"id": "k2", "name": "Pledge", "amount": 2500, "status": "Pledged",
                 "contributionType": "Donation", "expectedPaymentDate": "2026-09-01",
                 "sponsorProfileId": "s1"},
            ],
            "CConversation": [{"id": "v1", "name": "Thread"}],
        }
        self.forbid = False

    async def get(self, entity, record_id, select=None):
        for r in self.data.get(entity, []):
            if r["id"] == record_id:
                return dict(r)
        from core.espo import EspoError
        raise EspoError("get failed: HTTP 404 Not Found")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        rows = list(self.data.get(entity, []))
        for c in where or []:
            a, t, v = c["attribute"], c["type"], c.get("value")
            if t == "equals":
                rows = [r for r in rows if r.get(a) == v]
            elif t == "in":
                rows = [r for r in rows if r.get(a) in set(v)]
            elif t == "linkedWith":
                pass  # the fake links everything; the query shape is what matters
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def metadata(self, key):
        return {}


def _app(monkeypatch, fake, *, analytics=True):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ANALYTICS_ENABLED", "true" if analytics else "false")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    from analytics.store import MemoryAnalyticsStore
    app.state.analytics_store = MemoryAnalyticsStore()
    monkeypatch.setattr("analytics.router.current_user", lambda r: _ADMIN)
    monkeypatch.setattr("analytics.router._system_client", lambda s: fake)
    monkeypatch.setattr("analytics.router.client_for", lambda s, u: fake)
    return app


# --- the seeded pages --------------------------------------------------------
@pytest.mark.parametrize("entity,record_id,page_key", [
    ("CMentorProfile", "m1", "record-mentor"),
    ("CEngagement", "e1", "record-engagement"),
    ("CPartnerProfile", "p1", "record-partner"),
    ("CSponsorProfile", "s1", "record-funder"),
    ("Contact", "c1", "record-contact"),
    ("CClientProfile", "cp1", "record-client"),
    ("Account", "a1", "record-company"),
])
def test_every_record_type_has_a_starter_dashboard(monkeypatch, entity, record_id, page_key):
    with TestClient(_app(monkeypatch, FakeEspo())) as c:
        body = c.get(f"/analytics/api/record/{entity}/{record_id}").json()
    assert body["available"] is True
    assert page_key in [p["key"] for p in body["pages"]]
    assert body["panels"], "a starter dashboard renders panels"
    # Every panel produced a result, and none of them errored.
    for panel in body["panels"]:
        assert panel["result"]["error"] is None, panel["title"]


def test_starter_metrics_compute_real_values(monkeypatch):
    """Spot-check the numbers, so a wrong filter can't pass as 'it rendered'."""
    with TestClient(_app(monkeypatch, FakeEspo())) as c:
        eng = c.get("/analytics/api/record/CEngagement/e1").json()
        funder = c.get("/analytics/api/record/CSponsorProfile/s1").json()
    by_key = {p["key"]: p["result"] for p in eng["panels"]}
    # e1 has two sessions but only one Completed.
    assert by_key["sessions_done"]["data"]["value"] == 1
    # Recent sessions lists both, newest first.
    assert [r["name"] for r in by_key["recent"]["data"]["rows"]] == ["Session 2", "Session 1"]

    funder_by_key = {p["key"]: p["result"] for p in funder["panels"]}
    # Only Received money counts toward the total; the pledge sits in pipeline.
    assert funder_by_key["received"]["data"]["value"] == 5000
    assert funder_by_key["received"]["data"]["format"] == "currency"
    assert funder_by_key["pipeline"]["data"]["value"] == 2500


def test_record_metric_off_a_record_says_so(monkeypatch):
    """A record metric placed on a system page degrades to a message, not a 500."""
    import asyncio

    from analytics.registry import MetricContext, get_metric
    spec = get_metric("engagement_sessions_completed")
    result = asyncio.run(spec.compute(MetricContext(settings=None, espo=FakeEspo())))
    assert result.error and "record" in result.error.lower()


# --- one dashboard per record type (§17 P3) ----------------------------------
def test_second_dashboard_for_a_record_type_is_refused(monkeypatch):
    with TestClient(_app(monkeypatch, FakeEspo())) as c:
        m = c.post("/analytics/api/admin/metrics", json={
            "name": "Engagements here", "entity": "CEngagement",
            "definition": {"aggregation": {"kind": "count"}, "filters": []},
            "applies_to": ["CMentorProfile"], "context_param": "mentorProfileId",
        }).json()["metric"]
        r = c.post("/analytics/api/admin/pages", json={
            "title": "My Mentor Page", "scope": "CMentorProfile",
            "panels": [{"title": "Engagements", "metric_key": m["key"]}],
        })
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Mentors" in detail and "Mentor Analytics" in detail  # names the one to edit


def test_customizing_the_builtin_is_still_allowed(monkeypatch):
    """The supported way to change a record dashboard: customize + edit it. The
    copy shares the built-in's key, so it overrides rather than duplicates."""
    with TestClient(_app(monkeypatch, FakeEspo())) as c:
        made = c.post("/analytics/api/admin/pages/customize/record-mentor")
        assert made.status_code == 200
        page = made.json()["page"]
        assert page["key"] == "record-mentor" and page["scope"] == "CMentorProfile"
        # Editing it (fewer panels) passes the guard — it is the same page.
        r = c.put(f"/analytics/api/admin/pages/{page['id']}", json={
            "title": "Mentor Analytics", "scope": "CMentorProfile",
            "panels": [{"title": "Active clients", "metric_key": "mentor_active_clients"}],
        })
        assert r.status_code == 200
        body = c.get("/analytics/api/record/CMentorProfile/m1").json()
    assert [p["title"] for p in body["panels"]] == ["Active clients"]


def test_multiple_system_pages_still_allowed(monkeypatch):
    """The portal dashboard is separated from the viewer by having two system
    pages, so the one-per-type rule must not touch them."""
    with TestClient(_app(monkeypatch, FakeEspo())) as c:
        r = c.post("/analytics/api/admin/pages", json={
            "title": "Portal Summary", "scope": "system", "portal_dashboard": True,
            "panels": [{"title": "Active mentors", "metric_key": "active_mentors"}],
        })
    assert r.status_code == 200


# --- the host apps advertise the tab ----------------------------------------
def test_session_tools_show_the_analytics_tab_only_when_enabled():
    from sessions.config import DOMAINS
    from sessions.router import _detail_tabs
    for cfg in DOMAINS.values():
        assert "analytics" not in [t["key"] for t in _detail_tabs(cfg)]
        tabs = _detail_tabs(cfg, analytics=True)
        assert tabs[-1] == {"key": "analytics", "label": "Analytics"}
