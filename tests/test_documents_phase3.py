"""Documents Phase 3 (DOC-MGMT): Drive access grants (DOC-09), the nightly
reconciliation, archive/restore (DOC-07), and the CRM link write-back
(DOC-08). No live Google or CRM calls."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.config import Settings
from docs import grants
from docs import service as docs_service
from docs.reconcile import run_docs_reconciliation
from docs.store import MemoryDocumentStore


def _settings(**overrides) -> Settings:
    """The ruled access model: docs on, service identity, real CRM creds."""
    values = {
        "gdrive_docs": True,
        "gdrive_shared_drive_id": "drv1",
        "gdrive_identity": "service",
        "espo_dry_run": False,
        "espo_api_key": "key1",
    }
    values.update(overrides)
    return Settings(**values)


def _dt(day: str) -> datetime:
    return datetime.fromisoformat(day + "T00:00:00+00:00")


@pytest.fixture(autouse=True)
def _clear_field_cache():
    docs_service._FIELD_CACHE.clear()
    yield
    docs_service._FIELD_CACHE.clear()


class FakeEspo:
    """CRM stub: records + related lists + metadata + updates."""

    def __init__(self):
        self.records: dict[tuple[str, str], dict] = {}
        self.related: dict[tuple[str, str, str], list[dict]] = {}
        self.fields: dict[str, dict] = {}  # entity -> entityDefs fields
        self.updates: list[tuple[str, str, dict]] = []

    async def get(self, entity, record_id, select=None):
        return dict(self.records.get((entity, record_id), {}))

    async def list_related(self, entity, record_id, link, select=None, max_size=50):
        return {"list": list(self.related.get((entity, record_id, link), []))}

    async def metadata(self, key):
        # key = "entityDefs.{entity}.fields"
        entity = key.split(".")[1]
        return dict(self.fields.get(entity, {}))

    async def update(self, entity, record_id, payload):
        self.records.setdefault((entity, record_id), {}).update(payload)
        self.updates.append((entity, record_id, dict(payload)))
        return {"id": record_id}


class GrantDrive:
    """Drive stub: folder permissions + file metadata/moves + folders."""

    def __init__(self):
        self.mailbox = "the application"
        self.drive_id = "drv1"
        self.perms: dict[str, list[dict]] = {}  # folder -> permissions
        self.files: dict[str, dict] = {}  # file_id -> {parents, webViewLink}
        self.folders: dict[tuple[str, str], str] = {}
        self.created_folders: list[tuple[str, str]] = []
        self.grant_calls: list[tuple[str, str, str]] = []
        self.revoke_calls: list[tuple[str, str]] = []
        self.moves: list[tuple[str, str, list]] = []
        self._next_perm = 0

    async def list_permissions(self, file_id):
        return [dict(p) for p in self.perms.get(file_id, [])]

    async def create_permission(self, file_id, email, role="commenter"):
        self._next_perm += 1
        perm = {"id": f"p{self._next_perm}", "type": "user", "role": role,
                "emailAddress": email, "inherited": False}
        self.perms.setdefault(file_id, []).append(perm)
        self.grant_calls.append((file_id, email, role))
        return perm

    async def delete_permission(self, file_id, permission_id):
        self.perms[file_id] = [
            p for p in self.perms.get(file_id, []) if p["id"] != permission_id
        ]
        self.revoke_calls.append((file_id, permission_id))

    async def get_file(self, file_id, fields="id"):
        return dict(self.files.get(file_id, {"id": file_id}))

    async def move_file(self, file_id, add_parent, remove_parents):
        self.moves.append((file_id, add_parent, list(remove_parents)))
        self.files.setdefault(file_id, {})["parents"] = [add_parent]

    async def find_child_folder(self, parent_id, name):
        return self.folders.get((parent_id, name))

    async def create_folder(self, parent_id, name):
        folder_id = f"sub{len(self.created_folders) + 1}"
        self.folders[(parent_id, name)] = folder_id
        self.created_folders.append((parent_id, name))
        return folder_id


def _perm(email, role="commenter", inherited=False, ptype="user", pid=None):
    return {"id": pid or f"perm-{email}-{role}", "type": ptype, "role": role,
            "emailAddress": email, "inherited": inherited}


# --- grants_enabled gate -----------------------------------------------------------


def test_grants_enabled_only_under_service_identity():
    assert grants.grants_enabled(_settings())
    assert not grants.grants_enabled(_settings(gdrive_identity="user"))
    assert not grants.grants_enabled(_settings(gdrive_docs=False))
    assert not grants.grants_enabled(_settings(gdrive_shared_drive_id=""))
    assert not grants.grants_enabled(_settings(espo_dry_run=True))
    assert not grants.grants_enabled(_settings(espo_api_key=""))


# --- entitlement derivation --------------------------------------------------------


async def test_entitled_engagement_mentor_and_comentors():
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": "MP1"}
    espo.records[("CMentorProfile", "MP1")] = {"cbmEmail": "Jane.Smith@cbmentors.org"}
    espo.related[("CEngagement", "E1", "additionalMentors")] = [
        {"cbmEmail": "bob.jones@cbmentors.org"},
        {"cbmEmail": ""},  # co-mentor without a CBM address — skipped
    ]
    emails = await grants.entitled_emails(espo, "CEngagement", "E1")
    assert emails == {"jane.smith@cbmentors.org", "bob.jones@cbmentors.org"}


async def test_entitled_partner_and_sponsor_manager():
    espo = FakeEspo()
    espo.records[("CPartnerProfile", "P1")] = {"partnerManagerId": "MP1"}
    espo.records[("CSponsorProfile", "S1")] = {"cBMSponsorManagerId": "MP2"}
    espo.records[("CMentorProfile", "MP1")] = {"cbmEmail": "pm@cbmentors.org"}
    espo.records[("CMentorProfile", "MP2")] = {"cbmEmail": "sm@cbmentors.org"}
    assert await grants.entitled_emails(espo, "CPartnerProfile", "P1") == {
        "pm@cbmentors.org"
    }
    assert await grants.entitled_emails(espo, "CSponsorProfile", "S1") == {
        "sm@cbmentors.org"
    }


async def test_entitled_contact_folders_are_application_only():
    """Mentor personnel folders are granted to NO ONE (D-09)."""
    espo = FakeEspo()
    espo.records[("Contact", "C1")] = {"name": "Jane Smith"}
    assert await grants.entitled_emails(espo, "Contact", "C1") == set()


async def test_entitled_unassigned_records_grant_nobody():
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": None}
    espo.records[("CPartnerProfile", "P1")] = {}
    assert await grants.entitled_emails(espo, "CEngagement", "E1") == set()
    assert await grants.entitled_emails(espo, "CPartnerProfile", "P1") == set()


# --- grant application (the diff) --------------------------------------------------


async def test_apply_grants_adds_missing_commenters():
    drive = GrantDrive()
    result = await grants.apply_folder_grants(
        drive, "f1", {"jane@cbmentors.org", "bob@cbmentors.org"}
    )
    assert sorted(result["added"]) == ["bob@cbmentors.org", "jane@cbmentors.org"]
    assert result["removed"] == [] and result["errors"] == []
    assert all(role == "commenter" for _, _, role in drive.grant_calls)


async def test_apply_grants_removes_unjustified_and_keeps_entitled():
    drive = GrantDrive()
    drive.perms["f1"] = [
        _perm("jane@cbmentors.org"),                 # entitled, correct — kept
        _perm("intruder@cbmentors.org"),             # not entitled — removed
    ]
    result = await grants.apply_folder_grants(drive, "f1", {"jane@cbmentors.org"})
    assert result["added"] == []
    assert result["removed"] == [
        {"email": "intruder@cbmentors.org", "role": "commenter"}
    ]
    emails = {p["emailAddress"] for p in drive.perms["f1"]}
    assert emails == {"jane@cbmentors.org"}


async def test_apply_grants_corrects_wrong_role_to_commenter():
    """An entitled person holding writer (hand-granted in the console) is
    downgraded — Editor would let them bypass the app's index."""
    drive = GrantDrive()
    drive.perms["f1"] = [_perm("jane@cbmentors.org", role="writer")]
    result = await grants.apply_folder_grants(drive, "f1", {"jane@cbmentors.org"})
    assert result["removed"] == [{"email": "jane@cbmentors.org", "role": "writer"}]
    assert result["added"] == ["jane@cbmentors.org"]
    assert drive.perms["f1"][0]["role"] == "commenter"


async def test_apply_grants_never_touches_inherited():
    drive = GrantDrive()
    drive.perms["f1"] = [
        _perm("sa@project.iam.gserviceaccount.com", role="organizer", inherited=True),
    ]
    result = await grants.apply_folder_grants(drive, "f1", set())
    assert result["removed"] == [] and drive.revoke_calls == []


async def test_apply_grants_revokes_noninherited_nonuser_grants():
    """Review docs-F9: a console-added domain/group/anyone share is never
    justified by the access model (the CRM entitles individual people only) —
    it must be revoked like any stray grant, not silently kept forever."""
    drive = GrantDrive()
    drive.perms["f1"] = [
        _perm("sa@project.iam.gserviceaccount.com", role="organizer", inherited=True),
        _perm("", role="reader", ptype="domain", pid="dom1"),
        _perm("", role="reader", ptype="anyone", pid="any1"),
    ]
    result = await grants.apply_folder_grants(drive, "f1", set())
    # The inherited membership stays; both org-wide shares are revoked.
    assert ("f1", "dom1") in drive.revoke_calls
    assert ("f1", "any1") in drive.revoke_calls
    assert {r["email"] for r in result["removed"]} == {"domain:domain", "anyone:anyone"}


async def test_apply_grants_tolerates_per_grant_failures():
    class FlakyDrive(GrantDrive):
        async def create_permission(self, file_id, email, role="commenter"):
            if email.startswith("bad"):
                raise RuntimeError("not a Workspace user")
            return await super().create_permission(file_id, email, role)

    drive = FlakyDrive()
    result = await grants.apply_folder_grants(
        drive, "f1", {"bad@example.com", "jane@cbmentors.org"}
    )
    assert result["added"] == ["jane@cbmentors.org"]
    assert len(result["errors"]) == 1 and "bad@example.com" in result["errors"][0]


# --- sync_record_grants ------------------------------------------------------------


async def test_sync_record_grants_noop_when_disabled():
    assert (
        await grants.sync_record_grants(
            _settings(gdrive_identity="user"), "CEngagement", "E1", folder_id="f1"
        )
        is None
    )


async def test_sync_record_grants_applies_derived_set():
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": "MP1"}
    espo.records[("CMentorProfile", "MP1")] = {"cbmEmail": "jane@cbmentors.org"}
    drive = GrantDrive()
    result = await grants.sync_record_grants(
        _settings(), "CEngagement", "E1", folder_id="f1", espo=espo, drive=drive
    )
    assert result["added"] == ["jane@cbmentors.org"]


async def test_sync_record_grants_safe_swallows_failures():
    class BoomEspo(FakeEspo):
        async def get(self, *a, **k):
            raise RuntimeError("CRM down")

    drive = GrantDrive()
    result = await grants.sync_record_grants_safe(
        _settings(), "CEngagement", "E1", folder_id="f1", espo=BoomEspo(), drive=drive
    )
    assert result is None  # logged, never raised


# --- nightly reconciliation --------------------------------------------------------


async def test_reconciliation_corrects_both_directions_and_alerts_removals():
    store = MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "fE1"}
    )
    await store.insert_document(
        {"drive_file_id": "b", "entity_type": "Contact", "record_id": "C1",
         "original_filename": "resume.pdf", "drive_folder_id": "fC1"}
    )
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": "MP1"}
    espo.records[("CMentorProfile", "MP1")] = {"cbmEmail": "jane@cbmentors.org"}
    espo.records[("Contact", "C1")] = {"name": "Bob"}
    drive = GrantDrive()
    # drift both ways: E1 lacks jane; C1 (a personnel folder) has a stray grant
    drive.perms["fC1"] = [_perm("nosy@cbmentors.org")]
    alerts: list[str] = []

    async def send(text):
        alerts.append(text)

    summary = await run_docs_reconciliation(
        _settings(), store=store, espo=espo, drive=drive, send=send
    )
    assert summary["folders"] == 2
    assert summary["granted"] == 1 and summary["revoked"] == 1
    assert {p["emailAddress"] for p in drive.perms["fE1"]} == {"jane@cbmentors.org"}
    assert drive.perms["fC1"] == []
    assert len(alerts) == 1 and "nosy@cbmentors.org" in alerts[0]


async def test_reconciliation_folder_failure_never_stops_the_pass():
    store = MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "fE1"}
    )
    await store.insert_document(
        {"drive_file_id": "b", "entity_type": "CEngagement", "record_id": "E2",
         "original_filename": "y.pdf", "drive_folder_id": "fE2"}
    )

    class HalfBrokenEspo(FakeEspo):
        async def get(self, entity, record_id, select=None):
            if record_id == "E1":
                raise RuntimeError("boom")
            return await super().get(entity, record_id, select)

    espo = HalfBrokenEspo()
    espo.records[("CEngagement", "E2")] = {"mentorProfileId": "MP1"}
    espo.records[("CMentorProfile", "MP1")] = {"cbmEmail": "jane@cbmentors.org"}
    drive = GrantDrive()

    async def send(text): ...

    summary = await run_docs_reconciliation(
        _settings(), store=store, espo=espo, drive=drive, send=send
    )
    assert summary["folders"] == 2
    assert summary["errors"] == 1 and summary["granted"] == 1


async def test_reconciliation_inert_outside_the_access_model():
    assert await run_docs_reconciliation(_settings(gdrive_identity="user")) is None


async def test_reconciliation_rechecks_folder_link_writeback():
    store = MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "fE1"}
    )
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": None}
    espo.fields["CEngagement"] = {"documentsFolderUrl": {"type": "url"}}
    drive = GrantDrive()
    drive.files["fE1"] = {"id": "fE1", "webViewLink": "https://drive.google.com/f/fE1"}

    async def send(text): ...

    summary = await run_docs_reconciliation(
        _settings(), store=store, espo=espo, drive=drive, send=send
    )
    assert summary["linksWritten"] == 1
    assert espo.records[("CEngagement", "E1")]["documentsFolderUrl"] == (
        "https://drive.google.com/f/fE1"
    )


# --- archive / restore (DOC-07) ----------------------------------------------------


async def _seed_doc(store, **overrides):
    values = {
        "drive_file_id": "gfile1", "entity_type": "CEngagement", "record_id": "E1",
        "original_filename": "resume.pdf", "mime_type": "application/pdf",
        "doc_type": "Resume", "drive_folder_id": "fE1",
        "uploaded_at": _dt("2026-07-01"),
    }
    values.update(overrides)
    await store.insert_document(values)
    rows = await store.list_documents(
        values["entity_type"], values["record_id"], include_archived=True
    )
    return next(r for r in rows if r["driveFileId"] == values["drive_file_id"])


async def test_archive_moves_file_then_flips_status():
    store, drive = MemoryDocumentStore(), GrantDrive()
    row = await _seed_doc(store)
    drive.files["gfile1"] = {"id": "gfile1", "parents": ["fE1"]}
    out = await docs_service.archive_document(store, drive, "CEngagement", "E1", row["id"])
    assert out["status"] == "archived"
    # the /_Archived subfolder was created under the record folder and used
    assert drive.created_folders == [("fE1", "_Archived")]
    assert drive.moves == [("gfile1", "sub1", ["fE1"])]
    assert await store.list_documents("CEngagement", "E1") == []
    both = await store.list_documents("CEngagement", "E1", include_archived=True)
    assert [r["status"] for r in both] == ["archived"]


async def test_restore_reverses_archive():
    store, drive = MemoryDocumentStore(), GrantDrive()
    row = await _seed_doc(store, status="archived")
    drive.folders[("fE1", "_Archived")] = "archF"
    drive.files["gfile1"] = {"id": "gfile1", "parents": ["archF"]}
    out = await docs_service.restore_document(store, drive, "CEngagement", "E1", row["id"])
    assert out["status"] == "active"
    assert drive.moves == [("gfile1", "fE1", ["archF"])]
    active = await store.list_documents("CEngagement", "E1")
    assert [r["id"] for r in active] == [row["id"]]


async def test_archive_twice_is_a_readable_error():
    store, drive = MemoryDocumentStore(), GrantDrive()
    row = await _seed_doc(store, status="archived")
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.archive_document(store, drive, "CEngagement", "E1", row["id"])
    assert "already archived" in str(exc.value)
    assert drive.moves == []


async def test_archive_unknown_doc_raises_not_found():
    store, drive = MemoryDocumentStore(), GrantDrive()
    with pytest.raises(docs_service.DocsNotFound):
        await docs_service.archive_document(store, drive, "CEngagement", "E1", "nope")


async def test_archive_rolls_back_move_when_status_flip_fails():
    """Doug's ruling: move first, flip after — a mid-failure moves the file
    back so Drive and metadata are never inconsistent."""

    class FailingStore(MemoryDocumentStore):
        async def set_status(self, doc_id, status):
            raise RuntimeError("db down")

    store, drive = FailingStore(), GrantDrive()
    row = await _seed_doc(store)
    drive.files["gfile1"] = {"id": "gfile1", "parents": ["fE1"]}
    with pytest.raises(docs_service.DocsError):
        await docs_service.archive_document(store, drive, "CEngagement", "E1", row["id"])
    # moved into _Archived, then moved back when the flip failed
    assert drive.moves == [
        ("gfile1", "sub1", ["fE1"]),
        ("gfile1", "fE1", ["sub1"]),
    ]
    both = await store.list_documents("CEngagement", "E1", include_archived=True)
    assert [r["status"] for r in both] == ["active"]  # unchanged


async def test_archive_without_recorded_folder_is_a_readable_error():
    store, drive = MemoryDocumentStore(), GrantDrive()
    row = await _seed_doc(store, drive_folder_id=None)
    with pytest.raises(docs_service.DocsError) as exc:
        await docs_service.archive_document(store, drive, "CEngagement", "E1", row["id"])
    assert "folder" in str(exc.value)


async def test_archive_moves_from_wherever_the_file_sits():
    """A human re-filed the file inside Drive — archive still works: the
    actual parents are read first and used as the move source."""
    store, drive = MemoryDocumentStore(), GrantDrive()
    row = await _seed_doc(store)
    drive.files["gfile1"] = {"id": "gfile1", "parents": ["somewhereElse"]}
    await docs_service.archive_document(store, drive, "CEngagement", "E1", row["id"])
    assert drive.moves == [("gfile1", "sub1", ["somewhereElse"])]


async def test_store_list_include_archived_toggle():
    store = MemoryDocumentStore()
    await _seed_doc(store)
    await _seed_doc(store, drive_file_id="gfile2", status="archived",
                    original_filename="old.pdf", uploaded_at=_dt("2026-07-02"))
    assert len(await store.list_documents("CEngagement", "E1")) == 1
    both = await store.list_documents("CEngagement", "E1", include_archived=True)
    assert [r["filename"] for r in both] == ["old.pdf", "resume.pdf"]


async def test_store_list_folder_records_dedupes():
    store = MemoryDocumentStore()
    await _seed_doc(store)
    await _seed_doc(store, drive_file_id="gfile2", uploaded_at=_dt("2026-07-02"))
    await _seed_doc(store, drive_file_id="gfile3", entity_type="Contact",
                    record_id="C1", drive_folder_id="fC1")
    recs = await store.list_folder_records()
    assert sorted((r["entityType"], r["recordId"], r["driveFolderId"]) for r in recs) == [
        ("CEngagement", "E1", "fE1"),
        ("Contact", "C1", "fC1"),
    ]


# --- CRM link write-back (DOC-08) --------------------------------------------------


async def test_write_back_writes_once_then_idempotent():
    espo, drive = FakeEspo(), GrantDrive()
    espo.fields["CEngagement"] = {"documentsFolderUrl": {"type": "url"}}
    espo.records[("CEngagement", "E1")] = {}
    drive.files["fE1"] = {"id": "fE1", "webViewLink": "https://drive.google.com/f/fE1"}
    link = await docs_service.write_back_folder_link(
        _settings(), drive, "CEngagement", "E1", "fE1", espo=espo
    )
    assert link == "https://drive.google.com/f/fE1"
    assert len(espo.updates) == 1
    # second call: the stored value already matches — no write (DOC-08)
    link = await docs_service.write_back_folder_link(
        _settings(), drive, "CEngagement", "E1", "fE1", espo=espo
    )
    assert link is None and len(espo.updates) == 1


async def test_write_back_inert_until_the_field_is_built():
    """Feature-detection (the googleCalendarEventId precedent): no field in
    the CRM metadata => no read, no write, no error."""
    espo, drive = FakeEspo(), GrantDrive()
    espo.records[("CEngagement", "E1")] = {}
    link = await docs_service.write_back_folder_link(
        _settings(), drive, "CEngagement", "E1", "fE1", espo=espo
    )
    assert link is None and espo.updates == []


async def test_write_back_only_participating_entities():
    espo, drive = FakeEspo(), GrantDrive()
    espo.fields["CPartnerProfile"] = {"documentsFolderUrl": {"type": "url"}}
    link = await docs_service.write_back_folder_link(
        _settings(), drive, "CPartnerProfile", "P1", "fP1", espo=espo
    )
    assert link is None and espo.updates == []


async def test_write_back_skips_dry_run():
    espo, drive = FakeEspo(), GrantDrive()
    link = await docs_service.write_back_folder_link(
        _settings(espo_dry_run=True), drive, "CEngagement", "E1", "fE1", espo=espo
    )
    assert link is None


async def test_post_upload_hooks_never_raise(monkeypatch):
    """Both follow-ups are best-effort by contract — a CRM outage and a Drive
    permission failure must leave the upload's success untouched."""

    async def boom(*a, **k):
        raise RuntimeError("everything is down")

    monkeypatch.setattr(docs_service, "write_back_folder_link", boom)
    monkeypatch.setattr(
        "docs.grants.sync_record_grants", boom
    )
    await docs_service.post_upload_hooks(
        _settings(), GrantDrive(), "CEngagement", "E1",
        {"driveFolderId": "fE1"},
    )
    # no folder id => nothing to do, still no raise
    await docs_service.post_upload_hooks(
        _settings(), GrantDrive(), "CEngagement", "E1", {}
    )


async def test_reconcile_alerts_on_persistent_folder_errors(monkeypatch):
    """docs-F9: a folder that keeps erroring (second consecutive pass) alerts —
    previously only removals alerted, so grant drift could persist silently."""
    from docs import reconcile as rec_mod

    monkeypatch.setattr(rec_mod, "_error_passes", {})

    class ErroringDrive(GrantDrive):
        async def list_permissions(self, file_id):
            raise RuntimeError("permissions API down")

    store = MemoryDocumentStore()
    await store.insert_document(
        {"drive_file_id": "a", "entity_type": "CEngagement", "record_id": "E1",
         "original_filename": "x.pdf", "drive_folder_id": "f1"}
    )
    espo = FakeEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": None}
    sent: list[str] = []

    async def collect(text):
        sent.append(text)

    s = _settings()
    drive = ErroringDrive()
    await rec_mod.run_docs_reconciliation(s, store=store, espo=espo, drive=drive, send=collect)
    assert sent == []  # first pass: a blip, no alert yet
    await rec_mod.run_docs_reconciliation(s, store=store, espo=espo, drive=drive, send=collect)
    assert len(sent) == 1 and "keeps FAILING" in sent[0]
    # third pass: no repeat spam (alerts once at the persistence transition)
    await rec_mod.run_docs_reconciliation(s, store=store, espo=espo, drive=drive, send=collect)
    assert len(sent) == 1
    # recovery clears the counter
    ok_drive = GrantDrive()
    await rec_mod.run_docs_reconciliation(s, store=store, espo=espo, drive=ok_drive, send=collect)
    assert rec_mod._error_passes == {}
