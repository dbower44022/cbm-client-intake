"""The lead code in every link — build plan § 7d, D1 (rulings 71–75, 77).

The boundaries: one code per person, never two; the code is copied lead →
contact at conversion and never minted twice; a CRM without the two fields
gets no code and no select naming them; the resolve still never waits on the
CRM (ruling 31) and carries the code, never an id; the click lands on the
person's own touch on that campaign, once-stamped, never overwriting a call's
outcome; the per-form lookup answers ruling 75's allowlist and nothing more,
with one 404 for every failure; attribution reads the code before the old id;
the postcard prints the person's code; the sandbox gives the demo cards'
leads their fixed codes.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from campaigns import attribution, config as cfg, leadcode, postcard, sandbox_demo
from campaigns.public import destination_path, lead_prefill
from campaigns.tokens import looks_like_token
from core.config import Settings, get_settings
from core.postal import DryRunPostalClient

from tests.test_campaigns import FakeCrm, FakeStore, build


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class CodeCrm(FakeCrm):
    """The campaigns fake with the lead-code fields (or without them)."""

    def __init__(self, *, with_codes: bool = True, with_clicks: bool = True):
        super().__init__()
        self.with_codes = with_codes
        self.with_clicks = with_clicks

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.PROSPECT}.fields":
            base = await super().metadata(key) or {}
            return {**base, **({leadcode.LEAD_FIELD: {"type": "varchar"}} if self.with_codes else {})}
        if key == f"entityDefs.{cfg.CONTACT}.fields":
            return {leadcode.CONTACT_FIELD: {"type": "varchar"}} if self.with_codes else {"firstName": {}}
        if key == f"entityDefs.{cfg.TOUCH}.fields":
            return {"firstClickedAt": {}, "clickCount": {}} if self.with_clicks else {"scanCount": {}}
        return await super().metadata(key)


def _run(coro):
    return asyncio.run(coro)


# --- minting and the one-code rule ---------------------------------------------------------

def test_a_lead_gets_one_code_for_life():
    crm = CodeCrm()
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "businessName": "Acme"})
    first = _run(leadcode.ensure_for_lead(crm, lead["id"]))
    again = _run(leadcode.ensure_for_lead(crm, lead["id"]))
    assert looks_like_token(first) and len(first) == leadcode.CODE_LENGTH
    assert again == first
    assert crm.rows[cfg.PROSPECT][lead["id"]][leadcode.LEAD_FIELD] == first


def test_a_converted_leads_new_code_lands_on_its_contact_too():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Dana Okoro"})
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "promotedContactId": contact["id"]})
    code = _run(leadcode.ensure_for_lead(crm, lead["id"]))
    assert crm.rows[cfg.CONTACT][contact["id"]][leadcode.CONTACT_FIELD] == code


def test_a_lead_adopts_the_code_its_contact_already_holds():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Dana", leadcode.CONTACT_FIELD: "abcdefghjkmn"})
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "promotedContactId": contact["id"]})
    assert _run(leadcode.ensure_for_lead(crm, lead["id"])) == "abcdefghjkmn"


def test_a_contact_with_no_lead_holds_its_own_code():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Walter Kemp"})
    code = _run(leadcode.ensure_for_contact(crm, contact["id"]))
    assert crm.rows[cfg.CONTACT][contact["id"]][leadcode.CONTACT_FIELD] == code
    assert not crm.rows.get(cfg.PROSPECT)


def test_conversion_copies_the_code_and_never_mints_a_second():
    from campaigns.conversion import mark_converted
    crm = CodeCrm()
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "leadStatus": "Qualified", leadcode.LEAD_FIELD: "abcdefghjkmn"})
    contact = crm.add(cfg.CONTACT, {"name": "Dana"})
    _run(mark_converted(crm, lead, contact_id=contact["id"]))
    assert crm.rows[cfg.CONTACT][contact["id"]][leadcode.CONTACT_FIELD] == "abcdefghjkmn"
    assert crm.rows[cfg.PROSPECT][lead["id"]][leadcode.LEAD_FIELD] == "abcdefghjkmn"


def test_two_different_codes_are_both_kept():
    crm = CodeCrm()
    lead = crm.add(cfg.PROSPECT, {"name": "A", leadcode.LEAD_FIELD: "aaaaaaaaaaaa"})
    contact = crm.add(cfg.CONTACT, {"name": "B", leadcode.CONTACT_FIELD: "bbbbbbbbbbbb"})
    assert _run(leadcode.sync_on_conversion(crm, lead["id"], contact["id"])) is None
    assert crm.rows[cfg.CONTACT][contact["id"]][leadcode.CONTACT_FIELD] == "bbbbbbbbbbbb"


def test_a_crm_without_the_fields_gets_no_code_and_no_write():
    crm = CodeCrm(with_codes=False)
    lead = crm.add(cfg.PROSPECT, {"name": "Acme"})
    assert _run(leadcode.ensure_for_lead(crm, lead["id"])) is None
    assert _run(leadcode.resolve(crm, "abcdefghjkmn")) is None
    assert crm.updated == []


# --- resolving -----------------------------------------------------------------------------

def test_resolve_finds_the_contact_first_then_the_lead_behind_it():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Dana", leadcode.CONTACT_FIELD: "abcdefghjkmn"})
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "promotedContactId": contact["id"]})
    person = _run(leadcode.resolve(crm, "ABCDEFGHJKMN"))
    assert person.contact_id == contact["id"] and person.lead_id == lead["id"]


def test_resolve_refuses_a_malformed_or_unknown_code():
    crm = CodeCrm()
    assert _run(leadcode.resolve(crm, "bad!code")) is None
    assert _run(leadcode.resolve(crm, "zzzzzzzzzzzz")) is None


# --- the resolve route (ruling 31 kept) --------------------------------------------------------

def test_a_personal_link_carries_the_code_never_an_id():
    link = {"campaign_id": "camp1", "token": "abcdefgh", "destination_kind": cfg.DEST_FORM,
            "destination_target": "info-request"}
    assert destination_path(link, scan_token="abcdefghjkmn") == \
        "/info-request/?campaign=camp1&link=abcdefgh&lead=abcdefghjkmn"
    landing = {**link, "destination_kind": cfg.DEST_LANDING}
    assert destination_path(landing, scan_token="abcdefghjkmn") == "/p/abcdefghjkmn?link=abcdefgh"


def test_the_resolve_redirects_before_any_crm_read(monkeypatch):
    store = FakeStore()
    client = build(monkeypatch, user=None, store=store)
    clicks = []
    import campaigns.public as public_mod

    async def _later(factory, campaign_id, code):
        clicks.append((campaign_id, code))
    monkeypatch.setattr(public_mod, "_click_later", _later)
    link = _run(store.create_link(campaign_id="camp1", name="Ask", destination_kind=cfg.DEST_FORM,
                                  destination_target="info-request", destination_slug=None, created_by="t"))
    resp = client.get(f"/c/{link['token']}/ABCDEFGHJKMN", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["cache-control"] == "no-store"
    assert resp.headers["location"].endswith("&lead=abcdefghjkmn")
    assert clicks == [("camp1", "abcdefghjkmn")]          # after the answer, as a background task
    # A landing link records its own scan on /p/, never a click.
    clicks.clear()
    landing = _run(store.create_link(campaign_id="camp1", name="Card", destination_kind=cfg.DEST_LANDING,
                                     destination_target=None, destination_slug=None, created_by="t"))
    client.get(f"/c/{landing['token']}/abcdefghjkmn", follow_redirects=False)
    assert clicks == []


# --- the click ---------------------------------------------------------------------------------

def _touch(crm, campaign_id, **kw):
    return crm.add(cfg.TOUCH, {"outreachCampaignId": campaign_id, "touchStatus": "Sent",
                               "sentAt": "2026-10-20 10:00:00", **kw})


def test_a_click_lands_on_the_persons_touch_once_stamped():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Dana", leadcode.CONTACT_FIELD: "abcdefghjkmn"})
    mine = _touch(crm, "camp1", contactId=contact["id"])
    other = _touch(crm, "camp2", contactId=contact["id"])
    out = _run(leadcode.record_click(crm, "camp1", "abcdefghjkmn", "2026-10-22 13:00:00"))
    assert out == {"recorded": True, "touchId": mine["id"]}
    _run(leadcode.record_click(crm, "camp1", "abcdefghjkmn", "2026-10-22 14:00:00"))
    row = crm.rows[cfg.TOUCH][mine["id"]]
    assert row["clickCount"] == 2 and row["firstClickedAt"] == "2026-10-22 13:00:00"
    assert row["outcome"] == cfg.OUTCOME_CLICKED
    assert "clickCount" not in crm.rows[cfg.TOUCH][other["id"]]


def test_a_click_never_overwrites_a_calls_outcome_or_touches_a_preview():
    crm = CodeCrm()
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", leadcode.LEAD_FIELD: "abcdefghjkmn"})
    called = _touch(crm, "camp1", prospectId=lead["id"], outcome=cfg.OUTCOME_INTERESTED)
    _run(leadcode.record_click(crm, "camp1", "abcdefghjkmn", "2026-10-22 13:00:00"))
    assert crm.rows[cfg.TOUCH][called["id"]]["outcome"] == cfg.OUTCOME_INTERESTED
    crm2 = CodeCrm()
    lead2 = crm2.add(cfg.PROSPECT, {"name": "B", leadcode.LEAD_FIELD: "abcdefghjkmn"})
    _touch(crm2, "camp1", prospectId=lead2["id"], touchStatus="Planned")
    assert _run(leadcode.record_click(crm2, "camp1", "abcdefghjkmn", "x"))["reason"] == "no touch"


def test_no_click_fields_means_no_click_write():
    crm = CodeCrm(with_clicks=False)
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", leadcode.LEAD_FIELD: "abcdefghjkmn"})
    _touch(crm, "camp1", prospectId=lead["id"])
    assert _run(leadcode.record_click(crm, "camp1", "abcdefghjkmn", "x"))["recorded"] is False
    assert crm.updated == []


# --- the per-form lookup (ruling 75) ----------------------------------------------------------

def _person(crm):
    company = crm.add(cfg.ACCOUNT, {"name": "Acme Bakery", "website": "acme.example",
                                    "billingAddressStreet": "1 Main St", "billingAddressCity": "Cleveland",
                                    "billingAddressState": "OH", "billingAddressPostalCode": "44113"})
    contact = crm.add(cfg.CONTACT, {"name": "Dana Okoro", "firstName": "Dana", "lastName": "Okoro",
                                    "emailAddress": "dana@acme.example", "phoneNumber": "+12165550100",
                                    "addressPostalCode": "44113", "accountId": company["id"],
                                    leadcode.CONTACT_FIELD: "abcdefghjkmn"})
    crm.add(cfg.PROSPECT, {"name": "Acme", "businessName": "Acme Bakery LLC", "promotedContactId": contact["id"],
                           "mailingAddressStreet": "9 Filing Rd", leadcode.LEAD_FIELD: "abcdefghjkmn"})


@pytest.mark.parametrize("form", sorted(cfg.PREFILL_FIELDS))
def test_each_form_gets_exactly_its_allowlist(form):
    crm = CodeCrm()
    _person(crm)
    values = _run(lead_prefill(crm, "abcdefghjkmn", form))
    assert set(values) == set(cfg.PREFILL_FIELDS[form])


def test_the_prefill_reads_the_contact_and_its_company_before_the_lead():
    crm = CodeCrm()
    _person(crm)
    v = _run(lead_prefill(crm, "abcdefghjkmn", "client-intake"))
    assert v["email"] == "dana@acme.example" and v["companyName"] == "Acme Bakery"
    assert v["companyZip"] == "44113"
    landing = _run(lead_prefill(crm, "abcdefghjkmn", "landing"))
    assert landing == {"businessName": "Acme Bakery LLC", "mailingStreet": "9 Filing Rd", "mailingCity": "",
                       "mailingState": "", "mailingZip": ""}


def test_the_volunteer_lookup_serves_no_company_and_landing_no_person():
    assert not {"companyName", "companyWebsite"} & set(cfg.PREFILL_FIELDS["volunteer"])
    assert not {"firstName", "lastName", "email", "phone"} & set(cfg.PREFILL_FIELDS["landing"])


def test_the_lookup_route_404s_alike(monkeypatch):
    client = build(monkeypatch, user=None, store=FakeStore())
    crm = CodeCrm()
    _person(crm)
    client.app.state.events_client_factory = lambda: crm
    ok = client.get("/api/campaigns/public/lead/abcdefghjkmn?form=info-request")
    assert ok.status_code == 200 and set(ok.json()["lead"]) == set(cfg.PREFILL_FIELDS["info-request"])
    answers = {
        client.get("/api/campaigns/public/lead/zzzzzzzzzzzz?form=info-request").json()["detail"],
        client.get("/api/campaigns/public/lead/bad!code?form=info-request").json()["detail"],
        client.get("/api/campaigns/public/lead/abcdefghjkmn?form=nosuchform").json()["detail"],
        client.get("/api/campaigns/public/lead/abcdefghjkmn").json()["detail"],
    }
    assert answers == {"Not found"}


# --- attribution at delivery ---------------------------------------------------------------

def test_attribution_reads_the_code_before_the_old_id():
    crm = CodeCrm()
    by_code = crm.add(cfg.PROSPECT, {"name": "Coded", leadcode.LEAD_FIELD: "abcdefghjkmn"})
    by_id = crm.add(cfg.PROSPECT, {"name": "Old"})
    lead, contact = _run(attribution.valid_lead(crm, SimpleNamespace(lead_code="abcdefghjkmn", prospect_id=by_id["id"])))
    assert lead["id"] == by_code["id"] and contact is None
    lead, _ = _run(attribution.valid_lead(crm, SimpleNamespace(lead_code=None, prospect_id=by_id["id"])))
    assert lead["id"] == by_id["id"]


def test_an_unknown_code_drops_the_lead_never_the_submission():
    crm = CodeCrm()
    assert _run(attribution.valid_lead(crm, SimpleNamespace(lead_code="zzzzzzzzzzzz", prospect_id=None))) == (None, None)


def test_a_contact_only_code_attributes_to_the_contact():
    crm = CodeCrm()
    contact = crm.add(cfg.CONTACT, {"name": "Walter", leadcode.CONTACT_FIELD: "abcdefghjkmn"})
    attr = _run(attribution.resolve(crm, SimpleNamespace(lead_code="abcdefghjkmn", prospect_id=None, campaign_id=None),
                                    entity="CInformationRequest"))
    assert attr.prospect is None and attr.result() == {"leadContactId": contact["id"]}


def test_every_submission_model_carries_the_lead_code():
    from forms import SPECS_BY_SLUG
    for slug, spec in SPECS_BY_SLUG.items():
        assert "lead_code" in spec.submission_model.model_fields, slug


@pytest.mark.parametrize("form", ["client_intake", "volunteer", "info_request", "partner", "sponsor"])
def test_every_public_form_sends_the_lead_code(form):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "forms" / form / "frontend"
    assert 'id="lead_code"' in (root / "index.html").read_text()
    assert "lead_code" in (root / "app.js").read_text()


def test_the_event_pages_send_and_carry_the_lead_code():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "events" / "public_frontend"
    for name in ("event.js", "public.js"):
        assert 'lead_code: campaignParam("lead")' in (root / name).read_text(), name
    assert '"&lead="' in (root / "public.js").read_text()


# --- the postcard and the sandbox -----------------------------------------------------------

def test_the_card_prints_the_leads_code_and_a_retry_prints_the_same():
    crm = CodeCrm(); store = FakeStore(); vendor = DryRunPostalClient()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Cards", "campaignKind": "Postcard", "campaignStatus": "Signed off"})
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "businessName": "Acme", "leadStatus": "Qualified",
                                  "mailingAddressStreet": "1 Main St", "mailingAddressCity": "Cleveland",
                                  "mailingAddressState": "OH", "mailingAddressPostalCode": "44113",
                                  "mailingAddressCountry": "US"})
    touch = crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Planned",
                                "outreachCampaignId": camp["id"], "prospectId": lead["id"]})
    settings = Settings(_env_file=None, app_base_url="https://apps.example.org")
    _run(postcard.run_campaign(crm, camp, vendor=vendor, store=store, settings=settings))
    code = crm.rows[cfg.PROSPECT][lead["id"]][leadcode.LEAD_FIELD]
    assert crm.rows[cfg.TOUCH][touch["id"]]["scanToken"] == code
    target = _run(postcard._target_for(crm, crm.rows[cfg.TOUCH][touch["id"]]))
    assert _run(postcard.card_code(crm, target)) == code


def test_without_the_fields_a_card_keeps_a_per_card_token():
    crm = CodeCrm(with_codes=False)
    lead = crm.add(cfg.PROSPECT, {"name": "Acme"})
    code = _run(postcard.card_code(crm, {"kind": "prospect", "record": lead}))
    assert looks_like_token(code) and leadcode.LEAD_FIELD not in crm.rows[cfg.PROSPECT][lead["id"]]


def test_the_sandbox_gives_each_demo_cards_lead_its_card_code():
    crm = CodeCrm()
    leads = []
    for code in sandbox_demo.DEMO_SCAN_TOKENS:
        lead = crm.add(cfg.PROSPECT, {"name": f"Lead {code}"})
        crm.add(cfg.TOUCH, {"scanToken": code, "prospectId": lead["id"]})
        leads.append((lead["id"], code))
    first = _run(sandbox_demo.restore_demo_codes(crm))
    again = _run(sandbox_demo.restore_demo_codes(crm))
    assert first["set"] == len(leads) and again == {"set": 0, "present": len(leads), "skipped": 0}
    for lead_id, code in leads:
        assert crm.rows[cfg.PROSPECT][lead_id][leadcode.LEAD_FIELD] == code


@pytest.mark.parametrize("form", ["client_intake", "info_request", "partner", "sponsor"])
def test_the_shared_prefill_fills_each_forms_company_box(form):
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    html = (root / "forms" / form / "frontend" / "index.html").read_text()
    script = (root / "frontend" / "shared" / "campaign-link.js").read_text()
    filled = set(re.findall(r'fill\("([a-z_]+)", p\.businessName\)', script))
    boxes = {i for i in ("business_name", "company_name", "organization", "company") if f'id="{i}"' in html}
    assert boxes and boxes <= filled, (form, boxes - filled)
