"""The direct-use report and the shared-account report — mentor login
integrity plan § 4.2 items 8 and 9, step 4c (Doug's C2 ruling 11-05-26: run
them on the web component, which holds the administrator account).

Once a day, behind ``INTEGRITY_CRM_USE_REPORT``, the web component reads the
last 24 hours of the CRM's Action History and sign-in log as the
administrator (only an administrator can read them, check C2) and records:

* **condition 8** — a person who created, changed or deleted records in the
  CRM's own screens: one fault per person, with counts per record type;
* **condition 9** — a sign-in to the CRM's own screens by a shared account
  (``admin``, ``admin@<mail domain>``, ``mentoradmin@<mail domain>`` by
  default; ``INTEGRITY_SHARED_ACCOUNTS``).

**Screens versus applications.** Both sign in as ``Espo``; only the network
address separates them (check C2, and ``scripts/crm_direct_use_report.sh``).
An address is the *application's* when the key-based account used it in the
window or when ``INTEGRITY_APP_ADDRESSES`` lists it. Everything else is the
screens. The prototype's "three or more logins on one address" rule is NOT
used: three staff behind one office connection would hide the very use this
reports (review of v0.310.0). With no application address known at all, the
run reports nothing and says why, rather than report every edit made
through the applications. The addresses it treats as the application's are
logged (they are servers, not people).

The configuration account (``crm.config``), the provisioning account and the
key-based account are never reported under condition 8.

Both are events, like condition 7: the fault key carries the run's local day,
so a restart or a second web copy records nothing twice, and the next daily
check closes them. They appear in the integrity digest and the fault list.
A read over ``MAX_ROWS`` rows fails the run rather than reporting part of it.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings

log = logging.getLogger("cbm_intake.integrity")

_PAGE = 200
#: The most rows one report reads from one list; past it the run fails.
MAX_ROWS = 20_000
WRITE_ACTIONS = ("create", "update", "delete")


class TooMuchToRead(RuntimeError):
    pass


def shared_accounts(settings: Settings) -> list[str]:
    own = [a.strip().lower() for a in settings.integrity_shared_accounts.split(",") if a.strip()]
    if own:
        return own
    dom = (settings.mentor_email_domain or "").strip().lower()
    return ["admin"] + ([f"admin@{dom}", f"mentoradmin@{dom}"] if dom else [])


def excluded_logins(settings: Settings, key_user: str) -> set[str]:
    out = {a.strip().lower() for a in settings.integrity_excluded_logins.split(",") if a.strip()}
    for extra in (settings.espo_provision_username, key_user):
        if extra:
            out.add(extra.strip().lower())
    return out


async def _rows(admin: Any, entity: str, where: list[dict[str, Any]], select: str,
                max_rows: int = MAX_ROWS) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        # By id: unique, so a page boundary never repeats or skips a row the
        # way many rows sharing one createdAt second can.
        data = await admin.list(entity, where=where, select=select, max_size=_PAGE,
                                offset=offset, order_by="id", order="asc")
        page = data.get("list", [])
        out.extend(page)
        if len(page) < _PAGE:
            return out
        offset += _PAGE
        if offset >= max_rows:
            raise TooMuchToRead(f"more than {MAX_ROWS} {entity} rows in one day")


async def read_window(admin: Any, key: Any, settings: Settings, now: datetime) -> dict[str, Any]:
    """Everything the two reports need, for the 24 hours before ``now``."""
    since = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    window = [{"type": "after", "attribute": "createdAt", "value": since}]
    me = await key.app_user()
    key_user = ((me.get("user") or {}).get("userName") or "").lower()
    key_id = (me.get("user") or {}).get("id") or ""
    users = {u["id"]: u for u in await _rows(admin, "User", [], "id,userName,name,type")}

    signins = await _rows(
        admin, "AuthLogRecord",
        window + [{"type": "notEquals", "attribute": "username", "value": key_user}],
        "id,username,ipAddress,isDenied,createdAt")
    try:  # the key's own sign-ins (where still logged): every address it used
        key_signins = await _rows(
            admin, "AuthLogRecord",
            window + [{"type": "equals", "attribute": "username", "value": key_user}],
            "id,ipAddress", max_rows=MAX_ROWS)
    except TooMuchToRead:
        key_signins = []  # a busy key: its history rows still name its addresses
    history = await _rows(
        admin, "ActionHistoryRecord",
        window + [{"type": "in", "attribute": "action", "value": list(WRITE_ACTIONS)}],
        "id,userId,action,targetType,ipAddress,createdAt")
    return {"keyUser": key_user, "keyId": key_id, "users": users, "signins": signins,
            "keySignins": key_signins, "history": history}


def app_addresses(data: dict[str, Any], settings: Settings) -> set[str]:
    addrs = {a.strip() for a in settings.integrity_app_addresses.split(",") if a.strip()}
    addrs |= {r.get("ipAddress") for r in data["keySignins"] if r.get("ipAddress")}
    addrs |= {r.get("ipAddress") for r in data["history"]
              if r.get("userId") == data["keyId"] and r.get("ipAddress")}
    return addrs


def find_use(data: dict[str, Any], settings: Settings, day: str) -> list[dict[str, Any]]:
    """Condition 8 and 9 faults for one window. Never names an address."""
    app = app_addresses(data, settings)
    skip = excluded_logins(settings, data["keyUser"])
    users = data["users"]
    faults: list[dict[str, Any]] = []

    per_person: dict[str, Counter] = defaultdict(Counter)
    for r in data["history"]:
        u = users.get(r.get("userId") or "") or {}
        name = (u.get("userName") or "").lower()
        if (not name or name in skip or u.get("type") == "api"
                or (r.get("ipAddress") or "") in app):
            continue
        per_person[r["userId"]][r.get("targetType") or "?"] += 1
    for uid, counts in sorted(per_person.items(), key=lambda kv: -sum(kv[1].values())):
        u = users[uid]
        detail = ", ".join(f"{t} {n}" for t, n in counts.most_common())
        faults.append({
            "key": f"8:{uid}:{day}", "condition": 8, "mentors": [],
            "login": {"id": uid, "userName": u.get("userName") or uid},
            "summary": f"{u.get('name') or u.get('userName')} ({u.get('userName')}) created, "
                       f"changed or deleted {sum(counts.values())} record(s) in the CRM's "
                       f"own screens in the last 24 hours: {detail}.",
        })

    shared = set(shared_accounts(settings))
    per_account: Counter = Counter()
    for r in data["signins"]:
        name = (r.get("username") or "").lower()
        if name in shared and not r.get("isDenied") and (r.get("ipAddress") or "") not in app:
            per_account[name] += 1
    for name, n in sorted(per_account.items()):
        faults.append({
            "key": f"9:{name}:{day}", "condition": 9, "mentors": [],
            "login": {"id": "", "userName": name},
            "summary": f"The shared account {name} signed in to the CRM's own screens "
                       f"{n} time(s) in the last 24 hours. People sign in with their own "
                       f"logins (plan § 4.8).",
        })
    return faults


async def run_crm_use_report(settings: Settings, admin: Any, key: Any, store: Any, *,
                             now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """One daily run. The counts recorded, or None when the read failed."""
    from .signin import _day

    now = now or datetime.now(timezone.utc)
    try:
        data = await read_window(admin, key, settings, now)
    except Exception as exc:  # noqa: BLE001 — a partial read reports nothing
        log.warning("integrity CRM-use report: the read failed, nothing recorded: %s", exc)
        return None
    app = app_addresses(data, settings)
    if not app:
        log.warning("integrity CRM-use report: no address of this application is known "
                    "(the key made no change and no logged sign-in today, and "
                    "INTEGRITY_APP_ADDRESSES is empty) — nothing reported, rather than "
                    "report every edit made through the applications")
        return None
    log.info("integrity CRM-use report: treating %s as this application", ", ".join(sorted(app)))
    faults = find_use(data, settings, _day(settings, now))
    recorded = [f for f in faults if await store.record_event(f, now=now)]
    out = {"c8": sum(1 for f in faults if f["condition"] == 8),
           "c9": sum(1 for f in faults if f["condition"] == 9), "new": len(recorded)}
    log.info("integrity CRM-use report: %d person(s) edited in the CRM's screens, %d shared "
             "account(s) signed in there, %d new; read %d sign-ins and %d changes",
             out["c8"], out["c9"], out["new"], len(data["signins"]), len(data["history"]))
    return out
