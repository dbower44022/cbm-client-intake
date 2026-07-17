"""Email Template integration (ET) — comms/templates.py, the attachment send
path, and the native Email write-back (PRD failure model §5.3)."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from comms import service as comms_service
from comms import templates as tpl
from comms.store import MemoryCommsStore
from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from core.gmail import build_mime
from forms import info_request
from tests.test_comms_send import CFG, USER, FakeGmailSend, espo_with_contacts
from tests.test_comms_sync import FakeEspo


# --- fakes -------------------------------------------------------------------


class TemplateEspo(FakeEspo):
    """FakeEspo + the template/attachment surface of EspoClient."""

    def __init__(self, *args, prepare=None, meta_fields=None, files=None, **kw):
        super().__init__(*args, **kw)
        self.prepare_response = prepare or {
            "subject": "Hi Jane",
            "body": "<p>Welcome, Jane.</p>",
            "isHtml": True,
            "attachmentsIds": [],
            "attachmentsNames": {},
        }
        self.prepare_calls: list[dict] = []
        self.meta_fields = meta_fields  # None => metadata() raises
        self.files = files or {}        # attachment id -> (bytes, content_type)
        self.fail_email_create = False

    async def email_template_prepare(self, template_id, *, parent_type=None,
                                     parent_id=None, email_address=None,
                                     related_type=None, related_id=None):
        self.prepare_calls.append({
            "id": template_id, "parentType": parent_type,
            "parentId": parent_id, "emailAddress": email_address,
            "relatedType": related_type, "relatedId": related_id,
        })
        if isinstance(self.prepare_response, Exception):
            raise self.prepare_response
        return self.prepare_response

    async def metadata(self, key):
        if self.meta_fields is None:
            raise EspoError("metadata unavailable")
        return self.meta_fields

    async def download_attachment(self, attachment_id):
        if attachment_id not in self.files:
            raise EspoError(f"download attachment {attachment_id} failed: HTTP 404")
        return self.files[attachment_id]

    async def create(self, entity, payload):
        if entity == "Email" and self.fail_email_create:
            raise EspoError("create Email failed: HTTP 403 forbidden")
        return await super().create(entity, payload)


# --- unit: sanitize + leftover tokens ---------------------------------------


def test_sanitize_strips_script_events_and_js_urls():
    dirty = (
        "<p onclick=\"evil()\">Hi</p><script>bad()</script>"
        "<a href=\"javascript:evil()\">x</a><a href=\"https://ok.test\">ok</a>"
    )
    clean = tpl.sanitize_template_html(dirty)
    assert "<script" not in clean and "onclick" not in clean
    assert "javascript:" not in clean
    assert "https://ok.test" in clean  # formatting/links survive


def test_leftover_tokens_found_and_deduped():
    tokens = tpl.leftover_tokens(
        "About {Case.name}", "<p>{Person.name}, case {Case.name} ({Case.number})</p>"
    )
    assert tokens == ["{Case.name}", "{Person.name}", "{Case.number}"]
    assert tpl.leftover_tokens("plain", "<p>no tokens {not one}</p>") == []


# --- unit: list_templates ----------------------------------------------------


async def test_list_templates_without_context_returns_all():
    espo = TemplateEspo()
    espo.records[("EmailTemplate", "t1")] = {"name": "Welcome", "categoryName": "Partner"}
    espo.records[("EmailTemplate", "t2")] = {"name": "Follow-up"}
    out = await tpl.list_templates(espo)  # quick-compose: no context
    assert out["contextFiltered"] is False
    assert {t["name"] for t in out["templates"]} == {"Welcome", "Follow-up"}


async def test_list_templates_filters_by_native_category_name():
    # The context filter rides EmailTemplate's NATIVE category (the entity is
    # customizable:false — no custom field is possible through the UI).
    espo = TemplateEspo()
    espo.records[("EmailTemplate", "t1")] = {"name": "Anywhere", "categoryName": None}
    espo.records[("EmailTemplate", "t2")] = {"name": "Partners only", "categoryName": "Partner"}
    espo.records[("EmailTemplate", "t3")] = {"name": "Engagements", "categoryName": "engagement"}
    espo.records[("EmailTemplate", "t4")] = {"name": "Newsletter", "categoryName": "Newsletters"}
    out = await tpl.list_templates(espo, context="Engagement")
    assert out["contextFiltered"] is True
    names = {t["name"] for t in out["templates"]}
    # no category / unrecognized category => shows everywhere; other-domain hides
    assert names == {"Anywhere", "Engagements", "Newsletter"}


# --- unit: parse_template ----------------------------------------------------


async def test_parse_returns_sanitized_draft_with_chips_and_tokens():
    espo = TemplateEspo(prepare={
        "subject": "Case {Case.number}",
        "body": "<p onmouseover=\"x()\">Hi Jane</p><script>x()</script><p>{Case.name}</p>",
        "isHtml": True,
        "attachmentsIds": ["a1", "a2"],
        "attachmentsNames": {"a1": "brochure.pdf", "a2": "terms.docx"},
    })
    out = await tpl.parse_template(
        espo, "t1", parent_type="CEngagement", parent_id="E1",
        email_address="jane@acme.test",
    )
    assert espo.prepare_calls[0] == {
        "id": "t1", "parentType": "CEngagement", "parentId": "E1",
        "emailAddress": "jane@acme.test", "relatedType": None, "relatedId": None,
    }
    assert "<script" not in out["bodyHtml"] and "onmouseover" not in out["bodyHtml"]
    assert out["attachments"] == [
        {"id": "a1", "name": "brochure.pdf"}, {"id": "a2", "name": "terms.docx"},
    ]
    assert out["leftoverTokens"] == ["{Case.number}", "{Case.name}"]


async def test_parse_upconverts_plain_text_template():
    espo = TemplateEspo(prepare={
        "subject": "s", "body": "line one\n\nline two", "isHtml": False,
        "attachmentsIds": [], "attachmentsNames": {},
    })
    out = await tpl.parse_template(espo, "t1")
    assert "<" in out["bodyHtml"] and "line one" in out["bodyHtml"]


# --- unit: related_manager_profile ({CMentorProfile.*} resolution) -----------


async def test_related_manager_prefers_the_records_manager():
    espo = TemplateEspo()
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": "mp7"}
    got = await tpl.related_manager_profile(
        espo, user_id="u1",
        parent_entity="CEngagement", parent_id="E1", manager_link="mentorProfile",
    )
    assert got == "mp7"


async def test_related_manager_falls_back_to_the_senders_profile():
    espo = TemplateEspo()
    espo.records[("CEngagement", "E1")] = {}  # record has no assigned mentor
    espo.records[("CMentorProfile", "mp9")] = {
        "name": "Bob Mentor", "assignedUserId": "u1",
    }
    got = await tpl.related_manager_profile(
        espo, user_id="u1",
        parent_entity="CEngagement", parent_id="E1", manager_link="mentorProfile",
    )
    assert got == "mp9"


async def test_related_manager_none_when_nothing_resolves():
    got = await tpl.related_manager_profile(TemplateEspo(), user_id="u1")
    assert got is None


# --- unit: resolve_attachments (ET-131 blocks the send) ----------------------


async def test_resolve_attachments_espo_and_local():
    espo = TemplateEspo(files={"a1": (b"PDFBYTES", "application/pdf")})
    espo.records[("Attachment", "a1")] = {"name": "brochure.pdf", "type": "application/pdf"}
    got = await comms_service.resolve_attachments(espo, [
        {"espoId": "a1"},
        {"filename": "notes.txt", "contentType": "text/plain",
         "dataBase64": base64.b64encode(b"hello").decode()},
    ])
    assert got[0] == ("brochure.pdf", "application/pdf", b"PDFBYTES")
    assert got[1] == ("notes.txt", "text/plain", b"hello")


async def test_missing_espo_attachment_blocks_with_readable_error():
    espo = TemplateEspo()  # no files
    espo.records[("Attachment", "gone")] = {"name": "lost.pdf"}
    with pytest.raises(comms_service.CommsError) as exc:
        await comms_service.resolve_attachments(espo, [{"espoId": "gone"}])
    assert "NOT sent" in str(exc.value)


async def test_attachment_size_cap_enforced():
    big = base64.b64encode(b"x" * (comms_service.MAX_ATTACHMENT_TOTAL_BYTES + 1)).decode()
    with pytest.raises(comms_service.CommsError) as exc:
        await comms_service.resolve_attachments(TemplateEspo(), [
            {"filename": "huge.bin", "contentType": "application/octet-stream", "dataBase64": big},
        ])
    assert "too large" in str(exc.value)


async def test_bad_base64_is_a_readable_error():
    with pytest.raises(comms_service.CommsError):
        await comms_service.resolve_attachments(TemplateEspo(), [
            {"filename": "x.bin", "dataBase64": "!!! not base64 !!!"},
        ])


def test_build_mime_with_attachments_is_multipart_mixed():
    msg = build_mime(
        sender="a@b.c", to=["x@y.z"], subject="s", body_text="",
        body_html="<p>hi</p>",
        attachments=[("brochure.pdf", "application/pdf", b"PDFBYTES")],
    )
    assert msg.get_content_type() == "multipart/mixed"
    parts = list(msg.iter_attachments())
    assert parts[0].get_filename() == "brochure.pdf"
    assert parts[0].get_content_type() == "application/pdf"
    # the HTML alternative survives alongside the attachment
    body = msg.get_body(preferencelist=("html",))
    assert body is not None and "hi" in body.get_content()


# --- send paths: attachment blocking + Email write-back ----------------------


def _user_client_with_contact():
    espo = TemplateEspo()
    espo.records[("Contact", "c1")] = {
        "name": "James", "emailAddress": "james@acme.test", "cContactType": [],
    }
    return espo


async def test_send_message_writes_back_email_parented_to_contact():
    user_client = _user_client_with_contact()
    gmail = FakeGmailSend()
    result = await comms_service.send_message(
        settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
        gmail=gmail, cfg=CFG, parent_id="E1", user=USER,
        to=["james@acme.test"], subject="Hello", body_html="<p>hi</p>",
        user_client=user_client,
    )
    assert result["writeBack"]["ok"] is True
    emails = [rec for (ent, _), rec in user_client.records.items() if ent == "Email"]
    assert len(emails) == 1
    e = emails[0]
    assert e["status"] == "Sent" and e["name"] == "Hello"
    assert e["from"] == gmail.mailbox and e["to"] == "james@acme.test"
    assert e["parentType"] == "Contact" and e["parentId"] == "c1"
    assert e["messageId"].startswith("<sent-rfc")  # the sent copy's RFC id, bracketed


async def test_send_message_write_back_failure_surfaces_retry_payload():
    user_client = _user_client_with_contact()
    user_client.fail_email_create = True
    result = await comms_service.send_message(
        settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
        gmail=FakeGmailSend(), cfg=CFG, parent_id="E1", user=USER,
        to=["james@acme.test"], subject="Hello", body_html="<p>hi</p>",
        user_client=user_client,
    )
    wb = result["writeBack"]
    assert wb["ok"] is False and "WAS sent" in wb["error"]
    assert wb["retryPayload"]["to"] == ["james@acme.test"]
    assert wb["retryPayload"]["parentType"] == "Contact"
    assert result["gmailMessageId"] == "gsent1"  # the send itself succeeded


async def test_attachment_failure_blocks_send_entirely():
    user_client = _user_client_with_contact()  # no files => download fails
    gmail = FakeGmailSend()
    with pytest.raises(comms_service.CommsError):
        await comms_service.send_message(
            settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
            gmail=gmail, cfg=CFG, parent_id="E1", user=USER,
            to=["james@acme.test"], subject="x", body_html="hi",
            user_client=user_client, attachments=[{"espoId": "missing"}],
        )
    assert gmail.sent == []  # nothing went out (ET-131)


async def test_send_message_attachments_reach_the_mime():
    user_client = _user_client_with_contact()
    user_client.files["a1"] = (b"PDFBYTES", "application/pdf")
    user_client.records[("Attachment", "a1")] = {"name": "brochure.pdf", "type": "application/pdf"}
    gmail = FakeGmailSend()
    await comms_service.send_message(
        settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
        gmail=gmail, cfg=CFG, parent_id="E1", user=USER,
        to=["james@acme.test"], subject="x", body_html="hi",
        user_client=user_client, attachments=[{"espoId": "a1"}],
    )
    mime, _ = gmail.sent[0]
    attached = list(mime.iter_attachments())
    assert attached and attached[0].get_filename() == "brochure.pdf"


async def test_quick_send_writes_back_with_contact_parent():
    user_client = _user_client_with_contact()
    result = await comms_service.send_quick_message(
        gmail=FakeGmailSend(), to=["james@acme.test"], subject="q",
        body_html="hello", sender_name="Bob Mentor", user_client=user_client,
    )
    assert result["writeBack"]["ok"] is True
    emails = [rec for (ent, _), rec in user_client.records.items() if ent == "Email"]
    assert emails and emails[0]["parentType"] == "Contact" and emails[0]["parentId"] == "c1"


async def test_quick_send_without_user_client_keeps_old_contract():
    result = await comms_service.send_quick_message(
        gmail=FakeGmailSend(), to=["a@b.c"], subject="q", body_html="hello",
    )
    assert result["gmailMessageId"] == "gsent1"
    assert result["writeBack"]["ok"] is True  # nothing to write back = ok


# --- endpoints ---------------------------------------------------------------

_STAFF = {
    "userId": "u1", "userName": "bob.mentor", "name": "Bob Mentor",
    "isAdmin": True, "teams": [], "roles": [], "token": "t",
}


def _app(monkeypatch, gmail_sync=True):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, client):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _STAFF)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: client)
    monkeypatch.setattr("assignments.auth.current_user", lambda request, key=None: _STAFF)
    # assignments' quicksend registration captured client_for by reference at
    # import time — intercept at the client-construction level instead.
    monkeypatch.setattr(
        "core.espo.EspoClient.for_user_token",
        classmethod(lambda cls, *a, **kw: client),
    )


def test_sessions_template_list_and_parse_endpoints(monkeypatch):
    espo = TemplateEspo(meta_fields={})
    espo.records[("EmailTemplate", "t1")] = {"name": "Welcome"}
    espo.records[("CEngagement", "E1")] = {"mentorProfileId": "mp1"}
    _as(monkeypatch, espo)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/emailtemplates")
        assert r.status_code == 200
        assert r.json()["templates"] == [{"id": "t1", "name": "Welcome"}]
        r2 = c.post(
            "/mentorsessions/api/records/E1/emailtemplates/t1/parse",
            json={"emailAddress": "jane@acme.test"},
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["subject"] == "Hi Jane" and "Welcome" in body["bodyHtml"]
        # the record IS the {Parent.*} context
        assert espo.prepare_calls[0]["parentType"] == "CEngagement"
        assert espo.prepare_calls[0]["parentId"] == "E1"
        assert espo.prepare_calls[0]["emailAddress"] == "jane@acme.test"
        # the record's assigned mentor rides along so {CMentorProfile.*} resolves
        assert espo.prepare_calls[0]["relatedType"] == "CMentorProfile"
        assert espo.prepare_calls[0]["relatedId"] == "mp1"


def test_parse_failure_is_a_readable_error_and_no_500(monkeypatch):
    espo = TemplateEspo()
    espo.prepare_response = EspoError("prepare failed: HTTP 403 forbidden")
    _as(monkeypatch, espo)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/records/E1/emailtemplates/t1/parse", json={})
    assert r.status_code == 403
    assert "permission" in r.json()["detail"]


def test_templates_503_when_gmail_off(monkeypatch):
    _as(monkeypatch, TemplateEspo())
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        assert c.get("/mentorsessions/api/emailtemplates").status_code == 503
        assert c.get("/assignments/api/emailtemplates").status_code == 503


def test_quicksend_surface_has_template_endpoints(monkeypatch):
    espo = TemplateEspo(meta_fields={})
    espo.records[("EmailTemplate", "t1")] = {"name": "Welcome"}
    _as(monkeypatch, espo)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/assignments/api/emailtemplates")
        assert r.status_code == 200 and r.json()["templates"][0]["name"] == "Welcome"
        r2 = c.post(
            "/assignments/api/emailtemplates/t1/parse",
            json={"emailAddress": "jane@acme.test"},
        )
        assert r2.status_code == 200
        # record-less: {Person.*} resolves from the address alone (ET-OI-1)
        assert espo.prepare_calls[0]["parentType"] is None
        assert espo.prepare_calls[0]["emailAddress"] == "jane@acme.test"


def test_write_back_retry_endpoint_creates_email(monkeypatch):
    espo = TemplateEspo()
    _as(monkeypatch, espo)

    async def fake_mailbox(client, user_id):
        return "bob.mentor@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_mailbox)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/assignments/api/emailwriteback", json={
            "subject": "Hello", "bodyHtml": "<p>hi</p>", "to": ["james@acme.test"],
            "parentType": "Contact", "parentId": "c1", "messageId": "rfc-1",
        })
    assert r.status_code == 200 and r.json()["status"] == "ok"
    emails = [rec for (ent, _), rec in espo.records.items() if ent == "Email"]
    assert emails and emails[0]["parentType"] == "Contact"
    assert emails[0]["from"] == "bob.mentor@cbmentors.org"
