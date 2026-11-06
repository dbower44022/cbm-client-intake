"""Mentor login integrity, step 4c items 8 and 9 (plan § 4.2; Doug's C2
ruling 11-05-26, on the web component): who edited records in the CRM's own
screens, and screen sign-ins by a shared account. The application's own
addresses are never counted; the configuration, provisioning and key-based
accounts are never reported for edits; a run records each finding once a day."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import Settings
from integrity import crm_use
from tests.test_integrity_signin import Store

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)
APP = "10.0.0.1"      # the application's egress address
OFFICE = "203.0.113.7"  # someone's office, in the CRM's screens

USERS = [
    {"id": "uKey", "userName": "api.intake", "type": "api", "name": "Intake API"},
    {"id": "uSue", "userName": "sue.staff@cbmentors.org", "type": "regular", "name": "Sue Staff"},
    {"id": "uCfg", "userName": "crm.config", "type": "admin", "name": "Config"},
    {"id": "uProv", "userName": "mentoradmin@cbmentors.org", "type": "admin", "name": "Provisioning"},
    {"id": "uAdm", "userName": "admin", "type": "admin", "name": "Administrator"},
    {"id": "uJo", "userName": "jo.mentor@cbmentors.org", "type": "regular", "name": "Jo Mentor"},
]
SIGNINS = [
    {"username": "sue.staff@cbmentors.org", "ipAddress": OFFICE},
    {"username": "admin", "ipAddress": OFFICE},
    {"username": "admin", "ipAddress": OFFICE, "isDenied": True},
    {"username": "jo.mentor@cbmentors.org", "ipAddress": APP},
    {"username": "mentoradmin@cbmentors.org", "ipAddress": APP},
]
HISTORY = [
    {"userId": "uSue", "action": "update", "targetType": "CMentorProfile", "ipAddress": OFFICE},
    {"userId": "uSue", "action": "update", "targetType": "CMentorProfile", "ipAddress": OFFICE},
    {"userId": "uSue", "action": "create", "targetType": "Contact", "ipAddress": OFFICE},
    {"userId": "uSue", "action": "update", "targetType": "Contact", "ipAddress": APP},  # in the app
    {"userId": "uCfg", "action": "update", "targetType": "Role", "ipAddress": OFFICE},
    {"userId": "uProv", "action": "create", "targetType": "User", "ipAddress": OFFICE},
    {"userId": "uKey", "action": "create", "targetType": "CActionLog", "ipAddress": APP},
    {"userId": "uJo", "action": "update", "targetType": "CSession", "ipAddress": APP},
]


class Crm:
    def __init__(self, cap=None):
        self.cap = cap
        self.wheres: list = []

    async def app_user(self):
        return {"user": {"id": "uKey", "userName": "api.intake"}}

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        self.wheres.append((entity, where))
        if entity == "User":
            rows = USERS
        elif entity == "AuthLogRecord":
            w = {c["type"]: c.get("value") for c in where or []}
            if "equals" in w:
                rows = [{"ipAddress": APP}]  # the key's own sign-ins
            else:
                rows = [dict(r, isDenied=r.get("isDenied", False)) for r in SIGNINS]
        elif entity == "ActionHistoryRecord":
            rows = HISTORY * (self.cap or 1)
        else:
            rows = []
        return {"list": rows[offset:offset + max_size]}


def _s(**kw):
    return Settings(mentor_email_domain="cbmentors.org", espo_provision_username="mentoradmin@cbmentors.org", **kw)


async def test_screen_edits_and_shared_sign_ins_are_found_app_traffic_is_not():
    crm, store = Crm(), Store()
    out = await crm_use.run_crm_use_report(_s(), crm, crm, store, now=NOW)
    assert out == {"c8": 1, "c9": 1, "new": 2}
    assert store.keys == {"8:uSue:2026-11-06", "9:admin:2026-11-06"}


async def test_the_summaries_name_counts_never_an_address():
    data = await crm_use.read_window(Crm(), Crm(), _s(), NOW)
    faults = crm_use.find_use(data, _s(), "2026-11-06")
    text = " ".join(f["summary"] for f in faults)
    assert "Sue Staff (sue.staff@cbmentors.org) created, changed or deleted 3 record(s)" in text
    assert "CMentorProfile 2, Contact 1" in text
    assert "The shared account admin signed in to the CRM's own screens 1 time(s)" in text
    assert OFFICE not in text and APP not in text
    # crm.config, the provisioning account and the key are never condition 8
    assert not [f for f in faults if f["condition"] == 8 and f["login"]["id"] in ("uCfg", "uProv", "uKey")]


async def test_a_second_run_the_same_day_records_nothing_new():
    crm, store = Crm(), Store()
    await crm_use.run_crm_use_report(_s(), crm, crm, store, now=NOW)
    out = await crm_use.run_crm_use_report(_s(), crm, crm, store, now=NOW)
    assert out["new"] == 0


async def test_too_much_to_read_records_nothing():
    crm, store = Crm(cap=3000), Store()  # 24,000 change rows
    assert await crm_use.run_crm_use_report(_s(), crm, crm, store, now=NOW) is None
    assert store.keys == set()


def test_shared_accounts_default_from_the_mail_domain_and_can_be_set():
    assert crm_use.shared_accounts(_s()) == ["admin", "admin@cbmentors.org",
                                             "mentoradmin@cbmentors.org"]
    assert crm_use.shared_accounts(_s(integrity_shared_accounts="Root, x@y")) == ["root", "x@y"]


def test_a_listed_address_is_the_application():
    data = {"keyUser": "", "keyId": "", "users": {u["id"]: u for u in USERS},
            "signins": [], "keySignins": [], "history": HISTORY[:3]}
    assert len(crm_use.find_use(data, _s(), "d")) == 1
    assert crm_use.find_use(data, _s(integrity_app_addresses=OFFICE), "d") == []


def test_the_switch_defaults_off_and_is_on_the_setup_page():
    from core.settings_registry import SETTINGS

    assert Settings().integrity_crm_use_report is False
    keys = {s.key for s in SETTINGS}
    assert {"integrity_crm_use_report", "integrity_shared_accounts",
            "integrity_excluded_logins", "integrity_app_addresses"} <= keys


def test_the_report_runs_an_hour_before_the_check():
    from integrity.web_loop import next_report_time

    s = Settings(login_integrity_hour=7, login_integrity_tz="America/New_York")
    assert next_report_time(s, datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)) == \
        datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc)


def test_the_digest_lists_conditions_8_and_9():
    from integrity import digest

    rows = [{"id": "a", "condition": 8, "summary": "Sue edited.", "mentors": [],
             "notified_at": None},
            {"id": "b", "condition": 9, "summary": "admin signed in.", "mentors": [],
             "notified_at": None}]
    _, text = digest.digest_body(Settings(), rows, acknowledged=0, fixed=0)
    assert "Edited in the CRM's own screens (1)" in text
    assert "Shared account signed in to the CRM (1)" in text


async def test_with_no_application_address_known_nothing_is_reported():
    class Quiet(Crm):
        async def list(self, entity, **kw):
            data = await super().list(entity, **kw)
            if entity == "AuthLogRecord" and any(c["type"] == "equals" for c in kw.get("where") or []):
                return {"list": []}  # the key's sign-ins are no longer logged
            if entity == "ActionHistoryRecord":
                return {"list": [r for r in data["list"] if r["userId"] != "uKey"]}
            return data

    store = Store()
    assert await crm_use.run_crm_use_report(_s(), Quiet(), Quiet(), store, now=NOW) is None
    assert store.keys == set()
    # Listing the application's address is enough to run.
    out = await crm_use.run_crm_use_report(_s(integrity_app_addresses=APP), Quiet(), Quiet(),
                                           store, now=NOW)
    assert out["c8"] == 1


async def test_three_staff_behind_one_office_address_are_still_reported():
    class Office(Crm):
        async def list(self, entity, **kw):
            data = await super().list(entity, **kw)
            if entity == "AuthLogRecord" and not any(
                    c["type"] == "equals" for c in kw.get("where") or []):
                data = {"list": data["list"] + [
                    {"username": "a@x", "ipAddress": OFFICE, "isDenied": False},
                    {"username": "b@x", "ipAddress": OFFICE, "isDenied": False}]}
            return data

    store = Store()
    out = await crm_use.run_crm_use_report(_s(), Office(), Office(), store, now=NOW)
    assert out["c8"] == 1 and out["c9"] == 1


async def test_a_failing_administrator_sign_in_is_retried_once_then_waits_a_day(monkeypatch):
    from datetime import timedelta

    from integrity import web_loop

    clock = [NOW]
    calls = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    async def failing(settings):
        calls.append(clock[0])
        raise RuntimeError("login refused")

    ticks = []

    async def sleep(seconds):
        ticks.append(seconds)
        clock[0] = clock[0] + timedelta(seconds=seconds)
        if len(ticks) > 6 * 30:  # thirty hours of ten-minute ticks
            raise asyncio.CancelledError

    import asyncio

    monkeypatch.setattr(web_loop, "datetime", Clock)
    monkeypatch.setattr(web_loop, "run_once", failing)
    monkeypatch.setattr(web_loop.asyncio, "sleep", sleep)
    monkeypatch.setattr(web_loop, "get_settings", lambda: Settings(
        integrity_crm_use_report=True, login_integrity_hour=7,
        login_integrity_tz="America/New_York"))
    with pytest.raises(asyncio.CancelledError):
        await web_loop.crm_use_loop()
    # 06:00 Eastern on 11-06 (11:00 UTC), its one retry, then 06:00 the next day and its retry.
    assert len(calls) == 4
    assert calls[1] - calls[0] <= timedelta(minutes=40)
    assert calls[2] - calls[0] >= timedelta(hours=23)
