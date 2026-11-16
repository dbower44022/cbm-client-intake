"""The Zoom split, phase 9 of the Integrations tab (rulings EH1, EH5 to EH8 and
EH11 of prds/events/event-hosting-plan.md; Doug's approval 11-15-26, option A
for the webinar credentials).

The rule choosing Zoom Webinars' credentials; the Zoom Meetings test; its
wizard screens; ``when:`` read back from a saved answer; the choice labels;
readiness, the status line and the nightly run covering Zoom Meetings.
"""

from __future__ import annotations

import asyncio

import pytest

from core.config import Settings, apply_overrides, get_settings
from core.settings_registry import BY_KEY as SETTINGS_BY_KEY
from core.settings_registry import SECRET_KEYS, spec_for
from core.zoom import meetings_account, webinars_account
from integrations import nightly, wizard
from integrations.checks import zoom_meetings
from integrations.registry import BY_KEY as INTEGRATIONS
from integrations.testing import FAILED, OK, UNKNOWN

SECRET = "zm-very-secret-777"
MEETINGS = dict(zoom_meetings_account_id="macc", zoom_meetings_client_id="mcid",
                zoom_meetings_client_secret=SECRET, zoom_event_host_email="events@x.org")


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    apply_overrides({})
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


# --- the rule for Zoom Webinars' credentials (EH7, option A) ---------------------------

def test_webinars_use_their_own_until_meetings_has_credentials():
    """Cleveland's production today: Webinars credentials only, same account
    left at its default of Yes. Nothing moves."""
    s = Settings(zoom_account_id="wacc", zoom_client_id="wcid", zoom_client_secret="ws",
                 zoom_host_email="zweb@x.org")
    a = webinars_account(s)
    assert (a.account_id, a.host, a.shared) == ("wacc", "zweb@x.org", False)


def test_webinars_use_meetings_on_the_same_account():
    s = Settings(zoom_account_id="wacc", zoom_client_id="wcid", zoom_client_secret="ws",
                 zoom_host_email="zweb@x.org", **MEETINGS)
    a = webinars_account(s)
    assert (a.account_id, a.client_secret, a.host, a.shared) == ("macc", SECRET, "events@x.org", True)
    separate = webinars_account(Settings(zoom_webinars_same_account=False, zoom_account_id="wacc",
                                         zoom_client_id="wcid", zoom_client_secret="ws", **MEETINGS))
    assert (separate.account_id, separate.shared) == ("wacc", False)


def test_zoom_active_reads_the_rule():
    assert Settings(zoom_events=True, **MEETINGS).zoom_active is True
    assert Settings(zoom_events=True, zoom_host_email="").zoom_active is False
    assert Settings(zoom_meetings_events=True, **MEETINGS).zoom_meetings_active is True
    assert Settings(**MEETINGS).zoom_meetings_active is False
    assert meetings_account(Settings(**MEETINGS)).complete


# --- the settings --------------------------------------------------------------------

def test_the_settings_events_reads_exist():
    for key in ("zoom_meetings_in_use", "zoom_meetings_events", "zoom_meetings_account_id",
                "zoom_meetings_client_id", "zoom_meetings_client_secret", "zoom_event_host_email",
                "zoom_webinars_same_account", "zoom_meetings_capacity",
                "events_default_method_public", "events_default_method_members"):
        assert key in SETTINGS_BY_KEY, key
    assert "zoom_meetings_client_secret" in SECRET_KEYS
    s = Settings()
    assert s.zoom_meetings_capacity == 100 and s.zoom_webinars_same_account is True
    assert s.events_default_method_public == "CBM Zoom" == s.events_default_method_members
    spec = spec_for("events_default_method_public")
    assert spec.choices == ("CBM Zoom", "Zoom Meetings", "Other platform", "Outside host")
    assert dict(spec.choice_labels) == {"CBM Zoom": "Zoom Webinars"}
    # The Webinars keys are kept, relabelled (no chapter's override is stranded).
    assert spec_for("zoom_in_use").label == "Zoom Webinars in use"
    assert spec_for("zoom_host_email").integration == "zoom"
    assert spec_for("zoom_event_host_email").integration == "zoom_meetings"


def test_a_default_naming_zoom_meetings_counts_as_used_but_never_blocks():
    from integrations.guard import refusal

    s = Settings(zoom_meetings_in_use=False)
    assert refusal("events_default_method_members", "Zoom Meetings", s) is None
    assert refusal("zoom_meetings_events", "true", s) is not None


# --- the Zoom Meetings test ------------------------------------------------------------

class FakeZoom:
    def __init__(self, scopes=" ".join(zoom_meetings.REQUIRED_SCOPES), user_type=2, co_host=True,
                 past=True, list_error=None):
        self.scopes = ""
        self._scopes, self.user_type, self.co_host, self.past = scopes, user_type, co_host, past
        self.list_error = list_error

    async def _access_token(self):
        self.scopes = self._scopes
        return "t"

    async def get_user(self, user):
        return {"email": user, "type": self.user_type, "account_number": 42}

    async def get_user_settings(self, user):
        in_meeting = {} if self.co_host is None else {"co_host": self.co_host}
        return {"feature": {"meeting_capacity": 100}, "in_meeting": in_meeting}

    async def list_meetings(self, user, kind="upcoming", page_size=1):
        if self.list_error:
            raise self.list_error
        if kind == "upcoming":
            return {"total_records": 2, "meetings": [{}, {}]}
        return {"meetings": [{"uuid": "u1", "topic": "Last month"}] if self.past else []}

    async def list_meeting_participants(self, meeting_id):
        return [{"user_email": "a@x.org"}]


def test_meetings(fake, **settings):
    deps = zoom_meetings.Deps(client=lambda s: fake)
    result = run(zoom_meetings.run(Settings(**{**MEETINGS, **settings}), deps))
    return {c["key"]: c for c in result["checks"]}, {f["label"]: f["value"] for f in result["facts"]}, result


test_meetings.__test__ = False  # a helper, not a test


def test_zoom_meetings_passes_on_a_good_account():
    checks, facts, result = test_meetings(FakeZoom())
    assert [c for c in checks] == ["settings", "token", "scopes", "host", "co_host", "meetings", "attendance"]
    assert result["outcome"] == OK, checks
    assert facts["Meeting capacity"] == "Zoom 100 · limit setting 100"
    assert facts["Upcoming meetings"] == "2"


def test_zoom_meetings_names_the_missing_scopes():
    checks, _, result = test_meetings(FakeZoom(scopes="user:read:user:admin meeting:read:meeting:admin"))
    assert checks["scopes"]["outcome"] == FAILED and result["outcome"] == FAILED
    assert "meeting:write:registrant:admin" in checks["scopes"]["detail"]
    assert "user:read:user:admin," not in checks["scopes"]["detail"]
    assert test_meetings(FakeZoom(scopes=""))[0]["scopes"]["outcome"] == UNKNOWN


def test_zoom_meetings_needs_a_licensed_host_and_co_host():
    assert test_meetings(FakeZoom(user_type=1))[0]["host"]["outcome"] == FAILED
    off = test_meetings(FakeZoom(co_host=False))[0]["co_host"]
    assert off["outcome"] == FAILED and "Co-host is off" in off["detail"]
    assert test_meetings(FakeZoom(co_host=None))[0]["co_host"]["outcome"] == UNKNOWN


def test_zoom_meetings_shows_zooms_words_for_a_missing_scope():
    from core.zoom import ZoomError

    refused = ZoomError('HTTP 400 {"code":4711,"message":"Invalid access token, does not contain '
                        'scopes:[meeting:read:list_meetings:admin]."}', status_code=400)
    checks, _, _ = test_meetings(FakeZoom(list_error=refused))
    assert checks["meetings"]["outcome"] == FAILED
    assert "does not contain scopes:[meeting:read:list_meetings:admin]" in checks["meetings"]["detail"]


def test_zoom_meetings_with_no_past_meeting_still_passes():
    checks, _, result = test_meetings(FakeZoom(past=False))
    assert checks["attendance"]["outcome"] == "skipped" and result["outcome"] == OK


def test_zoom_meetings_settings_missing_blocks_the_rest():
    checks, _, result = test_meetings(FakeZoom(), zoom_event_host_email="")
    assert checks["settings"]["outcome"] == FAILED and "event host user" in checks["settings"]["detail"]
    assert result["outcome"] == FAILED


def test_no_secret_value_in_the_meetings_result():
    import json

    assert SECRET not in json.dumps(test_meetings(FakeZoom())[2])


# --- the wizard screens ------------------------------------------------------------------

def test_zoom_meetings_has_the_eighteen_approved_screens():
    screens = wizard.screens_for("zoom_meetings")
    assert [s.id for s in screens] == [
        "zoom-meetings-use", "zoom-meetings-have-account", "zoom-meetings-mailbox", "zoom-meetings-signup",
        "zoom-meetings-plan", "zoom-meetings-build-app", "zoom-meetings-information", "zoom-meetings-scopes",
        "zoom-meetings-activate", "zoom-meetings-account-id", "zoom-meetings-client-id",
        "zoom-meetings-client-secret", "zoom-meetings-scopes-check", "zoom-meetings-host",
        "zoom-meetings-co-host", "zoom-meetings-capacity", "zoom-meetings-default", "zoom-meetings-switch-on"]
    assert wizard.problems(screens, set(SETTINGS_BY_KEY), set(INTEGRATIONS)) == []
    scopes = next(s for s in screens if s.id == "zoom-meetings-scopes")
    assert tuple(scopes.copy) == zoom_meetings.REQUIRED_SCOPES
    assert "Add Scopes" in scopes.how


def test_every_screen_names_a_real_check():
    bad = [wizard.Screen("a", "1.1", "A", check="test:zoom_meetings/nope"),
           wizard.Screen("b", "1.1", "B", when="a=Maybe")]
    assert len(wizard.problems(bad, set(SETTINGS_BY_KEY), set(INTEGRATIONS))) == 2


def test_the_meetings_wizard_starts_at_the_first_failing_screen(monkeypatch):
    monkeypatch.delenv("ZOOM_MEETINGS_IN_USE", raising=False)
    screens = wizard.screens_for("zoom_meetings")
    st = wizard.State(settings=Settings(), overrides={})
    assert wizard.start(screens, st) == "zoom-meetings-use"
    st = wizard.State(settings=Settings(), overrides={"zoom_meetings_in_use": object()})
    assert wizard.start(screens, st) == "zoom-meetings-account-id"
    run_ = {"outcome": "ok", "checks": [{"key": k, "outcome": "ok", "detail": ""}
                                        for k in ("token", "scopes", "host", "co_host")]}
    st = wizard.State(settings=Settings(**MEETINGS), overrides={"zoom_meetings_in_use": object()},
                      test_runs={"zoom_meetings": run_})
    assert wizard.start(screens, st) is None


def test_when_reads_a_saved_answer_back_from_its_setting():
    screens = wizard.screens_for("zoom")
    assert wizard.when_answers(screens, {}, Settings(zoom_webinars_same_account=False))[
        "zoom-same-account"] == "No"
    assert wizard.when_answers(screens, {}, Settings())["zoom-same-account"] == "Yes"
    # This run's answer wins over the setting.
    assert wizard.when_answers(screens, {"zoom-same-account": "No"}, Settings())[
        "zoom-same-account"] == "No"


# --- readiness, the status line, the nightly run ------------------------------------------

def test_readiness_has_a_zoom_meetings_row_and_webinars_reads_the_rule():
    from setup.readiness import FEATURES, _requirement_rows

    by = {f.key: f for f in FEATURES}
    assert by["zoom_meetings"].flag == "zoom_meetings_events"
    rows = _requirement_rows(by["zoom"], Settings(**MEETINGS))
    assert all(r["ok"] for r in rows), rows


def test_the_nightly_run_covers_zoom_meetings_once_switched_on():
    assert INTEGRATIONS["zoom_meetings"] not in nightly.due(Settings())
    assert INTEGRATIONS["zoom_meetings"] in nightly.due(Settings(zoom_meetings_events=True))


@pytest.mark.asyncio
async def test_the_status_line_on_the_same_account():
    from setup.service import page_payload
    from tests.test_integrations_tab import FakeStore

    apply_overrides({"integrations_tab": "true", **MEETINGS})
    payload = await page_payload(FakeStore())
    by = {i["key"]: i for i in payload["integrations"]}
    assert by["zoom"]["status"]["credentialsMissing"] == []
    assert by["zoom_meetings"]["status"]["credentialsMissing"] == []
    default = next(r for g in payload["groups"] for r in g["settings"]
                   if r["key"] == "events_default_method_public")
    assert default["choiceLabels"] == {"CBM Zoom": "Zoom Webinars"}




def test_the_token_is_tried_before_the_host_is_entered():
    """Phase 11 live review, 11-16-26: the setup asks for the client secret
    (its check: the token) before the event host user, so the token must not
    wait for the host. The host checks wait instead."""
    checks, _, result = test_meetings(FakeZoom(), zoom_event_host_email="")
    assert checks["settings"]["outcome"] == FAILED and "event host user" in checks["settings"]["detail"]
    assert checks["token"]["outcome"] == OK and checks["scopes"]["outcome"] == OK
    assert checks["host"]["outcome"] == "skipped" or "not set" in checks["host"]["detail"]
    assert result["outcome"] == "failed"
