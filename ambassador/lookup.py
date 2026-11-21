"""What the activity form fills in for the mentor (decision AM3a; PRD § 3.4).

Every read here runs AS THE MENTOR, with their own sign-in. The Mentor Role
reads every Contact and Company, so these lookups show nothing the mentor
could not already browse in Workspace Directories. What they return is a
fixed, small set of Contact and Company fields: never a contact's type, a
client's status, an engagement, a mentor or anything else the CRM holds.

* An email that belongs to a Contact fills in the person and their company.
* A new email whose domain matches a company fills in the company. A domain
  on the free-mail list never matches (``AMBASSADOR_FREE_MAIL_DOMAINS``); a
  domain matches on a company's website address and on the email domains of
  its existing contacts, and several matches are offered to pick from.
* A matched company that is a partner says so: partner status is public.
  Client status is never sent to the browser.
* A CBM member's address (a Mentor-typed Contact, or an address on
  ``MENTOR_EMAIL_DOMAIN``) is reported as a member, and nothing else.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

from core.crm_upsert import website_key
from core.espo import EspoError

from . import config as cfg

log = logging.getLogger("cbm_intake.ambassador")

_EMAIL = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$")
CONTACT_SELECT = ("id,firstName,lastName,name,emailAddress,phoneNumber,title,accountId,"
                  "accountName,cContactType")
COMPANY_SELECT = "id,name,website,cCompanyType"
#: How many people a name search offers.
NAME_RESULTS = 8


def email_domain(email: str) -> str:
    m = _EMAIL.match((email or "").strip().lower())
    return m.group(1) if m else ""


def is_free_mail(domain: str, free: Iterable[str]) -> bool:
    d = (domain or "").strip().lower()
    return bool(d) and d in set(free)


def is_member_address(settings: Any, email: str, types: Optional[Iterable[str]] = None) -> bool:
    """A CBM member: a Mentor-typed contact, or an address on the
    organization's own mail domain."""
    if "Mentor" in list(types or []):
        return True
    domain = (getattr(settings, "mentor_email_domain", "") or "").strip().lower()
    return bool(domain) and (email or "").strip().lower().endswith("@" + domain)


def _person(contact: dict[str, Any]) -> dict[str, Any]:
    """The Contact fields the form may show — nothing else leaves here."""
    return {
        "contactId": contact.get("id") or "",
        "firstName": contact.get("firstName") or "",
        "lastName": contact.get("lastName") or "",
        "email": contact.get("emailAddress") or "",
        "phone": contact.get("phoneNumber") or "",
        "title": contact.get("title") or "",
        "companyId": contact.get("accountId") or "",
        "organization": contact.get("accountName") or "",
    }


def _company(company: dict[str, Any]) -> dict[str, Any]:
    return {"companyId": company.get("id") or "", "organization": company.get("name") or "",
            "website": company.get("website") or "",
            "isPartner": "Partner" in (company.get("cCompanyType") or [])}


def _host(url: str) -> str:
    """A website's host for comparing with an email domain: ``website_key``
    without its path."""
    return website_key(url).split("/", 1)[0]


def _domain_matches(host: str, domain: str) -> bool:
    return bool(host) and (host == domain or host.endswith("." + domain)
                           or domain.endswith("." + host))


async def companies_for_domain(client: Any, domain: str) -> list[dict[str, Any]]:
    """Companies whose website is on ``domain``, or whose contacts' addresses
    are; in name order, at most ten."""
    found: dict[str, dict[str, Any]] = {}
    try:
        page = await client.list(cfg.ACCOUNT, where=[
            {"type": "contains", "attribute": "website", "value": domain}],
            select=COMPANY_SELECT, max_size=20)
        for c in page.get("list", []):
            if _domain_matches(_host(c.get("website") or ""), domain):
                found[c["id"]] = c
        people = await client.list(cfg.CONTACT, where=[
            {"type": "endsWith", "attribute": "emailAddress", "value": "@" + domain}],
            select="id,accountId", max_size=50)
        ids = {p.get("accountId") for p in people.get("list", [])
               if p.get("accountId") and p.get("accountId") not in found}
        for cid in sorted(ids)[:10]:
            try:
                found[cid] = await client.get(cfg.ACCOUNT, cid, select=COMPANY_SELECT)
            except EspoError:
                continue
    except EspoError as exc:
        log.warning("ambassador lookup: companies for %s not read: %s", domain, exc)
    rows = sorted(found.values(), key=lambda c: (c.get("name") or "").lower())
    return [_company(c) for c in rows[:10]]


async def by_email(settings: Any, client: Any, email: str) -> dict[str, Any]:
    """What the form fills in for an email address.

    ``{"kind": "person", "person": {...}, "isPartner": bool}`` for a known
    Contact; ``{"kind": "member"}`` for a CBM member; ``{"kind": "company",
    "companies": [...]}`` for a new address on a company's domain;
    ``{"kind": "none"}`` otherwise (a free-mail domain included)."""
    email = (email or "").strip()
    domain = email_domain(email)
    if not domain:
        return {"kind": "none"}
    if is_member_address(settings, email):
        return {"kind": "member"}
    try:
        contact = await client.find_one(cfg.CONTACT, "emailAddress", email, select=CONTACT_SELECT)
    except EspoError as exc:
        log.warning("ambassador lookup: contact by email not read: %s", exc)
        contact = None
    if contact:
        if is_member_address(settings, contact.get("emailAddress") or email,
                             contact.get("cContactType")):
            return {"kind": "member"}
        is_partner = False
        if contact.get("accountId"):
            try:
                company = await client.get(cfg.ACCOUNT, contact["accountId"], select=COMPANY_SELECT)
                is_partner = "Partner" in (company.get("cCompanyType") or [])
            except EspoError:
                pass
        return {"kind": "person", "person": _person(contact), "isPartner": is_partner}
    if is_free_mail(domain, settings.ambassador_free_mail_domains_set):
        return {"kind": "none"}
    companies = await companies_for_domain(client, domain)
    if companies:
        return {"kind": "company", "companies": companies}
    return {"kind": "none"}


async def people(settings: Any, client: Any, query: str) -> list[dict[str, Any]]:
    """Contacts whose first or last name starts with ``query`` (three letters
    or more), members left out; at most ``NAME_RESULTS``."""
    q = (query or "").strip()
    if len(q) < 3:
        return []
    words = q.split()
    if len(words) >= 2:
        where = [{"type": "startsWith", "attribute": "firstName", "value": words[0]},
                 {"type": "startsWith", "attribute": "lastName", "value": " ".join(words[1:])}]
    else:
        where = [{"type": "or", "value": [
            {"type": "startsWith", "attribute": "firstName", "value": q},
            {"type": "startsWith", "attribute": "lastName", "value": q}]}]
    try:
        page = await client.list(cfg.CONTACT, where=where, select=CONTACT_SELECT,
                                 max_size=NAME_RESULTS * 2, order_by="lastName", order="asc")
    except EspoError as exc:
        log.warning("ambassador lookup: name search not read: %s", exc)
        return []
    out = []
    for c in page.get("list", []):
        if is_member_address(settings, c.get("emailAddress") or "", c.get("cContactType")):
            continue
        out.append(_person(c))
        if len(out) >= NAME_RESULTS:
            break
    return out


async def person_by_id(settings: Any, client: Any, contact_id: str) -> Optional[dict[str, Any]]:
    """A picked person, read again as the mentor (a member reads as None)."""
    try:
        c = await client.get(cfg.CONTACT, contact_id, select=CONTACT_SELECT)
    except EspoError:
        return None
    if is_member_address(settings, c.get("emailAddress") or "", c.get("cContactType")):
        return None
    return _person(c)
