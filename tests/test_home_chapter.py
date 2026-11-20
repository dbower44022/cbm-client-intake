"""The new home page, phase 4: At the chapter (HOME_V2; prds/home-page-plan.md
§ 4.1 and § 8; Doug's eight answers at the phase's first stop, 11-20-26).

The rules on their own, then the endpoint: the chapter's numbers for every
member, the member's own over owned and co-mentored engagements of every
status, the asks' team rule, a failing part, the shared figures, the switch
off, and the page."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request, volunteer
from portal import chapter

ROOT = Path(__file__).resolve().parents[1]
MENTOR_TEAM = "Mentor Team"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- the rules ------------------------------------------------------------------

def test_the_year_starts_on_the_chapters_own_first_of_january():
    # 03:00 UTC on 1 January is still 31 December in the chapter's zone.
    year, since = chapter.year_start(datetime(2027, 1, 1, 3, 0, tzinfo=timezone.utc))
    assert year == 2026 and since == "2026-01-01 05:00:00"
    year, since = chapter.year_start(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))
    assert year == 2026 and since == "2026-01-01 05:00:00"


def test_the_figures_count_engagements_sessions_and_hours():
    facts = chapter.session_facts([
        {"engagementId": "e1", "dateStart": "2026-03-01 14:00:00", "dateEnd": "2026-03-01 15:00:00"},
        {"engagementId": "e1", "dateStart": "2026-04-01 14:00:00", "dateEnd": "2026-04-01 15:30:00"},
        {"engagementId": "e2", "dateStart": "2026-05-01 14:00:00", "dateEnd": None},
    ])
    assert chapter.figures(facts) == {"clients": 2, "sessions": 3, "hours": 2}
    assert chapter.figures(facts, {"e2"}) == {"clients": 1, "sessions": 1, "hours": 0}
    assert chapter.figures(facts, set()) == {"clients": 0, "sessions": 0, "hours": 0}


def test_calls_to_make_follow_the_calls_tab():
    open_ = [{"touchStatus": "Planned"}, {"touchStatus": "Planned"}, {"touchStatus": "Done"}]
    assert chapter.calls_to_make(open_, "u1") == 2
    assigned = [{"touchStatus": "Planned", "assignedUserId": "u1"},
                {"touchStatus": "Planned", "assignedUserId": "u2"},
                {"touchStatus": "Planned"}]
    assert chapter.calls_to_make(assigned, "u1") == 2
    row = chapter.ask_row({"name": "Fall follow-up calls"}, 1)
    assert row["reason"] == "1 call to make" and row["url"] == "/campaigns/#calls"


# --- the endpoint -----------------------------------------------------------------

def _eng(eid, status, mentor="p1"):
    return {"id": eid, "name": f"Engagement {eid}", "engagementStatus": status,
            "clientOrganizationName": f"Company {eid}", "mentorProfileId": mentor,
            "createdAt": "2026-01-01 00:00:00"}


PROFILE = [{"id": "p1", "name": "Joe Mentor", "mentorStatus": "Active",
            "cbmEmail": "joe@example.org", "assignedUserId": "u1", "assignedUsersIds": ["u1"]}]

YEAR_SESSIONS = [
    {"engagementId": "e1", "dateStart": "2026-03-01 14:00:00", "dateEnd": "2026-03-01 15:00:00"},
    {"engagementId": "e3", "dateStart": "2026-03-02 14:00:00", "dateEnd": "2026-03-02 15:00:00"},
    {"engagementId": "e5", "dateStart": "2026-03-03 14:00:00", "dateEnd": "2026-03-03 15:00:00"},
    {"engagementId": "zz", "dateStart": "2026-03-04 14:00:00", "dateEnd": "2026-03-04 16:00:00"},
]


class OrgClient:
    """The chapter-wide key: the year's sessions and the call campaigns."""

    def __init__(self, fail=False, campaigns=()):
        self.fail, self.campaigns = fail, list(campaigns)
        self.session_reads = 0

    async def list(self, entity, **kw):
        if entity == "CSession":
            self.session_reads += 1
            if self.fail:
                raise EspoError("CRM down")
            return {"list": YEAR_SESSIONS}
        if entity == "COutreachCampaign":
            return {"list": [{"id": c["id"], "name": c["name"]} for c in self.campaigns]}
        return {"list": []}

    async def get(self, entity, rid, **kw):
        return next(c for c in self.campaigns if c["id"] == rid)


class MemberClient:
    """The member's own token: Client Management's list and the touches."""

    def __init__(self, touches=None):
        self.touches = touches or {}

    async def list(self, entity, **kw):
        if entity == "CMentorProfile":
            return {"list": PROFILE}
        if entity == "COutreachTouch":
            cid = next(w["value"] for w in kw["where"] if w["attribute"] == "outreachCampaignId")
            return {"list": self.touches.get(cid, [])}
        return {"list": []}

    async def list_related(self, entity, rid, link, **kw):
        if link == "engagements1":
            return {"list": [_eng("e1", "Active"), _eng("e3", "Completed")]}
        return {"list": [_eng("e5", "Assigned", mentor="p9")]}

    async def get(self, entity, rid, **kw):
        return {"userName": "joe"}

    async def metadata(self, key):
        return None


def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _sign_in(monkeypatch, c, member, org, teams=(MENTOR_TEAM,)):
    user = {"userId": "u1", "userName": "joe", "name": "Joe Mentor", "token": "tok",
            "isAdmin": False, "teams": list(teams), "roles": []}

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return user

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)
    monkeypatch.setattr("portal.router.client_for", lambda settings, u: member)
    monkeypatch.setattr("portal.router._org_client", lambda settings: org)
    c.post("/api/portal/login", json={"username": "joe", "password": "x"})


def _chapter(monkeypatch, member=None, org=None, teams=(MENTOR_TEAM,), **env):
    with TestClient(_app(monkeypatch, HOME_V2="true", **env)) as c:
        _sign_in(monkeypatch, c, member or MemberClient(), org if org is not None else OrgClient(),
                 teams)
        r = c.get("/api/portal/home/chapter")
    assert r.status_code == 200, r.text
    return r.json()


def test_off_the_endpoint_is_not_there(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        _sign_in(monkeypatch, c, MemberClient(), OrgClient())
        assert c.get("/api/portal/home/chapter").status_code == 404


def test_signed_out_is_refused(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        assert c.get("/api/portal/home/chapter").status_code == 401


def test_a_mentor_sees_the_chapter_beside_their_own_co_mentored_and_closed_included(monkeypatch):
    data = _chapter(monkeypatch)
    assert data["chapter"] == {"clients": 4, "sessions": 4, "hours": 5}
    # e1 owned and Active, e3 owned and Completed, e5 co-mentored; zz is not theirs.
    assert data["own"] == {"clients": 3, "sessions": 3, "hours": 3}
    assert data["year"] == chapter.year_start(datetime.now(timezone.utc))[0]
    assert data["unavailable"] == []


def test_a_staff_member_sees_the_chapter_but_no_own_figure(monkeypatch):
    data = _chapter(monkeypatch, teams=("Marketing Admin Team",))
    assert data["chapter"]["sessions"] == 4
    assert data["own"] is None


def test_no_chapter_key_means_no_figures_and_no_error(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        _sign_in(monkeypatch, c, MemberClient(), None)
        data = c.get("/api/portal/home/chapter").json()
    assert data["chapter"] is None and data["own"] is None and data["unavailable"] == []


def test_a_failing_read_is_left_out_and_named(monkeypatch):
    data = _chapter(monkeypatch, org=OrgClient(fail=True))
    assert data["chapter"] is None and data["own"] is None
    assert data["unavailable"] == ["chapter"]


def test_the_chapters_figures_are_read_once_for_everyone(monkeypatch):
    org = OrgClient()
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        _sign_in(monkeypatch, c, MemberClient(), org)
        c.get("/api/portal/home/chapter")
        c.get("/api/portal/home/chapter")
    assert org.session_reads == 1


def test_the_asks_are_the_running_call_campaigns_naming_the_members_team(monkeypatch):
    org = OrgClient(campaigns=[
        {"id": "c1", "name": "Fall follow-up calls", "teamsNames": {"t1": MENTOR_TEAM}},
        {"id": "c2", "name": "Staff only calls", "teamsNames": {"t2": "Marketing Admin Team"}},
        {"id": "c3", "name": "Nothing left", "teamsNames": {"t1": MENTOR_TEAM}},
    ])
    member = MemberClient(touches={
        "c1": [{"touchStatus": "Planned"}] * 3,
        "c2": [{"touchStatus": "Planned"}],
        "c3": [],
    })
    data = _chapter(monkeypatch, member=member, org=org,
                    CAMPAIGNS_ENABLED="true", CAMPAIGNS_CALLS="true")
    assert [(a["name"], a["reason"]) for a in data["asks"]] == [
        ("Fall follow-up calls", "3 calls to make")]
    assert data["asks"][0]["target"] == "cbm-campaigns"


def test_without_call_campaigns_there_are_no_asks(monkeypatch):
    data = _chapter(monkeypatch)
    assert data["asks"] is None


# --- the page -------------------------------------------------------------------

def test_analytics_has_its_own_frame_at_the_end(monkeypatch):
    from portal.router import _home_sections

    monkeypatch.setenv("HOME_V2", "true")
    get_settings.cache_clear()
    user = {"teams": [MENTOR_TEAM], "isAdmin": False}
    assert "analytics" not in _home_sections(user, get_settings())
    monkeypatch.setattr(type(get_settings()), "analytics_active", property(lambda s: True))
    sections = _home_sections(user, get_settings())
    assert sections[-1] == "analytics"


def test_the_page_fills_at_the_chapter():
    js = (ROOT / "portal/frontend/home.js").read_text()
    assert "/api/portal/home/chapter" in js
    assert "CBMBusy.loading(body, read)" in js
    assert '"Where you\'re needed"' in js and '"yours "' in js
    assert 'moveIn(frames.analytics._body, "analyticsSection"' in js
    # The dashboard no longer sits in At the chapter.
    assert 'moveIn(frames.chapter._body' not in js
    app = (ROOT / "portal/frontend/app.js").read_text()
    assert "drawn.analyticsBody" in app and "drawn.chapterBody" not in app
