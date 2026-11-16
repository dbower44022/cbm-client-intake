"""Business Evaluation phase 5, release and action items (evaluation/release.py
and the Evaluations routes on Client Management): the client version without
any reviewers-only section and made from the reviewed report (BE17, BE19),
release by the engagement's mentor only, refused before approval and before
a review session, the action items written (BE20), a released report locked,
the release email, and the switch off."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from evaluation import email as eval_email
from evaluation import release, report, review, service
from forms import info_request

ENG = "6612engagement001"
OTHER_ENG = "6612engagement999"
DRAFT_ONLY = "WORDS-ONLY-IN-THE-DRAFT"


def _reviewed() -> str:
    rep = report.Report(
        summary="A busy bakery.", scores=[], strengths=[], gaps=[],
        action_items=[
            report.ActionItem(title="Work out what a cake costs", reason="Costs rose.",
                              priority="High", time_horizon="Next 30 days"),
            report.ActionItem(title="Start a customer list", reason="Birthdays repeat.",
                              priority="Medium", time_horizon="Next 90 days"),
        ],
        missing_information=["How many cake orders a month?"],
        points_to_check=["SECRET-REVIEWER-NOTE"])
    return report.render(rep, area="Marketing", company="Brightline Bakehouse",
                         dimension_names={})


def _rec(status="Approved", **kw):
    return {"id": "r1", "engagementId": ENG, "evaluationArea": "Marketing",
            "evaluationRound": 1, "status": status, "reviewedReport": _reviewed(),
            "draftReport": DRAFT_ONLY, "reviewSessionId": "s1",
            "reviewSessionName": "Review", **kw}


class FakeCrm:
    """The engagement, its mentor profile, contacts and co-mentors, one
    evaluation record, the review session and the action items made."""

    def __init__(self, rec=None, *, items_entity=True, refuse_create=False):
        self.rec = rec if rec is not None else _rec()
        self.items: list[dict] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.creates: list[tuple[str, dict]] = []
        self.items_entity = items_entity
        self.refuse_create = refuse_create

    async def metadata(self, key):
        if key == f"entityDefs.{release.ACTION_ITEM}":
            return {"fields": {"status": {}}} if self.items_entity else None
        return None

    async def get(self, entity, record_id, select=None):
        if entity == "CEngagement":
            return {"id": ENG, "mentorProfileId": "mp-joe", "mentorProfileName": "Joe Mentor",
                    "primaryEngagementContactId": "c-dana",
                    "primaryEngagementContactName": "Dana Whitcomb",
                    "clientOrganizationName": "Brightline Bakehouse",
                    "assignedUsersIds": ["u-mentor", "u-comentor"]}
        if entity == "CMentorProfile":
            return {"id": record_id, "assignedUsersIds": ["u-mentor"], "name": "Joe Mentor",
                    "contactRecordId": "c-joe", "contactRecordName": "Joe Mentor"}
        if entity == "CSession":
            return {"id": record_id, "dateStart": "2026-11-16 15:00:00"}
        if entity == service.ENTITY and record_id == self.rec["id"]:
            return dict(self.rec)
        if entity == release.ACTION_ITEM:
            for it in self.items:
                if it["id"] == record_id:
                    return dict(it)
        if entity == "Contact":
            return {"name": "Dana Whitcomb", "firstName": "Dana", "emailAddress": "dana@example.com"}
        raise EspoError(f"get {entity}/{record_id} failed: HTTP 404")

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        rows = [i for i in self.items if all(i.get(w["attribute"]) == w["value"] for w in where)]
        return {"total": len(rows), "list": rows[offset:offset + max_size]}

    async def list_related(self, entity, record_id, link, select=None, max_size=50, **kw):
        if link == "engagementContacts":
            return {"list": [{"id": "c-dana", "name": "Dana Whitcomb"},
                             {"id": "c-sam", "name": "Sam Whitcomb"}]}
        if link == "additionalMentors":
            return {"list": [{"id": "mp-matt", "name": "Matt Mentor", "contactRecordId": "c-matt",
                              "contactRecordName": "Matt Mentor"}]}
        return {"list": []}

    async def create(self, entity, payload):
        if self.refuse_create:
            raise EspoError(f"create {entity} failed: HTTP 403 Forbidden")
        row = {"id": f"ai{len(self.items) + 1}", **payload}
        self.items.append(row)
        self.creates.append((entity, payload))
        return row

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        if entity == service.ENTITY:
            self.rec.update(payload)
        for it in self.items:
            if it["id"] == record_id:
                it.update(payload)
        return {"id": record_id, **payload}


def run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)
AGREED = [{"title": "Work out what a cake costs", "reason": "Costs rose.", "ownerId": "c-dana",
           "due": "2026-12-16", "priority": "High", "timeHorizon": "Next 30 days"},
          {"title": "Start a customer list", "ownerId": "c-joe", "due": "2027-02-14"}]


class Filer:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, html, filename):
        self.calls.append((html, filename))
        return {"id": "doc1", "filename": filename}


def _release(crm, *, user="u-mentor", items=AGREED, filer=None, escalate=None):
    return run(release.release(crm, ENG, "r1", user_id=user, items=items, org="Cleveland Business Mentors",
                               file_document=filer or Filer(), escalate=escalate, now=NOW))


# --- the client version (BE19) ------------------------------------------------------

def test_the_client_version_drops_every_reviewers_only_section():
    body = release.client_body(_reviewed())
    assert "SECRET-REVIEWER-NOTE" not in body and "Points to check" not in body
    assert "data-internal" not in body
    assert "Summary" in body and "Questions to explore" in body
    # The report's own title is replaced by the document's header.
    assert "<h2>" not in body


def test_any_element_marked_internal_is_dropped_not_only_the_div():
    html = '<p>keep</p><p data-internal="true">reviewer note</p><span data-internal>x</span>'
    assert release.client_body(html) == "<p>keep</p>"


def test_the_released_document_is_made_from_the_reviewed_report_never_the_draft():
    crm, filer = FakeCrm(), Filer()
    _release(crm, filer=filer)
    html, filename = filer.calls[0]
    assert DRAFT_ONLY not in html and "SECRET-REVIEWER-NOTE" not in html
    assert "Marketing evaluation: Brightline Bakehouse" in html
    assert "Prepared with you by Joe Mentor" in html
    assert "Reviewed together on November 16, 2026" in html
    assert "Action items we agreed" in html and "December 16, 2026" in html
    assert filename == "Brightline Bakehouse - Marketing evaluation - 2026-11-16.pdf"


def test_the_action_items_are_read_from_the_reviewed_reports_table():
    items = release.parse_action_items(_reviewed())
    assert [i["title"] for i in items] == ["Work out what a cake costs", "Start a customer list"]
    assert items[0]["reason"] == "Costs rose." and items[0]["priority"] == "High"
    assert items[1]["timeHorizon"] == "Next 90 days"
    assert release.parse_action_items("<p>no table</p>") == []


def test_the_dialog_gets_items_with_due_dates_from_the_review_session_and_the_owners():
    view = run(release.release_view(FakeCrm(), ENG, "r1", org="X"))
    assert view["blocked"] == "" and view["reviewedOn"] == "2026-11-16"
    assert [i["due"] for i in view["items"]] == ["2026-12-16", "2027-02-14"]
    assert [(o["id"], o["kind"]) for o in view["owners"]] == [
        ("c-dana", "client"), ("c-sam", "client"), ("c-joe", "mentor"), ("c-matt", "mentor")]
    assert view["defaultOwner"] == "c-dana"
    assert "SECRET-REVIEWER-NOTE" not in view["clientHtml"]


# --- Release ------------------------------------------------------------------------------

def test_the_mentor_releases_items_then_document_then_status():
    crm = FakeCrm()
    out = _release(crm)
    assert [c[0] for c in crm.creates] == [release.ACTION_ITEM, release.ACTION_ITEM]
    first = crm.creates[0][1]
    assert first["engagementId"] == ENG and first["businessEvaluationId"] == "r1"
    assert first["ownerId"] == "c-dana" and first["dueDate"] == "2026-12-16"
    assert first["status"] == "Open" and first["priority"] == "High"
    assert first["assignedUsersIds"] == ["u-mentor", "u-comentor"]
    assert "priority" not in crm.creates[1][1]
    assert crm.updates[-1] == (service.ENTITY, "r1", {
        "status": "Reviewed with Client", "releasedAt": "2026-11-16 18:00:00"})
    assert out["agreed"] == 2 and out["document"]["id"] == "doc1"
    assert out["fields"]["status"] == {"from": "Approved", "to": "Reviewed with Client"}


def test_a_co_mentor_is_refused_release_with_the_mentor_named():
    crm, filer = FakeCrm(), Filer()
    with pytest.raises(review.NotTheMentor, match="Only the engagement's mentor, Joe Mentor"):
        _release(crm, user="u-comentor", filer=filer)
    assert crm.creates == [] and crm.updates == [] and filer.calls == []


def test_release_is_refused_before_approval():
    crm = FakeCrm(_rec(status="Draft Ready"))
    with pytest.raises(release.ReleaseError, match="Only an approved report can be released"):
        _release(crm)
    assert crm.creates == [] and crm.updates == []


def test_release_is_refused_before_a_review_session():
    crm = FakeCrm(_rec(reviewSessionId=None))
    with pytest.raises(release.ReleaseError, match="Schedule the review session"):
        _release(crm)
    view = run(release.release_view(FakeCrm(_rec(reviewSessionId=None)), ENG, "r1", org="X"))
    assert "Schedule the review session" in view["blocked"]


def test_a_released_report_cannot_be_released_again_or_edited():
    crm = FakeCrm(_rec(status="Reviewed with Client", releasedAt="2026-11-16 18:00:00"))
    with pytest.raises(release.ReleaseError, match="already released.*final"):
        _release(crm)
    with pytest.raises(review.ReviewError, match="released to the client, so it is final"):
        run(review.save_report(crm, ENG, "r1", html="<p>x</p>", base=None))


def test_a_record_of_another_engagement_is_refused():
    crm = FakeCrm(_rec(engagementId=OTHER_ENG))
    with pytest.raises(release.ReleaseError, match="not on this engagement"):
        _release(crm)


def test_an_item_needs_wording_an_owner_and_a_date():
    owners = [{"id": "c-dana", "name": "Dana"}]
    with pytest.raises(release.ReleaseError, match="item 1 has no wording"):
        release.check_items([{"title": " ", "ownerId": "c-dana", "due": "2026-12-01"}], owners)
    with pytest.raises(release.ReleaseError, match="Choose who owns action item 1"):
        release.check_items([{"title": "A", "ownerId": "c-stranger", "due": "2026-12-01"}], owners)
    with pytest.raises(release.ReleaseError, match="a due date"):
        release.check_items([{"title": "A", "ownerId": "c-dana", "due": "soon"}], owners)


def test_a_release_with_no_items_files_and_releases():
    crm, filer = FakeCrm(items_entity=False), Filer()
    out = _release(crm, items=[], filer=filer)
    assert crm.creates == [] and out["agreed"] == 0
    assert "Action items we agreed" not in filer.calls[0][0]
    assert crm.rec["status"] == "Reviewed with Client"


def test_items_need_the_record_type_on_the_crm():
    crm = FakeCrm(items_entity=False)
    with pytest.raises(release.ReleaseError, match="action-item-crm-handoff.md"):
        _release(crm)
    assert crm.updates == []


def test_pressing_release_again_after_a_failure_makes_no_second_item():
    crm = FakeCrm()

    async def broken(html, filename):
        raise RuntimeError("Drive down")

    with pytest.raises(RuntimeError):
        _release(crm, filer=broken)
    assert len(crm.items) == 2 and crm.rec["status"] == "Approved"
    _release(crm)
    assert len(crm.items) == 2 and crm.rec["status"] == "Reviewed with Client"


def test_an_item_refused_as_the_user_is_written_under_the_org_key():
    user, key = FakeCrm(refuse_create=True), FakeCrm()
    _release(user, escalate=lambda: key)
    assert len(key.items) == 2


def test_an_item_is_marked_done_and_a_wrong_status_is_refused():
    crm = FakeCrm()
    crm.items.append({"id": "ai1", "name": "A", "status": "Open", "engagementId": ENG})
    out = run(release.set_item_status(crm, ENG, "ai1", "Done"))
    assert out["changed"] and crm.items[0]["status"] == "Done"
    assert out["fields"]["status"] == {"from": "Open", "to": "Done"}
    with pytest.raises(release.ReleaseError, match="Open, Done or Dropped"):
        run(release.set_item_status(crm, ENG, "ai1", "Finished"))
    crm.items[0]["engagementId"] = OTHER_ENG
    with pytest.raises(release.ReleaseError, match="not on this engagement"):
        run(release.set_item_status(crm, ENG, "ai1", "Open"))


def test_the_release_email():
    mail = eval_email.release(org="Cleveland Business Mentors", first_name="Dana <b>",
                              area_title="Marketing")
    assert mail["subject"] == "Your Marketing evaluation from Cleveland Business Mentors"
    assert mail["bodyHtml"].startswith("<p>Hi Dana &lt;b&gt;,</p>")
    assert "The report we discussed is attached." in mail["bodyHtml"]
    assert mail["version"] == "release.v1"
    assert eval_email.release(org="X", first_name="", area_title="Finance")["bodyHtml"].startswith("<p>Hello,")


# --- the routes ---------------------------------------------------------------------------

JOE = {"userId": "u-mentor", "userName": "joe.mentor", "name": "Joe Mentor",
       "isAdmin": False, "teams": ["Mentor Team"], "roles": [], "token": "t"}
MATT = {"userId": "u-comentor", "userName": "matt.mentor", "name": "Matt Mentor",
        "isAdmin": False, "teams": ["Mentor Team"], "roles": [], "token": "t"}
BASE = f"/mentorsessions/api/records/{ENG}"


def _app(monkeypatch, *, user=JOE, on=True, docs=True, crm=None):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("BUSINESS_EVALUATION", "true" if on else "false")
    monkeypatch.setenv("GDRIVE_DOCS", "true" if docs else "false")
    get_settings.cache_clear()
    crm = crm or FakeCrm()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: crm)
    filed: list = []

    async def fake_file(settings, store, drive, **kw):
        filed.append(kw)
        return {"id": "doc1", "filename": kw["filename"]}

    async def fake_drive(settings, client, user):
        return object()

    async def nothing(*a, **kw):
        return None

    async def fallback(cfg, client, rows):
        return None

    monkeypatch.setattr("docs.service.get_store", lambda settings: object())
    monkeypatch.setattr("docs.service.drive_for_user", fake_drive)
    monkeypatch.setattr("docs.service.file_generated_pdf", fake_file)
    monkeypatch.setattr("docs.service.post_upload_hooks", nothing)
    monkeypatch.setattr("sessions.service.fill_company_fallback", fallback)
    app = create_app([info_request.SPEC])
    return app, crm, filed


@pytest.fixture
def recorded(monkeypatch):
    out = []

    async def fake_record(client, **kw):
        out.append(kw)

    async def fake_log(**kw):
        out.append(kw)

    monkeypatch.setattr("core.action_log.record_action", fake_record)
    monkeypatch.setattr("core.action_log.log_action", fake_log)
    return out


def test_every_release_route_answers_404_while_the_switch_is_off(monkeypatch):
    app, crm, filed = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        assert c.get(f"{BASE}/evaluations/r1/release").status_code == 404
        assert c.post(f"{BASE}/evaluations/r1/release", json={"items": []}).status_code == 404
        assert c.get(f"{BASE}/actionitems").status_code == 404
        assert c.put(f"{BASE}/actionitems/ai1", json={"status": "Done"}).status_code == 404
    assert crm.updates == [] and filed == []


def test_release_without_the_document_integration_is_refused_with_a_reason(monkeypatch):
    app, crm, _ = _app(monkeypatch, docs=False)
    with TestClient(app) as c:
        r = c.post(f"{BASE}/evaluations/r1/release", json={"items": []})
    assert r.status_code == 400 and "document integration is not switched on" in r.json()["detail"]
    assert crm.updates == []


def test_release_route_files_records_and_returns_the_email(monkeypatch, recorded):
    app, crm, filed = _app(monkeypatch)
    with TestClient(app) as c:
        r = c.post(f"{BASE}/evaluations/r1/release", json={"items": AGREED})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Reviewed with Client"
    assert body["email"]["to"] == "dana@example.com"
    assert body["email"]["subject"] == "Your Marketing evaluation from Cleveland Business Mentors"
    assert body["email"]["documents"] == [{"documentId": "doc1", "filename": filed[0]["filename"]}]
    assert filed[0]["doc_type"] == "Evaluation report"
    assert "SECRET-REVIEWER-NOTE" not in filed[0]["html"] and DRAFT_ONLY not in filed[0]["html"]
    actions = [x["action"] for x in recorded]
    assert actions == ["Evaluation Released", "Action Item Agreed", "Action Item Agreed"]
    assert recorded[0]["details"]["fields"]["status"]["to"] == "Reviewed with Client"
    assert recorded[1]["details"]["fields"]["owner"]["to"] == "Dana Whitcomb"


def test_release_route_refuses_a_co_mentor(monkeypatch, recorded):
    app, crm, filed = _app(monkeypatch, user=MATT)
    with TestClient(app) as c:
        r = c.post(f"{BASE}/evaluations/r1/release", json={"items": AGREED})
        view = c.get(f"{BASE}/evaluations/r1/release")
    assert r.status_code == 403 and "Joe Mentor" in r.json()["detail"]
    assert crm.updates == [] and crm.items == [] and filed == [] and recorded == []
    assert view.status_code == 200 and len(view.json()["items"]) == 2
    assert view.json()["blocked"].startswith("Only the engagement's mentor, Joe Mentor")


def test_action_item_routes(monkeypatch, recorded):
    crm = FakeCrm()
    crm.items.append({"id": "ai1", "name": "A", "status": "Open", "engagementId": ENG,
                      "dueDate": "2026-12-16", "ownerName": "Dana Whitcomb"})
    app, _, _ = _app(monkeypatch, crm=crm)
    with TestClient(app) as c:
        listed = c.get(f"{BASE}/actionitems").json()
        assert listed["available"] is True and listed["items"][0]["owner"] == "Dana Whitcomb"
        r = c.put(f"{BASE}/actionitems/ai1", json={"status": "Done"})
        bad = c.put(f"{BASE}/actionitems/ai1", json={"status": "Finished"})
    assert r.status_code == 200 and crm.items[0]["status"] == "Done"
    assert bad.status_code == 400
    assert recorded[0]["action"] == "Action Item Status Changed"
    assert recorded[0]["details"]["fields"]["status"] == {"from": "Open", "to": "Done"}


def test_action_items_say_unavailable_on_a_crm_without_them(monkeypatch):
    app, _, _ = _app(monkeypatch, crm=FakeCrm(items_entity=False))
    with TestClient(app) as c:
        out = c.get(f"{BASE}/actionitems").json()
    assert out["available"] is False and "action-item-crm-handoff.md" in out["reason"]


def test_the_page_carries_release_and_the_action_items():
    import pathlib

    js = pathlib.Path("sessions/frontend/app.js").read_text(encoding="utf-8")
    html = pathlib.Path("sessions/frontend/index.html").read_text(encoding="utf-8")
    assert "Release to client" in js and "/release" in js and "/actionitems" in js
    assert 'id="evlItemsTable"' in html
    compose = pathlib.Path("frontend/shared/compose.js").read_text(encoding="utf-8")
    assert "pre.documents" in compose


# --- filing and reconciliation ---------------------------------------------------------

def test_a_generated_pdf_of_the_same_name_is_reused_not_filed_twice(monkeypatch):
    from docs import service as docs_service

    class Store:
        async def list_documents(self, entity, rid, include_archived=False):
            return [{"id": "doc9", "filename": "A - Marketing evaluation - 2026-11-16.pdf"}]

    class Drive:
        async def html_to_pdf(self, folder, html):  # pragma: no cover - must not run
            raise AssertionError("converted again")

    row = run(docs_service.file_generated_pdf(
        get_settings(), Store(), Drive(), entity_type="CEngagement", record_id=ENG,
        record_name="E", html="<p>x</p>", filename="A - Marketing evaluation - 2026-11-16.pdf",
        doc_type=docs_service.EVALUATION_REPORT_DOC_TYPE))
    assert row["id"] == "doc9"


def test_the_evaluation_report_type_is_accepted_but_not_offered():
    from docs import service as docs_service

    s = get_settings()
    assert docs_service.EVALUATION_REPORT_DOC_TYPE not in s.gdrive_doc_types_list
    assert docs_service._validate_upload(s, filename="a.pdf",
                                         doc_type=docs_service.EVALUATION_REPORT_DOC_TYPE,
                                         data=b"%PDF") == "a.pdf"


def test_html_to_pdf_converts_exports_and_deletes_the_temporary_doc():
    from core import gdrive

    calls = []

    class Resp:
        def json(self):
            return {"id": "tmp1"}

    drive = gdrive.DriveClient.__new__(gdrive.DriveClient)

    async def send(method, url, **kw):
        calls.append(("send", kw["content"]))
        return Resp()

    async def export_pdf(fid):
        calls.append(("export", fid))
        return b"%PDF-1.4"

    async def delete_file(fid):
        calls.append(("delete", fid))

    drive._send, drive.export_pdf, drive.delete_file = send, export_pdf, delete_file
    assert run(drive.html_to_pdf("folder1", "<p>é</p>")) == b"%PDF-1.4"
    assert b'"mimeType": "application/vnd.google-apps.document"' in calls[0][1]
    assert b'"parents": ["folder1"]' in calls[0][1] and "<p>é</p>".encode() in calls[0][1]
    assert calls[1:] == [("export", "tmp1"), ("delete", "tmp1")]


def test_the_nightly_reconciliation_includes_action_items():
    from assignments import stamps

    class Crm:
        async def metadata(self, key):
            return {"actionItems": {}, "businessEvaluations": {}}

        async def list_related(self, entity, rid, link, select=None, max_size=50):
            return {"list": [{"id": "ai1"}] if link == "actionItems" else []}

    crm = Crm()
    assert run(stamps.action_items_linked(crm)) is True
    recs = run(stamps.related_records(crm, {"id": ENG}, with_action_items=True))
    assert ("CActionItem", "ai1", "action item") in recs
    assert ("CActionItem", "ai1", "action item") not in run(stamps.related_records(crm, {"id": ENG}))
