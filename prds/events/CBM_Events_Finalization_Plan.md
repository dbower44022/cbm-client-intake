# CBM Events & Webinars — Finalization Plan

Last Updated: 09-12-26 14:05 · Revision 2.1 — see change log at the end.

Companion to `CBM_Events_PRD.md`, `CBM_Events_Implementation_Plan.md` and
`CBM_Events_Registration_Recognition_Plan.md`. Those three say what the feature
is and how it was built. This document says what is left between today's state
and a finished, live, production feature, in the order it should be done, and
who owns each piece.

**Status:** Track A approved and half built (Doug, 2026-09-11: redirect, and
move the presenting section onto our page). Tracks B to E await scheduling.

---

## 1. Where it stands (verified 09-08-26)

The feature is a staff application for setting up events and tracking
enrollment, a public application programming interface (API) that feeds the
website, and a public registration path that creates a Contact and an Event
Registration in the customer relationship management system (CRM).

Verified today against the live deployments, not read from the documents:

- Both applications run **v0.221.0** (release tag v0.217.0). Six local commits
  are unpushed; none touch events.
- **crm-test** has Events switched on. The staff application answers (401 for an
  anonymous caller, as expected) and the public API serves the sandbox's
  published events at `/api/events/upcoming`.
- **Production** has Events switched off: the staff routes and the public API
  both 404. Production's CRM schema was migrated on 2026-08-09 and its `CEvent`
  entity holds no records, so the first published event there will be a real
  one.
- **The website still runs on the Google Apps Script.** `clevelandbusinessmentors.org/webinars/`
  answers 200 and is fed by the script plus a browser-side YouTube call whose key
  is visible in the page source. Every registrant there is still an invisible
  lead. That is the problem the whole feature exists to fix, and it is unchanged.

Built and verified: Phases 0, 1, 3, 5 and 6c (reporting).
Built and **never run against their external service**: Phase 2 (Zoom
provisioning), 6a (attendance from the Zoom report), 6b (follow-up email), 6d
(YouTube backfill).
**Struck:** Phase 4, the WordPress plugin. Doug ruled on 2026-09-11 that the
marketing site should **redirect** to a page this app serves rather than embed
or reimplement one. The plugin, its server-side proxy, its thumbnail proxy, its
rewrite rules and its settings screen are all cancelled. The two files under
`wp-plugin/cbm-events/assets/` stay exactly where they are — they are the
renderer and the site's verbatim stylesheet, and the public pages drive both.

**Built 2026-09-11 (v0.222.0):** the public pages themselves, at `/webinars/`
and `/webinars/{slug}`, with the "Interested in Presenting or Hosting?"
invitation carried across from the page that will redirect away.
**Designed, not built:** registration recognition (the five-step plan), and its
prerequisite fix to the near-duplicate hold.

---

## 2. What "finalized" means

The feature is finished when all of the following are true on **production**:

1. `clevelandbusinessmentors.org/webinars/` redirects to this app's programme
   page, which looks like the site and works at desktop and phone widths.
2. A registration from that page creates a Contact and an Event Registration in
   the production CRM, and the visitor receives a confirmation.
3. Each event has a shareable page of its own.
4. A visitor who reloads during a brief outage is answered from their own
   browser cache (the page sets a 60-second public `Cache-Control`).
5. A person registering for two events on one day gets both registrations.
6. Staff create, publish, run and report on an event entirely in `/events`,
   signed in as a non-admin member of the Marketing Admin Team.
7. The Google Apps Script is retired and its exposed YouTube key is rotated.

Items 1–5 and 7 are the **lead-leak fix**. Item 6 is the programme-management
tool. The Zoom automation, the follow-up emails and registration recognition
make the tool better but are not required for any of the seven.

---

## 3. The work, in five tracks

Tracks A and B are the finish line. C, D and E improve the tool and can run in
parallel or after. Each item names its owner: **Doug** (access, credentials,
site changes, rulings), **build** (code in this repository), or **verify** (a
live pass, always as a real non-admin where a gate is involved).

### Track A — The redirect. Ends the lead leak.

Doug's ruling, 2026-09-11: the marketing site **redirects** to a page this app
serves. No plugin, no proxy, no embedding. A8 is the only step that touches the
website, and it is one redirect rule.

| # | Item | Owner | Depends on | State |
|---|---|---|---|---|
| A1 | **Build the public pages** at `/webinars/` and `/webinars/{slug}`: server-rendered so a social crawler sees each event's own title, description and image, and so an unpublished event 404s; the two panels driven by the existing renderer under the site's own stylesheet; the presenting invitation carried across. | build | — | **Done, v0.222.0** |
| A2 | **A browser pass against real crm-test data**, as a real visitor (`OPEN-ITEMS.md` 19e). | verify | A1, deploy | **First pass done 2026-09-12** — side by side against the live page. Found four differences; three fixed in v0.223.0 (hero, band, site menu, panel wording), the fourth is A2b. |
| A2b | **Populate the recorded library** (`OPEN-ITEMS.md` 19i). The live page's library comes from the YouTube playlist; ours comes from event records, and there are none. Redirecting today replaces a populated section with an empty one. `scripts/import_youtube_events.py` is the fix and needs a **YouTube API key** and the **playlist identifier**, neither configured anywhere. | Doug supplies, build runs | — | **Blocking** |
| A3 | **Scope the near-duplicate hold per event** (19f). Give the form specification an optional payload key that joins the match, so event registration matches on form + email + event. Test: two events, one email, both deliver; the same event twice still holds. **Lands before the redirect** — every returning registrant makes this fire more often. | build | — | Owed |
| A4 | **Decide the consent wording** (19d). Both public doors send `consent: false` today, so a registration records no opt-in at all. Options and the recommendation are in § 4. **Lands before the redirect.** | Doug rules, build | — | Owed |
| A5 | **Share the Apps Script source and its Google Sheet.** Now needed only to confirm nothing else runs on it before it is retired — it is no longer a parity baseline, because we are not reimplementing its rendering. | Doug | — | Owed |
| A6 | **Export the current `/webinars/` page content** as the rollback copy, and confirm who can edit the page and add a redirect. | Doug | — | Owed |
| A7 | **Switch production on**: probe the prod events schema and diff against crm-test; set `EVENTS_ENABLED` and `EVENTS_PUBLIC_API` at `/setup`; confirm `APP_BASE_URL` is set, because every shared event link derives from it; confirm the Marketing Admin Team is the right administrator group. Full list: `OPEN-ITEMS.md` 19g. | Doug + build | A3, A4 | Owed |
| A8 | **Create the upcoming events in production `/events`**, so the page is not empty at the swap, then **add the redirect** from `clevelandbusinessmentors.org/webinars/` to the app's programme page. Runbook: `EVENTS-SETUP.md` § 6. Register once with obvious test data and delete the records. | Doug + verify | A7 | Owed |
| A9 | **Retire.** After a rollback window of one event cycle, remove the Apps Script, **rotate the exposed YouTube key** (R-7), and fix the mismatched contact address (R-8: the footer says `info@clbmentors.org`, the presenting section `info@cbmentors.org`; the second is the real domain). | Doug | A8 | Owed |

**The rollback is the redirect.** Removing it puts the old page back exactly as
it was, in under a minute, with no deploy and no code change. That is why the
Apps Script stays deployed but idle until A9.

### Track B — Live verification already owed on crm-test. Can start today.

| # | Item | Owner |
|---|---|---|
| B1 | **Phase 5 as a real non-admin** Marketing Admin Team user: the team gate, the grid, the detail tabs, check-in. Every earlier pass stubbed the session, so the non-admin CRM access has never been exercised. | verify |
| B2 | **The Add / Edit editor** (v0.202.0): create and edit one event; rich text round-trips to `eventOverview` / `eventSyllabus` and renders on the preview; the Duration select still produces the right `dateEnd`; the graphic uploads. | verify |
| B3 | **The preview against the live page** (19e): `/events/preview.html` on crm-test beside `clevelandbusinessmentors.org/webinars/`; click a title through to its page; register once with test data and delete the records. | verify |
| B4 | **Reporting with real numbers** (6c): mark one crm-test registration Attended and confirm the engagement Events tab, the contact history and the programme reports show it. | verify |

crm-test resets nightly at 04:00 UTC, so each pass is a single-day job or it
starts again.

### Track C — Zoom. Makes online events automatic.

| # | Item | Owner | Depends on |
|---|---|---|---|
| C1 | Create the **Server-to-Server OAuth application** in the Zoom Marketplace under the `zweb@cbmentors.org` account; capture Account ID, Client ID and Client Secret; grant webinar, registrant, report and user scopes; note the per-webinar attendee ceiling on the licence. | Doug | — |
| C2 | Run `scripts/probe_zoom.py` (read-only). Green means the scopes and the reporting licence are right. | verify | C1 |
| C3 | **Phase 2 live on crm-test:** publish a test event → webinar exists with registration on and Zoom reminders off; edit the time → patched; cancel → cancelled; a registrant gets exactly one Zoom confirmation. | verify | C2 |
| C4 | **6a live:** a real webinar with real participants, then confirm the worker marks attended and no-show correctly and leaves hand-set attendance alone. Needs the worker flag on. | verify | C3 |
| C5 | Switch `ZOOM_EVENTS` on in production. | Doug | C4 |

Until C5, staff paste an existing webinar link into the event (the
link-existing path, EV-23). The cutover does not wait for Zoom.

### Track D — Email. Confirmation and follow-ups.

| # | Item | Owner | Depends on |
|---|---|---|---|
| D1 | Author the **five EspoCRM templates** on both CRMs, named exactly: `EventReminder`, `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA`, `EventSurvey`. Templates survive the crm-test reset. | Doug (wording), build (names, placeholders) | — |
| D2 | **Build the Follow-up tab frontend.** The endpoints exist; the tab does not call them. Preview by default, send on confirmation, ledger shown per registrant. | build | — |
| D3 | **Build the CBM confirmation email** (recognition plan step 2): a single-recipient send from a sixth template, `EventConfirmation`, ledgered on `followUpsSent`. This is what makes "check your email" true for in-person events, and it is where the re-arm and correction links will live. | build | D1 |
| D4 | Switch `EVENTS_REMINDERS` on for the **worker** in production; confirm one reminder goes out 24 hours ahead and Zoom's does not. | Doug + verify | D1, C3 |

### Track E — After the cutover. Not part of finalization.

- Registration recognition steps 3–5 (email-first lookup, device token, member
  redirect handoff). The three undecided points in that plan stay undecided
  until D3 exists.
- 6d YouTube backfill against the real playlist: dry-run on crm-test first;
  needs a YouTube Data API key and the playlist id.
- A member-facing event list inside the portal, if members should not register
  from the public page.

---

## 4. Decisions Doug owns

Two decisions shape the build. The rest are rulings recorded already.

**Decision 1 — Sequencing: redirect before Zoom, or wait for Zoom?**
Redirecting first (Track A, then C) stops the lead leak as soon as the public
pages are verified; online events carry a hand-pasted Zoom link until Track C
lands. Waiting for Zoom ships one coordinated change but leaves every registrant
invisible for as long as the OAuth application takes. **Recommendation: redirect
first.** Cost: a few weeks of staff pasting webinar links by hand.

**Decision 2 — Consent wording in the sign-up modal (19d).**
(a) A **consent checkbox** naming the three policies, like the intake forms. It
is unambiguous evidence of acceptance; the cost is a visible change to a page
visitors know and one more click. (b) **Consent text** under the button naming
the three policies with links, no checkbox. It keeps one-click sign-up; the
cost is weaker evidence than an affirmative tick. **Recommendation: (a), the
checkbox** — it matches what every other public form on the site does, and
`consent: true` should never be written on the strength of a sentence nobody
had to read.

One constraint worth knowing before choosing. The calendar modal's markup comes
from `wp-plugin/cbm-events/assets/cbm-events.js`, checked against the site's
verbatim stylesheet by a guard test, so a checkbox **in the modal** means
editing both contract files. The per-event page's form is ours and can carry one
today. Whichever is chosen, **the two doors must agree** — one recording consent
and the other not is worse than neither doing so.

Smaller choices, decided at the step: template wording (D1); whether the Apps
Script rollback window is one event cycle or two (A9).

---

## 5. Sequence

```
A1 pages (done) ─> A2 browser pass on crm-test ─┐
A3 duplicate hold ─┐                            ├─> A7 prod on ─> A8 redirect ─> A9 retire
A4 consent wording ┘                            │
A5 A6 (Doug, any time) ─────────────────────────┘
B1–B4 (crm-test, any day)
C1 (Doug) ─> C2 ─> C3 ─> C4 ─> C5      (optional before A8)
D1 (Doug) ─> D2 D3 ─> D4
```

The critical path is A2 → A3/A4 → A7 → A8. Nothing on it is long: A3 is a small
extension to an existing query, A4 is a decision plus a line of markup, and A8
is one redirect rule on the website. The build half of Track A is finished.

---

## 6. Verification gates

Nothing on Track A reaches the live page without: the house test suite green
with new coverage · the public pages driven in a browser against real crm-test
data as a real visitor · both panels compared side by side with the current
site page at desktop and phone widths · a real registration from each of the
two doors landing in the CRM.

The single most important test remains the first real event end to end on
production: create → publish → a real person registers from the website →
Contact and registration in the CRM → confirmation arrives → event runs →
attendance recorded → recording link pasted → the engagement rollup shows it.

---

## 7. What this plan deliberately leaves out

- A dedicated approval queue for registrations. The Registrants tab and the CRM
  are the review path.
- Any change to the staff session cookie for member recognition. The redirect
  handoff is the agreed design.
- Restyling the site's stylesheet. It ships verbatim and stays in sync with the
  live page.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 2.1 | 09-12-26 14:05 | Claude (Claude Code) | First side-by-side against the live page. Track A gains A2b, the recorded-library backfill, which is blocking and needs two values from Doug. A2 records the three differences already fixed in v0.223.0. |
| 2.0 | 09-11-26 23:10 | Claude (Claude Code) | Track A rebuilt around Doug's 2026-09-11 ruling: the marketing site redirects to a page this app serves, and the presenting invitation moves onto it. The WordPress plugin, its proxy, its thumbnail proxy and its settings screen are struck. A1 is built (v0.222.0); the remaining Track A items are the browser pass, the per-event duplicate hold, the consent wording, and one redirect rule. Definition of done, sequence, decisions and verification gates follow. |
| 1.0 | 09-08-26 19:05 | Claude (Claude Code) | First draft. State verified against both live deployments and the website; seven-point definition of done; five tracks with owners and dependencies; two decisions for Doug. |
