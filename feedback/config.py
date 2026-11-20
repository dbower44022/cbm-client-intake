"""The feedback surveys' constants (rulings BE29 to BE33; phases 8 and 9).

The CRM names come from ``crm-plans/survey-response.json``; the moment
values are that plan's ``moment`` options and must match them exactly (an
out-of-list value would be refused, so every write checks the live options
first through the enum filter).
"""

from __future__ import annotations

from typing import Any

#: The survey purpose key, stored on every feedback link.
PURPOSE = "feedback"

ENTITY = "CSurveyResponse"
ENGAGEMENT = "CEngagement"
EVENT = "CEvent"
REGISTRATION = "CEventRegistration"
SESSION = "CSession"
EVALUATION = "CBusinessEvaluation"
CONTACT = "Contact"

SURVEY_MENTORING = "mentoring-feedback"
SURVEY_EVENT = "event-feedback"
SURVEY_EVALUATION = "evaluation-feedback"
SURVEY_KEYS = (SURVEY_MENTORING, SURVEY_EVENT, SURVEY_EVALUATION)

MOMENT_CLOSED = "Engagement Closed"
MOMENT_SESSIONS = "Session Milestone"
MOMENT_EVENT = "Event"
MOMENT_EVALUATION = "Evaluation Released"
MOMENT_ON_DEMAND = "On Demand"
MOMENTS = (MOMENT_CLOSED, MOMENT_SESSIONS, MOMENT_EVENT, MOMENT_EVALUATION, MOMENT_ON_DEMAND)

#: The recommendation score's question id in every feedback survey.
SCORE_QUESTION = "recommend"
#: A score at or below this is a low score (BE32; the net promoter cut-off).
LOW_SCORE = 6
#: Yes/no questions whose yes sets the follow-up flag too (decision 2,
#: 11-20-26), with the reason the alert gives.
FLAG_QUESTIONS: dict[str, str] = {
    "contact_me": "they asked to be contacted about their experience",
    "talk_to_mentor": "they would like to talk with a mentor about their business",
}

#: The engagement statuses that close it (ruling 70's three, decision 6).
CLOSED_STATUSES = ("Completed", "Inactive", "Abandoned")
SESSION_COMPLETED = "Completed"
REG_ATTENDED = "Attended"
EVENT_CANCELLED = "Cancelled"
RELEASED_STATUS = "Reviewed with Client"

#: Decision 6: an event's survey goes from 24 hours after it ends to 14 days
#: after; the session milestone's the day after the session; an evaluation
#: round's three days after its first release.
EVENT_WAIT_HOURS = 24
EVENT_WINDOW_DAYS = 14
SESSION_WAIT_HOURS = 24
EVALUATION_WAIT_DAYS = 3


def score_of(answers: dict[str, Any]) -> Any:
    value = (answers or {}).get(SCORE_QUESTION)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def follow_up_reasons(answers: dict[str, Any]) -> list[str]:
    """Why a response needs follow-up, in words; empty when it does not."""
    reasons = []
    score = score_of(answers)
    if score is not None and score <= LOW_SCORE:
        reasons.append(f"a low recommendation score ({score} out of 10)")
    for qid, why in FLAG_QUESTIONS.items():
        if (answers or {}).get(qid) == "Yes":
            reasons.append(why)
    return reasons


def survey_title(key: str) -> str:
    return {SURVEY_MENTORING: "Mentoring feedback", SURVEY_EVENT: "Event feedback",
            SURVEY_EVALUATION: "Evaluation feedback"}.get(key, key)


def alert_team(settings: Any, survey_key: str) -> str:
    """The team alerted for a response (BE32): the Marketing Admin Team for
    event feedback, the Mentor Administration Team for the rest. Read from
    the team-gate settings, so a chapter that renamed a team still alerts it."""
    if survey_key == SURVEY_EVENT:
        teams = getattr(settings, "ops_allowed_teams_list", None) or ["Marketing Admin Team"]
    else:
        teams = getattr(settings, "mentor_admin_allowed_teams_list", None) \
            or ["Mentor Administration Team"]
    return teams[0]


def enabled(settings: Any) -> bool:
    return bool(getattr(settings, "feedback_surveys", False))
