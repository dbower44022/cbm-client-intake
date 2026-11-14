"""Business Evaluation phase 3, the analysis (evaluation/analysis.py,
evaluation/report.py, the Retry route): the prompt and rubric files, the
report schema and template, the contact-detail scrub, the worker's pick-up
and status changes, failure and Retry, the mentor's email, the draft on the
Evaluations tab, and the switch off.

No call reaches the Claude API: ``FakeClaude`` stands in for the SDK client."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from evaluation import analysis, report, sending, service
from evaluation.purpose import load_surveys
from tests.test_evaluation_mentor import ENG, PROFILE, FakeCrm, _app

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def surveys():
    loaded = load_surveys()
    assert loaded
    return loaded


@pytest.fixture(scope="module")
def files():
    return analysis.load_all()


def _settings(**kw):
    base = dict(business_evaluation=True, evaluation_analysis_seconds=300,
                anthropic_api_key="k", anthropic_in_use=True, espo_dry_run=False,
                ops_mailbox="", app_base_url="https://apps.example.org")
    base.update(kw)
    return Settings(**base)


def _report(rubric, **kw):
    data = dict(
        summary="Your records are in good shape; cash is thin.",
        scores=[report.DimensionScore(dimension_id=d.id, score=3, reason="Because.")
                for d in rubric.dimensions],
        strengths=[report.Point(point="Separate account.", evidence="You said yes.")],
        gaps=[report.Point(point="Thin cash.", evidence="Less than a month.")],
        action_items=[report.ActionItem(title="Build a cash cushion", reason="Thin cash.",
                                        priority="High", time_horizon="Next 90 days")],
        missing_information=["Revenue range."],
        points_to_check=["The owner says profitable but often short of cash."],
    )
    data.update(kw)
    return report.Report(**data)


class FakeClaude:
    """The SDK client's ``beta.messages.parse``: records each call and
    returns a canned report, or raises."""

    def __init__(self, result=None, *, stop_reason="end_turn", error=None):
        self.result, self.stop_reason, self.error = result, stop_reason, error
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(
            model=kw["model"], stop_reason=self.stop_reason, parsed_output=self.result,
            usage=SimpleNamespace(input_tokens=4000, output_tokens=3000,
                                  cache_creation_input_tokens=0, cache_read_input_tokens=0))


PROFILE_ANSWERS = {
    "what_you_sell": "Custom printing for local shops. Call me at (216) 555-0142.",
    "industry": "Manufacturing or making products", "customer_type": "Other businesses",
    "where_you_sell": ["From a shop, office or location customers visit"],
    "stage": "Open more than 3 years and steady", "people": 4,
    "owner_time": "Yes, full time", "revenue_range": "$100,000 to $250,000",
    "profitable": "About even", "goals": ["Get more customers"],
    "biggest_challenge": "Cash is tight. Email pat@halstead.example or visit 1420 Superior Avenue.",
}
FINANCE_ANSWERS = {"bookkeeping_method": "A spreadsheet", "separate_account": "Yes",
                   "cash_runway": "Less than a month", "finance_worry": "Paying the press lease."}


class AnalysisCrm(FakeCrm):
    """The worker's view of the CRM: Submitted records, the client profile,
    the engagement's mentor, and every update."""

    def __init__(self, *, profile=True, records=None, submitted_at="2026-11-14 11:50:00"):
        super().__init__(records=records)
        if profile:
            self.profile["evaluationProfile"] = json.dumps(
                {"survey": "business-profile.v1", "answers": PROFILE_ANSWERS})
        if records is None:
            self.records = [{
                "id": "be1", "name": "Finance — Halstead Print Works", "engagementId": ENG,
                "clientProfileId": PROFILE, "evaluationArea": "Finance",
                "evaluationRound": 1, "status": "Submitted", "submittedAt": submitted_at,
                "answers": json.dumps({"survey": "finance.v1", "answers": FINANCE_ANSWERS}),
            }]

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200
        if where and where[0]["attribute"] == "status":
            rows = [r for r in self.records if r.get("status") == where[0]["value"]]
            return {"total": len(rows), "list": rows[:max_size]}
        return await super().list(entity, where=where, select=select, max_size=max_size,
                                  offset=offset, order_by=order_by, order=order)

    async def get(self, entity, record_id, select=None):
        if entity == "CEngagement" and select == "mentorProfileId":
            return {"id": ENG, "mentorProfileId": "mp1"}
        if entity == "CMentorProfile":
            return {"id": "mp1", "cbmEmail": "Joe.Mentor@cbmentors.org"}
        return await super().get(entity, record_id, select)

    async def update(self, entity, record_id, payload):
        await super().update(entity, record_id, payload)
        for r in self.records:
            if r["id"] == record_id:
                r.update(payload)
        return {"id": record_id, **payload}


# --- the files (BE9) -------------------------------------------------------------

def test_every_prompt_names_a_rubric_for_its_area(files):
    prompts, rubrics = files
    assert set(prompts) == {"finance.v1", "marketing.v1"}
    for p in prompts.values():
        assert rubrics[p.rubric].area == p.area
        assert "{{org}}" in p.system


def test_every_rubric_describes_five_levels_for_each_dimension(files):
    _, rubrics = files
    for r in rubrics.values():
        assert len(r.dimensions) == 5
        for d in r.dimensions:
            assert sorted(d.levels) == [1, 2, 3, 4, 5]


def test_rubric_answers_name_real_questions(files, surveys):
    _, rubrics = files
    profile = {q.id for s in surveys["business-profile.v1"].sections for q in s.questions}
    for r in rubrics.values():
        area = {q.id for s in surveys[r.ref].sections for q in s.questions}
        for d in r.dimensions:
            for name in d.informed_by:
                if name.startswith("profile."):
                    assert name[len("profile."):] in profile, (r.ref, name)
                else:
                    assert name in area, (r.ref, name)


def test_the_two_prompts_share_their_rules_word_for_word(files):
    """Every section from WHO READS IT to THE REPORT matches, except the
    area's own words: its name, its examples, and rules 2 and 7."""
    import re

    prompts, _ = files

    def shared(p, words):
        text = " ".join(p.system[p.system.index("WHO READS IT"):p.system.index("ABOUT ")].split())
        text = re.sub(r" 2\. .*? 3\. ", " 3. ", text)
        text = re.sub(r" 7\. .*? 8\. ", " 8. ", text)
        text = re.sub(r"\(for example, .*?\)", "(EXAMPLE)", text)
        for w in words:
            text = text.replace(w, "AREA")
        return text

    assert shared(prompts["finance.v1"], ("Finance", "finances", "money")) == \
        shared(prompts["marketing.v1"], ("Marketing", "marketing"))


def test_the_system_text_carries_the_org_and_the_whole_rubric(files):
    prompts, rubrics = files
    p = prompts["finance.v1"]
    text = analysis.system_text(p, rubrics[p.rubric], Settings(organization_name="Cleveland"))
    assert "{{org}}" not in text and "Cleveland" in text
    for d in rubrics[p.rubric].dimensions:
        assert f"(id: {d.id})" in text and d.levels[5] in text


# --- the report (BE16) -----------------------------------------------------------

def test_the_template_has_every_section_in_order_and_marks_the_internal_one(files):
    _, rubrics = files
    r = rubrics["finance.v1"]
    html_out = report.render(_report(r), area="Finance", company="Halstead <Print>",
                             dimension_names={d.id: d.name for d in r.dimensions})
    order = ["Summary", "Scores", "Strengths", "Gaps", "Recommended action items",
             "Questions to explore", "Points to check (for reviewers only)"]
    positions = [html_out.index(f"<h3>{h}</h3>") for h in order]
    assert positions == sorted(positions)
    assert '<div data-internal="true"><h3>Points to check' in html_out
    assert "Halstead &lt;Print&gt;" in html_out and "<Print>" not in html_out
    assert "Record keeping" in html_out and "3 of 5" in html_out


def test_an_unscored_dimension_reads_not_scored(files):
    _, rubrics = files
    r = rubrics["finance.v1"]
    rep = _report(r, scores=[report.DimensionScore(dimension_id="cash", score=None,
                                                   reason="No sales yet.")])
    out = report.render(analysis.tidy(rep, r), area="Finance", company="X",
                        dimension_names={d.id: d.name for d in r.dimensions})
    assert out.count("Not scored") == 5   # the one given, and four the reply missed


def test_tidy_puts_scores_in_rubric_order_and_drops_strays(files):
    _, rubrics = files
    r = rubrics["marketing.v1"]
    rep = _report(r, scores=[report.DimensionScore(dimension_id=d.id, score=9, reason="x")
                             for d in reversed(r.dimensions)]
                  + [report.DimensionScore(dimension_id="nope", score=2, reason="x")])
    tidied = analysis.tidy(rep, r)
    assert [s.dimension_id for s in tidied.scores] == [d.id for d in r.dimensions]
    assert all(s.score is None for s in tidied.scores)


# --- no contact details (the build rule) -------------------------------------------

@pytest.mark.parametrize("text", [
    "Write to pat.halstead@example.com today",
    "Call (216) 555-0142", "Call 216.555.0142", "Text +1 216 555 0142",
    "We are at 1420 Superior Avenue", "Mail P.O. Box 77",
    "Suite: 200 East Ninth St.",
])
def test_scrub_removes_contact_details(text):
    out = analysis.scrub(text)
    assert "[removed]" in out
    for digits in ("555", "1420", "77", "@"):
        if digits in text:
            assert digits not in out, out


def test_scrub_keeps_ordinary_numbers():
    text = "We take in $100,000 to $250,000 a year with 4 people since 2019."
    assert analysis.scrub(text) == text


def test_nothing_sent_to_the_claude_api_carries_contact_details(files, surveys):
    crm, claude = AnalysisCrm(), FakeClaude(_report(files[1]["finance.v1"]))
    run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys, now=NOW))
    assert len(claude.calls) == 1
    sent = json.dumps(claude.calls[0], default=str)
    for detail in ("555-0142", "pat@halstead.example", "1420 Superior", "Pat Halstead",
                   "pat@example.com"):
        assert detail not in sent
    assert "Halstead Print Works" in sent           # the company name is allowed
    assert "Custom printing for local shops" in sent  # and the business profile


# --- the worker pass ---------------------------------------------------------------

def test_a_submitted_record_gets_its_draft_and_draft_ready(files, surveys):
    crm, claude = AnalysisCrm(), FakeClaude(_report(files[1]["finance.v1"]))
    told = []

    async def notify(rec):
        told.append(rec["id"])

    counts = run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys,
                                             notify=notify, now=NOW))
    assert counts["ready"] == 1 and told == ["be1"]
    rec = crm.records[0]
    assert rec["status"] == "Draft Ready"
    assert rec["draftReport"] == rec["reviewedReport"] and "<h3>Summary</h3>" in rec["draftReport"]
    assert rec["promptVersion"] == "finance.v1" and rec["rubricVersion"] == "finance.v1"
    assert rec["analyzedAt"] == "2026-11-14 12:00:00" and rec["analysisError"] == ""
    assert set(json.loads(rec["scores"])) == {d.id for d in files[1]["finance.v1"].dimensions}
    call = claude.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is report.Report
    assert call["fallbacks"] == "default" and call["thinking"] == {"type": "adaptive"}


def test_a_record_waits_a_day_for_its_business_profile(files, surveys):
    claude = FakeClaude(_report(files[1]["finance.v1"]))
    crm = AnalysisCrm(profile=False)
    counts = run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys, now=NOW))
    assert counts["waiting"] == 1 and not claude.calls and crm.records[0]["status"] == "Submitted"
    later = NOW + timedelta(days=2)
    counts = run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys, now=later))
    assert counts["ready"] == 1
    assert "has not answered the business profile" in claude.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("claude, words", [
    (FakeClaude(error=RuntimeError("overloaded")), "could not be reached"),
    (FakeClaude(None, stop_reason="refusal"), "declined"),
    (FakeClaude(None, stop_reason="max_tokens"), "cut off"),
    (FakeClaude(None), "not a report"),
])
def test_a_failed_call_sets_analysis_failed_with_the_reason(surveys, claude, words):
    crm = AnalysisCrm()
    counts = run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys, now=NOW))
    assert counts["failed"] == 1
    rec = crm.records[0]
    assert rec["status"] == "Analysis Failed" and words in rec["analysisError"]
    assert "draftReport" not in rec


def test_an_area_without_a_prompt_fails_with_a_reason(surveys):
    crm = AnalysisCrm()
    crm.records[0]["evaluationArea"] = "Competition"
    claude = FakeClaude()
    run(analysis.run_analysis_cycle(_settings(), crm, claude, surveys=surveys, now=NOW))
    assert not claude.calls
    assert "no analysis prompt for Competition" in crm.records[0]["analysisError"]


def test_a_failed_email_never_fails_the_analysis(files, surveys):
    crm = AnalysisCrm()

    async def notify(rec):
        raise RuntimeError("gmail down")

    counts = run(analysis.run_analysis_cycle(
        _settings(), crm, FakeClaude(_report(files[1]["finance.v1"])), surveys=surveys,
        notify=notify, now=NOW))
    assert counts["ready"] == 1 and crm.records[0]["status"] == "Draft Ready"


def test_the_pass_is_off_unless_every_condition_holds():
    assert analysis.enabled(_settings())
    for off in (dict(business_evaluation=False), dict(evaluation_analysis_seconds=0),
                dict(anthropic_api_key=""), dict(anthropic_in_use=False),
                dict(espo_dry_run=True)):
        assert not analysis.enabled(_settings(**off)), off


def test_the_analysis_is_off_by_default():
    assert Settings().evaluation_analysis_seconds == 0


# --- telling the mentor ------------------------------------------------------------

def test_the_mentor_email_names_the_area_company_and_tab():
    subject, body = analysis.notice_email(
        area="Finance", company="Halstead Print Works",
        url=f"https://apps.example.org/mentorsessions/record/{ENG}?tab=evaluations")
    assert "Finance — Halstead Print Works" in subject
    assert "?tab=evaluations" in body and "has not seen it" in body


def test_the_notifier_writes_to_the_mentors_cbm_email(monkeypatch):
    sent = []

    class Gmail:
        async def aclose(self):
            pass

    async def gmail_for(settings, mailbox):
        sent.append(("from", mailbox))
        return Gmail()

    async def send_quick(**kw):
        sent.append(("send", kw))

    monkeypatch.setattr("comms.service.gmail_for_shared_mailbox", gmail_for)
    monkeypatch.setattr("comms.service.send_quick_message", send_quick)
    crm = AnalysisCrm()
    notify = analysis.make_notifier(_settings(ops_mailbox="info@cbmentors.org"), crm)
    run(notify(crm.records[0]))
    assert sent[0] == ("from", "info@cbmentors.org")
    assert sent[1][1]["to"] == ["joe.mentor@cbmentors.org"]
    assert f"/mentorsessions/record/{ENG}?tab=evaluations" in sent[1][1]["body_html"]


def test_no_shared_mailbox_means_no_email(monkeypatch):
    called = []
    monkeypatch.setattr("comms.service.gmail_for_shared_mailbox",
                        lambda *a: called.append(a))
    crm = AnalysisCrm()
    run(analysis.make_notifier(_settings(ops_mailbox=""), crm)(crm.records[0]))
    assert not called


# --- the tab: the draft, and Retry (BE15, BE17) -------------------------------------

def test_the_answers_view_carries_the_draft_for_reviewers(surveys):
    crm = AnalysisCrm()
    crm.records[0].update(status="Draft Ready", draftReport="<p>draft</p>",
                          promptVersion="finance.v1", rubricVersion="finance.v1")
    view = run(sending.answers_view(crm, ENG, "be1", surveys))
    assert view["draftHtml"] == "<p>draft</p>" and view["promptVersion"] == "finance.v1"


def test_retry_puts_a_failed_record_back_in_the_queue():
    crm = AnalysisCrm()
    crm.records[0].update(status="Analysis Failed", analysisError="overloaded")
    result = run(sending.retry_analysis(crm, ENG, "be1"))
    assert result["status"] == {"from": "Analysis Failed", "to": "Submitted"}
    assert crm.records[0]["status"] == "Submitted" and crm.records[0]["analysisError"] == ""


def test_retry_names_why_on_a_record_that_did_not_fail():
    crm = AnalysisCrm()
    crm.records[0]["status"] = "Draft Ready"
    with pytest.raises(sending.SendError, match="Draft Ready, so there is nothing to retry"):
        run(sending.retry_analysis(crm, ENG, "be1"))
    with pytest.raises(sending.SendError, match="not on this engagement"):
        run(sending.retry_analysis(crm, "another", "be1"))


def test_retry_route_records_the_action(monkeypatch):
    recorded = []

    async def fake_record(client, **kw):
        recorded.append(kw)

    monkeypatch.setattr("core.action_log.record_action", fake_record)
    crm = AnalysisCrm()
    crm.records[0].update(status="Analysis Failed", analysisError="overloaded")
    app, _ = _app(monkeypatch, crm=crm)
    base = f"/mentorsessions/api/records/{ENG}/evaluations/be1/retry"
    with TestClient(app) as c:
        r = c.post(base)
        assert r.status_code == 200, r.text
        assert c.post(base).status_code == 400          # now Submitted: named, not retried
    assert len(recorded) == 1
    assert recorded[0]["action"] == "Evaluation Analysis Retried"
    assert recorded[0]["details"]["fields"] == {
        "status": {"from": "Analysis Failed", "to": "Submitted"}}


def test_switch_off_hides_retry(monkeypatch):
    app, _ = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        assert c.post(f"/mentorsessions/api/records/{ENG}/evaluations/be1/retry").status_code == 404


def test_the_tab_shows_the_draft_and_retry():
    js = open("sessions/frontend/app.js", encoding="utf-8").read()
    assert "Draft report" in js and "Retry draft report" in js
    assert "/retry" in js and 'get("tab")' in js


def test_no_code_path_emails_or_files_the_draft():
    """BE17: the draft report is written to the record and shown on the tab;
    nothing else in the application reads it."""
    import pathlib

    readers = []
    for path in pathlib.Path(".").rglob("*.py"):
        if any(part in (".venv", "tests", "node_modules") for part in path.parts):
            continue
        if "draftReport" in path.read_text(encoding="utf-8", errors="ignore"):
            readers.append(str(path))
    assert sorted(readers) == ["evaluation/analysis.py", "evaluation/report.py",
                               "evaluation/sending.py"]
