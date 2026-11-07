"""Campaigns through the website and the newsletter form — prds/chapter-website-plan.md,
pieces D and E.

D: a campaign link may open a page on the chapter website and never anyone
else's; a form reached through the website carries only the link token, and
capture credits that link's campaign (decision 4.1); the website button the
visitor pressed lands on the lead (decision 4.4). E: the newsletter form is
dark until switched on, and a signup is a Contact with marketing consent set.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from campaigns import attribution as attrib
from campaigns import config as cfg
from campaigns import store as campaign_store
from campaigns.public import destination_path
from campaigns.router import _validate_destination
from core.app import create_app
from core.config import apply_overrides, get_settings
from core.receipts import _FORM_VALUES
from forms import ALL_SPECS, info_request
from forms.newsletter.orchestrator import submit_signup
from forms.newsletter.schemas import NewsletterSignup
from tests.test_campaign_attribution import Crm, _crm, _resumable

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://chapter-demo.example.org"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    apply_overrides({})
    yield
    apply_overrides({})
    campaign_store.set_capture_store(None)
    get_settings.cache_clear()


def _link(**kw):
    return {"campaign_id": "camp-1", "token": "abcdefgh", "destination_kind": cfg.DEST_WEBSITE,
            "destination_target": "/mentors/", **kw}


# --- D: a link that opens a chapter website page ------------------------------------

def test_a_website_link_opens_that_page_carrying_the_token():
    apply_overrides({"organization_website_url": SITE + "/"})
    assert destination_path(_link()) == f"{SITE}/mentors/?cmp=abcdefgh"


def test_a_persons_code_does_not_travel_through_the_website():
    apply_overrides({"organization_website_url": SITE})
    assert destination_path(_link(), scan_token="23456789abcd") == f"{SITE}/mentors/?cmp=abcdefgh"


@pytest.mark.parametrize("website,path", [
    ("http://chapter-demo.example.org", "/mentors/"),     # not https
    ("", "/mentors/"),                                    # not set
    (SITE, "https://evil.example.com/x"),                 # not a path
    (SITE, "/mentors/<script>"),
])
def test_a_website_link_never_sends_a_visitor_elsewhere(website, path):
    apply_overrides({"organization_website_url": website})
    assert destination_path(_link(destination_target=path)) is None


def test_creating_a_website_link_needs_the_connection_switched_on():
    apply_overrides({"organization_website_url": SITE})
    with pytest.raises(HTTPException) as exc:
        _validate_destination(cfg.DEST_WEBSITE, "/mentors/")
    assert "Chapter website connection" in exc.value.detail


def test_creating_a_website_link_takes_a_path_only():
    apply_overrides({"organization_website_url": SITE, "website_api": "true"})
    assert _validate_destination(cfg.DEST_WEBSITE, "mentors/") == (cfg.DEST_WEBSITE, "/mentors/")
    for bad in ("https://evil.example.com/", "/a b", ""):
        with pytest.raises(HTTPException):
            _validate_destination(cfg.DEST_WEBSITE, bad)


def test_creating_a_website_link_needs_the_website_address():
    apply_overrides({"organization_website_url": "", "website_api": "true"})
    with pytest.raises(HTTPException) as exc:
        _validate_destination(cfg.DEST_WEBSITE, "/mentors/")
    assert "Organisation website" in exc.value.detail


def test_the_link_editor_offers_a_website_page():
    js = (ROOT / "campaigns/frontend/app.js").read_text(encoding="utf-8")
    assert '["website", "A page on the chapter website"]' in js


# --- D: the token alone credits its campaign -------------------------------------------

class FakeLinks:
    async def get_link_by_token(self, token):
        return {"campaign_id": "camp-7"} if token == "abcdefgh" else None


class BrokenLinks:
    async def get_link_by_token(self, token):
        raise RuntimeError("database down")


@pytest.mark.asyncio
async def test_a_link_token_names_its_campaign():
    campaign_store.set_capture_store(FakeLinks())
    assert await campaign_store.campaign_for_link("abcdefgh") == "camp-7"
    assert await campaign_store.campaign_for_link("unknown1") is None


@pytest.mark.asyncio
async def test_a_failed_lookup_credits_nothing_and_never_raises():
    campaign_store.set_capture_store(BrokenLinks())
    assert await campaign_store.campaign_for_link("abcdefgh") is None
    campaign_store.set_capture_store(None)
    assert await campaign_store.campaign_for_link("abcdefgh") is None


def test_capture_credits_the_links_campaign(monkeypatch):
    seen = {}

    async def orchestrator(sub, client):
        seen["campaign_id"] = sub.campaign_id
        seen["campaign_link"] = sub.campaign_link
        return {"contactId": "c1"}

    spec = dataclasses.replace(info_request.SPEC, orchestrator=orchestrator)
    get_settings.cache_clear()
    client = TestClient(create_app([spec]))
    campaign_store.set_capture_store(FakeLinks())
    body = {"submission_token": "tok-12345678", "first_name": "Ada", "last_name": "L",
            "email": "ada@example.org", "message": "Hello", "campaign_link": "abcdefgh"}
    resp = client.post("/api/info-request/intake", json=body)
    assert resp.status_code == 200, resp.text
    assert seen == {"campaign_id": "camp-7", "campaign_link": "abcdefgh"}


# --- D: the website button lands on the lead ------------------------------------------------

class CrmWithPlacement(Crm):
    async def metadata(self, key):
        out = await super().metadata(key)
        if key == "entityDefs.CProspect.fields" and isinstance(out, dict):
            out = {**out, cfg.BUTTON_PLACEMENT_FIELD: {"type": "varchar"}}
        return out


def _signup(**kw) -> NewsletterSignup:
    data = {"submission_token": "tok-12345678", "first_name": "Ada", "last_name": "Lovelace",
            "email": "ada@example.org", "marketing_consent": True, **kw}
    return NewsletterSignup.model_validate(data)


@pytest.mark.asyncio
async def test_the_button_placement_is_written_on_the_new_lead():
    crm = CrmWithPlacement()
    crm.add("COutreachCampaign", {"id": "camp-1", "name": "x", "campaignStatus": "Running"})
    client, _ = _resumable(crm)
    await submit_signup(_signup(button_placement="mentor-profile"), client)
    lead = crm.created("CProspect")[0]
    assert lead[cfg.BUTTON_PLACEMENT_FIELD] == "mentor-profile"
    assert lead["leadSource"] == cfg.SOURCE_NEWSLETTER


@pytest.mark.asyncio
async def test_a_crm_without_the_field_simply_does_not_record_it():
    crm = _crm()
    client, _ = _resumable(crm)
    await submit_signup(_signup(button_placement="mentor-profile"), client)
    assert cfg.BUTTON_PLACEMENT_FIELD not in crm.created("CProspect")[0]


FORM_PAGES = sorted(ROOT.glob("forms/*/frontend/index.html"))


@pytest.mark.parametrize("page", FORM_PAGES, ids=lambda p: p.parent.parent.name)
def test_every_public_form_carries_the_button_placement(page):
    assert 'id="button_placement"' in page.read_text(encoding="utf-8")
    js = (page.parent / "app.js").read_text(encoding="utf-8")
    assert re.search(r"button_placement:", js)


def test_the_campaign_script_reads_the_placement():
    js = (ROOT / "frontend/shared/campaign-link.js").read_text(encoding="utf-8")
    assert 'params.get("placement")' in js and 'set("button_placement"' in js


# --- E: the newsletter form -------------------------------------------------------------------

def _app(**overrides) -> TestClient:
    get_settings.cache_clear()
    client = TestClient(create_app(ALL_SPECS))
    apply_overrides(overrides)
    return client


def test_the_newsletter_form_is_absent_until_switched_on():
    client = _app()
    assert client.get("/newsletter/").status_code == 404
    assert client.post("/api/newsletter/intake", json={}).status_code == 404
    apply_overrides({"newsletter_form": "true"})
    assert client.get("/newsletter/").status_code == 200


def test_the_other_forms_are_untouched_by_the_switch():
    assert _app().get("/info-request/").status_code == 200


def test_no_consent_no_signup():
    with pytest.raises(Exception):
        _signup(marketing_consent=False)


@pytest.mark.asyncio
async def test_a_new_subscriber_is_a_prospect_with_consent():
    crm = _crm()
    ids = await submit_signup(_signup(), crm)
    contact = crm.created("Contact")[0]
    assert contact["cMarketingOptIn"] is True and contact["cContactType"] == ["Prospect"]
    assert ids["contactId"]


@pytest.mark.asyncio
async def test_a_known_person_gains_consent_and_keeps_their_details():
    crm = _crm()
    crm.add("Contact", {"id": "c-9", "emailAddress": "ada@example.org", "firstName": "Augusta",
                        "lastName": "", "cMarketingOptIn": False, "cContactType": ["Client"]})
    await submit_signup(_signup(), crm)
    assert not crm.created("Contact")
    _, update = crm.updated("Contact")[0]
    assert update == {"cMarketingOptIn": True, "lastName": "Lovelace"}
    assert crm.rows["Contact"]["c-9"]["firstName"] == "Augusta"
    assert crm.rows["Contact"]["c-9"]["cContactType"] == ["Client"]


@pytest.mark.asyncio
async def test_consent_is_never_taken_away():
    crm = _crm()
    crm.add("Contact", {"id": "c-9", "emailAddress": "ada@example.org", "firstName": "Ada",
                        "lastName": "Lovelace", "cMarketingOptIn": True})
    await submit_signup(_signup(), crm)
    assert not any("cMarketingOptIn" in p and p["cMarketingOptIn"] is not True
                   for _, p in crm.updated("Contact"))


def test_the_receipt_names_the_newsletter_form():
    assert _FORM_VALUES["newsletter"] == "Newsletter"
