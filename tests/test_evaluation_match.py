"""Business Evaluation phase 7, the mentor match (evaluation/match.py,
ruling BE28; Doug's choices 11-19-26): Client Administration's AI analysis on
an engagement waiting for a mentor. Advice only; no contact details sent; only
eligible mentors sent; a mentor at capacity marked; a refused or failed call
a message, never a 500; every run in the action log."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from evaluation import match
from forms import info_request

ENG = "6619engagement001"
PROFILE = "6619clientprof001"
ROOT = Path(__file__).resolve().parent.parent

_STAFF = {"userId": "u1", "userName": "kitty", "name": "Kitty Cat", "isAdmin": False,
          "token": "tok", "teams": ["Client Administration Team"]}

NEEDS = ("<p>Dana Testbaker here. Cash flow is tight before the holidays. "
         "Call me on 216-555-0142 or dana@brightline.example, "
         "or visit 1234 Euclid Avenue.</p>")


def _mentor(mid, name, *, active=True, accepting=True, user="u", cap=3, **kw):
    base = {"id": mid, "name": name, "mentorStatus": "Active" if active else "Inactive",
            "acceptingNewClients": accepting, "assignedUserId": user,
            "assignedUsersIds": [user] if user else [], "maximumClientCapacity": cap,
            "cbmEmail": f"{mid}@cbmentors.example", "industryExperience": ["Food Service"],
            "areaOfExpertise": ["Finance"], "mentoringFocusAreas": ["Cash flow"],
            "industrySector": "Retail", "yearsOfExperience": 12, "mentorType": "Mentor",
            "fluentLanguages": ["English"], "mentorTitle": "Retired bakery owner",
            "mentorSummary": "<p>Ran a bakery. Reach me at joe@home.example.</p>",
            "aboutMentor": "<p>Twelve years in <b>food</b>. Phone 440-555-0199.</p>"}
    base.update(kw)
    return base


MENTORS = [
    _mentor("m1", "Joe Mentor", cap=3, lastClientAssignedDate="2026-11-18"),
    _mentor("m2", "Ann Full", cap=2),                      # two active clients: at capacity
    _mentor("m3", "Ivan Inactive", active=False),
    _mentor("m4", "Paula Paused", accepting=False),
    _mentor("m5", "Nora Nologin", user=None),
]
ENGAGEMENTS = [
    {"id": "e1", "mentorProfileId": "m2", "engagementStatus": "Active"},
    {"id": "e2", "mentorProfileId": "m2", "engagementStatus": "On-Hold"},
    {"id": "e3", "mentorProfileId": "m1", "engagementStatus": "Active"},
]


class Crm:
    def __init__(self, *, mentor_id=None, profile=None, mentors=MENTORS):
        self.eng = {"id": ENG, "name": "Dana Testbaker — Brightline Bakehouse",
                    "engagementStatus": "Submitted", "mentorProfileId": mentor_id,
                    "mentorProfileName": "Joe Mentor" if mentor_id else None,
                    "mentoringFocusAreas": ["Financial Management"],
                    "mentoringNeedsDescription": NEEDS,
                    "engagementClientId": PROFILE, "engagementClientName": "Brightline Bakehouse",
                    "primaryEngagementContactName": "Dana Testbaker"}
        self.profile = profile
        self.mentors = mentors

    async def get(self, entity, rid, select=None):
        if entity == "CEngagement":
            return dict(self.eng)
        if entity == "CClientProfile":
            return {"id": PROFILE, "name": "Brightline Bakehouse",
                    "evaluationProfile": self.profile or ""}
        raise AssertionError(entity)

    async def list(self, entity, where=None, select=None, max_size=None, **kw):
        if entity == "CMentorProfile":
            rows = list(self.mentors)
            for w in where or []:
                if w["type"] == "isTrue":
                    rows = [r for r in rows if r.get(w["attribute"])]
                elif w["type"] == "equals":
                    rows = [r for r in rows if r.get(w["attribute"]) == w["value"]]
            return {"list": rows, "total": len(rows)}
        if entity == "CEngagement":
            return {"list": [] if kw.get("offset") else ENGAGEMENTS, "total": len(ENGAGEMENTS)}
        if entity == "CBusinessEvaluation":
            return {"list": [{"id": "be1", "evaluationArea": "Finance"}], "total": 1}
        raise AssertionError(entity)

    async def metadata(self, key):
        if key == "entityDefs.CMentorProfile.fields":
            return {f: {} for f in ("mentorTitle", "mentorSummary", "aboutMentor",
                                    "fluentLanguages")}
        if key == "entityDefs.CBusinessEvaluation":
            return {"fields": {"status": {}}}
        return None


class Claude:
    """A fake AsyncAnthropic: records the request, returns ``reply``."""

    def __init__(self, reply=None, stop_reason="end_turn", boom=None):
        self.calls = []
        self.reply = reply if reply is not None else match.MatchReply(
            client_needs="Cash flow help before a busy season.",
            mentor_kind="Someone who ran a food business.",
            suggestions=[match.Suggestion(mentor_id="m1", reason="Ran a bakery."),
                         match.Suggestion(mentor_id="m2", reason="Strong fit, but at capacity."),
                         match.Suggestion(mentor_id="m99", reason="Invented.")],
            points_to_check=["The revenue question was not answered."])
        self.stop_reason, self.boom = stop_reason, boom
        outer = self

        class _Messages:
            async def parse(self, **kw):
                outer.calls.append(kw)
                if outer.boom is not None:
                    raise outer.boom
                return SimpleNamespace(model=kw["model"], stop_reason=outer.stop_reason,
                                       parsed_output=outer.reply,
                                       usage=SimpleNamespace(input_tokens=5000, output_tokens=800))

        self.beta = SimpleNamespace(messages=_Messages())


class Store:
    def __init__(self):
        self.rows = []

    async def add(self, **kw):
        row = {"id": len(self.rows) + 1, "engagementId": kw["engagement_id"],
               "runAt": "2026-11-19T22:00:00+00:00", "runByName": kw["run_by_name"],
               "model": kw["model"], "promptVersion": kw["prompt_version"],
               "cost": kw["cost"], "result": kw["result"]}
        self.rows.append(row)
        return row

    async def latest(self, engagement_id):
        rows = [r for r in self.rows if r["engagementId"] == engagement_id]
        return rows[-1] if rows else None


def _app(monkeypatch, crm, claude, *, store=None, logged=None, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("assignments.auth.current_user", lambda request: _STAFF)
    monkeypatch.setattr("assignments.router.client_for", lambda settings, user: crm)

    async def log_action(**kw):
        if logged is not None:
            logged.append(kw)
        return True

    monkeypatch.setattr("core.action_log.log_action", log_action)
    app = create_app([info_request.SPEC])
    app.state.evaluation_client = lambda: crm
    app.state.mentor_match_claude = lambda: claude
    app.state.mentor_match_store = store
    return app


URL = f"/assignments/api/engagements/{ENG}/mentor-match"


@pytest.fixture(autouse=True)
def _clear():
    yield
    get_settings.cache_clear()


def _sent(claude) -> dict:
    return json.loads(claude.calls[0]["messages"][0]["content"])


def test_the_switch_off_shows_no_tab_and_the_routes_answer_404(monkeypatch):
    claude = Claude()
    with TestClient(_app(monkeypatch, Crm(), claude)) as c:
        assert c.get("/assignments/api/session").json()["mentorMatchEnabled"] is False
        assert c.get(URL).status_code == 404
        assert c.post(URL).status_code == 404
    assert claude.calls == []


def test_a_run_suggests_named_mentors_with_their_room_and_is_logged(monkeypatch):
    claude, store, logged = Claude(), Store(), []
    with TestClient(_app(monkeypatch, Crm(), claude, store=store, logged=logged,
                         MENTOR_MATCH="true")) as c:
        assert c.get("/assignments/api/session").json()["mentorMatchEnabled"] is True
        assert c.get(URL).json()["latest"] is None
        res = c.post(URL)
        assert res.status_code == 200, res.text
        run = res.json()["latest"]
        r = run["result"]
        assert [s["name"] for s in r["suggestions"]] == ["Joe Mentor", "Ann Full"]
        assert r["suggestions"][0]["available"] == 2 and r["suggestions"][0]["atCapacity"] is False
        assert r["suggestions"][1]["atCapacity"] is True
        # Doug 11-20-26: each suggestion carries when the mentor last got a new client.
        assert r["suggestions"][0]["lastAssigned"] == "2026-11-18"
        assert r["suggestions"][1]["lastAssigned"] == "not recorded"
        assert r["dropped"] == 1                       # m99 was never sent
        assert run["runByName"] == "Kitty Cat" and run["promptVersion"] == "mentor-match.v1"
        # Kept: the tab opens on the latest run.
        assert c.get(URL).json()["latest"]["id"] == run["id"]
    [entry] = logged
    assert entry["action"] == "Mentor Match Run" and entry["parent_id"] == ENG
    assert entry["actor_name"] == "Kitty Cat" and entry["outcome"] == "Success"
    assert entry["details"]["cost"] > 0 and entry["details"]["suggested"] == ["m1", "m2"]
    # The organization's name is filled into the prompt.
    assert "{{org}}" not in claude.calls[0]["system"]


def test_no_contact_details_reach_the_ai_service(monkeypatch):
    claude = Claude()
    with TestClient(_app(monkeypatch, Crm(), claude, MENTOR_MATCH="true")) as c:
        assert c.post(URL).status_code == 200
    text = claude.calls[0]["messages"][0]["content"]
    for leak in ("216-555-0142", "dana@brightline.example", "1234 Euclid",
                 "joe@home.example", "440-555-0199", "@cbmentors.example", "Dana Testbaker"):
        assert leak not in text, leak
    sent = _sent(claude)
    assert sent["client"]["company"] == "Brightline Bakehouse"
    assert sent["client"]["intake_needs"].startswith("[name] here. Cash flow is tight")
    assert "Dana" not in text
    assert sent["client"]["evaluation_areas_picked"] == ["Finance"]
    joe = next(m for m in sent["mentors"] if m["id"] == "m1")
    assert joe["headline"] == "Retired bakery owner"
    assert "Twelve years in food" in joe["website_about"] and "<b>" not in joe["website_about"]
    assert "cbmEmail" not in json.dumps(joe) and "email" not in joe


def test_only_eligible_mentors_are_sent_and_capacity_is_marked(monkeypatch):
    claude = Claude()
    with TestClient(_app(monkeypatch, Crm(), claude, MENTOR_MATCH="true")) as c:
        assert c.post(URL).status_code == 200
    sent = {m["id"]: m for m in _sent(claude)["mentors"]}
    assert set(sent) == {"m1", "m2"}                   # inactive, paused, no login: never sent
    assert sent["m2"]["at_capacity"] is True and sent["m2"]["available"] == 0
    assert sent["m1"]["at_capacity"] is False and sent["m1"]["active_clients"] == 1


def test_an_assigned_engagement_is_refused_with_the_mentor_named(monkeypatch):
    claude = Claude()
    with TestClient(_app(monkeypatch, Crm(mentor_id="m1"), claude, MENTOR_MATCH="true")) as c:
        res = c.post(URL)
        assert res.status_code == 400
        assert "already assigned to Joe Mentor" in res.json()["detail"]
        assert c.get(URL).json()["assignedTo"] == "Joe Mentor"
    assert claude.calls == []


@pytest.mark.parametrize("claude, status, words", [
    (Claude(stop_reason="refusal"), 400, "declined"),
    (Claude(stop_reason="max_tokens"), 400, "cut off"),
    (Claude(boom=RuntimeError("connection reset")), 502, "could not be reached"),
])
def test_a_refused_or_failed_call_is_a_message_never_a_500(monkeypatch, claude, status, words):
    logged = []
    with TestClient(_app(monkeypatch, Crm(), claude, logged=logged, MENTOR_MATCH="true"),
                    raise_server_exceptions=False) as c:
        res = c.post(URL)
    assert res.status_code == status and words in res.json()["detail"]
    [entry] = logged
    assert entry["outcome"] == "Failed"


def test_without_a_key_the_run_says_so(monkeypatch):
    claude = Claude()
    app = _app(monkeypatch, Crm(), claude, MENTOR_MATCH="true", ANTHROPIC_API_KEY="")
    with TestClient(app) as c:
        res = c.post(URL)
    assert res.status_code == 400 and "Anthropic API key" in res.json()["detail"]
    assert claude.calls == []


def test_the_result_assigns_only_through_the_mentor_popup_and_its_confirmation():
    """Doug 11-20-26: a suggested mentor's name opens the mentor popup with this
    engagement in context, so its Assign this mentor button assigns (through the
    usual confirmation). The tab itself carries no Assign button or call."""
    js = (ROOT / "assignments/frontend/app.js").read_text(encoding="utf-8")
    block = js[js.index("function renderMentorMatch"):js.index("async function loadMentorMatch")]
    assert "/assign" not in block and "performAssign" not in block and "doReassign" not in block
    assert 'mode: "assign", fromMatch: true' in block
    assert not re.search(r"textContent\s*=\s*\"Assign", block)
    handler = js[js.index('$("mentorDetailAssignBtn").addEventListener'):]
    handler = handler[:handler.index("});")]
    assert "doAssign(" in handler and "closeModal(true)" in handler


def test_the_prompt_file_loads_and_names_its_version():
    prompt = match.current_prompt()
    assert prompt.ref == "mentor-match.v1"
    assert "Fit comes first, room second" in prompt.system


def test_plain_text_strips_html_and_contact_details():
    assert match.plain("<p>Hi&nbsp;there</p><p>Call 216-555-0142</p>") == "Hi\xa0there\nCall [removed]"
    assert len(match.plain("word " * 2000)) <= match.TEXT_MAX + 2


def test_the_run_reads_no_report_field():
    src = (ROOT / "evaluation/match.py").read_text(encoding="utf-8")
    assert "draftReport" not in src and "reviewedReport" not in src


def test_mentor_ids_in_the_text_become_names():
    mentors = [{"id": "6a1b2c3d4e5f6a7b8", "name": "Joe Mentor", "active_clients": 1,
                "maximum_clients": 3, "available": 2, "at_capacity": False},
               {"id": "s05", "name": "Ann Full", "active_clients": 2, "maximum_clients": 2,
                "available": 0, "at_capacity": True}]
    reply = match.MatchReply(
        client_needs="Needs cash help.", mentor_kind="A finance mentor like s05.",
        suggestions=[match.Suggestion(mentor_id="6a1b2c3d4e5f6a7b8",
                                      reason="Better than Ann Full (s05).")],
        points_to_check=["Ask 6a1b2c3d4e5f6a7b8 about time; s05, s050 look alike."])
    r = match.shape_result(reply, mentors, [])
    assert r["mentorKind"] == "A finance mentor like Ann Full."
    assert r["suggestions"][0]["reason"] == "Better than Ann Full."
    assert r["pointsToCheck"] == ["Ask Joe Mentor about time; Ann Full, s050 look alike."]
