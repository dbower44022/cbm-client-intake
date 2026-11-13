"""YouTube helpers — server-side only.

Two jobs:

1. **Turn a recording URL into a video id and a thumbnail URL.** Pure string
   work, no API key and no network call — thumbnails are served straight from
   ``i.ytimg.com`` by video id. This is what the public recorded-webinar list
   uses.
2. **Read a playlist** (``YouTubeClient``), for the one-off migration that
   backfills the existing playlist into past event records (EV-42). This is the
   only thing that needs an API key.

Why this module exists at all: the live ``/webinars/`` page calls the YouTube
Data API **from the browser**, with the API key visible in the page source
(EV-05). Nothing here ever reaches the browser, and the common path (rendering
the library) needs no key whatsoever.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx

_API = "https://www.googleapis.com/youtube/v3"

#: Video ids are 11 chars of the URL-safe alphabet.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: Path-style URLs that carry the id as the last segment.
_PATH_PREFIXES = ("/embed/", "/v/", "/live/", "/shorts/")


class YouTubeError(RuntimeError):
    """A YouTube Data API call failed. ``status_code`` is the HTTP status when
    the API answered (None when it could not be reached); ``reason`` is
    Google's error reason, for example ``quotaExceeded``, when it gave one."""

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 reason: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


def _error_reason(resp: httpx.Response) -> str:
    """Google's error reason from an error body, or empty. Google puts it in
    ``error.errors[].reason`` and, on newer answers, ``error.details[].reason``."""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        return ""
    for key in ("errors", "details"):
        for item in err.get(key) or []:
            if isinstance(item, dict) and item.get("reason"):
                return str(item["reason"])
    return str(err.get("status") or "")


def video_id_from_url(url: str) -> Optional[str]:
    """Extract the video id from any common YouTube URL shape.

    Handles ``watch?v=``, ``youtu.be/``, ``/embed/``, ``/v/``, ``/live/`` and
    ``/shorts/``. Returns None when the URL isn't a YouTube video — callers
    treat that as "no thumbnail", never as an error, because the field is
    staff-entered free text.
    """
    if not url:
        return None
    raw = url.strip()
    if _ID_RE.match(raw):
        return raw  # already a bare id
    try:
        parsed = urlparse(raw if "//" in raw else f"https://{raw}")
    except ValueError:
        return None

    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate if _ID_RE.match(candidate) else None

    if host not in ("youtube.com", "m.youtube.com", "youtube-nocookie.com"):
        return None

    values = parse_qs(parsed.query).get("v")
    if values and _ID_RE.match(values[0]):
        return values[0]

    for prefix in _PATH_PREFIXES:
        if parsed.path.startswith(prefix):
            candidate = parsed.path[len(prefix):].split("/")[0]
            return candidate if _ID_RE.match(candidate) else None
    return None


def thumbnail_url(video_id: str, quality: str = "hqdefault") -> Optional[str]:
    """Thumbnail URL for a video id. No API key, no request — ``i.ytimg.com``
    serves these directly."""
    if not video_id or not _ID_RE.match(video_id):
        return None
    return f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"


def watch_url(video_id: str) -> Optional[str]:
    if not video_id or not _ID_RE.match(video_id):
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


class YouTubeClient:
    """Minimal YouTube Data API client — playlist reads only.

    Used by the migration that backfills the existing recorded-webinar playlist
    into past event records. Not on any request path.
    """

    def __init__(self, api_key: str, timeout: int = 20) -> None:
        if not api_key:
            raise YouTubeError("A YouTube API key is required.")
        self._key = api_key
        self._timeout = timeout

    async def playlist_items(self, playlist_id: str, max_items: int = 500) -> list[dict[str, Any]]:
        """Every item in a playlist, following pagination.

        Returns the raw ``snippet`` + ``contentDetails`` rows; the caller maps
        them onto event records.
        """
        items: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            while len(items) < max_items:
                params = {
                    "part": "snippet,contentDetails",
                    "playlistId": playlist_id,
                    "maxResults": min(50, max_items - len(items)),
                    "key": self._key,
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = await http.get(f"{_API}/playlistItems", params=params)
                if resp.status_code >= 400:
                    raise YouTubeError(
                        f"playlistItems failed: HTTP {resp.status_code} "
                        f"{resp.text[:200]}"
                    )
                data = resp.json()
                items.extend(data.get("items", []))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
        return items

    async def playlists(self, playlist_ids: list[str]) -> list[dict[str, Any]]:
        """``playlists.list`` for the given ids (``snippet`` and
        ``contentDetails``) in one call: each found playlist's raw resource.
        A playlist that does not exist is simply absent from the answer."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                resp = await http.get(f"{_API}/playlists", params={
                    "part": "snippet,contentDetails",
                    "id": ",".join(playlist_ids),
                    "maxResults": 50,
                    "key": self._key,
                })
        except httpx.HTTPError as exc:
            raise YouTubeError(f"YouTube could not be reached ({type(exc).__name__}).") from exc
        if resp.status_code >= 400:
            reason = _error_reason(resp)
            raise YouTubeError(
                f"playlists failed: HTTP {resp.status_code}" + (f" ({reason})" if reason else ""),
                status_code=resp.status_code, reason=reason,
            )
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise YouTubeError("playlists answered without an items list.", status_code=resp.status_code)
        return data["items"]
