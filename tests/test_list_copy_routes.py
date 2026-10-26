"""M7 stop B — the routes of a list's copy in Constant Contact and of the email
campaign that sends to it (build plan § 7e.9; ruling 95; Doug's two rulings at
the M7 plan, 10-26-26: an email campaign needs a list, and its build writes no
touches).

Through ``build()``, the real application over the campaign and list fakes,
with a fake mailing client in place of the vendor. Every refusal is checked for
its words.
"""

from __future__ import annotations

import pytest

from campaigns import config as cfg
from campaigns import list_sync
from tests.test_campaign_lists import _contact, run
from tests.test_campaigns import MARKETING, build
from tests.test_list_sync import CcStore, CodeCrm, ListMail, connection
from tests.test_mailing_sync import FakeStore, vendor

API = "/campaigns/api"


class EmailCrm(CodeCrm):
    """The code fakes plus the campaign's picked-email field (or not)."""

    def __init__(self, *, with_vendor_email: bool = True):
        super().__init__()
        self.with_vendor_email = with_vendor_email

    async def metadata(self, key: str):
        out = await super().metadata(key)
        if self.with_vendor_email and key == f"entityDefs.{cfg.CAMPAIGN}.fields":
            out = {**(out or {}), "vendorEmailId": {"type": "varchar"}}
        return out


@pytest.fixture
def world(monkeypatch):
    crm = EmailCrm()
    store = CcStore()
    mail = ListMail()
    conn = FakeStore(connection())
    for k, v in {"CAMPAIGN_LISTS": "true", "CAMPAIGN_LIST_SYNC": "true", "CAMPAIGNS_EMAIL": "true",
                 "MAILING_CLIENT_ID": "id", "MAILING_CLIENT_SECRET": "secret"}.items():
        monkeypatch.setenv(k, v)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=store)
    import campaigns.lists_router as lists_mod
    import campaigns.router as router_mod

    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    monkeypatch.setattr(lists_mod, "_api_client", lambda settings, request: crm)

    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(lists_mod, "record_action", _no_log)
    # The test application runs in dry-run; the copy's code refuses that, so
    # the refusal is lifted here and the vendor is the fake.
    monkeypatch.setattr(list_sync, "_refused", lambda settings: "")
    monkeypatch.setattr(list_sync, "mail_clients", lambda settings: (mail, conn))
    return {"client": client, "crm": crm, "store": store, "mail": mail}


def _static(w, name, contacts, *, copy=True):
    c = w["client"]
    lid = c.post(f"{API}/lists", json={"name": name, "kind": "static",
                                       "recipe": {"include": [], "exclude": []}}).json()["list"]["id"]
    if contacts:
        resp = c.post(f"{API}/lists/{lid}/add-people", json={"keys": [f"contact:{x['id']}" for x in contacts]})
        assert resp.status_code == 200, resp.text
    if copy:
        assert c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True}).status_code == 200
    return lid


def _people(w):
    return [_contact(w["crm"], "Ann Able"), _contact(w["crm"], "Bob Baker")]


# --- the list's copy ----------------------------------------------------------------------------

def test_the_tick_sync_now_and_the_status_line(world):
    c = world["client"]
    lid = _static(world, "Spring prospects", _people(world), copy=False)
    body = c.get(f"{API}/lists/{lid}").json()["list"]
    assert body["ccSync"] is False and body["ccStatus"] == "No copy kept."
    resp = c.post(f"{API}/lists/{lid}/sync-now")
    assert resp.status_code == 400 and "tick Keep a copy in Constant Contact first" in resp.json()["detail"]
    assert c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True}).json()["list"]["ccSync"] is True
    synced = c.post(f"{API}/lists/{lid}/sync-now").json()
    assert synced["summary"]["audience"] == 2 and synced["summary"]["added"] == 2
    assert synced["list"]["ccStatus"].startswith("2 on the copy")
    assert world["mail"].created == ["Spring prospects"]
    # Unticking keeps the copy, and says so.
    off = c.put(f"{API}/lists/{lid}/cc-copy", json={"on": False}).json()["list"]
    assert off["ccHasCopy"] is True and "kept as it was" in off["ccStatus"]


def test_the_session_says_whether_copies_are_on(world, monkeypatch):
    assert world["client"].get(f"{API}/session").json()["listSyncOn"] is True


def test_the_routes_are_404_while_the_switch_is_off(world, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_LIST_SYNC", "false")
    from core.config import get_settings
    get_settings.cache_clear()
    c = world["client"]
    lid = c.post(f"{API}/lists", json={"name": "X", "kind": "static",
                                       "recipe": {"include": [], "exclude": []}}).json()["list"]["id"]
    resp = c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True})
    assert resp.status_code == 404 and "Campaign list copies at /setup" in resp.json()["detail"]
    assert c.post(f"{API}/lists/{lid}/sync-now").status_code == 404


def test_a_copy_cannot_take_the_standing_lists_name_or_another_copys(world):
    c = world["client"]
    lid = _static(world, "Event Notices", [], copy=False)
    resp = c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True})
    assert resp.status_code == 400 and "standing mailing list" in resp.json()["detail"]
    a = _static(world, "Twins", [])
    b = _static(world, "twins", [], copy=False)
    resp = c.put(f"{API}/lists/{b}/cc-copy", json={"on": True})
    assert resp.status_code == 400 and "already keeps a copy under that name" in resp.json()["detail"]
    assert a


def test_a_retired_list_takes_no_tick(world):
    c = world["client"]
    lid = _static(world, "Old", [], copy=False)
    c.post(f"{API}/lists/{lid}/retire")
    resp = c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True})
    assert resp.status_code == 400 and "reactivate it first" in resp.json()["detail"]


def test_a_rename_renames_the_copy(world):
    c = world["client"]
    lid = _static(world, "Before", _people(world))
    c.post(f"{API}/lists/{lid}/sync-now")
    resp = c.put(f"{API}/lists/{lid}", json={"name": "After", "kind": "static",
                                            "recipe": {"include": [], "exclude": []}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["copyNote"] == "The copy in Constant Contact is renamed \"After\"."
    assert world["mail"].renamed == [("L1", "After")]


def test_a_failed_sync_is_said_in_words(world):
    from core.mailing import MailingError
    c = world["client"]
    lid = _static(world, "Spring", _people(world))

    async def refuse(name):
        raise MailingError("Mailing service POST /contact_lists failed: HTTP 403 forbidden")
    world["mail"].create_list = refuse
    resp = c.post(f"{API}/lists/{lid}/sync-now")
    assert resp.status_code == 400 and resp.json()["detail"].startswith("The copy could not be synced: ")
    assert "The last sync failed" in c.get(f"{API}/lists/{lid}").json()["list"]["ccStatus"]


# --- the email campaign -------------------------------------------------------------------------

def _campaign(w, status=cfg.STATUS_DRAFT):
    return w["crm"].add(cfg.CAMPAIGN, {"name": "Spring email", "campaignKind": cfg.KIND_EMAIL,
                                       "campaignStatus": status})


def _choose(w, camp, lid):
    resp = w["client"].put(f"{API}/campaigns/{camp['id']}/audience", json={"listId": lid})
    assert resp.status_code == 200, resp.text


def test_an_email_campaign_needs_a_list_and_its_build_writes_no_touch(world):
    c = world["client"]
    camp = _campaign(world)
    resp = c.post(f"{API}/campaigns/{camp['id']}/build", json={})
    assert resp.status_code == 400 and "Choose a list for this email campaign first" in resp.json()["detail"]
    _choose(world, camp, _static(world, "Spring prospects", _people(world)))
    built = c.post(f"{API}/campaigns/{camp['id']}/build", json={}).json()
    assert built["pieces"] == 2 and built["created"] == 0 and built["copy"] is True
    assert not [e for e, _p in world["crm"].created if e == cfg.TOUCH]
    assert world["crm"].rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == cfg.STATUS_AWAITING


def test_sign_off_refuses_a_list_without_its_copy_then_syncs_it(world):
    c = world["client"]
    camp = _campaign(world)
    lid = _static(world, "Spring prospects", _people(world), copy=False)
    _choose(world, camp, lid)
    c.post(f"{API}/campaigns/{camp['id']}/build", json={})
    resp = c.post(f"{API}/campaigns/{camp['id']}/signoff", json={"confirm": "2"})
    assert resp.status_code == 400 and "keeps no copy in Constant Contact" in resp.json()["detail"]
    c.put(f"{API}/lists/{lid}/cc-copy", json={"on": True})
    resp = c.post(f"{API}/campaigns/{camp['id']}/signoff", json={"confirm": "3"})
    assert resp.status_code == 400 and "Type the number of people, 2" in resp.json()["detail"]
    signed = c.post(f"{API}/campaigns/{camp['id']}/signoff", json={"confirm": "2"}).json()["campaign"]
    assert signed["campaignStatus"] == cfg.STATUS_SIGNED_OFF and signed["pieceCount"] == 2
    assert world["mail"].created == ["Spring prospects"]                    # the copy was synced
    detail = c.get(f"{API}/campaigns/{camp['id']}").json()["emailCopy"]
    assert detail["listName"] == "Spring prospects" and detail["copyOn"] and detail["pickedEmailId"] == ""


def test_pick_the_email_lists_what_went_to_the_copy_and_moves_the_campaign_on(world, monkeypatch):
    c = world["client"]
    camp = _campaign(world)
    lid = _static(world, "Spring prospects", _people(world))
    _choose(world, camp, lid)
    c.post(f"{API}/campaigns/{camp['id']}/build", json={})
    early = c.post(f"{API}/campaigns/{camp['id']}/pick-email", json={"emailId": "E1"})
    assert early.status_code == 400 and "after the campaign is signed off" in early.json()["detail"]
    c.post(f"{API}/campaigns/{camp['id']}/signoff", json={"confirm": "2"})
    seen = []

    async def sent(list_id, **kw):
        seen.append(list_id)
        return [{"id": "E1", "name": "Spring notice", "status": "Done", "sentAt": "2026-10-26T15:00:00Z"}]
    world["mail"].emails_sent_to_list = sent
    listed = c.get(f"{API}/campaigns/{camp['id']}/emails").json()
    assert listed["emails"][0]["name"] == "Spring notice" and seen == ["L1"]
    wrong = c.post(f"{API}/campaigns/{camp['id']}/pick-email", json={"emailId": "E9"})
    assert wrong.status_code == 400 and "was not sent to this campaign's list" in wrong.json()["detail"]
    picked = c.post(f"{API}/campaigns/{camp['id']}/pick-email", json={"emailId": "E1"}).json()
    row = world["crm"].rows[cfg.CAMPAIGN][camp["id"]]
    assert row["vendorEmailId"] == "E1" and row["campaignStatus"] == cfg.STATUS_RUNNING
    assert picked["email"]["name"] == "Spring notice"
    again = c.post(f"{API}/campaigns/{camp['id']}/pick-email", json={"emailId": "E1"})
    assert again.status_code == 400 and "already picked" in again.json()["detail"]


def test_mark_as_sent_is_refused_with_copies_on(world):
    camp = _campaign(world, cfg.STATUS_RUNNING)
    resp = world["client"].post(f"{API}/campaigns/{camp['id']}/mark-sent")
    assert resp.status_code == 400 and "Pick the email" in resp.json()["detail"]


def test_a_crm_without_the_picked_email_field_refuses_in_words(world):
    c = world["client"]
    world["crm"].with_vendor_email = False
    camp = _campaign(world)
    _choose(world, camp, _static(world, "Spring prospects", _people(world)))
    c.post(f"{API}/campaigns/{camp['id']}/build", json={})
    c.post(f"{API}/campaigns/{camp['id']}/signoff", json={"confirm": "2"})

    async def sent(list_id, **kw):
        return [{"id": "E1", "name": "Spring notice", "status": "Done", "sentAt": ""}]
    world["mail"].emails_sent_to_list = sent
    resp = c.post(f"{API}/campaigns/{camp['id']}/pick-email", json={"emailId": "E1"})
    assert resp.status_code == 400 and "no place for the picked email" in resp.json()["detail"]


def test_the_email_listing_finds_the_copy_through_the_campaigns_activity(monkeypatch):
    """The client's composition over the three inferred email endpoints."""
    from core.mailing import MailingClient

    calls = []

    class Api(MailingClient):
        async def _request(self, method, path, *, params=None, json_body=None):
            calls.append(path)
            if path == "/emails":
                return {"campaigns": [
                    {"campaign_id": "E1", "name": "Ours", "current_status": "Done", "updated_at": "u1"},
                    {"campaign_id": "E2", "name": "Other list", "current_status": "Done"},
                    {"campaign_id": "E3", "name": "Draft", "current_status": "Draft"}]}
            if path.startswith("/emails/activities/"):
                return {"contact_list_ids": ["L1"] if path.endswith("A1") else ["L7"]}
            cid = path.rsplit("/", 1)[1]
            return {"campaign_activities": [{"campaign_activity_id": "A" + cid[1:], "role": "primary_email"}]}

    async def tok(force):
        return "t"
    out = run(Api(tok).emails_sent_to_list("L1"))
    assert out == [{"id": "E1", "name": "Ours", "status": "Done", "sentAt": "u1"}]
    assert "/emails/E3" not in calls                                        # a draft is never opened
