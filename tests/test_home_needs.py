"""The new home page, phase 3: Needs you (HOME_V2; prds/home-page-plan.md
§ 4.2 and § 8; Doug's eight answers at the phase's first stop, 11-18-26).

Each kind's rule on its own, then the endpoint: co-mentored engagements
included, the sort, ruling 3 (no waiting-clients row for a mentor), the
threshold setting, a kind that fails on its own, the switch off, and My
Email's link that opens one conversation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request, volunteer
from portal import needs

ROOT = Path(__file__).resolve().parents[1]
MENTOR_TEAM = "Mentor Team"
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)   # a Wednesday


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _ago(days: float, now: datetime = NOW) -> str:
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _client(cid, status, last=None, assigned=None):
    return {"id": cid, "name": f"Company {cid}", "status": status,
            "lastContact": last, "assignedDate": assigned}


# --- the rules, one kind at a time -----------------------------------------------

def test_no_contact_lists_past_the_threshold_with_the_day_count():
    rows = needs.no_contact_items([
        _client("a", "Active", last=_ago(30)),
        _client("b", "Active", last=_ago(10)),
        _client("c", "Assigned", last=None, assigned=_ago(25)),
        _client("d", "Pending Acceptance", last=_ago(22)),
    ], NOW, 21)
    by = {r["name"]: r for r in rows}
    assert set(by) == {"Company a", "Company c", "Company d"}
    assert by["Company a"]["chip"] == "30 days" and by["Company a"]["tone"] == "red"
    assert by["Company a"]["reason"] == "No contact for 30 days"
    assert by["Company c"]["reason"] == "No contact since assigned 25 days ago"
    assert by["Company a"]["url"] == "/mentorsessions/record/a"
    assert by["Company a"]["target"] == "cbm-rec-mentorsessions-a"


def test_no_contact_never_lists_on_hold_and_zero_switches_it_off():
    on_hold = [_client("a", "On-Hold", last=_ago(90))]
    assert needs.no_contact_items(on_hold, NOW, 21) == []
    active = [_client("a", "Active", last=_ago(90))]
    assert needs.no_contact_items(active, NOW, 0) == []
    # Neither a last contact nor an assignment: nothing to count from.
    assert needs.no_contact_items([_client("a", "Active")], NOW, 21) == []


def test_new_lists_pending_acceptance_and_the_last_seven_days():
    rows = needs.new_items([
        _client("a", "Pending Acceptance", assigned=_ago(40)),
        _client("b", "Assigned", assigned=_ago(3)),
        _client("c", "Active", assigned=_ago(9)),
        _client("d", "On-Hold", assigned=_ago(1)),
    ], NOW)
    by = {r["name"]: r for r in rows}
    assert set(by) == {"Company a", "Company b"}
    assert by["Company a"]["reason"] == "Assigned to you, waiting for you to accept"
    assert by["Company b"]["chip"] == "New" and by["Company b"]["tone"] == "navy"


def _session(sid, eid, days, notes="", steps="", summary=""):
    return {"id": sid, "engagementId": eid, "status": "Completed", "name": f"Session {sid}",
            "dateStart": _ago(days), "sessionNotes": notes, "nextSteps": steps,
            "sessionAiSummary": summary}


NAMES = {"e1": "Company e1", "e5": "Company e5"}


def test_notes_lists_a_completed_session_with_neither_notes_nor_next_steps():
    rows = needs.session_items([
        _session("s1", "e1", 2),                                # listed
        _session("s2", "e1", 3, notes="<p>Talked cash flow</p>"),
        _session("s3", "e1", 3, steps="<p>Send the P&amp;L</p>"),
        _session("s4", "e1", 3, notes="<p>&nbsp;</p><br>"),      # empty rich text: listed
        _session("s5", "e1", 45),                               # older than 30 days
        _session("s6", "zz", 2),                                # not the member's
    ], NAMES, NOW, summary_field="sessionAiSummary")
    assert [r["reason"].split(" (")[0] for r in rows] == ["Session s1", "Session s4"]
    assert all(r["kind"] == "notes" and r["tone"] == "amber" for r in rows)
    assert rows[0]["url"] == "/mentorsessions/record/e1?tab=sessions"


def test_summary_lists_a_summary_with_empty_session_notes_for_fourteen_days():
    rows = needs.session_items([
        # The note taker filled next steps; the mentor has written nothing.
        _session("s1", "e1", 2, steps="<ul><li>x</li></ul>", summary="<p>Summary</p>"),
        _session("s2", "e1", 2, notes="<p>Mine</p>", summary="<p>Summary</p>"),
        _session("s3", "e5", 20, summary="<p>Summary</p>"),       # past 14 days
    ], NAMES, NOW, summary_field="sessionAiSummary")
    assert [(r["kind"], r["name"]) for r in rows] == [("summary", "Company e1")]
    assert rows[0]["chip"] == "Summary"


def test_without_the_summary_field_a_session_is_judged_on_notes_alone():
    rows = needs.session_items([_session("s1", "e1", 2, summary="<p>ignored</p>")],
                               NAMES, NOW, summary_field=None)
    assert [r["kind"] for r in rows] == ["notes"]


def test_email_reuses_my_emails_flag_after_one_working_day():
    conv = lambda cid, at, waiting=True: {  # noqa: E731
        "id": cid, "subject": f"Re: {cid}", "awaitingReply": waiting, "lastMessageAt": at,
        "records": [{"name": "Engagement e1", "id": "e1", "entity": "CEngagement", "slug": "mentorsessions"}]}
    rows = needs.email_items([
        conv("c1", _ago(2)),                         # Monday: listed on Wednesday
        conv("c2", _ago(0.2)),                       # today: not yet
        conv("c3", _ago(5), waiting=False),          # the member replied last
    ], NOW)
    # The record's Communications tab with the conversation open (option C).
    assert [r["url"] for r in rows] == [
        "/mentorsessions/record/e1?tab=communications&conversation=c1"]
    assert rows[0]["target"] == "cbm-rec-mentorsessions-e1"
    assert rows[0]["reason"] == "Waiting for your reply: Re: c1"
    # A Friday message waits over the weekend: not listed on Sunday.
    sunday = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    friday = (sunday - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    assert needs.email_items([conv("c4", friday)], sunday) == []
    assert len(needs.email_items([conv("c4", friday)], sunday + timedelta(days=1))) == 1


def test_an_email_on_several_records_opens_the_engagement_and_none_opens_my_email():
    partner = {"name": "Alliance", "id": "p1", "entity": "CPartnerProfile",
               "slug": "partnersessions"}
    engagement = {"name": "Engagement e1", "id": "e1", "entity": "CEngagement",
                  "slug": "mentorsessions"}
    link = needs.conversation_link("c9", [partner, engagement])
    assert link["url"] == "/mentorsessions/record/e1?tab=communications&conversation=c9"
    link = needs.conversation_link("c9", [partner])
    assert link == {"url": "/partnersessions/record/p1?tab=communications&conversation=c9",
                    "target": "cbm-rec-partnersessions-p1"}
    assert needs.conversation_link("c9", [])["url"] == "/myemail/?conversation=c9"


def test_staff_rows_come_from_the_attention_counts():
    rows = needs.staff_items([
        {"url": "/assignments/", "count": 3, "label": "Clients awaiting mentor assignment"},
        {"url": "/ops/", "count": 0, "label": "Open submissions"},
    ])
    assert len(rows) == 1
    assert rows[0]["tone"] == "purple" and rows[0]["chip"] == "Staff"
    assert rows[0]["target"] == "cbm-assignments" and rows[0]["reason"] == "3 waiting"


def test_the_order_is_by_kind_then_age_and_only_a_red_first_row_is_urgent():
    items = (needs.staff_items([{"url": "/ops/", "count": 9, "label": "Open submissions"}])
             + needs.new_items([_client("n", "Pending Acceptance")], NOW)
             + needs.no_contact_items([_client("a", "Active", last=_ago(25)),
                                       _client("b", "Active", last=_ago(40))], NOW, 21)
             + needs.session_items([_session("s1", "e1", 2)], NAMES, NOW,
                                   summary_field=None))
    rows = needs.ordered(items)
    assert [r["kind"] for r in rows] == ["nocontact", "nocontact", "notes", "new", "staff"]
    assert rows[0]["name"] == "Company b"           # the older silence first
    assert [r["urgent"] for r in rows] == [True, False, False, False, False]
    # A first row that is not red is not tinted.
    calm = needs.ordered(needs.new_items([_client("n", "Pending Acceptance")], NOW))
    assert calm[0]["urgent"] is False


# --- the endpoint ------------------------------------------------------------------

def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%d %H:%M:%S")


def _eng(eid, status, mentor="p1", **extra):
    row = {"id": eid, "name": f"Engagement {eid}", "engagementStatus": status,
           "clientOrganizationName": f"Company {eid}", "clientOrganizationId": f"a-{eid}",
           "engagementClientName": f"Client {eid}", "lastContactDate": _stamp(timedelta(days=-2)),
           "mentorProfileId": mentor, "createdAt": "2026-10-01 00:00:00",
           "engagementAssignedDate": _stamp(timedelta(days=-60))}
    row.update(extra)
    return row


PROFILE = [{"id": "p1", "name": "Joe Mentor", "mentorStatus": "Active",
            "cbmEmail": "joe@example.org", "assignedUserId": "u1", "assignedUsersIds": ["u1"]}]


class FakeClient:
    """Answers the reads the two home page endpoints make."""

    def __init__(self, owned, comentored, completed, *, fail_sessions=False, fail_all=False,
                 summary_field=True):
        self.owned, self.comentored, self.completed = owned, comentored, completed
        self.fail_sessions, self.fail_all = fail_sessions, fail_all
        self.summary_field = summary_field
        self.calls: list[str] = []

    async def list(self, entity, **kw):
        self.calls.append(f"list {entity}")
        if self.fail_all:
            raise EspoError("CRM down")
        if entity == "CMentorProfile":
            return {"list": PROFILE}
        if entity == "CSession":
            completed = any(w.get("value") == "Completed" for w in kw.get("where") or [])
            if completed and self.fail_sessions:
                raise EspoError("sessions refused")
            return {"list": self.completed if completed else []}
        if entity == "CEngagement":
            return {"list": [], "total": 4}
        return {"list": [], "total": 0}

    async def list_related(self, entity, rid, link, **kw):
        self.calls.append(f"related {link}")
        if self.fail_all:
            raise EspoError("CRM down")
        return {"list": self.owned if link == "engagements1" else self.comentored}

    async def get(self, entity, rid, **kw):
        return {"userName": "joe"}

    async def metadata(self, key):
        if key == "entityDefs.CSession.fields" and self.summary_field:
            return {"sessionAiSummary": {"type": "wysiwyg"}}
        return None


def _standard(**kw):
    owned = [
        _eng("e1", "Active", lastContactDate=_stamp(timedelta(days=-30))),
        _eng("e2", "Pending Acceptance"),
        _eng("e4", "On-Hold", lastContactDate=_stamp(timedelta(days=-90))),
    ]
    comentored = [_eng("e5", "Assigned", mentor="p9", lastContactDate=None,
                       engagementAssignedDate=_stamp(timedelta(days=-25)))]
    completed = [
        {"id": "s1", "engagementId": "e5", "status": "Completed", "name": "Kick-off",
         "dateStart": _stamp(timedelta(days=-3)), "sessionNotes": "", "nextSteps": ""},
        {"id": "s9", "engagementId": "zz", "status": "Completed", "name": "Not mine",
         "dateStart": _stamp(timedelta(days=-3)), "sessionNotes": "", "nextSteps": ""},
    ]
    return FakeClient(owned, comentored, completed, **kw)


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


def _needs(monkeypatch, client, teams=(MENTOR_TEAM,), **env):
    with TestClient(_app(monkeypatch, HOME_V2="true", **env)) as c:
        _sign_in(monkeypatch, c, client, teams)
        r = c.get("/api/portal/home/needs")
    assert r.status_code == 200, r.text
    return r.json()


def test_off_the_endpoint_is_not_there(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        _sign_in(monkeypatch, c, _standard())
        assert c.get("/api/portal/home/needs").status_code == 404


def test_signed_out_is_refused(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        assert c.get("/api/portal/home/needs").status_code == 401


def test_a_mentor_sees_owned_and_co_mentored_rows_sorted(monkeypatch):
    data = _needs(monkeypatch, _standard())
    got = [(i["kind"], i["name"]) for i in data["items"]]
    assert got == [
        ("nocontact", "Company e1"),        # 30 days, owned
        ("nocontact", "Company e5"),        # 25 days since assigned, co-mentored
        ("notes", "Company e5"),            # the co-mentored session; "zz" is not theirs
        ("new", "Company e2"),              # Pending Acceptance
    ]
    assert data["items"][0]["urgent"] is True
    # On-Hold e4 is silent for 90 days and still not listed (answer 6).
    assert "Company e4" not in str(data)
    assert data["unavailable"] == []


def test_ruling_3_a_mentor_never_gets_the_waiting_clients_row(monkeypatch):
    data = _needs(monkeypatch, _standard())
    assert not [i for i in data["items"] if i["kind"] == "staff"]


def test_client_administration_staff_get_it_beside_their_mentoring_rows(monkeypatch):
    data = _needs(monkeypatch, _standard(),
                  teams=(MENTOR_TEAM, "Client Administration Team"))
    staff = [i for i in data["items"] if i["kind"] == "staff"]
    assert [(s["name"], s["reason"]) for s in staff] == [
        ("Clients awaiting mentor assignment", "4 waiting")]
    assert data["items"][-1]["kind"] == "staff"      # after every mentoring row


def test_a_staff_member_alone_gets_staff_rows_only(monkeypatch):
    client = _standard()
    data = _needs(monkeypatch, client, teams=("Client Administration Team",))
    assert {i["kind"] for i in data["items"]} == {"staff"}
    assert "related engagements1" not in client.calls


def test_the_threshold_is_a_setting_read_per_request(monkeypatch):
    from core.settings_registry import SETTINGS

    spec = next(s for s in SETTINGS if s.key == "home_no_contact_days")
    assert spec.kind == "int" and spec.unit == "days"
    assert get_settings().home_no_contact_days == 21
    data = _needs(monkeypatch, _standard(), HOME_NO_CONTACT_DAYS="40")
    assert not [i for i in data["items"] if i["kind"] == "nocontact"]
    data = _needs(monkeypatch, _standard(), HOME_NO_CONTACT_DAYS="1")
    names = {i["name"] for i in data["items"] if i["kind"] == "nocontact"}
    assert names == {"Company e1", "Company e2", "Company e5"}


def test_a_kind_that_fails_is_left_out_and_named(monkeypatch):
    data = _needs(monkeypatch, _standard(fail_sessions=True))
    assert data["unavailable"] == ["sessions"]
    assert {i["kind"] for i in data["items"]} == {"nocontact", "new"}


def test_a_failing_crm_never_fails_the_endpoint(monkeypatch):
    data = _needs(monkeypatch, _standard(fail_all=True),
                  teams=(MENTOR_TEAM, "Client Administration Team"))
    assert data["items"] == []
    assert "clients" in data["unavailable"]


def test_the_two_reads_share_one_engagement_read(monkeypatch):
    client = _standard()
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        _sign_in(monkeypatch, c, client)
        assert c.get("/api/portal/home/mentoring").status_code == 200
        assert c.get("/api/portal/home/needs").status_code == 200
    assert client.calls.count("related engagements1") == 1


def test_email_rows_and_the_unread_count_come_from_one_inbox_run(monkeypatch):
    runs = []

    async def fake_inbox(settings, client, store, user):
        runs.append(1)
        return {"profileFound": True, "conversations": [
            {"id": "c1", "subject": "Pricing", "awaitingReply": True, "unread": True,
             "lastMessageAt": _stamp(timedelta(days=-4)),
             "records": [{"name": "Engagement e1", "id": "e1", "entity": "CEngagement", "slug": "mentorsessions"}]},
            {"id": "c2", "subject": "Thanks", "awaitingReply": False, "unread": True,
             "lastMessageAt": _stamp(timedelta(days=-1)), "records": []},
        ]}

    monkeypatch.setattr("myemail.service.build_inbox", fake_inbox)
    monkeypatch.setattr("comms.service.get_store", lambda settings: object())
    data = _needs(monkeypatch, _standard(), GMAIL_SYNC="true")
    email = [i for i in data["items"] if i["kind"] == "email"]
    assert [e["url"] for e in email] == [
        "/mentorsessions/record/e1?tab=communications&conversation=c1"]
    assert data["unreadTotal"] == 2
    assert runs == [1]


def test_without_the_email_integration_there_are_no_email_rows(monkeypatch):
    data = _needs(monkeypatch, _standard())
    assert data["unreadTotal"] is None
    assert not [i for i in data["items"] if i["kind"] == "email"]


# --- the pages -----------------------------------------------------------------------

def test_the_page_fills_needs_you_and_the_greeting():
    js = (ROOT / "portal/frontend/home.js").read_text()
    assert "/api/portal/home/needs" in js
    assert "CBMBusy.loading(body, read)" in js
    assert '" items need you"' in js and '" item needs you"' in js
    assert "cbm-row--urgent" in js and "cbm-kind-chip cbm-tone--" in js
    # The counts move off the bar while Needs you holds them, and come back
    # when its read fails.
    app = (ROOT / "portal/frontend/app.js").read_text()
    v2 = app[app.index("function renderHomeV2"):app.index("function renderHome(")]
    assert "badgesFallback" in v2 and "badge: badgeTile" in v2
    assert "badgesFallback()" in js


def test_the_record_page_opens_a_linked_conversation_once():
    js = (ROOT / "sessions/frontend/app.js").read_text()
    assert "openLinkedConversation(wantTab);" in js
    assert 'get("conversation")' in js and "linkedConversationDone = true" in js


def test_my_emails_reply_there_button_opens_the_conversation_on_the_record():
    js = (ROOT / "myemail/frontend/app.js").read_text()
    assert '"?tab=communications&conversation=" + encodeURIComponent(row.id)' in js
    assert '"cbm-rec-" + rec.slug + "-" + rec.id' in js


def test_a_click_anywhere_on_a_needs_you_row_opens_it_once():
    js = (ROOT / "portal/frontend/home.js").read_text()
    row = js[js.index("function needRow"):js.index("function fillNeeds")]
    assert 'li.addEventListener("click"' in row
    assert row.count("now - lastOpen < 800") == 2       # the row and the name share one guard


def test_my_emails_record_name_is_a_label_so_the_row_opens_the_email():
    js = (ROOT / "myemail/frontend/app.js").read_text()
    rows = js[js.index("visible.forEach(function (r) {"):js.index("var c2 = ")]
    assert 'createElement("a")' not in rows and 'createElement("span")' in rows


def test_my_email_opens_one_conversation_from_a_link():
    js = (ROOT / "myemail/frontend/app.js").read_text()
    assert 'URLSearchParams(location.search).get("conversation")' in js
    assert "openLinkedConversation();" in js
    # Signing in on the way keeps the link.
    assert '"/myemail/" + location.search' in js
