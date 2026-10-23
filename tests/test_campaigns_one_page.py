"""Marketing Management as one page with six tabs (build plan § 7e.2; rulings
89, 112, 114) — step M1 of the redesign.

- Lists and Calls are panels of ``index.html``, drawn by their own scripts,
  which register with ``window.CBMMarketing``; their element ids are prefixed
  so the modal, notice and user corner exist once.
- ``lists.html`` and ``calls.html`` redirect to their tabs, so old bookmarks
  and the campaign page's copied address keep working.
- A caller from another team gets a ``callerOnly`` session and a *Campaign
  calls* portal tile when a running call campaign names a team they are in.
- No served campaigns file cites a ruling number.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from core.config import get_settings
from tests.test_campaigns import FakeCrm, FakeStore, MARKETING, OUTSIDER, build
from tests.test_campaigns_phase3 import MENTOR, _running_call_campaign

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "campaigns" / "frontend"
LANDING = ROOT / "campaigns" / "landing_frontend"


def run(coro):
    return asyncio.run(coro)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- the page --------------------------------------------------------------------------------

def test_the_top_bar_is_six_section_buttons_in_the_ruled_order():
    html = _text(FRONTEND / "index.html")
    nav = html[html.index('id="sectionNav"'):html.index("</nav>")]
    assert re.findall(r'data-section="([a-z]+)"', nav) == ["prospects", "lists", "campaigns", "review", "calls", "imports"]
    assert "<a " not in nav, "no tab opens a browser tab (ruling 89)"
    assert "lists.html" not in html and "calls.html" not in html


def test_every_section_has_a_panel_and_no_id_is_declared_twice():
    html = _text(FRONTEND / "index.html")
    for panel in ("prospectsPanel", "listsPanel", "campaignsPanel", "reviewPanel", "callsPanel", "importsPanel"):
        assert f'id="{panel}"' in html, panel
    ids = re.findall(r'\bid="([^"]+)"', html)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    assert dups == [], f"ids declared twice: {dups}"
    # The rehoused panels own their ids under a prefix; the shared chrome is unprefixed and single.
    lists_panel = html[html.index('id="listsPanel"'):html.index('id="callsPanel"')]
    calls_panel = html[html.index('id="callsPanel"'):html.index('id="campaignsPanel"')]
    assert all(i.startswith("ls_") for i in re.findall(r'\bid="([^"]+)"', lists_panel)[1:])
    assert all(i.startswith("cl_") for i in re.findall(r'\bid="([^"]+)"', calls_panel)[1:])
    for shared in ("modal", "notice", "offPanel", "offReason", "userCorner", "whoName"):
        assert ids.count(shared) == 1, shared


def test_the_two_scripts_load_after_the_page_script_and_speak_through_the_shared_object():
    html = _text(FRONTEND / "index.html")
    order = re.findall(r'<script src="([^"]+)"', html)
    assert order.index("/shared/busy.js") == 0
    assert order.index("app.js") < order.index("lists.js") < order.index("calls.js")
    assert 'href="lists.css"' in html
    app = _text(FRONTEND / "app.js")
    assert "window.CBMMarketing = {" in app
    for key in ("api: api", "notice: notice", "ask: ask", "register: function", "showSection: showSection", "session: function"):
        assert key in app, key
    for name in ("lists.js", "calls.js"):
        js = _text(FRONTEND / name)
        assert "var M = window.CBMMarketing;" in js and "if (!M) return;" in js
        assert "/calls/session" not in js and "location.assign(" not in js, f"{name} keeps no page of its own"
    assert 'M.register("lists", { onShow: onShow, onLeave: leaveUnsaved })' in _text(FRONTEND / "lists.js")
    assert 'M.register("calls", { onShow:' in _text(FRONTEND / "calls.js")


def test_the_scripts_address_only_their_own_prefixed_ids():
    lists = _text(FRONTEND / "lists.js")
    assert all(i.startswith("ls_") for i in re.findall(r'\$\("([^"]+)"\)', lists)), "lists.js reaches only ls_ ids"
    calls = _text(FRONTEND / "calls.js")
    assert all(i.startswith("cl_") for i in re.findall(r'\$\("([^"]+)"\)', calls)), "calls.js reaches only cl_ ids"
    app = _text(FRONTEND / "app.js")
    assert not re.search(r'\$\("(ls|cl)_', app), "app.js never reaches into the other tabs"


def test_an_unsaved_list_is_asked_about_before_the_tab_switches():
    app = _text(FRONTEND / "app.js")
    assert "sections[leaving].onLeave" in app and 'if (ok === false) { markNav(leaving); return false; }' in app
    lists = _text(FRONTEND / "lists.js")
    assert 'await ask("Unsaved changes"' in lists
    # Leaving discards: the list is re-read, so the tab never shows the abandoned edit later.
    assert "if (leave) { state.dirty = false; if (state.open) await openList(state.open, true); }" in lists


def test_the_lists_and_calls_links_point_at_the_tabs():
    app = _text(FRONTEND / "app.js")
    assert 'open.href = "/campaigns/#lists" + (a ? "?list=" + encodeURIComponent(a.listId) : "")' in app
    assert 'function callsPageUrl() { return location.origin + "/campaigns/#calls"; }' in app
    html = _text(FRONTEND / "index.html")
    assert 'id="audOpen" href="/campaigns/#lists" target="cbm-campaigns"' in html


@pytest.mark.parametrize("page, tab", [("lists.html", "lists"), ("calls.html", "calls")])
def test_the_old_pages_redirect_to_their_tabs(page, tab):
    html = _text(FRONTEND / page)
    assert f'content="0; url=/campaigns/#{tab}"' in html
    assert f'/campaigns/#{tab}' in html and 'name="cbm-org"' in html
    assert "<nav" not in html and "<script src=" not in html, "no second copy of the top bar or the scripts"


def test_the_old_lists_address_carries_its_open_list_into_the_tab():
    assert 'location.replace("/campaigns/#lists" + (want ? "?list=" + encodeURIComponent(want) : ""))' in _text(FRONTEND / "lists.html")


def test_the_page_boots_a_caller_on_the_calls_tab_alone():
    app = _text(FRONTEND / "app.js")
    assert "if (state.session.callerOnly) {" in app
    assert 'b.hidden = b.getAttribute("data-section") !== "calls"' in app
    assert 'await showSection("calls");' in app


# --- ruling 112: no screen cites a ruling number ---------------------------------------------

def test_no_served_campaigns_file_cites_a_ruling_number():
    offenders = []
    for folder in (FRONTEND, LANDING):
        for path in sorted(folder.iterdir()):
            if path.suffix not in (".html", ".js", ".css"):
                continue
            for n, line in enumerate(_text(path).splitlines(), 1):
                if re.search(r"\bruling \d|\bCM-\d", line):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
    assert offenders == [], "\n".join(offenders)


# --- the server: a caller's session, the team gate, the portal tile ----------------------------

def test_a_caller_outside_the_team_gets_caller_only_and_the_lists_stay_shut(monkeypatch):
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    monkeypatch.setenv("CAMPAIGNS_CALLS", "true")
    monkeypatch.setenv("CAMPAIGN_LISTS", "true")
    client = build(monkeypatch, user=MENTOR, crm=crm, store=FakeStore())
    body = client.get("/campaigns/api/session").json()
    assert body == {"name": "Mia Mentor", "userName": "mia", "userId": "u-3", "isAdmin": False,
                    "callerOnly": True, "callsOn": True}
    assert client.get("/campaigns/api/lists").status_code == 403
    assert client.get("/campaigns/api/campaigns").status_code == 403
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    assert len(client.get("/campaigns/api/calls").json()["rows"]) == 3


def test_caller_only_is_still_404_while_the_app_is_off_and_401_signed_out(monkeypatch):
    assert build(monkeypatch, user=OUTSIDER, enabled="false").get("/campaigns/api/session").status_code == 404
    assert build(monkeypatch, user=None).get("/campaigns/api/session").status_code == 401


def test_may_call_any_follows_the_campaigns_teams_and_fails_closed():
    from campaigns import calls
    from core.espo import EspoError
    from tests.test_campaigns_phase3 import _settings

    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    s = _settings()
    assert run(calls.may_call_any(crm, MENTOR, s)) is True
    assert run(calls.may_call_any(crm, OUTSIDER, s)) is False
    assert run(calls.may_call_any(crm, {**OUTSIDER, "isAdmin": True}, s)) is True

    class Broken:
        async def list(self, *a, **kw):
            raise EspoError("list COutreachCampaign failed: HTTP 503")

    assert run(calls.may_call_any(Broken(), MENTOR, s)) is False


def _tile_settings(monkeypatch, **env):
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "true")
    monkeypatch.setenv("CAMPAIGNS_CALLS", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    monkeypatch.setenv("ESPO_BASE_URL", "https://crm.example")
    monkeypatch.setenv("ESPO_API_KEY", "k")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return get_settings()


def test_the_portal_offers_campaign_calls_to_a_caller_from_another_team(monkeypatch):
    from campaigns import calls
    from portal.router import _campaign_calls_tile

    seen = {}

    async def fake_running(api_client):
        seen["client"] = api_client
        return [{"id": "c1", "name": "Chamber calls", "teamsNames": {"t-m": "Mentor Team"}}]

    monkeypatch.setattr(calls, "running_call_campaigns", fake_running)
    settings = _tile_settings(monkeypatch)
    tile = run(_campaign_calls_tile(MENTOR, settings))
    assert tile == {"title": "Campaign calls", "url": "/campaigns/#calls", "target": "cbm-campaigns"}
    assert seen["client"]._headers == {"X-Api-Key": "k"}, "read under the org-wide key, not the caller's"
    # Nobody's team is named: no tile. The team member has the full tile already: none either.
    assert run(_campaign_calls_tile(OUTSIDER, settings)) is None
    assert run(_campaign_calls_tile(MARKETING, settings)) is None


def test_the_campaign_calls_tile_stays_dark_without_calls_or_a_key(monkeypatch):
    from campaigns import calls
    from portal.router import _campaign_calls_tile

    async def fake_running(api_client):  # pragma: no cover — must never be reached
        raise AssertionError("the CRM was read")

    monkeypatch.setattr(calls, "running_call_campaigns", fake_running)
    assert run(_campaign_calls_tile(MENTOR, _tile_settings(monkeypatch, CAMPAIGNS_CALLS="false"))) is None
    assert run(_campaign_calls_tile(MENTOR, _tile_settings(monkeypatch, ESPO_API_KEY=""))) is None
    assert run(_campaign_calls_tile(MENTOR, _tile_settings(monkeypatch, CAMPAIGNS_ENABLED="false"))) is None


def test_the_campaign_calls_tile_never_fails_the_sign_in(monkeypatch):
    from campaigns import calls
    from portal.router import _campaign_calls_tile

    async def boom(api_client):
        raise RuntimeError("socket closed")

    monkeypatch.setattr(calls, "running_call_campaigns", boom)
    assert run(_campaign_calls_tile(MENTOR, _tile_settings(monkeypatch))) is None
