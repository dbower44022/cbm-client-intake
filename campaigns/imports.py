"""The import doors (build plan § 2): parse → normalise → already-known check →
plan → apply. Phase 1 builds the state-filing door (§ 2.1); the list door
(§ 2.3) shares every step and differs only in the rung it enters at.

**Plan, then apply.** The upload shows what would be created, matched and
skipped, with the counts, and nothing is written until the reviewer applies that
exact plan (the Operations-job pattern). The plan is stored in the ledger with
the normalised rows, so the apply writes what was reviewed.

**Who acts (ruling 33).** The already-known reads, the Company and Contact
creates and null-fills run under the intake API client; the prospect records are
created as the signed-in user. **A re-upload of the same file is a no-op**: the
ledger knows every row an applied batch created.

**The already-known check (ruling 12)** is conservative, close to exact: a
Company by name AND postal code, a Company by website key, a Contact by email. A
match leaves by the *Already known* side exit — the prospect record is still
created (it is the record that the row arrived and was recognised), with the
company it matched, and no touch is ever planned for it.
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

from core.crm_upsert import create_dropping_invalid, website_key
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
                if _is_prospect_typed(c, "cCompanyType"):
                    continue
                if ((c.get("billingAddressPostalCode") or "")[:5]) == zip5:
                    return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "name and postal code"}
        except EspoError as exc:
            log.warning("already-known name check failed for %r: %s", name, exc)
    if row.get("website"):
        try:
            c = await company_by_website(api_client, row["website"])
            if c and not _is_prospect_typed(c, "cCompanyType"):
                return {"kind": "company", "id": c["id"], "name": c.get("name"), "by": "website"}
        except EspoError as exc:
            log.warning("already-known website check failed for %r: %s", row["website"], exc)
    if row.get("email"):
        try:
            found = await api_client.find_one(cfg.CONTACT, "emailAddress", row["email"], select="id,name,cContactType")
            if found and not _is_prospect_typed(found, "cContactType"):
                return {"kind": "contact", "id": found["id"], "name": found.get("name"), "by": "email"}
        except EspoError as exc:
            log.warning("already-known email check failed for %r: %s", row["email"], exc)
    return None


def _is_prospect_typed(record: dict[str, Any], type_field: str) -> bool:
    """A Company or Contact typed Prospect is a PROMOTED prospect (ruling 21), not
    a known client or contact (ruling 12): the import reuses it at promotion
    rather than counting the row as already known."""
    types = record.get(type_field) or []
    return cfg.COMPANY_TYPE_PROSPECT in types and len(types) == 1


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


# --- plan ----------------------------------------------------------------------------------

async def plan_import(api_client: EspoApi, store, *, text: str, name: str, door: str,
                      qualified_by: str, list_source: str = "") -> dict[str, Any]:
    """What an import would do. Nothing is written; the plan is stored in the
    ledger as a planned batch and the apply names it."""
    if door not in (cfg.DOOR_FILING, cfg.DOOR_LIST):
        raise CampaignError("Unknown import door.")
    sha = file_hash(text)
    prior = await store.find_batch_by_file(sha)
    columns, raw_rows = parse_csv(text)
    rows = [normalise(r) for r in raw_rows]
    hashes = [row_hash(door, r) for r in rows]
    known = await store.known_row_hashes(list(set(hashes)))
    seen: set[str] = set()
    planned: list[dict[str, Any]] = []
    counts = {"rows": len(rows), "create": 0, "alreadyKnown": 0, "duplicate": 0,
              "knownRow": 0, "invalid": 0, "promoteCompany": 0, "promoteContact": 0}
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
            match = await already_known(api_client, row)
            if match:
                entry.update(outcome=OUTCOME_ALREADY_KNOWN, match=match,
                             note=f"matches {match['name'] or match['id']} by {match['by']}")
                counts["alreadyKnown"] += 1
            else:
                entry["outcome"] = OUTCOME_CREATE
                entry["promoteCompany"] = bool(row.get("website"))
                entry["promoteContact"] = bool(row.get("email"))
                counts["create"] += 1
                counts["promoteCompany"] += int(entry["promoteCompany"])
                counts["promoteContact"] += int(entry["promoteContact"])
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

def _prospect_payload(row: dict[str, Any], plan: dict[str, Any], batch_name: str,
                      entry: dict[str, Any]) -> dict[str, Any]:
    door = plan["door"]
    stage = cfg.STAGE_QUALIFIED if door == cfg.DOOR_FILING else cfg.STAGE_UNVERIFIED
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
        "funnelStage": stage,
        "entryStage": stage,
        "stageChangedAt": now,
        "entryDoor": door,
        "externalReference": (row.get("external_reference") or "")[:100] or None,
        "importBatch": (batch_name if door == cfg.DOOR_FILING
                        else f"{plan.get('listSource') or 'list'} — {batch_name}")[:255],
        "importRow": json.dumps(row, ensure_ascii=False)[:60000],
    }
    if door == cfg.DOOR_FILING:
        payload["qualifiedBy"] = (row.get("qualified_by") or plan.get("qualifiedBy") or "")[:255] or None
        payload["qualifiedAt"] = now
    if entry.get("outcome") == OUTCOME_ALREADY_KNOWN:
        payload["sideExit"] = cfg.EXIT_ALREADY_KNOWN
        payload["sideExitAt"] = now
        match = entry.get("match") or {}
        payload["sideExitNote"] = f"Matched {match.get('name') or match.get('id')} by {match.get('by')} at import."
    return {k: v for k, v in payload.items() if v is not None}


def _match_links(entry: dict[str, Any]) -> dict[str, str]:
    match = entry.get("match") or {}
    if entry.get("outcome") != OUTCOME_ALREADY_KNOWN or not match.get("id"):
        return {}
    if match.get("kind") == "company":
        return {"alreadyKnownCompanyId": match["id"]}
    if match.get("kind") == "contact":
        return {"promotedContactId": match["id"]}
    return {}


async def _company_type_has_prospect(api_client: EspoApi) -> bool:
    try:
        options = await api_client.metadata_enum_options(cfg.ACCOUNT, "cCompanyType")
    except Exception:  # noqa: BLE001
        return False
    return bool(options) and cfg.COMPANY_TYPE_PROSPECT in options


async def apply_import(api_client: EspoApi, user_client: EspoApi, store, batch: dict[str, Any], *,
                       user_name: str) -> dict[str, Any]:
    """Write exactly the planned batch. Resumable: a row the ledger already
    holds is skipped, so a failed apply is re-run, never doubled."""
    if batch.get("status") == "applied":
        raise CampaignError("This batch has already been applied.")
    plan = batch.get("plan") or {}
    rows = plan.get("rows") or []
    done = await store.known_row_hashes([e["hash"] for e in rows])
    type_ok = await _company_type_has_prospect(api_client)
    stage = cfg.STAGE_QUALIFIED if plan.get("door") == cfg.DOOR_FILING else cfg.STAGE_UNVERIFIED
    result = {"created": 0, "alreadyKnown": 0, "companies": 0, "contacts": 0, "skipped": 0, "errors": 0}
    ledger: list[dict[str, Any]] = []
    for entry in rows:
        outcome = entry.get("outcome")
        if outcome not in (OUTCOME_CREATE, OUTCOME_ALREADY_KNOWN) or entry["hash"] in done:
            result["skipped"] += 1
            continue
        row = entry["row"]
        try:
            payload = _prospect_payload(row, plan, batch["name"], entry)
            # The links to a Company or Contact are written AFTER the create,
            # under the API client (ruling 33): EspoCRM checks read access on the
            # foreign record when a link rides a create, and the Marketing Admin
            # Role reads no Company — found live 10-15-26 (two 403s per import).
            links: dict[str, str] = _match_links(entry)
            if outcome == OUTCOME_CREATE:
                if entry.get("promoteCompany"):
                    existing = await company_by_website(api_client, row["website"])
                    if existing is not None:
                        # A promoted company from an earlier (partial) run: reuse it.
                        links["promotedCompanyId"] = existing["id"]
                if entry.get("promoteCompany") and "promotedCompanyId" not in links:
                    company: dict[str, Any] = {
                        "name": payload["businessName"], "website": row.get("website"),
                        "cFunnelStage": stage, "cEntryStage": stage,
                        "billingAddressStreet": payload.get("mailingAddressStreet"),
                        "billingAddressCity": payload.get("mailingAddressCity"),
                        "billingAddressState": payload.get("mailingAddressState"),
                        "billingAddressPostalCode": payload.get("mailingAddressPostalCode"),
                        "billingAddressCountry": "US",
                    }
                    if type_ok:
                        company["cCompanyType"] = [cfg.COMPANY_TYPE_PROSPECT]
                    created = await api_client.create(cfg.ACCOUNT, {k: v for k, v in company.items() if v})
                    links["promotedCompanyId"] = created["id"]
                    result["companies"] += 1
                if entry.get("promoteContact"):
                    found = await api_client.find_one(cfg.CONTACT, "emailAddress", row["email"], select="id,cContactType")
                    if found is not None:
                        links["promotedContactId"] = found["id"]
                if entry.get("promoteContact") and "promotedContactId" not in links:
                    contact = {
                        "firstName": payload.get("firstName") or "", "lastName": payload.get("lastName") or payload["businessName"][:100],
                        "emailAddress": row.get("email"), "phoneNumber": row.get("phone") or None,
                        "cContactType": [cfg.CONTACT_TYPE_PROSPECT],
                        "cFunnelStage": stage, "cEntryStage": stage,
                    }
                    if links.get("promotedCompanyId"):
                        contact["accountId"] = links["promotedCompanyId"]
                    created = await create_dropping_invalid(api_client, cfg.CONTACT, {k: v for k, v in contact.items() if v})
                    links["promotedContactId"] = created["id"]
                    result["contacts"] += 1
            # The prospect record is the signed-in user's (ruling 33); its links
            # to the Company and the Contact are the API client's second write.
            prospect = await user_client.create(cfg.PROSPECT, payload)
            if links:
                await api_client.update(cfg.PROSPECT, prospect["id"], links)
            result["created" if outcome == OUTCOME_CREATE else "alreadyKnown"] += 1
            result.setdefault("firstProspectId", prospect.get("id"))
            ledger.append({"row_hash": entry["hash"], "external_reference": row.get("external_reference") or None,
                           "business_name": payload.get("businessName"), "postal_code": payload.get("mailingAddressPostalCode"),
                           "outcome": outcome, "prospect_id": prospect.get("id")})
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
    if result["errors"] == 0:
        await store.mark_applied(batch["id"], result)
    return result
