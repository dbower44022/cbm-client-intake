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
> meetings and copies of mentoring sessions. **A single checkbox, "Publish to
> website", is what separates a public workshop from an internal meeting.**
> Nothing reaches the website unless that box is ticked. Leave it off for
> anything that isn't a public event.

---

## The event list

The landing screen lists events, newest first.

**Show** (top left) chooses what you're looking at:

| Setting | What you see |
|---|---|
| **Published to the website** *(default)* | Just the public workshop programme. This is deliberately the default — otherwise the list opens on ~90 internal calendar entries. |
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
| **Publish to website** | The gate described above. Off by default. |

Saving creates the event. It does **not** publish it and does **not** create a
Zoom webinar until you ask.

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

Five figures at a glance — **Registered · Attended · Show rate · Waitlisted ·
Seats left** — then the event's facts, its public page address, Zoom details and
recording link.

Every one of those numbers is **worked out fresh each time you look**. None of
them is stored, so none of them can drift out of step with reality.

---

## What is not built yet

Being straight about the current state, so you're not hunting for things that
don't exist:

| Not yet | Meaning |
|---|---|
| **The website still runs on the old system** | Events you create here are not yet visible on clevelandbusinessmentors.org. Until the website change ships, this tool and the public page are separate worlds. The app warns you about this at the top of the screen. **This is the only phase still unbuilt, and it is the one that matters** — until it ships, every webinar registrant on the live site is still an invisible lead. |
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
Two possible reasons: "Publish to website" isn't ticked, or the website hasn't
been switched over yet (see above). The Overview tab tells you which.

**Why is an internal team meeting in this list?**
Because `CEvent` is CBM's calendar entity as well. Use the **Show** filter —
"Published to the website" hides them. If one is wrongly published, open it and
untick the box.

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
