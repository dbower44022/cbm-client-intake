"""F2 + F3 — the one visibility rule (who sees an event, where, and when).

Design: prds/events/CBM_Events_Audience_and_Display_Design.md. These tests pin
Doug's rulings: the tick decides whether, the audience decides where, the
display time decides when, and an empty audience carries over from the tick.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.espo import EspoError
from events import config as cfg
from events import service, visibility, zoom_sync
from forms.event_registration.orchestrator import RegistrationRefused, check_open

from tests.test_events_service import make_event

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
PAST = "2026-06-30 12:00:00"
FUTURE = "2026-07-02 12:00:00"
PUBLIC, PORTAL = visibility.SURFACE_PUBLIC, visibility.SURFACE_PORTAL


# --- the carry-over rule ----------------------------------------------------


@pytest.mark.parametrize("audience,ticked,expected", [
    (None, True, "Public"),       # an existing published event stays public
    ("", True, "Public"),
    (None, False, "Internal"),    # an existing unticked row is internal
    ("Public", False, "Public"),
    ("Internal", True, "Internal"),
    ("Somethin' else", True, "Internal"),   # unknown is never public
])
def test_effective_audience(audience, ticked, expected):
    event = make_event(audience=audience, publishToWebsite=ticked)
    assert visibility.effective_audience(event) == expected


# --- whether, where, when ---------------------------------------------------


def test_nothing_is_shown_unticked_whatever_the_audience():
    for audience in (None, "Public", "Internal"):
        event = make_event(audience=audience, publishToWebsite=False)
        assert not visibility.is_shown(event, PUBLIC, now=NOW)
        assert not visibility.is_shown(event, PORTAL, now=NOW)


def test_public_event_shows_on_both_surfaces():
    event = make_event(audience="Public")
    assert visibility.is_shown(event, PUBLIC, now=NOW)
    assert visibility.is_shown(event, PORTAL, now=NOW)


def test_internal_event_shows_on_the_portal_only():
    event = make_event(audience="Internal")
    assert not visibility.is_shown(event, PUBLIC, now=NOW)
    assert visibility.is_shown(event, PORTAL, now=NOW)


def test_cancelled_is_hidden_everywhere():
    event = make_event(audience="Public", status=cfg.STATUS_CANCELLED)
    assert not visibility.is_shown(event, PUBLIC, now=NOW)
    assert not visibility.is_shown(event, PORTAL, now=NOW)


@pytest.mark.parametrize("surface", [PUBLIC, PORTAL])
def test_display_time_holds_the_event_back_on_every_surface(surface):
    """F2-1 / F3-9: before its display time an event is on no page at all."""
    later = make_event(audience="Public", eventReleaseDate=FUTURE)
    earlier = make_event(audience="Public", eventReleaseDate=PAST)
    assert not visibility.is_shown(later, surface, now=NOW)
    assert visibility.is_shown(earlier, surface, now=NOW)
    assert visibility.is_shown(make_event(audience="Public"), surface, now=NOW)


def test_team_limit_is_a_portal_filter():
    event = make_event(audience="Internal", internalTeams=["Mentor Administration Team"])
    member = {"teams": ["Mentor Administration Team"]}
    outsider = {"teams": ["Mentor Team"]}
    admin = {"teams": [], "isAdmin": True}
    assert visibility.is_shown(event, PORTAL, now=NOW, user=member)
    assert not visibility.is_shown(event, PORTAL, now=NOW, user=outsider)
    assert visibility.is_shown(event, PORTAL, now=NOW, user=admin)
    # Empty limit: every signed-in member.
    open_event = make_event(audience="Internal", internalTeams=[])
    assert visibility.is_shown(open_event, PORTAL, now=NOW, user=outsider)


def test_team_limit_never_applies_to_a_public_event():
    event = make_event(audience="Public", internalTeams=["Mentor Administration Team"])
    assert visibility.is_shown(event, PORTAL, now=NOW, user={"teams": []})


# --- the CRM filter ---------------------------------------------------------


def test_where_clauses_only_name_fields_the_crm_has():
    """EspoCRM 400s a where on an unknown attribute (verified 2026-09-29)."""
    bare = visibility.public_where_clauses((), NOW)
    assert [c.get("attribute") for c in bare] == ["publishToWebsite", "status"]
    full = visibility.public_where_clauses(cfg.AUDIENCE_FIELDS, NOW)
    text = repr(full)
    assert "'audience'" in text and "'eventReleaseDate'" in text
    assert "2026-07-01 12:00:00" in text


class MetaEspo:
    """A fake CRM with metadata, which does NOT honour the audience clauses —
    so the per-row re-check is what is being tested."""

    def __init__(self, events, fields=cfg.AUDIENCE_FIELDS, meta_fails=False,
                 options=None):
        self.events = events
        self.fields = {f: {} for f in fields}
        self.meta_fails = meta_fails
        self.options = options or {}
        self.queries = []
        self.created = []
        self.updated = []

    async def metadata(self, key):
        if self.meta_fails:
            raise EspoError("metadata failed")
        return self.fields

    async def metadata_enum_options(self, entity, field):
        return self.options.get(field)

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        self.queries.append(where or [])
        rows = [r for r in self.events if r.get("publishToWebsite")]
        for clause in where or []:
            if clause.get("attribute") == "slug":
                rows = [r for r in rows if r.get("slug") == clause["value"]]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def create(self, entity, payload):
        self.created.append(payload)
        return {"id": "new1"}

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "slug": "x", **(self.created[-1] if self.created else {})}

    async def update(self, entity, record_id, payload):
        self.updated.append(payload)
        return {}


async def test_public_reads_drop_internal_and_not_yet_shown_events():
    crm = MetaEspo([
        make_event(id="pub", slug="pub", audience="Public", dateStart=FUTURE),
        make_event(id="int", slug="int", audience="Internal", dateStart=FUTURE),
        make_event(id="later", slug="later", audience="Public", dateStart=FUTURE,
                   eventReleaseDate="2099-01-01 00:00:00"),
        make_event(id="legacy", slug="legacy", dateStart=FUTURE),  # empty audience, ticked
    ])
    rows = await service.list_upcoming(crm, now=NOW)
    assert {r["id"] for r in rows} == {"pub", "legacy"}
    assert await service.get_by_slug(crm, "int") is None
    assert await service.get_by_slug(crm, "later") is None
    assert (await service.get_by_slug(crm, "pub"))["id"] == "pub"


async def test_a_failed_metadata_read_fails_closed():
    """Guessing 'no audience field' during an outage would publish Internal
    events, so the read raises instead (the public route answers 502)."""
    crm = MetaEspo([make_event()], meta_fails=True)
    with pytest.raises(EspoError):
        await service.list_upcoming(crm, now=NOW)


async def test_a_client_without_metadata_behaves_as_before():
    assert await service.live_event_fields(object()) == frozenset()


# --- the public registration form ------------------------------------------


class RegCrm:
    def __init__(self, event):
        self.event = event

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        return {"total": 1, "list": [self.event]}


@pytest.mark.parametrize("over", [
    {"audience": "Internal"},
    {"audience": "Public", "eventReleaseDate": "2099-01-01 00:00:00"},
    {"publishToWebsite": False},
])
async def test_registration_refuses_what_the_pages_do_not_show(over):
    crm = RegCrm(make_event(dateStart="2099-06-01 12:00:00", **over))
    with pytest.raises(RegistrationRefused, match="could not be found"):
        await check_open(crm, "grant-writing-basics")


async def test_registration_accepts_a_shown_public_event():
    crm = RegCrm(make_event(audience="Public", dateStart="2099-06-01 12:00:00"))
    assert (await check_open(crm, "grant-writing-basics"))["id"] == "ev1"


# --- Zoom: Public events only (ruling D2) ----------------------------------


def test_zoom_never_creates_for_an_internal_event_even_forced():
    event = make_event(zoomWebinarId="", audience="Internal")
    assert zoom_sync.decide(event)[0] == "skip"
    assert zoom_sync.decide(event, force=True)[0] == "skip"


def test_zoom_creates_for_a_shown_public_event():
    assert zoom_sync.decide(make_event(zoomWebinarId="", audience="Public"))[0] == "create"


def test_zoom_leaves_an_existing_webinar_alone_when_the_event_turns_internal():
    event = make_event(audience="Internal")          # still has its webinar id
    assert zoom_sync.decide(event, previous=dict(event))[0] == "skip"


# --- the editor's save rules -----------------------------------------------


async def test_new_event_defaults_to_public_this_chapter_and_includes_itself():
    crm = MetaEspo([], options={"reachChapters": ["cleveland", "boston"],
                                "internalTeams": ["Mentor Team"]})
    await service.create_event(crm, {"name": "Talk"}, chapter_key="cleveland")
    payload = crm.created[-1]
    assert payload["audience"] == "Public"
    assert payload["publicReach"] == "This chapter"
    assert payload["reachChapters"] == ["cleveland"]


async def test_own_chapter_is_added_but_never_an_unknown_one():
    crm = MetaEspo([], options={"reachChapters": ["boston"]})
    await service.create_event(crm, {"name": "Talk", "reachChapters": ["boston"]},
                               chapter_key="cleveland")
    assert crm.created[-1]["reachChapters"] == ["boston"]   # left alone, logged


async def test_audience_fields_are_dropped_when_the_crm_lacks_them():
    crm = MetaEspo([], fields=())
    await service.create_event(crm, {"name": "Talk", "audience": "Internal",
                                     "internalTeams": ["X"]}, chapter_key="cleveland")
    assert "audience" not in crm.created[-1]
    assert "internalTeams" not in crm.created[-1]


async def test_a_drifted_team_name_is_dropped_rather_than_failing_the_save():
    crm = MetaEspo([], options={"internalTeams": ["Mentor Team"],
                                "reachChapters": ["cleveland"]})
    await service.create_event(
        crm, {"name": "Talk", "internalTeams": ["Mentor Team", "Old Team", "Mentor Team"]},
        chapter_key="cleveland",
    )
    assert crm.created[-1]["internalTeams"] == ["Mentor Team"]


def test_save_warnings():
    unticked = make_event(publishToWebsite=False, eventReleaseDate=FUTURE)
    assert any("not ticked" in w for w in visibility.save_warnings(unticked, NOW))
    after_start = make_event(dateStart="2026-07-05 12:00:00",
                             eventReleaseDate="2026-07-06 12:00:00")
    assert any("after the event starts" in w
               for w in visibility.save_warnings(after_start, NOW))
    # A recording released after a past event: no warning (F2-5).
    past = make_event(dateStart="2026-06-01 12:00:00", eventReleaseDate=FUTURE)
    assert visibility.save_warnings(past, NOW) == []


def test_staff_state():
    assert visibility.staff_state(make_event(publishToWebsite=False), NOW)["label"] == "Hidden"
    assert visibility.staff_state(
        make_event(eventReleaseDate=FUTURE), NOW)["label"] == "Appears 2026-07-02"
    assert visibility.staff_state(make_event(), NOW)["label"] == "Public"
    assert visibility.staff_state(
        make_event(audience="Internal", internalTeams=["T"]), NOW)["label"] == "Internal, limited"


# --- the guard: one rule, one place ----------------------------------------


def test_nothing_reads_the_tick_for_itself():
    """Every visibility decision goes through events/visibility.py. A second
    hand-rolled check is how the registration form came to accept sign-ups for
    events the pages hid (found while designing F3)."""
    pattern = re.compile(r"""\.get\(\s*(["']publishToWebsite["']|cfg\.SHOW_FIELD)""")
    offenders = []
    for folder in ("events", "portal", "forms/event_registration"):
        for path in (ROOT / folder).rglob("*.py"):
            if path.name == "visibility.py":
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == [], offenders
