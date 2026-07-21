"""sessions/transcripts.py — the worker's Meet-transcript retrieval job."""

from __future__ import annotations

import types

import pytest

from sessions import transcripts
from sessions.transcripts import (
    MeetTranscriptSource,
    SourceResult,
    TranscriptSource,
    clamp_transcript,
    run_transcript_cycle,
)

SETTINGS_ON = types.SimpleNamespace(
    meet_transcripts=True, transcript_give_up_days=14, request_timeout_seconds=5
)
SETTINGS_OFF = types.SimpleNamespace(meet_transcripts=False)

META = {"sessionTranscription": {"type": "wysiwyg"},
        "transcriptDocUrl": {"type": "url"}}

MEET = "https://meet.google.com/abc-defg-hij"
DOC = "https://docs.google.com/document/d/xyz"


class FakeEspo:
    """API-key CRM stand-in: canned CSession candidates + mentor roster."""

    def __init__(self, *, sessions=None, mentors=None, records=None, meta=None):
        self.sessions = sessions or []
        self.mentors = mentors or []
        self.records = dict(records or {})
        self.meta = META if meta is None else meta
        self.updates = []
        self.list_calls = []

    async def metadata(self, key):
        return self.meta

    async def list(self, entity, **kw):
        self.list_calls.append((entity, kw))
        if kw.get("offset"):
            return {"list": []}
        if entity == "CSession":
            return {"list": list(self.sessions)}
        if entity == "CMentorProfile":
            return {"list": list(self.mentors)}
        return {"list": []}

    async def get(self, entity, record_id, select=None):
        rec = self.records.get((entity, record_id))
        if rec is None:
            raise RuntimeError(f"no record {entity}/{record_id}")
        return dict(rec, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}


class CannedSource(TranscriptSource):
    def __init__(self, results):
        self.results = dict(results)  # session id -> SourceResult (or Exception)
        self.fetched = []

    def matches(self, link):
        return "meet.google.com" in (link or "")

    async def fetch(self, session, mailbox):
        self.fetched.append((session["id"], mailbox))
        result = self.results[session["id"]]
        if isinstance(result, Exception):
            raise result
        return result


def _session(sid="s1", **kw):
    return dict({
        "id": sid, "dateStart": "2026-07-16 15:00:00",
        "videoMeetingLink": MEET, "assignedUserId": "u1",
    }, **kw)


MENTORS = [{"id": "mp1", "assignedUserId": "u1", "cbmEmail": "Doug.Bower@cbmentors.org"}]


# --- gates --------------------------------------------------------------------

async def test_disabled_flag_skips():
    espo = FakeEspo()
    assert await run_transcript_cycle(SETTINGS_OFF, espo) == {"skipped": "disabled"}
    assert espo.list_calls == []


async def test_missing_crm_field_skips():
    espo = FakeEspo(meta={})
    summary = await run_transcript_cycle(SETTINGS_ON, espo)
    assert summary == {"skipped": "no sessionTranscription field"}
    assert espo.list_calls == []


# --- the retrieval pass -------------------------------------------------------

async def test_ready_transcript_written_back_with_doc_url():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    source = CannedSource({"s1": SourceResult("ready", html="<p>hi</p>", doc_url=DOC)})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary == {"candidates": 1, "stored": 1, "pending": 0, "skipped": 0}
    # organizer resolved via the session's assigned user -> mentor cbmEmail
    assert source.fetched == [("s1", "doug.bower@cbmentors.org")]
    (entity, sid, payload), = espo.updates
    assert (entity, sid) == ("CSession", "s1")
    assert payload == {"sessionTranscription": "<p>hi</p>", "transcriptDocUrl": DOC}


async def test_doc_url_field_missing_writes_transcript_only():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS,
                    meta={"sessionTranscription": {}})
    source = CannedSource({"s1": SourceResult("ready", html="<p>hi</p>", doc_url=DOC)})
    await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    (_, _, payload), = espo.updates
    assert payload == {"sessionTranscription": "<p>hi</p>"}


async def test_not_ready_is_pending_and_writes_nothing():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    source = CannedSource({"s1": SourceResult("not_ready", reason="no record yet")})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary["pending"] == 1 and summary["stored"] == 0
    assert espo.updates == []


async def test_no_organizer_mailbox_skips_session():
    espo = FakeEspo(sessions=[_session(assignedUserId="u9")], mentors=MENTORS)
    source = CannedSource({"s1": SourceResult("ready", html="<p>hi</p>")})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary["skipped"] == 1
    assert source.fetched == [] and espo.updates == []


async def test_organizer_fallback_via_parent_manager_profile():
    """A session with no resolvable assigned user falls back to the parent
    engagement's assigned mentor profile."""
    espo = FakeEspo(
        sessions=[_session(assignedUserId=None, engagementId="E1")],
        mentors=MENTORS,
        records={
            ("CEngagement", "E1"): {"mentorProfileId": "mp2"},
            ("CMentorProfile", "mp2"): {"cbmEmail": "Mgr@cbmentors.org"},
        },
    )
    source = CannedSource({"s1": SourceResult("ready", html="<p>hi</p>")})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary["stored"] == 1
    assert source.fetched == [("s1", "mgr@cbmentors.org")]


async def test_one_failure_never_sinks_the_batch():
    espo = FakeEspo(sessions=[_session("s1"), _session("s2")], mentors=MENTORS)
    source = CannedSource({
        "s1": RuntimeError("google is down"),
        "s2": SourceResult("ready", html="<p>ok</p>"),
    })
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary["skipped"] == 1 and summary["stored"] == 1
    assert [u[1] for u in espo.updates] == ["s2"]


async def test_non_meet_link_skipped_by_provider_seam():
    espo = FakeEspo(sessions=[_session(videoMeetingLink="https://zoom.us/j/1")],
                    mentors=MENTORS)
    source = CannedSource({})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, sources=[source])
    assert summary["skipped"] == 1 and source.fetched == []


# --- clamp --------------------------------------------------------------------

def test_clamp_short_transcript_untouched():
    assert clamp_transcript("<p>short</p>") == "<p>short</p>"


def test_clamp_cuts_on_paragraph_boundary_with_note():
    para = "<p>" + "x" * 1000 + "</p>"
    long_html = "\n".join([para] * 300)  # > 200k chars
    clamped = clamp_transcript(long_html)
    assert len(clamped) < len(long_html)
    assert clamped.endswith("Google Doc.</em></p>")
    # the kept part ends cleanly on a closing tag before the note
    body = clamped[: clamped.rindex("<p><em>")].rstrip()
    assert body.endswith("</p>")


# --- MeetTranscriptSource (fake MeetClient) -----------------------------------

class FakeMeet:
    def __init__(self, records=None, transcripts=None, entries=None, participants=None):
        self.mailbox = None
        self.records = records if records is not None else [
            {"name": "conferenceRecords/cr1", "startTime": "2026-07-16T15:02:00Z"}]
        self.transcripts = transcripts if transcripts is not None else [
            {"name": "conferenceRecords/cr1/transcripts/t1", "state": "ENDED",
             "docsDestination": {"document": "d1", "exportUri": DOC}}]
        self.entries = entries if entries is not None else [
            {"participant": "p/1", "text": "Hello", "startTime": "2026-07-16T15:02:10Z"}]
        self.participants = participants if participants is not None else [
            {"name": "p/1", "signedinUser": {"displayName": "Doug Bower"}}]

    async def list_conference_records(self, code, after, before):
        self.window = (code, after, before)
        return list(self.records)

    async def list_transcripts(self, record_name):
        return list(self.transcripts)

    async def list_transcript_entries(self, transcript_name, page_size=1000):
        return list(self.entries)

    async def list_participants(self, record_name):
        return list(self.participants)


def _meet_source(monkeypatch, fake):
    monkeypatch.setattr(transcripts, "MeetClient",
                        lambda sa, mailbox, timeout=20: fake)
    return MeetTranscriptSource({"client_email": "sa@x"})


async def test_meet_source_ready(monkeypatch):
    fake = FakeMeet()
    source = _meet_source(monkeypatch, fake)
    result = await source.fetch(_session(), "doug.bower@cbmentors.org")
    assert result.status == "ready"
    assert "Doug Bower" in result.html and "Hello" in result.html
    assert result.doc_url == DOC
    # the conference window brackets the session start with the meeting code
    assert fake.window[0] == "abc-defg-hij"


async def test_meet_source_no_conference_yet(monkeypatch):
    source = _meet_source(monkeypatch, FakeMeet(records=[]))
    result = await source.fetch(_session(), "m@cbmentors.org")
    assert result.status == "not_ready"


async def test_meet_source_transcript_still_running(monkeypatch):
    fake = FakeMeet(transcripts=[{"name": "t1", "state": "STARTED"}])
    source = _meet_source(monkeypatch, fake)
    result = await source.fetch(_session(), "m@cbmentors.org")
    assert result.status == "not_ready"


# --- multi-source ordering + Fathom (v0.124.0) ---------------------------------

from sessions.transcripts import (  # noqa: E402
    FathomTranscriptSource,
    richtext_empty,
)

META_AI = {"sessionTranscription": {}, "transcriptDocUrl": {},
           "sessionAiSummary": {}}

SETTINGS_BOTH = types.SimpleNamespace(
    meet_transcripts=True, fathom_transcripts=True, fathom_api_key="k",
    fathom_base_url="https://f.test/v1", transcript_give_up_days=14,
    request_timeout_seconds=5,
)


class WideSource(CannedSource):
    """A canned source that (like Fathom) matches any link, needs no mailbox."""

    needs_mailbox = False
    link_contains = None

    def matches(self, link):
        return bool(link)


def test_richtext_empty():
    assert richtext_empty(None) and richtext_empty("") and richtext_empty("  ")
    assert richtext_empty("<p><br></p>") and richtext_empty("<p>&nbsp;</p>")
    assert not richtext_empty("<p>call the bank</p>")
    assert not richtext_empty("plain text")


async def test_first_source_ready_stops_the_walk():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    first = WideSource({"s1": SourceResult("ready", html="<p>fathom</p>")})
    second = CannedSource({"s1": SourceResult("ready", html="<p>meet</p>")})
    summary = await run_transcript_cycle(SETTINGS_BOTH, espo,
                                         sources=[first, second])
    assert summary["stored"] == 1
    assert second.fetched == []  # never consulted
    (_, _, payload), = espo.updates
    assert payload["sessionTranscription"] == "<p>fathom</p>"


async def test_not_ready_falls_back_to_next_source():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    first = WideSource({"s1": SourceResult("not_ready", reason="nothing yet")})
    second = CannedSource({"s1": SourceResult("ready", html="<p>meet</p>")})
    summary = await run_transcript_cycle(SETTINGS_BOTH, espo,
                                         sources=[first, second])
    assert summary["stored"] == 1 and summary["pending"] == 0
    (_, _, payload), = espo.updates
    assert payload["sessionTranscription"] == "<p>meet</p>"


async def test_source_exception_falls_back_to_next_source():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    first = WideSource({"s1": RuntimeError("fathom is down")})
    second = CannedSource({"s1": SourceResult("ready", html="<p>meet</p>")})
    summary = await run_transcript_cycle(SETTINGS_BOTH, espo,
                                         sources=[first, second])
    assert summary["stored"] == 1 and summary["skipped"] == 0


async def test_mailbox_free_source_serves_unresolvable_organizer():
    """A Fathom-style source needs no mailbox, so a session whose organizer
    can't be resolved still gets its transcript."""
    espo = FakeEspo(sessions=[_session(assignedUserId="u9")], mentors=MENTORS)
    source = WideSource({"s1": SourceResult("ready", html="<p>f</p>")})
    summary = await run_transcript_cycle(SETTINGS_BOTH, espo, sources=[source])
    assert summary["stored"] == 1
    assert source.fetched == [("s1", "")]  # fetched with no mailbox


async def test_candidate_query_widens_only_with_a_wide_source():
    espo = FakeEspo(sessions=[], mentors=MENTORS)
    await run_transcript_cycle(
        SETTINGS_BOTH, espo, sources=[WideSource({}), CannedSource({})])
    wide_clause = espo.list_calls[0][1]["where"][0]
    assert wide_clause == {"type": "isNotNull", "attribute": "videoMeetingLink"}

    meet_only = CannedSource({})
    meet_only.link_contains = "meet.google.com"
    espo2 = FakeEspo(sessions=[], mentors=MENTORS)
    await run_transcript_cycle(SETTINGS_ON, espo2, sources=[meet_only])
    narrow = espo2.list_calls[0][1]["where"][0]
    assert narrow["type"] == "contains" and narrow["value"] == "meet.google.com"


# --- action-items + summary routing (Doug's 2026-07-21 ruling) ------------------

def _ai_result(**kw):
    return SourceResult("ready", html="<p>t</p>", doc_url="https://fathom.video/x",
                        summary_html="<p>sum</p>",
                        action_items_html="<ul>\n<li>do it</li>\n</ul>", **kw)


async def test_action_items_fill_empty_next_steps():
    espo = FakeEspo(sessions=[_session(nextSteps="<p><br></p>")],
                    mentors=MENTORS, meta=META_AI)
    source = WideSource({"s1": _ai_result()})
    await run_transcript_cycle(SETTINGS_BOTH, espo, sources=[source])
    (_, _, payload), = espo.updates
    assert payload["nextSteps"] == "<ul>\n<li>do it</li>\n</ul>"
    assert payload["sessionAiSummary"] == "<p>sum</p>"
    assert payload["transcriptDocUrl"] == "https://fathom.video/x"


async def test_action_items_divert_to_summary_when_next_steps_filled():
    espo = FakeEspo(sessions=[_session(nextSteps="<p>mentor wrote this</p>")],
                    mentors=MENTORS, meta=META_AI)
    source = WideSource({"s1": _ai_result()})
    await run_transcript_cycle(SETTINGS_BOTH, espo, sources=[source])
    (_, _, payload), = espo.updates
    assert "nextSteps" not in payload  # human content untouched
    assert payload["sessionAiSummary"] == (
        "<p>sum</p>\n<p><strong>Action items</strong></p>\n"
        "<ul>\n<li>do it</li>\n</ul>")


async def test_no_ai_field_still_routes_items_to_empty_next_steps():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)  # META: no AI field
    source = WideSource({"s1": _ai_result()})
    await run_transcript_cycle(SETTINGS_BOTH, espo, sources=[source])
    (_, _, payload), = espo.updates
    assert payload["nextSteps"] == "<ul>\n<li>do it</li>\n</ul>"
    assert "sessionAiSummary" not in payload  # summary dropped, field missing


async def test_no_ai_field_and_filled_next_steps_drops_items():
    espo = FakeEspo(sessions=[_session(nextSteps="<p>keep me</p>")],
                    mentors=MENTORS)
    source = WideSource({"s1": _ai_result()})
    await run_transcript_cycle(SETTINGS_BOTH, espo, sources=[source])
    (_, _, payload), = espo.updates
    assert "nextSteps" not in payload and "sessionAiSummary" not in payload
    assert payload["sessionTranscription"] == "<p>t</p>"


# --- FathomTranscriptSource (fake FathomClient) ---------------------------------

from datetime import datetime, timezone  # noqa: E402

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

FATHOM_MEETING = {
    "recording_id": 77,
    "meeting_url": MEET,
    "recording_start_time": "2026-07-16T15:03:00Z",
    "share_url": "https://fathom.video/share/abc",
    "recorded_by": {"email": "doug.bower@cbmentors.org"},
    "summary": {"markdown_formatted": "## Recap\n- went well"},
    "action_items": [{"description": "Send deck"}],
}

FATHOM_ENTRIES = [
    {"speaker": {"display_name": "Doug"}, "text": "Hi", "timestamp": "00:00:01"},
]


class FakeFathom:
    def __init__(self, meetings=None, entries=None, fail_listing=False):
        self.meetings = meetings if meetings is not None else [dict(FATHOM_MEETING)]
        self.entries = entries if entries is not None else list(FATHOM_ENTRIES)
        self.fail_listing = fail_listing
        self.listings = 0
        self.transcript_calls = []

    async def list_meetings(self, created_after, **kw):
        self.listings += 1
        if self.fail_listing:
            from core.fathom import FathomError
            raise FathomError("nope")
        return list(self.meetings)

    async def get_transcript(self, recording_id):
        self.transcript_calls.append(recording_id)
        return list(self.entries)


def _fathom_source(fake):
    return FathomTranscriptSource(fake, now=NOW, give_up_days=14)


async def test_fathom_source_ready_with_summary_and_items():
    fake = FakeFathom()
    result = await _fathom_source(fake).fetch(_session(), "")
    assert result.status == "ready"
    assert "Doug" in result.html and "Hi" in result.html
    assert result.doc_url == "https://fathom.video/share/abc"
    assert "<p><strong>Recap</strong></p>" in result.summary_html
    assert "<li>went well</li>" in result.summary_html
    assert "<li>Send deck</li>" in result.action_items_html
    assert fake.transcript_calls == [77]


async def test_fathom_source_one_listing_per_cycle():
    fake = FakeFathom()
    source = _fathom_source(fake)
    await source.fetch(_session("s1"), "")
    await source.fetch(_session("s2"), "")
    assert fake.listings == 1


async def test_fathom_source_no_match_outside_window():
    late = dict(FATHOM_MEETING, recording_start_time="2026-07-01T10:00:00Z")
    result = await _fathom_source(FakeFathom(meetings=[late])).fetch(_session(), "")
    assert result.status == "not_ready"


async def test_fathom_source_picks_closest_of_reused_links():
    near = dict(FATHOM_MEETING, recording_id=1,
                recording_start_time="2026-07-16T15:05:00Z")
    far = dict(FATHOM_MEETING, recording_id=2,
               recording_start_time="2026-07-17T10:00:00Z")
    fake = FakeFathom(meetings=[far, near])
    result = await _fathom_source(fake).fetch(_session(), "")
    assert result.status == "ready" and fake.transcript_calls == [1]


async def test_fathom_source_empty_transcript_not_ready():
    fake = FakeFathom(entries=[])
    result = await _fathom_source(fake).fetch(_session(), "")
    assert result.status == "not_ready"


async def test_fathom_source_listing_failure_idles_the_cycle():
    fake = FakeFathom(fail_listing=True)
    source = _fathom_source(fake)
    r1 = await source.fetch(_session("s1"), "")
    r2 = await source.fetch(_session("s2"), "")
    assert r1.status == r2.status == "not_ready"
    assert fake.listings == 1  # failure cached; no per-session hammering


async def test_fathom_source_unrecognized_link_skips():
    result = await _fathom_source(FakeFathom()).fetch(
        _session(videoMeetingLink="https://example.com/x"), "")
    assert result.status == "skip"
