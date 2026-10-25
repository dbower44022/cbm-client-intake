"""Review as the research queue — the contacts mode through the app (build
plan § 7e.6; rulings 110, 121).

What these prove: the contacts write goes through the lead page's
normalisation and is written as the user; the guard refuses a lead someone
else moved, naming who and the level; ``stays`` is true while the lead is
still Identified and ``needs`` says what is missing; the findings the row was
filled from are closed Accepted under the org-wide key without their values
being rewritten; one action-log row is recorded; the suggestions answer maps
the lead's Proposed findings onto the boxes and says whether research is
still running; a CRM without the ladder refuses the contacts queue plainly.
"""

from __future__ import annotations

from typing import Any

from campaigns import config as cfg
from campaigns import ladder
from core.config import get_settings
from tests.test_campaigns import MARKETING, FakeCrm, FakeStore, build

FINDING = "CEnrichmentFinding"


class LadderCrm(FakeCrm):
    """The campaigns fake with the ladder's fields and links, and the
    Enrichment Finding record type, so placement and findings run."""

    def __init__(self, *, ladder_fields: bool = True, findings: bool = True):
        super().__init__()
        self.ladder_fields, self.findings = ladder_fields, findings

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.PROSPECT}.fields" and self.ladder_fields:
            base = await super().metadata(key)
            return {**base, **{f: {} for f in ladder.FIELDS}}
        if key == f"entityDefs.{cfg.PROSPECT}.links":
            return {l: {} for l in ladder.LINKS} if self.ladder_fields else {}
        if key == f"entityDefs.{FINDING}.links":
            return {"prospect": {}, "company": {}} if self.findings else None
        return await super().metadata(key)

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        out = await super().list(entity, where=where, select=select, max_size=max_size, offset=offset)
        if order_by:
            out["list"] = sorted(out["list"], key=lambda r: str(r.get(order_by) or ""), reverse=order == "desc")
        return out


class PendingStore:
    def __init__(self, pending: int = 0):
        self.pending = pending

    async def target_pending(self, target_id: str) -> int:
        return self.pending


def _identified(crm, **row):
    return crm.add(cfg.PROSPECT, {"name": row.get("businessName") or "Marigold Pet Grooming",
                                  "businessName": "Marigold Pet Grooming", "leadStatus": cfg.LEAD_QUALIFIED,
                                  "qualificationLevel": cfg.LEVEL_IDENTIFIED, "firstName": "", "lastName": "",
                                  "phone": "", "email": "", "createdAt": "2026-10-01 10:00:00",
                                  "modifiedByName": "Pat", "modifiedAt": "2026-10-25 11:00:00", **row})


def _app(monkeypatch, crm, *, store=None, pending=None):
    monkeypatch.setenv("LEAD_LADDER", "true")
    client = build(monkeypatch, user=MARKETING, crm=crm, store=store or FakeStore())
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_system_client", lambda settings: crm)
    logged: list[dict[str, Any]] = []

    async def _log(user_client, **kw):
        logged.append(kw)
    monkeypatch.setattr(router_mod, "record_action", _log)
    client.app.state.enrichment_store = pending
    return client, logged


SEEN = {"seenStatus": "Qualified", "seenExit": "", "seenLevel": "Identified"}


def test_the_contacts_queue_lists_identified_leads_and_refuses_without_the_ladder(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm)
    crm.add(cfg.PROSPECT, {"name": "Unq", "leadStatus": cfg.LEAD_UNQUALIFIED, "createdAt": "2026-10-02 10:00:00"})
    client, _ = _app(monkeypatch, crm)
    res = client.get("/campaigns/api/prospects?review=1&mode=contacts").json()
    assert [p["id"] for p in res["prospects"]] == [lead["id"]] and res["ladder"] is True
    assert client.get("/campaigns/api/prospects?review=1&mode=hot").status_code == 400
    bare, _ = _app(monkeypatch, LadderCrm(ladder_fields=False))
    resp = bare.get("/campaigns/api/prospects?review=1&mode=contacts")
    assert resp.status_code == 400 and "Find contacts queue is not available" in resp.json()["detail"]
    resolve = bare.post("/campaigns/api/prospects/bulk/resolve", json={"query": {"mode": "contacts"}, "review": True})
    assert resolve.status_code == 400 and "not available" in resolve.json()["detail"]


def test_the_contacts_write_is_normalised_placed_and_logged(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm)
    client, logged = _app(monkeypatch, crm)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts",
                       json={"firstName": " Dana ", "lastName": "Okoro", "email": "Dana@Marigold.example", **SEEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["written"] == ["email", "firstName", "lastName"]
    assert body["level"] == cfg.LEVEL_CONTACTABLE and body["stays"] is False and body["needs"] == ""
    row = crm.rows[cfg.PROSPECT][lead["id"]]
    assert (row["firstName"], row["lastName"], row["email"]) == ("Dana", "Okoro", "Dana@Marigold.example")
    assert row["qualificationLevel"] == cfg.LEVEL_CONTACTABLE
    # One action-log row, the contacts action, naming the fields and the level.
    assert [l["action"] for l in logged] == ["Lead Contact Found"]
    assert "email, firstName, lastName" in logged[0]["summary"] and "level Contactable" in logged[0]["summary"]
    assert logged[0]["details"]["written"]["firstName"] == "Dana"
    # An email that is not one is refused in words, nothing written.
    bad = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={"email": "not-an-email", **SEEN, "seenLevel": "Contactable"})
    assert bad.status_code == 400 and "not an email address" in bad.json()["detail"]
    # Nothing typed and no findings: refused in words.
    empty = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={**SEEN, "seenLevel": "Contactable"})
    assert empty.status_code == 400 and "nothing new to save" in empty.json()["detail"]


def test_a_name_alone_stays_in_the_queue_and_says_what_is_still_needed(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm)
    client, _ = _app(monkeypatch, crm)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={"lastName": "Okoro", **SEEN})
    body = resp.json()
    assert resp.status_code == 200 and body["stays"] is True and body["level"] == cfg.LEVEL_IDENTIFIED
    assert body["needs"] == "a phone or an email"
    assert crm.rows[cfg.PROSPECT][lead["id"]]["qualificationLevel"] == cfg.LEVEL_IDENTIFIED
    phone_only = _identified(crm, businessName="Northcoast Drone Services")
    body2 = client.post(f"/campaigns/api/prospects/{phone_only['id']}/contacts", json={"phone": "216 555 0100", **SEEN}).json()
    assert body2["stays"] is True and body2["needs"] == "the person's name"


def test_the_guard_refuses_a_lead_someone_else_moved(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm, qualificationLevel=cfg.LEVEL_CONTACTABLE, firstName="Dana", email="d@m.example")
    client, logged = _app(monkeypatch, crm)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={"phone": "216 555 0100", **SEEN})
    assert resp.status_code == 409 and resp.json()["detail"] == "Already Contactable, by Pat at 2026-10-25 11:00 UTC."
    assert crm.updated == [] and logged == []
    stopped = _identified(crm, sideExit="Stale")
    resp = client.post(f"/campaigns/api/prospects/{stopped['id']}/contacts", json={"phone": "216 555 0100", "seenStatus": "Qualified", "seenLevel": "Identified"})
    assert resp.status_code == 400 and "stopped (Stale)" in resp.json()["detail"]
    assert client.post("/campaigns/api/prospects/nope/contacts", json={"phone": "1", **SEEN}).status_code == 404


def test_enter_on_filled_suggestions_writes_the_values_and_closes_the_findings(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm)
    # Real finding ids are alphanumeric (the fake's hyphenated ones would be refused as not ids).
    person = crm.add(FINDING, {"id": "fnd001personDana", "prospectId": lead["id"], "kind": "Person", "personName": "Dana Okoro",
                               "personEmail": "dana@marigold.example", "findingStatus": "Proposed", "createdAt": "2026-10-25 10:00:00"})
    phone = crm.add(FINDING, {"id": "fnd002phone", "prospectId": lead["id"], "kind": "Field value", "targetField": "phone",
                              "proposedValue": "216 555 0100", "findingStatus": "Proposed", "createdAt": "2026-10-25 10:01:00"})
    decided = crm.add(FINDING, {"id": "fnd003decided", "prospectId": lead["id"], "kind": "Field value", "targetField": "email",
                                "proposedValue": "old@x.example", "findingStatus": "Rejected", "decidedBy": "Pat"})
    client, logged = _app(monkeypatch, crm, pending=PendingStore(0))
    sug = client.get(f"/campaigns/api/prospects/{lead['id']}/suggestions").json()
    assert sug["available"] is True and sug["researching"] is False
    assert (sug["firstName"], sug["lastName"], sug["email"], sug["phone"], sug["website"]) == ("Dana", "Okoro", "dana@marigold.example", "216 555 0100", "")
    assert sorted(sug["findingIds"]) == sorted([person["id"], phone["id"]])
    # The reviewer corrects the phone before Enter: the typed value wins, the
    # findings close Accepted all the same, their values never rewritten.
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={
        "firstName": sug["firstName"], "lastName": sug["lastName"], "email": sug["email"], "phone": "216 555 0199",
        "findingIds": sug["findingIds"] + [decided["id"]], **SEEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stays"] is False and body["level"] == cfg.LEVEL_CONTACTABLE
    assert [c["id"] for c in body["findings"]["closed"]] == sug["findingIds"]
    assert body["findings"]["skipped"] == [{"id": decided["id"], "why": "Already rejected by Pat."}]
    assert crm.rows[cfg.PROSPECT][lead["id"]]["phone"] == "216 555 0199"
    assert crm.rows[FINDING][person["id"]]["findingStatus"] == "Accepted" and crm.rows[FINDING][person["id"]]["decidedBy"] == "Mark Marketing"
    assert crm.rows[FINDING][phone["id"]]["findingStatus"] == "Accepted"
    assert "2 AI finding(s) accepted" in logged[0]["summary"]
    # Findings alone (every value already held) still close, nothing written.
    again = crm.add(FINDING, {"id": "fnd004again", "prospectId": lead["id"], "kind": "Person", "personName": "Dana Okoro", "findingStatus": "Proposed"})
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/contacts", json={
        "firstName": "Dana", "lastName": "Okoro", "findingIds": [again["id"]], **SEEN, "seenLevel": "Contactable"})
    assert resp.status_code == 200 and resp.json()["written"] == [] and crm.rows[FINDING][again["id"]]["findingStatus"] == "Accepted"


def test_suggestions_say_when_research_is_running_or_the_crm_lacks_findings(monkeypatch):
    crm = LadderCrm()
    lead = _identified(crm)
    client, _ = _app(monkeypatch, crm, pending=PendingStore(1))
    sug = client.get(f"/campaigns/api/prospects/{lead['id']}/suggestions").json()
    assert sug["researching"] is True and sug["findingIds"] == [] and sug["available"] is True
    assert client.get("/campaigns/api/prospects/nope/suggestions").status_code == 404
    bare = LadderCrm(findings=False)
    lead2 = _identified(bare)
    client2, _ = _app(monkeypatch, bare)
    sug2 = client2.get(f"/campaigns/api/prospects/{lead2['id']}/suggestions").json()
    assert sug2["available"] is False and sug2["researching"] is False and sug2["email"] == ""
    get_settings.cache_clear()
