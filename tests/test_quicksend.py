"""Quick-send email endpoints on the staff tools (comms/quicksend.py):
GET /mailbox + POST /sendmail behind each app's own gate, backing the
shared compose widget that replaces mailto: links product-wide."""

from __future__ import annotations

from fastapi.testclient import TestClient

from comms import service as comms_service
from core.app import create_app
from core.config import get_settings
from forms import info_request

# Admin passes both apps' team gates without team membership.
_USER = {
    "userId": "u1",
    "userName": "staff.admin",
    "name": "Staff Admin",
    "isAdmin": True,
    "teams": [],
    "roles": [],
    "token": "t",
}


def _app(monkeypatch, gmail_sync: bool):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user=_USER, signature=""):
    # assignments calls auth.current_user; mentoradmin imported the name.
    monkeypatch.setattr("assignments.auth.current_user", lambda request, key=None: user)
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: user)

    # /mailbox reads the user's Preferences signature — keep it off the network.
    async def fake_signature(client, user_id):
        return signature

    monkeypatch.setattr(comms_service, "user_signature", fake_signature)


class FakeGmail:
    mailbox = "staff.admin@cbmentors.org"

    def __init__(self):
        self.sent = []
        self.thread_ids = []

    async def send(self, mime, thread_id=None):
        self.sent.append(mime)
        self.thread_ids.append(thread_id)
        return {"id": "gm-1"}


def test_mailbox_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        assert c.get("/assignments/api/mailbox").status_code == 401
        assert c.get("/mentoradmin/api/mailbox").status_code == 401


def test_mailbox_reports_disabled_when_gmail_sync_off(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        for base in ("/assignments/api", "/mentoradmin/api"):
            r = c.get(base + "/mailbox")
            assert r.status_code == 200
            assert r.json() == {"mailbox": None, "sendEnabled": False, "signature": ""}


def test_sendmail_503_when_gmail_sync_off(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.post("/assignments/api/sendmail", json={"to": ["a@b.c"], "body": "hi"})
    assert r.status_code == 503
    assert "isn't enabled" in r.json()["detail"]


def test_mailbox_resolves_users_cbm_address(monkeypatch):
    _as(monkeypatch)

    async def fake_resolve(client, user_id):
        assert user_id == "u1"
        return "staff.admin@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentoradmin/api/mailbox")
    assert r.status_code == 200
    assert r.json() == {
        "mailbox": "staff.admin@cbmentors.org",
        "sendEnabled": True,
        "signature": "",
    }


def test_mailbox_null_when_no_linked_profile(monkeypatch):
    _as(monkeypatch)

    async def fake_resolve(client, user_id):
        return None

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/assignments/api/mailbox")
    assert r.json() == {"mailbox": None, "sendEnabled": False, "signature": ""}


def test_sendmail_sends_as_the_user(monkeypatch):
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post(
            "/assignments/api/sendmail",
            json={"to": ["James@Acme.test"], "subject": "Hello", "body": "Quick note"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["gmailMessageId"] == "gm-1"
    assert len(gmail.sent) == 1
    msg = gmail.sent[0]  # EmailMessage from build_mime
    # The From header carries the signed-in user's display name so ingested
    # copies (and recipients) can see WHO sent it, not just the mailbox.
    assert msg["From"] == "Staff Admin <staff.admin@cbmentors.org>"
    assert msg["To"] == "james@acme.test"  # normalized lowercase
    assert msg["Subject"] == "Hello"
    assert "Quick note" in msg.as_string()


def test_sendmail_requires_a_recipient(monkeypatch):
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post("/mentoradmin/api/sendmail", json={"to": [], "body": "hi"})
    assert r.status_code == 400
    assert "recipient" in r.json()["detail"]
    assert not gmail.sent


def test_sessions_router_has_sendmail_and_mailbox_reports_send_enabled(monkeypatch):
    """Grid-page peeks (no open record) use the quickmail widget on the
    session tools too: their own /mailbox gains sendEnabled and they get
    POST /sendmail (include_mailbox=False keeps their existing /mailbox)."""
    _as(monkeypatch)
    monkeypatch.setattr(
        "sessions.router.current_user", lambda request, key=None: _USER
    )
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())

    async def fake_resolve(client, user_id):
        return "staff.admin@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/mailbox")
        assert r.status_code == 200
        assert r.json() == {
            "mailbox": "staff.admin@cbmentors.org",
            "sendEnabled": True,
            "signature": "",
        }
        r2 = c.post(
            "/mentorsessions/api/sendmail",
            json={"to": ["james@acme.test"], "subject": "Hi", "body": "note"},
        )
    assert r2.status_code == 200 and r2.json()["status"] == "ok"
    assert len(gmail.sent) == 1


def test_sessions_mailbox_send_disabled_when_gmail_sync_off(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(
        "sessions.router.current_user", lambda request, key=None: _USER
    )
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())

    async def fake_resolve(client, user_id):
        return "staff.admin@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/mentorsessions/api/mailbox")
        assert r.json()["sendEnabled"] is False
        assert c.post(
            "/mentorsessions/api/sendmail", json={"to": ["a@b.c"], "body": "x"}
        ).status_code == 503


def test_sendmail_no_mailbox_is_a_readable_400(monkeypatch):
    _as(monkeypatch)

    async def fake_gmail_for_user(settings, client, user):
        raise comms_service.CommsError(
            "Your profile has no CBM email address, so your mailbox can't be read."
        )

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post("/assignments/api/sendmail", json={"to": ["a@b.c"], "body": "hi"})
    assert r.status_code == 400
    assert "no CBM email" in r.json()["detail"]


def test_sendmail_cc_bcc_land_on_the_mime_headers(monkeypatch):
    """Cc/Bcc ride the whole quick-send path: normalized, deduped against To,
    and set as MIME headers (Gmail delivers to Bcc from the raw message and
    strips the header from recipients' copies)."""
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post(
            "/assignments/api/sendmail",
            json={
                "to": ["james@acme.test"],
                # duplicate of a To address is dropped from Cc; Bcc keeps its own
                "cc": ["Maria@Acme.test", "james@acme.test"],
                "bcc": ["boss@cbmentors.org", "maria@acme.test"],
                "subject": "Hello",
                "body": "note",
            },
        )
    assert r.status_code == 200
    msg = gmail.sent[0]
    assert msg["To"] == "james@acme.test"
    assert msg["Cc"] == "maria@acme.test"
    assert msg["Bcc"] == "boss@cbmentors.org"


def test_sendmail_cc_only_promotes_to_to(monkeypatch):
    """A message with only Cc recipients still sends — the Cc list becomes To
    (headers need at least one To address)."""
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post(
            "/assignments/api/sendmail",
            json={"to": [], "cc": ["maria@acme.test"], "body": "note"},
        )
    assert r.status_code == 200
    msg = gmail.sent[0]
    assert msg["To"] == "maria@acme.test"
    assert msg["Cc"] is None


def test_sendmail_reply_threading(monkeypatch):
    """threadId/inReplyTo/references (Submission Admin follow-ups) keep the
    send on the original Gmail thread + RFC chain; build_mime appends the
    replied-to id to References."""
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post(
            "/assignments/api/sendmail",
            json={
                "to": ["kim@keybank.test"], "subject": "Re: Your request",
                "body": "Following up.",
                "threadId": "t-123", "inReplyTo": "msg-1@mail.test",
                "references": "<msg-0@mail.test>",
            },
        )
    assert r.status_code == 200
    assert gmail.thread_ids == ["t-123"]
    msg = gmail.sent[0]
    assert msg["In-Reply-To"] == "<msg-1@mail.test>"
    assert msg["References"] == "<msg-0@mail.test> <msg-1@mail.test>"


def test_sendmail_without_reply_fields_is_a_fresh_message(monkeypatch):
    _as(monkeypatch)
    gmail = FakeGmail()

    async def fake_gmail_for_user(settings, client, user):
        return gmail

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post("/assignments/api/sendmail",
                   json={"to": ["a@b.test"], "subject": "Hi", "body": "x"})
    assert r.status_code == 200
    assert gmail.thread_ids == [None]
    assert gmail.sent[0]["In-Reply-To"] is None
