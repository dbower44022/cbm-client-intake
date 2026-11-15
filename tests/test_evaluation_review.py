"""Business Evaluation phase 4, review and approval (evaluation/review.py and
the Evaluations routes on Client Management): the reviewed report saved as
the user and the draft never written (BE17), every reviewer editing (BE18),
a save over a newer one refused, the approval withdrawn by a later edit,
Approve by the mentor only, the review session's readiness and link, the
action log, and the switch off."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from evaluation import review, sending, service
from forms import info_request
from tests.survey_fakes import MemoryStore

ENG = "6612engagement001"
OTHER_ENG = "6612engagement999"
DRAFT = "<h2>Finance</h2><p>draft</p>"
REVIEWED = ('<h2>Finance</h2><p>draft</p><div data-internal="true">'
            "<h3>Points to check (for reviewers only)</h3><ul><li>x</li></ul></div>")

JOE = {"userId": "u-mentor", "userName": "joe.mentor", "name": "Joe Mentor",
       "isAdmin": False, "teams": ["Mentor Team"], "roles": [], "token": "t"}
MATT = {"userId": "u-comentor", "userName": "matt.mentor", "name": "Matt Mentor",
        "isAdmin": False, "teams": ["Mentor Team"], "roles": [], "token": "t"}


def _rec(rid, area, status, rnd=1, **kw):
    return {"id": rid, "engagementId": ENG, "evaluationArea": area, "evaluationRound": rnd,
            "status": status, "draftReport": DRAFT, "reviewedReport": REVIEWED,
            "modifiedByName": "Matt Mentor", **kw}


class FakeCrm:
    """Enough of the CRM for review: the engagement and its mentor profile,
    the records, the engagement's sessions. ``refuse_link`` makes a user's
    write naming ``approvedById`` or ``reviewSessionId`` a 403."""

    def __init__(self, records=None, *, refuse_link=False, sessions=None):
        self.records = list(records or [])
        self.updates: list[tuple[str, str, dict]] = []
        self.refuse_link = refuse_link
        self.sessions = sessions if sessions is not None else [
            {"id": "s-future", "name": "Next meeting", "status": "Scheduled",
             "dateStart": "2099-01-05 15:00:00", "engagementId": ENG},
            {"id": "s-past", "name": "Old", "status": "Scheduled",
             "dateStart": "2000-01-05 15:00:00", "engagementId": ENG},
            {"id": "s-done", "name": "Done", "status": "Completed",
             "dateStart": "2099-02-05 15:00:00", "engagementId": ENG},
            {"id": "s-other", "name": "Elsewhere", "status": "Scheduled",
             "dateStart": "2099-01-05 15:00:00", "engagementId": OTHER_ENG},
        ]

    async def metadata(self, key):
        return {"fields": {"status": {}}} if key == f"entityDefs.{service.ENTITY}" else None

    async def get(self, entity, record_id, select=None):
        if entity == "CEngagement":
            return {"id": ENG, "mentorProfileId": "mp-joe", "mentorProfileName": "Joe Mentor"}
        if entity == "CMentorProfile":
            return {"id": record_id, "assignedUsersIds": ["u-mentor"]}
        if entity == "CSession":
            for s in self.sessions:
                if s["id"] == record_id:
                    return dict(s)
        if entity == service.ENTITY:
            for r in self.records:
                if r["id"] == record_id:
                    return dict(r)
        raise EspoError(f"get {entity}/{record_id} failed: HTTP 404")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        rows = [r for r in self.records if r.get("engagementId") == where[0]["value"]]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def list_related(self, entity, record_id, link, select=None, max_size=50, **kw):
        assert link == review.ENGAGEMENT_SESSIONS_LINK
        return {"list": [s for s in self.sessions if s["engagementId"] == record_id]}

    async def update(self, entity, record_id, payload):
        if self.refuse_link and ("approvedById" in payload or "reviewSessionId" in payload):
            raise EspoError(f"update {entity} failed: HTTP 403 Forbidden")
        self.updates.append((entity, record_id, payload))
        for r in self.records:
            if r["id"] == record_id:
                r.update(payload)
        return {"id": record_id, **payload}

    async def create(self, entity, payload):
        return {"id": "n1"}


def run(coro):
    return asyncio.run(coro)


# --- saving the reviewed report ----------------------------------------------------

def test_a_save_writes_only_the_reviewed_report_never_the_draft():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    new = REVIEWED.replace("draft</p>", "corrected</p>")
    out = run(review.save_report(crm, ENG, "r1", html=new, base=REVIEWED))
    assert out["changed"] is True and out["warning"] is None
    assert crm.updates == [(service.ENTITY, "r1", {"reviewedReport": new})]
    assert crm.records[0]["draftReport"] == DRAFT


def test_an_unchanged_save_writes_nothing():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    out = run(review.save_report(crm, ENG, "r1", html=REVIEWED + "  ", base=REVIEWED))
    assert out["changed"] is False and crm.updates == []


def test_a_save_over_someone_elses_newer_save_is_refused_naming_them():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    with pytest.raises(review.Conflict, match="Matt Mentor saved this report"):
        run(review.save_report(crm, ENG, "r1", html="<p>mine</p>", base="<p>what I opened</p>"))
    assert crm.updates == []


def test_editing_an_approved_report_withdraws_the_approval():
    crm = FakeCrm([_rec("r1", "Finance", "Approved", approvedById="u-mentor",
                        approvedByName="Joe Mentor", approvedAt="2026-11-14 10:00:00")])
    out = run(review.save_report(crm, ENG, "r1", html="<p>changed</p>" + REVIEWED, base=REVIEWED))
    assert out["approvalWithdrawn"] is True and out["status"] == "Draft Ready"
    payload = crm.updates[0][2]
    assert payload["status"] == "Draft Ready"
    assert payload["approvedAt"] is None and payload["approvedById"] is None
    assert out["fields"]["status"] == {"from": "Approved", "to": "Draft Ready"}


def test_a_report_without_a_draft_cannot_be_edited():
    crm = FakeCrm([_rec("r1", "Finance", "Submitted")])
    with pytest.raises(review.ReviewError, match="while the evaluation is Submitted"):
        run(review.save_report(crm, ENG, "r1", html="<p>x</p>", base=None))


def test_a_record_of_another_engagement_is_refused():
    crm = FakeCrm([{**_rec("r1", "Finance", "Draft Ready"), "engagementId": OTHER_ENG}])
    with pytest.raises(review.ReviewError, match="not on this engagement"):
        run(review.save_report(crm, ENG, "r1", html="<p>x</p>", base=None))


def test_losing_the_reviewers_only_marker_is_warned():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    stripped = REVIEWED.replace(' data-internal="true"', "")
    out = run(review.save_report(crm, ENG, "r1", html=stripped, base=REVIEWED))
    assert out["warning"] and "reviewers-only marker" in out["warning"]
    # Deleting the whole section is a reviewer's choice, not a warning.
    crm2 = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    out2 = run(review.save_report(crm2, ENG, "r1", html="<p>short</p>", base=REVIEWED))
    assert out2["warning"] is None


# --- Approve -------------------------------------------------------------------------

def test_the_mentor_approves():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    out = run(review.approve(crm, ENG, "r1", user_id="u-mentor"))
    payload = crm.updates[0][2]
    assert payload["status"] == "Approved" and payload["approvedById"] == "u-mentor"
    assert payload["approvedAt"] == out["approvedAt"]


def test_a_co_mentor_is_refused_approve_with_the_mentor_named():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    with pytest.raises(review.NotTheMentor, match="Only the engagement's mentor, Joe Mentor"):
        run(review.approve(crm, ENG, "r1", user_id="u-comentor"))
    assert crm.updates == []


def test_approve_needs_a_draft_ready_report():
    crm = FakeCrm([_rec("r1", "Finance", "Submitted"),
                   _rec("r2", "Marketing", "Approved", approvedByName="Joe Mentor")])
    with pytest.raises(review.ReviewError, match="no report to approve yet"):
        run(review.approve(crm, ENG, "r1", user_id="u-mentor"))
    with pytest.raises(review.ReviewError, match="already approved by Joe Mentor"):
        run(review.approve(crm, ENG, "r2", user_id="u-mentor"))


def test_an_approve_refused_as_the_user_is_written_under_the_org_key():
    user, key = FakeCrm([_rec("r1", "Finance", "Draft Ready")], refuse_link=True), FakeCrm()
    run(review.approve(user, ENG, "r1", user_id="u-mentor", escalate=lambda: key))
    assert key.updates and key.updates[0][2]["status"] == "Approved"


# --- the review session -----------------------------------------------------------------

def test_a_round_with_a_report_not_approved_is_not_ready():
    ready = review.readiness([_rec("a", "Finance", "Approved"), _rec("b", "Marketing", "Draft Ready")])
    assert ready["ready"] is False and ready["waiting"] == ["Marketing"]
    ready = review.readiness([_rec("a", "Finance", "Approved"), _rec("b", "Marketing", "Expired")])
    assert ready["ready"] is True and ready["approved"] == ["Finance"]
    assert review.readiness([_rec("b", "Marketing", "Sent")])["ready"] is False


def test_the_view_offers_only_upcoming_scheduled_sessions_of_this_engagement():
    crm = FakeCrm([_rec("a", "Finance", "Approved")])
    view = run(review.review_session_view(crm, ENG, 1))
    assert view["ready"] is True and [s["id"] for s in view["upcoming"]] == ["s-future"]
    assert view["current"] is None


def test_linking_sets_the_session_on_every_record_of_the_round():
    crm = FakeCrm([_rec("a", "Finance", "Approved"), _rec("b", "Marketing", "Expired"),
                   _rec("c", "Finance", "Draft Ready", rnd=2)])
    out = run(review.link_review_session(crm, ENG, 1, "s-future"))
    assert sorted(out["records"]) == ["a", "b"]
    assert all(u[2] == {"reviewSessionId": "s-future"} for u in crm.updates)


def test_linking_is_refused_while_not_ready_or_for_another_engagements_session():
    crm = FakeCrm([_rec("a", "Finance", "Draft Ready")])
    with pytest.raises(review.ReviewError, match="Still waiting: Finance"):
        run(review.link_review_session(crm, ENG, 1, "s-future"))
    crm = FakeCrm([_rec("a", "Finance", "Approved")])
    with pytest.raises(review.ReviewError, match="not on this engagement"):
        run(review.link_review_session(crm, ENG, 1, "s-other"))
    assert crm.updates == []


def test_the_tab_rows_carry_the_approval_and_the_review_session():
    crm = FakeCrm([_rec("a", "Finance", "Approved", approvedByName="Joe Mentor",
                        reviewSessionId="s-future", reviewSessionName="Next meeting")])
    rounds = run(sending.rounds_view(crm, None, ENG))
    assert rounds[0]["reviewSession"] == {"id": "s-future", "name": "Next meeting"}
    assert rounds[0]["records"][0]["approvedBy"] == "Joe Mentor"


# --- the routes ------------------------------------------------------------------------

def _app(monkeypatch, *, user=JOE, on=True, crm=None):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("BUSINESS_EVALUATION", "true" if on else "false")
    get_settings.cache_clear()
    crm = crm or FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: crm)
    app = create_app([info_request.SPEC])
    app.state.survey_store = MemoryStore()
    return app, crm


@pytest.fixture
def recorded(monkeypatch):
    out = []

    async def fake_record(client, **kw):
        out.append(kw)

    monkeypatch.setattr("core.action_log.record_action", fake_record)
    return out


BASE = f"/mentorsessions/api/records/{ENG}/evaluations"


def test_switch_off_hides_every_review_route(monkeypatch):
    app, crm = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        assert c.put(f"{BASE}/r1/report", json={"html": "<p>x</p>"}).status_code == 404
        assert c.post(f"{BASE}/r1/approve").status_code == 404
        assert c.get(f"{BASE}/rounds/1/review-session").status_code == 404
        assert c.post(f"{BASE}/rounds/1/review-session", json={"sessionId": "s"}).status_code == 404
    assert crm.updates == []


def test_a_co_mentor_saves_and_the_save_is_recorded(monkeypatch, recorded):
    app, crm = _app(monkeypatch, user=MATT)
    with TestClient(app) as c:
        r = c.put(f"{BASE}/r1/report", json={"html": "<p>Matt's fix</p>", "base": REVIEWED})
    assert r.status_code == 200, r.text
    assert r.json()["changed"] is True
    assert crm.updates[0][2] == {"reviewedReport": "<p>Matt's fix</p>"}
    assert recorded[0]["action"] == "Evaluation Report Edited"
    assert recorded[0]["actor_name"] == "Matt Mentor"
    assert "reviewed report" in recorded[0]["details"]["fields"]


def test_a_stale_save_answers_409(monkeypatch, recorded):
    app, _ = _app(monkeypatch)
    with TestClient(app) as c:
        r = c.put(f"{BASE}/r1/report", json={"html": "<p>x</p>", "base": "<p>old</p>"})
    assert r.status_code == 409 and "saved this report after you opened it" in r.json()["detail"]
    assert recorded == []


def test_approve_route_mentor_and_co_mentor(monkeypatch, recorded):
    app, crm = _app(monkeypatch, user=MATT)
    with TestClient(app) as c:
        r = c.post(f"{BASE}/r1/approve")
    assert r.status_code == 403 and "Joe Mentor" in r.json()["detail"]
    assert crm.updates == [] and recorded == []
    app, crm = _app(monkeypatch, user=JOE)
    with TestClient(app) as c:
        r = c.post(f"{BASE}/r1/approve")
    assert r.status_code == 200 and r.json()["approvedBy"] == "Joe Mentor"
    assert recorded[0]["action"] == "Evaluation Approved"
    assert recorded[0]["details"]["fields"]["status"] == {"from": "Draft Ready", "to": "Approved"}


def test_review_session_routes(monkeypatch, recorded):
    app, crm = _app(monkeypatch, crm=FakeCrm([_rec("a", "Finance", "Approved")]))
    with TestClient(app) as c:
        view = c.get(f"{BASE}/rounds/1/review-session").json()
        assert view["ready"] is True and view["upcoming"][0]["id"] == "s-future"
        assert c.post(f"{BASE}/rounds/1/review-session", json={"sessionId": ""}).status_code == 400
        r = c.post(f"{BASE}/rounds/1/review-session", json={"sessionId": "s-future"})
    assert r.status_code == 200 and r.json()["session"]["name"] == "Next meeting"
    assert recorded[0]["action"] == "Evaluation Review Session Linked"
    assert recorded[0]["details"]["fields"]["review session"]["to"] == "Next meeting"


def test_the_page_carries_the_editor_approve_and_the_review_session():
    js = open("sessions/frontend/app.js", encoding="utf-8").read()
    assert "function evlReviewScreen" in js and "CBMRichText.create(base" in js
    assert '"/approve"' in js and '"/report"' in js
    assert "Schedule review session" in js and "evlReviewRound" in js
    # No upload hook: images are refused in the report (Doug, 11-14-26).
    screen = js[js.index("function evlReviewScreen"):js.index("// --- The review session")]
    assert "uploadImage" not in screen


def test_a_save_returns_the_text_as_stored_for_the_next_conflict_check():
    crm = FakeCrm([_rec("r1", "Finance", "Draft Ready")])
    out = run(review.save_report(crm, ENG, "r1", html="<p>new</p>", base=REVIEWED))
    assert out["stored"] == "<p>new</p>"
    again = run(review.save_report(crm, ENG, "r1", html="<p>newer</p>", base=out["stored"]))
    assert again["changed"] is True
