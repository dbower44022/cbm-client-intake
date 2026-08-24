# Rating Engine — plan v0.1 (2026-08-23) — **STRAWMAN, not approved**

CBM captures recipient feedback **in-house** (Doug's ruling 2026-08-23), rather
than pointing people at an outside survey tool. This is its own feature arc: it
was scoped out of `prds/grant-management-plan.md`, which depends on it for
rating-based deliverables ("average approval rating for seminars or mentoring
sessions") but does not wait for it — those deliverables ship as manually entered
numbers and become automatic the day this lands, with no change to the grant
model.

Status: **six rulings settled (below), the rest open.** Nothing built.

## Doug's rulings (2026-08-23)

1. **Ratings are captured in-house** — the whole engine lives in this system.
2. **Two subjects to start: a mentoring SESSION and an EVENT, each rated by the
   RECIPIENT** (the client; the attendee). Designed so a third subject is a
   config entry, not a rebuild.
3. **One instrument per subject** — a short questionnaire (three or four
   questions) on a shared **1–5** scale, plus a free-text comment, with **one
   question designated the headline**: its average *is* "the approval rating"
   that a grant report quotes.
4. **A mentor sees their own ratings — aggregate AND verbatim comments.**
5. Storage is attributed (see *Attribution and disclosure*).
6. **A response is a real CRM record — `CRating`** (2026-08-23), not app-only
   Postgres rows with a score written back. Feedback is a business record, and
   CBM wants it reportable in the CRM alongside the session it is about.

## Attribution and disclosure

Responses are stored **attributed to the responding Contact**, because the engine
has to dedupe, chase non-responders, and stand behind a number sent to a funder.
Ruling 4 then makes the **disclosure load-bearing**: the public page must state,
before the person types, that *their mentor will see the rating and the
comments*. A comment written in the belief that only staff would read it, which
the mentor then reads, is the failure mode that kills a feedback programme
permanently — and with a mentor who has three clients, no amount of aggregation
makes it anonymous anyway. The honest version costs some candor; that is the
trade ruling 4 makes, and the page must not paper over it.

Corollaries: the person rated can never edit or delete a response about
themselves; staff can redact an abusive comment, leaving an `action_log` trail;
and any aggregate used for *judgment* (a roster quality column, say) renders only
above a minimum response count — an average of one is not a measurement.

## Concepts

- **Instrument** — one per subject type. An ordered list of questions on the
  shared 1–5 scale, one flagged `headline`, plus the comment prompt and the
  disclosure text. **Versioned**: a live instrument may be edited, and a stored
  response keeps the version *and the question text as asked*, so an edit can
  never rewrite what someone was answering. (The analytics-builder precedent:
  built-in defaults in code, overridable by a DB row.)
- **Request** — one per (subject, recipient), carrying a signed single-use token,
  `sent_at`, `reminder_at`, `responded_at`, `expires_at`. Operational plumbing.
- **Response** — the per-question scores, the comment, `submitted_at`, and the
  Contact. Amendable by the responder until the request expires; immutable after.

## Where the data lives — settled: `CRating` in the CRM

Ruled 2026-08-23: the response is a **CRM entity**. Three sub-decisions follow
that Doug did not have to make; they are recorded here as **assumptions, open to
correction**, each chosen to keep the Entity Manager build to *one* entity:

- **The instrument stays app-side configuration**, not a CRM entity — built-in
  defaults in code, overridable by a DB row, the analytics-builder precedent.
  Questions and their wording are configuration; the answers are the business
  record.
- **Per-question scores ride as a JSON snapshot** in a text field, exactly as the
  grant report's `results` does, storing the instrument key and version **and the
  question text as asked**. The *headline* score is a real numeric field, so the
  CRM can average it natively — which is the whole reason for putting ratings
  there. A four-question instrument therefore does not become four columns, and
  editing an instrument never rewrites history.
- **The request and its token stay in the app's Postgres** (`rating_request`),
  and a `CRating` row is created **on response**, not on send. Tokens are
  secrets and do not belong in a CRM field staff can read, and a row per
  unanswered invitation would fill the entity with noise. Response rate stays
  computable in-app. *(The alternative — a `Requested` row updated in place, the
  `CIntakeSubmission` receipt pattern — is a real option if Doug wants
  outstanding requests visible in the CRM.)*

### `CRating`

> `name` (req) · **`parent`** (belongsToParent — `CSession`, `CEvent`; **adding a
> third subject is adding an entity to that parent list**, which is what makes
> ruling 2's "config, not a rebuild" true) · `respondentContact` (belongsTo
> Contact, reverse `cRatings`) · `mentorProfile` (belongsTo CMentorProfile,
> reverse `ratings` — set on session ratings, so a mentor's own feedback is one
> query) · **`ratingScore`** (int 1–5, the headline) · `answers` (text, the JSON
> snapshot) · `comment` (text) · `instrumentKey` · `instrumentVersion` ·
> `submittedDate` · `ratingStatus` (Submitted / Comment Redacted) ·
> `assignedUser` · `teams`

**Who writes it**: the respondent has no CRM identity, so the public endpoint
creates the row under the **org-wide API key**, exactly as the five intake forms
create theirs.

**Role grants, and they carry a rule**: the Mentor Team reads its own
(`assignedUser` stamped with the rated mentor's User, the established read-own
pattern) with **no edit and no delete** — ruling: *the person rated can never
edit or delete a response about themselves*. Staff (Mentor Administration Team)
read all and edit (that is how a comment gets redacted), also **no delete**. Both
CRMs, crm-test first.

## Capture — a public page, because the raters have no login

Clients and attendees are not portal users, so capture is a **public tokenized
page** in the same shape as the five intake forms: no login, honeypot, rate
limiting, `busy.js` first, the `{{org}}` token and the `cbm-org` meta tag, no
build step. `GET /rating/{token}` renders the instrument; `POST` records the
response. An expired, unknown or already-submitted token renders a plain
explanatory page, never a stack trace, and **echoes nothing about the subject or
the recipient** — a public page that reveals what we know is a harvester (the
events registration-recognition ruling, applied here).

## Distribution

- **Session** — a session saved **Completed** requests a rating from each client
  contact on it. Not from the mentor's own mailbox: a request to rate your mentor
  that arrives *from* your mentor is not a neutral ask, so it sends as the shared
  **info@ / CBM** identity, like every other staff-tool outbound.
- **Event** — an event marked **Held** requests one from each registration at
  `Attended`. Most of this exists: `events/notify.py` already has a `Survey`
  follow-up kind, a once-per-registrant/event/kind ledger written **after** a
  successful send, and preview-by-default. It needs to point at our own page.
- **One reminder** after N days if unanswered, then expiry. Ledgered the same way,
  so a redeploy or a re-run never double-sends.
- All sends are best-effort and never fail the staff save that triggered them.

## What reads it

- **The mentor** — their own aggregate and comments, on `/mentorprofile`.
- **Staff** — individual responses on the session/event, and a roster-level
  quality view in Mentor Administration (minimum-N gated).
- **Grants** — the `rating.sessions.avg` / `rating.events.avg` measures, computed
  over the grant's period and its attributed engagements.
- **Analytics** — metrics for the record dashboards and the analytics pages.

## Phasing

| Phase | What |
|---|---|
| **1** | Instrument model + the public page + capture; requests sent by hand from the record |
| **2** | Automatic triggers (session Completed, event Held) + the reminder, in the worker |
| **3** | Mentor self-view and the staff views, with the minimum-N gate and comment redaction |
| **4** | The two grant measures reading `CRating` over the grant period |
| **5** | Further subjects (engagement-level periodic, partner/funder), as config |

Behind **`RATINGS_ENABLED`**, checked per request (the `record_quick_add`
pattern, not boot-read) so it is toggleable at `/setup`.

## Still open

1. ~~**Storage**~~ **RULED: a `CRating` CRM entity.** What remains is
   confirming the three sub-decisions above (instrument as app config,
   per-question JSON, row-on-response).
2. **The questions themselves** — CBM's actual wording for the session and event
   instruments, and which one is the headline.
3. **Timing** — how long after a session/event does the request go, how long
   until the reminder, when does the token expire?
4. **The minimum-N threshold** for a judgment-facing aggregate.
5. **Does a client rate every session, or the engagement periodically?** Per
   session is the ruling as it stands; it risks fatigue on a weekly cadence, and
   a "not every time" rule (first session, then every Nth) is a config decision
   worth making deliberately.
6. **Redaction policy** — who may redact a comment, and does the mentor see that
   one was redacted?
