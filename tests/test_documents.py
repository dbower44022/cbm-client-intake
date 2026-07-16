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


def test_folder_labels_map_entity_types():
    s = _settings()
    assert docs_service.folder_label(s, "Contact") == "Mentors"
    assert docs_service.folder_label(s, "CEngagement") == "Clients"
    assert docs_service.folder_label(s, "CPartnerProfile") == "Partners"
    assert docs_service.folder_label(s, "CSponsorProfile") == "Sponsors"
    # unmapped types fall back to the raw entity name
    assert docs_service.folder_label(s, "CWidget") == "CWidget"


async def test_ensure_record_folder_creates_label_and_record_levels():
    drive, store = FakeDrive(), MemoryDocumentStore()
    folder = await docs_service.ensure_record_folder(
        _settings(), drive, store, "Contact", "C1", "Jane Smith"
    )
    assert drive.created == [("drv1", "Mentors"), ("f1", "Jane Smith (C1)")]
    assert folder == "f2"


async def test_ensure_record_folder_nests_engagement_under_client():
    """PRD v1.2 D-07: Clients/{Client Name} (clientId)/{Engagement} (engId)/."""
    drive, store = FakeDrive(), MemoryDocumentStore()
    folder = await docs_service.ensure_record_folder(
        _settings(), drive, store, "CEngagement", "eng4455", "Jane Smith – 2026",
        client_id="77aa88", client_name="Acme Robotics",
    )
    assert drive.created == [
        ("drv1", "Clients"),
        ("f1", "Acme Robotics (77aa88)"),
        ("f2", "Jane Smith – 2026 (eng4455)"),
    ]
    assert folder == "f3"


async def test_ensure_record_folder_no_client_sits_under_label():
    drive, store = FakeDrive(), MemoryDocumentStore()
    folder = await docs_service.ensure_record_folder(
        _settings(), drive, store, "CEngagement", "E1", "Agape"
    )
    assert drive.created == [("drv1", "Clients"), ("f1", "Agape (E1)")]
    assert folder == "f2"


async def test_ensure_record_folder_reuses_existing_drive_folders():
    drive, store = FakeDrive(), MemoryDocumentStore()
    drive.folders[("drv1", "Clients")] = "labelF"
    drive.folders[("labelF", "Acme (A1)")] = "clientF"
    drive.folders[("clientF", "Agape (E1)")] = "recF"
    folder = await docs_service.ensure_record_folder(
        _settings(), drive, store, "CEngagement", "E1", "Agape",
        client_id="A1", client_name="Acme",
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
        _settings(), drive, store, "CEngagement", "E1", "Agape"
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


async def test_upload_document_stores_client_record_id():
    drive, store = FakeDrive(), MemoryDocumentStore()
    row = await docs_service.upload_document(
        _settings(), store, drive,
        entity_type="CEngagement", record_id="eng1", record_name="Jane – 2026",
        filename="deck.pptx", mime_type="application/vnd.ms-powerpoint",
        doc_type="Pitch Deck", data=b"pptx",
        client_id="acct9", client_name="Acme Robotics",
    )
    assert row["clientRecordId"] == "acct9"
    # the upload landed in the third-level (engagement) folder
    assert drive.created[-1] == ("f2", "Jane – 2026 (eng1)")
    assert drive.uploads[0][0] == "f3"


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


# --- viewing (Phase 2: DOC-03/04/06 + the DOC-02 lazy refresh) ---------------------


class ViewDrive(FakeDrive):
    """FakeDrive + the Phase 2 read surface."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.downloads: list[str] = []
        self.exports: list[str] = []
        self.folder_files: dict[str, list[dict]] = {}

    async def download_file(self, file_id):
        self.downloads.append(file_id)
        return b"native-bytes"

    async def export_pdf(self, file_id):
        self.exports.append(file_id)
        return b"%PDF-exported"

    async def list_folder_files(self, folder_id):
        return self.folder_files.get(folder_id, [])


async def _seed(store, **overrides):
    values = {
        "drive_file_id": "gfile1", "entity_type": "CEngagement", "record_id": "E1",
        "original_filename": "resume.pdf", "mime_type": "application/pdf",
        "doc_type": "Resume", "drive_folder_id": "foldE1",
        "modified_time": _dt("2026-07-16"),
    }
    values.update(overrides)
    await store.insert_document(values)
    rows = await store.list_documents(values["entity_type"], values["record_id"])
    return next(r for r in rows if r["driveFileId"] == values["drive_file_id"])


async def test_fetch_document_native_bytes():
    drive, store = ViewDrive(), MemoryDocumentStore()
    row = await _seed(store)
    doc = await docs_service.fetch_document(store, drive, "CEngagement", "E1", row["id"])
    assert doc["data"] == b"native-bytes"
    assert doc["mime_type"] == "application/pdf"
    assert doc["filename"] == "resume.pdf"
    assert drive.downloads == ["gfile1"] and drive.exports == []


async def test_fetch_document_google_native_exports_pdf():
    drive, store = ViewDrive(), MemoryDocumentStore()
    row = await _seed(
        store, drive_file_id="gdoc1", original_filename="Business Plan.gdoc",
        mime_type="application/vnd.google-apps.document",
    )
    doc = await docs_service.fetch_document(store, drive, "CEngagement", "E1", row["id"])
    assert doc["data"] == b"%PDF-exported"
    assert doc["mime_type"] == "application/pdf"
    assert doc["filename"] == "Business Plan.pdf"
    assert drive.exports == ["gdoc1"] and drive.downloads == []


async def test_fetch_document_unknown_id_raises_not_found():
    drive, store = ViewDrive(), MemoryDocumentStore()
    with pytest.raises(docs_service.DocsNotFound):
        await docs_service.fetch_document(store, drive, "CEngagement", "E1", "nope")


async def test_fetch_document_scoped_to_its_record():
    """A doc id from record E1 must not resolve through record E2's route —
    the route's CRM ACL check covers exactly the record it read."""
    drive, store = ViewDrive(), MemoryDocumentStore()
    row = await _seed(store)
    with pytest.raises(docs_service.DocsNotFound):
        await docs_service.fetch_document(store, drive, "CEngagement", "E2", row["id"])


def test_is_google_native():
    assert docs_service.is_google_native("application/vnd.google-apps.spreadsheet")
    assert not docs_service.is_google_native("application/pdf")
    assert not docs_service.is_google_native(None)


def test_content_headers_immutable_and_named():
    h = docs_service.content_headers("Résumé v2.pdf")
    assert h["Cache-Control"] == "private, max-age=31536000, immutable"
    assert 'filename="R?sum? v2.pdf"' in h["Content-Disposition"]
    assert "filename*=UTF-8''R%C3%A9sum%C3%A9%20v2.pdf" in h["Content-Disposition"]


async def test_refresh_updates_changed_rows_and_flags_them():
    drive, store = ViewDrive(), MemoryDocumentStore()
    changed = await _seed(store)  # gfile1, stored 2026-07-16
    same = await _seed(
        store, drive_file_id="gfile2", original_filename="notes.docx",
        mime_type="application/msword",
    )
    drive.folder_files["foldE1"] = [
        {"id": "gfile1", "modifiedTime": "2026-07-17T09:00:00.000Z",
         "md5Checksum": "new-sum", "webViewLink": "https://drive.google.com/new"},
        {"id": "gfile2", "modifiedTime": "2026-07-16T00:00:00.000Z"},
    ]
    rows = await docs_service.refresh_documents(store, drive, "CEngagement", "E1")
    by_file = {r["driveFileId"]: r for r in rows}
    assert by_file["gfile1"]["changedInDrive"] is True
    assert by_file["gfile1"]["modifiedTime"].startswith("2026-07-17")
    assert by_file["gfile1"]["checksumMd5"] == "new-sum"
    assert by_file["gfile1"]["webViewLink"] == "https://drive.google.com/new"
    assert by_file["gfile2"]["changedInDrive"] is False
    assert by_file["gfile2"]["modifiedTime"] == same["modifiedTime"]
    # a second refresh is a no-op: the stored time now matches Drive
    rows = await docs_service.refresh_documents(store, drive, "CEngagement", "E1")
    assert all(not r["changedInDrive"] for r in rows)
    assert changed["id"] in {r["id"] for r in rows}


async def test_refresh_leaves_unlisted_files_untouched():
    """A file a human moved out of the record folder isn't in the scoped
    files.list — its row keeps its stored state (never nulled)."""
    drive, store = ViewDrive(), MemoryDocumentStore()
    row = await _seed(store)
    drive.folder_files["foldE1"] = []  # listing doesn't cover the file
    rows = await docs_service.refresh_documents(store, drive, "CEngagement", "E1")
    assert rows[0]["modifiedTime"] == row["modifiedTime"]
    assert rows[0]["changedInDrive"] is False


async def test_refresh_without_rows_or_folder():
    drive, store = ViewDrive(), MemoryDocumentStore()
    assert await docs_service.refresh_documents(store, drive, "CEngagement", "E1") == []
    row = await _seed(store, drive_folder_id=None)
    rows = await docs_service.refresh_documents(store, drive, "CEngagement", "E1")
    assert rows[0]["id"] == row["id"]  # no cached folder -> metadata returned as is


async def test_store_update_file_state_roundtrip():
    store = MemoryDocumentStore()
    row = await _seed(store)
    new_time = docs_service._parse_drive_time("2026-07-18T12:00:00.000Z")
    await store.update_file_state(row["id"], modified_time=new_time, checksum_md5="s2")
    got = await store.get_document("CEngagement", "E1", row["id"])
    assert got["modifiedTime"].startswith("2026-07-18")
    assert got["checksumMd5"] == "s2"
    # web_view_link untouched when not supplied
    assert got["webViewLink"] == row["webViewLink"]


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
