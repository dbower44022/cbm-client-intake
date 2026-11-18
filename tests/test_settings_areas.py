"""The Settings tab in sub-tabs (prds/settings-page-areas-plan.md).

Guards the plan's rules: every setting is placed exactly once, each heading
shows its main switch first and the rest A to Z, the switch off leaves the page
as it was, and rulings Q1, Q3, Q4 and Q8 hold.
"""

from __future__ import annotations

import pytest

from core.config import apply_overrides, get_settings
from core.settings_areas import (
    AREA_CONNECTED,
    AREA_EVENTS,
    AREA_PLATFORM,
    AREA_STAFF,
    AREAS,
    PLACEMENT,
)
from core.settings_registry import SETTINGS
from setup.service import page_payload


class FakeStore:
    async def load(self):
        return {}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    apply_overrides({})
    yield
    apply_overrides({})
    get_settings.cache_clear()


def test_every_setting_is_placed_exactly_once():
    """A new setting with no place fails here: add it to core/settings_areas.py."""
    keys = [k for a in AREAS for h in a.headings for k in h.keys]
    assert len(keys) == len(set(keys)), "a setting is placed twice"
    registry = {s.key for s in SETTINGS}
    assert registry - set(keys) == set(), "settings with no area"
    assert set(keys) - registry == set(), "placed keys that are not settings"
    assert all(s.area and s.heading for s in SETTINGS)


def test_a_main_switch_is_an_on_off_setting_under_its_own_heading():
    kinds = {s.key: s.kind for s in SETTINGS}
    for area in AREAS:
        for h in area.headings:
            if h.lead:
                assert h.lead in h.keys, (area.name, h.title)
                assert kinds[h.lead] == "bool", h.lead


def test_restart_required_settings_live_in_their_own_areas():
    """Ruling Q1."""
    assert PLACEMENT["events_enabled"][0] == AREA_EVENTS
    assert PLACEMENT["analytics_enabled"][0] == AREA_STAFF
    assert PLACEMENT["log_level"][0] == AREA_PLATFORM


def test_integrity_and_alert_settings_are_with_their_features():
    """Rulings Q3 and Q4."""
    for key in ("login_integrity_check", "integrity_digest_to", "login_integrity_hour"):
        assert PLACEMENT[key] == (AREA_STAFF, "Login integrity check")
    for key in ("alert_email_to", "alert_email_from", "alert_webhook_url", "alert_check_seconds"):
        assert PLACEMENT[key] == (AREA_PLATFORM, "Alerts and checks")


@pytest.mark.asyncio
async def test_switch_off_sends_no_areas():
    payload = await page_payload(FakeStore())
    assert "areas" not in payload
    assert payload["groups"]


@pytest.mark.asyncio
async def test_each_heading_is_main_switch_first_then_a_to_z():
    apply_overrides({"settings_areas": "true"})
    payload = await page_payload(FakeStore())
    assert [a["name"] for a in payload["areas"]] == [a.name for a in AREAS]
    for area in payload["areas"]:
        for h in area["headings"]:
            rows = h["settings"]
            rest = rows
            if h["lead"]:
                assert rows[0]["key"] == h["lead"]
                rest = rows[1:]
            labels = [r["label"].casefold() for r in rest]
            assert labels == sorted(labels), (area["name"], h["name"])
            assert all(r["area"] == area["name"] and r["heading"] == h["name"] for r in rows)


@pytest.mark.asyncio
async def test_every_shown_setting_is_in_one_area():
    apply_overrides({"settings_areas": "true"})
    payload = await page_payload(FakeStore())
    in_areas = [r["key"] for a in payload["areas"] for h in a["headings"] for r in h["settings"]]
    in_groups = [r["key"] for g in payload["groups"] for r in g["settings"]]
    assert len(in_areas) == len(set(in_areas))
    assert sorted(in_areas) == sorted(in_groups)


@pytest.mark.asyncio
async def test_integrations_tab_on_keeps_feature_settings_in_their_areas():
    """Ruling Q8: only Connected services leaves; a feature setting tagged with
    a service stays in its area and is on the Integrations tab as well."""
    apply_overrides({"settings_areas": "true", "integrations_tab": "true"})
    payload = await page_payload(FakeStore())
    names = [a["name"] for a in payload["areas"]]
    assert AREA_CONNECTED not in names
    in_areas = {r["key"] for a in payload["areas"] for h in a["headings"] for r in h["settings"]}
    for key in ("enrichment_ai", "zoom_meetings_events", "gmail_sync", "google_create_mailbox"):
        assert key in in_areas, key
    on_tab = {r["key"] for i in payload["integrations"]
              for r in i["settings"] + [x for s in i["sections"] for x in s["settings"]]}
    assert "enrichment_ai" in on_tab
    expected = {k for k, (area, _) in PLACEMENT.items() if area != AREA_CONNECTED}
    assert in_areas == expected
