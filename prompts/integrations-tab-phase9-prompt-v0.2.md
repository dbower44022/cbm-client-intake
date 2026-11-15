# Kickoff prompt — Integrations tab, phase 9: the Zoom split, then the other eight integrations' wizard screens

Last Updated: 11-15-26 02:30 · Revision 0.2 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 9 session starts.
Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`. Revision 0.1 is kept beside it for
the record; this revision replaces it.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
five stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md`.
- `prds/integrations-tab-plan.md`, **§ 10**: rulings W1 to W6 and its
  *Event hosting* paragraph. Do not re-open them.
- **`prds/events/event-hosting-plan.md`, revision 0.7 or later**: rulings
  **EH1 to EH14** (settled; do not re-open them) and § 3, which records what
  Zoom Meetings did on a real account on 11-15-26.
- `OPEN-ITEMS.md` items 82, 84 and 85, `setup/CLAUDE.md`, `CHANGELOG.md`
  0.331.0 to 0.332.3.
- **Zoom's 14 screens** in `prds/chapter-network/deployment-guide/steps/stage-05.yaml`
  (step 5.5's `wizard:` key) and `steps/README.md`'s `wizard` row: the
  pattern to follow. And `integrations/wizard.py`,
  `integrations/registry.py` (the `zoom` entry), `integrations/checks/zoom.py`.
- `scripts/probe_zoom.py --meetings`: the Zoom Meetings calls as they were
  proved on 11-15-26.
- Each integration's guide steps (`integration:` keys from phase 4) and its
  checks in `integrations/checks/`.

## Part one — the Zoom split (before any other integration)

Rulings EH1, EH5, EH6, EH7, EH8 and EH11. **The event hosting build waits on
this part**: its step 4 (`prompts/event-hosting-step4-resume.md`) starts only
once it is committed, and stops if a setting below is missing. Build only the
System Settings side here; the Events side (creating meetings, registrants,
attendance, the event form) is that build's.

**Two integrations where there is one.** The `zoom` integration becomes
**Zoom Webinars**; a new **Zoom Meetings** integration is added beside it,
each with its own "in use" setting, credentials, test, wizard and checklist.
Keep the existing setting keys for Webinars (`zoom_in_use`, `zoom_events`,
`zoom_account_id`, `zoom_client_id`, `zoom_client_secret`,
`zoom_host_email`): renaming a key strands every chapter's stored override.
Relabel them for Webinars instead.

**The settings the Events side reads** — put the names you choose in
`setup/CLAUDE.md` so step 4 can find them:

1. Zoom Meetings' account id, client id and client secret (the secret stored
   encrypted, as every secret is), and its "in use" setting.
2. **Whether Zoom Webinars is on the same Zoom account as Zoom Meetings**
   (EH7), default yes. When yes, Webinars uses Meetings' credentials and its
   wizard skips its own credential screens.
3. **The event host user** (EH8): the one Zoom user every Zoom event is
   created under, for example events@ on the chapter's domain. When Webinars
   is on a separate account, that account's host (today's `zoom_host_email`)
   is used for webinars.
4. **The default hosting method for public events and for members-only
   events** (EH5): each one of Zoom Webinars, Zoom Meetings, Other platform,
   Outside host. The stored values are the CRM's: `CBM Zoom` (shown as Zoom
   Webinars), `Zoom Meetings`, `Other platform`, `Outside host`
   (`cevent-hosting-method-crm-handoff.md`).
5. **Zoom Meetings' capacity limit** (EH6), default 100: the Business Mentors
   Association's Pro account read 100 on 11-15-26.

**Zoom Meetings' test and checks**, from what the probe proved on 11-15-26:

- The credentials authenticate.
- **The ten meeting scopes are granted**, besides `user:read:user:admin`:
  `user:read:settings:admin`, `meeting:read:list_meetings:admin`,
  `meeting:read:meeting:admin`, `meeting:write:meeting:admin`,
  `meeting:update:meeting:admin`, `meeting:delete:meeting:admin`,
  `meeting:write:registrant:admin`, `meeting:read:list_registrants:admin`,
  `meeting:update:registrant_status:admin`,
  `report:read:list_meeting_participants:admin`. Zoom names a missing scope
  in its refusal (`code 4711`, "does not contain scopes:[…]"); show those
  words.
- The event host user exists and is **Licensed** (`type` 2): a Basic user
  cannot take registrations.
- **The co-host feature is on** (`GET /users/{host}/settings` →
  `in_meeting.co_host`). Ruling EH11 lets only the host share, so a
  co-presenter shares by being made co-host; without the feature they cannot.
  Not yet read on any account.
- The meeting capacity (`feature.meeting_capacity`) as a fact beside the
  capacity limit setting.

**The wizards.** Zoom Meetings' screens drafted in the same shape as Zoom's,
from guide step 5.5 split in two: the guide's scope list for Meetings is the
ten above, found on the app's Scopes page through its **Add Scopes** button —
the page's own "Search name, ID, type" box searches only the scopes already
added (seen 11-15-26). The pilot's 14 screens reworded for Zoom Webinars,
with "Is Zoom Webinars on the same Zoom account as Zoom Meetings?" asked
early (EH7). Feature readiness and the nightly test cover Zoom Meetings.

## Stopping point 1 — the split's settings and screens

Put to Doug: the setting names and labels, the Zoom Meetings checks, and the
two integrations' screens in order, as he will see them. Then stop.

## Stopping point 2 — the split built

Build what Doug approved, with tests, and commit it on its own version so the
event hosting build can start. Tell Doug the event hosting build's step 4
can now run. Then stop.

## Part two — the other eight integrations

Screens for EspoCRM, Google Workspace, Fathom, Constant Contact, Lob, Twilio,
Anthropic and YouTube, in the same shape as Zoom's: the "Does this chapter
use …?" question first (none for EspoCRM, always in use), one screen per
action, a check on every screen the application can check, branches where a
chapter may already have the account. Where a phase 7 coded action exists
(the Google shared drive, the Twilio sender number), its screen runs it.
Any new check kind the screens need (for example, a Google directory user
exists) is added to `integrations/wizard.py` with its tests.

## Stopping point 3 — Google Workspace's screens

Google is the largest: put its screens to Doug first, in order, as he will
see them. Then stop.

## Stopping point 4 — the other seven

Put the other seven integrations' screens to Doug. Then stop.

## Stopping point 5 — built

Build the approved screens, with tests that each integration's screens load
and name only real checks and settings, and that the rendered guide is
unchanged. Close the phase as the orchestrator requires, and write the
phase 10 prompt (the removal, ruling W4) as a draft. Then stop.

## Things the build has learned

- **Another session works in the same checkout and git index.** Commit with
  an explicit path list (`git commit -- <paths>`, after `git add` of new
  files only); audit with `git show --stat`. Read `git log` for the version
  (in `pyproject.toml` and `uv.lock`) and `uv run alembic heads` before
  choosing either.
- **The test system is the Business Mentors Association's**, not crm-test,
  since 11-14-26 (`OPEN-ITEMS.md` #85): switch features on and check them at
  its System Settings. Its Zoom app already holds the ten meeting scopes; its
  host `admin@mentorsassociation.org` is Licensed, Pro, without the Webinars
  add-on. Its Zoom credentials are in Doug's vault, never in a file here.
- Doug's review of 11-13-26: one list, never three; never ask to set a value
  the page already shows; one step or question at a time
  (memory `wizard-not-lists`).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-15-26 02:30 | Claude (Claude Code) | Part one added: the Zoom split (plan § 10's *Event hosting* paragraph; rulings EH1, EH5 to EH8, EH11), the five settings the event hosting build's step 4 reads, Zoom Meetings' checks from the probe of 11-15-26, two new stopping points ahead of the original three. The test system named (#85). Written by the event hosting session at Doug's request (option A, 11-15-26). |
| 0.1 | 11-14-26 01:40 | Claude (Claude Code) | Draft written at the close of phase 8 (v0.331.0). |
