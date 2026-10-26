"""Personal outreach from the lead's page (build plan § 7e.5; rulings 107-109,
115, 118-120, 122, 128) — the server side.

Each guardrail refuses in words; the opt-out sentence and the postal address
are appended when the message lacks them and the send is refused while the
address setting is empty; one *Personal email* touch per send and one
*Personal call* touch per call, written as the user with the team stamped;
the three call outcomes and their consequences through the campaign calls'
own code; the sender resolver's three cases (ruling 120); the template
filter; the endpoints dark behind LEAD_OUTREACH.
"""

from __future__ import annotations

import asyncio

import pytest

from campaigns import calls, config as cfg, ladder, outreach
from campaigns.service import CampaignError
from comms import crm as comms_crm
from comms import service as comms_service
from tests.test_campaigns import MARKETING, FakeCrm, FakeStore, build

OTHER = {"userName": "sue", "name": "Sue Staff", "userId": "u-9", "token": "t", "isAdmin": False,
         "teams": ["Marketing Admin Team"]}
ADDRESS = "Cleveland Business Mentors\n1 Public Square\nCleveland, OH 44113"


def run(coro):
    return asyncio.run(coro)


class OutreachCrm(FakeCrm):
    """The campaigns fake with the ladder's fields and links (the lead's
    Assigned to and Replied fields) and the Team the touch is stamped with."""

    def __init__(self, *, ladder_fields: bool = True):
        super().__init__()
        self.ladder_fields = ladder_fields
        self.add("Team", {"id": "team-mkt", "name": "Marketing Admin Team"})

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.PROSPECT}.fields" and self.ladder_fields:
            base = await super().metadata(key)
            return {**base, **{f: {} for f in ladder.FIELDS}}
        if key == f"entityDefs.{cfg.PROSPECT}.links":
            return {l: {} for l in ladder.LINKS} if self.ladder_fields else {}
        return await super().metadata(key)


def _lead(crm, **row):
    base = {"id": "lead0000000000001", "name": "Marigold Pet Grooming", "businessName": "Marigold Pet Grooming",
            "leadStatus": cfg.LEAD_QUALIFIED, "qualificationLevel": cfg.LEVEL_CONTACTABLE,
            "email": "owner@marigold.example", "phone": "216 555 0199",
            "assignedUserId": MARKETING["userId"], "assignedUserName": MARKETING["name"],
            "createdAt": "2026-10-01 10:00:00"}
    base.update(row)
    return crm.add(cfg.PROSPECT, base)


# --- the rules, without a CRM ----------------------------------------------------------------

def test_why_not_email_names_each_guardrail_in_words():
    me = MARKETING
    ok = {"leadStatus": "Qualified", "qualificationLevel": "Contactable", "email": "a@b.example", "assignedUserId": "u-1"}
    assert outreach.why_not_email(ok, me) == ""
    assert outreach.why_not_email({**ok, "qualificationLevel": "Referred"}, me) == ""
    assert "Only a Contactable or Referred lead" in outreach.why_not_email({**ok, "qualificationLevel": "Identified"}, me)
    assert "this one is Unqualified" in outreach.why_not_email({**ok, "leadStatus": "Unqualified", "qualificationLevel": None}, me)
    assert "stopped being worked (Declined)" in outreach.why_not_email({**ok, "sideExit": "Declined"}, me)
    assert "no email address" in outreach.why_not_email({**ok, "email": ""}, me)
    assert outreach.why_not_email({**ok, "assignedUserId": ""}, me) == outreach.ASSIGN_FIRST
    other = outreach.why_not_email({**ok, "assignedUserId": "u-9", "assignedUserName": "Sue Staff"}, me)
    assert other.startswith("This lead is assigned to Sue Staff.") and other.endswith(outreach.ASSIGN_FIRST)


def test_why_not_call_refuses_a_disqualified_or_unassigned_lead():
    me = MARKETING
    assert outreach.why_not_call({"leadStatus": "Qualified", "assignedUserId": "u-1"}, me) == ""
    assert outreach.why_not_call({"leadStatus": "Unqualified", "assignedUserId": "u-1"}, me) == ""
    assert "Disqualified" in outreach.why_not_call({"leadStatus": "Disqualified", "assignedUserId": "u-1"}, me)
    assert outreach.why_not_call({"leadStatus": "Qualified"}, me) == outreach.ASSIGN_FIRST


def test_exactly_one_recipient_the_leads_own_address():
    lead = {"email": "Owner@Marigold.example"}
    assert outreach.check_recipients(lead, ["owner@marigold.example"]) == "owner@marigold.example"
    with pytest.raises(CampaignError, match="no Cc or Bcc"):
        outreach.check_recipients(lead, ["owner@marigold.example"], cc=["x@y.example"])
    with pytest.raises(CampaignError, match="own address only"):
        outreach.check_recipients(lead, ["someone@else.example"])
    with pytest.raises(CampaignError, match="own address only"):
        outreach.check_recipients(lead, ["owner@marigold.example", "two@marigold.example"])
    with pytest.raises(CampaignError, match="no recipient"):
        outreach.check_recipients(lead, [])


def test_the_footer_is_appended_only_where_missing_and_refuses_without_an_address():
    body = "<p>Hello Rosa,</p><p>We mentor small businesses.</p>"
    out = outreach.append_footer(body, ADDRESS)
    assert out.startswith(body)
    assert out.count(outreach.OPT_OUT_SENTENCE.replace("'", "&#x27;")) == 1
    assert "1 Public Square<br>Cleveland, OH 44113" in out
    # Already present (as a reader sees it — tags and entities aside): appended once, never twice.
    again = outreach.append_footer(out, ADDRESS)
    assert again == out
    present = body + "<div>If you&#x27;d rather not hear from us, reply and say so and we won&#x27;t write again.</div>"
    once = outreach.append_footer(present, ADDRESS)
    assert once.count("rather not hear from us") == 1 and "Public Square" in once
    with pytest.raises(CampaignError, match="CHAPTER_POSTAL_ADDRESS"):
        outreach.append_footer(body, "")
    with pytest.raises(CampaignError, match="Chapter postal address under Presentation"):
        outreach.append_footer(body, "   \n ")


def test_the_two_touch_payloads():
    lead = {"id": "lead0000000000001", "businessName": "Marigold Pet Grooming", "leadStatus": "Qualified", "phone": "216 555 0199"}
    e = outreach.email_touch_payload(lead, "Hello from the chapter", user_id="u-1", team_ids=["team-mkt"], now="2026-10-25 23:00:00")
    assert e == {"name": "Hello from the chapter", "channel": "Personal email", "touchStatus": "Sent",
                 "sentAt": "2026-10-25 23:00:00", "prospectId": "lead0000000000001", "stageAtTouch": "Qualified",
                 "assignedUserId": "u-1", "teamsIds": ["team-mkt"]}
    assert "outreachCampaignId" not in e
    c = outreach.call_touch_payload(lead, "No reply yet", "", "", user_id="u-1", team_ids=[], now="2026-10-25 23:00:00")
    assert c["channel"] == "Personal call" and c["touchStatus"] == "Done" and c["doneAt"] == "2026-10-25 23:00:00"
    assert c["outcome"] == "No answer" and c["calledPhone"] == "216 555 0199" and c["callNotes"] is None
    assert "teamsIds" not in c and c["assignedUserId"] == "u-1"
    c2 = outreach.call_touch_payload(lead, "Not interested", "Happy with their accountant", "440 555 0100", user_id="u-1", team_ids=["t"])
    assert c2["outcome"] == "Declined" and c2["calledPhone"] == "440 555 0100"
    assert outreach.call_touch_payload(lead, "Interested", "", "", user_id="u-1", team_ids=[])["outcome"] == "Interested"
    with pytest.raises(CampaignError, match="note is required"):
        outreach.call_touch_payload(lead, "Not interested", "  ", "", user_id="u-1", team_ids=[])
    with pytest.raises(CampaignError, match="Interested, Not interested or No reply yet"):
        outreach.call_touch_payload(lead, "Declined", "", "", user_id="u-1", team_ids=[])


def test_only_template_and_own_file_attachments_ride_a_personal_email():
    ok = [{"espoId": "a1", "filename": "flyer.pdf"}, {"filename": "x.txt", "contentType": "text/plain", "dataBase64": "aGk="}]
    assert outreach.attachments_for_lead(ok) == ok
    with pytest.raises(CampaignError, match="no Documents folder"):
        outreach.attachments_for_lead([{"documentId": "d1", "filename": "a.pdf"}])
    with pytest.raises(CampaignError, match="forward"):
        outreach.attachments_for_lead([{"forwardCommunicationId": "c1", "partIndex": 0, "filename": "a.pdf"}])


# --- the sender's mailbox (ruling 120) ----------------------------------------------------------

def test_the_mailbox_rule_profile_first_then_own_address_on_the_domain():
    assert comms_crm.user_mailbox("Mark.M@cbmentors.org", "other@cbmentors.org", "cbmentors.org") == "mark.m@cbmentors.org"
    assert comms_crm.user_mailbox("", "mark.marketing@cbmentors.org", "cbmentors.org") == "mark.marketing@cbmentors.org"
    assert comms_crm.user_mailbox("", "mark@gmail.example", "cbmentors.org") is None
    assert comms_crm.user_mailbox(None, None, "cbmentors.org") is None


class _Settings:
    mentor_email_domain = "cbmentors.org"


def test_the_resolver_reads_the_profile_then_the_user_and_refuses_in_words(monkeypatch):
    calls_made = []

    async def profile_mailbox(client, user_id):
        calls_made.append(("profile", user_id))
        return client.profile

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", profile_mailbox)

    class Client:
        def __init__(self, profile, own):
            self.profile, self.own = profile, own

        async def get(self, entity, record_id, select=None):
            assert entity == "User" and record_id == "u-1"
            return {"id": record_id, "emailAddress": self.own}

    assert run(comms_service.sender_mailbox(Client("m.mentor@cbmentors.org", "x"), MARKETING, _Settings())) == "m.mentor@cbmentors.org"
    assert run(comms_service.sender_mailbox(Client(None, "Mark.Marketing@cbmentors.org"), MARKETING, _Settings())) == "mark.marketing@cbmentors.org"
    with pytest.raises(comms_service.CommsError) as exc:
        run(comms_service.sender_mailbox(Client(None, "mark@gmail.example"), MARKETING, _Settings()))
    assert "no chapter mailbox on your profile or your user" in str(exc.value)
    assert "cbmentors.org" in str(exc.value)


# --- templates --------------------------------------------------------------------------------

def test_templates_narrow_to_the_marketing_category_when_any_has_it():
    crm = FakeCrm()
    crm.add("EmailTemplate", {"name": "EventReminder", "categoryName": None})
    crm.add("EmailTemplate", {"name": "MentorAssignmentNotice", "categoryName": "Engagement"})
    out = run(outreach.marketing_templates(crm))
    assert [t["name"] for t in out["templates"]] == ["EventReminder", "MentorAssignmentNotice"] and out["contextFiltered"] is False
    crm.add("EmailTemplate", {"name": "Hello from the chapter", "categoryName": "Marketing"})
    out = run(outreach.marketing_templates(crm))
    assert [t["name"] for t in out["templates"]] == ["Hello from the chapter"] and out["contextFiltered"] is True


# --- the endpoints ----------------------------------------------------------------------------

def _outreach_app(monkeypatch, crm, *, user=MARKETING, on="true", gmail="true", postal=ADDRESS):
    monkeypatch.setenv("LEAD_LADDER", "true")
    monkeypatch.setenv("LEAD_OUTREACH", on)
    monkeypatch.setenv("GMAIL_SYNC", gmail)
    monkeypatch.setenv("CHAPTER_POSTAL_ADDRESS", postal)
    client = build(monkeypatch, user=user, crm=crm, store=FakeStore())
    import campaigns.router as router_mod
    import campaigns.outreach_router as outreach_mod
    monkeypatch.setattr(router_mod, "_system_client", lambda settings: crm)      # the org-wide key is the same fake

    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(outreach_mod, "record_action", _no_log)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: FakeStore())

    async def _no_enrich(*a, **kw):
        return None
    monkeypatch.setattr(comms_service, "enrich_conversation_rows", _no_enrich)
    return client


def test_everything_is_dark_while_the_switch_is_off(monkeypatch):
    crm = OutreachCrm()
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm, on="false")
    assert client.get("/campaigns/api/session").json()["leadOutreachOn"] is False
    for method, path, body in (("get", "/campaigns/api/mailbox", None),
                               ("get", "/campaigns/api/emailtemplates", None),
                               ("post", f"/campaigns/api/prospects/{lead['id']}/messages", {"to": [lead["email"]], "subject": "x", "body": "y"}),
                               ("post", f"/campaigns/api/prospects/{lead['id']}/calls", {"outcome": "No reply yet"}),
                               ("get", f"/campaigns/api/prospects/{lead['id']}/conversations", None)):
        resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert resp.status_code == 404 and "switched off" in resp.json()["detail"], path


def test_a_crm_without_the_fields_is_told_so(monkeypatch):
    crm = OutreachCrm(ladder_fields=False)
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/messages", json={"to": [lead["email"]], "subject": "x", "body": "y"})
    assert resp.status_code == 409 and "Assigned to field" in resp.json()["detail"]


def test_the_mailbox_endpoint_resolves_the_users_own_address_or_says_what_is_missing(monkeypatch):
    crm = OutreachCrm()
    crm.add("User", {"id": MARKETING["userId"], "emailAddress": "mark.marketing@cbmentors.org"})
    client = _outreach_app(monkeypatch, crm)
    body = client.get("/campaigns/api/mailbox").json()
    assert body["mailbox"] == "mark.marketing@cbmentors.org" and body["sendEnabled"] is True
    crm.rows["User"][MARKETING["userId"]]["emailAddress"] = "mark@gmail.example"
    body = client.get("/campaigns/api/mailbox").json()
    assert body["mailbox"] is None and "no chapter mailbox" in body["reason"]


def _sent(monkeypatch):
    """Stub the mailbox and the send; return the list of send_message kwargs."""
    seen = []

    async def fake_gmail(settings, mailbox):
        class G:
            pass
        G.mailbox = mailbox
        return G()

    async def fake_send(**kw):
        seen.append(kw)
        return {"gmailMessageId": "g1", "conversationId": "conv1", "writeBack": {"ok": True, "emailId": "e1"}, "ingestWarning": ""}

    monkeypatch.setattr(comms_service, "gmail_for_shared_mailbox", fake_gmail)
    monkeypatch.setattr(comms_service, "send_message", fake_send)
    return seen


def test_each_send_guardrail_refuses_in_words(monkeypatch):
    crm = OutreachCrm()
    crm.add("User", {"id": MARKETING["userId"], "emailAddress": "mark.marketing@cbmentors.org"})
    client = _outreach_app(monkeypatch, crm)
    seen = _sent(monkeypatch)
    ok_body = {"to": ["owner@marigold.example"], "subject": "Hello", "body": "<p>Hi</p>"}

    def send(lead_id, body=ok_body):
        return client.post(f"/campaigns/api/prospects/{lead_id}/messages", json=body)

    identified = _lead(crm, id="lead0000000000002", qualificationLevel="Identified")
    assert "Only a Contactable or Referred lead" in send(identified["id"]).json()["detail"]
    stopped = _lead(crm, id="lead0000000000003", sideExit="Do Not Contact")
    assert "stopped being worked" in send(stopped["id"]).json()["detail"]
    no_email = _lead(crm, id="lead0000000000004", email="")
    assert "no email address" in send(no_email["id"]).json()["detail"]
    theirs = _lead(crm, id="lead0000000000005", assignedUserId="u-9", assignedUserName="Sue Staff")
    assert send(theirs["id"]).json()["detail"].endswith("Assign the lead to yourself first.")
    unassigned = _lead(crm, id="lead0000000000006", assignedUserId=None, assignedUserName=None)
    assert send(unassigned["id"]).json()["detail"] == "Assign the lead to yourself first."
    mine = _lead(crm)
    resp = send(mine["id"], {**ok_body, "to": ["someone@else.example"]})
    assert resp.status_code == 400 and "own address only" in resp.json()["detail"]
    resp = send(mine["id"], {**ok_body, "cc": ["x@y.example"]})
    assert "no Cc or Bcc" in resp.json()["detail"]
    resp = send(mine["id"], {**ok_body, "attachments": [{"documentId": "d1", "filename": "a.pdf"}]})
    assert "no Documents folder" in resp.json()["detail"]
    assert seen == [] and cfg.TOUCH not in crm.rows


def test_an_empty_postal_address_refuses_the_send_naming_the_setting(monkeypatch):
    crm = OutreachCrm()
    crm.add("User", {"id": MARKETING["userId"], "emailAddress": "mark.marketing@cbmentors.org"})
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm, postal="")
    seen = _sent(monkeypatch)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/messages", json={"to": [lead["email"]], "subject": "Hello", "body": "<p>Hi</p>"})
    assert resp.status_code == 400 and "CHAPTER_POSTAL_ADDRESS" in resp.json()["detail"]
    assert seen == []


def test_a_sender_without_a_chapter_mailbox_is_refused(monkeypatch):
    crm = OutreachCrm()
    crm.add("User", {"id": MARKETING["userId"], "emailAddress": "mark@gmail.example"})
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm)
    seen = _sent(monkeypatch)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/messages", json={"to": [lead["email"]], "subject": "Hello", "body": "<p>Hi</p>"})
    assert resp.status_code == 400 and "no chapter mailbox on your profile or your user" in resp.json()["detail"]
    assert seen == []


def test_the_send_appends_the_footer_scopes_to_the_lead_and_writes_one_touch(monkeypatch):
    crm = OutreachCrm()
    crm.add("User", {"id": MARKETING["userId"], "emailAddress": "mark.marketing@cbmentors.org"})
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm)
    seen = _sent(monkeypatch)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/messages",
                       json={"to": ["Owner@Marigold.example"], "subject": "Hello from the chapter", "body": "<p>Hi Rosa</p>",
                             "attachments": [{"espoId": "att1", "filename": "flyer.pdf"}]})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["from"] == "mark.marketing@cbmentors.org" and out["conversationId"] == "conv1" and out["warnings"] == []
    kw = seen[0]
    assert kw["to"] == ["owner@marigold.example"] and kw["gmail"].mailbox == "mark.marketing@cbmentors.org"
    assert kw["ref"].entity == cfg.PROSPECT and kw["ref"].id == lead["id"] and kw["ref"].addresses == {"owner@marigold.example"}
    assert kw["body_html"].startswith("<p>Hi Rosa</p>") and "rather not hear from us" in kw["body_html"]
    assert "1 Public Square<br>Cleveland, OH 44113" in kw["body_html"]
    assert kw["attachments"] == [{"espoId": "att1", "filename": "flyer.pdf"}]
    assert kw["user_client"] is crm and "cc" not in kw
    touches = list(crm.rows[cfg.TOUCH].values())
    assert len(touches) == 1 and out["touchId"] == touches[0]["id"]
    t = touches[0]
    assert t["channel"] == "Personal email" and t["touchStatus"] == "Sent" and t["name"] == "Hello from the chapter"
    assert t["prospectId"] == lead["id"] and t["assignedUserId"] == "u-1" and t["teamsIds"] == ["team-mkt"]
    assert "outreachCampaignId" not in t
    assert (cfg.TOUCH, t) in [(e, p) for e, p in crm.created] or any(e == cfg.TOUCH for e, _ in crm.created)


def test_log_a_call_the_three_outcomes_and_their_consequences(monkeypatch):
    crm = OutreachCrm()
    client = _outreach_app(monkeypatch, crm)
    # No reply yet: the touch only, stored as No answer; the lead unchanged.
    quiet = _lead(crm, id="lead0000000000011", businessName="Quiet Shop")
    resp = client.post(f"/campaigns/api/prospects/{quiet['id']}/calls", json={"outcome": "No reply yet", "notes": "voicemail"})
    assert resp.status_code == 200, resp.text
    t = crm.rows[cfg.TOUCH][resp.json()["touchId"]]
    assert t["channel"] == "Personal call" and t["touchStatus"] == "Done" and t["outcome"] == "No answer"
    assert t["callNotes"] == "voicemail" and t["calledPhone"] == "216 555 0199" and t["teamsIds"] == ["team-mkt"]
    assert "outreachCampaignId" not in t and crm.rows[cfg.PROSPECT][quiet["id"]]["leadStatus"] == "Qualified"
    assert resp.json()["consequences"] == []
    # Not interested: the note is required; then Declined with the note, never over another exit.
    nope = _lead(crm, id="lead0000000000012", businessName="No Shop")
    resp = client.post(f"/campaigns/api/prospects/{nope['id']}/calls", json={"outcome": "Not interested"})
    assert resp.status_code == 400 and "note is required" in resp.json()["detail"]
    resp = client.post(f"/campaigns/api/prospects/{nope['id']}/calls", json={"outcome": "Not interested", "notes": "Happy as they are", "calledPhone": "440 555 0100"})
    assert resp.status_code == 200, resp.text
    row = crm.rows[cfg.PROSPECT][nope["id"]]
    assert row["sideExit"] == "Declined" and row["sideExitNote"] == "Happy as they are"
    assert crm.rows[cfg.TOUCH][resp.json()["touchId"]]["calledPhone"] == "440 555 0100"
    assert "stopped by Declined" in resp.json()["consequences"]
    stale = _lead(crm, id="lead0000000000013", businessName="Stale Shop", sideExit="Stale")
    resp = client.post(f"/campaigns/api/prospects/{stale['id']}/calls", json={"outcome": "Not interested", "notes": "no"})
    assert crm.rows[cfg.PROSPECT][stale["id"]]["sideExit"] == "Stale"
    assert any("already stopped" in w for w in resp.json()["warnings"])
    # Interested: converts from the lead's own email under the API client (ruling 47).
    keen = _lead(crm, id="lead0000000000014", businessName="Keen Shop", email="rosa@keen.example")
    resp = client.post(f"/campaigns/api/prospects/{keen['id']}/calls", json={"outcome": "Interested", "notes": "wants a mentor"})
    assert resp.status_code == 200, resp.text
    row = crm.rows[cfg.PROSPECT][keen["id"]]
    assert row["leadStatus"] == "Converted" and "lead converted" in resp.json()["consequences"]
    contact = crm.rows["Contact"][row["promotedContactId"]]
    assert contact["emailAddress"] == "rosa@keen.example" and crm.rows["Account"][row["promotedCompanyId"]]["name"] == "Keen Shop"
    touch = crm.rows[cfg.TOUCH][resp.json()["touchId"]]
    assert touch["contactId"] == contact["id"] and touch["outcome"] == "Interested"
    # Interested without an email or website: recorded, the lead stays, the answer says why.
    bare = _lead(crm, id="lead0000000000015", businessName="Bare Shop", email="", website="")
    resp = client.post(f"/campaigns/api/prospects/{bare['id']}/calls", json={"outcome": "Interested"})
    assert resp.status_code == 200 and "stays a lead" in resp.json()["notConverted"]
    assert crm.rows[cfg.PROSPECT][bare["id"]]["leadStatus"] == "Qualified"
    # The guardrails: someone else's lead, a Disqualified lead, a bad outcome word.
    theirs = _lead(crm, id="lead0000000000016", assignedUserId="u-9", assignedUserName="Sue Staff")
    assert client.post(f"/campaigns/api/prospects/{theirs['id']}/calls", json={"outcome": "No reply yet"}).status_code == 400
    dq = _lead(crm, id="lead0000000000017", leadStatus="Disqualified", qualificationLevel=None)
    assert "Disqualified" in client.post(f"/campaigns/api/prospects/{dq['id']}/calls", json={"outcome": "No reply yet"}).json()["detail"]
    assert "Interested, Not interested or No reply yet" in client.post(f"/campaigns/api/prospects/{quiet['id']}/calls", json={"outcome": "Declined"}).json()["detail"]


def test_apply_outcome_is_the_campaign_calls_code_too():
    """The same function serves ``calls.record_outcome``: Declined on a
    campaign call stops the lead with the campaign named; Interested converts."""
    api = FakeCrm()
    lead = api.add(cfg.PROSPECT, {"id": "lead0000000000021", "name": "Two Shop", "businessName": "Two Shop",
                                 "leadStatus": "Qualified", "email": "ann@two.example"})
    touch = api.add(cfg.TOUCH, {"id": "touch000000000001", "prospectId": lead["id"], "channel": "Call"})
    result = {"consequences": [], "warnings": []}
    assert run(calls.apply_outcome(api, lead["id"], "Declined", "Declined on a call from the campaign October", result=result)) is False
    assert api.rows[cfg.PROSPECT][lead["id"]]["sideExit"] == "Declined"
    assert api.rows[cfg.PROSPECT][lead["id"]]["sideExitNote"] == "Declined on a call from the campaign October"
    other = api.add(cfg.PROSPECT, {"id": "lead0000000000022", "name": "Three Shop", "businessName": "Three Shop",
                                  "leadStatus": "Qualified", "email": "b@three.example"})
    result = {"consequences": [], "warnings": []}
    assert run(calls.apply_outcome(api, other["id"], "Interested", "", touch_id=touch["id"], result=result)) is True
    assert api.rows[cfg.PROSPECT][other["id"]]["leadStatus"] == "Converted"
    assert api.rows[cfg.TOUCH][touch["id"]]["contactId"]
    assert run(calls.apply_outcome(api, other["id"], "No answer", "", result={"consequences": [], "warnings": []})) is False


def test_the_leads_conversations_read_as_the_user_or_say_why_not(monkeypatch):
    crm = OutreachCrm()
    lead = _lead(crm)
    client = _outreach_app(monkeypatch, crm, gmail="false")
    body = client.get(f"/campaigns/api/prospects/{lead['id']}/conversations").json()
    assert body["available"] is False and "email integration" in body["reason"] and body["conversations"] == []
    client = _outreach_app(monkeypatch, crm)

    async def fake_list(user_client, parent_entity, parent_id):
        assert parent_entity == cfg.PROSPECT and parent_id == lead["id"] and user_client is crm
        return [{"id": "conv1", "subject": "Re: Hello", "lastMessageAt": "2026-10-25 20:00:00"}]

    monkeypatch.setattr(comms_service, "list_conversations", fake_list)
    body = client.get(f"/campaigns/api/prospects/{lead['id']}/conversations").json()
    assert body["available"] is True and body["conversations"][0]["id"] == "conv1"
    assert client.get("/campaigns/api/prospects/missing/conversations").status_code == 404


def test_the_counts_gain_mine_for_the_signed_in_user(monkeypatch):
    crm = OutreachCrm()
    _lead(crm)
    _lead(crm, id="lead0000000000031", assignedUserId="u-9")
    client = _outreach_app(monkeypatch, crm)
    body = client.get("/campaigns/api/prospects/counts").json()
    assert body["ladder"] is True and body["mine"] == 1 and body["contactable"] == 2
