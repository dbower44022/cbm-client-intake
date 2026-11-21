"""Which sessions are mentoring (Ambassador Program PRD § 4.3).

An "Ambassador Contact" session records that a mentor, acting as an
ambassador, met a partner's, funder's or client's contact. It is shown on the
record's Sessions tab so the manager or mentor sees it, but it is NOT a
meeting held with the client: no count of sessions may include it. Engagement
activation, the feedback session milestone, "no contact for N days", the
Analytics session metrics and the calendar all go through this module.

``tests/test_session_kinds.py`` lists every module that reads ``CSession`` and
fails when one does not import this module, so a new count cannot forget it.
"""

from __future__ import annotations

from typing import Any, Iterable

AMBASSADOR_SESSION_TYPE = "Ambassador Contact"


def is_ambassador(session: dict[str, Any] | None) -> bool:
    """True for an ambassador contact, which no session count includes."""
    return bool(session) and (session.get("sessionType") or "") == AMBASSADOR_SESSION_TYPE


def mentoring_only(sessions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sessions that count, ambassador contacts left out."""
    return [s for s in sessions if not is_ambassador(s)]


def where_mentoring() -> dict[str, Any]:
    """A CRM ``where`` item that leaves ambassador contacts out.

    ``notEquals`` alone would also drop every session whose type is empty
    (SQL compares NULL as unknown), so empty types are kept explicitly."""
    return {"type": "or", "value": [
        {"type": "notEquals", "attribute": "sessionType", "value": AMBASSADOR_SESSION_TYPE},
        {"type": "isNull", "attribute": "sessionType"},
    ]}
