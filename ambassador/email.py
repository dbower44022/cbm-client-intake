"""The Ambassador Program's emails, all from the shared mailbox (PRD § 4.2 item
6, § 5.1). One module holds every word, versioned like the feedback emails:
change the wording here and bump ``VERSION``.

Each function returns ``{"subject", "bodyHtml"}``. Names and notes are
escaped; ``org`` is the organization's name.
"""

from __future__ import annotations

from html import escape
from typing import Optional

VERSION = "ambassador.v1"


def _p(*lines: str) -> str:
    return "".join(f"<p>{line}</p>" for line in lines if line)


def _link(url: str, words: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(words)}</a>' if url else ""


def _note(note: str) -> str:
    if not (note or "").strip():
        return ""
    return ("<blockquote style=\"border-left:3px solid #ccc;margin:0;padding-left:10px\">"
            + escape(note.strip()).replace("\n", "<br>") + "</blockquote>")


def contact_met(*, org: str, ambassador: str, contact: str, organization: str,
                activity: str, date: str, note: str, record_words: str,
                link_url: str) -> dict[str, str]:
    """To a partner's or funder's manager, or a client's mentor: an
    ambassador met one of their record's contacts."""
    who = escape(contact) + (f" ({escape(organization)})" if organization else "")
    return {
        "subject": f"{ambassador} met {contact}" + (f" of {organization}" if organization else ""),
        "bodyHtml": _p(
            f"{escape(ambassador)}, an ambassador for {escape(org)}, reported meeting {who} "
            f"on {escape(date)}: <strong>{escape(activity)}</strong>.",
            _note(note),
            f"It is recorded as an ambassador contact on the Sessions tab of "
            f"{escape(record_words)}. It is not a mentoring session and counts as none.",
            _link(link_url, "Open the record"),
        ),
    }


def follow_up_requested(*, org: str, ambassador: str, activity: str, date: str,
                        contact: str, note: str, link_url: str) -> dict[str, str]:
    """To the review team: a mentor asked for follow-up (AM4)."""
    about = f" about {escape(contact)}" if contact else ""
    return {
        "subject": f"Ambassador follow-up requested by {ambassador}",
        "bodyHtml": _p(
            f"{escape(ambassador)} asked {escape(org)} to follow up{about}.",
            f"Activity: <strong>{escape(activity)}</strong>, on {escape(date)}.",
            _note(note),
            "Mark it done on the review list once someone has acted, with a note "
            "saying what was done. The ambassador is told.",
            _link(link_url, "Open the review list"),
        ),
    }


def follow_up_done(*, org: str, first_name: str, activity: str, date: str,
                   note: str, done_by: str) -> dict[str, str]:
    """To the mentor: their follow-up request was handled (PRD § 14 item 5)."""
    return {
        "subject": "Your ambassador follow-up was handled",
        "bodyHtml": _p(
            f"Hello {escape(first_name or '')},".replace("Hello ,", "Hello,"),
            f"Thank you for reporting <strong>{escape(activity)}</strong> on {escape(date)}. "
            f"{escape(done_by or 'The program team')} followed it up:",
            _note(note),
            f"Thank you for helping more people discover {escape(org)}.",
        ),
    }


def referral_applied(*, org: str, first_name: str, person: str, kind_words: str,
                     link_url: Optional[str] = None) -> dict[str, str]:
    """To the mentor: someone they referred has applied (AM5, AM5a)."""
    return {
        "subject": f"Your referral applied: {person}",
        "bodyHtml": _p(
            f"Hello {escape(first_name or '')},".replace("Hello ,", "Hello,"),
            f"{escape(person)}, whom you referred, has applied to {escape(org)} as a "
            f"{escape(kind_words)}. Your referral is credited to you.",
            f"Thank you for helping more people discover {escape(org)}.",
            _link(link_url or "", "See your activity"),
        ),
    }


def referral_received(*, org: str, ambassador: str, person: str, organization: str,
                      kind_words: str, note: str, link_url: str) -> dict[str, str]:
    """To the Partner or Funder Management team: an ambassador referred a
    potential partner or funder, now a Candidate in their list (AM5a)."""
    who = escape(person) + (f" of {escape(organization)}" if organization else "")
    return {
        "subject": f"Ambassador referral: {organization or person}",
        "bodyHtml": _p(
            f"{escape(ambassador)}, an ambassador for {escape(org)}, referred {who} "
            f"as a potential {escape(kind_words)}.",
            _note(note),
            "The record is in your list with the starting status, credited to the "
            "ambassador.",
            _link(link_url, "Open the record"),
        ),
    }
