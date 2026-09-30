# CBM Events & Webinars — Finalization Plan

Last Updated: 09-30-26 15:10 · Revision 4.13 — see change log at the end.

Companion to `CBM_Events_PRD.md`, `CBM_Events_Implementation_Plan.md` and
`CBM_Events_Registration_Recognition_Plan.md`. Those three say what the feature
is and how it was built. This document says what is left between today's state
and a finished, live, production feature, in the order it should be done, and
who owns each piece.

**Status:** Track A is DONE except the redirect itself — **but the cutover now waits on Track F**, the features
found by user review (Doug, 09-27-26), and on the confirmation email (D3),
which the definition of done always required. Production is switched
on, its recorded library is imported and published, and both blockers (consent,
the per-event duplicate hold) are built and live. What remains is Doug creating
the upcoming sessions, one end-to-end test registration, and the one redirect
rule on the marketing site.

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
8. Every Track F feature is built, verified, and live on production.

Item 2 requires the CBM confirmation email (D3). Zoom's own confirmation
covers only online events, and Zoom is switched off everywhere, so without D3 a
visitor who registers after the redirect receives nothing. D3 is therefore
required before the cutover, not an improvement after it.

Items 1–5 and 7 are the **lead-leak fix**. Item 8 is what user review found
missing (Doug, 09-27-26). Item 6 is the programme-management
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
| A2 | **A browser pass against real data**, as a real visitor (`OPEN-ITEMS.md` 19e). | verify | A1, deploy | **Done 2026-09-12 and 09-14** — side by side against the live page, then the real production pages. Seven defects found and fixed across v0.223.0, v0.229.1, v0.230.0 and v0.230.1. Owed: a registration end to end. |
| A2b | **Populate the recorded library** (`OPEN-ITEMS.md` 19i). | Doug supplied, build ran | — | **Done 2026-09-14.** Five playlists, 13 items, 10 imported to production and published with topics. The two YouTube values live in production's overlay, so a re-run needs no setup. |
| A2c | **A topic filter on the recorded library** (Doug, 2026-09-14). Selector above the search box, offering only subjects that have a recording; the search runs inside the chosen topic and clearing it reloads. | build | A2b | **Done, v0.230.x** |
| A3 | ~~**Scope the near-duplicate hold per event** (19f).~~ **Done, v0.229.0.** Give the form specification an optional payload key that joins the match, so event registration matches on form + email + event. Test: two events, one email, both deliver; the same event twice still holds. **Lands before the redirect** — every returning registrant makes this fire more often. | build | — | Owed |
| A4 | ~~**Decide the consent wording** (19d).~~ **Done, v0.227.0 — Doug chose an active tick on both doors.** Both public doors send `consent: false` today, so a registration records no opt-in at all. Options and the recommendation are in § 4. **Lands before the redirect.** | Doug rules, build | — | Owed |
| A5 | **Share the Apps Script source and its Google Sheet.** Now needed only to confirm nothing else runs on it before it is retired — it is no longer a parity baseline, because we are not reimplementing its rendering. | Doug | — | Owed |
| A6 | **Export the current `/webinars/` page content** as the rollback copy, and confirm who can edit the page and add a redirect. | Doug | — | Owed |
| A7 | ~~**Switch production on**~~ **Done 2026-09-14.** Originally:: probe the prod events schema and diff against crm-test; set `EVENTS_ENABLED` and `EVENTS_PUBLIC_API` at `/setup`; confirm `APP_BASE_URL` is set, because every shared event link derives from it; confirm the Marketing Admin Team is the right administrator group. Full list: `OPEN-ITEMS.md` 19g. | Doug + build | A3, A4 | Owed |
| A8 | **Create the upcoming events in production `/events`**, so the page is not empty at the swap, then **add the redirect** from `clevelandbusinessmentors.org/webinars/` to the app's programme page. Runbook: `EVENTS-SETUP.md` § 6. Register once with obvious test data and delete the records. | Doug + verify | A7 | Owed |
| A9 | **Retire.** After a rollback window of one event cycle, remove the Apps Script, **rotate the exposed YouTube key** (R-7), and fix the mismatched contact address (R-8: the footer says `info@clbmentors.org`, the presenting section `info@cbmentors.org`; the second is the real domain). | Doug | A8 | Owed |

**The rollback is the redirect.** Removing it puts the old page back exactly as
it was, in under a minute, with no deploy and no code change. That is why the
Apps Script stays deployed but idle until A9.

### Track F — Features from user review. Required before the cutover.

Doug, 09-27-26: user review of the live pages and Event Administration found
features that must exist before the redirect. This track is the catalog. Each
feature is **catalogued first, designed second**: the design is drafted only
after Doug's requirements are gathered, and nothing is settled until he rules.

| # | Feature | Raised by | State |
|---|---|---|---|
| F1 | Event topic: multiple selections, plus a user-entered value | User review, 09-2026 | Catalogued |
| F2 | Display Date/Time: the moment an event may first appear on the public pages | User review, 09-2026 | Built v0.233.0 (09-29-26); CRM on crm-test; live review, production and Boston owed (`OPEN-ITEMS.md` #35) |
| F3 | Event audience: Internal, a specific chapter, or Public — Internal events form a calendar on the chapter's portal | User review, 09-2026 | Built v0.233.0 (09-29-26); CRM on crm-test; live review, production and Boston owed (`OPEN-ITEMS.md` #35) |
| F4 | Presenters: select or add them per event, with an optional presenter biography on the event page | User review, 09-2026 | Catalogued |
| F5 | Portal home page: a left-hand list of upcoming internal events, each opening its details | User review, 09-2026 | Built v0.235.0 (09-30-26), dark behind `PORTAL_CALENDAR`; live review owed (`OPEN-ITEMS.md` #37) |

**The catalog is complete at five features** (Doug, 09-27-26). Design proceeds
one feature at a time, in the order Doug chooses.

**F1 — Event topic takes several values and a user-entered one.**

*The need, as stated:* "The topic selection needs to support multiple
selections and allow a user entered value in case the event does not match the
pre-defined topics."

*What exists today (verified in the code, 09-27-26):*
- `CEvent.topic` is a single enum of ten values. Doug ruled on 2026-07-25 to
  keep it single (`cevent-entities-crm-handoff.md` § 5), and that ruling
  anticipated widening it to a multi-enum as a one-line schema change. This
  feature supersedes the single-value half of that ruling.
- The field feeds four places: the Event Administration editor
  (`events/config.EVENT_FIELDS`), the public recorded-library topic filter
  (`events/service.recording_topics` / `filter_recordings`, ordered by
  `cfg.TOPIC_ORDER`), the public payload's `category` (`events/service.py`,
  `events/reporting.py`), and the enum clean-up on save (`events/service.py`,
  the empty-enum fix of v0.229.1).
- A user-entered value is new. It has no precedent in the 07-25 ruling, and
  EspoCRM refuses a multi-enum value outside the field's option list.

*Questions to settle at design, not yet asked:* who may enter a new value
(staff only, surely); whether a user-entered value appears in the public topic
filter; whether it is stored beside the curated values or in its own field;
whether a repeated user-entered value is ever promoted into the curated list;
and how an event with two topics is counted in the programme reports.

**F2 — Display Date/Time.**

*The need, as stated:* "When an event is created, a 'Display Date/Time' can be
defined that will specify the date and time when the event can first be
displayed on the event web sites. If not defined, the event can be displayed
immediately."

*What exists today (verified in the code, 09-27-26):*
- The only public boundary is `publishToWebsite` plus "not cancelled", applied
  by `events/service._public_where`. Every public read goes through it: the
  calendar (`list_upcoming`), the recorded library (`published_recordings`) and
  the per-event page (`get_by_slug`, which 404s an unpublished event).
- **A second gate exists outside that function.** The registration orchestrator
  checks `publishToWebsite` directly (`forms/event_registration/orchestrator.py`
  line 96). A display time enforced only in `_public_where` would hide an event
  from the pages while still accepting registrations for it.
- Public responses carry a public `Cache-Control` lifetime (`events/public.py`,
  `events/pages.py`), and the recorded library has a server-side cache. An
  event can therefore appear up to one cache lifetime after its display time.
- No display-time field exists on `CEvent` on either CRM, so this is a CRM
  build as well as a code change, and it follows the feature-detect convention.

*Requirements, ruled by Doug 09-28-26.* These are rulings. The design, drafted
together with F3's because both change the same public gate, has not been
drafted.

1. **The display time applies on every page** — the portal calendar, the
   public calendar, the recorded library and the event's own page — whatever
   the event's audience. Ruled as F3 requirement 9.
2. **The display time narrows the checkbox; it does not replace it.** An event
   is shown only when it is ticked (Publish to website, relabelled under F3)
   **and** its display time has passed. An empty display time means "as soon as
   it is ticked". Unticking hides an event at once, whatever its display time.
   The editor warns when a display time is set on an unticked event.
3. **Registration opens at the display time.** There is no separate opening
   time. The public registration form checks the same gate as the pages. A
   "Registration opens" time can be added later with no change to stored data,
   because empty would mean what this rule does.
4. **The Zoom webinar is created when the event is ticked, as today**
   (`events/zoom_sync.py`), whatever its display time. Verified 09-28-26: the
   create fires on a save of an online, ticked event with no webinar yet. Zoom
   creation is switched off on both deployments, so this has no effect until it
   is switched on.
5. **A display time later than the event's start is allowed.** When the event
   is still upcoming, the editor warns that no one will see it or register
   before it starts, and saves anyway. When the event is over — releasing a
   recording on a chosen day — no warning appears.

*Claude's decisions, open to challenge:*
- **Staff see the waiting state.** An event that is ticked but whose display
  time has not arrived shows in Event Administration as "Appears" with its
  date, on the grid and in the editor, so a scheduled event is not mistaken for
  a live one or a forgotten one.
- **The cache delay is accepted, not engineered away.** The public reads cache
  for `events_cache_seconds` (default 60) in the process and again in the
  browser, so an event can appear up to about two minutes after its display
  time. No change is planned.

**F3 — Event audience: Internal, a specific chapter, or Public.**

*The need, as stated:* "When an event is defined, it can be defined as an
internal event, a specific chapter event, or a public event. Internal events
will only be displayed on the chapter main menu page as a sort of internal
calendar."

*What exists today (verified in the code, 09-27-26):*
- An event has no audience field. Its only visibility control is the
  `publishToWebsite` tick (see F2 for where it is enforced). `eventType`
  (`Online Webinar` / `In Person Event` / `Online Course`) is an editorial
  category, not an audience.
- The "chapter main menu page" is the authenticated portal at `/`
  (`portal/router.py`). It shows no calendar today; events appear there only
  as the Event Administration tile and the public-pages links.
- `CEvent` already doubles as the organisation calendar: on crm-test most of
  its 94 rows are internal meetings and mentoring-session mirrors synced from
  Google, while production's rows are all programme events. An internal
  calendar built on `CEvent` would show whatever the Google sync puts there,
  unless it is filtered.
- **The chapter network bears on "a specific chapter event."** Chapter-network
  ruling 2 is one EspoCRM per chapter, and ruling 8 is that this application
  serves each chapter's public pages from that chapter's own deployment. So
  every event already belongs to exactly one chapter's CRM, and today no
  chapter can see another chapter's events. If "Public" means visible across
  chapters, that is a cross-CRM feature with no mechanism yet; if it means "on
  this chapter's public site", then "a specific chapter event" needs defining.
  The Business Mentors Association repository holds the rulings on how the
  chapters relate, and it would have to be read before this is designed.

*What the Business Mentors Association's rulings say (read 09-27-26, read
only):* nothing about events, calendars or chapters sharing content. Association
ruling 3 (one application everywhere; chapters differ only by optional settings
and their own processes) and chapter-network ruling 2 (one EspoCRM per chapter)
are the two that bear on this feature.

*Requirements, ruled by Doug 09-27-26 and 09-28-26.* These are rulings. The
design that follows from them has not been drafted.

1. **Two levels, not three choices.** An event's audience is **Internal** or
   **Public**. A Public event also carries a **reach**: all chapters, one
   chapter, or a list of chapters. "A specific chapter event" in the original
   need is the one-chapter reach of a Public event, not a separate audience.
2. **The goal is a shared list of public events across chapters, built later.**
   F3 records the reach on every event from now on. This chapter's public pages
   show only this chapter's own Public events. The sharing itself is not part of
   F3 and does not block the cutover. The editor states plainly that the reach
   has no effect until the sharing exists.
3. **The chapter names come from the CRM standard.** They are the fixed choices
   of the reach field, identical in every chapter, so the future shared list can
   match on them. Adding a chapter takes a release. A chapter that has not yet
   taken that release does not see the newest chapter in its list.
4. **The audience sits beside the Publish to website checkbox; it does not
   replace it.** The checkbox decides whether the event is shown at all; the
   audience decides where (the portal for Internal, the public pages for
   Public). Unticked means shown nowhere, as today. The checkbox is relabelled
   (working wording "Show this event") because it now governs the portal too;
   the CRM field keeps its name. Existing events carry over as: ticked → Public,
   reach this chapter; unticked → Internal, still unticked.
5. **Who sees an Internal event:** everyone who signs in to the portal, unless
   staff limit the event to one or more named teams. The team limit applies to
   Internal events only.
6. **The creating chapter is always in a Public event's reach.** The reach can
   only add other chapters. "One chapter" means the creating chapter. Hosting an
   event solely for another chapter's audience is left for later; relaxing this
   rule would change no stored data.
7. **Internal events take registrations when staff say so.** A per-event
   checkbox (working wording "Takes registrations") turns on a Register button
   for signed-in members, which records a registration against the member's own
   contact record with no form.
8. **The portal calendar shows Internal events and this chapter's Public
   events**, each Public event marked as public, with a filter each member sets
   for themselves. The filter choice is saved per user in the application's own
   database, keyed on the member's CRM user, so it follows them between
   computers. *Claude's decision, open to challenge:* the database rather than
   browser storage, because no per-user preference store exists today and
   browser storage does not follow the member.
9. **F2's display time applies everywhere.** Before an event's display time it
   is on no page, portal or public, whatever its audience. Early notice for
   members can be added later as its own setting.

*Found while gathering these, verified in the code 09-28-26:* the public
registration form accepts a sign-up for any ticked event
(`forms/event_registration/orchestrator.py`, `check_open`). Under ruling 4 an
Internal event is ticked too, so the public pages **and** the public
registration form must both require audience Public with this chapter in the
reach — the same gap F2 already names for the display time.

*Inferred, not yet checked:* that the meetings and session copies synced from
Google arrive unticked, and so stay off the portal calendar under ruling 4 with
no extra filter. The design verifies this on crm-test.

*This settles part of F5:* members can register from the portal list (ruling 7),
the list is filtered per member (ruling 8), and team limits apply to Internal
events (ruling 5).

**F4 — Presenters, and their biographies on the event page.**

*The need, as stated:* "The system needs to provide a way to select or add
presenter(s) to each event. The event contains an option to show the
presenters bio on the event details page. If the presenter selected is a
mentor, it will copy the mentor bio to the presenter bio and allow edits. If
the presenter is a contact the event manager will have to manually add a bio."

*What exists today (verified in the code and the schema handoff, 09-27-26):*
- The CRM already has the link: `CEvent.presenters`, many-to-many to Contact,
  foreign `cPresenterEvents` (`cevent-entities-crm-handoff.md` § 2). It was
  designed to cover guests, staff and mentors alike, with a mentor's
  `CMentorProfile` reached through their Contact.
- **The application does not use it anywhere.** No file under `events/` reads
  or writes `presenters`, the editor has no picker, and the public pages show
  no presenter. Being a custom many-to-many, it is a relationship, not a field:
  it is read with `list_related` and written with relate/unrelate, never as
  `presentersIds` on an update (the EspoCRM custom linkMultiple trap).
- The mentor biography to copy from is `CMentorProfile.aboutMentor`, a wysiwyg
  field that already feeds the public website mentor page, so it is public text
  by design. It refuses inline images by ruling, because its audience cannot
  reach the image proxy — the presenter biography on a public event page has
  the same audience and inherits the same constraint.
- No presenter-biography field and no "show presenter biographies" option
  exists on either CRM.

*Questions to settle at design, not yet asked:* whether a presenter biography
belongs to the person (one biography reused across events) or to the pairing
of person and event (edited per event), which decides where it is stored;
whether the copy from `aboutMentor` is one-time at selection or refreshes when
the mentor edits their profile; whether "add a presenter" creates a new Contact
from the editor, with the usual find-or-create on email; whether the show
option is one switch per event or per presenter; what else a presenter shows
publicly (name, photo, title, company); presenter order on the page; and
whether a partner organisation as host (`partnerHost`, D-10) is part of this
feature or separate.

**F5 — Upcoming internal events on the portal home page.**

*The need, as stated:* "Modify the initial page displayed after login to show a
list of internal events on the left side of the page in a list that allows the
user to see upcoming events and click on each to see details."

*Relationship to F3:* F3 defines which events are Internal and rules that they
appear only on the portal. F5 is that portal surface. F5 cannot be designed
before F3 settles what "Internal" selects.

*What exists today (verified in the code, 09-27-26):*
- The page after sign-in is the portal's home view (`portal/frontend/index.html`,
  `homeView`): a single column of sections — the analytics dashboard panel,
  Directories, Applications, the CRM links, Documentation and the public pages.
  There is no left rail and no events list.
- **The portal caps its own width** (`.portal { max-width:
  var(--cbm-container-narrow) }` in `portal/frontend/styles.css`). That
  contradicts the standing no-width-caps ruling, and a left rail beside the
  existing column is not workable inside it, so F5 lifts the cap.
- Event Administration, where event details live today, is gated to the
  Marketing Admin Team (`EVENTS_ALLOWED_TEAMS`). Most signed-in members are not
  in it, so "click to see details" cannot open that screen for them.

*Already settled by F3 (design § 6, built v0.233.0):* the portal reads events
under the organisation-wide API key and applies the team limit itself; the
list shows Internal events and this chapter's Public events past their display
time, each marked; the member's filter is saved per user in the application's
database; a Register button acts on Internal events that take registrations.
F5 puts these on screen and does not reopen them.

*Requirements, ruled by Doug 09-30-26.* These are rulings. The design that
follows from them has not been drafted.

1. **Clicking an event opens a page of its own, behind the portal sign-in.**
   Not a pop-up over the home page. The page renders the same body the public
   event page renders — description, overview, syllabus, graphic, time and
   place — with the member's Register button in place of the public sign-up
   form, so an Internal and a Public event read alike. Every event therefore
   has an address an announcement or reminder email can link to, which is why
   the page was chosen over the cheaper pop-up. Cost accepted: one more route
   and template, and a sign-in deep link the portal does not yet support for
   this target. Follow-on details for the design: slug or id in the address,
   and whether an online Internal event's join link shows to every member or
   only to registered ones.
2. **The list shows the near term in full and folds the rest.** Every event
   in the next thirty days is listed. Below it one line — "8 more events later
   this year" — expands to show the events beyond the window, so a far-off
   event still has somewhere to be found without pushing the rest of the home
   page below the fold. The thirty days is a setting staff can change, default
   thirty. Not chosen: a fixed window alone (an annual meeting announced three
   months out would be invisible) and a fixed count (a busy week would hide
   next month behind a click).
3. **The saved filter is two switches: Internal events, and Public webinars.**
   Both on when a member first signs in; the member's choice is saved to their
   account (F3-8). A member who turns both off sees one line in the rail, "You
   have hidden all events", with a link to turn them back on — the rail never
   goes blank. No filter by kind of event or by subject: the list is short by
   ruling 2, and a forgotten filter is the commonest reason an event is
   reported missing. "Only my teams" needs no switch: a team-limited Internal
   event is never sent to a member outside those teams.
4. **Register is on the list and on the page, the same action in both.** An
   Internal event that takes registrations shows a Register button in its row;
   the row's button asks a one-line confirmation ("Register for Board Meeting
   on October 23?") before it acts, so a mis-click registers no one; the page
   carries the same button. After registering, the row reads "Registered" with
   a Cancel link. Not chosen: page-only (two clicks for what F3-7 defined as one
   action, and a button missing from the row reads as broken).
5. **On a phone the rail becomes a collapsed strip at the top.** Where the
   screen is too narrow for two columns, the list shrinks to one line — "Next:
   Mentor Roundtable, Tue Oct 14 · 3 more" — that expands on a tap to the full
   list, so the next event and the application tiles are both on screen with
   no scrolling. On a desktop the list is a left rail beside the tiles, which
   fill the remaining width (the portal's width cap is lifted). Not chosen:
   stacking the list above the tiles (a phone user reaching My Email scrolls
   past the events every time) or below them (the list is out of sight).
6. **A Public webinar's website link lives on its member page, not in the
   row.** Every event in the list opens its member page (ruling 1). For a
   Public webinar that page carries "View on the website" and "Sign up on the
   website" where an Internal event carries Register, because public sign-up
   needs the public form's consent and details. The rows stay title, date and
   marks only, which the phone strip (ruling 5) depends on. Not chosen: a
   second link in the row, or public webinars opening the website page
   directly (which would undo half of ruling 1).

**All six questions are ruled (09-30-26).** The design is
`CBM_Events_Portal_Calendar_Design.md`, revision 0.2: its two decisions are
ruled (D1 the member page address is the event's id; D2 the join link shows to
everyone when an event takes no registrations, to registered members only when
it does). Approved and **built as v0.235.0 on 09-30-26**, dark behind
`PORTAL_CALENDAR`; design revision 0.3 § 10 records the departures; the live
review is `OPEN-ITEMS.md` #37.

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
| 4.13 | 09-30-26 15:10 | Claude (Claude Code) | F5 built as v0.235.0 on Doug's approval, dark behind `PORTAL_CALENDAR`; live review owed (#37). |
| 4.12 | 09-30-26 14:56 | Claude (Claude Code) | F5 design decisions D1 and D2 ruled by Doug; design at revision 0.2, awaiting approval to build. |
| 4.11 | 09-30-26 14:50 | Claude (Claude Code) | F5 ruling 6 (Doug, 09-30-26, on Claude's recommendation): a Public webinar's website link is on its member page, not in the row. All six F5 questions ruled; design to follow in `CBM_Events_Portal_Calendar_Design.md`. |
| 4.10 | 09-30-26 14:48 | Claude (Claude Code) | F5 ruling 5 (Doug, 09-30-26, on Claude's recommendation): on a phone the rail becomes a one-line strip at the top that expands on a tap; on a desktop a left rail beside full-width tiles. |
| 4.9 | 09-30-26 14:39 | Claude (Claude Code) | F5 ruling 4 (Doug, 09-30-26): Register is in the list row (with a one-line confirmation) and on the event page, one action in both places. |
| 4.8 | 09-30-26 14:36 | Claude (Claude Code) | F5 ruling 3 (Doug, 09-30-26): the per-member filter is two switches, Internal events and Public webinars, both on by default; no filter by kind or subject. |
| 4.7 | 09-30-26 14:35 | Claude (Claude Code) | F5 ruling 2 (Doug, 09-30-26): the list shows the next thirty days in full, with a one-line reveal for events beyond the window; the window is a staff setting. |
| 4.6 | 09-30-26 14:32 | Claude (Claude Code) | F5 requirements gathering opened. Ruling 1 (Doug, 09-30-26): clicking an event opens a member page of its own behind the portal sign-in, not a pop-up, so every event has a linkable address. F5 state moved from Catalogued; what F3 already settled for F5 recorded. |
| 4.5 | 09-29-26 01:44 | Claude (Claude Code) | F2 and F3 built as v0.233.0 and their CRM fields applied to crm-test. Owed: the live review as real non-admins, production at a Sunday slot, Boston with its next release. |
| 4.4 | 09-29-26 00:58 | Claude (Claude Code) | The F2/F3 design's four decisions ruled by Doug; design at revision 0.2, awaiting approval to build. |
| 4.3 | 09-28-26 00:32 | Claude (Claude Code) | F2 and F3 designed together in `CBM_Events_Audience_and_Display_Design.md` revision 0.1, a draft awaiting Doug's review with four decisions (D1–D4). Both features' state updated. |
| 4.2 | 09-28-26 00:24 | Claude (Claude Code) | F2 requirements ruled by Doug (09-28-26): the display time applies on every page; it narrows the Publish to website checkbox rather than replacing it, and an empty one means as soon as ticked; registration opens at the display time; the Zoom webinar is still created when the event is ticked; a display time after the start is allowed, with a warning only when the event is still upcoming. Claude's decisions recorded separately: a visible "Appears" state in Event Administration, and the cache delay of about two minutes accepted. F2 and F3 are to be designed together. |
| 4.1 | 09-28-26 00:10 | Claude (Claude Code) | F3 requirements ruled by Doug (09-27-26 and 09-28-26): an event is Internal or Public; a Public event carries a reach of all chapters, one chapter or a list, always including the creating chapter; the reach is recorded now and the sharing across chapters is built later, not blocking the cutover; chapter names come from the CRM standard; the audience sits beside the Publish to website checkbox; Internal events are seen by every signed-in member unless limited to teams, and take registrations when a per-event checkbox says so; the portal calendar shows Internal and this chapter's Public events with a per-member filter saved in the application's database; F2's display time applies everywhere. Also recorded: the Association's rulings say nothing about events, and the public registration form's gate must check the audience. F3 state moved from Catalogued. |
| 4.0 | 09-27-26 23:24 | Claude (Claude Code) | Track F added: features found by user review, catalogued before design, required before the cutover (Doug, 09-27-26). F1 recorded — the event topic takes several values and a user-entered one. F2 recorded — a Display Date/Time before which an event stays off the public pages. F3 recorded — an event audience of Internal, a specific chapter, or Public, with Internal events forming a portal calendar. F4 recorded — presenters per event, with an optional biography copied from a mentor's profile or written by hand. F5 recorded — a left-hand list of upcoming internal events on the portal home page. The catalog is complete at five. Definition of done gains item 8 (Track F), and D3, the confirmation email, is named as required by item 2. |
| 3.0 | 09-14-26 18:15 | Claude (Claude Code) | Track A is done but for the redirect. Production switched on, schema probed and diffed, recorded library imported and published, consent and the duplicate hold both shipped, and a topic filter added on Doug's request. Remaining: the upcoming sessions, one end-to-end registration, and the redirect rule. |
| 2.1 | 09-12-26 14:05 | Claude (Claude Code) | First side-by-side against the live page. Track A gains A2b, the recorded-library backfill, which is blocking and needs two values from Doug. A2 records the three differences already fixed in v0.223.0. |
| 2.0 | 09-11-26 23:10 | Claude (Claude Code) | Track A rebuilt around Doug's 2026-09-11 ruling: the marketing site redirects to a page this app serves, and the presenting invitation moves onto it. The WordPress plugin, its proxy, its thumbnail proxy and its settings screen are struck. A1 is built (v0.222.0); the remaining Track A items are the browser pass, the per-event duplicate hold, the consent wording, and one redirect rule. Definition of done, sequence, decisions and verification gates follow. |
| 1.0 | 09-08-26 19:05 | Claude (Claude Code) | First draft. State verified against both live deployments and the website; seven-point definition of done; five tracks with owners and dependencies; two decisions for Doug. |
