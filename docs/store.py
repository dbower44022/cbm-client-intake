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
    Column("record_name", String(255)),  # human-readable, at upload time
    Column("original_filename", String(255), nullable=False),
    Column("mime_type", String(128)),  # native MIME type as stored in Drive
    Column("doc_type", String(64)),  # business classification
    Column("web_view_link", String(512)),
    Column("uploaded_by", String(128)),  # Workspace email of uploader
    Column("uploaded_at", DateTime(timezone=True), nullable=False),  # UTC
    Column("modified_time", DateTime(timezone=True)),  # Drive modifiedTime
    Column("checksum_md5", String(64)),  # null for Google-native formats
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
        "recordName": row.record_name,
        "filename": row.original_filename,
        "mimeType": row.mime_type,
        "docType": row.doc_type,
        "webViewLink": row.web_view_link,
        "uploadedBy": row.uploaded_by,
        "uploadedAt": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "modifiedTime": row.modified_time.isoformat() if row.modified_time else None,
        "checksumMd5": row.checksum_md5,
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
        self, entity_type: str, record_id: str, status: str = STATUS_ACTIVE
    ) -> list[dict[str, Any]]:
        """Active documents for one record, newest first (DOC-02: renders from
        this table only — no Drive call)."""
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(app_document)
                    .where(
                        app_document.c.entity_type == entity_type,
                        app_document.c.record_id == record_id,
                        app_document.c.status == status,
                    )
                    .order_by(app_document.c.uploaded_at.desc())
                )
            ).all()
        return [_row_dict(r) for r in rows]

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
        self, entity_type: str, record_id: str, status: str = STATUS_ACTIVE
    ) -> list[dict[str, Any]]:
        matches = [
            r
            for r in self.rows
            if r["entity_type"] == entity_type
            and r["record_id"] == record_id
            and r["status"] == status
        ]
        matches.sort(key=lambda r: r["uploaded_at"], reverse=True)

        class _Row:
            def __init__(self, d: dict[str, Any]) -> None:
                for col in app_document.c:
                    setattr(self, col.name, d.get(col.name))

        return [_row_dict(_Row(r)) for r in matches]

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
