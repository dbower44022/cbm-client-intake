"""F1 — an event carries several curated topics (``prds/events/
CBM_Events_Topics_Design.md``). Two rulings: nobody types a topic (F1-1, the
editor offers the CRM's list only); an event appears under each of its topics
(F1-2). Feature-detected: a CRM without ``topics`` behaves exactly as before."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from events import config as cfg
from events import reporting, service
from tests.test_events_service import make_event

ROOT = Path(__file__).resolve().parents[1]


# --- which field holds the topics -------------------------------------------


def test_a_row_without_the_new_field_reads_the_single_topic():
    assert service.event_topics(make_event(topic="Operations")) == ["Operations"]
    assert service.event_topics(make_event(topic="")) == []


def test_a_row_from_a_crm_with_the_new_field_reads_it_and_only_it():
    """Even when it is empty: the single topic is retired there, and a fallback
    would resurrect a value staff deliberately cleared."""
    assert service.event_topics(make_event(topics=["A", "B"], topic="Old")) == ["A", "B"]
    assert service.event_topics(make_event(topics=[], topic="Old")) == []
    assert service.event_topics(make_event(topics=None, topic="Old")) == []
    assert service.event_topics(make_event(topics=["A", " ", "A", 3])) == ["A"]


# --- the editor spec and the write whitelist -------------------------------


def test_the_spec_offers_the_list_only_and_never_a_typed_value():
    """F1-1: the control is the CRM's multiEnum; there is no free-text field."""
    spec = {f.name: f for f in cfg.EVENT_FIELDS}
    assert spec["topics"].type == "multiEnum"
    assert spec["topics"].group == spec["topic"].group == "Event"
    assert spec["topic"].retired_by == "topics"
    assert "topics" in cfg.DETECTED_FIELDS
    assert not any("other" in f.name.lower() and "topic" in f.name.lower()
                   for f in cfg.EVENT_FIELDS)


def test_without_the_field_the_editor_shows_the_single_topic_as_before():
    names = [f.name for f in service.editor_fields(frozenset())]
    assert "topic" in names and "topics" not in names


def test_with_the_field_the_editor_shows_topics_and_retires_topic():
    names = [f.name for f in service.editor_fields(frozenset({"topics"}))]
    assert "topics" in names and "topic" not in names
    # Topics stands where Topic stood.
    assert names.index("topics") == [f.name for f in service.editor_fields(frozenset())].index("topic")


def test_the_whitelist_follows_the_crm():
    changes = {"topic": "Operations", "topics": ["Operations", "Other"], "name": "X"}
    before = service._writable(changes, available=frozenset())
    assert before == {"topic": "Operations", "name": "X"}
    after = service._writable(changes, available=frozenset({"topics"}))
    assert after == {"topics": ["Operations", "Other"], "name": "X"}


def test_topics_is_selected_on_every_read():
    assert "topics" in cfg.PUBLIC_SELECT.split(",")


# --- the public payloads ---------------------------------------------------


def test_public_payloads_carry_every_topic_and_keep_the_contract_key():
    event = make_event(topics=["Finance & Accounting", "Business Fundamentals"],
                       recordingUrl="https://www.youtube.com/watch?v=vid0000001")
    for payload in (service.public_event(event), service.public_recording(event)):
        assert payload["category"] == "Finance & Accounting"
        assert payload["categories"] == ["Finance & Accounting", "Business Fundamentals"]
    legacy = service.public_event(make_event(topic="Operations"))
    assert legacy["category"] == "Operations" and legacy["categories"] == ["Operations"]
    none = service.public_event(make_event(topics=[]))
    assert none["category"] == "" and none["categories"] == []


def test_the_reports_topic_column_names_every_topic():
    ref = reporting._event_ref(make_event(topics=["A", "B"]))
    assert ref["category"] == "A, B" and ref["categories"] == ["A", "B"]


# --- the recorded library (F1-2) -------------------------------------------


def _rec(name, **over):
    return make_event(name=name, recordingUrl="https://www.youtube.com/watch?v=vid0000001", **over)


def test_a_recording_with_two_topics_is_offered_under_both_and_matched_by_either():
    rows = [_rec("Cash Flow", topics=["Finance & Accounting", "Business Fundamentals"]),
            _rec("Hiring", topics=["Leadership & People"])]
    assert service.recording_topics(rows) == [
        "Business Fundamentals", "Finance & Accounting", "Leadership & People"]
    for topic in ("Finance & Accounting", "Business Fundamentals"):
        assert [r["name"] for r in service.filter_recordings(rows, topic=topic)] == ["Cash Flow"]
    assert [r["name"] for r in service.filter_recordings(rows, query="business")] == ["Cash Flow"]


def test_the_filter_follows_the_live_option_order_and_falls_back_to_the_code():
    rows = [_rec("a", topics=["Other"]), _rec("b", topics=["Operations"]),
            _rec("c", topics=["Retired Category"])]
    assert service.recording_topics(rows, order=["Other", "Operations"]) == [
        "Other", "Operations", "Retired Category"]
    assert service.recording_topics(rows) == ["Operations", "Other", "Retired Category"]


def test_live_topic_order_reads_the_field_the_crm_holds_topics_in():
    class Crm:
        def __init__(self, fields):
            self.fields = fields
            self.asked = []

        async def metadata(self, key):
            return {name: {} for name in self.fields}

        async def metadata_enum_options(self, entity, field):
            self.asked.append(field)
            return ["Z", "Y"]

    new = Crm(["topics", "topic"])
    assert asyncio.run(service.live_topic_order(new)) == ["Z", "Y"] and new.asked == ["topics"]
    old = Crm(["topic"])
    assert asyncio.run(service.live_topic_order(old)) == ["Z", "Y"] and old.asked == ["topic"]
    assert asyncio.run(service.live_topic_order(object())) is None


# --- the pages ---------------------------------------------------------------


def test_the_event_page_eyebrow_names_every_topic():
    for rel in ("frontend/shared/event-body.js", "events/frontend/preview-event.js"):
        js = (ROOT / rel).read_text()
        assert "event.categories" in js, rel
    grid = (ROOT / "events/frontend/app.js").read_text()
    assert "item.categories" in grid


# --- the one-time copy -----------------------------------------------------


def _load_copy_script():
    spec = importlib.util.spec_from_file_location(
        "migrate_event_topics_under_test", ROOT / "scripts/migrate_event_topics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Crm:
    def __init__(self, rows, options):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.options = options
        self.writes = []

    async def metadata_enum_options(self, entity, field):
        return self.options

    async def list(self, entity, *, select=None, max_size=50, offset=0, **kw):
        rows = list(self.rows.values())
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def update(self, entity, record_id, payload):
        self.writes.append((record_id, payload))
        self.rows[record_id].update(payload)
        return self.rows[record_id]

    async def get(self, entity, record_id, select=None):
        return self.rows[record_id]


def test_the_copy_is_dry_run_by_default_idempotent_and_refuses_an_unknown_value(capsys):
    mod = _load_copy_script()
    rows = [
        {"id": "1", "name": "Copy me", "topic": "Operations", "topics": []},
        {"id": "2", "name": "Done", "topic": "Other", "topics": ["Other"]},
        {"id": "3", "name": "Untagged", "topic": "", "topics": None},
        {"id": "4", "name": "Drifted", "topic": "Retired Category", "topics": []},
    ]
    crm = _Crm(rows, ["Operations", "Other"])
    assert asyncio.run(mod.run(crm, apply=False)) == 1      # the drifted one is named
    assert crm.writes == []
    out = capsys.readouterr().out
    assert "WOULD set 'Copy me': topics <- [Operations]" in out
    assert "'Drifted'" in out and "not an option" in out

    assert asyncio.run(mod.run(crm, apply=True)) == 1
    assert crm.writes == [("1", {"topics": ["Operations"]})]
    assert crm.rows["1"]["topics"] == ["Operations"]
    # A second apply has nothing left to copy (the drifted row is still named).
    assert asyncio.run(mod.run(crm, apply=True)) == 1
    assert len(crm.writes) == 1


def test_the_copy_refuses_to_run_before_the_plan(capsys):
    mod = _load_copy_script()
    crm = _Crm([], None)
    assert asyncio.run(mod.run(crm, apply=True)) == 2
    assert "apply scripts/plans/cevent-topics.json first" in capsys.readouterr().err
