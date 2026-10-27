"""A list's kept-current copy in Constant Contact (build plan § 7e.9; ruling 95)
and the lead code in the vendor (§ 7d.2; ruling 126).

Behind ``CAMPAIGN_LIST_SYNC``. Off, the worker runs the standing list's push
exactly as before (``core/mailing_sync.run_push``) and nothing here is called.

**One pass, every list.** :func:`run_pass` reads the vendor's unsubscribes once,
checks the lead-code custom field once, pushes the standing list, then syncs
every active list whose *Keep a copy in Constant Contact* tick is on. One list's
failure never stops the others; each records its own summary on its row and
gets its own alert key (``mailing_list_<id>_failed``).

**Who a copy holds.** A list's members as a campaign would see them now — a
static list's people added by hand, a dynamic list's search run now — resolved
through the email channel's rule (``audience.resolve_targets``): the person's
own marketing consent, a usable address, and a chapter member at their
``cbmEmail`` only. A lead has no Contact and so is never held (ruling 19).

**The copy's identity.** Found by its stored id first (it follows a rename in
the application), else by the list's name. The sandbox reset empties the
stored id every night while the copy survives at the vendor, so the next sync
finds it by name rather than creating a second one. A list named like the
standing list is refused. Unticking or retiring stops the sync and never
deletes the copy.

**The lead code.** Every push writes each person's code as the ``cf:`` column
of the import (``core/mailing_sync``), minting one for a contact that has none
under the org-wide key (``leadcode.ensure_for_contact``), at most
:data:`MINT_PER_PASS` a pass so a first pass over a large audience stays inside
the worker's cycle; the rest are minted on the passes after. A CRM without the
code fields writes no code at all.

*Inferred, not yet called* (Draft 8): the custom-field endpoints, the import
column key, the list rename — see ``core/mailing.py``. M7's live send is the
check.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError
from core.mailing import MailingAuthError, MailingClient, MailingError, MailingNotConnected
from core.mailing_sync import (
    Person,
    PushResult,
    _clients,
    _key,
    _refused,
    apply_plan,
    build_plan,
    run_push,
    vendor_unsubscribed,
)

from . import config as cfg
from . import leadcode
from .audience import _by_ids, catalogue, current_members, resolve_targets

log = logging.getLogger("cbm_intake.campaigns.list_sync")

#: The vendor custom field that carries the lead code (§ 7d.2).
CODE_FIELD = "cbm_lead_code"
#: Codes minted in one pass at most; the rest wait for the next pass.
MINT_PER_PASS = 500
#: Words for a custom field the pass had to create although it had found one before.
FIELD_PRESENT = "present"
FIELD_CREATED = "created"
FIELD_RECREATED = "recreated"


def code_key(name: str) -> str:
    """The import column for a custom field (*inferred*: ``cf:<stored name>``)."""
    return f"cf:{name}"


def paste_address(base_url: str, link: str, field_name: str = CODE_FIELD) -> str:
    """The address to paste into a notice: the campaign link followed by the
    vendor's merge tag for the person's code (*inferred* spelling)."""
    return f"{(base_url or '').rstrip('/')}/c/{link}/[[custom.{field_name}]]"


# --- the custom field -----------------------------------------------------------------------

async def ensure_code_field(mail: MailingClient, *, seen_before: bool = False) -> tuple[str, str]:
    """``(stored name, state)``: the field found, or created now. ``seen_before``
    (a previous pass found it) turns a creation into ``recreated`` — an
    administrator deleted it, which Readiness says in words."""
    found = await mail.find_custom_field(CODE_FIELD)
    if found:
        return str(found.get("name") or CODE_FIELD), FIELD_PRESENT
    created = await mail.create_custom_field(CODE_FIELD)
    return str(created.get("name") or CODE_FIELD), FIELD_RECREATED if seen_before else FIELD_CREATED


# --- the lead codes ---------------------------------------------------------------------------

async def give_codes(crm: EspoApi, people: dict[str, Person], *,
                     limit: int = MINT_PER_PASS) -> tuple[dict[str, Person], dict[str, int]]:
    """Each person with their lead code: read in batches, minted for up to
    ``limit`` contacts that have none. A failed mint leaves that person without
    a code this pass (their link then opens the campaign only) — never a
    failed push. ``counts`` says how many were read, minted and left."""
    counts = {"withCode": 0, "minted": 0, "withoutCode": 0}
    if not people or not await leadcode.available(crm):
        counts["withoutCode"] = len(people)
        return people, counts
    ids = [p.contact_id for p in people.values() if p.contact_id]
    try:
        stored = await _by_ids(crm, cfg.CONTACT, ids, f"id,{leadcode.CONTACT_FIELD}")
    except EspoError as exc:
        log.warning("list sync: lead codes unreadable (%s) — none written this pass", exc)
        counts["withoutCode"] = len(people)
        return people, counts
    out: dict[str, Person] = {}
    for key, p in people.items():
        code = str((stored.get(p.contact_id) or {}).get(leadcode.CONTACT_FIELD) or "")
        if code:
            counts["withCode"] += 1
        elif p.contact_id and counts["minted"] < limit:
            try:
                code = await leadcode.ensure_for_contact(crm, p.contact_id) or ""
            except (EspoError, RuntimeError) as exc:
                log.warning("list sync: no code minted for contact %s: %s", p.contact_id, exc)
                code = ""
            counts["minted" if code else "withoutCode"] += 1
        else:
            counts["withoutCode"] += 1
        out[key] = dataclasses.replace(p, lead_code=code) if code else p
    return out, counts


# --- who a copy holds --------------------------------------------------------------------------

async def people_for_list(crm: EspoApi, store, row: dict[str, Any], settings: Settings) -> tuple[dict[str, Person], dict[str, Any]]:
    """The list's members as the email channel reaches them, keyed on the
    address, and what the resolution skipped."""
    cat = await catalogue(crm, settings)
    members = await current_members(crm, store, row, cat)
    resolved = await resolve_targets(crm, cfg.KIND_EMAIL, members["keys"])
    people: dict[str, Person] = {}
    for t in resolved["targets"]:
        key = _key(t.get("email"))
        if key and key not in people:
            people[key] = Person(contact_id=str(t.get("id") or ""), email=str(t["email"]).strip(),
                                 first_name=str(t.get("first") or "").strip(),
                                 last_name=str(t.get("last") or "").strip())
    return people, {"members": members["total"],
                    "skipped": sum(s["count"] for s in resolved["skipped"])}


class _ListRecorder:
    """What ``apply_plan`` writes, aimed at the list's own row instead of the
    connection row."""

    def __init__(self, store, list_id: str) -> None:
        self._store = store
        self._id = list_id

    async def set_list_id(self, cc_list_id: str) -> None:
        await self._store.set_cc_list_id(self._id, cc_list_id)

    async def record_push(self, summary: dict[str, Any]) -> None:
        await self._store.record_cc_sync(self._id, summary)


def refusal(row: dict[str, Any], settings: Settings) -> str:
    """Why this list's copy cannot be synced, in words, or empty."""
    if row.get("status") != "active":
        return "The list is retired; its copy at the mailing service is kept and no longer synced."
    if (row.get("name") or "").strip().casefold() == (settings.mailing_list_name or "").strip().casefold():
        return (f"The list is named like the standing mailing list, \"{settings.mailing_list_name}\" — "
                "rename the list first.")
    return ""


async def sync_list(settings: Settings, row: dict[str, Any], *, crm: EspoApi, mail: MailingClient,
                    store, gone: Optional[set[str]] = None,
                    field_name: Optional[str] = None) -> PushResult:
    """One list's sync: plan, apply, record the summary on the row. Never raises."""
    reason = refusal(row, settings)
    if reason:
        return PushResult(ok=False, error=reason, text=reason)
    recorder = _ListRecorder(store, row["id"])
    try:
        people, resolved = await people_for_list(crm, store, row, settings)
        codes: dict[str, int] = {}
        if field_name:
            people, codes = await give_codes(crm, people)
        plan = await build_plan(crm, mail, row["name"], people=people, list_id=row.get("cc_list_id"),
                                gone=gone, code_key=code_key(field_name) if field_name else None)
        summary = await apply_plan(plan, mail, recorder)
    except MailingAuthError as exc:
        return await _failed(recorder, f"Re-authorisation needed: {exc}", reauth=True)
    except MailingNotConnected as exc:
        return await _failed(recorder, f"Not connected: {exc}",
                             reauth="re-authorisation" in str(exc))
    except (MailingError, EspoError) as exc:
        return await _failed(recorder, str(exc))
    except Exception as exc:  # noqa: BLE001 — one list never stops the pass
        log.exception("list sync %s failed", row.get("id"))
        return await _failed(recorder, f"{type(exc).__name__}: {exc}")
    summary.update(members=resolved["members"], skipped=resolved["skipped"], ok=True)
    if codes:
        summary["codes"] = codes
    await store.record_cc_sync(row["id"], summary)
    return PushResult(ok=True, plan=plan, summary=summary, partial=bool(summary.get("partial")),
                      text=plan.render())


async def _failed(recorder: _ListRecorder, error: str, *, reauth: bool = False) -> PushResult:
    from core.mailing_sync import _now

    try:
        await recorder.record_push({"at": _now().isoformat(), "ok": False, "error": error})
    except Exception as exc:  # noqa: BLE001 — recording the failure is best effort
        log.warning("list sync: could not record the failure: %s", exc)
    return PushResult(ok=False, error=error, text=error, needs_reauthorisation=reauth)


# --- the pass -----------------------------------------------------------------------------------

@dataclasses.dataclass
class PassResult:
    standing: PushResult
    lists: list[tuple[dict[str, Any], PushResult]]
    field_state: str = ""


async def _field(mail: MailingClient, crm: EspoApi, conn_store) -> tuple[Optional[str], str]:
    """The custom field's name and state, or (None, reason) when no code is
    written (a CRM without the code fields, or the vendor refused)."""
    if not await leadcode.available(crm):
        return None, "the CRM has no lead code fields"
    seen = False
    try:
        conn = await conn_store.get()
        seen = bool(((conn and conn.last_push_summary) or {}).get("customField"))
    except Exception:  # noqa: BLE001
        seen = False
    try:
        return await ensure_code_field(mail, seen_before=seen)
    except MailingError as exc:
        log.warning("list sync: the custom field %s could not be read or created: %s", CODE_FIELD, exc)
        return None, f"missing: {exc}"


async def run_pass(settings: Settings, *, crm: Optional[EspoApi] = None, mail: Optional[MailingClient] = None,
                   conn_store=None, campaign_store=None) -> PassResult:
    """The worker's mailing push with the switch on. Never raises."""
    reason = _refused(settings)
    if reason:
        return PassResult(PushResult(ok=False, error=reason, text=reason), [])
    try:
        crm, mail, conn_store = _clients(settings, crm, mail, conn_store)
        gone = await vendor_unsubscribed(mail)
        name, state = await _field(mail, crm, conn_store)
    except MailingAuthError as exc:
        return PassResult(PushResult(ok=False, error=str(exc), text=f"Re-authorisation needed: {exc}",
                                     needs_reauthorisation=True), [])
    except MailingNotConnected as exc:
        return PassResult(PushResult(ok=False, error=str(exc), text=f"Not connected: {exc}",
                                     needs_reauthorisation="re-authorisation" in str(exc)), [])
    except (MailingError, EspoError) as exc:
        return PassResult(PushResult(ok=False, error=str(exc), text=f"Could not start the pass: {exc}"), [])

    field_name = name if name else None
    counts: dict[str, int] = {}

    async def prepare(c: EspoApi, people: dict[str, Person]) -> dict[str, Person]:
        out, n = await give_codes(c, people)
        counts.update(n)
        return out

    standing = await run_push(settings, apply=True, crm=crm, mail=mail, store=conn_store, gone=gone,
                              prepare=prepare if field_name else None,
                              code_key=code_key(field_name) if field_name else None)
    if standing.ok and standing.summary:
        standing.summary["customField"] = state
        if counts:
            standing.summary["codes"] = counts
        try:
            await conn_store.record_push(standing.summary)
        except Exception as exc:  # noqa: BLE001
            log.warning("list sync: could not record the field state: %s", exc)

    results: list[tuple[dict[str, Any], PushResult]] = []
    if campaign_store is None:
        from .store import make_campaign_store

        campaign_store = make_campaign_store(settings)
    if campaign_store is not None and not standing.needs_reauthorisation:
        try:
            rows = await campaign_store.cc_sync_lists()
        except Exception as exc:  # noqa: BLE001
            log.warning("list sync: the lists could not be read: %s", exc)
            rows = []
        for row in rows:
            results.append((row, await sync_list(settings, row, crm=crm, mail=mail, store=campaign_store,
                                                 gone=gone, field_name=field_name)))
    return PassResult(standing, results, state)


def mail_clients(settings: Settings) -> tuple[MailingClient, Any]:
    """The vendor client and the connection store for a web request. A test
    seam: the route tests replace it with fakes."""
    from core.mailing import make_client, shared_connection_store

    store = shared_connection_store(settings)
    if store is None:
        raise MailingNotConnected("No database is attached, so there is no mailing connection.")
    return make_client(store, settings.mailing_client_id, settings.mailing_client_secret,
                       base_url=settings.mailing_base_url), store


#: *Sync now* gives up waiting after this many seconds (the web request is cut
#: off at about a minute); the next mailing pass finishes what it began.
SYNC_NOW_SECONDS = 50


async def sync_now(settings: Settings, row: dict[str, Any], *, campaign_store, crm: Optional[EspoApi] = None,
                   mail: Optional[MailingClient] = None, conn_store=None) -> PushResult:
    """*Sync now*: one list's pass from a web request (the list page, and an
    email campaign's sign-off). Reads the unsubscribes and the custom field
    for this list alone. Never raises."""
    reason = _refused(settings)
    if reason:
        return PushResult(ok=False, error=reason, text=reason)
    try:
        if mail is None or conn_store is None:
            mail, conn_store = mail_clients(settings)
        crm, mail, conn_store = _clients(settings, crm, mail, conn_store)
        gone = await vendor_unsubscribed(mail)
        name, _state = await _field(mail, crm, conn_store)
    except MailingAuthError as exc:
        return PushResult(ok=False, error=str(exc), text=f"Re-authorisation needed: {exc}",
                          needs_reauthorisation=True)
    except (MailingError, EspoError) as exc:
        return PushResult(ok=False, error=str(exc), text=str(exc),
                          needs_reauthorisation="re-authorisation" in str(exc))
    return await sync_list(settings, row, crm=crm, mail=mail, store=campaign_store, gone=gone,
                           field_name=name or None)


async def rename_copy(settings: Settings, cc_list_id: str, name: str) -> str:
    """Rename the copy at once after a rename in the application; the next
    sync converges either way. The error in words, or empty."""
    if _refused(settings):
        return _refused(settings)
    try:
        mail, _store = mail_clients(settings)
        await mail.rename_list(cc_list_id, name)
    except MailingError as exc:
        return str(exc)
    return ""


async def emails_for_list(settings: Settings, cc_list_id: str) -> list[dict[str, Any]]:
    """*Pick the email*: the account's emails sent to the copy in the last 30
    days. Raises :class:`MailingError` in words."""
    reason = _refused(settings)
    if reason:
        raise MailingError(reason)
    mail, _store = mail_clients(settings)
    return await mail.emails_sent_to_list(cc_list_id)


def status_words(row: dict[str, Any]) -> str:
    """The copy's status for the list page's top line, in words."""
    if row.get("cc_sync") and row.get("status") == "retired":
        return "The list is retired — its copy at the mailing service is kept and no longer synced."
    if not row.get("cc_sync"):
        return ("No copy kept — the copy at the mailing service is kept as it was."
                if row.get("cc_list_id") else "No copy kept.")
    last = row.get("cc_last_sync") or {}
    if not last:
        return "Copy on — not synced yet; the next mailing pass or Sync now makes it."
    if last.get("ok") is False:
        return f"The last sync failed: {last.get('error')}"
    held = last.get("audience", 0)
    words = (f"{held} on the copy — {last.get('added', 0)} added, {last.get('removed', 0)} removed"
             + (f", {last['withheld']} withheld as unsubscribed" if last.get("withheld") else ""))
    if last.get("partial"):
        words += f" (partial: {last.get('error') or last.get('importState')})"
    return words + "."
