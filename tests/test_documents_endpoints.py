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
