"""The switches the worker runs with, as it reports them in its heartbeat
(prds/events/event-hosting-plan.md § 8, item 1).

A switch can be on for the web part and off for the worker, because a
deployment's specification sets environment values per component. System
Settings reads the web part's settings, so it showed Events as on while the
worker that sends every confirmation had it off (the Business Mentors
Association, 11-18-26). The worker writes :func:`snapshot` beside each beat;
Feature readiness reads it back and :func:`mismatches` names any difference in
words.

Values only: a mailbox is reported as set or not, never its address.
"""

from __future__ import annotations

from typing import Any, Optional

#: (key, what staff read). The key is the Settings attribute, except where noted.
SWITCHES: tuple[tuple[str, str], ...] = (
    ("events_enabled", "Events & Webinars"),
    ("events_confirmations", "Registration confirmation emails"),
    ("events_reminders", "Event reminder emails"),
    ("gmail_sync", "Gmail conversation sync"),
    ("ops_mailbox", "Shared mailbox set"),          # reported as a bool
    ("zoom_events", "Zoom webinar provisioning"),
    ("zoom_meetings_events", "Zoom meeting provisioning"),
    ("events_attendance", "Attendance pull"),       # events_attendance_seconds > 0
    ("espo_dry_run", "CRM dry run"),
)
LABELS = dict(SWITCHES)


def _value(settings: Any, key: str) -> bool:
    if key == "ops_mailbox":
        return bool(str(getattr(settings, "ops_mailbox", "") or "").strip())
    if key == "events_attendance":
        try:
            return int(getattr(settings, "events_attendance_seconds", 0) or 0) > 0
        except (TypeError, ValueError):
            return False
    return bool(getattr(settings, key, False))


def snapshot(settings: Any) -> dict[str, bool]:
    """This process's switches, as booleans."""
    return {key: _value(settings, key) for key, _ in SWITCHES}


def mismatches(web: Any, worker: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every switch whose value differs between the web part (``web``, a
    Settings) and the worker's reported ``worker`` snapshot. Empty when the
    worker has not reported, or a key is absent from its report (an older
    build)."""
    if not worker:
        return []
    out = []
    for key, label in SWITCHES:
        if key not in worker:
            continue
        mine, theirs = _value(web, key), bool(worker[key])
        if mine != theirs:
            out.append({"key": key, "label": label, "web": mine, "worker": theirs})
    return out


def words(row: dict[str, Any]) -> str:
    """'Events & Webinars is on for the web part and off for the worker.'"""
    def on(v: bool) -> str:
        return "on" if v else "off"
    return (f"{row['label']} is {on(row['web'])} for the web part and "
            f"{on(row['worker'])} for the worker.")
