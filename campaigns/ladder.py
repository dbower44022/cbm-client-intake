"""The qualification ladder — the level inside Qualified (build plan § 7e.3;
rulings 104-106, 111, 117).

A Qualified lead sits at one of three levels. **Identified**: a real business
and a possible candidate, with no named person and no direct line — the
postcard's audience. **Contactable**: a named person and a phone or an email —
a call or a personal email can reach them. **Referred**: introduced by a
partner or someone trusted, with a phone or an email. The staff see one
ladder of five (Unqualified, the three, Disqualified); the CRM stores two
fields, ``leadStatus`` and ``qualificationLevel``, because the level is only
meaningful inside Qualified. It is empty at every other status.

**The rule** (ruling 106, Doug word for word: "The system will place the level
whenever something changes on a record. But a User can set it manually at
any time, and the system will not move it backwards."):

* :func:`facts` names what the lead holds — a named person, a phone, an
  email, a referrer.
* :func:`placed` is the level those facts earn.
* :func:`next_level` applies the rule. The level never moves backwards. With
  no hand setting it is the higher of the current level and the placed one.
  After a hand setting it moves forward only when a fact ABSENT at the setting
  is now present, and only as far as the facts allow ("only new facts move it
  forward"). A hand-set level whose snapshot is gone — the sandbox empties
  that table nightly — is never moved (ruling 117).

**Where it runs.** There is no one place a lead is saved: staff also edit
leads in the CRM's own screens. So :func:`after_write` runs inline after every
application write to a lead (review, enrichment, the postcard response, call
outcomes, conversion, the lead editor; the import computes the level into the
create itself), and :func:`run_level_sweep` runs in the worker every
``LEAD_LEVEL_SWEEP_SECONDS`` over the leads modified since its last pass.
Both are best-effort and write under the org-wide API key: placement is a
machine write, like every other on a lead. The watermark is the worker's
memory; the first pass after a start looks back a day, which is harmless
because placement only ever adds.

**The snapshot** of the facts at a hand setting is the application's
(``lead_level_manual``, campaigns/store.py); the CRM holds the level and who
set it, when (``levelSetByHand``, ``levelSetAt``). Everything here is
feature-detected: a CRM without the handoff's fields gets no write and the
Leads tab stays as it was.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from core.config import Settings, get_settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns.ladder")

#: The handoff's fields and links on ``CProspect`` (marketing-redesign-crm-handoff.md § 1).
FIELDS: tuple[str, ...] = ("qualificationLevel", "levelSetAt", "referredByName", "replied")
LINKS: tuple[str, ...] = ("levelSetByHand", "referredByPartner", "assignedUser")
#: What the grid and the lead page add to ``cfg.PROSPECT_SELECT`` when the CRM has them.
LADDER_SELECT = (
    "qualificationLevel,levelSetAt,levelSetByHandId,levelSetByHandName,"
    "referredByPartnerId,referredByPartnerName,referredByName,replied,"
    "assignedUserId,assignedUserName"
)
#: What placement needs to read.
FACT_SELECT = (
    "id,name,businessName,leadStatus,sideExit,firstName,lastName,phone,email,"
    "referredByPartnerId,referredByName,qualificationLevel,levelSetAt,levelSetByHandId,modifiedAt"
)

FACT_PERSON = "person"
FACT_PHONE = "phone"
FACT_EMAIL = "email"
FACT_REFERRER = "referrer"
FACTS = (FACT_PERSON, FACT_PHONE, FACT_EMAIL, FACT_REFERRER)

_PAGE = 200
_SWEEP_CAP = 5000
_FIRST_PASS_LOOKBACK = timedelta(hours=24)
_OVERLAP = timedelta(seconds=60)


# --- the rule (pure) -------------------------------------------------------------------------

def _has(value: Any) -> bool:
    return bool(str(value or "").strip())


def facts(lead: dict[str, Any]) -> frozenset[str]:
    """What the lead holds that the ladder cares about."""
    out = set()
    if _has(lead.get("firstName")) or _has(lead.get("lastName")):
        out.add(FACT_PERSON)
    if _has(lead.get("phone")):
        out.add(FACT_PHONE)
    if _has(lead.get("email")):
        out.add(FACT_EMAIL)
    if _has(lead.get("referredByPartnerId")) or _has(lead.get("referredByName")):
        out.add(FACT_REFERRER)
    return frozenset(out)


def placed(have: Iterable[str]) -> str:
    """The level the facts earn (ruling 105). A referrer with no phone or
    email is Identified, the referrer shown in the details."""
    have = set(have)
    reachable = FACT_PHONE in have or FACT_EMAIL in have
    if FACT_REFERRER in have and reachable:
        return cfg.LEVEL_REFERRED
    if FACT_PERSON in have and reachable:
        return cfg.LEVEL_CONTACTABLE
    return cfg.LEVEL_IDENTIFIED


def rank(level: Optional[str]) -> int:
    return cfg.LEVEL_RANK.get(level or "", 0)


def next_level(current: Optional[str], manual: bool, have: Iterable[str],
               facts_at_manual: Optional[Iterable[str]]) -> Optional[str]:
    """The level to write, or None for no change (ruling 106).

    ``manual`` says a person set the level by hand (the CRM's ``levelSetAt``);
    ``facts_at_manual`` is the snapshot taken then, or None when it is gone
    (ruling 117: then the level is never moved)."""
    have = set(have)
    target = placed(have)
    if rank(target) <= rank(current):
        return None                       # never backwards; nothing to add
    if manual:
        if facts_at_manual is None:
            return None                   # ruling 117: no snapshot, no move
        if not (have - set(facts_at_manual)):
            return None                   # no NEW fact since the hand setting
    return target


def plan_level(lead: dict[str, Any], snapshot: Optional[dict[str, Any]]) -> Optional[str]:
    """The ``qualificationLevel`` placement would write for this lead, or None
    for no change. ``""`` means clear: the level is empty at any status but
    Qualified."""
    current = lead.get("qualificationLevel") or ""
    if lead.get("leadStatus") != cfg.LEAD_QUALIFIED:
        return "" if current else None
    manual = _has(lead.get("levelSetAt"))
    at_manual = list(snapshot.get("facts") or []) if snapshot else None
    return next_level(current or None, manual, facts(lead), at_manual)


# --- the CRM ----------------------------------------------------------------------------------

async def available(client: EspoApi) -> bool:
    """Whether this CRM carries the handoff's lead fields and links. Fails
    closed. The metadata read is cached process-wide by ``EspoClient``."""
    reader = getattr(client, "metadata", None)
    if reader is None:
        return False
    try:
        fields = await reader(f"entityDefs.{cfg.PROSPECT}.fields")
        links = await reader(f"entityDefs.{cfg.PROSPECT}.links")
    except Exception as exc:  # noqa: BLE001 — unreadable is "not available"
        log.warning("could not read the ladder fields (%s) — no level placed", exc)
        return False
    return (isinstance(fields, dict) and all(f in fields for f in FIELDS)
            and isinstance(links, dict) and all(l in links for l in LINKS))


async def place(client: EspoApi, lead: dict[str, Any], snapshot: Optional[dict[str, Any]]) -> Optional[str]:
    """Place one lead's level. Returns the level written (``""`` for cleared),
    or None when nothing changed."""
    level = plan_level(lead, snapshot)
    if level is None:
        return None
    await client.update(cfg.PROSPECT, lead["id"], {"qualificationLevel": level or None})
    return level


def _client(settings: Settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


_store_cache: dict[str, Any] = {}


def _store(settings: Settings) -> Any:
    """One campaign store per process for the snapshot reads (the worker and
    the call sites that have none at hand)."""
    if not settings.store_enabled:
        return None
    key = settings.database_url
    if key not in _store_cache:
        from .store import make_campaign_store
        _store_cache[key] = make_campaign_store(settings)
    return _store_cache[key]


async def _snapshot(store: Any, lead_id: str) -> Optional[dict[str, Any]]:
    if store is None:
        return None
    try:
        return await store.get_level_manual(lead_id)
    except Exception as exc:  # noqa: BLE001 — a missing snapshot is "never moved" (ruling 117)
        log.warning("level snapshot read for %s failed: %s", lead_id, exc)
        return None


async def after_write(lead_id: str, *, client: Optional[EspoApi] = None,
                      settings: Optional[Settings] = None, store: Any = None) -> Optional[str]:
    """Run placement on one lead after an application write. Best-effort: never
    raises, writes nothing while the switch is off or the CRM lacks the fields.
    Returns the level written, ``""`` for cleared, None for no change."""
    try:
        settings = settings or get_settings()
        if not settings.lead_ladder:
            return None
        client = client or _client(settings)
        if client is None or not await available(client):
            return None
        lead = await client.get(cfg.PROSPECT, lead_id, select=FACT_SELECT)
        if not lead or not lead.get("id"):
            return None
        snapshot = await _snapshot(store if store is not None else _store(settings), lead_id)
        level = await place(client, lead, snapshot)
        if level is not None:
            log.info("lead %s level %s -> %s", lead_id, lead.get("qualificationLevel") or "(none)", level or "(none)")
        return level
    except Exception as exc:  # noqa: BLE001 — placement never fails the write it follows
        log.warning("level placement for %s failed: %s", lead_id, exc)
        return None


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def set_by_hand(user_client: EspoApi, store: Any, lead: dict[str, Any], level: str, *,
                      user_id: str, user_name: str) -> dict[str, Any]:
    """A person sets the level (ruling 106): written as the user, with who and
    when, and the facts snapshot recorded so later placement knows what was
    new. Raises :class:`CampaignError` when the level does not apply."""
    if level not in cfg.LEVELS:
        raise CampaignError(f"Choose Identified, Contactable or Referred; {level!r} is not a level.")
    if lead.get("leadStatus") != cfg.LEAD_QUALIFIED:
        raise CampaignError(f"Only a Qualified lead has a level; this one is {lead.get('leadStatus') or 'unknown'}. "
                            "Qualify it first.")
    if lead.get("sideExit"):
        raise CampaignError(f"This lead stopped being worked ({lead['sideExit']}); its level stays as it is.")
    was = lead.get("qualificationLevel") or ""
    held = sorted(facts(lead))
    payload = {"qualificationLevel": level, "levelSetByHandId": user_id or None, "levelSetAt": _now_crm()}
    updated = await user_client.update(cfg.PROSPECT, lead["id"], payload)
    if store is not None:
        try:
            await store.put_level_manual(lead["id"], level=level, facts=held,
                                         set_by_id=user_id, set_by=user_name)
        except Exception as exc:  # noqa: BLE001 — the CRM write stands; the sweep then never moves it (117)
            log.warning("level snapshot for %s not stored: %s", lead["id"], exc)
    return {"prospect": updated, "written": sorted(payload), "was": was}


# --- the sweep ---------------------------------------------------------------------------------

_state: dict[str, Any] = {"watermark": None}


def reset() -> None:
    """Forget the watermark (tests; a process restart does the same)."""
    _state["watermark"] = None


def _crm_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def plan_sweep(client: EspoApi, store: Any, since: str) -> list[dict[str, Any]]:
    """The leads modified after ``since`` whose level placement would change."""
    rows: list[dict[str, Any]] = []
    offset = 0
    leads: list[dict[str, Any]] = []
    while True:
        page = await client.list(
            cfg.PROSPECT, select=FACT_SELECT,
            where=[{"type": "after", "attribute": "modifiedAt", "value": since}],
            max_size=_PAGE, offset=offset, order_by="modifiedAt", order="asc")
        batch = page.get("list", [])
        leads.extend(batch)
        if len(batch) < _PAGE or offset + _PAGE >= _SWEEP_CAP:
            break
        offset += _PAGE
    snapshots: dict[str, dict[str, Any]] = {}
    if store is not None and leads:
        try:
            snapshots = await store.level_manual_for([l["id"] for l in leads])
        except Exception as exc:  # noqa: BLE001 — missing snapshots never move a hand-set level
            log.warning("level snapshots for the sweep failed: %s", exc)
    for lead in leads:
        level = plan_level(lead, snapshots.get(lead["id"]))
        if level is None:
            continue
        rows.append({"id": lead["id"], "name": lead.get("businessName") or lead.get("name") or lead["id"],
                     "from": lead.get("qualificationLevel") or "", "to": level, "lead": lead})
    return rows


def plan_text(plan: list[dict[str, Any]], since: str) -> str:
    head = f"Leads edited since {since} UTC whose level would change: {len(plan)}."
    lines = [f"  {r['id']}  {r['from'] or '(none)':<12} -> {r['to'] or '(none)':<12}  {r['name']}" for r in plan]
    return "\n".join([head, *lines]) if lines else head


async def apply_sweep(client: EspoApi, plan: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"placed": 0, "cleared": 0, "errors": 0}
    for row in plan:
        try:
            await client.update(cfg.PROSPECT, row["id"], {"qualificationLevel": row["to"] or None})
            totals["placed" if row["to"] else "cleared"] += 1
        except EspoError as exc:
            totals["errors"] += 1
            log.warning("level sweep: %s not placed: %s", row.get("id"), exc)
    return totals


async def run_level_sweep(settings: Settings, *, client: Optional[EspoApi] = None,
                          store: Any = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """The worker's pass. Best-effort, never raises."""
    totals: dict[str, Any] = {"planned": 0, "placed": 0, "cleared": 0, "errors": 0}
    if not (settings.campaigns_enabled and settings.lead_ladder):
        return totals
    client = client or _client(settings)
    if client is None:
        return totals
    started = now or datetime.now(timezone.utc)
    try:
        if not await available(client):
            return totals
        since = _state["watermark"] or _crm_stamp(started - _FIRST_PASS_LOOKBACK)
        plan = await plan_sweep(client, store if store is not None else _store(settings), since)
        totals["planned"] = len(plan)
        totals.update(await apply_sweep(client, plan))
        _state["watermark"] = _crm_stamp(started - _OVERLAP)
        totals["since"] = since
    except Exception as exc:  # noqa: BLE001 — a sweep failure is a log line, never a crash
        totals["errors"] += 1
        log.warning("lead level sweep failed: %s", exc)
    log.info("lead level sweep: %s", totals)
    return totals


# --- the Operations job (dry run, then apply that exact plan) ----------------------------------

def _job_since() -> str:
    return _crm_stamp(datetime.now(timezone.utc) - _FIRST_PASS_LOOKBACK)[:13] + ":00:00"


async def _job_client(settings: Settings) -> EspoApi:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    if not await available(client):
        raise RuntimeError("This CRM does not carry the ladder's lead fields yet (marketing-redesign-crm-handoff.md).")
    return client


async def job_dry_run(settings: Settings) -> str:
    client = await _job_client(settings)
    since = _job_since()
    return plan_text(await plan_sweep(client, _store(settings), since), since)


async def job_apply(settings: Settings) -> str:
    client = await _job_client(settings)
    plan = await plan_sweep(client, _store(settings), _job_since())
    totals = await apply_sweep(client, plan)
    return (f"{totals['placed']} leads placed, {totals['cleared']} levels cleared "
            f"(status no longer Qualified), {totals['errors']} errors.")
