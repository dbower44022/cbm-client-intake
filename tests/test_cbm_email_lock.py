"""Mentor login integrity, step 3 (prds/mentor-login-integrity-plan.md § 4.4):
the CBM email locks once a login exists, and is checked before then."""

from __future__ import annotations

import pytest

from core import login_guard
from core.config import get_settings
from mentoradmin import service
from tests.test_mentoradmin import ProvisionClient


@pytest.fixture
def lock_on(monkeypatch):
    monkeypatch.setenv("CBM_EMAIL_LOCK", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Directory(ProvisionClient):
    """ProvisionClient plus the two lookups the check makes."""

    def __init__(self, *, logins=(), other_profiles=None, **kw):
        super().__init__(**kw)
        self.logins = {l: {"id": f"u-{l}", "userName": l} for l in logins}
        self.other_profiles = dict(other_profiles or {})   # address -> {id, name}

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == "User":
            return self.logins.get(value)
        if entity == "CMentorProfile":
            return self.other_profiles.get(value)
        return await super().find_one(entity, attribute, value, select)

    async def get(self, entity, record_id, select=None):
        if entity == "User":
            return {"id": record_id, "userName": "jane.doe@cbmentors.org"}
        return await super().get(entity, record_id, select)


def _no_login(**kw):
    return Directory(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Approved",
                              "assignedUserId": None, "cbmEmail": "", "contactRecordId": "c1"}, **kw)


def _cbm_writes(c):
    return [u[2]["cbmEmail"] for u in c.updates if "cbmEmail" in u[2]]


async def test_switch_off_saves_as_before():
    c = _no_login()
    await service.update_mentor(c, "m1", {"cbmEmail": "Anything@Example.com"})
    assert _cbm_writes(c) == ["Anything@Example.com"]


async def test_with_a_login_the_field_cannot_change(lock_on):
    c = Directory(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Active",
                           "assignedUserId": "u1", "cbmEmail": "jane.doe@cbmentors.org",
                           "contactRecordId": "c1"})
    with pytest.raises(service.MentorAdminError, match="has a login"):
        await service.update_mentor(c, "m1", {"cbmEmail": "Doug.Bower@cbmentors.org"})
    assert c.updates == []                                   # nothing written


async def test_before_a_login_a_good_address_is_saved_in_lower_case(lock_on):
    c = _no_login()
    await service.update_mentor(c, "m1", {"cbmEmail": " Jane.Doe@CBMentors.org "})
    assert _cbm_writes(c) == ["jane.doe@cbmentors.org"]


@pytest.mark.parametrize("address, kwargs, words", [
    ("jane.doe@gmail.com", {}, "must be an address on @cbmentors.org"),
    ("doug.bower@cbmentors.org", {"logins": ["doug.bower@cbmentors.org"]}, "already a login"),
    ("sam.lee@cbmentors.org", {"other_profiles": {"sam.lee@cbmentors.org": {"id": "m9", "name": "Sam Lee"}}},
     "another mentor profile (Sam Lee)"),
])
async def test_before_a_login_a_bad_address_is_refused(lock_on, address, kwargs, words):
    c = _no_login(**kwargs)
    with pytest.raises(service.MentorAdminError, match=words.replace("(", r"\(").replace(")", r"\)")):
        await service.update_mentor(c, "m1", {"cbmEmail": address})
    assert c.updates == []


async def test_the_profiles_own_address_is_not_a_conflict(lock_on):
    c = _no_login(other_profiles={"jane.doe@cbmentors.org": {"id": "m1", "name": "Jane Doe"}})
    await service.update_mentor(c, "m1", {"cbmEmail": "jane.doe@cbmentors.org"})
    assert _cbm_writes(c) == ["jane.doe@cbmentors.org"]


async def test_a_lookup_that_fails_stores_nothing(lock_on):
    class Down(Directory):
        async def find_one(self, entity, attribute, value, select="id"):
            raise RuntimeError("CRM down")
    c = Down(profile={"id": "m1", "name": "J", "assignedUserId": None, "cbmEmail": "",
                      "contactRecordId": "c1"})
    with pytest.raises(service.MentorAdminError, match="nothing was saved"):
        await service.update_mentor(c, "m1", {"cbmEmail": "jane.doe@cbmentors.org"})
    assert c.updates == []


async def test_lock_state_for_the_page(lock_on, monkeypatch):
    with_login = Directory(profile={"id": "m1", "assignedUserId": "u1"})
    monkeypatch.setattr(login_guard, "reader", lambda: with_login)
    assert await service.cbm_email_lock(with_login, "m1") == {
        "locked": True, "login": "jane.doe@cbmentors.org"}
    assert await service.cbm_email_lock(_no_login(), "m1") == {"locked": False}


async def test_lock_state_is_absent_with_the_switch_off():
    assert await service.cbm_email_lock(_no_login(), "m1") is None


def test_the_page_locks_the_field_and_says_why():
    js = open("mentoradmin/frontend/app.js").read()
    assert "current.cbmEmailLock" in js and "input.readOnly = true" in js
    assert "An administrator changes the login, the Google mailbox and this field together." in js


def test_switch_defaults_off_and_is_on_the_setup_page():
    from core.config import Settings
    from core.settings_registry import SETTINGS
    assert Settings().cbm_email_lock is False
    assert "cbm_email_lock" in {getattr(x, "key", None) for x in SETTINGS}
