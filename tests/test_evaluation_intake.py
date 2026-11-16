"""Business Evaluation phase 6, the intake survey (evaluation/intake.py;
rulings BE24 to BE27): the email when a client intake is delivered, the
"more details?" offer and the area picker on the survey page, Client
Administration's Business profile tab, Assign moving the records, and the
analysis held while the engagement has no mentor.

The application database is ``tests/survey_fakes.MemoryStore``."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from core.espo import EspoError
from core.forms import run_after_delivery
from evaluation import analysis, intake, service
from evaluation.purpose import load_surveys
from forms import ALL_SPECS as SPECS
from forms import client_intake, info_request
from tests.survey_fakes import MemoryStore

ENG = "6612engagement001"
PROFILE = "6612clientprof001"
NOW = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
DRAFT = "<p>SECRET DRAFT TEXT</p>"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _surveys():
    assert load_surveys(), "the survey definitions must load"


def _settings(**kw):
    base = dict(intake_survey=True, business_evaluation=True, ops_mailbox="info@example.org",
                evaluation_link_days=30, organization_name="Cleveland Business Mentors",
                app_base_url="https://apps.example.org", evaluation_analyze_unassigned=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _sub(**kw):
    base = dict(email="dana@example.com", first_name="Dana", business_name="Brightline Bakehouse")
    base.update(kw)
    return SimpleNamespace(**base)


IDS = {"engagementId": ENG, "clientProfileId": PROFILE, "accountId": "a1", "contactId": "c1"}


class Crm:
    """Enough of the CRM for the intake survey, the offer, the tab and Assign."""

    def __init__(self, *, has_entity=True, profile="", mentor=None, records=None,
                 assigned=None):
        self.has_entity = has_entity
        self.profile = {"id": PROFILE, "name": "Brightline Bakehouse",
                        "linkedCompanyName": "Brightline Bakehouse",
                        "evaluationProfile": profile, "evaluationProfileAt": "2026-11-16 14:00:00"}
        self.mentor = mentor
        self.assigned = list(assigned or [])
        self.records = list(records or [])
        self.creates: list[dict] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.calls = 0

    async def metadata(self, key):
        self.calls += 1
        if key == f"entityDefs.{service.ENTITY}":
            return {"fields": {"status": {}}} if self.has_entity else None
        return None

    async def get(self, entity, record_id, select=None):
        self.calls += 1
        if entity == "CEngagement":
            return {"id": record_id, "engagementClientId": PROFILE, "mentorProfileId": self.mentor,
                    "assignedUsersIds": list(self.assigned)}
        if entity == service.CLIENT_PROFILE:
            return dict(self.profile)
        if entity == "CMentorProfile":
            return {"id": record_id, "cbmEmail": "joe.mentor@example.org"}
        raise EspoError(f"get {entity}/{record_id}: HTTP 404")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        self.calls += 1
        assert max_size <= 200
        rows = [r for r in self.records if r.get("engagementId") == where[0]["value"]]
        return {"total": len(rows), "list": [dict(r) for r in rows[offset:offset + max_size]]}

    async def create(self, entity, payload):
        self.calls += 1
        rec = {"id": f"be{len(self.records) + 1:015d}", **payload}
        self.records.append(rec)
        self.creates.append(payload)
        return rec

    async def update(self, entity, record_id, payload):
        self.calls += 1
        self.updates.append((entity, record_id, payload))
        for r in self.records:
            if r["id"] == record_id:
                r.update(payload)
        return {"id": record_id, **payload}


class Outbox:
    def __init__(self, fail=False):
        self.sent: list[tuple[str, str, str]] = []
        self.fail = fail

    async def __call__(self, settings, to, subject, body):
        if self.fail:
            raise RuntimeError("Gmail refused the send")
        self.sent.append((to, subject, body))


def _deliver(settings, crm, store, outbox, sub=None):
    return run(intake.on_delivered(settings, sub or _sub(), IDS, crm, store=store,
                                   send=outbox, now=NOW))


# --- the email when an intake is delivered (BE24) -----------------------------------

def test_switch_off_sends_nothing_and_touches_nothing():
    for settings in (_settings(intake_survey=False), _settings(business_evaluation=False)):
        crm, store, outbox = Crm(), MemoryStore(), Outbox()
        assert _deliver(settings, crm, store, outbox) == "off"
        assert outbox.sent == [] and store.links == {} and crm.calls == 0


def test_the_intake_email_carries_a_profile_only_link_from_the_shared_mailbox():
    crm, store, outbox = Crm(), MemoryStore(), Outbox()
    assert _deliver(_settings(), crm, store, outbox) == "sent"
    [link] = store.links.values()
    assert link["record_id"] == ENG and link["purpose"] == service.PURPOSE
    assert link["data"] == {"client_profile_id": PROFILE, "round": 1, "area_keys": [],
                            "profile_needed": True, "intake": True}
    assert [r["survey_key"] for r in store.rows.values()] == ["business-profile"]
    [(to, subject, body)] = outbox.sent
    assert to == "dana@example.com"
    assert subject == "While you wait: tell us about your business"
    assert f"https://apps.example.org/survey/{link['token']}" in body
    assert "Hi Dana," in body and "December 16, 2026" in body
    assert crm.creates == []   # no Business Evaluation record until the client picks


def test_the_link_is_made_once_per_engagement():
    crm, store, outbox = Crm(), MemoryStore(), Outbox()
    assert _deliver(_settings(), crm, store, outbox) == "sent"
    assert _deliver(_settings(), crm, store, outbox) == "already"
    assert len(store.links) == 1 and len(outbox.sent) == 1


def test_a_failed_send_never_fails_the_intake():
    crm, store = Crm(), MemoryStore()
    assert _deliver(_settings(), crm, store, Outbox(fail=True)) == "failed"
    # And a re-driven delivery still sends no second link.
    outbox = Outbox()
    assert _deliver(_settings(), crm, store, outbox) == "already" and outbox.sent == []


def test_the_after_delivery_step_never_raises(monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("anything at all")
    monkeypatch.setattr("evaluation.intake.on_delivered", boom)
    assert client_intake.SPEC.after_delivery is not None
    run(run_after_delivery(client_intake.SPEC, _settings(), _sub(), IDS, Crm()))
    # A form without the step is untouched.
    run(run_after_delivery(info_request.SPEC, _settings(), _sub(), IDS, Crm()))


def test_no_email_when_the_profile_is_on_file_or_there_is_no_mailbox_or_entity():
    on_file = json.dumps({"survey": "business-profile.v1", "answers": {}})
    cases = [(_settings(), Crm(profile=on_file), "profile-on-file"),
             (_settings(ops_mailbox=""), Crm(), "no-mailbox"),
             (_settings(), Crm(has_entity=False), "no-entity")]
    for settings, crm, outcome in cases:
        store, outbox = MemoryStore(), Outbox()
        assert _deliver(settings, crm, store, outbox) == outcome
        assert outbox.sent == [] and store.links == {}


# --- the survey page: "more details?" and the area picker (BE25) ---------------------

@pytest.fixture
def page():
    get_settings.cache_clear()
    app = create_app(SPECS)
    store, crm = MemoryStore(), Crm()
    app.state.survey_store = store
    app.state.evaluation_client = lambda: crm
    apply_overrides({"business_evaluation": "true", "intake_survey": "true"})
    load_surveys()
    _deliver(_settings(), crm, store, Outbox())
    [link] = store.links.values()
    yield TestClient(app), store, crm, link
    apply_overrides({})


def _profile_answers():
    survey = load_surveys()["business-profile.v1"]
    answers = {}
    for q in survey.questions.values():
        if q.required:
            answers[q.id] = (q.options[0] if q.type == "single_choice" else
                             [q.options[0]] if q.type == "multiple_choice" else
                             3 if q.type == "number" else "We bake bread.")
    return answers


def _consent_and_profile(client, link):
    api = f"/api/survey/{link['token']}"
    assert client.post(api + "/consent", json={"consent": True}).status_code == 200
    assert client.get(api).json()["offer"] is None   # not before the profile is in
    res = client.post(api + "/submit/business-profile",
                      json={"answers": _profile_answers(), "submission_token": "p1"})
    assert res.json()["delivered"] is True
    return api


def test_an_intake_link_speaks_for_the_organization_not_a_mentor(page):
    client, _store, _crm, link = page
    html = client.get(f"/survey/{link['token']}").text
    assert "Tell us about your business" in html
    assert "While we find the right person for" in html
    assert "Your mentor has offered you" not in html


def test_after_the_profile_the_page_asks_for_more_details(page):
    client, _store, _crm, link = page
    api = _consent_and_profile(client, link)
    offer = client.get(api).json()["offer"]
    assert offer["state"] == "ask"
    assert offer["text"]["question"] == "Thank you. Do you have time to provide more details?"
    keys = [c["key"] for c in offer["choices"]]
    assert "finance" in keys and "marketing" in keys and "business-profile" not in keys
    assert offer["adviseMax"] == 3


def test_no_ends_the_survey_and_can_be_changed(page):
    client, store, crm, link = page
    api = _consent_and_profile(client, link)
    res = client.post(api + "/offer", json={"accept": False})
    assert res.status_code == 200 and res.json()["offer"]["state"] == "declined"
    assert store.links[link["id"]]["data"]["details"] == "declined" and crm.creates == []
    # Doug's choice A: a no can still become a yes.
    res = client.post(api + "/offer", json={"accept": True, "keys": ["finance"]})
    assert res.status_code == 200 and res.json()["offer"] is None


def test_yes_creates_one_record_per_area_on_the_same_link(page):
    client, store, crm, link = page
    api = _consent_and_profile(client, link)
    res = client.post(api + "/offer", json={"accept": True, "keys": ["finance", "marketing"]})
    assert res.status_code == 200
    body = res.json()
    assert body["offer"] is None
    assert [s["key"] for s in body["surveys"]] == ["business-profile", "finance", "marketing"]
    assert [(c["evaluationArea"], c["evaluationRound"], c["status"]) for c in crm.creates] == [
        ("Finance", 1, "Sent"), ("Marketing", 1, "Sent")]
    assert all(c["engagementId"] == ENG and c["clientProfileId"] == PROFILE for c in crm.creates)
    rows = {r["survey_key"]: r["crm_record_id"] for r in store.rows.values()}
    assert rows["finance"] == crm.records[0]["id"] and rows["marketing"] == crm.records[1]["id"]
    # Answered once, never offered again.
    again = client.post(api + "/offer", json={"accept": True, "keys": ["finance"]})
    assert again.status_code == 409 and len(crm.creates) == 2


def test_yes_with_nothing_ticked_is_refused_with_the_words(page):
    client, _store, crm, link = page
    api = _consent_and_profile(client, link)
    res = client.post(api + "/offer", json={"accept": True, "keys": []})
    assert res.status_code == 422
    assert res.json()["detail"] == "Tick at least one area, or choose No, that's all for now."
    assert crm.creates == []


def test_a_repeated_yes_reuses_the_records_already_made():
    crm, store = Crm(), MemoryStore()
    _deliver(_settings(), crm, store, Outbox())
    [link] = store.links.values()
    from surveys.registry import OfferContext
    ctx = OfferContext(link=link, store=store, client=crm, accept=True, keys=["finance"])
    run(intake.answer_offer(ctx))
    run(intake.answer_offer(ctx))   # a press repeated before the page refreshed
    assert len(crm.creates) == 1


def test_a_mentor_link_is_unchanged():
    link = {"data": {"client_profile_id": PROFILE, "round": 1, "area_keys": ["finance"],
                     "profile_needed": True}}
    assert intake.page_for(link) is None and intake.offer(link) is None


# --- Client Administration's Business profile tab (BE26) ------------------------------

def _answered_profile():
    return json.dumps({"survey": "business-profile.v1",
                       "answers": {"what_you_sell": "Bread to cafés"}})


def test_the_tab_shows_the_answers_and_the_areas_and_never_a_report():
    records = [{"id": "be1", "engagementId": ENG, "evaluationArea": "Finance",
                "evaluationRound": 1, "status": "Draft Ready", "draftReport": DRAFT,
                "reviewedReport": DRAFT, "answersReadable": "<p>private</p>"}]
    crm = Crm(profile=_answered_profile(), records=records)
    view = run(intake.business_profile_view(crm, crm, None, ENG))
    assert "Bread to cafés" in view["profileHtml"]
    assert view["areas"] == [{"area": "Finance", "round": 1, "status": "Draft Ready"}]
    assert "SECRET DRAFT" not in json.dumps(view) and "private" not in json.dumps(view)


def test_the_tab_says_when_nothing_is_answered_or_the_client_said_no():
    crm, store = Crm(), MemoryStore()
    _deliver(_settings(), crm, store, Outbox())
    [link] = store.links.values()
    from surveys.registry import OfferContext
    run(intake.answer_offer(OfferContext(link=link, store=store, client=crm, accept=False,
                                         keys=[])))
    view = run(intake.business_profile_view(crm, crm, store, ENG))
    assert view["profileHtml"] is None
    assert view["profileNote"] == "The client has not answered the business profile yet."
    assert view["areas"] == [] and view["declined"] is True


_STAFF = {"userId": "u1", "userName": "staff", "name": "Jane Staff", "isAdmin": False,
          "token": "tok", "teams": ["Client Administration Team"]}


def _assign_app(monkeypatch, crm, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("assignments.auth.current_user", lambda request: _STAFF)
    monkeypatch.setattr("assignments.router.client_for", lambda settings, user: crm)
    app = create_app([info_request.SPEC])
    app.state.evaluation_client = lambda: crm
    return app


def test_the_tab_is_dark_while_the_switch_is_off(monkeypatch):
    crm = Crm(profile=_answered_profile())
    with TestClient(_assign_app(monkeypatch, crm, BUSINESS_EVALUATION="true")) as c:
        assert c.get("/assignments/api/session").json()["businessProfileEnabled"] is False
        assert c.get(f"/assignments/api/engagements/{ENG}/business-profile").status_code == 404
    get_settings.cache_clear()
    with TestClient(_assign_app(monkeypatch, crm, BUSINESS_EVALUATION="true",
                                INTAKE_SURVEY="true")) as c:
        assert c.get("/assignments/api/session").json()["businessProfileEnabled"] is True
        res = c.get(f"/assignments/api/engagements/{ENG}/business-profile")
        assert res.status_code == 200 and "Bread to cafés" in res.json()["profileHtml"]
    get_settings.cache_clear()


def test_the_tab_never_names_a_report_field():
    """BE17: the tab's code reads area, round and status only."""
    from pathlib import Path
    src = Path(intake.__file__).read_text()
    assert "draftReport" not in src and "reviewedReport" not in src


# --- Assign moves the records (BE26) and the analysis hold (BE27) --------------------

def test_assign_moves_the_records_and_tells_the_mentor_of_a_waiting_draft():
    records = [{"id": "be1", "engagementId": ENG, "evaluationArea": "Finance",
                "status": "Draft Ready", "assignedUsersIds": []},
               {"id": "be2", "engagementId": ENG, "evaluationArea": "Marketing",
                "status": "Submitted", "assignedUsersIds": ["u-other"]}]
    crm = Crm(records=records, assigned=["u-joe", "u-comentor"], mentor="mp1")
    told = []

    async def notify(rec):
        told.append(rec["id"])
    counts = run(intake.after_assign(_settings(), crm, ENG, first=True, notify=notify))
    assert counts == {"moved": 2, "told": 1, "errors": 0}
    assert crm.records[0]["assignedUsersIds"] == ["u-joe", "u-comentor"]
    assert crm.records[1]["assignedUsersIds"] == ["u-other", "u-joe", "u-comentor"]
    assert told == ["be1"]
    # A repair or a reassign moves, and never tells again.
    told.clear()
    run(intake.after_assign(_settings(), crm, ENG, first=False, notify=notify))
    assert told == []


def test_assign_with_the_switch_off_touches_nothing():
    crm = Crm(records=[{"id": "be1", "engagementId": ENG, "status": "Draft Ready"}])
    assert run(intake.after_assign(_settings(business_evaluation=False), crm, ENG,
                                   first=True)) == {"moved": 0, "told": 0, "errors": 0}
    assert crm.calls == 0


class Claude:
    def __init__(self):
        self.calls = 0


def _submitted():
    return [{"id": "be1", "engagementId": ENG, "evaluationArea": "Finance", "status": "Submitted",
             "clientProfileId": PROFILE, "answers": "{}", "submittedAt": "2026-11-16 14:00:00"}]


def test_the_analysis_waits_for_a_mentor_while_the_setting_is_off(monkeypatch):
    analyzed = []

    async def fake_analyze(rec, **kw):
        analyzed.append(rec["id"])
        return analysis.STATUS_DRAFT_READY

    async def fake_submitted(crm):
        return _submitted()
    monkeypatch.setattr(analysis, "analyze_record", fake_analyze)
    monkeypatch.setattr(analysis, "submitted_records", fake_submitted)
    monkeypatch.setattr(analysis, "load_all", lambda: ({}, {}))
    crm = Crm(mentor=None)
    counts = run(analysis.run_analysis_cycle(_settings(), crm, Claude(), surveys={}))
    assert counts["unassigned"] == 1 and analyzed == []
    # Assigned: it runs.
    crm.mentor = "mp1"
    counts = run(analysis.run_analysis_cycle(_settings(), crm, Claude(), surveys={}))
    assert counts["ready"] == 1 and analyzed == ["be1"]


def test_the_analysis_runs_before_assignment_when_the_setting_is_on(monkeypatch):
    analyzed = []

    async def fake_analyze(rec, **kw):
        analyzed.append(rec["id"])
        return analysis.STATUS_DRAFT_READY

    async def fake_submitted(crm):
        return _submitted()
    monkeypatch.setattr(analysis, "analyze_record", fake_analyze)
    monkeypatch.setattr(analysis, "submitted_records", fake_submitted)
    monkeypatch.setattr(analysis, "load_all", lambda: ({}, {}))
    counts = run(analysis.run_analysis_cycle(_settings(evaluation_analyze_unassigned=True),
                                             Crm(mentor=None), Claude(), surveys={}))
    assert counts["ready"] == 1 and counts["unassigned"] == 0 and analyzed == ["be1"]
