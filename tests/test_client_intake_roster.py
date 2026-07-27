"""The client-intake form's public mentor roster (2026-07-27).

Exposure rule (Doug's ruling): Active + accepting + already-public only, names
only. The endpoint is unauthenticated, so the filter is the privacy boundary.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from forms.client_intake.router import _visible, fetch_mentors, make_router
from forms.client_intake import router as roster_mod


def _m(name, status="Active", accepting=True, public=True, rid=None):
    return {
        "id": rid or f"id-{name.lower().replace(' ', '-')}",
        "name": name,
        "mentorStatus": status,
        "acceptingNewClients": accepting,
        "publicProfile": public,
    }


class FakeCrm:
    def __init__(self, records, fail=False):
        self._records = records
        self._fail = fail
        self.calls = 0

    async def list(self, entity, **kw):
        self.calls += 1
        if self._fail:
            raise RuntimeError("CRM down")
        return {"list": self._records, "total": len(self._records)}


@pytest.fixture(autouse=True)
def _clear_cache():
    roster_mod._cache["mentors"] = None
    roster_mod._cache["at"] = 0.0
    yield
    roster_mod._cache["mentors"] = None
    roster_mod._cache["at"] = 0.0


def _client(crm):
    app = FastAPI()
    app.include_router(make_router(lambda: crm))
    return TestClient(app)


@pytest.mark.parametrize(
    "record,expected",
    [
        (_m("Brad Swimmer"), True),
        (_m("Not Public", public=False), False),
        (_m("At Capacity", accepting=False), False),
        (_m("Candidate", status="Candidate"), False),
        (_m("Dormant", status="Dormant"), False),
    ],
)
def test_visibility_rule(record, expected):
    assert _visible(record) is expected


@pytest.mark.anyio
async def test_roster_returns_names_only_sorted():
    crm = FakeCrm([_m("Sue Marrone"), _m("Anthony Sacco"), _m("Hidden", public=False)])
    mentors = await fetch_mentors(crm)

    assert [m["name"] for m in mentors] == ["Anthony Sacco", "Sue Marrone"]
    # No status, email, capacity or any other attribute may leak out.
    assert all(set(m) == {"id", "name"} for m in mentors)


def test_endpoint_serves_the_roster():
    crm = FakeCrm([_m("Brad Swimmer")])
    r = _client(crm).get("/api/client-intake/mentors")
    assert r.status_code == 200
    assert r.json()["mentors"] == [{"id": "id-brad-swimmer", "name": "Brad Swimmer"}]


def test_endpoint_degrades_instead_of_failing():
    """A CRM outage must not 500 the form's page load."""
    r = _client(FakeCrm([], fail=True)).get("/api/client-intake/mentors")
    assert r.status_code == 200
    assert r.json()["mentors"] == []


def test_roster_is_cached():
    crm = FakeCrm([_m("Brad Swimmer")])
    c = _client(crm)
    c.get("/api/client-intake/mentors")
    c.get("/api/client-intake/mentors")
    assert crm.calls == 1, "a burst of form loads must not hammer the CRM"


def test_stale_roster_is_served_when_the_crm_goes_down():
    """Better a slightly stale list than an empty dropdown mid-outage."""
    crm = FakeCrm([_m("Brad Swimmer")])
    c = _client(crm)
    c.get("/api/client-intake/mentors")
    roster_mod._cache["at"] = 0.0          # force the cache to look expired
    crm._fail = True
    r = c.get("/api/client-intake/mentors")
    assert r.json()["mentors"] == [{"id": "id-brad-swimmer", "name": "Brad Swimmer"}]
