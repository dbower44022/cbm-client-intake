# CBM Events — Presenters: Design (Track F, F4)

Last Updated: 10-08-26 01:09 · Revision 0.3 — see change log at the end.

**Status: BUILT as v0.241.0 on Doug's approval (10-08-26), dark behind
`EVENT_PRESENTERS`; crm-test's CRM side applied and verified the same night;
production and Boston owed (`cevent-presenters-crm-handoff.md`); live pass
owed (`OPEN-ITEMS.md` #39). § 11 records where the build departs from this
design.** The requirements are the eight F4 rulings recorded in
`CBM_Events_Finalization_Plan.md` revision 4.24, section F4 — six are Doug's
(10-07-26 and 10-08-26), two are Claude's under the two-part test. They are
cited below as *F4-n*. What earlier designs settled for the surfaces this one
touches is cited as *design § n* (the F2/F3 audience design) and *F5 § n* (the
Portal Calendar design). Everything else is Claude's design and is marked
where it is a choice. Both decisions in § 10 are ruled (10-08-26) and the design was
approved the same night.

**Terms used here.** A **presenter** is a person who speaks at an event. A
**presenter entry** is the CRM record that joins one event to one presenter and
carries what the event page shows about them; there is one per presenter per
event. The **presenter card** is how one entry renders on an event page. The
**event editor** is the Add/Edit window in Event Administration. The **event
page** means both the public page at `/webinars/{slug}` and the member page at
`/portal/events/{id}`, which share one body renderer (F5 § 5). A **guest** is a
presenter who is not a mentor.

---

## 1. What this changes, in one paragraph

An event gains a list of presenters, managed in a new Presenters group of the
event editor. A presenter is picked from the CRM's Contacts or added on the
spot, and a new email creates the Contact (F4-3). Each presenter entry holds
its own biography, title, company and photo; for a mentor those are copied once
from the mentor profile as a starting point and never refreshed from it
(F4-1, F4-2, F4-6), for a guest they are typed and uploaded. The event page
shows a presenter card per entry — name, title, company, photo, and the
biography when the event's single **Show presenter biographies** switch is on
(F4-4, F4-5) — in the order the administrator set (F4-7). Sponsors are
untouched (F4-8). All of it needs one new CRM record type, so it ships dark
behind a switch **and** CRM feature detection, and lights up on each
deployment the day its CRM has the record type.

## 2. Findings that shaped the design

All verified on crm-test and in the code on 10-08-26 unless marked otherwise.

1. **The CRM has a presenters link and the application has never used it.**
   `CEvent.presenters` ↔ `Contact.cPresenterEvents` (relation
   `cEventPresenters`) is a bare many-to-many: it can hold *who* presents but
   not a biography, a photo or an order. F4-1 needs text per pairing, so the
   feature is built on a **new record type** (§ 3) and the bare link is left in
   place, unused. Removing it is a human decision for a later handoff; the
   application never reads or writes it either way.
2. **The Marketing Admin Role cannot see people or mentors.** Read as the
   configuration administrator: its grants hold `CEvent` (create, read all,
   edit all), `CEventRegistration` (the same) and `CPartnerProfile` /
   `CSponsorProfile` (read all), and **nothing** for `Contact`,
   `CMentorProfile`, `Account` or `Attachment`. F4-3 (add a presenter, create
   the Contact) and F4-5 (copy from the mentor profile) therefore cannot run
   as the signed-in user without a grant change. → Decision D1.
3. **"Presenter" is already a Contact type.** `Contact.cContactType` offers
   `Client, Mentor, Partner, Administrator, Presenter, Donor, Member, Prospect,
   Sponsor`. A guest Contact the editor creates can be typed `Presenter` with
   no CRM change. An existing Contact's type is **not** merged (the standing
   intake rule: a person's type is curated data, null-fill only).
4. **A Contact reaches its mentor profile through `cMentorProfileId`**
   (`Contact.cMentorProfile` ↔ `CMentorProfile.contactRecord`). That is how
   the editor tells a mentor from a guest at the moment of adding: a Contact
   with a mentor profile is a mentor. The mentor profile holds `aboutMentor`
   (wysiwyg, public website text), `mentorTitle` (varchar) and `profilePhoto`
   (an `image` field). The Contact holds `title` (varchar) and `account` (a
   link to the Company); it has **no** image field.
5. **The mentor biography refuses inline images by ruling**, because the
   public mentor page's audience cannot reach the attachment proxy. A
   presenter biography on a public event page has the same audience and the
   same constraint: the shared editor is opened without an `uploadImage` hook,
   so no Insert-image button appears, and the server strips `<img>` on save.
6. **The event graphic is the worked example for an uploaded image.** It is a
   `file` field (`eventGraphicId`), uploaded through its own endpoint (a file
   cannot ride the generic PUT), served through an app proxy keyed on the
   event's slug so that the public gate applies, and — on a new event — the
   editor says "Save the event first, then add its graphic here." The presenter
   photo follows every part of that, including the last: presenters are added
   to a saved event.
7. **The public image route is deliberately not keyed on an attachment id**
   (`events/service.get_published_graphic`): an id-keyed route would serve any
   attachment in the CRM, résumés included. A presenter photo route must be
   keyed on the event (slug publicly, id on the portal) **and** the presenter
   entry, and must check the entry belongs to that event.
8. **The event body is one renderer for two pages.** `frontend/shared/
   event-body.js` fills hero, eyebrow, title, when-line, summary, facts,
   overview and syllabus from element ids both `event.html` files share (F5
   § 5). A presenter section added there appears on both pages with no second
   implementation. Its classes are the pages' own (`pub__*`), not the website
   stylesheet's contract classes, so the class-contract guard tests are not
   involved.
9. **The public detail payload is cached for `events_cache_seconds` (60) and
   served to the world.** Presenters ride inside it, so one read of presenter
   entries per event per minute, and the biography is **omitted** from the
   payload — not merely hidden — when the switch is off, so the page cannot
   leak it.
10. **Sponsors are the pattern for a many-to-many editor, and the wrong pattern
    for this.** `set_event_sponsors` makes a link hold an exact id set on the
    event's Save. A presenter entry is a *record* with text and a photo, saved
    as it is edited, so presenters get their own endpoints and save
    independently of the event form, the way the graphic does (§ 6). What
    sponsors do contribute: the `_relate_or_escalate` shape — the user's edit
    on the event is the real gate — and the live-metadata feature detection
    that keeps a picker dark on a CRM without the link.
11. **F2/F3 fields ride every event read safely.** Selecting an attribute the
    CRM does not have is silently ignored (verified 09-29-26), so
    `showPresenterBios` can join `PUBLIC_SELECT` at once; its *editor* control
    is feature-detected like `audience` and friends (`live_event_fields`).
12. **The applier has not been proven on an `image` field.** Its field table
    lists varchar, text, wysiwyg, enum, multiEnum, bool, int, float,
    currency, date, datetime and url. The plan in § 9 declares the photo as
    `image`; the dry run on crm-test is where that is settled, with a hand step
    in the handoff as the fallback. Role grants are **not** a plan-file
    section; they are a separate merge-only role script, the
    `migrate_client_assignment_role.py` pattern (capability map: roles are
    read-and-write as an administrator, settled 09-07-26).

## 3. The record type — `CEventPresenter`

One record per presenter per event (F4-1). Entity name supplied unprefixed as
`EventPresenter`; EspoCRM stores `CEventPresenter`. Type `Base` — no assigned
user, no teams, no stream: it is content, not a work item.

| Field (stored name) | Type | What it holds |
|---|---|---|
| `name` | varchar (built-in) | The presenter's name at the time of adding, copied from the Contact, so a list of entries reads without a join. |
| `event` | link, many-to-one → `CEvent` | The event. Reverse on `CEvent`: `eventPresenters`. |
| `contact` | link, many-to-one → `Contact` | The person. Reverse on `Contact`: `cPresenterAppearances` (supplied as `presenterAppearances`; the `c` is EspoCRM's, because Contact is not custom). |
| `biography` | wysiwyg | The presenter's biography **for this event** (F4-1, F4-2). No inline images (finding 5). |
| `presenterTitle` | varchar | Shown under the name. See D2 for whether it is a copy or a live mirror. |
| `presenterCompany` | varchar | Shown beside the title. See D2. |
| `photo` | image | The presenter's photo **for this event** (F4-5, F4-6). |
| `displayOrder` | int | Position on the page (F4-7); 1 is first. |

And one field on the event:

| Field | Type | What it holds |
|---|---|---|
| `CEvent.showPresenterBios` | bool, default false | **Show presenter biographies** (F4-4). Off, the page shows name, title, company and photo only. |

*Claude's choices in the shape:* a many-to-one pair rather than a many-to-many
with additional columns, because Entity Manager cannot define relationship
columns and the applier cannot either; `Base` rather than `BasePlus`, because
a presenter entry is never assigned to anyone; `displayOrder` as a plain
integer the application rewrites on every reorder (1..n), rather than a
sparse sequence, because the list is short.

**Deliberately absent:** a per-entry show switch (F4-4 is one per event), any
link from the entry back to the mentor profile (the Contact already has one;
a second path would be a second thing to keep right), and any write to the
mentor profile from this feature (F4-6).

## 4. The event editor

A **Presenters** group in the event form, after Sponsorship, present only when
the live CRM has the record type (§ 7). On an unsaved event it reads "Save the
event first, then add its presenters here." (finding 6).

**The list.** One card per presenter entry in `displayOrder`: photo thumbnail
(or initials in a circle when there is none), name, title · company, a
biography preview of one line, and controls — **Up**, **Down**, **Edit**,
**Remove**. Remove asks a one-line confirmation ("Remove Jane Doe from this
event?") and deletes the entry; the Contact is untouched. Up and Down rewrite
the order of every entry in one request.

**Add a presenter.** A search box under the list: type a name or an email, the
editor lists matching Contacts (name, email, company; a mentor marked
**Mentor**), click one to add. Below the results, **+ New presenter** opens a
small form — first name, last name, email, title, company — and Add. The
server finds a Contact by that email and reuses it, else creates one typed
`Presenter` (F4-3, finding 3). Adding the same person twice is refused with
"Jane Doe is already a presenter on this event."

**What happens on add** (server-side, in one request):

1. The Contact is found or created.
2. If the Contact has a mentor profile (finding 4): `aboutMentor` is copied
   into `biography`, `mentorTitle` into `presenterTitle`, and the profile photo's
   bytes are downloaded and uploaded again as a new Attachment bound to
   `CEventPresenter.photo` (F4-5, F4-6). A copy, never a shared attachment id,
   so the mentor replacing their own photo later changes nothing here (F4-6).
   A mentor with no photo, title or biography leaves that slot empty.
3. If the Contact is a guest: `presenterTitle` from the Contact's `title`,
   `presenterCompany` from its company name, biography and photo empty.
4. `displayOrder` = current count + 1. The entry is saved and the card appears.

Nothing in the application refreshes any copied value afterwards, and there is
no re-copy control (F4-2).

**Edit.** Opens the card in place: title, company, the biography in the shared
CBMRichText editor **without** the Insert-image button (finding 5), and a
**Replace photo** / **Remove photo** control that uploads at once, exactly as
the event graphic does. **Save** writes the text fields; the photo has already
landed. For a mentor presenter this is where the administrator gives the event
a more current photo; the mentor's profile is never written (F4-6).

**The switch.** `showPresenterBios` is an ordinary spec field in the
**Publishing** group, labelled **Show presenter biographies**, help "Off, the
page shows each presenter's name, title, company and photo only. A presenter
with an empty biography shows the same either way." It is feature-detected
like the audience fields and saved with the event form.

**Staff Overview tab.** A **Presenters** facts group listing each entry as
"Jane Doe — Retired CFO" in order, "—" when there are none, under the
Sponsorship group; the Publishing facts gain the switch.

## 5. The event page

**Where.** A `<section class="pub__presenters" id="presenters">` between the
facts list and the overview, filled by `event-body.js` for both pages (finding
8). Hidden when the payload has no presenters. Heading "Presenter" or
"Presenters" by count.

**A card.** Photo (or an initials circle), name, a line with title and company
joined by " · " (either alone when the other is empty, the line absent when
both are), and, when the payload carries a biography, the biography rendered
through the same `safeHtml` sanitiser the overview uses. Cards stack in
`displayOrder`; on a desktop two per row when there are two or more, one per
row on a phone. *Claude's choice*: above the overview, because a visitor
deciding whether to attend reads who is speaking before what the syllabus
says; below the facts, because when and where come first on every page here.

**Styling.** `pub__presenters`, `pub__presenter`, `pub__presenter-photo`,
`pub__presenter-name`, `pub__presenter-role`, `pub__presenter-bio` in
`events/public_frontend/public.css` for the public page and the portal's own
styles for the member page — the pages' own classes, not the website
stylesheet's (finding 8).

**The photo.** `photoUrl` in the payload points at an app route keyed on the
event and the entry (finding 7): publicly
`/api/events/{slug}/presenters/{entryId}/photo`, on the portal
`/api/portal/events/{id}/presenters/{entryId}/photo`. Each resolves the event
first (the public gate or the portal gate), then reads the entry, refuses 404
unless the entry's `eventId` is that event, then streams the attachment with
the graphic route's cache headers (`public` and short-lived on the public
route, `private` on the portal route, F5 § 10.3). `?v=` carries the attachment
id prefix so a replaced photo changes address.

**The calendar card and the rail are unchanged** — presenters are long-form
content; the row stays short (F5 § 4).

## 6. The API

**Public and member reads.** `GET /api/events/{slug}` and
`GET /api/portal/events/{id}` gain `presenters: [...]` in order, each
`{id, name, title, company, photoUrl, biography}`, where `biography` is the
sanitised HTML when `showPresenterBios` is true and `""` otherwise (finding
9). One `CEventPresenter` list read per event (`eventId` equals, ordered by
`displayOrder`, page 200). On a CRM without the record type the key is an
empty list. The two photo routes of § 5.

**Staff endpoints**, all in `events/router.py`, team-gated as the rest of
`/events/api`, each recorded in the action history (`Presenter Added`,
`Presenter Updated`, `Presenter Removed`, `Presenters Reordered`, `Presenter
Photo Set` / `Cleared`):

| Endpoint | Does |
|---|---|
| `GET /events/{id}/presenters` | The entries in order, with `photoUrl` through the staff proxy. |
| `GET /events/presenter-search?q=` | Contacts matching a name or email: `id, name, email, company, isMentor`, at most 20. |
| `POST /events/{id}/presenters` | `{contactId}` or `{firstName, lastName, email, title, company}` — the add of § 4, returning the new entry. 409 for a duplicate. |
| `PUT /events/{id}/presenters/{entryId}` | `{title, company, biography}` — the text fields; the whitelist is the field spec. |
| `PUT /events/{id}/presenters/order` | `{ids: [...]}` — rewrites `displayOrder` 1..n; refuses a set that is not exactly the event's entries. |
| `DELETE /events/{id}/presenters/{entryId}` | Removes the entry. |
| `POST` / `DELETE /events/{id}/presenters/{entryId}/photo` | Base64 JSON upload → Attachment bound to `CEventPresenter.photo`; clear. Same size and type rules as the graphic. |
| `GET /events/{id}/presenters/{entryId}/photo` | The staff proxy, as the user. |

**Who the writes run as** is D1. Under either answer the signed-in user's own
**edit on the event** is checked first, as the sponsors code does, so a member
of the wrong team never reaches the escalated step.

**Guard tests.** The field spec is the whitelist (a smuggled `contactId`
change on PUT is dropped); the add refuses a second entry for the same Contact;
the photo route 404s for an entry on a different event and for an unpublished
event; the public payload carries no biography when the switch is off; the
portal payload passes `is_shown`; the editor source opens the biography editor
without `uploadImage`; the two `event.html` files carry the presenters section
and load the shared renderer first.

## 7. Feature detection and settings

**Detection.** `presenters_available(client)` reads `entityDefs.CEventPresenter`
and confirms `CEvent.links.eventPresenters` points at it; it **fails closed**
(no metadata reader, or a failed read, means unavailable), the grants pattern.
Unavailable: the editor group shows one explanatory line ("Presenters need the
CEventPresenter record type in this CRM — see the Events CRM handoff"), the
public and member payloads carry an empty list, the photo routes 404.
`showPresenterBios` joins the feature-detected editor fields and
`PUBLIC_SELECT` (finding 11).

**Settings.**

| Setting | Default | Where | What |
|---|---|---|---|
| `EVENT_PRESENTERS` | `false` | web | Shows the Presenters group and the page section, mounts the routes' behaviour (present-but-refusing when off, F5 § 10.4). |

Per-request, so `/setup` flips it. *Claude's choice*: a switch as well as
detection, because detection alone would light the feature on every
deployment the moment its CRM change lands, before anyone has reviewed it
there as a real non-admin — the standing promotion gate.

## 8. Rollout and verification

1. **Build dark**; suite green; the guard tests of § 6; the branding, `busy.js`,
   buttons-never-disabled and no-`datetime-local` guards cover the new markup.
2. **crm-test CRM change** with the applier from the plan in § 9: dry run,
   read the plan, apply with `--expect`, read every name back (`CEventPresenter`
   with exactly one `C`; `eventPresenters` on `CEvent`; `cPresenterAppearances`
   on `Contact`; `showPresenterBios` on `CEvent`). Then the role script for the
   grants in D1. Then prove the org-wide key reads `CEventPresenter?maxSize=1`
   (200, not 403) and a real Marketing Admin non-admin can add a presenter.
3. **Switch on at `/setup` on crm-test.** Review as a real Marketing Admin
   member: add a mentor presenter and see the copied biography, title and
   photo; replace the photo and confirm the mentor's profile photo is
   unchanged; add a guest by email and confirm a `Presenter`-typed Contact
   appeared; add the same guest to a second event and confirm no second
   Contact; reorder; remove; the switch on and off against the public page in
   a signed-out browser and the member page as a Mentor Team account; the
   photo route for an unpublished event answers 404. Note the nightly reset.
4. **Production** at the Sunday 17:00 UTC slot: the same plan, the same role
   script, from inside the deployed container; switch on at `/setup`. **Boston**
   with its next release; its switch off until its staff ask.

## 9. The CRM change — plan file and handoff

The plan, kept at `scripts/plans/cevent-presenters.json`, written unprefixed as
the applier requires:

```json
{
  "name": "cevent-presenters",
  "description": "F4 presenters: one record per presenter per event — CBM_Events_Presenters_Design.md",
  "entities": [
    {"name": "EventPresenter", "type": "Base",
     "labelSingular": "Event Presenter", "labelPlural": "Event Presenters", "stream": false}
  ],
  "fields": [
    {"entity": "CEventPresenter", "name": "biography", "type": "wysiwyg", "label": "Biography",
     "tooltipText": "This presenter's biography for this event. Copied once from a mentor's profile; never refreshed."},
    {"entity": "CEventPresenter", "name": "presenterTitle", "type": "varchar", "maxLength": 150, "label": "Title"},
    {"entity": "CEventPresenter", "name": "presenterCompany", "type": "varchar", "maxLength": 150, "label": "Company"},
    {"entity": "CEventPresenter", "name": "photo", "type": "image", "label": "Photo",
     "tooltipText": "This presenter's photo for this event. Copied once from a mentor's profile; never refreshed."},
    {"entity": "CEventPresenter", "name": "displayOrder", "type": "int", "min": 1, "label": "Display order"},
    {"entity": "CEvent", "name": "showPresenterBios", "type": "bool", "default": false,
     "label": "Show presenter biographies",
     "tooltipText": "Off, the event page shows each presenter's name, title, company and photo only."}
  ],
  "links": [
    {"entity": "CEventPresenter", "link": "event", "linkType": "manyToOne",
     "entityForeign": "CEvent", "linkForeign": "eventPresenters",
     "label": "Event", "labelForeign": "Presenters"},
    {"entity": "CEventPresenter", "link": "contact", "linkType": "manyToOne",
     "entityForeign": "Contact", "linkForeign": "presenterAppearances",
     "label": "Presenter", "labelForeign": "Presenter appearances"}
  ]
}
```

Two things the dry run must settle before the handoff is written: whether the
applier accepts `"type": "image"` (finding 12; the fallback is one Entity
Manager step for that field alone, written in the dialog's vocabulary), and
the exact stored name of the Contact-side link (`cPresenterAppearances`
expected). The role grants (D1) are a separate script, merge-only and dry-run
by default. The handoff document, `cevent-presenters-crm-handoff.md`, is
written after the crm-test dry run so it records what actually happened, as
the sponsorship handoff does.

## 10. Decisions for Doug

**D1 — Who the people and mentor reads and the Contact create run as.** The
Marketing Admin Role holds no grant on `Contact` or `CMentorProfile` (finding
2), so today a presenter cannot be searched, copied from or created as the
signed-in user. Two ways to give the feature what F4-3 and F4-5 need:

- *Grant the role.* `Contact`: create yes, read all, edit **no**; `CMentorProfile`:
  read all; `CEventPresenter`: create, read, edit, delete all. The CRM enforces
  it and records the staff member as the Contact's creator. A matched Contact
  is reused **without** null-fill (no edit grant), which for a presenter is
  right: nothing about the person changes because they spoke. Cost: a role
  change on three CRMs (scripted, merge-only), and Marketing Admin members can
  now read every Contact in the CRM — they already read every registration,
  which carries the same emails.
- *Run the reads and the create under the organisation-wide key*, with the
  user's own edit on the event as the gate and the action history as the
  attribution — the Events-tab-counts precedent. Cost: the Contact's creator in
  EspoCRM is the API user, not the person; and a precedent that was made for
  aggregates would now cover a record create.

*Ruled: grant the role* (Doug, 10-08-26, on Claude's recommendation). A
person created by a staff member should say so in the CRM, and the CRM is
the one enforcing the permission. Cost accepted: a merge-only role change on
three CRMs, and Marketing Admin members gaining sight of every Contact. The
grants, as they will be scripted: Marketing Admin Role — `Contact` create yes,
read all, edit no, delete no; `CMentorProfile` read all; `CEventPresenter`
create yes, read all, edit all, delete all. The org-wide API role
(`CustomAppAPIRole`) — `CEventPresenter` read all, for the public pages. Every
presenter read and write in § 6 runs **as the signed-in user**; the master key
is used for the public and member page reads only, as every other public read
is.

**D2 — Title and company: static copies on the entry, or live from the
Contact.** F4-5 says they "come from the Contact". Read live, a Contact's new
job title flows onto every past event page, which is the behaviour F4-2 and
F4-6 rejected for the biography and the photo; copied once into
`presenterTitle` / `presenterCompany` at adding time and editable per event,
they behave exactly as the other two. The record type in § 3 is drawn with the
copies.

*Ruled: static copies* (Doug, 10-08-26, on Claude's recommendation), for
consistency with F4-2 and F4-6 and so the page is the record of what was
presented. Cost accepted: a title that changes before the event has to be
corrected on the entry by hand, like the biography; and two more fields on
the record type. The record type in § 3 and the plan in § 9 stand as drawn.

## 11. As built — where the build departs from this design

Each is Claude's decision during the build, open to challenge.

1. **The presenter cards have one shared stylesheet**,
   `frontend/shared/event-body.css`, loaded by both event pages, rather than
   rules in `public.css` and the portal's styles (§ 5 said per page). One set
   of rules for one renderer; tokens only, so a chapter's colours apply.
2. **The search route is `/events/api/presenters/search`**, not
   `/events/presenter-search`: anything under `/events/` after the event
   routes would be captured by `/events/{{id}}`.
3. **`GET /fields` reports `presenters: {{enabled, available}}`**, two facts not
   one, so the editor can tell "switched off" (no group) from "this CRM lacks
   the record type" (one explanatory line). The staff event payload carries
   `presenters: null` in either of those cases and a list otherwise.
4. **A mentor profile the user cannot read still adds the presenter**, with
   the Contact's own title and an empty biography, logged. The copy is a
   starting point, not the record; refusing the add for it would be wrong.
5. **A new presenter's company is stored on the entry only.** No Account is
   created or linked from the events editor; D2 made the entry's copy the
   fact the page shows, and creating companies belongs to the quick-add doors.
6. **The role script writes an explicit `no`** for the actions it does not
   grant on a scope that was wholly absent, so the stored map is complete and
   reads unambiguously as "create yes, read all, edit no, delete no".
7. **The applier handled the `image` field** without a hand step (finding 12
   settled on the first dry run): `Admin/fieldManager` accepts the type as
   given, and the read-back verified it.
8. **Removing a presenter asks its one-line confirmation in the card's own
   action row** (Yes / No), the portal rail's pattern, rather than a dialog.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.4 | 10-08-26 01:26 | Claude (Claude Code) | Approved by Doug and built as v0.241.0, dark behind `EVENT_PRESENTERS`. crm-test CRM change and role grants applied and verified; production and Boston owed. § 11 added: eight places the build departs from the design. |
| 0.3 | 10-08-26 01:09 | Claude (Claude Code) | D2 ruled by Doug: title and company are static copies on the presenter entry. Both decisions ruled; awaiting approval to build. |
| 0.2 | 10-08-26 00:55 | Claude (Claude Code) | D1 ruled by Doug: widen the Marketing Admin Role (Contact create + read, mentor profile read, CEventPresenter all) rather than use the org-wide key; the exact grants recorded. D2 open. |
| 0.1 | 10-08-26 00:39 | Claude (Claude Code) | First draft, from the eight F4 requirements in the Finalization Plan revision 4.24. Twelve findings verified on crm-test and in the code (notably: the Marketing Admin Role has no Contact or mentor-profile grant; "Presenter" is already a Contact type; the applier is unproven on `image` fields). New record type `CEventPresenter` drawn in § 3, plan file in § 9. Two decisions for Doug (D1 grants, D2 title/company copies). Awaiting review; nothing built. |
