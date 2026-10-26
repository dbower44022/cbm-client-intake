"""M7 stop A — a list's kept-current copy in Constant Contact and the lead code
in the vendor (build plan § 7e.9, § 7d.2; rulings 95, 126).

No CRM and no vendor: the campaign-list fakes behind a fake mailing client that
holds lists, members, unsubscribes and custom fields. What is protected: the
standing list is unchanged by the parameters; a list's copy holds exactly the
people the email channel reaches (consent, address, a member at cbmEmail); an
unsubscribe is never re-added; the copy is found by id, then by name (the
sandbox reset loses the id, never the copy) and renamed when the list was; a
retired or unticked list is skipped and its copy kept; the custom field is
created once and checked every pass; a contact without a code gets one, under
the org-wide key, and it rides the import's ``cf:`` column.
"""

from __future__ import annotations

import asyncio

import pytest

from campaigns import config as cfg
from campaigns import list_sync
from campaigns.audience_store import STATE_IN
from core import mailing_sync as sync
from core.config import Settings
from core.mailing import Connection, STATUS_CONNECTED
from tests.test_campaign_lists import FakeListStore, ListCrm, _contact
from tests.test_mailing_sync import FakeMail, FakeStore, _NOW, vendor

from datetime import timedelta

SETTINGS = Settings(campaign_lists=True, campaign_list_sync=True, mailing_client_id="id",
                    mailing_client_secret="secret", espo_dry_run=False, mailing_list_name="Event notices")


def run(coro):
    return asyncio.run(coro)


# --- fakes --------------------------------------------------------------------------------

class CodeCrm(ListCrm):
    """The list fakes plus the two lead-code fields (or not)."""

    def __init__(self, *, with_codes: bool = True):
        super().__init__()
        self.with_codes = with_codes

    async def metadata(self, key: str):
        out = await super().metadata(key)
        if self.with_codes and key == "entityDefs.Contact.fields":
            out = {**out, "cLeadCode": {"type": "varchar"}}
        if self.with_codes and key == f"entityDefs.{cfg.PROSPECT}.fields":
            out = {**(out or {}), "leadCode": {"type": "varchar"}}
        return out


class ListMail(FakeMail):
    """FakeMail with several lists (members per list), rename and custom fields."""

    def __init__(self, *, lists=(), members=None, fields=(), **kw):
        super().__init__(lists=lists, **kw)
        self.members_by_list = {k: list(v) for k, v in (members or {}).items()}
        self.fields = list(fields)
        self.fields_created = []
        self.renamed = []
        self._n = 0

    async def lists(self):
        return list(self._lists)

    async def find_list_by_id(self, list_id):
        return next((l for l in self._lists if l["list_id"] == list_id), None)

    async def create_list(self, name):
        self._n += 1
        row = {"list_id": f"L{self._n}", "name": name}
        self._lists.append(row)
        self.created.append(name)
        return row

    async def rename_list(self, list_id, name):
        self.renamed.append((list_id, name))
        for l in self._lists:
            if l["list_id"] == list_id:
                l["name"] = name
        return {}

    async def contacts(self, *, list_id=None, status=None, updated_after=None, include=()):
        if list_id:
            for r in self.members_by_list.get(list_id, []):
                yield r
            return
        async for r in super().contacts(status=status, updated_after=updated_after):
            yield r

    async def find_custom_field(self, name):
        return next((f for f in self.fields if f["name"] == name or f["label"] == name), None)

    async def create_custom_field(self, label):
        row = {"custom_field_id": "cf1", "label": label, "name": label, "type": "string"}
        self.fields.append(row)
        self.fields_created.append(label)
        return row


class CcStore(FakeListStore):
    """FakeListStore plus the copy columns."""

    async def create_list(self, **kw):
        row = await super().create_list(**kw)
        self.lists[row["id"]].update(cc_sync=False, cc_list_id=None, cc_last_sync_at=None, cc_last_sync=None)
        return {**row, **self.lists[row["id"]]}

    async def set_cc_sync(self, list_id, on, actor):
        self.lists[list_id]["cc_sync"] = bool(on)
        return dict(self.lists[list_id])

    async def set_cc_list_id(self, list_id, cc_list_id):
        self.lists[list_id]["cc_list_id"] = cc_list_id

    async def record_cc_sync(self, list_id, summary):
        self.lists[list_id].update(cc_last_sync_at=_NOW, cc_last_sync=summary)

    async def cc_sync_lists(self):
        return [dict(r) for r in self.lists.values() if r.get("cc_sync") and r["status"] == "active"]


def connection():
    return Connection(status=STATUS_CONNECTED, account_label="Test Org", connected_by="adm",
                      connected_at=_NOW - timedelta(days=1), expires_at=_NOW + timedelta(hours=20),
                      last_refresh_at=None, last_error=None, scopes=(), list_id=None, pull_cursor=None,
                      last_push_at=None, last_push_summary=None)


def static_list(store, name, keys, *, cc=True):
    row = run(store.create_list(name=name, notes="", kind="static",
                                recipe={"include": [], "exclude": []}, actor="mark"))
    run(store.hand_add_many(row["id"], keys, "mark"))
    run(store.set_cc_sync(row["id"], cc, "mark"))
    return run(store.get_list(row["id"]))


def world(*, with_codes=True, **mail_kw):
    crm = CodeCrm(with_codes=with_codes)
    ann = _contact(crm, "Ann Able", cLeadCode="ANNCODE23456")
    bob = _contact(crm, "Bob Baker")
    cy = _contact(crm, "Cy Cole", cMarketingOptIn=False)
    dee = _contact(crm, "Dee Dunn")
    return crm, {"ann": ann, "bob": bob, "cy": cy, "dee": dee}, ListMail(**mail_kw), CcStore(), FakeStore(connection())


# --- the standing list is unchanged -------------------------------------------------------------

def test_the_standing_plan_is_the_same_without_the_new_parameters():
    crm, people, mail, _store, conn = world()
    plan = run(sync.build_plan(crm, mail, "Event notices"))
    assert plan.list_id is None and plan.code_key is None and plan.refresh == []
    assert {p.email for p in plan.add} == {"ann@x.org", "bob@x.org", "dee@x.org"}
    assert all("cf:" not in "".join(p.import_row()) for p in plan.add)


# --- a list's copy ----------------------------------------------------------------------------

def test_a_list_copy_holds_the_people_email_reaches_and_is_created_once():
    crm, p, mail, store, conn = world()
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}", f"contact:{p['bob']['id']}",
                                                  f"contact:{p['cy']['id']}"])
    result = run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store))
    assert result.ok, result.error
    assert mail.created == ["Spring prospects"]
    (list_id, rows), = mail.imports
    assert {r["email"] for r in rows} == {"ann@x.org", "bob@x.org"}      # Cy has no consent
    saved = run(store.get_list(row["id"]))
    assert saved["cc_list_id"] == list_id
    assert saved["cc_last_sync"]["ok"] and saved["cc_last_sync"]["skipped"] == 1
    # The next sync finds the copy by its id and creates nothing.
    run(list_sync.sync_list(SETTINGS, saved, crm=crm, mail=mail, store=store))
    assert mail.created == ["Spring prospects"]


def test_after_the_reset_the_copy_is_found_by_name_not_made_twice():
    crm, p, _m, store, conn = world()
    mail = ListMail(lists=[{"list_id": "L-old", "name": "Spring prospects"}])
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}"])
    assert row["cc_list_id"] is None                                    # the reset emptied it
    assert run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store)).ok
    assert mail.created == [] and run(store.get_list(row["id"]))["cc_list_id"] == "L-old"


def test_a_renamed_list_renames_its_copy():
    crm, p, _m, store, conn = world()
    mail = ListMail(lists=[{"list_id": "L9", "name": "Old name"}])
    row = static_list(store, "New name", [f"contact:{p['ann']['id']}"])
    run(store.set_cc_list_id(row["id"], "L9"))
    result = run(list_sync.sync_list(SETTINGS, run(store.get_list(row["id"])), crm=crm, mail=mail, store=store))
    assert result.ok and mail.renamed == [("L9", "New name")] and mail.created == []
    assert run(store.get_list(row["id"]))["cc_last_sync"]["renamedFrom"] == "Old name"


def test_an_unsubscribe_is_never_re_added_to_a_list_copy():
    crm, p, _m, store, conn = world()
    mail = ListMail(unsubscribed=[vendor("v1", "bob@x.org", "unsubscribed")])
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}", f"contact:{p['bob']['id']}"])
    run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store))
    (_lid, rows), = mail.imports
    assert [r["email"] for r in rows] == ["ann@x.org"]
    assert run(store.get_list(row["id"]))["cc_last_sync"]["withheld"] == 1


def test_a_person_taken_off_the_list_leaves_the_copy_but_stays_in_the_account():
    crm, p, _m, store, conn = world()
    mail = ListMail(lists=[{"list_id": "L1", "name": "Spring prospects"}],
                    members={"L1": [vendor("v1", "ann@x.org"), vendor("v2", "dee@x.org")]})
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}"])
    run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store))
    assert mail.removals == [("L1", ["v2"])]


def test_a_retired_or_unticked_list_is_skipped_and_its_copy_kept():
    crm, p, mail, store, conn = world()
    on = static_list(store, "Kept on", [f"contact:{p['ann']['id']}"])
    off = static_list(store, "Ticked off", [f"contact:{p['bob']['id']}"], cc=False)
    gone = static_list(store, "Retired", [f"contact:{p['dee']['id']}"])
    run(store.set_list_status(gone["id"], "retired", "mark"))
    passed = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    assert [r["name"] for r, _ in passed.lists] == ["Kept on"]
    assert "Ticked off" not in mail.created and "Retired" not in mail.created
    refused = run(list_sync.sync_list(SETTINGS, run(store.get_list(gone["id"])), crm=crm, mail=mail, store=store))
    assert not refused.ok and "retired" in refused.error and "kept" in refused.error


def test_a_list_named_like_the_standing_list_is_refused():
    crm, p, mail, store, conn = world()
    row = static_list(store, "event notices", [f"contact:{p['ann']['id']}"])
    result = run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store))
    assert not result.ok and "standing mailing list" in result.error and mail.created == []


def test_one_failing_list_records_its_error_in_words_and_never_stops_the_others():
    crm, p, mail, store, conn = world()
    bad = static_list(store, "A bad one", [f"contact:{p['ann']['id']}"])
    good = static_list(store, "B good one", [f"contact:{p['bob']['id']}"])
    real = mail.create_list

    async def refuse(name):
        if name == "A bad one":
            from core.mailing import MailingError
            raise MailingError("Mailing service POST /contact_lists failed: HTTP 409 duplicate")
        return await real(name)

    mail.create_list = refuse
    passed = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    results = {r["name"]: res for r, res in passed.lists}
    assert not results["A bad one"].ok and results["B good one"].ok
    assert "HTTP 409" in run(store.get_list(bad["id"]))["cc_last_sync"]["error"]
    assert "The last sync failed" in list_sync.status_words(run(store.get_list(bad["id"])))
    keys = [k for k, _t, _c in sync.alerts_for(results["A bad one"], kind=f"list_{bad['id']}",
                                                settings=SETTINGS, label="The copy")]
    assert keys == [f"mailing_list_{bad['id']}_failed"]
    assert good


def test_the_unsubscribes_are_read_once_per_pass():
    crm, p, mail, store, conn = world()
    static_list(store, "One", [f"contact:{p['ann']['id']}"])
    static_list(store, "Two", [f"contact:{p['bob']['id']}"])
    run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    reads = [c for c in mail.contacts_calls if c["status"] == "unsubscribed"]
    assert len(reads) == 1


# --- the lead code ----------------------------------------------------------------------------

def test_the_custom_field_is_created_once_and_checked_every_pass():
    crm, p, mail, store, conn = world()
    first = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    assert mail.fields_created == ["cbm_lead_code"] and first.field_state == "created"
    second = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    assert mail.fields_created == ["cbm_lead_code"] and second.field_state == "present"
    assert conn.pushes[-1]["customField"] == "present"


def test_a_deleted_custom_field_is_made_again_and_says_so():
    crm, p, mail, store, conn = world()
    run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    conn.conn = dataclass_replace(conn.conn, last_push_summary=conn.pushes[-1])
    mail.fields.clear()                                                  # an administrator deleted it
    again = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    assert again.field_state == "recreated"


def dataclass_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)


def test_every_push_writes_the_code_and_mints_one_for_a_contact_without():
    crm, p, mail, store, conn = world()
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}", f"contact:{p['bob']['id']}"])
    run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store, field_name="cbm_lead_code"))
    (_lid, rows), = mail.imports
    by = {r["email"]: r for r in rows}
    assert by["ann@x.org"]["cf:cbm_lead_code"] == "ANNCODE23456"
    minted = crm.rows["Contact"][p["bob"]["id"]]["cLeadCode"]
    assert minted and by["bob@x.org"]["cf:cbm_lead_code"] == minted
    assert run(store.get_list(row["id"]))["cc_last_sync"]["codes"] == {"withCode": 1, "minted": 1, "withoutCode": 0}


def test_people_already_on_the_copy_are_imported_again_for_their_code():
    crm, p, _m, store, conn = world()
    mail = ListMail(lists=[{"list_id": "L1", "name": "Spring prospects"}],
                    members={"L1": [vendor("v1", "ann@x.org")]})
    row = static_list(store, "Spring prospects", [f"contact:{p['ann']['id']}"])
    run(list_sync.sync_list(SETTINGS, row, crm=crm, mail=mail, store=store, field_name="cbm_lead_code"))
    (_lid, rows), = mail.imports
    assert rows == [{"email": "ann@x.org", "first_name": "Ann", "last_name": "Able",
                     "cf:cbm_lead_code": "ANNCODE23456"}]
    assert run(store.get_list(row["id"]))["cc_last_sync"]["added"] == 0


def test_the_standing_push_writes_codes_in_the_pass():
    crm, p, mail, store, conn = world()
    passed = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    (_lid, rows), = mail.imports
    assert all(r.get("cf:cbm_lead_code") for r in rows)
    assert passed.standing.summary["codes"]["minted"] == 2                 # Bob and Dee


def test_minting_is_capped_per_pass():
    crm, p, mail, store, conn = world()
    people = run(sync.audience(crm))
    out, counts = run(list_sync.give_codes(crm, people, limit=1))
    assert counts == {"withCode": 1, "minted": 1, "withoutCode": 1}


def test_a_crm_without_the_code_fields_writes_no_code_and_no_field():
    crm, p, mail, store, conn = world(with_codes=False)
    passed = run(list_sync.run_pass(SETTINGS, crm=crm, mail=mail, conn_store=conn, campaign_store=store))
    assert mail.fields_created == [] and passed.standing.ok
    (_lid, rows), = mail.imports
    assert not any(k.startswith("cf:") for r in rows for k in r)


def test_the_paste_address_carries_the_merge_tag():
    assert list_sync.paste_address("https://apps.example.org/", "ab12") == \
        "https://apps.example.org/c/ab12/[[custom.cbm_lead_code]]"


def test_status_words():
    assert list_sync.status_words({"cc_sync": False}) == "No copy kept."
    assert "kept as it was" in list_sync.status_words({"cc_sync": False, "cc_list_id": "L1"})
    assert "not synced yet" in list_sync.status_words({"cc_sync": True})
    assert list_sync.status_words({"cc_sync": True, "cc_last_sync": {"ok": True, "audience": 3, "added": 2,
                                                                     "removed": 0, "withheld": 1}}) == \
        "3 on the copy — 2 added, 0 removed, 1 withheld as unsubscribed."


def test_readiness_names_the_custom_field_state():
    from setup.readiness import _code_field_check

    assert _code_field_check({})["ok"] is None
    assert _code_field_check({"customField": "present"})["ok"] is True
    missing = _code_field_check({"customField": "missing: HTTP 403"})
    assert missing["ok"] is False and missing["detail"] == "custom field missing: HTTP 403"
    assert "made it again" in _code_field_check({"customField": "recreated"})["detail"]
