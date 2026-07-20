"""assignments.stamps — the shared assignment-stamp engine (audit CLI + the
worker's nightly merge-only reconciliation; stamp-drift layer 3)."""

from __future__ import annotations

from core.config import Settings
from assignments import stamps


class FakeEspo:
    def __init__(self, engagements=None, records=None, related=None):
        self.engagements = engagements or []
        self.records = dict(records or {})       # (entity, id) -> dict
        self.related = dict(related or {})       # (entity, id, link) -> [rows]
        self.updates: list[tuple[str, str, dict]] = []

    async def list(self, entity, *, select=None, max_size=200, offset=0, **kw):
        assert entity == "CEngagement"
        return {"list": self.engagements[offset:offset + max_size]}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=50):
        return {"list": self.related.get((entity, record_id, link), [])}

    async def get(self, entity, record_id, select=None):
        return dict(self.records.get((entity, record_id), {}), id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.records.setdefault((entity, record_id), {}).update(payload)
        return {"id": record_id}


def _eng(**over):
    base = {
        "id": "E1", "name": "Agape", "engagementStatus": "Active",
        "mentorProfileId": "MP1", "mentorProfileName": "Matt Mentor",
        "primaryEngagementContactId": "C1", "engagementClientId": "CP1",
        "clientOrganizationId": "A1", "assignedUsersIds": ["uM"],
    }
    base.update(over)
    return base


def _fake(**over):
    """A world with one Active engagement: mentor uM, co-mentor uC; the
    engagement carries uM only; C1 empty, CP1 has uM, A1 has a stranger."""
    values = dict(
        engagements=[_eng()],
        records={
            ("CMentorProfile", "MP1"): {"name": "Matt Mentor", "assignedUserId": "uM"},
            ("Contact", "C1"): {"assignedUsersIds": []},
            ("CClientProfile", "CP1"): {"assignedUsersIds": ["uM"]},
            ("Account", "A1"): {"assignedUsersIds": ["uStranger"]},
            ("CEngagement", "E1"): {"assignedUsersIds": ["uM"]},
        },
        related={
            ("CEngagement", "E1", "additionalMentors"): [
                {"name": "Cici Caver", "assignedUsersIds": ["uC"]},
            ],
            ("CEngagement", "E1", "engagementContacts"): [{"id": "C1"}],
        },
    )
    values.update(over)
    return FakeEspo(**values)


def _settings(**over):
    base = dict(espo_dry_run=False, espo_api_key="k")
    base.update(over)
    return Settings(**base)


async def test_entitled_users_mentor_plus_comentors():
    espo = _fake()
    entitled = await stamps.entitled_user_ids(espo, _eng())
    assert entitled == {"uM": "Matt Mentor", "uC": "Cici Caver"}


async def test_related_records_cover_all_client_records():
    espo = _fake()
    recs = await stamps.related_records(espo, _eng())
    assert recs == [
        ("CEngagement", "E1", "engagement"),
        ("Contact", "C1", "contact"),
        ("CClientProfile", "CP1", "client profile"),
        ("Account", "A1", "company"),
    ]


async def test_related_records_linked_company_fallback():
    espo = _fake(records={
        ("CClientProfile", "CP1"): {"linkedCompanyId": "A9", "assignedUsersIds": []},
    })
    recs = await stamps.related_records(espo, _eng(clientOrganizationId=None))
    assert ("Account", "A9", "company") in recs


async def test_reconciliation_merges_only_missing_and_keeps_strangers():
    espo = _fake()
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["audited"] == 1 and summary["engagementsHealed"] == 1
    writes = {(e, r): p["assignedUsersIds"] for e, r, p in espo.updates}
    # Engagement + contact + profile get the missing users merged in…
    assert writes[("CEngagement", "E1")] == ["uM", "uC"]
    assert writes[("Contact", "C1")] == ["uM", "uC"]
    assert writes[("CClientProfile", "CP1")] == ["uM", "uC"]
    # …and MERGE-ONLY: the stranger on the Account is kept, never removed.
    assert writes[("Account", "A1")] == ["uStranger", "uM", "uC"]


async def test_reconciliation_is_idempotent():
    espo = _fake()
    await stamps.run_stamp_reconciliation(_settings(), client=espo)
    first_writes = len(espo.updates)
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert len(espo.updates) == first_writes  # nothing left to merge
    assert summary["recordsHealed"] == 0


async def test_reconciliation_skips_unassigned_and_terminal():
    espo = _fake(engagements=[
        _eng(id="E1"),
        _eng(id="E2", mentorProfileId=None),
        _eng(id="E3", engagementStatus="Completed"),
    ])
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["audited"] == 1


async def test_reconciliation_counts_profiles_without_user(caplog):
    espo = _fake(records={
        ("CMentorProfile", "MP1"): {"name": "Fred Flinstone"},  # no linked User
    }, related={})
    with caplog.at_level("WARNING", logger="cbm_intake.assignments.stamps"):
        summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["profilesWithoutUser"] == 1
    assert summary["recordsHealed"] == 0
    assert any("no linked login User" in r.getMessage() for r in caplog.records)


async def test_reconciliation_one_engagement_failure_never_stops_the_pass():
    class Flaky(FakeEspo):
        async def get(self, entity, record_id, select=None):
            if record_id == "MP-broken":
                from core.espo import EspoError

                raise EspoError("get CMentorProfile/MP-broken failed: HTTP 404 ")
            return await super().get(entity, record_id, select)

    espo = _fake()
    espo.__class__ = Flaky
    espo.engagements = [_eng(id="E0", mentorProfileId="MP-broken"), _eng()]
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["errors"] == 1
    assert summary["engagementsHealed"] == 1  # E1 still healed


async def test_reconciliation_inert_without_a_real_crm():
    assert await stamps.run_stamp_reconciliation(Settings(espo_dry_run=True)) is None
    assert await stamps.run_stamp_reconciliation(
        Settings(espo_dry_run=False, espo_api_key="")
    ) is None
