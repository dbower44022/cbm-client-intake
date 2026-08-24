"""Grants — the funder grant book (prds/grant-management-plan.md).

Doug's rulings 2026-08-23 under test:

* the **grant is the hub** — contributions are its payments, deliverables its
  obligations, and the two are siblings (no deliverable→contribution link);
* client attribution lives on the grant (``fundedEngagements``);
* Declined/Cancelled grants stay visible and stop counting — there is no delete
  surface anywhere, the Contributions soft-delete ruling applied to the award.

Phase 2 is MANUAL measurement, so the progress math here is the one place that
decides what a number means; phase 3 changes it and nothing else.

Everything is feature-detected against live CRM metadata, because at the time
this shipped the three entities did not exist in either CRM yet.
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
    DELIVERABLE_EDIT_NAMES,
    DELIVERABLE_FIELDS,
    GRANT_EDIT_NAMES,
    GRANT_FIELDS,
    MENTOR,
    PARTNER,
    SPONSOR,
)
from sessions.router import _detail_tabs

TODAY = date(2026, 8, 23)

_USER = {
    "userId": "u1", "userName": "sam.sponsor", "name": "Sam Sponsor",
    "isAdmin": True, "teams": ["Sponsor Management Team"], "roles": [],
}

_PARENT = ("CSponsorProfile", "S1")

# Metadata the fake CRM reports — keyed exactly as the service asks for it.
_GRANT_META = {f["name"]: {"type": f["type"]} for f in GRANT_FIELDS}
_DELIV_META = {f["name"]: {"type": f["type"]} for f in DELIVERABLE_FIELDS}


class Fake:
    """Minimal SessionClient covering the grant paths.

    ``metadata`` is keyed by the real metadata path, because feature detection
    asks two different entities whether they exist — a fake that answers the
    same fields for every key would hide exactly the bug this guards.
    """

    def __init__(self, *, records=None, related=None, meta=None, listed=None):
        self.records = dict(records or {})
        self.related = related or {}
        self.meta = _META_DEFAULT if meta is None else meta
        self.listed = listed or []          # rows returned by list()
        self.created, self.updates, self.gets, self.lists = [], [], [], []
        self._seq = 0

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id))
        if (entity, record_id) not in self.records:
            from core.espo import EspoError
            raise EspoError(f"get {entity}/{record_id} failed: HTTP 403 forbidden")
        return dict(self.records[(entity, record_id)], id=record_id)

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": self.related.get(link, [])}

    async def list(self, entity, **kw):
        self.lists.append((entity, kw))
        return {"list": list(self.listed)}

    async def create(self, entity, payload):
        self._seq += 1
        rid = f"{entity.lower()}-{self._seq}"
        self.created.append((entity, payload))
        self.records[(entity, rid)] = dict(payload, id=rid)
        return {"id": rid}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.records.setdefault((entity, record_id), {"id": record_id}).update(payload)
        return {"id": record_id}

    async def metadata(self, key):
        return self.meta.get(key)


_META_DEFAULT = {
    "entityDefs.CGrant.fields": _GRANT_META,
    "entityDefs.CGrantDeliverable.fields": _DELIV_META,
}


def _fake(**kw):
    records = {_PARENT: {"name": "Generous Corp", "sponsorCompanyId": "acc1"}}
    records.update(kw.pop("records", {}))
    return Fake(records=records, **kw)


def _deliv(dtype="Numeric", target=10, current=0, *, due=None, status=None, rid="d1"):
    return service._deliverable_row({
        "id": rid, "name": "10 seminars", "deliverableType": dtype,
        "targetValue": target, "currentValue": current, "dueBy": due,
        "deliverableStatus": status, "unit": "seminars",
    }, TODAY)


def _grant(status="Active", amount=50000, *, first=None, nxt=None, rid="g1",
           period_start="2026-01-01", period_end="2026-12-31"):
    return service._grant_row({
        "id": rid, "name": "2026 operating grant", "grantStatus": status,
        "awardAmount": amount, "awardAmountCurrency": "USD",
        "periodStart": period_start, "periodEnd": period_end,
        "firstReportDue": first, "nextReportDue": nxt,
    }, TODAY)


# --- deliverable progress: the one place that decides what a number means ----

def test_numeric_progress_is_current_over_target():
    d = _deliv(current=4, target=10)
    assert d["percent"] == 40.0
    assert d["status"] == "On track" and d["met"] is False


def test_numeric_progress_clamps_above_target_and_reads_met():
    d = _deliv(current=14, target=10)
    assert d["percent"] == 100.0          # 140% would draw a bar off the end
    assert d["status"] == "Met" and d["met"] is True


def test_milestone_is_binary():
    assert _deliv("Milestone", target=1, current=0)["percent"] == 0.0
    done = _deliv("Milestone", target=1, current=1)
    assert done["percent"] == 100.0 and done["met"] is True


def test_narrative_has_no_percentage_at_all():
    """A written answer is not a quantity — an empty bar would read as zero."""
    d = _deliv("Narrative", target=None, current=0)
    assert d["percent"] is None and d["derivedStatus"] is None


def test_no_target_yet_shows_no_bar():
    assert _deliv(target=None, current=3)["percent"] is None
    assert _deliv(target=0, current=3)["percent"] is None


def test_past_due_and_unmet_reads_behind():
    assert _deliv(current=2, due="2026-08-01")["status"] == "Behind"
    assert _deliv(current=2, due="2026-09-01")["status"] == "On track"
    # ...but hitting the target still reads Met, due date or not
    assert _deliv(current=10, due="2026-08-01")["status"] == "Met"


def test_stored_status_overrides_the_arithmetic():
    """Staff overriding the computed status is the point of a manual phase."""
    d = _deliv(current=10, status="Not met")
    assert d["derivedStatus"] == "Met"      # what the numbers say
    assert d["status"] == "Not met" and d["met"] is False   # what staff said


# --- grant rows + summary ----------------------------------------------------

def test_report_due_falls_back_to_first_report_due():
    assert _grant(first="2026-09-30")["reportDue"] == "2026-09-30"
    assert _grant(first="2026-09-30", nxt="2026-10-31")["reportDue"] == "2026-10-31"
    assert _grant()["reportDue"] is None


def test_overdue_flag_ignores_declined_and_cancelled():
    assert _grant(first="2026-08-01")["reportOverdue"] is True
    assert _grant("Cancelled", first="2026-08-01")["reportOverdue"] is False
    assert _grant("Declined", first="2026-08-01")["excluded"] is True


def test_summary_counts_live_grants_only():
    rows = [
        _grant("Active", 50000, rid="a"),
        _grant("Awarded", 25000, rid="b"),
        _grant("Applied", 90000, rid="c"),       # not yet money
        _grant("Declined", 80000, rid="d"),      # never counts
        _grant("Cancelled", 70000, rid="e"),
    ]
    s = service.grant_summary(rows, TODAY)
    assert s["activeCount"] == 2
    assert s["awardedAmount"] == 75000.0
    assert s["totalCount"] == 5                  # everything stays visible


def test_summary_rolls_up_deliverables_excluding_dead_grants():
    live = _grant("Active", rid="a"); live["deliverableCount"] = 4; live["deliverablesMet"] = 3
    dead = _grant("Cancelled", rid="b"); dead["deliverableCount"] = 9; dead["deliverablesMet"] = 9
    s = service.grant_summary([live, dead], TODAY)
    assert (s["deliverablesTotal"], s["deliverablesMet"]) == (4, 3)


def test_summary_next_report_is_the_soonest_future_one():
    rows = [
        _grant("Active", first="2026-11-30", rid="a"),
        _grant("Active", first="2026-09-30", rid="b"),
        _grant("Active", first="2026-07-01", rid="c"),   # overdue, not "next"
    ]
    s = service.grant_summary(rows, TODAY)
    assert s["nextReportDue"] == "2026-09-30"
    assert s["overdueReports"] == 1


def test_summary_empty():
    s = service.grant_summary([], TODAY)
    assert s["activeCount"] == 0 and s["awardedAmount"] == 0
    assert s["nextReportDue"] is None and s["deliverablesTotal"] == 0


# --- feature detection: the CRM may not have the entities yet ----------------

@pytest.mark.asyncio
async def test_grants_available_needs_both_entities():
    assert await service.grants_available(_fake()) is True
    assert await service.grants_available(_fake(meta={})) is False
    assert await service.grants_available(
        _fake(meta={"entityDefs.CGrant.fields": _GRANT_META})   # deliverable missing
    ) is False


@pytest.mark.asyncio
async def test_grants_available_fails_closed_when_metadata_breaks():
    """Fail CLOSED: an unreadable probe cannot prove the entities exist, and
    offering the tab on a guess produces forms whose saves the CRM rejects."""
    class Broken(Fake):
        async def metadata(self, key):
            raise RuntimeError("boom")

    assert await service.grants_available(Broken()) is False


@pytest.mark.asyncio
async def test_list_grants_short_circuits_when_the_crm_lacks_them():
    fake = _fake(meta={})
    res = await service.list_grants(SPONSOR, fake, "S1")
    assert res["available"] is False and res["records"] == []
    assert fake.gets[0] == _PARENT          # the ACL gate still ran first


@pytest.mark.asyncio
async def test_field_specs_drop_fields_the_crm_does_not_have():
    """The spec IS the whitelist, so a dropped field is dropped from both."""
    fake = _fake(meta={
        "entityDefs.CGrant.fields": {"name": {}, "grantStatus": {}},
        "entityDefs.CGrantDeliverable.fields": {"name": {}},
    })
    assert [f["name"] for f in await service.grant_fields(fake)] == ["name", "grantStatus"]
    assert [f["name"] for f in await service.deliverable_fields(fake)] == ["name"]


@pytest.mark.asyncio
async def test_create_grant_drops_a_field_the_crm_lacks():
    fake = _fake(meta={
        "entityDefs.CGrant.fields": {"name": {}, "grantStatus": {}},
        "entityDefs.CGrantDeliverable.fields": {"name": {}},
    })
    await service.create_grant(
        SPONSOR, fake, "S1", {"name": "G", "grantStatus": "Active", "renewalDeadline": "2027-01-01"},
    )
    assert "renewalDeadline" not in fake.created[0][1]


# --- CRUD --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_grants_reads_parent_first_and_attaches_rollups():
    fake = _fake(
        related={"grants": [
            {"id": "g1", "name": "A", "grantStatus": "Active", "awardAmount": 1000,
             "periodStart": "2026-01-01"},
            {"id": "g2", "name": "B", "grantStatus": "Active", "awardAmount": 500,
             "periodStart": "2025-01-01"},
        ]},
        listed=[
            {"id": "d1", "grantId": "g1", "deliverableType": "Numeric",
             "targetValue": 10, "currentValue": 10},
            {"id": "d2", "grantId": "g1", "deliverableType": "Numeric",
             "targetValue": 10, "currentValue": 2},
        ],
    )
    res = await service.list_grants(SPONSOR, fake, "S1")
    assert fake.gets[0] == _PARENT                       # the ACL gate
    assert [r["id"] for r in res["records"]] == ["g1", "g2"]   # newest period first
    g1 = res["records"][0]
    assert (g1["deliverableCount"], g1["deliverablesMet"]) == (2, 1)
    assert len(fake.lists) == 1                          # ONE call, never N+1


@pytest.mark.asyncio
async def test_rollup_failure_never_breaks_the_grid():
    class NoList(Fake):
        async def list(self, entity, **kw):
            from core.espo import EspoError
            raise EspoError("list CGrantDeliverable failed: HTTP 403 forbidden")

    fake = NoList(
        records={_PARENT: {"name": "Generous Corp"}},
        related={"grants": [{"id": "g1", "name": "A", "grantStatus": "Active"}]},
    )
    res = await service.list_grants(SPONSOR, fake, "S1")
    assert res["records"][0]["deliverableCount"] == 0


@pytest.mark.asyncio
async def test_create_grant_stamps_parent_and_whitelists():
    fake = _fake()
    res = await service.create_grant(
        SPONSOR, fake, "S1",
        {"name": "2026 operating", "grantStatus": "Awarded", "awardAmount": 50000,
         "sponsorProfileId": "SMUGGLED", "deliverablesIds": ["x"], "nonsense": True},
    )
    entity, payload = fake.created[0]
    assert entity == "CGrant"
    assert payload["sponsorProfileId"] == "S1"     # smuggled FK overridden
    assert "nonsense" not in payload and "deliverablesIds" not in payload
    assert res["parentId"] == "S1"


@pytest.mark.asyncio
async def test_award_amount_save_backfills_currency():
    """EspoCRM's validCurrency rejects a bare amount when the stored currency is
    null — the exact defect that 400'd the contributions ledger in v0.123.2."""
    fake = _fake()
    await service.create_grant(SPONSOR, fake, "S1", {"name": "G", "awardAmount": 1000})
    assert fake.created[0][1]["awardAmountCurrency"] == "USD"

    fake2 = _fake(records={("CGrant", "g9"): {
        "name": "G", "sponsorProfileId": "S1", "awardAmountCurrency": "EUR",
    }})
    await service.update_grant(SPONSOR, fake2, "g9", {"awardAmount": 500})
    assert fake2.updates[0][2]["awardAmountCurrency"] == "EUR"

    # clearing an amount adds no currency
    fake3 = _fake(records={("CGrant", "g9"): {"name": "G", "sponsorProfileId": "S1"}})
    await service.update_grant(SPONSOR, fake3, "g9", {"awardAmount": None, "programArea": "x"})
    assert "awardAmountCurrency" not in fake3.updates[0][2]


@pytest.mark.asyncio
async def test_next_report_due_seeded_from_first_but_never_overwritten():
    fake = _fake()
    await service.create_grant(
        SPONSOR, fake, "S1", {"name": "G", "firstReportDue": "2026-09-30"})
    assert fake.created[0][1]["nextReportDue"] == "2026-09-30"

    # a date already on the record wins over the inferred one
    fake2 = _fake(records={("CGrant", "g9"): {
        "name": "G", "sponsorProfileId": "S1", "nextReportDue": "2026-12-31",
    }})
    await service.update_grant(SPONSOR, fake2, "g9", {"firstReportDue": "2026-09-30"})
    assert "nextReportDue" not in fake2.updates[0][2]


@pytest.mark.asyncio
async def test_update_grant_whitelists_and_gates_scope_first():
    fake = _fake(records={("CGrant", "g9"): {
        "name": "G", "grantStatus": "Active", "sponsorProfileId": "S1",
    }})
    await service.update_grant(
        SPONSOR, fake, "g9", {"grantStatus": "Cancelled", "sponsorProfileId": "HIJACK"})
    entity, rid, payload = fake.updates[0]
    assert (entity, rid) == ("CGrant", "g9")
    assert payload == {"grantStatus": "Cancelled"}       # the soft-delete path
    assert ("CGrant", "g9") in fake.gets and _PARENT in fake.gets


@pytest.mark.asyncio
async def test_grant_without_a_funder_is_rejected():
    fake = _fake(records={("CGrant", "orphan"): {"name": "X"}})
    with pytest.raises(service.SessionError):
        await service.get_grant(SPONSOR, fake, "orphan")


@pytest.mark.asyncio
async def test_grant_scope_check_enforces_the_funder_acl():
    from core.espo import EspoError
    fake = Fake(records={("CGrant", "g1"): {"name": "X", "sponsorProfileId": "FORBIDDEN"}})
    with pytest.raises(EspoError):
        await service.get_grant(SPONSOR, fake, "g1")


@pytest.mark.asyncio
async def test_deliverable_create_stamps_its_grant_and_whitelists():
    fake = _fake(records={("CGrant", "g9"): {"name": "G", "sponsorProfileId": "S1"}})
    await service.create_deliverable(
        SPONSOR, fake, "g9",
        {"name": "10 seminars", "deliverableType": "Numeric", "targetValue": 10,
         "grantId": "SMUGGLED", "sponsorProfileId": "NOPE"},
    )
    entity, payload = fake.created[0]
    assert entity == "CGrantDeliverable"
    assert payload["grantId"] == "g9"
    assert "sponsorProfileId" not in payload


@pytest.mark.asyncio
async def test_deliverable_scope_runs_through_its_grants_funder():
    """A bare deliverable id must not resolve from outside the funder workspace."""
    from core.espo import EspoError
    fake = Fake(records={
        ("CGrantDeliverable", "d1"): {"name": "X", "grantId": "g9"},
        ("CGrant", "g9"): {"name": "G", "sponsorProfileId": "FORBIDDEN"},
    })
    with pytest.raises(EspoError):
        await service.get_deliverable(SPONSOR, fake, "d1")

    orphan = _fake(records={("CGrantDeliverable", "d2"): {"name": "X"}})
    with pytest.raises(service.SessionError):
        await service.get_deliverable(SPONSOR, orphan, "d2")


@pytest.mark.asyncio
async def test_enum_drift_is_dropped_and_fails_open():
    meta = dict(_META_DEFAULT)
    meta["entityDefs.CGrant.fields"] = dict(
        _GRANT_META, grantStatus={"type": "enum", "options": ["Active", "Closed"]})
    fake = _fake(records={("CGrant", "g9"): {"name": "G", "sponsorProfileId": "S1"}}, meta=meta)
    await service.update_grant(
        SPONSOR, fake, "g9", {"grantStatus": "NotAStatus", "programArea": "Mentoring"})
    assert fake.updates[0][2] == {"programArea": "Mentoring"}

    class Broken(Fake):
        async def metadata(self, key):
            if key.endswith(".fields"):
                return _META_DEFAULT.get(key)
            raise RuntimeError("boom")

    fake2 = Broken(records={
        _PARENT: {"name": "Generous Corp"},
        ("CGrant", "g9"): {"name": "G", "sponsorProfileId": "S1"},
    })
    await service.update_grant(SPONSOR, fake2, "g9", {"grantStatus": "Anything"})
    assert fake2.updates[0][2]["grantStatus"] == "Anything"


# --- config / router wiring --------------------------------------------------

def test_whitelists_are_exactly_the_specs():
    assert GRANT_EDIT_NAMES == {f["name"] for f in GRANT_FIELDS} | {"awardAmountCurrency"}
    assert DELIVERABLE_EDIT_NAMES == {f["name"] for f in DELIVERABLE_FIELDS}
    # the links that decide WHOSE record this is are never editable here
    assert "sponsorProfileId" not in GRANT_EDIT_NAMES
    assert "grantId" not in DELIVERABLE_EDIT_NAMES
    assert "fundedEngagementsIds" not in GRANT_EDIT_NAMES


def test_only_the_sponsor_domain_has_a_grant_book():
    assert SPONSOR.grants_link == "grants"
    assert MENTOR.grants_link is None and PARTNER.grants_link is None


def test_grants_tab_needs_the_flag_and_sits_after_contributions():
    assert "grants" not in [t["key"] for t in _detail_tabs(SPONSOR)]
    keys = [t["key"] for t in _detail_tabs(SPONSOR, grants=True)]
    assert keys == [
        "overview", "details", "sessions", "contributions", "grants",
        "communications", "documents",
    ]
    # the flag alone never puts the tab on a domain that has no grant book
    assert "grants" not in [t["key"] for t in _detail_tabs(MENTOR, grants=True)]


def _app(monkeypatch, *, grants=False):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GRANTS_ENABLED", "true" if grants else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_grant_endpoints_registered_only_on_sponsor(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_list(cfg, client, parent_id):
        return {"records": [], "summary": None, "parentName": "X", "available": True}

    monkeypatch.setattr("sessions.service.list_grants", fake_list)
    with TestClient(_app(monkeypatch, grants=True)) as c:
        assert c.get("/sponsorsessions/api/records/S1/grants").status_code == 200
        assert c.get("/mentorsessions/api/records/S1/grants").status_code == 404
        assert c.get("/partnersessions/api/records/S1/grants").status_code == 404
    get_settings.cache_clear()


def test_grant_endpoints_404_while_the_feature_is_off(monkeypatch):
    """Off must be indistinguishable from never built — the routes exist
    because mounting happens once at boot, so the flag is checked per request."""
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch, grants=False)) as c:
        assert c.get("/sponsorsessions/api/records/S1/grants").status_code == 404
        assert c.get("/sponsorsessions/api/grantfields").status_code == 404
    get_settings.cache_clear()


def test_grant_endpoints_gated_by_team(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Mentor Team"], roles=[]))
    with TestClient(_app(monkeypatch, grants=True)) as c:
        r = c.get("/sponsorsessions/api/records/S1/grants")
    assert r.status_code == 403
    assert "Sponsor Management Team" in r.json()["detail"]
    get_settings.cache_clear()


def test_no_delete_route_exists(monkeypatch):
    """A grant that falls through is Declined or Cancelled — never deleted."""
    with TestClient(_app(monkeypatch, grants=True)) as c:
        assert c.delete("/sponsorsessions/api/grants/g1").status_code in (404, 405)
        assert c.delete("/sponsorsessions/api/deliverables/d1").status_code in (404, 405)
    get_settings.cache_clear()
