"""Documents endpoints on the sessions routers (flag-gated, DOC-MGMT Phase 1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from docs import service as docs_service
from docs.store import MemoryDocumentStore
from forms import info_request

_USER = {
    "userId": "u1",
    "userName": "bob.mentor",
    "name": "Bob Mentor",
    "isAdmin": False,
    "teams": ["Mentor Team"],
    "roles": [],
    "token": "t",
}


def _app(monkeypatch, gdrive_docs: bool):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GDRIVE_DOCS", "true" if gdrive_docs else "false")
    monkeypatch.setenv("GDRIVE_SHARED_DRIVE_ID", "drv1")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user=_USER):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: _FakeCrm())


class _FakeCrm:
    async def get(self, entity, record_id, select=None):
        assert entity == "CEngagement"
        return {"id": record_id, "name": "Agape W8 Loss"}


def test_disabled_returns_503(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gdrive_docs=False)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents")
    assert r.status_code == 503
    assert "isn't enabled" in r.json()["detail"]


def test_session_config_reports_docs_flag(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gdrive_docs=False)) as c:
        r = c.get("/mentorsessions/api/session")
    assert r.status_code == 200
    assert r.json()["docsEnabled"] is False
    tabs = {t["key"]: t for t in r.json()["detailTabs"]}
    assert "placeholder" not in tabs["documents"]


def test_enabled_without_database_503s(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: None)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents")
    assert r.status_code == 503
    assert "database" in r.json()["detail"]


def test_unauthenticated_401(monkeypatch):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: None)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents")
    assert r.status_code == 401


def test_wrong_team_403(monkeypatch):
    user = dict(_USER, teams=["Sponsor Management Team"])
    _as(monkeypatch, user)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents")
    assert r.status_code == 403


def test_list_documents(monkeypatch):
    _as(monkeypatch)
    store = MemoryDocumentStore()
    monkeypatch.setattr(docs_service, "get_store", lambda settings: store)

    async def seed():
        await store.insert_document(
            {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
             "original_filename": "resume.pdf", "doc_type": "Resume",
             "uploaded_by": "bob.mentor@cbmentors.org"}
        )

    import asyncio

    asyncio.run(seed())
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"][0]["filename"] == "resume.pdf"
    assert "Resume" in body["docTypes"]
    # the frontend size gate reads the server's cap from the list response
    assert body["maxFileMb"] == 100


def test_upload_document(monkeypatch):
    _as(monkeypatch)
    store = MemoryDocumentStore()
    monkeypatch.setattr(docs_service, "get_store", lambda settings: store)
    seen = {}

    class FakeDrive:
        mailbox = "bob.mentor@cbmentors.org"
        drive_id = "drv1"

    async def fake_drive_for_user(settings, client, user):
        return FakeDrive()

    async def fake_upload(settings, st, drive, **kwargs):
        seen.update(kwargs)
        assert st is store
        return {"driveFileId": "file1", "filename": kwargs["filename"]}

    monkeypatch.setattr(docs_service, "drive_for_user", fake_drive_for_user)
    monkeypatch.setattr(docs_service, "upload_document", fake_upload)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/documents",
            params={"filename": "resume.pdf", "docType": "Resume"},
            content=b"%PDF-1.4",
            headers={"Content-Type": "application/pdf"},
        )
    assert r.status_code == 200
    assert r.json()["document"]["driveFileId"] == "file1"
    # The record name came from the user's own CRM read; the raw bytes and the
    # header MIME made it through.
    assert seen["record_name"] == "Agape W8 Loss"
    assert seen["entity_type"] == "CEngagement"
    assert seen["data"] == b"%PDF-1.4"
    assert seen["mime_type"] == "application/pdf"
    assert seen["doc_type"] == "Resume"
    # no company on the record => no client nesting, upload still proceeds
    assert seen["client_id"] is None


def test_upload_resolves_engagement_client(monkeypatch):
    """PRD v1.2 D-07: the parent client is resolved from the CEngagement at
    upload time (own link first, client-profile fallback) and passed through."""

    class Crm:
        async def get(self, entity, record_id, select=None):
            if entity == "CEngagement":
                assert "clientOrganizationId" in select and "engagementClientId" in select
                return {"id": record_id, "name": "Agape W8 Loss",
                        "engagementClientId": "prof1"}
            assert entity == "CClientProfile" and record_id == "prof1"
            return {"linkedCompanyId": "acct9", "linkedCompanyName": "Acme Robotics"}

    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: Crm())
    store = MemoryDocumentStore()
    monkeypatch.setattr(docs_service, "get_store", lambda settings: store)
    seen = {}

    async def fake_drive_for_user(settings, client, user):
        class D:
            mailbox = "bob.mentor@cbmentors.org"
        return D()

    async def fake_upload(settings, st, drive, **kwargs):
        seen.update(kwargs)
        return {"driveFileId": "file1"}

    monkeypatch.setattr(docs_service, "drive_for_user", fake_drive_for_user)
    monkeypatch.setattr(docs_service, "upload_document", fake_upload)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/documents",
            params={"filename": "deck.pptx", "docType": "Pitch Deck"},
            content=b"x",
            headers={"Content-Type": "application/vnd.ms-powerpoint"},
        )
    assert r.status_code == 200
    assert seen["client_id"] == "acct9"
    assert seen["client_name"] == "Acme Robotics"


def test_upload_validation_maps_to_400(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())

    async def fake_drive_for_user(settings, client, user):
        raise docs_service.DocsError("Your profile has no CBM email address.")

    monkeypatch.setattr(docs_service, "drive_for_user", fake_drive_for_user)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/documents",
            params={"filename": "resume.pdf", "docType": "Resume"},
            content=b"x",
            headers={"Content-Type": "application/pdf"},
        )
    assert r.status_code == 400
    assert "CBM email" in r.json()["detail"]


# --- Mentor Administration: mentor documents on the linked Contact -------------

_STAFF = dict(_USER, teams=["Mentor Administration Team"])


def _as_staff(monkeypatch, crm=None):
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: _STAFF)
    monkeypatch.setattr(
        "mentoradmin.router.client_for", lambda settings, user: crm or _FakeMentorCrm()
    )


class _FakeMentorCrm:
    async def get(self, entity, record_id, select=None):
        assert entity == "CMentorProfile"
        return {"id": record_id, "name": "Jane Smith",
                "contactRecordId": "C77", "contactRecordName": "Jane Smith"}


def test_mentoradmin_documents_disabled_503(monkeypatch):
    _as_staff(monkeypatch)
    with TestClient(_app(monkeypatch, gdrive_docs=False)) as c:
        r = c.get("/mentoradmin/api/mentors/M1/documents")
    assert r.status_code == 503


def test_mentoradmin_session_reports_docs_flag(monkeypatch):
    _as_staff(monkeypatch)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentoradmin/api/session")
    assert r.status_code == 200
    assert r.json()["docsEnabled"] is True


def test_mentoradmin_lists_contact_anchored_documents(monkeypatch):
    _as_staff(monkeypatch)
    store = MemoryDocumentStore()
    monkeypatch.setattr(docs_service, "get_store", lambda settings: store)

    async def seed():
        await store.insert_document(
            {"drive_file_id": "a", "entity_type": "Contact", "record_id": "C77",
             "original_filename": "jane-resume.pdf", "doc_type": "Resume"}
        )

    import asyncio

    asyncio.run(seed())
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentoradmin/api/mentors/M1/documents")
    assert r.status_code == 200
    assert r.json()["documents"][0]["filename"] == "jane-resume.pdf"


def test_mentoradmin_upload_anchors_to_contact(monkeypatch):
    _as_staff(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    seen = {}

    async def fake_drive_for_user(settings, client, user):
        class D:
            mailbox = "staff@cbmentors.org"
        return D()

    async def fake_upload(settings, st, drive, **kwargs):
        seen.update(kwargs)
        return {"driveFileId": "file1"}

    monkeypatch.setattr(docs_service, "drive_for_user", fake_drive_for_user)
    monkeypatch.setattr(docs_service, "upload_document", fake_upload)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentoradmin/api/mentors/M1/documents",
            params={"filename": "resume.pdf", "docType": "Resume"},
            content=b"%PDF",
            headers={"Content-Type": "application/pdf"},
        )
    assert r.status_code == 200
    assert seen["entity_type"] == "Contact"
    assert seen["record_id"] == "C77"
    assert seen["record_name"] == "Jane Smith"
    assert "client_id" not in seen or seen.get("client_id") is None


def test_mentoradmin_upload_requires_linked_contact(monkeypatch):
    class NoContactCrm:
        async def get(self, entity, record_id, select=None):
            return {"id": record_id, "name": "Jane Smith", "contactRecordId": None}

    _as_staff(monkeypatch, crm=NoContactCrm())
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentoradmin/api/mentors/M1/documents",
            params={"filename": "resume.pdf", "docType": "Resume"},
            content=b"%PDF",
            headers={"Content-Type": "application/pdf"},
        )
    assert r.status_code == 400
    assert "linked Contact" in r.json()["detail"]


# --- Phase 2: view proxy + lazy refresh ----------------------------------------


class _ViewDrive:
    mailbox = "bob.mentor@cbmentors.org"
    drive_id = "drv1"


async def _fake_drive_for_user(settings, client, user):
    return _ViewDrive()


def test_document_content_streams_with_immutable_cache_headers(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    seen = {}

    async def fake_fetch(store, drive, entity_type, record_id, doc_id, original=False):
        seen.update(entity=entity_type, record=record_id, doc=doc_id)
        return {"data": b"%PDF-1.4", "mime_type": "application/pdf",
                "filename": "resume.pdf", "modified_time": "2026-07-16T10:00:00+00:00"}

    monkeypatch.setattr(docs_service, "fetch_document", fake_fetch)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents/D1/content?v=2026-07-16")
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4"
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert 'filename="resume.pdf"' in r.headers["content-disposition"]
    assert seen == {"entity": "CEngagement", "record": "E1", "doc": "D1"}


def test_document_content_original_downloads_as_attachment(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    seen = {}

    async def fake_fetch(store, drive, entity_type, record_id, doc_id, original=False):
        seen["original"] = original
        return {"data": b"xlsx-bytes", "mime_type": "application/vnd.ms-excel",
                "filename": "Financials.xlsx", "modified_time": None}

    monkeypatch.setattr(docs_service, "fetch_document", fake_fetch)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents/D1/content?original=true")
    assert r.status_code == 200
    assert seen["original"] is True
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.content == b"xlsx-bytes"


def test_document_content_unknown_doc_404(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents/nope/content")
    assert r.status_code == 404
    assert "isn't on this record" in r.json()["detail"]


def test_document_content_drive_failure_502(monkeypatch):
    from core.gdrive import DriveError

    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)

    async def failing_fetch(*a, **k):
        raise DriveError("HTTP 500")

    monkeypatch.setattr(docs_service, "fetch_document", failing_fetch)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/documents/D1/content")
    assert r.status_code == 502
    assert "Open in Drive" in r.json()["detail"]


def test_documents_refresh_returns_flagged_rows(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    seen = {}

    async def fake_refresh(store, drive, entity_type, record_id):
        seen.update(entity=entity_type, record=record_id)
        return [{"id": "D1", "filename": "resume.pdf", "changedInDrive": True}]

    monkeypatch.setattr(docs_service, "refresh_documents", fake_refresh)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post("/mentorsessions/api/records/E1/documents/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"][0]["changedInDrive"] is True
    assert "Resume" in body["docTypes"]
    assert seen == {"entity": "CEngagement", "record": "E1"}


def test_documents_refresh_disabled_503(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gdrive_docs=False)) as c:
        r = c.post("/mentorsessions/api/records/E1/documents/refresh")
    assert r.status_code == 503


def test_mentoradmin_content_anchors_to_contact(monkeypatch):
    _as_staff(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    seen = {}

    async def fake_fetch(store, drive, entity_type, record_id, doc_id, original=False):
        seen.update(entity=entity_type, record=record_id, doc=doc_id)
        return {"data": b"img", "mime_type": "image/png",
                "filename": "photo.png", "modified_time": None}

    monkeypatch.setattr(docs_service, "fetch_document", fake_fetch)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.get("/mentoradmin/api/mentors/M1/documents/D9/content")
    assert r.status_code == 200
    assert r.content == b"img"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert seen == {"entity": "Contact", "record": "C77", "doc": "D9"}


def test_mentoradmin_refresh_anchors_to_contact(monkeypatch):
    _as_staff(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())
    monkeypatch.setattr(docs_service, "drive_for_user", _fake_drive_for_user)
    seen = {}

    async def fake_refresh(store, drive, entity_type, record_id):
        seen.update(entity=entity_type, record=record_id)
        return []

    monkeypatch.setattr(docs_service, "refresh_documents", fake_refresh)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post("/mentoradmin/api/mentors/M1/documents/refresh")
    assert r.status_code == 200
    assert seen == {"entity": "Contact", "record": "C77"}


def test_upload_drive_failure_maps_to_502(monkeypatch):
    from core.gdrive import DriveError

    _as(monkeypatch)
    monkeypatch.setattr(docs_service, "get_store", lambda settings: MemoryDocumentStore())

    async def fake_drive_for_user(settings, client, user):
        raise DriveError("HTTP 500")

    monkeypatch.setattr(docs_service, "drive_for_user", fake_drive_for_user)
    with TestClient(_app(monkeypatch, gdrive_docs=True)) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/documents",
            params={"filename": "resume.pdf", "docType": "Resume"},
            content=b"x",
            headers={"Content-Type": "application/pdf"},
        )
    assert r.status_code == 502
    assert "Google Drive" in r.json()["detail"]
