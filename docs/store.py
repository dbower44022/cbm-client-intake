"""Postgres metadata for managed documents (DOC-MGMT PRD §4).

Drive holds the bytes; this table holds the relational truth — which documents
belong to which CRM record, their business type, uploader, and lifecycle
status (PRD §3.3). The Drive ``fileId`` is the sole durable pointer to the
bytes (decision D-06: never derive state from folder paths).

The table is created by Alembic migration ``0005_app_document`` (``create_all``
mirrors it for local dev, like :mod:`comms.store`). Adaptations from the PRD's
MariaDB DDL: Postgres via SQLAlchemy; the ``status`` ENUM is a short varchar
holding ``active`` / ``archived``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)

from core.config import Settings
from core.store import make_async_engine

metadata = MetaData()

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

app_document = Table(
    "app_document",
    metadata,
    Column("id", String(36), primary_key=True),  # UUID, application-generated
    # Drive fileId — the sole durable pointer to the bytes.
    Column("drive_file_id", String(128), nullable=False, unique=True, index=True),
    Column("drive_folder_id", String(128)),  # parent record folder (cached)
    Column("entity_type", String(64), nullable=False, index=True),
    Column("record_id", String(64), nullable=False, index=True),
    # For engagement-anchored documents: the parent client record id (D-07),
    # denormalized for cross-engagement client reporting. Null otherwise.
    Column("client_record_id", String(64), index=True),
    Column("record_name", String(255)),  # human-readable, at upload time
    Column("original_filename", String(255), nullable=False),
    Column("mime_type", String(128)),  # native MIME type as stored in Drive
    Column("doc_type", String(64)),  # business classification
    Column("web_view_link", String(512)),
    Column("uploaded_by", String(128)),  # Workspace email of uploader
    Column("uploaded_at", DateTime(timezone=True), nullable=False),  # UTC
    Column("modified_time", DateTime(timezone=True)),  # Drive modifiedTime
    Column("checksum_md5", String(64)),  # null for Google-native formats
    # SHA-256 of the stored bytes — the per-record dedup key for email
    # attachments (Phase 1, email-quality plan section 3.1). Null for uploads
    # made before the column existed.
    Column("content_sha256", String(64), index=True),
    Column("status", String(16), nullable=False, server_default=STATUS_ACTIVE),
    # Supports the per-record listing query (PRD §4).
    Index("ix_app_document_record", "entity_type", "record_id", "status"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_document_id() -> str:
    return str(uuid.uuid4())


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "driveFileId": row.drive_file_id,
        "driveFolderId": row.drive_folder_id,
        "entityType": row.entity_type,
        "recordId": row.record_id,
        "clientRecordId": row.client_record_id,
        "recordName": row.record_name,
        "filename": row.original_filename,
        "mimeType": row.mime_type,
        "docType": row.doc_type,
        "webViewLink": row.web_view_link,
        "uploadedBy": row.uploaded_by,
        "uploadedAt": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "modifiedTime": row.modified_time.isoformat() if row.modified_time else None,
        "checksumMd5": row.checksum_md5,
        "contentSha256": row.content_sha256,
        "status": row.status,
    }


class DocumentStore:
    """app_document persistence (one engine, like CommsStore)."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def insert_document(self, values: dict[str, Any]) -> None:
        values = dict(values)
        values.setdefault("id", new_document_id())
        values.setdefault("uploaded_at", _now())
        values.setdefault("status", STATUS_ACTIVE)
        async with self._engine.begin() as conn:
            await conn.execute(insert(app_document).values(**values))

    async def list_documents(
        self, entity_type: str, record_id: str, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Documents for one record, newest first (DOC-02: renders from this
        table only — no Drive call). Archived rows are hidden by default; the
        "include archived" toggle (DOC-07) lists every status."""
        conds = [
            app_document.c.entity_type == entity_type,
            app_document.c.record_id == record_id,
        ]
        if not include_archived:
            conds.append(app_document.c.status == STATUS_ACTIVE)
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(app_document)
                    .where(*conds)
                    .order_by(app_document.c.uploaded_at.desc())
                )
            ).all()
        return [_row_dict(r) for r in rows]

    async def set_status(self, doc_id: str, status: str) -> None:
        """Flip one document's lifecycle status (DOC-07 archive/restore)."""
        async with self._engine.begin() as conn:
            await conn.execute(
                update(app_document)
                .where(app_document.c.id == doc_id)
                .values(status=status)
            )

    async def list_folder_records(self) -> list[dict[str, Any]]:
        """Every record that owns a Drive folder — (entity_type, record_id,
        drive_folder_id), deduped — for the nightly grant reconciliation
        (DOC-09): the grant set is re-derived per record folder."""
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        app_document.c.entity_type,
                        app_document.c.record_id,
                        app_document.c.drive_folder_id,
                    )
                    .where(app_document.c.drive_folder_id.is_not(None))
                    .distinct()
                )
            ).all()
        return [
            {
                "entityType": r.entity_type,
                "recordId": r.record_id,
                "driveFolderId": r.drive_folder_id,
            }
            for r in rows
        ]

    async def get_document(
        self, entity_type: str, record_id: str, doc_id: str
    ) -> Optional[dict[str, Any]]:
        """One document row, scoped to its anchor record — a doc id from
        another record's route never resolves (the route's ACL check covers
        exactly the record it read)."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(app_document).where(
                        app_document.c.id == doc_id,
                        app_document.c.entity_type == entity_type,
                        app_document.c.record_id == record_id,
                    )
                )
            ).first()
        return _row_dict(row) if row else None

    async def update_file_state(
        self,
        doc_id: str,
        *,
        modified_time: Optional[datetime],
        checksum_md5: Optional[str] = None,
        web_view_link: Optional[str] = None,
    ) -> None:
        """Refresh the Drive-derived columns after a lazy sync (DOC-02):
        ``modified_time`` is the cache-invalidation key; checksum + view link
        ride along when Drive reported them."""
        values: dict[str, Any] = {"modified_time": modified_time}
        if checksum_md5 is not None:
            values["checksum_md5"] = checksum_md5
        if web_view_link is not None:
            values["web_view_link"] = web_view_link
        async with self._engine.begin() as conn:
            await conn.execute(
                update(app_document)
                .where(app_document.c.id == doc_id)
                .values(**values)
            )

    async def find_by_sha256(
        self, entity_type: str, record_id: str, sha256: str
    ) -> Optional[dict[str, Any]]:
        """A document on THIS record whose stored bytes hash to ``sha256`` —
        the email-attachment dedup lookup (any status: an archived copy still
        means the record has the file; per-record by design, since Drive
        grants and folder placement are per-record)."""
        if not sha256:
            return None
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(app_document).where(
                        app_document.c.entity_type == entity_type,
                        app_document.c.record_id == record_id,
                        app_document.c.content_sha256 == sha256,
                    )
                )
            ).first()
        return _row_dict(row) if row else None

    async def cached_folder_id(self, entity_type: str, record_id: str) -> Optional[str]:
        """The record's Drive folder id, from any prior upload (folder-ID cache,
        PRD §4 — denormalized on the rows; any status counts)."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(app_document.c.drive_folder_id)
                    .where(
                        app_document.c.entity_type == entity_type,
                        app_document.c.record_id == record_id,
                        app_document.c.drive_folder_id.is_not(None),
                    )
                    .order_by(app_document.c.uploaded_at.desc())
                    .limit(1)
                )
            ).first()
        return row.drive_folder_id if row else None

    async def clear_folder_cache(self, entity_type: str, record_id: str) -> None:
        """Forget the record's cached Drive folder id (P2, reliability review
        2026-07-17): a record folder deleted in the Drive console otherwise
        404s every subsequent upload forever. The next upload re-runs the
        find-or-create path and re-caches the new folder on its row."""
        async with self._engine.begin() as conn:
            await conn.execute(
                update(app_document)
                .where(
                    app_document.c.entity_type == entity_type,
                    app_document.c.record_id == record_id,
                )
                .values(drive_folder_id=None)
            )


def make_document_store(settings: Settings) -> Optional[DocumentStore]:
    if not settings.database_url:
        return None
    return DocumentStore(settings.database_url)


class MemoryDocumentStore:
    """In-memory stand-in for tests / DB-less dev (same surface as DocumentStore)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def create_all(self) -> None: ...

    async def dispose(self) -> None: ...

    async def insert_document(self, values: dict[str, Any]) -> None:
        values = dict(values)
        values.setdefault("id", new_document_id())
        values.setdefault("uploaded_at", _now())
        values.setdefault("status", STATUS_ACTIVE)
        if any(r["drive_file_id"] == values["drive_file_id"] for r in self.rows):
            raise ValueError(f"duplicate drive_file_id {values['drive_file_id']}")
        self.rows.append(values)

    async def list_documents(
        self, entity_type: str, record_id: str, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        matches = [
            r
            for r in self.rows
            if r["entity_type"] == entity_type
            and r["record_id"] == record_id
            and (include_archived or r["status"] == STATUS_ACTIVE)
        ]
        matches.sort(key=lambda r: r["uploaded_at"], reverse=True)

        class _Row:
            def __init__(self, d: dict[str, Any]) -> None:
                for col in app_document.c:
                    setattr(self, col.name, d.get(col.name))

        return [_row_dict(_Row(r)) for r in matches]

    async def get_document(
        self, entity_type: str, record_id: str, doc_id: str
    ) -> Optional[dict[str, Any]]:
        for r in self.rows:
            if (
                r["id"] == doc_id
                and r["entity_type"] == entity_type
                and r["record_id"] == record_id
            ):
                return (await self._as_rows([r]))[0]
        return None

    async def update_file_state(
        self,
        doc_id: str,
        *,
        modified_time: Optional[datetime],
        checksum_md5: Optional[str] = None,
        web_view_link: Optional[str] = None,
    ) -> None:
        for r in self.rows:
            if r["id"] == doc_id:
                r["modified_time"] = modified_time
                if checksum_md5 is not None:
                    r["checksum_md5"] = checksum_md5
                if web_view_link is not None:
                    r["web_view_link"] = web_view_link

    async def _as_rows(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        class _Row:
            def __init__(self, d: dict[str, Any]) -> None:
                for col in app_document.c:
                    setattr(self, col.name, d.get(col.name))

        return [_row_dict(_Row(r)) for r in matches]

    async def set_status(self, doc_id: str, status: str) -> None:
        for r in self.rows:
            if r["id"] == doc_id:
                r["status"] = status

    async def list_folder_records(self) -> list[dict[str, Any]]:
        seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        for r in self.rows:
            if not r.get("drive_folder_id"):
                continue
            key = (r["entity_type"], r["record_id"], r["drive_folder_id"])
            seen[key] = {
                "entityType": r["entity_type"],
                "recordId": r["record_id"],
                "driveFolderId": r["drive_folder_id"],
            }
        return list(seen.values())

    async def find_by_sha256(
        self, entity_type: str, record_id: str, sha256: str
    ) -> Optional[dict[str, Any]]:
        if not sha256:
            return None
        for r in self.rows:
            if (
                r["entity_type"] == entity_type
                and r["record_id"] == record_id
                and r.get("content_sha256") == sha256
            ):
                return (await self._as_rows([r]))[0]
        return None

    async def cached_folder_id(self, entity_type: str, record_id: str) -> Optional[str]:
        matches = [
            r
            for r in self.rows
            if r["entity_type"] == entity_type
            and r["record_id"] == record_id
            and r.get("drive_folder_id")
        ]
        matches.sort(key=lambda r: r["uploaded_at"], reverse=True)
        return matches[0]["drive_folder_id"] if matches else None

    async def clear_folder_cache(self, entity_type: str, record_id: str) -> None:
        for r in self.rows:
            if r["entity_type"] == entity_type and r["record_id"] == record_id:
                r["drive_folder_id"] = None
