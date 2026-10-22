"""What a public form does with a campaign id and a lead id at delivery
(prds/prospect-marketing/build-plan.md § 5 — Phase 2, "the public forms honour
the ids"). Shared by the five orchestrators so the rules live once:

* **Validate-or-drop** (§ 5 step 1, the ``_valid_referring_partner`` precedent
  in ``forms/client_intake/orchestrator.py``): the ids arrive from a public
  address, so an unknown, stale or forged value — or a CRM that does not carry
  the link yet — drops the attribution with a logged note and never the
  submission.
* **The campaign lands on the relationship record every time, and on the
  Contact and the Company only when THIS submission created them**
  (ruling 27). The relationship records' link is ``outreachCampaign``; on the
  two native entities the stored name is ``cOutreachCampaign``.
* **The lead's converted Company is used by id before any name match**
  (§ 5 step 3), so the business a landing page converted is not matched a
  second time into a same-named stranger.
* **Every new record from a public form has a lead behind it** (ruling 48,
  :func:`record_lead`): a lead the form named is Converted and linked; else,
  when this submission created the Company or the Contact, a lead is created
  Converted at once, its Lead Source the form. A repeat submitter gets none.
* **The stage is evidence, advance-only** (§ 1.8): an information request or
  a registration puts a person on Engaged (rulings 17, 50); nothing ever lowers
  a stage and nothing is written on a record that has no stage field — nor on
  one that already holds a relationship type (ruling 37: the stages are for
  prospects; a client's position is read from the engagement).
* **A notes line names the campaign** (step 8), because an application write
  and a hand edit are indistinguishable in the CRM history.

Every write here is best-effort: it reports through the result and the log,
never by raising, so a classification can never cost the lead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.crm_upsert import COMPANY_TYPE_FIELD, CONTACT_TYPE_FIELD, RELATIONSHIP_TYPES
from core.espo import EspoApi, EspoError

from . import config as cfg
from .service import advance_stage

log = logging.getLogger("cbm_intake.campaigns.attribution")

#: The many-to-one link from a relationship record to its campaign (§ 1.5) and
#: the attribute a create or update writes it through.
CAMPAIGN_LINK = "outreachCampaign"
CAMPAIGN_FK = "outreachCampaignId"
#: The same link on Contact and Account — a custom link on a native entity
#: carries the ``c`` prefix ([[espo-custom-prefix-rules]]).
NATIVE_CAMPAIGN_LINK = "cOutreachCampaign"
NATIVE_CAMPAIGN_FK = "cOutreachCampaignId"
#: The stage fields on Contact and Account (§ 1.6, § 1.8; ruling 50).
FUNNEL_STAGE = "cFunnelStage"
ENTRY_STAGE = "cEntryStage"
#: The engagement's many-to-many to every referring partner (ruling 30).
REFERRING_PARTNERS_LINK = "referringPartners"

#: What a public form reads of the lead it was handed.
PROSPECT_SELECT = (
    "id,name,businessName,leadStatus,promotedCompanyId,promotedContactId,website"
)

ARRIVAL_NOTE = "Arrived through the campaign {name}."
PARTNERS_NOTE = "Referring partners set from the campaign {name}: {names}."


@dataclass
class Attribution:
    """The validated ids one submission carried, or nothing."""

    campaign: Optional[dict[str, Any]] = None   # {"id", "name"}
    prospect: Optional[dict[str, Any]] = None   # a PROSPECT_SELECT read
    #: The Contact a lead code named when no lead stands behind it (§ 7d.1:
    #: a Contact with no lead holds the code alone).
    contact_id: Optional[str] = None
    #: What the form did with them, for the delivery result.
    written: dict[str, Any] = field(default_factory=dict)

    @property
    def campaign_id(self) -> Optional[str]:
        return (self.campaign or {}).get("id") or None

    @property
    def campaign_name(self) -> str:
        c = self.campaign or {}
        return c.get("name") or c.get("id") or ""

    @property
    def promoted_company_id(self) -> Optional[str]:
        return (self.prospect or {}).get("promotedCompanyId") or None

    def note(self) -> Optional[str]:
        """The relationship record's notes line, or None without a campaign."""
        return ARRIVAL_NOTE.format(name=self.campaign_name) if self.campaign else None

    def result(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.campaign:
            out["campaignId"] = self.campaign["id"]
        if self.prospect:
            out["prospectId"] = self.prospect["id"]
        if self.contact_id and not self.prospect:
            out["leadContactId"] = self.contact_id
        out.update(self.written)
        return out


# --- feature detection -------------------------------------------------------------

async def link_available(client: EspoApi, entity: str, link: str) -> bool:
    """Whether this CRM has ``entity.link``. Fails CLOSED — an unreadable
    answer is "no", so a CRM without the Phase 1 change (production until its
    Sunday slot) drops the attribution instead of 400ing the create."""
    try:
        links = await client.metadata(f"entityDefs.{entity}.links")
    except Exception as exc:  # noqa: BLE001 — a metadata failure is "not available"
        log.warning("could not read %s links (%s) — campaign attribution dropped", entity, exc)
        return False
    return isinstance(links, dict) and link in links


async def prospect_type_available(client: EspoApi) -> bool:
    """Whether ``Prospect`` is a live option of ``Account.cCompanyType``
    (added by the Phase 1 handoff). EspoCRM refuses an unknown multiEnum value
    outright, so a form writes it only when the option exists."""
    try:
        options = await client.metadata_enum_options(cfg.ACCOUNT, "cCompanyType")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read Account.cCompanyType options (%s)", exc)
        return False
    return bool(options) and cfg.COMPANY_TYPE_PROSPECT in options


async def rung_available(client: EspoApi, entity: str) -> bool:
    """Whether ``entity`` (Contact or Account) carries the stage field WITH
    the lead model's stages (ruling 50). Fails closed: a CRM without the field,
    or one whose options are still the old ladder (production until its
    Sunday slot), gets no stage write — EspoCRM refuses an unknown enum value
    outright, so writing *Engaged* there would 400 the whole create."""
    try:
        fields = await client.metadata(f"entityDefs.{entity}.fields")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s fields (%s) — no stage written", entity, exc)
        return False
    if not isinstance(fields, dict) or not isinstance(fields.get(FUNNEL_STAGE), dict):
        return False
    options = fields[FUNNEL_STAGE].get("options") or []
    if not all(s in options for s in cfg.STAGES):
        log.info("%s.%s lacks the lead model's stages — no stage written", entity, FUNNEL_STAGE)
        return False
    return True


# --- validate-or-drop ----------------------------------------------------------------

async def valid_campaign(client: EspoApi, campaign_id: Optional[str], *, entity: str) -> Optional[dict[str, Any]]:
    """The campaign (id + name) when ``campaign_id`` names a real, uncancelled
    ``COutreachCampaign`` AND ``entity`` carries the link to write it on; else
    None, with the reason logged. Never raises."""
    if not campaign_id:
        return None
    if not await link_available(client, entity, CAMPAIGN_LINK):
        log.warning("campaign %r dropped: %s has no %s link on this CRM", campaign_id, entity, CAMPAIGN_LINK)
        return None
    try:
        row = await client.get(cfg.CAMPAIGN, campaign_id, select="id,name,campaignStatus")
    except Exception as exc:  # noqa: BLE001 — an optional attribution never blocks
        log.warning("campaign %r not usable (%s) — dropped", campaign_id, exc)
        return None
    if not row or not row.get("id"):
        return None
    if row.get("campaignStatus") == cfg.STATUS_CANCELLED:
        log.warning("campaign %r is cancelled — attribution dropped", campaign_id)
        return None
    return {"id": row["id"], "name": row.get("name") or ""}


async def valid_prospect(client: EspoApi, prospect_id: Optional[str]) -> Optional[dict[str, Any]]:
    """The lead when ``prospect_id`` names a real ``CProspect``,
    else None. Never raises."""
    if not prospect_id:
        return None
    try:
        row = await client.get(cfg.PROSPECT, prospect_id, select=PROSPECT_SELECT)
    except Exception as exc:  # noqa: BLE001
        log.warning("lead %r not usable (%s) — dropped", prospect_id, exc)
        return None
    return row if row and row.get("id") else None


async def valid_lead(client: EspoApi, sub: Any) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """The lead a submission names, and the Contact when a code names a
    Contact with no lead behind it. The lead code (§ 7d.3) first; the CRM id
    ``prospect_id`` only when no code came (a submission captured before
    D1, kept for one release). Validate-or-drop: an unknown code is dropped
    with a logged note, never the submission. Never raises."""
    from . import leadcode

    code = getattr(sub, cfg.PAYLOAD_LEAD_CODE, None)
    if code:
        person = await leadcode.resolve(client, code)
        if person is None:
            log.warning("lead code dropped: it names nobody on this CRM")
            return None, None
        lead = await valid_prospect(client, person.lead_id) if person.lead_id else None
        return lead, (None if lead else person.contact_id)
    return await valid_prospect(client, getattr(sub, "prospect_id", None)), None


async def resolve(client: EspoApi, sub: Any, *, entity: str) -> Attribution:
    """Validate what the submission carried. ``entity`` is the relationship
    record this form creates — the one whose ``outreachCampaign`` link must
    exist for the campaign to be honoured. A lead code with no campaign (a
    retired link re-minted, a code typed by hand) still attributes to the
    lead (§ 7d.4)."""
    campaign = await valid_campaign(client, getattr(sub, "campaign_id", None), entity=entity)
    prospect, contact_id = await valid_lead(client, sub)
    return Attribution(campaign=campaign, prospect=prospect, contact_id=contact_id)


# --- the promoted company ---------------------------------------------------------------

async def promoted_company(client: EspoApi, attr: Attribution, *, select: str) -> Optional[dict[str, Any]]:
    """The Company the lead was converted to, read as the form's
    company match would read it, or None (no prospect, no promotion, or the
    record is gone — then the form falls back to its name match)."""
    company_id = attr.promoted_company_id
    if not company_id:
        return None
    try:
        row = await client.get(cfg.ACCOUNT, company_id, select=select)
    except Exception as exc:  # noqa: BLE001
        log.warning("promoted company %s of prospect %s not readable (%s) — name match instead",
                    company_id, attr.prospect.get("id") if attr.prospect else "?", exc)
        return None
    return row if row and row.get("id") else None


# --- the writes -------------------------------------------------------------------------

def stamp_new(payload: dict[str, Any], attr: Attribution, *, stage: Optional[str] = None) -> dict[str, Any]:
    """Add to a Contact or Company CREATE payload what a record this
    submission creates carries: the campaign (ruling 27) and, when the form
    has stage evidence, the funnel and entry stage (§ 1.8 — the entry stage is
    written once, here). Returns the payload for chaining."""
    if attr.campaign:
        payload[NATIVE_CAMPAIGN_FK] = attr.campaign["id"]
    if stage:
        payload[FUNNEL_STAGE] = stage
        payload[ENTRY_STAGE] = stage
    return payload


def holds_relationship(record: dict[str, Any]) -> bool:
    """True when the record's Contact or Company type already holds Client,
    Partner, Sponsor or Mentor (ruling 37)."""
    for type_field in (CONTACT_TYPE_FIELD, COMPANY_TYPE_FIELD):
        if RELATIONSHIP_TYPES.intersection(record.get(type_field) or []):
            return True
    return False


async def advance_rung(client: EspoApi, entity: str, record: dict[str, Any], proposed: str) -> Optional[str]:
    """Advance-only: write ``proposed`` to the record's ``cFunnelStage`` when it
    is later on the ladder than the stored value (read with ``cFunnelStage``
    selected). Best-effort. Returns the stage written, or None.

    Ruling 37: a record whose type field (``cContactType`` / ``cCompanyType``,
    which the caller must select) already holds a relationship type is left
    alone — the ladder is for prospects only."""
    if holds_relationship(record):
        return None
    new = advance_stage(record.get(FUNNEL_STAGE), proposed)
    if not new or not record.get("id"):
        return None
    try:
        await client.update(entity, record["id"], {FUNNEL_STAGE: new})
    except EspoError as exc:
        log.warning("could not advance %s/%s to %s: %s", entity, record.get("id"), new, exc)
        return None
    return new


async def lead_model_available(client: EspoApi) -> bool:
    """Whether this CRM carries ``CProspect.leadStatus`` (the lead-model
    handoff). Fails closed: no lead is written on a CRM without it."""
    try:
        fields = await client.metadata(f"entityDefs.{cfg.PROSPECT}.fields")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s fields (%s) — no lead written", cfg.PROSPECT, exc)
        return False
    return isinstance(fields, dict) and "leadStatus" in fields and "leadSource" in fields


def _created_here(client: EspoApi, entity: str, record_id: Optional[str]) -> bool:
    if not record_id:
        return False
    created = getattr(client, "created_ids", None)
    return bool(created) and record_id in created(entity)


async def record_lead(client: EspoApi, attr: Attribution, *, source: str,
                      company_id: Optional[str] = None, contact_id: Optional[str] = None,
                      values: Optional[dict[str, Any]] = None) -> None:
    """Ruling 48, at the end of every public form's delivery.

    * The form named a lead (``prospect_id``): it is **Converted** and its
      *Converted to company / contact* links are set when empty.
    * Otherwise, when THIS submission created the Company or the Contact, a lead
      is created **Converted at once**, its Lead Source ``source``, linked to
      what was created. A repeat submitter whose records already existed gets
      no lead. "Created here" is read from the delivery's recorded creates, so
      a retry decides exactly as the first run did, and the lead's own create
      is keyed like every other — retry-safe.

    Best-effort: a failure is logged and reported, never raised, so a lead can
    never cost the submission. Feature-detected (:func:`lead_model_available`)."""
    try:
        if not await lead_model_available(client):
            return
        from .conversion import mark_converted
        if attr.prospect:
            lead = attr.prospect
            fill = await mark_converted(client, lead, company_id=company_id, contact_id=contact_id)
            if fill:
                attr.written["leadConverted"] = sorted(fill)
            return
        company_new = _created_here(client, cfg.ACCOUNT, company_id)
        contact_new = _created_here(client, cfg.CONTACT, contact_id)
        if not (company_new or contact_new):
            return
        v = values or {}
        business = (v.get("businessName") or "").strip()
        person = " ".join(x for x in ((v.get("firstName") or "").strip(), (v.get("lastName") or "").strip()) if x)
        payload: dict[str, Any] = {
            "name": (business or person or v.get("email") or source)[:255],
            "businessName": business[:255] or None,
            "firstName": (v.get("firstName") or "")[:100] or None,
            "lastName": (v.get("lastName") or "")[:100] or None,
            "email": (v.get("email") or "") or None,
            "website": (v.get("website") or "") or None,
            "phone": (v.get("phone") or "") or None,
            "leadStatus": cfg.LEAD_CONVERTED,
            "leadStatusChangedAt": _now_crm(),
            "leadSource": source,
            "promotedCompanyId": company_id if company_new else None,
            "promotedContactId": contact_id if contact_new else None,
        }
        created = await client.create(cfg.PROSPECT, {k: val for k, val in payload.items() if val})
        attr.written["leadId"] = created.get("id")
    except EspoError as exc:
        log.warning("the lead behind this %s submission was not written: %s", source, exc)
        attr.written["leadWarning"] = f"The lead was not recorded ({exc})."


def lead_values(sub: Any) -> dict[str, Any]:
    """What a public form's submission says about the business and the person,
    in the lead's words, whatever the form calls its fields."""
    def g(*names: str) -> str:
        for n in names:
            v = getattr(sub, n, None)
            if v:
                return str(v).strip()
        return ""
    return {"businessName": g("business_name", "company"), "website": g("business_website", "website"),
            "firstName": g("first_name"), "lastName": g("last_name"), "email": g("email"),
            "phone": g("phone")}


def _now_crm() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def campaign_partners(client: EspoApi, attr: Attribution) -> list[dict[str, Any]]:
    """The partners the campaign names (CM-4), id and name, in name order; []
    without a campaign or when unreadable (logged)."""
    if not attr.campaign:
        return []
    try:
        data = await client.list_related(cfg.CAMPAIGN, attr.campaign["id"], cfg.LINK_PARTNERS,
                                         select="id,name", max_size=200)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read the partners of campaign %s (%s) — none related", attr.campaign["id"], exc)
        return []
    rows = [{"id": r["id"], "name": r.get("name") or r["id"]} for r in data.get("list", []) if r.get("id")]
    rows.sort(key=lambda r: (r["name"] or "").lower())
    return rows


def partners_note(attr: Attribution, partners: list[dict[str, Any]]) -> Optional[str]:
    if not attr.campaign or not partners:
        return None
    return PARTNERS_NOTE.format(name=attr.campaign_name, names=", ".join(p["name"] for p in partners))


async def relate_referring_partners(client: EspoApi, engagement_id: str,
                                    partner_ids: list[str]) -> list[str]:
    """Relate every id on ``CEngagement.referringPartners`` (ruling 30), each
    best-effort, when the CRM has the link. Returns the ids related."""
    ids = list(dict.fromkeys(i for i in partner_ids if i))
    if not ids:
        return []
    if not await link_available(client, "CEngagement", REFERRING_PARTNERS_LINK):
        log.warning("CEngagement has no %s link on this CRM — %d referring partner(s) not related",
                    REFERRING_PARTNERS_LINK, len(ids))
        return []
    done: list[str] = []
    for pid in ids:
        try:
            await client.relate("CEngagement", engagement_id, REFERRING_PARTNERS_LINK, pid)
            done.append(pid)
        except EspoError as exc:
            log.warning("could not relate partner %s to engagement %s: %s", pid, engagement_id, exc)
    return done



async def opportunity_on_attendance(api_client: EspoApi, registration_id: str) -> Optional[str]:
    """Build plan § 6: attendance recorded on a registration whose Contact is
    typed Prospect moves the Contact to Opportunity — advance-only, never on a
    record holding a relationship type (ruling 37), whatever the attendance
    source (a manual mark, a door check-in or the Zoom pull). Under the
    org-wide API client: the Marketing Admin Role does not edit Contacts.
    Best-effort; returns the stage written, or None."""
    try:
        reg = await api_client.get("CEventRegistration", registration_id, select="id,contactId,attendanceStatus")
        if not reg or reg.get("attendanceStatus") != "Attended" or not reg.get("contactId"):
            return None
        if not await rung_available(api_client, "Contact"):
            return None
        contact = await api_client.get("Contact", reg["contactId"],
                                       select=f"id,cContactType,{FUNNEL_STAGE}")
    except EspoError as exc:
        log.warning("opportunity on attendance: registration %s unreadable: %s", registration_id, exc)
        return None
    if not contact or "Prospect" not in (contact.get("cContactType") or []):
        return None
    return await advance_rung(api_client, "Contact", contact, cfg.STAGE_OPPORTUNITY)
