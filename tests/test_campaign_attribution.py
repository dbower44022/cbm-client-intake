"""Prospect marketing Phase 2 — the doors honour the ids
(prds/prospect-marketing/build-plan.md § 5, § 1.9, § 3.7; rulings 21, 27, 30,
34).

What is pinned here:

* the Prospect relabel is one rule in ``core/crm_upsert`` — a relationship
  type removes ``Prospect``, any other type leaves it, nothing else is ever
  removed;
* every door validates-or-drops the campaign id and the prospect id, writes the
  campaign on the relationship record every time and on the Contact and the
  Company only when it created them, uses a prospect record's promoted company
  by id, links the prospect record to what it became, and writes the notes
  line;
* the engagement's ``referringPartners`` holds the partner link's partner AND
  every partner the campaign names (ruling 30), and the three readers take the
  union;
* the information request door types a new company Prospect (ruling 34) and
  falls back to the old shape on a CRM without the option;
* the Responses tab's counts and the programme page's carry-through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from campaigns import attribution as attrib
from campaigns import config as cfg
from campaigns.router import summarize_responses
from core.crm_upsert import merge_company_type, merge_contact_type, merged_types
from core.espo import EspoError
from forms.client_intake.orchestrator import ENGAGEMENT, submit_intake
from forms.event_registration.orchestrator import deliver as deliver_registration
from forms.info_request.orchestrator import INFO_REQUEST, submit_request
from forms.partner.orchestrator import PARTNER_PROFILE, submit_partner
from forms.sponsor.orchestrator import SPONSOR_PROFILE, submit_sponsor
from tests.test_client_intake import _submission
from tests.test_events_registration import make_event
from tests.test_events_registration import submission as _reg_sub
from tests.test_info_request import _request
from tests.test_partner import _application as _partner_app
from tests.test_sponsor import _application as _sponsor_app

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = {"id": "camp-1", "name": "Spring postcards", "campaignStatus": "Running"}
WARM = cfg.STAGE_WARM_LEAD


# --- a CRM with the Phase 1 change ------------------------------------------------------

class Crm:
    """A fake EspoCRM carrying the Phase 1 entities and links: records by
    entity, equals-only where clauses, relate recorded, metadata answering
    the links and fields the doors feature-detect."""

    def __init__(self, *, phase1: bool = True, prospect_option: bool | None = None):
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.related: dict[tuple[str, str, str], list[str]] = {}
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.relates: list[tuple[str, str, str, str]] = []
        self.gets: list[tuple[str, str]] = []
        self.phase1 = phase1
        self.prospect_option = phase1 if prospect_option is None else prospect_option
        self._n = 0

    def add(self, entity: str, row: dict[str, Any]) -> dict[str, Any]:
        self._n += 1
        row = {"id": row.get("id") or f"{entity}-{self._n}", **row}
        self.rows.setdefault(entity, {})[row["id"]] = row
        return row

    def link(self, entity: str, record_id: str, link: str, *ids: str) -> None:
        self.related.setdefault((entity, record_id, link), []).extend(ids)

    # -- metadata (feature detection) --
    async def metadata(self, key: str):
        if not self.phase1:
            return {} if key.endswith(".links") or key.endswith(".fields") else None
        if key.endswith(".links"):
            entity = key.split(".")[1]
            links = {"outreachCampaign": {"type": "belongsTo"}} if entity != "Contact" and entity != "Account" else {"cOutreachCampaign": {"type": "belongsTo"}}
            if entity == "CEngagement":
                links["referringPartners"] = {"type": "hasMany"}
            return links
        if key.endswith(".fields"):
            return {"cFunnelStage": {"type": "enum"}, "cEntryStage": {"type": "enum"}}
        return None

    async def metadata_enum_options(self, entity, field):
        if entity == "Account" and field == "cCompanyType":
            base = ["Client", "Sponsor", "Partner", "Other"]
            return base + ["Prospect"] if self.prospect_option else base
        return None

    # -- reads --
    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id))
        row = self.rows.get(entity, {}).get(record_id)
        if row is None:
            raise EspoError(f"get {entity}/{record_id} failed: 404 Not Found")
        return dict(row)

    async def find_one(self, entity, attribute, value, select="id"):
        for r in self.rows.get(entity, {}).values():
            if r.get(attribute) == value:
                return dict(r)
        return None

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        rows = list(self.rows.get(entity, {}).values())
        for c in where or []:
            if c.get("type") == "equals":
                rows = [r for r in rows if r.get(c["attribute"]) == c.get("value")]
        return {"total": len(rows), "list": [dict(r) for r in rows[offset:offset + max_size]]}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        key = (entity, record_id, link)
        if key not in self.related and not self.phase1:
            raise EspoError(f"list_related {entity}/{record_id}/{link} failed: 404 Not Found")
        foreign = {"partnerProfiles": "CPartnerProfile", "referringPartners": "CPartnerProfile"}.get(link)
        out = []
        for rid in self.related.get(key, []):
            out.append(dict(self.rows.get(foreign, {}).get(rid) or {"id": rid, "name": rid}))
        return {"total": len(out), "list": out}

    # -- writes --
    async def create(self, entity, payload):
        row = self.add(entity, dict(payload))
        self.creates.append((entity, payload))
        return dict(row)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.rows.setdefault(entity, {}).setdefault(record_id, {"id": record_id}).update(payload)
        return {"id": record_id, **payload}

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))
        self.related.setdefault((entity, record_id, link), []).append(related_id)

    def created(self, entity):
        return [p for e, p in self.creates if e == entity]

    def updated(self, entity):
        return [(rid, p) for e, rid, p in self.updates if e == entity]


def _crm(**kw) -> Crm:
    crm = Crm(**kw)
    crm.add("COutreachCampaign", CAMPAIGN)
    return crm


# --- the relabel rule -------------------------------------------------------------------

@pytest.mark.parametrize("types,new,expected", [
    (["Prospect"], "Client", ["Client"]),
    (["Prospect"], "Partner", ["Partner"]),
    (["Prospect", "Other"], "Sponsor", ["Other", "Sponsor"]),
    (["Prospect"], "Presenter", ["Prospect", "Presenter"]),   # not a relationship type
    (["Prospect"], "Member", ["Prospect", "Member"]),
    (["Sponsor"], "Partner", ["Sponsor", "Partner"]),           # nothing else is ever removed
    (["Client"], "Client", None),                                # already there: no write
    ([], "Client", ["Client"]),
    (None, "Prospect", ["Prospect"]),
])
def test_merged_types_appends_and_removes_prospect_only_for_a_relationship(types, new, expected):
    assert merged_types(types, new) == expected


@pytest.mark.asyncio
async def test_merge_contact_type_relabels_a_prospect_and_is_best_effort():
    crm = Crm()
    assert await merge_contact_type(crm, {"id": "c1", "cContactType": ["Prospect"]}, "Client") is True
    assert crm.updated("Contact") == [("c1", {"cContactType": ["Client"]})]
    assert await merge_contact_type(crm, {"id": "c1", "cContactType": ["Client"]}, "Client") is False

    class Refusing(Crm):
        async def update(self, *a, **k):
            raise EspoError("update failed: 403")
    assert await merge_contact_type(Refusing(), {"id": "c2", "cContactType": ["Prospect"]}, "Client") is False


@pytest.mark.asyncio
async def test_merge_company_type_now_removes_prospect_on_conversion():
    crm = Crm()
    await merge_company_type(crm, {"id": "a1", "cCompanyType": ["Prospect"]}, "Partner")
    assert crm.updated("Account") == [("a1", {"cCompanyType": ["Partner"]})]


# --- validate-or-drop -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_real_campaign_is_honoured_and_a_stale_one_dropped():
    crm = _crm()
    assert await attrib.valid_campaign(crm, "camp-1", entity="CEngagement") == {"id": "camp-1", "name": "Spring postcards"}
    assert await attrib.valid_campaign(crm, "nope", entity="CEngagement") is None
    assert await attrib.valid_campaign(crm, None, entity="CEngagement") is None
    assert await attrib.valid_prospect(crm, "nope") is None


@pytest.mark.asyncio
async def test_a_cancelled_campaign_is_dropped():
    crm = Crm()
    crm.add("COutreachCampaign", {**CAMPAIGN, "campaignStatus": "Cancelled"})
    assert await attrib.valid_campaign(crm, "camp-1", entity="CEngagement") is None


@pytest.mark.asyncio
async def test_a_crm_without_the_link_drops_the_campaign_before_reading_it():
    crm = _crm(phase1=False)
    assert await attrib.valid_campaign(crm, "camp-1", entity="CEngagement") is None
    assert ("COutreachCampaign", "camp-1") not in crm.gets


# --- client intake -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_intake_writes_the_campaign_everywhere_it_created_and_the_notes_line():
    crm = _crm()
    crm.add("CPartnerProfile", {"id": "p-a", "name": "Alpha Partners"})
    crm.add("CPartnerProfile", {"id": "p-b", "name": "Beta Partners"})
    crm.link("COutreachCampaign", "camp-1", "partnerProfiles", "p-b", "p-a")
    ids = await submit_intake(_submission(campaign_id="camp-1", campaign_link="abcd1234"), crm)

    company, = crm.created("Account")
    contact, = crm.created("Contact")
    eng, = crm.created(ENGAGEMENT)
    assert company["cOutreachCampaignId"] == "camp-1"
    assert contact["cOutreachCampaignId"] == "camp-1"
    assert eng["outreachCampaignId"] == "camp-1"
    assert "Arrived through the campaign Spring postcards." in eng["description"]
    # step 6a: the campaign's partners, name order, related and named
    assert "Referring partners set from the campaign Spring postcards: Alpha Partners, Beta Partners." in eng["description"]
    assert [(l, r) for _, _, l, r in crm.relates if l == "referringPartners"] == [("referringPartners", "p-a"), ("referringPartners", "p-b")]
    assert "referringPartnerId" not in eng          # the single link is the partner link's own
    assert ids["campaignId"] == "camp-1"
    assert ids["referringPartnerIds"] == ["p-a", "p-b"]
    # no stage fields on a client: Candidate is read from the engagement
    assert "cFunnelStage" not in contact and "cFunnelStage" not in company


@pytest.mark.asyncio
async def test_client_intake_partner_link_plus_campaign_credits_everyone():
    crm = _crm()
    crm.add("CPartnerProfile", {"id": "p-link", "name": "Link Partner"})
    crm.add("CPartnerProfile", {"id": "p-camp", "name": "Campaign Partner"})
    crm.link("COutreachCampaign", "camp-1", "partnerProfiles", "p-camp")
    await submit_intake(_submission(campaign_id="camp-1", referring_partner_id="p-link"), crm)
    eng, = crm.created(ENGAGEMENT)
    assert eng["referringPartnerId"] == "p-link"
    related = [r for _, _, l, r in crm.relates if l == "referringPartners"]
    assert related == ["p-link", "p-camp"]


@pytest.mark.asyncio
async def test_client_intake_without_a_campaign_still_relates_the_link_partner_on_the_many_link():
    crm = _crm()
    crm.add("CPartnerProfile", {"id": "p-link", "name": "Link Partner"})
    await submit_intake(_submission(referring_partner_id="p-link"), crm)
    assert [r for _, _, l, r in crm.relates if l == "referringPartners"] == ["p-link"]
    eng, = crm.created(ENGAGEMENT)
    assert "outreachCampaignId" not in eng and "campaign" not in eng.get("description", "").lower()


@pytest.mark.asyncio
async def test_client_intake_uses_the_promoted_company_by_id_and_relabels_both_records():
    crm = _crm()
    promoted = crm.add("Account", {"id": "acc-p", "name": "Difference Engine LLC", "cCompanyType": ["Prospect"], "website": None})
    crm.add("Account", {"id": "acc-stranger", "name": "Difference Engine LLC", "cCompanyType": ["Client"], "website": "https://stranger.example"})
    crm.add("Contact", {"id": "c-p", "emailAddress": "ada@example.com", "cContactType": ["Prospect"]})
    crm.add("CProspect", {"id": "pr-1", "name": "Difference Engine", "promotedCompanyId": "acc-p", "promotedContactId": None, "funnelStage": "Lead"})
    ids = await submit_intake(_submission(campaign_id="camp-1", prospect_id="pr-1"), crm)

    assert ids["accountId"] == "acc-p"                      # by id, never the same-named stranger
    assert crm.created("Account") == []
    assert ("acc-p", {"cCompanyType": ["Client"]}) in crm.updated("Account")       # Prospect -> Client
    assert ("acc-p", {"website": "https://example.com"}) in crm.updated("Account")  # null-filled
    assert ("c-p", {"cContactType": ["Client"]}) in crm.updated("Contact")         # Prospect -> Client
    assert crm.created("Contact") == []
    assert ("pr-1", {"promotedContactId": "c-p"}) in crm.updated("CProspect")      # linked, company already set
    assert ids["prospectLinked"] == ["promotedContactId"]
    # ruling 27: a MATCHED contact and company do not gain the campaign
    assert not any("cOutreachCampaignId" in p for _, p in crm.updated("Contact") + crm.updated("Account"))


@pytest.mark.asyncio
async def test_client_intake_matched_contact_with_another_type_gains_client_keeps_the_rest():
    crm = _crm()
    crm.add("Contact", {"id": "c-m", "emailAddress": "ada@example.com", "cContactType": ["Mentor"]})
    await submit_intake(_submission(), crm)
    assert ("c-m", {"cContactType": ["Mentor", "Client"]}) in crm.updated("Contact")


@pytest.mark.asyncio
async def test_client_intake_unknown_ids_drop_the_attribution_never_the_submission():
    crm = _crm()
    ids = await submit_intake(_submission(campaign_id="stale", prospect_id="gone"), crm)
    assert ids["engagementId"]
    eng, = crm.created(ENGAGEMENT)
    assert "outreachCampaignId" not in eng and "description" not in eng
    assert "campaignId" not in ids and "prospectId" not in ids


@pytest.mark.asyncio
async def test_client_intake_on_a_crm_without_the_links_is_exactly_as_before():
    crm = _crm(phase1=False)
    crm.add("CPartnerProfile", {"id": "p-link", "name": "Link Partner"})
    ids = await submit_intake(_submission(campaign_id="camp-1", referring_partner_id="p-link"), crm)
    eng, = crm.created(ENGAGEMENT)
    assert eng["referringPartnerId"] == "p-link"
    assert "outreachCampaignId" not in eng
    assert not [r for _, _, l, r in crm.relates if l == "referringPartners"]
    assert ids["engagementId"]


# --- information request ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_info_request_creates_a_prospect_company_at_warm_lead_with_the_campaign():
    crm = _crm()
    ids = await submit_request(_request(company="Ada's Bakery", campaign_id="camp-1"), crm)
    company, = crm.created("Account")
    assert company["cCompanyType"] == ["Prospect"]
    assert "cClientStatus" not in company                     # ruling 34: untouched
    assert company["cFunnelStage"] == WARM and company["cEntryStage"] == WARM
    assert company["cOutreachCampaignId"] == "camp-1"
    contact, = crm.created("Contact")
    assert contact["cContactType"] == ["Prospect"]
    assert contact["cFunnelStage"] == WARM and contact["cEntryStage"] == WARM
    assert contact["cOutreachCampaignId"] == "camp-1"
    info, = crm.created(INFO_REQUEST)
    assert info["outreachCampaignId"] == "camp-1"
    assert info["description"].startswith("Arrived through the campaign Spring postcards.")
    assert ids["campaignId"] == "camp-1"


@pytest.mark.asyncio
async def test_info_request_falls_back_to_the_old_shape_without_the_prospect_option():
    crm = _crm(prospect_option=False)
    await submit_request(_request(company="Ada's Bakery"), crm)
    company, = crm.created("Account")
    assert company["cCompanyType"] == ["Client"] and company["cClientStatus"] == "Prospect"
    assert "cFunnelStage" not in company


@pytest.mark.asyncio
async def test_info_request_leaves_a_known_company_alone_and_advances_a_known_contact():
    crm = _crm()
    crm.add("Account", {"id": "a-s", "name": "Generous Corp", "cCompanyType": ["Sponsor"]})
    await submit_request(_request(company="Generous Corp"), crm)
    assert crm.updated("Account") == []                      # ruling 34
    crm2 = _crm()
    crm2.add("Contact", {"id": "c-e", "emailAddress": "ada@example.com", "cFunnelStage": "Lead", "cContactType": ["Prospect"]})
    await submit_request(_request(campaign_id="camp-1"), crm2)
    assert ("c-e", {"cFunnelStage": WARM}) in crm2.updated("Contact")
    assert not any("cContactType" in p for _, p in crm2.updated("Contact"))   # the type is untouched
    assert not any("cOutreachCampaignId" in p for _, p in crm2.updated("Contact"))  # ruling 27


@pytest.mark.asyncio
async def test_info_request_never_lowers_a_rung():
    crm = _crm()
    crm.add("Contact", {"id": "c-o", "emailAddress": "ada@example.com", "cFunnelStage": "Opportunity"})
    await submit_request(_request(), crm)
    assert not any("cFunnelStage" in p for _, p in crm.updated("Contact"))


@pytest.mark.asyncio
async def test_info_request_uses_the_promoted_company_and_links_the_prospect_record():
    crm = _crm()
    crm.add("Account", {"id": "acc-p", "name": "Ada's Bakery", "cCompanyType": ["Prospect"], "cFunnelStage": "Lead"})
    crm.add("CProspect", {"id": "pr-1", "promotedCompanyId": "acc-p", "promotedContactId": None})
    ids = await submit_request(_request(company="Ada's Bakery", prospect_id="pr-1"), crm)
    assert ids["accountId"] == "acc-p" and crm.created("Account") == []
    assert ("acc-p", {"cFunnelStage": WARM}) in crm.updated("Account")
    assert not any("cCompanyType" in p for _, p in crm.updated("Account"))   # no relationship: stays Prospect
    assert ("pr-1", {"promotedContactId": ids["contactId"]}) in crm.updated("CProspect")


# --- event registration --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registration_carries_the_campaign_on_create_and_moves_the_person_to_warm_lead():
    crm = _crm()
    crm.add("CEvent", make_event())
    ids = await deliver_registration(_reg_sub(campaign_id="camp-1"), crm, settings=None)
    contact, = crm.created("Contact")
    assert contact["cContactType"] == ["Prospect"]
    assert contact["cFunnelStage"] == WARM and contact["cEntryStage"] == WARM
    assert contact["cOutreachCampaignId"] == "camp-1"
    reg, = crm.created("CEventRegistration")
    assert reg["outreachCampaignId"] == "camp-1"
    assert ids["campaignId"] == "camp-1"


@pytest.mark.asyncio
async def test_registration_existing_contact_keeps_type_gains_rung_and_a_repeat_keeps_the_first_campaign():
    crm = _crm()
    crm.add("CEvent", make_event())
    crm.add("Contact", {"id": "c-cl", "emailAddress": "sam@example.com", "cContactType": ["Client"], "cFunnelStage": None})
    await deliver_registration(_reg_sub(email="sam@example.com", campaign_id="camp-1"), crm, settings=None)
    assert ("c-cl", {"cFunnelStage": WARM}) in crm.updated("Contact")
    assert not any("cContactType" in p for _, p in crm.updated("Contact"))   # D-09
    assert not any("cOutreachCampaignId" in p for _, p in crm.updated("Contact"))
    crm.add("COutreachCampaign", {"id": "camp-2", "name": "Second", "campaignStatus": "Running"})
    await deliver_registration(_reg_sub(email="sam@example.com", campaign_id="camp-2"), crm, settings=None)
    assert len(crm.created("CEventRegistration")) == 1
    assert not any("outreachCampaignId" in p for _, p in crm.updated("CEventRegistration"))


# --- partner and sponsor -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partner_form_writes_the_campaign_and_relabels_a_prospect_company_and_contact():
    crm = _crm()
    crm.add("Account", {"id": "a-p", "name": "Acme Partners", "cCompanyType": ["Prospect"], "website": None})
    crm.add("Contact", {"id": "c-p", "emailAddress": "pat@acme.example", "cContactType": ["Prospect"]})
    sub = _partner_app(company="Acme Partners", email="pat@acme.example", campaign_id="camp-1")
    ids = await submit_partner(sub, crm)
    assert ("a-p", {"cCompanyType": ["Partner"]}) in crm.updated("Account")
    assert ("c-p", {"cContactType": ["Partner"]}) in crm.updated("Contact")
    profile, = crm.created(PARTNER_PROFILE)
    assert profile["outreachCampaignId"] == "camp-1"
    assert "Arrived through the campaign Spring postcards." in profile["description"]
    assert ids["campaignId"] == "camp-1"


@pytest.mark.asyncio
async def test_sponsor_form_writes_the_campaign_on_new_records_and_the_profile():
    crm = _crm()
    sub = _sponsor_app(campaign_id="camp-1")
    await submit_sponsor(sub, crm)
    company, = crm.created("Account")
    contact, = crm.created("Contact")
    profile, = crm.created(SPONSOR_PROFILE)
    assert company["cOutreachCampaignId"] == "camp-1" and contact["cOutreachCampaignId"] == "camp-1"
    assert profile["outreachCampaignId"] == "camp-1"
    assert profile["description"].endswith("Arrived through the campaign Spring postcards.")
    assert sub.message.strip() in profile["description"]


# --- the three readers take the union ----------------------------------------------------------

@pytest.mark.asyncio
async def test_popup_detail_names_every_referring_partner_single_first():
    from assignments import service as assignments
    from tests.test_assignments import FakeClient

    client = FakeClient(
        engagement={"referringPartnerId": "p-link", "referringPartnerName": "Link Partner"},
        related={"list": [{"id": "p-camp", "name": "Campaign Partner"}, {"id": "p-link", "name": "Link Partner"}]},
    )
    detail = await assignments.get_engagement_detail(client, "E1")
    assert detail["referringPartner"] == {"id": "p-link", "name": "Link Partner"}
    assert detail["referringPartners"] == [{"id": "p-link", "name": "Link Partner"},
                                           {"id": "p-camp", "name": "Campaign Partner"}]


@pytest.mark.asyncio
async def test_popup_detail_survives_a_crm_without_the_many_link():
    from assignments import service as assignments
    from tests.test_assignments import FakeClient

    class NoLink(FakeClient):
        async def list_related(self, *a, **k):
            raise EspoError("list_related failed: 404 Not Found")

    detail = await assignments.get_engagement_detail(NoLink(engagement={"referringPartnerId": "p1", "referringPartnerName": "P"}), "E1")
    assert detail["referringPartners"] == [{"id": "p1", "name": "P"}]


@pytest.mark.asyncio
async def test_analytics_partner_referrals_count_the_union_once():
    from analytics import records
    from analytics.registry import MetricContext

    class Espo:
        def __init__(self):
            self.rows = [
                {"id": "e1", "referringPartnerId": "P1", "createdAt": "2026-01-05 10:00:00"},
                {"id": "e2", "referringPartnerId": "P2", "createdAt": "2026-02-05 10:00:00"},
            ]
            self.many = [{"id": "e1", "createdAt": "2026-01-05 10:00:00"},
                         {"id": "e3", "createdAt": "2026-03-05 10:00:00"}]

        async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
            rows = [r for r in self.rows if all(r.get(c["attribute"]) == c["value"] for c in where or [])]
            return {"total": len(rows), "list": rows[offset:offset + max_size]}

        async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
            assert (entity, record_id, link) == ("CPartnerProfile", "P1", "referredEngagements")
            return {"list": list(self.many)}

    ctx = MetricContext(settings=None, espo=Espo())
    rows = await records._referred_engagements(ctx, "P1", "createdAt")
    assert [r["id"] for r in rows] == ["e1", "e3"]


# --- the Responses tab -----------------------------------------------------------------------

def test_responses_summary_counts_responded_and_converted():
    rows = [
        {"id": "s1", "form_slug": "client-intake", "status": "completed", "received_at": None,
         "result": {"engagementId": "E1", "campaignId": "camp-1"}},
        {"id": "s2", "form_slug": "info-request", "status": "completed", "received_at": None,
         "result": {"informationRequestId": "I1"}},
        {"id": "s3", "form_slug": "prospect-response", "status": "pending", "received_at": None, "result": None},
        {"id": "s4", "form_slug": "partner", "status": "held_honeypot", "received_at": None,
         "result": {"partnerProfileId": "P1"}},
        {"id": "s5", "form_slug": "event-registration", "status": "completed", "received_at": None,
         "result": {"eventRegistrationId": "R1", "eventId": "EV1"}},
    ]
    out = summarize_responses(rows)
    assert out["responded"] == 4 and out["converted"] == 1
    assert out["totals"] == {"client-intake": 1, "info-request": 1, "prospect-response": 1, "event-registration": 1}
    by_id = {r["id"]: r for r in out["responses"]}
    assert by_id["s1"]["converted"] is True and by_id["s1"]["records"] == {"engagementId": "E1", "campaignId": "camp-1"}
    assert by_id["s5"]["records"] == {"eventRegistrationId": "R1", "eventId": "EV1"}
    assert by_id["s4"]["converted"] is False


def test_responses_tab_links_through_to_each_record_and_the_admin_apps_take_the_deep_link():
    js = (ROOT / "campaigns" / "frontend" / "app.js").read_text(encoding="utf-8")
    assert '"/assignments/?engagement=" + encodeURIComponent(ids.engagementId)' in js
    assert '"/events/?event=" + encodeURIComponent(ids.eventId)' in js
    assert '"/partnersessions/record/"' in js and '"/sponsorsessions/record/"' in js
    assert '"Responded", r.responded' in js and '"Converted", r.converted' in js
    assignments_js = (ROOT / "assignments" / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'get("engagement")' in assignments_js and "openDetail(wanted)" in assignments_js
    events_js = (ROOT / "events" / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'get("event")' in events_js and "openEvent(wanted)" in events_js


def test_popup_band_renders_every_partner():
    js = (ROOT / "assignments" / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "setReferralBand(d.referringPartner, false, d.referringPartners)" in js
    assert "function setReferralBand(partner, loading, partners)" in js


# --- the programme page's carry-through and the Submission Admin filter ------------------------

def test_programme_page_carries_the_campaign_to_every_event_address():
    renderer = (ROOT / "wp-plugin" / "cbm-events" / "assets" / "cbm-events.js").read_text(encoding="utf-8")
    assert "eventUrlQuery" in renderer and 'eventUrlQuery: ""' in renderer
    public = (ROOT / "events" / "public_frontend" / "public.js").read_text(encoding="utf-8")
    assert "window.CBMEvents.config.eventUrlQuery = campaignQuery();" in public
    assert 'campaignParam("campaign")' in public and 'campaignParam("link")' in public


def test_submission_admin_filter_lists_the_two_newer_form_kinds():
    js = (ROOT / "ops" / "frontend" / "app.js").read_text(encoding="utf-8")
    forms_line = js[js.index("var FORMS = ["):js.index("];", js.index("var FORMS = ["))]
    assert '"event-registration"' in forms_line and '"prospect-response"' in forms_line


# --- through the worker's delivery wrapper (v0.259.1) ---------------------------------------

@pytest.mark.asyncio
async def test_the_campaign_survives_the_worker_delivery_wrapper():
    """The worker delivers through core.resumable.ResumableClient. It must pass
    the attribution's metadata and list_related reads through, or every check
    fails closed and the campaign is dropped (found on the Phase 2 live pass)."""
    from core.resumable import ResumableClient

    crm = _crm()
    crm.add("CPartnerProfile", {"id": "p-a", "name": "Alpha Partners"})
    crm.link("COutreachCampaign", "camp-1", "partnerProfiles", "p-a")
    wrapped = ResumableClient(crm, None, None)
    ids = await submit_intake(_submission(campaign_id="camp-1"), wrapped)
    eng, = crm.created(ENGAGEMENT)
    assert eng["outreachCampaignId"] == "camp-1"
    assert ids["referringPartnerIds"] == ["p-a"]


def test_the_delivery_wrapper_exposes_every_read_the_attribution_uses():
    from core.resumable import ResumableClient
    for name in ("metadata", "metadata_enum_options", "list_related", "list", "get", "find_one", "relate", "update", "create"):
        assert callable(getattr(ResumableClient, name, None)), name
