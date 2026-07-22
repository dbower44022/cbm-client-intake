"""V2 Phase 2: the ops console router — auth gating, list, re-drive."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request

_USER = {"userName": "staffer", "name": "Staff Person", "isAdmin": True,
         "userId": "u-staff", "token": "tok-staff"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeOpsStore:
    def __init__(self):
        self.rows = {
            "abc12345": {
                "id": "abc12345", "form_slug": "info-request", "status": "needs_attention",
                "attempt_count": 2, "last_error": "boom", "email": "a@b.com",
                "payload": {"first_name": "Ada", "email": "a@b.com"},
                "progress": None, "result": None, "thread_ids": None,
            }
        }
        self.redriven = []
        self.anchored = []

    async def list_submissions(self, *, status=None, form=None, limit=200):
        rows = list(self.rows.values())
        if status:
            rows = [r for r in rows if r["status"] == status]
        if form:
            rows = [r for r in rows if r["form_slug"] == form]
        return rows

    async def get_submission(self, submission_id):
        return self.rows.get(submission_id)

    async def counts_by_status(self):
        return {"needs_attention": 1}

    async def redrive(self, submission_id, *, acted_by=None):
        if submission_id in self.rows:
            self.redriven.append((submission_id, acted_by))
            return True
        return False

    async def discard(self, submission_id, *, acted_by=None):
        row = self.rows.get(submission_id)
        if row is None or row["status"] == "completed":
            return False
        row["status"] = "discarded"
        row["acted_by"] = acted_by
        return True

    async def set_notes(self, submission_id, notes, *, acted_by=None):
        row = self.rows.get(submission_id)
        if row is None:
            return False
        row["notes"] = notes
        row["acted_by"] = acted_by
        return True

    async def set_resolved(self, submission_id, resolved, *, acted_by=None):
        row = self.rows.get(submission_id)
        if row is None:
            return False
        row["resolved_at"] = "2026-07-19 12:00:00" if resolved else None
        row["resolved_by"] = acted_by if resolved else None
        return True

    async def set_request_status(self, submission_id, request_status, *, acted_by=None):
        row = self.rows.get(submission_id)
        if row is None:
            return False
        row["request_status"] = request_status
        row["acted_by"] = acted_by
        return True

    async def add_thread_id(self, submission_id, thread_id):
        row = self.rows.get(submission_id)
        if row is None:
            return False
        threads = list(row.get("thread_ids") or [])
        if thread_id not in threads:
            threads.append(thread_id)
        row["thread_ids"] = threads
        self.anchored.append((submission_id, thread_id))
        return True

    async def metrics(self):
        return {"counts": {"needs_attention": 1}, "needsAttention": 1,
                "backlog": 0, "oldestPendingAgeSeconds": None, "avgLatencySeconds": None}


def _app(monkeypatch, store):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables session + ops router
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.submission_store = store
    return app


def _authed(monkeypatch):
    monkeypatch.setattr("ops.router.current_user", lambda request: _USER)


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        assert c.get("/ops/api/submissions").status_code == 401


def test_gated_to_marketing_admin_team(monkeypatch):
    """/ops has its own request-time gate (Marketing Admin Team by default) —
    membership in the other staff teams is not enough."""
    outsider = {"userName": "cc", "name": "C", "isAdmin": False,
                "teams": ["Client Administration Team"], "roles": []}
    monkeypatch.setattr("ops.router.current_user", lambda request: outsider)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        r = c.get("/ops/api/submissions")
    assert r.status_code == 403
    assert "Marketing Admin Team" in r.json()["detail"]

    member = dict(outsider, teams=["Marketing Admin Team"])
    monkeypatch.setattr("ops.router.current_user", lambda request: member)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        assert c.get("/ops/api/submissions").status_code == 200


def test_lists_submissions_and_counts(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions").json()
    assert data["counts"] == {"needs_attention": 1}
    assert [r["id"] for r in data["submissions"]] == ["abc12345"]


def test_503_when_store_not_configured(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, None)) as c:
        assert c.get("/ops/api/submissions").status_code == 503


def test_redrive(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.post("/ops/api/submissions/abc12345/redrive")
        missing = c.post("/ops/api/submissions/nope/redrive")
    assert ok.status_code == 200 and ok.json()["status"] == "requeued"
    # P1-11: the acting username is recorded on the row.
    assert store.redriven == [("abc12345", _USER["userName"])]
    assert missing.status_code == 404


def test_discard(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.post("/ops/api/submissions/abc12345/discard")
        missing = c.post("/ops/api/submissions/nope/discard")
    assert ok.status_code == 200 and ok.json()["status"] == "discarded"
    assert store.rows["abc12345"]["status"] == "discarded"
    assert missing.status_code == 404


def test_detail(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        d = c.get("/ops/api/submissions/abc12345").json()
    assert d["payload"]["first_name"] == "Ada"
    assert d["status"] == "needs_attention"


def test_metrics(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        m = c.get("/ops/api/metrics").json()
    assert m["needsAttention"] == 1 and "backlog" in m


def test_session_carries_crm_url_and_comms_flag(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        data = c.get("/ops/api/session").json()
    assert "crmUrl" in data
    assert data["commsEnabled"] is False  # gmail off in tests


def test_save_notes(monkeypatch):
    """Staff triage notes (Submission Admin rebuild): stored with acted_by."""
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.put("/ops/api/submissions/abc12345/notes", json={"notes": "called them"})
        missing = c.put("/ops/api/submissions/nope/notes", json={"notes": "x"})
    assert ok.status_code == 200
    assert store.rows["abc12345"]["notes"] == "called them"
    assert store.rows["abc12345"]["acted_by"] == _USER["userName"]
    assert missing.status_code == 404


def test_messages_degrade_readably(monkeypatch):
    """The conversation endpoint degrades to a reason (never a 500): gmail off
    on this deployment, and a submission with no submitter email."""
    store = FakeOpsStore()
    store.rows["noemail01"] = {
        "id": "noemail01", "form_slug": "info-request", "status": "completed",
        "attempt_count": 1, "last_error": None, "email": None,
        "payload": {"first_name": "Nan"}, "progress": None, "result": None,
    }
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        off = c.get("/ops/api/submissions/abc12345/messages").json()
        noaddr = c.get("/ops/api/submissions/noemail01/messages").json()
        missing = c.get("/ops/api/submissions/nope/messages")
    assert off["messages"] == [] and "enabled" in off["reason"]
    assert noaddr["messages"] == [] and "no submitter email" in noaddr["reason"]
    assert missing.status_code == 404


def test_resolve_and_reopen(monkeypatch):
    """The staff resolution marker: resolved_at/resolved_by set and cleared,
    independent of the delivery status."""
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.put("/ops/api/submissions/abc12345/resolved", json={"resolved": True})
        assert ok.status_code == 200 and ok.json()["resolved"] is True
        assert store.rows["abc12345"]["resolved_by"] == _USER["userName"]
        assert store.rows["abc12345"]["resolved_at"] is not None
        undo = c.put("/ops/api/submissions/abc12345/resolved", json={"resolved": False})
        assert undo.status_code == 200
        assert store.rows["abc12345"]["resolved_at"] is None
        missing = c.put("/ops/api/submissions/nope/resolved", json={"resolved": True})
        assert missing.status_code == 404


def test_set_request_status(monkeypatch):
    """The staff request status (New/In Progress/Responded/Closed): stored with
    acted_by; bad values 422 with the vocabulary named; unknown id 404. No
    CInformationRequest on the row = app-only save (no crmUpdated)."""
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.put("/ops/api/submissions/abc12345/requeststatus",
                   json={"status": "In Progress"})
        bad = c.put("/ops/api/submissions/abc12345/requeststatus",
                    json={"status": "Sideways"})
        missing = c.put("/ops/api/submissions/nope/requeststatus",
                        json={"status": "Closed"})
    assert ok.status_code == 200
    assert ok.json()["requestStatus"] == "In Progress"
    assert "crmUpdated" not in ok.json() and "crmWarning" not in ok.json()
    assert store.rows["abc12345"]["request_status"] == "In Progress"
    assert store.rows["abc12345"]["acted_by"] == _USER["userName"]
    assert bad.status_code == 422 and "Responded" in bad.json()["detail"]
    assert missing.status_code == 404


class _FakeCrm:
    def __init__(self, fail=False):
        self.fail = fail
        self.updates = []
        self.creates = []

    async def update(self, entity, record_id, payload):
        if self.fail:
            from core.espo import EspoError
            raise EspoError("update CInformationRequest: 403 Forbidden")
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}

    async def create(self, entity, payload):  # stream note from record_action
        self.creates.append((entity, payload))
        return {"id": "note1"}


def test_request_status_writes_through_to_crm(monkeypatch):
    """When the delivery created a CInformationRequest, its requestStatus is
    written too (via the API-key client) so the CRM worklist stays in step."""
    store = FakeOpsStore()
    store.rows["abc12345"]["result"] = {"informationRequestId": "ir-77"}
    crm = _FakeCrm()
    monkeypatch.setattr("ops.router._api_client", lambda: crm)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        r = c.put("/ops/api/submissions/abc12345/requeststatus",
                  json={"status": "Responded"})
    assert r.status_code == 200 and r.json().get("crmUpdated") is True
    assert crm.updates == [("CInformationRequest", "ir-77", {"requestStatus": "Responded"})]
    assert store.rows["abc12345"]["request_status"] == "Responded"


def test_request_status_crm_failure_keeps_app_save(monkeypatch):
    """A CRM rejection never loses the app-side save — the response carries a
    readable crmWarning instead of an error status."""
    store = FakeOpsStore()
    store.rows["abc12345"]["result"] = {"informationRequestId": "ir-77"}
    monkeypatch.setattr("ops.router._api_client", lambda: _FakeCrm(fail=True))
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        r = c.put("/ops/api/submissions/abc12345/requeststatus",
                  json={"status": "Closed"})
    assert r.status_code == 200
    assert "couldn't be updated" in r.json()["crmWarning"]
    assert store.rows["abc12345"]["request_status"] == "Closed"


def test_reply_states_empty_when_gmail_off(monkeypatch):
    """The awaiting-reply column degrades to an empty map (never an error)
    when the deployment has no Gmail integration."""
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        r = c.post("/ops/api/replystates", json={"ids": ["abc12345"]})
    assert r.status_code == 200
    assert r.json() == {"states": {}}


def test_session_carries_reply_template(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        data = c.get("/ops/api/session").json()
    assert data["replyTemplate"] == "InfoRequestReply"


# --- shared info@ mailbox mode (OPS_MAILBOX, v0.110.0) ----------------------

_MAILBOX = "info@cbmentors.org"


def _b64(text):
    import base64
    return base64.urlsafe_b64encode(text.encode()).decode()


def _raw_msg(msg_id, thread_id, frm, *, subject="Hello", body="hi",
             internal="1753000000000", labels=("INBOX",)):
    return {
        "id": msg_id, "threadId": thread_id, "labelIds": list(labels),
        "internalDate": internal, "snippet": body,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": frm},
                {"name": "To", "value": _MAILBOX},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{msg_id}@mail.test>"},
            ],
            "body": {"data": _b64(body)},
        },
    }


class FakeSharedGmail:
    def __init__(self, threads):
        self.mailbox = _MAILBOX
        self._threads = threads

    async def get_thread(self, thread_id, *, headers_only=False):
        return self._threads[thread_id]

    async def aclose(self):
        pass


def _shared_env(monkeypatch, gmail):
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("OPS_MAILBOX", _MAILBOX)

    async def fake(settings, mailbox):
        assert mailbox == _MAILBOX
        return gmail

    monkeypatch.setattr("comms.service.gmail_for_shared_mailbox", fake)


def test_shared_conversation_shows_only_anchored_threads(monkeypatch):
    """With OPS_MAILBOX set, the conversation is exactly the submission's
    anchored threads — a submitter's unrelated mail can't appear because no
    address search happens at all."""
    store = FakeOpsStore()
    store.rows["abc12345"]["thread_ids"] = ["t1"]
    gmail = FakeSharedGmail({
        "t1": {"messages": [
            _raw_msg("m1", "t1", "Ada <a@b.com>", internal="1753000000000"),
            _raw_msg("m2", "t1", f"CBM Info <{_MAILBOX}>", internal="1753000600000"),
        ]},
    })
    _shared_env(monkeypatch, gmail)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions/abc12345/messages").json()
    assert data["mailbox"] == _MAILBOX
    assert len(data["messages"]) == 2
    by_id = {m["id"]: m for m in data["messages"]}
    assert by_id["m1"]["direction"] == "received"
    assert by_id["m2"]["direction"] == "sent"  # written by the shared mailbox
    # newest first
    assert [m["id"] for m in data["messages"]] == ["m2", "m1"]


def test_shared_conversation_without_anchor_names_the_reason(monkeypatch):
    store = FakeOpsStore()
    _shared_env(monkeypatch, FakeSharedGmail({}))
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions/abc12345/messages").json()
    assert data["messages"] == []
    assert "No conversation" in data["reason"] and _MAILBOX in data["reason"]


def test_shared_conversation_uses_payload_origin_thread(monkeypatch):
    """An email-originated submission carries its inbound thread in the
    payload — the conversation shows it even before any staff reply."""
    store = FakeOpsStore()
    store.rows["em1"] = {
        "id": "em1", "form_slug": "info-email", "status": "held_review",
        "attempt_count": 0, "last_error": None, "email": "j@x.test",
        "payload": {"email": "j@x.test", "gmail_thread_id": "t-in"},
        "progress": None, "result": None, "thread_ids": None,
    }
    gmail = FakeSharedGmail({
        "t-in": {"messages": [_raw_msg("m1", "t-in", "J <j@x.test>")]},
    })
    _shared_env(monkeypatch, gmail)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions/em1/messages").json()
    assert [m["id"] for m in data["messages"]] == ["m1"]
    assert data["messages"][0]["direction"] == "received"


def test_shared_mailbox_endpoint_reports_info_identity(monkeypatch):
    """GET /ops/api/mailbox in shared mode: the info@ identity, no personal
    signature (the recipient sees the organization name, not a staffer's sign-off)."""
    _shared_env(monkeypatch, FakeSharedGmail({}))
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        data = c.get("/ops/api/mailbox").json()
    assert data["mailbox"] == _MAILBOX
    assert data["sendEnabled"] is True
    assert data["signature"] == ""


def test_send_anchors_thread_to_submission(monkeypatch):
    """POST /ops/api/sendmail with submissionId: sends as the shared mailbox
    and records the resulting Gmail thread on the submission."""
    store = FakeOpsStore()
    _shared_env(monkeypatch, FakeSharedGmail({}))
    _authed(monkeypatch)
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)
        return {"gmailMessageId": "m9", "gmailThreadId": "t9",
                "writeBack": {"ok": True, "emailId": ""}}

    monkeypatch.setattr("comms.service.send_quick_message", fake_send)
    with TestClient(_app(monkeypatch, store)) as c:
        r = c.post("/ops/api/sendmail", json={
            "to": ["a@b.com"], "subject": "Hi", "body": "<p>hello</p>",
            "submissionId": "abc12345",
        })
    assert r.status_code == 200
    assert r.json()["gmailThreadId"] == "t9"
    assert sent["gmail"].mailbox == _MAILBOX
    assert sent["sender_name"] == "Cleveland Business Mentors"
    assert store.anchored == [("abc12345", "t9")]
    assert store.rows["abc12345"]["thread_ids"] == ["t9"]


def test_replystates_shared_mode_reads_anchored_threads(monkeypatch):
    """owed = the newest message on the submission's threads wasn't ours;
    waiting = it was; none = nothing anchored yet."""
    store = FakeOpsStore()
    store.rows["abc12345"]["thread_ids"] = ["t1"]
    store.rows["w1"] = dict(store.rows["abc12345"], id="w1", thread_ids=["t2"])
    store.rows["n1"] = dict(store.rows["abc12345"], id="n1", thread_ids=None)
    gmail = FakeSharedGmail({
        "t1": {"messages": [
            _raw_msg("m1", "t1", f"CBM Info <{_MAILBOX}>", internal="1"),
            _raw_msg("m2", "t1", "Ada <a@b.com>", internal="2"),
        ]},
        "t2": {"messages": [
            _raw_msg("m3", "t2", "Ada <a@b.com>", internal="1"),
            _raw_msg("m4", "t2", f"CBM Info <{_MAILBOX}>", internal="2"),
        ]},
    })
    _shared_env(monkeypatch, gmail)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        r = c.post("/ops/api/replystates", json={"ids": ["abc12345", "w1", "n1"]})
    states = r.json()["states"]
    assert states["abc12345"]["state"] == "owed"
    assert states["w1"]["state"] == "waiting"
    assert states["n1"]["state"] == "none"


def test_lifetime_query_time_boxes_legacy_search():
    """Without OPS_MAILBOX the per-admin search is bounded to the submission's
    lifetime: after received_at, and (once resolved) before resolved + grace."""
    from datetime import datetime, timezone

    from ops.router import _lifetime_query

    received = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    resolved = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    open_q = _lifetime_query("a@b.com", {"received_at": received})
    assert open_q.startswith("(from:a@b.com OR to:a@b.com)")
    assert f"after:{int(received.timestamp())}" in open_q
    assert "before:" not in open_q
    closed_q = _lifetime_query(
        "a@b.com", {"received_at": received, "resolved_at": resolved}
    )
    assert f"before:{int(resolved.timestamp()) + 2 * 86400}" in closed_q


# --- bounce visibility (info@ rollout Phase 4 follow-up, 2026-07-21) ---------
# A bounced reply threads with the original send; unclassified it reads as an
# ordinary received message and the admin believes the reply was delivered.


def test_looks_like_bounce_classifier():
    from core.gmail import looks_like_bounce

    assert looks_like_bounce("mailer-daemon@googlemail.com", "")
    assert looks_like_bounce("MAILER-DAEMON@x.test", "anything")
    assert looks_like_bounce("postmaster@corp.test", "")
    assert looks_like_bounce("odd@mta.test", "Undeliverable: Hello")
    assert looks_like_bounce("odd@mta.test", "Delivery Status Notification (Failure)")
    assert not looks_like_bounce("ada@b.com", "Re: Hello")
    assert not looks_like_bounce("info@cbmentors.org", "Following up")


def test_shared_conversation_marks_bounce_messages(monkeypatch):
    store = FakeOpsStore()
    store.rows["abc12345"]["thread_ids"] = ["t1"]
    gmail = FakeSharedGmail({
        "t1": {"messages": [
            _raw_msg("m1", "t1", f"CBM Info <{_MAILBOX}>", internal="1753000000000"),
            _raw_msg(
                "m2", "t1", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                subject="Delivery Status Notification (Failure)",
                body="Address not found", internal="1753000600000",
            ),
        ]},
    })
    _shared_env(monkeypatch, gmail)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions/abc12345/messages").json()
    by_id = {m["id"]: m for m in data["messages"]}
    assert by_id["m2"]["bounce"] is True
    assert by_id["m2"]["direction"] == "received"
    assert by_id["m1"]["bounce"] is False  # our own send never marks


def test_replystates_bounced_when_newest_is_a_bounce(monkeypatch):
    store = FakeOpsStore()
    store.rows["abc12345"]["thread_ids"] = ["t1"]
    gmail = FakeSharedGmail({
        "t1": {"messages": [
            _raw_msg("m1", "t1", f"CBM Info <{_MAILBOX}>", internal="1"),
            _raw_msg(
                "m2", "t1", "mailer-daemon@googlemail.com",
                subject="Delivery Status Notification (Failure)", internal="2",
            ),
        ]},
    })
    _shared_env(monkeypatch, gmail)
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        r = c.post("/ops/api/replystates", json={"ids": ["abc12345"]})
    assert r.json()["states"]["abc12345"]["state"] == "bounced"
