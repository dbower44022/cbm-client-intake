"""The free web check (build plan § 2, ruling E12).

From the business name it guesses a few web addresses — the name without its
legal suffix, run together and hyphenated, at ``.com``, and run together at
``.net`` — fetches each home page with a short timeout, and applies the strict
rule: the page must show the business name **and** either the street address
or postal code, or one of the filing's associates by name.

Never counted as the second fact (E12): the address when it is a registered
agent's. A page that shows only the name is not verified, whatever it is —
the research pass found 97% of name matches were someone else.

Behind its own switch, ``ENRICHMENT_WEB_CHECKS``. It uses its own HTTP client,
never the CRM's connection pool, and reads at most ``_MAX_BYTES`` of a page.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

import httpx

from . import fit, geo
from .terms import Terms, core_name, words

log = logging.getLogger("cbm_intake.enrichment.findability")

_MAX_BYTES = 300_000
_TIMEOUT = 6.0
_USER_AGENT = "CBM-LeadCheck/1.0 (business lookup for a nonprofit mentoring chapter)"
_TAG = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.S | re.I)
_STREET = re.compile(r"^\s*(\d+[a-z]?)\s+(?:[nsew]\.?\s+)?([a-z0-9]+)", re.I)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, max_redirects=3,
                             headers={"User-Agent": _USER_AGENT})


def candidates(name: str, terms: Terms) -> list[str]:
    """The guessed web addresses, at most three, in the order tried."""
    tokens = core_name(name, terms)
    joined = "".join(tokens)
    if len(joined) < 4:
        return []
    out = [f"{joined}.com"]
    if len(tokens) > 1:
        out.append(f"{'-'.join(tokens)}.com")
    out.append(f"{joined}.net")
    return out


def page_text(html: str) -> str:
    return words(_TAG.sub(" ", html or ""))


def facts(text: str, lead: Mapping[str, Any], terms: Terms, *, agent: bool) -> list[str]:
    """Which of the E12 facts the page shows, in plain words."""
    found: list[str] = []
    name = lead.get("businessName") or lead.get("name") or ""
    tokens = core_name(name, terms)
    if not tokens or not all(f" {t} " in text for t in tokens):
        return found
    found.append("the name")
    if not agent:
        m = _STREET.match(lead.get("mailingAddressStreet") or "")
        if m and f" {m.group(1).lower()} {m.group(2).lower()} " in text:
            found.append("the street address")
        else:
            z = geo.zip5(lead.get("mailingAddressPostalCode") or "")
            if z and f" {z} " in text:
                found.append("the postal code")
    for person in fit.associates(lead):
        if len(person.split()) >= 2 and f" {person} " in text:
            found.append(f"the associate {person}")
            break
    return found


async def _fetch(http: httpx.AsyncClient, domain: str) -> Optional[str]:
    for scheme in ("https", "http"):
        try:
            async with http.stream("GET", f"{scheme}://{domain}/") as resp:
                if resp.status_code >= 400:
                    return None
                kind = resp.headers.get("content-type", "")
                if "html" not in kind and "text" not in kind:
                    return None
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) >= _MAX_BYTES:
                        break
                return body.decode(resp.encoding or "utf-8", errors="replace")
        except (httpx.HTTPError, UnicodeError):
            continue
    return None


async def check(lead: Mapping[str, Any], terms: Terms, http: httpx.AsyncClient,
                *, agent: bool) -> fit.WebCheck:
    """The first guessed address whose page passes E12, or an unverified result."""
    name = lead.get("businessName") or lead.get("name") or ""
    for domain in candidates(name, terms):
        html = await _fetch(http, domain)
        if not html:
            continue
        shown = facts(page_text(html), lead, terms, agent=agent)
        if len(shown) >= 2:
            return fit.WebCheck(website=f"https://{domain}", verified=True,
                                evidence=" and ".join(shown) + " appear on its home page")
        if shown:
            log.debug("web check: %s shows only the name for %s", domain, lead.get("id"))
    return fit.WebCheck()
