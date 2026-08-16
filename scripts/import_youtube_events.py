"""Phase 6d (EV-42) — backfill the recorded-webinar playlist into past events.

The website's recorded library is currently a YouTube playlist that EspoCRM
knows nothing about. This imports each video as a **past** ``CEvent`` carrying
the recording link, so the library can be served from the CRM like everything
else.

Two decisions worth knowing before you run it:

**Imported events arrive UNPUBLISHED.** A video's publish date is not the event
date (R-6) — it is usually days later, and sometimes years, if the archive was
uploaded in a batch. So every import needs a human to check the date and the
topic. Creating them with ``publishToWebsite=false`` means a wrong date can
never reach the public site: staff review, correct, then publish. The
alternative — import published and fix afterwards — puts bad data in front of
visitors for as long as the review takes.

**It is idempotent.** An event whose ``recordingUrl`` already carries the video
id is skipped, so a re-run after a partial failure adds only what is missing.

Usage::

    # dry run (default) — prints the plan, changes nothing
    PYTHONPATH=. uv run python scripts/import_youtube_events.py

    # apply
    PYTHONPATH=. uv run python scripts/import_youtube_events.py --write

Needs ``YOUTUBE_API_KEY`` and ``YOUTUBE_PLAYLIST_ID`` (the key is used ONLY
here — rendering the library derives thumbnails from the video id with no key
and no API call, which is what keeps it out of the browser, EV-05).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from core.config import Settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from core.youtube import YouTubeClient, watch_url  # noqa: E402
from events import config as cfg  # noqa: E402
from events import service  # noqa: E402

#: Imported recordings get this length. Nothing in the payload depends on it,
#: but `dateEnd` is required on CEvent and a zero-length event reads oddly.
DEFAULT_DURATION = timedelta(hours=1)
#: Trimmed so a 5,000-character YouTube description doesn't become the card blurb.
SUMMARY_CHARS = 400


def _snippet(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("snippet") or {}


def video_id_of(item: dict[str, Any]) -> str:
    snip = _snippet(item)
    resource = snip.get("resourceId") or {}
    return str(resource.get("videoId") or "").strip()


def existing_video_ids(events: list[dict[str, Any]]) -> set[str]:
    """Video ids already represented in the CRM, from their recording links."""
    from core.youtube import video_id_from_url

    out = set()
    for row in events:
        vid = video_id_from_url(row.get("recordingUrl") or "")
        if vid:
            out.add(vid)
    return out


def build_payload(item: dict[str, Any], *, slug: str) -> dict[str, Any]:
    """The CEvent for one playlist entry.

    ``dateStart`` is the video's publish date, which is a STARTING GUESS, not
    the event date — hence unpublished (see the module docstring).
    """
    snip = _snippet(item)
    vid = video_id_of(item)
    published = service.parse_crm_datetime(
        str(snip.get("publishedAt") or "").replace("T", " ").replace("Z", "")
    )
    title = str(snip.get("title") or "").strip() or f"Recorded webinar {vid}"
    summary = " ".join(str(snip.get("description") or "").split())[:SUMMARY_CHARS]

    payload: dict[str, Any] = {
        "name": title,
        "description": summary,
        "slug": slug,
        "status": cfg.STATUS_HELD,
        "format": cfg.FORMAT_VIRTUAL,
        "eventType": "Online Webinar",
        "recordingUrl": watch_url(vid),
        # Never published on import: the date below is a guess (R-6).
        "publishToWebsite": False,
    }
    if published:
        payload["dateStart"] = service.to_crm_datetime(published)
        payload["dateEnd"] = service.to_crm_datetime(published + DEFAULT_DURATION)
    return payload


def plan_import(
    items: list[dict[str, Any]], events: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Split the playlist into (to create, already present). Pure — testable."""
    have = existing_video_ids(events)
    taken = {e.get("slug") for e in events if e.get("slug")}
    to_create: list[dict[str, Any]] = []
    skipped: list[str] = []
    for item in items:
        vid = video_id_of(item)
        # An id the URL helpers refuse would yield recordingUrl=None, i.e. an
        # event that can never appear in the recorded library. Skip it rather
        # than create a useless record.
        if not vid or not watch_url(vid):
            continue
        if vid in have:
            skipped.append(vid)
            continue
        title = str(_snippet(item).get("title") or "").strip()
        slug = service.unique_slug(title or f"recording-{vid}", taken)
        taken.add(slug)
        have.add(vid)              # a playlist can list the same video twice
        to_create.append(build_payload(item, slug=slug))
    return to_create, skipped


async def main() -> int:
    write = "--write" in sys.argv
    settings = Settings()
    if not settings.youtube_api_key or not settings.youtube_playlist_id:
        print("Set YOUTUBE_API_KEY and YOUTUBE_PLAYLIST_ID.", file=sys.stderr)
        return 2
    if settings.espo_dry_run or not settings.espo_api_key:
        print("No live CRM configured (ESPO_DRY_RUN / ESPO_API_KEY).", file=sys.stderr)
        return 2

    crm = EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )
    tube = YouTubeClient(settings.youtube_api_key, settings.request_timeout_seconds)

    print(f"CRM:      {settings.espo_base_url}")
    print(f"Playlist: {settings.youtube_playlist_id}")
    print(f"Mode:     {'WRITE' if write else 'DRY RUN — nothing will change'}\n")

    items = await tube.playlist_items(settings.youtube_playlist_id)
    events = await service._all_events(
        crm, select="id,name,slug,recordingUrl", where=None, limit=2000
    )
    to_create, skipped = plan_import(items, events)

    print(f"{len(items)} playlist item(s); {len(skipped)} already in the CRM; "
          f"{len(to_create)} to import.\n")
    for payload in to_create:
        print(f"  + {payload['dateStart'][:10] if payload.get('dateStart') else '(no date)'}"
              f"  {payload['name'][:70]}")
    if not to_create:
        print("Nothing to do.")
        return 0

    if not write:
        print("\nDry run only. Re-run with --write to create these.")
        print("They will be created UNPUBLISHED — check each date and topic, then "
              "publish. A video's upload date is not the event date.")
        return 0

    created = failed = 0
    for payload in to_create:
        try:
            await crm.create(cfg.EVENT, payload)
            created += 1
        except EspoError as exc:
            failed += 1
            print(f"  ! FAILED {payload['name'][:60]}: {exc}")
    print(f"\nCreated {created}, failed {failed}.")
    print("All created UNPUBLISHED. Review each date and topic in Event "
          "Administration, then tick Publish to website.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
