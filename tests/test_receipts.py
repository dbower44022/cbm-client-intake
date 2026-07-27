"""Intake receipts (the 2026-07-27 redesign): the one-vocabulary CRM receipt
engine — expected fields, the sync/adopt/create logic, and the sweep."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core import receipts

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def _row(**over):
    base = {
        "id": "row-1",
        "form_slug": "volunteer",
        "submission_token": "tok-abc",
        "status": "pending",
        "payload": {"email": "jane@x.org", "first_name": "Jane",
                    "submission_token": "tok-abc", "how_did_you_hear": "Friend"},
        "result": None,
        "last_error": None,
        "attempt_count": 0,
        "progress": None,
        "acted_by": None,
        "closed_at": None, "closed_by": None, "close_reason": None, "close_note": None,
        "crm_receipt_id": None,
        "received_at": NOW,
    }
    base.update(over)
    return base


class FakeEspo:
    """Create/update/get/list over an in-memory receipt table."""

    def __init__(self):
        self.records: dict[str, dict] = {}
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        rid = f"r{self._n}"
        self.records[rid] = dict(payload)
        return {"id": rid, **payload}

    async def update(self, entity, rid, payload):
        self.records[rid].update(payload)
        return {"id": rid}

    async def get(self, entity, rid, select=None):
        if rid not in self.records:
            raise RuntimeError("404")
        return {"id": rid, **self.records[rid]}

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        value = (where or [{}])[0].get("value", "")
        attr = (where or [{}])[0].get("attribute", "")
        hits = [
            {"id": rid} for rid, r in self.records.items()
            if value and value in str(r.get(attr) or "")
        ]
        return {"total": len(hits), "list": hits[:max_size]}


class FakeStore:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}

    async def get_submission(self, sid):
        return self.rows.get(sid)

    async def set_receipt_id(self, sid, rid):
        self.rows[sid]["crm_receipt_id"] = rid

    async def list_all_for_receipts(self, *, limit=500, offset=0):
        return list(self.rows.values())[offset:offset + limit]


# --- expected_fields ---------------------------------------------------------

def test_status_vocabulary_mapping():
    for machine, word in [
        ("pending", "Received"), ("processing", "Received"), ("retry", "Received"),
        ("completed", "Completed"), ("needs_attention", "Error"),
        ("held_honeypot", "Held-Spam"), ("held_review", "Held-Email"),
        ("discarded", "Discarded"),
    ]:
        assert receipts.receipt_status(machine) == word


def test_expected_fields_received_form():
    f = receipts.expected_fields(_row())
    assert f["intakeStatus"] == "Received"
    assert f["intakeMessage"] == ""
    assert f["form"] == "volunteer"
    assert f["submitterEmail"] == "jane@x.org"
    assert f["source"] == "Friend"
    assert '"submission_token": "tok-abc"' in f["payload"]
    assert "company_url" not in f["payload"]
    assert "emailLink" not in f and "contactId" not in f


def test_expected_fields_spam_and_form_enum_casing():
    f = receipts.expected_fields(_row(form_slug="partner", status="held_honeypot"))
    assert f["intakeStatus"] == "Held-Spam"
    assert "spam trap was triggered" in f["intakeMessage"]
    assert f["form"] == "Partner"  # the CRM enum's Title-case value


def test_expected_fields_completed_links_contact():
    f = receipts.expected_fields(
        _row(status="completed", result={"contactId": "c9", "profileId": "p1"})
    )
    assert f["intakeStatus"] == "Completed" and f["contactId"] == "c9"


def test_expected_fields_email_carries_content_and_link():
    row = _row(
        form_slug="info-email", status="held_review",
        submission_token="gmail-thread-t77",
        payload={"email": "bob@y.org", "first_name": "Bob", "last_name": "Ray",
                 "subject": "Question", "message": "Hi there",
                 "gmail_thread_id": "t77", "mailbox": "info@cbmentors.org",
                 "email_date": "2026-07-27 10:00:00"},
    )
    f = receipts.expected_fields(row)
    assert f["intakeStatus"] == "Held-Email"
    assert f["intakeMessage"] == "All emails need review"
    assert f["form"] == "Email"
    for fragment in ("bob@y.org", "Subject: Question", "Hi there",
                     "Reference token: gmail-thread-t77"):
        assert fragment in f["payload"]
    assert f["emailLink"].endswith("#all/t77")


def test_expected_fields_error_message_is_specific():
    row = _row(
        status="needs_attention", attempt_count=3,
        last_error="create Contact failed: HTTP 400 validationFailure phoneNumber valid",
        progress={"create:Account:0": "a1"},
    )
    f = receipts.expected_fields(row)
    assert f["intakeStatus"] == "Error"
    msg = f["intakeMessage"]
    assert "could NOT be processed" in msg
    assert "3 delivery attempt(s)" in msg
    assert "validationFailure" in msg          # the CRM's own words
    assert "create:Account:0" in msg           # what already exists
    assert "Re-drive" in msg                   # the fix path


def test_expected_fields_discarded_carries_the_business_decision():
    f = receipts.expected_fields(_row(
        status="discarded", acted_by="anita",
        closed_at=NOW, closed_by="anita", close_reason="Spam", close_note="bot",
    ))
    assert f["intakeStatus"] == "Discarded"
    assert f["dispositionedBy"] == "anita"
    assert f["dispositionedAt"] == "2026-07-27 12:00:00"
    assert f["dispositionReason"] == "Spam — bot"


def test_discarded_before_the_redesign_gets_the_migration_reason():
    f = receipts.expected_fields(_row(status="discarded", acted_by="old-admin"))
    assert f["dispositionedBy"] == "old-admin"
    assert "predates disposition reasons" in f["dispositionReason"]


# --- sync_row ----------------------------------------------------------------

@pytest.mark.anyio
async def test_sync_creates_and_links():
    espo, row = FakeEspo(), _row()
    store = FakeStore([row])
    assert await receipts.sync_row(espo, store, row) == "created"
    assert row["crm_receipt_id"] == "r1"
    assert espo.records["r1"]["intakeStatus"] == "Received"
    # Second pass: no drift, no write.
    assert await receipts.sync_row(espo, store, row) == "ok"


@pytest.mark.anyio
async def test_sync_updates_on_status_change():
    espo, row = FakeEspo(), _row()
    store = FakeStore([row])
    await receipts.sync_row(espo, store, row)
    row.update(status="completed", result={"contactId": "c1"})
    assert await receipts.sync_row(espo, store, row) == "updated"
    assert espo.records["r1"]["intakeStatus"] == "Completed"
    assert espo.records["r1"]["contactId"] == "c1"


@pytest.mark.anyio
async def test_sync_adopts_existing_receipt_by_token():
    """A receipt written before the row was linked (or by the historical
    migration) is ADOPTED, never duplicated."""
    espo, row = FakeEspo(), _row()
    espo.records["old1"] = {"payload": 'x "submission_token": "tok-abc" y',
                            "intakeStatus": "Received"}
    store = FakeStore([row])
    assert await receipts.sync_row(espo, store, row) == "updated"
    assert row["crm_receipt_id"] == "old1"
    assert len(espo.records) == 1  # no second receipt


@pytest.mark.anyio
async def test_sync_recreates_when_linked_receipt_was_deleted():
    espo, row = FakeEspo(), _row(crm_receipt_id="gone")
    store = FakeStore([row])
    assert await receipts.sync_row(espo, store, row) == "created"
    assert row["crm_receipt_id"] == "r1"


@pytest.mark.anyio
async def test_sync_extra_carries_action_time_disposition():
    espo, row = FakeEspo(), _row()
    store = FakeStore([row])
    await receipts.sync_row(
        espo, store, row,
        extra={"dispositionedBy": "Jane Staff", "dispositionedAt": "2026-07-27 12:00:00"},
    )
    assert espo.records["r1"]["dispositionedBy"] == "Jane Staff"


@pytest.mark.anyio
async def test_sync_never_raises():
    class Broken:
        async def create(self, *a, **k):
            raise RuntimeError("CRM down")

    row = _row()
    assert await receipts.sync_row(Broken(), FakeStore([row]), row) == "failed"


# --- the sweep ---------------------------------------------------------------

@pytest.mark.anyio
async def test_sweep_converges_everything():
    rows = [
        _row(id="a", status="completed", result={"contactId": "c1"}),
        _row(id="b", submission_token="tok-b", status="discarded",
             closed_at=NOW, closed_by="anita", close_reason="Spam"),
        _row(id="c", submission_token="tok-c"),
    ]
    espo, store = FakeEspo(), FakeStore(rows)
    from core.config import Settings

    stats = await receipts.run_receipt_sweep(espo, store, Settings())
    assert stats["checked"] == 3 and stats["created"] == 3 and stats["failed"] == 0
    # Second pass: everything matches — zero writes.
    stats2 = await receipts.run_receipt_sweep(espo, store, Settings())
    assert stats2["ok"] == 3 and stats2["created"] == 0 and stats2["updated"] == 0
    statuses = sorted(r["intakeStatus"] for r in espo.records.values())
    assert statuses == ["Completed", "Discarded", "Received"]
