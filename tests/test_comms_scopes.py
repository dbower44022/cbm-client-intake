"""The mailbox-scope cache (comms/scopes.py, v0.247.0, Doug's option A)."""

from __future__ import annotations

import pytest

from comms import scopes
from core.espo import EspoError


class Cfg:
    comms_scope_rebuild_seconds = 3600
    comms_engagement_statuses_list = ["Active"]
    comms_partner_excluded_statuses_list = []
    comms_internal_domains_list = ["cbmentors.org"]


class FakeEspo:
    """Counts reads; answers the change check from ``changed`` and the scope
    build from one manager with one active engagement and one contact."""

    def __init__(self, changed: set[str] | None = None, fail: set[str] | None = None):
        self.changed = changed or set()
        self.fail = fail or set()
        self.calls: list[str] = []

    async def list(self, entity, *, where=None, select=None, max_size=50, **kw):
        self.calls.append(f"list {entity}")
        if where and where[0].get("type") == "after":
            if entity in self.fail:
                raise EspoError(f"list {entity} failed: HTTP 403")
            return {"total": 1 if entity in self.changed else 0, "list": []}
        return {"list": [{
            "id": "mp1", "name": "Mentor One", "cbmEmail": "m1@cbmentors.org",
            "assignedUserId": "u1", "contactRecordId": "c-m1",
        }]}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=50, **kw):
        self.calls.append(f"related {entity}/{link}")
        if link == "engagements1":
            return {"list": [{"id": "e1", "name": "Client", "engagementStatus": "Active"}]}
        if link == "engagementContacts":
            return {"list": [{"id": "c1", "name": "Pat", "emailAddress": "pat@client.example"}]}
        return {"list": []}


@pytest.fixture(autouse=True)
def _fresh():
    scopes.reset()
    yield
    scopes.reset()


def _builds(espo: FakeEspo) -> int:
    return sum(1 for c in espo.calls if c == "related CMentorProfile/engagements1")


async def test_first_pass_builds_then_reuses_when_nothing_changed():
    espo = FakeEspo()
    first = await scopes.scopes_for_pass(espo, Cfg())
    assert len(first) == 1 and first[0].mailbox == "m1@cbmentors.org"
    assert _builds(espo) == 1
    second = await scopes.scopes_for_pass(espo, Cfg())
    assert second is first, "the same scope objects, no rebuild"
    assert _builds(espo) == 1
    # The change check is one one-row read per watched entity, nothing more.
    checks = [c for c in espo.calls if c.startswith("list ")][2:]  # the build read profiles AND leads
    assert checks == [f"list {e}" for e in scopes.WATCHED_ENTITIES]


@pytest.mark.parametrize("entity", scopes.WATCHED_ENTITIES)
async def test_a_change_in_any_watched_entity_rebuilds(entity):
    espo = FakeEspo()
    first = await scopes.scopes_for_pass(espo, Cfg())
    espo.changed = {entity}
    second = await scopes.scopes_for_pass(espo, Cfg())
    assert second is not first and _builds(espo) == 2


async def test_an_unanswerable_check_rebuilds():
    espo = FakeEspo(fail={"CEngagement"})
    await scopes.scopes_for_pass(espo, Cfg())
    await scopes.scopes_for_pass(espo, Cfg())
    assert _builds(espo) == 2, "fail open to freshness"


async def test_the_age_limit_forces_a_rebuild(monkeypatch):
    espo = FakeEspo()
    await scopes.scopes_for_pass(espo, Cfg())
    monkeypatch.setattr(scopes.time, "monotonic", lambda: scopes._cache.built_at + 3601)
    await scopes.scopes_for_pass(espo, Cfg())
    assert _builds(espo) == 2


async def test_zero_rebuilds_every_pass_without_a_check():
    class Off(Cfg):
        comms_scope_rebuild_seconds = 0

    espo = FakeEspo()
    await scopes.scopes_for_pass(espo, Off())
    await scopes.scopes_for_pass(espo, Off())
    assert _builds(espo) == 2
    assert not any(c == "list CEngagement" for c in espo.calls), "no change check"


def test_watermark_sits_behind_the_build_in_crm_format():
    from datetime import datetime, timezone

    stamp = scopes._crm_stamp(datetime(2026, 10, 9, 16, 30, 5, tzinfo=timezone.utc) - scopes._OVERLAP)
    assert stamp == "2026-10-09 16:29:05"


async def test_the_sync_pass_uses_the_cache(monkeypatch):
    """run_gmail_sync goes through the cache, not straight to build_scopes."""
    from comms import sync

    seen = {"n": 0}

    async def fake_scopes(client, settings):
        seen["n"] += 1
        return []

    monkeypatch.setattr(scopes, "scopes_for_pass", fake_scopes)
    out = await sync.run_gmail_sync(Cfg(), None, FakeEspo(), {})
    assert seen["n"] == 1 and out["mailboxes"] == 0


@pytest.mark.asyncio
async def test_scope_build_reads_the_additional_manager_links_and_skips_an_absent_one(caplog):
    """v0.251.0: a manager's mailbox covers the records they are an ADDITIONAL
    manager on (co-mentored engagements, co-managed partners and funders),
    read through the second reverse link per domain. A CRM that lacks the
    link answers 404, which is skipped quietly — never an hourly warning."""
    from comms.crm import build_scopes

    class Espo(FakeEspo):
        async def list_related(self, entity, record_id, link, *, select=None, max_size=50, **kw):
            self.calls.append(f"related {entity}/{link}")
            if link == "comanagedSponsors":
                raise EspoError("list_related CMentorProfile/mp1/comanagedSponsors failed: HTTP 404 Not Found")
            if link == "comanagedPartners":
                return {"list": [{"id": "p9", "name": "Key Bank", "partnershipStatus": "Active"}]}
            if link == "contacts":
                return {"list": [{"id": "c-kb", "name": "Dana", "emailAddress": "dana@keybank.example"}]}
            return await super().list_related(entity, record_id, link, select=select, max_size=max_size, **kw)

    espo = Espo()
    with caplog.at_level("WARNING"):
        built = await build_scopes(espo, Cfg())
    assert "related CMentorProfile/engagements" in espo.calls       # co-mentored engagements
    assert "related CMentorProfile/comanagedPartners" in espo.calls
    assert "related CMentorProfile/comanagedSponsors" in espo.calls
    assert "comanagedSponsors" not in caplog.text                    # the 404 is not a warning
    scope = built[0]
    assert any(r.id == "p9" and "dana@keybank.example" in r.addresses for r in scope.records)



# --- the lead source (prospect marketing rulings 109, 118, 120; M5) ----------

async def test_assigned_leads_join_their_assignees_mailbox_and_only_assigned_ones():
    """A lead with an assignee and an email joins the scope of the assignee's
    mailbox — the mentor profile's address first. An unassigned lead, a lead
    with no email, and a lead on an internal address contribute nothing."""
    from comms.crm import build_scopes

    class Espo(FakeEspo):
        async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, **kw):
            self.calls.append(f"list {entity}")
            if entity == "CProspect":
                return {"list": [
                    {"id": "L1", "name": "Marigold", "businessName": "Marigold Pet Grooming",
                     "email": "Rosa@Marigold.example", "assignedUserId": "u1"},
                    {"id": "L2", "name": "Nobody", "email": "x@unassigned.example"},          # dropped by the where in life
                    {"id": "L3", "name": "Internal", "email": "pat@cbmentors.org", "assignedUserId": "u1"},
                ]}
            return await super().list(entity, where=where, select=select, max_size=max_size, **kw)

    espo = Espo()
    built = await build_scopes(espo, Cfg())
    assert len(built) == 1
    scope = built[0]
    assert scope.mailbox == "m1@cbmentors.org"
    leads = [r for r in scope.records if r.entity == "CProspect"]
    assert [(r.id, r.addresses) for r in leads] == [("L1", {"rosa@marigold.example"})]
    assert scope.records_for({"rosa@marigold.example"})[0].id == "L1"
    # Exact address only: a stranger on the same domain is nobody's lead.
    assert scope.records_for({"someone.else@marigold.example"}) == []


async def test_a_marketer_without_a_profile_gets_a_scope_from_their_own_address():
    """Ruling 120: no mentor profile, but the user's own address is on the
    chapter's mail domain — a scope of their own, built from their leads. A
    user whose address is elsewhere contributes no scope."""
    from comms.crm import build_scopes

    class Espo(FakeEspo):
        async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, **kw):
            self.calls.append(f"list {entity}")
            if entity == "CProspect":
                return {"list": [
                    {"id": "L1", "name": "Marigold", "email": "rosa@marigold.example", "assignedUserId": "u-mark",
                     "assignedUserName": "Mark Marketing"},
                    {"id": "L2", "name": "Elsewhere", "email": "ed@elsewhere.example", "assignedUserId": "u-gmail"},
                ]}
            return await super().list(entity, where=where, select=select, max_size=max_size, **kw)

        async def get(self, entity, record_id, select=None):
            self.calls.append(f"get {entity}/{record_id}")
            return {"u-mark": {"id": "u-mark", "emailAddress": "Mark.Marketing@cbmentors.org", "name": "Mark Marketing"},
                    "u-gmail": {"id": "u-gmail", "emailAddress": "ed@gmail.example"}}[record_id]

    class Settings(Cfg):
        mentor_email_domain = "cbmentors.org"

    espo = Espo()
    built = await build_scopes(espo, Settings())
    by_mailbox = {s.mailbox: s for s in built}
    assert set(by_mailbox) == {"m1@cbmentors.org", "mark.marketing@cbmentors.org"}
    mark = by_mailbox["mark.marketing@cbmentors.org"]
    assert mark.owner_user_id == "u-mark" and mark.manager_name == "Mark Marketing"
    assert [r.id for r in mark.records] == ["L1"] and mark.records[0].entity == "CProspect"
    assert espo.calls.count("get User/u-mark") == 1 and "get User/u-gmail" in espo.calls


async def test_a_crm_without_leads_is_skipped_quietly(caplog):
    from comms.crm import build_scopes

    class Espo(FakeEspo):
        async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, **kw):
            if entity == "CProspect":
                raise EspoError("list CProspect failed: HTTP 404 Not Found")
            return await super().list(entity, where=where, select=select, max_size=max_size, **kw)

    with caplog.at_level("WARNING"):
        built = await build_scopes(Espo(), Cfg())
    assert len(built) == 1 and all(r.entity != "CProspect" for r in built[0].records)
    assert "CProspect" not in caplog.text


def test_leads_are_a_watched_entity():
    assert "CProspect" in scopes.WATCHED_ENTITIES
