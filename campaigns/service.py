"""Campaign Management — the CRM logic (build plan § 3.1, § 3.6, § 3.8).

Who acts: staff reads and writes on a campaign run **as the signed-in user**
(the Marketing Admin Role creates, reads and edits the three entities since
10-15-26), so EspoCRM enforces the permission and records the staff member.
Aggregates a marketing user may not read record by record — the selection, the
counts over partner records, the import's Company and Contact writes (ruling
33) — run under the **org-wide API client**, which the router passes in
separately. Relating a campaign to a partner needs edit on the partner record,
which that role deliberately lacks (ruling 2026-10-07), so the relate runs as
the user first and escalates only a ``noAccessToForeignRecord`` denial to the
provisioning administrator — the events sponsors picker's pattern.

Every read of a Phase 1 entity or link feature-detects it from metadata first,
so a CRM without the change (production until its Sunday slot) answers
``available: False`` with a reason instead of 500ing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from core.espo import EspoApi, EspoError, is_forbidden

from . import config as cfg

log = logging.getLogger("cbm_intake.campaigns")

_PAGE = 200
#: A whole-population read (a postcard selection, the reporting counts) stops
#: here and says so in the log. It was 2,000 until 10-20-26, which at about
#: 10,000 leads a year (build plan § 7b) would have cut a selection short
#: silently within months.
_MAX_ROWS = 50000


class CampaignError(Exception):
    """A refusal the user can act on (400), never a CRM failure."""


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --- feature detection ---------------------------------------------------------

async def availability(client: EspoApi) -> dict[str, Any]:
    """Whether this CRM carries the Phase 1 change. Fails CLOSED: an unreadable
    metadata answer counts as absent, with the reason named."""
    missing: list[str] = []
    try:
        for entity in (cfg.PROSPECT, cfg.CAMPAIGN, cfg.TOUCH):
            scope = await client.metadata(f"scopes.{entity}")
            if not isinstance(scope, dict) or not scope.get("entity"):
                missing.append(entity)
        links = await client.metadata(f"entityDefs.{cfg.CAMPAIGN}.links") or {}
        for link in (cfg.LINK_PARTNERS, cfg.LINK_EVENTS, cfg.LINK_TOUCHES):
            if not isinstance(links, dict) or link not in links:
                missing.append(f"{cfg.CAMPAIGN}.{link}")
        # The lead model (rulings 41-52): the code reads and writes leadStatus,
        # so a CRM without it is "not available" rather than a refused select.
        lead_fields = await client.metadata(f"entityDefs.{cfg.PROSPECT}.fields") or {}
        for name in ("leadStatus", "leadSource", "leadStatusChangedAt"):
            if cfg.PROSPECT not in missing and (not isinstance(lead_fields, dict) or name not in lead_fields):
                missing.append(f"{cfg.PROSPECT}.{name}")
    except Exception as exc:  # noqa: BLE001 — a metadata failure is "not available", not a 500
        return {"available": False, "reason": f"The CRM's configuration could not be read ({exc})."}
    if missing:
        return {
            "available": False,
            "reason": "This CRM does not carry the campaign entities yet: "
                      + ", ".join(missing) + " (coutreach-entities-crm-handoff.md, coutreach-lead-model-crm-handoff.md).",
        }
    return {"available": True, "reason": ""}


# --- live options ---------------------------------------------------------------

async def _enum_options(client: EspoApi, entity: str, names: Iterable[str]) -> dict[str, list[str]]:
    fields = await client.metadata(f"entityDefs.{entity}.fields") or {}
    out: dict[str, list[str]] = {}
    for name in names:
        spec = fields.get(name) if isinstance(fields, dict) else None
        options = (spec or {}).get("options") if isinstance(spec, dict) else None
        out[name] = [o for o in (options or []) if o not in ("", None)]
    return out


async def field_options(client: EspoApi, *, calls_on: bool = False, sms_on: bool = False,
                        email_on: bool = False) -> dict[str, Any]:
    """Enum options for the campaign form and the prospect filters, live from
    the CRM. A kind outside this phase is listed but marked so the screen can
    say which phase brings it."""
    campaign = await _enum_options(client, cfg.CAMPAIGN, cfg.CAMPAIGN_ENUM_NAMES)
    live = await client.metadata(f"entityDefs.{cfg.CAMPAIGN}.fields") or {}
    missing = sorted(n for n in cfg.CAMPAIGN_OPTIONAL_FIELDS if not (isinstance(live, dict) and n in live))
    prospect = await _enum_options(
        client, cfg.PROSPECT, ("leadStatus", "leadSource", "sideExit", "addressStatus"))
    # The options the lead model retired stay in the CRM until the removal step
    # (coutreach-lead-model-crm-handoff.md § 6); the screens never offer them.
    prospect["sideExit"] = [o for o in prospect.get("sideExit", [])
                            if o in (cfg.EXIT_DUPLICATE, cfg.EXIT_DO_NOT_CONTACT, cfg.EXIT_DECLINED, cfg.EXIT_STALE)]
    return {
        "campaign": campaign,
        "prospect": prospect,
        "kindsBuilt": list(cfg.kinds_built(calls_on, sms_on, email_on)),
        "missingFields": missing,
    }


def sanitize_changes(changes: dict[str, Any], options: dict[str, list[str]],
                     missing: Iterable[str] = ()) -> dict[str, Any]:
    """The whitelist plus the enum guard: an unknown field is dropped, an enum
    value outside the live options is dropped (fails open — a drifted option
    stores nothing rather than 400ing the whole save)."""
    out: dict[str, Any] = {}
    missing = set(missing)
    for key, value in (changes or {}).items():
        if key not in cfg.CAMPAIGN_EDIT_NAMES or key in missing:
            continue
        if key in cfg.CAMPAIGN_ENUM_NAMES:
            if value in ("", None):
                out[key] = None
                continue
            allowed = options.get(key)
            if allowed and value not in allowed:
                log.warning("campaign enum %s=%r is not a live option; dropped", key, value)
                continue
        if isinstance(value, str):
            value = value.strip()
            if key not in ("description", "smsMessage") and value == "":
                value = None
        out[key] = value
    return out


# --- campaigns -------------------------------------------------------------------

async def _page_all(client: EspoApi, entity: str, *, select: str, where=None,
                    order_by: str = "createdAt", order: str = "desc",
                    limit: int = _MAX_ROWS) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(entity, select=select, where=where, max_size=_PAGE,
                                 offset=offset, order_by=order_by, order=order)
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < _PAGE:
            break
        if len(rows) >= limit:
            log.warning("%s read stopped at %s rows (the cap); later rows were not read", entity, len(rows))
            break
        offset += _PAGE
    return rows


async def list_campaigns(client: EspoApi) -> list[dict[str, Any]]:
    return await _page_all(client, cfg.CAMPAIGN, select=cfg.CAMPAIGN_SELECT)


async def get_campaign(client: EspoApi, campaign_id: str) -> dict[str, Any]:
    return await client.get(cfg.CAMPAIGN, campaign_id, select=cfg.CAMPAIGN_SELECT)


async def funders_available(client: EspoApi) -> bool:
    """Ruling 57's link, read live; a failed read counts as absent."""
    try:
        links = await client.metadata(f"entityDefs.{cfg.CAMPAIGN}.links") or {}
    except Exception:  # noqa: BLE001 — a probe never raises
        return False
    return isinstance(links, dict) and cfg.LINK_FUNDERS in links


async def related_names(client: EspoApi, campaign_id: str, link: str) -> Optional[list[dict[str, Any]]]:
    """The records on one relationship of a campaign — id and name. None when
    unreadable (rendered "—", never an empty list that would read as none)."""
    try:
        data = await client.list_related(cfg.CAMPAIGN, campaign_id, link, select="id,name", max_size=_PAGE)
    except EspoError as exc:
        log.warning("could not read %s of campaign %s: %s", link, campaign_id, exc)
        return None
    return [{"id": r["id"], "name": r.get("name") or "(unnamed)"} for r in data.get("list", []) if r.get("id")]


async def picker_options(client: EspoApi, entity: str, *, where=None) -> Optional[list[dict[str, Any]]]:
    """Records for a picker, name order, paged at 200. A FORBIDDEN list is None:
    the picker renders read-only and says so (the events sponsors precedent)."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            page = await client.list(entity, select="id,name", where=where, max_size=_PAGE,
                                     offset=offset, order_by="name", order="asc")
        except EspoError as exc:
            if is_forbidden(exc):
                log.info("%s list forbidden for the picker: %s", entity, exc)
                return None
            raise
        batch = page.get("list", [])
        rows.extend({"id": r["id"], "name": r.get("name") or "(unnamed)"} for r in batch if r.get("id"))
        if len(batch) < _PAGE or offset >= _MAX_ROWS:
            break
        offset += _PAGE
    return rows


def _not_built(kind: str, built: tuple[str, ...]) -> str:
    return f"The {kind} kind is not built yet — {', '.join(built)} " + ("are." if len(built) > 1 else "is.")


async def create_campaign(client: EspoApi, changes: dict[str, Any], *, user_id: str,
                          calls_on: bool = False, sms_on: bool = False, email_on: bool = False) -> dict[str, Any]:
    built = cfg.kinds_built(calls_on, sms_on, email_on)
    opts = await field_options(client)
    payload = sanitize_changes(changes, opts["campaign"], opts["missingFields"])
    if not payload.get("name"):
        raise CampaignError("A campaign needs a name.")
    if not payload.get("campaignKind"):
        raise CampaignError("Choose the campaign's kind.")
    if payload["campaignKind"] not in built:
        raise CampaignError(_not_built(payload["campaignKind"], built))
    if payload["campaignKind"] != cfg.KIND_SOCIAL:
        payload["platform"] = None
    if payload["campaignKind"] != cfg.KIND_SMS:
        payload.pop("smsMessage", None)
    payload["campaignStatus"] = cfg.STATUS_DRAFT
    if user_id:
        payload["assignedUserId"] = user_id
    return await client.create(cfg.CAMPAIGN, payload)


#: The User types that can own a campaign: a person, never the API user or a
#: portal login.
_OWNER_USER_TYPES = ("regular", "admin")


async def owner_options(reader: EspoApi, team_names: Iterable[str]) -> list[dict[str, str]]:
    """Ruling 76: the people a campaign may be handed to — the active members
    of the Campaign Management teams, by name. ``reader`` is the org-wide
    client where there is one: a marketing role may hold no Team or User read,
    and the list is the choice, not anyone's data."""
    seen: dict[str, str] = {}
    for team_name in team_names:
        team = await reader.find_one("Team", "name", team_name, select="id,name")
        if not team or not team.get("id"):
            log.info("owner options: no team named %r", team_name)
            continue
        page = await reader.list_related("Team", team["id"], "users",
                                         select="id,name,isActive,type", max_size=_PAGE)
        for u in page.get("list", []):
            if not u.get("id") or u.get("isActive") is False:
                continue
            if (u.get("type") or "regular") not in _OWNER_USER_TYPES:
                continue
            seen[u["id"]] = u.get("name") or "(unnamed)"
    return sorted(({"id": i, "name": n} for i, n in seen.items()), key=lambda o: o["name"].lower())


async def change_owner(client: EspoApi, campaign: dict[str, Any], user_id: str,
                       options: list[dict[str, str]]) -> tuple[dict[str, Any], Optional[str]]:
    """Write the campaign's Assigned User (ruling 76), as the signed-in user so
    the CRM's own assignment check applies. Returns the campaign and the new
    owner's name, or None for the name when nothing changed."""
    user_id = (user_id or "").strip()
    if not user_id:
        raise CampaignError("Choose the person who should own this campaign.")
    chosen = next((o for o in options if o["id"] == user_id), None)
    if chosen is None:
        raise CampaignError("That person is not an active member of the Marketing Management team, "
                            "so they cannot own a campaign.")
    if campaign.get("assignedUserId") == user_id:
        return campaign, None
    updated = await client.update(cfg.CAMPAIGN, campaign["id"], {"assignedUserId": user_id})
    return updated, chosen["name"]


async def update_campaign(client: EspoApi, campaign: dict[str, Any], changes: dict[str, Any],
                          *, calls_on: bool = False, sms_on: bool = False, email_on: bool = False) -> dict[str, Any]:
    built = cfg.kinds_built(calls_on, sms_on, email_on)
    opts = await field_options(client)
    payload = sanitize_changes(changes, opts["campaign"], opts["missingFields"])
    if "smsMessage" in payload and campaign.get("campaignStatus") not in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING, None):
        raise CampaignError("A text message is frozen once the campaign is signed off.")
    if "campaignKind" in payload and payload["campaignKind"] != campaign.get("campaignKind"):
        if campaign.get("campaignStatus") not in (cfg.STATUS_DRAFT, None):
            raise CampaignError("A campaign's kind can only change while it is a draft.")
        if payload["campaignKind"] not in built:
            raise CampaignError(_not_built(payload["campaignKind"], built))
    if not payload:
        return campaign
    return await client.update(cfg.CAMPAIGN, campaign["id"], payload)


#: Which status moves a person may make by hand, per kind (§ 1.3: the
#: application moves the status; the social kind is the exception — nothing
#: runs, so its Running and Complete are the user's own).
_MANUAL_MOVES: dict[str, dict[str, tuple[str, ...]]] = {
    cfg.KIND_SOCIAL: {
        cfg.STATUS_DRAFT: (cfg.STATUS_RUNNING, cfg.STATUS_CANCELLED),
        cfg.STATUS_RUNNING: (cfg.STATUS_COMPLETE, cfg.STATUS_CANCELLED),
        cfg.STATUS_COMPLETE: (cfg.STATUS_RUNNING,),
        cfg.STATUS_CANCELLED: (cfg.STATUS_DRAFT,),
    },
    cfg.KIND_POSTCARD: {
        cfg.STATUS_DRAFT: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_AWAITING: (cfg.STATUS_DRAFT, cfg.STATUS_CANCELLED),
        cfg.STATUS_SIGNED_OFF: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_CANCELLED: (cfg.STATUS_DRAFT,),
    },
    # An email campaign: the worker pushes its list; staff mark it sent.
    cfg.KIND_EMAIL: {
        cfg.STATUS_DRAFT: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_AWAITING: (cfg.STATUS_DRAFT, cfg.STATUS_CANCELLED),
        cfg.STATUS_SIGNED_OFF: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_RUNNING: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_CANCELLED: (cfg.STATUS_DRAFT,),
    },
    # A text-message campaign is sent by the worker, like the postcard run.
    cfg.KIND_SMS: {
        cfg.STATUS_DRAFT: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_AWAITING: (cfg.STATUS_DRAFT, cfg.STATUS_CANCELLED),
        cfg.STATUS_SIGNED_OFF: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_RUNNING: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_CANCELLED: (cfg.STATUS_DRAFT,),
    },
    # A call list runs from its sign-off (no vendor, no worker): Running until
    # the last Planned row is recorded, when the application completes it.
    cfg.KIND_CALL: {
        cfg.STATUS_DRAFT: (cfg.STATUS_CANCELLED,),
        cfg.STATUS_AWAITING: (cfg.STATUS_DRAFT, cfg.STATUS_CANCELLED),
        cfg.STATUS_RUNNING: (cfg.STATUS_COMPLETE, cfg.STATUS_CANCELLED),
        cfg.STATUS_CANCELLED: (cfg.STATUS_DRAFT,),
    },
}


def manual_moves(campaign: dict[str, Any]) -> tuple[str, ...]:
    kind = campaign.get("campaignKind") or ""
    status = campaign.get("campaignStatus") or cfg.STATUS_DRAFT
    return _MANUAL_MOVES.get(kind, {}).get(status, ())


async def set_status(client: EspoApi, campaign: dict[str, Any], status: str) -> dict[str, Any]:
    allowed = manual_moves(campaign)
    if status not in allowed:
        raise CampaignError(
            f"A {campaign.get('campaignKind') or 'campaign'} at {campaign.get('campaignStatus')} "
            f"cannot be moved to {status} by hand"
            + (f" — it can go to {', '.join(allowed)}." if allowed else "."))
    return await client.update(cfg.CAMPAIGN, campaign["id"], {"campaignStatus": status})


async def stamp_campaign(user_client: EspoApi, api_client: Optional[EspoApi], campaign_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
    """One campaign write split by who owns each field (ruling 40): the
    person's own change (the status) as the signed-in user, first — a refused
    grant changes nothing — then the application's stamps (the rule, the
    sign-off, the run) under the org-wide API client. Returns the record with
    both halves applied."""
    app = {k: v for k, v in payload.items() if k in cfg.CAMPAIGN_APP_FIELDS}
    own = {k: v for k, v in payload.items() if k not in cfg.CAMPAIGN_APP_FIELDS}
    result: dict[str, Any] = {}
    if own:
        result = dict(await user_client.update(cfg.CAMPAIGN, campaign_id, own) or {})
    if app:
        writer = api_client or user_client
        result.update(await writer.update(cfg.CAMPAIGN, campaign_id, app) or {})
    result.update(app)
    result.update(own)
    result.setdefault("id", campaign_id)
    return result


def _foreign_read_refusal(exc: EspoError) -> bool:
    """EspoCRM's refusal of a write that links a record the user cannot read
    (the two body shapes ``core.espo.forbidden_hint`` reads)."""
    text = str(exc)
    return is_forbidden(exc) and ("cannotRelateForbidden" in text or "No foreign record access" in text
                                  or "noAccessToForeignRecord" in text)


async def set_teams(client: EspoApi, campaign_id: str, team_ids: list[str],
                    *, admin_factory=None) -> dict[str, Any]:
    """The campaign's own teams — for a call campaign, who calls (ruling 36).
    ``teams`` is EspoCRM's native link, which an update writes through
    ``teamsIds`` (unlike a custom linkMultiple).

    Written as the user first. Linking a Team needs READ on the Team, which
    the Marketing Admin Role does not hold (found on the lead model's live
    pass, 10-19-26 — the Phase 3 pass created its call campaign as an
    administrator, who skips the check), so that one refusal is retried as
    the admin account, the ``_link_or_escalate`` precedent. The user's own
    edit on the campaign is what admitted the change."""
    ids = sorted({i for i in (team_ids or []) if isinstance(i, str) and i})
    try:
        return await client.update(cfg.CAMPAIGN, campaign_id, {"teamsIds": ids})
    except EspoError as exc:
        if not _foreign_read_refusal(exc) or admin_factory is None:
            raise
        log.info("teams of campaign %s escalated to the admin account (%s)", campaign_id, exc)
        admin = await admin_factory()
        return await admin.update(cfg.CAMPAIGN, campaign_id, {"teamsIds": ids})


# --- relationships (partners, events) --------------------------------------------

async def _link_or_escalate(client: EspoApi, admin_factory, op: str, campaign_id: str,
                            link: str, related_id: str) -> None:
    """relate/unrelate as the user first; only a foreign-record denial (the
    partner's half — the campaign's half passed) is retried as the admin."""
    try:
        await getattr(client, op)(cfg.CAMPAIGN, campaign_id, link, related_id)
        return
    except EspoError as exc:
        escalatable = is_forbidden(exc) and "noAccessToForeignRecord" in str(exc)
        if not escalatable or admin_factory is None:
            raise
        log.info("%s %s on campaign %s escalated to the admin account (%s)", op, link, campaign_id, exc)
        admin = await admin_factory()
        await getattr(admin, op)(cfg.CAMPAIGN, campaign_id, link, related_id)


async def set_relations(client: EspoApi, campaign_id: str, wanted: dict[str, list[str]],
                        *, admin_factory=None) -> dict[str, dict[str, list[str]]]:
    """Reconcile the exact set on each relationship; returns what moved."""
    out: dict[str, dict[str, list[str]]] = {}
    for link in (cfg.LINK_PARTNERS, cfg.LINK_FUNDERS, cfg.LINK_EVENTS):
        if link not in wanted:
            continue
        target = {i for i in wanted[link] if isinstance(i, str) and i}
        current = await related_names(client, campaign_id, link)
        if current is None:
            raise CampaignError(f"The campaign's {link} could not be read, so nothing was changed.")
        have = {r["id"] for r in current}
        added, removed = [], []
        for rid in sorted(target - have):
            await _link_or_escalate(client, admin_factory, "relate", campaign_id, link, rid)
            added.append(rid)
        for rid in sorted(have - target):
            await _link_or_escalate(client, admin_factory, "unrelate", campaign_id, link, rid)
            removed.append(rid)
        out[link] = {"added": added, "removed": removed}
    return out


# --- touches ----------------------------------------------------------------------

async def campaign_touches(client: EspoApi, campaign_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(
            cfg.TOUCH, select=cfg.TOUCH_SELECT, max_size=_PAGE, offset=offset,
            where=[{"type": "equals", "attribute": "outreachCampaignId", "value": campaign_id}],
            order_by="createdAt", order="asc",
        )
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < _PAGE or len(rows) >= 5000:
            break
        offset += _PAGE
    return rows


def touch_summary(touches: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Selected / sent / delivered / returned / scanned — computed live, never
    stored (§ 3.1 step 5)."""
    s = {"planned": 0, "sent": 0, "delivered": 0, "returned": 0, "cancelled": 0,
         "scanned": 0, "total": 0}
    for t in touches:
        s["total"] += 1
        status = (t.get("touchStatus") or "").lower()
        if status in s:
            s[status] += 1
        if t.get("outcome") == cfg.OUTCOME_SCANNED or (t.get("scanCount") or 0) > 0:
            s["scanned"] += 1
    s["pieces"] = s["sent"] + s["delivered"] + s["returned"]
    return s


# --- prospects ---------------------------------------------------------------------

async def list_prospects(client: EspoApi, *, status: Optional[str] = None, exit_: Optional[str] = None,
                         source: Optional[str] = None, batch: Optional[str] = None) -> list[dict[str, Any]]:
    """The leads, filtered by lead status, reason, Lead Source and import batch."""
    where: list[dict[str, Any]] = []
    if status:
        where.append({"type": "equals", "attribute": "leadStatus", "value": status})
    if exit_ == "none":
        where.append({"type": "isNull", "attribute": "sideExit"})
    elif exit_:
        where.append({"type": "equals", "attribute": "sideExit", "value": exit_})
    if source:
        where.append({"type": "equals", "attribute": "leadSource", "value": source})
    if batch:
        where.append({"type": "equals", "attribute": "importBatch", "value": batch})
    return await _page_all(client, cfg.PROSPECT, select=cfg.PROSPECT_SELECT, where=where or None)


async def get_prospect(client: EspoApi, prospect_id: str) -> dict[str, Any]:
    return await client.get(cfg.PROSPECT, prospect_id, select=cfg.PROSPECT_SELECT)


async def record_actions(client: Optional[EspoApi], prospect_id: str) -> list[dict[str, Any]]:
    """The action-history rows for one lead (core/action_log.py's CActionLog
    half), newest first. Read under the org-wide key — the Marketing Admin
    Role has no CActionLog grant and the rows are the record's own history.
    Feature-gated: a CRM without the entity, or a refused read, is []."""
    if client is None:
        return []
    try:
        page = await client.list(
            "CActionLog", select="id,name,actionType,category,actorName,summary,createdAt", max_size=_PAGE,
            where=[{"type": "equals", "attribute": "recordId", "value": prospect_id}],
            order_by="createdAt", order="desc",
        )
    except EspoError as exc:
        log.info("action history for %s not read: %s", prospect_id, exc)
        return []
    return page.get("list", []) if isinstance(page, dict) else []


async def partner_options(client: EspoApi) -> list[dict[str, str]]:
    """Every partner profile by name, for the lead page's referrer picker.
    Paged at the CRM's limit."""
    rows = await _page_all(client, cfg.PARTNER_PROFILE, select="id,name", limit=2000)
    return sorted(({"id": r["id"], "name": r.get("name") or "(unnamed)"} for r in rows if r.get("id")),
                  key=lambda o: o["name"].lower())


async def prospect_touches(client: EspoApi, prospect_id: str) -> list[dict[str, Any]]:
    page = await client.list(
        cfg.TOUCH, select=cfg.TOUCH_SELECT, max_size=_PAGE,
        where=[{"type": "equals", "attribute": "prospectId", "value": prospect_id}],
        order_by="createdAt", order="desc",
    )
    return page.get("list", [])


def advance_stage(current: Optional[str], proposed: str) -> Optional[str]:
    """The stage to write, or None when the proposed stage is not an advance
    (advance-only, evidence-only — § 1.8)."""
    if proposed not in cfg.STAGE_RANK:
        return None
    if current in cfg.STAGE_RANK and cfg.STAGE_RANK[current] >= cfg.STAGE_RANK[proposed]:
        return None
    return proposed


def mailing_address_text(record: dict[str, Any], prefix: str = "mailingAddress") -> str:
    """One snapshot string of an address, the form a card carries."""
    street = (record.get(f"{prefix}Street") or "").strip()
    city = (record.get(f"{prefix}City") or "").strip()
    state = (record.get(f"{prefix}State") or "").strip()
    postal = (record.get(f"{prefix}PostalCode") or "").strip()
    country = (record.get(f"{prefix}Country") or "").strip()
    line2 = " ".join(p for p in (f"{city}," if city and (state or postal) else city, state, postal) if p)
    return "\n".join(p for p in (street, line2, country) if p)


def parse_address_text(text: str) -> dict[str, str]:
    """The inverse, good enough for a snapshot the application itself wrote."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    out = {"street": "", "city": "", "state": "", "postalCode": "", "country": ""}
    if not lines:
        return out
    out["street"] = lines[0]
    if len(lines) > 1:
        rest = lines[1]
        if "," in rest:
            city, _, tail = rest.partition(",")
            out["city"] = city.strip()
            parts = tail.split()
            if parts:
                out["state"] = parts[0]
                out["postalCode"] = " ".join(parts[1:])
        else:
            out["city"] = rest
    if len(lines) > 2:
        out["country"] = lines[2]
    return out
