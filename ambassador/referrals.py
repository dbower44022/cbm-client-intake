"""Referrals: the person a mentor refers is recorded at once and credited to
them, and the credit follows the person when they apply (decisions AM5, AM5a;
PRD § 4.4, § 4.5).

* :func:`create_referral` — the delivery's step for a referred person the
  CRM does not know: the Company (found by name or created), the Contact
  (typed Prospect, Referred by the mentor), a lead with Lead Source
  "Ambassador referral" and, for a potential partner or funder, a starting
  profile that shows at once in Partner or Funder Management.
* :func:`credit_engagement` — called by the client intake delivery: the new
  engagement gains the Contact's Referred by, the activity reads Applied and
  the mentor is told.
* :func:`referred_candidate` and :func:`claim_candidate` — called by the
  partner and funder form deliveries: an open referred profile on the same
  company is reused instead of a second one being created.

Everything here feature-detects its link or field from live metadata, so a
CRM without the Ambassador build is untouched; and the calls from the public
forms are best-effort: a failure is logged and never costs the submission.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.espo import EspoError
from core.phone import e164_or_none

from . import config as cfg

log = logging.getLogger("cbm_intake.ambassador")

KIND_WORDS = {cfg.POTENTIAL_CLIENT: "client", cfg.POTENTIAL_PARTNER: "partner",
              cfg.POTENTIAL_FUNDER: "funder"}


# --- feature detection ------------------------------------------------------------

async def _links(client: Any, entity: str) -> dict[str, Any]:
    try:
        links = await client.metadata(f"entityDefs.{entity}.links")
    except Exception:  # noqa: BLE001 — absent reads as absent
        return {}
    return links if isinstance(links, dict) else {}


async def _fields(client: Any, entity: str) -> dict[str, Any]:
    try:
        fields = await client.metadata(f"entityDefs.{entity}.fields")
    except Exception:  # noqa: BLE001
        return {}
    return fields if isinstance(fields, dict) else {}


async def has_link(client: Any, entity: str, link: str) -> bool:
    return link in await _links(client, entity)


async def activity_available(client: Any) -> bool:
    """Whether this CRM holds the Ambassador Activity record type."""
    return bool(await _fields(client, cfg.ACTIVITY))


def _domain(kind: str) -> dict[str, str]:
    """The partner or funder side's names."""
    if kind == cfg.POTENTIAL_PARTNER:
        return {"entity": cfg.PARTNER, "company": cfg.PARTNER_COMPANY,
                "contacts": cfg.PARTNER_CONTACTS, "manager": cfg.PARTNER_MANAGER,
                "primary": cfg.PARTNER_PRIMARY, "status": cfg.PARTNER_STATUS_FIELD,
                "candidate": cfg.PARTNER_CANDIDATE, "team": cfg.PARTNER_TEAM_SETTING,
                "slug": "partnersessions", "words": "partner"}
    return {"entity": cfg.SPONSOR, "company": cfg.SPONSOR_COMPANY,
            "contacts": cfg.SPONSOR_CONTACTS, "manager": cfg.SPONSOR_MANAGER,
            "primary": cfg.SPONSOR_PRIMARY, "status": cfg.SPONSOR_STATUS_FIELD,
            "candidate": cfg.SPONSOR_CANDIDATE, "team": cfg.SPONSOR_TEAM_SETTING,
            "slug": "sponsorsessions", "words": "funder"}


async def team_ids(client: Any, team_name: str) -> list[str]:
    name = (team_name or "").strip()
    if not name:
        return []
    try:
        team = await client.find_one("Team", "name", name)
    except EspoError as exc:
        log.warning("ambassador: team %r not read (%s); record left without it", name, exc)
        return []
    return [team["id"]] if team else []


# --- a new referred person (PRD § 4.4, § 4.5) ----------------------------------------

async def _company(client: Any, entered: dict[str, Any], stamps: dict[str, Any]) -> Optional[str]:
    """The referred person's company: the one the lookup picked, else one of
    the same name (reused, never duplicated), else a new one. No company type
    until they apply (PRD § 14 item 4)."""
    picked = (entered.get("companyId") or "").strip()
    if picked:
        return picked
    name = (entered.get("organization") or "").strip()
    if not name:
        return None
    existing = await client.find_one(cfg.ACCOUNT, "name", name, select="id,name")
    if existing:
        return existing["id"]
    created = await client.create(cfg.ACCOUNT, {"name": name, **stamps})
    return created["id"]


async def create_referral(client: Any, settings: Any, *, kind: str, entered: dict[str, Any],
                          mentor_profile_id: str, user_id: str,
                          marketing_agreed: bool) -> dict[str, Any]:
    """Record a referred person the CRM does not know. ``client`` is the
    delivery's resumable client under the organization-wide key, so a retry
    converges on one set of records. Returns ``{"contactId", "companyId",
    "profileId", "profileEntity"}``."""
    from campaigns import attribution as attrib
    from core.crm_upsert import find_create_or_fill

    stamps: dict[str, Any] = {"assignedUsersIds": [user_id]} if user_id else {}
    domain = _domain(kind) if kind in (cfg.POTENTIAL_PARTNER, cfg.POTENTIAL_FUNDER) else None
    domain_teams = await team_ids(client, getattr(settings, domain["team"], "")) if domain else []
    if domain_teams:
        stamps["teamsIds"] = domain_teams
    company_id = await _company(client, entered, stamps)

    payload: dict[str, Any] = {
        "firstName": (entered.get("firstName") or "").strip() or None,
        "lastName": (entered.get("lastName") or "").strip() or "(not given)",
        "emailAddress": (entered.get("email") or "").strip(),
        "cContactType": ["Prospect"],
        **stamps,
    }
    if company_id:
        payload["accountId"] = company_id
    phone = e164_or_none(entered.get("phone") or "")
    if phone:
        payload["phoneNumber"] = phone
    if await has_link(client, cfg.CONTACT, cfg.CONTACT_REFERRED_BY):
        payload[f"{cfg.CONTACT_REFERRED_BY}Id"] = mentor_profile_id
    if marketing_agreed:
        payload["cMarketingOptIn"] = True
    payload = {k: v for k, v in payload.items() if v is not None}
    contact_id, action = await find_create_or_fill(
        client, cfg.CONTACT, match_attr="emailAddress", match_value=payload["emailAddress"],
        create_payload=payload,
        fill_keys=[k for k in payload if k not in ("emailAddress", "cContactType",
                                                    "assignedUsersIds", "teamsIds")],
        true_wins=("cMarketingOptIn",) if marketing_agreed else ())
    log.info("ambassador referral: contact %s (%s)", contact_id, action)

    profile_id = None
    if domain:
        profile_id = await _create_profile(client, domain, company_id, contact_id,
                                           entered, mentor_profile_id, domain_teams)

    # Ruling 48: a record from an outside source has a lead behind it.
    await attrib.record_lead(client, attrib.Attribution(), source=cfg.LEAD_SOURCE,
                             company_id=company_id, contact_id=contact_id, values={
                                 "businessName": entered.get("organization") or "",
                                 "firstName": entered.get("firstName") or "",
                                 "lastName": entered.get("lastName") or "",
                                 "email": entered.get("email") or "",
                                 "phone": phone or ""})
    return {"contactId": contact_id, "companyId": company_id or "", "profileId": profile_id or "",
            "profileEntity": domain["entity"] if domain else ""}


async def _create_profile(client: Any, domain: dict[str, str], company_id: Optional[str],
                          contact_id: str, entered: dict[str, Any], mentor_profile_id: str,
                          teams: list[str]) -> Optional[str]:
    """The starting partner or funder profile (AM5a): Candidate (partner) or
    Prospective (funder), Referred by the mentor, the domain team stamped, no
    manager. A company that already holds a profile of this kind keeps it,
    and no second one is made."""
    if company_id:
        page = await client.list(domain["entity"], where=[
            {"type": "equals", "attribute": domain["company"], "value": company_id}],
            select="id", max_size=1)
        if page.get("list"):
            return page["list"][0]["id"]
    name = (entered.get("organization") or "").strip() or " ".join(
        x for x in (entered.get("firstName"), entered.get("lastName")) if x) or "Referral"
    payload: dict[str, Any] = {"name": name, domain["primary"]: contact_id}
    if company_id:
        payload[domain["company"]] = company_id
    if teams:
        payload["teamsIds"] = teams
    fields = await _fields(client, domain["entity"])
    if domain["status"] in fields:
        payload[domain["status"]] = domain["candidate"]
    if await has_link(client, domain["entity"], cfg.REFERRED_BY):
        payload[f"{cfg.REFERRED_BY}Id"] = mentor_profile_id
    created = await client.create(domain["entity"], payload)
    try:
        await client.relate(domain["entity"], created["id"], domain["contacts"], contact_id)
    except EspoError as exc:
        log.warning("ambassador referral: contact not added to %s %s: %s",
                    domain["entity"], created["id"], exc)
    return created["id"]


async def credit_contact(client: Any, contact: dict[str, Any], mentor_profile_id: str) -> bool:
    """A known person referred again: Referred by is filled only when empty, so
    the first mentor keeps the credit (AM5 item 3)."""
    if contact.get(f"{cfg.CONTACT_REFERRED_BY}Id"):
        return False
    if not await has_link(client, cfg.CONTACT, cfg.CONTACT_REFERRED_BY):
        return False
    await client.update(cfg.CONTACT, contact["id"],
                        {f"{cfg.CONTACT_REFERRED_BY}Id": mentor_profile_id})
    return True


# --- the credit follows the person (PRD § 4.4 item 5, § 4.5 item 4) -----------------

async def _mark_applied(client: Any, settings: Any, contact_id: str, kind: str,
                        person: str) -> None:
    """The referral's activity reads Applied, and its mentor is told."""
    from . import email as am_email
    from . import notify

    try:
        page = await client.list(cfg.ACTIVITY, where=[
            {"type": "equals", "attribute": "contactId", "value": contact_id},
            {"type": "equals", "attribute": "activityType", "value": cfg.REFERRED},
            {"type": "equals", "attribute": "referralOutcome", "value": cfg.O_NOT_YET}],
            select="id,mentorProfileId", max_size=5, order_by="createdAt", order="asc")
    except EspoError as exc:
        log.warning("ambassador: referral activity for %s not read: %s", contact_id, exc)
        return
    rows = page.get("list", [])
    if not rows:
        return
    first = rows[0]
    for row in rows:
        try:
            await client.update(cfg.ACTIVITY, row["id"], {"referralOutcome": cfg.O_APPLIED})
        except EspoError as exc:
            log.warning("ambassador: activity %s not marked Applied: %s", row["id"], exc)
    if not getattr(settings, "ambassador_program", False):
        return
    address, _name, first_name = await notify.profile_mailbox(client, first.get("mentorProfileId"))
    if address:
        filled = am_email.referral_applied(
            org=settings.organization_name, first_name=first_name, person=person,
            kind_words=kind, link_url=notify.base_url(settings) + "/ambassador/")
        await notify.send(settings, [address], filled, what="referral-applied")


async def credit_engagement(client: Any, settings: Any, *, contact_id: str,
                            engagement_id: str, person: str = "") -> bool:
    """The client intake delivery's step: copy the Contact's Referred by onto
    the new engagement. Best-effort, never raises; True when credited."""
    try:
        if not await has_link(client, cfg.CONTACT, cfg.CONTACT_REFERRED_BY):
            return False
        contact = await client.get(cfg.CONTACT, contact_id,
                                   select=f"id,name,{cfg.CONTACT_REFERRED_BY}Id")
        mentor = contact.get(f"{cfg.CONTACT_REFERRED_BY}Id")
        if not mentor:
            return False
        if await has_link(client, cfg.ENGAGEMENT, cfg.REFERRED_BY):
            await client.update(cfg.ENGAGEMENT, engagement_id, {f"{cfg.REFERRED_BY}Id": mentor})
        await _mark_applied(client, settings, contact_id, "client",
                            person or contact.get("name") or "")
        return True
    except Exception as exc:  # noqa: BLE001 — never costs the submission
        log.warning("ambassador: engagement %s not credited: %s", engagement_id, exc)
        return False


async def referred_candidate(client: Any, entity: str, company_id: str) -> Optional[dict[str, Any]]:
    """An open referred profile on ``company_id`` the partner or funder form
    should reuse: starting status, Referred by set, no manager. None when
    there is none, or this CRM has no Referred by (nothing is ever reused
    then). Never raises."""
    kind = cfg.POTENTIAL_PARTNER if entity == cfg.PARTNER else cfg.POTENTIAL_FUNDER
    domain = _domain(kind)
    try:
        if not company_id or not await has_link(client, entity, cfg.REFERRED_BY):
            return None
        page = await client.list(entity, where=[
            {"type": "equals", "attribute": domain["company"], "value": company_id},
            {"type": "isNotNull", "attribute": f"{cfg.REFERRED_BY}Id"},
            {"type": "isNull", "attribute": domain["manager"]}],
            select=f"id,name,{domain['status']},{domain['primary']},description",
            max_size=5, order_by="createdAt", order="asc")
    except Exception as exc:  # noqa: BLE001
        log.warning("ambassador: referred %s on %s not read: %s", entity, company_id, exc)
        return None
    for row in page.get("list", []):
        if (row.get(domain["status"]) or domain["candidate"]) == domain["candidate"]:
            return row
    return None


async def claim_candidate(client: Any, settings: Any, entity: str, profile: dict[str, Any],
                          contact_id: str, fill: dict[str, Any], person: str = "") -> str:
    """Reuse the referred profile for an application: empty fields filled from
    the application (never overwriting), the applicant made primary when the
    profile has none and added to its contacts, the activity marked Applied.
    Returns the profile id."""
    kind = cfg.POTENTIAL_PARTNER if entity == cfg.PARTNER else cfg.POTENTIAL_FUNDER
    domain = _domain(kind)
    update = {k: v for k, v in fill.items() if v not in (None, "", []) and not profile.get(k)}
    if not profile.get(domain["primary"]):
        update[domain["primary"]] = contact_id
    if fill.get("description") and profile.get("description"):
        update["description"] = (profile["description"] + "\n" + fill["description"]).strip()
    if update:
        await client.update(entity, profile["id"], update)
    try:
        await client.relate(entity, profile["id"], domain["contacts"], contact_id)
    except EspoError as exc:
        log.warning("ambassador: applicant not added to %s %s: %s", entity, profile["id"], exc)
    try:
        # The activity names the person the mentor referred, who may not be
        # the person who filled in the application.
        referred = profile.get(domain["primary"]) or contact_id
        await _mark_applied(client, settings, referred, domain["words"],
                            person or profile.get("name") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("ambassador: applied mark for %s failed: %s", profile["id"], exc)
    log.info("ambassador: %s %s reused for an application", entity, profile["id"])
    return profile["id"]
