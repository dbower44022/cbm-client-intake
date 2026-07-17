"""Document-management operations behind the sessions Documents tab (Phase 1).

CRM reads (the parent record's name + the ACL check that the signed-in user
may see it) run **as the user**, like every other sessions read. Drive
operations impersonate ONLY the signed-in user's own CBM mailbox, resolved
from their CRM identity — never from request input (the comms subject rule).

The rollback contract (PRD DOC-01): a Drive file with no metadata row is
deleted; a metadata row is never written without a confirmed Drive file.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.gdrive import (
    GOOGLE_NATIVE_MIMES,
    OFFICE_CONVERT_MIMES,
    PDF_MIME,
    DriveClient,
    DriveError,
)

from .store import DocumentStore, make_document_store

log = logging.getLogger("cbm_intake.docs.service")


class DocsError(Exception):
    """A user-visible failure (message is safe to show)."""


class DocsNotFound(DocsError):
    """The requested document isn't on this record (routes map it to a 404)."""


# --- lazy singleton (comms pattern) -------------------------------------------

_store: Optional[DocumentStore] = None


def get_store(settings: Settings) -> Optional[DocumentStore]:
    global _store
    if _store is None:
        _store = make_document_store(settings)
    return _store


# --- Drive client for the signed-in user ---------------------------------------


async def drive_for_user(
    settings: Settings, user_client: Any, user: dict[str, Any]
) -> DriveClient:
    """A Drive client acting for the signed-in user, per ``GDRIVE_IDENTITY``.

    ``"user"`` (the PRD D-01 original): impersonate their own CBM account —
    the subject comes from their linked ``CMentorProfile.cbmEmail`` (resolved
    through their own token, so it's their profile by ACL + assignment), and
    that person must be a shared-drive member.

    ``"service"`` (Doug's ruling 2026-07-16 — users are NOT drive members):
    the service account acts as ITSELF (the SA is the drive member); the
    user's cbmEmail (or username) rides along as attribution only, feeding
    logs + the app-level ``uploaded_by``. No CBM mailbox is required to
    operate in this mode.
    """
    from comms.service import get_service_account
    from sessions.service import resolve_user_mailbox

    service_mode = settings.gdrive_identity == "service"
    mailbox = await resolve_user_mailbox(user_client, user["userId"])
    if not mailbox:
        if not service_mode:
            raise DocsError(
                "Your profile has no CBM email address, so documents can't be "
                "uploaded as you — ask CBM staff to set it."
            )
        # attribution-only in service mode — never blocks
        mailbox = user.get("userName") or "unknown"
    if not settings.gdrive_shared_drive_id:
        raise DocsError("The document storage drive isn't configured.")
    sa_info = await get_service_account(settings)
    if sa_info is None:
        raise DocsError("The document integration isn't configured.")
    return DriveClient(
        sa_info,
        mailbox,
        settings.gdrive_shared_drive_id,
        timeout=max(settings.request_timeout_seconds, 60),
        impersonate=not service_mode,
    )


# --- folder scheme (PRD §3.2) ---------------------------------------------------

_FOLDER_UNSAFE = re.compile(r"[\\/\x00-\x1f]+")


def sanitize_folder_name(name: str) -> str:
    """A Drive-safe folder component: control chars + path separators collapse
    to spaces. Folders are for human browsing only (D-06) — the app never
    resolves files by path, so lossy sanitizing is fine."""
    cleaned = _FOLDER_UNSAFE.sub(" ", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "(unnamed)"


def record_folder_name(record_name: str, record_id: str) -> str:
    """``{words} ({recordId})`` — human-readable-first identifier (§3.2 rule 3).
    Humans may rename the words freely; the app locates folders by id only."""
    return f"{sanitize_folder_name(record_name)} ({record_id})"


def folder_label(settings: Settings, entity_type: str) -> str:
    """The top-level display label for an anchor entity type (§3.2 rule 3):
    Contact -> Mentors, CEngagement -> Clients, … Unmapped types fall back to
    the raw entity name."""
    return settings.gdrive_entity_labels_map.get(entity_type, entity_type)


async def _ensure_path(drive: DriveClient, segments: list[str]) -> str:
    """Walk ``segments`` from the shared-drive root, find-or-creating each
    folder level; returns the last segment's folder id."""
    parent = drive.drive_id  # a shared drive's root folder id IS the drive id
    for name in segments:
        folder = await drive.find_child_folder(parent, name)
        if not folder:
            folder = await drive.create_folder(parent, name)
        parent = folder
    return parent


async def ensure_record_folder(
    settings: Settings,
    drive: DriveClient,
    store: DocumentStore,
    entity_type: str,
    record_id: str,
    record_name: str,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
) -> str:
    """The anchor record's own folder id, creating all levels on first upload
    (PRD v1.2 §3.2): ``{Label}/{Record Name} ({recordId})/`` — and for
    engagement anchors with a resolved client,
    ``Clients/{Client Name} (clientId)/{Engagement Name} (engagementId)/``
    (D-07: engagement folders nest inside their client's folder). The folder id
    cached on prior metadata rows is used when available (no Drive lookups).
    An engagement whose client can't be resolved sits directly under the label
    (browsing nicety only — the app never resolves by path)."""
    cached = await store.cached_folder_id(entity_type, record_id)
    if cached:
        return cached
    segments = [folder_label(settings, entity_type)]
    if client_id:
        segments.append(record_folder_name(client_name or "", client_id))
    segments.append(record_folder_name(record_name, record_id))
    return await _ensure_path(drive, segments)


# --- upload + list ---------------------------------------------------------------


def _parse_drive_time(value: Optional[str]) -> Optional[datetime]:
    """Drive RFC3339 (``2026-07-16T12:34:56.789Z``) -> aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _validate_upload(
    settings: Settings, *, filename: str, doc_type: str, data: bytes
) -> str:
    filename = (filename or "").strip()
    if not filename:
        raise DocsError("The upload needs a file name.")
    if not data:
        raise DocsError("The uploaded file is empty.")
    max_bytes = settings.gdrive_max_file_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise DocsError(
            f"The file is too large — the limit is {settings.gdrive_max_file_mb} MB."
        )
    if doc_type not in settings.gdrive_doc_types_list:
        raise DocsError("Please choose a document type from the list.")
    return filename


async def upload_document(
    settings: Settings,
    store: DocumentStore,
    drive: DriveClient,
    *,
    entity_type: str,
    record_id: str,
    record_name: str,
    filename: str,
    mime_type: str,
    doc_type: str,
    data: bytes,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
) -> dict[str, Any]:
    """DOC-01: upload to the anchor record's folder (all levels created as
    needed), then write the metadata row — including ``client_record_id`` for
    engagement-anchored documents (D-07). Rollback: a row-write failure deletes
    the Drive file; a Drive failure writes no row."""
    filename = _validate_upload(
        settings, filename=filename, doc_type=doc_type, data=data
    )
    mime_type = (mime_type or "").strip() or "application/octet-stream"
    folder_id = await ensure_record_folder(
        settings, drive, store, entity_type, record_id, record_name,
        client_id=client_id, client_name=client_name,
    )
    file = await drive.upload_file(folder_id, filename, mime_type, data)
    row = {
        "drive_file_id": file["id"],
        "drive_folder_id": folder_id,
        "entity_type": entity_type,
        "record_id": record_id,
        "client_record_id": client_id,
        "record_name": record_name,
        "original_filename": filename,
        "mime_type": mime_type,
        "doc_type": doc_type,
        "web_view_link": file.get("webViewLink"),
        "uploaded_by": drive.mailbox,
        "modified_time": _parse_drive_time(file.get("modifiedTime")),
        "checksum_md5": file.get("md5Checksum"),
    }
    try:
        await store.insert_document(row)
    except Exception as exc:
        log.warning(
            "document metadata write failed (%s %s, file %s): %s — rolling back",
            entity_type, record_id, file["id"], exc,
        )
        try:
            await drive.delete_file(file["id"])
        except DriveError as del_exc:  # orphan left in Drive — log loudly
            log.error(
                "ROLLBACK FAILED: Drive file %s has no metadata row and could "
                "not be deleted: %s", file["id"], del_exc,
            )
        raise DocsError(
            "The upload could not be recorded, so it was rolled back — "
            "please try again."
        ) from exc
    rows = await store.list_documents(entity_type, record_id)
    for r in rows:
        if r["driveFileId"] == file["id"]:
            return r
    # The row was written; worst case return a minimal shape.
    return {"driveFileId": file["id"], "filename": filename, "docType": doc_type}


async def list_documents(
    store: DocumentStore, entity_type: str, record_id: str
) -> list[dict[str, Any]]:
    """DOC-02 (partial): active documents, newest first, from metadata only."""
    return await store.list_documents(entity_type, record_id)


# --- viewing (Phase 2) -------------------------------------------------------------


def content_headers(filename: str) -> dict[str, str]:
    """Response headers for the view proxy (DOC-06 — the browser IS the cache):
    the frontend versions the URL by the row's modifiedTime, so the bytes at
    any one URL are immutable — each browser holds them privately, cache hits
    are instant with zero network, and a Drive edit (new modifiedTime → new
    URL after the lazy refresh) invalidates automatically. No server-side
    cache state exists (App Platform's disk is ephemeral anyway)."""
    ascii_name = (
        filename.encode("ascii", "replace").decode().replace('"', "'") or "document"
    )
    quoted = urllib.parse.quote(filename)
    return {
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
        ),
    }


def is_google_native(mime_type: Optional[str]) -> bool:
    """Google-native editor formats (Docs/Sheets/Slides) have no native bytes —
    in-app viewing goes through ``files.export`` to PDF (DOC-04)."""
    return (mime_type or "") in GOOGLE_NATIVE_MIMES


def _pdf_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem or 'document'}.pdf"


async def fetch_document(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
) -> dict[str, Any]:
    """The document's viewable bytes, fetched from Drive as the signed-in user
    (DOC-03). Binary files come back with their native MIME type; Google-native
    formats are exported to PDF (DOC-04). Returns
    ``{data, mime_type, filename, modified_time}`` — the caller serves it with
    cache headers keyed on the row's modifiedTime (DOC-06, browser HTTP cache)."""
    row = await store.get_document(entity_type, record_id, doc_id)
    if row is None:
        raise DocsNotFound("That document isn't on this record.")
    file_id = row["driveFileId"]
    stored_mime = row.get("mimeType") or ""
    if is_google_native(stored_mime):
        data = await drive.export_pdf(file_id)
        mime, filename = PDF_MIME, _pdf_filename(row.get("filename") or "")
    elif stored_mime in OFFICE_CONVERT_MIMES:
        # Office formats view via read-time conversion (copy-as-Google-format
        # → export PDF → delete the temp); the stored file is untouched.
        data = await drive.export_office_pdf(
            file_id, OFFICE_CONVERT_MIMES[stored_mime]
        )
        mime, filename = PDF_MIME, _pdf_filename(row.get("filename") or "")
    else:
        data = await drive.download_file(file_id)
        mime = stored_mime or "application/octet-stream"
        filename = row.get("filename") or "document"
    return {
        "data": data,
        "mime_type": mime,
        "filename": filename,
        "modified_time": row.get("modifiedTime"),
    }


async def refresh_documents(
    store: DocumentStore, drive: DriveClient, entity_type: str, record_id: str
) -> list[dict[str, Any]]:
    """DOC-02 completion — the lazy modifiedTime refresh on record open: ONE
    ``files.list`` scoped to the record folder updates each row's
    ``modified_time`` (+ checksum/view link), and rows whose file changed in
    Drive since last sync are flagged ``changedInDrive`` (which also busts the
    browser's cached copy — the view URL is versioned by modifiedTime). Files
    the listing doesn't cover (moved out of the folder by a human) are left
    untouched. Returns the refreshed rows, list-shaped."""
    rows = await store.list_documents(entity_type, record_id)
    if not rows:
        return []
    folder_id = await store.cached_folder_id(entity_type, record_id)
    if not folder_id:
        return rows
    listed = {f["id"]: f for f in await drive.list_folder_files(folder_id)}
    changed_ids: set[str] = set()
    for row in rows:
        file = listed.get(row["driveFileId"])
        if not file:
            continue
        drive_time = _parse_drive_time(file.get("modifiedTime"))
        stored_time = _parse_drive_time(row.get("modifiedTime"))
        if drive_time and drive_time != stored_time:
            await store.update_file_state(
                row["id"],
                modified_time=drive_time,
                checksum_md5=file.get("md5Checksum"),
                web_view_link=file.get("webViewLink"),
            )
            changed_ids.add(row["id"])
    if changed_ids:
        rows = await store.list_documents(entity_type, record_id)
    for row in rows:
        row["changedInDrive"] = row["id"] in changed_ids
    return rows
