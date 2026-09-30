# CBM Events — The Portal Calendar: Design (Track F, F5)

Last Updated: 09-30-26 14:55 · Revision 0.1 — see change log at the end.

**Status: DRAFT, awaiting Doug's review. Nothing is built.** The requirements
are Doug's six rulings recorded in `CBM_Events_Finalization_Plan.md` revision
4.11, section F5; they are cited below as *F5-n*. What F3 already settled for
this surface is cited as *F3-n* and the F2/F3 design as *design § n*. Everything
else is Claude's design and is marked where it is a choice. The two decisions in
§ 9 are Doug's to rule; the design as a whole awaits his approval before
anything is built.

**Terms used here.** The **portal** is the page a member sees after signing in
at `/`. The **rail** is the events list on its left side. The **strip** is what
the rail becomes on a phone. The **member page** is the page one event opens,
behind the portal sign-in. The **window** is the number of days the rail shows
in full. A **member** is any signed-in CRM user.

---

## 1. What this changes, in one paragraph

The portal's home view becomes two columns: the rail on the left, listing every
event the member may see (F3-8) for the next thirty days with the rest folded
behind one line (F5-2), and the existing sections filling the width on the
right, with the portal's width cap removed. Each event opens a member page at
`/portal/events/{id}` that renders the same body as the public event page
(F5-1). An Internal event that takes registrations carries a Register button in
its row and on its page, one action in both places (F5-4); a Public webinar's
page links to its website page instead (F5-6). Two switches, saved to the
member's account, hide Internal events or Public webinars (F5-3). On a phone
the rail collapses to a one-line strip that expands on a tap (F5-5). All of it
sits behind a new switch, off by default, so it can be reviewed on crm-test as
a real member before production sees it.

## 2. Findings that shaped the design

All verified in the code on 09-30-26.

1. **The calendar payload carries no long-form content.** `GET /api/portal/events`
   shapes each row with `service.public_event` (title, summary, date, time,
   format, location, category, graphic, registration state) and not
   `public_event_detail`, which adds the overview, the syllabus and the join
   link. The member page needs a read of its own (§ 6).
2. **The public per-event read refuses Internal events by design.**
   `GET /api/events/{slug}` goes through `get_by_slug`, which applies the
   public visibility rule and 404s anything not Public. The member page cannot
   read from it; it needs a portal read gated on the portal surface of
   `visibility.is_shown`.
3. **An Internal event's graphic is unreachable today.** `public_image_url`
   points at `/api/events/{slug}/image`, which is keyed on the slug so that it
   inherits the public gate. The rail and the member page would show a broken
   image for every Internal event with a graphic. A portal image route with the
   same short cache lifetime is needed (§ 6).
4. **Internal events may have no slug.** The slug is filled for the public
   programme; crm-test's seeded events carry none. An address built on the slug
   would fail for exactly the events this feature is for. → Decision D1.
5. **The rail cannot say "Registered" from what it receives.** The payload has
   `canRegister` but nothing about the member's own registrations. One extra
   list read of `CEventRegistration` for the events in view, by the member's
   address, supplies it (§ 6). The member's address is already resolved by
   `events.member._member_identity`.
6. **There is no portal cancellation.** The public cancel endpoint takes a
   signed token from the confirmation email. F5-4's Cancel link needs a portal
   endpoint that checks the registration is the member's own and then calls the
   existing `service.cancel_registration`, which frees the seat and promotes
   the waitlist.
7. **The sign-in deep link forwards only exact, listed addresses.**
   `portal/frontend/app.js` `nextTarget` sends a signed-in user on to
   `?next=` only when it equals an entitled application, directory or public
   form address. A member page address in an announcement email would sign the
   member in and then drop them on the home page. The same gap already exists
   for the directory record pages; F5 adds a prefix rule for its own pages
   only (§ 5).
8. **`/portal` is a static mount.** The portal's assets are served by
   `BrandedStaticFiles` at `/portal`, so a `/portal/events/{id}` page route
   must be registered before that mount or it is shadowed. The directory record
   pages (`/directory/{kind}/record/{id}` in `core/app.py`) are the worked
   example: a route that reads the template, renders branding and adds a
   `<base>` tag.
9. **Two width caps stack on the portal.** `.portal` sets
   `max-width: var(--cbm-container-narrow)` (750px) inside `.cbm-container`
   (1200px). Both go for the home view; the sign-in card keeps its own 420px,
   which is a card, not a page.
10. **The `Portal` registration source is in the applied CRM plan**
    (`scripts/plans/cevent-audience-display.json`), so crm-test has it.
    Production gets it with the F2/F3 CRM change (`OPEN-ITEMS.md` #35). Until
    then `register_member` refuses with a message naming the missing option,
    which the rail shows on click rather than hiding the button.
11. **Nothing else on the home page fetches before it renders.** The tiles,
    badges and analytics dashboard all load after the home view is shown and
    fail silently. The rail follows that pattern: a CRM outage never blanks the
    portal.

## 3. The home page layout

Desktop (wider than 767px, the breakpoint the public pages already use):

- The toolbar ("Signed in as … / Sign out") spans the full width, as today.
- Below it a two-column grid: the rail at a fixed 22rem on the left, and a main
  column taking all remaining width, holding Analytics, Directories,
  Applications, CRM, Documentation and Public pages in their present order.
- `.portal`'s width cap and the `.cbm-container` cap are removed for the
  home view (`.portal--home`). The sign-in and reset views are unchanged.
- The tiles grid already uses `auto-fill`, so it packs more tiles per row on a
  wide screen without change — density by packing, per the standing ruling.

Phone (767px and narrower):

- The grid becomes one column. The rail is replaced by the strip at the top of
  the main column: one line, "Next: Mentor Roundtable · Tue Oct 14 · 3 more",
  which is a button. Tapping it expands the full rail in place; tapping the
  line again collapses it. With no events the strip reads "No upcoming
  events". The expanded state is not remembered between visits. *Claude's
  choice*: forgetting is right on a phone, where the strip's purpose is to keep
  the tiles one tap away.

*Claude's choice, open to challenge:* the rail sits under the toolbar rather
than beside it, so "Sign out" stays where every member knows it.

## 4. The rail

**What it lists.** The rows `GET /api/portal/events` returns, in the order it
returns them (soonest first), after the member's two switches are applied in
the browser. The selection itself is F3's and is not changed: Internal events
to the member's teams if limited, plus this chapter's Public events, all shown
and past their display time.

**The window (F5-2).** Every row whose start is within `windowDays` of now is
listed in full. Below them one line, "*N* more events later", expands to list
the rest and reads "Show fewer" while open. The number of days comes from the
server in the response envelope (§ 6), so the setting is one place. The split
is made in the browser from `startsAtUtc`. *Claude's choice*: the server keeps
returning the whole list (bounded already at 1,000 rows) rather than paging,
because the fold is presentation and a second request for "the rest" would
buy nothing.

**A row.** Title, then a line with the date and time, then marks. Nothing
else, by F5-6: the phone strip depends on short rows.

- The date line uses the payload's `day`, `monthShort` and `time`: "Tue 14 Oct
  · 6:00 PM – 7:00 PM". Events with no start read "Date to be confirmed", as
  the public page says.
- Marks: **Public** on a Public event (F3-8: "each Public event marked as
  public"); **Team** on an Internal event limited to teams, with a tooltip
  "Limited to teams you belong to" (the payload's `teamLimited`); **Registered**
  or **Waitlisted** once the member is (finding 5).
- The title is a link to the member page. It opens in a stable named tab,
  `cbm-event-{id}`, so re-clicking a row brings the same tab back, the
  convention the tiles already follow.

**Register in the row (F5-4).** An Internal event with `canRegister` true and
no registration of the member's shows a Register button at the row's right
edge. Clicking it swaps the button for a one-line confirmation inside the row:
"Register for Board Meeting on Thu 23 Oct?" with **Yes** and **No**. Yes calls
`POST /api/portal/events/{id}/register`; the row then reads Registered (or
Waitlisted, from the response) with a **Cancel** link. Cancel asks the same
one-line confirmation and calls the new cancel endpoint. A refusal from either
call (the CRM lacks the Portal option, registration closed, no email on the
account) is shown in the row in the server's own words. The button is never
disabled and never hidden for a permission reason: the server decides and the
row reports.

**The two switches (F5-3).** At the top of the rail, under its heading
"Upcoming events": two checkboxes, **Internal events** and **Public webinars**,
both ticked for a member with no saved preference. A change filters the rows
at once and is saved with `PUT /api/portal/preferences/events.calendar` as
`{"internal": true, "public": false}`. The key is already whitelisted. With
both unticked the rail shows "You have hidden all events. Show them" where
"Show them" re-ticks both. With both ticked and no rows, "No upcoming events".
A failed save keeps the switches as set for this visit and says "Your choice
was not saved" under them.

**When the calendar cannot be read** (the endpoint answers 502 or the fetch
fails) the rail shows "The events calendar is unavailable right now" and the
rest of the portal renders as usual (finding 11).

## 5. The member page — `/portal/events/{id}`

**Route.** A page route in `core/app.py`, registered before the `/portal`
mount, that renders `portal/frontend/event.html` through the branding
substitution — the directory record pages' pattern (finding 8). The page
itself is served to anyone; **the data is not**: its script calls
`GET /api/portal/events/{id}`, and on 401 sends the browser to
`/?next=/portal/events/{id}`, as the directory record page does. The portal's
`nextTarget` gains one rule: a `next` beginning `/portal/events/` is
forwarded. *Claude's choice*: a prefix rule for this app's own same-origin
path only, not a general one, so the redirect target stays one the portal
knows. A signed-in member outside the event's team limit, or asking for an
event that is not shown, gets 404 "That event could not be found" — the same
answer as an unknown id, so the address confirms nothing (design § 5's
reasoning applied to the portal).

**Head.** Title "{event} — {org}", the branding meta tag, no Open Graph tags:
the page is behind sign-in, so no crawler will read it, and the title alone
serves a browser tab and a bookmark. `busy.js` first, then `/shared/footer.js`
last, as on every page.

**Body.** The same body as `events/public_frontend/event.html` — hero graphic,
eyebrow (category · format), title, when-line, summary, facts, overview,
syllabus — under `/shared/tokens.css` and the portal's own styles rather than
the website's stylesheet. *Claude's choice*: the member page is a portal page
and should look like one; F5-1's "same body" is the content and its order,
which the two pages share through one small renderer, `portal/frontend/
event-body.js`, that both `event.js` files call. The public page keeps the
website's look; the sanitising of the wysiwyg fields (`safeHtml`) moves into
the shared renderer so it exists once. A "← Back to the portal" crumb at the
top.

**The action box** replaces the public sign-up form:

- **Internal, takes registrations, open, not registered** — the Register
  button, with the same confirmation as the row.
- **Internal, registered** — "You are registered" (or waitlisted) and a Cancel
  link with confirmation.
- **Internal, registration closed** — "Registration for this event has
  closed", no button.
- **Internal, does not take registrations** — no box; an event everyone is
  simply expected at needs no sign-up.
- **Public** — "This is a public webinar" with two links: **View on the
  website** and **Sign up on the website**, both to the payload's `publicUrl`
  in a new tab (F5-6). With the public pages switched off in this deployment
  (`publicUrl` empty) the box says so instead of offering a dead link.

**The join link.** `virtualMeetingUrl` for an online event, shown as a **Join
online** fact. When it shows is Decision D2.

## 6. The API

Existing, unchanged: `GET /api/portal/events` (the calendar),
`POST /api/portal/events/{id}/register`, `GET`/`PUT
/api/portal/preferences/events.calendar`. All under the organisation-wide key
with the member as the recorded actor (design § 10.1).

Added, all in `events/member.py`, all gated on `visibility.is_shown(event,
"portal", user=user)` after a read by id under the organisation-wide key:

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /api/portal/events` | as today, plus `windowDays` in the envelope and `myRegistration: {id, status}` or `null` on each row | One `CEventRegistration` list read: `eventId` in the returned ids, `email` equals the member's, page size 200 in pages. A failed read leaves `myRegistration` `null` and logs; the row then offers Register, and the server's one-registration rule makes a second click an update, not a duplicate. |
| `GET /api/portal/events/{id}` | `calendar_entry` plus `overview`, `syllabus`, `joinUrl` (subject to D2), `myRegistration` | 404 when not shown to this member. Never exposes the reach or the team list (design § 5). |
| `GET /api/portal/events/{id}/image` | the event graphic | The portal twin of the public image route: keyed on the id, gated on the portal surface, cached for `events_cache_seconds`, never `immutable`, for the same revocability reason. `calendar_entry` rewrites `imageUrl` to this route for every row. |
| `POST /api/portal/events/{id}/cancel` | `{ok, status}` | Finds the member's own registration for the event (by the resolved address), refuses 404 if there is none or it is not theirs, then `service.cancel_registration`. Recorded in the action history as "Event Registration Cancelled". |

The home payload (`GET /api/portal/session`) gains `eventsCalendar: true` when
the switch in § 7 is on and events are active, which is what tells the page to
render the rail at all.

**Guard.** The existing test that fails on any visibility read of
`publishToWebsite` outside `events/visibility.py` covers the new reads, since
they all call `is_shown`. A new test asserts every member endpoint answers 404
for an event the member's teams exclude, with the same body as an unknown id.

## 7. Settings

| Setting | Default | Where | What |
|---|---|---|---|
| `PORTAL_CALENDAR` | `false` | web | Shows the rail and mounts the member page. Off, the portal is exactly today's. |
| `PORTAL_EVENTS_WINDOW_DAYS` | `30` | web | The window (F5-2). `0` means every event is in the fold-out and the rail shows only the line. |

Both are per-request reads, so `/setup` changes them without a restart, and
both appear on the settings page under Events. *Claude's choice on the flag*:
production's events all read as Public until its CRM change lands (they carry
no audience), so on the day this is pushed every published webinar would
appear in every member's rail. That is correct under F3-8 but unreviewed; the
flag lets crm-test show it to a real non-admin member first, per the standing
promotion gate. Rollback is the flag, not a revert.

## 8. Rollout and verification

1. Build dark; suite green; the four guard tests (branding token and meta,
   `busy.js` first, no `datetime-local`, buttons never disabled) extended to
   the new page.
2. Switch on at `/setup` on crm-test. Review as **two real non-admin
   accounts**, one in a team an Internal event is limited to and one not, on a
   desktop and at phone width: the rail, the fold, both switches surviving a
   sign-out and a different browser, Register from a row and from the page,
   Cancel, the member page for an Internal event with a graphic and no slug, a
   Public webinar's two website links, and a deep link to a member page from a
   signed-out browser. Note the nightly reset: registrations made during the
   day are gone by morning.
3. Production after the F2/F3 CRM change (`OPEN-ITEMS.md` #35), which is what
   gives production the audience field and the `Portal` source. Switch on at
   `/setup`. Boston with its next release; its flag off until its staff ask.

## 9. Decisions for Doug

**D1 — The member page's address: the event's id, or its slug.** The id is on
every event and never changes; the slug is filled for the public programme,
often empty on Internal events (finding 4), and staff can edit it, which would
break a link already sent. The slug reads better in an email. *Recommendation:
the id.* Cost: the address is opaque, `/portal/events/68d3…`. A slug address
could be added later as an alias without changing anything stored.

**D2 — Who sees an online Internal event's join link.** Three rules are
possible: every member who can see the event; only registered members, with
the link appearing after Register; or a split — every member when the event
takes no registrations (a team meeting everyone is expected at), registered
members only when it does. *Recommendation: the split.* An event that takes
registrations has a reason to know who is coming, and hiding the link until
then is the only lever the portal has; an event that does not cannot hide the
link from the people it is for. Cost: two behaviours to explain in the staff
guide, one line each.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 09-30-26 14:55 | Claude (Claude Code) | First draft, from the six F5 rulings Doug made on 09-30-26 (Finalization Plan revision 4.11). Eleven findings verified in the code. Two decisions for Doug (D1 address, D2 join link). Awaiting review; nothing built. |
