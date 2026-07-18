# `CSession` transcript fields — CRM build specification

**Status: BUILT on crm-test (2026-07-18, probe-verified — both fields present
with the specified types, and the API key's CSession READ works; the EDIT
half of the grant is proven by the first live write). Prod build status
unverified from the app side (the overlay's API key is encrypted) — confirm
at prod activation.** Required for the Meeting Transcript integration (the
app side shipped in v0.83.0, gated off by `MEET_TRANSCRIPTS`; plan:
`prds/meet-transcript-integration.md`). This is the CRM-team handoff, in the
style of `csession-calendar-field.md`. Built on **crm-test first**; prod
follows after live verification. Track as a crmbuilder program in
`ClevelandBusinessMentors/programs/` per that repo's requirement-first process.

## What this is

Every Google Meet the session tools schedule gets automatic transcription
turned on. After the meeting, a background job retrieves the finished
transcript and stores it on the session record:

- the **speaker-attributed transcript text** goes into `sessionTranscription`
  — the session view's Transcript zone and the editor's Transcript box (built
  and feature-gated since v0.37.0) light up automatically once this field
  exists;
- a **link to the permanent Google Doc transcript** (kept in the organizer's
  Drive by Google) goes into `transcriptDocUrl`, shown as a copyable
  "Transcript document" row in the session view.

The app **feature-detects both fields via metadata** and stays completely
inert until they exist, so this build can land before or after the app deploy
in any order.

## The build (two fields)

Standing in **Entity Manager → CSession → Fields → Add Field**:

### 1. `sessionTranscription`

| Setting | Value |
|---|---|
| Type | **Wysiwyg** |
| Name | `sessionTranscription` |
| Label | Transcript |
| Required | No |
| Default | (none) |
| Audited | No |

Notes:
- The retrieval job writes it, and mentors may also paste/edit a transcript in
  the session editor (the field is part of the session tools' editable set) —
  so unlike the calendar event id, staff edits here are fine.
- Transcripts are long. If the instance's wysiwyg columns are created as
  `MEDIUMTEXT` (EspoCRM default for text/wysiwyg), nothing more is needed; the
  app clamps at ~200k characters regardless, with a note pointing to the Doc.

### 2. `transcriptDocUrl`

| Setting | Value |
|---|---|
| Type | **Url** |
| Name | `transcriptDocUrl` |
| Label | Transcript Document |
| Max Length | 255 |
| Required | No |
| Default | (none) |
| Audited | No |

Notes:
- App-managed (the retrieval job is the only writer). If it is placed on the
  detail layout, make it **Read-only** so a hand-edit can't point the session
  at the wrong document.

## Role grant (required)

The intake **API user's role (`CustomAppAPIRole`)** needs **CSession: Read +
Edit** (scope *all*). The retrieval job runs under the API key (the
comms-sync precedent) and today that role has **no CSession grant at all** —
without it the job can neither find candidate sessions nor store transcripts.
No change to the staff/mentor gate roles: they already read/edit their own
sessions, which covers viewing the new fields.

## Google/Workspace prerequisites (Doug, not CRM-team)

Listed here for completeness — details in `prds/meet-transcript-integration.md`:

1. **Licensing (BLOCKING):** Meet transcripts require **Business Standard or
   above** for the meeting organizer. Confirm the `@cbmentors.org` edition in
   Google Admin → Billing → Subscriptions; the free Nonprofits tier does NOT
   include transcripts (nonprofit Business Standard covers only the
   session-hosting users).
2. Admin console → Apps → Google Workspace → Google Meet → Meet video
   settings → **Transcription = ON** for the org unit.
3. Enable the **Google Meet REST API** on GCP project `espcrm-498315`.
4. Add `https://www.googleapis.com/auth/meetings.space.created` to the
   service account's existing domain-wide-delegation row (Google Admin →
   Security → API controls). **Gotcha: the scope field REPLACES — edit the
   existing line keeping all current scopes** (gmail.readonly, gmail.send,
   calendar.events, drive, and the Directory scopes as applicable).
5. Set `MEET_TRANSCRIPTS=true` on **web AND worker** (web enables
   transcription at schedule time; the worker retrieves).

## Verification (after `MEET_TRANSCRIPTS` is turned on)

1. In `/mentorsessions`, create a Scheduled session with a generated Meet
   link, hold a short real meeting on it (transcription should start
   automatically; participants see Google's notice), and end the meeting.
2. Within a poll cycle (~30 min; watch the worker logs for
   "transcript stored"), the session view's Transcript zone shows the
   speaker-attributed text and the facts grid shows the "Transcript document"
   link opening the Google Doc.
3. Give-up path: a Scheduled Meet session whose meeting never happens is
   quietly dropped once its start is `TRANSCRIPT_GIVE_UP_DAYS` (14) old.
4. A non-admin mentor on the engagement can see the transcript (the session's
   existing `assignedUsers` stamps carry visibility; the write is attributed
   to the API user).
