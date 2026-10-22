"""The calendar file attached to a registration confirmation (D3).

One ``VEVENT`` in a ``VCALENDAR``, built by hand: the file is six lines of
plain text and a library would be the heaviest thing in the module. Times are
written in UTC with a ``Z`` suffix, which every calendar client converts to
the reader's own zone — the same choice Zoom's own invitations make — so no
``VTIMEZONE`` block is needed.

Two rules from RFC 5545 that matter for a file a phone will open: text values
escape ``\\``, ``;``, ``,`` and newlines; and no physical line exceeds 75
octets, so long values are folded onto continuation lines that start with one
space.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def _escape(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold at 75 octets (RFC 5545 § 3.1); continuation lines begin with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out: list[str] = []
    chunk = bytearray()
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not out else 74
        if len(chunk) + len(b) > limit:
            out.append(chunk.decode("utf-8"))
            chunk = bytearray()
        chunk.extend(b)
    if chunk:
        out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    *,
    uid: str,
    summary: str,
    start: datetime,
    end: Optional[datetime],
    description: str = "",
    location: str = "",
    url: str = "",
    organizer_name: str = "",
    organizer_email: str = "",
    now: Optional[datetime] = None,
) -> str:
    """The text of a one-event calendar file.

    ``end`` falls back to one hour after ``start`` so the entry always has a
    length; a CRM event with no ``dateEnd`` would otherwise produce a file some
    clients refuse.
    """
    moment = now or datetime.now(timezone.utc)
    finish = end or (start + timedelta(hours=1))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CBM Client Intake//Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{_escape(uid)}",
        f"DTSTAMP:{_stamp(moment)}",
        f"DTSTART:{_stamp(start)}",
        f"DTEND:{_stamp(finish)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if url:
        lines.append(f"URL:{url}")
    if organizer_email:
        cn = f";CN={_escape(organizer_name)}" if organizer_name else ""
        lines.append(f"ORGANIZER{cn}:mailto:{organizer_email}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def attachment(ics_text: str, *, filename: str = "event.ics") -> dict[str, Any]:
    """The shape ``comms.service.resolve_attachments`` accepts for a local file."""
    import base64

    return {
        "filename": filename,
        "contentType": "text/calendar",
        "dataBase64": base64.b64encode(ics_text.encode("utf-8")).decode("ascii"),
    }
