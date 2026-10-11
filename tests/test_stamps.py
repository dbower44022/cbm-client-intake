"""assignments.stamps — the shared assignment-stamp engine (audit CLI + the
worker's nightly merge-only reconciliation; stamp-drift layer 3)."""

from __future__ import annotations

from core.config import Settings
from core.espo import EspoError
from assignments import stamps


class FakeEspo:
    def __init__(self, engagements=None, records=None, related=None, profiles=None,
                 partners=None, sponsors=None, teams=None):
        self.engagements = engagements or []
        self.profiles = profiles or []           # CMentorProfile roster (phase A)
        self.partners = partners or []           # CPartnerProfile rows (phase C)
        self.sponsors = sponsors or []           # CSponsorProfile rows (phase C)
        self.teams = dict(teams or {})           # team name -> id (phase C)
        self.records = dict(records or {})       # (entity, id) -> dict
        self.related = dict(related or {})       # (entity, id, link) -> [rows]
        self.updates: list[tuple[str, str, dict]] = []

    async def list(self, entity, *, select=None, max_size=200, offset=0, **kw):
        rows = {"CEngagement": self.engagements, "CMentorProfile": self.profiles,
                "CPartnerProfile": self.partners, "CSponsorProfile": self.sponsors}[entity]
        return {"list": rows[offset:offset + max_size]}

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == "Team" and value in self.teams:
            return {"id": self.teams[value]}
        return None

    async def list_related(self, entity, record_id, link, *, select=None, max_size=50):
        return {"list": self.related.get((entity, record_id, link), [])}

    async def get(self, entity, record_id, select=None):
        return dict(self.records.get((entity, record_id), {}), id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.records.setdefault((entity, record_id), {}).update(payload)
        # A list row or a related row is the same record: keep them in step so
        # a second pass sees what the first wrote (the idempotency tests).
        for rows in (self.engagements, self.profiles, self.partners, self.sponsors,
                     *self.related.values()):
            for row in rows:
                if row.get("id") == record_id:
                    row.update(payload)
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


# --- mentor own-Contact phase (the SECOND drift class, 2026-07-20) ------------


async def test_reconciliation_heals_mentor_own_contacts():
    """/mentorprofile 403 class: a profile's linked Contact missing the
    profile's own User is merged; already-stamped and unlinked profiles are
    left alone."""
    espo = FakeEspo(
        profiles=[
            {"id": "MP1", "name": "Jane", "assignedUserId": "uJ", "contactRecordId": "cJ"},
            {"id": "MP2", "name": "Ok", "assignedUserId": "uO", "contactRecordId": "cO"},
            {"id": "MP3", "name": "NoUser", "contactRecordId": "cN"},
            {"id": "MP4", "name": "NoContact", "assignedUserId": "uX"},
        ],
        engagements=[],
        records={
            ("Contact", "cJ"): {"assignedUsersIds": ["uStranger"]},
            ("Contact", "cO"): {"assignedUsersIds": ["uO"]},
        },
    )
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["mentorProfiles"] == 2  # MP3/MP4 aren't stampable pairs
    assert summary["mentorContactsHealed"] == 1
    writes = {(e, r): p["assignedUsersIds"] for e, r, p in espo.updates}
    assert writes == {("Contact", "cJ"): ["uStranger", "uJ"]}  # merge-only


async def test_ensure_user_on_record_is_noop_when_present():
    espo = FakeEspo(records={("Contact", "c1"): {"assignedUsersIds": ["u1"]}})
    assert await stamps.ensure_user_on_record(espo, "Contact", "c1", "u1") is False
    assert espo.updates == []
    assert await stamps.ensure_user_on_record(espo, "Contact", "c1", "u2") is True
    assert espo.updates == [("Contact", "c1", {"assignedUsersIds": ["u1", "u2"]})]


# --- phase C: the domain team on partner / funder records (#40) ----------------

def _team_fake(**over):
    """One funder record out of its team, its company half in, two contacts:
    one in, one out. One partner already fully in."""
    values = dict(
        teams={"Sponsor Management Team": "T-S", "Partner Management Team": "T-P"},
        sponsors=[{"id": "S1", "name": "Harrowgate", "teamsIds": [], "sponsorCompanyId": "A-S"}],
        partners=[{"id": "P1", "name": "Key Bank", "teamsIds": ["T-P"], "partnerCompanyId": "A-P"}],
        records={
            ("Account", "A-S"): {"teamsIds": ["T-Other"]},
            ("Account", "A-P"): {"teamsIds": ["T-P"]},
        },
        related={
            ("CSponsorProfile", "S1", "sponsorContacts"): [
                {"id": "C-in", "teamsIds": ["T-S"]}, {"id": "C-out", "teamsIds": []},
            ],
            ("CPartnerProfile", "P1", "contacts"): [{"id": "C-P", "teamsIds": ["T-P"]}],
        },
    )
    values.update(over)
    return FakeEspo(**values)


async def test_team_reconciliation_stamps_record_company_and_contacts_merge_only():
    espo = _team_fake()
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["teamRecords"] == 2 and summary["teamHealed"] == 1
    writes = {(e, r): p["teamsIds"] for e, r, p in espo.updates if "teamsIds" in p}
    assert writes[("CSponsorProfile", "S1")] == ["T-S"]
    assert writes[("Account", "A-S")] == ["T-Other", "T-S"]     # merge-only: the other team stays
    assert writes[("Contact", "C-out")] == ["T-S"]
    assert ("Contact", "C-in") not in writes                    # already in: no write
    assert not any(e == "CPartnerProfile" for e, _, _ in espo.updates)  # fully in: untouched


async def test_team_reconciliation_is_idempotent():
    espo = _team_fake()
    await stamps.run_stamp_reconciliation(_settings(), client=espo)
    first = len(espo.updates)
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert len(espo.updates) == first and summary["teamHealed"] == 0


async def test_team_reconciliation_skips_a_domain_whose_team_is_missing(caplog):
    espo = _team_fake(teams={"Partner Management Team": "T-P"})   # no sponsor team on this CRM
    with caplog.at_level("WARNING"):
        summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert "Sponsor Management Team" in caplog.text and "not found" in caplog.text
    assert summary["teamRecords"] == 1          # the partner domain still ran
    assert not any(e == "CSponsorProfile" for e, _, _ in espo.updates)


async def test_team_reconciliation_one_record_failure_never_stops_the_pass():
    class Flaky(FakeEspo):
        async def list_related(self, entity, record_id, link, *, select=None, max_size=50):
            if record_id == "S1":
                raise EspoError("list_related CSponsorProfile/S1/sponsorContacts failed: HTTP 500")
            return await super().list_related(entity, record_id, link, select=select, max_size=max_size)
    espo = _team_fake()
    espo.__class__ = Flaky
    summary = await stamps.run_stamp_reconciliation(_settings(), client=espo)
    assert summary["errors"] == 1
    # the record and its company were stamped before the contacts read failed…
    assert any(e == "CSponsorProfile" for e, _, _ in espo.updates)
    # …and the partner domain still ran
    assert summary["teamRecords"] == 2

