"""Campaign audiences — named lists and the engine that runs them (build plan
§ 7c; rulings 58–68). L1: leads and contacts.

A **list** is an ordered **recipe** of steps (ruling 62):

- ``add``    — every record of the step's type matching its conditions joins;
- ``keep``   — of the members of the step's type, only those matching stay
               (members of other types pass through untouched);
- ``remove`` — the members of the step's type matching leave.

Conditions within one step must all match (ruling 63). A **static** list runs
once and is frozen; hand ticks then change it, and "Run again" keeps them. A
**dynamic** list runs again at each campaign build; a hand edit on it is a
standing entry, always include / always exclude, applied after the recipe
(ruling 65).

The fields a step may use are a curated list per type (ruling 63) — the
setting ``CAMPAIGN_LIST_FIELDS``, editable at /setup, the defaults below when
empty. Every run is under the organisation-wide API key, like every campaign
selection; a marketing user sees a record's name and the curated fields only.

**Members are records; recipients are resolved at build time, per channel**
(§ 7c.2) and the send-time checks always apply (ruling 62): consent (rulings 9
and 19), a lead's exit or Disqualified status, a dead address (ruling 15),
one card per business for a lead (ruling 14 as scoped by ruling 68). A
Mentor, Member or Administrator contact is emailed at their ``cbmEmail`` only
(ruling 60).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from core.config import Settings
from core.crm_upsert import CONTACT_TYPE_FIELD
from core.espo import EspoError
from core.phone import e164_or_none
from core.postal import Address

from . import config as cfg
from .audience_store import KIND_DYNAMIC, KIND_STATIC, MODE_EXCLUDE, MODE_INCLUDE, STATE_IN, STATE_OUT

log = logging.getLogger("cbm_intake.campaigns.audience")

_PAGE = 200
_ID_BATCH = 100
#: A step whose result exceeds this is refused — "narrow the step" (§ 7c.4).
STEP_CAP = 20000

ACTIONS = ("add", "keep", "remove")
ACTION_LABELS = {"add": "Add matching", "keep": "Keep only matching", "remove": "Remove matching"}

#: Target types. L1 builds leads and contacts; clients, partners and funders
#: arrive with L2 (§ 7c.7).
TYPES: dict[str, dict[str, str]] = {
    "lead": {"entity": cfg.PROSPECT, "label": "Leads", "one": "lead"},
    "contact": {"entity": cfg.CONTACT, "label": "Contacts", "one": "contact"},
}
TYPES_BUILT = ("lead", "contact")

#: § 7c.3, verified against crm-test's metadata on 10-20-26. ``industry`` on a
#: lead is ruling 66's new field: offered only where the CRM has it.
DEFAULT_FIELDS: dict[str, list[str]] = {
    "lead": ["leadStatus", "leadSource", "industry", "mailingAddressPostalCode", "mailingAddressCity",
             "importBatch", "createdAt", "qualifiedAt", "sideExit"],
    "contact": [CONTACT_TYPE_FIELD, "cFunnelStage", "cMarketingOptIn", "cSmsOptIn", "cHowDidYouHear",
                "addressPostalCode", "createdAt"],
}
DEFAULT_LABELS: dict[str, dict[str, str]] = {
    "lead": {"leadStatus": "Lead status", "leadSource": "Lead Source", "industry": "Industry",
             "mailingAddressPostalCode": "Postal code", "mailingAddressCity": "City",
             "importBatch": "Import batch", "createdAt": "Arrived", "qualifiedAt": "Qualified on",
             "sideExit": "Exit"},
    "contact": {CONTACT_TYPE_FIELD: "Contact type", "cFunnelStage": "Funnel stage",
                "cMarketingOptIn": "Marketing opt-in", "cSmsOptIn": "Text-message opt-in",
                "cHowDidYouHear": "How did you hear", "addressPostalCode": "Postal code",
                "createdAt": "Created"},
}
#: The record's display name, per type.
NAME_FIELDS = {"lead": "name,businessName", "contact": "name"}

#: Contact types that are the chapter's own people: emailed at their cbmEmail
#: only (ruling 60, the standing cbm-members rule).
MEMBER_TYPES = frozenset({"Mentor", "Member", "Administrator"})
#: The "No type" choice for the contact-type picker (ruling 60).
NO_TYPE = "__none__"

# --- operators, by the field's family -----------------------------------------------------

FAMILY_OF_TYPE = {
    "enum": "choice", "multiEnum": "multi", "array": "multi", "checklist": "multi",
    "varchar": "text", "text": "text", "email": "text", "phone": "text", "url": "text",
    "date": "date", "datetime": "date", "datetimeOptional": "date",
    "int": "number", "float": "number", "currency": "number",
    "bool": "bool",
}
OPERATORS: dict[str, list[tuple[str, str]]] = {
    "choice": [("in", "is one of"), ("notIn", "is not one of"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "multi": [("anyOf", "includes any of"), ("noneOf", "includes none of"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "text": [("in", "is one of (separate with commas)"), ("contains", "contains"), ("startsWith", "starts with"), ("equals", "is exactly"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "date": [("after", "after"), ("before", "before"), ("lastDays", "within the last N days"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "number": [("atLeast", "at least"), ("atMost", "at most"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "bool": [("isTrue", "is ticked"), ("isFalse", "is not ticked")],
}


class AudienceError(Exception):
    """A list or step a marketing user can fix — the message says how."""


# --- the curated field list (ruling 63) -----------------------------------------------------

def parse_field_setting(text: str) -> dict[str, list[str]]:
    """``lead: leadStatus, leadSource; contact: cContactType`` → per-type lists.
    Empty or unparseable ⇒ {} (the defaults apply)."""
    out: dict[str, list[str]] = {}
    for part in re.split(r"[;\n]+", text or ""):
        if ":" not in part:
            continue
        kind, fields = part.split(":", 1)
        kind = kind.strip().lower()
        names = [f.strip() for f in fields.split(",") if f.strip()]
        if kind and names:
            out[kind] = names
    return out


def configured_fields(settings: Optional[Settings]) -> dict[str, list[str]]:
    custom = parse_field_setting(getattr(settings, "campaign_list_fields", "") or "")
    return {t: list(custom.get(t) or DEFAULT_FIELDS.get(t, [])) for t in TYPES}


async def _entity_fields(client, entity: str) -> dict[str, Any]:
    try:
        defs = await client.metadata(f"entityDefs.{entity}.fields")
    except Exception:  # noqa: BLE001
        return {}
    return defs if isinstance(defs, dict) else {}


async def _labels(client, entity: str) -> dict[str, str]:
    i18n = getattr(client, "i18n", None)
    if not i18n:
        return {}
    try:
        data = await i18n(entity) or {}
    except Exception:  # noqa: BLE001
        return {}
    fields = data.get("fields") if isinstance(data, dict) else None
    return fields if isinstance(fields, dict) else {}


def _humanize(name: str) -> str:
    n = re.sub(r"^c(?=[A-Z])", "", name)
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", n)
    return n[:1].upper() + n[1:].lower()


async def catalogue(client, settings: Optional[Settings], *, types: Iterable[str] = TYPES_BUILT) -> dict[str, Any]:
    """The fields a step may use, per type, read live: label, family, operators
    and the CRM's options. A configured field the CRM lacks is listed under
    ``missing`` rather than offered (ruling 63: flagged, never silently used)."""
    wanted = configured_fields(settings)
    out: dict[str, Any] = {}
    for t in types:
        entity = TYPES[t]["entity"]
        defs = await _entity_fields(client, entity)
        labels = await _labels(client, entity)
        fields, missing = [], []
        for name in wanted.get(t, []):
            d = defs.get(name)
            if not isinstance(d, dict) or d.get("disabled"):
                missing.append(name)
                continue
            family = FAMILY_OF_TYPE.get(d.get("type") or "varchar", "")
            if not family:
                missing.append(name)
                continue
            entry: dict[str, Any] = {
                "field": name,
                "label": DEFAULT_LABELS.get(t, {}).get(name) or labels.get(name) or _humanize(name),
                "family": family,
                "operators": [{"op": o, "label": l} for o, l in OPERATORS[family]],
            }
            if family in ("choice", "multi"):
                opts = [o for o in (d.get("options") or []) if o not in (None,)]
                entry["options"] = [o for o in opts if o != ""]
                if family == "multi" and name == CONTACT_TYPE_FIELD:
                    entry["options"].append(NO_TYPE)
                    entry["noTypeLabel"] = "No type"
            fields.append(entry)
        out[t] = {"label": TYPES[t]["label"], "entity": entity, "fields": fields, "missing": missing}
    return out


def field_map(cat: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    return {t: {f["field"]: f for f in v["fields"]} for t, v in cat.items()}


# --- recipes -----------------------------------------------------------------------------------

def normalise_recipe(recipe: Any) -> dict[str, Any]:
    """Shape only — the catalogue check is ``check_recipe``."""
    steps = []
    for s in (recipe or {}).get("steps") or []:
        if not isinstance(s, dict):
            continue
        conds = []
        for c in s.get("conditions") or []:
            if isinstance(c, dict) and c.get("field") and c.get("op"):
                conds.append({"field": str(c["field"]), "op": str(c["op"]), "value": c.get("value")})
        steps.append({"action": str(s.get("action") or ""), "type": str(s.get("type") or ""),
                      "conditions": conds})
    return {"steps": steps}


def check_recipe(recipe: dict[str, Any], cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Every problem, per step, in words a marketing user can act on. Empty
    means the recipe can run."""
    fmap = field_map(cat)
    problems: list[dict[str, Any]] = []

    def bad(i: int, msg: str) -> None:
        problems.append({"step": i, "message": msg})

    if not recipe["steps"]:
        bad(0, "A list needs at least one step — start with Add matching.")
    for i, s in enumerate(recipe["steps"]):
        n = i + 1
        if s["action"] not in ACTIONS:
            bad(n, f"Step {n}: choose Add, Keep only or Remove.")
        if s["type"] not in TYPES_BUILT:
            bad(n, f"Step {n}: choose what the step selects (leads or contacts).")
            continue
        if not s["conditions"]:
            bad(n, f"Step {n} has no conditions — add at least one.")
        fields = fmap.get(s["type"], {})
        for c in s["conditions"]:
            f = fields.get(c["field"])
            if not f:
                bad(n, f"Step {n}: the field {c['field']!r} is no longer offered for "
                       f"{TYPES[s['type']]['label'].lower()} — edit or remove the condition.")
                continue
            if c["op"] not in {o for o, _ in OPERATORS[f["family"]]}:
                bad(n, f"Step {n}: {f['label']} cannot use that comparison.")
                continue
            if c["op"] in ("in", "notIn", "anyOf", "noneOf") and not _as_list(c["value"]):
                bad(n, f"Step {n}: {f['label']} — tick at least one value.")
            if c["op"] in ("contains", "startsWith", "equals") and not str(c["value"] or "").strip():
                bad(n, f"Step {n}: {f['label']} — type the text to match.")
            if c["op"] in ("after", "before") and not _date(c["value"]):
                bad(n, f"Step {n}: {f['label']} — give a date.")
            if c["op"] in ("lastDays", "atLeast", "atMost") and _number(c["value"]) is None:
                bad(n, f"Step {n}: {f['label']} — give a number.")
        # Ruling 60: a contacts Add names the contact types it reaches.
        if s["type"] == "contact" and s["action"] == "add" and not any(
            c["field"] == CONTACT_TYPE_FIELD and c["op"] == "anyOf" and _as_list(c["value"])
            for c in s["conditions"]
        ):
            bad(n, f"Step {n}: adding contacts must name the contact types it reaches "
                   "(Contact type includes any of …) — ruling 60.")
    return problems


def _as_list(v: Any) -> list[str]:
    """A ticked list, or typed text separated by commas ("44113, 44114")."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if x not in (None, "") and str(x).strip()]
    if v in (None, ""):
        return []
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _date(v: Any) -> Optional[str]:
    s = str(v or "").strip()[:10]
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def _number(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _empty(attr: str) -> dict[str, Any]:
    return {"type": "or", "value": [{"type": "isNull", "attribute": attr},
                                    {"type": "equals", "attribute": attr, "value": ""}]}


def condition_where(cond: dict[str, Any], field: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    """One condition as an EspoCRM ``where`` clause."""
    a, op, v = cond["field"], cond["op"], cond.get("value")
    fam = field["family"]
    if op == "isEmpty":
        return {"type": "arrayIsEmpty", "attribute": a} if fam == "multi" else _empty(a)
    if op == "isNotEmpty":
        if fam == "multi":
            return {"type": "arrayIsNotEmpty", "attribute": a}
        return {"type": "and", "value": [{"type": "isNotNull", "attribute": a},
                                         {"type": "notEquals", "attribute": a, "value": ""}]}
    if op in ("in", "notIn"):
        return {"type": op, "attribute": a, "value": _as_list(v)}
    if op in ("anyOf", "noneOf"):
        values = _as_list(v)
        real = [x for x in values if x != NO_TYPE]
        # "No type" is an empty list OR a list holding one blank value: on
        # crm-test 14 of 61 untyped Contacts are stored as [""], which
        # arrayIsEmpty does not match (read 10-21-26).
        if op == "anyOf":
            parts = []
            if real:
                parts.append({"type": "arrayAnyOf", "attribute": a, "value": real})
            if NO_TYPE in values:
                parts += [{"type": "arrayIsEmpty", "attribute": a},
                          {"type": "arrayAnyOf", "attribute": a, "value": [""]}]
            return parts[0] if len(parts) == 1 else {"type": "or", "value": parts}
        parts = []
        if real:
            parts.append({"type": "arrayNoneOf", "attribute": a, "value": real})
        if NO_TYPE in values:
            parts += [{"type": "arrayIsNotEmpty", "attribute": a},
                      {"type": "arrayNoneOf", "attribute": a, "value": [""]}]
        return parts[0] if len(parts) == 1 else {"type": "and", "value": parts}
    if op in ("contains", "startsWith", "equals"):
        return {"type": op, "attribute": a, "value": str(v or "").strip()}
    if op in ("after", "before"):
        return {"type": op, "attribute": a, "value": _date(v)}
    if op == "lastDays":
        n = int(_number(v) or 0)
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max(n, 0))
        return {"type": "after", "attribute": a, "value": cutoff.strftime("%Y-%m-%d %H:%M:%S")}
    if op == "atLeast":
        return {"type": "greaterThanOrEquals", "attribute": a, "value": _number(v)}
    if op == "atMost":
        return {"type": "lessThanOrEquals", "attribute": a, "value": _number(v)}
    if op == "isTrue":
        return {"type": "isTrue", "attribute": a}
    if op == "isFalse":
        return {"type": "isFalse", "attribute": a}
    raise AudienceError(f"Unknown comparison {op!r}.")


def step_where(step: dict[str, Any], cat: dict[str, Any], *, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    fields = field_map(cat).get(step["type"], {})
    return [condition_where(c, fields[c["field"]], now=now) for c in step["conditions"]]


def describe_step(step: dict[str, Any], cat: dict[str, Any]) -> str:
    """The step in a sentence — the history line and the build summary."""
    fields = field_map(cat).get(step["type"], {})
    parts = []
    for c in step["conditions"]:
        f = fields.get(c["field"]) or {"label": c["field"], "family": "text"}
        op_label = dict(OPERATORS.get(f["family"], [])).get(c["op"], c["op"])
        val = c.get("value")
        if isinstance(val, list):
            val = ", ".join("No type" if x == NO_TYPE else str(x) for x in val)
        parts.append(f"{f['label']} {op_label}" + (f" {val}" if val not in (None, "") else ""))
    noun = TYPES.get(step["type"], {}).get("label", step["type"]).lower()
    return f"{ACTION_LABELS.get(step['action'], step['action'])}: {noun} where " + " and ".join(parts)


# --- running ------------------------------------------------------------------------------------

async def _ids_matching(client, entity: str, where: list[dict[str, Any]], *, cap: int = STEP_CAP) -> list[str]:
    out: list[str] = []
    offset = 0
    while True:
        page = await client.list(entity, select="id", where=where, max_size=_PAGE, offset=offset,
                                 order_by="createdAt", order="asc")
        batch = page.get("list", [])
        out.extend(r["id"] for r in batch if r.get("id"))
        if len(out) > cap:
            raise AudienceError(f"This step matches more than {cap:,} records — narrow the step.")
        if len(batch) < _PAGE:
            return out
        offset += _PAGE


async def _ids_matching_within(client, entity: str, where: list[dict[str, Any]], ids: list[str]) -> set[str]:
    """Which of these ids match — the Keep only and Remove steps test only the
    current members, in batches, so they never hit the cap."""
    out: set[str] = set()
    for i in range(0, len(ids), _ID_BATCH):
        chunk = ids[i:i + _ID_BATCH]
        page = await client.list(entity, select="id", max_size=_PAGE,
                                 where=[{"type": "in", "attribute": "id", "value": chunk}, *where])
        out.update(r["id"] for r in page.get("list", []) if r.get("id"))
    return out


def split_key(key: str) -> tuple[str, str]:
    t, _, rid = key.partition(":")
    return t, rid


async def run_recipe(client, recipe: dict[str, Any], cat: dict[str, Any], *,
                     now: Optional[datetime] = None) -> dict[str, Any]:
    """Run the steps in order. Returns ``keys`` (key → the step that added it,
    in order), and per step its before / after counts."""
    problems = check_recipe(recipe, cat)
    if problems:
        raise AudienceError(problems[0]["message"])
    working: dict[str, int] = {}
    report = []
    for i, step in enumerate(recipe["steps"], start=1):
        before = len(working)
        entity = TYPES[step["type"]]["entity"]
        where = step_where(step, cat, now=now)
        prefix = step["type"] + ":"
        if step["action"] == "add":
            for rid in await _ids_matching(client, entity, where):
                working.setdefault(prefix + rid, i)
        else:
            of_type = [split_key(k)[1] for k in working if k.startswith(prefix)]
            matched = await _ids_matching_within(client, entity, where, of_type)
            for rid in of_type:
                hit = rid in matched
                if (step["action"] == "keep" and not hit) or (step["action"] == "remove" and hit):
                    working.pop(prefix + rid, None)
        after = len(working)
        report.append({"step": i, "summary": describe_step(step, cat), "before": before, "after": after,
                       "added": max(after - before, 0), "dropped": max(before - after, 0)})
    return {"keys": working, "steps": report, "total": len(working)}


def apply_hand(keys: dict[str, int], hand_rows: list[dict[str, Any]]) -> dict[str, int]:
    """A static list's hand ticks over a run's result."""
    out = dict(keys)
    for r in hand_rows:
        if r.get("source") != "hand":
            continue
        if r.get("state") == STATE_OUT:
            out.pop(r["target_key"], None)
        elif r.get("state") == STATE_IN:
            out.setdefault(r["target_key"], 0)
    return out


def apply_entries(keys: dict[str, int], entries: list[dict[str, Any]]) -> dict[str, int]:
    """A dynamic list's standing entries, after the recipe (ruling 65)."""
    out = dict(keys)
    for e in entries:
        if e.get("mode") == MODE_EXCLUDE:
            out.pop(e["target_key"], None)
        elif e.get("mode") == MODE_INCLUDE:
            out.setdefault(e["target_key"], 0)
    return out


async def current_members(client, store, row: dict[str, Any], cat: dict[str, Any]) -> dict[str, Any]:
    """The list as a campaign would send to it now: a static list's frozen
    membership; a dynamic list's recipe run now, with its standing entries."""
    if row["kind"] == KIND_STATIC:
        rows = await store.member_rows(row["id"])
        if row.get("last_run_at") is None:
            raise AudienceError(f"The static list \"{row['name']}\" has never been run — run it first.")
        keys = {r["target_key"]: (r.get("step") or 0) for r in rows if r.get("state") == STATE_IN}
        return {"keys": keys, "steps": (row.get("last_run") or {}).get("steps", []), "total": len(keys),
                "frozen": True}
    result = await run_recipe(client, normalise_recipe(row["recipe"]), cat)
    keys = apply_entries(result["keys"], await store.entries(row["id"]))
    return {**result, "keys": keys, "total": len(keys), "frozen": False}


# --- showing members -------------------------------------------------------------------------

def used_fields(recipe: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in recipe.get("steps") or []:
        for c in s.get("conditions") or []:
            lst = out.setdefault(s.get("type") or "", [])
            if c.get("field") and c["field"] not in lst:
                lst.append(c["field"])
    return out


async def describe_members(client, keys: list[str], recipe: dict[str, Any], cat: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per key: its type, name and the values of the curated fields
    the recipe used — nothing else (§ 7c.4, who sees what). A record the CRM
    no longer holds is flagged, never dropped."""
    used = used_fields(recipe)
    fmap = field_map(cat)
    by_type: dict[str, list[str]] = {}
    for k in keys:
        t, rid = split_key(k)
        by_type.setdefault(t, []).append(rid)
    found: dict[str, dict[str, Any]] = {}
    for t, ids in by_type.items():
        if t not in TYPES:
            continue
        cols = [f for f in used.get(t, []) if f in fmap.get(t, {})]
        select = ",".join(dict.fromkeys(["id", *NAME_FIELDS[t].split(","), *cols]))
        for i in range(0, len(ids), _ID_BATCH):
            page = await client.list(TYPES[t]["entity"], select=select, max_size=_PAGE,
                                     where=[{"type": "in", "attribute": "id", "value": ids[i:i + _ID_BATCH]}])
            for r in page.get("list", []):
                found[f"{t}:{r['id']}"] = r
    out = []
    for k in keys:
        t, rid = split_key(k)
        r = found.get(k)
        if not r:
            out.append({"key": k, "type": t, "id": rid, "name": "(no longer in the CRM)", "missing": True,
                        "values": {}})
            continue
        name = (r.get("businessName") or r.get("name") or "") if t == "lead" else (r.get("name") or "")
        values = {}
        for f in used.get(t, []):
            if f in fmap.get(t, {}):
                v = r.get(f)
                values[fmap[t][f]["label"]] = ", ".join(map(str, v)) if isinstance(v, list) else v
        out.append({"key": k, "type": t, "id": rid, "name": name, "missing": False, "values": values})
    return out


# --- recipients, per channel (§ 7c.2) -----------------------------------------------------------

CONTACT_SELECT = (
    f"id,name,firstName,lastName,emailAddress,emailAddressIsOptedOut,emailAddressIsInvalid,"
    f"cMarketingOptIn,phoneNumber,phoneNumberIsOptedOut,doNotCall,cSmsOptIn,{CONTACT_TYPE_FIELD},"
    f"cFunnelStage,accountId,addressStreet,addressCity,addressState,addressPostalCode,addressCountry"
)
SKIP = {
    "missing": "no longer in the CRM",
    "exit": "the lead has left (an exit is set)",
    "disqualified": "the lead is Disqualified",
    "no_address": "no usable mailing address",
    "carded": "already sent a postcard (one per business, ruling 14)",
    "no_contact": "a lead with no Contact yet — only a Contact can be emailed or texted",
    "no_consent": "no consent for this channel",
    "no_email": "no usable email address",
    "member_no_cbm_email": "a chapter member with no chapter email address",
    "no_phone": "no usable phone number",
    "do_not_call": "do not call, or the phone is opted out",
    "declined": "declined a call before",
    "duplicate": "the same person or address is already on the list",
}


async def _by_ids(client, entity: str, ids: list[str], select: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), _ID_BATCH):
        page = await client.list(entity, select=select, max_size=_PAGE,
                                 where=[{"type": "in", "attribute": "id", "value": ids[i:i + _ID_BATCH]}])
        for r in page.get("list", []):
            out[r["id"]] = r
    return out


async def cbm_emails(client, contact_ids: list[str]) -> dict[str, str]:
    """Contact id → the chapter email address on that member's mentor profile."""
    out: dict[str, str] = {}
    ids = list(dict.fromkeys(i for i in contact_ids if i))
    for i in range(0, len(ids), _ID_BATCH):
        try:
            page = await client.list("CMentorProfile", select="id,cbmEmail,contactRecordId", max_size=_PAGE,
                                     where=[{"type": "in", "attribute": "contactRecordId",
                                             "value": ids[i:i + _ID_BATCH]}])
        except EspoError as exc:
            log.warning("audience: mentor profiles unreadable for cbmEmail: %s", exc)
            return out
        for r in page.get("list", []):
            if r.get("contactRecordId") and (r.get("cbmEmail") or "").strip():
                out[r["contactRecordId"]] = r["cbmEmail"].strip()
    return out


def is_member(contact: dict[str, Any]) -> bool:
    return bool(MEMBER_TYPES & set(contact.get(CONTACT_TYPE_FIELD) or []))


def email_consented(c: dict[str, Any]) -> bool:
    return bool(c.get("cMarketingOptIn")) and not c.get("emailAddressIsOptedOut")


async def address_for_email(client, contact: dict[str, Any]) -> Optional[str]:
    """The address a campaign email goes to: a chapter member's cbmEmail, else
    the Contact's own usable address. None when there is none."""
    if is_member(contact):
        return (await cbm_emails(client, [contact["id"]])).get(contact["id"])
    if contact.get("emailAddress") and not contact.get("emailAddressIsInvalid"):
        return contact["emailAddress"].strip()
    return None


def _company_address(c: dict[str, Any]) -> Address:
    return Address(name=c.get("name") or "", line1=c.get("billingAddressStreet") or "",
                   city=c.get("billingAddressCity") or "", state=c.get("billingAddressState") or "",
                   postal_code=c.get("billingAddressPostalCode") or "",
                   country=c.get("billingAddressCountry") or "US")


def contact_address(c: dict[str, Any]) -> Address:
    return Address(name=c.get("name") or "", line1=c.get("addressStreet") or "",
                   city=c.get("addressCity") or "", state=c.get("addressState") or "",
                   postal_code=c.get("addressPostalCode") or "", country=c.get("addressCountry") or "US")


async def resolve_targets(client, kind: str, keys: Iterable[str]) -> dict[str, Any]:
    """The list's members as the targets ``kind``'s ``build_list`` writes as
    Planned touches, with every send-time check applied and each skip counted
    by reason. The target dicts are the shapes each kind's own selection
    produces."""
    from . import calls, postcard  # local: those modules import nothing from here

    keys = list(keys)
    lead_ids = [split_key(k)[1] for k in keys if k.startswith("lead:")]
    contact_ids = [split_key(k)[1] for k in keys if k.startswith("contact:")]
    leads = await _by_ids(client, cfg.PROSPECT, lead_ids, cfg.PROSPECT_SELECT)
    promoted = [p.get("promotedContactId") for p in leads.values() if p.get("promotedContactId")]
    contacts = await _by_ids(client, cfg.CONTACT, contact_ids + promoted, CONTACT_SELECT)
    # A Contact whose lead has left stopped with it (the existing call / text rule).
    left: set[str] = set()
    for i in range(0, len(contact_ids), _ID_BATCH):
        page = await client.list(cfg.PROSPECT, select="id,sideExit,promotedContactId", max_size=_PAGE, where=[
            {"type": "in", "attribute": "promotedContactId", "value": contact_ids[i:i + _ID_BATCH]},
            {"type": "isNotNull", "attribute": "sideExit"}])
        left.update(p["promotedContactId"] for p in page.get("list", []) if p.get("promotedContactId"))

    skipped: Counter = Counter()
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take(t: dict[str, Any], dedupe: str) -> None:
        if t["key"] in seen or dedupe in seen:
            skipped["duplicate"] += 1
            return
        seen.add(t["key"]); seen.add(dedupe)
        targets.append(t)

    def lead_ok(p: dict[str, Any]) -> bool:
        if p.get("sideExit"):
            skipped["exit"] += 1
            return False
        if p.get("leadStatus") == cfg.LEAD_DISQUALIFIED:
            skipped["disqualified"] += 1
            return False
        return True

    # The person each member stands for, for the person channels.
    def people() -> list[tuple[str, dict[str, Any]]]:
        out = []
        for k in keys:
            t, rid = split_key(k)
            if t == "lead":
                p = leads.get(rid)
                if not p:
                    skipped["missing"] += 1
                    continue
                if not lead_ok(p):
                    continue
                c = contacts.get(p.get("promotedContactId") or "")
                if not c:
                    if kind == cfg.KIND_CALL and p.get("phone"):
                        out.append((k, {"_lead": p}))
                    else:
                        skipped["no_contact" if kind != cfg.KIND_CALL else "no_phone"] += 1
                    continue
                out.append((k, c))
            elif t == "contact":
                c = contacts.get(rid)
                if not c:
                    skipped["missing"] += 1
                    continue
                if rid in left:
                    skipped["exit"] += 1
                    continue
                out.append((k, c))
        return out

    if kind == cfg.KIND_POSTCARD:
        carded = await postcard._carded_targets(client)
        account_ids = [c.get("accountId") for c in contacts.values() if c.get("accountId")]
        accounts = await _by_ids(client, cfg.ACCOUNT, account_ids,
                                 "id,name,cFunnelStage,billingAddressStreet,billingAddressCity,"
                                 "billingAddressState,billingAddressPostalCode,billingAddressCountry")
        for k in keys:
            t, rid = split_key(k)
            if t == "lead":
                p = leads.get(rid)
                if not p:
                    skipped["missing"] += 1
                    continue
                if not lead_ok(p):
                    continue
                if f"prospect:{rid}" in carded or (p.get("promotedCompanyId")
                                                  and f"company:{p['promotedCompanyId']}" in carded):
                    skipped["carded"] += 1
                    continue
                address = postcard._prospect_address(p)
                if p.get("addressStatus") != cfg.ADDRESS_USABLE or not address.is_complete():
                    skipped["no_address"] += 1
                    continue
                take({"key": f"prospect:{rid}", "kind": "prospect", "id": rid,
                      "name": p.get("businessName") or p.get("name") or "", "address": address,
                      "stage": p.get("leadStatus")}, _card_key(address))
            elif t == "contact":
                c = contacts.get(rid)
                if not c:
                    skipped["missing"] += 1
                    continue
                if rid in left:
                    skipped["exit"] += 1
                    continue
                acct = accounts.get(c.get("accountId") or "")
                if acct and _company_address(acct).is_complete():
                    address = _company_address(acct)
                    take({"key": f"company:{acct['id']}", "kind": "company", "id": acct["id"],
                          "name": acct.get("name") or "", "address": address, "stage": acct.get("cFunnelStage")},
                         _card_key(address))
                    continue
                address = contact_address(c)
                if not address.is_complete():
                    skipped["no_address"] += 1
                    continue
                take({"key": f"contact:{rid}", "kind": "contact", "id": rid, "name": c.get("name") or "",
                      "address": address, "stage": c.get("cFunnelStage")},
                     _card_key(address))
        return {"targets": targets, "skipped": _skips(skipped)}

    persons = people()
    if kind == cfg.KIND_EMAIL:
        members = [c["id"] for _, c in persons if c.get("id") and is_member(c)]
        cbm = await cbm_emails(client, members)
        for _k, c in persons:
            if not email_consented(c):
                skipped["no_consent"] += 1
                continue
            if is_member(c):
                email = cbm.get(c["id"])
                if not email:
                    skipped["member_no_cbm_email"] += 1
                    continue
            else:
                email = (c.get("emailAddress") or "").strip()
                if not email or c.get("emailAddressIsInvalid"):
                    skipped["no_email"] += 1
                    continue
            take({"key": f"contact:{c['id']}", "kind": "contact", "id": c["id"], "name": c.get("name") or "",
                  "email": email, "first": c.get("firstName") or "", "last": c.get("lastName") or "",
                  "stage": c.get("cFunnelStage")}, "email:" + email.lower())
    elif kind == cfg.KIND_SMS:
        for _k, c in persons:
            if not c.get("cSmsOptIn"):
                skipped["no_consent"] += 1
                continue
            phone = e164_or_none(c.get("phoneNumber"))
            if not phone or c.get("phoneNumberIsOptedOut"):
                skipped["no_phone"] += 1
                continue
            take({"key": f"contact:{c['id']}", "kind": "contact", "id": c["id"], "name": c.get("name") or "",
                  "phone": phone, "stage": c.get("cFunnelStage")}, "phone:" + phone)
    elif kind == cfg.KIND_CALL:
        declined = await calls.declined_targets(client)
        for k, c in persons:
            lead = c.get("_lead")
            if lead:
                key = f"prospect:{lead['id']}"
                if key in declined:
                    skipped["declined"] += 1
                    continue
                take({"key": key, "kind": "prospect", "id": lead["id"],
                      "name": lead.get("businessName") or lead.get("name") or "", "phone": lead["phone"],
                      "stage": lead.get("leadStatus")}, "phone:" + str(lead["phone"]))
                continue
            key = f"contact:{c['id']}"
            if key in declined or (k.startswith("lead:") and f"prospect:{split_key(k)[1]}" in declined):
                skipped["declined"] += 1
                continue
            if c.get("doNotCall") or c.get("phoneNumberIsOptedOut"):
                skipped["do_not_call"] += 1
                continue
            phone = c.get("phoneNumber")
            if not phone and k.startswith("lead:"):
                phone = (leads.get(split_key(k)[1]) or {}).get("phone")
            if not phone:
                skipped["no_phone"] += 1
                continue
            take({"key": key, "kind": "contact", "id": c["id"], "name": c.get("name") or "",
                  "phone": phone, "stage": c.get("cFunnelStage")}, "phone:" + str(phone))
    else:
        raise AudienceError(f"A {kind} campaign does not send to a list.")
    return {"targets": targets, "skipped": _skips(skipped)}


def _card_key(address: Address) -> str:
    """One card per name at an address: two businesses in one building are two
    cards; the same business twice is one."""
    from .postcard import address_text
    return "addr:" + f"{address.name}|{address_text(address)}".lower()


def _skips(counter: Counter) -> list[dict[str, Any]]:
    return [{"reason": SKIP.get(r, r), "code": r, "count": n} for r, n in counter.most_common() if n]


def audience_result(audience: dict[str, Any]) -> dict[str, Any]:
    """What a build reports about the list it sent to — the sign-off screen's
    members, reached and skip reasons (§ 7c.4)."""
    return {"list": audience["list"], "members": audience["members"],
            "reached": len(audience["targets"]), "skipped": audience["skipped"]}


async def audience_for_build(client, store, settings: Settings, campaign: dict[str, Any]) -> Optional[dict[str, Any]]:
    """What a campaign build sends to when the campaign names a list: the
    targets, the skips and the summary. None when it names none (the kind's
    own rule then applies, as before § 7c)."""
    if not getattr(settings, "campaign_lists", False) or store is None:
        return None
    chosen = await store.get_campaign_audience(campaign["id"])
    if not chosen:
        return None
    row = await store.get_list(chosen["list_id"])
    if not row:
        raise AudienceError("The campaign's list no longer exists — choose another.")
    cat = await catalogue(client, settings)
    members = await current_members(client, store, row, cat)
    resolved = await resolve_targets(client, campaign.get("campaignKind") or cfg.KIND_POSTCARD, members["keys"])
    skipped_total = sum(s["count"] for s in resolved["skipped"])
    summary = (f"The {row['kind']} list \"{row['name']}\" (version {row['version']}): "
               f"{members['total']} members, {len(resolved['targets'])} reached, {skipped_total} skipped.")
    return {"list": {"id": row["id"], "name": row["name"], "kind": row["kind"], "version": row["version"]},
            "members": members["total"], "targets": resolved["targets"], "skipped": resolved["skipped"],
            "summary": summary}
