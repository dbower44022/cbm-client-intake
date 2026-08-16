"""Phase 6b — event follow-up email (EV-60…EV-64).

The rules that must not slip: once per registrant per kind, cancelled and
opted-out excluded, and nothing improvised when a template is missing.
"""

from __future__ import annotations

import pytest

from core.config import Settings, get_settings
from events import config as cfg
from events import notify


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _reg(rid="r1", status=cfg.REG_REGISTERED, email="a@b.org", sent=None, **over):
    row = {"id": rid, "attendanceStatus": status, "email": email,
           "followUpsSent": sent or [], "firstName": "A", "lastName": "B"}
    row.update(over)
    return row


REMINDER = notify.BY_KIND[notify.KIND_REMINDER]
SURVEY = notify.BY_KIND[notify.KIND_SURVEY]


# --- EV-62: once per registrant per kind -------------------------------------

def test_an_already_sent_kind_is_skipped():
    send, skip = notify.plan_sends(REMINDER, [_reg(sent=["Reminder"])])
    assert send == []
    assert skip[0]["reason"] == "already sent"


def test_a_different_kind_already_sent_does_not_block():
    send, _ = notify.plan_sends(REMINDER, [_reg(sent=["Survey"])])
    assert len(send) == 1


# --- EV-63: cancelled and opted-out ------------------------------------------

def test_a_cancelled_registration_gets_nothing():
    send, skip = notify.plan_sends(REMINDER, [_reg(status=cfg.REG_CANCELLED)])
    assert send == []
    assert skip[0]["reason"] == "registration cancelled"


def test_marketing_sends_require_opt_in():
    send, skip = notify.plan_sends(SURVEY, [_reg(status=cfg.REG_ATTENDED)])
    assert send == [] and skip[0]["reason"] == "no marketing opt-in"

    send, _ = notify.plan_sends(
        SURVEY, [_reg(status=cfg.REG_ATTENDED, marketingOptIn=True)]
    )
    assert len(send) == 1


def test_operational_sends_do_not_require_opt_in():
    """A reminder is about a thing the person signed up for, not marketing."""
    send, _ = notify.plan_sends(REMINDER, [_reg()])
    assert len(send) == 1


def test_the_contacts_opt_in_counts_too():
    send, _ = notify.plan_sends(
        SURVEY,
        [_reg(status=cfg.REG_ATTENDED, contactId="c1")],
        {"c1": {"cMarketingOptIn": True}},
    )
    assert len(send) == 1


# --- status and address gates -------------------------------------------------

def test_a_no_show_does_not_get_the_mentor_cta():
    send, skip = notify.plan_sends(
        notify.BY_KIND[notify.KIND_MENTOR_CTA], [_reg(status=cfg.REG_NO_SHOW)]
    )
    assert send == [] and "status is" in skip[0]["reason"]


def test_a_registrant_without_an_address_is_skipped():
    send, skip = notify.plan_sends(REMINDER, [_reg(email="")])
    assert send == [] and skip[0]["reason"] == "no email address"


# --- the ledger ---------------------------------------------------------------

class FakeCrm:
    def __init__(self, options=None):
        self.options = options
        self.updates = []

    async def metadata_enum_options(self, entity, field):
        return self.options

    async def update(self, entity, rid, payload):
        self.updates.append((rid, payload))
        return {"id": rid}


async def test_recording_a_send_appends_without_losing_earlier_kinds():
    crm = FakeCrm(options=["Reminder", "Survey"])
    assert await notify.record_sent(crm, _reg(sent=["Survey"]), "Reminder") is True
    assert crm.updates[0][1] == {"followUpsSent": ["Survey", "Reminder"]}


async def test_a_kind_missing_from_the_crm_enum_is_not_written():
    """An out-of-enum multiEnum value 400s the whole update — the trap that
    silently lost every event registration's receipt in v0.192.3."""
    crm = FakeCrm(options=["Recording"])
    assert await notify.record_sent(crm, _reg(), "Reminder") is False
    assert crm.updates == []


async def test_recording_is_idempotent():
    crm = FakeCrm(options=["Reminder"])
    assert await notify.record_sent(crm, _reg(sent=["Reminder"]), "Reminder") is True
    assert crm.updates == []      # nothing to do


# --- gating -------------------------------------------------------------------

def test_inert_without_the_send_stack(monkeypatch):
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    get_settings.cache_clear()
    # Gmail sync and the shared mailbox are both unset.
    assert notify.notify_active(get_settings()) is False


async def test_preview_never_sends():
    """`preview` is the default on the endpoint precisely so a mis-scripted call
    cannot email a roster."""
    result = await notify.send_follow_up(
        Settings(), FakeCrm(), {"id": "e1", "name": "X"}, REMINDER,
        registrations=[_reg()], dry_run=True,
    )
    assert result["dryRun"] is True and result["sent"] == 0
    assert [r["email"] for r in result["recipients"]] == ["a@b.org"]


def test_every_kind_matches_a_crm_ledger_value():
    """The ledger values are an enum in the CRM; a typo here would 400 every
    write for that kind."""
    assert {f.kind for f in notify.FOLLOW_UPS} == {
        "Reminder", "Recording", "No Show", "Mentor CTA", "Survey",
    }
