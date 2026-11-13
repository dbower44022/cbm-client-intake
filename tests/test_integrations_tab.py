"""The Integrations tab of System Settings, phase 1 (prds/integrations-tab-plan.md).

The registry is complete, every integration setting is tagged, the page is
exactly as before with the switch off, both "in use" refusals hold at the API,
and a not-in-use integration's warnings leave the readiness counts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, apply_overrides, get_settings
from core.settings_registry import (
    BY_KEY,
    GROUP_CONNECTION,
    GROUP_INTEGRATIONS,
    INTEGRATION_TAGS,
    SETTINGS,
)
from core.settings_store import Override
from forms import info_request
from integrations import guard
from integrations.registry import BY_KEY as INTEGRATIONS_BY_KEY
from integrations.registry import IN_USE_KEYS, INTEGRATIONS
from setup.readiness import FEATURES, readiness_payload
from setup.service import page_payload

_ADMIN = {"userName": "adm", "name": "Ada", "isAdmin": True, "userId": "u1",
          "token": "t", "teams": [], "roles": []}

_BASELINE = Path(__file__).parent / "fixtures" / "setup_payload_before_integrations.json"
_FIELDS = ("key", "label", "group", "kind", "choices", "unit", "help", "restart",
           "component", "editable", "secret", "scopable")


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeStore:
    """The override table in memory: enough for the save path."""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})

    async def load(self):
        return dict(self.rows)

    async def set(self, key, value, **kw):
        record = Override(key=key, value=value)
        self.rows[key] = record
        return record

    async def clear(self, key, **kw):
        return self.rows.pop(key, None) is not None

    async def revert(self, key, **kw):
        return self.rows.pop(key, None) is not None


# --- the registry ---------------------------------------------------------

def test_the_integrations_are_the_nine_in_display_order():
    assert [i.name for i in INTEGRATIONS] == [
        "EspoCRM", "Google Workspace", "Zoom", "Fathom", "Constant Contact", "Lob",
        "Twilio", "Anthropic", "YouTube",
    ]


def test_every_in_use_setting_exists_and_espocrm_has_none():
    """Mapping decision 1 (Doug, 11-13-26): EspoCRM is always in use."""
    assert INTEGRATIONS_BY_KEY["espocrm"].in_use_setting == ""
    for integ in INTEGRATIONS:
        if integ.key == "espocrm":
            continue
        key = integ.in_use_setting
        assert key == f"{integ.key}_in_use"
        assert key in Settings.model_fields and Settings.model_fields[key].default is True
        spec = BY_KEY[key]
        assert spec.kind == "bool" and spec.component == "both"
        assert spec.integration == integ.key and spec.section == ""


def test_every_tagged_setting_names_a_real_integration_and_section():
    for key, (integ_key, section) in INTEGRATION_TAGS.items():
        assert key in BY_KEY, f"{key} is tagged but not registered"
        integ = INTEGRATIONS_BY_KEY.get(integ_key)
        assert integ is not None, f"{key} names no integration: {integ_key}"
        sections = {s.key for s in integ.sections}
        if sections and key != integ.in_use_setting:
            assert section in sections, f"{key}: no section {section!r} on {integ.name}"
        else:
            assert section == "", f"{key}: {integ.name} has no sections"


def test_google_sections_are_in_the_ruled_order():
    assert [s.title for s in INTEGRATIONS_BY_KEY["google_workspace"].sections] == [
        "Credentials", "Drive", "Calendar", "Meet", "Gmail and the shared mailbox",
        "Workspace accounts",
    ]


def test_every_readiness_feature_named_by_an_integration_exists():
    known = {f.key for f in FEATURES}
    for integ in INTEGRATIONS:
        for feature in integ.features:
            assert feature in known, f"{integ.name} names readiness feature {feature!r}"


def test_every_switch_used_by_and_credential_is_a_real_setting():
    for integ in INTEGRATIONS:
        keys = ([s.key for s in integ.switches] + [u.key for u in integ.used_by]
                + list(integ.credentials))
        for key in keys:
            assert key in BY_KEY, f"{integ.name} names {key}, which is not a setting"
        # A switch is on the integration's own sub-tab; a used-by is not.
        for s in integ.switches:
            assert BY_KEY[s.key].integration == integ.key, s.key
        for u in integ.used_by:
            assert BY_KEY[u.key].integration != integ.key, u.key


def test_every_setting_that_was_in_the_integrations_group_is_tagged():
    untagged = [s.key for s in SETTINGS
                if s.group in (GROUP_INTEGRATIONS, GROUP_CONNECTION) and not s.integration]
    assert not untagged, f"left behind on the Settings tab: {untagged}"


def test_the_mapping_decisions_hold():
    """Doug's corrections, 11-13-26: a switch and the settings that only serve
    it stay together."""
    for key in ("comms_digest", "comms_digest_hour", "comms_digest_tz",
                "comms_digest_seconds", "campaign_send_report_seconds",
                "campaign_send_report", "campaigns_sms", "mentor_provision_users"):
        assert BY_KEY[key].integration == "", key
    for key in ("enrichment_ai", "enrichment_ai_model", "enrichment_ai_fallback",
                "enrichment_ai_max_searches", "enrichment_ai_record_cap",
                "enrichment_ai_max_records", "enrichment_ai_poll_seconds",
                "enrichment_monthly_budget"):
        assert BY_KEY[key].integration == "anthropic", key
    lob = INTEGRATIONS_BY_KEY["lob"]
    assert [(s.key, s.on_value) for s in lob.blocking_switches] == [("postal_provider", "lob")]
    blocking = {i.key: sorted(u.key for u in i.used_by if u.blocks) for i in INTEGRATIONS}
    assert blocking["twilio"] == ["campaigns_sms"]
    assert blocking["constant_contact"] == ["campaign_send_report", "campaigns_email"]
    assert blocking["google_workspace"] == [
        "events_confirmations", "events_reminders", "lead_outreach", "mentor_provision_users"]


# --- the switch off: the page exactly as before ----------------------------

def _structure(payload):
    return {
        "topKeys": sorted(payload),
        "groups": [
            {"name": g["name"],
             "settings": [{f: r.get(f) for f in _FIELDS} for r in g["settings"]
                          if r["key"] != "integrations_tab"]}
            for g in payload["groups"]
        ],
        "other": [r["key"] for r in payload["other"]],
    }


@pytest.mark.asyncio
async def test_switch_off_payload_is_unchanged(monkeypatch, tmp_path):
    """Compared with the payload captured before phase 1 (the fixture). The one
    difference allowed is the switch itself, in the Features group."""
    monkeypatch.chdir(tmp_path)   # no local .env
    monkeypatch.delenv("ORGANIZATION_NAME", raising=False)
    monkeypatch.delenv("ORGANIZATION_ABBREVIATION", raising=False)
    get_settings.cache_clear()
    payload = await page_payload(FakeStore())
    assert "integrations" not in payload and "integrationsTab" not in payload
    features = next(g for g in payload["groups"] if g["name"] == "Features")
    assert features["settings"][-1]["key"] == "integrations_tab"
    expected = json.loads(_BASELINE.read_text())
    assert _structure(payload) == expected


@pytest.mark.asyncio
async def test_switch_on_moves_every_tagged_setting_to_its_sub_tab():
    apply_overrides({"integrations_tab": "true"})
    payload = await page_payload(FakeStore())
    names = [g["name"] for g in payload["groups"]]
    assert GROUP_INTEGRATIONS not in names and GROUP_CONNECTION not in names
    on_settings_tab = {r["key"] for g in payload["groups"] for r in g["settings"]}
    assert not on_settings_tab & set(INTEGRATION_TAGS)
    assert [i["key"] for i in payload["integrations"]] == [i.key for i in INTEGRATIONS]
    placed = set()
    for entry in payload["integrations"]:
        rows = entry["settings"] + [r for s in entry["sections"] for r in s["settings"]]
        placed |= {r["key"] for r in rows}
        if entry["inUseKey"]:
            assert entry["settings"][0]["key"] == entry["inUseKey"], entry["key"]
        assert entry["status"]["tested"] is None
    assert placed == set(INTEGRATION_TAGS)
    google = next(i for i in payload["integrations"] if i["key"] == "google_workspace")
    assert google["sections"][0]["title"] == "Credentials"
    assert {r["key"] for r in google["sections"][0]["settings"]} == {
        "google_service_account_json", "google_delegated_admin"}
    twilio = next(i for i in payload["integrations"] if i["key"] == "twilio")
    assert [(u["key"], u["blocks"]) for u in twilio["usedBy"]] == [("campaigns_sms", True)]


@pytest.mark.asyncio
async def test_the_status_line_names_switches_and_missing_credentials():
    apply_overrides({"integrations_tab": "true", "zoom_events": "true",
                     "zoom_account_id": "a", "zoom_client_id": "b",
                     "zoom_client_secret": "", "zoom_host_email": ""})
    payload = await page_payload(FakeStore())
    zoom = next(i for i in payload["integrations"] if i["key"] == "zoom")
    assert zoom["status"]["on"] is True
    assert zoom["status"]["onSwitches"] == ["Zoom webinar provisioning"]
    assert zoom["status"]["credentialsMissing"] == ["Zoom client secret", "Zoom host"]


def test_the_guard_counts_a_scoped_switch_as_on():
    s = get_settings()
    zoom = INTEGRATIONS_BY_KEY["zoom"]
    scoped = {"zoom_events": Override(key="zoom_events", value="true", scope_teams=("A",))}
    assert guard.switches_on(zoom, s, scoped) == ["zoom_events"]
    assert guard.refusal("zoom_in_use", "false", s, scoped)


# --- the refusals, through the API -----------------------------------------

def _app(monkeypatch, env, store=None):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("setup.router.current_user", lambda r: _ADMIN)
    get_settings.cache_clear()
    app = create_app_for_test()
    app.state.settings_store = store or FakeStore()
    app.state.job_store = None
    return app


def create_app_for_test():
    from core.app import create_app

    return create_app([info_request.SPEC])


def test_marking_not_in_use_is_refused_while_a_switch_is_on(monkeypatch):
    client = TestClient(_app(monkeypatch, {"ZOOM_EVENTS": "true"}))
    resp = client.put("/setup/api/settings/zoom_in_use", json={"value": "false"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "Zoom cannot be marked not in use" in detail
    assert "Zoom webinar provisioning (zoom_events)" in detail


def test_the_refusal_names_every_switch_that_is_on(monkeypatch):
    """A used-by feature that cannot work without the integration counts too."""
    client = TestClient(_app(monkeypatch, {"GCAL_EVENTS": "true", "LEAD_OUTREACH": "true"}))
    resp = client.put("/setup/api/settings/google_workspace_in_use", json={"value": "false"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "(gcal_events)" in detail and "(lead_outreach)" in detail


def test_marking_not_in_use_is_allowed_with_every_switch_off(monkeypatch):
    client = TestClient(_app(monkeypatch, {"ZOOM_EVENTS": "false"}))
    resp = client.put("/setup/api/settings/zoom_in_use", json={"value": "false"})
    assert resp.status_code == 200, resp.text


def test_switching_on_is_refused_while_not_in_use(monkeypatch):
    client = TestClient(_app(monkeypatch, {"ZOOM_IN_USE": "false"}))
    resp = client.put("/setup/api/settings/zoom_events", json={"value": "true"})
    assert resp.status_code == 409
    assert "Mark Zoom in use first" in resp.json()["detail"]
    # Switching it OFF is always allowed.
    assert client.put("/setup/api/settings/zoom_events",
                      json={"value": "false"}).status_code == 200


@pytest.mark.parametrize("env,key,value", [
    ({"TWILIO_IN_USE": "false"}, "campaigns_sms", "true"),
    ({"LOB_IN_USE": "false"}, "postal_provider", "lob"),
    ({"TWILIO_IN_USE": "false"}, "sms_provider", "twilio"),
    ({"GOOGLE_WORKSPACE_IN_USE": "false"}, "mentor_provision_users", "true"),
    ({"CONSTANT_CONTACT_IN_USE": "false"}, "campaigns_email", "true"),
])
def test_every_kind_of_switch_is_refused_while_not_in_use(monkeypatch, env, key, value):
    client = TestClient(_app(monkeypatch, env))
    resp = client.put(f"/setup/api/settings/{key}", json={"value": value})
    assert resp.status_code == 409, resp.text
    assert "in use first" in resp.json()["detail"]


def test_a_dry_run_vendor_and_an_information_only_entry_are_not_switches(monkeypatch):
    client = TestClient(_app(monkeypatch, {"LOB_IN_USE": "false",
                                           "CONSTANT_CONTACT_IN_USE": "false"}))
    assert client.put("/setup/api/settings/postal_provider",
                      json={"value": "dryrun"}).status_code == 200
    # campaign_list_sync is listed under Constant Contact, but blocks nothing.
    assert client.put("/setup/api/settings/campaign_list_sync",
                      json={"value": "true"}).status_code == 200


def test_a_reset_that_would_switch_a_feature_on_is_refused(monkeypatch):
    """Resetting returns the setting to its deployment value — here, on."""
    store = FakeStore({"zoom_events": Override(key="zoom_events", value="false"),
                       "zoom_in_use": Override(key="zoom_in_use", value="false")})
    client = TestClient(_app(monkeypatch, {"ZOOM_EVENTS": "true"}, store))
    apply_overrides({"zoom_events": "false", "zoom_in_use": "false"})
    resp = client.request("DELETE", "/setup/api/settings/zoom_events", json={"reason": ""})
    assert resp.status_code == 409
    assert "Mark Zoom in use first" in resp.json()["detail"]


# --- readiness ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_not_in_use_integrations_warnings_leave_the_readiness_counts():
    """The recorded webinar library has no switch, so it is always "on" and,
    with no YouTube key, blocked — until YouTube is marked not in use."""
    apply_overrides({"integrations_tab": "true", "youtube_api_key": "",
                     "youtube_playlist_id": ""})
    before = await readiness_payload(get_settings())
    row = next(f for f in before["features"] if f["key"] == "events_library")
    assert row["status"] == "blocked" and row["integration"] == "youtube"
    blocked_before = before["counts"]["blocked"]

    apply_overrides({"integrations_tab": "true", "youtube_api_key": "",
                     "youtube_playlist_id": "", "youtube_in_use": "false"})
    after = await readiness_payload(get_settings())
    row = next(f for f in after["features"] if f["key"] == "events_library")
    assert row["status"] == "not used" and row["notInUse"] is True
    assert row["unmet"] == 0 and "left out of the counts" in row["excludedNote"]
    assert after["counts"]["blocked"] == blocked_before - 1
    assert after["counts"]["notUsed"] == 1


@pytest.mark.asyncio
async def test_readiness_is_unchanged_with_the_switch_off():
    apply_overrides({"youtube_in_use": "false"})
    payload = await readiness_payload(get_settings())
    assert "counts" not in payload and "integrationsTab" not in payload
    row = next(f for f in payload["features"] if f["key"] == "events_library")
    assert "integration" not in row and row["status"] != "not used"


def test_in_use_keys_are_exactly_the_integrations_settings():
    assert set(IN_USE_KEYS) == {i.in_use_setting for i in INTEGRATIONS if i.in_use_setting}
