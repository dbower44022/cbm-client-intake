"""Document-management operations behind the sessions Documents tab (Phase 1).

CRM reads (the parent record's name + the ACL check that the signed-in user
may see it) run **as the user**, like every other sessions read. Drive
operations impersonate ONLY the signed-in user's own CBM mailbox, resolved
from their CRM identity — never from request input (the comms subject rule).

The rollback contract (PRD DOC-01): a Drive file with no metadata row is
deleted; a metadata row is never written without a confirmed Drive file.

**Upload-safety strategy (P1-13, reliability review 2026-07-17 — the chosen
one of the review's two options): pre-generated file ids.** Every upload
first asks Drive for a server-generated id (``files.generateIds``) and
creates the file WITH it, so (a) a retried create can never duplicate (the
duplicate id is rejected; a 409 resolves to the already-committed file), and
(b) when the upload RESPONSE is lost after Drive committed — previously an
unfindable orphan the user's retry would duplicate — the rollback target is
still known and the file is deleted before the error surfaces. When the id
pre-generation itself fails, the upload proceeds the old way (single
attempt, no blind retry) rather than blocking. The row-first/pending-sweep
alternative was NOT chosen (no migration, no reconcile changes needed).
Folder creation is not id-protected; instead a failed create re-runs
find-or-create, which converges on the committed folder.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.gdrive import (
    GOOGLE_NATIVE_DOWNLOADS,
    GOOGLE_NATIVE_MIMES,
    OFFICE_CONVERT_MIMES,
    PDF_MIME,
    DriveClient,
    DriveError,
)

from .store import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    DocumentStore,
    make_document_store,
)

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
    folder level; returns the last segment's folder id.

    A failed folder create re-runs the find once (P1-13): the create POST is
    never blind-retried (a 5xx after commit would mint a duplicate folder) —
    if the create actually committed, the re-run find picks it up."""
    parent = drive.drive_id  # a shared drive's root folder id IS the drive id
    for name in segments:
        folder = await drive.find_child_folder(parent, name)
        if not folder:
            try:
                folder = await drive.create_folder(parent, name)
            except DriveError:
                folder = await drive.find_child_folder(parent, name)
                if not folder:
                    raise
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
    from_cache = bool(await store.cached_folder_id(entity_type, record_id))
    folder_id = await ensure_record_folder(
        settings, drive, store, entity_type, record_id, record_name,
        client_id=client_id, client_name=client_name,
    )
    # P1-13: pre-generate the file id so a lost response is recoverable (the
    # rollback target is known) and a retried create can't duplicate. Fail
    # open: no id just means the old single-attempt behavior.
    pre_id: Optional[str] = None
    try:
        pre_id = await drive.generate_file_id()
    except DriveError as exc:
        log.warning("file-id pre-generation failed (continuing without): %s", exc)
    try:
        file = await drive.upload_file(
            folder_id, filename, mime_type, data, file_id=pre_id
        )
    except DriveError as exc:
        # Cached-folder staleness: the folder was deleted in the Drive console
        # (404s every upload forever without this) — drop the cache, rebuild
        # the path, and retry ONCE.
        if from_cache and "404" in str(exc):
            log.warning(
                "cached Drive folder for %s %s is gone (%s) — rebuilding the "
                "folder path", entity_type, record_id, exc,
            )
            await store.clear_folder_cache(entity_type, record_id)
            folder_id = await ensure_record_folder(
                settings, drive, store, entity_type, record_id, record_name,
                client_id=client_id, client_name=client_name,
            )
            file = await drive.upload_file(
                folder_id, filename, mime_type, data, file_id=pre_id
            )
        else:
            # The response may have been LOST after Drive committed — with the
            # pre-generated id the file (if any) is deletable before the error
            # surfaces, so the user's retry can't duplicate it.
            if pre_id:
                try:
                    await drive.delete_file(pre_id)
                except DriveError as del_exc:
                    log.error(
                        "ROLLBACK FAILED: possibly-committed Drive file %s could "
                        "not be deleted: %s", pre_id, del_exc,
                    )
            raise
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
    store: DocumentStore,
    entity_type: str,
    record_id: str,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """DOC-02 (partial): documents newest first, from metadata only. Archived
    rows are hidden unless the "include archived" toggle asks for them."""
    return await store.list_documents(
        entity_type, record_id, include_archived=include_archived
    )


# --- archive / restore (DOC-07) ---------------------------------------------------

# The per-record subfolder archived files move into. Underscore-prefixed so it
# sorts apart from documents when a human browses the record folder.
ARCHIVED_FOLDER_NAME = "_Archived"


async def _move_into(
    drive: DriveClient, file_id: str, dest_folder_id: str
) -> Optional[list[str]]:
    """Move the file into ``dest_folder_id`` from wherever it currently sits
    (a human may have re-filed it — the actual parents are read first).
    Returns the original parents for a rollback move-back, or None when the
    file was already there (no move happened, so no rollback either)."""
    file = await drive.get_file(file_id, fields="id,parents")
    parents = [p for p in (file.get("parents") or []) if p != dest_folder_id]
    if dest_folder_id in (file.get("parents") or []) and not parents:
        return None
    await drive.move_file(file_id, dest_folder_id, parents)
    return parents


async def _lifecycle_move(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
    *,
    to_status: str,
) -> dict[str, Any]:
    """The shared DOC-07 mechanic, per Doug's ruling (2026-07-17): the Drive
    move happens FIRST, and the metadata status flips only after a confirmed
    move; if the flip fails the file is moved back — the two are never left
    inconsistent (Phase 1's DOC-01 rollback precedent). Archive moves the file
    into the record folder's ``/_Archived`` subfolder; restore moves it back."""
    row = await store.get_document(entity_type, record_id, doc_id)
    if row is None:
        raise DocsNotFound("That document isn't on this record.")
    verb = "archived" if to_status == STATUS_ARCHIVED else "restored"
    if row["status"] == to_status:
        raise DocsError(f"That document is already {verb}.")
    record_folder = row.get("driveFolderId") or await store.cached_folder_id(
        entity_type, record_id
    )
    if not record_folder:
        raise DocsError(
            "This document's Drive folder isn't recorded, so it can't be "
            f"{verb} — contact CBM staff."
        )
    if to_status == STATUS_ARCHIVED:
        dest = await drive.find_child_folder(record_folder, ARCHIVED_FOLDER_NAME)
        if not dest:
            dest = await drive.create_folder(record_folder, ARCHIVED_FOLDER_NAME)
    else:
        dest = record_folder
    original_parents = await _move_into(drive, row["driveFileId"], dest)
    try:
        await store.set_status(doc_id, to_status)
    except Exception as exc:
        if original_parents:
            try:
                await drive.move_file(row["driveFileId"], original_parents[0], [dest])
            except DriveError as move_exc:  # inconsistent — log loudly
                log.error(
                    "ROLLBACK FAILED: document %s (file %s) was moved for %s "
                    "but the status flip failed and the move-back also failed: "
                    "%s", doc_id, row["driveFileId"], verb, move_exc,
                )
        raise DocsError(
            f"The document could not be {verb} — please try again."
        ) from exc
    log.info(
        "document %s (%s %s): %s -> %s",
        verb, entity_type, record_id, doc_id, dest,
    )
    refreshed = await store.get_document(entity_type, record_id, doc_id)
    return refreshed or row


async def archive_document(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
) -> dict[str, Any]:
    """DOC-07: soft-delete — the file moves to ``/_Archived`` and the row
    leaves the default list. Hard deletion stays out of the app."""
    return await _lifecycle_move(
        store, drive, entity_type, record_id, doc_id, to_status=STATUS_ARCHIVED
    )


async def restore_document(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
) -> dict[str, Any]:
    """DOC-07: the reverse of archive — file back to the record folder,
    status back to active."""
    return await _lifecycle_move(
        store, drive, entity_type, record_id, doc_id, to_status=STATUS_ACTIVE
    )


# --- viewing (Phase 2) -------------------------------------------------------------


def content_headers(filename: str, attachment: bool = False) -> dict[str, str]:
    """Response headers for the view/download proxy (DOC-06 — the browser IS
    the cache): the frontend versions the URL by the row's modifiedTime, so
    the bytes at any one URL are immutable — each browser holds them
    privately, cache hits are instant with zero network, and a Drive edit
    (new modifiedTime → new URL after the lazy refresh) invalidates
    automatically. ``attachment=True`` = the Download-original action: the
    browser saves the file instead of rendering it, so the user can open it
    in the locally installed application (Excel, Word, …)."""
    ascii_name = (
        filename.encode("ascii", "replace").decode().replace('"', "'") or "document"
    )
    quoted = urllib.parse.quote(filename)
    kind = "attachment" if attachment else "inline"
    return {
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": (
            f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
        ),
    }


def is_google_native(mime_type: Optional[str]) -> bool:
    """Google-native editor formats (Docs/Sheets/Slides) have no native bytes —
    in-app viewing goes through ``files.export`` to PDF (DOC-04)."""
    return (mime_type or "") in GOOGLE_NATIVE_MIMES


def _swap_extension(filename: str, ext: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem or 'document'}{ext}"


def _pdf_filename(filename: str) -> str:
    return _swap_extension(filename, ".pdf")


async def fetch_document(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
    original: bool = False,
) -> dict[str, Any]:
    """The document's bytes for the view proxy (DOC-03). Default = VIEWING:
    binary files come back native, Google-native AND Office formats arrive as
    PDF (DOC-04 / convert-on-view). ``original=True`` = the Download action:
    the stored file's exact bytes, no conversion (formulas and all) — except
    Google-native files, which have no native bytes and export to their
    Office equivalent (Sheets → .xlsx, like Drive's own Download). Returns
    ``{data, mime_type, filename, modified_time}`` — the caller serves it
    with cache headers keyed on the row's modifiedTime (DOC-06)."""
    row = await store.get_document(entity_type, record_id, doc_id)
    if row is None:
        raise DocsNotFound("That document isn't on this record.")
    file_id = row["driveFileId"]
    stored_mime = row.get("mimeType") or ""
    stored_name = row.get("filename") or "document"
    if is_google_native(stored_mime):
        if original:
            mime, ext = GOOGLE_NATIVE_DOWNLOADS[stored_mime]
            data = await drive.export_file(file_id, mime)
            filename = _swap_extension(stored_name, ext)
        else:
            data = await drive.export_pdf(file_id)
            mime, filename = PDF_MIME, _pdf_filename(stored_name)
    elif not original and stored_mime in OFFICE_CONVERT_MIMES:
        # Office formats view via read-time conversion (copy-as-Google-format
        # → export PDF → delete the temp); the stored file is untouched.
        data = await drive.export_office_pdf(
            file_id, OFFICE_CONVERT_MIMES[stored_mime]
        )
        mime, filename = PDF_MIME, _pdf_filename(stored_name)
    else:
        data = await drive.download_file(file_id)
        mime = stored_mime or "application/octet-stream"
        filename = stored_name
    return {
        "data": data,
        "mime_type": mime,
        "filename": filename,
        "modified_time": row.get("modifiedTime"),
    }


async def stream_original(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    doc_id: str,
) -> Optional[dict[str, Any]]:
    """The Download-original path as a STREAM (P2, reliability review
    2026-07-17): the stored file's exact bytes flow through in chunks instead
    of buffering whole in memory — a few concurrent large downloads could OOM
    a small instance. Returns ``{stream, mime_type, filename}`` (the stream is
    primed, so pre-body errors still raise cleanly as DriveError), or None for
    Google-native files (no native bytes — the caller uses the buffered export
    path, which Drive itself caps at ~10 MB). Raises :class:`DocsNotFound`
    when the document isn't on this record."""
    row = await store.get_document(entity_type, record_id, doc_id)
    if row is None:
        raise DocsNotFound("That document isn't on this record.")
    if is_google_native(row.get("mimeType")):
        return None
    gen = drive.stream_file(row["driveFileId"])
    # Prime: force the HTTP open + status check NOW, while the router can
    # still answer with a proper error response instead of a broken stream.
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        first = b""

    async def body():
        if first:
            yield first
        async for chunk in gen:
            yield chunk

    return {
        "stream": body(),
        "mime_type": row.get("mimeType") or "application/octet-stream",
        "filename": row.get("filename") or "document",
    }


async def refresh_documents(
    store: DocumentStore,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """DOC-02 completion — the lazy modifiedTime refresh on record open: ONE
    ``files.list`` scoped to the record folder updates each row's
    ``modified_time`` (+ checksum/view link), and rows whose file changed in
    Drive since last sync are flagged ``changedInDrive`` (which also busts the
    browser's cached copy — the view URL is versioned by modifiedTime). Files
    the listing doesn't cover (moved out of the folder by a human, or archived
    into ``/_Archived``) are left untouched. Returns the refreshed rows,
    list-shaped."""
    rows = await store.list_documents(
        entity_type, record_id, include_archived=include_archived
    )
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
        rows = await store.list_documents(
            entity_type, record_id, include_archived=include_archived
        )
    for row in rows:
        row["changedInDrive"] = row["id"] in changed_ids
    return rows


# --- CRM link write-back (DOC-08) + post-upload hooks -----------------------------

# The read-only URL field the CRM team builds on the participating entities
# (spec: documentsfolderurl-crm-field.md). Only these two anchors carry it —
# PRD §3.5: CEngagement (client work) + Contact (mentor documents).
FOLDER_LINK_FIELD = "documentsFolderUrl"
WRITE_BACK_ENTITIES = ("CEngagement", "Contact")

# Feature-detection cache: entity -> (field exists, monotonic deadline). The
# field activates with no app deploy once the CRM team builds it (the
# googleCalendarEventId precedent); re-checked every 10 minutes.
_FIELD_CACHE: dict[str, tuple[bool, float]] = {}
_FIELD_CACHE_TTL = 600.0


async def _folder_link_field_exists(espo: Any, entity_type: str) -> bool:
    import time

    cached = _FIELD_CACHE.get(entity_type)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    fields = await espo.metadata(f"entityDefs.{entity_type}.fields") or {}
    present = FOLDER_LINK_FIELD in fields
    _FIELD_CACHE[entity_type] = (present, time.monotonic() + _FIELD_CACHE_TTL)
    return present


async def write_back_folder_link(
    settings: Settings,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    folder_id: str,
    espo: Any = None,
) -> Optional[str]:
    """DOC-08: put the record FOLDER's ``webViewLink`` in the CRM record's
    ``documentsFolderUrl`` (one stable link per record, D-05). Self-healing
    best-effort (Doug's ruling 2026-07-17, no retry queue): checked on EVERY
    upload — idempotent (no write when the stored value already matches) —
    and re-checked by the nightly reconciliation. The write runs as the app's
    API user (a system bookkeeping write, not a user edit). Returns the link
    written, or None when nothing was (not a participating entity, field not
    built yet, already correct)."""
    if entity_type not in WRITE_BACK_ENTITIES:
        return None
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from . import grants

    espo = espo or grants.system_espo(settings)
    if not await _folder_link_field_exists(espo, entity_type):
        return None
    folder = await drive.get_file(folder_id, fields="id,webViewLink")
    link = folder.get("webViewLink")
    if not link:
        return None
    record = await espo.get(entity_type, record_id, select=FOLDER_LINK_FIELD)
    if record.get(FOLDER_LINK_FIELD) == link:
        return None
    await espo.update(entity_type, record_id, {FOLDER_LINK_FIELD: link})
    log.info(
        "documentsFolderUrl written (%s %s): %s", entity_type, record_id, link
    )
    return link


async def post_upload_hooks(
    settings: Settings,
    drive: DriveClient,
    entity_type: str,
    record_id: str,
    row: Optional[dict[str, Any]],
) -> None:
    """Best-effort follow-ups after a successful upload — neither may ever
    fail the upload (the PRD's contract for both): the DOC-08 CRM folder-link
    write-back, and the DOC-09 grant sync on the record folder (covers the
    folder-creation grant for already-entitled people, and self-heals any
    earlier hook failure)."""
    folder_id = (row or {}).get("driveFolderId")
    if not folder_id:
        return
    try:
        await write_back_folder_link(
            settings, drive, entity_type, record_id, folder_id
        )
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        log.warning(
            "documentsFolderUrl write-back failed (%s %s): %s — it will "
            "self-heal on the next upload or the nightly reconciliation",
            entity_type, record_id, exc,
        )
    from . import grants

    await grants.sync_record_grants_safe(
        settings, entity_type, record_id, folder_id=folder_id
    )
