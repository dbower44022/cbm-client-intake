"""The new home page, phase 1: the frame (HOME_V2; prds/home-page-plan.md § 8).

Off, today's page and payload are what they were. On, the session payload
carries the member's sections, the page loads the frame's files, the
preference `home.sections` is accepted within the size limit, and every
text-on-background pair in /shared/panel.css reaches 4.5 to 1."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request, volunteer

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _login(monkeypatch, client, **user):
    base = {"userId": "u1", "userName": "jdoe", "name": "Jane Doe", "token": "tok",
            "isAdmin": False, "teams": [], "roles": []}
    base.update(user)

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return base

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)
    return client.post("/api/portal/login", json={"username": "jdoe", "password": "x"}).json()


# --- the switch -------------------------------------------------------------------

def test_off_the_payload_is_todays(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        data = _login(monkeypatch, c)
        assert data["homeV2"] is False
        assert "home" not in data
        session = c.get("/api/portal/session").json()
    assert session["homeV2"] is False and "home" not in session
    # Everything today's page draws is still in the payload.
    for key in ("apps", "directories", "forms", "docsUrl", "crmUrl",
                "analyticsEnabled", "eventsCalendar", "birthdays"):
        assert key in session, key


def test_off_the_page_keeps_todays_view(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        html = c.get("/").text
    for needle in ('id="homeView"', 'id="appsList"', 'id="directoriesList"',
                   'id="eventsRail"', 'id="analyticsSection"', 'id="formsList"',
                   'id="crmList"', 'id="docsList"', 'id="logoutBtn"'):
        assert needle in html, needle
    # busy.js still loads first; the frame's script loads before app.js calls it.
    assert html.index("/shared/busy.js") < html.index("/portal/home.js") < html.index("/portal/app.js")


def test_off_nothing_new_applies_until_the_script_says_so():
    """home.css styles only under body.home2-on (and the .home2 view that
    home.js creates), so loading it changes nothing on today's page."""
    css = (ROOT / "portal" / "frontend" / "home.css").read_text()
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel in re.findall(r"([^{}]+)\{", body):
        for part in sel.split(","):
            part = part.strip()
            if not part or part.startswith("@media"):
                continue
            assert part.startswith(("body.home2-on", ".home2", ".cbm-panel--collapsed .home2")), part


def test_on_the_payload_carries_the_sections(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        data = _login(monkeypatch, c, name="Kim Sarver")
    assert data["homeV2"] is True
    assert data["home"] == {"firstName": "Kim", "sections": ["chapter", "pages"]}


@pytest.mark.parametrize("teams, sections", [
    (["Mentor Team"], ["today", "needs", "clients", "chapter", "pages"]),
    (["Client Administration Team"], ["needs", "chapter", "pages"]),
    (["Marketing Admin Team"], ["needs", "chapter", "pages"]),
    ([], ["chapter", "pages"]),
])
def test_the_sections_follow_the_members_teams(monkeypatch, teams, sections):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        data = _login(monkeypatch, c, teams=teams)
    assert data["home"]["sections"] == sections


def test_an_administrator_gets_every_section(monkeypatch):
    with TestClient(_app(monkeypatch, HOME_V2="true")) as c:
        data = _login(monkeypatch, c, isAdmin=True)
    assert data["home"]["sections"] == ["today", "needs", "clients", "chapter", "pages"]


def test_the_switch_is_on_the_system_settings_page():
    from core.settings_registry import GROUP_FEATURES, SETTINGS

    spec = next(s for s in SETTINGS if s.key == "home_v2")
    assert spec.group == GROUP_FEATURES
    assert spec.kind == "bool"


# --- the preference ---------------------------------------------------------------

class PrefStore:
    def __init__(self):
        self.rows = {}

    async def get_user_preference(self, user_id, key):
        return self.rows.get((user_id, key))

    async def set_user_preference(self, user_id, key, value):
        self.rows[(user_id, key)] = value


def test_the_sections_preference_is_kept_per_member(monkeypatch):
    url = "/api/portal/preferences/home.sections"
    app = _app(monkeypatch, HOME_V2="true")
    with TestClient(app) as c:
        app.state.submission_store = PrefStore()
        _login(monkeypatch, c)
        assert c.get(url).json() == {"key": "home.sections", "value": None, "stored": True}
        value = {"collapsed": ["today"], "hidden": ["pages"]}
        assert c.put(url, json={"value": value}).status_code == 200
        assert c.get(url).json()["value"] == value
        # The size limit holds for this key as for every other.
        assert c.put(url, json={"value": {"hidden": ["x" * 3000]}}).status_code == 400


# --- the contrast pairs -----------------------------------------------------------

def _tokens() -> dict[str, str]:
    css = (ROOT / "frontend" / "shared" / "tokens.css").read_text()
    root = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    return dict(re.findall(r"(--cbm-[\w-]+)\s*:\s*([^;]+);", root))


def _resolve(value: str, tokens: dict[str, str]) -> str | None:
    value = value.strip()
    for _ in range(5):
        m = re.fullmatch(r"var\((--cbm-[\w-]+)(?:,\s*[^)]*)?\)", value)
        if not m:
            break
        value = tokens[m.group(1)].split("/*")[0].strip()
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else None


def _luminance(hex_: str) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _panel_pairs():
    tokens = _tokens()
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "frontend" / "shared" / "panel.css").read_text(), flags=re.S)
    pairs = []
    for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        props = dict((k.strip(), v.strip()) for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+);", decls))
        bg = props.get("background") or props.get("background-color")
        fg = props.get("color")
        if not (bg and fg):
            continue
        if bg == "transparent":
            bg = "var(--cbm-panel)"   # a quiet button sits on its panel
        pairs.append((sel.strip(), _resolve(bg, tokens), _resolve(fg, tokens)))
    return pairs


def test_every_text_on_tint_pair_in_panel_css_reaches_4_5_to_1():
    pairs = _panel_pairs()
    assert len(pairs) >= 12          # the panel, rows, five tones, buttons
    for sel, bg, fg in pairs:
        assert bg and fg, f"{sel}: a colour the test cannot resolve"
        assert _ratio(bg, fg) >= 4.5, f"{sel}: {fg} on {bg} is {_ratio(bg, fg):.2f} to 1"


@pytest.mark.parametrize("fg, bg", [
    ("--cbm-text-muted", "--cbm-page"),     # a section label on the page
    ("--cbm-text-muted", "--cbm-panel"),
    ("--cbm-text", "--cbm-page"),
    ("--cbm-text", "--cbm-panel"),
    ("--cbm-text-strong", "--cbm-panel"),
    ("--cbm-navy", "--cbm-page"),           # the greeting
])
def test_the_new_tokens_read_on_the_page_and_the_panel(fg, bg):
    tokens = _tokens()
    f = _resolve(f"var({fg})", tokens)
    b = _resolve(f"var({bg})", tokens)
    assert _ratio(f, b) >= 4.5


# --- the fixed header bar (#89 part 8; Doug, 11-19-26) -----------------------------

def test_the_header_bar_never_scrolls_away():
    css = (ROOT / "portal/frontend/home.css").read_text()
    bar = re.search(r"\.home2__bar \{([^}]*)\}", css).group(1)
    assert "position: sticky" in bar and "top: 0" in bar and "z-index" in bar
    # An open narrow-screen menu scrolls inside the bar instead of running
    # past the bottom of the window; written with --cbm-vh, never a bare vh.
    opened = re.search(r"\.home2__bar--open \{([^}]*)\}", css).group(1)
    assert "max-height: calc(100 * var(--cbm-vh, 1vh))" in opened
    assert "overflow-y: auto" in opened
    js = (ROOT / "portal/frontend/home.js").read_text()
    # The bar sits directly in <body>, beside the view, so the footer below
    # the view cannot push it off; leave() takes it away again.
    assert 'bar.id = "home2Bar"' in js
    assert "insertBefore(bar, host)" in js
    assert 'getElementById("home2Bar")' in js
