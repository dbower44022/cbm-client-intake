"""User-facing Communications operations (the session tools' endpoints).

CRM reads run **as the signed-in user** (their token, ACL-enforced) — like
every other sessions read. Gmail operations (search, send) impersonate ONLY
the signed-in user's own CBM mailbox, resolved from their CRM identity
(:func:`user_mailbox`) — never from request input. CRM *writes* that need
create/edit grants (storing an included/sent message, unlinking) go through
the intake API client, the same identity the sync worker uses.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoError
from core.gmail import GmailClient, build_mime, parse_message

from . import crm
from .store import ACTION_EXCLUDE, ACTION_INCLUDE, CommsStore, make_comms_store
from .sync import ingest_message

log = logging.getLogger("cbm_intake.comms.service")

# Reverse link on each parent entity listing its conversations (spec §4.1).
PARENT_CONVERSATIONS_LINK = "conversations"

_PAGE = 200


class CommsError(Exception):
    """A user-visible failure (message is safe to show)."""


class OriginalGoneError(CommsError):
    """The message no longer exists in the source mailbox (View original)."""


# --- lazy singletons ---------------------------------------------------------

_store: Optional[CommsStore] = None
_sa_info: Optional[dict[str, Any]] = None


def get_store(settings: Settings) -> Optional[CommsStore]:
    global _store
    if _store is None:
        _store = make_comms_store(settings)
    return _store


async def get_service_account(settings: Settings) -> Optional[dict[str, Any]]:
    """The Google service-account key (Email-Setup config first, env fallback),
    cached for the process lifetime."""
    global _sa_info
    if _sa_info is not None:
        return _sa_info
    from core.app_config import make_app_config_store
    from core.gmail import resolve_gmail_service_account

    google_cfg = None
    cfg_store = make_app_config_store(settings)
    if cfg_store is not None:
        try:
            google_cfg = await cfg_store.get_google_config()
        except Exception as exc:  # noqa: BLE001 — fall back to env
            log.warning("could not read Email-Setup config: %s", exc)
        finally:
            await cfg_store.dispose()
    _sa_info = resolve_gmail_service_account(settings, google_cfg)
    return _sa_info


async def gmail_for_user(
    settings: Settings, user_client: Any, user: dict[str, Any]
) -> GmailClient:
    """A Gmail client for the SIGNED-IN user's own mailbox — the subject rule.

    The mailbox comes from their linked ``CMentorProfile.cbmEmail`` (resolved
    through their own token, so it's their profile by ACL + assignment).
    """
    from sessions.service import resolve_manager_profile

    profile_id = await resolve_manager_profile(user_client, user["userId"])
    if not profile_id:
        raise CommsError("Your login isn't linked to a CBM profile.")
    profile = await user_client.get(crm.MENTOR_PROFILE, profile_id, select="cbmEmail")
    mailbox = (profile.get("cbmEmail") or "").strip().lower()
    if not mailbox:
        raise CommsError(
            "Your profile has no CBM email address, so your mailbox can't be read."
        )
    sa_info = await get_service_account(settings)
    if sa_info is None:
        raise CommsError("The Gmail integration isn't configured.")
    return GmailClient(sa_info, mailbox, settings.request_timeout_seconds)


async def gmail_for_shared_mailbox(settings: Settings, mailbox: str) -> GmailClient:
    """A Gmail client for a SHARED mailbox (the /ops info@ channel) — same
    delegated stack, fixed subject from config instead of the user's profile.
    The mailbox must be a real Workspace user mailbox (not a group/alias)."""
    mailbox = (mailbox or "").strip().lower()
    if not mailbox:
        raise CommsError("No shared mailbox is configured.")
    sa_info = await get_service_account(settings)
    if sa_info is None:
        raise CommsError("The Gmail integration isn't configured.")
    return GmailClient(sa_info, mailbox, settings.request_timeout_seconds)


# --- reads (as the user) -------------------------------------------------------

_CONV_SELECT = (
    "name,conversationStatus,summary,actionItems,keyTopics,"
    "firstMessageAt,lastMessageAt,messageCount,participants"
)


def _conversation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a CConversation list envelope to the API row shape, newest first."""
    rows = [
        {
            "id": c["id"],
            "subject": c.get("name"),
            "status": c.get("conversationStatus"),
            "summary": c.get("summary"),
            "actionItems": [
                a for a in (c.get("actionItems") or "").split("\n") if a.strip()
            ],
            "keyTopics": [
                t.strip() for t in (c.get("keyTopics") or "").split(",") if t.strip()
            ],
            "participants": c.get("participants"),
            "messageCount": c.get("messageCount"),
            "firstMessageAt": c.get("firstMessageAt"),
            "lastMessageAt": c.get("lastMessageAt"),
        }
        for c in data.get("list", [])
    ]
    rows.sort(key=lambda r: r.get("lastMessageAt") or "", reverse=True)
    return rows


async def list_conversations(
    user_client: Any, parent_entity: str, parent_id: str
) -> list[dict[str, Any]]:
    data = await user_client.list_related(
        parent_entity, parent_id, PARENT_CONVERSATIONS_LINK,
        select=_CONV_SELECT, max_size=_PAGE,
    )
    return _conversation_rows(data)


# The Contact side of the CConversation.contacts many-to-many — EspoCRM
# auto-prefixed the custom link on the built-in Contact entity (see
# cconversation-entity.md). Probe-verified live on crm-test 2026-07-23.
CONTACT_CONVERSATIONS_LINK = "cConversations"


async def list_contact_conversations(
    user_client: Any, contact_id: str
) -> list[dict[str, Any]]:
    """Every conversation linked to ONE Contact (the View Contact page read).
    Callers apply their own visibility filter (e.g. only-my-conversations)."""
    data = await user_client.list_related(
        "Contact", contact_id, CONTACT_CONVERSATIONS_LINK,
        select=_CONV_SELECT, max_size=_PAGE,
    )
    return _conversation_rows(data)


# A conversation the user has NEVER opened counts as unread only when its last
# message is this recent — without the window, day one would bold a year of
# history. Opening a thread (or "Mark all read") stamps it read permanently.
_NEVER_SEEN_UNREAD_DAYS = 30


def _parse_crm_stamp(value: Any) -> Optional[Any]:
    """EspoCRM datetime string ("YYYY-MM-DD HH:MM:SS", UTC) -> aware datetime."""
    from datetime import datetime, timezone

    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None


async def enrich_conversation_rows(
    user_client: Any, store: Any, username: str, rows: list[dict[str, Any]]
) -> None:
    """Stamp each conversation row with ``unread`` + ``awaitingReply`` +
    ``bounced``.

    - ``awaitingReply``: the conversation's LAST message is inbound — the ball
      is in the manager's court. One batched CCommunication query for the whole
      page (newest-first, capped), never one query per row.
    - ``bounced``: that last inbound message is a delivery-status bounce — the
      manager's send did NOT arrive (rendered as "delivery failed", §3.4).
    - ``unread``: the last message is newer than this user's read stamp
      (conversation_seen); a never-opened conversation counts as unread only
      inside the recent window above.

    Pure decoration: any failure leaves the rows unstamped (both keys default
    False) and never breaks the listing."""
    if not rows:
        return
    from datetime import datetime, timedelta, timezone

    from core.gmail import looks_like_bounce

    for r in rows:
        r.setdefault("unread", False)
        r.setdefault("awaitingReply", False)
        r.setdefault("bounced", False)
    ids = [r["id"] for r in rows]
    try:
        # Newest-first, paged at EspoCRM's hard 200-per-page cap (a larger
        # maxSize is a 403 that silently killed this whole enrichment — found
        # live 2026-07-22); stop as soon as every listed conversation has its
        # newest message, bounded so a page of long threads can't spin.
        last_message: dict[str, dict[str, Any]] = {}
        offset = 0
        for _ in range(3):
            data = await user_client.list(
                crm.COMMUNICATION,
                where=[{"type": "in", "attribute": crm.CONVERSATION_FK, "value": ids}],
                select=f"{crm.CONVERSATION_FK},direction,sentAt,fromAddress,name",
                order_by="sentAt",
                order="desc",
                max_size=200,
                offset=offset,
            )
            batch = data.get("list", [])
            for m in batch:
                cid = m.get(crm.CONVERSATION_FK)
                if cid and cid not in last_message:
                    last_message[cid] = m
            if len(last_message) >= len(ids) or len(batch) < 200:
                break
            offset += 200
        for r in rows:
            m = last_message.get(r["id"])
            if not m or (m.get("direction") or "") != "Inbound":
                continue
            # A bounce as the newest message = the manager's send did NOT
            # arrive — "delivery failed", never "reply owed" (§3.4).
            if looks_like_bounce(m.get("fromAddress") or "", m.get("name") or ""):
                r["bounced"] = True
            else:
                r["awaitingReply"] = True
    except Exception as exc:  # noqa: BLE001 — decoration only
        log.warning("awaiting-reply enrichment failed: %s", exc)
    try:
        seen = await store.seen_map(username, ids) if store else {}
        window_start = datetime.now(timezone.utc) - timedelta(
            days=_NEVER_SEEN_UNREAD_DAYS
        )
        for r in rows:
            last_at = _parse_crm_stamp(r.get("lastMessageAt"))
            if last_at is None:
                continue
            seen_at = seen.get(r["id"])
            r["unread"] = (
                last_at > window_start if seen_at is None else last_at > seen_at
            )
    except Exception as exc:  # noqa: BLE001 — decoration only
        log.warning("unread enrichment failed: %s", exc)


_MSG_SELECT = (
    "name,direction,sentAt,fromAddress,fromName,toAddresses,ccAddresses,"
    "snippet,bodyCleaned,gmailThreadId,gmailMessageId,sourceMailbox,rfcMessageId"
)


async def get_conversation(
    user_client: Any,
    conversation_id: str,
    *,
    store: Any = None,
    parent_entity: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> dict[str, Any]:
    """The thread payload. With a record context (``parent_entity`` +
    ``parent_id`` + ``store``), each message also carries its ``attachments``
    ledger rows for THAT record — the thread view's chips (§3.1)."""
    from core.gmail import looks_like_bounce

    conv = await user_client.get(crm.CONVERSATION, conversation_id, select=_CONV_SELECT)
    msgs = await user_client.list(
        crm.COMMUNICATION,
        where=[{"type": "equals", "attribute": crm.CONVERSATION_FK, "value": conversation_id}],
        select=_MSG_SELECT,
        max_size=_PAGE,
        order_by="sentAt",
    )
    messages = [
        {
            "id": m["id"],
            "direction": m.get("direction"),
            "sentAt": m.get("sentAt"),
            "from": m.get("fromName") or m.get("fromAddress"),
            "fromAddress": m.get("fromAddress"),
            "to": m.get("toAddresses"),
            "cc": m.get("ccAddresses"),
            "subject": m.get("name"),
            "bodyHtml": m.get("bodyCleaned") or "",
            "gmailMessageId": m.get("gmailMessageId"),
            "sourceMailbox": m.get("sourceMailbox"),
            "rfcMessageId": m.get("rfcMessageId"),
            # A delivery-status bounce renders as a red "Delivery failed"
            # card instead of an ordinary received message (§3.4).
            "bounce": (
                m.get("direction") == "Inbound"
                and looks_like_bounce(m.get("fromAddress") or "", m.get("name") or "")
            ),
        }
        for m in msgs.get("list", [])
    ]
    if store is not None and parent_entity and parent_id:
        try:
            by_rfc = await store.attachments_for_record(
                parent_entity, parent_id,
                [m["rfcMessageId"] for m in messages if m.get("rfcMessageId")],
            )
            for m in messages:
                rows = by_rfc.get(m.get("rfcMessageId") or "") or []
                if rows:
                    m["attachments"] = [
                        {
                            "filename": a.get("filename"),
                            "status": a.get("status"),
                            "documentId": a.get("documentId"),
                            "size": a.get("size"),
                            "mimeType": a.get("mimeType"),
                        }
                        for a in rows
                    ]
        except Exception as exc:  # noqa: BLE001 — chips are decoration
            log.warning("attachment chip lookup failed: %s", exc)
    return {
        "id": conversation_id,
        "subject": conv.get("name"),
        "status": conv.get("conversationStatus"),
        "summary": conv.get("summary"),
        "actionItems": [a for a in (conv.get("actionItems") or "").split("\n") if a.strip()],
        "keyTopics": [t.strip() for t in (conv.get("keyTopics") or "").split(",") if t.strip()],
        "messages": messages,
    }


# --- View original (§3.2) ----------------------------------------------------

_ORIGINAL_SELECT = (
    "name,direction,sentAt,fromAddress,fromName,toAddresses,ccAddresses,"
    "gmailThreadId,gmailMessageId,sourceMailbox,rfcMessageId"
)


async def _original_comm(
    settings: Settings, user_client: Any, communication_id: str
) -> tuple[dict[str, Any], GmailClient]:
    """The stored message row (read AS THE USER — the same ACL gate as the
    thread read) and a Gmail client for its SOURCE mailbox. The source-mailbox
    fetch runs under the service delegation regardless of the viewer (Doug's
    ruling: any viewer entitled to the record sees the full original —
    consistent with the conversation already being shared on the record)."""
    comm = await user_client.get(
        crm.COMMUNICATION, communication_id, select=_ORIGINAL_SELECT
    )
    mailbox = (comm.get("sourceMailbox") or "").strip().lower()
    gmail_id = comm.get("gmailMessageId") or ""
    if not mailbox or not gmail_id:
        raise CommsError(
            "This message's Gmail original isn't tracked, so it can't be shown."
        )
    return comm, await gmail_for_shared_mailbox(settings, mailbox)


async def get_original(
    settings: Settings,
    user_client: Any,
    communication_id: str,
    *,
    cid_base: str,
    acting_user: str = "",
) -> dict[str, Any]:
    """The complete original message, formatting intact, for the in-app
    viewer: sanitized original HTML (``cid:`` inline images rewritten to the
    companion endpoint at ``cid_base``), headers, and the attachment parts.
    Every access is provenance-logged (§3.4 trust note)."""
    from core.email_clean import _text_to_html, sanitize_original_html
    from core.gmail import MessageGoneError, parse_message

    comm, gmail = await _original_comm(settings, user_client, communication_id)
    log.info(
        "original view: %s/%s fetched for %s (communication %s)",
        gmail.mailbox, comm.get("gmailMessageId"), acting_user or "?",
        communication_id,
    )
    try:
        raw = await gmail.get_message(comm["gmailMessageId"])
    except MessageGoneError:
        raise OriginalGoneError(
            "The original message no longer exists in the source mailbox."
        )
    finally:
        await gmail.aclose()
    parsed = parse_message(raw)
    html = parsed.body_html or _text_to_html(parsed.body_text or "")
    return {
        "id": communication_id,
        "subject": parsed.subject or comm.get("name"),
        "from": parsed.from_name or parsed.from_address,
        "fromAddress": parsed.from_address,
        "to": ", ".join(parsed.to_addresses),
        "cc": ", ".join(parsed.cc_addresses),
        "sentAt": parsed.sent_at or comm.get("sentAt"),
        "bodyHtml": sanitize_original_html(html, cid_base=cid_base),
        "attachments": [
            {
                "filename": a.filename,
                "mimeType": a.mime_type,
                "size": a.size,
                "inline": not a.is_attachment,
            }
            for a in parsed.attachments
        ],
    }


async def get_original_part(
    settings: Settings,
    user_client: Any,
    communication_id: str,
    content_id: str,
    *,
    acting_user: str = "",
) -> dict[str, Any]:
    """One inline part's bytes by Content-ID — the ``cid:`` subresource behind
    the View original render. Same ACL gate + provenance logging as the
    original itself."""
    from core.gmail import MessageGoneError, parse_message

    comm, gmail = await _original_comm(settings, user_client, communication_id)
    wanted = (content_id or "").strip().strip("<>").strip()
    try:
        try:
            raw = await gmail.get_message(comm["gmailMessageId"])
        except MessageGoneError:
            raise OriginalGoneError(
                "The original message no longer exists in the source mailbox."
            )
        parsed = parse_message(raw)
        part = next(
            (a for a in parsed.attachments if a.content_id == wanted), None
        )
        if part is None:
            raise CommsError("That inline image isn't part of this message.")
        log.info(
            "original cid fetch: %s/%s part %s for %s",
            gmail.mailbox, comm.get("gmailMessageId"), wanted, acting_user or "?",
        )
        data = await gmail.get_attachment(parsed.gmail_id, part.attachment_id)
    finally:
        await gmail.aclose()
    return {"data": data, "mime_type": part.mime_type or "application/octet-stream"}


# --- curation ---------------------------------------------------------------


async def exclude_conversation(
    user_client: Any,
    store: CommsStore,
    parent_entity: str,
    parent_id: str,
    conversation_id: str,
    username: str,
) -> None:
    """Hide a conversation from this record (record-level, shared): unlink in
    the CRM, then persist the exclusion so the sync never re-links it.

    Contract (P2, reliability review 2026-07-17 + decision D5): the unlink runs
    FIRST, **as the signed-in user** (their ACL applies and Espo history
    records them — like every other staff write), and only a successful unlink
    records the durable override. A failed unlink raises :class:`EspoError`
    (the router maps it to a readable 403/502) with NOTHING recorded, so the
    conversation stays visible — the old order recorded the override even when
    the unlink failed, leaving "hidden in the app, still linked in the CRM"
    with nothing retrying. A store failure AFTER the unlink raises
    :class:`CommsError`; until the user retries, the sync may re-link the
    conversation (it stays visible), which converges on retry.
    """
    if parent_entity == "Contact":
        # A View Contact page "Remove": detach the conversation from the one
        # contact (the contacts many-to-many), not from any parent record.
        link = crm.CONTACTS_LINK
    else:
        link = crm.PARENT_LINKS.get(parent_entity)
    if link:
        await user_client.unrelate(crm.CONVERSATION, conversation_id, link, parent_id)
    try:
        await store.set_override(
            parent_entity, parent_id, conversation_id, ACTION_EXCLUDE, username
        )
    except Exception as exc:
        log.warning(
            "exclude override write failed for %s on %s/%s: %s",
            conversation_id, parent_entity, parent_id, exc,
        )
        raise CommsError(
            "The conversation was unlinked in the CRM, but the hide could not "
            "be recorded — it may reappear after the next sync. Hide it again "
            "to finish."
        )


async def search_mailbox(gmail: GmailClient, query: str) -> list[dict[str, Any]]:
    """Live search of the signed-in user's own mailbox (thread-level rows)."""
    page = await gmail.list_messages(query, max_results=25)
    threads: dict[str, dict[str, Any]] = {}
    for ref in page.get("messages", []) or []:
        if len(threads) >= 10:
            break
        raw = await gmail.get_message(ref["id"])
        parsed = parse_message(raw)
        row = threads.setdefault(
            parsed.thread_id,
            {
                "gmailThreadId": parsed.thread_id,
                "subject": parsed.subject,
                "from": parsed.from_name or parsed.from_address,
                "date": parsed.sent_at,
                "snippet": parsed.snippet,
                "messageCount": 0,
            },
        )
        row["messageCount"] += 1
        if parsed.sent_at > (row["date"] or ""):
            row["date"] = parsed.sent_at
    return sorted(threads.values(), key=lambda r: r["date"] or "", reverse=True)


async def _record_ref(
    client: Any, cfg: Any, parent_id: str, parent_name: str = ""
) -> crm.RecordRef:
    """A RecordRef for ONE record (contacts + addresses), for targeted ingest."""
    ref = crm.RecordRef(entity=cfg.parent_entity, id=parent_id, name=parent_name)
    contacts = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select="name,emailAddress", max_size=_PAGE,
    )
    for c in contacts.get("list", []) or []:
        ref.contact_ids.add(c["id"])
        for addr in crm._contact_addresses(c):
            ref.addresses.add(addr)
            ref.contact_by_address.setdefault(addr, c["id"])
    return ref


async def contact_ref(client: Any, contact_id: str) -> crm.RecordRef:
    """A RecordRef for ONE Contact (the View Contact page scope): the ingest
    links the conversation to the contact via the ``contacts`` many-to-many
    and to NO parent record, and the contact's own addresses are the
    known-recipient allowlist."""
    contact = await client.get(
        "Contact", contact_id, select="name,emailAddress,emailAddressData"
    )
    ref = crm.RecordRef(
        entity="Contact", id=contact_id, name=contact.get("name") or ""
    )
    ref.contact_ids.add(contact_id)
    for addr in crm._contact_addresses(contact):
        ref.addresses.add(addr)
        ref.contact_by_address.setdefault(addr, contact_id)
    return ref


async def include_thread(
    *,
    settings: Settings,
    api_client: Any,
    store: CommsStore,
    gmail: GmailClient,
    cfg: Any = None,
    parent_id: str = "",
    gmail_thread_id: str,
    user: dict[str, Any],
    ref: Optional[crm.RecordRef] = None,
) -> Optional[str]:
    """Attach a mailbox thread to this record: ingest its messages (targeted —
    the record's contacts are force-matched) + persist the inclusion. Pass a
    pre-built ``ref`` (e.g. :func:`contact_ref`) to scope to something other
    than a ``cfg`` parent record; overrides key off ``(ref.entity, ref.id)``."""
    ref = ref or await _record_ref(api_client, cfg, parent_id)
    scope = crm.MailboxScope(
        mailbox=gmail.mailbox,
        manager_name=user.get("name") or "",
        owner_user_id=user.get("userId"),
        records=[ref],
    )
    thread = await gmail.get_thread(gmail_thread_id)
    conv_id: Optional[str] = None
    for raw in thread.get("messages", []) or []:
        parsed = parse_message(raw)
        # Force the match: an included thread belongs to this record even when
        # no known contact address appears on it.
        ref.addresses |= parsed.all_addresses
        result = await ingest_message(
            api_client, store, scope, parsed, settings=settings, gmail=gmail
        )
        conv_id = result or conv_id
    if conv_id:
        await store.set_override(
            ref.entity, ref.id, conv_id, ACTION_INCLUDE, user.get("userName", "")
        )
    return conv_id


# --- send ---------------------------------------------------------------------


async def user_signature(user_client: Any, user_id: str) -> str:
    """The signed-in user's email signature — ``Preferences.signature`` in
    EspoCRM (authored under Preferences → Email Signature, or via the
    /mentorprofile editor), sanitized for the compose editor. Gmail never
    appends its own signature to API-sent raw MIME, so the compose dialogs
    seed this into the body instead. Best-effort: any failure = "" — a
    signature must never break composing."""
    try:
        prefs = await user_client.get("Preferences", user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("signature read failed for %s: %s", user_id, exc)
        return ""
    sig = str(prefs.get("signature") or "")
    if not sig.strip():
        return ""
    from .templates import sanitize_template_html

    return sanitize_template_html(sig)


# One Gmail message tops out at 25 MB encoded; stay under it with headroom.
MAX_ATTACHMENT_TOTAL_BYTES = 20 * 1024 * 1024


async def resolve_attachments(
    user_client: Any, items: Optional[list[dict[str, Any]]]
) -> list[tuple[str, str, bytes]]:
    """Materialize compose attachments as ``(filename, content_type, bytes)``.

    Two shapes per item: ``{"espoId": …}`` — a template-attachment chip whose
    bytes live in EspoCRM and are downloaded NOW, at send time, as the acting
    user (ET-B3/ET-131); or ``{"filename", "contentType", "dataBase64"}`` — a
    file the user attached locally. ANY failure raises :class:`CommsError` so
    the send is blocked rather than going out without the attachment (ET-131).
    """
    import base64 as b64

    out: list[tuple[str, str, bytes]] = []
    total = 0
    for item in items or []:
        espo_id = (item.get("espoId") or "").strip()
        if espo_id:
            name = item.get("filename") or "attachment"
            try:
                meta = await user_client.get("Attachment", espo_id, select="name,type")
                name = meta.get("name") or name
                data, content_type = await user_client.download_attachment(espo_id)
                content_type = meta.get("type") or content_type
            except EspoError as exc:
                log.warning("template attachment %s download failed: %s", espo_id, exc)
                raise CommsError(
                    f"Couldn't fetch the template attachment \"{name}\" from the "
                    "CRM — the message was NOT sent. Remove the attachment or try again."
                )
        else:
            name = (item.get("filename") or "").strip() or "attachment"
            try:
                data = b64.b64decode(item.get("dataBase64") or "", validate=True)
            except Exception:
                raise CommsError(f"The attachment \"{name}\" didn't upload cleanly — re-attach it.")
            if not data:
                raise CommsError(f"The attachment \"{name}\" is empty — re-attach it.")
            content_type = item.get("contentType") or "application/octet-stream"
        total += len(data)
        if total > MAX_ATTACHMENT_TOTAL_BYTES:
            raise CommsError(
                "Attachments are too large — keep the total under "
                f"{MAX_ATTACHMENT_TOTAL_BYTES // (1024 * 1024)} MB per message."
            )
        out.append((name, content_type, data))
    return out


async def write_back_email(
    user_client: Any,
    *,
    subject: str,
    body_html: str,
    sender: str,
    to: list[str],
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    parent_type: Optional[str] = None,
    parent_id: Optional[str] = None,
    message_id: str = "",
) -> str:
    """Record the sent message as a native EspoCRM **Email** (status Sent) so
    it shows in the parent's History/Activities panel — created AS the acting
    user (ET-140/143). Raises on failure; callers surface a retry (ET-142)."""
    from datetime import datetime, timezone

    payload: dict[str, Any] = {
        "name": subject or "(no subject)",
        "status": "Sent",
        "from": sender,
        "to": ";".join(to),
        "body": body_html,
        "isHtml": True,
        "dateSent": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        # sender attribution = createdBy — the record is created as the acting user
    }
    if cc:
        payload["cc"] = ";".join(cc)
    if bcc:
        payload["bcc"] = ";".join(bcc)
    if message_id:
        payload["messageId"] = f"<{message_id}>" if not message_id.startswith("<") else message_id
    if parent_type and parent_id:
        payload["parentType"] = parent_type
        payload["parentId"] = parent_id
    created = await user_client.create("Email", payload)
    return created.get("id") or ""


def _write_back_result(
    ok: bool, *, email_id: str = "", error: str = "",
    retry_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """The ``writeBack`` block on a send response. On failure it carries the
    exact payload the retry endpoint replays — never silent (ET-142)."""
    if ok:
        return {"ok": True, "emailId": email_id}
    return {"ok": False, "error": error, "retryPayload": retry_payload or {}}


async def send_message(
    *,
    settings: Settings,
    api_client: Any,
    store: CommsStore,
    gmail: GmailClient,
    cfg: Any = None,
    parent_id: str = "",
    user: dict[str, Any],
    to: list[str],
    subject: str,
    body_html: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    reply_to_communication_id: Optional[str] = None,
    allow_unknown_recipients: bool = False,
    user_client: Optional[Any] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    ref: Optional[crm.RecordRef] = None,
) -> dict[str, Any]:
    """Send as the signed-in manager's own mailbox; the sent message is
    ingested immediately (write-through) so the tab shows it without waiting
    for the next sync — Message-ID dedup makes the sync's copy a no-op.

    Pass a pre-built ``ref`` (e.g. :func:`contact_ref`) instead of
    ``cfg``/``parent_id`` to scope the send to something other than a parent
    record; the include overrides then key off ``(ref.entity, ref.id)``."""
    to = [a.strip().lower() for a in to if a and a.strip()]
    cc = [a.strip().lower() for a in (cc or []) if a and a.strip()]
    bcc = [a.strip().lower() for a in (bcc or []) if a and a.strip()]
    # An address in To wins over a duplicate in Cc/Bcc (one copy per person).
    cc = [a for a in cc if a not in to]
    bcc = [a for a in bcc if a not in to and a not in cc]
    if not to and cc:
        # Headers need at least one To: promote the Cc list.
        to, cc = cc, []
    if not to:
        raise CommsError("Add at least one recipient.")

    ref = ref or await _record_ref(api_client, cfg, parent_id)
    # CBM-internal recipients are never "unknown" — emailing a co-mentor or
    # staff about the record shouldn't trip the guard (their copy dedups via
    # Message-ID when their own mailbox syncs). Cc/Bcc count: they receive
    # the email just the same.
    everyone = to + cc + bcc
    unknown = [
        a for a in everyone
        if a not in ref.addresses and not a.endswith("@cbmentors.org")
    ]
    if unknown and not allow_unknown_recipients:
        raise CommsError(
            "These recipients aren't contacts on this record: "
            + ", ".join(unknown)
            + ". Confirm sending to them, or add them as contacts first."
        )

    in_reply_to, references, thread_id = "", "", None
    if reply_to_communication_id:
        try:
            prev = await api_client.get(
                crm.COMMUNICATION, reply_to_communication_id,
                select="rfcMessageId,gmailThreadId,sourceMailbox,name",
            )
            in_reply_to = prev.get("rfcMessageId") or ""
            if prev.get("sourceMailbox") == gmail.mailbox:
                thread_id = prev.get("gmailThreadId")
            if not subject:
                base = prev.get("name") or ""
                subject = base if base.lower().startswith("re:") else f"Re: {base}"
        except EspoError as exc:
            log.warning("reply lookup failed: %s", exc)

    from core.email_clean import _text_to_html  # body may arrive as plain text

    if "<" not in body_html:
        body_html = _text_to_html(body_html)
    # Attachment bytes materialize now, at send time — a failure here BLOCKS
    # the send (ET-131); nothing has gone out yet.
    mime_attachments = await resolve_attachments(user_client or api_client, attachments)
    mime = build_mime(
        sender=gmail.mailbox,
        sender_name=user.get("name") or "",
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject or "(no subject)",
        body_text="",
        body_html=body_html,
        in_reply_to=in_reply_to,
        references=references,
        attachments=mime_attachments,
    )
    sent = await gmail.send(mime, thread_id=thread_id)

    # A confirmed send to non-contacts established this conversation manually.
    # Persist the include override BEFORE the best-effort write-through (P1-5
    # F6): the send already happened, and the override is what guarantees the
    # thread ingests later — the sync alone never matches unknown recipients,
    # so an override recorded only after a successful write-through orphaned
    # the thread from the CRM on one Espo blip. The conversation is resolved
    # or created as a shell here; the write-through (and the sync) fill it via
    # the thread map.
    conv_id = None
    ingest_warning = ""
    sent_thread = sent.get("threadId") or thread_id or ""
    if unknown and sent_thread:
        try:
            conv_id = await crm.find_conversation_for_thread(
                api_client, gmail.mailbox, sent_thread
            ) or await store.get_thread_conversation(gmail.mailbox, sent_thread)
            if not conv_id:
                conv_id = await crm.create_conversation(
                    api_client, subject=subject or "(no subject)", sent_at=""
                )
                await store.set_thread_conversation(
                    gmail.mailbox, sent_thread, conv_id
                )
            await store.set_override(
                ref.entity, ref.id, conv_id, ACTION_INCLUDE,
                user.get("userName", ""),
            )
        except Exception as exc:  # noqa: BLE001 — the send is out; keep going
            log.warning("include-override persist failed for sent message: %s", exc)
            ingest_warning = (
                "The message was sent, but attaching its conversation to this "
                "record failed — it may not appear here. Use “Add emails” to "
                "attach the thread."
            )

    # Write-through: ingest the sent message now (best-effort — the next sync
    # cycle picks it up regardless, now that the override is durable).
    sent_rfc_id = ""
    try:
        raw = await gmail.get_message(sent["id"])
        parsed = parse_message(raw)
        sent_rfc_id = parsed.rfc_message_id
        scope = crm.MailboxScope(
            mailbox=gmail.mailbox,
            manager_name=user.get("name") or "",
            owner_user_id=user.get("userId"),
            records=[ref],
        )
        ref.addresses |= set(everyone)
        ingested = await ingest_message(api_client, store, scope, parsed)
        if ingested and unknown and ingested != conv_id:
            # The ingest resolved a different conversation than the pre-created
            # shell (no/mismatched thread id) — the override must follow the
            # conversation the messages actually live in.
            await store.set_override(
                ref.entity, ref.id, ingested, ACTION_INCLUDE,
                user.get("userName", ""),
            )
        conv_id = ingested or conv_id
    except Exception as exc:  # noqa: BLE001
        log.warning("write-through ingest of sent message failed: %s", exc)
        if not ingest_warning:
            ingest_warning = (
                "The message was sent, but it couldn't be shown here yet — "
                "it will appear after the next sync."
            )

    # Native Email write-back (ET-140..143): parent it to the first recipient
    # who is a record contact so it shows in that Contact's History panel.
    # The message is already sent — a failure here is surfaced with a retry
    # payload (ET-142), never silently swallowed.
    write_back: dict[str, Any] = {"ok": True, "emailId": ""}
    if user_client is not None:
        parent_contact_id = next(
            (ref.contact_by_address[a] for a in everyone if a in ref.contact_by_address),
            None,
        )
        wb_payload = {
            "subject": subject or "(no subject)",
            "bodyHtml": body_html,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "parentType": "Contact" if parent_contact_id else None,
            "parentId": parent_contact_id,
            "messageId": sent_rfc_id,
        }
        try:
            email_id = await write_back_email(
                user_client,
                subject=wb_payload["subject"],
                body_html=body_html,
                sender=gmail.mailbox,
                to=to,
                cc=cc,
                bcc=bcc,
                parent_type=wb_payload["parentType"],
                parent_id=wb_payload["parentId"],
                message_id=sent_rfc_id,
            )
            write_back = _write_back_result(True, email_id=email_id)
        except Exception as exc:  # noqa: BLE001 — the message is already out;
            # nothing here may fail the response (ET-142: surface + retry).
            log.warning("Email write-back failed: %s", exc)
            write_back = _write_back_result(
                False,
                error="The message WAS sent, but recording it in the CRM failed.",
                retry_payload=wb_payload,
            )
    return {
        "gmailMessageId": sent.get("id"),
        "conversationId": conv_id,
        "writeBack": write_back,
        # Non-empty = the send succeeded but the tab may not show the message
        # yet (write-through/override failure) — shown as a notice, not silence.
        "ingestWarning": ingest_warning,
    }


async def send_quick_message(
    *, gmail: GmailClient, to: list[str], subject: str, body_html: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    sender_name: str = "",
    user_client: Optional[Any] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    thread_id: Optional[str] = None,
    in_reply_to: str = "",
    references: str = "",
) -> dict[str, Any]:
    """A record-less "quick email" — behind the email-address links shown in
    the staff tools outside a record context (Client/Mentor Administration).

    Sends as the signed-in user's own mailbox: no record link, no
    unknown-recipient guard (the user clicked a specific address). The regular
    sync ingests the sent copy when it matches a record the sender manages;
    with ``user_client`` the send is ALSO written back as a native EspoCRM
    Email, parented to the recipient's Contact when one matches (ET-140..143).
    """
    to = [a.strip().lower() for a in to if a and a.strip()]
    cc = [a.strip().lower() for a in (cc or []) if a and a.strip()]
    bcc = [a.strip().lower() for a in (bcc or []) if a and a.strip()]
    cc = [a for a in cc if a not in to]
    bcc = [a for a in bcc if a not in to and a not in cc]
    if not to and cc:
        to, cc = cc, []
    if not to:
        raise CommsError("Add at least one recipient.")

    from core.email_clean import _text_to_html  # body may arrive as plain text

    if "<" not in body_html:
        body_html = _text_to_html(body_html)
    mime_attachments = await resolve_attachments(user_client, attachments) \
        if user_client is not None else []
    mime = build_mime(
        sender=gmail.mailbox,
        sender_name=sender_name,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject or "(no subject)",
        body_text="",
        body_html=body_html,
        attachments=mime_attachments,
        in_reply_to=in_reply_to,
        references=references,
    )
    sent = await gmail.send(mime, thread_id=thread_id)

    write_back: dict[str, Any] = {"ok": True, "emailId": ""}
    if user_client is not None:
        parent_contact_id = None
        for addr in to + cc + bcc:
            try:
                hit = await lookup_contact_by_email(user_client, addr)
            except Exception:  # noqa: BLE001 — parenting is best-effort
                hit = {"found": False}
            if hit.get("found") and hit.get("contact"):
                parent_contact_id = hit["contact"].get("id")
                break
        wb_payload = {
            "subject": subject or "(no subject)",
            "bodyHtml": body_html,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "parentType": "Contact" if parent_contact_id else None,
            "parentId": parent_contact_id,
            "messageId": "",
        }
        try:
            email_id = await write_back_email(
                user_client,
                subject=wb_payload["subject"],
                body_html=body_html,
                sender=gmail.mailbox,
                to=to,
                cc=cc,
                bcc=bcc,
                parent_type=wb_payload["parentType"],
                parent_id=wb_payload["parentId"],
            )
            write_back = _write_back_result(True, email_id=email_id)
        except Exception as exc:  # noqa: BLE001 — the message is already out;
            # nothing here may fail the response (ET-142: surface + retry).
            log.warning("quick-send Email write-back failed: %s", exc)
            write_back = _write_back_result(
                False,
                error="The message WAS sent, but recording it in the CRM failed.",
                retry_payload=wb_payload,
            )
    return {
        "gmailMessageId": sent.get("id"),
        # The Gmail thread the sent message landed on — /ops anchors it to the
        # submission so the conversation view can show exactly this thread.
        "gmailThreadId": sent.get("threadId"),
        "writeBack": write_back,
    }


# --- compose-dialog lookups -----------------------------------------------------


async def lookup_contact_by_email(user_client: Any, address: str) -> dict[str, Any]:
    """CRM-wide lookup of an email address, for the compose dialog's router.

    Returns ``{"found": False}`` or ``{"found": True, "contact": {...}}`` with
    ``isCbmMember`` set when the contact is CBM-side (a Mentor-typed contact or
    a @cbmentors.org address) — those aren't client contacts, so the dialog
    offers only a plain send for them.
    """
    address = (address or "").strip().lower()
    if "@" not in address:
        return {"found": False}

    # A CBM member can be reached two ways: their work address lives on their
    # MENTOR PROFILE (cbmEmail, usually not on their Contact record), or a
    # personal address on their Mentor-typed Contact. Either way the dialog
    # must get the mentorProfileId so "add" means co-mentor — never a client
    # contact link. Profiles are scanned in Python (small set; never a where
    # on restricted attributes).
    async def _profiles() -> list[dict[str, Any]]:
        data = await user_client.list(
            crm.MENTOR_PROFILE, select="name,cbmEmail,contactRecordId", max_size=200
        )
        return data.get("list", [])

    profile_hit = None
    profiles_cache: Optional[list[dict[str, Any]]] = None
    if address.endswith("@cbmentors.org"):
        profiles_cache = await _profiles()
        for pr in profiles_cache:
            if (pr.get("cbmEmail") or "").strip().lower() == address:
                profile_hit = pr
                break

    data = await user_client.list(
        "Contact",
        where=[{"type": "equals", "attribute": "emailAddress", "value": address}],
        select="name,accountName,cContactType,emailAddress",
        max_size=1,
    )
    rows = data.get("list", [])

    if not rows and not profile_hit:
        return {"found": False}

    if profile_hit:
        return {
            "found": True,
            "contact": {
                "id": profile_hit.get("contactRecordId"),
                "name": profile_hit.get("name"),
                "company": "Cleveland Business Mentors",
                "types": ["Mentor"],
                "isCbmMember": True,
                "mentorProfileId": profile_hit["id"],
            },
        }

    c = rows[0]
    types = c.get("cContactType") or []
    if isinstance(types, str):
        types = [types]
    is_cbm = "Mentor" in types or address.endswith("@cbmentors.org")
    mentor_profile_id = None
    if is_cbm:
        # Personal-address path: find their profile through its Contact link
        # (this was the "added as Other Contacts" bug — without the profile id
        # the frontend fell back to a client-contact link).
        if profiles_cache is None:
            profiles_cache = await _profiles()
        for pr in profiles_cache:
            if pr.get("contactRecordId") == c["id"]:
                mentor_profile_id = pr["id"]
                break
    return {
        "found": True,
        "contact": {
            "id": c["id"],
            "name": c.get("name"),
            "company": c.get("accountName"),
            "types": types,
            "isCbmMember": is_cbm,
            "mentorProfileId": mentor_profile_id,
        },
    }


async def search_companies(user_client: Any, query: str = "") -> list[dict[str, Any]]:
    """Accounts for the compose dialog's company picker (empty query = first
    page, alphabetical — CBM-scale)."""
    where = None
    q = (query or "").strip()
    if q:
        where = [{"type": "contains", "attribute": "name", "value": q}]
    data = await user_client.list(
        "Account", where=where, select="name", max_size=50, order_by="name"
    )
    return [{"id": a["id"], "name": a.get("name")} for a in data.get("list", [])]


async def resolve_company(
    user_client: Any, api_client: Any, name: str
) -> Optional[str]:
    """An Account id for ``name`` — reuse an existing same-named Account
    (case-insensitive read as the user), else create it via the intake API
    client (gate roles don't hold Account create; the API user does — its
    original job). Mirrors the intake orchestrators' find-or-create policy."""
    name = (name or "").strip()
    if not name:
        return None
    data = await user_client.list(
        "Account",
        where=[{"type": "equals", "attribute": "name", "value": name}],
        select="name", max_size=1,
    )
    rows = data.get("list", [])
    if rows:
        return rows[0]["id"]
    created = await api_client.create("Account", {"name": name})
    return created["id"]


# --- contact address fix ---------------------------------------------------------


async def add_contact_address(user_client: Any, contact_id: str, address: str) -> None:
    """Add a secondary email address to a Contact (as the user) — the durable
    fix that makes future mail from that address auto-match everywhere."""
    address = (address or "").strip().lower()
    if "@" not in address:
        raise CommsError("That doesn't look like an email address.")
    contact = await user_client.get(
        "Contact", contact_id, select="emailAddress,emailAddressData"
    )
    data = list(contact.get("emailAddressData") or [])
    if not data and contact.get("emailAddress"):
        data = [{"emailAddress": contact["emailAddress"], "primary": True}]
    if any((e.get("emailAddress") or "").lower() == address for e in data):
        return  # already there
    data.append({"emailAddress": address, "primary": False, "optOut": False, "invalid": False})
    await user_client.update("Contact", contact_id, {"emailAddressData": data})
