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
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
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
    await run_transcript_cycle(SETTINGS_ON, espo, source=source)
    (_, _, payload), = espo.updates
    assert payload == {"sessionTranscription": "<p>hi</p>"}


async def test_not_ready_is_pending_and_writes_nothing():
    espo = FakeEspo(sessions=[_session()], mentors=MENTORS)
    source = CannedSource({"s1": SourceResult("not_ready", reason="no record yet")})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
    assert summary["pending"] == 1 and summary["stored"] == 0
    assert espo.updates == []


async def test_no_organizer_mailbox_skips_session():
    espo = FakeEspo(sessions=[_session(assignedUserId="u9")], mentors=MENTORS)
    source = CannedSource({"s1": SourceResult("ready", html="<p>hi</p>")})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
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
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
    assert summary["stored"] == 1
    assert source.fetched == [("s1", "mgr@cbmentors.org")]


async def test_one_failure_never_sinks_the_batch():
    espo = FakeEspo(sessions=[_session("s1"), _session("s2")], mentors=MENTORS)
    source = CannedSource({
        "s1": RuntimeError("google is down"),
        "s2": SourceResult("ready", html="<p>ok</p>"),
    })
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
    assert summary["skipped"] == 1 and summary["stored"] == 1
    assert [u[1] for u in espo.updates] == ["s2"]


async def test_non_meet_link_skipped_by_provider_seam():
    espo = FakeEspo(sessions=[_session(videoMeetingLink="https://zoom.us/j/1")],
                    mentors=MENTORS)
    source = CannedSource({})
    summary = await run_transcript_cycle(SETTINGS_ON, espo, source=source)
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
