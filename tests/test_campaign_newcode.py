"""*New code* (prospect marketing build plan § 7d.1; ruling 126 puts it in
M2): a fresh personal-link code on the lead and its converted Contact, or on
the Contact and the lead it came from; the old code stops resolving; the
action log gets the old code's last four characters only; the two buttons'
endpoints refuse plainly on a CRM without the fields and to the wrong team.
"""

from __future__ import annotations

import asyncio

import pytest

from campaigns import config as cfg
from campaigns import leadcode
from tests.test_campaigns import MARKETING, FakeCrm, FakeStore, build


def run(coro):
    return asyncio.run(coro)


class CodeCrm:
    def __init__(self):
        self.rows = {cfg.PROSPECT: {}, cfg.CONTACT: {}}
        self.updates = []

    async def metadata(self, key):
        if key == f"entityDefs.{cfg.PROSPECT}.fields":
            return {leadcode.LEAD_FIELD: {"type": "varchar"}}
        if key == f"entityDefs.{cfg.CONTACT}.fields":
            return {leadcode.CONTACT_FIELD: {"type": "varchar"}}
        return {}

    async def get(self, entity, record_id, select=""):
        return dict(self.rows[entity].get(record_id) or {})

    async def find_one(self, entity, attribute, value, select="id"):
        return next((dict(r) for r in self.rows[entity].values() if r.get(attribute) == value), None)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.rows[entity][record_id].update(payload)
        return dict(self.rows[entity][record_id])


def test_replace_for_lead_mints_a_fresh_code_on_the_lead_and_its_contact():
    crm = CodeCrm()
    crm.rows[cfg.PROSPECT]["l1"] = {"id": "l1", "leadCode": "abcd1234efgh", "promotedContactId": "c1"}
    crm.rows[cfg.CONTACT]["c1"] = {"id": "c1", "cLeadCode": "abcd1234efgh"}
    old, new = run(leadcode.replace_for_lead(crm, "l1"))
    assert old == "abcd1234efgh" and new != old and leadcode.looks_like_code(new)
    assert crm.rows[cfg.PROSPECT]["l1"]["leadCode"] == new and crm.rows[cfg.CONTACT]["c1"]["cLeadCode"] == new
    # A lead with no code yet is simply given one.
    crm.rows[cfg.PROSPECT]["l2"] = {"id": "l2"}
    old2, new2 = run(leadcode.replace_for_lead(crm, "l2"))
    assert old2 is None and leadcode.looks_like_code(new2) and new2 != new


def test_replace_for_contact_reaches_the_lead_it_came_from():
    crm = CodeCrm()
    crm.rows[cfg.CONTACT]["c1"] = {"id": "c1", "cLeadCode": "zzzz9999yyyy"}
    crm.rows[cfg.PROSPECT]["l1"] = {"id": "l1", "leadCode": "zzzz9999yyyy", "promotedContactId": "c1"}
    old, new = run(leadcode.replace_for_contact(crm, "c1"))
    assert old == "zzzz9999yyyy" and crm.rows[cfg.PROSPECT]["l1"]["leadCode"] == new
    assert leadcode.code_tail(old) == "…yyyy" and leadcode.code_tail(None) == "(none)"


def test_replace_refuses_a_crm_without_the_fields():
    class Bare(CodeCrm):
        async def metadata(self, key):
            return {}
    with pytest.raises(RuntimeError, match="lead code fields"):
        run(leadcode.replace_for_lead(Bare(), "l1"))


def test_the_lead_page_endpoint_refuses_plainly_without_the_fields(monkeypatch):
    crm = FakeCrm()
    lead = crm.add(cfg.PROSPECT, {"name": "Acme", "leadStatus": cfg.LEAD_QUALIFIED})
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    resp = client.post(f"/campaigns/api/prospects/{lead['id']}/code")
    assert resp.status_code == 409 and "lead code fields" in resp.json()["detail"]
    assert client.post("/campaigns/api/prospects/missing/code").status_code == 404


def test_the_contact_page_endpoint_is_for_marketing_team_members(monkeypatch):
    from starlette.testclient import TestClient

    from tests.test_directory import _app, _login

    monkeypatch.setenv("WORKSPACE_ALLOWED_TEAMS", "Workspace")
    _login(monkeypatch, teams=["Workspace"])          # a workspace member who is not marketing
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "x", "password": "y"})
        resp = c.post("/directory/contacts/api/records/c1/leadcode")
        assert resp.status_code == 403 and "Marketing Management" in resp.json()["detail"]
        # A company has no code: the route exists on the contacts kind alone.
        assert c.post("/directory/companies/api/records/a1/leadcode").status_code in (404, 405)
