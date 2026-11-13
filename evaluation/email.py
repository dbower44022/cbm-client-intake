"""The evaluation email (Business Evaluation phase 2, step 4): the subject and
body the shared composer opens with when a mentor sends or resends an
evaluation. Approved by Doug 11-13-26.

The wording lives in this repository, versioned with the surveys (ruling BE9;
Doug's choice 11-13-26 over a CRM email template): it always agrees with the
link and the areas the application fills in, and a change is a release. A
wording change bumps ``VERSION``.

The mentor edits the email in the composer before sending; this only fills
it in. The link reaches the client only through this email (ruling BE12).
"""

from __future__ import annotations

import html
from datetime import datetime

VERSION = "invitation.v1"


def join_areas(titles: list[str]) -> str:
    """"Finance", "Finance and Marketing", "Finance, Marketing and Product"."""
    titles = [t for t in titles if t]
    if len(titles) <= 1:
        return "".join(titles)
    return ", ".join(titles[:-1]) + " and " + titles[-1]


def long_date(at: datetime) -> str:
    """"December 13, 2026"."""
    return f"{at:%B} {at.day}, {at.year}"


def invitation(*, org: str, first_name: str, area_titles: list[str], link_url: str,
               expires_at: datetime, profile_needed: bool) -> dict[str, str]:
    """The email's subject and HTML body. Every value is escaped."""
    esc = html.escape
    greeting = f"Hi {esc(first_name.strip())}," if (first_name or "").strip() else "Hello,"
    first = ("You will first answer a few questions about your business, then one "
             "survey for each area. " if profile_needed else "There is one survey for each area. ")
    paragraphs = [
        greeting,
        "As we discussed, here is your free business evaluation. It covers "
        f"{esc(join_areas(area_titles))}.",
        f'<a href="{esc(link_url, quote=True)}">Start your evaluation</a>',
        first + "You can stop at any time and come back to the same link. Your answers "
        "are saved as you go.",
        f"Your answers stay with your {esc(org)} record and are seen by me and the mentors "
        "working with you. An AI service helps prepare a first draft of the results. We "
        "review every word before we go through them with you in a session.",
        f"The link works until {long_date(expires_at)}. If it stops working, reply to "
        "this email and I will send you a new one.",
    ]
    return {
        "subject": f"Your free business evaluation from {org}",
        "bodyHtml": "".join(f"<p>{p}</p>" for p in paragraphs),
        "version": VERSION,
    }
