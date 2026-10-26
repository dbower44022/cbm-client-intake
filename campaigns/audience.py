"""Campaign audiences — named lists and the engine that runs them (build plan
§ 7c, reshaped by § 7e.8; rulings 58–68 and 90–94). Leads, contacts, clients
(an engagement), partners and funders; fields reached through a link; lists of
lists; imports.

A **dynamic** list is a search and nothing else (rulings 90–92): its recipe is
``{"include": [group, …], "exclude": [group, …]}``, and its members are the
union of the Include groups minus the union of the Leave out groups. Leave out
always wins; groups have no order. A group is one of:

- ``match``  — every record of one type matching all its conditions (ruling 63);
- ``list``   — everyone on another list (a static exclusion list, typically);
- ``import`` — the records a pasted file names (CRM ids, or email addresses
               for leads and contacts); a row matching nothing is counted,
               never created.

It runs again at every campaign build. A person kept off it goes onto a static
exclusion list the dynamic list leaves out (the member grid's *Exclude*).

A **static** list is people added by hand and nothing else (rulings 91, 94):
its recipe is empty and never run. Its *Add people* uses the same condition
panel, copied once, no search saved. A list's kind is fixed (ruling 93).

The fields a group may use are a curated list per type (ruling 63) — the
setting ``CAMPAIGN_LIST_FIELDS``, editable at /setup, the defaults below when
empty. A name with dots follows links: ``engagementClient.industrySector`` is
the client profile's sector; ``engagementClient.linkedCompany.billingAddressPostalCode``
goes on to its Company. Every run is under the organisation-wide API key, like
every campaign selection; a marketing user sees a record's name and the curated
fields only.

**Members are records; recipients are resolved at build time, per channel**
(§ 7c.2) and the send-time checks always apply (ruling 62): consent (rulings 9
and 19), a lead's exit or Disqualified status, a dead address (ruling 15),
one card per business for a lead (ruling 14 as scoped by ruling 68). A client,
partner or funder reaches its primary contact, or every contact on the record
when the campaign ticks *Include every contact* (ruling 59). A Mentor, Member
or Administrator contact is emailed at their ``cbmEmail`` only (ruling 60).
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
from .audience_store import KIND_STATIC, STATE_IN

log = logging.getLogger("cbm_intake.campaigns.audience")

_PAGE = 200
_ID_BATCH = 100
#: A group whose result exceeds this is refused — "narrow it" (§ 7c.4).
STEP_CAP = 20000
#: A condition reached through a link resolves to the linked records' ids
#: first; above this many the group is refused rather than sent as one huge
#: filter.
VIA_CAP = 2000
#: Rows a pasted import may hold.
IMPORT_CAP = 2000
#: How deep "members of another list" may nest.
LIST_DEPTH = 5

GROUP_MATCH = "match"
GROUP_LIST = "list"
GROUP_IMPORT = "import"
GROUP_KINDS = (GROUP_MATCH, GROUP_LIST, GROUP_IMPORT)
GROUP_LABELS = {GROUP_MATCH: "Records matching conditions", GROUP_LIST: "Everyone on another list",
                GROUP_IMPORT: "The records a file names"}
SIDES = ("include", "exclude")
SIDE_LABELS = {"include": "Include", "exclude": "Leave out"}

TYPES: dict[str, dict[str, str]] = {
    "lead": {"entity": cfg.PROSPECT, "label": "Leads", "one": "Lead"},
    "contact": {"entity": cfg.CONTACT, "label": "Contacts", "one": "Contact"},
    "client": {"entity": "CEngagement", "label": "Clients", "one": "Client"},
    "partner": {"entity": "CPartnerProfile", "label": "Partners", "one": "Partner"},
    "funder": {"entity": "CSponsorProfile", "label": "Funders", "one": "Funder"},
}
TYPES_BUILT = ("lead", "contact", "client", "partner", "funder")
#: The record types whose people are reached through the record (ruling 59).
ORG_TYPES = ("client", "partner", "funder")

#: § 7c.3, verified against crm-test's metadata on 10-20-26. ``industry`` on a
#: lead (ruling 66) and ``funderStatus`` (ruling 67) are offered only where the
#: CRM has them; so are the lead's ``qualificationLevel`` and ``phone`` (added
#: by M7, owed from M6's live pass: the ready-made lists of M8 filter on the
#: level).
DEFAULT_FIELDS: dict[str, list[str]] = {
    "lead": ["leadStatus", "leadSource", "industry", "mailingAddressPostalCode", "mailingAddressCity",
             "importBatch", "createdAt", "qualifiedAt", "sideExit", "qualificationLevel", "phone"],
    "contact": [CONTACT_TYPE_FIELD, "cFunnelStage", "cMarketingOptIn", "cSmsOptIn", "cHowDidYouHear",
                "addressPostalCode", "createdAt"],
    "client": ["engagementStatus", "closeDate", "closeReason", "engagementStartDate", "mentoringFocusAreas",
               "referringPartner", "outreachCampaign", "engagementClient.industrySector",
               "engagementClient.annualRevenueRange", "engagementClient.numberOfEmployees",
               "engagementClient.isHomeBased", "engagementClient.linkedCompany.billingAddressPostalCode"],
    "partner": ["partnershipStatus", "partnershipType", "partnerManager", "partnershipStartDate", "lastContacted",
                "partnerCompany.cIndustrySector", "partnerCompany.billingAddressPostalCode"],
    "funder": ["funderStatus", "cBMSponsorManager", "lastContribution", "totalContribution", "lastContacted",
               "sponsorCompany.cSponsorshipLevel", "sponsorCompany.cSponsorshipRenewalDate",
               "sponsorCompany.billingAddressPostalCode"],
}
DEFAULT_LABELS: dict[str, dict[str, str]] = {
    "lead": {"leadStatus": "Lead status", "leadSource": "Lead Source", "industry": "Industry",
             "qualificationLevel": "Level", "phone": "Phone",
             "mailingAddressPostalCode": "Postal code", "mailingAddressCity": "City",
             "importBatch": "Import batch", "createdAt": "Arrived", "qualifiedAt": "Qualified on",
             "sideExit": "Exit"},
    "contact": {CONTACT_TYPE_FIELD: "Contact type", "cFunnelStage": "Funnel stage",
                "cMarketingOptIn": "Marketing opt-in", "cSmsOptIn": "Text-message opt-in",
                "cHowDidYouHear": "How did you hear", "addressPostalCode": "Postal code",
                "createdAt": "Created"},
    "client": {"engagementStatus": "Engagement status", "closeDate": "Close date", "closeReason": "Close reason",
               "engagementStartDate": "Start date", "mentoringFocusAreas": "Mentoring focus areas",
               "referringPartner": "Referring partner", "outreachCampaign": "Outreach campaign",
               "engagementClient.industrySector": "Industry sector",
               "engagementClient.annualRevenueRange": "Annual revenue range",
               "engagementClient.numberOfEmployees": "Number of employees",
               "engagementClient.isHomeBased": "Home-based",
               "engagementClient.linkedCompany.billingAddressPostalCode": "Company postal code"},
    "partner": {"partnershipStatus": "Partnership status", "partnershipType": "Partnership type",
                "partnerManager": "Partner manager", "partnershipStartDate": "Partnership start date",
                "lastContacted": "Last contacted", "partnerCompany.cIndustrySector": "Industry sector",
                "partnerCompany.billingAddressPostalCode": "Company postal code"},
    "funder": {"funderStatus": "Funder status", "cBMSponsorManager": "Funder manager",
               "lastContribution": "Last contribution", "totalContribution": "Total contribution",
               "lastContacted": "Last contacted", "sponsorCompany.cSponsorshipLevel": "Sponsorship level",
               "sponsorCompany.cSponsorshipRenewalDate": "Sponsorship renewal date",
               "sponsorCompany.billingAddressPostalCode": "Company postal code"},
}
#: The record's display name, per type.
NAME_FIELDS = {"lead": "name,businessName", "contact": "name", "client": "name", "partner": "name", "funder": "name"}

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
    "bool": "bool", "link": "link",
}
OPERATORS: dict[str, list[tuple[str, str]]] = {
    "choice": [("in", "is one of"), ("notIn", "is not one of"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "multi": [("anyOf", "includes any of"), ("noneOf", "includes none of"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "text": [("in", "is one of (separate with commas)"), ("contains", "contains"), ("startsWith", "starts with"), ("equals", "is exactly"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "date": [("after", "after"), ("before", "before"), ("lastDays", "within the last N days"),
             ("olderDays", "more than N days ago"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "number": [("atLeast", "at least"), ("atMost", "at most"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
    "bool": [("isTrue", "is ticked"), ("isFalse", "is not ticked")],
    "link": [("in", "is one of"), ("notIn", "is not one of"), ("isEmpty", "is empty"), ("isNotEmpty", "is not empty")],
}


class AudienceError(Exception):
    """A list or group a marketing user can fix — the message says how."""


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


async def _meta(client, key: str) -> dict[str, Any]:
    try:
        defs = await client.metadata(key)
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
    n = re.sub(r"^c(?=[A-Z])", "", name.split(".")[-1])
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", n)
    return n[:1].upper() + n[1:].lower()


async def resolve_path(client, entity: str, name: str) -> Optional[dict[str, Any]]:
    """A field name, possibly through links (``a.b.field``), as the hops to
    walk and the leaf field's definition — or None when the CRM lacks any part.
    A hop is a belongsTo (the key is on this side, ``<link>Id``) or a hasOne
    (the key is on the other side, the foreign link's ``<foreign>Id``)."""
    parts = name.split(".")
    hops = []
    current = entity
    for link in parts[:-1]:
        links = await _meta(client, f"entityDefs.{current}.links")
        ld = links.get(link)
        if not isinstance(ld, dict) or not ld.get("entity"):
            return None
        if ld.get("type") == "belongsTo":
            hops.append({"link": link, "from": current, "to": ld["entity"], "kind": "belongsTo"})
        elif ld.get("type") == "hasOne" and ld.get("foreign"):
            hops.append({"link": link, "from": current, "to": ld["entity"], "kind": "hasOne",
                         "foreign": ld["foreign"]})
        else:
            return None
        current = ld["entity"]
    defs = await _meta(client, f"entityDefs.{current}.fields")
    leaf = defs.get(parts[-1])
    if not isinstance(leaf, dict) or leaf.get("disabled"):
        return None
    out: dict[str, Any] = {"hops": hops, "entity": current, "leaf": parts[-1], "def": leaf}
    if leaf.get("type") == "link":
        links = await _meta(client, f"entityDefs.{current}.links")
        target = (links.get(parts[-1]) or {}).get("entity")
        if not target or (links.get(parts[-1]) or {}).get("type") != "belongsTo":
            return None
        out["target"] = target
    return out


async def _link_options(client, entity: str) -> list[dict[str, str]]:
    try:
        page = await client.list(entity, select="id,name", max_size=_PAGE, order_by="name", order="asc")
    except EspoError as exc:
        log.warning("audience: %s options unreadable: %s", entity, exc)
        return []
    return [{"value": r["id"], "label": r.get("name") or r["id"]} for r in page.get("list", []) if r.get("id")]


async def catalogue(client, settings: Optional[Settings], *, types: Iterable[str] = TYPES_BUILT) -> dict[str, Any]:
    """The fields a group may use, per type, read live: label, family, operators
    and the CRM's options. A configured field the CRM lacks is listed under
    ``missing`` rather than offered (ruling 63: flagged, never silently used)."""
    wanted = configured_fields(settings)
    out: dict[str, Any] = {}
    for t in types:
        entity = TYPES[t]["entity"]
        labels = await _labels(client, entity)
        fields, missing = [], []
        for name in wanted.get(t, []):
            path = await resolve_path(client, entity, name)
            if not path:
                missing.append(name)
                continue
            d = path["def"]
            family = FAMILY_OF_TYPE.get(d.get("type") or "varchar", "")
            if not family:
                missing.append(name)
                continue
            label = DEFAULT_LABELS.get(t, {}).get(name) or (labels.get(name) if not path["hops"] else None) \
                or _humanize(name)
            if path["hops"] and name not in DEFAULT_LABELS.get(t, {}):
                label += " (" + " → ".join(_humanize(h["link"]).lower() for h in path["hops"]) + ")"
            entry: dict[str, Any] = {
                "field": name, "label": label, "family": family,
                "operators": [{"op": o, "label": lab} for o, lab in OPERATORS[family]],
                "hops": path["hops"], "leaf": path["leaf"], "leafEntity": path["entity"],
            }
            if family in ("choice", "multi"):
                entry["options"] = [o for o in (d.get("options") or []) if o not in (None, "")]
                if family == "multi" and name == CONTACT_TYPE_FIELD:
                    entry["options"].append(NO_TYPE)
                    entry["noTypeLabel"] = "No type"
            if family == "link":
                entry["options"] = await _link_options(client, path["target"])
            fields.append(entry)
        out[t] = {"label": TYPES[t]["label"], "entity": entity, "fields": fields, "missing": missing}
    return out


def field_map(cat: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    return {t: {f["field"]: f for f in v["fields"]} for t, v in cat.items()}


# --- recipes: Include and Leave out (ruling 90) ------------------------------------------------

def _import_values(v: Any) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[\s,;]+", v)
    return [str(x).strip().strip('"') for x in (v or []) if str(x).strip().strip('"')]


def empty_recipe() -> dict[str, Any]:
    return {"include": [], "exclude": []}


def normalise_group(g: Any) -> Optional[dict[str, Any]]:
    """One group's shape; the catalogue check is ``check_recipe``."""
    if not isinstance(g, dict):
        return None
    kind = str(g.get("kind") or "")
    if kind == GROUP_LIST:
        return {"kind": GROUP_LIST, "listId": str(g.get("listId") or "")}
    if kind == GROUP_IMPORT:
        return {"kind": GROUP_IMPORT, "type": str(g.get("type") or ""), "values": _import_values(g.get("values"))}
    conds = [{"field": str(c["field"]), "op": str(c["op"]), "value": c.get("value")}
             for c in g.get("conditions") or [] if isinstance(c, dict) and c.get("field") and c.get("op")]
    return {"kind": kind or GROUP_MATCH, "type": str(g.get("type") or ""), "conditions": conds}


def normalise_recipe(recipe: Any) -> dict[str, Any]:
    """Shape only: ``{"include": [group], "exclude": [group]}``."""
    recipe = recipe if isinstance(recipe, dict) else {}
    return {side: [n for n in (normalise_group(g) for g in recipe.get(side) or []) if n] for side in SIDES}


def groups(recipe: dict[str, Any]) -> Iterable[tuple[str, int, dict[str, Any]]]:
    """Every group as (side, 1-based index, group)."""
    for side in SIDES:
        for i, g in enumerate(recipe.get(side) or [], start=1):
            yield side, i, g


def referenced_lists(recipe: dict[str, Any]) -> list[str]:
    return [g["listId"] for _s, _i, g in groups(recipe) if g.get("kind") == GROUP_LIST and g.get("listId")]


def group_label(side: str, i: int) -> str:
    return f"{SIDE_LABELS[side]} group {i}"


def check_recipe(recipe: dict[str, Any], cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Every problem, per group, in words a marketing user can act on. Empty
    means the recipe can run."""
    fmap = field_map(cat)
    problems: list[dict[str, Any]] = []

    def bad(side: str, i: int, msg: str) -> None:
        problems.append({"side": side, "group": i, "message": msg})

    if not recipe.get("include"):
        bad("include", 0, "A dynamic list needs at least one Include group — press + Group under Include.")
    for side, i, g in groups(recipe):
        at = group_label(side, i)
        if g["kind"] not in GROUP_KINDS:
            bad(side, i, f"{at}: choose what the group holds.")
            continue
        if g["kind"] == GROUP_LIST:
            if not g.get("listId"):
                bad(side, i, f"{at}: choose the list whose members it holds.")
            continue
        if g["type"] not in TYPES_BUILT:
            bad(side, i, f"{at}: choose what it selects (leads, contacts, clients, partners or funders).")
            continue
        if g["kind"] == GROUP_IMPORT:
            vals = g.get("values") or []
            if not vals:
                bad(side, i, f"{at}: paste the CRM ids or email addresses, or choose a file.")
            elif len(vals) > IMPORT_CAP:
                bad(side, i, f"{at}: a file may hold at most {IMPORT_CAP:,} rows — split it into two groups.")
            elif g["type"] in ORG_TYPES and any("@" in v for v in vals):
                bad(side, i, f"{at}: {TYPES[g['type']]['label'].lower()} are matched by CRM id only — "
                             "email addresses match leads and contacts.")
            continue
        problems.extend({"side": side, "group": i, "message": f"{at}: {m}"}
                        for m in condition_problems(g, fmap))
        # A contacts Include names the contact types it reaches: a chapter
        # member is never swept in by accident.
        if side == "include" and g["type"] == "contact" and not names_contact_types(g):
            bad(side, i, f"{at}: a group of contacts must name the contact types it reaches "
                         "(Contact type includes any of …).")
    return problems


def names_contact_types(g: dict[str, Any]) -> bool:
    return any(c["field"] == CONTACT_TYPE_FIELD and c["op"] == "anyOf" and _as_list(c["value"])
               for c in g.get("conditions") or [])


def condition_problems(g: dict[str, Any], fmap: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    """What is wrong with a match group's conditions — shared with the static
    list's *Add people* search."""
    out: list[str] = []
    if not g.get("conditions"):
        out.append("it has no conditions — add at least one.")
    fields = fmap.get(g.get("type") or "", {})
    for c in g.get("conditions") or []:
        f = fields.get(c["field"])
        if not f:
            out.append(f"the field {c['field']!r} is no longer offered for "
                       f"{TYPES.get(g.get('type') or '', {}).get('label', 'records').lower()} — edit or remove the condition.")
            continue
        if c["op"] not in {o for o, _ in OPERATORS[f["family"]]}:
            out.append(f"{f['label']} cannot use that comparison.")
            continue
        if c["op"] in ("in", "notIn", "anyOf", "noneOf") and not _as_list(c["value"]):
            out.append(f"{f['label']} — tick at least one value.")
        if c["op"] in ("contains", "startsWith", "equals") and not str(c["value"] or "").strip():
            out.append(f"{f['label']} — type the text to match.")
        if c["op"] in ("after", "before") and not _date(c["value"]):
            out.append(f"{f['label']} — give a date.")
        if c["op"] in ("lastDays", "olderDays", "atLeast", "atMost") and _number(c["value"]) is None:
            out.append(f"{f['label']} — give a number.")
    return out


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
    """One condition as an EspoCRM ``where`` clause on the field's own entity
    (the leaf of a link path; ``group_where`` walks the hops)."""
    a, op, v = field.get("leaf") or cond["field"], cond["op"], cond.get("value")
    fam = field["family"]
    if fam == "link":
        a = a + "Id"
        if op == "isEmpty":
            return {"type": "isNull", "attribute": a}
        if op == "isNotEmpty":
            return {"type": "isNotNull", "attribute": a}
        return {"type": op, "attribute": a, "value": _as_list(v)}
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
    if op in ("lastDays", "olderDays"):
        n = int(_number(v) or 0)
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max(n, 0))
        return {"type": "after" if op == "lastDays" else "before", "attribute": a,
                "value": cutoff.strftime("%Y-%m-%d %H:%M:%S")}
    if op == "atLeast":
        return {"type": "greaterThanOrEquals", "attribute": a, "value": _number(v)}
    if op == "atMost":
        return {"type": "lessThanOrEquals", "attribute": a, "value": _number(v)}
    if op == "isTrue":
        return {"type": "isTrue", "attribute": a}
    if op == "isFalse":
        return {"type": "isFalse", "attribute": a}
    raise AudienceError(f"Unknown comparison {op!r}.")


_NOTHING = {"type": "in", "attribute": "id", "value": ["__none__"]}


async def _via_where(client, field: dict[str, Any], clause: dict[str, Any]) -> dict[str, Any]:
    """Walk a link path backwards: the leaf entity's matching ids become a
    filter on the entity before it, and so on to the group's own entity."""
    for hop in reversed(field.get("hops") or []):
        if hop["kind"] == "belongsTo":
            ids = await _ids_matching(client, hop["to"], [clause], cap=VIA_CAP,
                                      too_many=f"{field['label']} matches more than {VIA_CAP:,} linked records "
                                               "— narrow the condition.")
            clause = {"type": "in", "attribute": hop["link"] + "Id", "value": ids} if ids else _NOTHING
        else:  # hasOne: the key sits on the linked record
            key = hop["foreign"] + "Id"
            owners: list[str] = []
            offset = 0
            while True:
                page = await client.list(hop["to"], select=f"id,{key}", where=[clause], max_size=_PAGE,
                                         offset=offset)
                batch = page.get("list", [])
                owners.extend(r[key] for r in batch if r.get(key))
                if len(owners) > VIA_CAP:
                    raise AudienceError(f"{field['label']} matches more than {VIA_CAP:,} linked records "
                                        "— narrow the condition.")
                if len(batch) < _PAGE:
                    break
                offset += _PAGE
            owners = list(dict.fromkeys(owners))
            clause = {"type": "in", "attribute": "id", "value": owners} if owners else _NOTHING
    return clause


async def group_where(client, group: dict[str, Any], cat: dict[str, Any], *,
                      now: Optional[datetime] = None) -> list[dict[str, Any]]:
    fields = field_map(cat).get(group["type"], {})
    out = []
    for c in group["conditions"]:
        f = fields[c["field"]]
        clause = condition_where(c, f, now=now)
        if f.get("hops"):
            clause = await _via_where(client, f, clause)
        out.append(clause)
    return out


def _conditions_text(group: dict[str, Any], cat: dict[str, Any]) -> str:
    fields = field_map(cat).get(group["type"], {})
    parts = []
    for c in group["conditions"]:
        f = fields.get(c["field"]) or {"label": c["field"], "family": "text"}
        # The operator's typing hint ("separate with commas") is for the
        # builder, not the sentence.
        op_label = dict(OPERATORS.get(f["family"], [])).get(c["op"], c["op"]).split(" (")[0]
        val = c.get("value")
        if isinstance(val, str) and c["op"] in ("in", "notIn"):
            val = ", ".join(_as_list(val))
        if isinstance(val, list):
            names = {o["value"]: o["label"] for o in f.get("options") or [] if isinstance(o, dict)}
            val = ", ".join("No type" if x == NO_TYPE else names.get(x, str(x)) for x in val)
        parts.append(f"{f['label']} {op_label}" + (f" {val}" if val not in (None, "") else ""))
    return " and ".join(parts)


def describe_group(group: dict[str, Any], cat: dict[str, Any], list_names: Optional[dict[str, str]] = None) -> str:
    """The group in one sentence — *who is on it* on the list page, the run
    report and the history line."""
    if group["kind"] == GROUP_LIST:
        name = (list_names or {}).get(group.get("listId") or "", "another list")
        return f"Everyone on the list “{name}”."
    noun = TYPES.get(group["type"], {}).get("label", group["type"] or "records").lower()
    if group["kind"] == GROUP_IMPORT:
        n = len(group.get("values") or [])
        return f"The {noun} a file names ({n:,} row{'' if n == 1 else 's'})."
    cond = _conditions_text(group, cat)
    return (f"{noun[:1].upper()}{noun[1:]} where {cond}." if cond else f"{noun[:1].upper()}{noun[1:]}, no conditions yet.")


def describe_recipe(recipe: dict[str, Any], cat: dict[str, Any],
                    list_names: Optional[dict[str, str]] = None) -> dict[str, list[str]]:
    return {side: [describe_group(g, cat, list_names) for g in recipe.get(side) or []] for side in SIDES}


# --- running ------------------------------------------------------------------------------------

async def _ids_matching(client, entity: str, where: list[dict[str, Any]], *, cap: int = STEP_CAP,
                        too_many: str = "") -> list[str]:
    out: list[str] = []
    offset = 0
    while True:
        page = await client.list(entity, select="id", where=where, max_size=_PAGE, offset=offset,
                                 order_by="createdAt", order="asc")
        batch = page.get("list", [])
        out.extend(r["id"] for r in batch if r.get("id"))
        if len(out) > cap:
            raise AudienceError(too_many or f"This group matches more than {cap:,} records — narrow it.")
        if len(batch) < _PAGE:
            return out
        offset += _PAGE


async def _ids_matching_within(client, entity: str, where: list[dict[str, Any]], ids: list[str]) -> set[str]:
    """Which of these ids match — a Leave out group tests only the records the
    Include groups found, in batches, so it never hits the cap."""
    out: set[str] = set()
    for i in range(0, len(ids), _ID_BATCH):
        chunk = ids[i:i + _ID_BATCH]
        page = await client.list(entity, select="id", max_size=_PAGE,
                                 where=[{"type": "in", "attribute": "id", "value": chunk}, *where])
        out.update(r["id"] for r in page.get("list", []) if r.get("id"))
    return out


async def _import_ids(client, type_: str, values: list[str]) -> tuple[list[str], int]:
    """The records a pasted file names: CRM ids for every type, email addresses
    for leads and contacts. Returns the ids found and how many rows matched
    nothing."""
    entity = TYPES[type_]["entity"]
    emails = [v.lower() for v in values if "@" in v]
    ids = [v for v in values if "@" not in v]
    found: list[str] = []
    matched_rows = 0
    for i in range(0, len(ids), _ID_BATCH):
        chunk = ids[i:i + _ID_BATCH]
        page = await client.list(entity, select="id", max_size=_PAGE,
                                 where=[{"type": "in", "attribute": "id", "value": chunk}])
        hit = {r["id"] for r in page.get("list", []) if r.get("id")}
        matched_rows += sum(1 for x in chunk if x in hit)
        found.extend(x for x in chunk if x in hit)
    if emails and type_ in ("lead", "contact"):
        attr = "email" if type_ == "lead" else "emailAddress"
        for i in range(0, len(emails), _ID_BATCH):
            chunk = emails[i:i + _ID_BATCH]
            page = await client.list(entity, select=f"id,{attr}", max_size=_PAGE,
                                     where=[{"type": "in", "attribute": attr, "value": chunk}])
            seen = set()
            for r in page.get("list", []):
                found.append(r["id"])
                seen.add(str(r.get(attr) or "").lower())
            matched_rows += sum(1 for x in chunk if x in seen)
    return list(dict.fromkeys(found)), len(values) - matched_rows


def split_key(key: str) -> tuple[str, str]:
    t, _, rid = key.partition(":")
    return t, rid


async def match_keys(client, group: dict[str, Any], cat: dict[str, Any], *,
                     now: Optional[datetime] = None) -> list[str]:
    """Every record a match group selects, as keys — an Include group, and the
    static list's *Add people* search."""
    where = await group_where(client, group, cat, now=now)
    prefix = group["type"] + ":"
    return [prefix + rid for rid in await _ids_matching(client, TYPES[group["type"]]["entity"], where)]


async def run_recipe(client, recipe: dict[str, Any], cat: dict[str, Any], *, store=None,
                     now: Optional[datetime] = None, _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    """The union of the Include groups minus the union of the Leave out
    groups; Leave out always wins and groups have no order. Returns ``keys``
    (key → the first Include group that holds it), one report line per group,
    and the totals."""
    problems = check_recipe(recipe, cat)
    if problems:
        raise AudienceError(problems[0]["message"])
    included: dict[str, int] = {}
    report: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for i, g in enumerate(recipe["include"], start=1):
        extra: dict[str, Any] = {}
        if g["kind"] == GROUP_LIST:
            other = await _other_list(store, g["listId"], _seen)
            names[other["id"]] = other["name"]
            keys = list((await current_members(client, store, other, cat, _seen=_seen))["keys"])
        elif g["kind"] == GROUP_IMPORT:
            ids, unmatched = await _import_ids(client, g["type"], g.get("values") or [])
            keys = [f"{g['type']}:{rid}" for rid in ids]
            extra["unmatched"] = unmatched
        else:
            keys = await match_keys(client, g, cat, now=now)
        for k in keys:
            included.setdefault(k, i)
        report.append({"side": "include", "group": i, "summary": describe_group(g, cat, names),
                       "count": len(keys), **extra})
    left_out: set[str] = set()
    for i, g in enumerate(recipe["exclude"], start=1):
        extra = {}
        if g["kind"] == GROUP_LIST:
            other = await _other_list(store, g["listId"], _seen)
            names[other["id"]] = other["name"]
            hit = set((await current_members(client, store, other, cat, _seen=_seen))["keys"]) & set(included)
        elif g["kind"] == GROUP_IMPORT:
            ids, unmatched = await _import_ids(client, g["type"], g.get("values") or [])
            hit = {f"{g['type']}:{rid}" for rid in ids} & set(included)
            extra["unmatched"] = unmatched
        else:
            prefix = g["type"] + ":"
            of_type = [split_key(k)[1] for k in included if k.startswith(prefix)]
            where = await group_where(client, g, cat, now=now)
            hit = {prefix + rid for rid in await _ids_matching_within(client, TYPES[g["type"]]["entity"],
                                                                         where, of_type)}
        left_out |= hit
        report.append({"side": "exclude", "group": i, "summary": describe_group(g, cat, names),
                       "count": len(hit), **extra})
    keys = {k: gi for k, gi in included.items() if k not in left_out}
    return {"keys": keys, "groups": report, "included": len(included), "leftOut": len(included) - len(keys),
            "total": len(keys)}


async def _other_list(store, list_id: str, seen: tuple[str, ...]) -> dict[str, Any]:
    if store is None:
        raise AudienceError("Lists of lists need the application database.")
    if list_id in seen:
        raise AudienceError("A list cannot include itself, directly or through another list.")
    if len(seen) >= LIST_DEPTH:
        raise AudienceError(f"Lists may nest at most {LIST_DEPTH} deep.")
    other = await store.get_list(list_id)
    if not other:
        raise AudienceError("A group names a list that no longer exists — choose another.")
    return other


async def reaches(store, start_ids: list[str], target: str, depth: int = 0) -> bool:
    """Does following "everyone on the list" groups from these lists reach
    ``target``? The save refuses a cycle."""
    if depth > LIST_DEPTH:
        return False
    for lid in start_ids:
        if lid == target:
            return True
        row = await store.get_list(lid)
        if row and await reaches(store, referenced_lists(normalise_recipe(row["recipe"])), target, depth + 1):
            return True
    return False


async def current_members(client, store, row: dict[str, Any], cat: dict[str, Any], *,
                          _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    """The list as a campaign would send to it now: a static list's people
    added by hand (rulings 91, 94 — never run, never empty by mistake), a
    dynamic list's search run now."""
    if row["kind"] == KIND_STATIC:
        rows = await store.member_rows(row["id"])
        keys = {r["target_key"]: 0 for r in rows if r.get("state") == STATE_IN}
        return {"keys": keys, "groups": [], "total": len(keys), "frozen": True}
    result = await run_recipe(client, normalise_recipe(row["recipe"]), cat, store=store,
                              _seen=(*_seen, row["id"]))
    return {**result, "frozen": False}


async def copy_to_static(client, store, row: dict[str, Any], cat: dict[str, Any], *, name: str,
                         actor: str) -> tuple[dict[str, Any], int]:
    """*Copy current members to a new static list* (ruling 93): the members as
    they are now — a dynamic list is run for it — as hand rows on a new static
    list. The campaigns stay on the original."""
    members = await current_members(client, store, row, cat)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new = await store.copy_list(name=name, notes=f"Copied from \"{row['name']}\" on {stamp}.",
                                keys=list(members["keys"]), actor=actor)
    return new, members["total"]


# --- per channel: how many a list reaches (ruling 98's top line) -------------------------------

#: The channels the list page counts, in its order. Calls are a campaign kind
#: of their own and are not on the top line.
COUNT_CHANNELS = ((cfg.KIND_EMAIL, "Email"), (cfg.KIND_SMS, "Text"), (cfg.KIND_POSTCARD, "Postcard"))


async def channel_counts(client, keys: Iterable[str]) -> list[dict[str, Any]]:
    """For each channel, how many the members reach after every send-time
    check — ``resolve_targets`` run per kind and read as its count only.
    Computed on demand, never stored."""
    keys = list(keys)
    out = []
    for kind, label in COUNT_CHANNELS:
        resolved = await resolve_targets(client, kind, keys)
        out.append({"channel": kind, "label": label, "count": len(resolved["targets"]),
                    "skipped": sum(s["count"] for s in resolved["skipped"])})
    return out


# --- showing members -------------------------------------------------------------------------

def used_fields(recipe: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for _side, _i, g in groups(recipe):
        for c in g.get("conditions") or []:
            lst = out.setdefault(g.get("type") or "", [])
            if c.get("field") and c["field"] not in lst:
                lst.append(c["field"])
    return out


async def describe_members(client, keys: list[str], recipe: dict[str, Any], cat: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per key: its type, name and the values of the curated fields
    the recipe used — nothing else (§ 7c.4, who sees what). A field reached
    through a link shows no value here; a direct field shows on its own record
    type. A record the CRM no longer holds is flagged, never dropped."""
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
        cols = []
        for f in used.get(t, []):
            info = fmap.get(t, {}).get(f)
            if info and not info.get("hops"):
                cols.append(f + "Name" if info["family"] == "link" else f)
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
            info = fmap.get(t, {}).get(f)
            if info and not info.get("hops"):
                v = r.get(f + "Name") if info["family"] == "link" else r.get(f)
                values[info["label"]] = ", ".join(map(str, v)) if isinstance(v, list) else v
        out.append({"key": k, "type": t, "id": rid, "name": name, "missing": False, "values": values})
    return out


# --- recipients, per channel (§ 7c.2) -----------------------------------------------------------

CONTACT_SELECT = (
    f"id,name,firstName,lastName,emailAddress,emailAddressIsOptedOut,emailAddressIsInvalid,"
    f"cMarketingOptIn,phoneNumber,phoneNumberIsOptedOut,doNotCall,cSmsOptIn,{CONTACT_TYPE_FIELD},"
    f"cFunnelStage,accountId,addressStreet,addressCity,addressState,addressPostalCode,addressCountry"
)
ACCOUNT_SELECT = ("id,name,cFunnelStage,billingAddressStreet,billingAddressCity,billingAddressState,"
                  "billingAddressPostalCode,billingAddressCountry")
#: Per organisation type: its primary contact's id attribute, its contacts
#: relationship, and where its company is (ruling 59, § 7c.2).
ORG_SHAPE = {
    "client": {"primary": "primaryEngagementContactId", "contacts": "engagementContacts",
               "select": "id,name,primaryEngagementContactId,clientOrganizationId,engagementClientId"},
    "partner": {"primary": "primaryPartnercontactId", "contacts": "contacts",
                "select": "id,name,primaryPartnercontactId,partnerCompanyId"},
    "funder": {"primary": "sponsorContactId", "contacts": "sponsorContacts",
               "select": "id,name,sponsorContactId,sponsorCompanyId"},
}
SKIP = {
    "missing": "no longer in the CRM",
    "exit": "the lead has left (an exit is set)",
    "disqualified": "the lead is Disqualified",
    "no_address": "no usable mailing address",
    "carded": "already sent a postcard (one card per business)",
    "no_contact": "a lead with no Contact yet — only a Contact can be emailed or texted",
    "no_primary": "no primary contact on the record",
    "no_contacts": "no contacts on the record",
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


async def _org_records(client, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Client / partner / funder records by key, with their company id
    resolved (a client's through its client profile when the engagement has
    no company of its own)."""
    out: dict[str, dict[str, Any]] = {}
    for t in ORG_TYPES:
        ids = [split_key(k)[1] for k in keys if k.startswith(t + ":")]
        if not ids:
            continue
        rows = await _by_ids(client, TYPES[t]["entity"], ids, ORG_SHAPE[t]["select"])
        if t == "client":
            need = [r["engagementClientId"] for r in rows.values()
                    if not r.get("clientOrganizationId") and r.get("engagementClientId")]
            via: dict[str, str] = {}
            for i in range(0, len(need), _ID_BATCH):
                page = await client.list(cfg.ACCOUNT, select="id,cClientProfileId", max_size=_PAGE,
                                         where=[{"type": "in", "attribute": "cClientProfileId",
                                                 "value": need[i:i + _ID_BATCH]}])
                for a in page.get("list", []):
                    if a.get("cClientProfileId"):
                        via[a["cClientProfileId"]] = a["id"]
            for r in rows.values():
                r["_companyId"] = r.get("clientOrganizationId") or via.get(r.get("engagementClientId") or "")
        else:
            attr = "partnerCompanyId" if t == "partner" else "sponsorCompanyId"
            for r in rows.values():
                r["_companyId"] = r.get(attr)
        for rid, r in rows.items():
            out[f"{t}:{rid}"] = r
    return out


async def _org_people(client, key: str, rec: dict[str, Any], every: bool) -> list[str]:
    t, rid = split_key(key)
    shape = ORG_SHAPE[t]
    ids = [rec[shape["primary"]]] if rec.get(shape["primary"]) else []
    if every:
        try:
            page = await client.list_related(TYPES[t]["entity"], rid, shape["contacts"], select="id", max_size=_PAGE)
            ids += [r["id"] for r in page.get("list", []) if r.get("id")]
        except EspoError as exc:
            log.warning("audience: contacts of %s unreadable: %s", key, exc)
    return list(dict.fromkeys(ids))


async def resolve_targets(client, kind: str, keys: Iterable[str], *, every_contact: bool = False) -> dict[str, Any]:
    """The list's members as the targets ``kind``'s ``build_list`` writes as
    Planned touches, with every send-time check applied and each skip counted
    by reason. The target dicts are the shapes each kind's own selection
    produces."""
    from . import calls, postcard  # local: those modules import nothing from here

    keys = list(keys)
    lead_ids = [split_key(k)[1] for k in keys if k.startswith("lead:")]
    leads = await _by_ids(client, cfg.PROSPECT, lead_ids, cfg.PROSPECT_SELECT)
    orgs = await _org_records(client, [k for k in keys if split_key(k)[0] in ORG_TYPES])

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

    if kind == cfg.KIND_POSTCARD:
        carded = await postcard._carded_targets(client)
        contact_ids = [split_key(k)[1] for k in keys if k.startswith("contact:")]
        contacts = await _by_ids(client, cfg.CONTACT, contact_ids, CONTACT_SELECT)
        left = await _left(client, contact_ids)
        account_ids = [c.get("accountId") for c in contacts.values()] + [o.get("_companyId") for o in orgs.values()]
        accounts = await _by_ids(client, cfg.ACCOUNT, [a for a in account_ids if a], ACCOUNT_SELECT)

        def card_to_company(acct: Optional[dict[str, Any]]) -> bool:
            if not acct or not _company_address(acct).is_complete():
                return False
            address = _company_address(acct)
            take({"key": f"company:{acct['id']}", "kind": "company", "id": acct["id"],
                  "name": acct.get("name") or "", "address": address, "stage": acct.get("cFunnelStage")},
                 _card_key(address))
            return True

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
                if card_to_company(accounts.get(c.get("accountId") or "")):
                    continue
                address = contact_address(c)
                if not address.is_complete():
                    skipped["no_address"] += 1
                    continue
                take({"key": f"contact:{rid}", "kind": "contact", "id": rid, "name": c.get("name") or "",
                      "address": address, "stage": c.get("cFunnelStage")}, _card_key(address))
            elif t in ORG_TYPES:
                # Ruling 68: a card reached through a client, partner or funder
                # is limited by this campaign alone (the de-duplication here).
                o = orgs.get(k)
                if not o:
                    skipped["missing"] += 1
                    continue
                if not card_to_company(accounts.get(o.get("_companyId") or "")):
                    skipped["no_address"] += 1
        return {"targets": targets, "skipped": _skips(skipped)}

    # The person channels: every member as the people it stands for.
    persons: list[tuple[str, Any]] = []   # (member key, contact id | {"_lead": lead})
    for k in keys:
        t, rid = split_key(k)
        if t == "lead":
            p = leads.get(rid)
            if not p:
                skipped["missing"] += 1
                continue
            if not lead_ok(p):
                continue
            if p.get("promotedContactId"):
                persons.append((k, p["promotedContactId"]))
            elif kind == cfg.KIND_CALL and p.get("phone"):
                persons.append((k, {"_lead": p}))
            else:
                skipped["no_contact" if kind != cfg.KIND_CALL else "no_phone"] += 1
        elif t == "contact":
            persons.append((k, rid))
        elif t in ORG_TYPES:
            o = orgs.get(k)
            if not o:
                skipped["missing"] += 1
                continue
            people = await _org_people(client, k, o, every_contact)
            if not people:
                skipped["no_contacts" if every_contact else "no_primary"] += 1
                continue
            persons.extend((k, cid) for cid in people)
    contact_ids = [p for _, p in persons if isinstance(p, str)]
    contacts = await _by_ids(client, cfg.CONTACT, contact_ids, CONTACT_SELECT)
    left = await _left(client, contact_ids)
    resolved: list[tuple[str, dict[str, Any]]] = []
    for k, p in persons:
        if isinstance(p, dict):
            resolved.append((k, p))
            continue
        c = contacts.get(p)
        if not c:
            skipped["missing"] += 1
            continue
        if p in left:
            skipped["exit"] += 1
            continue
        resolved.append((k, c))

    if kind == cfg.KIND_EMAIL:
        cbm = await cbm_emails(client, [c["id"] for _, c in resolved if c.get("id") and is_member(c)])
        for _k, c in resolved:
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
        for _k, c in resolved:
            if c.get("_lead"):
                skipped["no_contact"] += 1
                continue
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
        for k, c in resolved:
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


async def _left(client, contact_ids: list[str]) -> set[str]:
    """Contacts whose lead has left: they stopped with it (the existing call /
    text rule)."""
    left: set[str] = set()
    ids = list(dict.fromkeys(contact_ids))
    for i in range(0, len(ids), _ID_BATCH):
        page = await client.list(cfg.PROSPECT, select="id,sideExit,promotedContactId", max_size=_PAGE, where=[
            {"type": "in", "attribute": "promotedContactId", "value": ids[i:i + _ID_BATCH]},
            {"type": "isNotNull", "attribute": "sideExit"}])
        left.update(p["promotedContactId"] for p in page.get("list", []) if p.get("promotedContactId"))
    return left


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
            "reached": len(audience["targets"]), "skipped": audience["skipped"],
            "everyContact": audience.get("everyContact", False)}


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
    every = bool(chosen.get("include_every_contact"))
    cat = await catalogue(client, settings)
    members = await current_members(client, store, row, cat)
    resolved = await resolve_targets(client, campaign.get("campaignKind") or cfg.KIND_POSTCARD, members["keys"],
                                     every_contact=every)
    skipped_total = sum(s["count"] for s in resolved["skipped"])
    summary = (f"The {row['kind']} list \"{row['name']}\" (version {row['version']}): "
               f"{members['total']} members, {len(resolved['targets'])} reached, {skipped_total} skipped"
               + (", every contact on each client, partner or funder." if every else "."))
    return {"list": {"id": row["id"], "name": row["name"], "kind": row["kind"], "version": row["version"]},
            "members": members["total"], "targets": resolved["targets"], "skipped": resolved["skipped"],
            "summary": summary, "everyContact": every}
