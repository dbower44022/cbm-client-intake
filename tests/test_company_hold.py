"""The company-website hold on the public forms (prds/company-website-hold-plan.md).

A submission naming a company that already exists at a DIFFERENT web address
is held for staff — never refused (the submitter is an anonymous visitor),
never merged (one business would land on another's record). Staff resolve it
in Submission Admin as "same company" or "different company"; both re-queue.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import worker
from core import receipts
from core.app import create_app
from core.config import Settings, get_settings
from core.crm_upsert import (
    CompanyConflict, conflicting_website, fill_company_website,
)
from core.espo import EspoError
from core.store import Claimed
from forms import info_request
from forms.client_intake.orchestrator import ACCOUNT as CI_ACCOUNT, submit_intake
from forms.client_intake.schemas import IntakeSubmission
from forms.partner.orchestrator import submit_partner
from forms.partner.schemas import PartnerApplication
from forms.sponsor.orchestrator import submit_sponsor
from forms.sponsor.schemas import SponsorApplication


# --- the helpers --------------------------------------------------------------

def test_conflicting_website_is_none_without_both_sides():
    assert conflicting_website({"id": "A", "website": "https://acme.com"}, "") is None
    assert conflicting_website({"id": "A", "website": "https://acme.com"}, None) is None
    assert conflicting_website({"id": "A"}, "acme.com") is None


def test_conflicting_website_is_none_for_one_site_in_two_forms():
    assert conflicting_website({"id": "A", "website": "https://www.acme.com/"}, "ACME.com") is None


def test_conflicting_website_returns_the_stored_address_on_a_real_difference():
    stored = "https://acme-ohio.com"
    assert conflicting_website({"id": "A", "website": stored}, "acme.com") == stored


class _Client:
    def __init__(self, existing=None, refuse_update=False):
        self.existing = existing
        self.refuse_update = refuse_update
        self.creates, self.updates, self.relates = [], [], []
        self._n = 0

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == "Account" and self.existing:
            return dict(self.existing)
        if entity == "Team":
            return None
        return None

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def update(self, entity, record_id, payload):
        if self.refuse_update:
            raise EspoError("HTTP 403: Access denied to Account")
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}

    async def metadata_enum_options(self, entity, field):
        return None

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))

    async def get(self, entity, record_id, select=None):
        return {"id": record_id}


@pytest.mark.asyncio
async def test_fill_company_website_writes_only_when_empty():
    c = _Client()
    assert await fill_company_website(c, {"id": "A", "website": "https://x.com"}, "https://y.com") is False
    assert await fill_company_website(c, {"id": "A"}, "https://y.com") is True
    assert c.updates == [("Account", "A", {"website": "https://y.com"})]


@pytest.mark.asyncio
async def test_fill_company_website_is_best_effort():
    assert await fill_company_website(_Client(refuse_update=True), {"id": "A"}, "https://y.com") is False


# --- the three orchestrators --------------------------------------------------

def _partner(**over):
    base = dict(company="Acme Supply", first_name="Pat", last_name="Lee",
                email="pat@acme.com", terms_accepted=True, submission_token="tok-partner-01",
                business_website="https://acme.com")
    base.update(over)
    return PartnerApplication(**base)


def _sponsor(**over):
    base = dict(company="Acme Supply", first_name="Sam", last_name="Lee",
                email="sam@acme.com", terms_accepted=True, submission_token="tok-sponsor-01",
                message="We would like to fund a cohort.", business_website="https://acme.com")
    base.update(over)
    return SponsorApplication(**base)


_EXISTING = {"id": "A-OLD", "cCompanyType": ["Sponsor"], "website": "https://acme-ohio.com"}


@pytest.mark.asyncio
async def test_partner_form_holds_a_same_name_at_a_different_website():
    client = _Client(existing=_EXISTING)
    with pytest.raises(CompanyConflict) as excinfo:
        await submit_partner(_partner(), client)
    exc = excinfo.value
    assert (exc.name, exc.existing_id, exc.existing_website) == ("Acme Supply", "A-OLD", "https://acme-ohio.com")
    assert exc.submitted_website == "https://acme.com"
    assert client.creates == [] and client.updates == []   # nothing written


@pytest.mark.asyncio
async def test_partner_form_reuses_a_same_name_at_the_same_website():
    client = _Client(existing={**_EXISTING, "website": "http://www.acme.com/"})
    ids = await submit_partner(_partner(), client)
    assert ids["accountId"] == "A-OLD"
    # Only the type merge is written — the website agrees.
    assert client.updates == [("Account", "A-OLD", {"cCompanyType": ["Sponsor", "Partner"]})]


@pytest.mark.asyncio
async def test_partner_form_fills_a_missing_website_on_the_match():
    client = _Client(existing={"id": "A-OLD", "cCompanyType": ["Partner"]})
    await submit_partner(_partner(), client)
    assert client.updates == [("Account", "A-OLD", {"website": "https://acme.com"})]


@pytest.mark.asyncio
async def test_partner_form_without_a_website_matches_by_name_as_before():
    client = _Client(existing=_EXISTING)
    ids = await submit_partner(_partner(business_website=None), client)
    assert ids["accountId"] == "A-OLD"


@pytest.mark.asyncio
async def test_sponsor_form_holds_a_same_name_at_a_different_website():
    client = _Client(existing={**_EXISTING, "cCompanyType": ["Partner"]})
    with pytest.raises(CompanyConflict):
        await submit_sponsor(_sponsor(), client)
    assert client.creates == [] and client.updates == []


def _intake(**over):
    base = dict(first_name="Ada", last_name="Lovelace", email="ada@example.com",
                confirm_email="ada@example.com", phone="216-555-0100", zip_code="44121",
                mentoring_focus_areas=["Retail"], mentoring_needs_description="Pricing help.",
                business_name="Acme Supply", business_website="https://acme.com",
                business_stage="Startup", terms_accepted=True,
                submission_token="tok-intake-001")
    base.update(over)
    return IntakeSubmission(**base)


@pytest.mark.asyncio
async def test_client_intake_holds_a_same_name_at_a_different_website():
    """The case that matters most: a wrong match here would also hand the
    client another business's client profile and engagement."""
    client = _Client(existing=_EXISTING)
    with pytest.raises(CompanyConflict):
        await submit_intake(_intake(), client)
    assert client.creates == [] and client.updates == []


@pytest.mark.asyncio
async def test_client_intake_pre_startup_never_conflicts():
    """A pre-startup submission collects no business profile, so its placeholder
    company can never be the one at a different address."""
    client = _Client(existing=_EXISTING)
    ids = await submit_intake(_intake(business_stage="Pre-Startup", business_name=None), client)
    assert ids["accountId"] == "A-OLD"
    assert CI_ACCOUNT not in [e for e, _ in client.creates]


# --- the worker: hold, and the override merge ---------------------------------

class _Store:
    def __init__(self):
        self.failed, self.completed, self.retried = [], [], []
        self.progress = {}

    async def save_progress(self, sid, progress):
        self.progress[sid] = progress

    async def mark_completed(self, sid, result, *, auto_close_reason=None):
        self.completed.append((sid, result))

    async def mark_retry(self, sid, **kw):
        self.retried.append(sid)

    async def mark_failed(self, sid, *, status, error):
        self.failed.append((sid, status, error))


def _claimed(payload, overrides=None):
    return Claimed(id="sub-1", form_slug="partner", submission_token="tok-partner-01",
                   payload=payload, progress=None, attempt_count=0, overrides=overrides)


_PAYLOAD = {"company": "Acme Supply", "first_name": "Pat", "last_name": "Lee",
            "email": "pat@acme.com", "terms_accepted": True, "submission_token": "tok-partner-01",
            "business_website": "https://acme.com"}


@pytest.mark.asyncio
async def test_worker_holds_a_company_conflict_instead_of_failing(monkeypatch):
    monkeypatch.setattr(worker, "_client", lambda s: _Client(existing=_EXISTING))
    store = _Store()
    await worker.process_one(store, Settings(espo_dry_run=True), _claimed(_PAYLOAD))
    assert store.completed == [] and store.retried == []
    [(sid, status, why)] = store.failed
    assert (sid, status) == ("sub-1", "held_company")
    assert "https://acme-ohio.com" in why and "Acme Supply" in why


@pytest.mark.asyncio
async def test_worker_same_company_override_reuses_the_company(monkeypatch):
    """"Same company": the submitted website is blanked by the override, so the
    name match reuses the company on file and its website stands."""
    crm = _Client(existing=_EXISTING)
    monkeypatch.setattr(worker, "_client", lambda s: crm)
    store = _Store()
    await worker.process_one(
        store, Settings(espo_dry_run=True), _claimed(_PAYLOAD, {"business_website": None})
    )
    [(sid, result)] = store.completed
    assert result["accountId"] == "A-OLD" and store.failed == []
    assert ("Account", {"name": "Acme Supply"}) not in [(e, {"name": p.get("name")}) for e, p in crm.creates]


@pytest.mark.asyncio
async def test_worker_different_company_override_creates_under_the_new_name(monkeypatch):
    crm = _Client(existing=None)   # the qualified name matches nothing
    monkeypatch.setattr(worker, "_client", lambda s: crm)
    store = _Store()
    await worker.process_one(
        store, Settings(espo_dry_run=True), _claimed(_PAYLOAD, {"company": "Acme Supply (Ohio)"})
    )
    [(sid, result)] = store.completed
    account = next(p for e, p in crm.creates if e == "Account")
    assert account["name"] == "Acme Supply (Ohio)"
    assert store.failed == []


# --- the receipt ---------------------------------------------------------------

def test_receipt_vocabulary_and_message():
    assert receipts.receipt_status("held_company") == "Held-Company"
    msg = receipts.intake_message({
        "status": "held_company", "form_slug": "partner",
        "last_error": "A company named Acme Supply already exists (Account/A-OLD) with the "
                      "website https://acme-ohio.com; this submission gave https://acme.com.",
    })
    assert "Same company" in msg and "Different company" in msg and "acme-ohio.com" in msg


class _StatusEnum:
    def __init__(self, options):
        self.options = options

    async def metadata_enum_options(self, entity, field):
        return self.options if field == "intakeStatus" else None


@pytest.mark.asyncio
async def test_receipt_status_falls_back_to_received_until_the_crm_has_the_option():
    receipts._status_options_cache["options"] = None
    six = ["Received", "Completed", "Held-Spam", "Held-Email", "Error", "Discarded"]
    out = await receipts._gate_status(_StatusEnum(six), {"intakeStatus": "Held-Company"})
    assert out["intakeStatus"] == "Received"
    receipts._status_options_cache["options"] = None
    out = await receipts._gate_status(_StatusEnum(six + ["Held-Company"]), {"intakeStatus": "Held-Company"})
    assert out["intakeStatus"] == "Held-Company"
    receipts._status_options_cache["options"] = None


# --- Submission Admin: the resolution endpoint ---------------------------------

_USER = {"userName": "staffer", "name": "Staff Person", "isAdmin": True,
         "teams": ["Marketing Admin Team"], "roles": [], "token": "t", "userId": "u1"}


class _OpsStore:
    def __init__(self, status="held_company", slug="partner"):
        self.rows = {"held1": {
            "id": "held1", "form_slug": slug, "status": status,
            "payload": {"company": "Acme Supply", "business_website": "https://acme.com",
                        "business_name": "Acme Supply", "email": "pat@acme.com"},
            "last_error": "conflict", "progress": None, "result": None, "thread_ids": None,
        }}
        self.overrides, self.redriven, self.activity = [], [], []

    async def get_submission(self, sid):
        return self.rows.get(sid)

    async def set_delivery_overrides(self, sid, overrides, *, acted_by=None):
        row = self.rows.get(sid)
        if row is None or row["status"] != "held_company":
            return False
        self.overrides.append((sid, overrides, acted_by))
        return True

    async def redrive(self, sid, *, acted_by=None):
        self.redriven.append((sid, acted_by))
        return True

    async def add_activity(self, sid, **kw):
        self.activity.append((sid, kw))


def _app(monkeypatch, store):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    monkeypatch.setattr("ops.router.current_user", lambda request: _USER)
    monkeypatch.setattr("ops.router._api_client", lambda: None)
    app = create_app([info_request.SPEC])
    app.state.submission_store = store
    return app


def _post(monkeypatch, store, body, sid="held1"):
    with TestClient(_app(monkeypatch, store)) as c:
        return c.post(f"/ops/api/submissions/{sid}/company", json=body)


def test_same_company_blanks_the_submitted_website_and_requeues(monkeypatch):
    store = _OpsStore()
    r = _post(monkeypatch, store, {"decision": "same"})
    assert r.status_code == 200 and r.json()["status"] == "requeued"
    assert store.overrides == [("held1", {"business_website": None}, "staffer")]
    assert store.redriven == [("held1", "staffer")]
    assert "same company" in store.activity[0][1]["summary"]


def test_different_company_replaces_the_name_and_requeues(monkeypatch):
    store = _OpsStore()
    r = _post(monkeypatch, store, {"decision": "different", "name": "Acme Supply (Ohio)"})
    assert r.status_code == 200
    assert store.overrides == [("held1", {"company": "Acme Supply (Ohio)"}, "staffer")]
    assert store.redriven == [("held1", "staffer")]


def test_different_company_uses_the_form_s_own_name_key(monkeypatch):
    store = _OpsStore(slug="client-intake")
    r = _post(monkeypatch, store, {"decision": "different", "name": "Acme Supply (Ohio)"})
    assert r.status_code == 200
    assert store.overrides[0][1] == {"business_name": "Acme Supply (Ohio)"}


def test_different_company_needs_a_distinguishing_name(monkeypatch):
    store = _OpsStore()
    assert _post(monkeypatch, store, {"decision": "different", "name": "  "}).status_code == 422
    assert _post(monkeypatch, store, {"decision": "different", "name": "acme supply"}).status_code == 422
    assert store.overrides == [] and store.redriven == []


def test_resolution_refuses_a_row_that_is_not_held(monkeypatch):
    store = _OpsStore(status="needs_attention")
    r = _post(monkeypatch, store, {"decision": "same"})
    assert r.status_code == 409 and store.redriven == []


def test_resolution_refuses_an_unknown_decision(monkeypatch):
    assert _post(monkeypatch, _OpsStore(), {"decision": "maybe"}).status_code == 422
