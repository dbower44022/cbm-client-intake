"""Mentor login integrity, step 4a (prds/mentor-login-integrity-plan.md § 4.2):
the six daily conditions, the read under the key, the run that records them,
the schedule and the read-only report.

The fixture replays the 10-16-26 fault: Doug Bower's login (uD) on David
Weissman's Approved profile (MP-DW, CBM email Doug.Bower@…) and on Doug's own
Active profile (MP-DB); David's Contact still carries David's own login (uDW)
and now Doug's too. The check must find it under condition 1 and condition 6.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.config import Settings
from integrity import check, run
from integrity.check import CrmSnapshot, find_faults, read_crm


def _snap(**over) -> CrmSnapshot:
    values: dict[str, Any] = dict(
        profiles=[
            {"id": "MP-DW", "name": "David Weissman", "mentorStatus": "Approved",
             "cbmEmail": "Doug.Bower@cbmentors.org", "assignedUsersIds": ["uD"],
             "contactRecordId": "C-DW"},
            {"id": "MP-DB", "name": "Douglas Bower", "mentorStatus": "Active",
             "cbmEmail": "doug.bower@cbmentors.org", "assignedUsersIds": ["uD"],
             "contactRecordId": "C-DB"},
            {"id": "MP-J", "name": "Jane Doe", "mentorStatus": "Active",
             "cbmEmail": "jane.doe@cbmentors.org", "assignedUsersIds": ["uJ"],
             "contactRecordId": "C-J"},
        ],
        users={
            "uD": {"id": "uD", "userName": "doug.bower@cbmentors.org", "isActive": True,
                   "type": "admin", "name": "Doug Bower"},
            "uJ": {"id": "uJ", "userName": "jane.doe@cbmentors.org", "isActive": True,
                   "type": "regular", "name": "Jane Doe"},
            "uDW": {"id": "uDW", "userName": "david.weissman@cbmentors.org",
                    "isActive": True, "type": "regular", "name": "David Weissman"},
        },
        team_members={"Mentor Team": {"uD", "uJ", "uDW"}},
        contacts={"C-DW": ["uDW", "uD"], "C-DB": ["uD"], "C-J": ["uJ"]},
    )
    values.update(over)
    return CrmSnapshot(**values)


def _by_cond(faults) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for f in faults:
        out.setdefault(f["condition"], []).append(f)
    return out


def test_the_10_16_fault_is_found_under_conditions_1_5_and_6():
    got = _by_cond(find_faults(_snap()))
    assert [f["key"] for f in got[1]] == ["1:uD"]
    assert "doug.bower@cbmentors.org is on 2 mentor profiles" in got[1][0]["summary"]
    assert {m["id"] for m in got[1][0]["mentors"]} == {"MP-DW", "MP-DB"}
    # David's own login sits on the Mentor Team and on no profile.
    assert [f["key"] for f in got[5]] == ["5:uDW"]
    # David's Contact carries David's login, which is not his profile's login.
    assert [f["key"] for f in got[6]] == ["6:MP-DW:uDW"]
    # His CBM email matches the (wrong) login ignoring case, so not condition 2;
    # the address appears on two profiles ignoring case, so condition 3.
    assert 2 not in got
    assert [f["key"] for f in got[3]] == ["3:doug.bower@cbmentors.org"]
    assert 4 not in got


def test_a_clean_chapter_has_no_faults():
    snap = _snap(
        profiles=[{"id": "MP-J", "name": "Jane Doe", "mentorStatus": "Active",
                   "cbmEmail": "Jane.Doe@cbmentors.org ", "assignedUserId": "uJ",
                   "contactRecordId": "C-J"}],
        team_members={"Mentor Team": {"uJ"}}, contacts={"C-J": ["uJ"]})
    assert find_faults(snap) == []


def test_condition_2_names_both_addresses_and_a_blank_one():
    snap = _snap(profiles=[
        {"id": "A", "name": "A", "cbmEmail": "a@x.org", "assignedUsersIds": ["uJ"]},
        {"id": "B", "name": "B", "cbmEmail": "", "assignedUsersIds": ["uDW"]},
    ], team_members={}, contacts={})
    got = _by_cond(find_faults(snap))
    assert [f["key"] for f in got[2]] == ["2:A", "2:B"]
    assert "a@x.org, but the login is jane.doe@cbmentors.org" in got[2][0]["summary"]
    assert "CBM email is blank" in got[2][1]["summary"]


def test_condition_4_only_for_approved_or_active_and_a_vanished_login_counts():
    snap = _snap(profiles=[
        {"id": "A", "name": "A", "mentorStatus": "Approved"},
        {"id": "B", "name": "B", "mentorStatus": "Active", "assignedUsersIds": ["gone"]},
        {"id": "C", "name": "C", "mentorStatus": "Candidate"},
    ], team_members={}, contacts={})
    got = _by_cond(find_faults(snap))
    assert [f["key"] for f in got[4]] == ["4:A", "4:B"]
    assert "has no login" in got[4][0]["summary"]
    assert "no longer exists" in got[4][1]["summary"]


def test_condition_5_skips_inactive_api_and_profiled_logins():
    users = {
        "u1": {"id": "u1", "userName": "a", "isActive": False, "type": "regular"},
        "u2": {"id": "u2", "userName": "b", "isActive": True, "type": "api"},
        "u3": {"id": "u3", "userName": "c", "isActive": True, "type": "regular"},
        "u4": {"id": "u4", "userName": "d", "isActive": True, "type": "regular"},
    }
    snap = CrmSnapshot(
        profiles=[{"id": "P", "name": "P", "cbmEmail": "c", "assignedUsersIds": ["u3"]}],
        users=users,
        team_members={"Mentor Team": {"u1", "u2", "u3"}, "Partner Management Team": {"u4"}},
        contacts={})
    got = _by_cond(find_faults(snap))
    assert [f["key"] for f in got[5]] == ["5:u4"]
    assert "Partner Management Team" in got[5][0]["summary"]


def test_keys_are_stable_between_runs():
    assert [f["key"] for f in find_faults(_snap())] == [f["key"] for f in find_faults(_snap())]


# --- the read, under the key ---------------------------------------------------

TEAMS = {"Mentor Team": "T1", "Partner Management Team": "T2",
         "Sponsor Management Team": "T3"}


class FakeCrm:
    def __init__(self, snap: CrmSnapshot, teams: dict[str, str], fail: str = ""):
        self.snap, self.teams, self.fail = snap, teams, fail
        self.calls: list[tuple[str, Any]] = []

    async def list(self, entity, *, select=None, where=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        self.calls.append((entity, where))
        if entity == self.fail:
            raise RuntimeError("HTTP 500")
        if entity == "CMentorProfile":
            rows = self.snap.profiles
        elif entity == "Team":
            rows = [{"id": i, "name": n} for n, i in self.teams.items()]
        elif entity == "User" and where:
            team = {i: n for n, i in self.teams.items()}[where[0]["value"][0]]
            rows = [{"id": u} for u in sorted(self.snap.team_members.get(team, set()))
                    if u not in self.hidden]
        elif entity == "User":
            rows = list(self.snap.users.values())
        elif entity == "Contact":
            ids = where[0]["value"]
            rows = [{"id": c, "assignedUsersIds": self.snap.contacts[c]}
                    for c in ids if c in self.snap.contacts]
        else:
            rows = []
        return {"list": [r for r in rows if r.get("id") not in self.hidden][offset:offset + max_size]}

    hidden: set = set()  # ids a short list leaves out
    existing: set = set()  # of those, ids a get still reads

    async def get(self, entity, rid, select=None):
        if rid in self.existing:
            return {"id": rid}
        raise RuntimeError(f"EspoCRM GET {entity}/{rid} failed: HTTP 404 Not Found")


async def test_read_crm_reads_every_team_by_its_gate_name():
    snap = _snap(team_members={"Mentor Team": {"uDW"}, "Sponsor Management Team": {"uJ"}})
    crm = FakeCrm(snap, TEAMS)
    got = await read_crm(crm, Settings())
    assert got.team_members == {"Mentor Team": {"uDW"}, "Partner Management Team": set(),
                                "Sponsor Management Team": {"uJ"}}
    assert set(got.contacts) == {"C-DW", "C-DB", "C-J"}
    assert len(got.profiles) == 3 and set(got.users) == {"uD", "uJ", "uDW"}
    linked = [w for e, w in crm.calls if e == "User" and w]
    assert linked[0][0]["type"] == "linkedWith" and linked[0][0]["attribute"] == "teams"


# --- one run -------------------------------------------------------------------

class FakeStore:
    """In memory, the same rules as integrity.store (the Postgres test proves
    the real one): one open row per key; gone daily faults close."""

    def __init__(self):
        self.rows: list[dict] = []

    async def apply_run(self, found, now=None):
        now = now or datetime.now(timezone.utc)
        keys = {f["key"]: f for f in found}
        open_rows = {r["fault_key"]: r for r in self.rows if r["closed_at"] is None}
        closed = []
        for k, r in open_rows.items():
            if k not in keys:
                r["closed_at"] = now
                closed.append(r)
        new = []
        for k, f in keys.items():
            if k in open_rows:
                open_rows[k].update(summary=f["summary"], last_seen=now)
            else:
                r = {"id": str(len(self.rows)), "fault_key": k, "condition": f["condition"],
                     "summary": f["summary"], "mentors": f["mentors"], "login": f["login"],
                     "first_seen": now, "last_seen": now, "closed_at": None,
                     "ack_at": None, "ack_by": None, "ack_note": None, "notified_at": None}
                self.rows.append(r)
                new.append(r)
        return {"new": new, "closed": closed, "open": await self.open_faults()}

    async def open_faults(self):
        return [r for r in self.rows if r["closed_at"] is None]


async def test_a_run_records_logs_and_sends_nothing(caplog):
    crm = FakeCrm(_snap(), TEAMS)
    store, sent = FakeStore(), []

    async def send(*a, **k):
        sent.append(a)

    with caplog.at_level(logging.INFO, logger="cbm_intake.integrity"):
        result = await run.run_integrity_check(Settings(), crm, store, send=send)
    assert len(result["new"]) == 4 and not result["closed"]
    line = [r.message for r in caplog.records if r.message.startswith("login integrity check:")]
    assert line and "4 open (c1=1 c2=0 c3=1 c4=0 c5=1 c6=1 c7=0), 4 new, 0 closed" in line[0]
    assert sent == []  # 4a: the digest switch is off, so no email of any kind

    # Next day: David's record repaired — the faults close themselves.
    fixed = _snap(
        profiles=[dict(_snap().profiles[0], cbmEmail="david.weissman@cbmentors.org",
                       assignedUsersIds=["uDW"]), *_snap().profiles[1:]],
        contacts={"C-DW": ["uDW"], "C-DB": ["uD"], "C-J": ["uJ"]})
    result = await run.run_integrity_check(Settings(), FakeCrm(fixed, TEAMS), store)
    assert result["open"] == [] and len(result["closed"]) == 4


async def test_a_failed_read_changes_nothing(caplog):
    store = FakeStore()
    await run.run_integrity_check(Settings(), FakeCrm(_snap(), TEAMS), store)
    before = [dict(r) for r in store.rows]
    with caplog.at_level(logging.WARNING, logger="cbm_intake.integrity"):
        got = await run.run_integrity_check(
            Settings(), FakeCrm(_snap(), TEAMS, fail="Contact"), store)
    assert got is None and store.rows == before
    assert any("nothing changed" in r.message for r in caplog.records)


# --- the schedule --------------------------------------------------------------

def _sched(settings, after):
    from worker import _next_local_hour

    return run.next_run_time(settings, after, _next_local_hour)


def test_the_run_lands_at_the_local_hour():
    s = Settings(login_integrity_hour=7, login_integrity_tz="America/New_York")
    after = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)
    assert _sched(s, after) == datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def test_the_sandbox_never_runs_inside_the_restore_window():
    s = Settings(login_integrity_hour=4, login_integrity_tz="UTC",
                 espo_base_url="https://crm-test.example.org")
    after = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)
    assert _sched(s, after) == datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
    prod = Settings(login_integrity_hour=4, login_integrity_tz="UTC",
                    espo_base_url="https://crm.example.org")
    assert _sched(prod, after) == datetime(2026, 11, 6, 4, 0, tzinfo=timezone.utc)


def test_the_switches_default_off_and_are_on_the_setup_page():
    from core.settings_registry import SETTINGS

    s = Settings()
    assert not s.login_integrity_check and not s.integrity_digest
    assert not s.integrity_signin_alert
    keys = {spec.key: spec for spec in SETTINGS}
    for k in ("login_integrity_check", "login_integrity_hour", "login_integrity_tz",
              "integrity_digest", "integrity_digest_to", "integrity_signin_alert"):
        assert k in keys, k
    assert keys["login_integrity_check"].component == "worker"


def test_recipients_fall_back_to_the_alert_list():
    assert Settings(alert_email_to="a@x.org").integrity_recipients == ["a@x.org"]
    assert Settings(alert_email_to="a@x.org",
                    integrity_digest_to=" b@x.org, c@x.org").integrity_recipients == \
        ["b@x.org", "c@x.org"]


def test_the_fault_table_resets_on_the_sandbox():
    from core.sandbox_reset import RESET_TABLES

    assert "login_integrity_fault" in RESET_TABLES


# --- the read-only report --------------------------------------------------------

async def test_the_live_report_prints_and_records_nothing(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "integrity_report", Path(__file__).parents[1] / "scripts" / "integrity_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    crm = FakeCrm(_snap(), TEAMS)
    monkeypatch.setattr(mod, "get_settings", lambda: Settings(
        espo_base_url="https://crm.example.org", espo_api_key="k", espo_dry_run=False))
    monkeypatch.setattr(mod, "EspoClient", lambda *a, **k: crm)
    assert await mod.run(live=True) == 0
    out = capsys.readouterr().out
    assert "4 login fault(s)" in out and "Nothing recorded" in out
    assert "== 1. One login on several mentor profiles" in out
    assert all(e != "Contact" or w for e, w in crm.calls)


# --- a short read changes nothing (review of 4a) ---------------------------------

async def test_a_short_user_list_fails_the_read_but_a_deleted_login_does_not():
    crm = FakeCrm(_snap(), TEAMS)
    crm.hidden, crm.existing = {"uJ"}, {"uJ"}  # the list left uJ out; uJ still exists
    with pytest.raises(check.IncompleteRead):
        await read_crm(crm, Settings())
    crm.existing = set()  # uJ really is gone: condition 4 may say so
    snap = await read_crm(crm, Settings())
    assert "uJ" not in snap.users


async def test_a_missing_team_or_contact_fails_the_read():
    with pytest.raises(check.IncompleteRead, match="no team named"):
        await read_crm(FakeCrm(_snap(), {"Partner Team": "T9"}), Settings())
    crm = FakeCrm(_snap(), TEAMS)
    crm.hidden, crm.existing = {"C-J"}, {"C-J"}
    with pytest.raises(check.IncompleteRead):
        await read_crm(crm, Settings())


async def test_profiles_with_no_logins_at_all_mean_the_logins_were_not_read():
    snap = _snap(profiles=[dict(p, assignedUsersIds=[]) for p in _snap().profiles])
    with pytest.raises(check.IncompleteRead, match="no mentor profile carries a login"):
        await read_crm(FakeCrm(snap, TEAMS), Settings())
