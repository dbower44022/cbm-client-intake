"""Partner and funder associations — one rule, every writer.

prds/partner-association-plan.md (Doug's rulings 10-28-26). A partner or funder
is associated with a business when it referred the business to CBM, when
someone from the business attended its event, or when a mentor referred the
business to it. The association is held by the **company** — "that partner will
be associated with that company, and all of their related contacts forever" —
or by the person or the lead until there is a company, then it moves to the
company and stays. A second partner or funder is a second association; the
application never deletes one.

Every write goes through :func:`associate` under the org-wide API key (the CRM
grants only the application's role create and edit). Each is best-effort: a
failure is a log line, never a failed save, intake or import. Nothing here runs
until the CRM has ``CPartnerAssociation`` (:func:`available`), so a CRM without
the change behaves exactly as before.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from core.espo import EspoApi, EspoError

log = logging.getLogger("cbm_intake.partner_links")

ENTITY = "CPartnerAssociation"
PARTNER = "CPartnerProfile"
FUNDER = "CSponsorProfile"
REASON_REFERRED_TO = "Referred to CBM"
REASON_ATTENDED = "Attended an event"
REASON_REFERRED_BY = "Referred by CBM"
REASONS = (REASON_REFERRED_TO, REASON_ATTENDED, REASON_REFERRED_BY)
#: An event's partners and funders (events/config.py EventLink).
EVENT_PARTNERS = "partnerProfiles"
EVENT_FUNDERS = "sponsorProfiles"
#: The registration's company when the person registered.
REG_COMPANY = "registrationCompanyId"
SELECT = ("id,name,reason,associatedAt,partnerProfileId,partnerProfileName,sponsorProfileId,"
          "sponsorProfileName,companyId,companyName,contactId,contactName,leadId,eventId,eventName,engagementId")
PAGE = 200
_ID_BATCH = 80


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def available(client: EspoApi) -> bool:
    """Whether this CRM has the association entity. Fails closed."""
    try:
        fields = await client.metadata(f"entityDefs.{ENTITY}.fields")
    except Exception:  # noqa: BLE001 — unreadable is "not here"
        return False
    return isinstance(fields, dict) and "reason" in fields


async def registration_company_available(client: EspoApi) -> bool:
    try:
        links = await client.metadata("entityDefs.CEventRegistration.links")
    except Exception:  # noqa: BLE001
        return False
    return isinstance(links, dict) and "registrationCompany" in links


async def _name_of(client: EspoApi, entity: str, record_id: str) -> str:
    try:
        row = await client.get(entity, record_id, select="id,name")
        return (row or {}).get("name") or ""
    except EspoError:
        return ""


async def associate(client: EspoApi, *, reason: str, partner_id: Optional[str] = None,
                    funder_id: Optional[str] = None, company_id: Optional[str] = None,
                    contact_id: Optional[str] = None, lead_id: Optional[str] = None,
                    event_id: Optional[str] = None, engagement_id: Optional[str] = None,
                    at: Optional[str] = None, check: bool = True) -> Optional[str]:
    """One association, written once. Held by the company when there is one,
    else the contact, else the lead; the contact and lead are kept as who
    carried it. The same (partner or funder, holder, reason, event) is never
    written twice — a repeat fills in a company or person it lacked. Returns the
    record's id, or None when nothing could be written. Never raises."""
    if reason not in REASONS or bool(partner_id) == bool(funder_id) or not (company_id or contact_id or lead_id):
        return None
    try:
        if check and not await available(client):
            return None
        org_field, org_id, org_entity = (("partnerProfileId", partner_id, PARTNER) if partner_id
                                         else ("sponsorProfileId", funder_id, FUNDER))
        where: list[dict[str, Any]] = [
            {"type": "equals", "attribute": org_field, "value": org_id},
            {"type": "equals", "attribute": "reason", "value": reason},
            ({"type": "equals", "attribute": "eventId", "value": event_id} if event_id
             else {"type": "isNull", "attribute": "eventId"}),
        ]
        if company_id:
            where.append({"type": "equals", "attribute": "companyId", "value": company_id})
        elif contact_id:
            where.append({"type": "equals", "attribute": "contactId", "value": contact_id})
        else:
            where.append({"type": "equals", "attribute": "leadId", "value": lead_id})
        found = (await client.list(ENTITY, where=where, select="id,companyId,contactId,leadId,engagementId",
                                   max_size=1)).get("list") or []
        if found:
            row = found[0]
            fill = {k: v for k, v in (("companyId", company_id), ("contactId", contact_id),
                                      ("leadId", lead_id), ("engagementId", engagement_id))
                    if v and not row.get(k)}
            if fill:
                await client.update(ENTITY, row["id"], fill)
            return row["id"]
        org_name = await _name_of(client, org_entity, org_id)
        payload = {
            "name": f"{org_name or ('Partner' if partner_id else 'Funder')} — {reason}"[:255],
            "reason": reason,
            "associatedAt": at or _now_crm(),
            org_field: org_id,
            "companyId": company_id, "contactId": contact_id, "leadId": lead_id,
            "eventId": event_id, "engagementId": engagement_id,
        }
        created = await client.create(ENTITY, {k: v for k, v in payload.items() if v})
        return created.get("id")
    except EspoError as exc:
        log.warning("partner association (%s, %s/%s) not written: %s", reason,
                    "partner" if partner_id else "funder", partner_id or funder_id, exc)
        return None


async def transfer(client: EspoApi, *, company_id: str, contact_id: Optional[str] = None,
                   lead_id: Optional[str] = None, person_id: Optional[str] = None) -> int:
    """Decision 2's move: every association a contact or lead held without a
    company gains ``company_id`` (and, from a lead, its person). Merge-only.
    Returns how many moved. Never raises."""
    if not company_id or not (contact_id or lead_id):
        return 0
    moved = 0
    try:
        for attr, value in (("contactId", contact_id), ("leadId", lead_id)):
            if not value:
                continue
            rows = (await client.list(ENTITY, where=[
                {"type": "equals", "attribute": attr, "value": value},
                {"type": "isNull", "attribute": "companyId"}], select="id,contactId", max_size=PAGE)).get("list") or []
            for row in rows:
                fill: dict[str, Any] = {"companyId": company_id}
                if person_id and not row.get("contactId"):
                    fill["contactId"] = person_id
                await client.update(ENTITY, row["id"], fill)
                moved += 1
    except EspoError as exc:
        log.warning("partner associations not moved to company %s: %s", company_id, exc)
    return moved


# --- the writers ----------------------------------------------------------------------

async def on_conversion(client: EspoApi, lead: dict[str, Any], *, company_id: Optional[str],
                        contact_id: Optional[str]) -> int:
    """A lead converted: its *Referred by partner* becomes an association on the
    company (else the person), and every association it held moves with it."""
    if not (company_id or contact_id) or not await available(client):
        return 0
    written = 0
    if lead.get("referredByPartnerId"):
        if await associate(client, reason=REASON_REFERRED_TO, partner_id=lead["referredByPartnerId"],
                           company_id=company_id, contact_id=contact_id, lead_id=lead.get("id"),
                           check=False):
            written += 1
    if company_id:
        written += await transfer(client, company_id=company_id, lead_id=lead.get("id"), person_id=contact_id)
    else:
        try:
            rows = (await client.list(ENTITY, where=[{"type": "equals", "attribute": "leadId", "value": lead.get("id")},
                                                     {"type": "isNull", "attribute": "contactId"}],
                                      select="id", max_size=PAGE)).get("list") or []
            for row in rows:
                await client.update(ENTITY, row["id"], {"contactId": contact_id})
                written += 1
        except EspoError as exc:
            log.warning("lead %s associations not moved to contact %s: %s", lead.get("id"), contact_id, exc)
    return written


async def on_intake(client: EspoApi, *, partner_ids: Iterable[str], company_id: str, contact_id: str,
                    engagement_id: Optional[str]) -> int:
    """A client applied through a partner's link, or a campaign naming partners:
    each partner is associated with the company."""
    ids = [p for p in dict.fromkeys(partner_ids) if p]
    if not ids or not await available(client):
        return 0
    n = 0
    for pid in ids:
        if await associate(client, reason=REASON_REFERRED_TO, partner_id=pid, company_id=company_id,
                           contact_id=contact_id, engagement_id=engagement_id, check=False):
            n += 1
    return n


async def company_of_contact(client: EspoApi, contact_id: str) -> Optional[str]:
    try:
        row = await client.get("Contact", contact_id, select="id,accountId")
        return (row or {}).get("accountId") or None
    except EspoError:
        return None


async def stamp_registration_company(client: EspoApi, registration_id: str, contact_id: Optional[str]) -> Optional[str]:
    """Decision 3: the registration records the company the person was with
    when they registered — written once, never changed after."""
    if not contact_id or not await registration_company_available(client):
        return None
    company = await company_of_contact(client, contact_id)
    if not company:
        return None
    try:
        await client.update("CEventRegistration", registration_id, {REG_COMPANY: company})
        return company
    except EspoError as exc:
        log.warning("registration %s company not recorded: %s", registration_id, exc)
        return None


async def event_orgs(client: EspoApi, event_id: str) -> tuple[list[str], list[str]]:
    """The event's partners and funders, by id. A CRM without a link yields none."""
    out: list[list[str]] = []
    for link in (EVENT_PARTNERS, EVENT_FUNDERS):
        try:
            rows = (await client.list_related("CEvent", event_id, link, select="id", max_size=PAGE)).get("list") or []
            out.append([r["id"] for r in rows if r.get("id")])
        except EspoError:
            out.append([])
    return out[0], out[1]


async def on_attendance(client: EspoApi, registration_id: str) -> int:
    """Decision 4: someone attended an event its partners and funders are on —
    each is associated with the company the person registered from (else
    their company now, else the person). Only *Attended*; a no-show writes
    nothing (decision 3)."""
    if not await available(client):
        return 0
    try:
        select = "id,contactId,eventId,attendanceStatus"
        if await registration_company_available(client):
            select += "," + REG_COMPANY
        reg = await client.get("CEventRegistration", registration_id, select=select)
    except EspoError as exc:
        log.warning("attendance association: registration %s unreadable: %s", registration_id, exc)
        return 0
    if not reg or reg.get("attendanceStatus") != "Attended" or not reg.get("eventId") or not reg.get("contactId"):
        return 0
    partners, funders = await event_orgs(client, reg["eventId"])
    if not (partners or funders):
        return 0
    company = reg.get(REG_COMPANY) or await company_of_contact(client, reg["contactId"])
    n = 0
    for pid in partners:
        if await associate(client, reason=REASON_ATTENDED, partner_id=pid, company_id=company,
                           contact_id=reg["contactId"], event_id=reg["eventId"], check=False):
            n += 1
    for fid in funders:
        if await associate(client, reason=REASON_ATTENDED, funder_id=fid, company_id=company,
                           contact_id=reg["contactId"], event_id=reg["eventId"], check=False):
            n += 1
    return n


async def on_mentor_referral(client: EspoApi, *, partner_id: str, engagement: dict[str, Any]) -> Optional[str]:
    """Decision 5: a mentor referred the client to a partner."""
    company = engagement.get("clientOrganizationId")
    contact = engagement.get("primaryEngagementContactId")
    if not await available(client):
        return None
    return await associate(client, reason=REASON_REFERRED_BY, partner_id=partner_id, company_id=company,
                           contact_id=contact, engagement_id=engagement.get("id"), check=False)


# --- the nightly move and the backfill ---------------------------------------------------

async def run_transfer_pass(client: EspoApi, *, cap: int = 2000) -> dict[str, int]:
    """Associations still held by a person or lead whose company now exists
    gain the company (decision 2) — whatever screen attached it. Merge-only."""
    summary = {"checked": 0, "moved": 0, "errors": 0}
    if not await available(client):
        return summary
    offset = 0
    while summary["checked"] < cap:
        try:
            page = (await client.list(ENTITY, where=[{"type": "isNull", "attribute": "companyId"}],
                                      select="id,contactId,leadId", max_size=PAGE, offset=offset)).get("list") or []
        except EspoError as exc:
            log.warning("partner association transfer pass: %s", exc)
            summary["errors"] += 1
            break
        if not page:
            break
        summary["checked"] += len(page)
        contact_ids = sorted({r["contactId"] for r in page if r.get("contactId")})
        lead_ids = sorted({r["leadId"] for r in page if r.get("leadId") and not r.get("contactId")})
        companies: dict[str, str] = {}
        leads: dict[str, dict[str, Any]] = {}
        try:
            for i in range(0, len(contact_ids), _ID_BATCH):
                rows = (await client.list("Contact", where=[{"type": "in", "attribute": "id",
                                                             "value": contact_ids[i:i + _ID_BATCH]}],
                                          select="id,accountId", max_size=PAGE)).get("list") or []
                companies.update({r["id"]: r["accountId"] for r in rows if r.get("accountId")})
            for i in range(0, len(lead_ids), _ID_BATCH):
                rows = (await client.list("CProspect", where=[{"type": "in", "attribute": "id",
                                                               "value": lead_ids[i:i + _ID_BATCH]}],
                                          select="id,promotedCompanyId,promotedContactId", max_size=PAGE)).get("list") or []
                leads.update({r["id"]: r for r in rows})
        except EspoError as exc:
            log.warning("partner association transfer pass: %s", exc)
            summary["errors"] += 1
            break
        moved_here = 0
        for r in page:
            fill: dict[str, Any] = {}
            if r.get("contactId") and companies.get(r["contactId"]):
                fill["companyId"] = companies[r["contactId"]]
            elif r.get("leadId") and leads.get(r["leadId"]):
                lead = leads[r["leadId"]]
                if lead.get("promotedCompanyId"):
                    fill["companyId"] = lead["promotedCompanyId"]
                if lead.get("promotedContactId"):
                    fill["contactId"] = lead["promotedContactId"]
            if not fill:
                continue
            try:
                await client.update(ENTITY, r["id"], fill)
                if "companyId" in fill:
                    moved_here += 1
            except EspoError as exc:
                log.warning("partner association %s not moved: %s", r["id"], exc)
                summary["errors"] += 1
        summary["moved"] += moved_here
        # Records that moved left the filter; the rest stay, so step past them.
        offset += len(page) - moved_here
        if len(page) < PAGE:
            break
    return summary


async def _all(client: EspoApi, entity: str, where: list[dict[str, Any]], select: str, cap: int = 5000):
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < cap:
        page = (await client.list(entity, where=where, select=select, max_size=PAGE, offset=offset)).get("list") or []
        out.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return out


async def plan_backfill(client: EspoApi) -> list[dict[str, Any]]:
    """The associations the records already imply, as associate() arguments:
    a lead's *Referred by partner*; an engagement's referring partners; an
    attended registration at an event with partners or funders. Read-only."""
    plan: list[dict[str, Any]] = []
    if not await available(client):
        return plan
    try:
        leads = await _all(client, "CProspect", [{"type": "isNotNull", "attribute": "referredByPartnerId"}],
                           "id,referredByPartnerId,promotedCompanyId,promotedContactId")
    except EspoError:
        leads = []
    for lead in leads:
        plan.append({"reason": REASON_REFERRED_TO, "partner_id": lead["referredByPartnerId"],
                     "company_id": lead.get("promotedCompanyId"), "contact_id": lead.get("promotedContactId"),
                     "lead_id": lead["id"], "why": "lead referred by partner"})
    try:
        engs = await _all(client, "CEngagement", [], "id,referringPartnerId,clientOrganizationId,primaryEngagementContactId")
    except EspoError:
        engs = []
    for eng in engs:
        partners = {eng["referringPartnerId"]} if eng.get("referringPartnerId") else set()
        try:
            rows = (await client.list_related("CEngagement", eng["id"], "referringPartners", select="id",
                                              max_size=PAGE)).get("list") or []
            partners.update(r["id"] for r in rows if r.get("id"))
        except EspoError:
            pass
        if not (eng.get("clientOrganizationId") or eng.get("primaryEngagementContactId")):
            continue
        for pid in sorted(partners):
            plan.append({"reason": REASON_REFERRED_TO, "partner_id": pid,
                         "company_id": eng.get("clientOrganizationId"),
                         "contact_id": eng.get("primaryEngagementContactId"),
                         "engagement_id": eng["id"], "why": "engagement's referring partner"})
    try:
        events = await _all(client, "CEvent", [], "id,name")
    except EspoError:
        events = []
    for ev in events:
        partners, funders = await event_orgs(client, ev["id"])
        if not (partners or funders):
            continue
        try:
            regs = await _all(client, "CEventRegistration",
                              [{"type": "equals", "attribute": "eventId", "value": ev["id"]},
                               {"type": "equals", "attribute": "attendanceStatus", "value": "Attended"}],
                              "id,contactId")
        except EspoError:
            regs = []
        for reg in regs:
            if not reg.get("contactId"):
                continue
            company = await company_of_contact(client, reg["contactId"])
            for pid in partners:
                plan.append({"reason": REASON_ATTENDED, "partner_id": pid, "company_id": company,
                             "contact_id": reg["contactId"], "event_id": ev["id"], "why": f"attended {ev.get('name')}"})
            for fid in funders:
                plan.append({"reason": REASON_ATTENDED, "funder_id": fid, "company_id": company,
                             "contact_id": reg["contactId"], "event_id": ev["id"], "why": f"attended {ev.get('name')}"})
    return plan


async def apply_backfill(client: EspoApi, plan: list[dict[str, Any]]) -> dict[str, int]:
    """Write the plan. Safe to run again: associate() never writes a tie twice."""
    done = {"planned": len(plan), "written": 0, "failed": 0}
    for item in plan:
        args = {k: v for k, v in item.items() if k != "why"}
        if await associate(client, check=False, **args):
            done["written"] += 1
        else:
            done["failed"] += 1
    return done


# --- the Operations job and the worker ---------------------------------------------------

def _client(settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


def plan_text(plan: list[dict[str, Any]]) -> str:
    """The backfill plan in words, deterministic (the job's fingerprint is
    taken from it): one line per tie, sorted, and a count per kind."""
    by_kind: dict[str, int] = {}
    lines = []
    for item in plan:
        kind = item["why"] if not item["why"].startswith("attended ") else "attended an event"
        by_kind[kind] = by_kind.get(kind, 0) + 1
        org = f"partner {item.get('partner_id')}" if item.get("partner_id") else f"funder {item.get('funder_id')}"
        holder = (f"company {item['company_id']}" if item.get("company_id")
                  else f"contact {item['contact_id']}" if item.get("contact_id") else f"lead {item.get('lead_id')}")
        lines.append(f"  {item['reason']}: {org} → {holder} ({item['why']})")
    head = [f"{len(plan)} association(s) the records already imply. Each is written once; "
            "one already there is left as it is."]
    head += [f"  {n} from: {k}" for k, n in sorted(by_kind.items())]
    return "\n".join(head + [""] + sorted(lines))


async def job_dry_run(settings) -> str:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    if not await available(client):
        raise RuntimeError("This CRM does not have partner and funder associations yet "
                           "(partner-association-crm-handoff.md).")
    return plan_text(await plan_backfill(client))


async def job_apply(settings) -> str:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    done = await apply_backfill(client, await plan_backfill(client))
    moved = await run_transfer_pass(client)
    return (f"{done['written']} association(s) written or already there, {done['failed']} not written; "
            f"{moved['moved']} moved to a company.")


async def run_nightly(settings) -> dict[str, int]:
    """The worker's pass: associations held by a person or lead whose company
    now exists move to it. Never raises."""
    client = _client(settings)
    if client is None:
        return {"checked": 0, "moved": 0, "errors": 0}
    try:
        return await run_transfer_pass(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("partner association transfer pass failed: %s", exc)
        return {"checked": 0, "moved": 0, "errors": 1}
