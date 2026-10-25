"""The lead's page and the ladder's endpoints through the app (build plan
§ 7e.4): the page is served like the record page with the single-tab guard;
the counts answer ``ladder: false`` while the switch is off; Set level and
Assign refuse plainly on a CRM without the fields; an inline edit writes as the
user and runs placement; the lead's answer carries the Activity timeline.
"""

from __future__ import annotations

from campaigns import config as cfg
from tests.test_campaigns import MARKETING, FakeCrm, FakeStore, build


def _lead(crm, **row):
    return crm.add(cfg.PROSPECT, {"name": row.get("businessName") or "Acme", "leadStatus": cfg.LEAD_QUALIFIED,
                                  "createdAt": "2026-10-01 10:00:00", **row})


def test_the_lead_page_is_served_with_the_campaigns_base(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm(), store=FakeStore())
    resp = client.get("/campaigns/lead/abc123")
    assert resp.status_code == 200
    assert '<base href="/campaigns/">' in resp.text and 'id="leadPanel"' in resp.text
    assert resp.headers.get("cache-control") == "no-store"
    assert "This record is open in another tab" in resp.text


def test_counts_answer_off_while_the_switch_is_off(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm(), store=FakeStore())
    assert client.get("/campaigns/api/prospects/counts").json() == {"ladder": False}
    assert client.get("/campaigns/api/session").json()["ladderOn"] is False


def test_set_level_and_assign_refuse_plainly_without_the_fields(monkeypatch):
    monkeypatch.setenv("LEAD_LADDER", "true")
    crm = FakeCrm()
    lead = _lead(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    assert client.get("/campaigns/api/session").json()["ladderOn"] is True
    resp = client.put(f"/campaigns/api/prospects/{lead['id']}/level", json={"level": "Identified"})
    assert resp.status_code == 409 and "does not carry the ladder" in resp.json()["detail"]
    resp = client.put(f"/campaigns/api/prospects/{lead['id']}/assignee", json={"userId": "u-1"})
    assert resp.status_code == 409 and "Assigned to field" in resp.json()["detail"]
    off = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore(), enabled="true")
    monkeypatch.setenv("LEAD_LADDER", "false")
    from core.config import get_settings
    get_settings.cache_clear()
    assert off.put(f"/campaigns/api/prospects/{lead['id']}/level", json={"level": "Identified"}).status_code == 404


def test_the_lead_answer_carries_the_timeline_and_an_inline_edit_writes_as_the_user(monkeypatch):
    crm = FakeCrm()
    lead = _lead(crm, businessName="Acme", website="")
    crm.add(cfg.TOUCH, {"name": "card", "channel": "Postcard", "touchStatus": "Sent", "sentAt": "2026-10-02 10:00:00",
                        "prospectId": lead["id"], "outreachCampaignName": "September cards"})
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    body = client.get(f"/campaigns/api/prospects/{lead['id']}").json()
    assert body["prospect"]["id"] == lead["id"] and body["ladder"] is False
    assert [r["title"] for r in body["activity"]] == ["Postcard sent"]
    assert body["levels"] == list(cfg.LEVELS)
    resp = client.patch(f"/campaigns/api/prospects/{lead['id']}/facts", json={"changes": {"website": "acme.com", "phone": "216 555 0100"}})
    assert resp.status_code == 200
    assert sorted(resp.json()["written"]) == ["phone", "website"]
    assert crm.rows[cfg.PROSPECT][lead["id"]]["website"] == "https://acme.com"
    bad = client.patch(f"/campaigns/api/prospects/{lead['id']}/facts", json={"changes": {"leadStatus": "Converted"}})
    assert bad.status_code == 400 and "not a field" in bad.json()["detail"]
    same = client.patch(f"/campaigns/api/prospects/{lead['id']}/facts", json={"changes": {"website": "acme.com"}})
    assert same.status_code == 400 and "Nothing changed" in same.json()["detail"]
    assert client.get("/campaigns/api/prospects/missing").status_code == 404


def test_convert_from_the_page_needs_an_email_or_a_website(monkeypatch):
    crm = FakeCrm()
    bare = _lead(crm, businessName="Nothing Known")
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    resp = client.post(f"/campaigns/api/prospects/{bare['id']}/convert")
    assert resp.status_code == 400 and "converts from an email" in resp.json()["detail"]
    done = _lead(crm, businessName="Done", leadStatus=cfg.LEAD_CONVERTED, email="a@b.com")
    assert "already Converted" in client.post(f"/campaigns/api/prospects/{done['id']}/convert").json()["detail"]
