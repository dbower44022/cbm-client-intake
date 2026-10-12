"""A partner's client intake link (2026-10-12): ``?partner=<CPartnerProfile id>``
on the form's launch URL credits that partner as the engagement's referring
partner. Link form ruled "the CRM id" (Doug, 10-12-26).

Rules under test:
- a real partner id is written to ``referringPartnerId`` with a notes line
  that says the LINK did it (an app write is otherwise indistinguishable from
  a hand edit in the CRM history);
- an unknown or malformed id drops the attribution, never the submission;
- the public name lookup returns the name only, and every failure is a 404.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.espo import EspoError
from forms.client_intake.orchestrator import (
    ENGAGEMENT, PARTNER_PROFILE, REFERRING_PARTNER_ID, submit_intake,
)
from forms.client_intake.router import fetch_partner, make_router
from forms.client_intake.schemas import IntakeSubmission
from tests.test_client_intake import CapturingClient, _submission


class PartnerAwareClient(CapturingClient):
    def __init__(self, partners=None, **kw):
        super().__init__(**kw)
        self._partners = partners or {}

    async def get(self, entity, record_id, select=None):
        if entity == PARTNER_PROFILE:
            self.gets.append((entity, record_id))
            if record_id in self._partners:
                return {"id": record_id, "name": self._partners[record_id]}
            raise EspoError(f"GET {entity}/{record_id} -> 404 Not Found")
        return await super().get(entity, record_id, select)


def _engagement(client):
    return next(p for e, p in client.creates if e == ENGAGEMENT)


@pytest.mark.asyncio
async def test_a_real_partner_is_written_as_the_referring_partner():
    client = PartnerAwareClient(partners={"partner-7": "Greater Cleveland SBDC"})
    await submit_intake(_submission(referring_partner_id="partner-7"), client)
    eng = _engagement(client)
    assert eng[REFERRING_PARTNER_ID] == "partner-7"
    assert "Greater Cleveland SBDC" in eng["description"]
    assert "intake link" in eng["description"]


@pytest.mark.asyncio
async def test_an_unknown_partner_drops_the_attribution_not_the_submission():
    client = PartnerAwareClient(partners={})
    ids = await submit_intake(_submission(referring_partner_id="stale-id"), client)
    assert ids["engagementId"]
    eng = _engagement(client)
    assert REFERRING_PARTNER_ID not in eng
    assert "description" not in eng


@pytest.mark.asyncio
async def test_no_partner_means_no_read_and_no_note():
    client = PartnerAwareClient(partners={"partner-7": "X"})
    await submit_intake(_submission(), client)
    assert not [g for g in client.gets if g[0] == PARTNER_PROFILE]
    assert "description" not in _engagement(client)


@pytest.mark.asyncio
async def test_the_referral_note_and_the_sanitizer_note_both_survive():
    client = PartnerAwareClient(
        partners={"partner-7": "SBDC"},
        enum_options={(ENGAGEMENT, "mentoringFocusAreas"): ["Retail"]},
    )
    await submit_intake(_submission(referring_partner_id="partner-7"), client)
    desc = _engagement(client)["description"]
    assert "SBDC" in desc and "not recognized" in desc


def test_the_schema_accepts_and_bounds_the_id():
    assert IntakeSubmission(**_submission().model_dump()).referring_partner_id is None
    sub = _submission(referring_partner_id="abc123")
    assert sub.referring_partner_id == "abc123"
    with pytest.raises(Exception):
        _submission(referring_partner_id="x" * 33)


# --- the public name lookup -------------------------------------------------

class FakeCrm:
    def __init__(self, partners=None, fail=False):
        self._partners = partners or {}
        self._fail = fail
        self.calls = []

    async def get(self, entity, record_id, select=None):
        self.calls.append((entity, record_id, select))
        if self._fail:
            raise RuntimeError("CRM down")
        if record_id in self._partners:
            return {"id": record_id, "name": self._partners[record_id], "partnerNotes": "secret"}
        raise EspoError(f"GET {entity}/{record_id} -> 404 Not Found")


def _client(crm):
    app = FastAPI()
    app.include_router(make_router(lambda: crm))
    return TestClient(app)


def test_lookup_returns_the_name_only():
    crm = FakeCrm({"abc123": "Greater Cleveland SBDC"})
    res = _client(crm).get("/api/client-intake/partner/abc123")
    assert res.status_code == 200
    assert res.json() == {"partner": {"id": "abc123", "name": "Greater Cleveland SBDC"}}
    assert crm.calls[0][2] == "id,name"


@pytest.mark.parametrize("partner_id", ["unknown", "bad%20id", "x" * 40])
def test_unknown_or_malformed_ids_are_404(partner_id):
    crm = FakeCrm({"abc123": "X"})
    assert _client(crm).get(f"/api/client-intake/partner/{partner_id}").status_code == 404


def test_a_crm_outage_is_a_404_not_a_500():
    assert _client(FakeCrm(fail=True)).get("/api/client-intake/partner/abc123").status_code == 404


@pytest.mark.asyncio
async def test_fetch_partner_rejects_a_malformed_id_before_the_crm():
    crm = FakeCrm({"abc123": "X"})
    assert await fetch_partner(crm, "../Account") is None
    assert crm.calls == []
