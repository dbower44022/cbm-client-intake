"""The chapter website's key pages — prds/chapter-website-plan.md, piece B.

Covers: who appears, the cmw- prefix on every class (ruling 33, WT-44), the
mentor's own text cleaned before it reaches a public page, one CRM read per
cache period with the last copy served through an outage, and a switched-off
or unservable page answering 404.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from core.espo import EspoError
from forms import info_request
from website import content

_STATIC = Path(__file__).resolve().parents[1] / "website" / "static"

MENTORS = [
    {"id": "m1", "name": "Ada Lovelace", "mentorStatus": "Active", "publicProfile": True,
     "acceptingNewClients": True, "mentorTitle": "Retired engineer", "contactRecordId": "c1",
     "aboutMentor": '<p class="x" style="color:red" onclick="evil()">I build <b>things</b>.'
                    '<script>alert(1)</script> <a href="javascript:alert(1)">bad</a> '
                    '<a href="https://example.org" class="y">good</a></p><img src="x">',
     "areaOfExpertise": ["Finance"], "industryExperience": ["Manufacturing"],
     "fluentLanguages": ["English", "Spanish"], "profilePhotoId": "att1"},
    {"id": "m2", "name": "Grace Hopper", "mentorStatus": "Active", "publicProfile": True,
     "acceptingNewClients": False, "mentorTitle": "Admiral", "contactRecordId": "c2",
     "aboutMentor": "", "areaOfExpertise": "Operations", "profilePhotoId": None},
    {"id": "m3", "name": "Hidden One", "mentorStatus": "Active", "publicProfile": False},
    {"id": "m4", "name": "Former Mentor", "mentorStatus": "Inactive", "publicProfile": True},
    {"id": "m5", "name": "Ada Lovelace", "mentorStatus": "Active", "publicProfile": True,
     "acceptingNewClients": True, "contactRecordId": None},
]
CONTACTS = [
    {"id": "c1", "firstName": "Ada", "lastName": "Lovelace", "cLinkedInProfile": "https://linkedin.com/in/ada"},
    {"id": "c2", "firstName": "Grace", "lastName": "Hopper"},
]


class FakeCRM:
    calls = 0
    fail = False

    async def metadata(self, key):
        return {"mentorTitle": {}, "aboutMentor": {}}

    async def list(self, entity, **kw):
        if FakeCRM.fail:
            raise EspoError("CRM down")
        FakeCRM.calls += 1
        if entity == "CMentorProfile":
            return {"list": MENTORS}
        if entity == "Contact":
            return {"list": CONTACTS}
        return {"list": []}

    async def download_attachment(self, attachment_id):
        return b"\x89PNG\r\n\x1a\nphoto", "image/png"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    apply_overrides({})
    content.cache.clear()
    FakeCRM.calls, FakeCRM.fail = 0, False
    yield
    apply_overrides({})
    content.cache.clear()
    get_settings.cache_clear()


def _client(monkeypatch, **overrides) -> TestClient:
    monkeypatch.setenv("WEBSITE_API", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.events_client_factory = lambda: FakeCRM()
    apply_overrides({"website_page_mentors": "true", "website_page_events": "true",
                     "website_page_recordings": "true", **overrides})
    return TestClient(app)


def _classes(markup: str) -> set[str]:
    out: set[str] = set()
    for attr in re.findall(r'class="([^"]*)"', markup):
        out.update(attr.split())
    return out


# --- who appears -----------------------------------------------------------------

def test_only_active_public_mentors_appear(monkeypatch):
    html = _client(monkeypatch).get("/api/website/pages/mentors").json()["html"]
    assert "Ada Lovelace" in html and "Grace Hopper" in html
    assert "Hidden One" not in html and "Former Mentor" not in html


def test_a_shared_name_gets_a_distinct_slug(monkeypatch):
    paths = _client(monkeypatch).get("/api/website/sitemap").json()["paths"]
    assert paths == ["/mentors/ada-lovelace/", "/mentors/ada-lovelace-2/", "/mentors/grace-hopper/"]


def test_a_mentor_not_taking_clients_still_appears_and_says_why(monkeypatch):
    html = _client(monkeypatch).get("/api/website/pages/mentors/grace-hopper").json()["html"]
    assert "not taking new clients" in html
    assert 'href="/request-a-mentor/"' in html


def test_a_mentor_taking_clients_can_be_requested_by_name(monkeypatch):
    page = _client(monkeypatch).get("/api/website/pages/mentors/ada-lovelace").json()
    assert page["title"] == "Ada Lovelace"
    assert 'href="/request-a-mentor/?mentor=ada-lovelace"' in page["html"]
    assert "Request Ada as your mentor" in page["html"]


def test_an_unknown_mentor_is_404(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/website/pages/mentors/nobody").status_code == 404
    assert client.get("/api/website/pages/mentors/hidden-one").status_code == 404


# --- the mentor's own text --------------------------------------------------------

def test_the_mentors_text_is_cleaned(monkeypatch):
    html = _client(monkeypatch).get("/api/website/pages/mentors/ada-lovelace").json()["html"]
    about = html.split('<div class="cmw-profile__about">', 1)[1].split("</div>", 1)[0]
    assert "<script" not in about and "onclick" not in about and "style=" not in about
    assert "javascript:" not in about and "<img" not in about and "class=" not in about
    assert '<a href="https://example.org" rel="nofollow noopener">good</a>' in about
    assert "<b>things</b>" in about


def test_a_summary_falls_back_to_the_about_text(monkeypatch):
    html = _client(monkeypatch).get("/api/website/pages/mentors").json()["html"]
    assert "I build things." in html


# --- the prefix rule (ruling 33, WT-44) ----------------------------------------------

def test_every_class_in_every_page_starts_with_cmw(monkeypatch):
    client = _client(monkeypatch)
    pages = [client.get("/api/website/pages/mentors").json()]
    pages += [client.get(f"/api/website/pages{p[:-1]}").json()
              for p in client.get("/api/website/sitemap").json()["paths"]]
    events = [{"monthShort": "Dec", "day": "3", "time": "6pm", "topic": "Cash flow",
               "summary": "s", "url": "https://apps.example.org/webinars/x", "registrationOpen": True}]
    recordings = [{"dateLabel": "NOV 1, 2026", "title": "Pricing", "categories": ["Finance"],
                   "summary": "s", "url": "https://apps.example.org/webinars/y"}]
    pages += [content.page_events(events), content.page_events([]),
              content.page_recordings(recordings), content.page_recordings([]),
              content.page_mentors("https://a", [])]
    bad = set().union(*(_classes(p["html"]) for p in pages)) - {c for c in set().union(
        *(_classes(p["html"]) for p in pages)) if c.startswith("cmw-")}
    assert not bad, f"classes without the cmw- prefix: {sorted(bad)}"


def test_every_class_in_the_stylesheet_starts_with_cmw():
    css = (_STATIC / "website.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    bad = sorted({c for c in re.findall(r"\.([a-zA-Z][\w-]*)", css)
                  if not c.startswith("cmw-") and not re.fullmatch(r"\d+\w*", c)})
    assert not bad, f"classes without the cmw- prefix: {bad}"


# --- search, cache, outage ------------------------------------------------------------

def test_search_matches_every_word(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/website/mentors.json?q=spanish finance").json()["slugs"] == ["ada-lovelace"]
    assert len(client.get("/api/website/mentors.json").json()["slugs"]) == 3


def test_the_crm_is_read_once_per_cache_period(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(5):
        client.get("/api/website/mentors.json?q=ada")
        client.get("/api/website/pages/mentors")
    assert FakeCRM.calls == 2  # the mentors and their contacts, once


def test_the_last_copy_is_served_when_the_crm_is_down(monkeypatch):
    client = _client(monkeypatch, website_cache_seconds="0")
    assert client.get("/api/website/pages/mentors").status_code == 200
    FakeCRM.fail = True
    resp = client.get("/api/website/pages/mentors")
    assert resp.status_code == 200 and "Ada Lovelace" in resp.json()["html"]


def test_with_no_copy_an_outage_is_503_not_500(monkeypatch):
    client = _client(monkeypatch)
    FakeCRM.fail = True
    assert client.get("/api/website/pages/mentors").status_code == 503


# --- switches -------------------------------------------------------------------------

def test_a_switched_off_page_is_404(monkeypatch):
    client = _client(monkeypatch, website_page_mentors="false")
    assert client.get("/api/website/pages/mentors").status_code == 404
    assert client.get("/api/website/mentors.json").status_code == 404
    assert client.get("/api/website/sitemap").json()["paths"] == []


@pytest.mark.parametrize("page", ["partners", "sponsors", "stories", "anything"])
def test_an_unserved_page_is_404(monkeypatch, page):
    assert _client(monkeypatch).get(f"/api/website/pages/{page}").status_code == 404


def test_the_whole_connection_off_is_404(monkeypatch):
    client = _client(monkeypatch)
    apply_overrides({"website_api": "false"})
    for path in ("/api/website/pages/mentors", "/api/website/sitemap", "/assets/website.css"):
        assert client.get(path).status_code == 404, path


# --- photos and assets ------------------------------------------------------------------

def test_a_photo_is_served_for_a_shown_mentor_only(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/api/website/mentors/ada-lovelace/photo")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"
    assert client.get("/api/website/mentors/grace-hopper/photo").status_code == 404
    assert client.get("/api/website/mentors/hidden-one/photo").status_code == 404


def test_the_page_points_at_the_photo_and_the_search_on_this_application(monkeypatch):
    html = _client(monkeypatch).get("/api/website/pages/mentors").json()["html"]
    assert 'data-cmw-search="https://apps.example.org/api/website/mentors.json"' in html
    assert 'src="https://apps.example.org/api/website/mentors/ada-lovelace/photo"' in html


def test_the_styles_and_search_script_are_served(monkeypatch):
    client = _client(monkeypatch)
    css = client.get("/assets/website.css")
    js = client.get("/assets/search.js")
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]


def test_the_search_may_be_fetched_by_the_chapter_website(monkeypatch):
    client = _client(monkeypatch, website_origins="https://site.example.org")
    resp = client.get("/api/website/mentors.json?q=ada", headers={"Origin": "https://site.example.org"})
    assert resp.headers.get("access-control-allow-origin") == "https://site.example.org"


# --- events and recordings ---------------------------------------------------------------

def test_events_and_recordings_pages(monkeypatch):
    from events import service as events_service

    async def upcoming(client, **kw):
        return [{"monthShort": "Dec", "day": "3", "time": "6:00 PM", "topic": "Cash flow basics",
                 "summary": "Plan ahead.", "url": "https://apps.example.org/webinars/cash",
                 "registrationOpen": True}]

    async def published(client):
        return [{"id": "e1", "name": "Pricing", "slug": "pricing", "dateStart": "2026-10-01 22:00:00",
                 "description": "How to price.", "recordingUrl": "https://youtu.be/abc"}]

    monkeypatch.setattr(events_service, "upcoming_payload", upcoming)
    monkeypatch.setattr(events_service, "published_recordings", published)
    client = _client(monkeypatch)
    events = client.get("/api/website/pages/events").json()
    assert "Cash flow basics" in events["html"] and ">Register</a>" in events["html"]
    recs = client.get("/api/website/pages/recordings").json()
    assert "Pricing" in recs["html"] and "How to price." in recs["html"]
