"""The Business Evaluation's mentor side, phase 2 (evaluation/sending.py and
the Evaluations routes on Client Management): the tab and its switch, the
feature detection, Send (records, round, assigned users, the link, the
warning above three, the escalation of a refused create), the answers view,
the action log, and Partner and Funder Management never carrying any of it.

The application database is ``tests/survey_fakes.MemoryStore``."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from evaluation import sending, service
from evaluation.purpose import load_surveys
from forms import info_request
from sessions.config import MENTOR, PARTNER, SPONSOR
from surveys.service import link_is_open
from tests.survey_fakes import MemoryStore

ENG = "6612engagement001"
PROFILE = "6612clientprof001"

_USER = {
    "userId": "u-mentor", "userName": "joe.mentor", "name": "Joe Mentor",
    "isAdmin": False, "teams": ["Mentor Team"], "roles": [], "token": "t",
}


class FakeCrm:
    """Enough of the CRM for the tab and Send. ``refuse_create`` makes the
    user's create a 403, as the Mentor Role's ``team`` assignment permission
    does for a stamp naming someone outside the mentor's teams."""

    def __init__(self, *, has_entity=True, refuse_create=False, profile_answered=False,
                 records=None):
        self.has_entity = has_entity
        self.refuse_create = refuse_create
        self.profile = {"id": PROFILE, "name": "Halstead Print Works",
                        "linkedCompanyName": "Halstead Print Works",
                        "evaluationProfile": "", "evaluationProfileAt": None}
        if profile_answered:
            self.profile["evaluationProfile"] = json.dumps(
                {"survey": "business-profile.v1", "answers": {}})
        self.records = list(records or [])
        self.creates: list[dict] = []
        self.notes: list[dict] = []
        self.updates: list[tuple[str, str, dict]] = []

    async def metadata(self, key):
        if key == f"entityDefs.{service.ENTITY}":
            return {"fields": {"status": {}}} if self.has_entity else None
        return None

    async def get(self, entity, record_id, select=None):
        if entity == "CEngagement":
            return {"id": ENG, "name": "Halstead — mentoring", "engagementClientId": PROFILE,
                    "clientOrganizationName": "Halstead Print Works",
                    "assignedUsersIds": ["u-mentor", "u-comentor"],
                    "primaryEngagementContactId": "c1",
                    "primaryEngagementContactName": "Pat Halstead"}
        if entity == service.CLIENT_PROFILE:
            return dict(self.profile)
        if entity == "Contact":
            return {"id": record_id, "name": "Pat Halstead", "firstName": "Pat",
                    "emailAddress": "pat@example.com"}
        if entity == service.ENTITY:
            for r in self.records:
                if r["id"] == record_id:
                    return dict(r)
            raise EspoError(f"get {entity}/{record_id} failed: HTTP 404")
        raise EspoError(f"get {entity} failed: HTTP 404")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        rows = [r for r in self.records if r.get("engagementId") == where[0]["value"]]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def create(self, entity, payload):
        if entity == "Note":
            self.notes.append(payload)
            return {"id": f"n{len(self.notes)}"}
        if self.refuse_create:
            raise EspoError("create CBusinessEvaluation failed: HTTP 403 Assignment failure")
        rec = {"id": f"be{len(self.records) + 1:015d}", **payload}
        self.records.append(rec)
        self.creates.append(payload)
        return rec

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}


@pytest.fixture(scope="module")
def surveys():
    loaded = load_surveys()
    assert loaded, "the survey definitions must load"
    return loaded


def run(coro):
    return asyncio.run(coro)


# --- the service --------------------------------------------------------------

def test_the_send_dialog_offers_the_area_surveys_and_never_the_business_profile(surveys):
    keys = [a["key"] for a in sending.area_choices(surveys)]
    assert "finance" in keys and "marketing" in keys
    assert "business-profile" not in keys


def test_more_than_three_areas_is_advised_against_and_still_allowed():
    assert sending.advice(2) is None and sending.advice(3) is None
    assert "4 areas" in sending.advice(4)


def test_send_creates_one_record_per_area_and_a_link(surveys):
    crm, store = FakeCrm(), MemoryStore()
    result = run(sending.send(crm, store, engagement_id=ENG, area_keys=["finance", "marketing"],
                              surveys=surveys, created_by="joe.mentor", days=30))
    assert result["round"] == 1
    assert [c["evaluationArea"] for c in crm.creates] == ["Finance", "Marketing"]
    for c in crm.creates:
        assert c["status"] == "Sent" and c["evaluationRound"] == 1
        assert c["engagementId"] == ENG and c["clientProfileId"] == PROFILE
        assert c["assignedUsersIds"] == ["u-mentor", "u-comentor"]
        assert c["name"].endswith("— Halstead Print Works")
    link = result["link"]
    assert link["data"]["round"] == 1 and link["data"]["area_keys"] == ["finance", "marketing"]
    assert link["data"]["profile_needed"] is True and link["display_name"] == "Halstead Print Works"
    rows = run(store.answers_for(link["id"]))
    assert sorted(r["survey_key"] for r in rows) == ["business-profile", "finance", "marketing"]
    assert {r["crm_record_id"] for r in rows if r["survey_key"] != "business-profile"} == {
        c["id"] for c in crm.records}
    assert result["warning"] is None


def test_the_next_send_is_the_next_round_and_skips_an_answered_profile(surveys):
    crm = FakeCrm(profile_answered=True, records=[
        {"id": "old1", "engagementId": ENG, "evaluationRound": 1, "evaluationArea": "Finance",
         "status": "Submitted"}])
    store = MemoryStore()
    result = run(sending.send(crm, store, engagement_id=ENG, area_keys=["marketing"],
                              surveys=surveys, created_by="joe.mentor", days=30))
    assert result["round"] == 2
    assert result["link"]["data"]["profile_needed"] is False
    rows = run(store.answers_for(result["link"]["id"]))
    assert [r["survey_key"] for r in rows] == ["marketing"]


def test_send_refuses_no_area_and_an_unknown_area(surveys):
    with pytest.raises(sending.SendError, match="at least one"):
        run(sending.send(FakeCrm(), MemoryStore(), engagement_id=ENG, area_keys=[],
                         surveys=surveys, created_by="x", days=30))
    with pytest.raises(sending.SendError, match="not an evaluation area"):
        run(sending.send(FakeCrm(), MemoryStore(), engagement_id=ENG, area_keys=["payroll"],
                         surveys=surveys, created_by="x", days=30))
    with pytest.raises(sending.SendError, match="not an evaluation area"):
        run(sending.send(FakeCrm(), MemoryStore(), engagement_id=ENG,
                         area_keys=["business-profile"], surveys=surveys, created_by="x", days=30))


def test_a_create_refused_as_the_user_is_written_under_the_org_key(surveys):
    user, key = FakeCrm(refuse_create=True), FakeCrm()
    result = run(sending.send(user, MemoryStore(), engagement_id=ENG, area_keys=["finance"],
                              surveys=surveys, created_by="x", days=30, escalate=lambda: key))
    assert len(key.creates) == 1 and result["records"][0]["escalated"] is True


def test_a_refused_create_with_no_org_key_is_the_users_error(surveys):
    with pytest.raises(EspoError):
        run(sending.send(FakeCrm(refuse_create=True), MemoryStore(), engagement_id=ENG,
                         area_keys=["finance"], surveys=surveys, created_by="x", days=30,
                         escalate=lambda: None))


def test_the_tab_groups_records_by_round_and_reports_the_link_without_its_token(surveys):
    crm, store = FakeCrm(), MemoryStore()
    run(sending.send(crm, store, engagement_id=ENG, area_keys=["finance"],
                     surveys=surveys, created_by="x", days=30))
    run(sending.send(crm, store, engagement_id=ENG, area_keys=["marketing", "finance"],
                     surveys=surveys, created_by="x", days=30))
    rounds = run(sending.rounds_view(crm, store, ENG))
    assert [r["round"] for r in rounds] == [2, 1]
    assert [x["area"] for x in rounds[0]["records"]] == ["Finance", "Marketing"]
    assert rounds[0]["link"]["state"] == "open"
    token = run(sending.links_for_engagement(store, ENG))[0]["token"]
    assert token not in json.dumps(rounds, default=str)


def test_the_answers_view_refuses_a_record_from_another_engagement(surveys):
    crm = FakeCrm(records=[{"id": "x1", "engagementId": "other", "clientProfileId": PROFILE}])
    assert run(sending.answers_view(crm, ENG, "x1", surveys)) is None


def test_the_answers_view_shows_the_answers_and_the_business_profile(surveys):
    crm = FakeCrm(profile_answered=True, records=[{
        "id": "x1", "engagementId": ENG, "clientProfileId": PROFILE, "evaluationArea": "Finance",
        "evaluationRound": 1, "status": "Submitted", "answersReadable": "<p>Q</p>"}])
    view = run(sending.answers_view(crm, ENG, "x1", surveys))
    assert view["answersHtml"] == "<p>Q</p>" and view["profileHtml"]


# --- the routes -----------------------------------------------------------------

def _app(monkeypatch, *, on=True, crm=None, store="memory"):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("BUSINESS_EVALUATION", "true" if on else "false")
    get_settings.cache_clear()
    crm = crm or FakeCrm()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: crm)
    app = create_app([info_request.SPEC])
    app.state.survey_store = MemoryStore() if store == "memory" else store
    return app, crm


def test_the_tab_is_client_management_only():
    assert MENTOR.evaluations_tab is True
    assert PARTNER.evaluations_tab is False and SPONSOR.evaluations_tab is False


def test_switch_off_hides_the_tab_and_every_route(monkeypatch):
    app, _ = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        tabs = [t["key"] for t in c.get("/mentorsessions/api/session").json()["detailTabs"]]
        assert "evaluations" not in tabs
        assert c.get(f"/mentorsessions/api/records/{ENG}/evaluations").status_code == 404
        assert c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send",
                      json={"areas": ["finance"]}).status_code == 404


def test_switch_on_shows_the_tab_on_client_management_only(monkeypatch):
    app, _ = _app(monkeypatch)
    with TestClient(app) as c:
        tabs = [t["key"] for t in c.get("/mentorsessions/api/session").json()["detailTabs"]]
        assert tabs.index("evaluations") == tabs.index("sessions") + 1
        for slug in ("partnersessions", "sponsorsessions"):
            assert c.get(f"/{slug}/api/records/{ENG}/evaluations").status_code == 404


def test_a_crm_without_the_entity_says_so(monkeypatch):
    app, _ = _app(monkeypatch, crm=FakeCrm(has_entity=False))
    with TestClient(app) as c:
        body = c.get(f"/mentorsessions/api/records/{ENG}/evaluations").json()
        assert body["available"] is False and "Business Evaluation record type" in body["reason"]
        r = c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send", json={"areas": ["finance"]})
        assert r.status_code == 409


def test_send_route_records_the_action_and_puts_the_link_only_in_the_email(monkeypatch):
    recorded = []

    async def fake_record(client, **kw):
        recorded.append(kw)

    monkeypatch.setattr("core.action_log.record_action", fake_record)
    app, crm = _app(monkeypatch)
    with TestClient(app) as c:
        r = c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send",
                   json={"areas": ["finance", "marketing", "finance"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["round"] == 1 and body["areas"] == ["Finance", "Marketing"]
        token = next(iter(app.state.survey_store.links.values()))["token"]
        email = body.pop("email")
        assert token not in json.dumps(body)
        assert f"/survey/{token}" in email["bodyHtml"]
        assert email["to"] == "pat@example.com"
        assert email["subject"] == "Your free business evaluation from " + get_settings().organization_name
        assert "Hi Pat," in email["bodyHtml"] and "Finance and Marketing" in email["bodyHtml"]
        tab = c.get(f"/mentorsessions/api/records/{ENG}/evaluations").json()
        assert tab["available"] is True and tab["rounds"][0]["round"] == 1
    assert len(recorded) == 1
    entry = recorded[0]
    assert entry["action"] == "Evaluation Sent" and entry["parent_id"] == ENG
    assert entry["details"]["fields"] == {"status": {"to": "Sent"}}
    assert entry["actor_name"] == "Joe Mentor"


def test_send_route_warns_above_three_and_still_sends(monkeypatch, surveys):
    many = [s.key for s in sending.area_surveys(surveys)]
    if len(many) <= sending.ADVISED_MAX:
        # The pilot has two areas (BE22): prove the warning on the service.
        assert sending.advice(len(many) + 2)
        return
    app, crm = _app(monkeypatch)
    with TestClient(app) as c:
        r = c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send", json={"areas": many})
    assert r.status_code == 200 and r.json()["warning"]


def test_send_route_names_a_missing_choice(monkeypatch):
    app, _ = _app(monkeypatch)
    with TestClient(app) as c:
        r = c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send", json={"areas": []})
    assert r.status_code == 400 and "at least one" in r.json()["detail"]


def test_send_route_without_a_database_says_so(monkeypatch):
    app, crm = _app(monkeypatch, store=None)
    with TestClient(app) as c:
        r = c.post(f"/mentorsessions/api/records/{ENG}/evaluations/send", json={"areas": ["finance"]})
    assert r.status_code == 400 and "database" in r.json()["detail"]
    assert crm.creates == []


def test_answers_route_404s_a_record_from_another_engagement(monkeypatch):
    app, _ = _app(monkeypatch, crm=FakeCrm(records=[{"id": "x1", "engagementId": "other"}]))
    with TestClient(app) as c:
        assert c.get(f"/mentorsessions/api/records/{ENG}/evaluations/x1").status_code == 404


def test_the_panel_and_its_renderer_exist():
    html = open("sessions/frontend/index.html", encoding="utf-8").read()
    js = open("sessions/frontend/app.js", encoding="utf-8").read()
    assert 'data-dpanel="evaluations"' in html and 'id="evlSendBtn"' in html
    assert "function renderEvaluations" in js and 'tab === "evaluations"' in js
    assert 'fitGrid("evlTable"' in js


# --- the email -------------------------------------------------------------------

def test_the_email_names_the_areas_the_link_and_the_expiry(surveys):
    from datetime import datetime, timezone
    from evaluation import email

    out = email.invitation(org="Cleveland Business Mentors", first_name="Pat <b>",
                           area_titles=["Finance", "Marketing", "Product"],
                           link_url="https://apps.example.org/evaluation/abc",
                           expires_at=datetime(2026, 12, 13, 15, tzinfo=timezone.utc),
                           profile_needed=True)
    assert out["subject"] == "Your free business evaluation from Cleveland Business Mentors"
    body = out["bodyHtml"]
    assert "Hi Pat &lt;b&gt;," in body
    assert "Finance, Marketing and Product" in body
    assert 'href="https://apps.example.org/evaluation/abc"' in body
    assert "December 13, 2026" in body
    assert "a few questions about your business" in body
    again = email.invitation(org="X", first_name="", area_titles=["Finance"], link_url="u",
                             expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
                             profile_needed=False)
    assert again["bodyHtml"].startswith("<p>Hello,</p>")
    assert "a few questions about your business" not in again["bodyHtml"]


def test_the_composer_opens_with_a_prefilled_message_that_is_unsent_work():
    js = open("frontend/shared/compose.js", encoding="utf-8").read()
    assert "pre.bodyHtml" in js and "pre.draftName" in js
    app = open("sessions/frontend/app.js", encoding="utf-8").read()
    assert "bodyHtml: email.bodyHtml" in app


# --- Resend, Expire, Record a decline ------------------------------------------

def _sent(surveys, crm=None, store=None):
    crm, store = crm or FakeCrm(), store or MemoryStore()
    run(sending.send(crm, store, engagement_id=ENG, area_keys=["finance", "marketing"],
                     surveys=surveys, created_by="x", days=30))
    return crm, store


def test_resend_ends_the_old_link_and_carries_answers_and_consent(surveys):
    crm, store = _sent(surveys)
    old = run(sending.links_for_engagement(store, ENG))[0]
    run(store.set_consent(old["id"], service.utcnow()))
    run(store.save_answers(old["id"], "finance", {"q": 1}, service.utcnow()))
    result = run(sending.resend(crm, store, engagement_id=ENG, round_no=1,
                                created_by="x", days=30))
    new = result["link"]
    assert not link_is_open(run(store.link_by_id(old["id"])))
    assert link_is_open(new) and new["data"]["round"] == 1
    assert new["consent_at"] is not None
    rows = {r["survey_key"]: r for r in run(store.answers_for(new["id"]))}
    assert rows["finance"]["answers"] == {"q": 1}


def test_resend_reopens_expired_areas(surveys):
    crm, store = _sent(surveys)
    run(sending.expire(crm, store, engagement_id=ENG, round_no=1))
    for r in crm.records:
        r["status"] = "Expired"
    result = run(sending.resend(crm, store, engagement_id=ENG, round_no=1,
                                created_by="x", days=30))
    assert {c["status"]["to"] for c in result["changed"]} == {"Sent"}


def test_resend_is_refused_when_nothing_is_left_to_answer(surveys):
    crm, store = _sent(surveys)
    for r in crm.records:
        r["status"] = "Submitted"
    with pytest.raises(sending.SendError, match="Nothing in round 1"):
        run(sending.resend(crm, store, engagement_id=ENG, round_no=1, created_by="x", days=30))


def test_expire_ends_the_link_and_expires_only_open_records(surveys):
    crm, store = _sent(surveys)
    crm.records[0]["status"] = "Submitted"
    result = run(sending.expire(crm, store, engagement_id=ENG, round_no=1))
    assert result["linkEnded"] is True
    assert [u[2] for u in crm.updates] == [{"status": "Expired"}]
    assert crm.updates[0][1] == crm.records[1]["id"]
    assert not link_is_open(run(sending.links_for_engagement(store, ENG))[0])


def test_decline_sets_declined_on_what_is_not_submitted(surveys):
    crm, store = _sent(surveys)
    crm.records[0]["status"] = "Submitted"
    crm.records[1]["status"] = "In Progress"
    result = run(sending.decline(crm, store, engagement_id=ENG, round_no=1))
    assert [(u[1], u[2]) for u in crm.updates] == [(crm.records[1]["id"], {"status": "Declined"})]
    assert sending.status_fields(result["changed"]) == {
        "status": {"from": "In Progress", "to": "Declined"}}


def test_a_round_that_is_not_there_is_named(surveys):
    crm, store = _sent(surveys)
    with pytest.raises(sending.SendError, match="Round 7"):
        run(sending.expire(crm, store, engagement_id=ENG, round_no=7))


def test_round_routes_record_old_and_new_values(monkeypatch):
    recorded = []

    async def fake_record(client, **kw):
        recorded.append(kw)

    monkeypatch.setattr("core.action_log.record_action", fake_record)
    app, crm = _app(monkeypatch)
    base = f"/mentorsessions/api/records/{ENG}/evaluations"
    with TestClient(app) as c:
        assert c.post(f"{base}/send", json={"areas": ["finance"]}).status_code == 200
        r = c.post(f"{base}/rounds/1/resend")
        assert r.status_code == 200, r.text
        assert "/survey/" in r.json()["email"]["bodyHtml"]
        r = c.post(f"{base}/rounds/1/expire")
        assert r.status_code == 200 and r.json()["changed"] == 1
        crm.records[0]["status"] = "Expired"
        r = c.post(f"{base}/rounds/1/decline")
        assert r.status_code == 200 and r.json()["changed"] == 1
        assert c.post(f"{base}/rounds/9/expire").status_code == 400
    actions = [e["action"] for e in recorded]
    assert actions == ["Evaluation Sent", "Evaluation Resent", "Evaluation Expired",
                       "Evaluation Declined"]
    assert recorded[2]["details"]["fields"] == {"status": {"from": "Sent", "to": "Expired"}}
    assert recorded[3]["details"]["fields"] == {"status": {"from": "Expired", "to": "Declined"}}
    assert "evaluation link" in recorded[1]["details"]["fields"]


def test_switch_off_hides_the_round_routes(monkeypatch):
    app, _ = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        for act in ("resend", "expire", "decline"):
            assert c.post(f"/mentorsessions/api/records/{ENG}/evaluations/rounds/1/{act}").status_code == 404
