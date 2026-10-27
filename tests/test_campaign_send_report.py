"""The Constant Contact send report and the Recipients view (build plan
§ 7e.9, ruling 96; step M9)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from campaigns import config as cfg
from campaigns import send_report
from core.config import Settings
from tests.test_campaigns import MARKETING, FakeCrm, FakeStore, build


def run(coro):
    return asyncio.run(coro)


SETTINGS = Settings(campaign_send_report=True, campaign_lists=True, campaign_list_sync=True,
                    mailing_client_id="id", mailing_client_secret="secret", espo_dry_run=False)


class ReportCrm(FakeCrm):
    """FakeCrm whose touch carries the opens fields (or not) and the vendor id."""

    def __init__(self, *, opens: bool = True):
        super().__init__()
        self.opens = opens

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.TOUCH}.fields":
            base = {"clickCount": {"type": "int"}, "firstClickedAt": {"type": "datetime"}}
            if self.opens:
                base.update(openCount={"type": "int"}, firstOpenedAt={"type": "datetime"})
            return base
        if key == f"entityDefs.{cfg.CAMPAIGN}.fields":
            out = dict(await super().metadata(key) or {})
            out["vendorEmailId"] = {"type": "varchar"}
            return out
        return await super().metadata(key)


class FakeMail:
    """The vendor: one email, one primary activity, four tracking reports."""

    def __init__(self, tracking):
        self.tracking = tracking
        self.paths: list[str] = []

    async def email_campaign(self, campaign_id):
        return {"campaign_id": campaign_id, "campaign_activities": [
            {"role": "permalink", "campaign_activity_id": "perma"},
            {"role": "primary_email", "campaign_activity_id": "act-1"}]}

    async def _iter_pages(self, path, params, *, key):
        assert key == "tracking_activities" and path.startswith("/reports/email_reports/act-1/tracking/")
        self.paths.append(path)
        for row in self.tracking.get(path.rsplit("/", 1)[1], []):
            yield row


def _row(email, when, **kw):
    return {"email_address": email, "created_time": when, **kw}


TRACKING = {
    "sends": [_row("pat@x.org", "2026-10-27T15:00:00Z"), _row("Bea@X.org", "2026-10-27T15:00:01Z"),
              _row("member@cbmentors.org", "2026-10-27T15:00:02Z"), _row("stranger@y.org", "2026-10-27T15:00:03Z")],
    "bounces": [_row("bea@x.org", "2026-10-27T15:05:00Z", bounce_code="B")],
    "opens": [_row("pat@x.org", "2026-10-27T16:00:00Z"), _row("pat@x.org", "2026-10-27T15:30:00Z")],
    "clicks": [_row("pat@x.org", "2026-10-27T16:10:00Z", link_url="https://x")],
}


def _world(opens=True):
    crm = ReportCrm(opens=opens)
    pat = crm.add(cfg.CONTACT, {"name": "Pat Prospect", "emailAddress": "pat@x.org"})
    bea = crm.add(cfg.CONTACT, {"name": "Bea Bounce", "emailAddress": "bea@x.org"})
    mem = crm.add(cfg.CONTACT, {"name": "Mo Member", "emailAddress": "mo@home.net"})
    crm.add("CMentorProfile", {"cbmEmail": "member@cbmentors.org", "contactRecordId": mem["id"]})
    camp = crm.add(cfg.CAMPAIGN, {"name": "Autumn notice", "campaignKind": cfg.KIND_EMAIL,
                                  "campaignStatus": cfg.STATUS_RUNNING, "vendorEmailId": "cc-email-1",
                                  "runStartedAt": "2026-10-27 14:00:00"})
    return crm, camp, {"pat": pat, "bea": bea, "mem": mem}


def _touches(crm, camp):
    return {t["contactId"]: t for t in crm.rows.get(cfg.TOUCH, {}).values() if t.get("outreachCampaignId") == camp["id"]}


NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def test_summarise_folds_every_kind_into_one_row_per_address():
    people = send_report.summarise(TRACKING)
    assert set(people) == {"pat@x.org", "bea@x.org", "member@cbmentors.org", "stranger@y.org"}
    pat = people["pat@x.org"]
    assert (pat.sent_at, pat.opens, pat.first_open, pat.clicks, pat.first_click) == (
        "2026-10-27 15:00:00", 2, "2026-10-27 15:30:00", 1, "2026-10-27 16:10:00")
    assert people["bea@x.org"].bounced_at == "2026-10-27 15:05:00" and people["bea@x.org"].bounce_code == "B"


def test_one_touch_per_recipient_matched_by_email_and_chapter_address():
    crm, camp, who = _world()
    mail = FakeMail(TRACKING)
    result = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=mail, now=NOW))
    assert result.ok, result.error
    assert (result.recipients, result.created, result.updated) == (4, 3, 0)
    assert result.unmatched == ["stranger@y.org"]                       # counted, never created
    t = _touches(crm, camp)
    assert set(t) == {who["pat"]["id"], who["bea"]["id"], who["mem"]["id"]}
    pat = t[who["pat"]["id"]]
    assert pat["touchStatus"] == "Delivered" and pat["openCount"] == 2 and pat["clickCount"] == 1
    assert pat["outcome"] == "Clicked" and pat["channel"] == "Email" and pat["vendorPieceId"] == "cc-email-1"
    bea = t[who["bea"]["id"]]
    assert bea["touchStatus"] == "Returned" and bea["returnedAt"] == "2026-10-27 15:05:00"
    assert bea["vendorStatus"] == "bounced: B"
    assert len(mail.paths) == 4


def test_a_second_read_never_doubles_and_writes_only_what_changed():
    crm, camp, who = _world()
    run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW))
    again = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW))
    assert (again.created, again.updated, again.unchanged) == (0, 0, 3)
    more = {**TRACKING, "opens": TRACKING["opens"] + [_row("member@cbmentors.org", "2026-10-28T09:00:00Z")]}
    crm.updated.clear()
    third = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(more), now=NOW))
    assert (third.created, third.updated) == (0, 1)
    (_e, tid, changes), = [u for u in crm.updated if u[0] == cfg.TOUCH]
    assert set(changes) == {"openCount", "firstOpenedAt"}
    assert len(_touches(crm, camp)) == 3


def test_a_human_outcome_is_never_overwritten():
    crm, camp, who = _world()
    crm.add(cfg.TOUCH, {"outreachCampaignId": camp["id"], "contactId": who["pat"]["id"], "channel": "Email",
                        "touchStatus": "Delivered", "outcome": "Interested"})
    run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW))
    assert _touches(crm, camp)[who["pat"]["id"]]["outcome"] == "Interested"


def test_without_the_opens_fields_the_rest_is_still_recorded():
    crm, camp, who = _world(opens=False)
    result = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW))
    pat = _touches(crm, camp)[who["pat"]["id"]]
    assert "openCount" not in pat and pat["clickCount"] == 1 and result.opens_recorded is False
    assert "Opens are not recorded" in result.words()


def test_the_web_cap_leaves_the_rest_for_the_nightly_pass():
    crm, camp, _who = _world()
    result = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW, max_writes=1))
    assert (result.created, result.left_for_later) == (1, 2)
    assert "nightly pass" in result.words()


def test_the_campaign_completes_when_the_reading_window_closes():
    crm, camp, _who = _world()
    early = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING), now=NOW))
    assert early.completed is False and crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Running"
    late = run(send_report.read_campaign(SETTINGS, camp, crm=crm, mail=FakeMail(TRACKING),
                                         now=datetime(2026, 12, 1, tzinfo=timezone.utc)))
    assert late.completed is True
    row = crm.rows[cfg.CAMPAIGN][camp["id"]]
    assert row["campaignStatus"] == "Complete" and row["runCompletedAt"].startswith("2026-12-01")


def test_no_picked_email_and_switch_off_are_refused_in_words():
    crm, camp, _who = _world()
    out = run(send_report.read_campaign(SETTINGS, {**camp, "vendorEmailId": ""}, crm=crm, mail=FakeMail({})))
    assert not out.ok and "Pick the email" in out.error
    assert "switched off" in send_report.refusal(Settings(campaign_send_report=False))
    assert send_report.refusal(SETTINGS) == ""


def test_the_worker_pass_reads_every_running_picked_email():
    crm, camp, _who = _world()
    crm.add(cfg.CAMPAIGN, {"name": "Not picked", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": "Running"})
    crm.add(cfg.CAMPAIGN, {"name": "Postcard", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": "Running",
                           "vendorEmailId": "x"})
    read = run(send_report.run_report_cycle(SETTINGS, crm=crm, mail=FakeMail(TRACKING), conn_store=object(), now=NOW))
    assert [c["id"] for c, _r in read] == [camp["id"]] and read[0][1].created == 3
    assert run(send_report.run_report_cycle(Settings(campaign_send_report=False), crm=crm, mail=FakeMail(TRACKING))) == []


# --- the routes ------------------------------------------------------------------------------

def _app(monkeypatch, crm, *, report="true"):
    for k, v in {"CAMPAIGN_LISTS": "true", "CAMPAIGN_LIST_SYNC": "true", "CAMPAIGNS_EMAIL": "true",
                 "CAMPAIGN_SEND_REPORT": report, "MAILING_CLIENT_ID": "id", "MAILING_CLIENT_SECRET": "s",
                 "CAMPAIGN_LISTS_ONLY": "true"}.items():
        monkeypatch.setenv(k, v)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    import campaigns.router as router_mod
    import campaigns.list_sync as list_sync
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    monkeypatch.setattr(router_mod, "_system_client", lambda settings: crm)
    monkeypatch.setattr(list_sync, "mail_clients", lambda settings: (FakeMail(TRACKING), object()))
    monkeypatch.setattr(send_report, "refusal", lambda settings: "" if settings.campaign_send_report
                        else "The send report is switched off (Campaign send report at /setup).")
    return client


def test_read_the_report_now_and_the_recipients_view(monkeypatch):
    crm, camp, who = _world()
    crm.add(cfg.TOUCH, {"outreachCampaignId": camp["id"], "channel": "Email", "touchStatus": "Cancelled",
                        "contactId": "c-old", "contactName": "Old Planned", "name": "Autumn notice — old"})
    client = _app(monkeypatch, crm)
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/report")
    assert resp.status_code == 200, resp.text
    assert resp.json()["report"]["created"] == 3 and "stranger@y.org" in resp.json()["words"]
    body = client.get(f"/campaigns/api/campaigns/{camp['id']}/recipients").json()
    assert body["all"] == 4 and body["opensRecorded"] is True
    assert body["statusCounts"] == {"Cancelled": 1, "Delivered": 2, "Returned": 1}
    pat = next(r for r in body["recipients"] if r["reachedAt"] == "pat@x.org")
    assert pat["opens"] == 2 and pat["clicks"] == 1 and pat["status"] == "Delivered"
    found = client.get(f"/campaigns/api/campaigns/{camp['id']}/recipients?q=bea").json()
    assert [r["reachedAt"].lower() for r in found["recipients"]] == ["bea@x.org"]
    returned = client.get(f"/campaigns/api/campaigns/{camp['id']}/recipients?status=Returned").json()
    assert returned["total"] == 1
    paged = client.get(f"/campaigns/api/campaigns/{camp['id']}/recipients?limit=2&offset=2").json()
    assert len(paged["recipients"]) == 2 and paged["total"] == 4
    csv = client.get(f"/campaigns/api/campaigns/{camp['id']}/recipients.csv?status=Delivered")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("Recipient,Type,Reached at")
    assert len(csv.text.strip().splitlines()) == 3 and "Opens" in csv.text.splitlines()[0]


def test_read_now_is_refused_in_words(monkeypatch):
    crm, camp, _who = _world()
    client = _app(monkeypatch, crm, report="false")
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/report")
    assert resp.status_code == 400 and "switched off" in resp.json()["detail"]
    client = _app(monkeypatch, crm)
    postcard = crm.add(cfg.CAMPAIGN, {"name": "Cards", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": "Running"})
    resp = client.post(f"/campaigns/api/campaigns/{postcard['id']}/report")
    assert resp.status_code == 400 and "email campaign" in resp.json()["detail"]
