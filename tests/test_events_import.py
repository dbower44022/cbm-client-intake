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
    to_create, skipped, _dupes = plan_import(items, events)
    assert skipped == ["dQw4w9WgXcQ"]
    assert [p["recordingUrl"] for p in to_create] == [
        "https://www.youtube.com/watch?v=nEw0000001x"
    ]


def test_a_playlist_listing_the_same_video_twice_creates_one_event():
    to_create, _, _dupes = plan_import([_item("dUp0000001x"), _item("dUp0000001x")], [])
    assert len(to_create) == 1


def test_slugs_do_not_collide_with_each_other_or_with_existing_events():
    items = [_item("v100000001x", title="Grant Writing"), _item("v200000002x", title="Grant Writing")]
    events = [{"slug": "grant-writing", "recordingUrl": ""}]
    to_create, _, _dupes = plan_import(items, events)
    slugs = [p["slug"] for p in to_create]
    assert len(set(slugs)) == 2
    assert "grant-writing" not in slugs      # the existing one is not stolen


def test_imported_events_are_never_published():
    """R-6: the upload date is a guess at the event date, so a wrong date must
    not be able to reach the public site. Staff review, then publish."""
    to_create, _, _dupes = plan_import([_item("v100000001x")], [])
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
    to_create, skipped, _dupes = plan_import(
        [{"snippet": {"title": "junk"}}, _item("not-an-id")], []
    )
    assert to_create == [] and skipped == []


def test_video_id_of_reads_the_resource_id():
    assert video_id_of(_item("abc")) == "abc"
    assert video_id_of({}) == ""


# --- five playlists, not one -------------------------------------------------


def test_the_playlist_setting_takes_several_ids():
    """CBM keeps its recordings in five topic playlists — Startup, New Product
    Development, AI and Tech, Business Planning and Strategy, Nonprofit — rather
    than one library, and the website's page shows them mixed together. The
    import reads them all."""
    from core.config import Settings

    s = Settings(youtube_playlist_id="PLstartup, PLnpd ,PLtech")
    assert s.youtube_playlist_ids == ["PLstartup", "PLnpd", "PLtech"]


def test_one_id_still_works():
    from core.config import Settings

    assert Settings(youtube_playlist_id="PLonly").youtube_playlist_ids == ["PLonly"]


def test_no_playlist_configured_reads_as_none():
    """Both forms of "nothing configured" — never set, and set to blank.

    Deliberately NOT `Settings()`: pydantic-settings reads the developer's own
    `.env`, so once a real playlist is configured locally that spelling asserts
    on whatever happens to be on this machine. It passed until the day the
    values were added, which is the worst moment for a test to start lying."""
    from core.config import Settings

    assert Settings(youtube_playlist_id="").youtube_playlist_ids == []
    assert Settings(youtube_playlist_id="  ").youtube_playlist_ids == []


def test_the_same_playlist_listed_twice_is_read_once():
    """A duplicated id would double every video it holds into the plan, where
    the video-id dedup would then hide the configuration mistake."""
    from core.config import Settings

    s = Settings(youtube_playlist_id="PLone,PLtwo,PLone")
    assert s.youtube_playlist_ids == ["PLone", "PLtwo"]


def test_a_video_in_two_playlists_is_imported_once():
    """The real reason the planner runs over the COMBINED list rather than once
    per playlist: an AI webinar aimed at nonprofits sits in two of them, and two
    separate runs would create it twice under two slugs."""
    startup = [_item("shared00001"), _item("onlyone0001")]
    nonprofit = [_item("shared00001"), _item("onlytwo0001")]
    to_create, _, _dupes = plan_import(startup + nonprofit, [])
    slugs = [p["slug"] for p in to_create]
    assert len(to_create) == 3, slugs
    assert len(set(slugs)) == 3, slugs


def test_the_import_does_not_guess_a_topic():
    """The five playlist names are a different taxonomy from the CRM's ten
    curated topic values: 'AI and Tech' and 'Nonprofit' map cleanly, 'Startup'
    and 'Business Planning and Strategy' would both collapse onto Business
    Fundamentals, and 'New Product Development' has no home at all. A wrong
    category on a public page is worse than an empty one, so the topic stays
    part of the same human review the date already needs."""
    to_create, _, _dupes = plan_import([_item("v100000001x")], [])
    assert "topic" not in to_create[0]


def test_a_cross_playlist_duplicate_is_not_reported_as_already_imported():
    """Reading five playlists made "the same video twice" ordinary, and the old
    single count called it "already in the CRM" — telling an operator that three
    videos were imported into a CRM holding none of them."""
    items = [_item("shared00001"), _item("shared00001"), _item("unique00001")]
    to_create, already, duplicates = plan_import(items, [])
    assert len(to_create) == 2
    assert already == []                    # nothing was in the CRM
    assert duplicates == ["shared00001"]    # met a second time across the lists


def test_a_video_genuinely_in_the_crm_is_reported_as_such():
    events = [{"id": "e1", "slug": "s", "recordingUrl": "https://youtu.be/shared00001"}]
    to_create, already, duplicates = plan_import([_item("shared00001")], events)
    assert to_create == []
    assert already == ["shared00001"]
    assert duplicates == []
