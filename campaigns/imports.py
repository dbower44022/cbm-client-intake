"""The imports (build plan § 2, reworked for the lead model § 7a): parse →
normalise → already-known check → plan → apply. Three Lead Sources share every
step: the state filing (§ 2.1), the purchased list and the partner file (§ 2.3).

**Every row becomes a lead, and nothing else is created** (rulings 41, 43): the
Company and the Contact are made at first contact, never at import.

**The status a lead enters at (ruling 53).** A state-filing row that carries a
website or an email enters **Qualified** on the outside filter's verdict
(ruling 11), with the filter recorded in ``qualifiedBy`` / ``qualifiedAt``.
Every other row enters **Unqualified** (rulings 18, 42).

**Plan, then apply.** The upload shows what would be created, matched and
skipped, with the counts, and nothing is written until the reviewer applies that
exact plan (the Operations-job pattern). The plan is stored in the ledger with
the normalised rows, so the apply writes what was reviewed.

**Who acts (ruling 33).** The already-known reads and the link to a matched
Company run under the intake API client; the leads are created as the
signed-in user. **A re-upload of the same file is a no-op**: the ledger knows
every row an applied batch created.

**The already-known check (ruling 12)** is conservative, close to exact: a
Company by name AND postal code, a Company by website key, a Contact by email. A
match is a **Duplicate** (ruling 50) — a converted lead's Company or Contact
included, since the import no longer reuses one at a later conversion — the lead is still created (it is the
record that the row arrived and was recognised), linked to the Company it
matched, or naming the Contact it matched in its reason note, and no touch is
ever planned for it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from core.crm_upsert import website_key
from core.espo import EspoApi, EspoError

from . import config as cfg
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.imports")

REQUIRED = ("business_name",)
ADDRESS_SET = ("mailing_street", "mailing_city", "mailing_state", "mailing_zip")
KNOWN_COLUMNS = REQUIRED + ADDRESS_SET + (
    "external_reference", "website", "email", "phone", "contact_first_name",
    "contact_last_name", "qualified_by", "list_source",
)
MAX_ROWS = 5000
MAX_TEXT = 5 * 1024 * 1024

OUTCOME_CREATE = "create"
OUTCOME_ALREADY_KNOWN = "already_known"
OUTCOME_DUPLICATE = "duplicate"          # the same row twice in one file
OUTCOME_KNOWN_ROW = "known_row"          # an applied batch already created it
OUTCOME_INVALID = "invalid"

_ZIP = re.compile(r"^\d{5}(-\d{4})?$")


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_")


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Columns (normalised) and rows. A missing required column fails the plan
    with the column named; unknown columns ride along into ``importRow``."""
    if len(text) > MAX_TEXT:
        raise CampaignError("The file is too large to import in one go (5 MB limit).")
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise CampaignError("The file is empty.")
    columns = [_norm_header(h) for h in header]
    missing = [c for c in REQUIRED if c not in columns]
    if missing:
        raise CampaignError(f"The file has no {', '.join(missing)} column.")
    if not any(c in columns for c in ADDRESS_SET):
        raise CampaignError("The file has no mailing address columns "
                            "(mailing_street, mailing_city, mailing_state, mailing_zip).")
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any((v or "").strip() for v in raw):
            continue
        row = {columns[i]: (raw[i].strip() if i < len(raw) else "") for i in range(len(columns)) if columns[i]}
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise CampaignError(f"The file has more than {MAX_ROWS} rows; split it.")
    return columns, rows


def normalise(row: dict[str, str]) -> dict[str, Any]:
    out = dict(row)
    out["business_name"] = re.sub(r"\s+", " ", row.get("business_name", "")).strip()
    out["mailing_state"] = (row.get("mailing_state") or "").strip().upper()[:2]
    zip_ = (row.get("mailing_zip") or "").strip()
    if len(zip_) == 9 and zip_.isdigit():
        zip_ = f"{zip_[:5]}-{zip_[5:]}"
    out["mailing_zip"] = zip_
    out["email"] = (row.get("email") or "").strip().lower()
    out["website"] = (row.get("website") or "").strip()
    out["external_reference"] = (row.get("external_reference") or "").strip()
    return out


def row_hash(door: str, row: dict[str, Any]) -> str:
    """The across-batch key (§ 2.1): the external reference when the row has
    one, else business name plus postal code."""
    ref = row.get("external_reference") or ""
    if ref:
        key = f"{door}|ref|{ref.lower()}"
    else:
        key = f"{door}|name|{(row.get('business_name') or '').lower()}|{(row.get('mailing_zip') or '')[:5]}"
    return hashlib.sha256(key.encode()).hexdigest()


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _invalid_reason(row: dict[str, Any]) -> Optional[str]:
    if not row.get("business_name"):
        return "no business name"
    if not all(row.get(c) for c in ADDRESS_SET):
        return "incomplete mailing address"
    if not _ZIP.match(row.get("mailing_zip") or ""):
        return "postal code is not a US ZIP"
    return None


# --- the already-known check (ruling 12) -----------------------------------------------

async def already_known(api_client: EspoApi, row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The Company (or Contact) this row already is, or None. Conservative and
    close to exact; each step is best-effort so one unreadable list never blocks
    an import (a miss errs toward mailing a card — ruling 12)."""
    name = row.get("business_name") or ""
    zip5 = (row.get("mailing_zip") or "")[:5]
    if name and zip5:
        try:
            page = await api_client.list(
                cfg.ACCOUNT, select="id,name,billingAddressPostalCode,website,cCompanyType", max_size=20,
                where=[{"type": "equals", "attribute": "name", "value": name}],
            )
            for c in page.get("list", []):
                if ((c.get("billingAddressPostalCode") or "")[:5]) == zip5:
                    return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "name and postal code"}
        except EspoError as exc:
            log.warning("already-known name check failed for %r: %s", name, exc)
    if row.get("website"):
        try:
            c = await company_by_website(api_client, row["website"])
            if c:
                return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "website"}
        except EspoError as exc:
            log.warning("already-known website check failed for %r: %s", row["website"], exc)
    if row.get("email"):
        try:
            found = await api_client.find_one(cfg.CONTACT, "emailAddress", row["email"], select="id,name,cContactType")
            if found:
                return {"kind": "contact", "id": found["id"], "name": found.get("name"), "by": "email"}
        except EspoError as exc:
            log.warning("already-known email check failed for %r: %s", row["email"], exc)
    return None


async def company_by_website(api_client: EspoApi, website: str) -> Optional[dict[str, Any]]:
    """The Company at this web address, by website key (scheme, www., case and a
    trailing slash ignored; the path counts), or None."""
    key = website_key(website)
    if not key:
        return None
    host = key.split("/")[0]
    page = await api_client.list(
        cfg.ACCOUNT, select="id,name,website,cCompanyType", max_size=50,
        where=[{"type": "contains", "attribute": "website", "value": host}],
    )
    for c in page.get("list", []):
        if website_key(c.get("website")) == key:
            return c
    return None


_CHUNK = 40


class KnownIndex:
    """The already-known check (ruling 12) for a whole file in a few CRM
    reads instead of one to three per row — a month's filing is about 800
    rows (build plan § 7b), and row by row the plan took 61 seconds and timed
    the browser out (10-20-26). Same three matches, same order, same
    best-effort: a failed read is logged and that check simply finds nothing."""

    def __init__(self) -> None:
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        self.by_website: dict[str, dict[str, Any]] = {}
        self.by_email: dict[str, dict[str, Any]] = {}

    @classmethod
    async def build(cls, api_client: EspoApi, rows: list[dict[str, Any]]) -> "KnownIndex":
        idx = cls()
        names = sorted({r["business_name"] for r in rows if r.get("business_name")})
        for i in range(0, len(names), _CHUNK):
            chunk = names[i:i + _CHUNK]
            try:
                page = await api_client.list(
                    cfg.ACCOUNT, select="id,name,billingAddressPostalCode,website,cCompanyType", max_size=200,
                    where=[{"type": "in", "attribute": "name", "value": chunk}])
                for c in page.get("list", []):
                    idx.by_name.setdefault((c.get("name") or "").lower(), []).append(c)
            except EspoError as exc:
                log.warning("already-known name check failed for %s names: %s", len(chunk), exc)
        keys = sorted({k for k in (website_key(r.get("website")) for r in rows) if k})
        for i in range(0, len(keys), 20):
            chunk = keys[i:i + 20]
            try:
                page = await api_client.list(
                    cfg.ACCOUNT, select="id,name,website,cCompanyType", max_size=200,
                    where=[{"type": "or", "value": [{"type": "contains", "attribute": "website",
                                                     "value": k.split("/")[0]} for k in chunk]}])
                for c in page.get("list", []):
                    k = website_key(c.get("website"))
                    if k and k not in idx.by_website:
                        idx.by_website[k] = c
            except EspoError as exc:
                log.warning("already-known website check failed for %s addresses: %s", len(chunk), exc)
        emails = sorted({r["email"] for r in rows if r.get("email")})
        for i in range(0, len(emails), 20):
            chunk = emails[i:i + 20]
            try:
                page = await api_client.list(
                    cfg.CONTACT, select="id,name,emailAddress,cContactType", max_size=200,
                    where=[{"type": "or", "value": [{"type": "equals", "attribute": "emailAddress",
                                                     "value": e} for e in chunk]}])
                for c in page.get("list", []):
                    e = (c.get("emailAddress") or "").lower()
                    if e and e not in idx.by_email:
                        idx.by_email[e] = c
            except EspoError as exc:
                log.warning("already-known email check failed for %s addresses: %s", len(chunk), exc)
        return idx

    def match(self, row: dict[str, Any]) -> Optional[dict[str, Any]]:
        name = (row.get("business_name") or "").lower()
        zip5 = (row.get("mailing_zip") or "")[:5]
        if name and zip5:
            for c in self.by_name.get(name, []):
                if ((c.get("billingAddressPostalCode") or "")[:5]) == zip5:
                    return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "name and postal code"}
        k = website_key(row.get("website"))
        if k and k in self.by_website:
            c = self.by_website[k]
            return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "website"}
        e = (row.get("email") or "").lower()
        if e and e in self.by_email:
            c = self.by_email[e]
            return {"kind": "contact", "id": c["id"], "name": c.get("name"), "by": "email"}
        return None


# --- plan ----------------------------------------------------------------------------------

async def plan_import(api_client: EspoApi, store, *, text: str, name: str, door: str,
                      qualified_by: str, list_source: str = "") -> dict[str, Any]:
    """What an import would do. Nothing is written; the plan is stored in the
    ledger as a planned batch and the apply names it."""
    if door not in cfg.IMPORT_SOURCES:
        raise CampaignError("Unknown Lead Source for an import.")
    sha = file_hash(text)
    prior = await store.find_batch_by_file(sha)
    columns, raw_rows = parse_csv(text)
    rows = [normalise(r) for r in raw_rows]
    hashes = [row_hash(door, r) for r in rows]
    known = await store.known_row_hashes(list(set(hashes)))
    seen: set[str] = set()
    planned: list[dict[str, Any]] = []
    index = await KnownIndex.build(api_client, [r for r, h in zip(rows, hashes)
                                                if h not in known and not _invalid_reason(r)])
    counts = {"rows": len(rows), "create": 0, "alreadyKnown": 0, "duplicate": 0,
              "knownRow": 0, "invalid": 0, "qualified": 0, "unqualified": 0}
    for row, h in zip(rows, hashes):
        entry: dict[str, Any] = {"row": row, "hash": h, "name": row.get("business_name") or "",
                                 "postalCode": row.get("mailing_zip") or ""}
        reason = _invalid_reason(row)
        if reason:
            entry.update(outcome=OUTCOME_INVALID, note=reason); counts["invalid"] += 1
        elif h in seen:
            entry.update(outcome=OUTCOME_DUPLICATE, note="the same row appears earlier in this file")
            counts["duplicate"] += 1
        elif h in known:
            entry.update(outcome=OUTCOME_KNOWN_ROW, note="an earlier import already created this row")
            counts["knownRow"] += 1
        else:
            match = index.match(row)
            if match:
                entry.update(outcome=OUTCOME_ALREADY_KNOWN, match=match,
                             note=f"matches {match['name'] or match['id']} by {match['by']}")
                counts["alreadyKnown"] += 1
            else:
                entry["outcome"] = OUTCOME_CREATE
                entry["status"] = entry_status(door, row)
                counts["create"] += 1
                counts["qualified" if entry["status"] == cfg.LEAD_QUALIFIED else "unqualified"] += 1
        seen.add(h)
        planned.append(entry)
    plan = {
        "door": door, "qualifiedBy": qualified_by, "listSource": list_source,
        "columns": columns, "counts": counts, "rows": planned,
        "priorBatch": {"id": prior["id"], "appliedAt": prior["applied_at"].isoformat()} if prior else None,
    }
    batch = await store.create_batch(name=name, door=door, file_sha256=sha, row_count=len(rows),
                                     plan=plan, created_by="")
    return {"batchId": batch["id"], "name": name, "counts": counts,
            "nothingToDo": counts["create"] + counts["alreadyKnown"] == 0,
            "priorBatch": plan["priorBatch"],
            "rows": [{k: v for k, v in e.items() if k != "row"} | {
                "website": e["row"].get("website") or "", "email": e["row"].get("email") or ""}
                     for e in planned[:500]]}


# --- apply ---------------------------------------------------------------------------------

def entry_status(source: str, row: dict[str, Any]) -> str:
    """Ruling 53: a state filing with a website or an email enters Qualified on
    the outside filter's verdict; every other row enters Unqualified."""
    if source == cfg.SOURCE_FILING and (row.get("website") or row.get("email")):
        return cfg.LEAD_QUALIFIED
    return cfg.LEAD_UNQUALIFIED


def _lead_payload(row: dict[str, Any], plan: dict[str, Any], batch_name: str,
                  entry: dict[str, Any]) -> dict[str, Any]:
    source = plan["door"]
    status = entry_status(source, row)
    now = _now_crm()
    payload: dict[str, Any] = {
        "name": (row.get("business_name") or f"{row.get('contact_first_name','')} {row.get('contact_last_name','')}".strip())[:255],
        "businessName": (row.get("business_name") or "")[:255],
        "firstName": (row.get("contact_first_name") or "")[:100] or None,
        "lastName": (row.get("contact_last_name") or "")[:100] or None,
        "mailingAddressStreet": row.get("mailing_street") or None,
        "mailingAddressCity": row.get("mailing_city") or None,
        "mailingAddressState": row.get("mailing_state") or None,
        "mailingAddressPostalCode": row.get("mailing_zip") or None,
        "mailingAddressCountry": "US",
        "addressStatus": cfg.ADDRESS_USABLE,
        "website": row.get("website") or None,
        "email": row.get("email") or None,
        "phone": row.get("phone") or None,
        "leadStatus": status,
        "leadStatusChangedAt": now,
        "leadSource": source,
        "externalReference": (row.get("external_reference") or "")[:100] or None,
        "importBatch": (batch_name if source == cfg.SOURCE_FILING
                        else f"{plan.get('listSource') or 'list'} — {batch_name}")[:255],
        "importRow": json.dumps(row, ensure_ascii=False)[:60000],
    }
    if status == cfg.LEAD_QUALIFIED:
        payload["qualifiedBy"] = (row.get("qualified_by") or plan.get("qualifiedBy") or "")[:255] or None
        payload["qualifiedAt"] = now
    if entry.get("outcome") == OUTCOME_ALREADY_KNOWN:
        payload["sideExit"] = cfg.EXIT_DUPLICATE
        payload["sideExitAt"] = now
        match = entry.get("match") or {}
        what = "the contact" if match.get("kind") == "contact" else "the company"
        payload["sideExitNote"] = (f"Duplicate of {what} {match.get('name') or match.get('id')} "
                                   f"(matched by {match.get('by')} at import).")
    return {k: v for k, v in payload.items() if v is not None}


def _match_links(entry: dict[str, Any]) -> dict[str, str]:
    """A Duplicate's link to the Company it matched. A matched Contact is named
    in the reason note only — never on ``promotedContact`` (*Converted to
    contact*), so a duplicate never reads as converted."""
    match = entry.get("match") or {}
    if entry.get("outcome") != OUTCOME_ALREADY_KNOWN or not match.get("id"):
        return {}
    if match.get("kind") == "company":
        return {"alreadyKnownCompanyId": match["id"]}
    return {}


async def apply_import(api_client: EspoApi, user_client: EspoApi, store, batch: dict[str, Any], *,
                       user_name: str, max_rows: Optional[int] = None) -> dict[str, Any]:
    """Write exactly the planned batch. Resumable: a row the ledger already
    holds is skipped, so a failed apply is re-run, never doubled.

    ``max_rows`` writes at most that many rows and returns with ``remaining``
    (the browser calls again until it is 0): 800 creates in one request
    outlast every timeout between the browser and the CRM (10-20-26)."""
    if batch.get("status") == "applied":
        raise CampaignError("This batch has already been applied.")
    plan = batch.get("plan") or {}
    rows = plan.get("rows") or []
    done = await store.known_row_hashes([e["hash"] for e in rows])
    result = {"created": 0, "duplicates": 0, "qualified": 0, "unqualified": 0, "skipped": 0, "errors": 0}
    ledger: list[dict[str, Any]] = []
    writes = 0
    remaining = 0
    for entry in rows:
        outcome = entry.get("outcome")
        if outcome not in (OUTCOME_CREATE, OUTCOME_ALREADY_KNOWN) or entry["hash"] in done:
            result["skipped"] += 1
            continue
        if max_rows is not None and writes >= max_rows:
            remaining += 1
            continue
        writes += 1
        row = entry["row"]
        try:
            payload = _lead_payload(row, plan, batch["name"], entry)
            # The lead is the signed-in user's (ruling 33). Its link to a
            # matched Company is the API client's second write: EspoCRM checks
            # read access on the foreign record when a link rides a create, and
            # the Marketing Admin Role reads no Company (found live 10-15-26).
            lead = await user_client.create(cfg.PROSPECT, payload)
            links = _match_links(entry)
            if links:
                await api_client.update(cfg.PROSPECT, lead["id"], links)
            if outcome == OUTCOME_CREATE:
                result["created"] += 1
                result["qualified" if payload["leadStatus"] == cfg.LEAD_QUALIFIED else "unqualified"] += 1
            else:
                result["duplicates"] += 1
            result.setdefault("firstProspectId", lead.get("id"))
            ledger.append({"row_hash": entry["hash"], "external_reference": row.get("external_reference") or None,
                           "business_name": payload.get("businessName"), "postal_code": payload.get("mailingAddressPostalCode"),
                           "outcome": outcome, "prospect_id": lead.get("id")})
            done.add(entry["hash"])
        except EspoError as exc:
            result["errors"] += 1
            log.warning("import %s row %r failed: %s", batch["id"], entry.get("name"), exc)
        if len(ledger) >= 50:
            await store.record_rows(batch["id"], ledger)
            ledger = []
    if ledger:
        await store.record_rows(batch["id"], ledger)
    result["appliedBy"] = user_name
    result["remaining"] = remaining
    if result["errors"] == 0 and remaining == 0:
        await store.mark_applied(batch["id"], result)
    return result
