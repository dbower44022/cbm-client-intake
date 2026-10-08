# Event Administration — user guide

The staff tool for CBM's **workshop and webinar programme**: create events, take
registrations, track who actually turned up, and publish the recording. It is
**not** a public form — the public side is the website's Webinars page.

- **URL:** `/events/` (page title **"Event Administration"**).
- **Who can use it:** staff who sign in at the portal and belong to the
  **Marketing Admin Team** (admins always allowed).
- **What it edits:** the `CEvent` record and its `CEventRegistration` records.
- All reads and writes run as the **logged-in staff user**, so EspoCRM enforces
  your permissions and records you as the person who made the change.

> **Read this first, it is the one rule that matters.**
> `CEvent` is also CBM's general calendar entity — it holds internal team
> meetings and copies of mentoring sessions. **Nothing is shown anywhere — the
> website or the portal — unless "Show this event" is ticked.** Once it is, the
> **Audience** decides where it appears (Public: the website and the portal;
> Internal: the portal only), and **Display from** decides when. See *Who sees an
> event, where, and when* below.

---

## The event list

**The list opens on "Needs review" whenever there is anything in it.** That means
events carrying a recording link that are not yet published — exactly what the
YouTube import creates, and nothing else looks like it, so the list can never
open on the internal calendar by mistake. Each one needs its real date (the
import's starting guess is the video's upload date, which is usually wrong), a
topic, and the **Show this event** tick. The count beside the option falls as
you work through them. Once it empties, the list opens on the published
programme as before.

Use the **Show** dropdown to move between Needs review, Shown or scheduled,
Upcoming, Past and All events. Choosing one yourself stops the
automatic switch for the rest of your visit, so a reload will not drag you back.


The landing screen lists events, newest first.

**Show** (top left) chooses what you're looking at:

| Setting | What you see |
|---|---|
| **Shown or scheduled** *(default)* | Every event with "Show this event" ticked — Public, Internal, and those waiting for their display time. This is deliberately the default — otherwise the list opens on the internal calendar entries nobody ticked. |
| **Upcoming** | Everything in the future, published or not. |
| **Past** | Everything that has already happened. |
| **All events** | Everything, including internal meetings. Useful for spotting something wrongly published. |

**Search** (top centre) filters by title, summary, topic, status, format or
location. **Any column heading sorts** — click once, click again to reverse.

Columns: **Event · When · Format · Status · Registered · Attended · Show rate ·
Website · Recording**.

Click a row to open it.

---

## Creating an event

**+ New event** opens a form grouped into sections. The fields that carry
behaviour:

| Field | Why it matters |
|---|---|
| **Title** | Required. Also generates the event's web address, which is then **fixed** — later title edits don't move the URL, so links you've already shared keep working. |
| **Summary** | The short blurb under the title on the website calendar. Keep it to a sentence or two. |
| **Format** | **This is what decides whether a Zoom webinar gets created.** *Virtual* and *Hybrid* get one; *In-Person* does not. |
| **Event type** | Editorial category (Online Webinar / In Person Event / Online Course). Doesn't drive anything. |
| **Topic** | Subject category used by the website's recorded-webinar search. Ten choices, shared with nothing else. |
| **Starts / Duration** | Cleveland time. The website shows the time band from these. |
| **Registration closes** | Leave empty and registration closes when the event starts. |
| **Capacity** | Seat cap. **Leave empty (or 0) for unlimited.** Zero does not mean "full". |
| **Location** | Venue, for in-person and hybrid events. |
| **Full description / Syllabus** | Long-form content for the event's own page. Both are **formatted text** — bold, lists, links and headings work, and there is no need to know any HTML. |
| **Show this event** | The one switch that decides whether the event appears **anywhere**. Off by default. |
| **Audience** | **Public**: the public pages and the portal calendar. **Internal**: the portal calendar only. A new event starts Public. |
| **Reach** *(Public only)* | This chapter, All chapters, or Selected chapters. **Other chapters do not show your events yet** — the reach is recorded now so the shared list can use it later. |
| **Chapters** *(Selected chapters only)* | The chapters named. Your own chapter is always included, even if you untick it. |
| **Limit to teams** *(Internal only)* | Only members of these teams see the event on the portal. Empty means everyone who signs in. **This is not private**: anyone who can read events in the CRM can still find it. Keep genuinely confidential meetings off the calendar. |
| **Takes registrations** *(Internal only)* | Gives members a Register button on the portal. Public events always take registrations through the website. |
| **Display from** | The first moment the event may appear, on any page. Empty means as soon as it is ticked. Registration opens at the same moment. |

Saving creates the event. It does **not** show it and does **not** create a
Zoom webinar until you ask.

## Who sees an event, where, and when

Three controls, read in this order:

1. **Show this event** decides *whether*. Unticked, the event is on no page at
   all — not the website, not the portal. Unticking hides it at once.
2. **Audience** decides *where*. Public events are on the website **and** the
   portal calendar; Internal events are on the portal calendar only, to everyone
   who signs in unless you limit them to teams.
3. **Display from** decides *when*. Before that moment the event is on no page,
   whatever its audience, and nobody can register. Use it to prepare an event
   now and announce it later — or to release a recording on a chosen day.

The **Shown** column in the list reads the result back: *Hidden*, *Appears*
with a date, *Public*, *Internal* or *Internal, limited*.

Events created before these controls existed have no audience set. They read
from the tick: a ticked one is Public, an unticked one Internal. The Overview
says so ("not set — read from Show this event"); saving the event writes it.

Two warnings can appear after a save. Neither stops the save:

- **A display time on an unticked event** — it will not appear at that time
  until you tick "Show this event".
- **A display time after the event starts** on an event that has not happened
  yet — nobody will see it or be able to register before it begins. (After the
  event, this is how a recording is released later, and no warning appears.)

**What members see on the portal.** When the portal calendar is switched on
(System Settings → Features → *Events on the portal home page*), every member's
home page has a list of upcoming events down the left side: Internal events (to
their teams, if you limited them) and this chapter's Public webinars, the next
30 days in full and the rest behind one line. Each opens a page of its own.
An Internal event with **Takes registrations** ticked shows a Register button
in the list and on the page; a Public webinar's page points to the website
instead. **The join link of an online Internal event** shows to everyone when
the event takes no registrations, and only to members who have registered when
it does — so tick Takes registrations if you want to know who is coming before
handing out the link.

**Zoom webinars are for Public events only.** An Internal event never gets one,
even from the Zoom button. Instead, when the audience is Internal the form shows
a **Join URL** box under Place & capacity: paste the meeting link members should
join (Google Meet, your own Zoom room, Teams), and the member page shows it as
**Join online** under the rule above. For a Public event the box is not offered
— Zoom owns that link and would write over anything you typed. An event that
already has a webinar keeps it if you change it to Internal.

**About the form itself.** It opens as a large window sized to your screen, and
you can drag the **bottom-right corner** to make it whatever size suits you. The
**Save** and **Cancel** buttons are pinned to the bottom and stay put — long
forms scroll under them, so the buttons never disappear off the end. On a wide
monitor the panels fill the width in columns rather than stretching one field
across the screen.

---

## Getting a Zoom webinar

**Create / sync Zoom webinar** on the event screen provisions the webinar under
CBM's shared Zoom host and stores the webinar ID and join link on the event.

- Only for *Virtual* and *Hybrid* events.
- Registration is enabled and auto-approved, so people who sign up on the
  website are added to the webinar automatically.
- **Zoom sends its own confirmation email** with each person's unique join
  link — that has to come from Zoom, nobody else can send it.
- **Zoom's reminder emails are switched off** on purpose, so registrants don't
  get two of everything once CBM's own reminders exist.

Afterwards, editing the **title, time, duration or summary** updates the Zoom
webinar too. Changing something Zoom doesn't care about (capacity, topic,
publishing) deliberately leaves it alone — otherwise Zoom emails every
registrant that "the host updated this event".

Setting the event's **Status to Cancelled** cancels the Zoom webinar and tells
registrants. Switching a Virtual event to **In-Person** also cancels it, so
nobody is left holding a link to a room nobody will host.

If Zoom isn't connected yet, the button says so when you click it. It is never
greyed out.

---

## Registrations

### Where they come from

When the website is live, each sign-up creates:

1. a **Contact** in the CRM — matched by email, created as a **Prospect** if new;
2. a **registration record** linked to that Contact and the event;
3. a **Zoom registrant**, so Zoom emails them their join link.

Someone who already exists in the CRM — a client, a mentor, a partner — keeps
the type they already have. Nobody is relabelled "Prospect" for attending a
webinar.

Registering twice with the same address **updates** the existing registration
rather than creating a duplicate.

### The Registrants tab

Everyone signed up for this event, with their status, how they registered, and
minutes attended. Per row you can mark **Attended**, **No-show**, or **Cancel**.

**+ Add registrant** books someone by hand — a phone booking. If you give an
email they get a Contact like any website registrant; without one, the
registration is still recorded.

### Capacity and the waitlist

If an event has a capacity and it's full, further sign-ups are recorded as
**Waitlisted** rather than turned away. A waitlisted person is deliberately
**not** given a Zoom join link, because they don't have a seat.

When someone cancels, the **longest-waiting person is promoted automatically**
and given the seat.

### Cancelling

Registrants can cancel themselves from a link in their email — no login needed.
Staff can cancel from the Registrants tab. Either way the seat is freed, the
person is removed from Zoom, and the waitlist moves up.

---

## Check-in (in-person events)

The **Check-in** tab is built for a phone at the door.

- Type any part of a name to find someone.
- Tap **Check in** — the row turns green and shows **Here ✓**.
- **+ Add walk-in** records someone who wasn't registered and marks them
  attended in one step. Give an email and they become a Contact too, so a
  walk-in is a real lead rather than a name on a list.

The tab stays put after each person, so you can work down a queue without
re-clicking.

Attendance you set by hand is marked as manual and will **not** be overwritten
when automatic Zoom attendance arrives.

---

## The event graphic

On the edit form, under **Content**, there is an **Event graphic** control:
press **Choose image…** and pick a file (the name appears beside the buttons),
then press **Upload graphic**, and it becomes the picture the website shows on
the calendar card and the event page.

Why it matters: without one, a card falls back to the **recording's YouTube
thumbnail** — and an upcoming event has no recording yet, so it would have no
picture at all. If you want an upcoming workshop to look like anything, give it
a graphic.

- JPEG, PNG, WebP or GIF, up to 5 MB.
- **Save a new event first.** The graphic attaches to a specific event, so the
  control asks you to save before it can accept an upload.
- **Remove graphic** takes it off; the card then falls back to the YouTube
  thumbnail if there is a recording, or to no image.
- An uploaded graphic always **wins** over the YouTube thumbnail, including for
  past events — so you can replace an unflattering auto-generated video frame
  with a proper card.
- The image is only reachable publicly while the event is **published**.
  Unpublish it and the picture becomes as unreachable as the page, which is the
  same rule that keeps internal calendar entries off the website.

---

## Presenters

Needs **Presenters on events** switched on (System Settings → Features) and a
CRM that has the presenter record type — until both are true the group below
does not appear.

**Who presents an event, and what the event page says about them.** On a saved
event the form has a **Presenters** group under Sponsorship. Type a name or an
email in the search box to find a person the CRM already knows and click them
to add; a mentor is marked **Mentor**. If the person is not in the CRM, **+ New
presenter** takes a first name, last name, email, title and company, and adds
them — the email is what the CRM is checked against, so a presenter whose email
is already on file is reused rather than duplicated, and a new email creates a
contact typed *Presenter*. A new event has no Presenters group until its first
Save.

**What is copied, once.** Adding a mentor copies their public mentor biography,
their mentor title and their profile photo onto *this event's* presenter entry.
Adding anyone else brings their title and company from their contact record and
leaves the biography and photo empty. From then on the entry is the event's own
text: edit it to fit the talk, and nothing you change here touches the person's
contact record or the mentor's profile. **It is never updated from the profile
afterwards**, and there is no re-copy — a mentor who rewrites their profile
biography next month changes nothing on this page, which is deliberate: a past
event's page is the record of what was presented.

**Edit, photo, order, remove.** **Edit** opens the entry in place: title,
company and the biography in the usual rich-text editor, which has no image
button here because the page's readers cannot reach pictures stored in the CRM.
**Choose photo… / Upload photo** replaces the photo *for this event only* — the
way to give a mentor a more current headshot without touching their profile;
**Remove photo** clears it and the page shows their initials instead. **Up** and
**Down** set the order on the page. **Remove** asks once in the row and then
takes the person off the event; their contact record stays.

**Show presenter biographies** is one tick on the event, in the Publishing
group. Ticked, the event page shows each presenter's biography under their
name; unticked, it shows name, title, company and photo only. To hide one
presenter's biography while showing the others, leave theirs empty.

**Where they appear.** On the public event page and the portal's member page,
between the facts and the full description, one card per presenter with photo
or initials, name, "title · company" and the biography when the tick is on.
The calendar card and the portal rail do not list presenters.

## Publishing the recording

After the event, upload the recording to YouTube yourself, then use **Add
recording** and paste the watch link. The app pulls out the video ID and
thumbnail. The event then appears in the website's recorded-webinar library,
searchable by title, summary and topic.

Clearing the field removes it from the library.

The app deliberately does **not** upload to YouTube for you — nothing gets
published to the CBM channel without a person deciding to.

---

## The Overview tab

**The whole record, read-only, on one screen** — so you can check an event
without opening the editor.

Five figures at a glance — **Registered · Attended · Show rate · Waitlisted ·
Seats left** — then two columns:

- **Left — the facts.** Every field the editor offers, in the editor's own
  groups and order (Event, Schedule, Place & capacity, Publishing, Zoom), plus
  what the app works out from them: the public page address, whether
  registration is open, and the date as the website shows it. An empty field
  shows a dash rather than disappearing.
- **Right — what the website shows.** The event graphic, then the Summary, the
  Full description and the Syllabus, rendered the way the public page renders
  them. An event with no graphic says so here, and the facts column says what
  the website card falls back to.

Every one of the figures is **worked out fresh each time you look**. None of
them is stored, so none of them can drift out of step with reality.

---

## What is not built yet

Being straight about the current state, so you're not hunting for things that
don't exist:

| Not yet | Meaning |
|---|---|
| **The website still points at the old system** | The public programme page is built and live on production — `/webinars/`, with a page per event — but `clevelandbusinessmentors.org/webinars/` has not been redirected to it yet. Until that one redirect is added, this tool and the public page are separate worlds, and every webinar registrant on the live site is still an invisible lead. **Creating an event through this screen is what gives it a web address**, so create events here rather than in the CRM. |
| **Automatic attendance from Zoom** | Built, but switched **off** and never yet run against the real Zoom account. Attendance is manual for now — the Registrants tab and door check-in. |
| **Follow-up emails** | Built, but they need their five email templates created in EspoCRM before anything can send, and there is no button for them in this tool yet. See below. |

---

## Reports

**Reports** on the event list opens two programme-level views for a period
(the last twelve months by default):

- **Programme totals** — events held, unique attendees, total attendances, how
  many people came more than once, and the repeat rate.
- **Attendee → client conversion** — how many attendees later became clients,
  with the list. It counts someone **only if their engagement was created after
  their first attended event** in the period: an existing client who happens to
  attend a webinar is not a conversion, and counting them would flatter the
  programme.

Both are worked out from the registration records each time you ask, so they can
never drift out of step with the records they count.

### Where attendance shows up elsewhere

- **On a person** — the directory Contact page has an **Events** tab listing
  every event they registered for, with what happened and how long they stayed.
  A past event still saying *Registered* means attendance was never resolved,
  which is worth noticing rather than assuming they didn't come.
- **On a client** — a client engagement in Client Management has an **Events**
  tab showing what that client's people have attended, **one row per event**,
  naming who went. Three colleagues at one webinar is one row: the question it
  answers is whether the client engaged with the programme, not how many seats
  were filled.

---

## Follow-up emails — what's needed before they work

The five sends (reminder, recording available, no-show nudge, mentor
call-to-action, feedback survey) are built and go out as the shared
**info@** identity. Before any of them can send, someone has to create five
**email templates in EspoCRM**, named exactly:

`EventReminder` · `EventRecordingAvailable` · `EventNoShow` ·
`EventMentorCTA` · `EventSurvey`

Until a template exists, that send refuses and names the missing template —
it will never improvise an email in CBM's name.

Two rules worth knowing when they do go live:

- **Nobody gets the same email twice.** Each send is recorded on the
  registration, so retries, reruns and second clicks cannot produce a duplicate.
- **Cancelled registrants get nothing**, and the two marketing-flavoured sends
  (mentor call-to-action, survey) go only to people who opted in. The reminder,
  recording and no-show emails are about something the person signed up for, so
  they don't need an opt-in.

---

## Frequently asked

**I created an event but it isn't on the website.**
Check four things: "Show this event" is ticked; the **Audience** is Public;
**Display from** is empty or already past; and the website has been switched
over (see above). The **Shown** column tells you the first three at a glance.

**Why is an internal team meeting in this list?**
Because `CEvent` is CBM's calendar entity as well. Use the **Show** filter —
"Shown or scheduled" hides the unticked ones. If one is wrongly shown, open it
and untick the box.

**Someone registered twice — do I need to delete one?**
No. A repeat sign-up updates the existing registration; you'll only ever have one
per person per event.

**Can I delete an event or a registration?**
No, by design. Events are **Cancelled** and registrations are **Cancelled** —
nothing is destroyed, so the history stays honest.

**The Zoom button did nothing.**
It will have shown a message saying why — most likely Zoom isn't connected yet,
or the event is In-Person.

**Someone turned up who never registered.**
**+ Add walk-in** on the Check-in tab. They're recorded as an attendee and, if
you have their email, become a Contact.
