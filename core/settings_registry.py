"""What the System Settings page may show and change (plan §4, rulings 2–3).

Three things live here and nowhere else:

* **:data:`DENYLIST`** — keys that can never be overridden from the browser,
  enforced server-side rather than merely hidden in the UI. Every secret, the
  CRM target, the database, and the switches guarding this feature itself. The
  page must not be able to lock you out of the page that fixes it.
* **:data:`SETTINGS`** — the curated, editable settings, grouped. Ruling 3:
  these are the flags and knobs that actually get tuned; every other field on
  ``Settings`` is still *shown* (read-only) but not editable.
* **Boot-read settings are denylisted, not badged.** ``create_app`` decides
  router mounting and builds the middleware from the ENVIRONMENT, and the
  override layer only loads afterwards in the startup hook — so an override for
  one of those keys never takes effect, not even after a redeploy, because the
  redeploy re-runs mounting first. v0.190.1 shipped them as editable-with-a-
  "takes effect on next deploy" badge, which was simply wrong: toggling
  ``events_enabled`` here made the portal show an Event Administration tile
  whose routes did not exist. They now live on the denylist and are changed in
  the deployment overlay, which is the only thing that can change them.

``component`` records which process actually reads the setting — the worker owns
delivery, monitoring, Gmail sync, Drive reconciliation, transcripts and receipt
sweeps; web owns everything user-facing. It drives the readiness panel, and it
exists because "the flag is on but nothing happens" is usually this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal, Optional

Kind = Literal["bool", "int", "text", "csv", "choice"]
Component = Literal["web", "worker", "both"]

# --- groups, in display order ----------------------------------------------
GROUP_FEATURES = "Features"
GROUP_INTEGRATIONS = "Integrations"
GROUP_EMAIL = "Email"
GROUP_RELIABILITY = "Reliability"
GROUP_GATES = "Team gates"
GROUP_PRESENTATION = "Presentation"
# The chapter website (prds/chapter-website-plan.md, decision 4.2): the values
# the website shows, each set once. The chapter-wide values moved here from
# Presentation under their existing keys, so nothing that reads them changed.
GROUP_WEBSITE = "Website"
# Read once while the process starts, so a change waits for a restart. Grouped
# together rather than scattered, because the thing they share — "saving this
# does not take effect yet" — is the thing a reader most needs told.
GROUP_RESTART = "Restart required"
# Editable, but a wrong value breaks something important — so each is TRIED
# before it is stored and the system is checked afterwards (setup/verify.py).
GROUP_CONNECTION = "CRM connection"
GROUP_SECURITY = "Access & security"
# Visible, never editable here. Two of them are not dangerous but impossible.
GROUP_FOUNDATIONS = "Foundations"

GROUP_ORDER = [
    GROUP_FEATURES,
    GROUP_INTEGRATIONS,
    GROUP_EMAIL,
    GROUP_RELIABILITY,
    GROUP_GATES,
    GROUP_PRESENTATION,
    GROUP_WEBSITE,
    GROUP_RESTART,
    GROUP_CONNECTION,
    GROUP_SECURITY,
    GROUP_FOUNDATIONS,
]

# Keys that may NEVER be overridden from the UI, whatever the request says.
# Enforced in core/settings_store.py, not just omitted from the page.
#
#   * secrets — never stored in app_setting, never rendered (plan §3);
#   * espo_base_url / espo_dry_run — which CRM this app writes to, and whether
#     it writes at all. A mistake here is unrecoverable from inside the app;
#   * database_url / session_secret / app_encryption_key — the app's own
#     foundations, read once at boot;
#   * setup_enabled / settings_overrides — the break-glass pair. If the page
#     could switch itself (or the whole override layer) off, recovery would
#     need a redeploy;
#
# BOOT_READ_KEYS are NO LONGER denylisted. Doug ruled on 2026-08-28 that every
# setting belongs on the page — hiding one where it cannot be viewed or edited
# is not acceptable — and `core/boot_overrides.load_at_boot` now installs the
# override layer BEFORE create_app mounts anything, so "takes effect on
# restart" is true rather than a promise. They are curated into the
# "Restart required" group, which shows the value in force beside the one
# waiting for a restart.
BOOT_READ_KEYS: frozenset[str] = frozenset({
    # Decide router mounting / static mounts / portal tiles in create_app.
    "analytics_enabled",
    "events_enabled",
    "events_public_api",
    "assignments_enabled",
    # Built into middleware at app construction.
    "intake_rate_limit",
    "intake_rate_window_seconds",
    "intake_max_body_mb",
    # Applied once by logging_setup at process start.
    "log_level",
    # The CRM configuration-stamp probe: its refresh task is created once in
    # the lifespan, so changing the interval later cannot start, stop or
    # re-time it. `release_tag` is baked into the image at build time and is
    # not a runtime value at all.
    "crm_config_refresh_seconds",
    "release_tag",
})

# --- what a change can cost, and what proves it safe ------------------------
#
# Doug's ruling, 2026-08-28: "All settings should be editable, unless a change
# would make the system unusable. Then there must be a verification that the
# system is still functional."
#
# So the denylist is now tiny and holds only the two changes that are not
# dangerous but IMPOSSIBLE (see below). Everything else that used to be hidden
# is editable through the verified path in `setup/verify.py`, which tries the
# value before storing it and checks the system afterwards.

# A change here could lock the admin out of this page. Neither a pre-flight
# probe nor a health check catches that: the app would be working perfectly and
# simply refusing to let anyone back in. These get a confirm-or-revert deadline
# instead — the change applies, and unless a human confirms the system still
# works it reverts itself. The network engineer's `commit confirmed`.
LOCKOUT_KEYS: frozenset[str] = frozenset({
    "setup_enabled",        # hides this page
    "settings_overrides",   # switches off the whole override layer
    "session_cookie_secure",  # `true` over plain http means nobody can sign in
    "allowed_origins",
    "session_secret",       # signs every session cookie: changing it signs you out
})

# A wrong value here breaks something important but cannot lock anyone out, so
# the pre-flight probe plus the post-apply check are the whole safety net.
VERIFIED_KEYS: frozenset[str] = frozenset({
    "espo_base_url",
    "espo_api_key",
    "espo_dry_run",
    "espo_provision_username",
    "espo_provision_password",
    "google_service_account_json",
    "anthropic_api_key",
    "zoom_account_id",
    "zoom_client_id",
    "zoom_client_secret",
    "fathom_api_key",
    "youtube_api_key",
    "setup_peer_url",
    "setup_peer_token",
    "sandbox_nightly_reset",
})

DENYLIST: frozenset[str] = frozenset({
    # Baked into the container image at build time. An override would survive a
    # restart and make the deployment MISREPORT which image it is running,
    # which defeats the only reason the stamp exists. Curated read-only instead
    # of hidden, per the 2026-08-28 ruling: visible, explained, not editable.
    "release_tag",
    # NOT caution — a logical impossibility. The override table lives INSIDE the
    # database this names, so an override moving the app to a different database
    # would live in the database being left behind: the new one has no such row,
    # the app reads its own configuration from there, and moves straight back.
    # There is no value of this setting that can change it.
    "database_url",
    # Rotating this makes every already-encrypted stored secret permanently
    # unreadable — the Google configuration and now the secrets on this page.
    # That is data loss rather than lockout, and no verification can undo it.
    # Rotation needs a re-encryption migration, not a text box.
    "app_encryption_key",
})

# Settings whose VALUE must never be sent to the browser, even read-only. The
# page shows "set / not set" for these instead.
SECRET_KEYS: frozenset[str] = frozenset({
    # A Postgres URL carries the password inside it, so rendering the value
    # hands any admin the database credential. It was in the read-only "show
    # all" list in the clear before 2026-08-28; curating it as a visible row
    # would have made that worse rather than better. Read-only AND masked.
    "database_url",
    "espo_api_key",
    "session_secret",
    "app_encryption_key",
    "espo_provision_password",
    "google_service_account_json",
    "anthropic_api_key",
    "zoom_client_secret",
    "fathom_api_key",
    "youtube_api_key",
    "setup_peer_token",
    "mailing_client_secret",
    "postal_api_key",
    "postal_webhook_secret",
    "sms_auth_token",
})


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: str
    label: str
    kind: Kind = "text"
    help: str = ""
    restart: bool = False
    # Shown on the page but never editable. For values the app cannot own — the
    # release tag comes from the image. Ruled 2026-08-28: visible beats hidden,
    # and "read-only, here is why" beats absent.
    readonly: bool = False
    component: Component = "web"
    choices: tuple[str, ...] = ()
    unit: str = ""
    # The integration whose sub-tab this setting appears on when the
    # Integrations tab is switched on (an integrations/registry.py key), or
    # empty. Set from INTEGRATION_TAGS below, never by hand in a spec.
    integration: str = ""
    # The section of that sub-tab — empty unless the integration has sections.
    section: str = ""


def _s(key: str, group: str, label: str, **kw) -> SettingSpec:
    return SettingSpec(key=key, group=group, label=label, **kw)


_IN_USE_HELP = (
    "Whether this chapter uses {name}. Off, its sub-tab says Not used by this "
    "chapter and its warnings are left out of Feature readiness. Refused while any "
    "{name} feature is switched on, and no {name} feature can be switched on while "
    "this is off."
)


SETTINGS: tuple[SettingSpec, ...] = (
    # --- Features ----------------------------------------------------------
    _s("zoom_events", GROUP_FEATURES, "Zoom webinar provisioning", kind="bool",
       component="both",
       help="Public webinars only — mentor 1:1 sessions never use the {{abbr}} Zoom account."),
    _s("mailing_sync", GROUP_FEATURES, "Mailing list sync", kind="bool",
       component="worker",
       help="Pushes the CRM's opted-in contacts to the mailing service's list each "
            "night and pulls unsubscribes back each hour. Needs the mailing service "
            "credentials AND a connected account (Readiness → Mailing list sync)."),
    _s("events_reminders", GROUP_FEATURES, "Event reminder emails", kind="bool",
       component="worker",
       help="The only time-driven follow-up. Needs the EventReminder template in "
            "the CRM; every send refuses by name until it exists."),
    _s("website_api", GROUP_FEATURES, "Chapter website connection", kind="bool",
       help="Serves the Website group's values, images and key pages to the "
            "chapter website at /api/website/…. Public and unauthenticated by "
            "design; off, those addresses answer 404. Read per request."),
    _s("form_framing", GROUP_FEATURES, "Forms in website frames", kind="bool",
       help="Only the Chapter website addresses (and this app) may show the public "
            "forms in a frame, the forms report their height to that website, and a "
            "form opened with ?embed=1 takes the Website colours and drops its own "
            "heading and footer. Before switching on, put EVERY website that frames "
            "a form today into Chapter website addresses, or its forms go blank."),
    _s("newsletter_form", GROUP_FEATURES, "Newsletter signup form", kind="bool",
       help="The public form at /newsletter/: a subscriber becomes a Contact with "
            "marketing consent, which the mailing-list sync passes to the mailing "
            "service. Off, the form answers 404."),
    _s("business_evaluation", GROUP_FEATURES, "Business Evaluation", kind="bool",
       component="both",
       help="The free business evaluation a mentor offers a new client: the "
            "public survey pages at /evaluation/… and, in later phases, the "
            "Evaluations tab. Off, those addresses answer 404 and no existing "
            "page changes. Read per request. Needs the CBusinessEvaluation "
            "entity in the CRM (business-evaluation-crm-handoff.md)."),
    _s("evaluation_link_days", GROUP_FEATURES, "Evaluation link lifetime", kind="int",
       unit="days",
       help="Days a Business Evaluation link stays open after it is made. A link "
            "made earlier keeps the expiry it was given."),
    _s("evaluation_retry_seconds", GROUP_FEATURES, "Evaluation retry interval", kind="int",
       component="worker", unit="s",
       help="Seconds between the worker's passes that send a submitted survey the "
            "CRM refused at the time. The answers are kept until it succeeds. 0 stops "
            "the pass."),
    _s("campaigns_enabled", GROUP_FEATURES, "Marketing Management", kind="bool",
       component="both",
       help="The Marketing Management tile, the Prospects grid and import, the "
            "postcard kind and the campaign links at /c/. Read per request: no "
            "restart. Needs the CProspect, COutreachCampaign and COutreachTouch "
            "entities in the CRM (coutreach-entities-crm-handoff.md)."),
    _s("campaigns_landing_public", GROUP_FEATURES, "Postcard landing page", kind="bool",
       help="The public page a postcard's QR code opens (/p/{token}). Off, the "
            "page answers 404; a card already mailed waits for it."),
    _s("postal_provider", GROUP_INTEGRATIONS, "Mail vendor", kind="choice",
       choices=("dryrun", "lob"), component="both",
       help="'dryrun' mails nothing and produces the preview pieces. 'lob' is the "
            "real adapter and needs the key below."),
    _s("postal_api_key", GROUP_INTEGRATIONS, "Mail vendor API key", component="both",
       help="The vendor's API key. With 'Mail vendor test mode' on, a test key is "
            "the right one: the whole pipeline runs and nothing is printed."),
    _s("postal_webhook_secret", GROUP_INTEGRATIONS, "Mail vendor webhook secret",
       help="Signs the delivery and return events the vendor posts to "
            "/api/campaigns/postal/events. Unset, that route is not mounted."),
    _s("postal_test_mode", GROUP_INTEGRATIONS, "Mail vendor test mode", kind="bool",
       component="both",
       help="On (the default), even a real key mails nothing. Switch it off for "
            "ONE real run and back on afterwards (build plan § 7 Phase 1)."),
    _s("postal_unit_cost", GROUP_INTEGRATIONS, "Postcard unit cost", kind="float",
       help="The per-piece price from the vendor's price sheet; the sign-off shows "
            "pieces × this. 0 (the dry run's price) until the vendor is chosen."),
    _s("postal_currency", GROUP_INTEGRATIONS, "Postcard cost currency",
       help="The three-letter code the estimated cost is written in (the CRM's "
            "currency field needs it on every write)."),
    _s("campaigns_run_seconds", GROUP_FEATURES, "Campaign run poll", kind="int",
       unit="s", component="worker",
       help="How often the worker looks for a signed-off postcard campaign to run. "
            "0 disables the run."),
    _s("campaigns_calls", GROUP_FEATURES, "Campaign calls", kind="bool",
       help="The Call campaign kind and the Calls screen (prospect marketing "
            "Phase 3). Callers are the members of the teams named on each "
            "campaign (ruling 36). Read per request: no restart."),
    _s("prospect_stale_days", GROUP_FEATURES, "Prospect stale after", kind="int",
       unit="days", component="both",
       help="An Unverified or Qualified prospect record with no touch for this "
            "many days leaves by the Stale side exit. 0 makes every untouched "
            "record stale — for a live check only."),
    _s("campaigns_email", GROUP_FEATURES, "Campaign emails", kind="bool", component="both",
       help="The email campaign kind: each campaign's opted-in people pushed as its own "
            "named list at the mailing service, where staff design and send the notice. "
            "Needs the mailing connection (Mailing list sync's client ID and secret)."),
    _s("campaign_lists", GROUP_FEATURES, "Campaign lists", kind="bool", component="web",
       help="Named lists a campaign sends to (build plan § 7c): the Lists page in "
            "Marketing Management and the List picker on a campaign. Off, every campaign "
            "selects by its kind's own rule, as before. Read per request: no restart."),
    _s("campaign_list_sync", GROUP_FEATURES, "Campaign list copies", kind="bool", component="both",
       help="A list may keep a copy in Constant Contact, kept current by the mailing pass, and an "
            "email campaign sends to its list's copy: sign-off syncs it, staff send the notice at "
            "the mailing service, then pick that email in the campaign. Every push writes each "
            "person's lead code to the custom field cbm_lead_code. Needs Campaign lists and the "
            "mailing connection. Off, lists and email campaigns work as before."),
    _s("campaign_lists_only", GROUP_FEATURES, "Campaigns send to lists only", kind="bool", component="web",
       help="Every campaign sends to a list: the per-kind rule boxes go, five ready-made lists stand in "
            "for them, and the campaign page shows its stage strip and the Audience and content tab. "
            "A campaign already built by a rule box is given its kind's ready-made list. Needs Campaign "
            "lists. Read per request: no restart. Off, campaigns work as before."),
    _s("campaign_send_report", GROUP_FEATURES, "Campaign send report", kind="bool", component="both",
       help="Each email campaign's Constant Contact report is read for 30 days after its email is "
            "picked: one touch per recipient — delivered or bounced, opens and clicks — and the "
            "campaign completes when the 30 days end. Also the Recipients tab's Read the report now. "
            "Needs Campaign lists, Campaign list copies and the mailing connection. Off, nothing is read."),
    _s("campaign_send_report_seconds", GROUP_FEATURES, "Campaign send report interval", kind="int",
       component="worker",
       help="Seconds between the worker's reads of the send reports (default a day). 0 stops the reads."),
    _s("campaign_list_screens", GROUP_FEATURES, "Campaign list screens", kind="bool", component="web",
       help="The Lists tab redesigned: it opens on a searchable list of every list, with a "
            "Preview panel; Edit and View are screens of their own, and View opens the members in "
            "a separate browser tab. Needs Campaign lists. Read per request: no restart. Off, the "
            "Lists tab is the one built before."),
    _s("event_promote", GROUP_FEATURES, "Promote this event", kind="bool", component="web",
       help="A Promote this event button on an event in Event Administration makes one draft campaign "
            "per ticked channel, each linked to the event, with a link to its registration page and "
            "the chosen list; the event gains a Campaigns tab counting who each campaign reached, "
            "registered and attended. Needs Marketing Management and Campaign lists. Read per "
            "request: no restart. Off, Event Administration shows neither."),
    _s("calls_panel", GROUP_FEATURES, "Calls tab side panel", kind="bool", component="web",
       help="The Calls tab with a count line, the brief at the top, attempts and the last attempt "
            "per row, and a side panel holding what we know, the person's own link and the four "
            "outcomes; Call again takes a time, and recording moves to the next row. Read per "
            "request: no restart. Off, the Calls tab works as before."),
    _s("campaign_list_count_seconds", GROUP_FEATURES, "Campaign list count interval", kind="int",
       component="worker",
       help="Seconds between the worker's passes that re-run every active dynamic list and count "
            "every active list's members and reach (default a day). 0 stops the pass; Refresh on a "
            "list still counts that list."),
    _s("campaign_list_fields", GROUP_FEATURES, "Campaign list fields", component="web",
       help="The fields a list step may filter on, per record type (ruling 63), written "
            "as 'lead: leadStatus, leadSource; contact: cContactType, cFunnelStage'. Use "
            "the CRM's field names; a dotted name follows links (client: "
            "engagementClient.industrySector). Record types: lead, contact, client, partner, "
            "funder. Empty uses the defaults. Each field is checked against the CRM when "
            "saved; a field the CRM lacks is refused."),
    _s("campaigns_sms", GROUP_FEATURES, "Campaign texts", kind="bool", component="both",
       help="The text-message campaign kind (rulings 38, 39). The application sends "
            "the texts through the texting service below — with 'Texting service' at "
            "dryrun nothing is texted. Needs COutreachCampaign.smsMessage in the CRM."),
    _s("sms_provider", GROUP_INTEGRATIONS, "Texting service", kind="choice",
       choices=("dryrun", "twilio"), component="both",
       help="'dryrun' texts nothing. 'twilio' sends for real and needs the account, "
            "the sender number and the carrier registration (A2P 10DLC) first."),
    _s("sms_account_sid", GROUP_INTEGRATIONS, "Texting account SID", component="both"),
    _s("sms_auth_token", GROUP_INTEGRATIONS, "Texting auth token", component="both",
       help="Sends the texts (worker) and verifies the replies and delivery reports "
            "the service posts back (web)."),
    _s("sms_from_number", GROUP_INTEGRATIONS, "Texting sender number", component="worker",
       help="The number texts come from, in +1… form."),
    _s("sms_send_hours", GROUP_INTEGRATIONS, "Texting hours", component="worker",
       help="Hours a text may go out, chapter time, as start-end (9-20 = 9:00 to 19:59)."),
    _s("sms_timezone", GROUP_INTEGRATIONS, "Texting time zone", component="worker",
       help="The time zone the texting hours are read in."),
    _s("enrichment_free_pass", GROUP_FEATURES, "Lead fit scores", kind="bool",
       component="worker",
       help="The free pass: the worker scores every open lead 0 to 100 for fit "
            "(prds/lead-enrichment/). Needs the nine fit fields on CProspect "
            "(lead-fit-score-crm-handoff.md). Writes nothing but the score fields, and "
            "a verified website into an empty website field."),
    _s("enrichment_web_checks", GROUP_FEATURES, "Lead web checks", kind="bool",
       component="worker",
       help="Lets the free pass fetch web addresses guessed from a lead's name and keep "
            "one only when the page shows the name and the address or an associate "
            "(ruling E12). Off, no outside request is made."),
    _s("enrichment_sweep_seconds", GROUP_FEATURES, "Lead fit sweep", kind="int",
       unit="s", component="worker",
       help="How often the worker scores a batch of leads. 0 stops the sweep; "
            "/setup → Operations → Lead fit scores still runs it by hand."),
    _s("enrichment_batch", GROUP_FEATURES, "Lead fit batch", kind="int", component="worker",
       help="Leads scored per pass, at most 200 (the CRM's page limit)."),
    _s("chapter_counties", GROUP_FEATURES, "Service area counties", component="both",
       help="The chapter's counties as State:County pairs separated by |, for example "
            "OH:Cuyahoga|OH:Lake. A lead confirmed outside them scores 0 and is flagged "
            "Out of area. Empty: the location is not checked. Changing it rescores every lead."),
    _s("fit_weights", GROUP_FEATURES, "Fit score weights", component="worker",
       help="Three numbers: operating business, segment, findability. 1,1,1 weighs them "
            "equally. Changing it rescores every lead."),
    _s("chapter_segments_url", GROUP_FEATURES, "Segment list address", component="worker",
       help="The address of the chapter's segment list, a JSON file with \"favoured\" and "
            "\"excluded\" lists of industries or words. Empty: every lead scores 50 for segment."),
    _s("enrichment_terms_url", GROUP_FEATURES, "Name rules address", component="worker",
       help="The address of a chapter's own version of the name-reading rules "
            "(enrichment/data/name_terms.json). Empty: the shipped rules."),
    _s("enrichment_ai", GROUP_FEATURES, "AI research", kind="bool", component="both",
       help="Lets staff start an AI research run on a lead, a set of leads or a client's company "
            "(prds/lead-enrichment/, ruling E18). Needs the Anthropic API key and the "
            "CEnrichmentFinding entity (enrichment-finding-crm-handoff.md). Read per request."),
    _s("enrichment_ai_model", GROUP_FEATURES, "AI research model", component="worker",
       help="The Claude model the research runs on. claude-opus-5-5 by default."),
    _s("enrichment_monthly_budget", GROUP_FEATURES, "Enrichment monthly budget", kind="float",
       unit="$", component="both",
       help="What paid enrichment may spend in a calendar month (rulings E8, E9). A run that would "
            "pass it is refused, with the amounts named."),
    _s("enrichment_ai_max_searches", GROUP_FEATURES, "AI research searches per business", kind="int",
       component="worker", help="Web searches the model may make for one business ($0.01 each)."),
    _s("enrichment_ai_record_cap", GROUP_FEATURES, "AI research cap per business", kind="float",
       unit="$", component="worker",
       help="A business whose research passes this cost is stopped and marked failed."),
    _s("enrichment_ai_max_records", GROUP_FEATURES, "AI research records per run", kind="int",
       component="web", help="The most records one run may take."),
    _s("enrichment_ai_fallback", GROUP_FEATURES, "AI research fallback", kind="bool", component="worker",
       help="When the model declines a request, re-run it on the next model automatically. Off: "
            "a declined business is marked failed."),
    _s("enrichment_ai_poll_seconds", GROUP_FEATURES, "AI research queue poll", kind="int", unit="s",
       component="worker", help="How often the worker takes the next records from the queue. 0 stops it."),
    _s("lead_ladder", GROUP_FEATURES, "Lead qualification ladder", kind="bool", component="both",
       help="The level inside Qualified — Identified, Contactable, Referred — placed by the "
            "system and settable by hand, never moved backwards; the Leads tab's counts, "
            "Level and Reach columns, Assigned to, and the lead's own page. Needs the "
            "redesign's lead fields on the CRM (marketing-redesign-crm-handoff.md); without "
            "them the Leads tab stays as before. Read per request: no restart."),
    _s("lead_level_sweep_seconds", GROUP_FEATURES, "Lead level sweep", kind="int",
       unit="s", component="worker",
       help="How often the worker re-places the level of leads edited since its last pass "
            "(catches edits made in the CRM's own screens). 0 stops the sweep; "
            "/setup → Operations → Lead levels still runs it by hand."),
    _s("import_templates", GROUP_FEATURES, "Import templates", kind="bool", component="both",
       help="The import tool on the Imports tab: saved templates for recurring spreadsheets, "
            "Excel as well as CSV, recognition of the matching template with the differences "
            "shown, the four column fixes, a preview the delivery worker computes while the "
            "page polls, repeat rows filling a lead's empty fields, the level per row, and "
            "Undo this import. Off, the Imports tab and the CSV import behave exactly as "
            "before. Read per request: no restart."),
    _s("lead_outreach", GROUP_FEATURES, "Personal outreach to leads", kind="bool", component="both",
       help="On a lead's page: Email through the full composer from the assignee's own chapter "
            "mailbox (the mentor profile's address, else the user's own on the mail domain), Log a "
            "call with Interested / Not interested / No reply yet, a Conversations block, and the "
            "email sync attaching a reply from an assigned lead's address to the lead and marking "
            "it Replied. Needs the lead's Assigned to and Replied fields and the conversation link "
            "on the CRM (marketing-redesign-crm-handoff.md), the Gmail integration, and the "
            "chapter postal address under Presentation. Read per request: no restart."),
    _s("import_plan_poll_seconds", GROUP_FEATURES, "Import plan poll", kind="int", unit="s",
       component="worker",
       help="How often the delivery worker looks for an import preview waiting to be "
            "computed. 0 stops it — then no import can be previewed, and the page says so "
            "after two minutes."),
    _s("prospect_stale_sweep_seconds", GROUP_FEATURES, "Prospect stale sweep", kind="int",
       unit="s", component="worker",
       help="How often the worker runs the Stale sweep (default nightly). 0 "
            "disables it; /setup → Operations still runs it by hand."),
    _s("gmail_sync", GROUP_FEATURES, "Gmail conversation sync", kind="bool",
       component="both",
       help="The whole Communications pipeline. Needs the Google service account."),
    _s("gcal_events", GROUP_FEATURES, "Google Calendar events", kind="bool",
       help="Saving a Scheduled session reconciles an event on the manager's calendar."),
    _s("meet_transcripts", GROUP_FEATURES, "Meet transcripts", kind="bool",
       component="both",
       help="Do NOT switch on before the meetings.space.created DWD scope exists — "
            "every Scheduled save would show mentors a transcription failure."),
    _s("fathom_transcripts", GROUP_FEATURES, "Fathom transcripts", kind="bool",
       component="worker",
       help="Worker-only: Fathom auto-joins from the mentor's own calendar."),
    _s("gdrive_docs", GROUP_FEATURES, "Google Drive documents", kind="bool",
       component="both", help="The Documents tab. Needs a database and the shared drive."),
    _s("record_quick_add", GROUP_FEATURES, "Add partners & funders in-app", kind="bool",
       help="The '+ Add partner' / '+ Add funder' button on those grids. Creates the "
            "company, primary contact and profile as the signed-in user."),
    _s("login_repair_guards", GROUP_FEATURES, "Stop login repairs on disagreement", kind="bool",
       component="both",
       help="The nightly clean-up, a Mentor Administration save, Update Mentor Status "
            "and provisioning copy a mentor's login only when the login data agrees "
            "(one profile, its CBM email matching). Otherwise they leave it and log a "
            "fault."),
    _s("manager_profile_strict", GROUP_FEATURES, "Strict mentor profile choice", kind="bool",
       help="A login on several mentor profiles opens only the one Active profile whose "
            "CBM email matches the login. Otherwise Client Management and My Mentor "
            "Profile show no records and say why."),
    _s("cbm_email_lock", GROUP_FEATURES, "Lock the mentor CBM email", kind="bool",
       help="In Mentor Administration the CBM email can't be edited once the mentor "
            "has a login; it shows the login's user name. Before then a typed address "
            "must be on the chapter's mail domain and not already a login or another "
            "mentor's address."),
    _s("login_integrity_check", GROUP_FEATURES, "Daily login integrity check", kind="bool",
       component="worker",
       help="Once a day the worker checks every mentor profile, login and mentor "
            "Contact for the six login faults and records what it finds. Report only: "
            "a log line and scripts/integrity_report.py. Sends no email."),
    _s("integrity_digest", GROUP_FEATURES, "Tell staff about login faults", kind="bool",
       component="both",
       help="The integrity digest: one email a day listing every open login fault, "
            "new ones marked. Also the fault list and the badge in Mentor "
            "Administration. Turn on only after reading this instance's first report."),
    _s("record_history_tab", GROUP_FEATURES, "History tab on records", kind="bool",
       help="A History tab on a mentor profile (Mentor Administration), an engagement "
            "(Client Administration), a partner or funder (Partner and Funder "
            "Management) and an event (Event Administration). It lists the "
            "applications' recorded actions and the CRM's own record changes, newest "
            "first, with old and new values. Never shown in Client Management."),
    _s("activity_page", GROUP_FEATURES, "Activity page", kind="bool",
       help="A page listing every change by one person, or in a date range, across "
            "every record, with a CSV export. For the System Management Team; "
            "administrators always see it."),
    _s("integrity_crm_use_report", GROUP_FEATURES, "Report work in the CRM's own screens",
       kind="bool",
       help="Once a day the web component reads the CRM's Action History and sign-in log "
            "as the administrator and records who created, changed or deleted records in "
            "the CRM's own screens, and any screen sign-in by a shared account. Listed in "
            "the login fault list and the integrity digest."),
    _s("integrity_signin_alert", GROUP_FEATURES, "Alert when a login has no mentor profile",
       kind="bool",
       help="When a login with no mentor profile opens Client Management or My Mentor "
            "Profile, record it and (with the integrity digest on) email at once, at "
            "most once per login per day."),
    _s("portal_calendar", GROUP_FEATURES, "Events on the portal home page", kind="bool",
       help="The rail of upcoming events beside the portal's tiles, and the member "
            "page each one opens. Members see Internal events (to their teams, if "
            "limited) and this chapter's Public webinars. Needs Events & Webinars on."),
    _s("portal_events_window_days", GROUP_FEATURES, "Portal calendar window", kind="int",
       unit="days",
       help="How many days ahead the rail lists in full; events beyond fold behind "
            "one line. 0 folds everything."),
    _s("event_presenters", GROUP_FEATURES, "Presenters on events", kind="bool",
       help="The Presenters group in the event editor and the presenter cards on "
            "the public and portal event pages. Stays hidden until the CRM has "
            "CEventPresenter, so it is safe to switch on early."),
    _s("events_confirmations", GROUP_FEATURES, "Registration confirmation emails", kind="bool",
       component="both",
       help="CBM's own confirmation to each event registrant, from the EspoCRM "
            "templates EventConfirmation, EventWaitlisted and EventSeatOffered, "
            "as the shared mailbox. Zoom's own confirmations are off, so this is "
            "the registrant's only email. Needs Gmail sync and the shared mailbox."),
    _s("grants_enabled", GROUP_FEATURES, "Grants on funder records", kind="bool",
       help="The Grants tab in Funder Management — awards, deliverables and (later) "
            "funder reporting. Stays hidden until the CRM has CGrant and "
            "CGrantDeliverable, so it is safe to switch on early."),
    _s("comms_ai_summary", GROUP_FEATURES, "AI conversation summaries", kind="bool",
       component="worker", help="Optional. Requires ANTHROPIC_API_KEY."),
    _s("comms_digest", GROUP_FEATURES, "Daily email digest", kind="bool",
       component="worker", help="Needs Gmail sync, the shared mailbox and the database."),
    _s("mentor_provision_users", GROUP_FEATURES, "Provision mentor logins", kind="bool",
       help="Creates an EspoCRM User on approval, via the admin service account."),
    _s("google_directory_check", GROUP_FEATURES, "Verify {{abbr}} mailbox exists", kind="bool",
       help="Blocks provisioning when a mailbox is confirmed missing. Fails open."),
    _s("google_create_mailbox", GROUP_FEATURES, "Create missing mailboxes", kind="bool",
       help="Needs the read-WRITE Directory scope."),
    _s("async_delivery", GROUP_FEATURES, "Asynchronous delivery", kind="bool",
       component="both",
       help="Capture returns immediately and the worker delivers with retries. "
            "Off = synchronous. Needs a database."),
    _s("gmail_resync", GROUP_FEATURES, "Gmail one-shot resync", kind="bool",
       component="worker",
       help="Clears every mailbox cursor on worker start so the next pass re-runs the "
            "backfill. Set it, let ONE pass complete, then turn it off — left on, every "
            "restart re-reads all mailboxes. A good candidate for a temporary override."),
    _s("integrations_tab", GROUP_FEATURES, "Integrations tab", kind="bool",
       help="An Integrations tab on this page, one sub-tab per outside service. Each "
            "integration's own settings and switches move there from this tab. Off, "
            "this page is exactly as before. Read per request: no restart."),

    # --- "in use", one per integration (prds/integrations-tab-plan.md, ruling
    # I5). Shown only on the Integrations tab, first on each sub-tab. EspoCRM
    # has none: it is always in use.
    _s("google_workspace_in_use", GROUP_INTEGRATIONS, "Google Workspace in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Google Workspace")),
    _s("zoom_in_use", GROUP_INTEGRATIONS, "Zoom in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Zoom")),
    _s("fathom_in_use", GROUP_INTEGRATIONS, "Fathom in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Fathom")),
    _s("constant_contact_in_use", GROUP_INTEGRATIONS, "Constant Contact in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Constant Contact")),
    _s("lob_in_use", GROUP_INTEGRATIONS, "Lob in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Lob")),
    _s("twilio_in_use", GROUP_INTEGRATIONS, "Twilio in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Twilio")),
    _s("anthropic_in_use", GROUP_INTEGRATIONS, "Anthropic in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="Anthropic")),
    _s("youtube_in_use", GROUP_INTEGRATIONS, "YouTube in use", kind="bool",
       component="both", help=_IN_USE_HELP.format(name="YouTube")),

    # --- Integrations ------------------------------------------------------
    _s("gdrive_identity", GROUP_INTEGRATIONS, "Drive identity", kind="choice",
       choices=("user", "service"), component="both",
       help="'service' is the operational mode — nobody is a shared-drive member."),
    _s("gdrive_shared_drive_id", GROUP_INTEGRATIONS, "Shared drive ID", component="both"),
    _s("gdrive_entity_labels", GROUP_INTEGRATIONS, "Drive folder labels", kind="csv",
       component="both", help="Entity=Label pairs, e.g. CEngagement=Clients."),
    _s("gdrive_doc_types", GROUP_INTEGRATIONS, "Document types", kind="csv"),
    _s("gdrive_max_file_mb", GROUP_INTEGRATIONS, "Max upload size", kind="int", unit="MB"),
    _s("gdrive_reconcile_seconds", GROUP_INTEGRATIONS, "Drive grant reconciliation",
       kind="int", unit="s", component="worker", help="0 disables the nightly job."),
    _s("google_delegated_admin", GROUP_INTEGRATIONS, "Delegated Workspace admin",
       component="both", help="Must be a real licensed mailbox — a group or alias 403s."),
    _s("google_members_group", GROUP_INTEGRATIONS, "All Members group",
       help="Google Group a mentor's new mailbox joins when their account is created. "
            "Blank skips the group step. Needs the Directory group scope."),
    _s("zoom_host_email", GROUP_INTEGRATIONS, "Zoom host", component="both"),
    _s("zoom_base_url", GROUP_INTEGRATIONS, "Zoom API base URL", component="both"),
    _s("fathom_base_url", GROUP_INTEGRATIONS, "Fathom API base URL", component="worker"),
    _s("meet_transcripts_poll_seconds", GROUP_INTEGRATIONS, "Transcript retrieval",
       kind="int", unit="s", component="worker", help="Shared by the Meet and Fathom sources."),
    _s("transcript_give_up_days", GROUP_INTEGRATIONS, "Transcript give-up window",
       kind="int", unit="days", component="worker",
       help="Keep inside Google's 30-day transcript retention."),
    _s("summary_model", GROUP_INTEGRATIONS, "Summary model", component="worker"),
    _s("youtube_playlist_id", GROUP_INTEGRATIONS, "YouTube playlists",
       help="The recorded-webinar playlists to import from, comma separated. "
            "{{abbr}} keeps five topic playlists rather than one library. A video in "
            "two of them is imported once. Read only by the import script."),

    # --- Email -------------------------------------------------------------
    _s("ops_mailbox", GROUP_EMAIL, "Shared mailbox", component="both",
       help="Submission Admin sends and reads as this. Must be a REAL mailbox, not a "
            "group. Only ONE environment may poll it — setting it on both double-captures."),
    _s("ops_mailbox_name", GROUP_EMAIL, "Shared mailbox display name", component="both"),
    _s("sandbox_address_domain", GROUP_EMAIL, "Sandbox address domain", component="both",
       help="The domain this system's invented training addresses sit on, such as "
            "sandbox.mentorsassociation.org. Nothing is ever sent to, shared with, "
            "added to a group as, or put on a mailing list as an address on it. "
            "Blank on a system with no training data."),
    _s("ops_reply_template", GROUP_EMAIL, "Canned reply template"),
    _s("ops_inbound_seconds", GROUP_EMAIL, "Inbound poll", kind="int", unit="s",
       component="worker", help="0 turns inbound capture off."),
    _s("ops_inbound_window_days", GROUP_EMAIL, "Inbound sweep window", kind="int",
       unit="days", component="worker"),
    _s("alert_email_to", GROUP_EMAIL, "Alert recipients", kind="csv", component="both"),
    _s("alert_email_from", GROUP_EMAIL, "Alert sender", component="both",
       help="Must be a real licensed mailbox; falls back to the shared mailbox."),
    _s("alert_webhook_url", GROUP_EMAIL, "Alert webhook", component="both"),
    _s("gmail_sync_seconds", GROUP_EMAIL, "Gmail sync cadence", kind="int", unit="s",
       component="worker"),
    _s("comms_scope_rebuild_seconds", GROUP_EMAIL, "Mailbox scope rebuild", kind="int",
       unit="s", component="worker",
       help="How long the sync may reuse its map of who handles which records "
            "before rebuilding it from the CRM. Between rebuilds each pass only "
            "asks the CRM whether anything changed. 0 rebuilds every pass."),
    _s("gmail_backfill", GROUP_EMAIL, "Initial sync window", component="worker"),
    _s("gmail_dead_letter_passes", GROUP_EMAIL, "Dead-letter after", kind="int",
       unit="passes", component="worker"),
    _s("integrity_digest_to", GROUP_EMAIL, "Login fault recipients", kind="csv",
       component="both",
       help="Who receives the integrity digest and the no-profile sign-in alert. "
            "Empty uses the alert recipients."),
    _s("login_integrity_hour", GROUP_EMAIL, "Integrity check hour", kind="int",
       component="both",
       help="Local hour of the daily login integrity check; the digest follows it, and "
            "the report on the CRM's own screens runs an hour before. "
            "On the training sandbox a time between 04:00 and 06:00 UTC moves to 06:00 UTC."),
    _s("login_integrity_tz", GROUP_EMAIL, "Integrity check timezone", component="both"),
    _s("integrity_shared_accounts", GROUP_EMAIL, "Shared CRM accounts", kind="csv",
       help="Logins whose sign-in to the CRM's own screens is reported. Empty means admin, "
            "and admin@ and mentoradmin@ the mentor email domain."),
    _s("integrity_excluded_logins", GROUP_EMAIL, "Logins not reported for CRM edits",
       kind="csv",
       help="Never reported for editing in the CRM's own screens. The provisioning and "
            "key-based accounts are left out automatically."),
    _s("integrity_app_addresses", GROUP_EMAIL, "This application's network addresses",
       kind="csv",
       help="Addresses known to be this application, so its traffic is never counted as "
            "use of the CRM's own screens. Usually found automatically; empty is normal."),
    _s("comms_digest_hour", GROUP_EMAIL, "Digest hour", kind="int", component="worker"),
    _s("comms_digest_tz", GROUP_EMAIL, "Digest timezone", component="worker"),
    _s("comms_digest_seconds", GROUP_EMAIL, "Digest re-check", kind="int", unit="s",
       component="worker"),
    _s("comms_internal_domains", GROUP_EMAIL, "Internal domains", kind="csv",
       component="both", help="Mail between these domains links to Contacts, never records."),
    _s("mentor_email_domain", GROUP_EMAIL, "Mentor email domain", component="web",
       help="Mentor logins and mailboxes are minted as firstname.lastname@ this domain."),
    _s("comms_engagement_statuses", GROUP_EMAIL, "Active engagement statuses", kind="csv",
       component="both"),
    _s("comms_partner_excluded_statuses", GROUP_EMAIL, "Excluded partner statuses",
       kind="csv", component="both"),
    _s("comms_attachment_excluded_types", GROUP_EMAIL, "Never file these attachments",
       kind="csv", component="both",
       help="MIME types (text/calendar) or filenames/extensions (.ics, winmail.dat) "
            "that inbound mail never files to a record's Documents tab. The bytes "
            "stay in the message — View original still shows them."),

    # --- Reliability -------------------------------------------------------
    _s("duplicate_hold_seconds", GROUP_RELIABILITY, "Near-duplicate hold", kind="int",
       unit="s", component="both", help="0 disables the hold entirely."),
    _s("worker_poll_seconds", GROUP_RELIABILITY, "Worker poll", kind="int", unit="s",
       component="worker"),
    _s("worker_batch_size", GROUP_RELIABILITY, "Worker batch size", kind="int",
       component="worker"),
    _s("worker_lease_seconds", GROUP_RELIABILITY, "Delivery lease", kind="int", unit="s",
       component="worker", help="How long a claimed row stays leased before reclaim."),
    _s("max_delivery_attempts", GROUP_RELIABILITY, "Max delivery attempts", kind="int",
       component="worker"),
    _s("alert_check_seconds", GROUP_RELIABILITY, "Alert evaluation", kind="int", unit="s",
       component="worker"),
    _s("alert_needs_attention_threshold", GROUP_RELIABILITY, "Needs-attention threshold",
       kind="int", component="worker"),
    _s("alert_pending_age_minutes", GROUP_RELIABILITY, "Oldest-pending threshold",
       kind="int", unit="min", component="worker"),
    _s("alert_cooldown_seconds", GROUP_RELIABILITY, "Alert cooldown", kind="int", unit="s",
       component="worker"),
    _s("integration_test_hour", GROUP_RELIABILITY, "Nightly integration test hour", kind="int",
       component="worker",
       help="Local hour at which the worker runs the integration test of every integration "
            "in use with a feature switched on, while the Integrations tab is on. A failure "
            "sends one alert; an unchanged failure is not repeated."),
    _s("integration_test_tz", GROUP_RELIABILITY, "Nightly integration test timezone",
       component="worker"),
    _s("schema_check_seconds", GROUP_RELIABILITY, "Schema-drift check", kind="int",
       unit="s", component="worker", help="0 disables."),
    _s("worker_liveness_check_seconds", GROUP_RELIABILITY, "Worker liveness watch",
       kind="int", unit="s", help="Runs on WEB — a dead worker can't alert on itself."),
    _s("worker_heartbeat_alert_seconds", GROUP_RELIABILITY, "Heartbeat staleness",
       kind="int", unit="s"),
    _s("receipt_reconcile_seconds", GROUP_RELIABILITY, "Receipt reconciliation",
       kind="int", unit="s", component="worker", help="0 disables the timer."),
    _s("assignment_reconcile_seconds", GROUP_RELIABILITY, "Assignment-stamp reconciliation",
       kind="int", unit="s", component="worker", help="0 disables."),
    _s("analytics_refresh_seconds", GROUP_RELIABILITY, "Analytics warm job", kind="int",
       unit="s", component="worker"),
    _s("analytics_default_cache_ttl_seconds", GROUP_RELIABILITY, "Analytics cache TTL",
       kind="int", unit="s"),
    # Events worker cadences. Inert unless Events is on; grouped with the other
    # worker timers rather than with the events feature, because what a reader
    # needs to know about them is that they are polling intervals.
    _s("events_attendance_seconds", GROUP_RELIABILITY, "Attendance pull", kind="int",
       unit="s", component="worker",
       help="How often finished online events are checked for a Zoom participant "
            "report."),
    _s("events_attendance_grace_minutes", GROUP_RELIABILITY, "Attendance grace",
       kind="int", unit="min", component="worker",
       help="How long after an event ends before its report is first asked for — "
            "an empty report means 'not published yet', never 'nobody came'."),
    _s("events_attendance_give_up_hours", GROUP_RELIABILITY, "Attendance give-up",
       kind="int", unit="h", component="worker",
       help="When to stop asking. Past this an event's attendance stays as it is."),
    _s("events_reminder_seconds", GROUP_RELIABILITY, "Reminder sweep", kind="int",
       unit="s", component="worker",
       help="How often the worker looks for reminders that are due."),
    _s("events_reminder_lead_hours", GROUP_RELIABILITY, "Reminder lead time",
       kind="int", unit="h", component="worker",
       help="How far ahead of an event a reminder goes out. Never sent after an "
            "event has started, so a worker that was down through the window "
            "stays quiet rather than sending late."),
    _s("setup_refresh_seconds", GROUP_RELIABILITY, "Settings refresh", kind="int",
       unit="s", component="both",
       help="How often each process re-reads the overrides on this page. Web and "
            "worker refresh independently; /healthz reports each one's version."),
    _s("membership_refresh_seconds", GROUP_RELIABILITY, "Membership re-read", kind="int",
       unit="s", help="How long a session's cached team membership stays trusted."),
    _s("request_timeout_seconds", GROUP_RELIABILITY, "CRM request timeout", kind="int",
       unit="s", component="both"),
    _s("crm_metadata_cache_seconds", GROUP_RELIABILITY, "CRM metadata cache", kind="int",
       unit="s", component="both",
       help="How long field definitions, layouts, labels and enum options are "
            "remembered before the CRM is asked again. A field built in the CRM "
            "shows within this window. 0 reads the CRM on every request."),
    _s("request_timing_log_ms", GROUP_RELIABILITY, "Timing log threshold", kind="int",
       unit="ms", component="web",
       help="The web log carries one 'timing' line per API request: total time, "
            "CRM calls and their time. 0 logs every API request; a higher value "
            "logs only the requests slower than it."),

    # --- Team gates --------------------------------------------------------
    _s("assign_allowed_teams", GROUP_GATES, "Client Administration", kind="csv"),
    _s("assign_allowed_roles", GROUP_GATES, "Client Administration (roles)", kind="csv",
       help="A regular user's token cannot read its own roles — prefer teams."),
    _s("mentor_admin_allowed_teams", GROUP_GATES, "Mentor Administration", kind="csv"),
    _s("system_management_allowed_teams", GROUP_GATES, "System Management", kind="csv",
       help="The team whose members see the activity page (and later System Management functions). Copy the team's name "
            "exactly; administrators always pass."),
    _s("mentor_profile_allowed_teams", GROUP_GATES, "My Mentor Profile", kind="csv"),
    _s("ops_allowed_teams", GROUP_GATES, "Submission Admin", kind="csv"),
    _s("session_mentor_allowed_teams", GROUP_GATES, "Client Management", kind="csv"),
    _s("session_partner_allowed_teams", GROUP_GATES, "Partner Management", kind="csv"),
    _s("session_sponsor_allowed_teams", GROUP_GATES, "Funder Management", kind="csv"),
    _s("workspace_allowed_teams", GROUP_GATES, "Workspace Directories", kind="csv"),
    _s("events_allowed_teams", GROUP_GATES, "Event Administration", kind="csv"),
    _s("campaigns_allowed_teams", GROUP_GATES, "Marketing Management", kind="csv"),
    _s("analytics_view_allowed_teams", GROUP_GATES, "Analytics — view", kind="csv"),
    _s("analytics_admin_allowed_teams", GROUP_GATES, "Analytics — author", kind="csv"),
    _s("mentor_team_name", GROUP_GATES, "Mentor team (provisioning)"),
    _s("partner_team_name", GROUP_GATES, "Partner team stamp",
       help="Stamped on new CPartnerProfiles. Empty disables the stamp."),
    _s("sponsor_team_name", GROUP_GATES, "Funder team stamp"),

    # --- Presentation ------------------------------------------------------
    _s("organization_name", GROUP_WEBSITE, "Organisation name", component="both",
       help="The name every page carries — title, footer and the public forms' prose. "
            "Substituted server-side as it is served, so a change here takes effect on "
            "the next page load with no redeploy."),
    _s("organization_abbreviation", GROUP_WEBSITE, "Chapter acronym", component="both",
       help="The short form of the name, CBM for Cleveland. Every page, message and "
            "email that used to say CBM says this instead — \"ask CBM staff\", the "
            "\"CBM contacts\" table, the daily digest subject. Substituted as pages "
            "are served, so a change takes effect on the next page load."),
    _s("chapter_postal_address", GROUP_WEBSITE, "Chapter postal address", kind="text", component="web",
       help="The chapter's mailing address, one or more lines. Every personal email a lead receives "
            "ends with the sentence offering a way to say no AND this address (the server appends "
            "both when the message lacks them). Empty, personal email is refused and the refusal "
            "names this setting."),
    _s("chapter_key", GROUP_PRESENTATION, "Chapter short label",
       help="This chapter's short label in the chapter list of the CRM standard — "
            "cleveland, boston. Every public event's reach includes it. It must be "
            "one of the options of the event Chapters field, or the reach is left alone."),
    _s("organization_logo_url", GROUP_WEBSITE, "Organisation logo URL",
       help="A publicly-hosted https image (typically on the org's own website). "
            "Powers the email-signature editor's Insert-logo button — signature "
            "images must be reachable without a login. The website uses the logo "
            "uploaded under Website images below, and this address only when none "
            "is uploaded."),
    _s("policy_client_conduct_url", GROUP_PRESENTATION, "Client code of conduct URL",
       help="Linked from the consent checkbox on the public forms."),
    _s("policy_mentor_ethics_url", GROUP_PRESENTATION, "Mentor code of ethics URL",
       help="The volunteer form's Code of Conduct link — a different document."),
    _s("policy_terms_url", GROUP_PRESENTATION, "Terms of use URL"),
    _s("policy_privacy_url", GROUP_PRESENTATION, "Privacy policy URL"),
    _s("chapter_tokens_url", GROUP_WEBSITE, "Chapter design-token override",
       help="URL of a stylesheet redefining --cbm-* custom properties on :root. "
            "Loaded after the base tokens; custom properties only, never selectors."),
    _s("env_label", GROUP_PRESENTATION, "Environment label",
       help="Overrides the auto-derived Production/Test/Dev wording in the footer."),
    _s("docs_site_url", GROUP_PRESENTATION, "Documentation site"),
    _s("app_base_url", GROUP_PRESENTATION, "This app's public URL",
       help="Used for deep links in alert emails and the digest."),
    _s("events_public_base_url", GROUP_PRESENTATION, "Public event page base",
       help="Empty means this app's own /webinars/, derived from the public URL "
            "above — which is almost always what you want."),
    _s("events_cache_seconds", GROUP_PRESENTATION, "Public read cache", kind="int", unit="s"),
    # The public programme page's chrome. All six were shipped in v0.222.0 and
    # v0.223.0 WITHOUT being registered here, so they landed in the catch-all
    # group and were read-only — a page's whole visible wording editable only by
    # an overlay edit, which is exactly what the 2026-08-28 ruling forbids.
    _s("organization_website_url", GROUP_WEBSITE, "Organisation website",
       help="The public site. Every /webinars/ page links back to it, and it is "
            "the base the menu below resolves its paths against."),
    _s("organization_site_nav", GROUP_WEBSITE, "Website menu",
       help="Reproduced across the top of the public pages so a visitor is not "
            "stranded. \"Label|path\" pairs, comma separated; a leading / is "
            "resolved against the website above. Empty renders no menu."),
    _s("events_hero_tagline", GROUP_PRESENTATION, "Programme page tagline",
       help="The line under the heading on /webinars/. Empty removes it."),
    _s("events_hero_pillars", GROUP_PRESENTATION, "Programme page pillars",
       help="The short third line in the hero. Empty removes it."),
    _s("events_default_graphic_url", GROUP_PRESENTATION, "Default event graphic",
       help="A publicly-hosted image for events with no picture of their own. "
            "Last fallback only — an event's own graphic wins, and a recording's "
            "video thumbnail wins over this. Mainly fixes the empty social-share "
            "card an image-less event otherwise has. Empty means no image."),
    _s("events_hero_band", GROUP_PRESENTATION, "Programme page band",
       help="The gold strapline under the hero. Empty removes it."),
    _s("events_contact_email", GROUP_PRESENTATION, "Programme contact address",
       help="Who the \"Interested in Presenting or Hosting?\" panel writes to. "
            "Empty falls back to the shared mailbox; with both empty the panel "
            "carries no address rather than a dead link."),

    # --- Website (prds/chapter-website-plan.md, piece A) -------------------
    # What the Association's chapter connector reads from /api/website/settings.
    # The name, acronym, postal address, logo address, website address, menu
    # and token override above are part of this group too (decision 4.2).
    _s("website_origins", GROUP_WEBSITE, "Chapter website addresses", kind="csv",
       help="The chapter website's own addresses, such as https://example.org — "
            "scheme and host only, comma separated. Only these may fetch the "
            "website's content from a visitor's browser (the mentor search). "
            "Separate from Allowed origins, which covers every address of this app."),
    _s("website_color_base", GROUP_WEBSITE, "Colour — background",
       help="The page background. A colour written #RRGGBB."),
    _s("website_color_contrast", GROUP_WEBSITE, "Colour — text",
       help="Body text and headings. A colour written #RRGGBB."),
    _s("website_color_accent_1", GROUP_WEBSITE, "Colour — main brand",
       help="Links, headings and the main buttons. A colour written #RRGGBB."),
    _s("website_color_accent_2", GROUP_WEBSITE, "Colour — light brand tint",
       help="A pale version of the main brand colour, for soft panels. #RRGGBB."),
    _s("website_color_accent_3", GROUP_WEBSITE, "Colour — highlight",
       help="The second brand colour: call-to-action buttons and key accents. #RRGGBB."),
    _s("website_color_accent_4", GROUP_WEBSITE, "Colour — muted text",
       help="Secondary text such as captions and dates. #RRGGBB."),
    _s("website_color_accent_5", GROUP_WEBSITE, "Colour — light section background",
       help="Bands and cards that sit on the page background. #RRGGBB."),
    _s("website_color_accent_6", GROUP_WEBSITE, "Colour — borders",
       help="Lines and borders. #RRGGBB."),
    _s("website_font_heading", GROUP_WEBSITE, "Font — headings",
       help="A font list as a stylesheet writes it, such as Georgia, serif. "
            "Letters, digits, spaces, commas, quotes and hyphens only."),
    _s("website_font_body", GROUP_WEBSITE, "Font — body text",
       help="As for the heading font."),
    _s("chapter_email", GROUP_WEBSITE, "Chapter contact email",
       help="The one public contact address the website shows, in its footer and "
            "on its Contact page."),
    _s("chapter_phone", GROUP_WEBSITE, "Chapter telephone"),
    _s("chapter_ein", GROUP_WEBSITE, "Employer identification number",
       help="Shown in the website footer beside the 501(c)(3) statement. "
            "Written 12-3456789."),
    _s("chapter_payment_url", GROUP_WEBSITE, "Donation payment page",
       help="The hosted payment page the website's Donate button opens, such as "
            "a Stripe Payment Link. An https address."),
    _s("chapter_social_links", GROUP_WEBSITE, "Social media addresses", kind="csv",
       help="\"Label|https://…\" pairs, comma separated, such as "
            "LinkedIn|https://www.linkedin.com/company/example."),
    _s("website_cache_seconds", GROUP_WEBSITE, "Key page refresh", kind="int", unit="s",
       help="How long the key pages keep what they read from the CRM. A change in "
            "the CRM reaches the website within this time plus the website's own "
            "few minutes. The mentor search uses the kept list, never the CRM."),
    _s("website_page_mentors", GROUP_WEBSITE, "Key page — Find a Mentor", kind="bool",
       help="Shows the mentor directory and profiles on the website, with their "
            "menu entry. A mentor appears when Active and Public profile is ticked."),
    _s("website_page_events", GROUP_WEBSITE, "Key page — Workshops and Events", kind="bool",
       help="The upcoming published events, by the same rule as the public programme page."),
    _s("website_page_recordings", GROUP_WEBSITE, "Key page — Recordings", kind="bool",
       help="The published recorded webinars."),
    _s("website_page_partners", GROUP_WEBSITE, "Key page — Our Partners", kind="bool",
       help="Refused: partners on the website is a feature request owed to the "
            "Association's committee."),
    _s("website_page_sponsors", GROUP_WEBSITE, "Key page — Our Sponsors", kind="bool",
       help="Refused: sponsors on the website is a feature request owed to the "
            "Association's committee."),
    _s("website_page_stories", GROUP_WEBSITE, "Key page — Client Stories", kind="bool",
       help="Refused: client stories need recorded consent, a feature request "
            "owed to the Association's committee."),

    # Integration credentials. A wrong one disables that integration and nothing
    # else, so the pre-flight check is the whole safety net. None is ever shown
    # back once set.
    _s("google_service_account_json", GROUP_INTEGRATIONS, "Google service account",
       component="both",
       help="The key behind Gmail, Calendar, Drive and Directory. Checked for shape "
            "before it is stored; whether domain-wide delegation has been granted "
            "cannot be seen from here."),
    _s("anthropic_api_key", GROUP_INTEGRATIONS, "Anthropic API key", component="worker",
       help="AI conversation summaries only."),
    _s("zoom_account_id", GROUP_INTEGRATIONS, "Zoom account ID", component="both"),
    _s("zoom_client_id", GROUP_INTEGRATIONS, "Zoom client ID", component="both"),
    _s("zoom_client_secret", GROUP_INTEGRATIONS, "Zoom client secret", component="both",
       help="Public webinars only. Mentor sessions never use the {{abbr}} Zoom account."),
    _s("fathom_api_key", GROUP_INTEGRATIONS, "Fathom API key", component="worker"),
    _s("mailing_client_id", GROUP_INTEGRATIONS, "Mailing service client ID", component="both",
       help="The developer application's API key (Constant Contact). One application "
            "per deployment, created by the account's own user — it is private to them."),
    _s("mailing_client_secret", GROUP_INTEGRATIONS, "Mailing service client secret",
       component="both",
       help="Shown once by the vendor when generated. Its check is the Connect step on "
            "the Readiness tab — nothing can probe it without a user authorising."),
    _s("mailing_list_name", GROUP_INTEGRATIONS, "Mailing list name", component="worker",
       help="The list the push maintains; found by name, created when absent."),
    _s("mailing_push_seconds", GROUP_INTEGRATIONS, "Mailing push interval", kind="int",
       unit="s", component="worker", help="0 disables the push and leaves the pull."),
    _s("mailing_pull_seconds", GROUP_INTEGRATIONS, "Mailing pull interval", kind="int",
       unit="s", component="worker", help="0 disables the pull of unsubscribes."),
    _s("mailing_base_url", GROUP_INTEGRATIONS, "Mailing service API base URL",
       component="both", help="Override only for a vendor change."),
    _s("youtube_api_key", GROUP_INTEGRATIONS, "YouTube API key",
       help="The recorded-webinar library."),

    # --- Restart required --------------------------------------------------
    # Every one of these is read while the process starts — routers are mounted,
    # middleware is built and logging is configured before the app serves its
    # first request. Saving one here stores it; the running process keeps the
    # value it booted with until it restarts, and the page shows both.
    _s("analytics_enabled", GROUP_RESTART, "Analytics", kind="bool", restart=True,
       component="both",
       help="Mounts the /analytics routes and its portal tile. The routes do not "
            "exist until the process restarts, so switching this on mid-run would "
            "otherwise produce a tile leading nowhere."),
    _s("events_enabled", GROUP_RESTART, "Events & Webinars", kind="bool", restart=True,
       component="both",
       help="Mounts the /events routes and its portal tile."),
    _s("events_public_api", GROUP_RESTART, "Public events API", kind="bool", restart=True,
       help="The unauthenticated read API the website's programme reads. "
            "Publishing is still gated per event."),
    _s("assignments_enabled", GROUP_RESTART, "Staff applications", kind="bool",
       restart=True, component="both",
       help="The whole staff stack — portal, Client Administration and the rest. "
            "Turning this off leaves only the public intake forms."),
    _s("log_level", GROUP_RESTART, "Log level", kind="choice", restart=True,
       component="both", choices=("DEBUG", "INFO", "WARNING", "ERROR"),
       help="Applied once by logging setup as the process starts."),
    _s("intake_rate_limit", GROUP_RESTART, "Intake rate limit", kind="int",
       restart=True, unit="requests",
       help="Built into the middleware at startup. Submissions allowed per window "
            "from one address."),
    _s("intake_rate_window_seconds", GROUP_RESTART, "Intake rate window", kind="int",
       restart=True, unit="s", help="The window the limit above is counted over."),
    _s("intake_max_body_mb", GROUP_RESTART, "Maximum submission size", kind="int",
       restart=True, unit="MB",
       help="Built into the middleware at startup. Chiefly the volunteer form's "
            "optional resume."),
    _s("crm_config_refresh_seconds", GROUP_RESTART, "CRM configuration check",
       kind="int", restart=True, unit="s",
       help="How often to re-read the CRM's configuration version for the status "
            "page. 0 switches it off. The background task is created once at "
            "startup, so starting or stopping it needs a restart. /healthz always "
            "serves the cached answer and never waits on the CRM."),
    # --- CRM connection ----------------------------------------------------
    # Each of these is tried against the live CRM before it is stored: a key
    # the CRM rejects, or an address that is not a CRM this application can
    # use, is refused with the CRM's own error rather than accepted and left to
    # fail on every later call.
    _s("espo_base_url", GROUP_CONNECTION, "CRM address",
       help="Which EspoCRM this deployment reads and writes. Checked before it is "
            "saved: the address must answer AND hold this application's entities, so "
            "pointing at a stranger's EspoCRM is refused rather than accepted."),
    _s("espo_api_key", GROUP_CONNECTION, "CRM API key",
       help="The org-wide key. Tried against the CRM before it is stored; a key the "
            "CRM rejects is refused. Never shown back once set."),
    _s("espo_dry_run", GROUP_CONNECTION, "Dry run (no CRM writes)", kind="bool",
       component="both",
       help="On, nothing is ever written to the CRM and submissions are logged only. "
            "This is how the dev deployment runs."),
    _s("espo_provision_username", GROUP_CONNECTION, "Provisioning admin username",
       help="The admin service account used for the few operations EspoCRM reserves "
            "for admins — creating mentor logins, team membership."),
    _s("espo_provision_password", GROUP_CONNECTION, "Provisioning admin password",
       help="Never shown back once set."),

    # --- Access & security -------------------------------------------------
    # Everything here can lock somebody out, which no probe can detect — the app
    # would be working perfectly and simply refusing to let anyone in. They
    # apply with a countdown and revert themselves unless confirmed.
    _s("session_secret", GROUP_SECURITY, "Session signing secret",
       help="Signs every session cookie. Changing it signs EVERYONE out, including "
            "you — so confirm you can still sign in, or it reverts itself."),
    _s("session_cookie_secure", GROUP_SECURITY, "HTTPS-only session cookie",
       kind="bool",
       help="On is correct for any real deployment. On over plain http, no one can "
            "sign in at all — hence the countdown."),
    _s("allowed_origins", GROUP_SECURITY, "Allowed origins", kind="csv",
       help="Only matters if a separate frontend origin is ever introduced; the "
            "wizard posts to its own origin."),
    _s("setup_enabled", GROUP_SECURITY, "This Settings page", kind="bool",
       help="Switching this off hides the page you are reading. It reverts itself "
            "unless confirmed, because otherwise recovery would need a redeploy."),
    _s("settings_overrides", GROUP_SECURITY, "Settings overrides", kind="bool",
       component="both",
       help="The break-glass. Off, every stored setting stops applying and the "
            "deployment's own values take over — including the one that switched "
            "this off, so it could never switch itself back on. Reverts unless "
            "confirmed."),
    _s("setup_peer_url", GROUP_SECURITY, "Peer deployment URL",
       help="The other environment, for the comparison on the Environment diff tab."),
    _s("setup_peer_token", GROUP_SECURITY, "Peer deployment token",
       help="Authorises that comparison. No secret value ever crosses the wire."),
    _s("sandbox_reset_hour", GROUP_SECURITY, "Sandbox wipe hour", kind="int",
       component="worker",
       help="When the nightly wipe runs, in the timezone below. Meaningless "
            "unless the wipe itself is switched on."),
    _s("sandbox_reset_tz", GROUP_SECURITY, "Sandbox wipe timezone",
       component="worker",
       help="The timezone the hour above is read in."),
    _s("sandbox_nightly_reset", GROUP_SECURITY, "Nightly sandbox wipe", kind="bool",
       component="worker",
       help="Worker-side. Empties this deployment's own submission queue and "
            "document index every night. Correct on the training sandbox, ruinous "
            "anywhere else — which is why it is checked before it is stored."),

    # --- Foundations -------------------------------------------------------
    _s("database_url", GROUP_FOUNDATIONS, "Database", readonly=True,
       help="Cannot be changed here, and this is a logical impossibility rather "
            "than caution: the stored settings live INSIDE this database, so a "
            "setting that moved the app elsewhere would be left behind in the "
            "database being abandoned, and the app would read its configuration "
            "from the new one and move straight back. Change it in the deployment "
            "configuration."),
    _s("app_encryption_key", GROUP_FOUNDATIONS, "Encryption key", readonly=True,
       help="Protects the secrets stored on this page and the Google configuration. "
            "Rotating it makes every one of them permanently unreadable — data "
            "loss, which no verification can undo. Rotation needs a re-encryption "
            "migration, not a text box."),

    # In Foundations, NOT "Restart required", although it is read once at
    # startup. That group means "change it here and it takes effect on the next
    # restart", and this cannot be changed here at all — a restart will never
    # alter it, only rebuilding the image will. Sitting among nine editable
    # settings implied otherwise, which is exactly the confusion the group was
    # created to remove.
    _s("release_tag", GROUP_FOUNDATIONS, "Release tag", readonly=True,
       help="Which release this container was built from — stamped into the image "
            "at build time and supplied by the deployment's own configuration. "
            "Read-only on purpose: a stored value would survive a restart and make "
            "this deployment misreport which build it is running. Empty means an "
            "untagged build."),
)

# --- which settings live on an integration's sub-tab -------------------------
#
# The mapping Doug approved on 11-13-26 (prds/integrations-tab-plan.md, change
# log 0.5). The rule: a credential or connection setting; a feature switch for
# a feature that cannot work without that integration and uses no other; a
# setting that only tunes that integration's calls. A switch and the settings
# that only serve it stay together. Everything else stays on the Settings tab.
# Order within a sub-tab follows this table; the "in use" setting comes first.
INTEGRATION_TAGS: dict[str, tuple[str, str]] = {
    # EspoCRM — no "in use" setting: always in use.
    "espo_base_url": ("espocrm", ""),
    "espo_api_key": ("espocrm", ""),
    "espo_dry_run": ("espocrm", ""),
    "espo_provision_username": ("espocrm", ""),
    "espo_provision_password": ("espocrm", ""),
    "crm_metadata_cache_seconds": ("espocrm", ""),
    # Google Workspace
    "google_workspace_in_use": ("google_workspace", ""),
    "google_service_account_json": ("google_workspace", "credentials"),
    "google_delegated_admin": ("google_workspace", "credentials"),
    "gdrive_docs": ("google_workspace", "drive"),
    "gdrive_identity": ("google_workspace", "drive"),
    "gdrive_shared_drive_id": ("google_workspace", "drive"),
    "gdrive_entity_labels": ("google_workspace", "drive"),
    "gdrive_doc_types": ("google_workspace", "drive"),
    "gdrive_max_file_mb": ("google_workspace", "drive"),
    "gdrive_reconcile_seconds": ("google_workspace", "drive"),
    "gcal_events": ("google_workspace", "calendar"),
    "meet_transcripts": ("google_workspace", "meet"),
    "meet_transcripts_poll_seconds": ("google_workspace", "meet"),
    "transcript_give_up_days": ("google_workspace", "meet"),
    "gmail_sync": ("google_workspace", "gmail"),
    "gmail_resync": ("google_workspace", "gmail"),
    "gmail_sync_seconds": ("google_workspace", "gmail"),
    "gmail_backfill": ("google_workspace", "gmail"),
    "gmail_dead_letter_passes": ("google_workspace", "gmail"),
    "ops_mailbox": ("google_workspace", "gmail"),
    "ops_mailbox_name": ("google_workspace", "gmail"),
    "ops_inbound_seconds": ("google_workspace", "gmail"),
    "ops_inbound_window_days": ("google_workspace", "gmail"),
    "google_directory_check": ("google_workspace", "accounts"),
    "google_create_mailbox": ("google_workspace", "accounts"),
    "google_members_group": ("google_workspace", "accounts"),
    # Zoom
    "zoom_in_use": ("zoom", ""),
    "zoom_events": ("zoom", ""),
    "zoom_account_id": ("zoom", ""),
    "zoom_client_id": ("zoom", ""),
    "zoom_client_secret": ("zoom", ""),
    "zoom_host_email": ("zoom", ""),
    "zoom_base_url": ("zoom", ""),
    "events_attendance_seconds": ("zoom", ""),
    "events_attendance_grace_minutes": ("zoom", ""),
    "events_attendance_give_up_hours": ("zoom", ""),
    # Fathom
    "fathom_in_use": ("fathom", ""),
    "fathom_transcripts": ("fathom", ""),
    "fathom_api_key": ("fathom", ""),
    "fathom_base_url": ("fathom", ""),
    # Constant Contact
    "constant_contact_in_use": ("constant_contact", ""),
    "mailing_sync": ("constant_contact", ""),
    "mailing_client_id": ("constant_contact", ""),
    "mailing_client_secret": ("constant_contact", ""),
    "mailing_list_name": ("constant_contact", ""),
    "mailing_push_seconds": ("constant_contact", ""),
    "mailing_pull_seconds": ("constant_contact", ""),
    "mailing_base_url": ("constant_contact", ""),
    # Lob
    "lob_in_use": ("lob", ""),
    "postal_provider": ("lob", ""),
    "postal_api_key": ("lob", ""),
    "postal_webhook_secret": ("lob", ""),
    "postal_test_mode": ("lob", ""),
    "postal_unit_cost": ("lob", ""),
    "postal_currency": ("lob", ""),
    # Twilio
    "twilio_in_use": ("twilio", ""),
    "sms_provider": ("twilio", ""),
    "sms_account_sid": ("twilio", ""),
    "sms_auth_token": ("twilio", ""),
    "sms_from_number": ("twilio", ""),
    "sms_send_hours": ("twilio", ""),
    "sms_timezone": ("twilio", ""),
    # Anthropic — AI research moves whole, its budget and caps included.
    "anthropic_in_use": ("anthropic", ""),
    "anthropic_api_key": ("anthropic", ""),
    "summary_model": ("anthropic", ""),
    "comms_ai_summary": ("anthropic", ""),
    "enrichment_ai": ("anthropic", ""),
    "enrichment_ai_model": ("anthropic", ""),
    "enrichment_ai_fallback": ("anthropic", ""),
    "enrichment_ai_max_searches": ("anthropic", ""),
    "enrichment_ai_record_cap": ("anthropic", ""),
    "enrichment_ai_max_records": ("anthropic", ""),
    "enrichment_ai_poll_seconds": ("anthropic", ""),
    "enrichment_monthly_budget": ("anthropic", ""),
    # YouTube
    "youtube_in_use": ("youtube", ""),
    "youtube_api_key": ("youtube", ""),
    "youtube_playlist_id": ("youtube", ""),
}

SETTINGS = tuple(
    replace(s, integration=INTEGRATION_TAGS[s.key][0], section=INTEGRATION_TAGS[s.key][1])
    if s.key in INTEGRATION_TAGS else s
    for s in SETTINGS
)

BY_KEY: dict[str, SettingSpec] = {s.key: s for s in SETTINGS}


# --- the Website group's own rules (prds/chapter-website-plan.md) ------------

#: Each key page's switch, by the page key the chapter connector uses.
WEBSITE_PAGE_SWITCHES: dict[str, str] = {
    "mentors": "website_page_mentors",
    "events": "website_page_events",
    "recordings": "website_page_recordings",
    "partners": "website_page_partners",
    "sponsors": "website_page_sponsors",
    "stories": "website_page_stories",
}

#: The key pages this release can serve. WT-10: System Settings refuses to
#: switch on any other, and the website is told it is off whatever is stored,
#: so a menu never leads to "page not found". Partners, sponsors and stories
#: are committee feature requests.
WEBSITE_PAGES_SERVED: frozenset[str] = frozenset({"mentors", "events", "recordings"})

_WEBSITE_PAGE_REFUSALS: dict[str, str] = {
    "partners": "partners on the website is a feature request owed to the Association's committee",
    "sponsors": "sponsors on the website is a feature request owed to the Association's committee",
    "stories": "client stories need recorded consent, a feature request owed to the Association's committee",
}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FONT = re.compile(r"""^[A-Za-z0-9 ,'"\-]{1,200}$""")
_EIN = re.compile(r"^\d{2}-\d{7}$")
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_ORIGIN = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?/?$")
_TRUE = {"1", "true", "yes", "on"}


def website_value_problem(key: str, value: str) -> Optional[str]:
    """Why ``value`` is not acceptable for a Website key, or None.

    Used on save (``settings_store.validate_value``) and again when the
    settings are served, so a bad value in the deployment's own configuration
    is dropped rather than handed to the website. Never raises."""
    v = (value or "").strip()
    page = next((p for p, k in WEBSITE_PAGE_SWITCHES.items() if k == key), None)
    if page is not None:
        if v.lower() in _TRUE and page not in WEBSITE_PAGES_SERVED:
            return _WEBSITE_PAGE_REFUSALS.get(
                page, "this release of the applications cannot serve that page yet")
        return None
    if not v:
        return None
    if key.startswith("website_color_"):
        return None if _HEX.match(v) else "a colour is written #RRGGBB, such as #173B60"
    if key.startswith("website_font_"):
        return None if _FONT.match(v) else (
            "a font list may hold letters, digits, spaces, commas, quotes and hyphens only")
    if key == "chapter_ein":
        return None if _EIN.match(v) else "an employer identification number is written 12-3456789"
    if key == "chapter_email":
        return None if _EMAIL.match(v) else "that is not an email address"
    if key == "chapter_payment_url":
        return None if v.startswith("https://") and " " not in v else "the payment page must be an https address"
    if key == "website_origins":
        bad = [o for o in (x.strip() for x in v.split(",")) if o and not _ORIGIN.match(o)]
        return f"not a website address (scheme and host only): {', '.join(bad)}" if bad else None
    if key == "chapter_social_links":
        for pair in (x.strip() for x in v.split(",")):
            if not pair:
                continue
            label, _, url = pair.partition("|")
            if not label.strip() or not url.strip().startswith("https://"):
                return f"each entry is Label|https://…, and this one is not: {pair}"
        return None
    return None


def spec_for(key: str) -> Optional[SettingSpec]:
    return BY_KEY.get(key)


def is_editable(key: str) -> bool:
    """Editable = curated AND not on the denylist. Both conditions, always."""
    return key in BY_KEY and key not in DENYLIST


def is_secret(key: str) -> bool:
    return key in SECRET_KEYS


def is_readonly(key: str) -> bool:
    spec = BY_KEY.get(key)
    return bool(spec and spec.readonly) or key in DENYLIST


# Sanity: a curated setting that is also denylisted would render an editable
# control the server always refuses. A spec marked `readonly` is the exception —
# it is curated precisely so the value is VISIBLE and explained rather than
# hidden, and it renders no control at all.
_conflict = sorted(
    k for k in (set(BY_KEY) & DENYLIST) if not BY_KEY[k].readonly
)
if _conflict:  # pragma: no cover — a coding error, not a runtime condition
    raise RuntimeError(f"settings registry: curated but denylisted: {_conflict}")
