"""The Gmail sync engine: pull → match → clean → dedup → store → link.

Runs inside the delivery worker on its own timer (``GMAIL_SYNC`` +
``gmail_sync_seconds``). Per manager mailbox (plan §5.2):

- **initial sync**: address-book queries bounded by ``GMAIL_BACKFILL``, then
  the profile's current ``historyId`` becomes the cursor;
- **incremental**: ``history.list`` from the stored cursor (messageAdded only),
  keeping only messages that match the scope's contact addresses;
- **expired cursor** (Gmail 404): date-window re-query with one-day overlap —
  Message-ID dedup makes the overlap exactly-once;
- **new addresses** (a record/contact added since the last cycle): a targeted
  backfill query for just those addresses, so matching stays retroactive.

Ingest (per message): triage → RFC Message-ID dedup (a CC'd co-mentor's copy
becomes ONE stored message) → conversation resolution (same-mailbox threadId,
else cross-mailbox References merge, else create) → clean → store → link
matched records honoring exclusions → owner-stamp. Failures are logged and
skip the message; the loop never dies on one bad email.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from core.email_clean import clean_email
from core.espo import EspoError
from core.gmail import (
    GmailClient,
    GmailError,
    HistoryExpiredError,
    ParsedGmailMessage,
    address_queries,
    parse_message,
)

from . import crm, triage
from .crm import MailboxScope

log = logging.getLogger("cbm_intake.comms.sync")

_MAX_QUERY_PAGES = 10   # per address-chunk query (initial/backfill)
_MAX_HISTORY_PAGES = 20


async def _collect_query_ids(gmail: GmailClient, queries: list[str]) -> list[str]:
    """Union of message ids across the (chunked) address queries."""
    ids: list[str] = []
    seen: set[str] = set()
    for q in queries:
        token: Optional[str] = None
        for _ in range(_MAX_QUERY_PAGES):
            page = await gmail.list_messages(q, page_token=token)
            for m in page.get("messages", []) or []:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    ids.append(m["id"])
            token = page.get("nextPageToken")
            if not token:
                break
    return ids


async def _collect_history_ids(
    gmail: GmailClient, start_history_id: str
) -> tuple[list[str], Optional[str]]:
    """(added message ids, new cursor) since ``start_history_id``.

    If ``_MAX_HISTORY_PAGES`` truncates the listing with a ``nextPageToken``
    still pending, the returned cursor is the LAST PROCESSED history entry's
    own id — the next pass continues from there. The old code saved the
    current-tip ``historyId`` in that case, permanently skipping every
    unfetched page after a long outage on a busy mailbox (P1-5, reliability
    review 2026-07-17).
    """
    ids: list[str] = []
    seen: set[str] = set()
    tip_cursor: Optional[str] = None
    last_entry_id: Optional[str] = None
    token: Optional[str] = None
    for _ in range(_MAX_HISTORY_PAGES):
        page = await gmail.list_history(start_history_id, page_token=token)
        tip_cursor = page.get("historyId") or tip_cursor
        for entry in page.get("history", []) or []:
            last_entry_id = entry.get("id") or last_entry_id
            for added in entry.get("messagesAdded", []) or []:
                mid = (added.get("message") or {}).get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
        token = page.get("nextPageToken")
        if not token:
            return ids, tip_cursor
    # Truncated: resume from the last processed entry (or hold the old cursor
    # if nothing was processed at all).
    log.warning(
        "history listing truncated at %d pages for %s — resuming from the last "
        "processed entry next pass", _MAX_HISTORY_PAGES, gmail.mailbox,
    )
    return ids, last_entry_id or start_history_id or None


async def ingest_message(
    espo: Any,
    store: Any,
    scope: MailboxScope,
    parsed: ParsedGmailMessage,
) -> Optional[str]:
    """Store one matched message; returns the conversation id (None = skipped).

    A message qualifies when it involves a record contact's address OR belongs
    to a Gmail thread that is already a stored conversation (thread-following):
    once a conversation exists — auto-matched, added by search, or established
    by a confirmed send to a non-contact — its replies keep arriving even when
    the correspondent's address is on no contact record.
    """
    # Drafts are unsent (Gmail keeps each revision as its own message — the
    # source of duplicate "messages" in the first live run); spam/trash can
    # arrive via the history feed. None of them belong on the record.
    if {"DRAFT", "SPAM", "TRASH"} & set(parsed.label_ids):
        log.debug("skipping %s (labels=%s)", parsed.rfc_message_id, parsed.label_ids)
        return None

    # Conversation resolution inputs, shared by matching and storing.
    refs = [r.strip().strip("<>") for r in parsed.references.split() if r.strip()]
    if parsed.in_reply_to:
        refs.insert(0, parsed.in_reply_to)

    matched = scope.records_for(parsed.all_addresses)
    known_conv: Optional[str] = None
    if not matched:
        # Thread-following: no address match, but is this a reply on a thread
        # we already store? (same-mailbox thread id, else the References chain)
        known_conv = await crm.find_conversation_for_thread(
            espo, scope.mailbox, parsed.thread_id
        )
        if not known_conv and refs:
            known_conv = await crm.find_conversation_by_refs(espo, refs)
        if not known_conv:
            return None

    if triage.is_junk(parsed):
        log.debug("triage: dropping %s (%s)", parsed.rfc_message_id, parsed.subject)
        return None

    excludes = await store.all_excludes()

    # The CRM's varchar fields are 100 chars (as built) — clamp everything we
    # write so an unusually long value can never 400 the whole message. The
    # rfc id is clamped ONCE here and used for both the dedup lookup and the
    # stored value, so the key stays consistent.
    rfc_id = (parsed.rfc_message_id or "")[:100]

    # Everyone on the email counts as a participant — sender AND recipients
    # (Doug's ruling 2026-07-15: it matters who was included, not just who wrote).
    participants = [
        (parsed.from_name, parsed.from_address),
        *parsed.to_named,
        *parsed.cc_named,
    ]

    # 1. Global dedup: this exact email may already be stored from another
    #    mailbox (CC'd co-mentor). Then only the record links can be new —
    #    plus the participants merge, so a GMAIL_RESYNC replay backfills
    #    recipients onto conversations stored before v0.55.0.
    existing = await crm.find_communication_by_rfc_id(espo, rfc_id)
    if existing:
        conv_id = existing.get(crm.CONVERSATION_FK)
        if conv_id:
            await crm.refresh_participants(espo, conv_id, participants)
            await crm.link_records(espo, conv_id, matched, excludes)
            if scope.owner_user_id:
                await crm.stamp_owners(espo, conv_id, {scope.owner_user_id})
        return conv_id

    # 2. Conversation: the thread-followed one, else same-mailbox Gmail thread,
    #    else cross-mailbox merge via References/In-Reply-To, else new.
    conv_id = known_conv or await crm.find_conversation_for_thread(
        espo, scope.mailbox, parsed.thread_id
    )
    if not conv_id and refs:
        conv_id = await crm.find_conversation_by_refs(espo, refs)
    if not conv_id and parsed.thread_id:
        # Empty-shell reuse (P1-5 F5): a conversation whose first message
        # create failed has no CCommunication rows, so the CRM lookups above
        # can't find it — the local thread map can, so the retry fills the
        # SAME conversation instead of minting a duplicate shell.
        conv_id = await store.get_thread_conversation(scope.mailbox, parsed.thread_id)
    if not conv_id:
        conv_id = await crm.create_conversation(
            espo, subject=parsed.subject, sent_at=parsed.sent_at
        )
        if parsed.thread_id:
            try:
                await store.set_thread_conversation(
                    scope.mailbox, parsed.thread_id, conv_id
                )
            except Exception as exc:  # noqa: BLE001 — the map is a resilience aid
                log.warning("thread-map write failed for %s: %s", conv_id, exc)

    # 3. Clean + store the message. Raw mail stays in Gmail (the ids deep-link).
    cleaned = clean_email(parsed.body_text, parsed.body_html)
    direction = "Outbound" if parsed.from_address == scope.mailbox else "Inbound"
    await espo.create(
        crm.COMMUNICATION,
        {
            "name": (parsed.subject or "(no subject)")[:249],
            "direction": direction,
            "sentAt": parsed.sent_at or None,
            "fromAddress": parsed.from_address[:100],
            "fromName": parsed.from_name[:100],
            "toAddresses": ", ".join(parsed.to_addresses)[:500],
            "ccAddresses": ", ".join(parsed.cc_addresses)[:500],
            "snippet": cleaned.snippet[:100],
            "bodyCleaned": cleaned.html,
            "rfcMessageId": rfc_id,
            "gmailThreadId": parsed.thread_id[:100],
            "gmailMessageId": parsed.gmail_id[:100],
            "sourceMailbox": scope.mailbox[:100],
            crm.CONVERSATION_FK: conv_id,
        },
    )

    await crm.refresh_conversation_aggregates(
        espo, conv_id, sent_at=parsed.sent_at, participants=participants
    )
    await crm.link_records(espo, conv_id, matched, excludes)
    if scope.owner_user_id:
        await crm.stamp_owners(espo, conv_id, {scope.owner_user_id})
    return conv_id


async def _ingest_ids(
    gmail: GmailClient, espo: Any, store: Any, scope: MailboxScope, ids: list[str]
) -> tuple[int, list[str]]:
    """Ingest each id; returns ``(stored, failed_ids)``.

    A failure no longer just logs (P1-5): the caller holds the cursor back so
    the failed message is re-read next pass instead of being silently lost —
    the exact mechanics of the robert.cohen incident.
    """
    stored = 0
    failed: list[str] = []
    for mid in ids:
        try:
            parsed = parse_message(await gmail.get_message(mid))
            if await ingest_message(espo, store, scope, parsed):
                stored += 1
        except (GmailError, EspoError) as exc:
            failed.append(mid)
            log.warning("ingest %s/%s failed: %s", scope.mailbox, mid, exc)
        except Exception:  # noqa: BLE001 — one bad message never kills the cycle
            failed.append(mid)
            log.exception("unexpected ingest failure %s/%s", scope.mailbox, mid)
    return stored, failed


def _update_failure_state(
    state: Any, failed: list[str], dead_letter_passes: int
) -> tuple[dict[str, int], list[str], list[str]]:
    """Fold this pass's failed ids into the consecutive-failure counters.

    Returns ``(failed_counts, dead_letter, newly_dead)``. Counting is
    CONSECUTIVE: an id that stopped failing (or stopped appearing) is
    forgotten. After ``dead_letter_passes`` consecutive failing passes (D6=5)
    the id moves to the bounded dead-letter list and no longer holds the
    cursor back.
    """
    prev_counts: dict[str, int] = dict(getattr(state, "failed_ids", None) or {})
    dead: list[str] = list(getattr(state, "dead_letter", None) or [])
    counts: dict[str, int] = {}
    newly_dead: list[str] = []
    for mid in failed:
        n = prev_counts.get(mid, 0) + 1
        if n >= dead_letter_passes:
            if mid not in dead:
                dead.append(mid)
                newly_dead.append(mid)
        else:
            counts[mid] = n
    return counts, dead, newly_dead


async def sync_mailbox(
    gmail: GmailClient, espo: Any, store: Any, scope: MailboxScope, settings: Any
) -> dict[str, int]:
    """One sync cycle for one mailbox. Returns counters for logging/monitoring.

    Loss-prevention contract (P1-5): a message that fails ingest counts in
    ``failed`` (not silently dropped), and the cursor is NOT advanced past it —
    the next pass re-reads it (Message-ID dedup makes the replay cheap). Only
    after ``gmail_dead_letter_passes`` consecutive failing passes is the id
    dead-lettered and the cursor allowed past it. ``last_synced_at`` (the
    expired-cursor backfill window source) only advances on a fully-successful
    pass.
    """
    state = await store.get_sync_state(scope.mailbox)
    addresses = scope.all_addresses
    stats = {"fetched": 0, "stored": 0, "failed": 0, "deadLettered": 0}
    dead_prev: set[str] = set(getattr(state, "dead_letter", None) or []) if state else set()

    if state is None or not state.initial_done:
        # Initial sync: bounded address-book backfill, then set the cursor.
        profile = await gmail.profile()
        queries = address_queries(sorted(addresses), extra=settings.gmail_backfill)
        ids = [i for i in await _collect_query_ids(gmail, queries) if i not in dead_prev]
        stats["fetched"] = len(ids)
        stats["stored"], failed = await _ingest_ids(gmail, espo, store, scope, ids)
        counts, dead, newly_dead = _update_failure_state(
            state, failed, settings.gmail_dead_letter_passes
        )
        stats["failed"] = len(failed)
        stats["deadLettered"] = len(newly_dead)
        # Failures (beyond the dead-lettered) => initial sync is NOT done, so
        # the next pass re-runs the (deduped) backfill and retries them.
        complete = not counts
        await store.save_sync_state(
            scope.mailbox,
            history_id=str(profile.get("historyId") or "") if complete else None,
            initial_done=complete,
            known_addresses=addresses if complete else set(),
            success=complete,
            failed_ids=counts,
            dead_letter=dead,
        )
        _log_failures(scope.mailbox, counts, newly_dead)
        return stats

    # Targeted backfill for addresses that are new since the last cycle
    # (a record went active / a contact gained an address) — retroactive match.
    all_failed: list[str] = []
    known_addresses = addresses
    new_addresses = addresses - state.known_addresses
    if new_addresses:
        queries = address_queries(sorted(new_addresses), extra=settings.gmail_backfill)
        ids = [i for i in await _collect_query_ids(gmail, queries) if i not in dead_prev]
        stats["fetched"] += len(ids)
        stored, failed = await _ingest_ids(gmail, espo, store, scope, ids)
        stats["stored"] += stored
        all_failed += failed
        if failed:
            # Keep the new addresses out of known_addresses so the next pass
            # re-runs their targeted backfill (the cursor doesn't cover them).
            known_addresses = addresses - new_addresses

    # Incremental via the history cursor; expired cursor => date-window requery.
    new_cursor = state.history_id
    cursor_ids: list[str] = []
    try:
        cursor_ids, cursor = await _collect_history_ids(gmail, state.history_id or "")
        new_cursor = cursor or new_cursor
    except HistoryExpiredError:
        log.info("history cursor expired for %s — date-window backfill", scope.mailbox)
        profile = await gmail.profile()
        new_cursor = str(profile.get("historyId") or "")
        # The re-query window comes from the last FULLY-successful pass — an
        # error-path save must never have bumped it (P1-5 F2).
        since = state.last_synced_at
        window = ""
        if since:
            window = "after:" + (since - timedelta(days=1)).strftime("%Y/%m/%d")
        queries = address_queries(sorted(addresses), extra=window)
        cursor_ids = await _collect_query_ids(gmail, queries)

    cursor_ids = [i for i in cursor_ids if i not in dead_prev]
    if cursor_ids:
        stats["fetched"] += len(cursor_ids)
        stored, failed = await _ingest_ids(gmail, espo, store, scope, cursor_ids)
        stats["stored"] += stored
        all_failed += failed

    counts, dead, newly_dead = _update_failure_state(
        state, all_failed, settings.gmail_dead_letter_passes
    )
    stats["failed"] = len(all_failed)
    stats["deadLettered"] = len(newly_dead)
    # Any still-tracked failure holds the cursor at its OLD position so the
    # failed messages are re-read next pass; dead-lettered ids no longer hold
    # it back.
    cursor_held = bool(counts)
    await store.save_sync_state(
        scope.mailbox,
        history_id=state.history_id if cursor_held else new_cursor,
        initial_done=True,
        known_addresses=known_addresses,
        success=not all_failed,
        failed_ids=counts,
        dead_letter=dead,
    )
    _log_failures(scope.mailbox, counts, newly_dead)
    return stats


def _log_failures(mailbox: str, counts: dict[str, int], newly_dead: list[str]) -> None:
    if counts:
        log.warning(
            "%s: %d message(s) failing ingest (cursor held back): %s",
            mailbox, len(counts),
            ", ".join(f"{m} (pass {n})" for m, n in sorted(counts.items())),
        )
    if newly_dead:
        log.error(
            "%s: DEAD-LETTERED %d message(s) after repeated failures — skipped "
            "from now on (recover with GMAIL_RESYNC after fixing the cause): %s",
            mailbox, len(newly_dead), ", ".join(newly_dead),
        )


async def run_gmail_sync(
    settings: Any, store: Any, espo: Any, service_account_info: dict[str, Any]
) -> dict[str, Any]:
    """One full sync pass over every manager mailbox (the worker's timer body).

    ``failed`` counts messages whose ingest failed this pass (the cursor is
    held for them — nothing is lost); an alert fires when a message KEEPS
    failing (second consecutive pass) and again if it is dead-lettered, so the
    robert.cohen class surfaces as an alert instead of "0 sync errors".
    """
    from core.monitoring import send_alert

    scopes = await crm.build_scopes(espo, settings)
    totals: dict[str, Any] = {
        "mailboxes": len(scopes), "fetched": 0, "stored": 0,
        "failed": 0, "deadLettered": 0, "errors": 0,
    }
    for scope in scopes:
        gmail = GmailClient(
            service_account_info, scope.mailbox, settings.request_timeout_seconds
        )
        try:
            stats = await sync_mailbox(gmail, espo, store, scope, settings)
            totals["fetched"] += stats["fetched"]
            totals["stored"] += stats["stored"]
            totals["failed"] += stats.get("failed", 0)
            totals["deadLettered"] += stats.get("deadLettered", 0)
            await _alert_on_persistent_failures(settings, store, scope.mailbox, stats, send_alert)
        except (GmailError, EspoError) as exc:
            totals["errors"] += 1
            log.warning("sync failed for %s: %s", scope.mailbox, exc)
            try:
                state = await store.get_sync_state(scope.mailbox)
                await store.save_sync_state(
                    scope.mailbox,
                    history_id=state.history_id if state else None,
                    initial_done=bool(state and state.initial_done),
                    error=str(exc)[:500],
                    known_addresses=state.known_addresses if state else set(),
                    # F2: an errored pass must NOT advance last_synced_at (the
                    # expired-cursor backfill window source) — a long outage
                    # would otherwise silently shrink the re-query window.
                    success=False,
                    failed_ids=state.failed_ids if state else {},
                    dead_letter=state.dead_letter if state else [],
                )
            except Exception:  # noqa: BLE001
                log.warning("could not record the sync error for %s", scope.mailbox)
        except Exception:  # noqa: BLE001 — one mailbox never kills the pass
            totals["errors"] += 1
            log.exception("unexpected sync failure for %s", scope.mailbox)
        finally:
            await gmail.aclose()
    log.info("gmail sync pass: %s", totals)
    return totals


async def _alert_on_persistent_failures(
    settings: Any, store: Any, mailbox: str, stats: dict[str, int], send
) -> None:
    """Webhook-alert when a message fails a SECOND consecutive pass (it will
    now be retried until dead-lettered) and when messages are dead-lettered.
    Keyed to those transitions, so each message alerts at most twice."""
    try:
        if stats.get("deadLettered"):
            await send(
                settings,
                f"Gmail sync: {stats['deadLettered']} message(s) in {mailbox} were "
                f"DEAD-LETTERED after {settings.gmail_dead_letter_passes} failed "
                f"attempts — they are being skipped. Check the worker logs for the "
                f"message ids and cause; a GMAIL_RESYNC re-attempts them.",
            )
            return
        state = await store.get_sync_state(mailbox)
        just_persistent = [
            m for m, n in (state.failed_ids if state else {}).items() if n == 2
        ]
        if just_persistent:
            await send(
                settings,
                f"Gmail sync: {len(just_persistent)} message(s) in {mailbox} keep "
                f"failing to ingest (the sync cursor is held back so nothing is "
                f"lost). They will be retried up to "
                f"{settings.gmail_dead_letter_passes} passes — see the worker logs.",
            )
    except Exception as exc:  # noqa: BLE001 — alerting never breaks the pass
        log.warning("gmail failure alert failed for %s: %s", mailbox, exc)
