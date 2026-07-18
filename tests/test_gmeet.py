"""core/gmeet.py — the pure helpers (no HTTP)."""

from __future__ import annotations

from core.gmeet import format_transcript_html, meeting_code, participant_names


# --- meeting_code -------------------------------------------------------------

def test_meeting_code_from_meet_link():
    assert meeting_code("https://meet.google.com/abc-defg-hij") == "abc-defg-hij"


def test_meeting_code_with_query_and_case():
    assert meeting_code("https://MEET.GOOGLE.COM/ABC-DEFG-HIJ?authuser=0") == "abc-defg-hij"


def test_meeting_code_non_meet_links():
    assert meeting_code("https://zoom.us/j/123456") is None
    assert meeting_code("") is None
    assert meeting_code(None) is None
    # a Meet host without a valid code shape is not a meeting
    assert meeting_code("https://meet.google.com/landing") is None


# --- participant_names --------------------------------------------------------

def test_participant_names_all_kinds():
    names = participant_names([
        {"name": "conferenceRecords/x/participants/1",
         "signedinUser": {"user": "users/9", "displayName": "Doug Bower"}},
        {"name": "conferenceRecords/x/participants/2",
         "anonymousUser": {"displayName": "Guest"}},
        {"name": "conferenceRecords/x/participants/3",
         "phoneUser": {"displayName": "+1 216 555"}},
        {"signedinUser": {"displayName": "No Resource Name"}},  # dropped
    ])
    assert names == {
        "conferenceRecords/x/participants/1": "Doug Bower",
        "conferenceRecords/x/participants/2": "Guest",
        "conferenceRecords/x/participants/3": "+1 216 555",
    }


# --- format_transcript_html ---------------------------------------------------

NAMES = {"p/1": "Doug Bower", "p/2": "James Koran"}


def test_format_merges_consecutive_same_speaker():
    html = format_transcript_html([
        {"participant": "p/1", "text": "Hello.", "startTime": "2026-07-17T15:00:00Z"},
        {"participant": "p/1", "text": "Welcome!", "startTime": "2026-07-17T15:00:05Z"},
        {"participant": "p/2", "text": "Thanks.", "startTime": "2026-07-17T15:01:10Z"},
    ], NAMES)
    # two paragraphs: Doug's two entries merged, James' own with elapsed stamp
    assert html.count("<p>") == 2
    assert "<strong>Doug Bower</strong> <em>[00:00]</em><br>Hello. Welcome!" in html
    assert "<strong>James Koran</strong> <em>[01:10]</em><br>Thanks." in html


def test_format_escapes_text_and_unknown_speaker():
    html = format_transcript_html([
        {"participant": "p/9", "text": "<script>alert(1)</script> & so on"},
    ], NAMES)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Unknown speaker" in html


def test_format_hour_offsets_and_empty():
    assert format_transcript_html([], NAMES) == ""
    html = format_transcript_html([
        {"participant": "p/1", "text": "start", "startTime": "2026-07-17T15:00:00Z"},
        {"participant": "p/2", "text": "late", "startTime": "2026-07-17T16:02:03Z"},
    ], NAMES)
    assert "[1:02:03]" in html


def test_format_skips_blank_entries():
    html = format_transcript_html([
        {"participant": "p/1", "text": "  "},
        {"participant": "p/1", "text": "real"},
    ], NAMES)
    assert html.count("<p>") == 1 and "real" in html
