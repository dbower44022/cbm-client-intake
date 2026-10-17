"""What a public door does with a campaign id and a prospect id at delivery
(prds/prospect-marketing/build-plan.md § 5 — Phase 2, "the doors honour the
ids"). Shared by the five orchestrators so the rules live once:

* **Validate-or-drop** (§ 5 step 1, the ``_valid_referring_partner`` precedent
  in ``forms/client_intake/orchestrator.py``): the ids arrive from a public
  address, so an unknown, stale or forged value — or a CRM that does not carry
  the link yet — drops the attribution with a logged note and never the
  submission.
* **The campaign lands on the relationship record every time, and on the
  Contact and the Company only when THIS submission created them**
  (ruling 27). The relationship records' link is ``outreachCampaign``; on the
  two native entities the stored name is ``cOutreachCampaign``.
* **The prospect record's promoted Company is used by id before any name
  match** (§ 5 step 3), so the business the landing page promoted is not
  matched a second time into a same-named stranger; its promotion links are
  set if empty (step 4) and its stage stops changing.
* **The rung is evidence, advance-only** (§ 1.8): an information request or a
  registration puts a person on Warm Lead (ruling 17); nothing ever lowers a
  rung and nothing is written on a record that has no stage field.
* **A notes line names the campaign** (step 8), because an application write
  and a hand edit are indistinguishable in the CRM history.

Every write here is best-effort: it reports through the result and the log,
never by raising, so a classification can never cost the lead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

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
#: The rung fields on Contact and Account (§ 1.6, § 1.8).
FUNNEL_STAGE = "cFunnelStage"
ENTRY_STAGE = "cEntryStage"
#: The engagement's many-to-many to every referring partner (ruling 30).
REFERRING_PARTNERS_LINK = "referringPartners"

#: What a door reads of the prospect record it was handed.
PROSPECT_SELECT = (
    "id,name,businessName,funnelStage,entryStage,promotedCompanyId,promotedContactId,website"
)

ARRIVAL_NOTE = "Arrived through the campaign {name}."
PARTNERS_NOTE = "Referring partners set from the campaign {name}: {names}."


@dataclass
class Attribution:
    """The validated ids one submission carried, or nothing."""

    campaign: Optional[dict[str, Any]] = None   # {"id", "name"}
    prospect: Optional[dict[str, Any]] = None   # a PROSPECT_SELECT read
    #: What the door did with them, for the delivery result.
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
    outright, so a door writes it only when the option exists."""
    try:
        options = await client.metadata_enum_options(cfg.ACCOUNT, "cCompanyType")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read Account.cCompanyType options (%s)", exc)
        return False
    return bool(options) and cfg.COMPANY_TYPE_PROSPECT in options


async def rung_available(client: EspoApi, entity: str) -> bool:
    """Whether ``entity`` (Contact or Account) carries the funnel-stage field.
    Fails closed, so a CRM without the Phase 1 change gets no rung writes."""
    try:
        fields = await client.metadata(f"entityDefs.{entity}.fields")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s fields (%s) — no rung written", entity, exc)
        return False
    return isinstance(fields, dict) and FUNNEL_STAGE in fields


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
    """The prospect record when ``prospect_id`` names a real ``CProspect``,
    else None. Never raises."""
    if not prospect_id:
        return None
    try:
        row = await client.get(cfg.PROSPECT, prospect_id, select=PROSPECT_SELECT)
    except Exception as exc:  # noqa: BLE001
        log.warning("prospect record %r not usable (%s) — dropped", prospect_id, exc)
        return None
    return row if row and row.get("id") else None


async def resolve(client: EspoApi, sub: Any, *, entity: str) -> Attribution:
    """Validate what the submission carried. ``entity`` is the relationship
    record this door creates — the one whose ``outreachCampaign`` link must
    exist for the campaign to be honoured."""
    campaign = await valid_campaign(client, getattr(sub, "campaign_id", None), entity=entity)
    prospect = await valid_prospect(client, getattr(sub, "prospect_id", None))
    return Attribution(campaign=campaign, prospect=prospect)


# --- the promoted company ---------------------------------------------------------------

async def promoted_company(client: EspoApi, attr: Attribution, *, select: str) -> Optional[dict[str, Any]]:
    """The Company the prospect record was promoted to, read as the door's
    company match would read it, or None (no prospect, no promotion, or the
    record is gone — then the door falls back to its name match)."""
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
    submission creates carries: the campaign (ruling 27) and, when the door
    has rung evidence, the funnel and entry stage (§ 1.8 — the entry stage is
    written once, here). Returns the payload for chaining."""
    if attr.campaign:
        payload[NATIVE_CAMPAIGN_FK] = attr.campaign["id"]
    if stage:
        payload[FUNNEL_STAGE] = stage
        payload[ENTRY_STAGE] = stage
    return payload


async def advance_rung(client: EspoApi, entity: str, record: dict[str, Any], proposed: str) -> Optional[str]:
    """Advance-only: write ``proposed`` to the record's ``cFunnelStage`` when it
    is later on the ladder than the stored value (read with ``cFunnelStage``
    selected). Best-effort. Returns the rung written, or None."""
    new = advance_stage(record.get(FUNNEL_STAGE), proposed)
    if not new or not record.get("id"):
        return None
    try:
        await client.update(entity, record["id"], {FUNNEL_STAGE: new})
    except EspoError as exc:
        log.warning("could not advance %s/%s to %s: %s", entity, record.get("id"), new, exc)
        return None
    return new


async def link_promotion(client: EspoApi, attr: Attribution, *, contact_id: Optional[str] = None,
                         company_id: Optional[str] = None) -> None:
    """Set the prospect record's ``promotedContact`` / ``promotedCompany`` when
    empty (§ 5 step 4). Nothing else on the record changes — its stage stops at
    promotion. Best-effort."""
    prospect = attr.prospect
    if not prospect:
        return
    fill: dict[str, Any] = {}
    if contact_id and not prospect.get("promotedContactId"):
        fill["promotedContactId"] = contact_id
    if company_id and not prospect.get("promotedCompanyId"):
        fill["promotedCompanyId"] = company_id
    if not fill:
        return
    try:
        await client.update(cfg.PROSPECT, prospect["id"], fill)
        attr.written["prospectLinked"] = sorted(fill)
    except EspoError as exc:
        log.warning("could not link prospect record %s to its promoted records (%s)", prospect["id"], exc)


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
