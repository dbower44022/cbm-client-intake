"""The audience push and the unsubscribe pull (plan § 11.5 – § 11.8).

The CRM decides who may be emailed; the mailing service's list is a mirror of
that decision (ruling 1). Every pass here is **plan, then apply**: the same
function that the nightly worker timer runs with ``apply=True`` is the
Operations job's dry-run with ``apply=False``, which is how the first run is
read before it writes anything (§ 11.5 step 7).

* **Audience** — every CRM Contact with a primary email address whose
  ``cMarketingOptIn`` is true and whose address is neither opted out nor
  invalid. Read under the org-wide API key, paged at 200 (the CRM's limit).
  The opt-in is filtered server-side; the two address flags are checked here
  from the returned record, because they are derived from the address table
  and a server-side filter on them is not relied on.
* **The list** — found by name, created when absent, its id cached on the
  connection row.
* **Add** = audience minus the list's members, minus anyone the vendor holds
  as unsubscribed (ruling 2: opt-out flows one way). Sent as one bulk import
  (``email``, ``first_name``, ``last_name`` only).
* **Remove** = the list's members minus the audience. Removed from the list,
  never deleted from the account.
* **Pull** — the vendor's unsubscribes since the cursor; the matching CRM
  Contact's address is marked opted out, advance-only, through
  ``emailAddressData`` (the write ``comms/service.py`` already makes). A
  contact the CRM does not hold is skipped, never created (ruling 1).

Nothing here raises past :func:`run_push` / :func:`run_pull`: each returns a
result whose ``ok``/``partial``/``error`` the caller reports. Alerting is the
worker's (``alerts_for``), so a failure is said once, not once per cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .config import Settings
from .espo import EspoApi, EspoError
from .mailing import (
    ConnectionStore,
    MailingAuthError,
    MailingClient,
    MailingError,
    MailingNotConnected,
    MailingRateLimited,
    make_client,
    make_connection_store,
)

log = logging.getLogger("cbm_intake.mailing.sync")

#: The CRM's list page limit — above it is a 403, not a truncation.
CRM_PAGE = 200
#: Vendor permission states that mean "never add" (ruling 2).
NEVER_ADD = frozenset({"unsubscribed", "temp_hold"})
#: Contact fields the audience read asks for.
AUDIENCE_SELECT = (
    "id,firstName,lastName,emailAddress,cMarketingOptIn,"
    "emailAddressIsOptedOut,emailAddressIsInvalid"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(email: Optional[str]) -> str:
    return (email or "").strip().lower()


# --- shapes -------------------------------------------------------------------


@dataclass(frozen=True)
class Person:
    """A CRM contact as the vendor will see it."""

    contact_id: str
    email: str
    first_name: str = ""
    last_name: str = ""

    def import_row(self) -> dict[str, str]:
        row = {"email": self.email}
        if self.first_name:
            row["first_name"] = self.first_name[:50]
        if self.last_name:
            row["last_name"] = self.last_name[:50]
        return row


@dataclass(frozen=True)
class Member:
    """A vendor contact on the list."""

    vendor_id: str
    email: str
    permission: str = ""


@dataclass
class Plan:
    list_name: str
    list_id: Optional[str]              # None ⇒ the list does not exist yet
    audience: dict[str, Person]
    members: dict[str, Member]
    vendor_unsubscribed: set[str]
    add: list[Person] = field(default_factory=list)
    remove: list[Member] = field(default_factory=list)
    withheld: list[Person] = field(default_factory=list)   # in the audience, but the vendor says no

    def compute(self) -> "Plan":
        for key in sorted(self.audience):
            if key in self.members:
                continue
            if key in self.vendor_unsubscribed:
                self.withheld.append(self.audience[key])
            else:
                self.add.append(self.audience[key])
        for key in sorted(self.members):
            if key not in self.audience:
                self.remove.append(self.members[key])
        return self

    @property
    def unchanged(self) -> int:
        return sum(1 for k in self.audience if k in self.members)

    def render(self) -> str:
        """The dry-run text. Deterministic (sorted), so its fingerprint is stable
        while the world stands still and changes the moment it does not."""
        lines = [
            f"Mailing list: {self.list_name!r}"
            + ("" if self.list_id else " — does not exist yet; apply CREATES it"),
            f"Audience (CRM, opted in, address usable): {len(self.audience)}",
            f"On the list now: {len(self.members)}",
            f"Already in step: {self.unchanged}",
            f"ADD to the list: {len(self.add)}",
        ]
        lines += [f"  + {p.email}" for p in self.add]
        lines.append(f"REMOVE from the list (stay in the account): {len(self.remove)}")
        lines += [f"  - {m.email}" for m in self.remove]
        if self.withheld:
            lines.append(
                f"Withheld — opted in here, unsubscribed at the mailing service "
                f"(never re-added): {len(self.withheld)}"
            )
            lines += [f"  ! {p.email}" for p in self.withheld]
        return "\n".join(lines)


@dataclass
class PushResult:
    ok: bool
    plan: Optional[Plan] = None
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    partial: bool = False
    needs_reauthorisation: bool = False
    text: str = ""


@dataclass
class PullResult:
    ok: bool
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    needs_reauthorisation: bool = False
    text: str = ""


# --- reads ----------------------------------------------------------------------


def _usable(record: dict[str, Any]) -> bool:
    return bool(record.get("emailAddress")) and not record.get("emailAddressIsOptedOut") \
        and not record.get("emailAddressIsInvalid")


async def audience(crm: EspoApi) -> dict[str, Person]:
    """Every opted-in contact with a usable primary address, keyed on the address."""
    out: dict[str, Person] = {}
    offset = 0
    while True:
        page = await crm.list(
            "Contact",
            where=[{"type": "isTrue", "attribute": "cMarketingOptIn"}],
            select=AUDIENCE_SELECT,
            max_size=CRM_PAGE,
            offset=offset,
            order_by="id",
            order="asc",
        )
        rows = page.get("list") or []
        for r in rows:
            if not _usable(r):
                continue
            key = _key(r.get("emailAddress"))
            if key and key not in out:  # two contacts, one address: the first wins
                out[key] = Person(
                    contact_id=str(r.get("id") or ""),
                    email=str(r.get("emailAddress")).strip(),
                    first_name=str(r.get("firstName") or "").strip(),
                    last_name=str(r.get("lastName") or "").strip(),
                )
        offset += len(rows)
        if len(rows) < CRM_PAGE or offset >= int(page.get("total") or 0):
            break
    return out


def _vendor_email(contact: dict[str, Any]) -> str:
    ea = contact.get("email_address") or {}
    if isinstance(ea, dict):
        return _key(ea.get("address"))
    return _key(ea if isinstance(ea, str) else "")


def _vendor_permission(contact: dict[str, Any]) -> str:
    ea = contact.get("email_address") or {}
    if isinstance(ea, dict):
        return str(ea.get("permission_to_send") or "").lower()
    return ""


async def members(mail: MailingClient, list_id: str) -> dict[str, Member]:
    out: dict[str, Member] = {}
    async for c in mail.contacts(list_id=list_id):
        key = _vendor_email(c)
        if key:
            out[key] = Member(str(c.get("contact_id") or ""), key, _vendor_permission(c))
    return out


async def vendor_unsubscribed(mail: MailingClient) -> set[str]:
    out: set[str] = set()
    async for c in mail.contacts(status="unsubscribed"):
        key = _vendor_email(c)
        if key:
            out.add(key)
    return out


async def build_plan(crm: EspoApi, mail: MailingClient, list_name: str) -> Plan:
    found = await mail.find_list(list_name)
    list_id = str(found.get("list_id")) if found else None
    people = await audience(crm)
    current = await members(mail, list_id) if list_id else {}
    gone = await vendor_unsubscribed(mail)
    return Plan(list_name, list_id, people, current, gone).compute()


# --- the push --------------------------------------------------------------------


async def apply_plan(plan: Plan, mail: MailingClient, store: ConnectionStore) -> dict[str, Any]:
    """Make the list match the plan. Returns the counts the readiness line shows."""
    summary: dict[str, Any] = {
        "at": _now().isoformat(), "audience": len(plan.audience), "onList": len(plan.members),
        "added": 0, "removed": 0, "withheld": len(plan.withheld), "createdList": False,
        "partial": False,
    }
    list_id = plan.list_id
    if not list_id:
        created = await mail.create_list(plan.list_name)
        list_id = str(created.get("list_id") or "")
        if not list_id:
            raise MailingError("The mailing service created the list but returned no id.")
        summary["createdList"] = True
    await store.set_list_id(list_id)
    try:
        if plan.add:
            ids = await mail.import_contacts([p.import_row() for p in plan.add], list_id=list_id)
            for activity_id in ids:
                if activity_id:
                    last = await mail.wait_for_activity(activity_id)
                    if str(last.get("state") or "").lower() not in ("completed", ""):
                        summary["partial"] = True
                        summary["importState"] = last.get("state")
            summary["added"] = len(plan.add)
        if plan.remove:
            await mail.remove_from_list([m.vendor_id for m in plan.remove if m.vendor_id], list_id=list_id)
            summary["removed"] = len(plan.remove)
    except MailingRateLimited as exc:
        summary["partial"] = True
        summary["error"] = str(exc)
    await store.record_push(summary)
    return summary


def _clients(settings: Settings, crm: Optional[EspoApi], mail: Optional[MailingClient],
             store: Optional[ConnectionStore]) -> tuple[EspoApi, MailingClient, ConnectionStore]:
    if store is None:
        store = make_connection_store(settings)
    if store is None:
        raise MailingNotConnected("No database is attached, so there is no mailing connection.")
    if mail is None:
        mail = make_client(
            store, settings.mailing_client_id, settings.mailing_client_secret,
            base_url=settings.mailing_base_url,
        )
    if crm is None:
        from .espo import EspoClient

        crm = EspoClient(
            settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
        )
    return crm, mail, store


def _refused(settings: Settings) -> str:
    if settings.espo_dry_run:
        return "This deployment runs in dry-run with no CRM; there is no audience to push."
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        return "The mailing service client ID and secret are not both set."
    return ""


async def run_push(
    settings: Settings,
    *,
    apply: bool,
    crm: Optional[EspoApi] = None,
    mail: Optional[MailingClient] = None,
    store: Optional[ConnectionStore] = None,
) -> PushResult:
    """Plan the push; apply it when asked. Never raises."""
    reason = _refused(settings)
    if reason:
        return PushResult(ok=False, error=reason, text=reason)
    try:
        crm, mail, store = _clients(settings, crm, mail, store)
        plan = await build_plan(crm, mail, settings.mailing_list_name)
    except MailingNotConnected as exc:
        text = f"Not connected: {exc}"
        return PushResult(ok=False, error=str(exc), text=text,
                          needs_reauthorisation="re-authorisation" in str(exc))
    except MailingAuthError as exc:
        return PushResult(ok=False, error=str(exc), text=f"Re-authorisation needed: {exc}",
                          needs_reauthorisation=True)
    except (MailingError, EspoError) as exc:
        return PushResult(ok=False, error=str(exc), text=f"Could not plan the push: {exc}")
    text = plan.render()
    if not apply:
        return PushResult(ok=True, plan=plan, text=text)
    try:
        summary = await apply_plan(plan, mail, store)
    except MailingAuthError as exc:
        return PushResult(ok=False, plan=plan, error=str(exc), needs_reauthorisation=True,
                          text=text + f"\n\nRe-authorisation needed: {exc}")
    except (MailingError, EspoError) as exc:
        return PushResult(ok=False, plan=plan, error=str(exc), text=text + f"\n\nFAILED: {exc}")
    tail = (
        f"\n\nApplied: added {summary['added']}, removed {summary['removed']}"
        + (", list created" if summary.get("createdList") else "")
        + (f". PARTIAL — {summary.get('error') or summary.get('importState')}" if summary.get("partial") else ".")
    )
    return PushResult(ok=True, plan=plan, summary=summary, partial=bool(summary.get("partial")),
                      text=text + tail)


# --- the pull --------------------------------------------------------------------


async def mark_opted_out(crm: EspoApi, contact_id: str, address: str) -> bool:
    """Set ``optOut`` on that one address of the Contact. Advance-only: an address
    already opted out is left alone (False = nothing to do)."""
    record = await crm.get("Contact", contact_id, select="emailAddress,emailAddressData")
    data = list(record.get("emailAddressData") or [])
    if not data and record.get("emailAddress"):
        data = [{"emailAddress": record["emailAddress"], "primary": True}]
    changed = False
    for entry in data:
        if _key(entry.get("emailAddress")) == _key(address) and not entry.get("optOut"):
            entry["optOut"] = True
            changed = True
    if changed:
        await crm.update("Contact", contact_id, {"emailAddressData": data})
    return changed


async def run_pull(
    settings: Settings,
    *,
    apply: bool,
    crm: Optional[EspoApi] = None,
    mail: Optional[MailingClient] = None,
    store: Optional[ConnectionStore] = None,
    now: Optional[datetime] = None,
) -> PullResult:
    """Unsubscribes since the cursor → CRM opt-outs. Never raises."""
    reason = _refused(settings)
    if reason:
        return PullResult(ok=False, error=reason, text=reason)
    started = now or _now()
    try:
        crm, mail, store = _clients(settings, crm, mail, store)
        conn = await store.get()
        if conn is None or not conn.usable:
            raise MailingNotConnected(
                "needs re-authorisation" if conn else "The mailing service is not connected."
            )
        cursor = conn.pull_cursor or conn.connected_at
        found: list[tuple[str, Optional[str]]] = []
        async for c in mail.contacts(status="unsubscribed", updated_after=cursor):
            email = _vendor_email(c)
            if email:
                found.append((email, None))
    except MailingNotConnected as exc:
        return PullResult(ok=False, error=str(exc), text=f"Not connected: {exc}",
                          needs_reauthorisation="re-authorisation" in str(exc))
    except MailingAuthError as exc:
        return PullResult(ok=False, error=str(exc), text=f"Re-authorisation needed: {exc}",
                          needs_reauthorisation=True)
    except (MailingError, EspoError) as exc:
        return PullResult(ok=False, error=str(exc), text=f"Could not read unsubscribes: {exc}")

    lines = [f"Unsubscribed at the mailing service since {cursor.isoformat() if cursor else 'the beginning'}: {len(found)}"]
    summary = {"at": started.isoformat(), "since": cursor.isoformat() if cursor else None,
               "unsubscribed": len(found), "optedOut": 0, "alreadyOut": 0, "unknown": 0, "errors": 0}
    for email, _ in sorted(found):
        try:
            match = await crm.find_one("Contact", "emailAddress", email, select="id,emailAddress")
        except EspoError as exc:
            summary["errors"] += 1
            lines.append(f"  ? {email} — CRM read failed: {exc}")
            continue
        if not match:
            summary["unknown"] += 1
            lines.append(f"  . {email} — not in the CRM; skipped (never created)")
            continue
        if not apply:
            lines.append(f"  → {email} would be marked opted out on Contact {match['id']}")
            continue
        try:
            changed = await mark_opted_out(crm, str(match["id"]), email)
        except EspoError as exc:
            summary["errors"] += 1
            lines.append(f"  ! {email} — CRM write refused: {exc}")
            continue
        summary["optedOut" if changed else "alreadyOut"] += 1
        lines.append(f"  - {email} {'marked opted out' if changed else 'already opted out'}")
    if apply and not summary["errors"]:
        # The cursor moves only after a clean pass, and to the pass's START, so
        # an unsubscribe that landed mid-pass is read next time.
        await store.set_pull_cursor(started)
        lines.append("Cursor advanced.")
    elif apply:
        lines.append("Cursor NOT advanced — a CRM write failed; the pass repeats next hour.")
    return PullResult(ok=not summary["errors"], summary=summary, text="\n".join(lines),
                      error="" if not summary["errors"] else f"{summary['errors']} CRM write(s) failed")


# --- alerting (§ 11.8) -----------------------------------------------------------

#: One re-authorisation alert a week at most — it is a human's to fix, and a
#: nightly repeat teaches people to ignore the channel.
REAUTH_COOLDOWN = 7 * 86400
FAILURE_COOLDOWN = 86400


def alerts_for(result: Any, *, kind: str, settings: Settings) -> list[tuple[str, str, int]]:
    """``(key, text, cooldown)`` for each alert this result deserves; the worker
    dedups them with ``monitoring._due``."""
    out: list[tuple[str, str, int]] = []
    if getattr(result, "needs_reauthorisation", False):
        out.append((
            "mailing_reauth",
            "Mailing service needs re-authorisation — the nightly push and hourly pull "
            "have stopped. An administrator reconnects it at /setup → Feature readiness → "
            f"Mailing list sync. ({result.error})",
            REAUTH_COOLDOWN,
        ))
        return out
    if not result.ok:
        out.append((f"mailing_{kind}_failed", f"Mailing {kind} failed: {result.error}", FAILURE_COOLDOWN))
    elif getattr(result, "partial", False):
        out.append((f"mailing_{kind}_partial",
                    f"Mailing {kind} was partial: {result.summary.get('error') or result.summary.get('importState')}",
                    FAILURE_COOLDOWN))
    return out
