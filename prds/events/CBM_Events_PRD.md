# CBM Events & Webinars — Product Requirements

**Status:** DRAFT for Doug's approval — nothing built.
**Author:** elicited from Doug in the 2026-07-25 interview session (his rulings
are recorded inline as **[Ruling]**).
**Companion docs:**
`CBM_Events_Implementation_Plan.md` (build plan) ·
`../../cevent-entities-crm-handoff.md` (CRM build spec).

---

## 1. Why

`https://clevelandbusinessmentors.org/webinars/` is CBM's public education
storefront. Today it is powered by machinery that lives entirely **outside** the
CRM:

| Piece | Today |
|---|---|
| Upcoming webinars | A **Google Apps Script** web app (`script.google.com/macros/s/AKfyc…/exec?action=list`) returning JSON, almost certainly backed by a Google Sheet and/or a direct Zoom call. |
| Sign-up | An Elementor modal posting First/Last/Email/Phone/Zip + an email-consent checkbox back to that Apps Script, which registers the person with Zoom. |
| Recorded library | A **direct browser call to the YouTube Data API** (`playlistItems`) with the **API key exposed in the page source**, plus a WP REST thumbnail proxy (`/wp-json/cbm-yt/v1/thumbnails`). |
| Registrant data | Zoom + a Google Sheet. |
| Attendance | Zoom reports, read by hand if at all. |
| EspoCRM | **Not involved at any point.** |

The consequences:

1. **Every registrant is an invisible lead.** People are raising their hand for
   free business education — the exact profile of a future client — and none of
   them reach the CRM, so no mentor, no report, and no follow-up ever sees them.
2. **Attendance is not a record.** There is no way to answer "did this person
   actually come?", "what has this client attended?", or "does the workshop
   program produce mentees?"
3. **The program is unmeasurable.** Show-rate, topic demand, and attendee →
   client conversion cannot be computed from any system CBM owns.
4. **Operational fragility.** An Apps Script and a Sheet with no version
   control, no monitoring, no backup story, and a publicly exposed YouTube API
   key sit on the critical path of a public page.

**This project replaces that page's data layer with an EspoCRM-backed custom
app**, so that events are first-class CRM records, registrants become Contacts,
attendance is captured automatically from Zoom, and the whole program reports
alongside mentoring.

### 1.1 Success statement

> A staff member creates an event once in a CBM app. The Zoom webinar is
> provisioned, the website updates itself, every registrant lands in the CRM as
> a Contact with a registration record, Zoom's attendance report is pulled back
> automatically, follow-up email goes out on its own, and a mentor opening a
> client engagement can see every CBM event that client's people attended.

---

## 2. Decisions taken (Doug, 2026-07-25)

These are settled. They are recorded here so the build never re-litigates them.

| # | Decision | Ruling |
|---|---|---|
| D-01 | **Website delivery** | The WordPress page **keeps its exact Elementor design**; we replace only its data source with our own JSON API. The page must look identical because it *is* the same page. |
| D-02 | **Per-event pages** | In addition, **each event gets its own shareable URL** on the marketing site (title, full description, presenter, register button) for email, social, and partner promotion. |
| D-03 | **Zoom** | **Yes — full Zoom Webinar API** via a Server-to-Server OAuth app on the CBM account: create/update webinars, push registrants, pull attendance. *(This deliberately does not disturb the standing "mentor 1:1 meetings use the mentor's own Zoom link, never a CBM Zoom account/API" ruling — that governs `CSession` meetings; this governs the public webinar program.)* |
| D-04 | **Zoom account shape** | **One shared licensed host: `zweb@cbmentors.org`.** All webinars run under it. Doug provisions the Server-to-Server OAuth app and supplies credentials (pending as of 2026-07-25 — build proceeds behind the `ZOOM_EVENTS` flag until then). |
| D-05 | **Event types in scope** | **Zoom webinars** and **in-person / hybrid events**. Zoom *Meetings* (non-webinar) and multi-session series are **out of scope for v1**. |
| D-06 | **Recorded library** | Each past event is a **CRM record carrying its recording URL**; YouTube remains only the video host. Recordings are searchable/taggable because we own the metadata. |
| D-07 | **Getting the recording out** | **Staff upload to YouTube and paste the link into the app.** No YouTube write credentials, no auto-publish. |
| D-08 | **Registrant → CRM** | **Find-or-create Contact + a registration record**, exactly like the info-request form: match on email, create if new, null-fill blanks if existing. |
| D-09 | **Contact typing** | A brand-new registrant is `cContactType=["Prospect"]`. **An existing Contact keeps whatever type it already has** — nobody is re-labelled for attending a webinar. |
| D-10 | **Presenters** | Four kinds, all supported: **CBM mentors** (CMentorProfile), **external guests** (Contact), **partner organizations** (CPartnerProfile), **CBM staff**. |
| D-11 | **Admin surface** | A **new staff app at `/events`** in this repo, following the house pattern. |
| D-12 | **Attendance depth** | **Full Zoom participant report** — attended y/n, join/leave times, minutes in session — matched to registrants by email. |
| D-13 | **Email** | **Zoom sends the registration confirmation** (the join link is per-registrant and must come from Zoom). **We send everything else** — reminders, recording link, follow-ups — from **info@** using EspoCRM email templates, logged in the CRM like all our other mail. |
| D-14 | **Follow-up automation** | All four: recording link to registrants · no-show re-engagement · mentor-connection CTA · feedback survey. |
| D-15 | **Access** | Administered by the **Marketing Admin Team** (the team that already owns info@ and the Submission Admin queue). |
| D-16 | **Registration rules** | Capacity + waitlist · registration closes at start time · one registration per email · self-service cancel link. |
| D-17 | **In-person attendance** | A **staff check-in screen** in the app: searchable roster, tap to mark arrived, plus "add walk-in" that creates the Contact on the spot. |
| D-18 | **Topics** | Ruled 2026-07-25: reuse the **`CMentorProfile.areaOfExpertise`** 31-value skills list, *not* `mentoringFocusAreas`. **⚠️ Reopened the same day** — the schema review found `CEvent.topic` already carries a curated, public-facing 10-value list built for this page. Decision pending in handoff §5; nothing else depends on it. |
| D-19 | **Consent** | The registration checkbox records **marketing opt-in plus the terms/privacy acceptances** the other four public forms capture, with policy links in the modal. |
| D-20 | **WordPress code** | A **small purpose-built CBM WordPress plugin**, version-controlled in this repo, providing shortcodes — not unversioned JS pasted into Elementor widgets. |
| D-21 | **Migration** | Backfill the **YouTube playlist** into past event records. Zoom history and the Google Sheet are **not** imported. |
| D-22 | **Reporting** | Registered-vs-attended per event · attendee → client conversion · per-person attendance history · **an events-attended list on each engagement, aggregated across all of that engagement's client contacts**. |
| D-23 | **Scope of release** | All four workstreams (public page + registration, Zoom sync + attendance, staff app, follow-up/check-in/reporting) are **in the first release**. Phasing below is build order, not scope reduction. |
| D-24 | **Event entity home** | **Use the existing `CEvent` entity** for public workshops rather than creating a new one (Doug, 2026-07-25: *"use existing event"*), gated by a new `publishToWebsite` flag defaulting to false. `CEvent` doubles as the org calendar, so that flag is load-bearing. |

**Explicitly deferred** (raised, not selected — do not build):
presenter/topic performance analytics as a dedicated report; QR self-check-in;
auto-upload of recordings to YouTube; Zoom Meeting (non-webinar) events;
multi-session series registration; importing historical Zoom/Sheet registrants.

---

## 3. Users

| Role | Team | What they do |
|---|---|---|
| **Visitor** (public) | — | Browses upcoming events, registers, searches the recorded library, watches a replay. Never authenticates. |
| **Event administrator** | Marketing Admin Team | Creates events, provisions the Zoom webinar, publishes to the site, manages registrants, runs check-in, publishes recordings, sends follow-ups, reads program reporting. |
| **Mentor** | Mentor Team | Sees, on a client engagement, which CBM events that client's people attended (context before a meeting). Read-only. Does not administer events. |
| **Presenter** | any | A mentor / partner / guest whose name appears on the event. No app access required in v1. |

---

## 4. Requirements

Numbered `EV-nn` so the plan, tests, and verification can cite them.

### 4.1 Public website (D-01, D-02, D-20)

- **EV-01** The `/webinars/` page renders **visually identically** to today —
  same hero, same two-column body ("Calendar of Upcoming Webinars" left, "Find a
  Recorded Webinar" right), same sign-up modal, same footer sections. The DOM
  class contract observed on the live page must be reproduced verbatim so the
  existing Elementor CSS continues to apply:
  `.cbm-wb`, `.month-label`, `.event-list`, `.event-item`, `.event-date`,
  `.event-date__month`, `.event-date__day`, `.event-info`, `.event-info__time`,
  `.event-info__title`, `.event-info__meta`, `.cbm-meta-text`,
  `.event-signup-btn`, `.cbm-modal-overlay`, `.cbm-modal`, `.cbm-modal-close`,
  `.cbm-modal-sub`, `.cbm-field`, `.cbm-consent-text`, `.cbm-submit-btn`,
  `.cbm-status`, `#cbm-signup-form`, `.cbm-yt`, `#cbm-yt-search-input`,
  `#cbm-yt-search-btn`, `#cbm-yt-search-msg`, `#cbm-yt-clear-search`,
  `.cbm-search-msg`, `.cbm-clear-search`, `.cbm-play-overlay`,
  `.cbm-meta-more`, `.cbm-video-frame-wrap`.
- **EV-02** Upcoming events are grouped by month with a month label
  (`JULY 2026`), each row showing month/day chip, time band
  (`2:00 PM - 3:30 PM | WEBINAR`), title, summary, and a **Sign Up** button —
  the current presentation, sourced from the CRM.
- **EV-03** Only events that are **published, in the future, and not cancelled**
  appear in the calendar.
- **EV-04** The recorded library lists past events that have a recording,
  newest first, with thumbnail, date, title, and a truncated summary with a
  **More** affordance; the search box filters by title, summary, and topic.
- **EV-05** The YouTube API key is **never exposed to the browser**. All
  YouTube/thumbnail access happens server-side.
- **EV-06** Each event has a **shareable public page** at a stable URL
  (`/webinars/<slug>`) with full description, presenter(s), date/time, location
  or "online", and a register control. It must carry correct page title,
  meta description, and Open Graph tags for social sharing.
- **EV-07** The public page must **degrade safely**: if our API is unreachable,
  the site shows the last successfully cached payload (and, failing that, a
  neutral "check back soon" message) — never a broken layout or an error dump.
- **EV-08** The website integration ships as a **versioned WordPress plugin** in
  this repo, exposing shortcodes for the calendar, the recorded library, and the
  sign-up modal, plus the per-event page route. No API keys or business logic
  live in page content.

### 4.2 Registration (D-08, D-09, D-16, D-19)

- **EV-10** A visitor registers with First Name, Last Name, Email, Phone, Zip
  Code and a consent checkbox — the fields collected today. Email is required
  and validated; the others follow current behavior.
- **EV-11** A registration is **captured durably before any external call**
  (the existing V2 durable-capture pipeline) and delivered asynchronously, so a
  Zoom or CRM outage can never lose a registrant. The visitor gets an immediate
  confirmation screen.
- **EV-12** Delivery performs, idempotently and resumably:
  1. find-or-create the **Contact** (match on email; null-fill blanks on an
     existing Contact, never overwrite);
  2. new Contacts get `cContactType=["Prospect"]`; **existing Contacts keep
     their type**;
  3. record consent — `cMarketingOptIn`, `cTermsOfUseAccepted`,
     `cPrivacyPolicyAccepted`, `cCodeOfConductAccepted` — setting them **true
     only**, never flipping an existing value to false;
  4. create the **CEventRegistration** linked to the event and the Contact,
     holding the submitted values as a snapshot;
  5. **push the registrant to Zoom**, storing the returned registrant id and
     per-registrant join URL. Zoom then emails its confirmation with the join
     link.
- **EV-13** **One registration per email per event.** A repeat submission
  updates the existing registration and re-sends the join link rather than
  creating a duplicate.
- **EV-14** **Registration closes at event start.** The Sign Up control
  disappears and the endpoint refuses late registrations with a readable
  message.
- **EV-15** **Capacity and waitlist.** An event may declare a seat cap; beyond
  it, registrants are recorded as **Waitlisted** and are not pushed to Zoom.
  When a seat frees (cancellation or a raised cap), the longest-waiting
  registrant is promoted automatically, pushed to Zoom, and emailed.
- **EV-16** **Self-service cancel.** Every registrant gets a cancel link that
  works without login, marks the registration Cancelled, removes them from Zoom,
  and frees the seat. The link must be unguessable and event/registration
  specific.
- **EV-17** The public registration endpoint carries the same abuse protections
  as the intake forms: honeypot field, per-IP rate limit, request body cap, and
  readable validation errors. No CAPTCHA.
- **EV-18** Staff can register someone manually from the admin app (phone
  registrations, walk-ins), producing the identical record shape with the source
  recorded as staff-entered.

### 4.3 Zoom integration (D-03, D-04)

- **EV-20** The app authenticates to Zoom with **Server-to-Server OAuth**
  (account credentials grant), caching the token and refreshing on expiry.
  Credentials are deploy-time secrets, never in the repo.
- **EV-21** Publishing an online event **creates the Zoom webinar** under the
  configured host with registration enabled and automatic approval, storing the
  webinar id, join URL, and registration URL on the event.
- **EV-22** Editing a published event's title, time, or duration **patches** the
  Zoom webinar. Cancelling the event **cancels** the Zoom webinar and notifies
  registrants.
- **EV-23** An event may instead be **linked to an existing Zoom webinar** by
  id, for webinars created directly in Zoom (this is also the migration path for
  anything in flight at cutover).
- **EV-24** **Zoom's own reminder emails are disabled** on app-created webinars;
  reminders come from CBM (D-13) so the branding, timing, and CRM logging are
  ours and registrants never get two of everything. Zoom's *confirmation* email
  stays on — it carries the unique join link.
- **EV-25** All Zoom calls are resilient: rate-limit (429) and 5xx responses
  back off and retry; a Zoom failure never fails a registration or a save — it
  surfaces as a warning and is retried by the worker.

### 4.4 Attendance (D-12, D-17)

- **EV-30** After an online event ends, the worker **pulls the Zoom participant
  report** and matches participants to registrations **by email**, recording
  attended/no-show, first join, last leave, and total minutes.
- **EV-31** The pull retries on a schedule until it succeeds or the event ages
  out of a give-up window (Zoom reports are not instantly available and can lag
  the event end). Failures alert; they never break anything else.
- **EV-32** Participants who attended but match **no registration** (someone
  forwarded a link, or a panelist) are recorded as attendees and flagged as
  unmatched for staff review rather than silently dropped.
- **EV-33** For in-person and hybrid events, a **check-in screen** works on a
  phone: search the roster, tap to mark arrived, and **add a walk-in**, which
  creates the Contact and registration on the spot.
- **EV-34** Staff can correct any attendance value by hand; a manual correction
  is never overwritten by a later automatic pull.
- **EV-35** Attendance counts and show-rates are **computed on the fly, never
  stored** as denormalized totals (the funder-contributions precedent).

### 4.5 Recordings (D-06, D-07, D-21)

- **EV-40** After an event completes, the admin app prompts for the recording:
  staff paste the YouTube URL, and the app derives the video id and thumbnail.
- **EV-41** A past event with a recording appears in the public recorded library
  with its CRM-owned title, summary, date, and topics.
- **EV-42** A one-time migration imports the existing YouTube playlist as past
  event records, preserving title, description, publish date, and video id, and
  flagging each as needing a staff date/topic review (the video publish date is
  not necessarily the event date).

### 4.6 Staff app `/events` (D-11, D-15)

- **EV-50** A team-gated app at `/events`, mounted like the other staff tools,
  gated per request on the Marketing Admin Team (admins pass), 401 →
  portal redirect, 403 naming the team. A portal tile appears for entitled users.
- **EV-51** An **events grid** in the house style: full-height, sticky header,
  sortable and resizable columns, live full-text search, status filter, and a
  right-click row menu. Columns: title, date/time, type, status, registered,
  attended, show-rate, recording, presenter.
- **EV-52** An **event detail** screen with tabs: **Overview** (facts, actions,
  live counts) · **Registrants** (grid, per-row actions, CSV export) ·
  **Check-in** (roster + walk-ins) · **Follow-up** (what's been sent, what's
  queued, send now).
- **EV-53** A grouped **event editor** driven by a single field spec that serves
  as both the form layout and the server-side write whitelist (the
  `SESSION_FIELDS` / `CONTRIBUTION_FIELDS` pattern); enum options and required
  flags read live from CRM metadata; only changed fields are sent.
- **EV-54** Explicit, confirmable actions: **Publish to website**, **Create /
  sync Zoom webinar**, **Pull attendance now**, **Add recording**, **Send
  follow-up**, **Cancel event**. Buttons are never disabled — they validate on
  click and explain what's missing (standing product ruling).
- **EV-55** Per-registrant actions: resend join link, cancel, promote from
  waitlist, mark attended, open the Contact.
- **EV-56** Every mutating action is recorded through the standard action-log
  path (on-record stream note + reporting row), so event administration has the
  same audit trail as the rest of the system.

### 4.7 Email (D-13, D-14)

- **EV-60** All CBM-sent event email goes out as the **shared info@ identity**,
  rendered from **EspoCRM email templates** so staff can edit wording without a
  deploy, and written back to the CRM as Email records against the recipient
  Contact (the existing send path).
- **EV-61** Sends supported: **reminder** (configurable lead time before start,
  carrying the registrant's own join link), **recording available**,
  **no-show re-engagement**, **mentor-connection CTA**, **feedback survey**.
- **EV-62** Each send is **once-per-registrant-per-event-per-kind** — no
  duplicates on retry, redrive, or a second click.
- **EV-63** Follow-ups honor cancellation and opt-out: a cancelled registrant
  and an opted-out Contact are excluded.
- **EV-64** An administrator can preview and manually trigger any follow-up for
  an event, and can see exactly who received what and when.

### 4.8 Reporting (D-22)

- **EV-70** Per event: registered, waitlisted, cancelled, attended, no-show,
  show-rate, average minutes attended.
- **EV-71** **Person history**: on a Contact (directory contact page), every
  event they registered for and attended, with dates and status.
- **EV-72** **Engagement rollup**: on a client engagement, an aggregated list of
  events attended **across all of that engagement's contacts** — deduplicated,
  newest first, showing which of the engagement's people attended each event.
  *(Doug's explicit requirement.)*
- **EV-73** **Attendee → client conversion**: for a chosen period, how many
  event attendees subsequently became clients (a client profile / engagement
  created after their first attended event), with the underlying list.
- **EV-74** Program totals over a period: events held, unique attendees,
  repeat-attendee rate.

### 4.9 Non-functional

- **EV-80 Availability.** The public read endpoints are cached and must survive
  our app being down (EV-07). The registration write path is durable-capture
  first (EV-11).
- **EV-81 Performance.** Public list endpoints respond from cache in
  well under a second; the WordPress side caches too, so normal page loads make
  no live call to us.
- **EV-82 Privacy.** Public endpoints expose **no registrant PII** — not names,
  not counts of who, only a seats-remaining number where capacity applies.
  Registrant data is visible only behind the team gate.
- **EV-83 Security.** Zoom credentials are encrypted deploy secrets. Cancel
  links are cryptographically derived and compared in constant time. The public
  write endpoint is rate-limited and body-capped.
- **EV-84 Feature gating.** The whole feature is behind a flag, and every CRM
  write is feature-detected, so the app can deploy safely **before** the CRM
  entities exist (the standing pattern) and roll back instantly.
- **EV-85 Timezone.** Events are authored and displayed in America/New_York and
  stored as UTC in the CRM. The public API returns **both** the ISO-UTC instant
  and pre-formatted local display strings so the website does no timezone math.
- **EV-86 Observability.** Sync jobs log per-pass totals and alert on repeated
  failure through the existing alerting path.

---

## 5. Data model (summary)

**`CEvent` and `CEventRegistration` already exist on crm-test** (schema read
2026-07-25). The design below therefore *adopts the as-built schema* rather than
inventing one. The review and the exact change list live in
**`../../cevent-entities-crm-handoff.md`** — read that document, not this
summary, before touching the CRM.

### `CEvent` — "Event" (exists; scope type **Event**, so it is on the CRM calendar)
Already built: title, `description` (the calendar-card blurb), `eventOverview`
and `eventSyllabus` (full content), `format` (In-Person / Virtual / Hybrid — the
field the Zoom logic keys on), `eventType` (Online Webinar / In Person Event /
Online Course), `status`, start/end/duration, `location`, `venueCapacity`,
`topic`, `eventGraphic`, `recordingUrl`, `virtualMeetingUrl`, `registrationUrl`,
`eventFee`, plus links to `presenters` (Contacts), `sponsorProfiles`,
`resources`, and `registrations`.

To add: **`publishToWebsite`** (the gate that keeps internal calendar entries
off the website), `slug`, `zoomWebinarId`, `registrationCloses`, a `Cancelled`
status option, and a `partnerHost` link.

**`CEvent` is currently also the organisation's calendar entity** — its 92
records are internal team meetings and mentoring-session mirrors, not workshops.
Per D-24 the public programme **shares this entity**, so `publishToWebsite` is
the only thing keeping internal meetings off the website: every website-facing
query must filter on it.

### `CEventRegistration` — "Event Registration" (exists, **0 records**)
Already built: `event` and `contact` links (the `contact` reverse link is
exactly what delivers per-person attendance history), a single
`attendanceStatus` (Registered / Attended / No-Show / Cancelled),
`registrationSource`, `registrationDate`, `remindersSent`, `confirmationSentAt`,
`postEventFollowUpSentAt`, `cancellationDate`/`Reason`, `specialRequests`,
`lastCommunicationBouncedAt`.

To add: `email` (dedupe + Zoom-report matching key), `firstName`/`lastName`,
`joinTime`/`leaveTime`/`minutesAttended`, `attendanceSource`,
`zoomRegistrantId`, `zoomJoinUrl`, `marketingOptIn`, `followUpsSent`,
`unmatchedParticipant`; plus a `Waitlisted` option on `attendanceStatus` and
`Staff`/`Import` on `registrationSource`.

⚠️ Four fields are `readOnly` — two of them **required *and* readOnly** — which
blocks API writes and would break the first live registration. Handoff §4.

### Why two entities and not three
Attendance is an attribute of a registration, not its own record: a walk-in is
simply a registration created at check-in, and the existing schema already
models it that way with one `attendanceStatus` field. This keeps every question
("who registered", "who came", "what did this person attend") answerable from
one place, and keeps the Contact-side history a single reverse link.

### Computed, never stored
Registration counts, attendance counts, show-rates, seats remaining, and every
rollup are **derived at read time**. No totals are persisted, so they can never
drift (the funder-contributions ruling applied consistently).

---

## 6. Public API contract (draft)

Served by our app, consumed by the WordPress plugin (which proxies and caches
server-side, so visitors' browsers never call us directly and no CORS is
required).

| Endpoint | Purpose |
|---|---|
| `GET /api/events/upcoming` | Published, future, non-cancelled events. **Deliberately returns today's Apps Script keys** (`topic`, `summary`, `date`, `month`, `monthShort`, `day`, `time`, `durationHrs`, `webinarId`) **plus** `slug`, `url`, `eventType`, `location`, `seatsRemaining`, `registrationOpen`, `startsAtUtc` — so the existing rendering logic ports with near-zero change and new capability is additive. |
| `GET /api/events/recordings?q=&limit=` | Past events with recordings: `title`, `date`, `summary`, `videoId`, `thumbnailUrl`, `url`, `topics`. Server-side search over title/summary/topics. |
| `GET /api/events/{slug}` | One event, full detail, for the per-event page (EV-06). |
| `POST /api/events/{slug}/register` | Register. Returns `{status:"received", reference}` immediately (EV-11). Honeypot + rate-limited. |
| `GET/POST /api/events/registrations/{token}/cancel` | Self-service cancel (EV-16). |

---

## 7. Risks and open items

| # | Risk / unknown | Handling |
|---|---|---|
| R-1 | **We have not seen the Apps Script source.** It may do more than we've inferred (e.g. it may be what creates webinars, or hold registrant history). | Doug to share the script + Sheet before Phase 1 build. Its behavior is the parity baseline. |
| R-2 | **Zoom plan and scopes.** Participant reports and the registrant API require a paid plan with webinar licensing and the right admin scopes. | Phase 0 prerequisite checklist, verified with a read-only probe before any build. |
| R-3 | **Zoom report latency.** Participant reports are not available the instant an event ends. | Retry on a schedule inside a give-up window (EV-31) — the transcript-retrieval pattern already in the codebase. |
| R-4 | **Double email.** Zoom's reminders plus ours would be duplicates. | EV-24: disable Zoom reminders on app-created webinars; verified on the first live event. |
| R-5 | **Cutover on a live public page.** | The Apps Script stays live until parity is verified; the plugin ships behind a switch with an instant revert. Cutover is a WordPress page change, reversible in a minute. |
| R-6 | **YouTube backfill dates.** Video publish date ≠ event date. | Imported events are flagged for staff date review (EV-42). |
| R-7 | **Exposed YouTube API key** in the current page source. | Fixed as a side effect (EV-05); the key should be rotated after cutover. |
| R-8 | **Two different contact addresses on the live page** — the "Interested in Presenting" section says `info@cbmentors.org` while the footer says `info@clbmentors.org` (extra "l"). One of them is wrong and may be bouncing mail today. | Flagged for Doug — a content fix on the site, independent of this project. |
| R-9 | **Capacity/waitlist for webinars.** Zoom webinars have their own capacity limits per licence. | App capacity is CBM's business rule; the Zoom licence ceiling is documented in Phase 0 and the app warns if capacity exceeds it. |

### Assumptions to confirm (not blocking design)
1. Event volume is on the order of a few per month, not hundreds — the design is
   correct either way, but it justifies "computed, never stored".
2. All events are **free** — no payment handling anywhere in scope.
3. Attendance for hybrid events = Zoom report **plus** door check-in, merged.
4. Registration collects no accessibility/dietary/company fields today; adding
   fields later is a field-spec change, not a redesign.

---

## 8. Out of scope (v1)

Payments/ticketing · CEU or certificate issuance · public user accounts ·
calendar (.ics) subscriptions *(easy add later)* · sponsor/exhibitor management ·
multi-language · SMS reminders · Zoom Meeting-product events · multi-session
series registration · automated YouTube publishing · importing historical Zoom
and Google Sheet registrant data.
