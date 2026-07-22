"""Inbound email attachments auto-filed to the record Documents tab.

Email-quality plan §3.1 (Doug's rulings 2026-07-21): REAL attachments only
(Content-Disposition: attachment — inline/signature images stay viewable via
View original), filed into every record the conversation links to, deduped
per record by SHA-256 so a five-reply thread re-attaching the same PDF stores
it once. Drive writes run under the SERVICE identity (the worker has no user
session); ``uploaded_by`` records the source mailbox's owner.

Best-effort by contract: a Drive/DB failure never fails message ingest — the
ledger row is marked ``failed`` and re-attempted on later sync passes until
filed (idempotent per (rfc id, part, record)) or it exhausts
``ATTACHMENT_MAX_ATTEMPTS`` (a WARN marks the give-up; the bytes remain one
click away in View original).

Gates: ``GMAIL_SYNC`` + ``GDRIVE_DOCS`` + ``DATABASE_URL`` + the shared drive
id + ``GDRIVE_IDENTITY=service`` (without service mode the SA is not a drive
member, so worker-side uploads could never succeed).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoError
from core.gdrive import DriveClient
from core.gmail import GmailClient, GmailError, MessageGoneError, ParsedGmailMessage

from . import crm
from .store import (
    ATTACHMENT_DUPLICATE,
    ATTACHMENT_FAILED,
    ATTACHMENT_FILED,
    ATTACHMENT_MAX_ATTEMPTS,
    ATTACHMENT_TOO_LARGE,
)

log = logging.getLogger("cbm_intake.comms.attachments")


def attachments_enabled(settings: Settings) -> bool:
    return bool(
        settings.gmail_sync
        and settings.gdrive_docs
        and settings.database_url
        and settings.gdrive_shared_drive_id
        and settings.gdrive_identity == "service"
    )


async def _service_drive(settings: Settings, attribution: str) -> Optional[DriveClient]:
    """A Drive client acting as the service account itself; ``attribution``
    (the source mailbox owner) feeds logs + the app-level ``uploaded_by``."""
    from .service import get_service_account

    sa_info = await get_service_account(settings)
    if sa_info is None:
        return None
    return DriveClient(
        sa_info,
        attribution,
        settings.gdrive_shared_drive_id,
        timeout=max(settings.request_timeout_seconds, 60),
        impersonate=False,
    )


async def _engagement_client(espo: Any, record_id: str) -> tuple[Optional[str], str]:
    """(client account id, name) for an engagement anchor — D-07 folder
    nesting, resolved exactly like the upload endpoint (company link with the
    client-profile fallback). Best-effort: unresolvable => no nesting."""
    try:
        from sessions.config import DOMAINS
        from sessions.service import fill_company_fallback

        cfg = next(
            c for c in DOMAINS.values() if c.parent_entity == "CEngagement"
        )
        if not cfg.company_fallback:
            return None, ""
        own_id, own_name, via_id = cfg.company_fallback[:3]
        rec = await espo.get(
            "CEngagement", record_id, select=f"name,{own_id},{own_name},{via_id}"
        )
        await fill_company_fallback(cfg, espo, [rec])
        return rec.get(own_id) or None, rec.get(own_name) or ""
    except Exception as exc:  # noqa: BLE001 — nesting is a browsing nicety only
        log.debug("client resolution failed for engagement %s: %s", record_id, exc)
        return None, ""


async def conversation_parent_records(
    espo: Any, conversation_id: str
) -> list[tuple[str, str, str]]:
    """The (entity, id, name) records a conversation links to — the filing
    targets for a thread-following message with no direct address match."""
    out: list[tuple[str, str, str]] = []
    for entity, link in crm.PARENT_LINKS.items():
        try:
            data = await espo.list_related(
                crm.CONVERSATION, conversation_id, link, select="name", max_size=20
            )
        except EspoError as exc:
            log.warning(
                "attachment targets: %s link read failed for %s: %s",
                entity, conversation_id, exc,
            )
            continue
        for r in data.get("list", []) or []:
            out.append((entity, r["id"], r.get("name") or ""))
    return out


async def _file_one(
    settings: Settings,
    espo: Any,
    store: Any,
    doc_store: Any,
    drive: DriveClient,
    *,
    att: Any,
    data: Optional[bytes],
    sha256: str,
    entity: str,
    record_id: str,
    record_name: str,
    rfc_id: str,
    gmail_id: str,
    mailbox: str,
    attempts: int,
) -> None:
    """File one attachment onto one record and write its ledger row."""
    base = {
        "rfc_message_id": rfc_id,
        "part_index": att.part_index,
        "entity_type": entity,
        "record_id": record_id,
        "filename": att.filename or "attachment",
        "mime_type": att.mime_type,
        "size": att.size or (len(data) if data else 0),
        "sha256": sha256 or None,
        "gmail_message_id": gmail_id,
        "source_mailbox": mailbox,
        "attempts": attempts,
        "last_error": None,
    }
    max_bytes = settings.gdrive_max_file_mb * 1024 * 1024
    if (att.size or 0) > max_bytes or (data is not None and len(data) > max_bytes):
        await store.upsert_attachment({**base, "status": ATTACHMENT_TOO_LARGE})
        return
    if data is None:
        raise GmailError("attachment bytes unavailable")
    existing = await doc_store.find_by_sha256(entity, record_id, sha256)
    if existing:
        await store.upsert_attachment(
            {**base, "status": ATTACHMENT_DUPLICATE, "document_id": existing["id"]}
        )
        return
    from docs import service as docs_service

    client_id, client_name = (None, "")
    if entity == "CEngagement":
        client_id, client_name = await _engagement_client(espo, record_id)
    row = await docs_service.upload_document(
        settings, doc_store, drive,
        entity_type=entity,
        record_id=record_id,
        record_name=record_name,
        filename=att.filename or "attachment",
        mime_type=att.mime_type,
        doc_type=docs_service.EMAIL_ATTACHMENT_DOC_TYPE,
        data=data,
        client_id=client_id,
        client_name=client_name,
        content_sha256=sha256,
        uploaded_by=mailbox,
    )
    await store.upsert_attachment(
        {**base, "status": ATTACHMENT_FILED, "document_id": row.get("id")}
    )
    # DOC-08/DOC-09 hooks (folder link write-back + grants) — best-effort.
    try:
        await docs_service.post_upload_hooks(settings, drive, entity, record_id, row)
    except Exception as exc:  # noqa: BLE001
        log.warning("post-upload hooks failed (%s %s): %s", entity, record_id, exc)
    log.info(
        "email attachment filed: %r (%s bytes) -> %s %s (doc %s, from %s)",
        att.filename, base["size"], entity, record_id, row.get("id"), mailbox,
    )


async def file_message_attachments(
    settings: Settings,
    espo: Any,
    store: Any,
    gmail: GmailClient,
    parsed: ParsedGmailMessage,
    records: list[tuple[str, str, str]],
) -> None:
    """File ``parsed``'s real attachments onto every target record.

    Idempotent: rows already ``filed``/``duplicate``/``too_large`` are
    skipped; ``failed`` rows are re-attempted (attempts incremented). Raises
    nothing — per-attachment failures are recorded on their ledger rows.
    """
    atts = parsed.real_attachments
    if not atts or not records:
        return
    from docs import service as docs_service

    doc_store = docs_service.get_store(settings)
    if doc_store is None:
        return
    drive = await _service_drive(settings, gmail.mailbox)
    if drive is None:
        return
    rfc_id = (parsed.rfc_message_id or "")[:100]
    bytes_cache: dict[int, tuple[bytes, str]] = {}  # part_index -> (data, sha)

    async def _bytes(att: Any) -> tuple[bytes, str]:
        cached = bytes_cache.get(att.part_index)
        if cached is None:
            data = await gmail.get_attachment(parsed.gmail_id, att.attachment_id)
            cached = (data, hashlib.sha256(data).hexdigest())
            bytes_cache[att.part_index] = cached
        return cached

    for entity, record_id, record_name in records:
        for att in atts:
            state = await store.attachment_state(
                rfc_id, att.part_index, entity, record_id
            )
            if state and state["status"] != ATTACHMENT_FAILED:
                continue
            attempts = (state or {}).get("attempts", 0) + 1
            try:
                data, sha = (None, "")
                max_bytes = settings.gdrive_max_file_mb * 1024 * 1024
                if (att.size or 0) <= max_bytes:
                    data, sha = await _bytes(att)
                await _file_one(
                    settings, espo, store, doc_store, drive,
                    att=att, data=data, sha256=sha,
                    entity=entity, record_id=record_id, record_name=record_name,
                    rfc_id=rfc_id, gmail_id=parsed.gmail_id,
                    mailbox=gmail.mailbox, attempts=attempts,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort by contract
                level = log.error if attempts >= ATTACHMENT_MAX_ATTEMPTS else log.warning
                level(
                    "email attachment filing failed (%r -> %s %s, attempt %d): %s",
                    att.filename, entity, record_id, attempts, exc,
                )
                try:
                    await store.upsert_attachment({
                        "rfc_message_id": rfc_id,
                        "part_index": att.part_index,
                        "entity_type": entity,
                        "record_id": record_id,
                        "filename": att.filename or "attachment",
                        "mime_type": att.mime_type,
                        "size": att.size or 0,
                        "sha256": None,
                        "gmail_message_id": parsed.gmail_id,
                        "source_mailbox": gmail.mailbox,
                        "status": ATTACHMENT_FAILED,
                        "attempts": attempts,
                        "last_error": str(exc)[:500],
                    })
                except Exception:  # noqa: BLE001
                    log.exception("attachment ledger write failed")


async def file_for_ingest(
    settings: Settings,
    espo: Any,
    store: Any,
    gmail: Optional[GmailClient],
    scope: Any,
    parsed: ParsedGmailMessage,
    conversation_id: str,
    matched: list[Any],
    excludes: set[tuple[str, str, str]],
) -> None:
    """The ingest hook (called from comms.sync): inbound messages only, gated,
    never raises. ``matched`` = the scope's matched RecordRefs; a
    thread-following message (no match) files to the conversation's linked
    records instead."""
    try:
        if gmail is None or not attachments_enabled(settings):
            return
        if parsed.from_address == scope.mailbox:
            return  # outbound — the plan auto-files INBOUND attachments only
        if not parsed.real_attachments:
            return
        if matched:
            records = [(r.entity, r.id, r.name) for r in matched]
        else:
            records = await conversation_parent_records(espo, conversation_id)
        records = [
            (e, i, n)
            for e, i, n in records
            if (e, i, conversation_id) not in excludes
        ]
        await file_message_attachments(settings, espo, store, gmail, parsed, records)
    except Exception as exc:  # noqa: BLE001 — filing never fails ingest
        log.warning("attachment filing hook failed for %s: %s", parsed.rfc_message_id, exc)


async def retry_failed_attachments(
    settings: Settings,
    espo: Any,
    store: Any,
    service_account_info: dict[str, Any],
    limit: int = 25,
) -> int:
    """Re-attempt failed ledger rows (the sync pass's retry sweep). Refetches
    each message from its source mailbox and re-runs the filing for exactly
    the failed row's record. Returns how many rows were attempted."""
    if not attachments_enabled(settings):
        return 0
    try:
        rows = await store.failed_attachments(limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("failed-attachment sweep read failed: %s", exc)
        return 0
    if not rows:
        return 0
    clients: dict[str, GmailClient] = {}
    attempted = 0
    try:
        for row in rows:
            mailbox = row.get("sourceMailbox") or ""
            gmail_id = row.get("gmailMessageId") or ""
            if not mailbox or not gmail_id:
                continue
            gmail = clients.get(mailbox)
            if gmail is None:
                gmail = GmailClient(
                    service_account_info, mailbox, settings.request_timeout_seconds
                )
                clients[mailbox] = gmail
            attempted += 1
            try:
                parsed_raw = await gmail.get_message(gmail_id)
            except MessageGoneError:
                # Nothing left to fetch — burn the remaining attempts so the
                # row stops occupying the sweep.
                await store.upsert_attachment({
                    "rfc_message_id": row["rfcMessageId"],
                    "part_index": row["partIndex"],
                    "entity_type": row["entityType"],
                    "record_id": row["recordId"],
                    "status": ATTACHMENT_FAILED,
                    "attempts": ATTACHMENT_MAX_ATTEMPTS,
                    "last_error": "the message no longer exists in the source mailbox",
                })
                continue
            except (GmailError, Exception) as exc:  # noqa: BLE001
                log.warning("attachment retry fetch failed (%s/%s): %s", mailbox, gmail_id, exc)
                continue
            from core.gmail import parse_message

            parsed = parse_message(parsed_raw)
            try:
                name = ""
                rec = await espo.get(row["entityType"], row["recordId"], select="name")
                name = rec.get("name") or ""
            except EspoError as exc:
                log.warning("attachment retry record read failed: %s", exc)
            await file_message_attachments(
                settings, espo, store, gmail, parsed,
                [(row["entityType"], row["recordId"], name)],
            )
    finally:
        for gmail in clients.values():
            try:
                await gmail.aclose()
            except Exception:  # noqa: BLE001
                pass
    return attempted
