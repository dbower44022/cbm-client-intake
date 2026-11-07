"""Forms in website frames — prds/chapter-website-plan.md, piece C.

The rule most worth guarding: with FORM_FRAMING off nothing changes for a site
that frames a form today (Cleveland's website frames three production forms).
On, only the chapter website addresses may frame a public form, the height goes
only to them, and ``?embed=1`` takes the Website colours.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from forms import ALL_SPECS

ROOT = Path(__file__).resolve().parents[1]
FORM_PAGES = sorted(ROOT.glob("forms/*/frontend/index.html"))


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    apply_overrides({})
    yield
    apply_overrides({})
    get_settings.cache_clear()


def _client(**overrides) -> TestClient:
    get_settings.cache_clear()
    client = TestClient(create_app(ALL_SPECS))
    apply_overrides(overrides)
    return client


SITE = "https://chapter-demo.example.org"


# --- off: nothing changes ------------------------------------------------------

def test_off_sends_no_frame_restriction():
    resp = _client().get("/client-intake/")
    assert resp.status_code == 200
    assert "content-security-policy" not in resp.headers


def test_off_the_scripts_are_empty_but_present():
    client = _client()
    js = client.get("/assets/frame.js")
    css = client.get("/assets/embed.css")
    assert js.status_code == 200 and "postMessage" not in js.text
    assert css.status_code == 200 and "--cbm-" not in css.text


# --- on ----------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/client-intake/", "/info-request/", "/volunteer/", "/partner/", "/sponsor/"])
def test_on_only_the_chapter_website_may_frame_a_form(path):
    resp = _client(form_framing="true", website_origins=SITE).get(path)
    assert resp.status_code == 200
    assert resp.headers["content-security-policy"] == f"frame-ancestors 'self' {SITE}"


def test_on_other_pages_are_untouched():
    client = _client(form_framing="true", website_origins=SITE)
    assert "content-security-policy" not in client.get("/healthz").headers
    assert "content-security-policy" not in client.get("/client-intake/app.js").headers


def test_the_height_goes_only_to_the_chapter_website():
    js = _client(form_framing="true", website_origins=f"{SITE}, http://localhost:8080/").get("/assets/frame.js").text
    assert "__ORIGINS__" not in js
    assert f'["{SITE}", "http://localhost:8080"]' in js
    assert '"*"' not in js


def test_embed_styles_take_the_website_colours():
    css = _client(form_framing="true", website_color_accent_1="#0B6E4F",
                  website_font_body="Georgia, serif").get("/assets/embed.css").text
    assert "--cbm-navy: #0B6E4F;" in css and "--cbm-font-body: Georgia, serif;" in css
    assert ".cbm-footer { display: none; }" in css


def test_a_broken_colour_is_left_out_of_the_embed_styles(monkeypatch):
    monkeypatch.setenv("WEBSITE_COLOR_ACCENT_1", "red;}*{display:none")
    css = _client(form_framing="true").get("/assets/embed.css").text
    assert "--cbm-navy" not in css and "display:none" not in css


# --- every public form loads the script ----------------------------------------------

@pytest.mark.parametrize("page", FORM_PAGES, ids=lambda p: p.parent.parent.name)
def test_every_public_form_loads_the_frame_script_after_busy(page):
    html = page.read_text(encoding="utf-8")
    busy = html.find('src="/shared/busy.js"')
    frame = html.find('src="/assets/frame.js"')
    assert busy >= 0 and frame > busy, "frame.js must load, after busy.js"


def test_the_intake_form_reads_the_mentor_from_its_address():
    js = (ROOT / "forms/client_intake/frontend/app.js").read_text(encoding="utf-8")
    assert re.search(r'\.get\("mentor"\)', js)
