# `CMentorProfile` meeting-preference fields — CRM build specification

**Status: NOT BUILT — wanted for mentor-supplied Zoom meeting links (My Mentor
Profile `/mentorprofile` + the session tools' New-session editor).** The app
side shipped feature-gated (v0.151.0): the two profile-editor fields and the
session editor's link pre-fill activate on their own once BOTH fields exist
(metadata feature-detection, the `mentorSummary` / `sessionTranscription`
precedent), so this build can land before or after any app deploy. Build on
**crm-test first**; prod follows. Track as a crmbuilder program in
`ClevelandBusinessMentors/programs/` per that repo's requirement-first process.

## What this is

Doug's ruling (2026-07-24): CBM supports **mentor-supplied Zoom** — a mentor
who already uses Zoom can have their **Zoom Personal Meeting room** used for
sessions instead of a generated Google Meet. No CBM Zoom account, no Zoom API:
the mentor stores their own static room link on their profile.

Behavior once built (all app-side, already shipped):

- `/mentorprofile` → Mentoring preferences gains **"Preferred meeting
  service"** (select) and **"Zoom personal meeting link"** (URL) side by side.
- When a mentor's preference is **Zoom Personal Meeting** AND a link is
  stored, every **New session** editor they open pre-fills "Video meeting
  link" with that link. The existing calendar hook then carries it into the
  Google Calendar event as an external link and **does not create a Meet**
  (the long-standing hand-typed-link rule). Clearing the pre-filled link
  before saving opts that one session back into a generated Meet.
- Preference **Google Meet** (or unset, or no link stored) = today's behavior
  exactly: blank link → a Meet is created.
- Fathom transcript retrieval already normalizes Zoom URLs and prefers
  invitee-overlap matches for reused personal rooms (v0.126.0), so note-taking
  on PMI sessions needs no extra work.

## The build (two fields)

Standing in **Entity Manager → CMentorProfile → Fields → Add Field**:

Field 1:

| Setting | Value |
|---|---|
| Type | **Enum** |
| Name | `preferredMeetingProvider` |
| Label | Preferred Meeting Service |
| Options | `Google Meet`, `Zoom Personal Meeting` — **verbatim, exact case** |
| Default | `Google Meet` |
| Required | No |
| Audited | No |

Field 2:

| Setting | Value |
|---|---|
| Type | **Url** |
| Name | `zoomPersonalLink` |
| Label | Zoom Personal Meeting Link |
| Required | No |
| Audited | No |

Notes:

- The option value **`Zoom Personal Meeting` must match exactly** — the app
  compares it verbatim (`sessions/service.py:ZOOM_PMI_PROVIDER`). Renaming the
  option in the CRM later would silently turn the feature off (the app would
  just fall back to Meet — safe, but confusing).
- Adding more options later (e.g. another vendor's personal-room service) is
  harmless: the app treats anything other than `Zoom Personal Meeting` as the
  Meet default until it's taught otherwise.
- **Field-level access:** the Mentor Team role needs read+edit on both fields
  (mentors edit their own profile through `/mentorprofile` under their own
  login). Remember the crm-test Mentor Role field-lockdown lesson — a
  write-denied field is silently stripped on a 200 OK save.
- Layout placement on the CRM detail layout is optional (staff visibility);
  the app edits via the API.

## Verification

1. Build both fields on crm-test.
2. Open `/mentorprofile` as a mentor — "Preferred meeting service" +
   "Zoom personal meeting link" appear in Mentoring preferences (no app
   deploy needed). Set Zoom Personal Meeting + a real PMI URL, Save,
   GET-verify both stored.
3. Open a record in `/mentorsessions` → New session: the Video meeting link
   field is pre-filled with the PMI URL. Save as Scheduled → the Google
   Calendar event carries the Zoom link (location/description) and **no Meet
   link is generated**; `videoMeetingLink` on the CSession stays the PMI URL.
4. Clear the pre-filled link on another new session → a Meet is created as
   before (the opt-out path).
5. As a mentor with preference Google Meet (or unset): New session shows a
   blank link field — behavior unchanged.
