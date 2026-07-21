"""Contributions — the funder ledger (prds/funder-contributions-plan.md).

Business rules under test (Doug's rulings 2026-07-20): totals count
status=Received ONLY; Cancelled = soft delete (excluded everywhere, no hard
delete exists); effective date = received → expected → commitment →
application; the last-12-months tile is a rolling window; the period rollup
anchors at the LAST received contribution and walks back in rolling windows,
rendering empty windows so giving gaps show.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request
from sessions import service
from sessions.config import (
    CONTRIBUTION_EDIT_NAMES,
    CONTRIBUTION_FIELDS,
    MENTOR,
    SPONSOR,
)
from sessions.router import _detail_tabs

TODAY = date(2026, 7, 20)

_USER = {
    "userId": "u1", "userName": "sam.sponsor", "name": "Sam Sponsor",
    "isAdmin": True, "teams": ["Sponsor Management Team"], "roles": [],
}


class Fake:
    """Minimal SessionClient for the contribution paths."""

    def __init__(self, *, records=None, related=None, meta_fields=None):
        self.records = dict(records or {})     # (entity, id) -> dict
        self.related = related or {}           # link -> [rows]
        self.meta_fields = meta_fields or {}
        self.created = []
        self.updates = []
        self.gets = []
        self._seq = 0

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id))
        if (entity, record_id) not in self.records:
            from core.espo import EspoError
            raise EspoError(f"get {entity}/{record_id} failed: HTTP 403 forbidden")
        return dict(self.records[(entity, record_id)], id=record_id)

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": self.related.get(link, [])}

    async def create(self, entity, payload):
        self._seq += 1
        rid = f"{entity.lower()}-{self._seq}"
        self.created.append((entity, payload))
        self.records[(entity, rid)] = dict(payload, id=rid)
        return {"id": rid}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        rec = self.records.setdefault((entity, record_id), {"id": record_id})
        rec.update(payload)
        return {"id": record_id}

    async def metadata(self, key):
        return self.meta_fields


def _row(status, amount, *, received=None, expected=None, commitment=None,
         application=None, currency=None, rid="x"):
    r = {
        "id": rid, "status": status, "amount": amount,
        "receivedDate": received, "expectedPaymentDate": expected,
        "commitmentDate": commitment, "applicationDate": application,
        "amountCurrency": currency,
    }
    return service._contribution_row(r, TODAY)


# --- effective date + month math -------------------------------------------

def test_effective_date_chain_first_set_wins():
    assert service.contribution_effective_date(
        {"receivedDate": "2026-01-01", "applicationDate": "2025-01-01"}
    ) == "2026-01-01"
    assert service.contribution_effective_date(
        {"expectedPaymentDate": "2026-03-01", "commitmentDate": "2026-02-01"}
    ) == "2026-03-01"
    assert service.contribution_effective_date(
        {"commitmentDate": "2026-02-01", "applicationDate": "2026-01-01"}
    ) == "2026-02-01"
    assert service.contribution_effective_date({"applicationDate": "2026-01-01"}) == "2026-01-01"
    assert service.contribution_effective_date({}) is None


def test_add_months_clamps_month_end():
    assert service._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert service._add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap
    assert service._add_months(date(2026, 7, 20), -6) == date(2026, 1, 20)
    assert service._add_months(date(2026, 1, 15), -6) == date(2025, 7, 15)


def test_months_between_floors_partial_months():
    assert service._months_between(date(2026, 6, 1), TODAY) == 1
    assert service._months_between(date(2026, 6, 25), TODAY) == 0
    assert service._months_between(date(2025, 7, 20), TODAY) == 12


# --- summary math -----------------------------------------------------------

def test_summary_counts_received_only():
    rows = [
        _row("Received", 1000, received="2026-06-01", rid="a"),
        _row("Pledged", 500, expected="2026-09-01", rid="b"),
        _row("Applied", 700, application="2026-05-01", rid="c"),
        _row("Unsuccessful", 900, application="2026-04-01", rid="d"),
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["totalCount"] == 1
    assert s["totalAmount"] == 1000.0


def test_summary_cancelled_soft_delete_excluded_everywhere():
    rows = [
        _row("Received", 1000, received="2026-06-01", rid="a"),
        _row("Cancelled", 5000, received="2026-06-15", rid="b"),
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["totalCount"] == 1 and s["totalAmount"] == 1000.0
    assert s["last12MonthsAmount"] == 1000.0
    assert s["periods"]["half"][0]["total"] == 1000.0
    # the row itself stays visible, flagged
    assert rows[1]["excluded"] is True


def test_summary_last12_is_rolling_365_days():
    rows = [
        _row("Received", 100, received="2026-01-01", rid="a"),   # inside
        _row("Received", 200, received="2025-07-21", rid="b"),   # inside (day 365)
        _row("Received", 400, received="2025-07-19", rid="c"),   # outside
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["last12MonthsAmount"] == 300.0
    assert s["totalAmount"] == 700.0  # all still count in the lifetime tile


def test_summary_scheduled_tile_future_pledged_committed_only():
    rows = [
        _row("Pledged", 500, expected="2026-09-01", rid="a"),     # counts
        _row("Committed", 300, expected="2026-07-20", rid="b"),   # today counts
        _row("Pledged", 900, expected="2026-06-01", rid="c"),     # past — no
        _row("Applied", 700, application="2026-09-15", rid="d"),  # Applied — no
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["scheduledAmount"] == 800.0
    assert s["scheduledCount"] == 2


def test_summary_recency_and_next_expected():
    rows = [
        _row("Received", 1000, received="2026-06-01", rid="a"),
        _row("Received", 800, received="2025-12-01", rid="b"),
        _row("Pledged", 500, expected="2026-09-01", rid="c"),
        _row("Committed", 250, expected="2026-08-01", rid="d"),
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["lastReceived"] == {"date": "2026-06-01", "amount": 1000.0, "monthsAgo": 1}
    # soonest upcoming scheduled row wins
    assert s["nextExpected"] == {"date": "2026-08-01", "amount": 250.0}


def test_summary_periods_anchor_at_last_received_with_empty_windows():
    # Last received 2026-06-01; an older gift 14 months earlier leaves the
    # middle window EMPTY — it must still render (the giving-gap principle).
    rows = [
        _row("Received", 1000, received="2026-06-01", rid="a"),
        _row("Received", 500, received="2025-04-15", rid="b"),
    ]
    s = service.contribution_summary(rows, TODAY)
    half = s["periods"]["half"]
    assert half[0]["end"] == "2026-06-01"          # anchored at last received
    assert half[0]["count"] == 1 and half[0]["total"] == 1000.0
    assert half[1]["count"] == 0 and half[1]["total"] == 0  # the gap shows
    assert half[2]["count"] == 1 and half[2]["total"] == 500.0
    assert len(half) == 3                           # stops once earliest covered
    year = s["periods"]["year"]
    assert year[0]["end"] == "2026-06-01"
    assert year[0]["count"] == 1
    assert year[1]["count"] == 1


def test_summary_undated_received_counts_in_totals_not_windows():
    rows = [
        _row("Received", 1000, received="2026-06-01", rid="a"),
        _row("Received", 250, rid="b"),  # no date anywhere
    ]
    s = service.contribution_summary(rows, TODAY)
    assert s["totalCount"] == 2 and s["totalAmount"] == 1250.0
    assert s["last12MonthsAmount"] == 1000.0
    assert s["periods"]["half"][0]["total"] == 1000.0


def test_summary_empty_rows():
    s = service.contribution_summary([], TODAY)
    assert s["totalCount"] == 0 and s["totalAmount"] == 0
    assert s["lastReceived"] is None and s["nextExpected"] is None
    assert s["periods"]["half"][0]["count"] == 0  # one anchor window still renders


def test_row_decoration_upcoming_and_excluded():
    up = _row("Pledged", 500, expected="2026-09-01")
    assert up["upcoming"] is True and up["excluded"] is False
    past = _row("Pledged", 500, expected="2026-06-01")
    assert past["upcoming"] is False
    rec = _row("Received", 500, received="2026-09-01")
    assert rec["upcoming"] is False  # received is never "upcoming"
    gone = _row("Cancelled", 500, expected="2026-09-01")
    assert gone["excluded"] is True and gone["upcoming"] is False


# --- service CRUD -----------------------------------------------------------

_PARENT = ("CSponsorProfile", "S1")


def _fake(**kw):
    records = {
        _PARENT: {"name": "Generous Corp", "sponsorCompanyId": "acc1",
                  "sponsorContactId": "con1"},
    }
    records.update(kw.pop("records", {}))
    return Fake(records=records, **kw)


@pytest.mark.asyncio
async def test_list_contributions_reads_parent_first_and_sorts():
    fake = _fake(related={"sponsorContributions": [
        {"id": "c1", "status": "Received", "amount": 100, "receivedDate": "2026-01-01"},
        {"id": "c2", "status": "Pledged", "amount": 200, "expectedPaymentDate": "2026-09-01"},
    ]})
    res = await service.list_contributions(SPONSOR, fake, "S1")
    assert fake.gets[0] == _PARENT  # the ACL gate
    assert [r["id"] for r in res["records"]] == ["c2", "c1"]  # effective desc
    assert res["parentName"] == "Generous Corp"
    assert res["summary"]["totalCount"] == 1


@pytest.mark.asyncio
async def test_create_contribution_stamps_parent_and_donor_defaults():
    fake = _fake()
    res = await service.create_contribution(
        SPONSOR, fake, "S1",
        {"name": "Gift", "contributionType": "Donation", "status": "Received",
         "amount": 1000, "receivedDate": "2026-07-01",
         "sponsorProfileId": "SMUGGLED", "donorNonsense": True},
    )
    entity, payload = fake.created[0]
    assert entity == "CContribution"
    assert payload["sponsorProfileId"] == "S1"       # smuggled FK overridden
    assert "donorNonsense" not in payload            # whitelist drop
    assert payload["donorAccountId"] == "acc1"       # defaults from the funder
    assert payload["donorContactId"] == "con1"
    assert res["name"] == "Gift" and res["parentId"] == "S1"


@pytest.mark.asyncio
async def test_update_contribution_whitelists_and_reads_scope_first():
    fake = _fake(records={("CContribution", "c9"): {
        "name": "Gift", "status": "Received", "sponsorProfileId": "S1",
    }})
    await service.update_contribution(
        SPONSOR, fake, "c9", {"status": "Cancelled", "sponsorProfileId": "HIJACK"}
    )
    entity, rid, payload = fake.updates[0]
    assert (entity, rid) == ("CContribution", "c9")
    assert payload == {"status": "Cancelled"}        # the soft delete path
    # scope check read the contribution, then its parent, before writing
    assert ("CContribution", "c9") in fake.gets and _PARENT in fake.gets


@pytest.mark.asyncio
async def test_amount_save_backfills_currency():
    """EspoCRM's validCurrency check rejects a bare amount when the record's
    stored amountCurrency is null (live 2026-07-21) — any save setting an
    amount carries a currency: the record's existing one, else USD."""
    # update on a record with no stored currency -> USD
    fake = _fake(records={("CContribution", "c9"): {
        "name": "Pledge", "sponsorProfileId": "S1",
    }})
    await service.update_contribution(SPONSOR, fake, "c9", {"amount": 1200})
    assert fake.updates[0][2] == {"amount": 1200, "amountCurrency": "USD"}

    # update on a record that already has a currency -> keep it
    fake2 = _fake(records={("CContribution", "c9"): {
        "name": "Pledge", "sponsorProfileId": "S1", "amountCurrency": "EUR",
    }})
    await service.update_contribution(SPONSOR, fake2, "c9", {"amount": 500})
    assert fake2.updates[0][2] == {"amount": 500, "amountCurrency": "EUR"}

    # create with an amount -> USD; clearing an amount adds NO currency
    fake3 = _fake()
    await service.create_contribution(
        SPONSOR, fake3, "S1", {"name": "G", "contributionType": "Donation",
                               "status": "Received", "amount": 100},
    )
    assert fake3.created[0][1]["amountCurrency"] == "USD"
    fake4 = _fake(records={("CContribution", "c9"): {
        "name": "Pledge", "sponsorProfileId": "S1",
    }})
    await service.update_contribution(SPONSOR, fake4, "c9", {"amount": None, "designation": "x"})
    assert "amountCurrency" not in fake4.updates[0][2]


@pytest.mark.asyncio
async def test_update_with_no_effective_changes_writes_nothing():
    fake = _fake(records={("CContribution", "c9"): {
        "name": "Gift", "sponsorProfileId": "S1",
    }})
    await service.update_contribution(SPONSOR, fake, "c9", {"bogus": 1})
    assert fake.updates == []


@pytest.mark.asyncio
async def test_contribution_without_parent_link_rejected():
    fake = _fake(records={("CContribution", "orphan"): {"name": "X"}})
    with pytest.raises(service.SessionError):
        await service.get_contribution(SPONSOR, fake, "orphan")


@pytest.mark.asyncio
async def test_contribution_scope_check_enforces_parent_acl():
    # Parent unreadable (403) => the EspoError surfaces; the ledger never leaks.
    from core.espo import EspoError
    fake = Fake(records={("CContribution", "c1"): {
        "name": "X", "sponsorProfileId": "FORBIDDEN",
    }})
    with pytest.raises(EspoError):
        await service.get_contribution(SPONSOR, fake, "c1")


@pytest.mark.asyncio
async def test_enum_sanitize_drops_drifted_status_fails_open():
    meta = {"status": {"type": "enum", "options": ["Received", "Cancelled"], "required": True}}
    fake = _fake(records={("CContribution", "c9"): {
        "name": "G", "sponsorProfileId": "S1",
    }}, meta_fields=meta)
    await service.update_contribution(
        SPONSOR, fake, "c9", {"status": "NotARealStatus", "designation": "Gala"}
    )
    entity, rid, payload = fake.updates[0]
    assert payload == {"designation": "Gala"}  # drifted enum dropped, save survives

    # fails open: metadata read blowing up keeps the value
    class Broken(Fake):
        async def metadata(self, key):
            raise RuntimeError("boom")

    fake2 = Broken(records={
        _PARENT: {"name": "Generous Corp"},
        ("CContribution", "c9"): {"name": "G", "sponsorProfileId": "S1"},
    })
    await service.update_contribution(SPONSOR, fake2, "c9", {"status": "Anything"})
    assert fake2.updates[0][2] == {"status": "Anything"}


@pytest.mark.asyncio
async def test_field_required_read_live_from_metadata():
    fake = _fake(meta_fields={
        "name": {"type": "varchar", "required": True},
        "status": {"type": "enum", "required": True, "options": ["Received"]},
        "amount": {"type": "currency"},
    })
    req = await service.contribution_field_required(fake)
    assert req == ["name", "status"]
    opts = await service.contribution_field_options(fake)
    assert opts == {"status": ["Received"]}


# --- config / router wiring -------------------------------------------------

def test_whitelist_covers_spec_plus_currency_companion():
    names = {f["name"] for f in CONTRIBUTION_FIELDS}
    assert CONTRIBUTION_EDIT_NAMES == names | {"amountCurrency"}
    assert "sponsorProfileId" not in CONTRIBUTION_EDIT_NAMES
    assert "donorAccountId" not in CONTRIBUTION_EDIT_NAMES


def test_contributions_tab_sponsor_only_after_sessions():
    sponsor_keys = [t["key"] for t in _detail_tabs(SPONSOR)]
    assert sponsor_keys == [
        "overview", "details", "sessions", "contributions", "communications", "documents",
    ]
    assert "contributions" not in [t["key"] for t in _detail_tabs(MENTOR)]


def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_contribution_endpoints_registered_only_on_sponsor(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_list(cfg, client, parent_id):
        return {"records": [], "summary": None, "parentName": "X"}

    monkeypatch.setattr("sessions.service.list_contributions", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/sponsorsessions/api/records/S1/contributions").status_code == 200
        # mentor/partner routers never registered the routes at all
        assert c.get("/mentorsessions/api/records/S1/contributions").status_code == 404
        assert c.get("/partnersessions/api/records/S1/contributions").status_code == 404
        assert c.get("/mentorsessions/api/contributionfields").status_code == 404


def test_contribution_endpoints_gated_by_team(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Mentor Team"], roles=[]))
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/sponsorsessions/api/records/S1/contributions")
    assert r.status_code == 403
    assert "Sponsor Management Team" in r.json()["detail"]


def test_no_delete_route_exists(monkeypatch):
    # Soft delete is the ONLY removal: no DELETE route is registered anywhere.
    with TestClient(_app(monkeypatch)) as c:
        r = c.delete("/sponsorsessions/api/contributions/c1")
    assert r.status_code in (404, 405)
