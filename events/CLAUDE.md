# events/ — Events, Webinars and the public pages

Last Updated: 10-20-26 17:30 · Revision 1.0

Detail for Event Administration (`/events`), the public programme pages (`/webinars/`), presenters, topics, attendance, follow-ups, reporting and the portal events rail.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Events & Webinars — `/events`

Replaces the data layer behind `clevelandbusinessmentors.org/webinars/`, which
today runs on a Google Apps Script plus a browser-side YouTube API call with
**EspoCRM involved at no point** — so every registrant is an invisible lead.
Staff guide: `event-administration.md`; activation + test script:
`EVENTS-SETUP.md`; schema: `cevent-entities-crm-handoff.md`.

**Live on BOTH deployments since 2026-09-14; the website still runs on the Apps
Script.** `EVENTS_ENABLED` + `EVENTS_PUBLIC_API` are on for crm-test and
production; `ZOOM_EVENTS`, `EVENTS_REMINDERS` and the attendance pull are off
everywhere. Production's overlay also carries `YOUTUBE_API_KEY` and
`YOUTUBE_PLAYLIST_ID` (five playlists, comma separated) on the **web** component
only — the worker needs neither until attendance is switched on.

**Production holds a real programme now**: 10 recorded webinars imported from the
playlists on 2026-09-14 and published with topics, plus one internal
`CRM Training Webinar` that is **published** and dated in the future, so it is
currently the only thing on the public calendar — check whether that is intended
before the redirect. Zero registrations so far; the end-to-end test registration
is still owed.

**The only thing between here and the lead leak stopping is the redirect
itself** — one rule on the marketing site, and removing it is the rollback. Phases 1, 2, 3, 5
and **6** are built. **Phase 4 — the WordPress plugin — was STRUCK on
2026-09-11**: Doug ruled that the marketing site should **redirect** to a page
this app serves rather than embed or reimplement one. What stops the lead leak
now is one redirect, plus two things owed before it (`OPEN-ITEMS.md` 19d
consent, 19f the per-event duplicate hold).

## The PUBLIC pages — `/webinars/` and `/webinars/{slug}` (v0.222.0)

`events/pages.py` + `events/public_frontend/`. Gated on `events_public_active`,
so an unconfigured deploy serves nothing. Assets ride `/webinars-assets` — a
separate top-level path, because `/webinars/{slug}` is a route and "assets"
would be indistinguishable from a slug.

- **They are ROUTES, not static files, for two reasons.** A social crawler runs
  no JavaScript, so each event's `<head>` is filled **server-side** or a shared
  link renders as a blank card. And an unpublished event must **404** — `CEvent`
  doubles as the internal calendar, so a page that merely rendered empty would
  still confirm the record exists.
- **The body is the SAME renderer the staff preview drives**
  (`/events-plugin/cbm-events.js`) under the site's own stylesheet, so the
  preview and the live page are one code path rather than two kept in step.
- **The site's stylesheet has TWO wrapper scopes, and they are not
  interchangeable**: `.cbm-wb` for the calendar, `.cbm-yt` for the recorded
  library, each carrying its own CSS variables, every rule written as
  `.cbm-wb .panel …`. The wrapper must be an **ancestor** of `.panel`, never the
  same element. Getting this wrong unstyles a whole panel and raises no error —
  it shipped that way for an hour on 2026-09-11 and is now in the class contract
  (`HOST_CLASSES` in `tests/test_events_graphic.py`).
- **Branding renders first, page values second**, every value HTML-escaped, so
  CRM-authored content is never rescanned for a `{{token}}`.
- **Both public doors send `consent: false`** — the calendar modal and the event
  page's own form — so a registration records **no opt-in at all**. That is
  deliberate and blocking: see `OPEN-ITEMS.md` 19d.
- **`EVENTS_PUBLIC_BASE_URL` empty means "this app"** (derived from
  `APP_BASE_URL` + `/webinars`). It used to default to the marketing site's
  `/webinars`, which **404s**, so every shared event link pointed at nothing.
- **The marketing page's whole opening came across, not just its panels** — the
  navy hero, the gold strapline band and the organisation's own top-level menu.
  All of it is content on a page that redirects away, and the first side-by-side
  (2026-09-12) is what found it missing, exactly as it found the presenting
  invitation. Settings: `EVENTS_HERO_TAGLINE`, `EVENTS_HERO_PILLARS`,
  `EVENTS_HERO_BAND` (each emptiable) and `ORGANIZATION_SITE_NAV`
  (`Label|path` pairs; a leading `/` resolves against
  `ORGANIZATION_WEBSITE_URL`, so a chapter changes one setting, not seven).
  The menu is built **server-side** for the same reason the name is substituted
  there: a menu that appears a moment late is worse than none, and it is the
  visitor's only way on to the rest of the site.
- **The recorded library has a TOPIC filter** (v0.230.x). It offers only
  subjects that actually have a recording — a filter listing an empty one is a
  dead end — computed from the whole library rather than the current results so
  the options do not shift as a visitor searches, and hidden below two topics.
  The selector sits **above** the search box because the search runs *inside*
  the chosen topic, and the placeholder names it. Clearing the search box
  reloads on its own (`input`, not the `search` event, which Firefox does not
  raise). One CRM read serves the results, the topic list and the count:
  `published_recordings` plus the pure `filter_recordings` / `recording_topics`.
  Order follows the live field's option order (`service.live_topic_order`),
  `cfg.TOPIC_ORDER` as the fallback; a value that has drifted out of the enum
  still appears.
- **An event carries SEVERAL curated topics, and nobody types one** (v0.242.0,
  Track F F1, Doug's ruling 2026-10-08: *"They must pick from the list, or
  update the list if they do not like the choices."*). `CEvent.topics` is a
  multiEnum with the same ten values as the single `topic` it supersedes.
  **Feature-detected, no switch**: a CRM without `topics` behaves exactly as
  before; on a CRM with it the single `topic` is **retired** from the editor,
  the write whitelist and every read — `service.event_topics(row)` decides by
  whether the row carries the `topics` key (a CRM that lacks the attribute
  omits it), and never falls back to `topic` when `topics` is merely empty.
  A chosen filter topic matches a recording carrying it among others; the
  eyebrow, the grid chips and the Events tabs name all of them; public
  payloads keep `category` (the first topic) and gain `categories`.
  `scripts/migrate_event_topics.py` copies the old value once per CRM, after
  `scripts/plans/cevent-topics.json`. The retired column stays until a removal
  handoff. Design: `prds/events/CBM_Events_Topics_Design.md`.
- **Panel wording is the SITE's, not ours** — "Calendar of Upcoming Webinars"
  and "Find a Recorded Webinar". Inventing better names put our page out of step
  with the one it replaces; don't re-invent them.
- **⚠️ The recorded library is empty and that blocks the redirect**
  (`OPEN-ITEMS.md` 19i). The live page's library comes straight from the YouTube
  playlist; ours comes from `CEvent` rows with a `recordingUrl`, and there are
  none on either CRM. `scripts/import_youtube_events.py` fixes it and has never
  been run — it needs `YOUTUBE_API_KEY` and `YOUTUBE_PLAYLIST_ID`, neither of
  which is configured anywhere, and the playlist id is not in the live page's
  source.
- New settings: `ORGANIZATION_WEBSITE_URL` (the back-link and the menu's base,
  per-chapter like `DOCS_SITE_URL`) and `EVENTS_CONTACT_EMAIL` (the
  presenting invitation's address; empty falls back to `OPS_MAILBOX`).
- The portal's bottom section is **"Public pages"** and leads with Workshops and
  Webinars, beside the five intake forms.
- Redirect runbook: `EVENTS-SETUP.md` § 6b. **The rollback is removing the
  redirect** — under a minute, no deploy.

- **The staff Overview tab is the whole record, read-only** (v0.231.0, Doug's
  rule): facts left, driven by `EVENT_FIELDS` so a new spec field shows without
  a second edit; graphic + Summary + Full description + Syllabus right, rich
  text through the shared sanitizer. Every slot renders even when empty.
- **An event's partners and funders are RELATIONSHIPS, set in the editor's
  Sponsorship group** (v0.239.0, plan `prds/mailing-list-and-event-sponsorship-plan.md`).
  `events/config.SPONSOR_LINKS` names the two links (`partnerProfiles` →
  `CPartnerProfile`, `sponsorProfiles` → `CSponsorProfile`, both reversed as
  `sponsoredEvents`); they are feature-detected per load from
  `entityDefs.CEvent.links`, ride their own `PUT …/sponsors` with the exact
  set per link (never the record PUT — a `*Ids` write is ignored), and only a
  `noAccessToForeignRecord` denial escalates to the admin account. The
  Marketing Admin Role reads partner and funder profiles, it does not edit
  them (Doug's ruling 2026-10-07). Production and Boston lack the partner
  link until the Phase A handoff is applied there, so they show Funders only.
- **Presenters are RECORDS, one per presenter per event** (v0.241.0, Track F
  F4, `prds/events/CBM_Events_Presenters_Design.md`). `CEventPresenter` holds
  the biography, title, company, photo and order as **copies made when the
  presenter is added and never refreshed** from the Contact or the mentor
  profile (Doug's rulings 10-07/08-26) — a past event's page is the record of
  what was presented. Added from the editor's Presenters group: a Contact
  search, or a new person whose unknown email **creates a `Presenter`-typed
  Contact** (an existing Contact is reused untouched — no null-fill, no type
  merge). One switch per event, `showPresenterBios`. Every staff read and
  write runs **as the signed-in user** (D1: the Marketing Admin Role carries
  Contact create + read, mentor-profile read **and Assignment Permission
  `all`** — `scripts/migrate_presenter_roles.py`. **A role that creates a
  record the app leaves unassigned needs Assignment Permission `all`**: at
  *not set* or *team* EspoCRM's checker inspects the new record's teams and
  assigned users, and at *team* a record with neither is refused outright
  ("Assignment failure: assigned user or team not allowed") — read from
  `Acl/AssignmentChecker/Helper.php` on crm-test 10-08-26 after the live
  pass found Contact create 403ing on a role that had the create grant); the page reads run
  under the org key, whose role reads the entity. Photos ride routes **keyed on the event and the entry** (public by
  slug, portal by id, staff authenticated), never on an attachment id. Dark
  behind `EVENT_PRESENTERS` AND feature detection (fails closed). The bare
  `CEvent.presenters` link is unused and left in place. crm-test CRM done;
  production and Boston owed (`cevent-presenters-crm-handoff.md`).
- **Phase 6a attendance** (`events/attendance.py`, worker): pulls each finished
  online event's Zoom participant report and matches by email. An empty report
  means "not published yet", never "nobody came"; a `Manual`/`Check-in` source
  is never overwritten; an attendee matching no registration is recorded flagged
  rather than dropped. **Never run against real Zoom.**
- **Phase 6b follow-ups** (`events/notify.py`): five sends as the shared info@
  identity, from EspoCRM templates. Once per registrant/event/kind, ledgered on
  `followUpsSent` **after** a successful send and enum-checked first. Preview is
  the default. **Needs five templates** — `EventReminder`,
  `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA`, `EventSurvey` —
  and has no frontend yet.
- **The registration confirmation is CBM's own and the ONLY email a
  registrant gets** (v0.277.0, Track D D3, `events/confirm.py`; design
  `prds/events/CBM_Events_Confirmation_Email_Design.md`; Doug's rulings
  10-22-26). D3-1: *the confirmation is the ticket* — a Public event in an
  online format with no Join URL is on no page and takes no registrations
  (`visibility.needs_join_link`, both surfaces, no switch; Event
  Administration shows **Awaiting join link**); nothing is pasted by hand on
  a Public event, Zoom fills it at publish. D3-2: *one email, ours* — it
  carries the registrant's personal `zoomJoinUrl`, and `core/zoom.webinar_settings`
  turns Zoom's registrant emails OFF; the website is not redirected until
  Track C is tested and active. Three single-recipient kinds (Confirmation /
  Waitlisted / Seat Offered, templates `EventConfirmation` /
  `EventWaitlisted` / `EventSeatOffered`), ledgered on `confirmationSentAt`
  and `followUpsSent` (`Seat Offered`, plan `cevent-confirmation.json`), sent
  from both doors (orchestrator at delivery, `member.register_member`) and
  from the waitlist promotion, which now pushes the person to Zoom first.
  **A public online registrant with no personal link is NOT confirmed** —
  skipped with a reason; a redrive retries. App tokens (`{{joinUrl}}`,
  `{{cancelUrl}}`, `{{when}}` …, `confirm.TOKEN_NAMES`) are substituted after
  EspoCRM's render in the three sends AND the five follow-ups. Calendar file:
  `events/ics.py`. Templates: `scripts/seed_event_templates.py` seeds all
  eight once (crm-test done 10-22-26 13:32). Dark behind `EVENTS_CONFIRMATIONS`.
- **Phase 6c reporting** (`events/reporting.py`): the engagement **Events tab**
  (attendance rolled up across all of a client's contacts, deduplicated by
  event), the contact **Events tab** in the directory, and programme + conversion
  reports in `/events`. Conversion counts an attendee only when their engagement
  postdates their first attended event. **Both record tabs read the
  registrations under the org-wide key after the user's own read gates the
  tab** (v0.249.2, Doug's ruling 2026-10-11, option B): no team role reads
  `CEventRegistration`, so as the user they 403'd for every non-administrator
  since they shipped. Same rule as the partner / funder Events tab.
- **Registration recognition is designed, not built** —
  `prds/events/CBM_Events_Registration_Recognition_Plan.md` (Doug's rulings
  2026-08-17): recognise a returning registrant by a signed device token, else
  by an email-first lookup that **registers them and echoes nothing** (a public
  page that returns what we know is a harvester), else the normal form; a
  signed-in member is recognised through a **redirect handoff**, never by
  loosening the staff session cookie. CBM sends its own confirmation email.
  Prerequisite and live defect: the near-duplicate hold holds a person's *second
  webinar of the day* (`OPEN-ITEMS.md` 19f).
- **Phase 6d** `scripts/import_youtube_events.py` — playlist backfill, dry-run by
  default, importing **unpublished** because an upload date is not an event date.
  Never run against the real playlist.

- **⚠️ `CEvent` doubles as CBM's org calendar** — most rows are internal team
  meetings and mentoring-session mirrors. That is true **on crm-test (94 rows)**;
  **prod's `CEvent` is empty** because it was never connected to Google
  (verified 2026-08-08), so the first published event there will be a real one.
  Workshops share the entity. **Since v0.233.0 visibility is ONE rule in
  `events/visibility.py`** (F2 + F3, Doug's rulings 09-27/29-26): the tick
  (`publishToWebsite`, labelled **"Show this event"**, default false) decides
  *whether* — unticked is on no page; **`audience`** (Internal / Public)
  decides *where* — Internal is the portal calendar only; **`eventReleaseDate`**
  (reused as the display time) decides *when*, on every page. **An empty
  audience carries over from the tick** (ticked → Public), which is how old rows
  and a CRM without the field behave exactly as before. Every public read goes
  through `_public_where` AND re-checks each row with `visibility.is_shown`; the
  registration form uses the same rule; a guard test fails on any other read of
  the tick. A failed metadata read **fails closed** (502) — guessing "no audience
  field" would publish Internal events. The team limit (`internalTeams`) is a
  **display filter, not confidentiality** — every role reads all events in the
  CRM (ruling D4). Never hand-roll a public CEvent query
  ([[events-publish-gate]]). Design:
  `prds/events/CBM_Events_Audience_and_Display_Design.md`.
- **Zoom here is the explicit exception** to the mentor-sessions "user-supplied
  links only" ruling: the public webinar programme uses the CBM Zoom account via
  Server-to-Server OAuth (host `zweb@cbmentors.org`). Ask which world you're in
  before applying either ruling ([[zoom-user-supplied-only]]).
- **Vocabulary trap**: in the public payload `topic` means the event **TITLE**
  (Zoom/Apps-Script vocabulary); the category rides as `category`. Aligning the
  names would blank every title on the live site.
- **The live page restricts images** — it sends `content-security-policy:
  img-src 'self' data: https://drive.google.com https://*.googleusercontent.com`
  (measured 2026-09-11). Anything rendered INSIDE that page would have needed
  every event graphic and YouTube thumbnail proxied through the WordPress
  domain; hotlinked `i.ytimg.com` thumbnails also returned 503 there. Serving
  our own page sidesteps both, because our document carries no such policy —
  one of the reasons the plugin was struck.
- **`wp-plugin/cbm-events/` holds the two files the public pages run**: the
  renderer (`cbm-events.js`) and the site's **own stylesheet** (`cbm-events.css`,
  copied verbatim from the live page's Elementor widgets — keep it in sync, do
  not restyle it). The directory name is now historical; the plugin was struck,
  but these two files are how our pages look like the website, so they stay
  where they are. `/webinars/` and `/events/preview.html` both load them from
  this shipping location, which is what makes either a real check. **Neither
  `events/frontend/preview.css` nor `events/public_frontend/public.css` may
  style a contract class** — an approximation in one hid a live class-name drift
  for three weeks. Guard tests assert every class the renderer emits has a rule
  in the stylesheet, and that neither of our own sheets styles one. Both guards
  strip CSS comments first, since a comment naming a class is the opposite of
  styling it.
- **A per-event link comes from `CBMEvents.config.eventUrlBase`**, which the
  public programme page sets to `/webinars/`. The payload's `url` is now this
  app's own address for the event (derived from `APP_BASE_URL`), so it is
  usable rather than a 404 — but the renderer still takes the base from config,
  because a host serving these panels somewhere else needs its own. **Sign-up
  stays a modal on the calendar** (Doug, 2026-08-16); the event page is for
  reading, and carries its own form rather than the modal.

## The portal events rail and member page (from the root Portal section)

- **The events rail and the member page (F5, v0.235.0)** — behind
  `PORTAL_CALENDAR` (off by default, `/setup` → Features; needs Events on). The
  home view is a 22rem rail of upcoming events beside the tiles; **the portal
  has no width cap any more.** What the rail SELECTS is F3's and lives in
  `events/service.portal_calendar` + `events/visibility.py` — never re-filter
  in the portal. The rail shows `PORTAL_EVENTS_WINDOW_DAYS` (30) in full and
  folds the rest; two saved switches (Internal / Public) in the F3 preference
  store; Register/Cancel in the row and on the page behind a one-line
  confirmation; a phone strip at ≤767px. Every event opens
  **`/portal/events/{id}`** (the id, not the slug — Internal events often have
  none), a route registered ahead of the `/portal` static mount, whose body is
  the shared `frontend/shared/event-body.js` the public event page also uses.
  **Its reads are the member endpoints in `events/member.py`**, all through
  `is_shown(..., "portal")`, and **an event the member may not see answers 404
  in the same words as an unknown id** — keep it that way. The graphic comes
  from `/api/portal/events/{id}/image` because the public image route is keyed
  on the slug and gated on the public surface. Join link rule (D2): everyone
  when the event takes no registrations, registered members only when it does,
  decided server-side. **Where the link comes from (D3, v0.240.0):** the Join
  URL is **editable in Event Administration for Internal events only** — the
  spec's `editable_when` rule offers an app-managed field under a condition
  and `_writable` admits it only when the record *as saved* meets it; for a
  Public event Zoom owns the field and a posted-back value is dropped.
  Design: `prds/events/CBM_Events_Portal_Calendar_Design.md`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
