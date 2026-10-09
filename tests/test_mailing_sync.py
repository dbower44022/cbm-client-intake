"""Phase C piece 3 — the audience push and the unsubscribe pull.

No CRM and no vendor: a fake CRM that pages at the real limit and a fake
mailing client that records what it was asked to do. What is protected: the
audience rule (three booleans, primary address), the one-way opt-out (a vendor
unsubscribe is never re-added; the pull never clears a CRM opt-out), remove
means remove-from-list, the plan text being stable while the world is, the
cursor moving only after a clean pass, and the alerts firing once.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import mailing_sync as sync
from core.config import Settings
from core.espo import EspoError
from core.mailing import (
    Connection,
    MailingAuthError,
    MailingNotConnected,
    MailingRateLimited,
    STATUS_CONNECTED,
    STATUS_NEEDS_REAUTH,
)
from setup.jobs import BY_KEY

_NOW = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)


# --- fakes ---------------------------------------------------------------------------


def contact(cid, email, first="", last="", opt_in=True, opted_out=False, invalid=False):
    return {"id": cid, "firstName": first, "lastName": last, "emailAddress": email,
            "cMarketingOptIn": opt_in, "emailAddressIsOptedOut": opted_out,
            "emailAddressIsInvalid": invalid}


class FakeCRM:
    def __init__(self, contacts):
        self.contacts = list(contacts)
        self.updates = []
        self.list_calls = []
        self.fail_update_for = set()

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, **kw):
        assert entity == "Contact" and max_size <= 200, "page over the CRM limit"
        assert where == [{"type": "isTrue", "attribute": "cMarketingOptIn"}]
        self.list_calls.append(offset)
        rows = [c for c in self.contacts if c["cMarketingOptIn"]]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def find_one(self, entity, attribute, value, select="id"):
        for c in self.contacts:
            if c["emailAddress"].lower() == value.lower():
                return {"id": c["id"], "emailAddress": c["emailAddress"]}
        return None

    async def get(self, entity, record_id, select=None):
        c = next(c for c in self.contacts if c["id"] == record_id)
        return {"emailAddress": c["emailAddress"], "emailAddressData": c.get("emailAddressData")}

    async def update(self, entity, record_id, payload):
        if record_id in self.fail_update_for:
            raise EspoError("update Contact forbidden")
        self.updates.append((record_id, payload))
        return payload


def vendor(cid, email, permission="implicit"):
    return {"contact_id": cid, "email_address": {"address": email, "permission_to_send": permission}}


class FakeMail:
    def __init__(self, *, lists=(), members=(), unsubscribed=(), on_hold=(), rate_limit_import=False):
        self._lists = list(lists)
        self._members = list(members)
        self._unsub = list(unsubscribed)
        self._hold = list(on_hold)
        self.imports = []
        self.removals = []
        self.created = []
        self.rate_limit_import = rate_limit_import
        self.contacts_calls = []

    async def find_list(self, name):
        return next((l for l in self._lists if l["name"].lower() == name.lower()), None)

    async def create_list(self, name):
        self.created.append(name)
        return {"list_id": "L-new", "name": name}

    async def contacts(self, *, list_id=None, status=None, updated_after=None, include=()):
        self.contacts_calls.append({"list_id": list_id, "status": status, "updated_after": updated_after})
        rows = (self._members if list_id
                else self._unsub if status == "unsubscribed"
                else self._hold if status == "temp_hold" else [])
        for r in rows:
            yield r

    async def import_contacts(self, rows, *, list_id):
        if self.rate_limit_import:
            raise MailingRateLimited("rate limited twice")
        self.imports.append((list_id, rows))
        return ["act-1"]

    async def wait_for_activity(self, activity_id, **kw):
        return {"state": "completed"}

    async def remove_from_list(self, contact_ids, *, list_id):
        self.removals.append((list_id, list(contact_ids)))
        return "act-r"


class FakeStore:
    def __init__(self, conn=None):
        self.conn = conn
        self.list_id = None
        self.pushes = []
        self.cursor = None

    async def get(self):
        return self.conn

    async def set_list_id(self, list_id):
        self.list_id = list_id

    async def record_push(self, summary):
        self.pushes.append(summary)

    async def set_pull_cursor(self, cursor):
        self.cursor = cursor


def connection(status=STATUS_CONNECTED, cursor=None):
    return Connection(status=status, account_label="Test Org", connected_by="adm",
                      connected_at=_NOW - timedelta(days=1), expires_at=_NOW + timedelta(hours=20),
                      last_refresh_at=None, last_error="HTTP 400" if status != STATUS_CONNECTED else None,
                      scopes=("contact_data",), list_id=None, pull_cursor=cursor,
                      last_push_at=None, last_push_summary=None)


def settings(**kw):
    base = dict(espo_dry_run=False, espo_base_url="https://crm.example", espo_api_key="k",
                mailing_client_id="cid", mailing_client_secret="sec")
    base.update(kw)
    return Settings(**base)


# --- the audience rule ----------------------------------------------------------------


async def test_audience_is_opted_in_with_a_usable_primary_address_paged_at_200():
    rows = [contact(f"c{i}", f"p{i}@x.org") for i in range(450)]
    rows += [
        contact("x1", "no@x.org", opt_in=False),
        contact("x2", "out@x.org", opted_out=True),
        contact("x3", "bad@x.org", invalid=True),
        contact("x4", ""),
        contact("dup", "P1@X.ORG"),  # same address as c1, different case → the first wins
    ]
    crm = FakeCRM(rows)
    people = await sync.audience(crm)
    assert len(people) == 450
    assert "p1@x.org" in people and people["p1@x.org"].contact_id == "c1"
    assert not any(k in people for k in ("no@x.org", "out@x.org", "bad@x.org"))
    assert crm.list_calls == [0, 200, 400]


# --- the plan -------------------------------------------------------------------------


async def _plan(crm, mail, name="Event notices"):
    return await sync.build_plan(crm, mail, name)


async def test_plan_adds_the_missing_removes_the_extra_and_withholds_the_unsubscribed():
    crm = FakeCRM([contact("c1", "a@x.org", "Ada", "Lovelace"), contact("c2", "b@x.org"),
                   contact("c3", "gone@x.org")])
    mail = FakeMail(
        lists=[{"list_id": "L1", "name": "Event Notices"}],
        members=[vendor("v-b", "b@x.org"), vendor("v-old", "old@x.org")],
        unsubscribed=[vendor("v-gone", "gone@x.org", "unsubscribed")],
    )
    plan = await _plan(crm, mail)
    assert plan.list_id == "L1"
    assert [p.email for p in plan.add] == ["a@x.org"]
    assert [m.email for m in plan.remove] == ["old@x.org"]
    assert [p.email for p in plan.withheld] == ["gone@x.org"]
    assert plan.unchanged == 1
    text = plan.render()
    assert "ADD to the list: 1" in text and "+ a@x.org" in text
    assert "REMOVE from the list (stay in the account): 1" in text and "- old@x.org" in text
    assert "Withheld" in text and "! gone@x.org" in text
    assert plan.render() == text  # stable


async def test_a_contact_on_temporary_hold_at_the_vendor_is_withheld_too():
    """Ruling 2 names both states; Temporary Hold is the one staff can set by hand."""
    crm = FakeCRM([contact("c1", "held@x.org"), contact("c2", "ok@x.org")])
    mail = FakeMail(lists=[{"list_id": "L1", "name": "Event notices"}],
                    on_hold=[vendor("v-h", "held@x.org", "temp_hold")])
    plan = await _plan(crm, mail)
    assert [p.email for p in plan.withheld] == ["held@x.org"]
    assert [p.email for p in plan.add] == ["ok@x.org"]
    assert [c["status"] for c in mail.contacts_calls if c["status"]] == ["unsubscribed", "temp_hold"]
    assert "unsubscribed or on hold" in plan.render()


async def test_plan_without_the_list_says_apply_creates_it():
    crm = FakeCRM([contact("c1", "a@x.org")])
    plan = await _plan(crm, FakeMail())
    assert plan.list_id is None and "apply CREATES it" in plan.render()
    assert [p.email for p in plan.add] == ["a@x.org"] and plan.remove == []


# --- apply ----------------------------------------------------------------------------


async def test_apply_creates_the_list_imports_names_and_removes_by_vendor_id():
    crm = FakeCRM([contact("c1", "a@x.org", "Ada", "Lovelace"), contact("c2", "b@x.org")])
    mail = FakeMail(lists=[{"list_id": "L1", "name": "Event notices"}],
                    members=[vendor("v-b", "b@x.org"), vendor("v-old", "old@x.org")])
    store = FakeStore(connection())
    plan = await _plan(crm, mail)
    summary = await sync.apply_plan(plan, mail, store)
    assert mail.imports == [("L1", [{"email": "a@x.org", "first_name": "Ada", "last_name": "Lovelace"}])]
    assert mail.removals == [("L1", ["v-old"])]
    assert store.list_id == "L1"
    assert summary["added"] == 1 and summary["removed"] == 1 and summary["partial"] is False
    assert store.pushes == [summary]

    mail2 = FakeMail()
    plan2 = await _plan(FakeCRM([contact("c1", "a@x.org")]), mail2)
    summary2 = await sync.apply_plan(plan2, mail2, FakeStore(connection()))
    assert mail2.created == ["Event notices"] and summary2["createdList"] is True
    assert mail2.imports[0][0] == "L-new"


async def test_a_rate_limited_import_is_a_partial_pass_that_is_still_recorded():
    crm = FakeCRM([contact("c1", "a@x.org")])
    mail = FakeMail(lists=[{"list_id": "L1", "name": "Event notices"}], rate_limit_import=True)
    store = FakeStore(connection())
    result = await sync.run_push(settings(), apply=True, crm=crm, mail=mail, store=store)
    assert result.ok and result.partial
    assert store.pushes[0]["partial"] is True and "rate limited" in store.pushes[0]["error"]
    assert "PARTIAL" in result.text


# --- run_push gates -------------------------------------------------------------------


async def test_run_push_dry_run_changes_nothing_and_returns_the_plan_text():
    crm = FakeCRM([contact("c1", "a@x.org")])
    mail = FakeMail()
    store = FakeStore(connection())
    result = await sync.run_push(settings(), apply=False, crm=crm, mail=mail, store=store)
    assert result.ok and result.plan is not None
    assert mail.imports == [] and mail.created == [] and store.pushes == []
    assert "ADD to the list: 1" in result.text


async def test_run_push_refuses_in_dry_run_and_without_credentials():
    r = await sync.run_push(settings(espo_dry_run=True), apply=False)
    assert not r.ok and "dry-run" in r.error
    r = await sync.run_push(settings(mailing_client_secret=""), apply=False)
    assert not r.ok and "secret" in r.error


async def test_run_push_reports_not_connected_and_reauthorisation_without_raising():
    class NotConnectedMail(FakeMail):
        async def find_list(self, name):
            raise MailingNotConnected("The mailing service needs re-authorisation: HTTP 400")

    r = await sync.run_push(settings(), apply=True, crm=FakeCRM([]), mail=NotConnectedMail(), store=FakeStore())
    assert not r.ok and r.needs_reauthorisation and "re-authorisation" in r.text

    class RefusedMail(FakeMail):
        async def find_list(self, name):
            raise MailingAuthError("refused")

    r = await sync.run_push(settings(), apply=True, crm=FakeCRM([]), mail=RefusedMail(), store=FakeStore())
    assert not r.ok and r.needs_reauthorisation


async def test_run_push_reports_a_crm_failure_as_text():
    class BrokenCRM(FakeCRM):
        async def list(self, *a, **kw):
            raise EspoError("list Contact failed: HTTP 403")

    r = await sync.run_push(settings(), apply=True, crm=BrokenCRM([]), mail=FakeMail(), store=FakeStore())
    assert not r.ok and "HTTP 403" in r.text and not r.needs_reauthorisation


# --- the pull -------------------------------------------------------------------------


async def test_pull_marks_the_matching_address_opted_out_and_advances_the_cursor():
    crm = FakeCRM([contact("c1", "a@x.org"), contact("c2", "b@x.org")])
    crm.contacts[0]["emailAddressData"] = [
        {"emailAddress": "a@x.org", "primary": True, "optOut": False},
        {"emailAddress": "other@x.org", "primary": False, "optOut": False},
    ]
    mail = FakeMail(unsubscribed=[vendor("v-a", "A@x.org", "unsubscribed"),
                                  vendor("v-z", "nobody@x.org", "unsubscribed")])
    store = FakeStore(connection(cursor=_NOW - timedelta(hours=1)))
    result = await sync.run_pull(settings(), apply=True, crm=crm, mail=mail, store=store, now=_NOW)
    assert result.ok
    assert mail.contacts_calls[0]["updated_after"] == _NOW - timedelta(hours=1)
    assert crm.updates == [("c1", {"emailAddressData": [
        {"emailAddress": "a@x.org", "primary": True, "optOut": True},
        {"emailAddress": "other@x.org", "primary": False, "optOut": False},  # untouched
    ]})]
    assert result.summary["optedOut"] == 1 and result.summary["unknown"] == 1
    assert store.cursor == _NOW  # the pass's start, not its end
    assert "not in the CRM; skipped" in result.text


async def test_pull_never_clears_an_opt_out_and_uses_connected_at_as_the_first_cursor():
    crm = FakeCRM([contact("c1", "a@x.org")])
    crm.contacts[0]["emailAddressData"] = [{"emailAddress": "a@x.org", "primary": True, "optOut": True}]
    mail = FakeMail(unsubscribed=[vendor("v-a", "a@x.org", "unsubscribed")])
    conn = connection()
    store = FakeStore(conn)
    result = await sync.run_pull(settings(), apply=True, crm=crm, mail=mail, store=store, now=_NOW)
    assert crm.updates == [] and result.summary["alreadyOut"] == 1
    assert mail.contacts_calls[0]["updated_after"] == conn.connected_at


async def test_pull_dry_run_writes_nothing_and_keeps_the_cursor():
    crm = FakeCRM([contact("c1", "a@x.org")])
    mail = FakeMail(unsubscribed=[vendor("v-a", "a@x.org", "unsubscribed")])
    store = FakeStore(connection())
    result = await sync.run_pull(settings(), apply=False, crm=crm, mail=mail, store=store)
    assert result.ok and crm.updates == [] and store.cursor is None
    assert "would be marked opted out" in result.text


async def test_pull_keeps_the_cursor_when_a_crm_write_fails():
    crm = FakeCRM([contact("c1", "a@x.org"), contact("c2", "b@x.org")])
    crm.fail_update_for = {"c1"}
    mail = FakeMail(unsubscribed=[vendor("v-a", "a@x.org", "unsubscribed"),
                                  vendor("v-b", "b@x.org", "unsubscribed")])
    store = FakeStore(connection())
    result = await sync.run_pull(settings(), apply=True, crm=crm, mail=mail, store=store)
    assert not result.ok and result.summary["errors"] == 1 and result.summary["optedOut"] == 1
    assert store.cursor is None and "NOT advanced" in result.text


async def test_pull_on_a_connection_needing_reauthorisation_says_so():
    store = FakeStore(connection(status=STATUS_NEEDS_REAUTH))
    result = await sync.run_pull(settings(), apply=True, crm=FakeCRM([]), mail=FakeMail(), store=store)
    assert not result.ok and result.needs_reauthorisation
    result = await sync.run_pull(settings(), apply=True, crm=FakeCRM([]), mail=FakeMail(), store=FakeStore(None))
    assert not result.ok and not result.needs_reauthorisation and "not connected" in result.text


# --- alerts -----------------------------------------------------------------------------


def test_alerts_fire_once_for_reauthorisation_and_name_the_fix():
    r = sync.PushResult(ok=False, error="HTTP 400", needs_reauthorisation=True)
    alerts = sync.alerts_for(r, kind="push", settings=settings())
    assert len(alerts) == 1
    key, text, cooldown = alerts[0]
    assert key == "mailing_reauth" and "/setup" in text and cooldown == sync.REAUTH_COOLDOWN


def test_alerts_for_failures_and_partials():
    assert sync.alerts_for(sync.PushResult(ok=True), kind="push", settings=settings()) == []
    (key, text, _), = sync.alerts_for(sync.PushResult(ok=False, error="boom"), kind="push", settings=settings())
    assert key == "mailing_push_failed" and "boom" in text
    (key, text, _), = sync.alerts_for(
        sync.PushResult(ok=True, partial=True, summary={"error": "rate limited"}), kind="push", settings=settings())
    assert key == "mailing_push_partial" and "rate limited" in text
    (key, _, _), = sync.alerts_for(sync.PullResult(ok=False, error="x"), kind="pull", settings=settings())
    assert key == "mailing_pull_failed"


# --- the Operations jobs ------------------------------------------------------------------


def test_both_mailing_jobs_are_runnable_and_mutating():
    for key in ("mailing_push", "mailing_pull"):
        spec = BY_KEY[key]
        assert spec.mutating and spec.runnable and spec.dry_run and spec.apply


async def test_the_push_job_raises_the_refusal_so_the_row_shows_it(monkeypatch):
    from setup import jobs

    async def refused(settings, *, apply, **kw):
        return sync.PushResult(ok=False, error="not connected", text="Not connected: x")

    monkeypatch.setattr("core.mailing_sync.run_push", refused)
    with pytest.raises(RuntimeError, match="Not connected"):
        await jobs.BY_KEY["mailing_push"].dry_run(settings())


# --- the worker gate -----------------------------------------------------------------------


def test_the_worker_runs_the_push_and_pull_only_with_the_switch_on():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "worker.py").read_text()
    assert "settings.mailing_sync and not settings.espo_dry_run" in src
    assert "run_push(settings, apply=True)" in src and "run_pull(settings, apply=True)" in src
    assert "alerts_for(result" in src
