# Google-side setup for session calendar events (v0.40.0) — step by step

Everything Google-side needed to activate the sessions Google Calendar + Meet
integration (`GCAL_EVENTS`). Two tasks, both reusing the service account the
Gmail integration already runs on — **no new service account, no new JSON key,
no change to any app secret**.

The facts you'll need (from the Gmail activation record, 2026-07-11):

| Item | Value |
|---|---|
| GCP project | `espcrm-498315` |
| Service account | `espocrm@espcrm-498315.iam.gserviceaccount.com` |
| Its OAuth2 **Client ID** (the DWD row key) | `109317126943210877831` |
| Scopes currently on the DWD row | `gmail.readonly`, `gmail.send` |
| Accounts to use | GCP console: the Google account that owns the project (created under `admin@cbmentors.org`). Admin console: a **super-admin** of `cbmentors.org` |

---

## Task 1 — Enable the Google Calendar API on the GCP project

Without this, every calendar call fails with HTTP 403
`accessNotConfigured` / "Google Calendar API has not been used in project
espcrm-498315 before or it is disabled".

1. Go to **https://console.cloud.google.com** and sign in with the account
   that owns the project.
2. In the **project picker** (top bar, left of the search box), select
   **`espcrm-498315`**. Verify the picker shows that project id before
   continuing — enabling the API on the wrong project does nothing.
3. Open the left-hand menu (☰) → **APIs & Services → Library**.
   (Direct URL: https://console.cloud.google.com/apis/library?project=espcrm-498315)
4. In the Library search box type **`Google Calendar API`** and open the
   result named exactly **Google Calendar API** (by Google Enterprise API).
5. Click **Enable**. If the button already reads **Manage**, it's enabled —
   nothing to do.
6. Sanity check: **APIs & Services → Enabled APIs & services** should now
   list **Google Calendar API** alongside **Gmail API**.

That's all in GCP. Do **not** add IAM roles to the service account — its
power comes from the Workspace delegation (Task 2), not GCP IAM. Do **not**
create a new key.

---

## Task 2 — Add the Calendar scope to the existing delegation row

This authorizes the service account to act on users' calendars. It's an
**edit of the existing row**, not a new row: Google keys delegation rows by
Client ID, and **all scopes for one Client ID must live in that single row** —
adding a second row for the same ID replaces/conflicts rather than merging.

1. Go to **https://admin.google.com** and sign in as a `cbmentors.org`
   **super-admin**.
2. Left menu → **Security → Access and data control → API controls**.
3. In the "Domain wide delegation" panel at the bottom, click
   **MANAGE DOMAIN WIDE DELEGATION**.
4. Find the row whose **Client ID** is `109317126943210877831` (it currently
   lists the two Gmail scopes). Hover the row and click **Edit** (pencil).
5. In **OAuth scopes**, set the value to exactly these **three** scopes,
   comma-separated, no spaces, no line breaks (copy-paste this whole line):

   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar.events
   ```

   ⚠️ The field REPLACES the previous list — the two Gmail scopes must be in
   it or the Communications integration breaks. Paste the full three-scope
   line, don't type just the new one.
6. Click **AUTHORIZE**.
7. Verify: the row now shows three scopes. Common paste mistakes that make
   authorization silently fail for one scope: a trailing period, a space
   after a comma, `http://` instead of `https://`, or the shorter
   `auth/calendar` scope (we deliberately use the narrower
   `auth/calendar.events` — events only, no calendar settings/ACL access).

**Propagation:** usually takes effect within a few minutes; Google documents
up to 24 hours. If a test right after authorizing fails with
`unauthorized_client` / "delegation denied", wait and retry before changing
anything.

---

## What does NOT need doing in Google

- **No new service account / key / OAuth consent screen** — the existing
  `GOOGLE_SERVICE_ACCOUNT_JSON` secret already deployed on the apps is the
  credential; delegation is keyed to its Client ID.
- **No per-user setup** — delegation covers every `@cbmentors.org` user; the
  app only ever impersonates the signed-in manager's own mailbox
  (their `CMentorProfile.cbmEmail`).
- **No extra scope for the time picker's conflict shading (v0.141.0)** —
  the session editor's busy-slot lookup reads the manager's own calendar via
  `events.list`, which the same `calendar.events` scope covers. It activates
  with the same `GCAL_EVENTS` flag; nothing separate to authorize.
- **No Meet-specific API or scope** — Meet links are created through the
  Calendar API (`conferenceData.createRequest`), covered by
  `calendar.events`. Only prerequisite: the **Google Meet service is ON** for
  the org (Admin console → Apps → Google Workspace → Google Meet — it is on
  by default; check only if Meet was ever turned off, and confirm "Let users
  ... video calls" is enabled).

---

## After Google (the rest of the activation, for context)

Google alone doesn't turn anything on — the app stays inert until:

1. The CRM team builds **`CSession.googleCalendarEventId`** on crm-test
   (`csession-calendar-field.md`).
2. **EspoCRM's own Google Calendar integration is disabled on crm-test**
   (the personal-account experiment) — otherwise every session gets two
   events. Production never had it.
3. **`GCAL_EVENTS=true`** is set on the crm-test **web** component
   (`doctl apps update … --spec .do/app.prod.yaml` with the flag added; the
   worker is not involved).

Then verify live in `/mentorsessions`: create a Scheduled session with a
start time → the event appears on the manager's Google calendar, the
attendees receive invitations, and the session's `videoMeetingLink` gains a
`meet.google.com` URL; edit the time → the event moves; set status Cancelled
→ the event is cancelled. Also (v0.141.0): pick a date on a day with an
existing meeting and open the **Time** selector → the overlapping half-hour
slots render with a light-red background and a tooltip naming the meeting;
they remain selectable (double-booking is allowed — the user deconflicts
manually), and editing an existing session never flags its own event.

**How attendees are addressed (v0.122.0/v0.123.1, verified live on prod
2026-07-21):** client contacts are invited at their Contact record's email.
**CBM members** (the assigned mentor, co-mentors, and the acting organizer)
are invited at their **`cbmEmail` only** — never the personal email on their
Contact record — and the organizer is never invited at all (Google shows the
event on their calendar as organizer). A member whose profile has no
`cbmEmail` is silently skipped (logged), not invited personally. This closed
the duplicate-event report: the organizer used to get a self-invitation at
their personal address, and accepting it created a second event copy.

**User guidance worth repeating in the mentor guide:** the meeting lives on
the mentor's `@cbmentors.org` calendar and the CRM session record is the
source of truth — cancel/reschedule from the app, not Google Calendar.
Deleting the event by hand in Google cancels it for the client too, and the
CRM never learns of Google-side deletions (sync is one-way, app → Google).

## Troubleshooting

| Symptom (app log / UI notice) | Cause / fix |
|---|---|
| `Calendar auth failed … unauthorized_client` or `access_denied` | The DWD row doesn't (yet) carry `calendar.events`: re-check Task 2 step 5 for paste errors, or wait out propagation |
| `HTTP 403 … accessNotConfigured` / "API has not been used in project" | Task 1 missed or done on the wrong project |
| `HTTP 403 … forbidden` on a specific mailbox | The impersonated user doesn't exist / is suspended in Workspace (check the mentor's `cbmEmail` matches a real account) |
| Event created but no Meet link | Meet service disabled for the org, or the link was still pending (the app retries once; re-saving the session's time backfills it) |
| "your profile has no CBM email address" notice | Not Google — the manager's `CMentorProfile.cbmEmail` is blank in the CRM |
| Mentor sees TWO copies of the meeting / is asked to accept their own meeting | Fixed in v0.122.0/v0.123.1 (members were invited at their Contact's personal email). On an older event, re-save the session with a schedule-relevant change — the re-patch removes the personal-address invite (Google emails it a cancellation) |
| Mentor deleted the event in Google Calendar; the CRM still shows the session | By design — sync is one-way (app → Google). Deleting the organizer copy cancels it for all guests. Cancel the session in the app (tolerates the already-deleted event) and create a fresh one if the meeting should still happen |
| A CBM member on the attendees got no invitation | Their `CMentorProfile.cbmEmail` is blank (members are never invited at personal addresses) — set the CBM email, or check the run log warning naming them |
