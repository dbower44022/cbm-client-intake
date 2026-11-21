"""The feedback survey emails (decision 7, wording approved by Doug 11-20-26).

The wording lives in this repository, versioned, as the evaluation emails do
(ruling BE9). A wording change bumps ``VERSION``. Every value is escaped. Version 2
(11-21-26, Doug): no possessive of the organization's name ("the staff of
{org}", not "{org}'s staff").

The automatic emails go from the shared mailbox (decision 7). They promise
the client who reads the answers: "Your answers go to the staff of {org}
and to your mentor." Keep that line wherever a mentor will read the answers.

Two further fillings follow the approved wording for sends the decisions
placed but did not word (noted for Doug's review at the closing):

* a staff member's on-demand mentoring survey (Mentor Administration, from
  the shared mailbox) uses the session milestone email without "for a few
  sessions now";
* a mentor's own on-demand survey opens in the composer in the mentor's
  voice, and says the answers go to the mentor and to staff. The mentor
  edits it before sending.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

VERSION = "feedback.v2"


def _greeting(first_name: str) -> str:
    name = (first_name or "").strip()
    return f"Hello {html.escape(name)}," if name else "Hello,"


def _link(url: str, label: str = "Answer the survey") -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _body(paragraphs: list[str]) -> str:
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def long_date(at: datetime) -> str:
    """"November 10"."""
    return f"{at:%B} {at.day}"


def _with(mentor_first: str, company: str) -> str:
    parts = []
    if (mentor_first or "").strip():
        parts.append(f"with {html.escape(mentor_first.strip())}")
    if (company or "").strip():
        parts.append(f"on {html.escape(company.strip())}")
    return " ".join(parts)


def session_milestone(*, org: str, first_name: str, mentor_first: str, company: str,
                      link_url: str, on_demand: bool = False) -> dict[str, str]:
    """The session milestone email; ``on_demand`` drops "for a few sessions
    now" for a staff member's send."""
    esc = html.escape
    working = _with(mentor_first, company)
    working = f" {working}" if working else ""
    when = "" if on_demand else " for a few sessions now"
    paragraphs = [
        _greeting(first_name),
        f"You have been working{working}{when}, and we would like to know how it is going. "
        "The survey takes about two minutes, and only the first question is needed.",
        _link(link_url),
        f"Your answers go to the staff of {esc(org)} and to your mentor.",
        f"Thank you,<br>{esc(org)}",
    ]
    return {"subject": "How is your mentoring going?", "bodyHtml": _body(paragraphs),
            "version": VERSION}


def engagement_closed(*, org: str, first_name: str, mentor_first: str, company: str,
                      link_url: str) -> dict[str, str]:
    esc = html.escape
    working = _with(mentor_first, company)
    working = f" {working}" if working else ""
    paragraphs = [
        _greeting(first_name),
        f"Your mentoring{working} has come to an end, and we would like to know how it went. "
        "The survey takes about two minutes, and only the first question is needed.",
        _link(link_url),
        f"Your answers go to the staff of {esc(org)} and to your mentor.",
        f"Thank you,<br>{esc(org)}",
    ]
    return {"subject": f"How was your mentoring with {org}?", "bodyHtml": _body(paragraphs),
            "version": VERSION}


def evaluation_released(*, org: str, first_name: str, mentor_first: str,
                        link_url: str) -> dict[str, str]:
    esc = html.escape
    who = esc(mentor_first.strip()) if (mentor_first or "").strip() else "Your mentor"
    paragraphs = [
        _greeting(first_name),
        f"{who} recently went through your business evaluation with you, and we would like "
        "to know how useful it was. The survey takes about two minutes, and only the first "
        "question is needed.",
        _link(link_url),
        f"Your answers go to the staff of {esc(org)} and to your mentor.",
        f"Thank you,<br>{esc(org)}",
    ]
    return {"subject": "How useful was your business evaluation?",
            "bodyHtml": _body(paragraphs), "version": VERSION}


def event(*, org: str, first_name: str, event_name: str, event_date: Optional[datetime],
          link_url: str) -> dict[str, str]:
    esc = html.escape
    name = (event_name or "").strip() or "our event"
    on = f" on {long_date(event_date)}" if event_date else ""
    paragraphs = [
        _greeting(first_name),
        f"Thank you for attending {esc(name)}{on}. Tell us what was useful and what we "
        "should cover next. It takes about two minutes.",
        _link(link_url),
        f"Thank you,<br>{esc(org)}",
    ]
    return {"subject": f'How was "{name}"?', "bodyHtml": _body(paragraphs),
            "version": VERSION}


def mentor_on_demand(*, org: str, first_name: str, company: str,
                     link_url: str) -> dict[str, str]:
    """What the composer opens with when a mentor sends the mentoring survey
    themself; the composer adds their signature."""
    esc = html.escape
    on = f" on {esc(company.strip())}" if (company or "").strip() else ""
    paragraphs = [
        _greeting(first_name),
        f"I would like to know how our work together{on} is going. The survey takes about "
        "two minutes, and only the first question is needed.",
        _link(link_url),
        f"Your answers go to me and to the staff of {esc(org)}.",
    ]
    return {"subject": "How is your mentoring going?", "bodyHtml": _body(paragraphs),
            "version": VERSION}


def alert(*, org: str, survey_title: str, about: str, score: Optional[int],
          reasons: list[str], who: str, link_url: str) -> dict[str, str]:
    """The follow-up alert to the responsible team (decision 4). Internal."""
    esc = html.escape
    shown = f"{score} out of 10" if score is not None else "not given"
    paragraphs = [
        f"A {esc(survey_title.lower())} response needs follow-up.",
        f"<strong>About:</strong> {esc(about)}<br><strong>From:</strong> {esc(who)}<br>"
        f"<strong>Recommendation score:</strong> {esc(shown)}<br>"
        f"<strong>Why:</strong> {esc('; '.join(reasons))}.",
        _link(link_url, "Open the response"),
        "Mark the follow-up done there, with a note, once someone has acted on it.",
        esc(org),
    ]
    subject = f"Feedback to follow up: {about}" if about else "Feedback to follow up"
    return {"subject": subject, "bodyHtml": _body(paragraphs), "version": VERSION}
