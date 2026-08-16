"""Phase 6d (EV-42) — the YouTube playlist backfill.

The two properties that matter: it never imports the same video twice, and it
never publishes anything, because a video's upload date is not the event date.
"""

from __future__ import annotations

from scripts.import_youtube_events import (
    build_payload,
    existing_video_ids,
    plan_import,
    video_id_of,
)
from events import config as cfg


def _item(vid, title="A Webinar", published="2026-03-04T15:00:00Z", desc=""):
    return {"snippet": {"resourceId": {"videoId": vid}, "title": title,
                        "publishedAt": published, "description": desc}}


def test_video_ids_are_recovered_from_existing_recording_links():
    events = [
        {"recordingUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        {"recordingUrl": ""},
        {"recordingUrl": "https://youtu.be/aBcDeFgHiJk"},
    ]
    assert existing_video_ids(events) == {"dQw4w9WgXcQ", "aBcDeFgHiJk"}


def test_an_already_imported_video_is_skipped():
    items = [_item("dQw4w9WgXcQ"), _item("nEw0000001x")]
    events = [{"recordingUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "slug": "a"}]
    to_create, skipped = plan_import(items, events)
    assert skipped == ["dQw4w9WgXcQ"]
    assert [p["recordingUrl"] for p in to_create] == [
        "https://www.youtube.com/watch?v=nEw0000001x"
    ]


def test_a_playlist_listing_the_same_video_twice_creates_one_event():
    to_create, _ = plan_import([_item("dUp0000001x"), _item("dUp0000001x")], [])
    assert len(to_create) == 1


def test_slugs_do_not_collide_with_each_other_or_with_existing_events():
    items = [_item("v100000001x", title="Grant Writing"), _item("v200000002x", title="Grant Writing")]
    events = [{"slug": "grant-writing", "recordingUrl": ""}]
    to_create, _ = plan_import(items, events)
    slugs = [p["slug"] for p in to_create]
    assert len(set(slugs)) == 2
    assert "grant-writing" not in slugs      # the existing one is not stolen


def test_imported_events_are_never_published():
    """R-6: the upload date is a guess at the event date, so a wrong date must
    not be able to reach the public site. Staff review, then publish."""
    to_create, _ = plan_import([_item("v100000001x")], [])
    assert to_create[0]["publishToWebsite"] is False


def test_payload_shape():
    payload = build_payload(
        _item("v100000001x", title="Finance Basics", published="2026-03-04T15:00:00Z",
              desc="  lots   of\nwhitespace  "),
        slug="finance-basics",
    )
    assert payload["status"] == cfg.STATUS_HELD
    assert payload["format"] == cfg.FORMAT_VIRTUAL
    assert payload["recordingUrl"] == "https://www.youtube.com/watch?v=v100000001x"
    assert payload["description"] == "lots of whitespace"
    assert payload["dateStart"] == "2026-03-04 15:00:00"
    assert payload["dateEnd"] == "2026-03-04 16:00:00"   # dateEnd is required


def test_a_video_with_no_title_still_gets_a_name():
    payload = build_payload(_item("v900000009x", title=""), slug="s")
    assert payload["name"] == "Recorded webinar v900000009x"


def test_items_without_a_usable_video_id_are_ignored():
    """No id at all, or one the URL helpers refuse — either way an event with no
    recording link would be useless in the library."""
    to_create, skipped = plan_import(
        [{"snippet": {"title": "junk"}}, _item("not-an-id")], []
    )
    assert to_create == [] and skipped == []


def test_video_id_of_reads_the_resource_id():
    assert video_id_of(_item("abc")) == "abc"
    assert video_id_of({}) == ""
