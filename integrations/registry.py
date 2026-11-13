"""The integrations, fixed in code (prds/integrations-tab-plan.md § 3).

One entry per outside service this application calls with its own
credentials, in display order. Each entry says:

* its "in use" setting (ruling I5) — none for EspoCRM, which is always in use
  and whose warnings are never hidden (mapping decision, Doug 11-13-26);
* its sections (only Google Workspace has more than one, ruling I3);
* its **switches**: the settings on its own sub-tab that switch one of its
  features on. A switch is usually a bool; Lob's and Twilio's are the vendor
  choice (``postal_provider = lob``, ``sms_provider = twilio``), because
  neither has a bool of its own;
* its **used-by** entries: settings that stay on the Settings tab but depend
  on it. Those with ``blocks=True`` are features that cannot work at all
  without the integration, and they count for both "in use" refusals exactly
  as a switch does (mapping decision 4, Doug 11-13-26). The rest are listed
  for information only;
* the settings that count as its credentials, for the status line;
* the readiness features it serves (``setup/readiness.FEATURES`` keys);
* its runbooks in this repository.

Which settings appear on a sub-tab is NOT held here: each ``SettingSpec``
carries its own ``integration`` and ``section`` (core/settings_registry.py).

Phase 2 adds the integration test: ``test_module`` names the module whose
``run(settings)`` is the test (integrations/testing.py), empty until the
integration's phase. Later phases add the allowed documentation sites and the
coded actions to :class:`Integration`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Section:
    key: str
    title: str


@dataclass(frozen=True)
class Switch:
    """A setting whose value switches a feature of an integration on.

    ``on_value`` empty means "on when truthy" (a bool, or a non-empty text such
    as the shared mailbox address); otherwise the feature is on when the value
    equals ``on_value``, ignoring case.
    """

    key: str
    on_value: str = ""

    def is_on(self, value: Any) -> bool:
        if self.on_value:
            return str(value if value is not None else "").strip().lower() == self.on_value
        if isinstance(value, bool):
            return value
        text = str(value if value is not None else "").strip().lower()
        if text in ("", "0", "false", "no", "off", "none"):
            return False
        return True


@dataclass(frozen=True)
class UsedBy:
    key: str
    # True: the feature cannot work at all without this integration, so it
    # counts for both "in use" refusals. False: listed for information only.
    blocks: bool = False
    on_value: str = ""

    @property
    def switch(self) -> Switch:
        return Switch(self.key, self.on_value)


@dataclass(frozen=True)
class Integration:
    key: str
    name: str
    in_use_setting: str
    sections: tuple[Section, ...] = ()
    switches: tuple[Switch, ...] = ()
    used_by: tuple[UsedBy, ...] = ()
    credentials: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    runbooks: tuple[str, ...] = ()
    # The phase that builds this integration's test (phase 2 or 3).
    test_phase: int = 2
    # The module holding the integration test, imported only when it runs;
    # empty until ``test_phase`` is built.
    test_module: str = ""

    @property
    def testable(self) -> bool:
        return bool(self.test_module)

    @property
    def always_in_use(self) -> bool:
        return not self.in_use_setting

    @property
    def blocking_switches(self) -> tuple[Switch, ...]:
        """Every setting that counts as switching this integration on: its own
        switches, then the used-by features that cannot work without it."""
        return self.switches + tuple(u.switch for u in self.used_by if u.blocks)


# Google Workspace's sections (ruling I3): the shared credentials first.
GOOGLE_SECTIONS: tuple[Section, ...] = (
    Section("credentials", "Credentials"),
    Section("drive", "Drive"),
    Section("calendar", "Calendar"),
    Section("meet", "Meet"),
    Section("gmail", "Gmail and the shared mailbox"),
    Section("accounts", "Workspace accounts"),
)


INTEGRATIONS: tuple[Integration, ...] = (
    Integration(
        key="espocrm", name="EspoCRM", in_use_setting="",
        used_by=(UsedBy("mentor_provision_users"),),
        credentials=("espo_base_url", "espo_api_key"),
        features=(),
        test_phase=2,
        test_module="integrations.checks.espocrm",
    ),
    Integration(
        key="google_workspace", name="Google Workspace",
        in_use_setting="google_workspace_in_use",
        sections=GOOGLE_SECTIONS,
        switches=(
            Switch("gdrive_docs"),
            Switch("gcal_events"),
            Switch("meet_transcripts"),
            Switch("gmail_sync"),
            Switch("gmail_resync"),
            # The shared mailbox is the switch of inbound info@ capture: set,
            # the worker polls it (readiness feature "inbound").
            Switch("ops_mailbox"),
            Switch("google_directory_check"),
            Switch("google_create_mailbox"),
        ),
        used_by=(
            UsedBy("events_confirmations", blocks=True),
            UsedBy("events_reminders", blocks=True),
            UsedBy("lead_outreach", blocks=True),
            UsedBy("mentor_provision_users", blocks=True),
            UsedBy("comms_digest"),
            UsedBy("alert_email_from"),
        ),
        credentials=("google_service_account_json", "google_delegated_admin"),
        features=("gmail", "digest", "inbound", "gcal", "meet", "gdrive"),
        runbooks=("GDRIVE-DOCS-SETUP.md", "GCAL-GOOGLE-SETUP.md",
                  "GMAIL-INTEGRATION-GUIDE.md"),
        test_phase=2,
        test_module="integrations.checks.google",
    ),
    Integration(
        key="zoom", name="Zoom", in_use_setting="zoom_in_use",
        switches=(Switch("zoom_events"),),
        credentials=("zoom_account_id", "zoom_client_id", "zoom_client_secret",
                     "zoom_host_email"),
        features=("zoom",),
        runbooks=("EVENTS-SETUP.md",),
        test_phase=2,
        test_module="integrations.checks.zoom",
    ),
    Integration(
        key="fathom", name="Fathom", in_use_setting="fathom_in_use",
        switches=(Switch("fathom_transcripts"),),
        used_by=(UsedBy("meet_transcripts_poll_seconds"),
                 UsedBy("transcript_give_up_days")),
        credentials=("fathom_api_key",),
        features=("fathom",),
        test_phase=3,
    ),
    Integration(
        key="constant_contact", name="Constant Contact",
        in_use_setting="constant_contact_in_use",
        switches=(Switch("mailing_sync"),),
        used_by=(
            UsedBy("campaigns_email", blocks=True),
            UsedBy("campaign_send_report", blocks=True),
            UsedBy("campaign_list_sync"),
            UsedBy("campaign_send_report_seconds"),
        ),
        credentials=("mailing_client_id", "mailing_client_secret"),
        features=("mailing",),
        runbooks=("MAILING-SETUP.md",),
        test_phase=3,
    ),
    Integration(
        key="lob", name="Lob", in_use_setting="lob_in_use",
        switches=(Switch("postal_provider", on_value="lob"),),
        used_by=(UsedBy("campaigns_enabled"),),
        credentials=("postal_api_key",),
        test_phase=3,
    ),
    Integration(
        key="twilio", name="Twilio", in_use_setting="twilio_in_use",
        switches=(Switch("sms_provider", on_value="twilio"),),
        used_by=(UsedBy("campaigns_sms", blocks=True),),
        credentials=("sms_account_sid", "sms_auth_token", "sms_from_number"),
        test_phase=3,
    ),
    Integration(
        key="anthropic", name="Anthropic", in_use_setting="anthropic_in_use",
        switches=(Switch("comms_ai_summary"), Switch("enrichment_ai")),
        credentials=("anthropic_api_key",),
        features=("ai_research",),
        test_phase=3,
    ),
    Integration(
        key="youtube", name="YouTube", in_use_setting="youtube_in_use",
        credentials=("youtube_api_key",),
        features=("events_library",),
        test_phase=3,
    ),
)

BY_KEY: dict[str, Integration] = {i.key: i for i in INTEGRATIONS}

#: Every "in use" setting, mapped to its integration.
IN_USE_KEYS: dict[str, Integration] = {
    i.in_use_setting: i for i in INTEGRATIONS if i.in_use_setting
}


def integration_for(key: str) -> Optional[Integration]:
    return BY_KEY.get(key)


def integration_of_feature(feature_key: str) -> Optional[Integration]:
    """The integration a readiness feature belongs to, or None."""
    for integ in INTEGRATIONS:
        if feature_key in integ.features:
            return integ
    return None


def integrations_switched_by(key: str) -> list[tuple[Integration, Switch]]:
    """Each integration that ``key`` switches on, with the switch."""
    out = []
    for integ in INTEGRATIONS:
        for sw in integ.blocking_switches:
            if sw.key == key:
                out.append((integ, sw))
    return out


def in_use(integ: Integration, settings: Any) -> bool:
    if integ.always_in_use:
        return True
    return bool(getattr(settings, integ.in_use_setting, True))
