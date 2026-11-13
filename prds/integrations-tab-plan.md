# Integrations tab — System Settings plan

Last Updated: 11-13-26 12:12 · Revision 0.11

This is the design record for a new top-level **Integrations** tab on the System
Settings page (`/setup`). It holds Doug's rulings, the contents of each
sub-tab, the diagnosis agent, the storage, and the build phases with their
stopping points. Once Doug approves it, the build orchestrator and the per-phase
build prompts are written from this file. Nothing has been built yet.

## 1. Terms

- **Integration**: one outside service that this application calls with its
  own credentials, for example Zoom or Google Workspace. Each integration has
  one sub-tab.
- **Sub-tab**: a tab inside the Integrations tab, one per integration.
- **Integration test**: the checks that run when someone clicks
  **Test Integration**, or when the nightly run starts. An integration test
  proves the integration works from end to end, not only that a key is set.
- **Integration facts**: what the integration test reports about the connected
  service, for example the installed EspoCRM version, the Zoom account, or the
  Google permissions granted.
- **Setup checklist**: the ordered setup steps for one integration, shown on its
  sub-tab and read from the chapter deployment guide's step files.
- **Automatic step**: a setup checklist step that the application can check for
  itself, so it ticks or clears on its own.
- **Manual step**: a setup checklist step done outside this application, ticked
  by an administrator.
- **Diagnosis agent**: the Claude model, called through the Claude API, that
  reads a failed integration test and writes a fix plan.
- **Setup assistant**: the same Claude model, asked to set an integration up
  rather than to diagnose it. It writes a setup plan.
- **Setup plan**: the setup assistant's numbered list of steps that should take
  the integration from its current state to a passing integration test.
- **Coded action**: a step the application can carry out against an outside
  service, written and tested in code, for example "create the shared drive".
  The setup assistant can only choose from the list of coded actions; it never
  writes its own call to an outside service.
- **Fix plan**: the diagnosis agent's numbered list of steps that should make the
  integration test pass. It has setting changes the application can apply,
  manual steps for a person, and a final re-test.

## 2. Rulings (Doug, 11-12-26)

| # | Ruling |
|---|---|
| I1 | Integrations is a top-level tab of System Settings, with one sub-tab per integration. |
| I2 | It is built on the settings store that exists today (`app_setting`, the checked save path, encryption of secrets, the History tab). There is no new integration record and only one account per integration. |
| I3 | Google is one sub-tab. Its shared credentials come first, then one section for each Google feature, and each section can be collapsed. |
| I4 | Each sub-tab carries a setup checklist read from the deployment guide's step files. Automatic steps tick themselves. Manual steps are ticked by hand. |
| I5 | Each integration has a setting saying whether this chapter uses it. An integration marked not in use keeps its sub-tab, labelled "Not used by this chapter", with its checklist folded and its warnings left out of readiness. The application refuses that mark while any feature of the integration is switched on. |
| I6 | Every sub-tab has a **Test Integration** button. It runs every check needed to prove the integration works, and it reports the integration facts. |
| I7 | When an integration test fails, the diagnosis agent can be asked to diagnose it. The diagnosis agent writes a fix plan. If the administrator approves the fix plan, the fix plan is carried out and the integration test runs again. |
| I8 | The integration tests also run every night in the worker, for each integration in use. A failure sends the existing alert email with a link to the sub-tab. The diagnosis agent never runs on its own. |
| I9 | The diagnosis agent may search and read the vendor's own documentation on the web, but only on an allowed list of sites for each integration. |
| I10 | The application, not the diagnosis agent, carries out an approved fix plan, step by step. If a step fails, the fix plan stops. |
| I11 | A setup assistant extends the diagnosis agent to setup (option B). It writes a setup plan of setting changes, manual steps and coded actions. It is never given broad administrator credentials for a vendor. |
| I12 | A setup plan is carried out one step at a time, and every step, automatic or manual, waits for the administrator's confirmation. A fix plan, once approved, runs its automatic steps straight through and waits only at manual steps. |
| I13 | The application also refuses switching a feature on while its integration is marked not in use. The message says to mark the integration in use first. |

### Decisions made under those rulings (announced, not separately ruled)

- EspoCRM has its own sub-tab: the CRM address, the API key, dry run and the
  provisioning account. Those settings keep their checked save and their
  automatic undo.
- Each setting appears in one place only. An integration's settings and its on/off
  switches move to its sub-tab. The "Integrations" group on the Settings tab is
  removed. Settings that call no outside service stay on the Settings tab:
  alert recipients, digest hours, the internal domains list and the like.
- The integration test runs only when someone clicks it, or in the nightly run.
  Opening the page never calls an outside service.
- Each sub-tab opens with a status line, for example
  "Zoom: on · credentials set · last test passed 11-12-26 23:30". The Feature
  readiness tab keeps its overview of everything and links to the matching
  sub-tab.
- Hand ticks are stored for the whole deployment in the application database.
  Every administrator sees the same ticks. Each tick is recorded on the History
  tab with the person who ticked it and the time.
- An automatic step can never be ticked by hand. When its check fails, the box
  stays empty and the reason is shown beside it.
- Approval covers that exact fix plan, as the Operations tab already does: the
  fix plan is fingerprinted, and applying it is refused if it changed after
  approval. A step the fix plan did not contain is never carried out.
- Every change runs as the administrator who approved it, through the checked
  save path. A change that could lock administrators out keeps its 10-minute
  confirm-or-undo countdown. History records the approving administrator with
  the note "applied from a fix plan".
- When an administrator confirms a manual step, the application runs that
  step's check, where one exists, before moving on. A failed check keeps the
  step open, names what is missing, and offers a diagnosis. This applies to
  setup plans and fix plans alike.
- A plan is shown one step at a time, to the Step-by-Step Instructions
  standard: one step open, a confirmed step collapses and the next comes to the
  top of the window, and a progress count is shown.
- The diagnosis agent never carries out a step outside this application. Those
  steps stay as instructions inside the fix plan and wait for a hand tick.
- The diagnosis agent never sees a secret's value. It sees only whether each
  secret is set and when it last changed. A fix that needs a new secret becomes
  a manual step: "paste the new client secret into the Zoom client secret box".
- The diagnosis agent's model is a setting on the Anthropic sub-tab, called
  "Integration agent model", with the default `claude-opus-5-5`. It is separate
  from the transcript summary model.

## 3. The sub-tabs

The sub-tab list is fixed in code. The list below is a proposal, built from the
settings and features in the code today. Each sub-tab has the same five parts,
in this order:

1. **Status line**: in use or not, switched on or off, credentials set,
   and the last integration test result with its time.
2. **Test Integration**: the button, the result of the last integration test as
   one line per check, and the integration facts.
3. **Diagnosis**: present only after a failed integration test. It has a
   "Diagnose with Claude" button, the fix plan, and the Approve and Apply
   buttons.
4. **Setup checklist**: the steps from the deployment guide, with done boxes.
5. **Settings**: the integration's switches and settings, edited as on the
   Settings tab today, through the same checked save path.

| Sub-tab | Settings that move there | Switches that move there | Proposed checks (confirmed during the build) | Proposed integration facts |
|---|---|---|---|---|
| EspoCRM | CRM address, CRM API key, dry run, provisioning username and password | none | Reach the CRM; sign in with the API key; read one record of each of this application's entities; sign in as the provisioning account and confirm it is an administrator; schema contract (`core/schema_contract.py`) | EspoCRM version; the image tag the droplet pins; the API user's name and roles; the number of entities found |
| Google Workspace | Service account, delegated admin, All Members group; Drive, Calendar, Meet and Gmail settings; shared mailbox and its settings | `gdrive_docs`, `gcal_events`, `meet_transcripts`, `gmail_sync`, `ops_mailbox` switch, mentor provisioning | Service account key valid; delegation token for each required scope; each enabled feature's own call: list the shared drive, read the shared mailbox's profile, read a calendar, read the directory | Service account client ID; the scopes granted and missing; the shared drive name; the shared mailbox |
| Zoom | Account ID, client ID, client secret, host, API address | `zoom_events` | Get a token by Server-to-Server OAuth; read the host user; list the host's webinars | Account; host user and plan type; scopes on the token |
| Fathom | API key, API address | `fathom_transcripts` | Call the API with the key; list one meeting | The account the key belongs to |
| Constant Contact | Client ID, client secret, list name, push and pull intervals, API address; the Connect and Disconnect buttons | `mailing_sync` | Connection row present; refresh the token; read the account; find the named list | Account name; list and member count; when the token expires |
| Lob | Mail vendor, API key, webhook secret, test mode, unit cost, currency | the postcard feature switch | Call the API with the key; confirm test or live mode | Test or live mode; account |
| Twilio | Texting service, account SID, auth token, sender number, hours, time zone | the texting feature switch | Read the account; read the sender number and confirm it can send texts | Account status; sender number capabilities |
| Anthropic | API key, summary model, integration agent model | `enrichment_ai`, `enrichment_free_pass` | List the models; confirm each configured model exists | The models available; whether each configured model is available |
| YouTube | API key, playlist IDs | none | Read each configured playlist | Playlist titles and video counts |

## 4. The setup checklist

- The steps stay written in one place, the deployment guide step files
  (`prds/chapter-network/deployment-guide/steps/stage-*.yaml`). The page and the
  guide cannot disagree.
- Each step that belongs to an integration gains two optional keys:
  - `integration:`, which names the sub-tab, for example `zoom`;
  - `check:`, which names an automatic check in code, for example
    `setting_set:zoom_client_secret`, `switch_on:zoom_events`,
    `test_passed:zoom` or `crm_field:CEvent.zoomWebinarId`.
  A step without `check:` is a manual step.
- The step's `produces:` key, which the files already carry, is the natural
  source for `setting_set` checks.
- The first step of every checklist is "Decide whether this chapter uses
  <integration>" (ruling I5).
- `scripts/render_deployment_guide.py --check` must still pass. The new keys do
  not change the rendered guide.
- Lob, Twilio, Anthropic and YouTube have no written setup steps yet. Phase 4
  writes them into the step files.

## 5. The nightly integration test

- The nightly integration test runs in the **worker** at the hour set by a new
  setting, default 06:00 in the chapter's time zone. It covers each integration
  that is in use and has at least one feature switched on.
- A failure sends one alert through `core/monitoring.send_alert`. The alert
  names the integration and the failed check, and links to the sub-tab. The
  alert is not repeated each night for an unchanged failure, using the same
  cool-down pattern `run_alert_check` uses.
- Every integration test, nightly or manual, is stored with its checks and its
  integration facts, so the status line can show the last result.
- On crm-test the application database is reset nightly, so the history of
  integration tests there is one day long. That is expected.

## 6. The diagnosis agent

### 6.1 How it is called

- It uses the Anthropic Python SDK the application already depends on, and the
  existing `anthropic_api_key` setting.
- It is built on the SDK's Tool Runner: the diagnosis agent calls read-only tools
  that this application defines, and the server-side web search and web fetch
  tools.
- Model: the "Integration agent model" setting, default `claude-opus-5-5`, with
  adaptive thinking, effort `high`, streaming, and the server-side refusal
  fallback switched on.
- It runs only when an administrator clicks "Diagnose with Claude". One
  diagnosis per integration at a time. The token use of each diagnosis is
  stored with the fix plan.

### 6.2 What it may read

The diagnosis agent may read only through these read-only tools:

- the failed integration test, every check with its error;
- the integration's settings, with each secret shown only as set or not set
  and the time it last changed;
- the integration's readiness rows;
- the setup checklist and its tick state;
- the integration's runbook from this repository;
- recent errors logged for the integration (see § 6.6, an open point);
- web search and web fetch, restricted to the integration's allowed list of
  documentation sites (ruling I9). Proposed lists:
  - EspoCRM: `docs.espocrm.com`
  - Google Workspace: `developers.google.com`, `support.google.com`
  - Zoom: `developers.zoom.us`
  - Constant Contact: `developer.constantcontact.com`
  - Lob: `docs.lob.com`
  - Twilio: `www.twilio.com`
  - Fathom: `developers.fathom.ai`
  - Anthropic: `platform.claude.com`, `docs.claude.com`
  - YouTube: `developers.google.com`

Everything the diagnosis agent reads from a check error or a web page is treated
as data, never as instructions. The system prompt says so.

### 6.3 What it produces

The diagnosis agent finishes by calling one tool, `submit_fix_plan`, with a
strict schema:

- a plain-language diagnosis: what failed and why, with its confidence stated;
- numbered steps, each of exactly one kind:
  - **setting change**: a key and the new value. It is refused if the key is
    a secret or is on the denylist;
  - **manual step**: written to the Step-by-Step Instructions standard, with
    where, the action, the value to copy, the expected result and what to do if
    it fails;
- a final **re-test**, always present.

### 6.4 Approval and carrying out the fix plan

- The fix plan is shown in full and fingerprinted.
- **Approve and apply** (ruling I7) carries out the steps in order:
  - a setting change is applied through the checked save path as the approving
    administrator;
  - a manual step pauses the fix plan until it is ticked;
  - the re-test runs the integration test.
- **The application carries out the steps, not the diagnosis agent** (ruling
  I10). It is what makes "approval covers that
  exact plan" enforceable: nothing can run that the administrator did not see.
  The cost is that the fix plan cannot adapt halfway through. If a step fails,
  the fix plan stops, and the administrator can ask for a new diagnosis.
- A setting change that fails its pre-flight check stops the fix plan at that
  step, with the check's own error shown.

### 6.5 The setup assistant (rulings I11, I12)

- "Set up with Claude" appears on a sub-tab whose setup checklist still has
  open steps. It uses the same model, read-only tools, allowed sites and
  approval machinery as the diagnosis agent.
- It reads the setup checklist, the values already entered in the setup fields
  and the vendor documentation, and writes a setup plan with the
  `submit_setup_plan` tool. A setup plan has a third step kind beside setting
  change and manual step: **coded action**, named from the list in code with
  its inputs.
- Every manual step arrives with the chapter's own values filled in, for
  example the delegation grant with the exact client ID and scope list.
- Steps that stay manual because the vendor offers no API, or would need
  administrator credentials this application must not hold: creating the Google
  Cloud project and service account, granting domain-wide delegation, creating
  the Zoom Server-to-Server app, and creating the Constant Contact developer app.
  (Inferred from vendor knowledge; each is confirmed during phase 7.)
- First coded actions, proposed: create the Google shared drive and its folder
  scheme; apply a feature's CRM fields and relationships (wrapping the existing
  `scripts/migrate_*_schema.py`); look up the Twilio sender number; confirm the
  Zoom host user. The list grows one tested action at a time.
- Every coded action is idempotent and has a dry run, as the Operations tab's
  jobs do, and runs as the confirming administrator where the CRM is involved.

### 6.6 Open point: recent errors

The web process cannot read the worker's log. Proposal: a small table,
`integration_event`, that both processes write an integration's errors to, kept
for 14 days. The diagnosis agent reads it through its read-only tool. To be
settled in phase 6.

## 7. Storage

New tables, added by Alembic migrations:

- `integration_test_run`: the integration, manual or nightly, the start and
  finish times, the outcome, the checks, the integration facts, and who ran it.
- `integration_checklist_tick`: the integration, the step ID, who ticked it and
  when.
- `integration_fix_plan`: the integration, its integration test, the fix plan,
  the fingerprint, the status (proposed, approved, applying, applied, stopped,
  superseded), the approving administrator, and token use.
- `integration_event`: see § 6.6.

The `integration_fix_plan` table also holds setup plans, with a `kind` column
(fix or setup) and the confirmation of each step.

The "in use" settings are ordinary settings, one for each integration, in the
settings registry. Each setting gains an `integration=` field, which places
it on its sub-tab.

## 8. Build phases and stopping points

The whole tab is built dark behind a new switch, `INTEGRATIONS_TAB`, default
off. While the switch is off, the Settings tab is exactly as it is today. Each
phase ends at a **stopping point**: the work pauses for Doug's go-ahead.

1. **The framework.** The integration registry, the `integration=` field on
   settings, the "in use" settings and their guard, the sub-tab shell with the
   status line and the settings section, the switch, and moving the settings.
   **Stop.**
2. **The integration test, three integrations.** The integration test
   framework, its table, the button, the result and integration facts display,
   for EspoCRM, Google Workspace and Zoom. **Stop.**
3. **The integration test, the other six.** Fathom, Constant Contact, Lob,
   Twilio, Anthropic, YouTube. **Stop.**
4. **The setup checklist.** The `integration:` and `check:` keys, the automatic
   checks, the hand ticks and their table, and the missing steps for Lob,
   Twilio, Anthropic and YouTube. **Stop.**
5. **The nightly integration test.** The worker job, its hour setting, and the
   alert with its cool-down. **Stop.**
6. **The diagnosis agent.** The read-only tools, the allowed sites, the
   `submit_fix_plan` schema, the fix plan table, approval, carrying out the
   steps, and the re-test. **Stop.**
7. **The setup assistant.** The `submit_setup_plan` schema, the coded-action
   list and its first actions, the one-step-at-a-time runner with
   check-on-confirm, and the manual steps confirmed against each vendor.
   **Stop.**
8. **Documentation and live review.** `SYSTEM-SETTINGS-SETUP.md`,
   `setup/CLAUDE.md`, `CHANGELOG.md`, `OPEN-ITEMS.md`. Then switch it on in
   crm-test's overlay and review it live as an administrator. **Stop** before
   production.

## 9. Open items

- ~~§ 6.6: how recent errors reach the diagnosis agent~~: settled in phase 6, the narrowed `integration_event` table.
- § 3: each sub-tab's checks and integration facts are proposals. Each one is
  confirmed against the vendor's API during its phase.
- ~~The EspoCRM version read~~: settled in phase 2, `GET App/user` →
  `settings.version` (9.3.10 on crm-test, 11-13-26).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.11 | 11-13-26 12:12 | Claude (Claude Code) | Phase 6 built: v0.327.0, the diagnosis agent and fix plans. Doug's decisions 11-13-26: § 6.6 settled as the narrowed `integration_event` table (only each integration job's top-level handler writes, scrubbed, once an hour, 14 days); a monthly budget setting, default $25; the allowed sites as checked (Google adds `knowledge.workspace.google.com`, Anthropic drops `docs.claude.com`). § 6.1's Tool Runner became a manual loop (SDK 0.116 does not resume a paused server-tool turn). Not pushed. |
| 0.10 | 11-13-26 11:04 | Claude (Claude Code) | Phase 5 built: v0.326.0, the nightly integration test. Doug's decision 11-13-26, option A: ruling I8 kept (the worker runs it); checks reading a value only the web process is given (the provisioning account, Lob's webhook secret, the All Members group) are skipped at night. § 5's cool-down is the stored runs, not the worker's memory; unknown alerts on the third night. Not pushed. |
| 0.9 | 11-13-26 10:30 | Claude (Claude Code) | Phase 4 built: v0.325.0, the setup checklist (mapping Doug approved 11-13-26). § 4's `check:` key became `check.auto`, since `check` already held `how` and `probe`; `crm_field` dropped (no step needs it) and `mailing_connected` added; a framing row first ("Decide whether …") and last ("The integration test passes"); Fathom and the Constant Contact connection gained steps beside the four § 4 named. Not pushed. |
| 0.8 | 11-13-26 01:42 | Claude (Claude Code) | Phase 3 built: v0.323.0, the integration test for Fathom, Constant Contact, Lob, Twilio, Anthropic and YouTube (the check lists Doug approved 11-13-26; Constant Contact refreshes only when due, option A). Changed from § 3: Fathom's account fact became the meetings' recorders (no who-am-I call); Lob's account fact dropped (no account read); Twilio gains a local sending-hours check, Constant Contact the lead-code field. Not pushed. |
| 0.7 | 11-13-26 01:21 | Claude (Claude Code) | Phase 2 built: v0.322.0, the integration test for EspoCRM, Google Workspace and Zoom. § 9's EspoCRM version read is settled: `GET App/user` → `settings.version` (crm-test, 9.3.10). Not pushed. |
| 0.6 | 11-13-26 00:36 | Claude (Claude Code) | Phase 1 built: v0.321.0 (the registry, the tags, the "in use" settings and refusals, the sub-tab shell, the switch). Not pushed. |
| 0.5 | 11-13-26 00:30 | Claude (Claude Code) | Phase 1 mapping approved by Doug 11-13-26 with four corrections, recorded as mapping decisions: (1) EspoCRM has no "in use" setting — it is always in use and its warnings are never hidden; (2) Lob's switch is `postal_provider = lob`, not `campaigns_enabled`, and `alert_email_from` blocks nothing; (3) a switch and the settings that only serve it stay together — `comms_digest` stays on the Settings tab with its hour, time zone and re-check, listed under Google's "Used by"; `campaign_send_report_seconds` stays with its switch; every `enrichment_ai_*` setting, the monthly budget and caps included, moves to Anthropic with `enrichment_ai`; Zoom's attendance timers move; (4) the "in use" refusals also cover the "Used by" switches whose feature cannot work at all without the integration: `campaigns_sms` (Twilio); `campaigns_email` and `campaign_send_report` (Constant Contact); `events_confirmations`, `events_reminders`, `lead_outreach` and `mentor_provision_users` (Google). Everything else as proposed. The full mapping is `core/settings_registry.INTEGRATION_TAGS`. |
| 0.4 | 11-13-26 00:16 | Claude (Claude Code) | Ruling I13 (Doug, 11-13-26): switching a feature on is refused while its integration is marked not in use. Build orchestrator and phase 1 prompt written. |
| 0.3 | 11-12-26 23:55 | Claude (Claude Code) | Rulings I11 (setup assistant, option B) and I12 (setup steps each confirmed; fix plans run automatic steps straight through), Doug 11-12-26. Check-on-confirm and the one-step display added; § 6.5 the setup assistant; phase 7 added, documentation becomes phase 8. |
| 0.2 | 11-12-26 23:52 | Claude (Claude Code) | Ruling I10 (Doug, 11-12-26): the application carries out an approved fix plan; the open item removed. |
| 0.1 | 11-12-26 23:47 | Claude (Claude Code) | First draft from the 11-12-26 design conversation: rulings I1–I9, the sub-tabs, the setup checklist, the nightly integration test, the diagnosis agent, storage, and seven phases with stopping points. For Doug's review. |
