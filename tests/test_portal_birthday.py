"""Birthday greeting on the portal — a mentor signing in on their birthday.

Covers the date rule (including 29 February), the CRM resolution chain, the
best-effort contract (nothing about this may break sign-in), the mentor-only
gate, and the per-day session cache.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request, volunteer
from portal import birthday


# --- the date rule (pure) ----------------------------------------------------

def test_is_birthday_matches_month_and_day_any_year():
    assert birthday.is_birthday("1965-05-04", date(2026, 5, 4)) is True
    assert birthday.is_birthday("1965-05-04", date(2026, 5, 5)) is False
    assert birthday.is_birthday("1965-06-04", date(2026, 5, 4)) is False


def test_is_birthday_leap_day_celebrated_on_feb_28_in_common_years():
    assert birthday.is_birthday("1988-02-29", date(2027, 2, 28)) is True   # common year
    assert birthday.is_birthday("1988-02-29", date(2028, 2, 29)) is True   # leap year
    # In a leap year the 28th is the 28th — no early greeting.
    assert birthday.is_birthday("1988-02-29", date(2028, 2, 28)) is False


@pytest.mark.parametrize("value", [None, "", "   ", "not-a-date", 20260504, {}])
def test_is_birthday_ignores_unusable_values(value):
    assert birthday.is_birthday(value, date(2026, 5, 4)) is False


def test_is_birthday_tolerates_a_datetime_string():
    assert birthday.is_birthday("1965-05-04 00:00:00", date(2026, 5, 4)) is True


# --- the CRM resolution chain ------------------------------------------------

class _Fake:
    """Minimal EspoCRM stand-in: profiles list + records by (entity, id)."""

    def __init__(self, profiles, records, *, fail=None):
        self.profiles = profiles          # rows for the CMentorProfile list
        self.records = records            # {(entity, id): {...}}
        self.fail = fail                  # (entity, id) that raises
        self.calls = 0

    async def list(self, entity, **kwargs):
        self.calls += 1
        return {"list": list(self.profiles), "total": len(self.profiles)}

    async def get(self, entity, record_id, select=None):
        self.calls += 1
        if self.fail == (entity, record_id):
            raise EspoError(f"get {entity}/{record_id} failed: 403 Forbidden")
        rec = self.records.get((entity, record_id))
        if rec is None:
            raise EspoError("not found")
        return dict(rec)


def _wire(monkeypatch, fake, today=date(2026, 5, 4)):
    monkeypatch.setattr(birthday, "client_for", lambda settings, user: fake)
    monkeypatch.setattr(birthday, "today_local", lambda: today)


def _linked(bday="1965-05-04", first="Ada"):
    return _Fake(
        profiles=[{"id": "p1", "assignedUserId": "u1"}],
        records={
            ("CMentorProfile", "p1"): {"id": "p1", "contactRecordId": "c1"},
            ("Contact", "c1"): {"id": "c1", "firstName": first, "cBirthday": bday},
        },
    )


_USER = {"userId": "u1", "userName": "ada", "name": "Ada Lovelace", "token": "t"}


@pytest.mark.asyncio
async def test_mentor_birthday_returns_greeting_on_the_day(monkeypatch):
    _wire(monkeypatch, _linked())
    got = await birthday.mentor_birthday(object(), _USER)
    assert got == {"firstName": "Ada", "date": "2026-05-04"}


@pytest.mark.asyncio
async def test_mentor_birthday_is_none_on_any_other_day(monkeypatch):
    _wire(monkeypatch, _linked(), today=date(2026, 5, 5))
    assert await birthday.mentor_birthday(object(), _USER) is None


@pytest.mark.asyncio
async def test_mentor_birthday_none_when_birthday_not_recorded(monkeypatch):
    _wire(monkeypatch, _linked(bday=None))
    assert await birthday.mentor_birthday(object(), _USER) is None


@pytest.mark.asyncio
async def test_mentor_birthday_none_without_a_linked_profile(monkeypatch):
    _wire(monkeypatch, _Fake(profiles=[{"id": "p9", "assignedUserId": "someone-else"}],
                             records={}))
    assert await birthday.mentor_birthday(object(), _USER) is None


@pytest.mark.asyncio
async def test_mentor_birthday_none_without_a_linked_contact(monkeypatch):
    _wire(monkeypatch, _Fake(
        profiles=[{"id": "p1", "assignedUserId": "u1"}],
        records={("CMentorProfile", "p1"): {"id": "p1"}},
    ))
    assert await birthday.mentor_birthday(object(), _USER) is None


@pytest.mark.asyncio
async def test_mentor_birthday_swallows_crm_failures(monkeypatch):
    """A forbidden/unavailable CRM read must never surface — sign-in comes first."""
    fake = _linked()
    fake.fail = ("Contact", "c1")
    _wire(monkeypatch, fake)
    assert await birthday.mentor_birthday(object(), _USER) is None


@pytest.mark.asyncio
async def test_mentor_birthday_resolves_through_collaborators(monkeypatch):
    """The profile may list another user first — membership decides ownership."""
    fake = _linked()
    fake.profiles = [{"id": "p1", "assignedUsersIds": ["other", "u1"]}]
    _wire(monkeypatch, fake)
    assert (await birthday.mentor_birthday(object(), _USER))["firstName"] == "Ada"


# --- the portal payload ------------------------------------------------------

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _login(monkeypatch, teams):
    user = dict(_USER, isAdmin=False, teams=teams, roles=[])

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return user

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)


def test_portal_login_carries_the_greeting_for_a_mentor(monkeypatch):
    _login(monkeypatch, ["Mentor Team"])
    _wire(monkeypatch, _linked())
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthday"] == {"firstName": "Ada", "date": "2026-05-04"}


def test_portal_login_has_no_greeting_on_an_ordinary_day(monkeypatch):
    _login(monkeypatch, ["Mentor Team"])
    _wire(monkeypatch, _linked(), today=date(2026, 11, 2))
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthday"] is None


def test_non_mentor_is_never_checked(monkeypatch):
    """Staff who aren't mentors cost no CRM call at all."""
    _login(monkeypatch, ["Marketing Admin Team"])
    fake = _linked()
    _wire(monkeypatch, fake)
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthday"] is None
    assert fake.calls == 0


def test_session_restore_reuses_the_days_answer(monkeypatch):
    """Refreshing the portal must not re-read the CRM for the same day."""
    _login(monkeypatch, ["Mentor Team"])
    fake = _linked()
    _wire(monkeypatch, fake)
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "x", "password": "y"})
        after_login = fake.calls
        body = c.get("/api/portal/session").json()
    assert body["birthday"] == {"firstName": "Ada", "date": "2026-05-04"}
    assert fake.calls == after_login          # served from the session cache
