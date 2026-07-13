# `CSession.googleCalendarEventId` — CRM build specification

**Status: NOT BUILT — required for the sessions Google Calendar integration**
(the app side shipped in v0.40.0, gated off by `GCAL_EVENTS`). This is the
CRM-team handoff, in the style of `cconversation-entity.md`. Build on
**crm-test first**; prod follows after live verification. Track as a
crmbuilder program in `ClevelandBusinessMentors/programs/` per that repo's
requirement-first process.

## What this is

When a manager saves a **Scheduled** session in the session tools, the app
creates a Google Calendar event (with a Google Meet link, written to the
existing `videoMeetingLink` field) on the manager's own calendar and invites
the attendees. To keep that event in sync — later time/title/attendee edits
update it, and setting the session to Cancelled cancels it — the app must
remember which Google event belongs to the session. This field stores that
Google Calendar event id.

The app **feature-detects the field via metadata** and stays completely inert
until it exists, so this build can land before or after the app deploy in any
order. The app is the only writer; staff never edit it.

## The build (one field)

Standing in **Entity Manager → CSession → Fields → Add Field**:

| Setting | Value |
|---|---|
| Type | **Varchar** |
| Name | `googleCalendarEventId` |
| Label | Google Calendar Event ID |
| Max Length | 255 |
| Required | No |
| Default | (none) |
| Audited | No |

Notes:
- **No layout placement is needed** — the app reads/writes it via the API and
  never shows it. If it is placed on the detail layout anyway, make it
  **Read-only** so staff can't hand-edit it (a wrong id would make the app
  patch/cancel someone else's event).
- No new relationships, no role changes: the session tools' gate roles already
  have `CSession` read-own/edit-own, which covers this field.

## Verification (after the app's `GCAL_EVENTS` is turned on)

1. In `/mentorsessions`, create a Scheduled session with a start time — the
   record should gain a `googleCalendarEventId` value and a
   `meet.google.com` link in `videoMeetingLink`, and the event should appear
   on the manager's Google calendar with the attendees invited.
2. Edit the session's time — the Google event moves.
3. Set the session status to Cancelled — the Google event is cancelled and
   both `googleCalendarEventId` and the generated Meet link are cleared.

## Related

- App-side settings and runbook: `GCAL_EVENTS` in `.env.example` /
  `DEPLOYMENT.md`; the domain-wide-delegation grant needs
  `https://www.googleapis.com/auth/calendar.events` added alongside the two
  Gmail scopes (Google Admin → Security → API controls → Domain-wide
  delegation → edit the existing service-account row), and the Google Calendar
  API enabled in the "CBM Integrations" GCP project.
- **Before enabling on crm-test: disable EspoCRM's own Google Calendar
  integration** (the personal-account test setup) — otherwise every session
  gets two calendar events. Production never had it; the app owns all
  calendar operations there.
