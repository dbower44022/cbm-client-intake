"""Fathom note-taker REST access for meeting transcripts.

Plan: ``prds/fathom-transcript-integration.md``. One :class:`FathomClient`
per worker cycle, authenticated with the single CBM team API key
(``FATHOM_API_KEY`` — Fathom keys are user-level and read meetings recorded
by that account **or shared to its Team**, which is why the one-key model
requires CBM's team-sharing setup). Plain REST via httpx (gmeet pattern);
429/5xx are retried with backoff honoring ``Retry-After``.

The pure helpers (no HTTP) mirror :mod:`core.gmeet`'s formatter contract so
either provider's transcript renders identically in the session view:
:func:`normalize_meeting_url` canonicalizes a Meet/Zoom/Teams join link into
the correlation key between ``CSession.videoMeetingLink`` and Fathom's
``meeting_url``; :func:`format_transcript_html` emits the same
speaker-attributed paragraphs; :func:`summary_html` renders Fathom's
markdown summary through a small escaped subset (headings, bullets, bold);
:func:`action_items_html` renders the task list.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import unquote

import httpx

from core.gmeet import meeting_code

log = logging.getLogger("cbm_intake.fathom")

DEFAULT_BASE_URL = "https://api.fathom.ai/external/v1"

# Test seam: monkeypatched so backoff tests don't sleep for real.
_sleep = asyncio.sleep


class FathomError(Exception):
    """Any Fathom API / transport failure."""


class FathomClient:
    """Fathom external API v1, authenticated by the team API key."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 20,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._headers = {"X-Api-Key": api_key}
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport  # test seam (httpx.MockTransport)

    async def _request(
        self, method: str, path: str, *, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        resp: Optional[httpx.Response] = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport
                ) as client:
                    resp = await client.request(
                        method,
                        f"{self._base}{path}",
                        params=params,
                        headers=self._headers,
                    )
            except httpx.HTTPError as exc:
                raise FathomError(f"Fathom request failed ({path}): {exc}") from exc
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < 3:
                    await _sleep(_retry_after(resp) or float(2**attempt))
                    continue
                break
            if resp.status_code >= 400:
                raise FathomError(
                    f"Fathom {method} {path}: HTTP {resp.status_code} "
                    f"{resp.text[:300]}"
                )
            return resp.json() if resp.content else {}
        raise FathomError(
            f"Fathom {method} {path}: HTTP {resp.status_code} after retries"
            if resp is not None
            else f"Fathom {method} {path}: no response"
        )

    async def list_meetings(
        self,
        created_after: datetime,
        *,
        include_summary: bool = True,
        include_action_items: bool = True,
    ) -> list[dict[str, Any]]:
        """Every meeting the key can see since ``created_after`` (all pages)."""
        params: dict[str, Any] = {
            "created_after": created_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        if include_summary:
            params["include_summary"] = "true"
        if include_action_items:
            params["include_action_items"] = "true"
        meetings: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            page = dict(params)
            if cursor:
                page["cursor"] = cursor
            data = await self._request("GET", "/meetings", params=page)
            meetings.extend(_meeting_items(data))
            cursor = data.get("next_cursor")
            if not cursor:
                return meetings

    async def get_transcript(self, recording_id: Any) -> list[dict[str, Any]]:
        """The structured transcript entries of one recording (sync mode —
        ``destination_url`` deliberately omitted)."""
        data = await self._request(
            "GET", f"/recordings/{recording_id}/transcript"
        )
        return list(data.get("transcript") or [])


def _retry_after(resp: httpx.Response) -> Optional[float]:
    try:
        value = float(resp.headers.get("Retry-After", ""))
        return min(value, 30.0) if value > 0 else None
    except ValueError:
        return None


def _meeting_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The listing's items array (key name tolerated across doc revisions)."""
    for key in ("items", "meetings", "data"):
        items = data.get(key)
        if isinstance(items, list):
            return items
    return []


# --- pure helpers (no HTTP) ---------------------------------------------------

_ZOOM_RE = re.compile(r"zoom\.us/(?:j|s|w)/(\d{9,12})", re.I)
_TEAMS_JOIN_RE = re.compile(r"teams\.microsoft\.com/l/meetup-join/([^?\s\"']+)", re.I)
_TEAMS_MEET_RE = re.compile(r"teams\.(?:live|microsoft)\.com/meet/([A-Za-z0-9_-]+)", re.I)


def normalize_meeting_url(link: Optional[str]) -> Optional[str]:
    """A platform-scoped canonical key for a meeting join link, or None.

    The same normalization is applied to ``CSession.videoMeetingLink`` and to
    Fathom's ``meeting_url``, so equality means "the same meeting" regardless
    of tracking params / ``?pwd=`` suffixes.
    """
    text = link or ""
    code = meeting_code(text)
    if code:
        return f"meet:{code}"
    m = _ZOOM_RE.search(text)
    if m:
        return f"zoom:{m.group(1)}"
    m = _TEAMS_JOIN_RE.search(text)
    if m:
        return f"teams:{unquote(m.group(1)).lower()}"
    m = _TEAMS_MEET_RE.search(text)
    if m:
        return f"teams:{m.group(1).lower()}"
    return None


def _stamp_label(timestamp: Any) -> str:
    """Fathom's ``"HH:MM:SS"`` (elapsed) -> the gmeet-style ``[MM:SS]`` label."""
    parts = str(timestamp or "").strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return ""
    if len(nums) == 3:
        h, m, s = nums
    elif len(nums) == 2:
        h, (m, s) = 0, nums
    else:
        return ""
    if h < 0 or m < 0 or s < 0:
        return ""
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def format_transcript_html(entries: list[dict[str, Any]]) -> str:
    """Speaker-attributed HTML for ``CSession.sessionTranscription``.

    Same shape as :func:`core.gmeet.format_transcript_html` — one paragraph
    per speaker turn, consecutive same-speaker entries merged, the speaker's
    name in bold with the elapsed stamp — so the Transcript UI renders both
    providers identically. All text is escaped.
    """
    paragraphs: list[str] = []
    current_speaker: Optional[str] = None
    for entry in entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        sp = entry.get("speaker") or {}
        speaker = (
            (sp.get("display_name") or "").strip()
            or (sp.get("matched_calendar_invitee_email") or "").strip()
            or "Unknown speaker"
        )
        if speaker != current_speaker:
            label = _stamp_label(entry.get("timestamp"))
            head = f"<strong>{html.escape(speaker)}</strong>"
            if label:
                head += f" <em>{label}</em>"
            paragraphs.append(f"<p>{head}<br>{html.escape(text)}")
            current_speaker = speaker
        else:
            paragraphs[-1] += f" {html.escape(text)}"
    return "</p>\n".join(paragraphs) + ("</p>" if paragraphs else "")


_HEADING_RE = re.compile(r"#{1,6}\s+(.*)")
_BULLET_RE = re.compile(r"(?:[-*•]|\d+[.)])\s+(.*)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
# Markdown links AFTER escaping (real Fathom summaries are link-dense — every
# claim carries a fathom.video timestamp link). http(s) targets only.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _inline(text: str) -> str:
    """Escape, then render the inline marks Fathom summaries use: ``**bold**``
    and ``[text](https://…)`` links (escaped first, so only the tags emitted
    here reach the CRM; non-http(s) link targets stay literal)."""
    escaped = html.escape(text)
    escaped = _LINK_RE.sub(
        r'<a href="\2" target="_blank" rel="noopener">\1</a>', escaped
    )
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def summary_html(markdown_text: Optional[str]) -> str:
    """Fathom's markdown summary -> sanitized HTML (small escaped subset:
    headings as bold paragraphs, dash/numbered bullets as lists, ``**bold**``;
    everything else is escaped paragraph text)."""
    out: list[str] = []
    items: list[str] = []
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def flush_items() -> None:
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in str(markdown_text or "").splitlines():
        line = raw.strip()
        if not line:
            flush_para()
            flush_items()
            continue
        heading = _HEADING_RE.fullmatch(line)
        if heading:
            flush_para()
            flush_items()
            out.append(f"<p><strong>{_inline(heading.group(1))}</strong></p>")
            continue
        bullet = _BULLET_RE.fullmatch(line)
        if bullet:
            flush_para()
            items.append(_inline(bullet.group(1)))
            continue
        flush_items()
        para.append(line)
    flush_para()
    flush_items()
    return "\n".join(out)


def action_items_html(items: Optional[list[Any]]) -> str:
    """Fathom's action items -> a sanitized ``<ul>`` (empty string for none).

    Tolerates strings or dicts (``description``/``text``/``title`` for the
    task, an optional ``assignee`` object/string appended in italics).
    """
    rendered: list[str] = []
    for item in items or []:
        assignee = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = (
                item.get("description") or item.get("text") or item.get("title") or ""
            ).strip()
            who = item.get("assignee")
            if isinstance(who, dict):
                assignee = (who.get("name") or who.get("email") or "").strip()
            elif who:
                assignee = str(who).strip()
        else:
            continue
        if not text:
            continue
        li = html.escape(text)
        if assignee:
            li += f" — <em>{html.escape(assignee)}</em>"
        rendered.append(f"<li>{li}</li>")
    if not rendered:
        return ""
    return "<ul>\n" + "\n".join(rendered) + "\n</ul>"
