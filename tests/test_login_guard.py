"""Mentor login integrity, step 2 (prds/mentor-login-integrity-plan.md § 4.3):
the three repair paths stop when login data disagrees, and the narrowed
two-profile guess. The fixtures replay the 10-16-26 fault: Doug Bower's login
(uD, doug.bower@cbmentors.org) on David Weissman's Approved profile (MP-DW),
whose CBM email reads Doug.Bower@cbmentors.org, as well as on Doug's own
Active profile (MP-DB)."""

from __future__ import annotations

import logging

import pytest

from core import login_guard
from core.config import Settings
from assignments import stamps
from mentoradmin import service as mentoradmin
from sessions import service as sessions
from tests.test_stamps import FakeEspo


def _fault_case(**over) -> FakeEspo:
    values = dict(
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
        engagements=[],
        records={
            ("User", "uD"): {"userName": "doug.bower@cbmentors.org"},
            ("User", "uJ"): {"userName": "jane.doe@cbmentors.org"},
            ("User", "uDW"): {"userName": "david.weissman@cbmentors.org"},
            ("Contact", "C-DW"): {"assignedUsersIds": []},
            ("Contact", "C-DB"): {"assignedUsersIds": ["uD"]},
            ("Contact", "C-J"): {"assignedUsersIds": []},
        },
    )
    values.update(over)
    espo = FakeEspo(**values)
    for p in espo.profiles:  # the profile reads in reconcile_user_links
        espo.records[("CMentorProfile", p["id"])] = dict(p)
    return espo


def _guards_on(monkeypatch, espo):
    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    monkeypatch.setattr(login_guard, "reader", lambda: espo)


def _contact_writes(espo):
    return [(r, p) for e, r, p in espo.updates if e == "Contact"]


# --- the helpers ---------------------------------------------------------------

def test_same_address_ignores_case_and_space_but_never_matches_blank():
    assert login_guard.same_address("Doug.Bower@cbmentors.org ", "doug.bower@cbmentors.org")
    assert not login_guard.same_address("", "")
    assert not login_guard.same_address(None, "x@y")


def test_login_ids_reads_both_shapes_once():
    assert login_guard.login_ids({"assignedUserId": "a", "assignedUsersIds": ["b", "a"]}) == ["b", "a"]
    assert login_guard.login_ids({"assignedUserId": "a"}) == ["a"]
    assert login_guard.login_ids({}) == []


async def test_profile_to_contact_refusals_and_agreement():
    espo = _fault_case()
    dw, db, j = (dict(p) for p in espo.profiles)
    assert "on 2 mentor profiles" in await login_guard.refuse_profile_to_contact(espo, dw, "uD")
    assert await login_guard.refuse_profile_to_contact(espo, j, "uJ") is None
    j["cbmEmail"] = "someone.else@cbmentors.org"
    assert "does not match" in await login_guard.refuse_profile_to_contact(espo, j, "uJ")


async def test_contact_to_profile_refusals_and_agreement():
    espo = _fault_case()
    empty = {"id": "MP-X", "cbmEmail": "david.weissman@cbmentors.org"}
    assert "carries 2 logins" in await login_guard.refuse_contact_to_profile(espo, empty, ["uDW", "uD"])
    assert "another mentor profile" in await login_guard.refuse_contact_to_profile(espo, empty, ["uD"])
    assert await login_guard.refuse_contact_to_profile(espo, empty, ["uDW"]) is None
    assert "does not match" in await login_guard.refuse_contact_to_profile(
        espo, {"id": "MP-X", "cbmEmail": ""}, ["uDW"])


# --- path 1: the nightly clean-up's Phase A ------------------------------------

def _settings():
    return Settings(espo_dry_run=False, espo_api_key="k", espo_base_url="https://crm-test.example")


async def test_phase_a_with_guards_does_not_spread_the_10_16_fault(monkeypatch, caplog):
    espo = _fault_case()
    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    with caplog.at_level(logging.WARNING, logger="cbm_intake.login_guard"):
        summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert ("C-DW", {"assignedUsersIds": ["uD"]}) not in _contact_writes(espo)
    assert summary["loginConflicts"] == 1
    assert "login-integrity:" in caplog.text and "MP-DW" in caplog.text
    # Jane's agreeing login is still copied.
    assert ("C-J", {"assignedUsersIds": ["uJ"]}) in _contact_writes(espo)


async def test_phase_a_without_guards_behaves_as_before(monkeypatch):
    espo = _fault_case()
    monkeypatch.setattr(login_guard, "enabled", lambda: False)
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert ("C-DW", {"assignedUsersIds": ["uD"]}) in _contact_writes(espo)
    assert summary["loginConflicts"] == 0


# --- path 2: reconcile_user_links (a save, Update Mentor Status) ---------------

async def test_reconcile_with_guards_refuses_both_directions(monkeypatch):
    espo = _fault_case()
    _guards_on(monkeypatch, espo)
    # profile -> Contact: Doug's login on David's profile is on two profiles.
    assert await mentoradmin.reconcile_user_links(espo, "MP-DW") == {}
    assert _contact_writes(espo) == []
    # Contact -> profile: David's profile emptied, his Contact holds Doug's login.
    espo.records[("CMentorProfile", "MP-DW")]["assignedUsersIds"] = []
    espo.records[("Contact", "C-DW")]["assignedUsersIds"] = ["uD"]
    assert await mentoradmin.reconcile_user_links(espo, "MP-DW") == {}
    assert espo.updates == []


async def test_reconcile_with_guards_still_heals_agreeing_data(monkeypatch):
    espo = _fault_case()
    _guards_on(monkeypatch, espo)
    assert await mentoradmin.reconcile_user_links(espo, "MP-J") == {
        "contactLoginAdded": {"contactId": "C-J", "userId": "uJ"}}


async def test_reconcile_fails_closed_when_the_check_cannot_run(monkeypatch):
    espo = _fault_case()

    class Broken(FakeEspo):
        async def list(self, *a, **kw):
            raise RuntimeError("CRM down")

    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    monkeypatch.setattr(login_guard, "reader", lambda: Broken())
    assert await mentoradmin.reconcile_user_links(espo, "MP-J") == {}
    assert espo.updates == []


async def test_reconcile_without_guards_behaves_as_before(monkeypatch):
    espo = _fault_case()
    monkeypatch.setattr(login_guard, "enabled", lambda: False)
    assert await mentoradmin.reconcile_user_links(espo, "MP-DW") == {
        "contactLoginAdded": {"contactId": "C-DW", "userId": "uD"}}


# --- path 3: provisioning's login reuse ----------------------------------------

async def test_login_reuse_refused_when_another_profile_carries_it(monkeypatch):
    from tests.test_mentoradmin import ProvisionClient

    class Roster(ProvisionClient):
        async def list(self, entity, **kw):
            if entity == "CMentorProfile":
                return {"list": [{"id": "MP-OTHER", "name": "Someone Else",
                                  "assignedUsersIds": ["u-x"]}]}
            return await super().list(entity, **kw)

    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    c = Roster(
        profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
                 "assignedUserId": None, "cbmEmail": "jane.doe@cbmentors.org",
                 "contactRecordId": "c1"},
        existing_users={"jane.doe@cbmentors.org"},
    )

    async def factory():
        return c

    result = await mentoradmin.update_mentor(
        c, "m1", {"mentorStatus": "Active"},
        team_name="Mentor Team", admin_client_factory=factory,
    )
    assert result["provision"]["ok"] is False
    assert "already linked to another mentor profile (Someone Else)" in result["provision"]["error"]
    assert c.created == []                                     # nothing minted either
    assert not [u for u in c.updates if u[2].get("assignedUserId") == "u-x"]


# --- the narrowed two-profile guess ---------------------------------------------

DW = {"id": "MP-DW", "name": "David Weissman", "mentorStatus": "Approved",
      "cbmEmail": "Doug.Bower@cbmentors.org"}
DB = {"id": "MP-DB", "name": "Douglas Bower", "mentorStatus": "Active",
      "cbmEmail": "doug.bower@cbmentors.org"}


def test_strict_choice_picks_the_one_active_matching_profile():
    # Check C5: Doug's screens keep working under the strict rule.
    assert sessions.choose_manager_profile(
        [DW, DB], strict=True, user_name="doug.bower@cbmentors.org") == "MP-DB"


def test_strict_choice_refuses_to_guess():
    two_active = [dict(DW, mentorStatus="Active"), DB]
    assert sessions.choose_manager_profile(two_active, strict=True,
                                           user_name="doug.bower@cbmentors.org") is None
    assert sessions.choose_manager_profile(
        [DW, dict(DB, cbmEmail="other@cbmentors.org")], strict=True,
        user_name="doug.bower@cbmentors.org") is None
    assert sessions.choose_manager_profile([DW, DB], strict=True, user_name=None) is None
    # One candidate is always the answer; not strict is today's rule.
    assert sessions.choose_manager_profile([DW], strict=True, user_name=None) == "MP-DW"
    assert sessions.choose_manager_profile(two_active) == "MP-DW"


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setenv("MANAGER_PROFILE_STRICT", "true")
    from core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_grid_shows_no_records_and_says_why(strict):
    from sessions.config import MENTOR
    from tests.test_sessions import Fake
    fake = Fake(
        mentors=[dict(DW, mentorStatus="Active", assignedUsersIds=["u1"]),
                 dict(DB, assignedUsersIds=["u1"])],
        records={("User", "u1"): {"userName": "doug.bower@cbmentors.org"}},
        related={"engagements1": [{"id": "E1", "name": "x"}]},
    )
    res = await sessions.list_records(MENTOR, fake, {"userId": "u1", "userName": "doug.bower@cbmentors.org"})
    assert res["records"] == []
    assert res["profileChoice"]["blocked"] is True
    assert res["profileChoice"]["chosenId"] is None


async def test_my_mentor_profile_says_the_login_is_ambiguous(strict):
    from mentorprofile import service as mentorprofile
    from tests.test_sessions import Fake
    fake = Fake(
        mentors=[dict(DW, mentorStatus="Active", assignedUsersIds=["u1"]),
                 dict(DB, assignedUsersIds=["u1"])],
        records={("User", "u1"): {"userName": "doug.bower@cbmentors.org"}},
    )
    assert await mentorprofile.get_own_profile(fake, "u1") == {
        "profileFound": False, "ambiguous": True}


def test_both_flags_default_off_and_are_on_the_setup_page():
    from core.settings_registry import SETTINGS
    s = Settings()
    assert s.login_repair_guards is False and s.manager_profile_strict is False
    keys = {getattr(x, "key", None) or getattr(x, "name", None) for x in SETTINGS}
    assert {"login_repair_guards", "manager_profile_strict"} <= keys


# --- review findings 11-05-26 --------------------------------------------------

async def test_reconcile_refuses_when_the_switch_is_on_but_nothing_can_check(monkeypatch):
    espo = _fault_case()
    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    monkeypatch.setattr(login_guard, "reader", lambda: None)
    assert await mentoradmin.reconcile_user_links(espo, "MP-J") == {}
    assert espo.updates == []


async def test_my_mentor_profile_heal_is_guarded_too(monkeypatch):
    """The fourth repair path: opening My Mentor Profile merged the signed-in
    login onto the resolved profile's Contact with no check."""
    from mentorprofile import service as mentorprofile
    espo = _fault_case()
    monkeypatch.setattr(login_guard, "enabled", lambda: True)
    monkeypatch.setattr(stamps, "system_client", lambda settings: espo)
    settings = _settings()
    # Doug's login on David's profile (two profiles): refused, Contact untouched.
    await mentorprofile.heal_own_contact_stamp(settings, "C-DW", "uD", "MP-DW")
    assert _contact_writes(espo) == []
    # No profile to check against: refused.
    await mentorprofile.heal_own_contact_stamp(settings, "C-J", "uJ")
    assert _contact_writes(espo) == []
    # Jane, agreeing: healed.
    await mentorprofile.heal_own_contact_stamp(settings, "C-J", "uJ", "MP-J")
    assert _contact_writes(espo) == [("C-J", {"assignedUsersIds": ["uJ"]})]


async def test_strict_choice_reads_the_login_with_the_key(strict, monkeypatch):
    from tests.test_sessions import Fake
    key = FakeEspo(records={("User", "u1"): {"userName": "doug.bower@cbmentors.org"}})
    monkeypatch.setattr(login_guard, "reader", lambda: key)
    own = Fake(mentors=[dict(DW, assignedUsersIds=["u1"]), dict(DB, assignedUsersIds=["u1"])])
    # The person's own token holds no User record; the key's read decides.
    chosen, _ = await sessions.resolve_manager_profile_detail(own, "u1")
    assert chosen == "MP-DB"


def test_a_repeated_fault_is_logged_once_an_hour(caplog):
    login_guard._last_logged.clear()
    with caplog.at_level(logging.WARNING, logger="cbm_intake.login_guard"):
        for _ in range(3):
            login_guard.fault("ambiguous", once="k1", user="u1")
        login_guard.fault("other", user="u1")
        login_guard.fault("other", user="u1")
    assert caplog.text.count("ambiguous") == 1
    assert caplog.text.count("other") == 2
