"""Campaign Management, Phase 4 — the email kind (build plan § 3.3; rulings 19, 25).

The boundaries: no cold email (opt-in and a usable address, a Contact only);
the dormant-client term; the push makes the campaign's OWN list and never
touches the standing list or its stored id; an address the vendor holds as
unsubscribed is withheld; Mark as sent only after the push.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from campaigns import config as cfg
from campaigns import email
from campaigns.service import CampaignError
from core.config import Settings
from tests.test_campaigns import FakeCrm


def run(coro):
    return asyncio.run(coro)


class FakeMail:
    def __init__(self, unsubscribed=()):
        self.lists = {"l-standing": "Event notices"}
        self.imported: list[tuple[str, list]] = []
        self.unsubscribed = set(unsubscribed)

    async def find_list(self, name):
        for i, n in self.lists.items():
            if n.casefold() == name.casefold():
                return {"list_id": i, "name": n}
        return None

    async def create_list(self, name):
        i = f"l-{len(self.lists) + 1}"
        self.lists[i] = name
        return {"list_id": i}

    async def import_contacts(self, rows, *, list_id):
        self.imported.append((list_id, rows))
        return ["act-1"]

    def contacts(self, *, list_id=None, status=None, **kw):
        async def gen():
            if status == "unsubscribed":
                for e in self.unsubscribed:
                    yield {"contact_id": e, "email_address": {"address": e}}
        return gen()


def _seed(crm):
    crm.add("Contact", {"id": "c-ok", "name": "Pat", "firstName": "Pat", "emailAddress": "pat@ex.example",
                        "cMarketingOptIn": True, "cContactType": ["Prospect"], "cFunnelStage": "Warm Lead"})
    crm.add("Contact", {"id": "c-cold", "name": "Cold", "emailAddress": "cold@ex.example",
                        "cMarketingOptIn": False, "cContactType": ["Prospect"], "cFunnelStage": "Warm Lead"})
    crm.add("Contact", {"id": "c-bad", "name": "Bad", "emailAddress": "bad@ex.example", "emailAddressIsInvalid": True,
                        "cMarketingOptIn": True, "cContactType": ["Prospect"], "cFunnelStage": "Warm Lead"})
    crm.add("Contact", {"id": "c-unsub", "name": "Uns", "emailAddress": "uns@ex.example",
                        "cMarketingOptIn": True, "cContactType": ["Prospect"], "cFunnelStage": "Lead"})
    crm.add("Contact", {"id": "c-old", "name": "Old Client", "emailAddress": "old@ex.example",
                        "cMarketingOptIn": True, "cContactType": ["Client"]})
    crm.add("Contact", {"id": "c-live", "name": "Live Client", "emailAddress": "live@ex.example",
                        "cMarketingOptIn": True, "cContactType": ["Client"]})
    crm.add("CEngagement", {"engagementStatus": "Completed", "closeDate": "2024-01-10", "primaryEngagementContactId": "c-old"})
    crm.add("CEngagement", {"engagementStatus": "Completed", "closeDate": "2024-01-10", "primaryEngagementContactId": "c-live"})
    crm.add("CEngagement", {"engagementStatus": "Active", "primaryEngagementContactId": "c-live"})


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def test_no_cold_email_and_the_dormant_term():
    crm = FakeCrm()
    _seed(crm)
    got = {t["id"] for t in run(email.select_targets(crm, {"stages": ["Lead", "Warm Lead"]}, now=NOW))}
    assert got == {"c-ok", "c-unsub"}
    with_dormant = {t["id"] for t in run(email.select_targets(crm, {"stages": [], "dormantDays": 365}, now=NOW))}
    assert with_dormant == {"c-old"}                          # the live client is not dormant
    assert run(email.select_targets(crm, {"stages": [], "dormantDays": 3650}, now=NOW)) == []


def test_build_sign_off_push_and_mark_sent():
    crm, mail = FakeCrm(), FakeMail(unsubscribed={"uns@ex.example"})
    _seed(crm)
    camp = crm.add(cfg.CAMPAIGN, {"name": "Autumn notice", "campaignKind": "Email", "campaignStatus": "Draft"})
    built = run(email.build_list(crm, crm, camp, {"stages": ["Lead", "Warm Lead"]}))
    assert built["pieces"] == 2
    settings = Settings(_env_file=None, mailing_client_id="id", mailing_client_secret="s")
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    with pytest.raises(CampaignError, match="Type the number"):
        run(email.sign_off(crm, crm, camp, confirm="9", user_name="Mark", settings=settings))
    run(email.sign_off(crm, crm, camp, confirm="2", user_name="Mark", settings=settings))
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    with pytest.raises(CampaignError, match="Running"):
        run(email.mark_as_sent(crm, camp))
    out = run(email.push_campaign(crm, mail, camp))
    assert out == {"pushed": 1, "withheld": 1, "skipped": 0}
    # Its OWN list, named for the campaign; the standing list untouched.
    (list_id, rows), = mail.imported
    assert mail.lists[list_id] == "Campaign — Autumn notice" and list_id != "l-standing"
    assert rows == [{"email": "pat@ex.example", "first_name": "Pat"}]
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    assert camp["campaignStatus"] == "Running"
    # A second pass pushes nobody twice.
    assert run(email.push_campaign(crm, mail, camp))["pushed"] == 0
    assert run(email.mark_as_sent(crm, camp)) == {"sent": 1}
    assert crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Complete"
    statuses = sorted(t["touchStatus"] for t in crm.rows[cfg.TOUCH].values())
    assert statuses == ["Cancelled", "Sent"]


def test_sign_off_refuses_without_the_mailing_connection_or_a_name_clash():
    crm = FakeCrm()
    _seed(crm)
    camp = crm.add(cfg.CAMPAIGN, {"name": "x", "campaignKind": "Email", "campaignStatus": "Awaiting sign-off"})
    crm.add(cfg.TOUCH, {"touchStatus": "Planned", "outreachCampaignId": camp["id"], "contactId": "c-ok"})
    with pytest.raises(CampaignError, match="not connected"):
        run(email.sign_off(crm, crm, camp, confirm="1", user_name="M", settings=Settings(_env_file=None)))
    clash = Settings(_env_file=None, mailing_client_id="i", mailing_client_secret="s", mailing_list_name="Campaign — x")
    with pytest.raises(CampaignError, match="standing"):
        run(email.sign_off(crm, crm, camp, confirm="1", user_name="M", settings=clash))
