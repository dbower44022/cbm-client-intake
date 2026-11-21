# The home page and Chapter News — plan

Last Updated: 11-21-26 01:45 · Revision 1.19 — change log at the end.

**Status: designed 11-16-26 to 11-17-26 in a Cowork session with Doug; every
decision below is his. Phase 0 (the contrast fix to the design tokens) is
built as v0.340.3. Phase 1 (the page frame) is built as v0.343.0, dark
behind `HOME_V2`, and passed stop 1 on 11-18-26. Phase 2 (Today and My
clients) is built as v0.346.0, dark behind `HOME_V2`, and passed stop 2 on
11-18-26; Doug's three changes after it are v0.348.0 (§ 8), checked by
him the same day, which closed the phase. Phase 3 (Needs you) is built as
v0.349.0, with Doug's two changes at its stop as v0.349.1 and v0.350.1,
dark behind `HOME_V2`; stop 3 passed on 11-20-26, which closed the phase.
Phase 4 (At the chapter) is built as v0.351.0, dark behind `HOME_V2`,
and passed stop 4 on 11-20-26, which closed the phase. Doug asked for phases 5 to 7 in one session with the fixed header bar and
one big test (11-20-26): `prompts/home-page-phases5-7-autonomous-prompt-v0.1.md`.
The fixed header bar is v0.352.0; phase 5 (Chapter News core) is v0.353.0, phase 6 (read reports) v0.355.0, phase 7 (the weekly digest) v0.356.0,
dark behind `CHAPTER_NEWS`, its CRM build on the Business Mentors
Association's CRM only. The decisions that session took on Doug's behalf are
listed under phase 5 in § 8. One stop, the big test, closes all three. **Big test run by Doug 11-20-26 on v0.356.3: the fixed header bar and phases 5 and 6 passed (stops 5 and 6 closed); the digest's delivery is untested (Doug, option C), so stop 7 stays open.**

Mockups: the design canvas *CBM Home Page — Looks*
(https://claude.ai/artifact/D6Gm6i9qYgBsYmMtUSfAmY). The **Mix** artboard is
the chosen look; Looks A and B stay on the canvas for reference.

## 1. Purpose

Today the signed-in home page (`portal/`) is a launcher: app tiles gated by
team, count badges for the staff work queues, the events rail, the analytics
panel and the birthday overlay. A mentor signing in sees tiles and nothing
about their own clients, sessions or week.

This plan turns the home page into the page that answers, at sign-in, what
the member must do today, what is slipping, how their clients are doing, and
what is happening at the chapter. It adds **Chapter News**: news that
publishers write and every member sees at sign-in. It also fixes a contrast
fault in the base design tokens that every application inherits, and sets the
design-system rules the new page, and later the other applications, follow.

## 2. Terms

- **Member**: anyone who signs in: mentors, staff and administrators.
- **Section**: one panel of the home page, such as Today or Needs you.
- **Attention item**: one row of the Needs you section, linking to the record
  it is about.
- **News item**: one piece of Chapter News, a record in the CRM.
- **Publisher**: a member allowed to write and publish news items.
- **Audience**: the teams a news item is for. No audience means every member.
- **Dismiss**: a member's one click that takes a read news item off their home
  page.
- **Acknowledge**: a member's explicit "I have read this" on a news item that
  requires it, recorded with the time.
- **Read receipt**: the CRM record of one member dismissing or acknowledging
  one news item.
- **Chip**: a small labelled box that says what kind of attention item a row
  is, coloured by meaning (§ 5.3).
- **Status pill**: a small rounded label for a record's status in a table.

## 3. Doug's rulings

1. **Summary and link** (11-16-26, option A). The home page shows work and
   links to the application that does it. It hosts no forms. Only actions
   that need no form happen in place: join a meeting, open an email, dismiss
   or acknowledge a news item. Each application keeps sole ownership of its
   write logic. Cost, accepted: mentors switch tabs to act.
2. **One page that adapts by role** (11-17-26, option A). Every member gets
   the same layout; each section appears only when the member's teams entitle
   them to it, the same way tiles and badges do today. A member with several
   roles sees one Needs you list that mixes staff queue items and mentoring
   items, sorted by urgency, not by application. Cost, accepted: long pages
   for members with many roles, eased by collapsing and hiding sections.
3. **Assignment stays staff-only** (11-17-26, option A). Mentors do not see,
   volunteer for, or claim clients waiting for a mentor, and are not shown a
   count of them. Client Administration staff keep seeing the waiting clients
   in their Needs you list.
4. **Chapter News** (11-17-26). Publishers publish news; members dismiss it
   after reading and can view past news. The first release has read reports, a
   weekly digest of unread news, items that must be acknowledged, audience by
   team, a call-to-action button and pinned items. **Posting news to the public
   chapter website is out of scope** (Doug: "I am not sure that will ever be
   done").
5. **Publishers write on a Chapter News page in the application, and
   everything is stored in the CRM** (11-17-26, option B, "with the
   requirement that the information is still stored in the CRM").
6. **Read receipts are CRM records** (11-17-26, option A). Acknowledgments of
   policy items are records someone will be asked about, and Analytics builds
   its reports from CRM records, the same reasoning as the Business Evaluation
   ruling that feedback survey answers live in the CRM.
7. **The look is the Mix artboard on a grey page** (11-17-26). Look B's quiet,
   dense layout, with Look A's colour used only for status and urgency, on
   Look A's light grey page background. Cost, accepted: the colour meanings in
   § 5.3 are a standard every screen must follow.
8. **Darken the gold and body-text tokens for contrast** (11-17-26, option
   A). Cost, accepted: buttons read a shade darker than the public website's
   gold. Built as phase 0 (§ 8).
9. **No component library.** The pages stay plain HTML, CSS and JavaScript on
   `frontend/shared/tokens.css`. AlignUI, coss ui, daisyUI, HeroUI and Ant
   Design were looked at as visual references only; four need React, and
   daisyUI needs a Tailwind CSS build step.

## 4. The home page

### 4.1 Layout, top to bottom

A white header bar carries the organisation name and the member's
applications as a compact navigation row, built from the same entitlement
list as today's tiles (`portal/router.py: _apps_for`), each still opening in
its stable named tab. Then a greeting with the date and a one-line count
("2 sessions today · 5 items need you"). Then the sections, in this fixed
order:

1. **Chapter News**: the member's unread news (§ 6). With nothing unread it
   shrinks to a **Past news** link.
2. **Today**: today's sessions with their video meeting links, and a line for
   the rest of the week.
3. **Needs you**: the attention list (§ 4.2).
4. **My clients**: one row per active engagement: client, status, last
   contact, next session.
5. **At the chapter**: the chapter's clients served, sessions held and hours
   mentored for the calendar year, each with the member's own beside it,
   and open asks (the running call campaigns the member's team is named
   in). **Upcoming events** is a panel of its own beside it (Doug,
   11-18-26) and holds the workshops; the **Analytics** dashboard is a
   panel of its own at the end of the page (phase 4).

Today and Needs you sit side by side on a wide screen and stack on a narrow
one. Every section fails quietly on its own, as the attention badges do today:
a failed read hides that section, never the page.

### 4.2 The Needs you list

Each item is one row with a chip (§ 5.3), the record's name, a short reason,
and a link that opens the owning application on that record (ruling 1). Rows
are sorted by urgency, then by age. The kinds, and where each comes from:

| Kind | Chip | Source |
|---|---|---|
| A client with no contact for longer than the threshold | the day count, red | `CEngagement.lastContactDate`, else `engagementAssignedDate`; Active, Assigned and Pending Acceptance, never On-Hold |
| A session held with no notes | Notes, amber | a Completed session of the last 30 days with empty `sessionNotes` and `nextSteps` and no meeting summary |
| A meeting summary waiting for review | Summary, navy | a Completed session of the last 14 days with `sessionAiSummary` and empty `sessionNotes` |
| A client email waiting for a reply | Email, navy | My Email's own awaiting-reply rule, the message at least one working day old |
| A newly assigned client | New, navy | Pending Acceptance, or `engagementAssignedDate` in the last 7 days |
| A staff work queue with items | Staff, purple | today's attention counts, one row per queue, after every mentoring row |

The no-contact threshold is a System Settings value, default 21 days
(`HOME_NO_CONTACT_DAYS`). The order, most urgent first: no contact, Notes,
Email, Summary, New, Staff; within a kind, the oldest first, and for Staff
the largest queue first. **Closing** (an engagement near its close date)
is left out: `CEngagement.closeDate` is stamped when an engagement closes
(ruling 70), so no planned end date exists (phase 3, answer 4).

### 4.3 Collapsing and hiding

A member may collapse or hide any section; the choice is stored in the
existing per-user preferences store (`PREFERENCE_KEYS` gains `home.sections`).
The Chapter News section cannot be hidden while it holds an item that must be
acknowledged.

### 4.4 What the page reuses

The attention counts (`core/attention.py`), the events rail
(`events/service.portal_calendar`, never re-filtered here), the analytics
portal panel's numbers, the birthday overlay, `busy.js` with
`CBMBusy.loading` around every section that waits on the server, the shared
grid for the My clients table, and the `{{org}}` and `{{abbr}}` tokens for
every visible name.

## 5. Design-system rules

These rules are the Mix artboard written down. They apply to the home page
from phase 1 and to any other screen as it is next reworked.

### 5.1 Tokens

The base layer stays `frontend/shared/tokens.css`; chapters still override it
with their colour file. New tokens, added in phase 1:

| Token | Value | Use |
|---|---|---|
| `--cbm-page` | `#F4F6F9` | The page background behind the panels |
| `--cbm-panel` | `#FFFFFF` | A panel's background |
| `--cbm-panel-border` | `#E3E8EF` | A panel's border and its row dividers |
| `--cbm-panel-radius` | `8px` | A panel's corners |
| `--cbm-text-strong` | `#111827` | Names and titles inside panels |
| `--cbm-text-muted` | `#4B5563` | Section labels and secondary lines |

Changed in phase 0: `--cbm-gold` `#8F6420`, `--cbm-btn-bg-hover` `#7A5518`,
`--cbm-text` `#5B6676`; new `--cbm-gold-light` `#CB963B`, the original gold,
for decoration that carries no text.

### 5.2 Components

All in one new shared stylesheet, `frontend/shared/panel.css`.

- **Panel**: white, a 1 px border, 8 px corners, no shadow. Rows inside are
  separated by 1 px dividers, never by gaps.
- **Section label**: 12 px, semibold, upper case, letter-spaced, muted grey,
  above or at the top of its panel. A count may follow it as a small pill.
- **Chip**: 12 px semibold text in a tinted box with 6 px corners, a fixed
  minimum width so a column of chips lines up.
- **Status pill**: 12 px semibold text in a tinted, fully rounded box.
- **Row**: 14 px text; the record's name in strong text, the reason in body
  text. The single most urgent row in a list may carry the red tint as its
  background; no other row does.
- **Buttons**: the main action is gold with white text; a second action is a
  white button with a border. Touch targets at least 40 px high. Never
  disabled, never hidden (the root `CLAUDE.md` convention).

### 5.3 What each colour means

Colour is reserved for status and urgency. Everything else is navy, grey or
white.

| Colour | Tint / text | Means |
|---|---|---|
| Red | `#FDECEC` / `#9B1C1C` | Overdue or at risk |
| Amber | `#FFF0D6` / `#7A4A00` | Missing, waiting, or must be acknowledged |
| Navy | `#E8EEF6` / `#173B60` | Informational: email, summary, new, pinned |
| Green | `#E6F6EA` / `#1D6B34` | Healthy: Active |
| Purple | `#EDE9FE` / `#5B21B6` | Staff work queue |

Text on any background reaches 4.5 to 1. Colour never carries meaning alone:
every chip and pill also says its meaning in words.

## 6. Chapter News

### 6.1 What the member sees

The Chapter News section lists the member's unread items: items that must be
acknowledged first, then pinned items, then the rest, newest first. Each shows
its title and summary; opening it shows the full body, with formatted text and
images. An optional call-to-action button opens the application or page that
does the work. A normal or pinned item has **Dismiss**; an item that must be
acknowledged has **I have read this** instead and stays at the top until
clicked. **Past news** lists every item the member could see, newest first,
dismissed, acknowledged and expired ones included. A member outside an item's
audience never sees it, anywhere.

### 6.2 What the publisher sees

A **Chapter News** page, its tile shown only to publishers. It lists every
item with its status, publish date and read count. Writing uses `CBMRichText`
with its `uploadImage` hook, so images are inline attachments on the news
item's live wysiwyg field. Beside the editor, a live preview shows the item as
a member will see it, collapsed and opened. The publisher sets the audience,
importance, publish date, optional expiry date and optional call-to-action
button. The **read report** on the same page shows how many of the audience
have read the item, out of how many, and who has not; for an item that must
be acknowledged, who acknowledged and when. A publisher can withdraw an item;
a withdrawn item disappears for every member, past news included. Every
publisher action is recorded through `core/action_log.py`.

### 6.3 Rules

- **Read** means dismissed or acknowledged. Being shown is not recorded.
- An expired item leaves the News section and the digest but stays in past
  news. An expired item that required acknowledgment stops prompting.
- A member who joins after an item was published sees it while it has not
  expired, if they are in its audience.
- Editing a published item resets no one's read status. A material change,
  such as a corrected policy, is published as a new item.
- Who may publish is a new team setting, `NEWS_PUBLISH_ALLOWED_TEAMS`,
  default System Management Team. **Superseded 11-21-26 (Doug): the
  default is Marketing Admin Team.**

### 6.4 Data — all in the CRM

**`CChapterNews`**, the news item:

| Field | Type | Notes |
|---|---|---|
| `name` | Varchar | The title |
| `summary` | Text, short | Shown collapsed and in the digest |
| `body` | Wysiwyg | Formatted text and images |
| `status` | Enum | Draft, Published, Withdrawn |
| `publishAt` | Date-time | Goes live at this time |
| `expiresAt` | Date-time, optional | Leaves the News section at this time |
| `importance` | Enum | Normal, Pinned, Must acknowledge |
| `audienceTeams` | Multi-enum of team names | Empty means every member. Built as a multi-select, not a link: EspoCRM refuses any link to Team (not customizable); the build script keeps its options in step with the CRM's teams |
| `ctaLabel` | Varchar, optional | The button's text |
| `ctaUrl` | URL, optional | Where the button goes |

**`CChapterNewsReceipt`**, the read receipt, one per member per item:

| Field | Type | Notes |
|---|---|---|
| `news` | Link to `CChapterNews` | The item |
| `user` | Link to User | The member |
| `action` | Enum | Dismissed, Acknowledged |
| `actedAt` | Date-time | When the member acted |

The pair of item and member is unique; a second click finds the existing
receipt. The application writes receipts under the org-wide key, so members
need no new CRM permissions. The receipts show as a related list on the news
item in the CRM. The only Chapter News data outside the CRM is each member's
digest opt-out, in the per-user preferences store (`news.digest`).

One handoff, `cchapternews-entities-crm-handoff.md`, covers both entities, in
Entity Manager vocabulary, applied by `prds/chapter-network/crm-update-runbook.md`.
The feature detects both entities from metadata and stays dark until they
exist.

## 7. What is out of scope

- Hosting forms or edits on the home page (ruling 1).
- Showing mentors clients who are waiting for a mentor (ruling 3).
- Posting Chapter News to the public chapter website (ruling 4).
- Comments and reactions on news: they would need moderation; replies go by
  email.
- Moving the other applications onto the panel look. Each follows when it is
  next reworked.

## 8. Build plan

Each phase is one release, behind its own switch, off by default, except
phase 0. **Each phase ends at a stop: Doug's check on the test system, the
Business Mentors Association's (root `CLAUDE.md` § Deployment), before the
next phase starts.** A push to `main` deploys the test system, crm-test and
production together; every phase after 0 is behind a switch that is off, so
production changes only when its switch is turned on there. Phase 0 has no
switch: its push changes production's colours at once, which is intended.

- **Phase 0 — the contrast fix (built, v0.340.3).** `tokens.css`: the three
  changed values and `--cbm-gold-light`; Marketing Management's list-members
  gold button hover reads `--cbm-btn-bg-hover` instead of a fixed colour;
  `chapter-colours.md` gains the new values and asks each chapter to check
  that white text on its button colour reaches 4.5 to 1. **Stop 0**: Doug
  looks at an intake form, a staff application and the portal on the test system.
- **Phase 1 — the page frame.** Switch `HOME_V2`; off keeps today's page. The
  new tokens and `frontend/shared/panel.css`; the header with the
  applications row; the greeting; empty section frames that self-gate; collapse
  and hide with the `home.sections` preference. **Stop 1**: the frame as a
  mentor, a staff member and an administrator.
  **Built v0.343.0 (11-18-26); stop 1 passed 11-18-26.** Doug's answers at the phase's first stop:
  the page is a second view inside today's `portal/frontend/index.html`;
  the events rail and the analytics panel sit in At the chapter, the CRM and
  Documentation links in the header, the public pages in a last frame;
  the application row wraps on a wide screen and becomes one *Applications*
  menu below 720 px. The chip and button classes are `cbm-kind-chip` and
  `cbm-action`, because `cbm-chip` and `cbm-btn` are taken.
- **Phase 2 — Today and My clients.** Both read the member's own sessions and
  engagements as the member. **Stop 2**: against a mentor with real sessions.
  **Built v0.346.0 (11-18-26); stop 2 owed.** Doug's answers at the phase's
  first stop, all as recommended: My clients lists the four active statuses
  (Active green, Assigned navy, Pending Acceptance and On-Hold amber); Open
  lands on the record's Sessions tab and the client's name on its Overview,
  each in the record's own named tab; Join shows whenever a session has a
  video meeting link, the next one to start in gold; co-mentored clients
  sit in the same list, marked "co-mentor"; one new endpoint,
  `GET /api/portal/home/mentoring`, calling `list_records` as the member.
  Today lists Scheduled sessions only, and its last line covers the next
  seven days as "Coming up". **Stop 2 passed 11-18-26** ("The new features
  worked great"). Doug's three changes after it, built as v0.348.0: the four
  directories are one *Directories* menu in the bar; Upcoming events is its
  own panel beside At the chapter, which keeps the Analytics numbers; and a
  **text size** (Standard, Large, Larger) for older mentors, chosen on the
  home page, kept as the member's preference `ui.textSize` and applied on
  every staff and mentor page (option A of three; B was one chapter-wide
  size in System Settings, C the home page only). **Checked by Doug on the
  test system 11-18-26; phase 2 closed.**
- **Phase 3 — Needs you.** Every kind in § 4.2, the staff counts folded in,
  and the threshold setting. **My Email gains a link that opens one
  conversation** (`/myemail/?conversation=<id>`), so the Email rows can point
  at it; the four other applications already open on a record from a link.
  **Stop 3**: one example of each kind on the test system.
  **Built v0.349.0 (11-18-26); stop 3 passed 11-20-26 ("All points done").** Doug's eight answers at the
  phase's first stop, all as recommended: (1) Notes is a Completed session
  of the last 30 days with neither session notes nor next steps, a meeting
  summary not counting as notes; (2) nothing in the CRM records a review,
  so a summary waits while the session notes are empty, for 14 days (no
  new field); (3) Email reuses My Email's rule, after one working day, from
  the same inbox run as My Email's badge; (4) Closing is dropped for now,
  since the close date is stamped at closing; (5) New is Pending Acceptance
  or assigned in the last 7 days; (6) one threshold, On-Hold never listed;
  (7) the order above, staff rows after the mentoring rows; (8) one new
  endpoint, `GET /api/portal/home/needs`, sharing the engagement read with
  Today's for 20 seconds, and the bar's count badges move into the list.
  Built on the way: Summary looks at the session notes only, because the
  note taker writes its action items into an empty next steps field.
  **Changed at stop 3 (v0.349.1, Doug 11-19-26, option C):** My Email's
  window cannot reply, so an Email row opens the record's Communications
  tab with the conversation's window open (Reply one click away), the
  engagement first when the conversation is on several records; My
  Email's "Open … — reply there" button opens the same place. **v0.350.1
  (11-20-26):** a click or double click anywhere on a Needs you row opens
  it, and a click anywhere on a My Email row opens the email.
- **Phase 4 — At the chapter.** Year-to-date numbers from the analytics
  portal panel's sources, the events rail's upcoming workshops, and open asks
  from Marketing Management's running call campaigns. A presenter-wanted ask
  has no data source yet and is left out until one exists. **Stop 4**.
  **Built v0.351.0 (11-20-26); stop 4 passed 11-20-26** ("Runbook
  completed successfully"; Marketing Management and Campaign calls switched
  on at the Association for it and left on, Doug's choice B). Doug's eight answers at the
  phase's first stop, all as recommended: (1) three numbers, clients served
  (engagements with a Completed session), sessions held and hours mentored,
  from one read of the year's Completed sessions; (2) the calendar year, in
  the chapter's time zone; (3) every member sees the chapter's figures,
  read with the chapter-wide key as totals; (4) "yours" for mentors with a
  profile, owned and co-mentored engagements of every status; (5) the
  Analytics dashboard moves into its own panel at the end, shown only
  where it comes up; (6) workshops stay in Upcoming events; (7) asks are
  the Running call campaigns naming the member's team, with the calls left
  as the Calls tab counts them; (8) one new endpoint,
  `GET /api/portal/home/chapter`, the chapter's figures and the campaigns
  kept for everyone for 15 minutes.
- **Phase 5 — Chapter News core.** Switch `CHAPTER_NEWS`. The handoff and both
  entities on the test system's CRM first; the News section with dismiss, acknowledge,
  pinned ordering, audience and the call-to-action button; past news; the
  Chapter News page with the editor, preview and withdraw; the publisher team
  setting. **Stop 5**: Doug publishes one item of each importance and reads
  them as a mentor.
  **Built v0.353.0 (11-20-26), one session with phases 6 and 7; the stop is
  the big test at the end of that session.** CRM build applied on the
  Association's CRM only (`scripts/migrate_chapter_news_schema.py`, which
  refuses any other). The decisions taken in advance at Doug's direction of
  11-20-26, each with its cost: (1) one release per phase (four version
  numbers); (2) audience by team — **changed**: EspoCRM's own code refuses a
  link to Team, so the fallback was built, a multi-select of team names kept
  in step by the build script (a team renamed later needs the options
  updated, and items keep the old name); (3) members and publishers write
  under the org-wide key, gated by this application (the CRM's history
  names the API user; the action log names the publisher); (4) publishers
  are `NEWS_PUBLISH_ALLOWED_TEAMS`, default System Management Team (on the
  Association only Doug's account is in it; **superseded 11-21-26: default
  Marketing Admin Team**); (5) publishing is its own
  application, Chapter News at `/news/`; (6) images are inline attachments
  on the body, shown to members through a proxy that serves only an image
  the item's body references, for an item the member may see; (7) an
  expired item to acknowledge stops prompting and says "Not acknowledged"
  in past news; (8) the items are kept 60 seconds for the whole process and
  dropped at once on a publish, edit or withdraw (another web process can
  show a withdrawn item for up to a minute); (9) the News section is first
  on the page and cannot be hidden **or collapsed** while an item to
  acknowledge waits (collapsing would hide the item as surely). Taken in the
  build: being an administrator does not widen an audience (an
  administrator outside it sees the item only on the Chapter News page),
  and editing a published item resets no one's read status (§ 6.3).
- **Phase 6 — read reports.** On the Chapter News page. **Stop 6**.
  **Built v0.355.0 (11-20-26)**: a Read column in the list ("3 of 12") and a
  Read report for the open item (who acknowledged and when, who has not,
  who dismissed). Taken in the build: the audience is counted from the
  CRM's members, every active regular login and every administrator in at
  least one team (the service accounts are in none); a receipt from someone
  who has left the audience is not counted. Cost: a member is counted by
  their teams today, so a member who joined late counts against an old
  item.
- **Phase 7 — the weekly digest.** Switch `NEWS_DIGEST`. A weekly worker job
  emails each member with unread items one list, from the shared mailbox
  (`OPS_MAILBOX`), items that must be acknowledged always included; the
  `news.digest` opt-out; nothing sent to a member with nothing unread.
  **Stop 7**: a digest received on the test system.
  **Built v0.356.0 (11-20-26)**, dark behind `NEWS_DIGEST`. Decided in
  advance (decisions 10 and 11): Monday at 08:00 in the chapter's time zone,
  both System Settings values; once per member per week, recorded in the
  application database; training addresses counted, never mailed. Taken in
  the build: the digest goes to the address on the member's CRM login (a
  mentor's login address is their chapter address); a worker started within
  12 hours after the hour catches up that week; the publisher's **Send me a
  test digest** is not counted as the week's digest.

## 9. Open questions, decided in their phase

- ~~The exact field that marks a session as having no notes (phase 3).~~
  Decided 11-18-26: both `sessionNotes` and `nextSteps` empty (§ 8).
- ~~Whether the no-contact threshold differs by engagement status (phase 3).~~
  Decided 11-18-26: one value; On-Hold is never listed.
- A planned end date for an engagement, which the Closing kind needs
  (phase 3 left it out).
- A data source for presenter-wanted asks (phase 4 or later).
- ~~The digest's day and hour (phase 7).~~ Decided 11-20-26: Monday 08:00
  in the chapter's time zone, changeable at System Settings.

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 1.19 | 11-21-26 01:45 | Publishers' default team is Marketing Admin Team, in place of System Management Team (Doug, 11-21-26; v0.359.4). |
| 1.18 | 11-20-26 18:59 | Big test run: header bar, phases 5 and 6 passed; stop 7 open (digest untested, option C); fixes v0.356.2 and v0.356.3. |
| 1.17 | 11-20-26 02:46 | Phase 7 built (v0.356.0); § 9's digest question closed. |
| 1.16 | 11-20-26 02:33 | Phase 6 built (v0.355.0). |
| 1.15 | 11-20-26 02:12 | Fixed header bar built (v0.352.0); phase 5 built (v0.353.0) with its decisions in § 8; `audienceTeams` is a multi-select of team names. |
| 1.14 | 11-20-26 01:40 | Phases 5 to 7 and the fixed header to be built in one session (Doug, 11-20-26); its prompt written. |
| 1.13 | 11-20-26 01:30 | Stop 4 passed; phase 4 closed; phase 5's prompt written. |
| 1.12 | 11-20-26 01:05 | Phase 4 built as v0.351.0: § 4.1's At the chapter as decided, § 8's answers. |
| 1.11 | 11-20-26 00:55 | Stop 3 passed; phase 3 closed; phase 4 started. |
| 1.10 | 11-20-26 00:10 | Stop 3 change: whole rows open (v0.350.1). |
| 1.9 | 11-19-26 23:55 | Stop 3 change: Email rows and My Email's reply button open the conversation on the record (v0.349.1). |
| 1.8 | 11-18-26 22:50 | Phase 4's prompt written, before stop 3. |
| 1.7 | 11-18-26 18:20 | Phase 3 built as v0.349.0: § 4.2's kinds as decided, Closing left out, § 8's answers, § 9's two phase 3 questions closed and the end-date question added. |
| 1.6 | 11-18-26 18:00 | v0.348.0 checked by Doug; phase 2 closed; phase 3's prompt written. |
| 1.5 | 11-18-26 02:15 | Stop 2 passed; Doug's three changes after it (Directories menu, Upcoming events panel, text size) recorded in § 4.1 and § 8, built as v0.348.0. |
| 1.4 | 11-18-26 01:50 | Phase 2 built as v0.346.0; § 8 records Doug's answers at its first stop. |
| 1.3 | 11-18-26 01:45 | Stop 1 passed. |
| 1.2 | 11-18-26 01:10 | Phase 1 built as v0.343.0; the status line and § 8 record Doug's three answers at its first stop. |
| 1.1 | 11-17-26 02:30 | The stops are checks on the test system, the Business Mentors Association's, not crm-test; § 8 says what a push deploys. |
| 1.0 | 11-17-26 01:30 | Created from the 11-16-26 to 11-17-26 design session: rulings 1 to 9, the home page, the design-system rules, Chapter News, and the build plan. Phase 0 built as v0.340.3. |
