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
    """(added message ids, new cursor) since ``start_history_id``."""
    ids: list[str] = []
    seen: set[str] = set()
    new_cursor: Optional[str] = None
    token: Optional[str] = None
    for _ in range(_MAX_HISTORY_PAGES):
        page = await gmail.list_history(start_history_id, page_token=token)
        new_cursor = page.get("historyId") or new_cursor
        for entry in page.get("history", []) or []:
            for added in entry.get("messagesAdded", []) or []:
                mid = (added.get("message") or {}).get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
        token = page.get("nextPageToken")
        if not token:
            break
    return ids, new_cursor


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

    # 1. Global dedup: this exact email may already be stored from another
    #    mailbox (CC'd co-mentor). Then only the record links can be new.
    existing = await crm.find_communication_by_rfc_id(espo, rfc_id)
    if existing:
        conv_id = existing.get(crm.CONVERSATION_FK)
        if conv_id:
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
    if not conv_id:
        conv_id = await crm.create_conversation(
            espo, subject=parsed.subject, sent_at=parsed.sent_at
        )

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

    # Everyone on the email counts as a participant — sender AND recipients
    # (Doug's ruling 2026-07-15: it matters who was included, not just who wrote).
    participants = [
        (parsed.from_name, parsed.from_address),
        *parsed.to_named,
        *parsed.cc_named,
    ]
    await crm.refresh_conversation_aggregates(
        espo, conv_id, sent_at=parsed.sent_at, participants=participants
    )
    await crm.link_records(espo, conv_id, matched, excludes)
    if scope.owner_user_id:
        await crm.stamp_owners(espo, conv_id, {scope.owner_user_id})
    return conv_id


async def _ingest_ids(
    gmail: GmailClient, espo: Any, store: Any, scope: MailboxScope, ids: list[str]
) -> int:
    stored = 0
    for mid in ids:
        try:
            parsed = parse_message(await gmail.get_message(mid))
            if await ingest_message(espo, store, scope, parsed):
                stored += 1
        except (GmailError, EspoError) as exc:
            log.warning("ingest %s/%s failed: %s", scope.mailbox, mid, exc)
        except Exception:  # noqa: BLE001 — one bad message never kills the cycle
            log.exception("unexpected ingest failure %s/%s", scope.mailbox, mid)
    return stored


async def sync_mailbox(
    gmail: GmailClient, espo: Any, store: Any, scope: MailboxScope, settings: Any
) -> dict[str, int]:
    """One sync cycle for one mailbox. Returns counters for logging/monitoring."""
    state = await store.get_sync_state(scope.mailbox)
    addresses = scope.all_addresses
    stats = {"fetched": 0, "stored": 0}

    if state is None or not state.initial_done:
        # Initial sync: bounded address-book backfill, then set the cursor.
        profile = await gmail.profile()
        queries = address_queries(sorted(addresses), extra=settings.gmail_backfill)
        ids = await _collect_query_ids(gmail, queries)
        stats["fetched"] = len(ids)
        stats["stored"] = await _ingest_ids(gmail, espo, store, scope, ids)
        await store.save_sync_state(
            scope.mailbox,
            history_id=str(profile.get("historyId") or ""),
            initial_done=True,
            known_addresses=addresses,
        )
        return stats

    # Targeted backfill for addresses that are new since the last cycle
    # (a record went active / a contact gained an address) — retroactive match.
    new_addresses = addresses - state.known_addresses
    if new_addresses:
        queries = address_queries(sorted(new_addresses), extra=settings.gmail_backfill)
        ids = await _collect_query_ids(gmail, queries)
        stats["fetched"] += len(ids)
        stats["stored"] += await _ingest_ids(gmail, espo, store, scope, ids)

    # Incremental via the history cursor; expired cursor => date-window requery.
    new_cursor = state.history_id
    try:
        ids, cursor = await _collect_history_ids(gmail, state.history_id or "")
        new_cursor = cursor or new_cursor
    except HistoryExpiredError:
        log.info("history cursor expired for %s — date-window backfill", scope.mailbox)
        profile = await gmail.profile()
        new_cursor = str(profile.get("historyId") or "")
        since = state.last_synced_at
        window = ""
        if since:
            window = "after:" + (since - timedelta(days=1)).strftime("%Y/%m/%d")
        queries = address_queries(sorted(addresses), extra=window)
        ids = await _collect_query_ids(gmail, queries)

    if ids:
        stats["fetched"] += len(ids)
        stats["stored"] += await _ingest_ids(gmail, espo, store, scope, ids)

    await store.save_sync_state(
        scope.mailbox,
        history_id=new_cursor,
        initial_done=True,
        known_addresses=addresses,
    )
    return stats


async def run_gmail_sync(
    settings: Any, store: Any, espo: Any, service_account_info: dict[str, Any]
) -> dict[str, Any]:
    """One full sync pass over every manager mailbox (the worker's timer body)."""
    scopes = await crm.build_scopes(espo, settings)
    totals: dict[str, Any] = {"mailboxes": len(scopes), "fetched": 0, "stored": 0, "errors": 0}
    for scope in scopes:
        gmail = GmailClient(
            service_account_info, scope.mailbox, settings.request_timeout_seconds
        )
        try:
            stats = await sync_mailbox(gmail, espo, store, scope, settings)
            totals["fetched"] += stats["fetched"]
            totals["stored"] += stats["stored"]
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
                )
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001 — one mailbox never kills the pass
            totals["errors"] += 1
            log.exception("unexpected sync failure for %s", scope.mailbox)
    log.info("gmail sync pass: %s", totals)
    return totals
