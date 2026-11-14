"""The Business Evaluation's public survey page, phase 1, on the survey engine
since phase 2b (surveys/router.py, surveys/service.py, evaluation/service.py):
the switch, the link states, consent, saving as the client goes, submit with
the CRM in dry run, the CRM-failure path and its retry, and no CRM id in
anything the page receives.

The application database is ``MemoryStore`` here, which keeps the contract of
``surveys/store.SurveyStore``; ``tests/test_survey_store_pg.py`` runs the real
one."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from core.espo import DryRunEspoClient, EspoError
from evaluation.purpose import PURPOSE, load_surveys
from forms import ALL_SPECS as SPECS
from surveys import answers as survey_answers
from surveys import service
from surveys.store import new_token
from tests.survey_fakes import MemoryStore

NOW = datetime.now(timezone.utc)


class RecordingClient(DryRunEspoClient):
    def __init__(self, fail=False):
        super().__init__()
        self.updates: list[tuple[str, str, dict]] = []
        self.fail = fail

    async def update(self, entity, record_id, payload):
        if self.fail:
            raise EspoError("update refused: HTTP 503")
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}


class NoCrm:
    """Any call fails the test: an invalid link must never reach the CRM."""

    def __getattr__(self, name):
        raise AssertionError(f"the CRM was called: {name}")


FINANCE_ID = "6612abcdef0123456"   # looks like a CRM id, so a leak would show
MARKETING_ID = "6612abcdef0999999"
PROFILE_ID = "6612cpcpcpcpcpcp1"

FINANCE_REQUIRED = {
    "bookkeeping_method": "A spreadsheet", "separate_account": "Yes",
    "review_frequency": "Every month", "accountant": "Yes, only for taxes", "confidence": 3,
    "top_customer_share": "Less than a tenth", "seasonality": "Yes, a little",
    "paid_when": "At the time of sale", "pricing_basis": "A mix of these",
    "biggest_costs": ["Wages", "Rent or a place to work"], "cash_runway": "1 to 3 months",
    "cash_shortfall": "Once or twice", "debt": ["No debt"], "owner_pay": "Not yet",
    "budget": "Only in my head",
}


@pytest.fixture
def world():
    """An app with the switch ON, a memory store and a recording CRM client."""
    get_settings.cache_clear()
    app = create_app(SPECS)
    store = MemoryStore()
    crm = RecordingClient()
    app.state.survey_store = store
    app.state.evaluation_client = lambda: crm
    apply_overrides({"business_evaluation": "true"})
    load_surveys()
    link = asyncio.run(store.create_link(
        purpose="business-evaluation", entity_type="CEngagement", record_id="ENG1",
        data={"client_profile_id": PROFILE_ID, "round": 1, "area_keys": ["finance", "marketing"],
              "profile_needed": True}, display_name="Quarry Street Coffee",
        created_by="test", days=30, surveys=[("business-profile", "business-profile.v1", None),
                                             ("finance", "finance.v1", FINANCE_ID),
                                             ("marketing", "marketing.v1", MARKETING_ID)]))
    yield TestClient(app), store, crm, link
    apply_overrides({})


def _consent(client, link):
    assert client.post(f"/api/survey/{link['token']}/consent",
                       json={"consent": True}).status_code == 200


# --- the switch ------------------------------------------------------------------

def test_switch_off_no_evaluation_address_answers_and_other_pages_stay():
    get_settings.cache_clear()
    apply_overrides({})
    client = TestClient(create_app(SPECS))
    token = new_token()
    assert client.get(f"/survey/{token}").status_code == 404
    assert client.get(f"/api/survey/{token}").status_code == 404
    assert client.post(f"/api/survey/{token}/consent", json={"consent": True}).status_code == 404
    assert client.get("/survey-assets/app.js").status_code == 404
    assert client.get("/client-intake/").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_switch_on_serves_the_assets(world):
    client, *_ = world
    assert client.get("/survey-assets/app.js").status_code == 200


# --- link states --------------------------------------------------------------------

@pytest.mark.parametrize("change", ["unknown", "expired", "replaced", "malformed"])
def test_a_link_no_longer_valid_shows_one_polite_page_and_never_calls_the_crm(world, change):
    client, store, _crm, link = world
    client.app.state.evaluation_client = lambda: NoCrm()
    token = link["token"]
    if change == "unknown":
        token = new_token()
    elif change == "malformed":
        token = "x'--"
    elif change == "expired":
        store.links[link["id"]]["expires_at"] = NOW - timedelta(minutes=1)
    else:
        store.links[link["id"]]["replaced_at"] = NOW
    page = client.get(f"/survey/{token}")
    assert page.status_code == 404
    assert "This link is no longer valid" in page.text and "contact your mentor" in page.text
    assert "Quarry" not in page.text
    api = client.get(f"/api/survey/{token}")
    assert api.status_code == 404 and api.json() == {"detail": "This link is no longer valid."}


def test_an_open_link_serves_the_page(world):
    client, _store, _crm, link = world
    page = client.get(f"/survey/{link['token']}")
    assert page.status_code == 200
    assert "Business Evaluation" in page.text and "{{org}}" not in page.text


def test_the_state_lists_the_profile_first_and_carries_no_crm_id(world):
    client, _store, _crm, link = world
    res = client.get(f"/api/survey/{link['token']}")
    body = res.json()
    assert body["displayName"] == "Quarry Street Coffee" and body["consentGiven"] is False
    assert [s["key"] for s in body["surveys"]] == ["business-profile", "finance", "marketing"]
    assert {s["state"] for s in body["surveys"]} == {"not_started"}
    for leak in (FINANCE_ID, MARKETING_ID, PROFILE_ID, "ENG1", link["id"]):
        assert leak not in res.text


def test_a_profile_already_answered_is_not_asked_again(world):
    client, store, _crm, link = world
    store.links[link["id"]]["data"]["profile_needed"] = False
    keys = [s["key"] for s in client.get(f"/api/survey/{link['token']}").json()["surveys"]]
    assert keys == ["finance", "marketing"]


# --- consent ---------------------------------------------------------------------------

def test_nothing_is_saved_or_submitted_before_consent(world):
    client, store, crm, link = world
    t = link["token"]
    assert client.put(f"/api/survey/{t}/answers/finance",
                      json={"answers": {"separate_account": "Yes"}}).status_code == 403
    assert client.post(f"/api/survey/{t}/submit/finance",
                       json={"answers": FINANCE_REQUIRED, "submission_token": "s1"}).status_code == 403
    assert client.post(f"/api/survey/{t}/consent", json={"consent": False}).status_code == 422
    assert crm.updates == []


def test_the_consent_honeypot_records_nothing(world):
    client, store, _crm, link = world
    res = client.post(f"/api/survey/{link['token']}/consent",
                      json={"consent": True, "company_url": "http://spam.example"})
    assert res.status_code == 200
    assert store.links[link["id"]]["consent_at"] is None


# --- saving as the client goes ---------------------------------------------------------

def test_saving_keeps_the_answers_and_marks_the_area_in_progress_once(world):
    client, store, crm, link = world
    _consent(client, link)
    t = link["token"]
    for _ in range(2):
        res = client.put(f"/api/survey/{t}/answers/finance",
                         json={"answers": {"separate_account": "Yes", "confidence": "4",
                                           "unknown_question": "x", "paid_when": "Never heard of it"}})
        assert res.status_code == 200 and res.json()["state"] == "in_progress"
    finance = next(s for s in client.get(f"/api/survey/{t}").json()["surveys"] if s["key"] == "finance")
    assert finance["state"] == "in_progress"
    # Unknown ids and values outside the options are not stored.
    assert finance["answers"] == {"separate_account": "Yes", "confidence": 4}
    assert crm.updates == [("CBusinessEvaluation", FINANCE_ID, {"status": "In Progress"})]


def test_a_survey_not_on_the_link_is_refused(world):
    client, _store, _crm, link = world
    _consent(client, link)
    assert client.put(f"/api/survey/{link['token']}/answers/funding",
                      json={"answers": {}}).status_code == 404


# --- submit --------------------------------------------------------------------------------

def test_submit_checks_required_answers_and_keeps_what_was_given(world):
    client, store, crm, link = world
    _consent(client, link)
    res = client.post(f"/api/survey/{link['token']}/submit/finance",
                      json={"answers": {"separate_account": "No"}, "submission_token": "s1"})
    assert res.status_code == 422
    assert "bookkeeping_method" in res.json()["errors"]
    assert "separate_account" not in res.json()["errors"]
    row = store._row(link["id"], "finance")
    assert row["answers"] == {"separate_account": "No"} and row["submitted_at"] is None
    assert crm.updates == []


def test_submit_writes_the_area_record_and_locks_the_survey(world):
    client, store, crm, link = world
    _consent(client, link)
    t = link["token"]
    res = client.post(f"/api/survey/{t}/submit/finance",
                      json={"answers": FINANCE_REQUIRED, "submission_token": "s1"})
    assert res.status_code == 200 and res.json() == {"state": "submitted", "delivered": True}
    [(entity, record_id, payload)] = crm.updates
    assert (entity, record_id) == ("CBusinessEvaluation", FINANCE_ID)
    assert payload["status"] == "Submitted" and payload["surveyVersion"] == "finance.v1"
    assert payload["consentAt"] and payload["submittedAt"]
    assert '"survey": "finance.v1"' in payload["answers"]
    assert "Does the business have its own bank account" in payload["answersReadable"]
    assert "Not answered" in payload["answersReadable"]      # the optional last question
    # Submitted: a repeat is the same answer, a save is refused, the state says so.
    again = client.post(f"/api/survey/{t}/submit/finance",
                        json={"answers": {}, "submission_token": "s2"})
    assert again.json() == {"state": "submitted", "delivered": True}
    assert len(crm.updates) == 1
    assert client.put(f"/api/survey/{t}/answers/finance",
                      json={"answers": {"budget": "No"}}).status_code == 409
    finance = next(s for s in client.get(f"/api/survey/{t}").json()["surveys"] if s["key"] == "finance")
    assert finance["state"] == "submitted" and finance["answers"]["budget"] == "Only in my head"


def test_the_business_profile_goes_to_the_client_profile(world):
    client, _store, crm, link = world
    _consent(client, link)
    survey = load_surveys()["business-profile.v1"]
    answers = {}
    for q in survey.questions.values():
        if q.required:
            answers[q.id] = (q.options[0] if q.type == "single_choice" else
                             [q.options[0]] if q.type == "multiple_choice" else
                             3 if q.type == "number" else "We roast coffee.")
    res = client.post(f"/api/survey/{link['token']}/submit/business-profile",
                      json={"answers": answers, "submission_token": "p1"})
    assert res.json()["delivered"] is True
    [(entity, record_id, payload)] = crm.updates
    assert (entity, record_id) == ("CClientProfile", PROFILE_ID)
    assert set(payload) == {"evaluationProfile", "evaluationProfileAt"}


def test_the_submit_honeypot_writes_nothing(world):
    client, store, crm, link = world
    _consent(client, link)
    res = client.post(f"/api/survey/{link['token']}/submit/finance",
                      json={"answers": FINANCE_REQUIRED, "submission_token": "s1",
                            "company_url": "spam"})
    assert res.json()["state"] == "submitted"
    assert crm.updates == [] and store._row(link["id"], "finance")["submitted_at"] is None


def test_submit_works_against_the_dry_run_client(world):
    client, _store, _crm, link = world
    client.app.state.evaluation_client = lambda: DryRunEspoClient()
    _consent(client, link)
    res = client.post(f"/api/survey/{link['token']}/submit/finance",
                      json={"answers": FINANCE_REQUIRED, "submission_token": "s1"})
    assert res.json() == {"state": "submitted", "delivered": True}


# --- the CRM refuses -------------------------------------------------------------------------

def test_a_crm_failure_keeps_the_answers_and_the_worker_retries(world):
    client, store, crm, link = world
    crm.fail = True
    _consent(client, link)
    res = client.post(f"/api/survey/{link['token']}/submit/finance",
                      json={"answers": FINANCE_REQUIRED, "submission_token": "s1"})
    assert res.status_code == 200 and res.json() == {"state": "submitted", "delivered": False}
    row = store._row(link["id"], "finance")
    assert row["submitted_at"] and not row["delivered_at"]
    assert "503" in row["delivery_error"] and row["attempts"] == 1
    assert row["next_attempt_at"] > datetime.now(timezone.utc)

    # Not due yet: nothing happens.
    assert asyncio.run(service.run_retry_cycle(store, PURPOSE, crm, load_surveys())) == {"written": 0, "refused": 0}
    # Due, and the CRM is back.
    row["next_attempt_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    crm.fail = False
    assert asyncio.run(service.run_retry_cycle(store, PURPOSE, crm, load_surveys())) == {"written": 1, "refused": 0}
    assert store._row(link["id"], "finance")["delivered_at"]
    assert crm.updates[0][2]["status"] == "Submitted"


def test_the_retry_backs_off():
    at = datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert service.next_retry(0, at) == at + timedelta(minutes=1)
    assert service.next_retry(3, at) == at + timedelta(hours=2)
    assert service.next_retry(40, at) == at + timedelta(hours=6)


# --- answers ---------------------------------------------------------------------------------

def test_values_are_checked_by_question_type():
    survey = load_surveys()["finance.v1"]
    kept, errors = survey_answers.clean_answers(survey, {
        "confidence": 9, "biggest_costs": ["Wages", "Insurance", "Not sure", "Rent or a place to work"],
        "separate_account": "Maybe", "finance_worry": "  cash  ",
    })
    assert kept == {"finance_worry": "cash"}
    assert set(errors) == {"confidence", "biggest_costs", "separate_account"}
    assert "no more than 3" in errors["biggest_costs"]


def test_money_and_numbers_read_as_people_type_them():
    survey = load_surveys()["business-profile.v1"]
    kept, errors = survey_answers.clean_answers(survey, {"people": "1,200"})
    assert kept == {"people": 1200} and not errors
    _, errors = survey_answers.clean_answers(survey, {"people": "about ten"})
    assert errors == {"people": "Please enter a number."}


def test_the_readable_text_escapes_what_the_client_typed():
    survey = load_surveys()["marketing.v1"]
    html = survey_answers.readable_html(survey, {"ideal_customer": "<script>x</script>"})
    assert "<script>" not in html and "&lt;script&gt;" in html
