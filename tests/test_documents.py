"""Documents (DOC-MGMT Phase 1): metadata store, folder scheme, upload rollback,
and the Drive client's upload-mode selection. No live Google calls."""

from __future__ import annotations

from datetime import timezone

import pytest

from core.config import Settings
from core.gdrive import RESUMABLE_THRESHOLD, DriveClient, _retryable
from docs import service as docs_service
from docs.store import MemoryDocumentStore


def _settings(**overrides) -> Settings:
    values = {"gdrive_docs": True, "gdrive_shared_drive_id": "drv1"}
    values.update(overrides)
    return Settings(**values)


class FakeDrive:
    """Records folder lookups/creates, uploads, and rollback deletes."""

    def __init__(self, mailbox="bob.mentor@cbmentors.org", drive_id="drv1"):
        self.mailbox = mailbox
        self.drive_id = drive_id
        self.folders: dict[tuple[str, str], str] = {}
        self.created: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str, str, int]] = []
        self.deleted: list[str] = []

    async def find_child_folder(self, parent_id, name):
        return self.folders.get((parent_id, name))

    async def create_folder(self, parent_id, name):
        folder_id = f"f{len(self.created) + 1}"
        self.folders[(parent_id, name)] = folder_id
        self.created.append((parent_id, name))
        return folder_id

    async def upload_file(self, folder_id, filename, mime_type, data):
        self.uploads.append((folder_id, filename, mime_type, len(data)))
        return {
            "id": f"file{len(self.uploads)}",
            "webViewLink": "https://drive.google.com/file/d/x/view",
            "modifiedTime": "2026-07-16T10:00:00.000Z",
            "md5Checksum": "abc123",
        }

    async def delete_file(self, file_id):
        self.deleted.append(file_id)


# --- metadata store -------------------------------------------------------------


async def test_store_lists_newest_first_active_only():
    store = MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "old.pdf", "uploaded_at": _dt("2026-07-01")}
    )
    await store.insert_document(
        {"drive_file_id": "b", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "new.pdf", "uploaded_at": _dt("2026-07-15")}
    )
    await store.insert_document(
        {"drive_file_id": "c", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "gone.pdf", "status": "archived",
         "uploaded_at": _dt("2026-07-16")}
    )
    await store.insert_document(
        {"drive_file_id": "d", "entity_type": "CEngagement", "record_id": "E2",
         "original_filename": "other.pdf", "uploaded_at": _dt("2026-07-16")}
    )
    rows = await store.list_documents("CEngagement", "E1")
    assert [r["filename"] for r in rows] == ["new.pdf", "old.pdf"]
    assert all(r["status"] == "active" for r in rows)


async def test_store_rejects_duplicate_drive_file_id():
    store = MemoryDocumentStore()
    row = {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
           "original_filename": "x.pdf"}
    await store.insert_document(row)
    with pytest.raises(ValueError):
        await store.insert_document(dict(row))


async def test_store_caches_folder_id():
    store = MemoryDocumentStore()
    assert await store.cached_folder_id("CEngagement", "E1") is None
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "fold9"}
    )
    assert await store.cached_folder_id("CEngagement", "E1") == "fold9"
    assert await store.cached_folder_id("CEngagement", "E2") is None


def _dt(day: str):
    from datetime import datetime

    return datetime.fromisoformat(day + "T00:00:00+00:00")


# --- folder scheme ---------------------------------------------------------------


def test_folder_name_sanitized():
    assert docs_service.sanitize_folder_name("Agape / W8 Loss") == "Agape W8 Loss"
    assert docs_service.sanitize_folder_name("a\\b\x01c") == "a b c"
    assert docs_service.sanitize_folder_name("  ") == "(unnamed)"
    assert (
        docs_service.record_folder_name("Jane Smith", "6543a1")
        == "Jane Smith (6543a1)"
    )


async def test_ensure_record_folder_creates_both_levels():
    drive, store = FakeDrive(), MemoryDocumentStore()
    folder = await docs_service.ensure_record_folder(
        drive, store, "CEngagement", "E1", "Agape"
    )
    assert drive.created == [("drv1", "CEngagement"), ("f1", "Agape (E1)")]
    assert folder == "f2"


async def test_ensure_record_folder_reuses_existing_drive_folders():
    drive, store = FakeDrive(), MemoryDocumentStore()
    drive.folders[("drv1", "CEngagement")] = "typeF"
    drive.folders[("typeF", "Agape (E1)")] = "recF"
    folder = await docs_service.ensure_record_folder(
        drive, store, "CEngagement", "E1", "Agape"
    )
    assert folder == "recF"
    assert drive.created == []


async def test_ensure_record_folder_prefers_cached_id():
    drive, store = FakeDrive(), MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "cachedF"}
    )
    folder = await docs_service.ensure_record_folder(
        drive, store, "CEngagement", "E1", "Agape"
    )
    assert folder == "cachedF"
    assert drive.created == []  # no Drive lookups at all


# --- upload + rollback -------------------------------------------------------------


async def test_upload_document_writes_metadata_row():
    drive, store = FakeDrive(), MemoryDocumentStore()
    row = await docs_service.upload_document(
        _settings(), store, drive,
        entity_type="CEngagement", record_id="E1", record_name="Agape",
        filename="resume.pdf", mime_type="application/pdf",
        doc_type="Resume", data=b"%PDF-1.4",
    )
    assert row["filename"] == "resume.pdf"
    assert row["docType"] == "Resume"
    assert row["uploadedBy"] == "bob.mentor@cbmentors.org"
    assert row["driveFileId"] == "file1"
    assert row["webViewLink"].startswith("https://drive.google.com/")
    assert row["checksumMd5"] == "abc123"
    assert row["modifiedTime"] is not None
    stored = await store.list_documents("CEngagement", "E1")
    assert len(stored) == 1 and stored[0]["driveFileId"] == "file1"
    assert drive.uploads == [("f2", "resume.pdf", "application/pdf", 8)]


async def test_upload_rolls_back_drive_file_when_row_write_fails():
    class FailingStore(MemoryDocumentStore):
        async def insert_document(self, values):
            raise RuntimeError("db down")

    drive, store = FakeDrive(), FailingStore()
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.upload_document(
            _settings(), store, drive,
            entity_type="CEngagement", record_id="E1", record_name="Agape",
            filename="resume.pdf", mime_type="application/pdf",
            doc_type="Resume", data=b"%PDF-1.4",
        )
    assert "rolled back" in str(exc.value)
    assert drive.deleted == ["file1"]  # a Drive file with no row gets deleted
    assert store.rows == []


async def test_upload_failure_writes_no_row():
    class FailingDrive(FakeDrive):
        async def upload_file(self, *a, **k):
            from core.gdrive import DriveError

            raise DriveError("boom")

    drive, store = FailingDrive(), MemoryDocumentStore()
    from core.gdrive import DriveError

    with pytest.raises(DriveError):
        await docs_service.upload_document(
            _settings(), store, drive,
            entity_type="CEngagement", record_id="E1", record_name="Agape",
            filename="resume.pdf", mime_type="application/pdf",
            doc_type="Resume", data=b"x",
        )
    assert store.rows == []  # a row is never written without a confirmed file


@pytest.mark.parametrize(
    "kwargs, phrase",
    [
        ({"filename": "  "}, "file name"),
        ({"data": b""}, "empty"),
        ({"doc_type": "Meme"}, "document type"),
    ],
)
async def test_upload_validations(kwargs, phrase):
    drive, store = FakeDrive(), MemoryDocumentStore()
    base = dict(
        entity_type="CEngagement", record_id="E1", record_name="Agape",
        filename="resume.pdf", mime_type="application/pdf",
        doc_type="Resume", data=b"x",
    )
    base.update(kwargs)
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.upload_document(_settings(), store, drive, **base)
    assert phrase in str(exc.value)
    assert drive.uploads == [] and store.rows == []


async def test_upload_size_cap():
    drive, store = FakeDrive(), MemoryDocumentStore()
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.upload_document(
            _settings(gdrive_max_file_mb=1), store, drive,
            entity_type="CEngagement", record_id="E1", record_name="Agape",
            filename="big.bin", mime_type="application/octet-stream",
            doc_type="Other", data=b"x" * (1024 * 1024 + 1),
        )
    assert "1 MB" in str(exc.value)


async def test_upload_defaults_missing_mime():
    drive, store = FakeDrive(), MemoryDocumentStore()
    await docs_service.upload_document(
        _settings(), store, drive,
        entity_type="CEngagement", record_id="E1", record_name="Agape",
        filename="x.bin", mime_type="", doc_type="Other", data=b"x",
    )
    assert drive.uploads[0][2] == "application/octet-stream"


def test_parse_drive_time():
    dt = docs_service._parse_drive_time("2026-07-16T10:00:00.123Z")
    assert dt is not None and dt.tzinfo == timezone.utc
    assert docs_service._parse_drive_time("") is None
    assert docs_service._parse_drive_time("not-a-date") is None


# --- drive_for_user (the impersonation-subject rule) ------------------------------


async def test_drive_for_user_uses_resolved_mailbox(monkeypatch):
    async def fake_resolve(client, user_id):
        assert user_id == "u1"
        return "bob.mentor@cbmentors.org"

    async def fake_sa(settings):
        return {"client_email": "sa@example.iam.gserviceaccount.com"}

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    monkeypatch.setattr("comms.service.get_service_account", fake_sa)
    drive = await docs_service.drive_for_user(
        _settings(), object(), {"userId": "u1", "userName": "evil-input"}
    )
    assert drive.mailbox == "bob.mentor@cbmentors.org"
    assert drive.drive_id == "drv1"


async def test_drive_for_user_requires_cbm_email(monkeypatch):
    async def fake_resolve(client, user_id):
        return None

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.drive_for_user(_settings(), object(), {"userId": "u1"})
    assert "CBM email" in str(exc.value)


async def test_drive_for_user_requires_shared_drive(monkeypatch):
    async def fake_resolve(client, user_id):
        return "bob.mentor@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.drive_for_user(
            _settings(gdrive_shared_drive_id=""), object(), {"userId": "u1"}
        )
    assert "drive" in str(exc.value).lower()


# --- DriveClient upload-mode selection (no HTTP) -----------------------------------


async def test_small_upload_uses_multipart(monkeypatch):
    client = DriveClient({}, "bob@cbmentors.org", "drv1")
    called = {}

    async def fake_multipart(folder_id, filename, mime, data):
        called["mode"] = "multipart"
        return {"id": "f"}

    async def fake_resumable(folder_id, filename, mime, data):
        called["mode"] = "resumable"
        return {"id": "f"}

    monkeypatch.setattr(client, "_upload_multipart", fake_multipart)
    monkeypatch.setattr(client, "_upload_resumable", fake_resumable)
    await client.upload_file("f1", "a.pdf", "application/pdf", b"x" * RESUMABLE_THRESHOLD)
    assert called["mode"] == "multipart"
    await client.upload_file("f1", "a.pdf", "application/pdf", b"x" * (RESUMABLE_THRESHOLD + 1))
    assert called["mode"] == "resumable"


def test_retryable_statuses():
    import httpx

    def resp(status, body=b""):
        return httpx.Response(status, content=body, request=httpx.Request("GET", "http://x"))

    assert _retryable(resp(500))
    assert _retryable(resp(429))
    assert _retryable(resp(403, b'{"reason": "userRateLimitExceeded"}'))
    assert not _retryable(resp(403, b'{"reason": "insufficientFilePermissions"}'))
    assert not _retryable(resp(404))
