"""The activity page — mentor login integrity step 6 (plan § 4.5)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from activity import service
from core import action_log, history
from core.app import create_app
from core.config import Settings, get_settings
from core.espo import EspoError
from core.settings_registry import SETTINGS
from forms import info_request

KEY = "6a186482490b9f3f2"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    history._key_user_cache.clear()
    yield
    get_settings.cache_clear()
    history._key_user_cache.clear()


class Key:
    def __init__(self, rows=(), notes=(), slow=False, key_user=KEY):
        self.rows, self.notes, self.slow, self.key_user = list(rows), list(notes), slow, key_user
        self.wheres = {}

    async def get(self, entity, rid, select=None):
        people = {"6a2b8368418e43c77": {"id": "6a2b8368418e43c77", "name": "Jane Staff", "userName": "jane.staff@x.org"}}
        if rid not in people:
            raise EspoError("get User failed: HTTP 404")
        return people[rid]

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        self.wheres[entity] = where
        if entity == "Note":
            if self.slow:
                await asyncio.sleep(5)
            data = self.notes
        elif entity == action_log.ACTION_LOG_ENTITY:
            data = self.rows
        elif entity == "User":
            data = [{"id": "6a2b8368418e43c77", "name": "Jane Staff", "isActive": True},
                    {"id": "6a2b8368418e43c78", "name": "Gone Person", "isActive": False}]
        else:  # a record-name read
            ids = next(c["value"] for c in where if c["attribute"] == "id")
            data = [{"id": i, "name": f"Record {i[-3:]}"} for i in ids]
        return {"total": len(data), "list": data[offset:offset + max_size]}

    async def app_user(self):
        if not self.key_user:
            raise EspoError("App/user failed: HTTP 500")
        return {"user": {"id": self.key_user}}

    async def i18n(self, scope):
        if scope == "Global":
            return {"Global": {"scopeNames": {"CMentorProfile": "Mentor"}}}
        return {scope: {"fields": {"mentorStatus": "Mentor Status"}}}

    async def metadata(self, key):
        return {"stream": True, "statusField": "mentorStatus"}


def _row(**kw):
    base = {"createdAt": "2026-11-06 12:00:00", "app": "Mentor Administration",
            "category": action_log.CAT_RECORD_EDIT, "actionType": action_log.ACT_RECORD_EDITED,
            "actorName": "Jane Staff", "summary": "Saved Mentor Status.",
            "recordType": "CMentorProfile", "recordId": "6a87e7247d5448281",
            "details": json.dumps({"fields": ["mentorStatus"]})}
    base.update(kw)
    return base


def _note(**kw):
    base = {"type": "Update", "createdAt": "2026-11-06 12:00:20", "createdById": "6a2b8368418e43c77",
            "createdByName": "Jane Staff", "parentType": "CMentorProfile",
            "parentId": "6a87e7247d5448281",
            "data": {"fields": [], "attributes": {"was": {}, "became": {}}, "value": "Active"}}
    base.update(kw)
    return base


async def test_one_person_across_records_with_the_record_named_never_its_id():
    key = Key(rows=[_row()], notes=[
        _note(),
        _note(parentId="6a87e7247d5448299", createdAt="2026-11-05 09:00:00"),
        _note(parentType=action_log.ACTION_LOG_ENTITY, parentId="6a87e7247d5448277"),
    ])
    out = await service.activity(person_id="6a2b8368418e43c77", since="", until="", viewer={},
                                 settings=Settings(), key=key)
    lines = out["lines"]
    assert len(lines) == 2, "the app save folds its note; the CActionLog note is skipped"
    assert lines[0]["where"] == "Mentor Administration"
    assert lines[0]["record"] == "Mentor: Record 281"
    assert lines[1]["where"] == "In the CRM directly"
    assert "6a87e7247d5448299" not in lines[1]["record"]
    assert key.wheres[action_log.ACTION_LOG_ENTITY] == [
        {"type": "in", "attribute": "actorName", "value": ["Jane Staff", "jane.staff@x.org"]}]


async def test_system_is_the_jobs_and_the_key_based_account():
    key = Key()
    await service.activity(person_id=service.SYSTEM_PERSON, since="", until="", viewer={},
                           settings=Settings(), key=key)
    assert {"type": "startsWith", "attribute": "actorName",
            "value": action_log.SYSTEM_ACTOR_PREFIX} in key.wheres[action_log.ACTION_LOG_ENTITY]
    assert {"type": "equals", "attribute": "createdById", "value": KEY} in key.wheres["Note"]


async def test_a_person_or_both_dates_is_required_and_dates_are_checked():
    with pytest.raises(service.ActivityError):
        await service.activity(person_id="", since="2026-11-01 04:00:00", until="",
                               viewer={}, key=Key())
    with pytest.raises(service.ActivityError):
        await service.activity(person_id="6a2b8368418e43c77", since="yesterday", until="", viewer={}, key=Key())
    out = await service.activity(person_id="", since="2026-11-01 04:00:00",
                                 until="2026-11-07 05:00:00", viewer={}, key=Key())
    assert out["lines"] == []


async def test_a_slow_crm_notes_read_lists_the_application_history_and_says_so(monkeypatch):
    monkeypatch.setattr(service, "NOTE_READ_SECONDS", 0.05)
    out = await service.activity(person_id="6a2b8368418e43c77", since="", until="", viewer={},
                                 key=Key(rows=[_row()], slow=True))
    assert len(out["lines"]) == 1 and out["truncated"] is True
    assert "took too long" in out["notice"]


async def test_people_lists_system_first_and_former_logins():
    got = await service.people(Key())
    assert got[0]["id"] == service.SYSTEM_PERSON
    assert {p["name"]: p["active"] for p in got[1:]} == {"Gone Person": False, "Jane Staff": True}


# --- the gate ------------------------------------------------------------------------


def _app(monkeypatch, user, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("activity.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("activity.router.service.key_client", lambda settings: Key())
    return create_app([info_request.SPEC])


_STAFF = {"userId": "u9", "userName": "s", "name": "S", "isAdmin": False,
          "teams": ["Mentor Administration Team"], "token": "t"}
_MEMBER = {**_STAFF, "teams": ["System Management Team"]}


def test_off_until_the_switch(monkeypatch):
    with TestClient(_app(monkeypatch, _MEMBER)) as c:
        assert c.get("/activity/api/session").status_code == 404


def test_the_team_gate(monkeypatch):
    with TestClient(_app(monkeypatch, _STAFF, ACTIVITY_PAGE="true")) as c:
        r = c.get("/activity/api/session")
        assert r.status_code == 403 and "System Management Team" in r.json()["detail"]
    get_settings.cache_clear()
    with TestClient(_app(monkeypatch, _MEMBER, ACTIVITY_PAGE="true")) as c:
        assert c.get("/activity/api/session").status_code == 200
        assert c.get("/activity/api/changes").status_code == 400
        assert c.get("/activity/api/changes?person=6a2b8368418e43c77").json()["lines"] == []
    get_settings.cache_clear()
    with TestClient(_app(monkeypatch, {**_STAFF, "isAdmin": True}, ACTIVITY_PAGE="true")) as c:
        assert c.get("/activity/api/session").status_code == 200


def test_the_settings_are_on_the_setup_page_and_off_by_default():
    s = Settings()
    assert s.activity_page is False
    assert s.system_management_allowed_teams_list == ["System Management Team"]
    keys = {getattr(x, "key", None) for x in SETTINGS}
    assert {"activity_page", "system_management_allowed_teams"} <= keys


def test_the_page_follows_the_conventions():
    html = (ROOT / "activity" / "frontend" / "index.html").read_text()
    assert html.index("/shared/busy.js") < html.index("/shared/grid.js") < html.index("app.js")
    assert '<meta name="cbm-org" content="{{org}}" />' in html
    assert "/shared/history.js" in html



# --- the step 6 review's findings ---------------------------------------------------


async def test_an_assign_credits_its_linked_records_to_the_application():
    rows = [_row(category=action_log.CAT_ASSIGNMENT, actionType=action_log.ACT_MENTOR_ASSIGNED,
                 app="Client Administration", recordType="CEngagement",
                 recordId="6a87e7247d5448100", details=None, summary="Mentor assigned.")]
    contact = {"type": "Assign", "createdAt": "2026-11-06 12:00:04", "createdById": "6a2b8368418e43c77",
               "createdByName": "Jane Staff", "parentType": "Contact",
               "parentId": "6a87e7247d5448101",
               "data": {"addedAssignedUsers": [{"id": "x", "name": "Matt Mentor"}]}}
    out = await service.activity(person_id="6a2b8368418e43c77", since="", until="", viewer={},
                                 settings=Settings(), key=Key(rows=rows, notes=[contact]))
    assert sorted(ln["where"] for ln in out["lines"]) == ["Client Administration"] * 2


async def test_system_without_the_accounts_id_lists_no_crm_notes():
    key = Key(key_user="")
    out = await service.activity(person_id=service.SYSTEM_PERSON, since="", until="",
                                 viewer={}, settings=Settings(), key=key)
    assert "Note" not in key.wheres and out["crmNotes"] is False and out["notice"]


async def test_a_person_must_be_a_login():
    for bad in ("../Contact/x", "6a2b8368418e43c78"):
        with pytest.raises(service.ActivityError):
            await service.activity(person_id=bad, since="", until="", viewer={}, key=Key())


def test_the_two_sources_keep_the_span_both_cover():
    rows = [{"createdAt": "2026-11-06 12:00:00"}, {"createdAt": "2026-11-05 12:00:00"}]
    notes = [{"createdAt": "2026-11-06 11:00:00"}, {"createdAt": "2026-11-01 12:00:00"}]
    r, n = service._same_window(rows, True, notes, False)
    # the cut falls a minute and a half after the oldest row the cap kept
    assert r == [rows[0]] and n == [notes[0]]
    assert service._same_window(rows, False, notes, False) == (rows, notes)


async def test_the_notes_read_keeps_the_pages_it_had_when_time_runs_out():
    class Paged(Key):
        async def list(self, entity, **kw):
            if entity == "Note":
                if kw.get("offset"):
                    await asyncio.sleep(5)
                return {"total": 400, "list": [_note()] * 200}
            return await super().list(entity, **kw)
    got, trunc, slow = await service._note_rows(Paged(), "6a2b8368418e43c77", KEY, "", "", budget=0.2)
    assert len(got) == 200 and trunc and slow
