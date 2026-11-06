"""The History engine and the History tab — mentor login integrity step 5
(plan prds/mentor-login-integrity-plan.md § 4.5; build prompt v0.6).

The note and row shapes are the ones read on crm-test 11-06-26: CActionLog
keeps the actor's name only; a status change is an Update note carrying
``value``; an Assign note lists added and removed users.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import action_log, history
from core.app import create_app
from core.config import Settings, get_settings
from core.espo import EspoError
from core.settings_registry import SETTINGS
from forms import info_request

SHARED = Path(__file__).resolve().parent.parent / "frontend" / "shared"
KEY = "6a186482490b9f3f2"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _row(**kw):
    base = {"createdAt": "2026-11-06 12:00:00", "app": "Mentor Administration",
            "category": action_log.CAT_RECORD_EDIT, "actionType": action_log.ACT_RECORD_EDITED,
            "actorName": "Jane Staff", "summary": "Saved Mentor status.", "outcome": "Success"}
    base.update(kw)
    return base


def _update(fields, was, became, *, by="Jane Staff", by_id="u1", at="2026-11-06 12:00:20", value=None):
    data = {"fields": fields, "attributes": {"was": was, "became": became}}
    if value is not None:
        data["value"] = value
    return {"type": "Update", "data": data, "createdAt": at,
            "createdById": by_id, "createdByName": by}


LABELS = {"mentorStatus": "Mentor Status", "cbmEmail": "CBM Email"}


# --- Q5.4: what moved ---------------------------------------------------------


def test_same_value_normalises_as_the_crm_reads_back():
    assert history.same_value("", None)
    assert history.same_value(["b", "a"], ["a", "b"])
    assert history.same_value("x\r\n", "x")
    assert not history.same_value("Active", "Inactive")


def test_value_changes_records_only_what_moved_never_an_id_or_a_secret():
    before = {"status": "Open", "notes": "a", "mentorId": "6a87e738294d32aac",
              "mentorName": "Old Mentor", "apiKey": "k1"}
    after = {"status": "Open", "notes": "b", "mentorId": "6a87e738294d32aad",
             "mentorName": "New Mentor", "apiKey": "k2"}
    moved = history.value_changes(before, after, ["status", "notes", "mentorId", "apiKey"])
    assert moved == {"notes": {"from": "a", "to": "b"},
                     "mentor": {"from": "Old Mentor", "to": "New Mentor"}}
    assert history.value_changes({}, after, ["notes"]) == {"notes": {"to": "b"}}


def test_display_value_hides_ids_and_markup():
    assert history.display_value("6a87e738294d32aac") == ""
    assert history.display_value("<p>Hello <b>there</b></p>") == "Hello there"
    assert history.display_value(True) == "Yes"
    assert history.display_value({"raw": 1}) == ""
    assert history.display_value("x" * 400).endswith("…")


# --- the merge rule -------------------------------------------------------------


def test_an_application_save_shows_once_with_the_crm_values_folded_in():
    rows = [_row(details=json.dumps({"fields": ["mentorStatus"]}))]
    notes = [_update(["mentorStatus"], {"mentorStatus": "Approved"}, {"mentorStatus": "Active"})]
    lines = history.merge(rows, notes, labels=LABELS, key_user=KEY)
    assert len(lines) == 1
    ln = lines[0]
    assert ln["where"] == "Mentor Administration" and ln["who"] == "Jane Staff"
    assert ln["changes"] == [{"field": "Mentor Status", "from": "Approved", "to": "Active",
                              "hasFrom": True}]
    assert ln["valuesRecorded"] is True


def test_a_note_by_someone_else_or_too_late_is_the_crm_directly():
    rows = [_row(details=json.dumps({"fields": {"mentorStatus": {"from": "A", "to": "B"}}}))]
    other = _update(["mentorStatus"], {"mentorStatus": "B"}, {"mentorStatus": "C"}, by="Sharon Rose")
    late = _update(["mentorStatus"], {"mentorStatus": "B"}, {"mentorStatus": "C"},
                   at="2026-11-06 12:05:00")
    lines = history.merge(rows, [other, late], labels=LABELS, key_user=KEY)
    assert len(lines) == 3
    crm = [ln for ln in lines if ln["source"] == "crm"]
    assert {ln["where"] for ln in crm} == {history.CRM_DIRECT}
    assert {ln["who"] for ln in crm} == {"Sharon Rose", "Jane Staff"}


def test_a_status_change_is_an_update_note_with_a_value():
    note = _update([], {}, {}, by="Sharon Rose", value="Active")
    [ln] = history.merge([], [note], labels=LABELS, key_user=KEY, status_field="mentorStatus")
    assert ln["what"] == "Mentor Status set to Active."
    assert ln["changes"] == [{"field": "Mentor Status", "to": "Active"}]


def test_post_notes_are_never_taken():
    post = {"type": "Post", "post": "[Mentor Administration] Saved", "createdAt": "2026-11-06 12:00:00",
            "createdByName": "Jane Staff", "data": {}}
    assert history.merge([], [post], labels={}, key_user=KEY) == []


def test_the_key_based_account_is_system_and_takes_the_jobs_name():
    rows = [_row(actorName="System: nightly clean-up, mentor Contacts",
                 category=action_log.CAT_ASSIGNMENT, actionType="Assignment Repaired",
                 summary="Login added to the mentor's Contact.")]
    assign = {"type": "Assign", "createdById": KEY, "createdByName": "customapps",
              "createdAt": "2026-11-06 12:00:05",
              "data": {"addedAssignedUsers": [{"id": "6a2b8368418e43c77", "name": "Matt Mentor"}],
                       "removedAssignedUsers": []}}
    lines = history.merge(rows, [assign], labels={}, key_user=KEY)
    assert len(lines) == 1
    assert (lines[0]["who"], lines[0]["job"]) == ("System", "nightly clean-up, mentor Contacts")
    lone = history.merge([], [assign], labels={}, key_user=KEY)[0]
    assert lone["who"] == "System" and lone["what"] == "Assigned to Matt Mentor."
    assert "6a2b" not in json.dumps(lone)


def test_a_line_never_carries_an_id():
    rows = [_row(actorName="Admin", category=action_log.CAT_PROVISIONING,
                 details=json.dumps({"userId": "6a87e4b8c23c4542d", "email": "a@b.org"}))]
    assert "6a87e4b8c23c4542d" not in json.dumps(history.merge(rows, [], labels={}, key_user=KEY))


def test_older_lines_say_values_were_not_recorded():
    rows = [_row(details=json.dumps({"fields": ["cbmEmail"]}))]
    [ln] = history.merge(rows, [], labels=LABELS, key_user=KEY)
    assert ln["valuesRecorded"] is False and ln["changes"] == [{"field": "CBM Email"}]


def test_status_admin_entries_are_for_two_teams_only():
    s = Settings()
    row = _row(actionType=action_log.ACT_MENTOR_STATUS_ADMIN)
    assert history._visible(row, {"teams": ["Mentor Administration Team"]}, s)
    assert history._visible(row, {"teams": ["Client Administration Team"]}, s)
    assert not history._visible(row, {"teams": ["Partner Management Team"]}, s)
    assert history._visible(row, {"isAdmin": True}, s)
    assert history._visible(_row(), {"teams": []}, s)


# --- the engine end to end --------------------------------------------------------


class FakeCrm:
    def __init__(self, *, readable=True, rows=(), notes=(), audited=True):
        self.readable, self.rows, self.notes, self.audited = readable, list(rows), list(notes), audited
        self.listed = []
        self._base = "https://crm.example/api/v1"

    async def get(self, entity, record_id, select=None):
        if not self.readable:
            raise EspoError("get CMentorProfile/x failed: HTTP 403")
        return {"id": record_id}

    async def list(self, entity, **kw):
        self.listed.append((entity, kw))
        assert kw["max_size"] <= 200
        return {"total": len(self.rows), "list": self.rows[kw.get("offset", 0):][:kw["max_size"]]}

    async def metadata(self, key):
        if key == "scopes":
            return {"CActionLog": {}}
        if key.startswith("scopes."):
            return {"stream": True, "statusField": "mentorStatus"}
        return {"mentorStatus": {"type": "enum", "audited": self.audited}, "x": {"type": "varchar"}}

    async def i18n(self, scope):
        return {scope: {"fields": LABELS}}

    async def app_user(self):
        return {"user": {"id": KEY}}

    async def _request(self, method, url, *, op, params=None, json_body=None):
        notes = self.notes
        params = dict(params)
        assert int(params["maxSize"]) <= 200

        class R:
            status_code = 200

            def json(self_inner):
                return {"total": len(notes), "list": notes}
        return R()


async def test_the_users_own_read_gates_the_tab():
    with pytest.raises(EspoError):
        await history.record_history(FakeCrm(readable=False), "CMentorProfile", "m1",
                                     viewer={}, key_client=FakeCrm())


async def test_record_history_merges_both_sources():
    action_log._exists_cache.clear()
    key = FakeCrm(rows=[_row(details=json.dumps({"fields": ["mentorStatus"]}))])
    user = FakeCrm(notes=[_update(["mentorStatus"], {"mentorStatus": "A"}, {"mentorStatus": "B"})])
    out = await history.record_history(user, "CMentorProfile", "m1", viewer={}, key_client=key,
                                       settings=Settings(espo_base_url="https://crm.example"))
    assert out["tracked"] is True and out["actionHistory"] and out["crmNotes"]
    assert len(out["lines"]) == 1 and out["lines"][0]["valuesRecorded"]
    where = {c["attribute"]: c["value"] for c in key.listed[0][1]["where"]}
    assert where == {"recordType": "CMentorProfile", "recordId": "m1"}


# --- the endpoint and the switch ----------------------------------------------------

_USER = {"userId": "u1", "userName": "boss", "name": "Mentor Boss", "isAdmin": True, "token": "tok"}


def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())
    return create_app([info_request.SPEC])


def test_the_tab_is_off_until_the_switch(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/session").json()["historyEnabled"] is False
        assert c.get("/mentoradmin/api/mentors/m1/history").status_code == 404


def test_the_tab_answers_when_on(monkeypatch):
    async def fake(client, entity, record_id, *, viewer):
        assert entity == "CMentorProfile" and record_id == "m1" and viewer is _USER
        return {"lines": [], "tracked": True}
    monkeypatch.setattr("mentoradmin.router.history.record_history", fake)
    with TestClient(_app(monkeypatch, RECORD_HISTORY_TAB="true")) as c:
        assert c.get("/mentoradmin/api/session").json()["historyEnabled"] is True
        assert c.get("/mentoradmin/api/mentors/m1/history").json() == {"lines": [], "tracked": True}


def test_the_switch_is_on_the_setup_page_and_off_by_default():
    assert Settings().record_history_tab is False
    assert "record_history_tab" in {getattr(x, "key", None) for x in SETTINGS}


def test_the_page_loads_the_shared_history_after_busy():
    html = (Path(__file__).resolve().parent.parent / "mentoradmin" / "frontend" / "index.html").read_text()
    assert html.index("/shared/busy.js") < html.index("/shared/history.js") < html.index("app.js")
    assert "/shared/history.css" in html


# --- the panel's pure helpers, under node ---------------------------------------------


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = f"require({json.dumps(str(SHARED / 'history.js'))});\nconst H = globalThis.CBMHistory;\n{script}"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_filters_and_csv():
    out = _node("""
      const lines = [
        {at:"2026-11-06T12:00:00Z", who:"Jane", job:null, where:"Mentor Administration", what:"Saved", kind:"Record Edit",
         changes:[{field:"Mentor Status", from:"A", to:"B"}]},
        {at:"2026-10-01T12:00:00Z", who:"System", job:"nightly clean-up", where:"The application", what:"=cmd", kind:"Assignment", changes:[]},
      ];
      const byWho = H.filterLines(lines, {who:"System — nightly clean-up"}).length;
      const byKind = H.filterLines(lines, {kind:"Record Edit"}).length;
      const byDate = H.filterLines(lines, {from:"2026-11-01"}).length;
      console.log(JSON.stringify({byWho, byKind, byDate, csv: H.toCsv(lines)}));
    """)
    assert (out["byWho"], out["byKind"], out["byDate"]) == (1, 1, 1)
    rows = out["csv"].strip().split("\r\n")
    assert rows[0].startswith("When (UTC),Who,Where,Record,What")
    assert rows[1].endswith("Mentor Status,A,B")
    assert ",'=cmd," in rows[2], "a formula is defused"


# --- the 5a review's findings ---------------------------------------------------------


def test_provisioning_explains_the_notes_it_caused():
    rows = [_row(category=action_log.CAT_PROVISIONING, actionType=action_log.ACT_LOGIN_PROVISIONED,
                 summary="CRM login created.", details=json.dumps({"reused": False}))]
    upd = _update(["cbmEmail"], {"cbmEmail": None}, {"cbmEmail": "a@b.org"}, value="Provisional")
    assign = {"type": "Assign", "createdById": "u1", "createdByName": "Jane Staff",
              "createdAt": "2026-11-06 12:00:10",
              "data": {"addedAssignedUsers": [{"id": "x", "name": "New Mentor"}]}}
    lines = history.merge(rows, [upd, assign], labels=LABELS, key_user=KEY,
                          status_field="mentorStatus")
    assert [ln["where"] for ln in lines] == ["Mentor Administration"]


def test_a_save_that_repaired_the_login_explains_its_assign_note():
    rows = [_row(details=json.dumps({"fields": {"mentorType": {"from": "A", "to": "B"}},
                                     "loginLinks": {"profileLogin": "x"}}))]
    assign = {"type": "Assign", "createdById": "u1", "createdByName": "Jane Staff",
              "createdAt": "2026-11-06 12:00:03",
              "data": {"addedAssignedUsers": [{"id": "x", "name": "New Mentor"}]}}
    assert len(history.merge(rows, [assign], labels={}, key_user=KEY)) == 1


def test_a_direct_edit_never_hides_inside_an_application_line():
    rows = [_row(details=json.dumps({"fields": {"acceptingNewClients": {"from": True, "to": False}}}))]
    direct = _update(["acceptingNewClients", "maximumClientCapacity"],
                     {"acceptingNewClients": False, "maximumClientCapacity": 4},
                     {"acceptingNewClients": True, "maximumClientCapacity": 9})
    lines = history.merge(rows, [direct], labels={}, key_user=KEY)
    assert sorted(ln["where"] for ln in lines) == ["In the CRM directly", "Mentor Administration"]


def test_the_status_value_fills_a_listed_status_field_and_is_a_status_change():
    note = _update(["mentorStatus"], {}, {}, value="Active", by="Sharon Rose")
    [ln] = history.merge([], [note], labels=LABELS, key_user=KEY, status_field="mentorStatus")
    assert ln["changes"][0]["to"] == "Active" and ln["kind"] == action_log.CAT_STATUS


def test_what_never_carries_an_id_or_a_raw_error_body():
    rows = [_row(summary='CRM login x — did not complete: create User failed: HTTP 400 '
                         '{"messageTranslation": {"data": {"id": "6a87e4b8c23c4542d"}}}')]
    [ln] = history.merge(rows, [], labels={}, key_user=KEY)
    assert "6a87e4b8c23c4542d" not in ln["what"] and "{" not in ln["what"]


async def test_a_bad_body_degrades_rather_than_failing_the_tab():
    class Broken(FakeCrm):
        async def list(self, entity, **kw):
            raise ValueError("Expecting value: line 1 column 1")
    action_log._exists_cache.clear()
    out = await history.record_history(FakeCrm(), "CMentorProfile", "m1", viewer={},
                                       key_client=Broken(), settings=Settings())
    assert out["actionHistory"] is False and out["crmNotes"] is True


def test_the_values_table_is_not_a_nested_table():
    js = (SHARED / "history.js").read_text()
    assert 'el("table", "cbm-hist__vals")' not in js, "the shared grid would take its headings"
