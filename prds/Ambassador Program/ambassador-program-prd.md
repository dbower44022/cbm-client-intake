# Ambassador Program — product requirements (build document)

Last Updated: 11-21-26 03:01 · Revision 0.2 · Status: approved 11-21-26; built as v0.360.0

This is an implementation document for the cbm-client-intake applications,
so it names the CRM (EspoCRM) and its record types. The decisions behind it
are Doug's, taken 11-21-26 and recorded one by one in
`prds/Ambassador Program/ambassador-program-decisions.md` (AM1 to AM7). This
document does not reopen them. Where it adds something the decisions did not
cover, the addition is marked **Proposed** and listed in § 14 for Doug's
confirmation before the build starts.

## 1. Purpose

CBM's Ambassador Program asks mentors to report the work they do to spread
the word: sharing posts, referring entrepreneurs, inviting people to events,
making community introductions, representing CBM at events and spotting
success stories.

A volunteer proposed collecting those reports with a Google Form and a
Google Sheet, imported into the CRM by hand once a week
(`CBM_Ambassador_Pilot_Form_and_CRM_Handoff (1).docx`, this folder). Doug
ruled that out on 11-21-26: the report is built into the applications
instead.

Building it in removes the hand import and the three problems the proposal
spent most of its length managing: matching an email to a mentor, avoiding
a double import, and retrying a follow-up task that failed. It also lets a
report do work the form could not:

- record the contact on the right partner, funder or client;
- create a referred person in the CRM at once, credited to the mentor;
- carry that credit onto the client's engagement, or the partner's or
  funder's profile, when they later apply by any route.

## 2. Who uses it

| Person | What they do | Gate |
|---|---|---|
| A mentor (every Mentor Team member, AM6) | Logs activities; sees and corrects their own | `AMBASSADOR_ALLOWED_TEAMS`, default Mentor Team |
| The program owner and designees | Receive follow-up alerts; work the review list; read every activity | `AMBASSADOR_REVIEW_TEAMS`, default Marketing Admin Team |
| A partner's or funder's assigned manager | Is told when an ambassador met one of their contacts | none — an email |
| An engagement's assigned mentor | Is told when an ambassador met their client's contact | none — an email |
| Partner and Funder Management teams | Work referred Candidate profiles in their own lists | their existing gates |
| Analytics Admin Team and the review team | Read the Ambassador Program analytics page | Analytics page visibility |

There is no pilot team (AM6, option C). The switch `AMBASSADOR_PROGRAM`
keeps the whole program dark until it is turned on.

## 3. The activity page — `/ambassador/`

### 3.1 Getting in (AM1)

1. The mentor opens the page from a phone bookmark, the portal tile
   "Ambassador Activity", or a "Log an activity" button on the home page.
2. The page asks the server whether the sign-in cookie is valid: signed by
   the server and carrying a working CRM sign-in.
3. Valid: the form shows at once.
4. Not valid: the page shows the **shared sign-in box** in place — CRM
   username, password, "Forgot your password?" — then the form. It never
   sends the mentor to the portal and back.
5. The sign-in box is one shared piece, `frontend/shared/signin.js` and
   `signin.css`, used by both the portal and this page. The portal's own
   sign-in is moved onto it, so a change to sign-in lands in both.
6. The cookie is the one every application shares, so signing in here signs
   the mentor in everywhere.

The page loads `busy.js` first and `textsize.js` second, uses `{{org}}` and
`{{abbr}}` for every mention of the organization, and has no width cap. It
is built for a phone first: large tap targets, the date defaulting to today.

### 3.2 The form

| # | Question | Shown when | Required | Notes |
|---|---|---|---|---|
| 0.2 | 11-21-26 03:01 | Claude (Claude Code) | § 14 approved; § 15 records the build's differences. |
| 1 | When did you do it? | always | yes | Date only, the shared date control's date half; defaults to today; not in the future |
| 2 | What did you do? | always | yes | Six large buttons, § 3.3 |
| 3 | Who did you talk to? | every activity except "liked or shared a post" | for a referral, yes; otherwise optional | The contact block, § 3.4 |
| 4 | This person is… | when a contact is given | yes | A potential client · a potential partner · a potential funder · from an organization we already work with · someone else (AM5a). Answered automatically when the lookup finds a partner (AM3a item 4); the mentor can change it |
| 5 | Did they agree to hear from {{abbr}}? | when the answer to 4 is a potential client, partner or funder | no | Yes sets the Contact's marketing opt-in; nothing clears it (AM5 item 5) |
| 6 | Does {{abbr}} need to follow up? | always | yes | Yes / No (AM4) |
| 7 | Anything we should know? | always | when 6 is Yes | Plain text. The hint asks for an event or organization name, and says to keep client and mentoring details out |

The mentor's email is not asked: the sign-in says who they are.

On save the mentor sees the same confirmation every time: "Thanks for
helping more people discover {{org}}. Your report was saved." When
follow-up was asked for, a second line says the program team will review
it. The confirmation never says whether, or where, the contact matched
(AM3 item 3).

### 3.3 The six activities

Stored as the `activityType` enum on the activity record; the values are
the labels.

1. I liked or shared a {{abbr}} post
2. I referred someone to {{abbr}} — **Proposed** wording (§ 14 item 2); the
   proposal's was "I referred an entrepreneur", but AM5a extends referrals to
   partners and funders
3. I invited someone to an event
4. I made a community introduction
5. I represented {{abbr}} at an event
6. I identified a success story

### 3.4 The contact block and the lookups (AM3, AM3a)

Fields: email, name (first and last), organization, title, phone. All are
looked up from the CRM **as the mentor**, under the mentor's own sign-in.
The production Mentor Role reads every Contact and every Company (08-31-26
roles capture), so the lookups show nothing the mentor cannot already see in
Workspace Directories. Re-read the live roles on each CRM before the build;
§ 13 phase 3.

1. **Email entered and it belongs to a known Contact:** name, organization,
   title and phone are filled in, each marked "From our records".
2. **Email new, but its domain matches a company:** the organization is
   filled in.
   - A domain matches on the company's website address, compared with
     `core/crm_upsert.website_key`, and on the email domains of the
     company's existing contacts.
   - More than one company matches: the mentor picks from a short list.
   - A free-mail domain never matches a company. The list is the setting
     `AMBASSADOR_FREE_MAIL_DOMAINS`, seeded with the common consumer and
     internet-provider domains.
3. **Name search:** from three letters typed in the name box, matching
   Contacts appear to pick from (name, organization). Picking one fills the
   block as in item 1.
4. **The matched company is a partner:** question 4 is answered "from an
   organization we already work with". Partner status is not confidential.
5. **A CBM member's address** (a Contact typed Mentor, or an address on
   `MENTOR_EMAIL_DOMAIN`): the block says "That's a {{abbr}} member" and the
   contact is not recorded (open item #77's rule).
6. **Never shown:** a contact's type, client status, engagement, mentor, or
   any record the lookup touched other than the Contact and Company fields
   listed above.
7. **Overrides:** every filled field stays editable. "Not this person"
   clears the match and the filled fields. A mentor's correction is saved on
   the activity only and **never changes the CRM record** (AM3a item 3); the
   review list shows what was corrected.

### 3.5 My activity (AM7)

Below the form, a "My activity" list of the mentor's own records, newest
first, on the shared grid (`frontend/shared/grid.js`): date, activity,
contact name, follow-up (Requested / Done), and for a referral its outcome
(Applied / Not yet).

- The mentor may correct the date, activity and note of their own entries
  for `AMBASSADOR_EDIT_DAYS` days (default 14). The button is always
  visible; after the window, a click says why it cannot be changed.
- The mentor cannot undo a Contact, Company or profile the system created.
  The note under the list says to ask the program team.
- No one else's activity, and no chapter figures, are shown.

## 4. What happens when an activity is saved

### 4.1 Capture first, then deliver

**Proposed** (§ 14 item 1). The decisions say each save is made as the
mentor (AM1 item 6) and that each submission is captured in the
application's database before any CRM write (AM2). Both hold if the work is
split as follows:

1. **Capture, as the request is made.** The server takes the mentor's
   identity from the sign-in — the User id and the mentor's
   `CMentorProfile` id, resolved server-side, never from the browser — and
   writes the submission to the durable store (`core/store.py`) under the
   slug `ambassador`, with a submission token for idempotency. The mentor
   gets the confirmation once this row is written. If the CRM is down, the
   report is still safe.
2. **Deliver, in the worker.** The delivery worker runs the chain in § 4.2
   under the organization-wide API key, resumably (`core/resumable.py`), with
   the standard retries. A half-finished chain resumes rather than
   duplicating, which is the retry problem the proposal set out to manage.
3. **Who it is recorded as.** The activity is linked to the mentor's
   profile and carries the mentor's User in its assigned users, so the
   Mentor Role's "own" grant lets the mentor read and correct it. Every CRM
   write in the chain is recorded in the action log (`core/action_log.py`)
   with the mentor as the actor.
4. **A mentor's correction from My activity** is a plain save as the
   mentor, under their own permissions.

The cost of this split: the CRM's own "Created by" on the activity is the
API user, not the mentor. The mentor link, the assigned user and the action
log name the mentor instead.

### 4.2 The delivery chain

1. **Create the activity record** (§ 7.1).
2. **Classify the contact**, when one was given and is not a CBM member.
   Under the organization-wide key, find the Contact by email. If there is
   no email, or no match, try the picked Contact id from the lookup.
3. **Route** by what was found and what the mentor said:

| Found | Mentor said | What happens |
|---|---|---|
| A contact of a partner profile | any | An "Ambassador contact" session on that partner (§ 4.3); its manager (`partnerManager`) is emailed |
| A contact of a funder profile | any | The same on the funder; its manager (`cBMSponsorManager`) is emailed |
| A contact of a client, with a current engagement | any | An "Ambassador contact" session on the client's current engagement; the engagement's assigned mentor is emailed |
| No match | potential client | The referral creation in § 4.4 |
| No match | potential partner or potential funder | The referral creation in § 4.5 |
| No match | from an organization we already work with | Held for review, "Not matched" |
| No match, no email, or no name | someone else | Held for review only if follow-up was asked for; otherwise the activity stands on its own |
| More than one match | any | Held for review, "More than one match" |

   "Current engagement" means the most recent engagement in
   `ACTIVE_CLIENT_STATUSES`; with none, the most recent of any status.
   A contact that belongs to both a partner and a client gets both
   sessions.

4. **A known person who is also a referral.** When the mentor said
   potential client, partner or funder and the Contact already exists, no
   record is duplicated. Referred by is filled on the Contact only when
   empty, so the first mentor to refer someone keeps the credit (AM5
   item 3). For a partner or funder referral where the company already has
   a profile of that kind, no new profile is made; the existing one is
   routed as in the table.
5. **Follow-up**, when asked for (§ 5).
6. **Notifications**, all from the shared mailbox (`OPS_MAILBOX`), each
   recorded so it is sent once only. Wording lives in one module,
   versioned like the feedback emails.

### 4.3 The "Ambassador contact" session type

A new `CSession.sessionType` value. An ambassador session has status
Completed, the activity date as its date, the ambassador as its recorded
manager, the Contact as its attendee, and the activity's note.

An ambassador's chat at a networking event must not count as mentoring.
**Every count of sessions ignores this type.** The build audits each one,
starting from this list, found 11-21-26:

- `sessions/service.py` — engagement activation (Assigned to Active on a
  Completed session).
- `feedback/` — the session milestone survey (the Nth Completed session).
- `core/engagement_close.py` — the closing rules.
- `portal/needs.py` — "no contact for N days" and the session rows of the
  home page's Needs you list.
- `analytics/records.py` — every Completed-session metric, on engagements,
  partners, contacts, clients and companies.
- `assignments/service.py` — status and capacity counts.
- `sessions/gcal.py` — no calendar event is created for an ambassador
  session.
- `sessions/transcripts.py` — no transcript is looked for.

The audit is a test: a list of the places that read sessions, each of which
is checked to exclude the type. A new place that counts sessions without
saying whether it excludes the type fails the test.

The session shows in the engagement's or partner's Sessions tab, labelled
"Ambassador contact by <mentor>", so the assigned mentor or manager sees it.

### 4.4 A referred potential client (AM5)

1. Find or create the **Company**, when an organization was given, by the
   rules every place that creates records follows (same name reused; a
   different website at the same name held for review, never created).
   The company gets no `cCompanyType` until it applies — **Proposed**,
   § 14 item 4.
2. Find or create the **Contact** by email, typed `Prospect`, with
   **Referred by** set to the mentor's profile, linked to the Company.
   The marketing opt-in is set only on a yes to question 5.
3. Stamp the creator and the team on both, as the staff screens do.
4. Record a **lead** (`CProspect`) with Lead Source "Ambassador referral",
   Converted at once, through `campaigns/attribution.record_lead`, as every
   public form does (ruling 48).
5. **When they later apply as a client by any route**, the client intake
   delivery finds the Contact by email, as it does today. The new step:
   when the Contact's Referred by is set and the new engagement has no
   referring ambassador, delivery copies it to `CEngagement` Referred by,
   then emails the mentor "Your referral applied". The activity's outcome
   becomes Applied.

### 4.5 A referred potential partner or funder (AM5a)

1. Company, Contact and lead exactly as in § 4.4, with the Contact typed
   `Prospect` — **Proposed**, § 14 item 4.
2. Create a **partner profile** (`CPartnerProfile`, `partnershipStatus`
   Candidate) or **funder profile** (`CSponsorProfile`, `funderStatus`
   Candidate — the value may need adding, § 7.4), linked to the Company and
   the Contact, with Referred by set to the mentor and **Source** set to
   Ambassador referral, stamped with the domain team so it shows at once in
   Partner Management or Funder Management. Partner and funder are one code
   path, keyed by `DomainConfig` (Doug, 10-11-26). The tie goes through
   `core/partner_links.py` like every other partner or funder tie.
3. The managing team is emailed.
4. **When the organization later applies** through the public partner or
   funder form, the form reuses that Candidate profile instead of creating a
   second, keeps Referred by, and fills the empty fields from the
   application. The reuse is narrow: only a Candidate profile whose Source
   is Ambassador referral and which has no assigned manager. Every other
   case still creates a new profile, as the ruling that a company may hold
   many profiles allows. The mentor is emailed "Your referral applied".

## 5. Follow-up and the review list (AM4)

### 5.1 Follow-up

- The activity carries `followUpRequested`, `followUpDone`,
  `followUpDoneAt`, `followUpNote` and `followUpDoneBy`.
- On save with a request, one email goes to each member of the review team
  (`AMBASSADOR_REVIEW_TEAMS`); a team with no members falls back to
  `ALERT_EMAIL_TO`. A failed alert retries hourly for a day, as feedback
  alerts do.
- The home page's Needs you list gets an "Ambassador follow-up" row for
  review-team members, opening the oldest open request.
- **Mark follow-up done** needs a note, is saved as the staff member, and
  records the old and new values in the action log.
- The mentor is emailed when their request is marked done, with the note —
  **Proposed**, § 14 item 5.

### 5.2 The review list — `/ambassador/review`

One list for the review team, on the shared grid, with two kinds of row:

1. **Follow-up requested** — action: Mark done.
2. **Contact to review** — "Not matched", "More than one match", or "The
   mentor corrected our records". Actions:
   - **Link to an existing partner, funder or client** — then the routing
     of § 4.2 runs for it (the session and the email).
   - **Create as a new referral** — the creation of § 4.4 or § 4.5, as
     chosen.
   - **Dismiss**, with a reason.
   For a correction, the row shows the CRM value and the mentor's value side
   by side. Applying it to the CRM is a staff decision made in the record's
   own screen, never from this list.

Each action is recorded in the action log. A row leaves the list when it is
acted on.

### 5.3 On the mentor's record

Mentor Administration's mentor record gets a read-only **Ambassador** tab
listing that mentor's activities — **Proposed**, § 14 item 6.

## 6. Reporting — the Ambassador Program analytics page (AM7)

A built-in Analytics system page, visible to the Analytics Admin Team and
the review team. Mentors see no figures. By month:

1. Active ambassadors — mentors with at least one activity.
2. Activities by type.
3. Open follow-ups.
4. Contacts awaiting review.
5. Referrals made, and referrals that applied, each split by client,
   partner and funder.
6. Ambassador contacts with existing partners, funders and clients.

One submission is one reported activity, as the proposal says. The
Ambassador Activity record type is also offered in the metric builder.

## 7. CRM changes

Applied through the API from a CRM plan (`crm-plans/ambassador.json`) and a
migration script in the established pattern, dry-run by default, verified
against live metadata, with a handoff document
(`ambassador-activity-crm-handoff.md`) for anything that must be done by
hand. Order: the Business Mentors Association's CRM, then crm-test,
production, and the chapters. The `espo-crm-changes` skill governs the
work.

### 7.1 New record type: Ambassador Activity

Typed `AmbassadorActivity`, so EspoCRM stores it as `CAmbassadorActivity`.
Its fields sit on a custom record type, so they are stored as typed.

| Field | Type | Notes |
|---|---|---|
| `name` | varchar | Built: "<activity> — <mentor> — <date>" |
| `activityDate` | date | Required |
| `activityType` | enum | The six values, § 3.3 |
| `mentorProfile` | link → `CMentorProfile` | Required; the ambassador |
| `contact` | link → `Contact` | The matched or created contact |
| `company` | link → `Account` | The matched or created company |
| `personKind` | enum | Potential client · potential partner · potential funder · existing organization · someone else |
| `enteredName`, `enteredEmail`, `enteredOrganization`, `enteredTitle`, `enteredPhone` | varchar / email / phone | What the mentor submitted, kept as the audit of the report |
| `corrections` | text | What the mentor changed from our records, readable |
| `matchStatus` | enum | Matched · Created · Not matched · More than one match · Member · No contact |
| `routedTo` | text | Readable: which session, profile or record the chain wrote |
| `marketingAgreed` | bool | Question 5 |
| `note` | text | Question 7 |
| `followUpRequested`, `followUpDone` | bool | |
| `followUpDoneAt` | datetime | |
| `followUpNote` | text | |
| `followUpDoneBy` | link → `User` | |
| `referralOutcome` | enum | Not a referral · Not yet · Applied |
| `receivedAt` | datetime | When the mentor submitted |
| `submissionReference` | varchar | The durable store's reference, the stable id the proposal asked for |
| `assignedUsers` | standard | The mentor's User, for the "own" grants |

None of these fields is Read-only in Entity Manager (the trap of ruling 40:
a Read-only field drops every API write). Staff are kept off fields with
field rules on their roles instead.

### 7.2 Referred by

- `Contact` → `CMentorProfile`, belongsTo. Typed unprefixed on the
  Contact side, so it is stored as `cReferredBy`. Verify in
  `GET /Metadata` after building.
- `CEngagement` → `CMentorProfile`, belongsTo, `referredBy`.
- `CPartnerProfile` and `CSponsorProfile` → `CMentorProfile`, belongsTo,
  `referredBy`.
- `CPartnerProfile` and `CSponsorProfile` get a `source` enum with
  Ambassador referral among its values, if no equivalent field exists — to
  check on the live metadata.

### 7.3 New option values

- `CSession.sessionType`: Ambassador contact.
- `CProspect.leadSource`: Ambassador referral, and `SOURCE_AMBASSADOR` in
  `campaigns/config.py`.
- `CSponsorProfile.funderStatus`: Candidate, if it is not there.

### 7.4 Roles

- **Mentor Role:** `CAmbassadorActivity` read own, edit own, create no,
  delete no. Its field rules let the mentor edit only `activityDate`,
  `activityType` and `note`; the edit window is the application's rule.
- **The review team's role (Marketing Admin Role by default):**
  `CAmbassadorActivity` read all, edit all, no delete.
- **The organization-wide API role:** `CAmbassadorActivity` create, read
  and edit all; Contact, Account, `CProspect`, `CPartnerProfile`,
  `CSponsorProfile` and `CSession` create — check each against the roles
  standard, including Assignment Permission all with Team read.
- Check each role twice, as the API key and as a real non-admin.

### 7.5 Sandbox

`CAmbassadorActivity` is a new table, so crm-test's nightly reset needs a
seeder stage and a re-baseline (memory: tables newer than the baseline are
truncated nightly). The Association's CRM restores on demand only; its
baseline re-capture is already owed (`OPEN-ITEMS.md` #87) and must be done
before this build is checked there.

## 8. Changes to existing code

1. **Portal sign-in** moves onto the shared sign-in box (§ 3.1).
2. **Home page:** the "Log an activity" button for Mentor Team members; the
   "Ambassador follow-up" Needs you row for the review team
   (`portal/needs.py` rules, `portal/router.py` items).
3. **Portal tile:** Ambassador Activity.
4. **Client intake delivery** (`forms/client_intake/orchestrator.py`):
   copy Referred by from the Contact to the new engagement; mark the
   activity Applied; email the mentor (§ 4.4 item 5).
5. **Partner and funder form delivery** (`forms/partner/orchestrator.py`,
   `forms/sponsor/orchestrator.py`): reuse an ambassador-referred Candidate
   profile (§ 4.5 item 4). One shared helper, not two copies.
6. **Every session count** excludes the Ambassador contact type (§ 4.3).
7. **Mentor Administration:** the Ambassador tab (§ 5.3).
8. **Analytics:** the system page and the builder entity (§ 6).
9. **Schema contract** (`core/schema_contract.py`): the new record type and
   fields, so the drift check watches them.
10. **System Settings:** the new settings (§ 9), each with its row in
    `tests/fixtures/setup_payload_before_integrations.json`.

## 9. Settings

| Setting | Default | Read | Notes |
|---|---|---|---|
| `AMBASSADOR_PROGRAM` | false | per request | The switch for the page, the review list, the tile, the home page button and the delivery chain. Feature-detects `CAmbassadorActivity` too: absent, the page says the program is not set up |
| `AMBASSADOR_ALLOWED_TEAMS` | Mentor Team | per request | Who may log activities |
| `AMBASSADOR_REVIEW_TEAMS` | Marketing Admin Team | per request | Alerts, the review list, the analytics page |
| `AMBASSADOR_FREE_MAIL_DOMAINS` | gmail.com, yahoo.com, outlook.com, hotmail.com, live.com, icloud.com, me.com, aol.com, msn.com, comcast.net, sbcglobal.net, att.net, verizon.net, protonmail.com, ymail.com | per request | Never matched to a company |
| `AMBASSADOR_EDIT_DAYS` | 14 | per request | How long a mentor may correct their own entry |

The delivery chain runs in the `delivery-worker`, which already holds the
durable store and the shared mailbox. The page, the lookups and the review
list run in the web process.

## 10. Rules

1. **The form never reveals who is a client** (AM3). The confirmation is
   the same for every outcome; the lookups show only Contact and Company
   fields the mentor can already read.
2. **A mentor's report never overwrites curated CRM data.** Lookups fill
   the form, corrections stay on the activity, Referred by fills only when
   empty, a marketing opt-in is set true only.
3. **A CBM member is never recorded as a contact.**
4. **Best-effort side effects never fail the report.** A failed session
   write, email or referral step is retried by the worker; the mentor's
   report is safe from the moment of capture.
5. **Validate on click.** No button is disabled or hidden; a click with a
   missing answer names it.
6. **Every write is in the action log**, with old and new values where a
   value changed.
7. **An Ambassador contact session is never mentoring** (§ 4.3).

## 11. Not in this build

Named so they are not lost; each is a later phase.

1. A personal referral link and QR code per mentor (AM5, later phase).
2. Paste a whole email signature or business card's text and split it into
   fields (AM3a item 7).
3. The mentor's five recent contacts as one-tap choices (AM3a item 8).
4. Picking the event for "I invited someone to an event" and "I
   represented {{abbr}} at an event" from the events calendar.
5. Chapter figures or rankings for mentors (AM7 option C, declined).

## 12. Acceptance checks

Adapted from the proposal's pilot check. Run on the Business Mentors
Association's system as a real non-admin mentor, then as a member of the
review team.

1. From a phone, signed out: open the bookmark, sign in on the page, see
   the form. Sign out and open the portal: still signed out; sign in on the
   portal and reopen the page: the form shows without a sign-in.
2. Log "I liked or shared a post", no follow-up. One activity, linked to
   the mentor, no contact block, no alert, nothing in the review list.
3. Log "I made a community introduction" with follow-up Yes. The review
   team is emailed, the Needs you row appears, Mark done needs a note, the
   mentor is told.
4. Type the email of a known partner contact. The form fills in; question 4
   answers itself. On save: an Ambassador contact session on the partner,
   the partner manager emailed, the confirmation unchanged.
5. Type the email of a known client contact. The form fills in the name and
   company only. On save: a session on the engagement, the assigned mentor
   emailed. The engagement's status, its session counts, its Needs you rows
   and its feedback milestone are unchanged.
6. Refer a new potential client. A Prospect Contact with Referred by, the
   Company, a lead with Lead Source Ambassador referral. Then submit the
   public client intake form with the same email: the engagement carries
   Referred by, the mentor is emailed, My activity shows Applied.
7. Refer a new potential funder. A Candidate funder profile shows in Funder
   Management. Then submit the public funder form for the same company:
   no second profile; Referred by kept. Repeat for a partner.
8. Type an address on a free-mail domain at a new name: no company is
   filled in.
9. Type a fellow member's address: "That's a CBM member", nothing recorded.
10. Type an unknown email and say "from an organization we already work
    with": a review row; link it to a partner from the review list; the
    session and email follow.
11. Correct a filled company name: the CRM Company is unchanged; the review
    list shows the correction.
12. Stop the CRM's network path for the worker (or point the worker at a
    bad address) and submit: the mentor is told it is saved; the activity
    arrives once the CRM is back, with no duplicates.
13. Correct an entry in My activity inside the window; try one outside it
    and read the message.
14. Read the Ambassador Program analytics page: each figure matches the
    checks above.

## 13. Build phases and stopping points

DETAIL mode: work stops at the end of each phase for Doug's go-ahead.
Between stops, work proceeds without asking. Every phase is built dark, with
tests, and committed locally; Doug reviews and pushes.

1. **CRM plan.** The CRM plan, the migration script, the roles script and
   the handoff; dry-run against the Association's CRM; re-read the live
   Mentor Role's Contact and Company grants. **Stop 1:** Doug reviews the
   plan; the Association's baseline re-capture (#87) is done; the plan is
   applied there.
2. **The page and the record.** The shared sign-in box (and the portal moved
   onto it), the page, the form without routing, durable capture, the
   worker creating the activity, My activity with corrections, the tile,
   the home page button, the settings. **Stop 2:** Doug runs checks 1, 2
   and 13 on the Association.
3. **The lookups** (§ 3.4). **Stop 3:** checks 4's form half, 8, 9, 11.
4. **Routing and the session type** (§ 4.2, § 4.3), with the session-count
   audit test. **Stop 4:** checks 4 and 5.
5. **Referrals** (§ 4.4, § 4.5) and the three public-form delivery changes.
   **Stop 5:** checks 6 and 7.
6. **Follow-up, the review list, the Needs you row, the Mentor
   Administration tab** (§ 5). **Stop 6:** checks 3 and 10.
7. **Analytics, documents and the outage check.** The analytics page, the
   staff guide (`ambassador-program.md`), the folder's `CLAUDE.md`, the
   `OPEN-ITEMS.md` entry, the root `CLAUDE.md` pointer. **Stop 7:** checks
   12 and 14; Doug decides when to apply the CRM plan to production and
   switch the program on for Cleveland.

## 14. Proposed additions awaiting Doug's confirmation

1. **Capture first, deliver in the worker** (§ 4.1): the CRM's "Created by"
   is the API user; the mentor link, assigned user and action log name the
   mentor. The alternative, every write as the mentor in the request, loses
   the CRM-down safety AM2 asked for and needs partner and client writes
   the Mentor Role does not have.
2. **Activity 2 reworded** to "I referred someone to {{abbr}}" (§ 3.3).
3. **The question 4 wording** as in § 3.2.
4. **Types before they apply:** a referred person's Contact is Prospect for
   client, partner and funder alike, and their Company has no
   `cCompanyType` until they apply.
5. **The mentor is emailed when their follow-up is marked done**, with the
   staff note (§ 5.1).
6. **Mentor Administration's read-only Ambassador tab** (§ 5.3).
7. **The edit window is 14 days** (§ 3.5).
8. **The page name** "Ambassador Activity" at `/ambassador/`.

## 15. As built (v0.360.0, 11-21-26)

Doug approved § 14's eight items as written on 11-21-26 and asked for the
whole build in one session, checked when done: the phase stops in § 13 were
not used. Where the build differs from this document, and why:

1. **The portal's own sign-in is not moved onto the shared box yet.** The
   activity page and the review page use `frontend/shared/signin.js`; the
   portal keeps its markup. Moving it touches the sign-in every member uses,
   so it waits for Doug's go-ahead (`OPEN-ITEMS.md` #91).
2. **A referred funder starts Prospective, not Candidate** (§ 4.5): the
   funder status already has Prospective for "being approached", so the CRM
   needs no new value. A referred partner starts Candidate.
3. **No Source field on partner and funder profiles** (§ 7.2): a referred
   starting profile is recognised by Referred by, no manager and its
   starting status, which is enough for the reuse rule.
4. **No partner-association tie** (§ 4.5 item 2): creating a partner or
   funder profile for a company ties it to no business; `core/partner_links.py`
   governs ties between a partner and a business, and none is made here.
5. **The action log points at the ambassador's mentor profile** with the
   activity's id in its details: the action log's record link cannot name
   an Ambassador Activity.
6. **A referral needs an email to be created** (§ 4.2): with no email the
   person waits on the review list, so a later application can find them.
7. **The analytics page's team gate is the Analytics Admin Team and the
   Marketing Admin Team**, the review setting's default; the program team
   also reaches Analytics through `AMBASSADOR_REVIEW_TEAMS` while the switch
   is on.
8. **Delivery**: the web tries once at save time; the worker retries every
   `AMBASSADOR_DELIVERY_SECONDS` (default 60).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 02:24 | Claude (Claude Code) | First draft, from decisions AM1 to AM7 of 11-21-26. |
