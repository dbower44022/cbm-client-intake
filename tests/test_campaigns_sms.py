"""Campaign Management, Phase 4 — the text-message kind (rulings 9, 38, 39).

The boundaries: who a text may go to (ruling 9's consent, not opted out, on the
ladder); the sign-off's refusals (no wording, no STOP, the typed count); the
send's discipline (texting hours, a touch marked sending before the call and
never resent by itself, a refused number cancelled); a STOP reply opting the
number out; the delivery report; the signed callbacks; the message parts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from campaigns import config as cfg
from campaigns import sms
from campaigns.service import CampaignError
from core import sms as core_sms
from core.config import Settings
from tests.test_campaigns import FakeCrm, FakeStore, MARKETING, build


def run(coro):
    return asyncio.run(coro)


def _settings(**kw):
    base = dict(campaigns_enabled=True, campaigns_sms=True, espo_dry_run=False)
    base.update(kw)
    return Settings(_env_file=None, **base)


NOON_EASTERN = datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc)
NIGHT_EASTERN = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
MESSAGE = "Free mentoring for your new business: https://x.example/c/abcd2345 Reply STOP to opt out."


def _seed(crm):
    crm.add("Contact", {"id": "c-ok", "name": "Pat", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "cSmsOptIn": True, "phoneNumber": "(216) 555-0101", "phoneNumberIsOptedOut": False})
    crm.add("Contact", {"id": "c-nocons", "name": "Noel", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "cSmsOptIn": False, "phoneNumber": "2165550102"})
    crm.add("Contact", {"id": "c-out", "name": "Otto", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "cSmsOptIn": True, "phoneNumber": "2165550103", "phoneNumberIsOptedOut": True})
    crm.add("Contact", {"id": "c-client", "name": "Cli", "cContactType": ["Client"], "cFunnelStage": "Qualified",
                        "cSmsOptIn": True, "phoneNumber": "2165550104"})
    crm.add("Contact", {"id": "c-nophone", "name": "Nop", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "cSmsOptIn": True})
    crm.add("Contact", {"id": "c-left", "name": "Left", "cContactType": ["Prospect"], "cFunnelStage": "Lead",
                        "cSmsOptIn": True, "phoneNumber": "2165550105"})
    crm.add(cfg.PROSPECT, {"id": "p-left", "sideExit": "Do Not Contact", "promotedContactId": "c-left"})
    crm.add(cfg.PROSPECT, {"id": "p-phone", "funnelStage": "Qualified", "phone": "2165550106"})   # never texted


def _campaign(crm, status="Draft", message=MESSAGE):
    return crm.add(cfg.CAMPAIGN, {"name": "Texts", "campaignKind": "SMS", "campaignStatus": status,
                                  "smsMessage": message})


def test_selection_is_ruling_9():
    crm = FakeCrm()
    _seed(crm)
    targets = run(sms.select_targets(crm, {"stages": ["Qualified", "Lead"]}))
    assert [(t["id"], t["phone"]) for t in targets] == [("c-ok", "+12165550101")]


def test_sign_off_refuses_without_wording_or_stop_and_needs_the_count():
    crm = FakeCrm()
    _seed(crm)
    camp = _campaign(crm, message="Free mentoring!")
    run(sms.build_list(crm, crm, camp, None))
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    with pytest.raises(CampaignError, match="STOP"):
        run(sms.sign_off(crm, crm, camp, confirm="1", user_name="Mark"))
    crm.rows[cfg.CAMPAIGN][camp["id"]]["smsMessage"] = MESSAGE
    with pytest.raises(CampaignError, match="Type the number"):
        run(sms.sign_off(crm, crm, camp, confirm="2", user_name="Mark"))
    signed = run(sms.sign_off(crm, crm, camp, confirm="1", user_name="Mark"))
    assert signed["campaignStatus"] == "Signed off" and signed["pieceCount"] == 1


def test_the_send_keeps_to_the_hours_and_completes():
    crm, sender = FakeCrm(), core_sms.DryRunSmsClient()
    _seed(crm)
    camp = _campaign(crm, status="Signed off")
    crm.add(cfg.TOUCH, {"id": "t1", "channel": "SMS", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "contactId": "c-ok"})
    night = run(sms.run_sms_cycle(_settings(), client=crm, sender=sender, now=NIGHT_EASTERN))
    assert night["campaigns"] == 0 and sender.sent == []
    out = run(sms.run_sms_cycle(_settings(app_base_url="https://apps.example"), client=crm, sender=sender, now=NOON_EASTERN))
    assert out["sent"] == 1
    assert sender.sent[0]["to"] == "+12165550101" and sender.sent[0]["body"] == MESSAGE
    assert sender.sent[0]["status_callback"] == "https://apps.example/api/campaigns/sms/status"
    t = crm.rows[cfg.TOUCH]["t1"]
    assert t["touchStatus"] == "Sent" and t["vendorPieceId"] == "dryrun-t1" and t["calledPhone"] == "+12165550101"
    assert t["stageAtTouch"] == "Qualified"
    assert crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Complete"
    # The touch was marked sending BEFORE the call.
    marks = [p for e, i, p in crm.updated if i == "t1"]
    assert marks[0] == {"vendorStatus": "sending"}


def test_an_interrupted_send_is_never_resent_by_itself():
    crm, sender = FakeCrm(), core_sms.DryRunSmsClient()
    _seed(crm)
    camp = _campaign(crm, status="Running")
    crm.add(cfg.TOUCH, {"id": "t1", "channel": "SMS", "touchStatus": "Planned", "outreachCampaignId": camp["id"],
                        "contactId": "c-ok", "vendorStatus": "sending"})
    out = run(sms.run_campaign(crm, camp, sender=sender, settings=_settings()))
    assert out["review"] == 1 and sender.sent == []
    assert crm.rows[cfg.TOUCH]["t1"]["vendorStatus"] == sms.NEEDS_REVIEW
    assert crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Running"     # not complete while one waits


class _Refusing:
    def __init__(self, exc):
        self.exc = exc

    async def send(self, **kw):
        raise self.exc


def test_a_refused_number_is_cancelled_and_a_timeout_goes_to_review():
    crm = FakeCrm()
    _seed(crm)
    camp = _campaign(crm, status="Running")
    crm.add(cfg.TOUCH, {"id": "t1", "channel": "SMS", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "contactId": "c-ok"})
    run(sms.run_campaign(crm, camp, sender=_Refusing(core_sms.SmsError("21610 unsubscribed", permanent=True)), settings=_settings()))
    assert crm.rows[cfg.TOUCH]["t1"]["touchStatus"] == "Cancelled"
    crm.add(cfg.TOUCH, {"id": "t2", "channel": "SMS", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "contactId": "c-ok"})
    run(sms.run_campaign(crm, camp, sender=_Refusing(core_sms.SmsError("timed out", ambiguous=True)), settings=_settings()))
    assert crm.rows[cfg.TOUCH]["t2"]["vendorStatus"] == sms.NEEDS_REVIEW and crm.rows[cfg.TOUCH]["t2"]["touchStatus"] == "Planned"


def test_consent_withdrawn_before_the_send_cancels_the_touch():
    crm, sender = FakeCrm(), core_sms.DryRunSmsClient()
    _seed(crm)
    camp = _campaign(crm, status="Running")
    crm.rows["Contact"]["c-ok"]["cSmsOptIn"] = False
    crm.add(cfg.TOUCH, {"id": "t1", "channel": "SMS", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "contactId": "c-ok"})
    run(sms.run_campaign(crm, camp, sender=sender, settings=_settings()))
    assert sender.sent == [] and crm.rows[cfg.TOUCH]["t1"]["touchStatus"] == "Cancelled"


def test_stop_opts_the_number_out_and_delivery_is_recorded():
    crm = FakeCrm()
    _seed(crm)
    assert run(sms.apply_stop(crm, "+1 216 555 0101")) == ["c-ok"]
    assert crm.rows["Contact"]["c-ok"]["cSmsOptIn"] is False
    crm.add(cfg.TOUCH, {"id": "t9", "vendorPieceId": "SM1", "touchStatus": "Sent"})
    assert run(sms.apply_status(crm, message_id="SM1", status="delivered"))["applied"] is True
    assert crm.rows[cfg.TOUCH]["t9"]["touchStatus"] == "Delivered"
    run(sms.apply_status(crm, message_id="SM1", status="undelivered", error_code="30003"))
    assert crm.rows[cfg.TOUCH]["t9"]["vendorStatus"] == "undelivered 30003"


def test_message_parts_and_stop_words():
    assert core_sms.segments("a" * 160)["parts"] == 1
    assert core_sms.segments("a" * 161)["parts"] == 2
    assert core_sms.segments("café ☕")["encoding"] == "UCS-2"
    assert core_sms.segments("x" * 70 + "☕")["parts"] == 2
    assert core_sms.is_stop_reply(" stop. ") and core_sms.is_stop_reply("Unsubscribe")
    assert not core_sms.is_stop_reply("please stop by tomorrow")
    assert sms.check_message("Hello")["problems"] and not sms.check_message(MESSAGE)["problems"]


def test_twilio_signature_round_trip():
    params = {"From": "+12165550101", "Body": "STOP", "MessageSid": "SM1"}
    sig = core_sms.twilio_signature("tok", "https://apps.example/api/campaigns/sms/inbound", params)
    core_sms.verify_twilio_signature("tok", "https://apps.example/api/campaigns/sms/inbound", params, sig)
    with pytest.raises(core_sms.SmsSignatureError):
        core_sms.verify_twilio_signature("tok", "https://apps.example/api/campaigns/sms/inbound", {**params, "Body": "x"}, sig)


def test_callbacks_are_404_until_the_real_service_and_verify_signatures(monkeypatch):
    from urllib.parse import urlencode
    crm = FakeCrm()
    _seed(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    assert client.post("/api/campaigns/sms/inbound", content="From=%2B12165550101&Body=STOP",
                       headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 404
    monkeypatch.setenv("CAMPAIGNS_SMS", "true")
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("SMS_AUTH_TOKEN", "tok")
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example")
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    client.app.state.events_client_factory = lambda: crm
    params = {"From": "+12165550101", "Body": "STOP"}
    bad = client.post("/api/campaigns/sms/inbound", content=urlencode(params),
                      headers={"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": "nope"})
    assert bad.status_code == 401 and crm.rows["Contact"]["c-ok"]["cSmsOptIn"] is True
    sig = core_sms.twilio_signature("tok", "https://apps.example/api/campaigns/sms/inbound", params)
    ok = client.post("/api/campaigns/sms/inbound", content=urlencode(params),
                     headers={"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": sig})
    assert ok.status_code == 200 and "<Response>" in ok.text
    assert crm.rows["Contact"]["c-ok"]["cSmsOptIn"] is False


def test_the_sms_kind_is_offered_only_with_the_switch_and_the_message_frozen_after_sign_off():
    from campaigns import service
    crm = FakeCrm()
    with pytest.raises(CampaignError):
        run(service.create_campaign(crm, {"name": "T", "campaignKind": "SMS"}, user_id="u"))
    made = run(service.create_campaign(crm, {"name": "T", "campaignKind": "SMS", "smsMessage": MESSAGE}, user_id="u", sms_on=True))
    assert made["smsMessage"] == MESSAGE
    signed = {**made, "campaignStatus": "Signed off"}
    with pytest.raises(CampaignError, match="frozen"):
        run(service.update_campaign(crm, signed, {"smsMessage": "changed STOP"}, sms_on=True))
    # A non-SMS campaign never carries the wording.
    card = run(service.create_campaign(crm, {"name": "C", "campaignKind": "Postcard", "smsMessage": "x"}, user_id="u"))
    assert "smsMessage" not in card


def test_a_crm_without_the_message_field_drops_it_and_says_so():
    from campaigns import service
    crm = FakeCrm()
    crm.with_sms_field = False
    made = run(service.create_campaign(crm, {"name": "T", "campaignKind": "SMS", "smsMessage": MESSAGE}, user_id="u", sms_on=True))
    assert "smsMessage" not in made
    assert run(sms.message_field_available(crm)) is False
    assert run(service.field_options(crm))["missingFields"] == ["smsMessage"]
