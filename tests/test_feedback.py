"""Feedback surveys, phases 8 and 9 (rulings BE29 to BE33; decisions 1 to 8,
11-20-26): the 0-to-10 question, the three survey files, the Survey Response
write, the follow-up flag and the alert, the quiet period, the four automatic
moments, the event Survey card, the screens' routes, a mentor never reading
another mentor's responses or figures, and every switch off.

The application database is ``tests/feedback_fakes.MemoryFeedbackStore`` and
``tests/survey_fakes.MemoryStore``; the CRM is ``tests/feedback_fakes.FakeCrm``."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from feedback import config as cfg
from feedback import moments, sending, service, views
from feedback.event_send import follow_up_survey
from feedback.purpose import RULES, SURVEY_DIR, surveys
from surveys.answers import check_value, readable_html
from surveys.definitions import SurveyError, latest, load_all, parse
from tests.feedback_fakes import FakeCrm, MemoryFeedbackStore, Outbox, settings
from tests.survey_fakes import MemoryStore

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%d %H:%M:%S")


# --- the survey files and the 0-to-10 question -------------------------------------

def test_the_three_surveys_load_and_open_with_the_required_score():
    loaded = load_all(SURVEY_DIR, RULES)
    assert sorted(s.key for s in loaded.values()) == sorted(cfg.SURVEY_KEYS)
    for survey in loaded.values():
        first = survey.sections[0].questions[0]
        assert (first.id, first.type, first.required) == ("recommend", "score", True)
        assert [q.id for q in survey.questions.values() if q.required] == ["recommend"]


def test_every_question_carries_a_for_comment():
    for path in sorted(SURVEY_DIR.glob("*.yaml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if re.match(r"\s+- id: ", line):
                assert lines[i - 1].strip().startswith("# For:"), f"{path.name}: {line.strip()}"


def test_the_flag_questions_are_where_decision_2_put_them():
    loaded = surveys()
    assert "contact_me" in latest(loaded, cfg.SURVEY_MENTORING).questions
    assert {"contact_me", "talk_to_mentor"} <= set(latest(loaded, cfg.SURVEY_EVENT).questions)
    assert "contact_me" not in latest(loaded, cfg.SURVEY_EVALUATION).questions


def test_the_score_type_takes_0_to_10_only():
    q = latest(surveys(), cfg.SURVEY_MENTORING).questions["recommend"]
    assert check_value(q, 0) == (0, None)
    assert check_value(q, "10") == (10, None)
    for bad in (11, -1, "x", 7.5, True):
        assert check_value(q, bad)[1] == "Please choose a number from 0 to 10."


def test_the_score_reads_out_of_10_with_its_ends():
    survey = latest(surveys(), cfg.SURVEY_MENTORING)
    text = readable_html(survey, {"recommend": 4})
    assert "4 out of 10 (Not at all likely to Extremely likely)" in text


def test_only_scale_and_score_take_end_words(tmp_path):
    (tmp_path / "x.v1.yaml").write_text(
        "key: x\nversion: 1\ntitle: X\nintroduction: I\nsections:\n  - title: S\n    questions:\n"
        "      - id: a\n        label: A\n        type: yes_no\n        low: no\n")
    with pytest.raises(SurveyError, match="scale or score"):
        parse(tmp_path / "x.v1.yaml")


def test_a_feedback_survey_must_open_with_the_score(tmp_path):
    (tmp_path / "mentoring-feedback.v2.yaml").write_text(
        "key: mentoring-feedback\nversion: 2\ntitle: X\nintroduction: I\nsections:\n"
        "  - title: S\n    questions:\n      - id: a\n        label: A\n        type: yes_no\n")
    with pytest.raises(SurveyError, match="first question"):
        parse(tmp_path / "mentoring-feedback.v2.yaml", RULES)


def test_the_page_fills_in_the_organization_name():
    from surveys.router import _survey_view

    view = _survey_view(latest(surveys(), cfg.SURVEY_MENTORING), None)
    label = view["sections"][0]["questions"][0]["label"]
    assert "{{org}}" not in label and "recommend" in label


def test_the_follow_up_reasons():
    assert cfg.follow_up_reasons({"recommend": 6})
    assert not cfg.follow_up_reasons({"recommend": 7})
    assert cfg.follow_up_reasons({"recommend": 10, "contact_me": "Yes"})
    assert cfg.follow_up_reasons({"recommend": 9, "talk_to_mentor": "Yes"})
    assert not cfg.follow_up_reasons({})


# --- submit: the Survey Response record, the flag, the alert -------------------------

ENG = "6620engagement01"
MENTOR_PROFILE = "6620mentorprof01"


def _world(**kw):
    crm = FakeCrm()
    crm.add("CEngagement", {"id": ENG, "name": "Brightline — mentoring",
                            "clientOrganizationName": "Brightline Bakehouse",
                            "engagementStatus": "Active", "mentorProfileId": MENTOR_PROFILE,
                            "mentorProfileName": "Joe Mentor",
                            "assignedUsersIds": ["u-joe", "u-matt"],
                            "primaryEngagementContactId": "c-dana"})
    crm.add("Contact", {"id": "c-dana", "name": "Dana Testbaker", "firstName": "Dana",
                        "emailAddress": "dana@example.com", "cContactType": ["Client"]})
    team = crm.add("Team", {"id": "t-ma", "name": "Mentor Administration Team"})
    crm.add("Team", {"id": "t-mk", "name": "Marketing Admin Team"})
    crm.add("User", {"id": "u-kitty", "name": "Kitty Cat", "emailAddress": "kitty@example.org",
                     "isActive": True})
    crm.add("User", {"id": "u-mark", "name": "Mark Marketing", "emailAddress": "mark@example.org",
                     "isActive": True})
    crm.links[("Team", team["id"], "users")] = ["u-kitty"]
    crm.links[("Team", "t-mk", "users")] = ["u-mark"]
    return crm


def _link(survey_key=cfg.SURVEY_MENTORING, **data):
    base = {"survey_key": survey_key, "moment": cfg.MOMENT_SESSIONS, "contact_id": "c-dana",
            "email": "dana@example.com", "name": "Dana Testbaker", "engagement_id": ENG,
            "mentor_profile_id": MENTOR_PROFILE}
    base.update(data)
    return {"id": "l1", "data": base, "display_name": "Brightline Bakehouse",
            "consent_at": NOW - timedelta(minutes=5)}


def _submit(crm, store, outbox, answers, link=None, monkeypatch=None):
    from surveys.registry import SubmitContext

    link = link or _link()
    survey = latest(surveys(), link["data"]["survey_key"])
    row = {"answers": answers, "submitted_at": NOW}
    import feedback.alerts as alerts_mod
    import feedback.runtime as rt

    rt.use(feedback=store)
    sent_shared = alerts_mod.send_shared
    alerts_mod.send_shared = outbox
    try:
        monkeypatch.setattr("feedback.service.get_settings", lambda: settings())
        run(service.submit(SubmitContext(link=link, row=row, survey=survey, client=crm)))
    finally:
        alerts_mod.send_shared = sent_shared
        rt.use()


def test_submit_writes_the_response_with_its_links_and_the_engagement_stamp(monkeypatch):
    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    _submit(crm, store, out, {"recommend": 9, "most_helpful": "Cash flow."}, monkeypatch=monkeypatch)
    (entity, payload), = crm.created
    assert entity == "CSurveyResponse"
    assert payload["recommendScore"] == 9 and payload["needsFollowUp"] is False
    assert payload["engagementId"] == ENG and payload["mentorProfileId"] == MENTOR_PROFILE
    assert payload["contactId"] == "c-dana" and payload["assignedUsersIds"] == ["u-joe", "u-matt"]
    assert payload["moment"] == cfg.MOMENT_SESSIONS
    assert payload["surveyVersion"] == "mentoring-feedback.v1"
    assert payload["name"] == "Mentoring feedback — Dana Testbaker"
    assert json.loads(payload["answers"])["answers"]["recommend"] == 9
    assert "{{org}}" not in payload["answersReadable"]
    assert out.sent == []


def test_a_low_score_sets_the_flag_and_alerts_the_mentor_administration_team_once(monkeypatch):
    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    _submit(crm, store, out, {"recommend": 4}, monkeypatch=monkeypatch)
    assert crm.created[0][1]["needsFollowUp"] is True
    (mail,) = out.sent
    assert mail["to"] == ["kitty@example.org"]
    assert "4 out of 10" in mail["body"] and "Brightline Bakehouse" in mail["subject"]
    assert f"mentor={MENTOR_PROFILE}&amp;tab=feedback" in mail["body"]
    # The engine retries the same submit: no second record, no second alert.
    _submit(crm, store, out, {"recommend": 4}, monkeypatch=monkeypatch)
    assert len(crm.created) == 1 and len(out.sent) == 1


def test_contact_me_flags_a_high_score_too(monkeypatch):
    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    _submit(crm, store, out, {"recommend": 10, "contact_me": "Yes"}, monkeypatch=monkeypatch)
    assert crm.created[0][1]["needsFollowUp"] is True
    assert "asked to be contacted" in out.sent[0]["body"]


def test_event_feedback_carries_no_stamp_and_alerts_the_marketing_admin_team(monkeypatch):
    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    link = _link(cfg.SURVEY_EVENT, moment=cfg.MOMENT_EVENT, engagement_id="",
                 mentor_profile_id="", event_id="ev1")
    link["display_name"] = "Cash Flow Basics"
    _submit(crm, store, out, {"recommend": 8, "talk_to_mentor": "Yes"}, link=link,
            monkeypatch=monkeypatch)
    payload = crm.created[0][1]
    assert "assignedUsersIds" not in payload and payload["eventId"] == "ev1"
    assert out.sent[0]["to"] == ["mark@example.org"]
    assert "events/?event=ev1&amp;tab=feedback" in out.sent[0]["body"]


def test_a_failed_alert_never_fails_the_submit_and_the_sweep_retries_it(monkeypatch):
    crm, store = _world(), MemoryFeedbackStore()
    _submit(crm, store, Outbox(fail=True), {"recommend": 2}, monkeypatch=monkeypatch)
    assert len(crm.created) == 1 and run(store.failed_alerts())
    out = Outbox()
    counts = run(moments.run_sweep(settings(feedback_on_close=False, feedback_on_sessions=False,
                                            feedback_on_event=False, feedback_on_evaluation=False),
                                   crm, store, MemoryStore(), surveys(), sender=out, now=NOW))
    assert counts.get("alert-sent") == 1 and out.sent[0]["to"] == ["kitty@example.org"]


def test_a_team_with_no_members_falls_back_to_the_alert_address(monkeypatch):
    from feedback.alerts import alert_once

    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    crm.links[("Team", "t-ma", "users")] = []
    word = run(alert_once(settings(alert_email_to_list=["alerts@example.org"]), crm, store,
                          {"id": "r1", "surveyKey": cfg.SURVEY_MENTORING, "recommendScore": 3},
                          about="X", who="Y", reasons=["a low recommendation score"], sender=out))
    assert word == "sent" and out.sent[0]["to"] == ["alerts@example.org"]


# --- the quiet period (BE33) ---------------------------------------------------------

def _send(store, *, key, quiet, email="dana@example.com", out=None, s=None, now=NOW):
    return run(sending.send(
        s or settings(), store=store, survey_store=MemoryStore(), surveys=surveys(),
        send_key=key, survey_key=cfg.SURVEY_MENTORING, moment=cfg.MOMENT_SESSIONS,
        entity_type="CEngagement", record_id=ENG,
        who={"contactId": "c-dana", "email": email, "firstName": "Dana", "name": "Dana"},
        data={"engagement_id": ENG}, display_name="Brightline Bakehouse",
        context={"mentorFirst": "Joe", "company": "Brightline Bakehouse"}, quiet=quiet,
        sender=out or Outbox(), now=now))


def test_the_quiet_period_skips_an_automatic_send_and_records_it():
    store = MemoryFeedbackStore()
    assert _send(store, key="a", quiet=True, now=NOW - timedelta(days=2)) == "sent"
    assert _send(store, key="b", quiet=True, email=" DANA@example.com ") == "skipped:quiet period"
    assert store.sends["b"]["outcome"] == "skipped" and store.sends["b"]["reason"] == "quiet period"


def test_the_quiet_period_never_stops_a_closing_or_hand_sent_survey():
    store = MemoryFeedbackStore()
    _send(store, key="a", quiet=True, now=NOW - timedelta(days=2))
    assert _send(store, key="closed:x", quiet=False) == "sent"


def test_the_quiet_period_ends_and_zero_turns_it_off():
    store = MemoryFeedbackStore()
    _send(store, key="a", quiet=True, now=NOW - timedelta(days=31))
    assert _send(store, key="b", quiet=True) == "sent"
    store2 = MemoryFeedbackStore()
    _send(store2, key="a", quiet=True, now=NOW - timedelta(days=1))
    assert _send(store2, key="b", quiet=True, s=settings(feedback_quiet_days=0)) == "sent"


def test_a_send_is_never_made_twice_and_a_failure_is_retried_three_times():
    store = MemoryFeedbackStore()
    out = Outbox()
    assert _send(store, key="k", quiet=False, out=out) == "sent"
    assert _send(store, key="k", quiet=False, out=out) == "already"
    assert len(out.sent) == 1
    bad = MemoryFeedbackStore()
    for _ in range(3):
        assert _send(bad, key="f", quiet=False, out=Outbox(fail=True)) == "failed"
    assert _send(bad, key="f", quiet=False, out=out) == "already"


def test_members_opted_out_and_address_less_people_are_skipped():
    store = MemoryFeedbackStore()
    assert _send(store, key="m", quiet=False, email="joe@example-mentors.org") \
        == "skipped:a member of the organization"
    assert _send(store, key="n", quiet=False, email="") == "skipped:no email address"


def test_the_email_says_who_reads_the_answers_and_carries_the_link():
    out = Outbox()
    _send(MemoryFeedbackStore(), key="k", quiet=False, out=out)
    mail = out.sent[0]
    assert mail["subject"] == "How is your mentoring going?"
    assert "Joe on Brightline Bakehouse for a few sessions now" in mail["body"]
    assert "Example Mentors's staff and to your mentor" in mail["body"]
    assert "https://apps.example.org/survey/" in mail["body"]


# --- the four automatic moments (BE30) -----------------------------------------------

def _moment_world():
    crm = _world()
    eng = crm.data["CEngagement"][ENG]
    eng.update(engagementStatus="Completed", closeDate=(NOW - timedelta(days=1)).strftime("%Y-%m-%d"),
               modifiedAt=stamp(NOW - timedelta(days=1)))
    for i, days in enumerate((40, 20, 3)):
        crm.add("CSession", {"id": f"s{i}", "engagementId": ENG, "status": "Completed",
                             "dateStart": stamp(NOW - timedelta(days=days))})
    return crm


def _sweep(crm, store, out, **kw):
    return run(moments.run_sweep(settings(**kw), crm, store, MemoryStore(), surveys(),
                                 sender=out, now=NOW))


def test_an_engagement_that_closes_is_surveyed_once():
    crm, store, out = _moment_world(), MemoryFeedbackStore(), Outbox()
    _sweep(crm, store, out, feedback_on_sessions=False, feedback_on_event=False,
           feedback_on_evaluation=False)
    _sweep(crm, store, out, feedback_on_sessions=False, feedback_on_event=False,
           feedback_on_evaluation=False)
    assert len(out.sent) == 1
    assert out.sent[0]["subject"] == "How was your mentoring with Example Mentors?"
    assert store.sends[f"closed:{ENG}"]["outcome"] == "sent"


def test_closing_and_the_milestone_in_one_pass_send_only_the_closing_survey():
    crm, store, out = _moment_world(), MemoryFeedbackStore(), Outbox()
    _sweep(crm, store, out, feedback_on_event=False, feedback_on_evaluation=False)
    assert len(out.sent) == 1
    assert store.sends[f"sessions:{ENG}"]["reason"] == "the closing survey went instead"


def test_a_closed_engagement_without_a_completed_session_or_from_before_is_not_surveyed():
    crm, store, out = _moment_world(), MemoryFeedbackStore(), Outbox()
    for s in crm.data["CSession"].values():
        s["status"] = "Cancelled"
    _sweep(crm, store, out, feedback_on_sessions=False)
    crm2 = _moment_world()
    crm2.data["CEngagement"][ENG]["closeDate"] = "2025-03-01"
    _sweep(crm2, store, out, feedback_on_sessions=False)
    assert out.sent == []


def test_the_session_milestone_follows_the_setting_and_waits_a_day():
    crm, store, out = _moment_world(), MemoryFeedbackStore(), Outbox()
    crm.data["CEngagement"][ENG]["engagementStatus"] = "Active"
    _sweep(crm, store, out, feedback_on_close=False)
    assert len(out.sent) == 1 and out.sent[0]["subject"] == "How is your mentoring going?"
    # With the milestone at 4 sessions, three are not enough.
    out2 = Outbox()
    _sweep(crm, MemoryFeedbackStore(), out2, feedback_on_close=False, feedback_session_count=4)
    assert out2.sent == []
    # A third session under a day old waits.
    crm.data["CSession"]["s2"]["dateStart"] = stamp(NOW - timedelta(hours=5))
    out3 = Outbox()
    _sweep(crm, MemoryFeedbackStore(), out3, feedback_on_close=False)
    assert out3.sent == []


def _event_world(audience="Public", ended_hours=30):
    crm = _world()
    crm.add("CEvent", {"id": "ev1", "name": "Cash Flow Basics", "status": "Held",
                       "audience": audience, "publishToWebsite": True,
                       "dateStart": stamp(NOW - timedelta(hours=ended_hours + 1)),
                       "dateEnd": stamp(NOW - timedelta(hours=ended_hours))})
    crm.add("CEventRegistration", {"id": "r1", "eventId": "ev1", "attendanceStatus": "Attended",
                                   "email": "ann@example.com", "firstName": "Ann", "lastName": "A"})
    crm.add("CEventRegistration", {"id": "r2", "eventId": "ev1", "attendanceStatus": "No-Show",
                                   "email": "bo@example.com", "firstName": "Bo"})
    return crm


def test_a_public_event_surveys_its_attendees_once_after_a_day():
    crm, store, out = _event_world(), MemoryFeedbackStore(), Outbox()
    only_event = dict(feedback_on_close=False, feedback_on_sessions=False,
                      feedback_on_evaluation=False)
    _sweep(crm, store, out, **only_event)
    _sweep(crm, store, out, **only_event)
    assert [m["to"] for m in out.sent] == [["ann@example.com"]]
    assert out.sent[0]["subject"] == 'How was "Cash Flow Basics"?'
    out2 = Outbox()
    _sweep(_event_world(ended_hours=5), MemoryFeedbackStore(), out2, **only_event)
    _sweep(_event_world(audience="Internal"), MemoryFeedbackStore(), out2, **only_event)
    _sweep(_event_world(ended_hours=24 * 15), MemoryFeedbackStore(), out2, **only_event)
    assert out2.sent == []


def test_a_released_round_is_surveyed_once_three_days_after_its_first_release():
    crm, store, out = _world(), MemoryFeedbackStore(), Outbox()
    for i, days in enumerate((4, 3.5)):
        crm.add("CBusinessEvaluation", {"id": f"be{i}", "engagementId": ENG, "evaluationRound": 1,
                                        "status": "Reviewed with Client",
                                        "releasedAt": stamp(NOW - timedelta(days=days))})
    only = dict(feedback_on_close=False, feedback_on_sessions=False, feedback_on_event=False)
    _sweep(crm, store, out, **only)
    _sweep(crm, store, out, **only)
    assert len(out.sent) == 1
    assert out.sent[0]["subject"] == "How useful was your business evaluation?"
    link_data = store.sends[f"evaluation:{ENG}:1"]
    assert link_data["outcome"] == "sent"


def test_every_moment_switched_off_sends_nothing():
    crm, store, out = _moment_world(), MemoryFeedbackStore(), Outbox()
    _sweep(crm, store, out, feedback_on_close=False, feedback_on_sessions=False,
           feedback_on_event=False, feedback_on_evaluation=False)
    assert out.sent == [] and store.sends == {}
    assert _sweep(crm, store, out, feedback_surveys=False) == {}


# --- the event Survey card ----------------------------------------------------------

def test_the_survey_card_previews_then_sends_and_the_sweep_never_repeats_it():
    crm, store, out = _event_world(), MemoryFeedbackStore(), Outbox()
    regs = list(crm.data["CEventRegistration"].values())
    event = crm.data["CEvent"]["ev1"]
    plan = run(follow_up_survey(settings(), crm, event, store=store, survey_store=MemoryStore(),
                                surveys=surveys(), registrations=regs, dry_run=True, sender=out))
    assert [r["email"] for r in plan["recipients"]] == ["ann@example.com"] and out.sent == []
    ledger = []

    async def record_sent(client, reg, kind):
        ledger.append((reg["id"], kind))
        return True

    sent = run(follow_up_survey(settings(), crm, event, store=store, survey_store=MemoryStore(),
                                surveys=surveys(), registrations=regs, dry_run=False, sender=out,
                                record_sent=record_sent))
    assert sent["sent"] == 1 and ledger == [("r1", "Survey")]
    _sweep(crm, store, out, feedback_on_close=False, feedback_on_sessions=False,
           feedback_on_evaluation=False)
    assert len(out.sent) == 1
    again = run(follow_up_survey(settings(), crm, event, store=store, survey_store=MemoryStore(),
                                 surveys=surveys(), registrations=regs, dry_run=True, sender=out))
    assert again["skipped"][0]["reason"] == "already sent the survey"


# --- reads: a mentor never reads another mentor's responses --------------------------

def _responses(crm):
    crm.add("CSurveyResponse", {"id": "rj", "surveyKey": cfg.SURVEY_MENTORING, "engagementId": ENG,
                                "mentorProfileId": MENTOR_PROFILE, "recommendScore": 4,
                                "needsFollowUp": True, "followUpDone": False,
                                "submittedAt": stamp(NOW),
                                "answers": json.dumps({"survey": "mentoring-feedback.v1",
                                                       "answers": {"recommend": 4}})})
    crm.add("CSurveyResponse", {"id": "rx", "surveyKey": cfg.SURVEY_MENTORING,
                                "engagementId": "other", "mentorProfileId": "other-mentor",
                                "recommendScore": 10, "submittedAt": stamp(NOW)})


def test_a_mentor_reads_only_the_responses_the_crm_shows_them():
    crm = _world()
    _responses(crm)
    crm.visible = {"rj"}          # the Mentor Role's read own: stamped with Joe only
    assert [r["id"] for r in run(views.list_responses(crm, "mentorProfileId", "other-mentor"))] == []
    with pytest.raises(Exception):
        run(views.detail(crm, "rx"))
    view = run(views.detail(crm, "rj"))
    assert view["sections"][0]["items"][0]["values"] == ["4 out of 10 (Not at all likely to Extremely likely)"]
    assert view["reasons"]


def test_mark_done_needs_a_note_and_records_old_and_new():
    crm = _world()
    _responses(crm)
    with pytest.raises(views.FollowUpError):
        run(views.mark_done(crm, "rj", "  "))
    result = run(views.mark_done(crm, "rj", "Phoned Dana; she is happy now.", now=NOW))
    assert crm.data["CSurveyResponse"]["rj"]["followUpDone"] is True
    assert result["fields"]["followUpDone"] == {"from": False, "to": True}
    with pytest.raises(views.FollowUpError, match="already"):
        run(views.mark_done(crm, "rj", "again"))


def test_no_feedback_figure_is_on_a_page_a_mentor_can_open():
    import analytics  # noqa: F401
    from analytics.registry import PAGE_REGISTRY

    page = PAGE_REGISTRY["feedback"]
    assert "Mentor Team" not in page.team_gate
    by_mentor = next(p for p in page.panels if p.key == "by_mentor")
    assert set(by_mentor.visibility) == {"Mentor Administration Team", "Analytics Admin Team"}
    for key, p in PAGE_REGISTRY.items():
        if p.scope == "CEngagement" or key == "record-engagement":
            assert not any("feedback" in panel.metric_key for panel in p.panels)


def test_the_net_promoter_score():
    from analytics.feedback import average, nps

    assert nps([10, 9, 8, 7, 6, 0]) == 0
    assert nps([10, 10, 9, 5]) == 50
    assert nps([]) is None and average([8, 9]) == 8.5


# --- switches off: every page as before ----------------------------------------------

_MENTOR_USER = {"userId": "u-joe", "userName": "joe.mentor", "name": "Joe Mentor",
                "isAdmin": False, "teams": ["Mentor Team", "Mentor Administration Team",
                                            "Marketing Admin Team", "Events Team"],
                "roles": [], "token": "t"}


def _app(monkeypatch, *, on: bool, crm=None):
    from core.app import create_app
    from core.config import get_settings
    from forms import info_request

    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("FEEDBACK_SURVEYS", "true" if on else "false")
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    get_settings.cache_clear()
    crm = crm or _world()
    for mod in ("sessions.router", "mentoradmin.router", "events.router"):
        monkeypatch.setattr(f"{mod}.current_user", lambda request, key=None: _MENTOR_USER)
        monkeypatch.setattr(f"{mod}.client_for", lambda settings, user: crm)
    app = create_app([info_request.SPEC])
    app.state.survey_store = MemoryStore()
    return app, crm


def test_switch_off_hides_the_tab_and_every_route(monkeypatch):
    app, _ = _app(monkeypatch, on=False)
    with TestClient(app) as c:
        tabs = [t["key"] for t in c.get("/mentorsessions/api/session").json()["detailTabs"]]
        assert "feedback" not in tabs
        for method, path in (
            ("get", f"/mentorsessions/api/records/{ENG}/feedback"),
            ("post", f"/mentorsessions/api/records/{ENG}/feedback/send"),
            ("get", f"/mentoradmin/api/mentors/{MENTOR_PROFILE}/feedback"),
            ("post", "/mentoradmin/api/feedback/rj/done"),
            ("get", "/events/api/events/ev1/feedback"),
            ("post", "/events/api/feedback/rj/done"),
        ):
            res = getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
            assert res.status_code == 404, (path, res.status_code)
        assert c.get("/mentoradmin/api/session").json()["feedbackEnabled"] is False


def test_switch_off_leaves_analytics_as_before(monkeypatch):
    import analytics  # noqa: F401
    from analytics.registry import PAGE_REGISTRY, page_switched_off, switched_off

    off = settings(feedback_surveys=False)
    assert page_switched_off(PAGE_REGISTRY["feedback"], off)
    assert all(switched_off(p.metric_key, off) for p in PAGE_REGISTRY["record-mentor"].panels
               if "feedback" in p.metric_key)
    assert not switched_off("mentor_active_clients", off)


def test_switch_on_the_tab_follows_evaluations_and_the_mentor_reads_its_responses(monkeypatch):
    crm = _world()
    _responses(crm)
    monkeypatch.setenv("BUSINESS_EVALUATION", "true")
    app, _ = _app(monkeypatch, on=True, crm=crm)
    with TestClient(app) as c:
        tabs = [t["key"] for t in c.get("/mentorsessions/api/session").json()["detailTabs"]]
        assert tabs.index("feedback") == tabs.index("evaluations") + 1
        body = c.get(f"/mentorsessions/api/records/{ENG}/feedback").json()
        assert [r["id"] for r in body["responses"]] == ["rj"]
        assert body["contacts"][0]["id"] == "c-dana"
        # A response that is not on this engagement is refused.
        assert c.get(f"/mentorsessions/api/records/{ENG}/feedback/rx").status_code == 404


def test_partner_and_funder_management_never_carry_the_tab():
    from sessions.config import MENTOR, PARTNER, SPONSOR

    assert MENTOR.feedback_tab and not PARTNER.feedback_tab and not SPONSOR.feedback_tab


# --- the nightly reconciliation includes Survey Responses ----------------------------

def test_the_stamp_reconciliation_includes_survey_responses():
    from assignments import stamps

    crm = _world()
    crm.add("CSurveyResponse", {"id": "sr1"})
    crm.links[("CEngagement", ENG, "surveyResponses")] = ["sr1"]
    recs = run(stamps.related_records(crm, {"id": ENG}, with_survey_responses=True))
    assert ("CSurveyResponse", "sr1", "survey response") in recs
    assert ("CSurveyResponse", "sr1", "survey response") not in run(
        stamps.related_records(crm, {"id": ENG}))


def test_the_new_tables_are_reset_on_the_sandbox():
    from core.sandbox_reset import RESET_TABLES

    assert {"feedback_send", "feedback_alert"} <= set(RESET_TABLES)


def test_the_feedback_teams_open_analytics_for_the_feedback_page_only_while_on():
    from analytics.registry import PAGE_REGISTRY
    from analytics.router import _can_view_page, feedback_viewer

    staff = {"teams": ["Mentor Administration Team"], "roles": [], "isAdmin": False}
    mentor = {"teams": ["Mentor Team"], "roles": [], "isAdmin": False}
    on = settings(analytics_view_allowed_teams_list=["Analytics Admin Team"])
    off = settings(feedback_surveys=False, analytics_view_allowed_teams_list=["Analytics Admin Team"])
    assert feedback_viewer(staff, on) and not feedback_viewer(staff, off)
    assert not feedback_viewer(mentor, on)
    assert _can_view_page(staff, PAGE_REGISTRY["feedback"], on)
    assert not _can_view_page(staff, PAGE_REGISTRY["system-overview"], on)
    assert not _can_view_page(mentor, PAGE_REGISTRY["feedback"], on)
