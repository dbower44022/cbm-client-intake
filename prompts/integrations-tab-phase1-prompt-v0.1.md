# Kickoff prompt — Integrations tab, phase 1: the framework

Last Updated: 11-12-26 23:59 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any code:

- `prompts/integrations-tab-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/integrations-tab-plan.md`: the plan. **Rulings I1 to I13 are settled;
  do not re-open them.** This phase builds §§ 2 and 3 (except the integration
  test, the diagnosis and the setup checklist) and § 7's "in use" settings.
- `setup/CLAUDE.md`.
- `core/settings_registry.py`, `core/settings_store.py`, `setup/service.py`,
  `setup/router.py`, `setup/readiness.py`, `setup/verify.py`, `setup/mailing.py`
  and `setup/frontend/` (`index.html`, `app.js`, `styles.css`).
- `tests/test_system_settings.py`, `tests/test_verified_settings.py` and
  `tests/test_mailing_setup.py`, for how the page is tested.

## Scope of this phase

Build the Integrations tab's frame, dark behind `INTEGRATIONS_TAB`:

1. **The integration registry.** A new package, `integrations/`, with
   `registry.py`. One entry per integration, in this display order: EspoCRM,
   Google Workspace, Zoom, Fathom, Constant Contact, Lob, Twilio, Anthropic,
   YouTube. Each entry holds its key, its display name, its "in use" setting,
   its sections (Google Workspace has several; the rest have one), the readiness
   features it serves (`setup/readiness.FEATURES` keys), and its runbook path
   where one exists. Later phases add the integration test, the allowed
   documentation sites and the coded actions here, so leave room for them.
2. **Settings know their integration.** `SettingSpec` gains `integration`
   (an integration key, or empty) and `section` (empty unless the integration
   has sections). Every setting that belongs to an integration is tagged, by
   the rule below.
3. **The "in use" settings** (ruling I5). One bool setting per integration,
   `<key>_in_use`, default true, component `both`, shown first on its sub-tab.
   - The application refuses `false` while any of that integration's feature
     switches is on. The message names each switch that is on.
   - The application refuses switching a feature on while its integration is
     marked not in use. The message says to mark the integration in use first.
     (Doug's ruling I13, 11-13-26.)
   - Both refusals are enforced on the server, in the save path, not only in
     the page.
4. **The switch, `INTEGRATIONS_TAB`.** A bool setting in the Features group,
   default false, read per request.
   - **Off:** the page is exactly as today. A test compares the settings
     payload with the switch off against the payload before this phase.
   - **On:** a top-level **Integrations** tab appears beside Settings. Every
     tagged setting leaves its group on the Settings tab and appears on its
     sub-tab. A group left empty disappears. The "Integrations" group therefore
     disappears.
5. **The sub-tab shell.** One sub-tab per integration, in registry order. Each
   sub-tab shows, top to bottom:
   - **The status line**: in use or "Not used by this chapter"; on or off
     (on when any of its feature switches is on); credentials set or which are
     missing; and "Not tested yet", which phase 2 replaces.
   - **Placeholders** for the integration test, the diagnosis and the setup
     checklist, each one line saying which phase brings it. Not buttons:
     nothing that looks clickable and does nothing.
   - **The settings**, edited exactly as on the Settings tab today: the same
     row component, the same checked save path, the same confirm-or-revert
     countdown, the same restart-required badge and in-force value, the same
     secret handling. Reuse the Settings tab's row rendering; do not copy it.
   - Google Workspace's settings are grouped in collapsible sections:
     Credentials, Drive, Calendar, Meet, Gmail and the shared mailbox, Workspace
     accounts. Credentials comes first and is open; the rest are open too on
     first view.
   - A sub-tab marked not in use keeps its settings visible and editable,
     under the "Not used by this chapter" label.
6. **Deep links and readiness.** Each sub-tab has an address
   (`/setup/#integrations/zoom`). With the switch on, each Feature readiness row
   whose feature belongs to an integration links to that sub-tab. Readiness
   leaves the warnings of a not-in-use integration out of its counts, and says
   so on the row.

### The rule for which settings move

A setting moves to an integration's sub-tab when it is one of these:

- a credential or connection setting for that integration;
- a feature switch for a feature that cannot work without that integration
  and uses no other integration;
- a setting that only tunes that integration's calls: a poll interval, an API
  address, a model name, a time zone for its sends.

A setting that does not meet the rule stays where it is. Where a feature on the
Settings tab depends on an integration but stays there (for example
`campaigns_sms`, which is Marketing Management's switch and also needs Twilio),
the sub-tab lists it under "Used by", read-only, with a link to the setting on
the Settings tab. Each setting is still edited in one place only.

## Stopping point 1 — the mapping, before any code

Read every `SettingSpec` in `core/settings_registry.py` and apply the rule.
Then put the result to Doug as **one table per integration**: each setting's
key, its label, its current group, and the section it would go to. After the
tables, list separately:

- the settings you could not place with confidence, each with your reasoning;
- the "Used by" entries for each integration;
- any feature switch that belongs to an integration but that you left on the
  Settings tab, with the reason.

Then stop. Write no code until Doug approves the mapping or corrects it.

## Stopping point 2 — the phase built

Build items 1 to 6 with the approved mapping. Tests:

- the registry is complete: every integration's "in use" setting exists; every
  tagged setting names a real integration and, for Google Workspace, a real
  section; every readiness feature named by an integration exists;
- every setting that was in the "Integrations" group is tagged;
- the switch-off payload is unchanged;
- both refusals of item 3, through the API;
- a not-in-use integration's warnings leave the readiness counts.

Then show the page. Run the application locally and open `/setup/` in the
browser with the switch on, using the preview recipe in
[[sessions-frontend-stub-harness]] if a CRM sign-in is not available. Take a
screenshot of the Zoom sub-tab and of the Google Workspace sub-tab.

Close the phase as the orchestrator's **Closing a phase** section requires,
including creating `OPEN-ITEMS.md` item **82**, "The Integrations tab of
System Settings", under "Needs a fix / decision", and writing the phase 2
prompt as a draft. Then stop for Doug's review.

## Out of scope

The integration test, the nightly run, the setup checklist, the diagnosis agent
and the setup assistant. No outside service is called by anything this phase
builds.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-12-26 23:59 | Claude (Claude Code) | Created from plan revision 0.3 and the orchestrator revision 0.1. |
