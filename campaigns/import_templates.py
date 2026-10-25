"""Import templates (build plan § 7e.7; rulings 79, 81, 82, 111) — step M4.

A **template** remembers how one recurring spreadsheet maps onto a lead: the
Lead Source, the list source, *Qualified by*, *Enters at* (ruling 111 — the
template carries the qualifying judgement), the referrer partner, and the
column **mapping**. Templates are shared by the whole team (ruling 79): anyone
creates, edits or deletes any of them, and each change is action-logged by the
router.

**The mapping** is a list of entries, each one of five shapes (ruling 82 — a
fix is picked from a list beside the column, never written as a formula):

* ``{"column": "<file column>", "field": "<lead field>"}`` — the plain case;
* ``{"split_name": "<file column>"}`` — a full name into ``contact_first_name``
  and ``contact_last_name`` (the last word is the surname, as
  ``enrichment.runs.split_name`` does);
* ``{"join": ["<a>", "<b>", …], "field": "<lead field>", "with": " "}`` — two
  or more columns into one field;
* ``{"fixed": "<value>", "field": "<lead field>"}`` — a value the file lacks;
* ``{"ignore": "<file column>"}`` — a column that must not ride along.

Column names in a mapping are the file's headers **normalised** (lower case,
runs of anything but letters and digits as one underscore) — the same rule
``campaigns.imports`` has always applied to CSV headers. A file column no entry
names rides along into the lead's ``importRow`` under its normalised name, as
unknown columns always have; ``ignore`` is how to stop one.

**Recognition (ruling 81)** scores every template by the share of the file
columns it maps that are present in the uploaded file's headers; the best
score above one half is *suggested*, never applied without the person's
confirm. The differences are listed plainly — new columns (in the file, not in
the template), missing columns (in the template, not in the file) and likely
renames (an unmatched file column close in name to an unmatched template
column, ``difflib`` ratio at or above 0.8) — because the system will sometimes
suggest the wrong template and the differences are what make that noticeable.

**The required check.** A mapping that yields no business name, or not every
one of the four mailing-address parts, stops the import with the field named
(ruling 81). Phone and ZIP normalisation stay automatic in
``campaigns.imports.normalise``.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, String, Table, select, update, delete
from sqlalchemy.dialects.postgresql import JSONB

from core.store import metadata

from . import config as cfg
from .service import CampaignError

import_template = Table(
    "import_template",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("door", String(32), nullable=False),
    Column("list_source", String(255)),
    Column("qualified_by", String(255)),
    Column("enters_at", String(16), nullable=False),
    Column("referrer_partner_id", String(32)),
    Column("referrer_partner_name", String(200)),
    Column("mapping", JSONB, nullable=False),
    Column("header_signature", JSONB, nullable=False),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_batch_id", String(36)),
)

ENTERS_UNQUALIFIED = cfg.LEAD_UNQUALIFIED
ENTERS_QUALIFIED = cfg.LEAD_QUALIFIED
ENTERS_AT = (ENTERS_UNQUALIFIED, ENTERS_QUALIFIED)

#: The lead fields a column may map onto, with the words the screen shows.
FIELD_LABELS: dict[str, str] = {
    "business_name": "Business name",
    "mailing_street": "Street",
    "mailing_city": "City",
    "mailing_state": "State",
    "mailing_zip": "ZIP",
    "external_reference": "Reference (the source's own id)",
    "website": "Website",
    "email": "Email",
    "phone": "Phone",
    "contact_first_name": "First name",
    "contact_last_name": "Last name",
    "qualified_by": "Qualified by (per row)",
}
FIELDS: tuple[str, ...] = tuple(FIELD_LABELS)
REQUIRED_FIELD = "business_name"
ADDRESS_FIELDS: tuple[str, ...] = ("mailing_street", "mailing_city", "mailing_state", "mailing_zip")
SPLIT_FIELDS: tuple[str, str] = ("contact_first_name", "contact_last_name")

#: Recognition: the lowest score that is suggested, and the rename similarity.
SUGGEST_FLOOR = 0.5
RENAME_RATIO = 0.8


def norm_header(h: Any) -> str:
    """The file header as the mapping names it (the CSV rule since Phase 1)."""
    return re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")


# --- the mapping ----------------------------------------------------------------------------

def validate_mapping(mapping: Any) -> list[dict[str, Any]]:
    """The mapping with each entry checked for shape; raises :class:`CampaignError`
    naming the first bad entry in plain words."""
    if not isinstance(mapping, list):
        raise CampaignError("The mapping must be a list of entries.")
    out: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for i, raw in enumerate(mapping, 1):
        if not isinstance(raw, dict):
            raise CampaignError(f"Mapping entry {i} is not an object.")
        e = {k: v for k, v in raw.items() if v not in (None, "")}
        field = e.get("field")
        if "ignore" in e:
            out.append({"ignore": norm_header(e["ignore"])}); continue
        if "split_name" in e:
            out.append({"split_name": norm_header(e["split_name"])})
            seen_fields.update(SPLIT_FIELDS); continue
        if field not in FIELD_LABELS:
            raise CampaignError(f"Mapping entry {i} names no lead field (or an unknown one: {field!r}).")
        if field in seen_fields:
            raise CampaignError(f"The field {FIELD_LABELS[field]} is mapped twice.")
        seen_fields.add(field)
        if "column" in e:
            out.append({"column": norm_header(e["column"]), "field": field})
        elif "join" in e:
            cols = [norm_header(c) for c in (e["join"] if isinstance(e["join"], list) else [e["join"]]) if norm_header(c)]
            if len(cols) < 2:
                raise CampaignError(f"A join for {FIELD_LABELS[field]} needs at least two columns.")
            out.append({"join": cols, "field": field, "with": str(e.get("with", " "))})
        elif "fixed" in e:
            out.append({"fixed": str(e["fixed"])[:255], "field": field})
        else:
            raise CampaignError(f"Mapping entry {i} ({FIELD_LABELS[field]}) is neither a column, a join nor a fixed value.")
    return out


def mapped_fields(mapping: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for e in mapping:
        if "split_name" in e:
            out.update(SPLIT_FIELDS)
        elif e.get("field"):
            out.add(e["field"])
    return out


def source_columns(mapping: list[dict[str, Any]]) -> list[str]:
    """The file columns the mapping reads (what recognition scores on)."""
    cols: list[str] = []
    for e in mapping:
        for c in ([e["column"]] if "column" in e else e.get("join") or ([e["split_name"]] if "split_name" in e else [])):
            if c and c not in cols:
                cols.append(c)
    return cols


def missing_required(mapping: list[dict[str, Any]]) -> list[str]:
    """The required fields the mapping leaves unmapped, as the screen's words:
    the business name, and the four address parts as a set (ruling 81)."""
    have = mapped_fields(mapping)
    missing = []
    if REQUIRED_FIELD not in have:
        missing.append(FIELD_LABELS[REQUIRED_FIELD])
    missing += [FIELD_LABELS[f] for f in ADDRESS_FIELDS if f not in have]
    return missing


def _split_name(value: Any) -> tuple[str, str]:
    parts = str(value or "").strip().split()
    if len(parts) > 1:
        return " ".join(parts[:-1]), parts[-1]
    return "", parts[0] if parts else ""


def apply_mapping(mapping: list[dict[str, Any]], raw: dict[str, str]) -> dict[str, str]:
    """One file row (normalised header → value) as the lead-field row the
    import's ``normalise`` expects. Unmapped columns ride along; ignored ones do
    not; a mapped column's own name does not ride along a second time."""
    out: dict[str, str] = {}
    consumed: set[str] = set()
    for e in mapping:
        if "ignore" in e:
            consumed.add(e["ignore"]); continue
        if "split_name" in e:
            first, last = _split_name(raw.get(e["split_name"], ""))
            out[SPLIT_FIELDS[0]], out[SPLIT_FIELDS[1]] = first, last
            consumed.add(e["split_name"]); continue
        field = e["field"]
        if "column" in e:
            out[field] = str(raw.get(e["column"], "") or "").strip(); consumed.add(e["column"])
        elif "join" in e:
            parts = [str(raw.get(c, "") or "").strip() for c in e["join"]]
            out[field] = e.get("with", " ").join(p for p in parts if p); consumed.update(e["join"])
        elif "fixed" in e:
            out[field] = e["fixed"]
    for col, value in raw.items():
        if col and col not in consumed and col not in out:
            out[col] = str(value or "").strip()
    return out


def identity_mapping(headers: list[str]) -> list[dict[str, Any]]:
    """The mapping a file that already uses the lead-field names implies — what
    the CSV import always assumed. The starting point for a new template."""
    return [{"column": h, "field": h} for h in headers if h in FIELD_LABELS]


# --- recognition (ruling 81) --------------------------------------------------------------------

def score(template: dict[str, Any], headers: list[str]) -> float:
    """The share of the template's source columns the file has (0 to 1)."""
    cols = source_columns(template.get("mapping") or [])
    if not cols:
        return 0.0
    present = set(headers)
    return sum(1 for c in cols if c in present) / len(cols)


def likely_renames(file_columns: list[str], template_columns: list[str]) -> list[dict[str, Any]]:
    """Pairs of (file column, template column) close in name — suggestions
    only, never applied by themselves."""
    out: list[dict[str, Any]] = []
    taken: set[str] = set()
    for fc in file_columns:
        best, best_ratio = None, 0.0
        for tc in template_columns:
            if tc in taken:
                continue
            r = difflib.SequenceMatcher(None, fc, tc).ratio()
            if r > best_ratio:
                best, best_ratio = tc, r
        if best and best_ratio >= RENAME_RATIO:
            taken.add(best)
            out.append({"from": fc, "to": best, "ratio": round(best_ratio, 2)})
    return out


def differences(template: dict[str, Any], headers: list[str]) -> dict[str, Any]:
    """New, missing and likely-renamed columns between a template and a file."""
    cols = source_columns(template.get("mapping") or [])
    present = set(headers)
    new = [h for h in headers if h and h not in set(cols)]
    missing = [c for c in cols if c not in present]
    renamed = likely_renames(new, missing)
    renamed_from = {r["from"] for r in renamed}
    renamed_to = {r["to"] for r in renamed}
    return {"new": [h for h in new if h not in renamed_from],
            "missing": [c for c in missing if c not in renamed_to],
            "renamed": renamed}


def recognise(templates: list[dict[str, Any]], headers: list[str]) -> dict[str, Any]:
    """Every template scored, the best one above the floor suggested."""
    scored = sorted(({"id": t["id"], "name": t["name"], "score": round(score(t, headers), 2)} for t in templates),
                    key=lambda s: (-s["score"], s["name"].lower()))
    suggested = None
    if scored and scored[0]["score"] > SUGGEST_FLOOR:
        best = next(t for t in templates if t["id"] == scored[0]["id"])
        suggested = {**scored[0], **differences(best, headers)}
    return {"suggested": suggested, "candidates": scored}


def rename_mapping(mapping: list[dict[str, Any]], renames: dict[str, str]) -> list[dict[str, Any]]:
    """The mapping with template columns renamed to the file's (the person
    accepted the suggestions): ``{template column: file column}``."""
    def r(c: str) -> str:
        return renames.get(c, c)
    out = []
    for e in mapping:
        if "column" in e:
            out.append({**e, "column": r(e["column"])})
        elif "join" in e:
            out.append({**e, "join": [r(c) for c in e["join"]]})
        elif "split_name" in e:
            out.append({**e, "split_name": r(e["split_name"])})
        elif "ignore" in e:
            out.append({**e, "ignore": r(e["ignore"])})
        else:
            out.append(dict(e))
    return out


# --- the template record ------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_template(body: dict[str, Any]) -> dict[str, Any]:
    """A template as posted → the row's values, checked. Raises
    :class:`CampaignError` in plain words."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise CampaignError("Name the template.")
    door = str(body.get("source") or body.get("door") or "").strip()
    if door not in cfg.IMPORT_SOURCES:
        raise CampaignError("Choose a Lead Source: " + ", ".join(cfg.IMPORT_SOURCES) + ".")
    enters_at = str(body.get("entersAt") or ENTERS_UNQUALIFIED).strip()
    if enters_at not in ENTERS_AT:
        raise CampaignError("Enters at is Unqualified or Qualified.")
    mapping = validate_mapping(body.get("mapping") or [])
    missing = missing_required(mapping)
    if missing:
        raise CampaignError("The template maps nothing onto " + ", ".join(missing) + ". Map those columns first.")
    qualified_by = str(body.get("qualifiedBy") or "").strip()[:255]
    if enters_at == ENTERS_QUALIFIED and not qualified_by:
        raise CampaignError("A template whose rows enter Qualified names who or what qualifies them (Qualified by).")
    partner_id = str(body.get("referrerPartnerId") or "").strip()
    if partner_id and not re.match(r"^[A-Za-z0-9]{6,32}$", partner_id):
        raise CampaignError("The referrer partner id is not a CRM id.")
    signature = body.get("headerSignature")
    if not isinstance(signature, list) or not signature:
        signature = source_columns(mapping)
    return {
        "name": name[:200], "door": door,
        "list_source": str(body.get("listSource") or "").strip()[:255] or None,
        "qualified_by": qualified_by or None, "enters_at": enters_at,
        "referrer_partner_id": partner_id or None,
        "referrer_partner_name": str(body.get("referrerPartnerName") or "").strip()[:200] or None,
        "mapping": mapping, "header_signature": [norm_header(h) for h in signature if norm_header(h)],
    }


def template_payload(row: dict[str, Any]) -> dict[str, Any]:
    """A stored template as the page reads it."""
    return {
        "id": row["id"], "name": row["name"], "source": row["door"],
        "listSource": row.get("list_source") or "", "qualifiedBy": row.get("qualified_by") or "",
        "entersAt": row.get("enters_at") or ENTERS_UNQUALIFIED,
        "referrerPartnerId": row.get("referrer_partner_id") or "",
        "referrerPartnerName": row.get("referrer_partner_name") or "",
        "mapping": row.get("mapping") or [], "headerSignature": row.get("header_signature") or [],
        "createdBy": row.get("created_by") or "", "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedBy": row.get("updated_by") or "", "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "lastBatchId": row.get("last_batch_id"),
    }


def plan_settings(template: Optional[dict[str, Any]], *, door: str, qualified_by: str = "",
                  list_source: str = "", enters_at: Optional[str] = None,
                  referrer_partner_id: str = "", referrer_partner_name: str = "",
                  mapping: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """What a plan needs to know about how its rows enter, from a template or
    from the one-off settings the import screen posted with a mapping of its
    own. The template's values win where it is given."""
    if template:
        return {
            "door": template["door"], "qualifiedBy": template.get("qualified_by") or "",
            "listSource": template.get("list_source") or "", "entersAt": template.get("enters_at") or ENTERS_UNQUALIFIED,
            "referrerPartnerId": template.get("referrer_partner_id") or "",
            "referrerPartnerName": template.get("referrer_partner_name") or "",
            "mapping": template.get("mapping") or [], "templateId": template["id"], "templateName": template["name"],
        }
    return {
        "door": door, "qualifiedBy": qualified_by or "", "listSource": list_source or "",
        "entersAt": enters_at or ENTERS_UNQUALIFIED, "referrerPartnerId": referrer_partner_id or "",
        "referrerPartnerName": referrer_partner_name or "", "mapping": mapping or [],
        "templateId": None, "templateName": "",
    }


class ImportTemplateStoreMixin:
    """The template table's methods. Needs ``self._engine`` (CampaignStore)."""

    _engine: Any

    async def list_templates(self) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(import_template).order_by(import_template.c.name))).mappings().all()
        return [dict(r) for r in rows]

    async def get_template(self, template_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(import_template).where(import_template.c.id == template_id))).mappings().first()
        return dict(row) if row else None

    async def create_template(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        now = _now()
        row = {"id": str(uuid.uuid4()), **values, "created_by": actor, "created_at": now,
               "updated_by": actor, "updated_at": now, "last_batch_id": None}
        async with self._engine.begin() as conn:
            await conn.execute(import_template.insert().values(**row))
        return row

    async def update_template(self, template_id: str, values: dict[str, Any], *, actor: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            await conn.execute(update(import_template).where(import_template.c.id == template_id)
                               .values(**values, updated_by=actor, updated_at=_now()))
        return await self.get_template(template_id)

    async def delete_template(self, template_id: str) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(delete(import_template).where(import_template.c.id == template_id))
        return bool(result.rowcount)

    async def set_template_last_batch(self, template_id: str, batch_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(import_template).where(import_template.c.id == template_id)
                               .values(last_batch_id=batch_id))
