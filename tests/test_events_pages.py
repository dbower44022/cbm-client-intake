"""The PUBLIC programme pages at /webinars/.

These replace the WordPress plugin: the marketing site redirects here, so this
app serves the page a member of the public actually reads (Doug, 2026-09-11).

Two properties carry the weight, and both are things a static file could not
give us:

* the per-event ``<head>`` is filled **server-side**, because a social crawler
  runs no JavaScript and would otherwise share every event as a blank card;
* an unpublished event **404s**, because ``CEvent`` doubles as the internal
  calendar and a page that merely rendered empty would still confirm it exists.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from events import service
from forms import info_request

from tests.test_events_public import FakeEspo, build
from tests.test_events_service import make_event


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- mounting ---------------------------------------------------------------


def test_pages_absent_when_the_public_api_is_off(monkeypatch):
    """An unconfigured deploy serves no public page at all."""
    client, _ = build(monkeypatch, events=[make_event()], public_api=False)
    assert client.get("/webinars/").status_code == 404
    assert client.get("/webinars-assets/public.css").status_code == 404


def test_pages_absent_when_the_feature_is_off(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()], enabled=False)
    assert client.get("/webinars/").status_code == 404


# --- the programme page -----------------------------------------------------


def test_programme_page_is_served_with_its_assets(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    page = client.get("/webinars/")
    assert page.status_code == 200
    assert "Workshops and Webinars" in page.text
    # It drives the REAL renderer and wears the site's own stylesheet, so the
    # staff preview and the live page stay one code path.
    assert "/events-plugin/cbm-events.js" in page.text
    assert "/events-plugin/cbm-events.css" in page.text
    assert client.get("/webinars-assets/public.css").status_code == 200
    assert client.get("/webinars-assets/public.js").status_code == 200
    assert client.get("/events-plugin/cbm-events.js").status_code == 200


def test_bare_webinars_redirects_to_the_slashed_form(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    resp = client.get("/webinars", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/webinars/"


def test_programme_carries_the_presenting_invitation(monkeypatch):
    """Carried over from the marketing site's page, which now redirects here —
    otherwise this invitation would have nowhere left to live."""
    monkeypatch.setenv("EVENTS_CONTACT_EMAIL", "info@example.org")
    client, _ = build(monkeypatch, events=[make_event()])
    page = client.get("/webinars/")
    assert "Interested in Presenting or Hosting?" in page.text
    assert "info@example.org" in page.text


def test_contact_address_falls_back_to_the_ops_mailbox(monkeypatch):
    monkeypatch.setenv("OPS_MAILBOX", "ops@example.org")
    client, _ = build(monkeypatch, events=[make_event()])
    assert "ops@example.org" in client.get("/webinars/").text


def test_no_contact_address_leaves_no_broken_mailto(monkeypatch):
    """With neither setting configured the invitation still reads — it simply
    carries no address, rather than a mailto: to nothing."""
    client, _ = build(monkeypatch, events=[make_event()])
    page = client.get("/webinars/")
    assert "Interested in Presenting or Hosting?" in page.text
    assert "mailto:" not in page.text


def test_every_branding_token_is_substituted(monkeypatch):
    """The guard the branding module exists to hold: no page may go out with a
    token still in it."""
    monkeypatch.setenv("ORGANIZATION_NAME", "Lakeside Business Mentors")
    client, _ = build(monkeypatch, events=[make_event()])
    for path in ("/webinars/", "/webinars/grant-writing-basics"):
        text = client.get(path).text
        assert "{{" not in text, path
        assert "Lakeside Business Mentors" in text, path


def test_page_links_back_to_the_organisations_own_website(monkeypatch):
    """A visitor who followed a link from the site's menu must not be stranded
    on a page with no way back."""
    monkeypatch.setenv("ORGANIZATION_WEBSITE_URL", "https://example.org")
    client, _ = build(monkeypatch, events=[make_event()])
    assert 'href="https://example.org"' in client.get("/webinars/").text


# --- one event's page -------------------------------------------------------


def test_event_page_fills_the_social_card_server_side(monkeypatch):
    """The whole reason this is a route and not a static file. A crawler runs
    no JavaScript; these tags must be in the bytes we send."""
    client, _ = build(monkeypatch, events=[make_event()])
    page = client.get("/webinars/grant-writing-basics")
    assert page.status_code == 200
    assert 'property="og:title" content="Grant Writing Basics"' in page.text
    assert 'property="og:type" content="article"' in page.text
    assert "<title>Grant Writing Basics" in page.text
    # The slug rides on the body so the page script never parses its own URL.
    assert 'data-event-slug="grant-writing-basics"' in page.text


def test_event_page_404s_for_an_unpublished_event(monkeypatch):
    """The publish gate is the page, not the content. CEvent doubles as the
    internal calendar, so an internal meeting must not be discoverable by URL."""
    hidden = make_event()
    hidden["publishToWebsite"] = False
    client, _ = build(monkeypatch, events=[hidden])
    assert client.get("/webinars/grant-writing-basics").status_code == 404


def test_event_page_404s_for_an_unknown_slug(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    assert client.get("/webinars/no-such-event").status_code == 404


def test_event_page_survives_a_crm_outage_without_leaking_it(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()], fail=True)
    resp = client.get("/webinars/grant-writing-basics")
    assert resp.status_code == 502
    assert "CRM" not in resp.text


def test_event_title_is_escaped_into_the_head(monkeypatch):
    """Event content is authored in the CRM. It reaches the <head> as an
    attribute value, so it is escaped there like anywhere else."""
    nasty = make_event()
    nasty["name"] = 'Grant "Writing" & <script>alert(1)</script>'
    client, _ = build(monkeypatch, events=[nasty])
    page = client.get("/webinars/grant-writing-basics")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


# --- the URL in the public payload ------------------------------------------


def test_payload_url_points_at_this_app_by_default(monkeypatch):
    """It used to name the marketing site's /webinars/<slug>, which 404s — every
    shared link would have gone nowhere."""
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    client, _ = build(monkeypatch, events=[make_event()])
    row = client.get("/api/events/upcoming").json()["webinars"][0]
    assert row["url"] == "https://apps.example.org/webinars/grant-writing-basics"


def test_payload_url_honours_an_explicit_override(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    monkeypatch.setenv("EVENTS_PUBLIC_BASE_URL", "https://elsewhere.example/w")
    client, _ = build(monkeypatch, events=[make_event()])
    row = client.get("/api/events/upcoming").json()["webinars"][0]
    assert row["url"] == "https://elsewhere.example/w/grant-writing-basics"


def test_payload_url_is_empty_rather_than_wrong_with_nothing_configured(monkeypatch):
    """An empty link renders the title as plain text. One pointing at a 404 is
    not recoverable."""
    client, _ = build(monkeypatch, events=[make_event()])
    row = client.get("/api/events/upcoming").json()["webinars"][0]
    assert row["url"] == ""


# --- the public page stylesheet may not style a contract class ---------------


def test_public_css_styles_no_contract_class():
    """The lesson of 2026-08-16: an approximation in a second stylesheet hid a
    class-name drift for three weeks, because our own CSS styled our own wrong
    names. The site's stylesheet owns every contract class; this one owns the
    chrome around it."""
    from pathlib import Path

    from tests.test_events_graphic import CONTRACT_CLASSES, _styles

    css = (
        Path(__file__).resolve().parents[1]
        / "events" / "public_frontend" / "public.css"
    ).read_text(encoding="utf-8")
    offenders = [c for c in CONTRACT_CLASSES if _styles(css, c)]
    assert not offenders, f"public.css must not style contract classes: {offenders}"


def test_the_two_panels_use_their_own_wrapper_scopes(monkeypatch):
    """The site's stylesheet scopes the calendar under `.cbm-wb` and the
    recorded library under `.cbm-yt`, each as an ANCESTOR of `.panel`. Reusing
    one wrapper for both, or collapsing wrapper and panel onto one element,
    leaves a section unstyled and raises no error — which is exactly what the
    first cut of this page did."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert '<div class="cbm-wb">' in html
    assert '<div class="cbm-yt">' in html
    # The wrapper is an ancestor, never the panel itself.
    assert 'class="cbm-wb panel"' not in html
    assert 'class="cbm-yt panel"' not in html


def test_the_logo_stays_hidden_until_one_is_configured(monkeypatch):
    """`display:` on a class beats the `hidden` attribute. Without an explicit
    guard the unconfigured logo rendered as a broken image on every page."""
    from pathlib import Path

    css = (
        Path(__file__).resolve().parents[1]
        / "events" / "public_frontend" / "public.css"
    ).read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css
    client, _ = build(monkeypatch, events=[make_event()])
    assert "hidden id=\"brandLogo\"" in client.get("/webinars/").text


def test_the_event_page_orders_the_date_the_way_people_read_it():
    """The payload's `month` is "September 2026" and `day` is "26", because the
    calendar renders them as a two-line chip. Joined in payload order they read
    "September 2026 26" — which is what this page showed until it was opened in
    a browser."""
    from pathlib import Path

    js = (
        Path(__file__).resolve().parents[1]
        / "events" / "public_frontend" / "event.js"
    ).read_text(encoding="utf-8")
    assert "function whenLine(event)" in js
    assert 'day + " " + month' in js
    # The naive join is what produced the defect; it must not come back.
    assert "[event.month, event.day, event.time]" not in js


# --- the marketing page's own chrome, carried across -------------------------


def test_the_hero_and_band_come_across(monkeypatch):
    """The page that redirects here opens with a navy hero and a gold band. Both
    are content on that page, so both had to move — the same omission as the
    presenting invitation, found the same way, by looking at the two side by
    side."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert "Free Education for Every Stage of Your Business" in html
    assert "Launch" in html and "Grow" in html and "Thrive" in html
    assert "Answered Free, Live, Straightforward" in html
    # The heading carries the organisation, not a literal.
    assert "Cleveland Business Mentors Webinars" in html


def test_each_hero_line_can_be_emptied(monkeypatch):
    """A chapter with nothing to say there gets a clean page, not a placeholder."""
    monkeypatch.setenv("EVENTS_HERO_TAGLINE", "")
    monkeypatch.setenv("EVENTS_HERO_PILLARS", "")
    monkeypatch.setenv("EVENTS_HERO_BAND", "")
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert "Free Education for Every Stage" not in html
    assert "Answered Free, Live, Straightforward" not in html
    # The heading is not one of the three and stays.
    assert "Webinars</h1>" in html


def test_the_site_menu_is_rendered_server_side(monkeypatch):
    """A menu that appears a moment after the page is worse than none, and this
    is the visitor's only way on to the rest of the site."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    for label in ("Home", "About", "Mentoring", "Resources", "Support Us", "Contact"):
        assert f">{label}</a>" in html, label
    assert 'href="https://clevelandbusinessmentors.org/about/"' in html
    # The site's own Webinars entry leads back here; mark it rather than let a
    # visitor make the round trip.
    assert 'aria-current="page"' in html


def test_the_menu_follows_the_configured_website(monkeypatch):
    """A chapter whose site has the same shape changes one setting, not seven."""
    monkeypatch.setenv("ORGANIZATION_WEBSITE_URL", "https://lakeside.example")
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert 'href="https://lakeside.example/about/"' in html
    assert "clevelandbusinessmentors.org/about/" not in html


def test_the_menu_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("ORGANIZATION_SITE_NAV", "")
    client, _ = build(monkeypatch, events=[make_event()])
    assert 'class="pub__nav"' not in client.get("/webinars/").text


def test_a_menu_label_is_escaped(monkeypatch):
    """The menu is a setting, and a setting is configuration an administrator
    types — escaped on the way into markup like every other value here."""
    monkeypatch.setenv("ORGANIZATION_SITE_NAV", '<script>x</script>|/x/')
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_event_page_carries_the_menu_too(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/grant-writing-basics").text
    assert 'class="pub__nav"' in html
    assert "All webinars and workshops" in html


def test_the_panels_use_the_sites_own_wording(monkeypatch):
    """These headings were mine, and they did not match the page this replaces."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert "Calendar of Upcoming Webinars" in html
    assert "Find a Recorded Webinar" in html
    assert "Results link directly to the recording." in html
    assert "Most Recent" in html


# --- the default event graphic ----------------------------------------------


def test_an_event_with_no_picture_gets_the_configured_default(monkeypatch):
    """What this actually fixes: an image-less event had an EMPTY og:image, so
    sharing its page produced a card with no picture at all."""
    monkeypatch.setenv("EVENTS_DEFAULT_GRAPHIC_URL", "https://example.org/house.png")
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/grant-writing-basics").text
    assert 'property="og:image" content="https://example.org/house.png"' in html


def test_no_default_configured_leaves_the_event_without_one(monkeypatch):
    """Empty means an image-less event has no image, exactly as before."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/grant-writing-basics").text
    assert 'property="og:image" content=""' in html


def test_a_recordings_own_video_thumbnail_beats_the_default():
    """Ordering matters: a recorded webinar's own still frame says more about it
    than a house card, so the default fills a hole neither the event's own
    graphic nor the video could."""
    from events import service
    from tests.test_events_service import make_event as _ev

    recorded = _ev(recordingUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    payload = service.public_event(recorded, default_image="https://example.org/house.png")
    assert payload["thumbnailUrl"]
    assert payload["imageUrl"] == ""      # the renderer falls through to the video


def test_the_events_own_graphic_beats_the_default():
    from events import service
    from tests.test_events_service import make_event as _ev

    with_graphic = _ev(eventGraphicId="att123456789")
    payload = service.public_event(
        with_graphic, api_base_url="https://apps.example.org",
        default_image="https://example.org/house.png",
    )
    assert payload["imageUrl"].startswith("https://apps.example.org/api/events/")


# --- consent is an active tick on BOTH doors --------------------------------


def test_the_event_page_asks_for_consent_and_names_the_three_documents(monkeypatch):
    """Doug's ruling, 2026-09-13, option A. Registration used to record no
    consent at all, because the only line shown promised emails about webinars
    while the record carries three separate agreements. Recording three
    acceptances nobody was shown would have been untrue; recording none was the
    lesser wrong. Now it asks properly."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/grant-writing-basics").text
    assert 'id="consent"' in html
    assert "Terms of Use" in html
    assert "Privacy Policy" in html
    assert "Code of Conduct" in html
    # Linked, not just named, and pointing at the live documents.
    assert "clevelandbusinessmentors.org/client-code-of-conduct/" in html
    assert "clevelandbusinessmentors.org/privacy-policy/" in html


def test_the_policy_links_follow_their_settings(monkeypatch):
    """A chapter points at its own documents without a code change."""
    monkeypatch.setenv("POLICY_TERMS_URL", "https://lakeside.example/terms/")
    client, _ = build(monkeypatch, events=[make_event()])
    assert 'href="https://lakeside.example/terms/"' in client.get(
        "/webinars/grant-writing-basics"
    ).text


def test_the_calendar_dialog_gets_its_policy_links_from_the_page(monkeypatch):
    """The renderer is served with no template substitution, so it cannot carry
    the links itself — the host page hands them over."""
    client, _ = build(monkeypatch, events=[make_event()])
    js = client.get("/webinars-assets/public.js").text
    assert "CBMEvents.config.policies" in js
    assert "clevelandbusinessmentors.org/privacy-policy/" in js
    # And the value sent is what was ticked, never a hardcoded answer.
    assert "consent: !!fields.consent," in js
    assert "consent: false," not in js


def test_neither_door_can_register_without_the_tick():
    """One door recording consent and the other not would be worse than
    neither doing so."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    renderer = (root / "wp-plugin" / "cbm-events" / "assets" / "cbm-events.js").read_text()
    assert "if (!fields.consent)" in renderer
    assert "cbm-consent-box" in renderer
    page = (root / "events" / "public_frontend" / "event.js").read_text()
    assert "if (!body.consent)" in page
    assert 'consent: !!$("consent").checked,' in page


# --- the recorded library's controls -----------------------------------------


def _public_js() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1]
        / "events" / "public_frontend" / "public.js"
    ).read_text(encoding="utf-8")


def test_the_topic_selector_comes_before_the_search_box(monkeypatch):
    """The search runs INSIDE the chosen topic, and reading order is the only
    thing telling a visitor which narrows which (Doug, 2026-09-14)."""
    client, _ = build(monkeypatch, events=[make_event()])
    html = client.get("/webinars/").text
    assert html.index('id="topicFilterRow"') < html.index('class="pub__search"')
    assert html.index('id="topicFilter"') < html.index('id="searchBox"')


def test_clearing_the_search_reloads_without_pressing_search():
    """The native clear control is an "x" that looks like it undoes the search.
    Leaving the old results up until Search is pressed again reads as broken."""
    js = _public_js()
    assert '$("searchBox").addEventListener("input"' in js
    assert 'lastQuery !== ""' in js
    # `input`, not the `search` event: Firefox does not raise that one.
    assert 'addEventListener("search"' not in js


def test_clearing_only_reloads_when_there_was_a_search_to_undo():
    """Otherwise every keystroke on an empty box would hit the server."""
    js = _public_js()
    assert 'lastQuery = q;' in js
    assert 'var lastQuery = "";' in js


def test_the_placeholder_names_the_topic_being_searched():
    """An empty result while a topic is set otherwise looks like the search is
    broken rather than scoped."""
    js = _public_js()
    assert "function describeSearchScope()" in js
    assert '"Search within " + topic' in js
