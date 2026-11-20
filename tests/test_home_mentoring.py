"""The new home page, phase 2: Today and My clients (HOME_V2;
prds/home-page-plan.md § 4.1 and § 8).

One read as the member, through Client Management's own list: owned and
co-mentored engagements, the active statuses only in My clients, the next
session from real sessions (never the stored field), and plain answers for a
member with no profile, one the strict rule refuses, a failing read and the
switch off."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request, volunteer

ROOT = Path(__file__).resolve().parents[1]
MENTOR_TEAM = "Mentor Team"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%d %H:%M:%S")


def _eng(eid, status, mentor="p1", **extra):
    row = {"id": eid, "name": f"Engagement {eid}", "engagementStatus": status,
           "clientOrganizationName": f"Company {eid}", "clientOrganizationId": f"a-{eid}",
           "engagementClientName": f"Client {eid}", "lastContactDate": "2026-11-10 14:00:00",
           # A hand-edited stored date the page must never show (sessions/CLAUDE.md).
           "nextSessionDateTime": "2030-01-01 09:00:00",
           "mentorProfileId": mentor, "createdAt": "2026-10-01 00:00:00"}
    row.update(extra)
    return row


class FakeClient:
    """Answers the reads ``sessions.service.list_records`` makes."""

    def __init__(self, profiles, owned, comentored, sessions, fail=False):
        self.profiles, self.owned, self.comentored = profiles, owned, comentored
        self.sessions, self.fail = sessions, fail

    async def list(self, entity, **kw):
        if self.fail:
            raise EspoError("CRM down")
        if entity == "CMentorProfile":
            return {"list": self.profiles}
        if entity == "CSession":
            return {"list": self.sessions}
        return {"list": []}

    async def list_related(self, entity, rid, link, **kw):
        return {"list": self.owned if link == "engagements1" else self.comentored}

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


def _sign_in(monkeypatch, c, client, teams=(MENTOR_TEAM,)):
    user = {"userId": "u1", "userName": "joe", "name": "Joe Mentor", "token": "tok",
            "isAdmin": False, "teams": list(teams), "roles": []}

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return user

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)
    monkeypatch.setattr("portal.router.client_for", lambda settings, u: client)
    c.post("/api/portal/login", json={"username": "joe", "password": "x"})


PROFILE = [{"id": "p1", "name": "Joe Mentor", "mentorStatus": "Active",
            "cbmEmail": "joe@example.org", "assignedUserId": "u1", "assignedUsersIds": ["u1"]}]


def _standard_client(**kw):
    owned = [_eng("e1", "Active"), _eng("e2", "Pending Acceptance"),
             _eng("e3", "Completed"), _eng("e4", "On-Hold")]
    comentored = [_eng("e5", "Assigned", mentor="p9")]
    sessions = [
        {"id": "s1", "engagementId": "e1", "dateStart": _stamp(timedelta(hours=2)),
         "status": "Scheduled", "name": "Cash-flow review", "sessionType": "Client Session",
         "videoMeetingLink": "https://meet.example/abc"},
        {"id": "s2", "engagementId": "e5", "dateStart": _stamp(timedelta(days=3)),
         "status": "Scheduled", "name": "Check-in", "sessionType": "Client Session"},
        {"id": "s3", "engagementId": "e4", "dateStart": _stamp(timedelta(days=2)),
         "status": "Cancelled", "name": "Cancelled one"},
        {"id": "s4", "engagementId": "e3", "dateStart": _stamp(timedelta(days=1)),
         "status": "Scheduled", "name": "Closing session"},
        {"id": "s5", "engagementId": "e2", "dateStart": _stamp(timedelta(days=20)),
         "status": "Scheduled", "name": "Far ahead"},
    ]
    return FakeClient(kw.get("profiles", PROFILE), owned, comentored, sessions,
                      fail=kw.get("fail", False))


def test_off_the_endpoint_is_not_there(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        _sign_in(monkeypatch, c, _standard_client())
        assert c.get("/api/portal/home/mentoring").status_code == 404


def test_signed_out_is_refused(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        assert c.get("/api/portal/home/mentoring").status_code == 401


def test_a_member_outside_the_mentor_team_is_refused(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        _sign_in(monkeypatch, c, _standard_client(), teams=("Marketing Admin Team",))
        assert c.get("/api/portal/home/mentoring").status_code == 403


def _read(monkeypatch, client):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        _sign_in(monkeypatch, c, client)
        r = c.get("/api/portal/home/mentoring")
    return r


def test_my_clients_lists_only_the_active_statuses_with_co_mentored_marked(monkeypatch):
    data = _read(monkeypatch, _standard_client()).json()
    assert data["profile"] == "found"
    by_id = {c["id"]: c for c in data["clients"]}
    # Completed (e3) is out; the four active statuses are in.
    assert set(by_id) == {"e1", "e2", "e4", "e5"}
    assert by_id["e1"]["name"] == "Company e1"
    assert by_id["e1"]["coMentor"] is False
    assert by_id["e5"]["coMentor"] is True


def test_the_next_session_comes_from_sessions_never_the_stored_field(monkeypatch):
    data = _read(monkeypatch, _standard_client()).json()
    by_id = {c["id"]: c for c in data["clients"]}
    assert "2030-01-01 09:00:00" not in str(data)
    assert len(by_id["e1"]["sessions"]) == 1
    # A cancelled session is not a next session; a far one still is.
    assert by_id["e4"]["sessions"] == []
    assert len(by_id["e2"]["sessions"]) == 1


def test_today_carries_scheduled_sessions_of_every_engagement_with_the_link(monkeypatch):
    data = _read(monkeypatch, _standard_client()).json()
    ids = [s["id"] for s in data["sessions"]]
    # s3 cancelled; s5 beyond the window; s4 belongs to a closed engagement
    # but is still the member's session.
    assert ids == ["s1", "s4", "s2"]
    first = data["sessions"][0]
    assert first["videoMeetingLink"] == "https://meet.example/abc"
    assert first["recordId"] == "e1" and first["client"] == "Company e1"
    assert first["name"] == "Cash-flow review"


def test_a_member_with_no_profile_gets_a_plain_answer(monkeypatch):
    data = _read(monkeypatch, _standard_client(profiles=[])).json()
    assert data == {"profile": "none", "clients": [], "sessions": []}


def test_a_login_the_strict_rule_refuses_gets_a_plain_answer(monkeypatch):
    monkeypatch.setenv("MANAGER_PROFILE_STRICT", "true")
    two = [dict(PROFILE[0]), dict(PROFILE[0], id="p2", name="Joe Duplicate")]
    data = _read(monkeypatch, _standard_client(profiles=two)).json()
    assert data["profile"] == "blocked" and data["clients"] == []


def test_a_failing_read_is_a_readable_502(monkeypatch):
    r = _read(monkeypatch, _standard_client(fail=True))
    assert r.status_code == 502
    assert "could not be read" in r.json()["detail"]


def test_the_page_fills_the_two_frames_from_the_one_read():
    js = (ROOT / "portal/frontend/home.js").read_text()
    assert "/api/portal/home/mentoring" in js
    assert "Open Client Management" in js
    assert "CBMGrid.enhance" in js and "CBMBusy.loading" in js
    # Open lands on the Sessions tab in the record's own named tab.
    assert '"sessions"' in js and '"cbm-rec-mentorsessions-"' in js
    # The stored next-session field is never read by the page.
    assert "nextSessionDateTime" not in js


# --- 11-18-26 changes: Directories menu, Upcoming events panel, text size -------

STAFF_PAGES = (
    "activity/frontend/index.html", "analytics/frontend/index.html",
    "assignments/frontend/index.html", "campaigns/frontend/index.html",
    "campaigns/frontend/list-members.html", "directory/frontend/index.html",
    "directory/frontend/mentor.html", "directory/frontend/record.html",
    "events/frontend/index.html", "mentoradmin/frontend/index.html",
    "mentorprofile/frontend/index.html", "myemail/frontend/index.html",
    "ops/frontend/index.html", "portal/frontend/event.html",
    "portal/frontend/index.html", "sessions/frontend/index.html",
    "setup/frontend/index.html",
)


@pytest.mark.parametrize("page", STAFF_PAGES)
def test_every_staff_page_applies_the_text_size_right_after_busy_js(page):
    html = (ROOT / page).read_text()
    assert "/shared/textsize.js" in html, page
    assert html.index("/shared/busy.js") < html.index("/shared/textsize.js")


def test_public_pages_do_not_load_the_text_size():
    for page in ("forms/client_intake/frontend/index.html", "events/public_frontend/index.html",
                 "surveys/frontend/index.html"):
        assert "/shared/textsize.js" not in (ROOT / page).read_text(), page


def test_no_staff_stylesheet_sizes_by_the_window_without_the_zoom_correction():
    """Under a text size zoom, a bare 90vh is 117% of the window at Larger."""
    import re

    bare = re.compile(r"(?<![\w.#-])\d+(?:\.\d+)?d?v[hw]\b")
    roots = ("frontend/shared", "portal", "sessions", "assignments", "mentoradmin",
             "mentorprofile", "myemail", "ops", "campaigns/frontend", "directory",
             "events/frontend", "analytics", "setup", "activity")
    found = []
    for r in roots:
        for p in (ROOT / r).rglob("*"):
            if p.suffix not in (".css", ".js") or "vendor" in p.parts or p.name == "textsize.js":
                continue
            for line in p.read_text().splitlines():
                code = line.split("//")[0] if p.suffix == ".js" else line
                if "/*" in code or code.strip().startswith("*"):
                    continue
                if bare.search(code.replace("1vh", "").replace("1vw", "").replace("1dvh", "")):
                    found.append(f"{p.relative_to(ROOT)}: {line.strip()}")
    assert not found, found


def test_the_text_size_is_a_member_preference(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        _sign_in(monkeypatch, c, _standard_client())
        assert c.get("/api/portal/preferences/ui.textSize").status_code == 200
        assert c.get("/api/portal/preferences/ui.fontSize").status_code == 404


def test_the_events_rail_has_its_own_frame_when_the_calendar_is_on(monkeypatch):
    from portal.router import _home_sections

    monkeypatch.setenv("HOME_V2", "true")
    get_settings.cache_clear()
    user = {"teams": [MENTOR_TEAM], "isAdmin": False}
    off = _home_sections(user, get_settings())
    assert "events" not in off
    monkeypatch.setattr(type(get_settings()), "portal_calendar_active", property(lambda s: True))
    on = _home_sections(user, get_settings())
    assert on.index("chapter") + 1 == on.index("events")
    js = (ROOT / "portal/frontend/home.js").read_text()
    assert 'moveIn(frames.events._body, "eventsRail"' in js
    # The analytics panel moved to its own frame in phase 4 (answer 5).
    assert 'moveIn(frames.analytics._body, "analyticsSection"' in js


def test_the_directories_are_one_menu_in_the_bar():
    js = (ROOT / "portal/frontend/home.js").read_text()
    assert '"Directories "' in js and "directoriesMenu(data.directories)" in js
