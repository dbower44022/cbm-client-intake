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
    checks = [c for c in espo.calls if c.startswith("list ")][1:]
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

