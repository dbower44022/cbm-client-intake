"""The browser's own failures, written to the server log (v0.260.0).

A request that never reaches the server leaves no trace in any server log: a
dropped connection, a timeout the page gave up on, a script error. On the
Phase 2 live pass (10-17-26) a Campaign Management save failed in Doug's
browser with "Failed to fetch" and nothing anywhere recorded it. Doug's ruling
(option A): the browser reports its failures here, and each one becomes one
WARNING line in the web log with the fixed prefix ``client-error``.

    POST /api/client-errors     → 204, always (a report never errors back)

What a report may carry — and nothing else is read:

* ``kind``: ``network`` (the request never got an answer), ``timeout``,
  ``http`` (a 5xx answer), ``script`` (an uncaught error) or ``rejection``
  (an unhandled promise rejection);
* the request's ``method`` and ``url`` **path** (the query string is dropped
  in the browser and again here), ``status``, ``ms`` (time until the failure);
* ``page`` (the page's path), ``message`` (the error text, 300 characters at
  most), ``queued`` (how many seconds the report waited before it got through).

Never a request body and never a form field: a public form's failure is
reported by its address alone. The signed-in staff user, when there is one,
is read from the session, never from the report.

Bounded three ways: a body cap (8 KB), a per-address limit of its own (so
reports can never use up a visitor's submission allowance), and the browser
sends at most twenty per page. Over the limit a report is dropped silently —
one WARNING line per address per window says so.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from fastapi import APIRouter, Request, Response

log = logging.getLogger("cbm_intake.client_errors")

PATH = "/api/client-errors"
MAX_BODY = 8 * 1024
LIMIT_PER_WINDOW = 30
WINDOW_SECONDS = 300
KINDS = frozenset({"network", "timeout", "http", "script", "rejection"})
_METHOD = re.compile(r"^[A-Z]{3,7}$")
_hits: dict[str, list[float]] = {}
_warned: dict[str, float] = {}

router = APIRouter(tags=["client-errors"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _allowed(ip: str, now: float) -> bool:
    hits = [t for t in _hits.get(ip, []) if now - t < WINDOW_SECONDS]
    if len(hits) >= LIMIT_PER_WINDOW:
        _hits[ip] = hits
        if now - _warned.get(ip, 0) > WINDOW_SECONDS:
            _warned[ip] = now
            log.warning("client-error reports from %s over the limit — dropping until the window passes", ip)
        return False
    hits.append(now)
    _hits[ip] = hits
    return True


def _text(value: Any, limit: int) -> str:
    """One printable line, at most ``limit`` characters — a report is caller
    data and must never be able to forge or break a log line."""
    if value is None:
        return ""
    s = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = "".join(ch for ch in s if ch.isprintable())
    return s[:limit]


def _path_only(value: Any) -> str:
    """A path, never a query string or another site's address."""
    s = _text(value, 300)
    if "://" in s:
        s = "/" + s.split("://", 1)[1].partition("/")[2]
    return s.split("?", 1)[0].split("#", 1)[0] or "-"


def _int(value: Any, lo: int, hi: int) -> Optional[int]:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _user(request: Request) -> str:
    if "session" not in request.scope:
        return "-"
    try:
        from assignments.auth import SESSION_KEY

        user = request.session.get(SESSION_KEY) or {}
    except Exception:  # noqa: BLE001 — never fail a report over the session
        return "-"
    return _text(user.get("userName"), 80) or "-"


def format_line(report: dict[str, Any], *, user: str, agent: str) -> Optional[str]:
    """The log line for one report, or None when it is not a report at all."""
    kind = _text(report.get("kind"), 20)
    if kind not in KINDS:
        return None
    method = _text(report.get("method"), 7).upper()
    method = method if _METHOD.match(method) else "-"
    status = _int(report.get("status"), 0, 999)
    ms = _int(report.get("ms"), 0, 86_400_000)
    queued = _int(report.get("queued"), 0, 86_400)
    parts = [
        f"client-error kind={kind}",
        f"page={_path_only(report.get('page'))}",
        f"request={method} {_path_only(report.get('url'))}",
        f"status={status if status is not None else '-'}",
        f"ms={ms if ms is not None else '-'}",
        f"user={user}",
    ]
    if queued:
        parts.append(f"queued={queued}s")
    parts.append(f"agent={_text(agent, 120) or '-'}")
    parts.append(f"message={_text(report.get('message'), 300) or '-'}")
    return " ".join(parts)


@router.post(PATH, include_in_schema=False)
async def client_errors(request: Request) -> Response:
    try:
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_BODY:
            return Response(status_code=204)
        if not _allowed(_client_ip(request), time.time()):
            return Response(status_code=204)
        body = await request.body()
        if len(body) > MAX_BODY:
            return Response(status_code=204)
        import json

        data = json.loads(body or b"{}")
        reports = data.get("reports") if isinstance(data, dict) else None
        if isinstance(data, dict) and reports is None:
            reports = [data]
        if not isinstance(reports, list):
            return Response(status_code=204)
        user = _user(request)
        agent = request.headers.get("user-agent", "")
        for report in reports[:20]:
            line = format_line(report, user=user, agent=agent) if isinstance(report, dict) else None
            if line:
                log.warning(line)
            else:
                # Visible, so a report that writes nothing can be explained
                # (10-17-26: one arrived on the live pass and left no line).
                log.info("client-error-unread kind=%s keys=%s",
                         _text(report.get("kind") if isinstance(report, dict) else type(report).__name__, 20) or "-",
                         _text(",".join(sorted(report)) if isinstance(report, dict) else "-", 120))
    except Exception as exc:  # noqa: BLE001 — a report must never error back
        log.info("client-error-unread body not understood: %s", _text(exc, 200))
    return Response(status_code=204)
