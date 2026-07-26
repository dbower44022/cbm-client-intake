"""Birthdays on the portal — your own greeting, and the announcement to CBM.

Covers the date rule (including 29 February), the roster read and its cache,
who is announced (current members only) vs. who is greeted (any member who can
sign in), self-exclusion from the announcement, and the best-effort contract:
nothing here may break sign-in.
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


# --- the roster read ---------------------------------------------------------

TODAY = date(2026, 5, 4)


class _Fake:
    """Minimal EspoCRM stand-in for the two roster reads."""

    def __init__(self, profiles, contacts, *, fail=False):
        self.profiles = profiles
        self.contacts = contacts          # {id: {...}}
        self.fail = fail
        self.calls = 0

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, **kw):
        self.calls += 1
        if self.fail:
            raise EspoError(f"list {entity} failed: 403 Forbidden")
        if entity == "CMentorProfile":
            page = self.profiles[offset : offset + max_size]
            return {"list": page, "total": len(self.profiles)}
        wanted = (where or [{}])[0].get("value", [])
        return {"list": [self.contacts[i] for i in wanted if i in self.contacts]}


def _member(pid, user, contact, bday, status="Active", first="Ada", last="Lovelace"):
    return (
        {"id": pid, "name": first + " " + last, "mentorStatus": status,
         "contactRecordId": contact, "assignedUserId": user},
        {"id": contact, "name": first + " " + last, "firstName": first,
         "lastName": last, "cBirthday": bday},
    )


def _wire(monkeypatch, fake, today=TODAY):
    birthday.reset_cache()
    monkeypatch.setattr(birthday, "_system_client", lambda settings: fake)
    monkeypatch.setattr(birthday, "today_local", lambda: today)


def _roster(*members):
    profiles = [m[0] for m in members]
    contacts = {m[1]["id"]: m[1] for m in members}
    return _Fake(profiles, contacts)


ADA = _member("p1", "u1", "c1", "1965-05-04")                       # today, Active
GRACE = _member("p2", "u2", "c2", "1906-05-04", first="Grace", last="Hopper")
ALAN = _member("p3", "u3", "c3", "1912-06-23", first="Alan", last="Turing")  # not today

_ADA_USER = {"userId": "u1", "userName": "ada", "name": "Ada Lovelace", "token": "t"}
_BOB_USER = {"userId": "u9", "userName": "bob", "name": "Bob Staff", "token": "t"}


@pytest.mark.asyncio
async def test_own_birthday_is_greeted_and_not_self_announced(monkeypatch):
    _wire(monkeypatch, _roster(ADA, ALAN))
    got = await birthday.greetings_for(object(), _ADA_USER)
    assert got["date"] == "2026-05-04"
    assert got["own"] == {"firstName": "Ada", "name": "Ada Lovelace"}
    assert got["others"] == []            # never "wish yourself a happy birthday"


@pytest.mark.asyncio
async def test_everyone_else_is_asked_to_wish_them_well(monkeypatch):
    _wire(monkeypatch, _roster(ADA, ALAN))
    got = await birthday.greetings_for(object(), _BOB_USER)
    assert got["own"] is None
    assert got["others"] == [{"firstName": "Ada", "name": "Ada Lovelace"}]


@pytest.mark.asyncio
async def test_own_birthday_shared_with_a_colleague_lists_both(monkeypatch):
    _wire(monkeypatch, _roster(ADA, GRACE))
    got = await birthday.greetings_for(object(), _ADA_USER)
    assert got["own"]["firstName"] == "Ada"
    assert [p["name"] for p in got["others"]] == ["Grace Hopper"]


@pytest.mark.asyncio
async def test_nothing_to_celebrate_returns_none(monkeypatch):
    _wire(monkeypatch, _roster(ALAN))
    assert await birthday.greetings_for(object(), _ADA_USER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Candidate", "Prospect", "Resigned", "Terminated",
                                    "Inactive", "Retired", "Declined", ""])
async def test_non_current_members_are_not_announced(monkeypatch, status):
    """Applicants and former members aren't announced to the organization."""
    applicant = _member("p4", "u4", "c4", "1965-05-04", status=status)
    _wire(monkeypatch, _roster(applicant))
    assert await birthday.greetings_for(object(), _BOB_USER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Candidate", "Resigned"])
async def test_but_they_still_get_their_own_greeting(monkeypatch, status):
    """Own greeting is deliberately not status-gated — they signed in today."""
    applicant = _member("p4", "u4", "c4", "1965-05-04", status=status)
    _wire(monkeypatch, _roster(applicant))
    got = await birthday.greetings_for(object(), {"userId": "u4", "userName": "x"})
    assert got["own"]["firstName"] == "Ada" and got["others"] == []


@pytest.mark.asyncio
async def test_own_record_resolves_through_collaborators(monkeypatch):
    """The member record may list another user first — membership decides."""
    profile, contact = _member("p1", None, "c1", "1965-05-04")
    profile["assignedUsersIds"] = ["other", "u1"]
    _wire(monkeypatch, _roster((profile, contact)))
    got = await birthday.greetings_for(object(), _ADA_USER)
    assert got["own"]["name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_members_without_a_linked_contact_are_skipped(monkeypatch):
    fake = _roster(ADA)
    fake.profiles.append({"id": "p5", "name": "No Contact", "mentorStatus": "Active"})
    _wire(monkeypatch, fake)
    got = await birthday.greetings_for(object(), _BOB_USER)
    assert [p["name"] for p in got["others"]] == ["Ada Lovelace"]


@pytest.mark.asyncio
async def test_crm_failure_is_swallowed(monkeypatch):
    """A struggling CRM must never surface at the sign-in door."""
    fake = _roster(ADA)
    fake.fail = True
    _wire(monkeypatch, fake)
    assert await birthday.greetings_for(object(), _ADA_USER) is None


@pytest.mark.asyncio
async def test_no_api_key_means_no_greeting(monkeypatch):
    """Dry-run/keyless deploys simply don't celebrate."""
    birthday.reset_cache()
    monkeypatch.setattr(birthday, "_system_client", lambda settings: None)
    monkeypatch.setattr(birthday, "today_local", lambda: TODAY)
    assert await birthday.greetings_for(object(), _ADA_USER) is None


@pytest.mark.asyncio
async def test_roster_is_read_once_for_the_whole_organization(monkeypatch):
    """One read serves every viewer for the day — not one per sign-in."""
    fake = _roster(ADA, GRACE, ALAN)
    _wire(monkeypatch, fake)
    await birthday.greetings_for(object(), _ADA_USER)
    after_first = fake.calls
    for _ in range(5):
        await birthday.greetings_for(object(), _BOB_USER)
    assert fake.calls == after_first > 0


@pytest.mark.asyncio
async def test_a_new_day_re_reads_the_roster(monkeypatch):
    fake = _roster(ADA)
    _wire(monkeypatch, fake)
    await birthday.greetings_for(object(), _BOB_USER)
    before = fake.calls
    monkeypatch.setattr(birthday, "today_local", lambda: date(2026, 5, 5))
    await birthday.greetings_for(object(), _BOB_USER)
    assert fake.calls > before


# --- the portal payload ------------------------------------------------------

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _login(monkeypatch, user, teams=()):
    session_user = dict(user, isAdmin=False, teams=list(teams), roles=[])

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return session_user

    async def fake_refresh(settings, s):
        return dict(s)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)


def test_portal_login_carries_the_greeting(monkeypatch):
    _login(monkeypatch, _ADA_USER)
    _wire(monkeypatch, _roster(ADA))
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthdays"]["own"]["firstName"] == "Ada"


def test_portal_announces_to_a_member_of_no_team(monkeypatch):
    """The announcement is for the whole organization — no team gate."""
    _login(monkeypatch, _BOB_USER)
    _wire(monkeypatch, _roster(ADA))
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthdays"]["others"] == [{"firstName": "Ada", "name": "Ada Lovelace"}]
    assert body["birthdays"]["own"] is None


def test_portal_session_restore_carries_it_too(monkeypatch):
    _login(monkeypatch, _ADA_USER)
    _wire(monkeypatch, _roster(ADA))
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "x", "password": "y"})
        body = c.get("/api/portal/session").json()
    assert body["birthdays"]["own"]["name"] == "Ada Lovelace"


def test_portal_payload_is_none_when_no_birthdays(monkeypatch):
    _login(monkeypatch, _ADA_USER)
    _wire(monkeypatch, _roster(ALAN))
    with TestClient(_app(monkeypatch)) as c:
        body = c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()
    assert body["birthdays"] is None
