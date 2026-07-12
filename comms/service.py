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


# --- reads (as the user) -------------------------------------------------------

_CONV_SELECT = (
    "name,conversationStatus,summary,actionItems,keyTopics,"
    "firstMessageAt,lastMessageAt,messageCount,participants"
)


async def list_conversations(
    user_client: Any, parent_entity: str, parent_id: str
) -> list[dict[str, Any]]:
    data = await user_client.list_related(
        parent_entity, parent_id, PARENT_CONVERSATIONS_LINK,
        select=_CONV_SELECT, max_size=_PAGE,
    )
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


_MSG_SELECT = (
    "name,direction,sentAt,fromAddress,fromName,toAddresses,ccAddresses,"
    "snippet,bodyCleaned,gmailThreadId,gmailMessageId,sourceMailbox,rfcMessageId"
)


async def get_conversation(user_client: Any, conversation_id: str) -> dict[str, Any]:
    conv = await user_client.get(crm.CONVERSATION, conversation_id, select=_CONV_SELECT)
    msgs = await user_client.list(
        crm.COMMUNICATION,
        where=[{"type": "equals", "attribute": crm.CONVERSATION_FK, "value": conversation_id}],
        select=_MSG_SELECT,
        max_size=_PAGE,
        order_by="sentAt",
    )
    return {
        "id": conversation_id,
        "subject": conv.get("name"),
        "status": conv.get("conversationStatus"),
        "summary": conv.get("summary"),
        "actionItems": [a for a in (conv.get("actionItems") or "").split("\n") if a.strip()],
        "keyTopics": [t.strip() for t in (conv.get("keyTopics") or "").split(",") if t.strip()],
        "messages": [
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
            }
            for m in msgs.get("list", [])
        ],
    }


# --- curation ---------------------------------------------------------------


async def exclude_conversation(
    api_client: Any,
    store: CommsStore,
    parent_entity: str,
    parent_id: str,
    conversation_id: str,
    username: str,
) -> None:
    """Hide a conversation from this record (record-level, shared): unlink in
    the CRM + persist the exclusion so the sync never re-links it."""
    await store.set_override(
        parent_entity, parent_id, conversation_id, ACTION_EXCLUDE, username
    )
    link = crm.PARENT_LINKS.get(parent_entity)
    if link:
        try:
            await api_client.unrelate(crm.CONVERSATION, conversation_id, link, parent_id)
        except EspoError as exc:
            log.warning("unlink %s from %s/%s failed: %s", conversation_id, parent_entity, parent_id, exc)


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
        ref.addresses |= crm._contact_addresses(c)
    return ref


async def include_thread(
    *,
    settings: Settings,
    api_client: Any,
    store: CommsStore,
    gmail: GmailClient,
    cfg: Any,
    parent_id: str,
    gmail_thread_id: str,
    user: dict[str, Any],
) -> Optional[str]:
    """Attach a mailbox thread to this record: ingest its messages (targeted —
    the record's contacts are force-matched) + persist the inclusion."""
    ref = await _record_ref(api_client, cfg, parent_id)
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
        result = await ingest_message(api_client, store, scope, parsed)
        conv_id = result or conv_id
    if conv_id:
        await store.set_override(
            cfg.parent_entity, parent_id, conv_id, ACTION_INCLUDE, user.get("userName", "")
        )
    return conv_id


# --- send ---------------------------------------------------------------------


async def send_message(
    *,
    settings: Settings,
    api_client: Any,
    store: CommsStore,
    gmail: GmailClient,
    cfg: Any,
    parent_id: str,
    user: dict[str, Any],
    to: list[str],
    subject: str,
    body_html: str,
    reply_to_communication_id: Optional[str] = None,
    allow_unknown_recipients: bool = False,
) -> dict[str, Any]:
    """Send as the signed-in manager's own mailbox; the sent message is
    ingested immediately (write-through) so the tab shows it without waiting
    for the next sync — Message-ID dedup makes the sync's copy a no-op."""
    to = [a.strip().lower() for a in to if a and a.strip()]
    if not to:
        raise CommsError("Add at least one recipient.")

    ref = await _record_ref(api_client, cfg, parent_id)
    # CBM-internal recipients are never "unknown" — emailing a co-mentor or
    # staff about the record shouldn't trip the guard (their copy dedups via
    # Message-ID when their own mailbox syncs).
    unknown = [
        a for a in to
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
    mime = build_mime(
        sender=gmail.mailbox,
        to=to,
        subject=subject or "(no subject)",
        body_text="",
        body_html=body_html,
        in_reply_to=in_reply_to,
        references=references,
    )
    sent = await gmail.send(mime, thread_id=thread_id)

    # Write-through: ingest the sent message now (best-effort — the next sync
    # cycle picks it up regardless).
    conv_id = None
    try:
        raw = await gmail.get_message(sent["id"])
        scope = crm.MailboxScope(
            mailbox=gmail.mailbox,
            manager_name=user.get("name") or "",
            owner_user_id=user.get("userId"),
            records=[ref],
        )
        ref.addresses |= set(to)
        conv_id = await ingest_message(api_client, store, scope, parse_message(raw))
    except Exception as exc:  # noqa: BLE001
        log.warning("write-through ingest of sent message failed: %s", exc)

    # A confirmed send to non-contacts established this conversation manually —
    # persist the attachment (same include override "Add emails…" writes) so a
    # resync can never drop it, and thread-following keeps its replies coming.
    if conv_id and unknown:
        await store.set_override(
            cfg.parent_entity, parent_id, conv_id, ACTION_INCLUDE,
            user.get("userName", ""),
        )
    return {"gmailMessageId": sent.get("id"), "conversationId": conv_id}


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
