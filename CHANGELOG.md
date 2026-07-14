# Changelog

All notable changes to **cbm-client-intake**. Versions are the value reported by
`/healthz` and the page footer (sourced from `pyproject.toml`), and double as the
deploy marker on App Platform.

## [0.44.0] — 2026-07-14

### Added
- **Client Administration: click-to-edit Notes column** on the engagements grid
  (new rightmost column). Clicking a cell opens an inline editor (Save / Cancel,
  Escape cancels); notes are stored in **`CEngagement.description`** via the new
  `PUT /assignments/api/engagements/{id}/notes` endpoint
  (`service.update_engagement_notes`), written as the signed-in user. These are
  staff-internal process notes about the assignment: `description` is surfaced
  in no other user interface — the session tools' metadata-driven Details tab
  now explicitly excludes it for CEngagement (`sessions/details.py`
  `_ENTITY_EXCLUDED`), on both render and save. Note: the intake orchestrator's
  enum-drift follow-up note also lands in `description`, so it shows in the
  Notes column — by design (it is exactly triage material); editing the cell
  replaces it.

## [0.43.0] — 2026-07-14

### Added
- **My Mentor Profile release marker** — first deploy of the `/mentorprofile`
  tool (v0.42.0 + v0.42.1 below). `CMentorProfile.mentorSummary` was built on
  crm-test (Text, verified live 2026-07-14), so the feature-gated summary box
  activates there on this deploy. Prod still lacks
  `mentorTitle`/`profilePhoto`/`mentorSummary` — the tool deploys inert-ish
  there (summary box hidden by the gate; headline/photo need the prod field
  build per `cmentorprofile-summary-field.md` + CLAUDE.md).

## [0.42.1] — 2026-07-14

### Changed
- **The `/mentorprofile` website preview is now an EXACT reproduction of the
  live mentor page** (Doug's ruling: mentors edit to look good on the website,
  so the preview must be what the site renders). The page's own HTML + CSS
  (the Elementor widget on clevelandbusinessmentors.org/mentor/…, fetched
  2026-07-14) are copied verbatim into the preview — navy hero with the
  gold-ringed circular photo (gradient placeholder when no photo, same as the
  site's fallback), name + gold title line, the 1fr/2fr profile grid (gold
  "ABOUT {FIRST}" label + summary + Request-a-Mentor / LinkedIn buttons +
  Industry Experience box left; Areas-of-Expertise gold-dot list + navy-ruled
  About box right), and the navy bottom panel ("Ready to Connect with
  {first}?" / Meet All Our Mentors / Questions). Rendered at the site's
  1200px desktop width and scaled to fit the pane; expertise/industry fill
  logic mirrors the page's own script; static links are inert (a real
  LinkedIn URL opens new-tab); first name flows into all four name slots.

### Added
- **`mentorSummary` — the website's short summary paragraph, feature-gated.**
  Doug's ruling: a new dedicated CRM field feeds the left-column summary
  (distinct from `aboutMentor`). NOT built in the CRM yet — the app
  feature-detects it from metadata (`sessionTranscription` precedent): the
  editor box, reads, and saves activate on their own once the CRM team builds
  it (spec: `cmentorprofile-summary-field.md`, incl. the full page-slot ↔ CRM
  field mapping for the website feed).

## [0.42.0] — 2026-07-14

### Added
- **My Mentor Profile (`/mentorprofile`)** — a self-service tool where a mentor
  edits their OWN `CMentorProfile` + linked Contact from one screen, with a
  **live preview styled like the public website mentor page** (the CRM feeds
  the website, so the pane shows exactly what the site will render: photo =
  `profilePhoto`, name = Contact first/last, headline = `mentorTitle`,
  Areas of Expertise = `areaOfExpertise`, Industries Served =
  `industryExperience`, About = `aboutMentor`, LinkedIn = Contact
  `cLinkedInProfile`). Linked from the portal for **Mentor Team** members
  (`MENTOR_PROFILE_ALLOWED_TEAMS`, default `Mentor Team`; friendly aliases
  `/mentorprofile`, `/myprofile`).
  - **Always "me":** no record id is ever taken from the request — every
    endpoint resolves the caller's own profile server-side
    (`sessions.service.resolve_manager_profile`), and all reads/writes run as
    the logged-in user (EspoCRM enforces their ACL).
  - **Non-administrative field set** (`mentorprofile/service.py:PROFILE_FIELDS`
    — the single source for the form layout AND the server-side whitelist):
    public-profile fields (photo, headline, publish toggle, expertise,
    industries, about, LinkedIn), contact info (name/email/phone/address, on
    the linked Contact), mentoring preferences (accepting, pause window,
    business stages, languages, years), and the internal bios. Status,
    compliance, dues, capacity, departure etc. are absent from the whitelist,
    so a smuggled change is dropped. Same protections as Mentor Admin: diffed
    saves, drifted-enum sanitization with plain-language warnings, E.164
    phone, CRM-required fields enforced from metadata.
  - **Photo upload/remove** — `CMentorProfile.profilePhoto` (image field):
    JPEG/PNG/WebP/GIF ≤5 MB, uploaded immediately as an Attachment; the app
    proxies the image bytes (`GET /mentorprofile/api/photo`, new
    `EspoClient.download_attachment`) since the browser can't reach the CRM.
  - Full-width layout with a drag splitter (form left, preview right); the
    unpublished state shows a banner + dimmed preview.
  - **CRM prerequisites** (crm-test has the fields; see CLAUDE.md): prod needs
    `mentorTitle` + `profilePhoto` built; the Mentor Team role needs
    CMentorProfile read/edit-own, Contact edit-own, and Attachment
    create/read for the photo.

## [0.41.2] — 2026-07-14

### Changed
- **No page-width cap — fields pack instead** (Doug's ruling: users are on 4K
  monitors; density comes from more data per row, not a narrower page). The
  0.41.1 `max-width: 1080px` is gone. Edit-form fields are now CONTENT-SIZED
  flex items that wrap: each width class is a sensible size for that field's
  data, and a line holds as many fields as the screen fits (5+ Identity fields
  per line at ~1700px, more at 4K; graceful wrap on laptops). Checkbox sets
  flow into as many columns as fit. The postal address block keeps its fixed
  internal proportions and packs as one cell (billing/shipping side by side
  whenever they fit).

## [0.41.1] — 2026-07-14

### Changed
- **Edit-form density pass** (Doug's review of 0.41.0): forms cap at 1080px
  wide, so a span-8 street field is ~40 characters instead of 100+; tighter
  group/row rhythm. **Billing and shipping addresses sit side by side** on one
  panel (billing left, shipping right, each with its own heading) — half the
  vertical space; the Contact address block is half-width too. **Country now
  lives inside the address block** (it was orphaned in Additional details).
  Company Identity groups all three industry fields on one row (Industry |
  Industry sector | Industry subsector — subsector was stranded at the bottom)
  and gains Email address. "Same as billing" now restores the original
  shipping values when unchecked (checking still copies billing over them).
- LinkedIn field labels render as "LinkedIn …" — the label generator no
  longer splits the brand into "Linked In" (`sessions/details.py:_label`).

## [0.41.0] — 2026-07-13

### Added
- **Section edit screens (prompt v0.1 / mockup v2)** for the session tools'
  Details tab: every section/contact edit form is now a curated, grouped
  12-column layout instead of a flat auto-fill field dump
  (`sessions/frontend/app.js` `DETAILS_LAYOUTS` + `layoutForm`).
  - **Edit Engagement** — Status | Start date | Mentor (read-only — Doug's
    ruling: reassignment stays in Client Administration) | Session cadence on
    one row; every other editable engagement field in "Additional details".
  - **Edit Company** — Identity (name/website/phone; org type/stage/industry/
    sector) + Billing address + Shipping address. **On the mentor domain the
    Partnership & account group is removed by design** (Account type, Client
    status, Partner/Sponsor fields, Public announcement) and the Company VIEW
    card's Account/Cadence/Announcements rows are gone — the right column now
    carries Business + Shipping. Partner/sponsor domains keep a curated group
    of their own relationship fields (Doug's scoping ruling); the system
    discriminators (`cAccountType`/`cClientStatus`/`cCompanyType`/`type`) are
    edited nowhere.
  - **Edit Client Business Profile** — Business structure / Financials /
    Sales & market / Certifications & owner demographics / Goals, with
    checkbox sets and mockup wording.
  - **Edit Contact** — Name / Contact information / Address / Preferences &
    agreements; used by row edits AND the + Add → Create-new-contact flow
    (same grouped form, empty).
  - Uncurated editable fields always land in an "Additional details" group —
    nothing the CRM exposes becomes uneditable; a missing field skips cleanly.
- **Reusable postal address block** (billing/shipping/contact): Address line
  1 (8) | line 2 (4); City (6) | State (2, US-state select) | ZIP (4). The two
  street lines map to EspoCRM's single multi-line street field (split on
  render, rejoined on save). The shipping instance gets a **"Same as billing
  address"** checkbox — checked dims/disables shipping and mirrors billing
  values live (the CRM models this as copied values; there is no flag).
- **Time-picker standard for every time field app-wide**: datetime fields are
  now a Date input + a time field opening a popover — half-hour slots
  ("Morning" 8:00–11:30 AM, "Afternoon & evening" 12:00–7:30 PM, 4 columns,
  navy selection) with an "Other time" free-entry escape (Enter commits;
  invalid input flags red). Replaces the browser `datetime-local` control
  (and its minute spinner) everywhere in the session tools, including the
  session editor's Start (UTC round-trip and the duration→dateEnd derivation
  unchanged; required-field check still fires when date or time is missing).
- **Multi-value fields are tap-to-toggle chip selectors** (funding sources,
  sales channels, certifications, contact type, meeting type, …) — never
  multi-select list boxes or checkbox grids. Options come from the CRM field
  definitions; a stored value that has drifted out of the options still
  renders selected so a save can't silently drop it.

### Changed
- `sessions/details.py` no longer hides `name` from the field spec, so
  Company name (and other varchar `name` fields) is editable on the forms;
  Contact's `personName`-typed name is still composed from first/last. The
  view suppresses the redundant "Name" row/cell (the card title/page header
  already shows it).

## [0.40.2] — 2026-07-13

### Changed
- **New sessions pre-invite ALL related contacts, not just CBM contacts**
  (Doug's ruling, widening the CBM-only default of v0.37.1): the attendee
  picker on a NEW session starts with every client/partner/sponsor contact
  AND every CBM contact checked (`defaultAttendees()` in the sessions
  frontend). Unchecking stays an explicit choice, and — with the calendar
  integration on — the Google Calendar invitations now reach the client
  contacts by default too. Editing an existing session still shows its
  actual attendee set.

## [0.40.1] — 2026-07-13

### Added
- **The meeting link is now visible and copyable** (Doug's live report after
  the first successful calendar event: the Meet URL existed only behind the
  Start Session button, with no way to copy it). It now shows as a clickable,
  truncating URL with a ⧉ copy-to-clipboard button in two places: the
  Overview's **Next session** callout (under the date, above Start Session)
  and the read-only **session view**'s facts grid (a "Meeting link" row,
  next to Meeting type/Location). New `linkWithCopy` helper reusing the
  attendees-grid copy machinery; `addKV` gains a `copylink` type. Verified in
  the stub harness (render, href, copy-failure notice path).

## [0.40.0] — 2026-07-13

### Added
- **Sessions create Google Calendar events with Meet links.** Saving a
  **Scheduled** session in any session tool now creates a Google Calendar
  event on the manager's OWN calendar (delegated as their
  `CMentorProfile.cbmEmail` via the shared service account — the same
  domain-wide-delegation stack the comms Gmail integration uses), with a
  **Google Meet** conference whose URL is written back to
  `CSession.videoMeetingLink`, and the session's attendee contacts invited
  (Google emails the invitations, `sendUpdates=all`). Later edits to
  time/title/attendees **patch the same event**; setting the status to
  Cancelled **cancels it** (clearing the stored event id and the generated
  Meet link — a hand-typed non-Meet link is never touched, and a session with
  a hand-typed link gets an event without a Meet conference, the link carried
  in the event's location). Logging a Completed past session never creates an
  event, and a notes-only edit never touches the calendar. New:
  `core/gcalendar.py` (delegated Calendar REST client), `sessions/gcal.py`
  (the best-effort sync hook — a Google failure never fails the session save;
  the outcome rides the save response as `calendar:{ok,...}` and shows as a
  notice in the UI). **Gated OFF by `GCAL_EVENTS`** and additionally inert
  until the CRM gains `CSession.googleCalendarEventId`
  (feature-detected via metadata; CRM handoff: `csession-calendar-field.md`).
  Activation also needs the Google Calendar API enabled in the GCP project
  and the `calendar.events` scope added to the service account's
  domain-wide-delegation grant. Replaces the crm-test-only EspoCRM
  server-side calendar sync experiment (personal account) — **disable that
  before enabling this**, or sessions get double events; production never had
  it (the app owns all email + calendar operations). 28 new tests.

## [0.39.2] — 2026-07-13

### Fixed
- **Session times now convert between the viewer's timezone and UTC** (live
  report: Google Calendar meetings didn't match the time shown in the app).
  The app itself creates no calendar events — EspoCRM's server-side Google
  Calendar sync does, from the `CSession.dateStart`/`dateEnd` the app writes,
  and the EspoCRM API treats those datetimes as **UTC**. The sessions frontend
  was sending the user's local wall-clock digits verbatim (and displaying
  stored digits verbatim), so a session entered as 3:30 PM Cleveland was
  stored as 3:30 UTC and the synced calendar event landed hours off. The
  frontend datetime boundary now converts both ways
  (`sessions/frontend/app.js`: `parseNaive` parses stamps as UTC,
  `fromLocalInput`/`toLocalInput` convert the datetime-local editor value
  local ↔ UTC, `stampPlusSeconds` emits UTC for the derived `dateEnd`,
  `fmtWhen` displays local) — the app, the EspoCRM UI, and Google Calendar
  now agree, each rendering in the viewer's own timezone. Date-only values
  (e.g. `formationDate`) still parse as local calendar dates, so they don't
  shift a day. Backend unchanged (it already assumed CRM datetimes are UTC).
  **Note:** sessions saved *before* this fix stored local digits as UTC and
  remain offset until manually re-saved with the correct time (Doug's ruling —
  no backfill, since a script can't distinguish app-created sessions from
  ones entered correctly via the CRM UI).

## [0.39.1] — 2026-07-13

### Fixed
- **CBM Contacts "+ Add" never opened its menu** (Details tab, live report).
  `repaintDetails` mapped any key starting with "c" to the Client Contacts
  card — and the CBM card's own key `cbmContacts` starts with "c", so every
  CBM-card repaint redrew the client card instead and the + Add menu (and the
  pick-a-mentor panel) never appeared. Row-edit keys (`c0…`/`b0…`) are now
  matched exactly. Verified in the stub harness: CBM + Add → menu → picker
  loads; client/CBM row Edit still expand.

## [0.39.0] — 2026-07-12

### Added
- **Session tools Details tab: contacts can now be removed.** Every Client
  Contacts row and every co-mentor row in CBM Contacts gets a **Remove** action
  (two-step inline confirm — "Remove" → "Really remove?" — no browser dialogs).
  Removal detaches the relation only (`engagementContacts`/`contacts`/
  `sponsorContacts`, or `additionalMentors` for co-mentors): the contact /
  mentor profile record itself stays in the CRM. The **assigned Mentor row is
  not removable** — that link is managed in Client Administration. Remove is
  shown only when the signed-in user can edit the parent record (the unrelate
  is a parent-relation write), and is hidden while the row's edit form is open.
  New endpoints: `DELETE /{slug}/api/records/{id}/contacts/{contactId}` and
  (mentor domain) `DELETE /{slug}/api/records/{id}/comentors/{profileId}`.
  Add flows (select existing / create new / pick CBM contact) already existed
  (v0.33.0); this completes the add/remove pair.

## [0.38.2] — 2026-07-12

### Added
- **Assigned mentor on the engagement Overview** (it wasn't displayed anywhere
  on the page): a key fact on the upper-left rail, right above Meeting
  cadence, linked to a pop-up of the mentor's profile (`CMentorProfile` added
  to the peek allowlist — mentor type, status, CBM email, areas of expertise,
  industry experience).

## [0.38.1] — 2026-07-12

### Fixed
- **Company now shows for intake-created engagements** (prod report: the Agape
  — James Koran engagement had a blank Company in the mentor sessions grid
  despite the client and company existing in the CRM). Root cause: the grid —
  and the Overview / Details / contact-company stamping — read
  `CEngagement.clientOrganization`, but the client-intake orchestrator never
  wrote that link; intake puts the Account on the CLIENT PROFILE
  (`CClientProfile.linkedCompany`) only. Two-part fix: (1) the orchestrator now
  links the Account to the engagement itself on create, and (2) for existing
  records the session tools fall back through the client profile's
  `linkedCompany` (`DomainConfig.company_fallback`) — the grid Company column +
  pop-up, the Overview's aggregated Company link, the Details company card, and
  the company stamped onto added/created contacts all resolve it. Best-effort:
  a profile the user can't read just leaves the company blank.

## [0.38.0] — 2026-07-12

### Changed
- **Records open as a dedicated page — `/{slug}/record/{id}` — not a mode of
  the list** (Doug's ruling: a record in another tab must be a real page, and
  "Back to list" goes away). Clicking a record on the grid opens
  `/mentorsessions/record/<id>` (partner/sponsor likewise) in a new tab: the
  server serves the shared frontend with a `<base href="/{slug}/">` so its
  assets resolve, and the JS boots **straight into that record** — no records
  list is fetched at all on a record page, and the browser tab is titled with
  the record's name. The list page is now purely a launcher; the "← Back to
  list" button and the old `?record=` deep-link mode are removed. Session
  editor/view navigation within a record page is unchanged ("Back to record").

## [0.37.2] — 2026-07-12

### Fixed
- **CBM contacts really are invited by default now** (0.37.1's default came up
  empty on live data, found by Doug on first use). Two live-data realities the
  0.37.1 implementation missed: engagements almost never carry
  `additionalMentors` (the CBM person on the record is the **assigned mentor**
  on `CEngagement.mentorProfile`), and several mentor profiles have **no
  linked contactRecord**. The invitee set is now resolved server-side
  (`cbmContacts` on the detail read): the assigned manager's profile plus any
  co-mentors, each resolved to a Contact via `contactRecordId` with a
  fallback Contact lookup by the profile's `cbmEmail` (the comms precedent),
  deduped. Profiles that resolve to no Contact are skipped — the durable fix
  for those is linking the profile's contactRecord (or cbmEmail) in the CRM.

## [0.37.1] — 2026-07-12

### Changed
- **CBM contacts are invited by default on new sessions** (Doug's ruling): the
  attendee picker now lists the engagement's CBM contacts (co-mentors with a
  linked Contact, tagged "(CBM)") alongside the client contacts, and a NEW
  session starts with every CBM contact pre-checked — in the dirty-tracking
  baseline, so unchecking is an explicit choice. Client contacts start
  unchecked as before.
- **Session view band, refined:** the "Client Session" type chip is gone — the
  type renders only when it differs from the domain's default, so it appears
  exactly when it says something. The **status badge (Scheduled/Held/…) moves
  to the center of the band and renders larger** — it is the key value. Date
  range stays left; Start Session / Open Meeting Link stays right.

## [0.37.0] — 2026-07-12

### Changed
- **Session detail View — Doug's session-details design rulings applied
  (Display Standard §12 extended).** Every fact appears exactly once:
  - **The band carries the time RANGE** ("Thursday, July 9 — 2:00 PM–3:00 PM",
    end computed from `dateEnd`); the Duration key-value row is gone.
  - **The video link is the band's action** — "Start Session" on a future
    session, "Open Meeting Link" on a past one — not a grid row.
  - **New ATTENDEES grid** replaces the attendee name-chips: Name / Role /
    Company / Email / Phone / Status. Names open the contact peek, companies
    the Account peek; email and phone carry per-cell ⧉ copy; the zone header
    offers **⧉ Copy grid** (TSV with headers — pastes into Excel/Sheets as
    columns) and **⧉ Copy emails** (comma-separated recipient list). Role
    derives from the open record (related contact → Client, co-mentor's
    contact → CBM); Status derives from the session (Held → Attended,
    No Show → Expected, else Invited) — per-person invited-vs-attended state
    is a pending CRM modeling ruling. §12.4's "Expected attendees" wording
    stays for No Shows. The table scrolls inside its card on narrow windows.
  - **Transcript zone (§12.5 lifted, feature-gated).** When the CRM gains the
    `sessionTranscription` field, the view renders it: attached → the text in
    its own scrolling allotment with **Find in transcript** (honest match
    count, first-match jump, text-node-safe highlighting); empty → "No
    transcript is attached… paste the meeting transcript into the Transcript
    box in Edit" (omitted for Cancelled/No Show per §12.4). The editor gains
    the Transcript box the same way — `/fields` serves it only when the CRM
    field exists, so a save can never send what the CRM must reject. Until
    the field lands, nothing renders (§12.5's no-stub rule stands).
  - Backend: `GET /sessions/{id}` now answers `attendeeDetails` (email/phone/
    company via the richer `sessionAttendees` read) and
    `transcriptFieldExists`; the transcript column is selected only when it
    exists (it will be the record's longest text — it never rides reads that
    don't render it).

### Fixed
- **The session view never showed Session Notes.** It read `s.notes`, but
  `GET /sessions/{id}` serves the raw CRM name `sessionNotes` (only the
  Overview feed maps to `notes`) — so the zone always fell to the empty
  copy. Verified rendering on the stubbed-API preview harness.

## [0.36.6] — 2026-07-12

### Added
- **Records grid (all three session tools):**
  - **Company column is a link** opening the standard aggregated
    company/client pop-up (the same peek the Overview uses: Account + the
    client/partnership/sponsorship profile). Sections the user's ACL can't
    read are now **omitted** — an unassigned user just sees the company
    information, with no permission noise (this also applies to the
    Overview's Company pop-up).
  - **Records open in a separate browser tab**: the name column is a real
    link (`?record=<id>` deep link, target=_blank), so several engagements
    can be worked simultaneously. The URL tracks the open record (refresh
    stays on it; Back to list clears it).
  - Column-header sorting already existed (click to toggle ▲/▼) — verified
    working; no change.

## [0.36.5] — 2026-07-12

### Fixed
- **`EspoClient.unrelate` used a URL form this EspoCRM rejects** (found live
  while unlinking Mindy Bower from the Agape engagement: the path-suffix
  DELETE 404'd; the documented body form succeeded). Now sends the id in the
  request body. This method backs the sessions attendee sync and the
  Communications "Not related — remove" unlink, both of which would have
  silently warn-logged on failure.

## [0.36.4] — 2026-07-12

### Fixed
- **A CBM member added from compose landed under "Other Contacts"** (Doug's
  report). A member reached via the personal address on their Mentor-typed
  Contact had no mentorProfileId in the lookup (the profile scan only ran
  for @cbmentors.org addresses), so the dialog fell back to a client-contact
  link. The lookup now also resolves the profile through its Contact link,
  and a CBM member is NEVER linked as a client contact — with no co-mentor
  path (partner/sponsor domains), their row shows a disabled "Will receive
  the email" instead.

## [0.36.3] — 2026-07-12

### Fixed
- **CBM members now get the "Add" checkbox in compose** (Doug's report: no
  checkbox for a CBM recipient). Two causes: the frontend skipped
  `@cbmentors.org` addresses entirely, and the CRM lookup only searched
  Contact email addresses while a member's work address lives on their
  MENTOR PROFILE (`cbmEmail`). The lookup now matches mentor profiles too,
  and a CBM member's row shows **"Add as CBM contact"** — on the mentor
  domain, checking it adds them as a co-mentor (the record's CBM-contact
  relationship), not a client contact. The server-side send guard still
  never blocks internal addresses.

## [0.36.2] — 2026-07-12

### Changed
- **Compose dialog redesigned to checkbox rows + one Send** (Doug's design):
  every non-record recipient gets an "Add to this record" checkbox (default
  on) — an existing CRM contact of ANY type (client, non-client, CBM member)
  shows who they are and links on Send; a new address shows the
  first/last/phone/company form (existing-Account picker or new company);
  unchecked rows send as a one-off (thread still followed, conversation
  still attached). A single Send click links/creates all checked rows, then
  sends. The compose/view modal is now a workspace-sized dialog
  (min(90rem, 94vw), 16rem message area) instead of a 40rem pop-up.

## [0.36.1] — 2026-07-12

### Changed
- **Compose dialog: CRM-wide lookup before offering to create a contact**
  (Doug's refinement of the non-contact recipient flow). Each unknown
  recipient's address is first searched across the whole CRM
  (`GET /{slug}/api/contactlookup`): an existing contact gets one button —
  "Add to this record & send" (links the existing contact; no duplicate) —
  and a CBM-member match short-circuits to "Send anyway". Only a
  genuinely-new address shows the create form, which now collects first/last
  **+ phone + company** — company picked from existing Accounts
  (`GET /{slug}/api/companies`) or typed as a new name (find-or-create via
  the intake API user, mirroring the intake orchestrators' policy;
  `ContactAddIn.newCompanyName`).

## [0.36.0] — 2026-07-11

### Changed
- **Staff tools: minor CRM rejections no longer stop a save, and what does
  fail speaks plain language — never a raw 502/504.** Two layers (extending
  the non-required-enums-never-block policy to Mentor Administration):
  1. **Mentor Administration saves sanitize enums server-side** (mirroring the
     sessions engine): an enum/multi-enum value the live CRM no longer offers
     is dropped before the write — the rest of the save proceeds, the drop is
     logged, and the save response carries plain-language `warnings` that the
     editor shows in a new amber "Saved, with a note:" notice. Fails open when
     options can't be fetched.
  2. **All three staff routers (mentoradmin / sessions / assignments) translate
     EspoCRM `validationFailure` 400s** into a readable 400 naming the field
     ("The CRM did not accept the save: 'How Did You Hear About CBM' has a
     value the CRM does not accept…") via the new `core.espo.validation_message`
     helper, instead of wrapping the raw CRM body in a 502 (which the edge
     showed as a 504). Genuine server faults still 502; expired sessions
     still 401.

## [0.35.2] — 2026-07-11

### Added / Fixed

*(also folds in the same-day activation fixes originally logged as a duplicate 0.35.1):*

- **Communications live-activation fixes** (found activating on crm-test —
  the CRM entities were built + probe-verified the same day):
  - `requests` was a missing dependency of google-auth's token transport
    (latent since v0.11.0 — first live Gmail call exposed it).
  - All varchar writes clamp to the as-built 100-char CRM fields (the first
    backfill 400'd on `snippet` maxLength, storing conversations but no
    messages); spec updated with as-built lengths.
  - Gmail **drafts are never ingested** (each draft revision is its own
    message — the source of a duplicated "Re:" pair and one never-sent
    "conversation"); SPAM/TRASH skipped too.
  - Quoted chains no longer leak into stored bodies: the "On … wrote:"
    header is matched even when line-wrapped, and `>`-prefixed quoting
    inside HTML bodies is truncated.
  - **Per Doug: `bodyCleaned` is now the author's NEW TEXT ONLY** — the
    demoted quoted-reply zone is no longer stored or rendered; a quote-only/
    image-only message stores a small placeholder instead of raw quoted text.
- **`GMAIL_RESYNC` one-shot ops lever**: set on the worker + deploy to clear
  every mailbox's sync cursor so the backfill re-runs idempotently; unset
  after one pass. Used twice during activation to re-drive dropped messages.

- **Non-contact recipients: the full design** (from Doug's scenario review —
  sending from a record to someone who isn't a record contact):
  - **Thread-following ingest** (correctness fix): a message now qualifies for
    ingest when it involves a record contact's address OR belongs to a Gmail
    thread that is already a stored conversation. Replies to any
    manually-established conversation (confirmed send, "Add emails…") keep
    arriving even when the correspondent is on no contact record — previously
    they were silently skipped.
  - **Durable attachment on confirmed sends**: a send confirmed to non-contact
    recipients now writes the same include override "Add emails…" writes, so
    a resync can never drop the conversation (the Sam-Smith-test lesson).
  - **Guided compose dialog**: instead of a bare "Send anyway", the compose
    modal now routes each non-contact recipient to the right fix — add the
    address to an existing contact (the durable fix; auto-resends as a normal
    matched send), create-and-link a new contact on the record, or an explicit
    one-off "Send anyway — attach this conversation only".
  - **CBM-internal recipients (`@cbmentors.org`) are never "unknown"** —
    emailing a co-mentor/staff about the record no longer trips the guard
    (their copy dedups by Message-ID when their own mailbox syncs).

## [0.35.1] — 2026-07-11

### Fixed
- **Mentor Administration: saving a mentor 400'd (surfaced as 502/504) after
  picking a "How they heard about CBM" value.** The CRM converted
  `CMentorProfile.howDidYouHearAboutCBM` from free-text to a real enum, but the
  editor still offered a hard-coded list from the free-text era (only "Other"
  was still valid), and the frontend prefers a field's static list over live
  options — so a picked value failed EspoCRM validation and blocked the whole
  save (hit live on prod saving Allen Ingram). The static `HOW_HEARD_OPTIONS`
  list is gone; the field's options are now pulled live from CRM metadata like
  every other enum (`service.field_options`), so the dropdown always offers
  exactly what the CRM accepts.

## [0.35.0] — 2026-07-10

### Added
- **Communications: the Gmail conversation integration is BUILT** (app side —
  per `prds/communications-gmail-integration.md`; gated OFF by `GMAIL_SYNC`
  until the CRM entities + Google scopes exist):
  - **Gmail access** (`core/gmail.py`): the existing Google service account
    with domain-wide delegation, extended to `gmail.readonly`/`gmail.send`,
    minting per-mailbox tokens. The impersonation subject is always derived
    server-side (the sync's enumerated managers; the signed-in user's own
    `cbmEmail` for search/send) — never from request input. Every access
    is logged.
  - **Email cleaning** (`core/email_clean.py`): the CRM_Extender pipeline
    ported (dual-track: quotequail + BeautifulSoup structural stripping with
    the tuned edge-case guards, mail-parser-reply + regex fallback), producing
    two-zone output — the author's new content, plus the quoted reply chain
    demoted into `<blockquote class="quoted-reply">`. Signatures, disclaimers,
    and boilerplate are deleted; the raw original stays in Gmail (deep links).
  - **Sync engine** (`comms/`): per-mailbox Gmail `historyId` incremental sync
    with expired-cursor date-window backfill and new-address targeted
    backfill; scope = ACTIVE records' contact addresses only; RFC Message-ID
    dedup across co-mentor mailboxes; conversation formation (thread id +
    cross-mailbox References merge); triage (no-reply/OOO/marketing mail is
    never stored); CRM upsert as `CConversation`/`CCommunication` linked to
    the engagement/partner/sponsor + contacts, owner-stamped via
    `assignedUsers`. Runs in the delivery worker on its own timer. State in
    Postgres (Alembic `0004_comms_sync`: cursors + curation overrides).
  - **Optional AI summaries** (`comms/summarize.py`, `COMMS_AI_SUMMARY`,
    default off): Claude summaries/status/action items per conversation via
    structured outputs, refreshed when new mail arrives; failures degrade to
    `Uncertain`. No Anthropic key or data egress when off.
  - **Endpoints** (per session-tool domain): conversation list + thread read
    (as the user, ACL-enforced), record-level exclude, mailbox search +
    include-thread, add-contact-address, and **send/reply as the manager's own
    @cbmentors.org address** (proper In-Reply-To/References threading, sent
    into their real Sent folder, written through immediately; recipients
    outside the record's contacts require an explicit confirm).
  - **Frontend**: the Communications tab now renders real conversations when
    enabled (status/participants/summary list → thread view with two-zone
    bodies, action-items callout, Open-in-Gmail links, reply/compose wired,
    "Not related — remove" and "Add emails…" curation). With the flag off it
    keeps the sample-data scaffold.
  - **CRM handoff spec**: `cconversation-entity.md` (entities, links, grants,
    layouts) — the CRM-side build is the activation prerequisite, along with
    authorizing the two Gmail scopes on the delegation grant.
  Verified: 25 new unit tests (cleaning corpus, sync engine with fakes,
  endpoint gating) — 342 total green — plus the full UI loop in the stubbed
  browser harness. NOT yet run against a real mailbox or CRM (blocked on the
  CRM entities + scope authorization).

## [0.34.1] — 2026-07-10

### Added
- **Session duration across the session tools.** `CSession.duration` is
  EspoCRM's *virtual* duration type — not stored, computed as
  `dateEnd − dateStart` (presets 5 min–3 hours, default 1 hour) — so the app
  writes `dateEnd` and displays the difference:
  - **Editor (session detail form):** a **Duration** select on the
    Status/Type/Start line, with the preset choices read live from CRM
    metadata (a stored non-preset value is offered as-is so it is never
    lost; new sessions default to 1 hour). On save the frontend recomputes
    and sends `dateEnd` whenever the start or the duration changed — moving
    the start keeps the duration; the virtual `duration` key never reaches
    the CRM (`SESSION_EDIT_NAMES` now excludes it and whitelists `dateEnd`).
  - **Engagement/record view:** the Sessions tab table gains a **Duration**
    column.
  - **Session summary cards** (Overview note feed): the duration is stamped
    next to the session date in the header band.
  - **Read-only session view:** a **Duration** entry in the key-value grid.
  Sessions without a `dateEnd` (recorded before this change) simply show no
  duration. Verified in the stubbed-API browser harness (cards/table/view
  render; update sends only `dateEnd`; create sends start + 1h; moving the
  start preserves the duration) — not yet driven against the live CRM.

## [0.34.0] — 2026-07-10

### Fixed
- **The portal now reviews ALL of a user's current teams — two causes fixed.**
  Reported as "when I log in, it only shows mentor admin, even though I am also
  on other teams."
  1. **Stale cached membership.** Teams/roles were captured into the signed
     session cookie at LOGIN time and never re-checked, so a team granted in
     the CRM after sign-in stayed invisible until a full sign-out/sign-in —
     and revisiting the portal "logs you in" silently from the cookie, so it
     looked like a fresh login was ignoring teams. `GET /api/portal/session`
     now **re-reads the user's teams, roles, and admin flag from the CRM**
     (as the user, via their token — `assignments.auth.refresh_membership`)
     on every session restore and re-saves the session, so the portal links
     AND the staff apps' per-request gates always see current membership.
     Best-effort on CRM blips (keeps cached values); an expired token now
     signs the user out (401) instead of serving stale entitlements.
     Verified live against crm-test (login → session restore → CRM re-read).
  2. **`ASSIGN_ALLOWED_TEAMS` defaulted to empty**, unlike every other gate —
     a deploy (or local run) that didn't set it hid Client Administration from
     every non-admin regardless of their teams. It now defaults to
     `Client Administration Team`, matching the real team name in both CRMs
     (an env override still wins).

## [0.33.3] — 2026-07-10

### Fixed
- **Website links open the actual site in a new tab.** The contact/company
  pop-up (peek) rendered a stored bare-domain website (`agapew8loss.com`) as a
  relative href, so clicking it tried to open
  `/mentorsessions/agapew8loss.com` on the app itself. All external-link
  renders in the sessions frontend now share one `externalHref()` helper
  (prepends `https://` when the stored value has no scheme; trims whitespace):
  the peek Website/LinkedIn fields, the Company card's directory link, the
  session view's video-meeting link, and the Next-session Start button. All
  open with `target="_blank"` + `noopener`.

## [0.33.2] — 2026-07-10

### Changed
- **Phone numbers display in the standard US format `(216)-555-1234`
  everywhere in the product.** One shared formatter serves every frontend
  (`frontend/shared/phone-format.js`, loaded by the sessions / Mentor
  Administration / Client Administration apps) with a Python twin
  (`core.phone.format_us`) for server-composed text. Applied to: the sessions
  Details tab (Client Contacts + CBM Contacts tables, the Company card's
  directory block), the contact/company pop-up peek (now a `tel:` link showing
  the formatted number), the peek's copy-to-clipboard contact card,
  `/mentoradmin`'s detail summary (its local formatter — previously
  `(216) 555-1234` — now delegates to the shared one), and `/assignments`'
  engagement contact panel. Display-only: the CRM keeps storing E.164, edit
  inputs and `tel:` hrefs keep the raw value, and anything that isn't a
  10-digit US number (international, extensions) renders as-is rather than
  being mangled.

## [0.33.1] — 2026-07-10

### Added
- **Sessions apps: distinct empty state when the login has no linked profile.**
  When `/records` returns `profileFound: false` (no `CMentorProfile` has the
  signed-in user as its Assigned User, so nothing can be scoped to them), the
  grid now explains that and says an administrator must link the user — instead
  of the domain's generic "No partners/sponsors/engagements found." The message
  ships in the `/session` config (`noProfileMessage`, `sessions/router.py`).
  Diagnosed live on crm-test: a hand-created "Partner Manager" profile managed
  3 partners but had no Assigned User, so `/partnersessions` looked empty with
  no hint why.

## [0.33.0] — 2026-07-10

### Changed
- **Details tab rebuilt to the approved mockup v4 layout**
  (`prds/Details Screen files2/`): top to bottom, single column —
  1. **Engagement summary strip** (replaces the Engagement panel): a slim labeled
     bar under the tab row — Status as a navy pill, then Started / Mentor / Cadence /
     Sessions and every other engagement field that carries information (long-form
     text stays on the Overview and in the edit form; empties and "No" omitted),
     with the strip's own **Edit** flipping it into the full engagement form.
  2. **Company** and **Client Business Profile** cards: a **two-column labeled row
     grid** (fixed small uppercase labels, composed bold values with light `|`
     separators) — Company leads with a directory block (name, billing address,
     phone · website) then Business / Shipping-when-different rows, with Account /
     Cadence / Announcements (red "Not allowed" badge) on the right; the profile
     composes Entity / Revenue / Sells / On-file rows with Certifications + Funding
     chips and the quoted Client goal. Any informative field the curated rows don't
     cover still renders as a generic labeled row (columns kept balanced); empty /
     false fields are hidden except operationally meaningful negatives.
  3. **Client Contacts** card: ALL related contacts in one true table — Name
     (muted salutation + navy bold), Role chips (contact type + title), Phone,
     Email, City, Contact via, and the three acceptance flags collapsed to **one
     Agreements badge** (green "Complete" / red "N pending"); empty cells stay
     empty. Per-row **Edit** expands the full contact form inline under the row.
  4. **CBM Contacts** card: the same table (no City/Agreements) for the CBM-side
     people, populated from the real CRM relations — the assigned mentor
     (`CEngagement.mentorProfile`) + co-mentors (`additionalMentors`), each
     resolved through the profile's linked Contact (`contactRecord`) for
     phone/email; verified live against crm-test, there is no other staff link on
     the engagement.
- No page-global Edit/Save/Cancel bar remains; every section (strip, card,
  contact row) edits independently with inline errors on failure.

### Added
- **+ Add contact flows** on both contact cards. Client side: a two-option menu —
  **Select existing contact…** (live search over CRM contacts as the signed-in
  user; picking one relates it via the domain's contacts link
  (`engagementContacts` / `contacts` / `sponsorContacts`) and backfills the
  contact's company affiliation (`Contact.account`) only when it has none) and
  **Create new contact…** (the full contact form; create + link is one compound
  operation, with the company stamped at create). CBM side: select an existing
  mentor profile (attached via `additionalMentors` — new CBM people are onboarded
  through Mentor Administration, so no create-new there). New endpoints:
  `GET /{slug}/api/contacts?q=` (picker search) and
  `POST /{slug}/api/records/{id}/contacts` (`contactId` to link, `changes` to
  create-and-link), both running as the user.
- **Grid columns rework (mentor list)** — carried in from the prior session
  (previously uncommitted): Next Session (friendly datetime) + Start Date columns
  inline, Company/Client moved right; `Column.type` drives date/datetime cells.
- **Communications tab email-inbox UI scaffold** — carried in from the prior
  session (previously uncommitted): an inbox grid + view/reply/compose modal,
  **frontend-only** (no CRM email data yet; the wiring contract is documented in
  CLAUDE.md); Overview CBM contacts now link to each co-mentor's Contact pop-up
  (`coMentors[].contactId`).

## [0.32.12] — 2026-07-10

### Changed
- **Details tab redesigned: per-panel editing + summary view (no field grids).**
  The single page-global Edit / Save / Cancel bar is gone; each panel — **Engagement**
  (new, shown first), **Company**, **Client Business Profile**, and each **Contact** —
  now carries its own **Edit** button that flips only that panel into a field-level
  form with its own **Save changes** / **Cancel** (saves write through per entity;
  on a 403/error the edit view stays open and the reason shows inline).
- **View mode composes fields into readable, directory-style blocks** instead of
  label/value grids: a **Contact** reads like a directory entry (salutation + name,
  preferred name in parens, address, phone, `mailto:` email; a secondary line for
  contact type / preferred method / notification, and the privacy/terms/code-of-conduct
  flags surfaced **only when not accepted**); **Company** reads letterhead-style
  (billing address block + phone + website, then a prose line composing
  organization type / stage / industry, account facts, and a shipping line only when
  it differs from billing); **Client Business Profile** as grouped structure/financial
  summary lines, the client's description quoted, with certifications and funding as
  badge rows; **Engagement** as a status-pill header + key dates / mentor / cadence /
  session count. Empty and false fields are hidden in view mode (except the three
  acceptance flags). Edit mode keeps the full field-level form.
- A new **Engagement** panel (mentor domain) / profile-first ordering (partner/sponsor)
  leads the Details tab; the engagement's mentor / assigned users / program are read
  as display-only extras alongside the editable scalar fields.

## [0.32.11] — 2026-07-10

### Added
- **Unsaved-changes guard on the session editor.** Clicking **Back** with unsaved
  edits (any field or the attendee set changed) now opens a dialog — **Save changes**
  (persists, then returns), **Discard** (drops them, returns), or **Keep editing** —
  so you don't have to go back and press Save separately. No prompt when nothing
  changed.

## [0.32.10] — 2026-07-10

### Changed
- **Session detail View redesigned to Display Standard §12.** The page title +
  metadata strip become a **summary header card** — tinted band (per-status, reusing
  the summary card's band/chip tokens) with the humanized date, status & type chips,
  and the engagement line, over an auto-fit **key-value grid** (meeting type,
  location, video link, next session, attendees). **Session Notes** render as a
  full-width reading block (no clamp); **Action items / next steps** as the gold
  callout. Per-status variants per §12.4 (No Show → "Expected attendees", omitted
  action-items/transcript boxes rather than empty ones). The Back / ‹ N of M › /
  Edit navigation row is unchanged. Auto-generated session titles never appear.
- **Transcript zone omitted (§12.5):** `CSession` has no transcript long-text field
  yet (documented as unbuilt `sessionTranscription`), so the transcript section is
  not rendered — no stub — until the CRM field lands.

## [0.32.9] — 2026-07-09

### Changed
- **Next session** panel date now matches the session-summary format —
  "Mon, July 14 — 4:00 PM" (abbreviated weekday), with the year rule and an ISO
  hover tooltip.

## [0.32.7] — 2026-07-09

### Changed
- **Overview "Session notes" — Session Summary Display Standard (v0.2).** Each
  session renders as a two-zone card: a tinted **header band** (pale blue for a
  Scheduled *future* session, neutral gray for past/Completed/Cancelled/No Show)
  carrying the date, type & status chips, and View/Edit; and a body with an
  **attendees** column beside the notes (clamped to 4 lines) with the gold
  **Next steps** callout. Status chips: Scheduled (blue) / Completed (green) /
  Cancelled (gray) / No Show (red) — state is never color-only. Dates read
  "Weekday, Month D — h:mm AM/PM" (year omitted in the current year; ISO in the
  hover tooltip). The feed groups **Upcoming** (soonest first) then **Past** (most
  recent first), with labels when a group has 3+. A Scheduled session shows
  "Scheduled — notes are recorded when the session is held." instead of "no notes."
- New sessions default to status **Scheduled** (the CRM's Scheduled/Completed/
  Cancelled/No Show vocabulary).

## [0.32.6] — 2026-07-09

### Changed
- **Mentor grid shows all engagement statuses** (was restricted to active/pending)
  so the Status filter can offer every status; the user narrows as they like.
- **Compact header:** "Signed in as …" + Sign out moved to the upper-right corner;
  Refresh moved into the filter row — reclaiming a full toolbar row of height.

## [0.32.5] — 2026-07-09

### Added
- **Records grid: filter, sort, and richer columns.** A **Status** filter (the
  statuses present in the grid); **click any column header to sort** (toggles
  asc/desc, arrow indicator); alternating row shading for readability. The
  **Created** column is now **Start Date** (the engagement/partnership start date).
- **Primary contact is a link** — clicking it opens the contact pop-up with the
  email as a `mailto:` link (opens the user's mail client) and a combined address.
- **Copy contact details.** The contact pop-up has a **⧉ Copy** button (top-right)
  that copies a paste-ready block — name, full address, email, phone — to the
  clipboard. `service.peek` returns a `copyText` card + a combined Address field
  for contacts; `get_session`/grid rows carry the needed ids.

## [0.32.4] — 2026-07-09

### Added
- **Read-only Session view.** Clicking a session's name (in the Overview note feed
  or the Sessions tab) or its **View** button opens a view-optimized page showing
  the whole session at a glance — a compact facts grid (status, type, start,
  meeting type, location, video link, next session, topics, **attendees**) plus the
  prominent Session notes / Action items blocks. **‹ / ›** buttons (and ← / →
  keys) walk to the previous / next session so a user can quickly page through the
  record's sessions; **Edit** jumps to the editor. `get_session` now returns
  `attendeeNames` for display.

## [0.32.3] — 2026-07-09

### Changed
- **Session editor layout.** The two most important fields — **Session notes** and
  **Action items / next steps** — are now large, prominent editors side by side
  (stacked on narrow screens). Removed the meeting **End** date; **Status /
  Session type / Start** now share one line. Tighter, more efficient use of space.

## [0.32.2] — 2026-07-09

### Fixed
- **Details tab respects the user's edit permission** — reads the ACL and, for an
  `edit: own` role, checks per-record ownership; sections you can't edit are
  read-only (no doomed edit → 403). Save is per-entity with a plain-language
  permission message.
- **Attendees now read and write correctly.** `sessionAttendees` is a CRM
  *relationship*, not a select-field: reads go through the link (`list_related`,
  like co-mentors) — reading `sessionAttendeesIds` off the record always returned
  empty, which is why attendees never displayed and edits looked lost. Writes sync
  via the relationship endpoints (relate added / unrelate removed). Both the
  session editor and the Overview note feed use the link read.
- **Friendlier empty grid** — "No client engagements / partners / sponsors found"
  instead of the "ask an administrator to link your profile" error.

### Changed
- **Next session** panel: dropped the session name/type line; added a button that
  opens the upcoming session for editing — **Start Session** (also launches the
  call) when it has a video link, else **Open Session**.

## [0.32.0] — 2026-07-09

### Changed
- **Session Management — redesigned record detail into a tabbed, information-
  dense view.** Opening an engagement / partner / sponsor now shows a tab bar
  common to all three domains: **Overview · Details · Sessions · Communications ·
  Documents** (`/session` → `detailTabs`). Phase-one delivery builds **Overview**,
  **Details**, and **Sessions**; **Communications** (email/SMS threads) and
  **Documents** (uploads) ship as placeholders.
- **Details tab** — a **read-optimized** view of the org records behind a record
  (the company Account, the client/partnership/sponsor profile, and each related
  contact), with an **Edit** button that flips the whole page into a field editor
  (Save / Cancel). Fields are read **live from CRM metadata** (filtered to the
  editable scalar fields, humanized labels) so it tracks the schema; the read view
  hides empties for scannability, the edit view exposes every editable field.
  Enum/multiEnum drift is dropped on save (per the non-required-enum policy);
  each changed entity is saved with its own `PUT` as the logged-in user (ACL
  enforced). New endpoints `GET/PUT /{slug}/api/details/…` (`sessions/details.py`).
- **Overview tab** — a full-width, review-oriented screen:
  - **Facts rail** (left, resizable via a drag splitter): key identity (status
    badge, a single aggregated **Company** link, primary contact, meeting
    cadence, referring partner), session activity (start/last/next counts, focus
    areas), **Other contacts** + **CBM Contacts**, and the mentoring need.
  - The **Company** link aggregates the company Account **and** its profile
    (client business / partnership / sponsor) into one pop-up; contact/referring-
    partner links open their own pop-up (read-only `/{slug}/api/peek`, entity
    allowlisted, ACL-enforced).
  - **Overall notes** (Engagement / Partner / Sponsor Notes) above an aggregated
    **session-notes feed** — every session's notes + next steps, most-recent
    first, each stamped with date/time and its **attendees**.
  - A bold **Next session** callout (soonest upcoming session, derived from the
    records).
- Detail tabs are built from config; the standalone Contacts tab folds into
  Overview (Other/CBM Contacts) and the forthcoming Details tab.

## [0.31.0] — 2026-07-09

### Added
- **Session Management tools** — three staff-only, team-gated routes
  (`/mentorsessions`, `/partnersessions`, `/sponsorsessions`) from one
  configurable engine. Each manager (mentor / partner manager / sponsor manager)
  reviews the records they own (engagements / managed partners / managed
  sponsors), opens one to a read-only detail (parent + related contacts +
  existing sessions), and creates/edits **`CSession`** meetings (notes, next
  steps, attendees, status). Mentors can also attach co-mentors. It's one
  `CSession` entity with the parent link swapped, driven by a per-domain
  `DomainConfig`; reuses the portal SSO, per-request team gate, per-user
  EspoClient, and the type-driven field editor. New settings:
  `SESSION_{MENTOR,PARTNER,SPONSOR}_ALLOWED_TEAMS`. Phase 1 (CRUD); Google
  Calendar/Meet + transcription are later phases. On branch, not yet deployed.

### Fixed
- **Sessions are stamped with their creator** (`assignedUser`/`assignedUsers`)
  on create, so a role whose `CSession` scope is read-own can see the session it
  just made.
- **Enum drift can't 400 a session save.** The editor sends only changed fields
  (diffed against a render-time snapshot), and the service drops enum/multiEnum
  values not in the live CRM options before create/update (fails open) — so a
  stored value that has drifted out of its field's options no longer fails the
  whole save.
- **Required fields are enforced in the editor**, read live from CRM metadata
  (e.g. `CSession.dateStart`): required fields show a `*` and Save is blocked
  with a readable message instead of surfacing a raw CRM `validationFailure`.
- **Session name is pre-filled and the user's value wins.** The New Session
  editor pre-fills a default title (`YYYY-MM-DD - <parent name>`) so the user
  sees what will be stored; create now sends the name verbatim. Pairs with the
  CRM name formula being set to keep any value already present (else it would
  overwrite the app's name).

### Changed
- App log lines are timestamped — `LEVEL: YYYY-MM-DD HH:MM - message` — so run
  logs show when each event (session create, CRM error) happened.

### Notes
- Mentor domain driven live end-to-end on crm-test. CRM prerequisites to run
  the tool (per CLAUDE.md): create the Partner/Sponsor Management Teams, grant
  the gate roles CSession create + read-own/edit-own, enable `assignedUsers`
  (collaborators) on `CSession` (so read-own credits the creator — otherwise
  create 403s and sessions are invisible), and make the `CSession` name formula
  keep-if-present.

## [0.30.1] — 2026-07-07

### Changed
- Portal home page: section labels (Applications / CRM / Public intake forms)
  are larger (1.45rem serif with an underline rule) and the links beneath them
  render in the standard link blue — headings and links are now clearly
  distinct.

## [0.30.0] — 2026-07-07

### Added
- **Authenticated portal at `/` with single sign-on for all apps.** The root
  page (on deployments with the staff stack, i.e. `SESSION_SECRET` set) is now
  a CRM login; after signing in, the user sees exactly the links their EspoCRM
  **teams** entitle them to: every signed-in user gets the five public
  intake-form links; **Mentor Team** adds a link to the CRM itself; **Client
  Administration Team** → `/assignments/`; **Mentor Administration Team** →
  `/mentoradmin/`; **Marketing Admin Team** → `/ops/` (**Submission Admin** —
  retitled from "Submission Operations"). CRM admins see everything. New
  `portal/` package (`/api/portal/login|session|logout` + the page); the login
  is **ungated** (any active internal user) — the portal listing is a
  convenience, never the security boundary.

### Changed
- **One login, no second prompts.** All staff apps now share one session
  (sign in once at the portal) and enforce their team gates **per request**
  instead of at login: 401 sends the browser to `/?next=<app>` (and back after
  login); 403 shows exactly which team is required. The per-app login
  screens/endpoints are gone; per-user CRM access (ACL, audit) is unchanged —
  every call still runs under the signed-in user's own token.
- `/ops` is now gated by its own `OPS_ALLOWED_TEAMS` (default **"Marketing
  Admin Team"** — the team must be created in the CRM) instead of sharing the
  assignments gate.
- The public form index at `/` remains only on deployments without the staff
  stack (the dry-run dev app); the forms themselves stay public everywhere by
  direct URL.

## [0.29.0] — 2026-07-07

### Added
- The `/mentoradmin` detail editor gains a **Contact tab** to view and edit the
  mentor's contact information — first/last name, email, phone, and street /
  city / state / ZIP. These fields live on the mentor's linked **Contact**
  record (the profile only mirrors them read-only in the summary card), so the
  save routes them to the Contact while profile fields keep writing to
  `CMentorProfile`. Phone is normalized to E.164 at the CRM boundary (EspoCRM
  rejects other formats). Saving contact fields on a mentor with **no linked
  Contact** fails fast — before anything is written — with a clear message
  (400), instead of half-saving.

## [0.28.0] — 2026-07-07

### Added
- The `/assignments` engagement **status filter now has an "All" option** at the
  top of the dropdown — one click selects (or clears) every status. It shows a
  checked/indeterminate state as individual statuses are toggled, and the
  summary reads "Status: All" when everything is selected.

## [0.27.4] — 2026-07-07

### Fixed
- The `/mentoradmin` **mentor detail summary card now shows the same five
  client counts as the roster grid** (Active clients · Max clients · Available ·
  Assigned (30d) · Lifetime clients), computed from CEngagement via the shared
  `client_counts_for` helper — attached to the detail response as
  `clientCounts` (a save refreshes it, since the save returns through the same
  read). Previously the card showed the CRM's computed
  `currentActiveClients`/`availableCapacity` (known-buggy formula) and omitted
  any null value, so counts were wrong, incomplete, or vanished entirely. The
  five counts are always rendered ("—" when unknown); the CRM-computed fields
  are no longer read.

## [0.27.3] — 2026-07-07

### Fixed
- The mentor-type filter in both staff mentor grids now offers **every**
  `mentorType` enum value (Mentor, Co-Mentor Only, Subject Matter Expert,
  Presenter, Volunteer, Other) — previously it listed only the types present in
  the loaded roster, so types with no current mentor couldn't be selected. The
  roster response carries the live CRM enum (`mentorTypeOptions`, best-effort);
  the frontend unions it with any stored value the enum no longer declares.

## [0.27.2] — 2026-07-06

### Changed
- Client-count column order in both staff mentor grids is now **Active Clients ·
  Max Clients · Available · Assigned (30d) · Lifetime** (Available moved before
  Assigned (30d)).

## [0.27.1] — 2026-07-06

### Changed
- Numeric columns in both staff mentor grids (the five client-count columns)
  are now **centered** under their headings (were right-aligned).

## [0.27.0] — 2026-07-06

### Added (both staff mentor grids)
- **Mentor client-count analytics** in the `/mentoradmin` roster and the
  `/assignments` "Review Mentors" grid — five columns, all sortable:
  **Active Clients** (engagements with status Active / Assigned / Pending
  Acceptance), **Max Clients** (the stored `maximumClientCapacity`),
  **Assigned (30d)** (active-set engagements whose `engagementAssignedDate` is
  within the last 30 days), **Available** (Max − Active, app-computed), and
  **Lifetime** (every engagement ever linked to the mentor, any status).
  Counts are computed by the app from `CEngagement` in one paginated sweep
  (grouped by `mentorProfile`) — the CRM's own computed
  `currentActiveClients`/`availableCapacity` fields are no longer read (the
  crm-test formula computes 1 for every mentor). The "Has capacity" filter and
  the assign dropdown's "(capacity N)" label use the same computed Available,
  so the grid and eligibility can't disagree.
- The **Assign action now stamps `CEngagement.engagementAssignedDate`** (UTC
  now) alongside mentor + Pending Acceptance — nothing CRM-side fills it, and
  the Assigned-(30d) count depends on it. Engagements assigned before 0.27.0
  have no date and won't count until backfilled CRM-side.

### Changed
- `GET /assignments/api/mentors` and `GET /mentoradmin/api/mentors` responses
  gained `metricsAvailable`. If the logged-in staffer's EspoCRM role can't read
  `CEngagement`, the roster still loads with blank count columns and the count
  line says so (grant CEngagement read to the staff Teams' role to fix).

## [0.26.0] — 2026-07-06

### Added (Mentor Administration `/mentoradmin`)
- **"Update Mentor Status"** — a roster-toolbar action that sweeps every mentor
  and reports, per mentor: does the linked EspoCRM **login User actually exist**
  (a dangling link to a deleted User, a deactivated User, and "no User linked"
  are all distinguished) and does the **@cbmentors.org mailbox exist** in Google
  Workspace. The sweep also recomputes completeness and **re-syncs the stored
  Record status** for every mentor (same write rules as the detail view — only
  on change, never over a manual Duplicate), so the whole grid self-heals in one
  click. Results shown in a wide modal table; the roster reloads after.
  Endpoint: `POST /mentoradmin/api/mentors/status-check` (staff session
  required). User reads run as the provisioning admin service account when
  configured (regular staff can't read Users — reported "could not verify"
  instead of failing). The mailbox column reports **"n/a — check not
  configured"** until the Google Directory integration is connected in Email
  Setup; nothing fails when it's absent.

## [0.25.2] — 2026-07-06

### Fixed
- **Partner form failed for anyone choosing partnership type "other".** The CRM's
  `partnershipType` enum gained a (lowercase) `"other"` value; the options sync
  correctly put it in the form dropdown, but the Pydantic schema still hard-coded
  the original six values as a `Literal`, so picking it 422'd the whole submission
  — shown to the user as the generic "Please check your entries and try again."
  All schema fields whose dropdowns are CRM-synced are now free strings
  (partner `partnership_type`; client-intake `business_stage`/
  `meeting_preference`/`notification_preference`; volunteer `contact_preference`/
  `currently_employed`) — the orchestrators already sanitize each against the
  live CRM enum, which is the single source of truth. A future CRM enum change
  can no longer break a form.
- **Follow-up (same day):** the CRM entry was corrected to Title-case **`Other`**
  on both CRMs; the partner dropdown was re-synced (`sync_form_options.py --write`).
  Prod parity checked read-only: all 16 managed lists match prod except a harmless
  ordering difference in volunteer how-did-you-hear (same values). Volunteer
  `phone_type` (static list, no CRM target) was loosened to a free string too —
  policy: **a non-required field must never block a submission over an
  unrecognized enumerated value.**
- **Error messages now state the exact reason — never generic.** Validation
  failures return a human-readable `detail` string naming each failing field and
  why (structured list preserved under `errors`), and are logged at WARNING so
  they're visible in the run logs. The shared wizard and the client-intake form
  display the server's reason verbatim; the only remaining fallback (a bodyless
  response) names the HTTP status.

## [0.25.1] — 2026-07-06

### Changed
- **Landing page shows each entry's shortcut path.** Every form and staff-tool
  link on `GET /` now displays its normalized alias (e.g. `/clientintake`,
  `/mentoradmin`) in a small code chip, so nobody has to remember where the
  dashes or capitals go.

## [0.25.0] — 2026-07-06

### Added
- **Friendly URL aliases.** A single-segment path is normalized (lowercase,
  alphanumerics only) and redirected (307) to the matching form or staff tool —
  so `/clientintake`, `/ClientIntake`, `/client_intake` all land directly on
  `/client-intake/` without showing the index. Works for all five forms and
  (when the staff tools are mounted) `/assignments`, `/ops`, `/mentoradmin`.
  Unknown paths still 404. Built for the upcoming
  `apps.clevelandbusinessmentors.org` custom domain, but live on every deploy.

## [0.24.1] — 2026-07-06

### Fixed
- **Volunteer consent now sets `CMentorProfile.ethicsAgreementAccepted`.** The
  mentor-intake consent checkbox set `termsAccepted` + `mentorCodeAccepted` (and the
  three Contact bools) but NOT the ethics flag `/mentoradmin`'s completeness rule
  requires — so every form-submitted mentor started with an "ethics agreement"
  completeness gap staff had to tick manually. Verified live on crm-test (left
  `ZZTEST-ETHICS LiveCheck` Contact `6a4b2bc43a7dd4681` + CMentorProfile
  `6a4b2bc4c3c1f0d55` to clean up in the UI).

### Changed
- **Mentor code-of-conduct link.** On the volunteer (mentor intake) form, the
  consent checkbox's "Code of Conduct" now links to the mentor code of ethics —
  `https://clevelandbusinessmentors.org/mentor-code-of-ethics/`. The other forms'
  Code of Conduct keeps pointing at the client code (`frontend/shared/legal-links.js`).
- **Mentor Administration: "Mentoring skills" editor removed** from the Bio tab
  (dropped from `EDITABLE_FIELDS`, so it also leaves the server-side update
  whitelist; the CRM field itself is untouched).

## [0.24.0] — 2026-07-05

### Changed (Client Administration `/assignments` — Available Mentors)
- **Focus Areas column removed** from the mentor grid (the engagement's focus areas
  are still shown in the engagement detail popup — that's a client-request field,
  not a mentor attribute).
- **Industry column now shows `CMentorProfile.industryExperience`** (the multi-value
  field the volunteer form writes) instead of the legacy single `industrySector`;
  rendered as chips, header "Industry Experience", sortable.
- **Filters reworked:** the "All industries" (industrySector) and "All focus areas"
  filters are replaced by **Industry Experience** and **Areas of Expertise** filters
  (each matches any of the mentor's values). Search now covers name, type, industry
  experience, and expertise.
- **Capacity column shows the stored value.** It now displays
  `maximumClientCapacity` exactly as on the CRM record (blank = "—"), instead of the
  CRM-computed `availableCapacity` (which showed "Unlimited" for −1 and drifted from
  what staff saw on the record). The "Has capacity" checkbox and the assign
  dropdown's "(capacity N)" label still use the computed available capacity, since
  those express eligibility to take a new client.
- **Available Mentors opens much wider** — the dialog defaults to ~96% of the window
  (the engagement detail popup keeps its previous sizing; both remain drag-resizable).

## [0.23.1] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin` — completeness)
- **`publicProfile` no longer affects completeness.** Removed the publicProfile-gated
  checks (About-the-mentor text + area of expertise) from the completeness rule
  (server + frontend pre-save modal + docs). The Public-profile checkbox stays an
  editable field on the Status tab; it just no longer drives Complete/Incomplete.
- **Background check is optional.** Removed `backgroundCheckCompleted` from the
  required sign-off flags, so a mentor is no longer flagged Incomplete for a missing
  background check. The field (and its date) remain editable on the Compliance tab.
- Completeness now requires: a linked Contact + ethics/training/terms; plus, if
  Active, a CBM email and matching User on the member and its Contact.

## [0.23.0] — 2026-07-02

### Changed (Client Administration `/assignments`)
- **Engagements that already have a mentor no longer show the picker.** The grid's
  "Assign to mentor" column now shows the **assigned mentor's name** for any
  engagement that already has one (`CEngagement.mentorProfile`), instead of the
  Select-a-Mentor dropdown + Assign button. The picker/button appear **only** when
  no mentor is assigned. So filtering to Active (or any status whose engagements are
  already assigned) shows the mentor, not a redundant assign control. `list_engagements`
  now returns `mentorId`/`mentorName`; after an assign the grid reloads and the row
  flips to showing the name.

## [0.22.3] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Mentor Email in the roster is now a `mailto:` link** — clicking it opens the
  staffer's email client addressed to the mentor's CBM email. Blank emails still
  render as "—".

## [0.22.2] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Removed Industry sector from the mentor admin app.** Dropped the Industry column
  and industry filter from the roster grid and the Industry-sector field from the
  Expertise detail tab. (`industrySector` is unchanged in the Client Administration
  tool, which still uses it.)
- **Roster grid gained Mentor Email + Type.** New columns: **Mentor Email** (the CBM
  `@cbmentors.org` login address, `cbmEmail`) and **Type** (`mentorType`), with a
  matching mentor-type filter replacing the old industry filter. Column order is now
  Mentor · Mentor Email · Record · Status · Type · Created · Assigned · Capacity.
- **Completeness: dropped the industry-sector requirement.** A public-profile mentor
  no longer needs an Industry sector to count as Complete (still requires About text +
  ≥1 area of expertise), consistent with removing the field. Server, frontend mirror,
  and docs updated.

## [0.22.1] — 2026-07-02

### Fixed (Mentor Administration `/mentoradmin`)
- **Roster "Record" column no longer goes stale vs. the detail badge.** The grid
  reads the stored `recordStatus`, which was only written on Save; a record made
  complete outside a save-through-this-tool (e.g. the v0.11.2 login-link fix) stayed
  Incomplete in the grid while the detail page computed Complete (reported for prod's
  Douglas Bower). The detail GET now **persists the recomputed status on view** when
  it changed (`sync_record_status`, still a no-op when unchanged and still preserving a
  manual `Duplicate`), so the stored value self-heals; the frontend reloads the roster
  on return when the status changed.

## [0.22.0] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Expertise tab now edits `industryExperience` instead of `mentoringFocusAreas`.**
  The mentoring-focus-areas multi-select was replaced by an Industry experience
  multi-select (the field the mentor intake form now writes). Auto-propagates to the
  detail-select, update whitelist, and live enum-options.
- **Status tab gained a mentor-pause window.** `mentorPauseStartDate` +
  `mentorPauseEndDate` (date) render on their own line directly beneath the
  Status/Type selectors (which now share a row).
- **"Back to list" warns on unsaved edits.** Leaving the detail view with changed,
  unsaved fields now pops a styled "Discard unsaved changes?" modal listing the
  changed fields ("Keep editing" / "Discard changes"). A clean save re-baselines the
  snapshots, so no false warning after saving.
- **Completeness rule: dropped the mentoring-focus-area requirement.** A public-profile
  mentor no longer needs ≥1 mentoring focus area to count as Complete (still requires
  About text + ≥1 area of expertise + an industry sector) — keeps the rule satisfiable
  now that focus areas aren't editable here. Updated server, frontend mirror, and docs.

## [0.21.3] — 2026-07-01

### Fixed
- **Volunteer/mentor form now records "How did you hear" on the Contact too.** It
  was written only to `CMentorProfile.howDidYouHearAboutCBM`, so the person's
  Contact ("client") record showed a blank "How did you hear" while the other three
  forms populate `Contact.cHowDidYouHear`. The volunteer orchestrator now also writes
  `Contact.cHowDidYouHear` (sanitized against the Contact enum, added to the null-fill
  keys) alongside the existing profile field. Not enum drift — the form's dropdown
  values match both fields verbatim on crm-test and prod. Existing records are not
  backfilled; a repeat submission from the same email null-fills the blank Contact field.

## [0.21.2] — 2026-07-01

### Changed
- **Three mentor-form fields are now required on the form:** "How should we contact
  you?", "Are you currently employed?", and "How did you hear about Cleveland Business
  Mentoring?" — each `<select>` got the `required` attribute + a required-asterisk
  label, so the wizard's `checkValidity()` blocks the step until they're chosen
  (required in the form regardless of the CRM's own optionality). Frontend-level
  enforcement; the schema still accepts them as optional for a direct API call.

## [0.21.1] — 2026-06-30

### Fixed (code-review cleanups — no behavior change)
- **Corrected the stale field-coverage docstring** in `client_intake/orchestrator.py`
  (it claimed marketing-consent / how-heard / year-formed / # employees / meeting +
  notification preference / terms were "NOT DEPLOYED / omitted" — they're all written
  now; only industry-subsector + applicant-since remain deferred).
- **Aligned the volunteer how-did-you-hear dropdown to its write target.** It was
  synced to `Contact.cHowDidYouHear` but written to
  `CMentorProfile.howDidYouHearAboutCBM` — identical options today, but two separate
  enums that could drift and silently drop the value. The form now syncs to the field
  it actually writes.
- Fixed a stale `# varchar` comment on `P_HOW_HEARD` (it's an enum, sanitized).

## [0.21.0] — 2026-06-30

### Changed (field-mapping — mentor areas of expertise)
- **Volunteer "Areas of Expertise" now maps to the skills field.** It previously
  wrote 42 *industry* values to `CMentorProfile.mentoringFocusAreas` — redundant with
  the "Industry Experience" question (which maps to `industryExperience`). It now
  writes to the purpose-named **`CMentorProfile.areaOfExpertise`** (31 *skill* values:
  Business Strategy, Digital Marketing, Leadership, Sales, Strategic Planning, …),
  giving a clean split: Industry Experience = industries, Areas of Expertise = skills.
  The form dropdown is re-synced to that field; `areaOfExpertise` is identical on both
  CRMs (31 values). `mentoringFocusAreas` is no longer set by the volunteer form (it
  remains the client-engagement field on CEngagement). Live-verified on crm-test.
  (Revises the earlier Pass B decision to keep it on `mentoringFocusAreas`.)

## [0.20.0] — 2026-06-30

### Changed (form keyboard UX)
- **Cursor starts in the first field, and Tab moves field-to-field.** Every form now
  focuses the first data-entry control of the active step on load (and when moving
  between steps). The consent policy links (Code of Conduct / Terms / Privacy) are
  pulled out of the tab order (`tabindex=-1`, still mouse-clickable) so tabbing flows
  between data fields. Labels were never tabbable; the nav buttons (Back/Next/Submit)
  stay tabbable so keyboard users can still reach them. Implemented in the shared
  `wizard.js` (covers volunteer/info-request/partner/sponsor) and in
  `client_intake/app.js` (it has its own wizard), plus `legal-links.js`. Verified
  in-browser across all five forms.

## [0.19.0] — 2026-06-30

### Changed
- **Environment indicator moved from the corner badge into the footer.** Instead of
  the colored top-right tag, the deploy environment now appears as the server name
  right after the version, e.g. `v0.19.0 (Production)` / `(Test)` / `(Dev)`. Applies
  to both the forms (shared `footer.js`) and the server-rendered landing page; the
  `.cbm-env-badge` styles and the index badge HTML were removed.

## [0.18.0] — 2026-06-30

### Added (field-mapping — meeting preference; mapping effort COMPLETE)
- **Client-intake "Meeting preference" now stores** to `Contact.cMeetingPreference`
  (`Video`/`Phone`/`Email`/`In Person`/`No Preference`) — the field was reconciled to
  an identical, typo-free option set on both CRMs, the form dropdown is CRM-backed and
  re-synced, and the orchestrator writes it via the sanitizer with null-fill.
  Live-verified on crm-test (`In Person` stored; works on prod, same options).
- **This completes the field-mapping effort** (`field-mapping-completion-plan.md`):
  every input collected across all five forms now maps to its intended CRM field. No
  collected field is silently dropped anymore.

## [0.17.0] — 2026-06-30

### Added (field-mapping — notification preference)
- **Client-intake "Notification preference" now stores.** The CRM team added
  `Contact.cNotificationPreference` (enum: `Email`/`Text`) on both CRMs, so the form
  value now writes there (was collected but dropped). The form dropdown is CRM-backed
  and re-synced (`Text Message` → `Text` to match the enum). Live-verified on crm-test;
  works on prod (same field/options). **Meeting preference** (`cMeetingPreference`)
  also now exists but is **not yet mapped** — its CRM options need a cleanup first
  (a `No Preferrence` typo on both CRMs + an `In Person`/`In-Person` divergence
  between them); tracked in `crm-field-handoff.md`.

## [0.16.0] — 2026-06-30

### Added (field-mapping — consent on partner & sponsor)
- **Partner & sponsor forms now collect consent.** Both gained the same single
  required consent checkbox ("I have read and agree to the Code of Conduct, Terms of
  Use, and Privacy Policy", with the policies linkified via `shared/legal-links.js`)
  on their final step. On submit it sets the three Contact bools
  `cTermsOfUseAccepted` + `cPrivacyPolicyAccepted` + `cCodeOfConductAccepted` (like
  client-intake). Submission is gated on it (schema `model_validator`). This
  **completes the consent model across all four forms.** Live-verified on crm-test
  (both forms wrote all three bools) and the checkbox + policy links confirmed
  rendering in the browser. 209 tests green (2 new).

## [0.15.0] — 2026-06-30

### Added (field-mapping — consent capture)
- **The single consent checkbox now records all three acceptances in the CRM.** The
  forms' one checkbox ("I have read and agree to the Code of Conduct, Terms of Use,
  and Privacy Policy") now sets all three Contact bools — `cTermsOfUseAccepted`,
  `cPrivacyPolicyAccepted`, `cCodeOfConductAccepted` — on **client-intake** and
  **volunteer**, plus `CMentorProfile.mentorCodeAccepted` (the mentor-specific
  code-of-conduct) for volunteers. All four bools exist on both CRMs (crm-test +
  prod, verified), so this works on production immediately. Live-verified on crm-test.
  (Consent capture for **partner & sponsor** is pending — those forms need the
  checkbox added; tracked as the next step.)

## [0.14.0] — 2026-06-30

### Changed (field-mapping — mentor industry experience)
- **Mentor "Industry Experience" now captures ALL selections.** The multi-select
  (up to 6) previously stored only the **first** pick into the single-enum
  `CMentorProfile.industrySector`; it now writes every selection to the multiEnum
  **`CMentorProfile.industryExperience`**. The CRM team made that field a multiEnum
  with a canonical 28-value list on both CRMs (crm-test + prod, verified identical),
  so this works on production immediately. The volunteer form's industry dropdown is
  re-synced to that field (28 CBM industry values, replacing the 20 NAICS sectors).
  Live-verified on crm-test (a 3-industry submission stored all three). `industrySector`
  is no longer written for mentors.

## [0.13.0] — 2026-06-30

### Added (field-mapping completion — Pass A)
- **More collected fields now land on the CRM.** Previously-dropped inputs are
  written to the fields the business intends (see `field-mapping-completion-plan.md`):
  - **client-intake** → Contact `cHowDidYouHear` / `cMarketingOptIn` /
    `cTermsOfUseAccepted`; CClientProfile `numberOfEmployees` and `formationDate`
    (the form's year → `YYYY-01-01`).
  - **volunteer** → Contact `cPreferredContactMethod` (from "how should we contact
    you") and `cEmploymentStatus` (from "are you employed").
  - **partner** + **sponsor** → Contact `cHowDidYouHear`.
  The how-did-you-hear / contact-method / employment dropdowns are now **CRM-backed**
  (synced from the live Contact enums via `scripts/sync_form_options.py`) so a value
  outside the enum is dropped by the sanitizer rather than 400-ing the create.
- **Repeat submitters backfill empty fields without clobbering.** New
  `core/crm_upsert.find_create_or_fill`: a Contact matched by email is reused and
  only its **null/empty** fields are filled — a value the CRM already holds (or a
  staffer curated) is never overwritten. Replaces the old "matched → reuse as-is".
  Verified live against crm-test (a second submission backfilled a null phone while
  leaving the existing how-heard untouched).

All four orchestrators share one `EnumSanitizer` across the Contact + profile
steps. 207 tests green (8 new). Live-verified end-to-end on crm-test; ZZTEST-PASSA
records left for UI cleanup (ids in the commit/chat).

## [0.12.1] — 2026-06-29

### Added
- **Environment badge now also on the landing page.** The form index (`GET /`) is
  server-rendered without the shared `footer.js`, so the 0.12.0 badge appeared on
  the forms but not on the home page. The badge is now rendered server-side into
  the index HTML (`_env_badge_html`, self-contained inline styles matching
  `.cbm-env-badge`) using `settings.environment` — so the prod/test/dev home pages
  each show their badge too.

## [0.12.0] — 2026-06-29

### Added
- **Environment badge on every form.** Each form now shows a color-coded badge in
  the top-right corner indicating the deploy target — 🟢 `PRODUCTION`, 🟡 `TEST`,
  🔴 `DEV · DRY-RUN` — so testers and staff can tell at a glance whether a form
  writes to the production CRM, crm-test, or nothing (dry-run). The label is
  derived server-side from the CRM target (`core/config.Settings.environment`:
  dry-run ⇒ `dev`, a `crm-test` base URL ⇒ `test`, any other live CRM ⇒
  `production`), surfaced on `/healthz` as `environment`, and rendered by the
  shared `frontend/shared/footer.js` (one change covers all five forms; no
  per-form HTML edits, no build step). Auto-resolves correctly for all three App
  Platform apps with no overlay changes; set `ENV_LABEL` to override the wording.

## [0.11.2] — 2026-06-26

### Fixed
- **Mentor login now actually links on production (the "approved mentor isn't
  selectable" bug).** Prod's `CMentorProfile` has the single `assignedUser` field
  **disabled** and uses the multi-user `assignedUsers` (collaborators) field — like
  `CEngagement`/`CClientProfile`. The app wrote `assignedUserId`, which prod
  accepts with HTTP 200 but silently stores nothing, so provisioned mentors stayed
  userless: never "truly Active", never eligible for the assignment dropdown,
  always "Incomplete: no User assigned". The mentor's User link is now **written as
  both** `assignedUserId` + `assignedUsersIds` and **read from whichever holds it**
  (`assigned_user_id`/`assigned_user_name` helpers) across both staff tools —
  assignments (`_mentor_row`, `list_eligible_mentors`, `assign_engagement`) and
  mentoradmin (provision link, `reconcile_user_links`, `check_completeness`,
  `update_mentor`, the `/provision` idempotency guard). Verified live on the
  production CRM.
- **Approval no longer creates duplicate login Users.** When the link write
  silently failed, each re-save re-provisioned and created `firstname.lastname`,
  then `…2`, then `…3`. Provisioning now **reuses** the mentor's existing CBM login
  (when the profile already has a `cbmEmail`) instead of creating a suffixed
  duplicate; the suffix path remains only for a genuinely new email that clashes
  with a different person.
- **"Couldn't load mentors" (504) on Client Administration in production.** The
  eligible-mentor query filtered `CMentorProfile` by `assignedUserId` in a `where`
  clause, which prod EspoCRM forbids ("Forbidden attribute 'assignedUserId' in
  where" → 400, surfaced as 502/504). The clause is dropped; userless rows are
  filtered in Python (the field is still readable in `select`). Works on crm-test
  and prod.

### Added
- **`scripts/sync_form_options.py`** — refresh the static form dropdown lists from
  the live EspoCRM enums. Rewrites only the arrays wrapped in `crm-enum` marker
  comments in `forms/*/frontend/options.js` (presentational lists untouched);
  dry-run by default (diff + non-zero exit on drift, so it doubles as a CI check),
  `--write` to apply. First sync aligned the volunteer industry list (it had
  drifted to a different taxonomy on both crm-test and prod).

## [0.11.1] — 2026-06-25

### Added
- **Step-by-step Google Workspace setup guide on the Email Setup page.** The page
  is now a two-column layout: the config form on the left, and a sticky "How to
  set this up" instructions box on the right (Google Cloud Console → service
  account + JSON key; Workspace Admin → domain-wide delegation with both Directory
  scopes, each with a copy button; then the steps back in the app). Per-field
  helper text ties each input to the relevant step. (Version bump doubles as the
  deploy marker for this UI change.)

## [0.11.0] — 2026-06-24

### Added
- **Mentor approval now creates the CBM Google Workspace mailbox when it's
  missing, with a live status window.** Approving a mentor (`/mentoradmin`)
  auto-fills `cbmEmail` (`firstname.lastname@cbmentors.org`) if blank, checks
  Google Workspace for that mailbox, and — when `GOOGLE_CREATE_MAILBOX` is on —
  **creates** the mailbox (temp password + change-at-first-login + the mentor's
  personal email as Google recovery) instead of blocking, polls up to ~60s for it
  to go live, then creates the EspoCRM login + welcome email. The Save button
  opens a **streaming status modal** (Server-Sent Events) that narrates each step
  ("Checking for the mentor email account…", "No account found, creating…",
  "Creating the EspoCRM login…") and shows the temp password to relay.
  (`core/google_directory.py` `create_user`/`resolve_google_directory`,
  `mentoradmin/service.py` `provision_mentor_user_steps`, the SSE
  `POST /mentoradmin/api/mentors/{id}/provision`.)
- **Admin-only "Email Setup" screen** in `/mentoradmin` to configure the Google
  Workspace authentication at runtime (service-account JSON, delegated admin,
  check/create toggles, a **Test connection** button). The service-account key is
  stored **encrypted at rest** in Postgres (Fernet, keyed by the new
  `APP_ENCRYPTION_KEY`) and takes precedence over the `GOOGLE_*` env vars.
  (`core/crypto.py`, `core/app_config.py`, Alembic `0003_app_config`,
  `GET/PUT/POST /mentoradmin/api/setup/google`.)

### Notes
- Creating a mailbox needs the service account's **read-write** Directory scope
  (`admin.directory.user`) authorized for domain-wide delegation, in addition to
  the existing read-only scope. The GCP service account + delegation must still be
  set up in Google Admin (the Email Setup *Test* button verifies it).
- New deploy secret: `APP_ENCRYPTION_KEY` (web + worker). `GOOGLE_CREATE_MAILBOX`
  defaults off. Alembic `0003` adds the `app_config` table (pre-deploy migrate).

## [0.10.5] — 2026-06-24

### Changed
- **The mentor-assignment confirmation is now a styled modal**, matching the
  `modal-card` popups used elsewhere in the app (e.g. Mentor Administration),
  instead of the browser's native `window.confirm()`. Same Assign/Cancel flow,
  Escape/backdrop to dismiss (`assignments/frontend/app.js` + `styles.css`).

## [0.10.4] — 2026-06-24

> **Live in production** (`cbm-client-intake-prod`) — `/healthz` reports `0.10.4`.
> The CRM-side fix is applied: `CIntakeSubmission.submitterEmail` is now `varchar`
> in dev + prod, and a live test submission confirmed the email is stored.

### Changed
- **Reverted 0.10.3's `submitterEmailData` approach — the real fix is CRM-side.**
  Live testing showed `CIntakeSubmission.submitterEmail` stays null whether the app
  sends a plain string **or** the `submitterEmailData` array, because the field was
  built as EspoCRM type **`email`**, which is bound to the entity's single primary
  `emailAddress` field — a custom-named email-type field stores nothing. The fix is
  to change that field's type to **varchar** in the CRM (the sister
  `CInformationRequest.submitterEmail` is varchar and stores fine). The log reverts
  to the simple string write, which works once the field is varchar
  (`core/submission_log.py`). **CRM action required** — see
  `cintake-submission-entity.md`.

## [0.10.3] — 2026-06-24

### Fixed
- *(superseded by 0.10.4 — the `submitterEmailData` array did not work either; the
  field type itself is the problem.)* Attempted to store
  `CIntakeSubmission.submitterEmail` via the `submitterEmailData` array.

## [0.10.2] — 2026-06-24

### Changed
- **The form index is served with `Cache-Control: no-store`**, so a freshly
  deployed landing page is never shown stale from a browser/edge cache (a
  redeploy briefly served the previous index from cache otherwise)
  (`core/app.py` `index`).

## [0.10.1] — 2026-06-24

### Changed
- **The form index opens each form/staff-tool link in a new browser tab**
  (`target="_blank"` + `rel="noopener"`), so the landing page stays put when a
  user opens a form or staff tool (`core/app.py` `_index_html`).

## [0.10.0] — 2026-06-24

### Added
- **Mentor provisioning hard-gates on the Google Workspace mailbox.** Before
  creating an EspoCRM login (and firing its `sendAccessInfo` welcome email) for an
  approved mentor, the app can verify their `firstname.lastname@cbmentors.org`
  mailbox actually exists in Google Workspace — otherwise the credentials email
  bounces and the mentor is stranded with a login they can't receive. A
  *confirmed-missing* mailbox blocks provisioning with a clear error ("create it
  before approving"); an inconclusive check (not configured, API/auth error) fails
  **open** so a Google outage can't freeze approvals. New `core/google_directory.py`
  (`GoogleDirectory.mailbox_status` → `EXISTS`/`MISSING`/`UNKNOWN`, via the Admin
  SDK Directory API with a domain-wide-delegated service account, read-only scope).
  **Off by default** — a no-op until `GOOGLE_DIRECTORY_CHECK=true` +
  `GOOGLE_SERVICE_ACCOUNT_JSON` + `GOOGLE_DELEGATED_ADMIN` are set, so prod is
  unchanged until the Google credentials exist.

## [0.9.1] — 2026-06-24

### Fixed
- **Mentor Admin no longer silently hides "no login created" on approval.** When a
  mentor is saved at `Approved`/`Active` but login provisioning is disabled on the
  server (no admin service account configured — the production state), the save now
  returns `provision={ok:false, disabled:true}` and the UI shows *"Status saved, but
  no login was created — mentor login provisioning is turned off on this server."*
  Previously this case was indistinguishable from a successful approval, so an
  approval in prod silently created no EspoCRM User and no welcome email
  (`mentoradmin/service.py`, `mentoradmin/frontend/app.js`).

## [0.8.0] — 2026-06-23

### Fixed
- **Implausible phone numbers no longer fail the Contact create.** A submission
  with a bogus phone (e.g. `12345` → `+12345`) was 400'ing EspoCRM's `phoneNumber`
  "valid" check and losing the whole lead. `core/phone.e164_or_none` normalizes to
  E.164 but returns `None` when the result can't be a real number (<10 or >15
  digits); every orchestrator (volunteer, client-intake, partner, sponsor,
  info-request — both the Contact and the `CInformationRequest` phone fields) now
  **omits** `phoneNumber` when invalid. Email stays the contact channel and the
  raw value is preserved in the `CIntakeSubmission` audit log.
  *(This was the one stuck volunteer re-drive that still failed after enum
  resilience landed.)*

## [0.7.0] — 2026-06-23

### Added
- **Enum-drift resilience extended to client-intake and partner.** `EnumSanitizer`
  generalized to span a whole create chain (entity passed per call, options cached
  per `(entity, field)`, one aggregated note):
  - **client-intake** — sanitizes `cBusinessStage` + `cIndustrySector` (Account)
    and `mentoringFocusAreas` (CEngagement); drop-note on `CEngagement.description`.
  - **partner** — sanitizes `partnershipType` + `partnershipValue`; drop-note on
    `CPartnerProfile.description`.
  - **sponsor** — no change (writes no user-supplied enum, only system
    discriminators + a free-text message).
- System discriminators (`cAccountType`/`cContactType`/status) are deliberately
  **not** sanitized — they're required/monitored and must fail loudly if they drift.

## [0.6.0] — 2026-06-23

### Added
- **Enum-drift resilience (volunteer).** New `core/enum_filter.py` `EnumSanitizer`
  validates enum/multiEnum payload values against the live CRM options and **drops**
  unrecognized ones instead of letting a single drifted value 400 the whole create.
  The volunteer orchestrator sanitizes `industrySector` / `mentoringFocusAreas` /
  `fluentLanguages`; dropped values are noted on `CMentorProfile.description` for
  staff follow-up. Fails open (keeps the value if options can't be fetched, e.g.
  dry-run). `metadata_enum_options` added to the `EspoApi` protocol +
  `DryRunEspoClient` + `ResumableClient`. **Effect:** re-driving a drift-failed
  submission now creates the record (with the valid data + contact info) instead
  of failing — no discarding needed.

## [0.5.0] — 2026-06-23

### Added
- **`/ops` Discard action.** A stuck submission that can't be delivered (e.g. a bad
  payload that re-driving would just replay) can be moved to a terminal `discarded`
  status, so it leaves the worker queue and stops counting toward the
  needs-attention alert. The row is kept for audit; a completed delivery can never
  be discarded; Re-drive also covers `discarded` so a mistaken discard can be
  undone. (`store.discard()`, `POST /ops/api/submissions/{id}/discard`, Discard
  button on stuck rows.)

## [0.4.0] — 2026-06-23

First version bump of the session — the footer/`/healthz` had been stuck at 0.3.0,
so it gave no signal for whether a new build was live. `core/__init__.__version__`
now reads from `pyproject.toml` (single source) instead of a stale hardcoded value.
Bundles the following work, all shipped under this version:

### Added
- **Client Administration (`/assignments`) — Available Mentors grid:** a **Type**
  column + filter (sortable) and an **Accepting** (new clients) column. `mentorType`
  is normalized so a single enum or multi-enum both render/filter/search.
- **Client Administration — Requested Mentor (DAT-026).** The engagement detail
  popup now shows the `CEngagement.requestedMentor` link (belongsTo CMentorProfile)
  when set, resolving the name defensively (inline accessor → CMentorProfile read;
  a deleted target shows "(no longer in the system)"). Hidden when unset.
- **Worker crash-recovery (lease).** `claim_batch` now leases each claimed row
  (`locked_until = now + worker_lease_seconds`, default 900s) and reclaims
  `processing` rows whose lease expired — a worker killed mid-delivery
  (redeploy/OOM/SIGKILL) no longer strands a submission in `processing` forever
  (safe because delivery is resumable). Alembic migration `0002_processing_lease`
  adds `locked_until` + a claim index.
- **`/healthz` database check.** Pings the durable store and returns `503` +
  `database:"error"` when it's configured but unreachable. The CRM is deliberately
  not pinged (a CRM outage must not take the web tier down — durable capture +
  the async worker exist to ride it out).

### Changed
- **Public intake forms (all five) — UX.** The submission **reference number** is
  now shown on the confirmation screen; a **30s request timeout** (AbortController)
  with a retryable message replaces an indefinite "Submitting…"; validation errors
  are **announced + focused** (`role="alert"`); a double-submit guard; clearer phone
  placeholders + explicit "(optional)" labels. (Applied in both the shared
  `wizard.js` and client-intake's standalone `app.js`.)
- **Staff tools — UX.** All three (`/assignments`, `/ops`, `/mentoradmin`) now
  distinguish a 5xx/network boot failure ("server isn't responding") from "not
  signed in". `/mentoradmin`: cancelling the incomplete-record modal jumps to the
  first unresolved field; a field-spec load failure warns instead of a blank
  editor. `/assignments`: labeled load errors (mentors vs engagements). `/ops`:
  surfaces "metrics unavailable" instead of swallowing the error.

### Fixed
- **Schema drift — volunteer industry/language.** The form's `industryExperience`
  (20 NAICS sectors) had **zero overlap** with the live `CMentorProfile.industrySector`
  enum (28 CBM values), and `fluentLanguages` offered 36 vs the CRM's 2 — so every
  industry pick (and most language picks) 400'd. Aligned both lists to the live
  enums (verbatim, including the CRM's typos). Extended `core/schema_contract.py` to
  cover the volunteer form's enum fields so the Phase-3 drift monitor warns before
  the next such failure (they were previously unmonitored).
- **`session_expired`** now matches the *first* `HTTP <code>` in the EspoError
  message, so a 502 whose body merely contains "HTTP 401" is no longer misread as
  token expiry.
- **`assign_engagement` partial-failure reporting.** The downstream re-homing
  (contacts/client/account) is now best-effort and per-target — a CRM failure on
  one record is captured in `reassignmentErrors` and reported to the staffer,
  instead of raising after the engagement was already assigned. Steps 1–2 (the core
  assignment) stay fail-fast.

---

For per-feature design notes and live-verification records, see `CLAUDE.md`. The
V2 reliability platform (durable capture + async worker + ops + alerting) is
specified in `prds/v2/`.
