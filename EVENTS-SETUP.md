# Events & Webinars — activation and testing runbook

How to switch the Events feature on and drive it end to end. Written for
**crm-test first**; production is a separate, later pass.

**Status (2026-07-26):** Phases 1, 2, 3 and 5 are built and committed.
The crm-test **CRM schema is already migrated**; production is **not**.
Everything is behind flags that default OFF, so a deploy changes nothing until
you set them.

Companion docs: `event-administration.md` (what the tool does, for staff) ·
`prds/events/CBM_Events_PRD.md` (requirements) ·
`cevent-entities-crm-handoff.md` (the CRM schema and what changed).

---

## What works today, and what doesn't

Read this before testing, so you're measuring against reality.

| Works now | Needs something first |
|---|---|
| Staff app at `/events` — create/edit events, registrants, check-in, recordings | **Website page** — still runs on the old Apps Script (Phase 4 not built) |
| Public read API — upcoming events, recordings, per-event detail | **Zoom webinars / join links** — needs the OAuth app (below) |
| Registration into the CRM (Contact + registration record) via the API | **Automatic attendance** — Phase 6 |
| Capacity, waitlist, auto-promotion, self-service cancel | **Follow-up emails, reporting** — Phase 6 |

So: you can test **everything except the website page itself and anything Zoom
touches**. Registration is testable via the API (§4 below) even though the
public page isn't wired up yet.

---

## 1. Deploy the code

The Events commits are on `main`. Confirm the deployed version:

```bash
curl -s https://cbm-client-intake-svxs3.ondigitalocean.app/healthz | python3 -m json.tool
```

You want **0.170.0 or later**. If it's older, push and wait for the App Platform
build.

---

## 2. Switch it on (crm-test)

Three flags, all on the **web** component of the crm-test overlay
(`.do/app.prod.yaml`):

| Variable | Value | What it turns on |
|---|---|---|
| `EVENTS_ENABLED` | `true` | The `/events` staff app + the portal tile |
| `EVENTS_PUBLIC_API` | `true` | The public read + registration endpoints |
| `EVENTS_ALLOWED_TEAMS` | *(omit)* | Defaults to `Marketing Admin Team` |

Apply as usual:

```bash
doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e \
  --spec .do/app.prod.yaml --wait
```

Then confirm:

```bash
curl -s https://cbm-client-intake-svxs3.ondigitalocean.app/api/events/upcoming
# {"success":true,"webinars":[]}   ← empty is correct; nothing is published yet
```

**No migration is needed** — Events adds no database tables.

---

## 3. Make sure you can get in

The staff app is gated on the **Marketing Admin Team** — the same team that
owns `/ops`. You are an admin, so you'll pass regardless, but **test with a
real non-admin too**: that's the only way to know the team gate and the CRM
permissions are right for the people who'll actually use it.

1. Sign in at `https://cbm-client-intake-svxs3.ondigitalocean.app/`.
2. You should see an **Event Administration** tile.
3. Open it. If you get a 403, the message names the team you need.

**CRM permissions the team's role needs** (crm-test only — check before blaming
the app):

| Entity | create | read | edit | delete |
|---|---|---|---|---|
| `CEvent` | yes | all | yes | no |
| `CEventRegistration` | yes | all | yes | no |

A missing grant shows as a readable 403 naming the exact entity and operation —
if you see one, that's what it means.

---

## 4. The test script

Roughly 20 minutes. Do it in order; each step sets up the next.

### 4.1 Create an event
1. `/events/` → **+ New event**.
2. Title `TEST Grant Writing Basics`, Format **Virtual**, Topic
   **Finance & Accounting**, Starts a week out, Duration 90 minutes,
   **Capacity 2** (small on purpose — you'll test the waitlist), and tick
   **Publish to website**.
3. Save.

✅ It appears in the grid, filter showing "Published to the website".
✅ Overview shows Registered 0, Seats left 2.

### 4.2 Confirm it reaches the public API
```bash
curl -s https://cbm-client-intake-svxs3.ondigitalocean.app/api/events/upcoming \
  | python3 -m json.tool
```
✅ Your event is there. Check `time` reads Cleveland time, not UTC — an event at
2:00 PM must say `2:00 PM`, not `6:00 PM`.

Note its **`slug`** — you need it next.

### 4.3 Register someone (the public path)
This is what the website will do. Replace `SLUG`:

```bash
curl -s -X POST \
  https://cbm-client-intake-svxs3.ondigitalocean.app/api/events/SLUG/register \
  -H 'Content-Type: application/json' \
  -d '{"submission_token":"test-0001","first_name":"Ada","last_name":"Tester",
       "email":"ada.tester@example.com","phone":"216-555-0101",
       "zip_code":"44122","consent":true}'
```

✅ Returns `"status":"ok"` with a `contactId` and `eventRegistrationId`.
✅ In EspoCRM: a **Contact** "Ada Tester", type **Prospect**, marketing opt-in
ticked, zip and phone filled.
✅ In `/events` → Registrants: Ada, status Registered.

**Send it again with a different `submission_token` but the same email** — it
must *update*, not duplicate. Registrants should still show one Ada.

### 4.4 Fill the event and test the waitlist
Register two more people (`bob.tester@`, `cara.tester@`, distinct tokens).

✅ The second fills the last seat. The **third comes back `Waitlisted`**.
✅ Overview: Seats left 0, Waitlisted 1.

### 4.5 Cancel, and watch the waitlist move
In Registrants, **Cancel** Ada.

✅ Notice says the next person has been given the seat.
✅ Cara flips from Waitlisted to Registered automatically.

### 4.6 Closed registration
Edit the event and set **Registration closes** to yesterday. Try 4.3 again.

✅ HTTP 409 with a readable message, and **no** record is created.

Set it back afterwards.

### 4.7 Check-in
Check-in tab → find Bob → **Check in**.

✅ Row turns green, **Here ✓**.
✅ Overview: Attended 1, Show rate appears.
✅ You stay on the Check-in tab.

Then **+ Add walk-in** with a name and email.
✅ Appears as attended; in EspoCRM they're a **Prospect Contact** with a
registration marked **Walk-In**.

### 4.8 Recording
**Add recording** → paste any YouTube watch URL → Save.

```bash
curl -s "https://cbm-client-intake-svxs3.ondigitalocean.app/api/events/recordings" \
  | python3 -m json.tool
```
✅ The event appears with a thumbnail URL.
✅ Try `?q=grant` — search works.

Paste a non-YouTube URL to confirm it's refused with a readable message.

### 4.9 The publish gate — the important one
Untick **Publish to website**, save, then re-run 4.2.

✅ The event **disappears** from the public API.
✅ `/api/events/SLUG` returns **404**.

Then change **Show** to "All events" in the grid.
✅ You see internal calendar entries ("Operations/Team Meeting", session
copies). Confirm none of them has **Website: Live**. That is the check that
matters most — those must never reach the public page.

### 4.10 Clean up
Set your test event's **Status** to **Cancelled** (events aren't deletable by
design). Delete the test Contacts and registrations in EspoCRM if you want a
tidy instance — they're named `TEST`/`Ada Tester` etc.

---

## 5. Zoom (when you're ready)

Nothing above needs Zoom. To add it:

1. **Zoom Marketplace → Develop → Build App → Server-to-Server OAuth**, on the
   account that owns `zweb@cbmentors.org`.
2. Scopes: webinar read/write, registrant read/write, report read, user read.
3. Capture **Account ID, Client ID, Client Secret**.
4. Check it before touching the app:

```bash
ZOOM_ACCOUNT_ID=... ZOOM_CLIENT_ID=... ZOOM_CLIENT_SECRET=... \
PYTHONPATH=. uv run python scripts/probe_zoom.py
```

This verifies the credentials, the host's **webinar licence and capacity**, and
— most importantly — whether the **participant report** is readable. That last
one needs a paid plan plus the report scope, and automatic attendance depends
entirely on it. The probe exits non-zero and names any blocker.

5. Then add to the crm-test overlay's **web** component:

| Variable | Value |
|---|---|
| `ZOOM_EVENTS` | `true` |
| `ZOOM_ACCOUNT_ID` | from step 3 |
| `ZOOM_CLIENT_ID` | from step 3 |
| `ZOOM_CLIENT_SECRET` | from step 3 — **encrypted secret** |
| `ZOOM_HOST_EMAIL` | `zweb@cbmentors.org` (the default; only set to override) |

6. Zoom test pass: create a Virtual event → **Create / sync Zoom webinar** →
   confirm in Zoom that it exists, **registration is on**, and **reminder
   emails are off**. Register through the API and confirm the person appears as
   a Zoom registrant and gets the confirmation email with a join link. Edit the
   time and confirm the webinar moves. Cancel the event and confirm the webinar
   is cancelled.

---

## 5b. Phase 6 — attendance, follow-ups, backfill

All three are built and all three are **off**. Each needs something outside the
app before it can do anything.

### Attendance from Zoom (6a)

Needs **Zoom working first** (§5) — it pulls the participant report, so with no
webinars there is nothing to pull. Then, on the **worker**:

| Variable | Default | Notes |
|---|---|---|
| `EVENTS_ATTENDANCE_SECONDS` | `1800` | How often the worker looks. `0` disables. |
| `EVENTS_ATTENDANCE_GRACE_MINUTES` | `20` | Zoom does not publish the report the instant a webinar ends. |
| `EVENTS_ATTENDANCE_GIVE_UP_HOURS` | `72` | Stops retrying an event that was never held. |

An **empty report is treated as "not ready yet", never "nobody came"** — it
retries until the give-up window closes. Attendance a person set by hand is
never overwritten.

### Follow-up email (6b)

Needs `GMAIL_SYNC` + `OPS_MAILBOX` (the shared info@ identity), **and five
EspoCRM email templates named exactly**:

`EventReminder` · `EventRecordingAvailable` · `EventNoShow` ·
`EventMentorCTA` · `EventSurvey`

Until a template exists that send refuses and names it — it will never improvise
an email in CBM's name. Reminders are the only automatic send:

| Variable | Default | Notes |
|---|---|---|
| `EVENTS_REMINDERS` | `false` | The timed reminder. The other four are staff-triggered. |
| `EVENTS_REMINDER_SECONDS` | `3600` | How often the worker looks. |
| `EVENTS_REMINDER_LEAD_HOURS` | `24` | How far ahead a reminder goes out. |

⚠️ **No frontend yet.** The endpoints work (preview is the default) but the
Follow-up tab does not call them, so today this is API-only.

### YouTube backfill (6d)

One-off. Needs a **YouTube Data API v3 key** and the playlist id — used only by
this script, never by the browser.

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
YOUTUBE_API_KEY='…' YOUTUBE_PLAYLIST_ID='PL…' ESPO_DRY_RUN=false PYTHONPATH=. uv run python scripts/import_youtube_events.py          # dry run
#                                                          …--write  # apply
```

Every imported event arrives **unpublished** on purpose: a video's upload date
is not the event date, so a human checks the date and topic before it can reach
the website. Safe to re-run — anything already imported is skipped.

---

## 6. Production

**Do not do this until crm-test has been through §4.** Production needs, in
order:

1. **The CRM schema migration** — crm-test and prod currently differ by exactly
   the change list:

```bash
PYTHONPATH=. ADMIN_BASE=https://crm.clevelandbusinessmentors.org \
ADMIN_USER=admin@cbmentors.org ADMIN_PASS=... \
uv run python scripts/migrate_event_schema.py            # dry run first
PYTHONPATH=. ADMIN_BASE=... ADMIN_USER=... ADMIN_PASS=... \
uv run python scripts/migrate_event_schema.py --apply
```

   Then diff the two instances:

```bash
PYTHONPATH=. ESPO_BASE_URL=https://crm.clevelandbusinessmentors.org \
ESPO_API_KEY=... uv run python scripts/probe_events_schema.py
```

   The script is idempotent and declarative, so prod ends up identical to
   crm-test **by construction** rather than by hand — which is how the last two
   schema drifts happened.

2. **Marketing Admin Team role grants** on prod (§3 table).
3. **The flags** on `.do/app.prod-crm.yaml` (app id
   `aa1ddf69-f359-4b53-91ba-035cbed7bd53`).
4. A short repeat of §4 against prod, using clearly-labelled test records.

---

## 7. Troubleshooting

| Symptom | Cause |
|---|---|
| `/events/` 404s | `EVENTS_ENABLED` isn't set, or the deploy is older than 0.170.0. |
| Portal tile missing | Same, or you're not in the Marketing Admin Team. |
| 403 naming an entity | A CRM role grant is missing — the message says exactly which entity and operation. |
| Public API returns `{"webinars":[]}` | Nothing has **Publish to website** ticked, or the events are in the past. |
| An event won't appear publicly | Publish gate, past date, or Status = Cancelled. All three exclude it. |
| Times are hours out | Check the CRM's default timezone is America/New_York. The app stores UTC and converts. |
| A save is refused with "not a registration status" | Something sent a status outside the CRM's enum — report it, that's a bug. |
| Zoom button says Zoom isn't connected | `ZOOM_EVENTS` / credentials aren't set. Expected until §5. |

**Where to look:** app run logs (`doctl apps logs <app-id> --type run -f`) carry
a line per staff write and per registration.

---

## 8. Known gaps

Honest list, so nothing surprises you mid-test:

- **The website page is not wired up** (Phase 4). The staff app warns about this.
- **No automatic attendance** — manual only, until Phase 6.
- **No follow-up emails** — designed, not built.
- **The staff app has been driven with a stubbed session**, not a real
  non-admin login. §3's non-admin check is genuinely worth doing.
- **Thumbnails must be proxied, not hotlinked** — hotlinked `i.ytimg.com` URLs
  returned HTTP 503 during the website preview. The WordPress plugin will
  supply the proxy; the public API returns the direct URL for callers that can
  use it.
