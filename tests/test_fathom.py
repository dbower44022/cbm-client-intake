"""core/fathom.py — the Fathom client + pure helpers."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from core import fathom
from core.fathom import (
    FathomClient,
    FathomError,
    action_items_html,
    format_transcript_html,
    normalize_meeting_url,
    summary_html,
)


# --- normalize_meeting_url ------------------------------------------------------

def test_normalize_meet_link():
    assert normalize_meeting_url("https://meet.google.com/abc-defg-hij") == \
        "meet:abc-defg-hij"
    # query strings and case don't change the key
    assert normalize_meeting_url("https://MEET.GOOGLE.COM/ABC-DEFG-HIJ?authuser=1") == \
        "meet:abc-defg-hij"


def test_normalize_zoom_link_ignores_pwd():
    a = normalize_meeting_url("https://us02web.zoom.us/j/1234567890?pwd=abcDEF")
    b = normalize_meeting_url("https://zoom.us/j/1234567890")
    assert a == b == "zoom:1234567890"


def test_normalize_teams_links():
    join = ("https://teams.microsoft.com/l/meetup-join/"
            "19%3ameeting_XYZ%40thread.v2/0?context=%7b%22Tid%22%3a%22t%22%7d")
    assert normalize_meeting_url(join) == "teams:19:meeting_xyz@thread.v2/0"
    assert normalize_meeting_url("https://teams.live.com/meet/9876543210") == \
        "teams:9876543210"


def test_normalize_unrecognized_links():
    assert normalize_meeting_url("https://example.com/call") is None
    assert normalize_meeting_url("") is None
    assert normalize_meeting_url(None) is None


# --- format_transcript_html -----------------------------------------------------

ENTRIES = [
    {"speaker": {"display_name": "Doug Bower"}, "text": "Hello there.",
     "timestamp": "00:00:05"},
    {"speaker": {"display_name": "Doug Bower"}, "text": "Welcome.",
     "timestamp": "00:00:09"},
    {"speaker": {"display_name": "Jane <Client>"}, "text": "Thanks & hi!",
     "timestamp": "01:02:03"},
]


def test_format_merges_consecutive_speakers_and_stamps():
    html_text = format_transcript_html(ENTRIES)
    # two paragraphs: Doug's two entries merged, Jane's separate
    assert html_text.count("<p>") == 2
    assert "Hello there. Welcome." in html_text
    assert "<strong>Doug Bower</strong> <em>[00:05]</em>" in html_text
    # hour-long stamp keeps the hour, gmeet style
    assert "[1:02:03]" in html_text
    # everything escaped
    assert "Jane &lt;Client&gt;" in html_text and "Thanks &amp; hi!" in html_text


def test_format_empty_and_unknown_speaker():
    assert format_transcript_html([]) == ""
    html_text = format_transcript_html([
        {"speaker": {}, "text": "hi", "timestamp": "bogus"},
    ])
    assert "Unknown speaker" in html_text and "<em>" not in html_text


def test_format_falls_back_to_matched_email():
    html_text = format_transcript_html([
        {"speaker": {"matched_calendar_invitee_email": "x@y.test"}, "text": "hi"},
    ])
    assert "x@y.test" in html_text


# --- summary_html ---------------------------------------------------------------

def test_summary_headings_bullets_bold_escaped():
    md = ("## Overview\n"
          "The client & mentor met.\n"
          "\n"
          "- Reviewed **pricing**\n"
          "* Discussed <hiring>\n"
          "1. Next call scheduled\n")
    out = summary_html(md)
    assert "<p><strong>Overview</strong></p>" in out
    assert "<p>The client &amp; mentor met.</p>" in out
    assert "<li>Reviewed <strong>pricing</strong></li>" in out
    assert "<li>Discussed &lt;hiring&gt;</li>" in out
    assert "<li>Next call scheduled</li>" in out
    assert "<script" not in out


def test_summary_empty():
    assert summary_html("") == ""
    assert summary_html(None) == ""


# --- action_items_html ----------------------------------------------------------

def test_action_items_variants():
    out = action_items_html([
        "Plain string task",
        {"description": "Send the deck", "assignee": {"name": "Doug"}},
        {"text": "Follow up <soon>"},
        {"title": ""},          # blank -> dropped
        42,                      # unrecognized -> dropped
    ])
    assert out.startswith("<ul>") and out.endswith("</ul>")
    assert "<li>Plain string task</li>" in out
    assert "Send the deck — <em>Doug</em>" in out
    assert "Follow up &lt;soon&gt;" in out
    assert out.count("<li>") == 3


def test_action_items_empty():
    assert action_items_html([]) == ""
    assert action_items_html(None) == ""


# --- FathomClient (MockTransport) -----------------------------------------------

def _client(handler):
    return FathomClient("k", base_url="https://f.test/v1",
                        transport=httpx.MockTransport(handler))


async def test_list_meetings_pages_with_cursor_and_auth_header():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["X-Api-Key"] == "k"
        if request.url.params.get("cursor"):
            return httpx.Response(200, json={"items": [{"recording_id": 2}]})
        return httpx.Response(
            200, json={"items": [{"recording_id": 1}], "next_cursor": "c2"}
        )

    meetings = await _client(handler).list_meetings(datetime(2026, 7, 1))
    assert [m["recording_id"] for m in meetings] == [1, 2]
    assert calls[0].url.params["created_after"] == "2026-07-01T00:00:00Z"
    assert calls[0].url.params["include_summary"] == "true"


async def test_retry_on_429_then_success(monkeypatch):
    sleeps = []

    async def fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(fathom, "_sleep", fake_sleep)
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"transcript": [{"text": "hi"}]})

    entries = await _client(handler).get_transcript(7)
    assert entries == [{"text": "hi"}]
    assert sleeps == [3.0]


async def test_4xx_raises_fathom_error():
    def handler(request):
        return httpx.Response(401, text="bad key")

    with pytest.raises(FathomError, match="HTTP 401"):
        await _client(handler).get_transcript(7)
