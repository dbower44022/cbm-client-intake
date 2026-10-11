"""The sandbox seeders' event showcase and team-stamp stages, against a fake CRM.

These scripts only ever run against crm-test, so what a test can prove is the
shape: feature detection skips rather than fails, every write is idempotent,
and nothing is ever removed. The live result is the re-baseline runbook's job.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    path = ROOT / "scripts" / "sandbox" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class FakeCrm:
    """Just enough of EspoClient for the two stages under test."""

    def __init__(self, *, presenters: bool = True, topics: bool = True) -> None:
        self.rows: dict[str, dict[str, dict]] = {
            "CEvent": {}, "Contact": {}, "CPartnerProfile": {}, "CSponsorProfile": {},
            "CEventPresenter": {}, "Team": {}, "CMentorProfile": {},
        }
        self.links: dict[tuple[str, str, str], set[str]] = {}
        self.writes: list[tuple] = []
        self._n = 0
        self.presenters = presenters
        self.topics = topics

    def add(self, entity: str, **row) -> dict:
        self._n += 1
        row.setdefault("id", f"{entity.lower()}-{self._n}")
        self.rows[entity][row["id"]] = row
        return row

    async def list(self, entity, select="", where=None, max_size=200, offset=0, **_):
        rows = list(self.rows.get(entity, {}).values())
        for clause in where or []:
            rows = [r for r in rows if r.get(clause["attribute"]) == clause["value"]]
        return {"list": rows[offset:offset + max_size], "total": len(rows)}

    async def find_one(self, entity, attribute, value, select="id"):
        data = await self.list(entity, where=[{"type": "equals", "attribute": attribute,
                                               "value": value}], max_size=1)
        return (data["list"] or [None])[0]

    async def get(self, entity, record_id, select=""):
        return dict(self.rows[entity].get(record_id) or {})

    async def create(self, entity, payload):
        self.writes.append(("create", entity, dict(payload)))
        return dict(self.add(entity, **payload))

    async def update(self, entity, record_id, payload):
        self.writes.append(("update", entity, record_id, dict(payload)))
        self.rows[entity][record_id].update(payload)
        return {}

    async def relate(self, entity, record_id, link, related_id):
        self.writes.append(("relate", entity, record_id, link, related_id))
        self.links.setdefault((entity, record_id, link), set()).add(related_id)

    async def list_related(self, entity, record_id, link, select="id", max_size=200, **_):
        ids = self.links.get((entity, record_id, link), set())
        return {"list": [{"id": i} for i in sorted(ids)]}

    async def metadata(self, key):
        if key == "entityDefs.CEventPresenter":
            return {"fields": {"name": {}}} if self.presenters else None
        if key == "entityDefs.CEvent.links":
            links = {"partnerProfiles": {"entity": "CPartnerProfile"},
                     "sponsorProfiles": {"entity": "CSponsorProfile"}}
            if self.presenters:
                links["eventPresenters"] = {"entity": "CEventPresenter"}
            return links
        if key == "entityDefs.CEvent.fields":
            fields = {"name": {}, "showPresenterBios": {}}
            if self.topics:
                fields["topics"] = {"type": "multiEnum"}
            return fields
        return None

    async def metadata_enum_options(self, entity, field):
        if (entity, field) == ("CEvent", "topics") and self.topics:
            return ["Business Fundamentals", "Marketing & Sales", "Finance & Accounting",
                    "Leadership & People", "Operations", "Technology & Digital"]
        return None

    async def download_attachment(self, attachment_id):
        return b"png", "image/png"

    async def upload_attachment(self, **kwargs):
        self.writes.append(("upload", kwargs["filename"]))
        return "att-copy"


def _seeded(crm: FakeCrm, enrich) -> None:
    for _offset, name, *_rest in enrich.EVENTS:
        crm.add("CEvent", name=name)
    for who in ("Joe Mentor", "Matt Mentor", "Terrence Boyd"):
        crm.add("Contact", name=who, emailAddress=who.lower().replace(" ", ".") + "@x")
    for p in ("Cuyahoga Small Business Alliance", "Northgate Chamber of Commerce"):
        crm.add("CPartnerProfile", name=p)
    for f in ("Harrowgate Family Trust", "Blue Heron Foundation"):
        crm.add("CSponsorProfile", name=f)


@pytest.mark.asyncio
async def test_event_showcase_adds_everything_once_and_removes_nothing():
    enrich = _load("enrich_training_data")
    crm = FakeCrm()
    _seeded(crm, enrich)
    pricing = next(r for r in crm.rows["CEvent"].values() if r["name"] == "Pricing for Profit")
    # The deepen script already related the funder — the stage must keep it
    # and must not relate it twice.
    harrowgate = next(r for r in crm.rows["CSponsorProfile"].values()
                      if r["name"] == "Harrowgate Family Trust")
    crm.links[("CEvent", pricing["id"], "sponsorProfiles")] = {harrowgate["id"]}

    e = enrich.Enricher(crm, apply=True)
    await enrich.add_event_showcase(e)

    presenters = list(crm.rows["CEventPresenter"].values())
    assert len(presenters) == 4
    hiring = next(r for r in crm.rows["CEvent"].values() if r["name"] == "Hiring Your First Employee")
    assert {r["name"] for r in presenters if r["eventId"] == hiring["id"]} == {"Joe Mentor", "Terrence Boyd"}
    guest = next(r for r in crm.rows["Contact"].values() if r.get("lastName") == "Okafor")
    assert guest["cContactType"] == ["Presenter"]
    assert hiring["showPresenterBios"] is True
    assert hiring["topics"] == ["Leadership & People", "Operations"]
    assert crm.links[("CEvent", hiring["id"], "partnerProfiles")]
    assert crm.links[("CEvent", pricing["id"], "sponsorProfiles")] == {harrowgate["id"]}
    relates = [w for w in crm.writes if w[0] == "relate"]
    assert len(relates) == 5  # 3 partner links + 2 new funder links; Harrowgate kept
    first_pass = len(crm.writes)

    e2 = enrich.Enricher(crm, apply=True)
    await enrich.add_event_showcase(e2)
    assert len(crm.writes) == first_pass, "a second run must write nothing"
    assert len(crm.rows["CEventPresenter"]) == 4


@pytest.mark.asyncio
async def test_event_showcase_skips_what_the_crm_lacks():
    enrich = _load("enrich_training_data")
    crm = FakeCrm(presenters=False, topics=False)
    _seeded(crm, enrich)
    e = enrich.Enricher(crm, apply=True)
    await enrich.add_event_showcase(e)
    assert not crm.rows["CEventPresenter"]
    assert any("no presenters" in n for n in e.did)
    assert not any(w[0] == "update" for w in crm.writes), "no switch without presenters"
    assert any(w[0] == "relate" for w in crm.writes), "links still seeded"


@pytest.mark.asyncio
async def test_stamp_management_teams_is_merge_only(monkeypatch):
    seed = _load("seed_training_data")
    crm = FakeCrm()
    partner_team = crm.add("Team", name="Partner Management Team")
    sponsor_team = crm.add("Team", name="Sponsor Management Team")
    other = crm.add("Team", name="Something Else")
    crm.add("CPartnerProfile", name="A", teamsIds=[other["id"]])
    crm.add("CPartnerProfile", name="B", teamsIds=[partner_team["id"]])
    crm.add("CSponsorProfile", name="F", teamsIds=[])

    s = seed.Seeder(crm, domain="sandbox.cbmentors.org", apply=True)
    await seed.stamp_management_teams(s)

    a = next(r for r in crm.rows["CPartnerProfile"].values() if r["name"] == "A")
    assert set(a["teamsIds"]) == {other["id"], partner_team["id"]}
    f = next(r for r in crm.rows["CSponsorProfile"].values() if r["name"] == "F")
    assert f["teamsIds"] == [sponsor_team["id"]]
    updates = [w for w in crm.writes if w[0] == "update"]
    assert len(updates) == 2, "B already carried the team and is untouched"
