# Course plan — the events marketing manager

Last Updated: 11-04-26 10:22 · Revision 1.2 — see change log at the end.

**Approved 11-04-26.** Module 1 is built; the development Artifact is
https://claude.ai/artifact/T1DhFMnfVwxAHfggAXS83b

The first training programme for this application. Audience, form and delivery
surface are Doug's, 10-30-26 and 11-04-26; everything else here is a draft.

## What this is

An interactive course for **the events marketing manager** — the person who
creates an event, markets it, runs its delivery, and follows it up. Each module
is **slides that explain the process, then video walkthroughs that show how to
execute each step**.

The course spans **two applications**: Event Administration (`/events`) and
Marketing Management (`/campaigns`). That is not a quirk of the course, it is
the job.

## Doug's rulings behind it

- 10-30-26 — the training programmes live in this repository, not a separate
  project folder.
- 11-04-26 — **Artifact during development; a page in the application once it
  is mature.** Both surfaces, in that order.
- 11-04-26 — audience and form, as above.
- 11-04-26 — **not a learning management system course.** CBM runs no learning
  management system today and this course carries no completion record, so it
  is reference material for one role. Authoring stays here. Note that CBM's own
  business requirements do specify one for *mentor* training, writing
  completion back to the mentor's Contact (`MR-ONBOARD-REQ-002` in the
  `ClevelandBusinessMentors` repository) — if that is ever stood up, this
  course exports into it from the content file rather than being re-authored.
- 11-04-26 — **screenshots carry the explanatory weight, not per-step clips.**
  One walkthrough per module stays the video; a slide that names a control gets
  a screenshot, and nothing gets a decorative one.

## Assumption I am working under

Module 2 is written now and **recorded later** — its screens are dark behind
`EVENT_PROMOTE`, `CAMPAIGN_SEND_REPORT`, `CAMPAIGN_LIST_SCREENS` and
`CALLS_PANEL`, M10's live pass is owed, and every campaign switch is off on
production. Modules 1, 3, 4 and 5 are written and recorded against crm-test
now. Say otherwise and I will reorder.

## The two surfaces, and what makes the second one cheap

The Artifact is the delivery surface during development. The application page
is where it ends up. The move is cheap only if the content is **data, not a
page**, so:

- **One content file holds the whole course** — modules, and per module its
  slides (title, body, notes) and its videos (title, what it shows, URL). The
  Artifact page is a thin player over that file; the future application page
  renders the same file. Moving the course re-renders the data and rewrites no
  content.
- **The organisation's name is never typed** — `{{org}}` and `{{abbr}}` from
  the first slide. `tests/test_shared_branding.py` fails on a hardcoded name
  the moment this becomes a served page, and retrofitting it across a finished
  course is tedious and error-prone.
- **No page-width cap**, per the standing rule.
- **Progress is per-viewer and disposable** — the browser's own storage in the
  Artifact, wrapped so a refusal renders the course anyway. The application
  page would keep progress in the app's database instead; nothing in the
  content depends on which.
- Colours come from the CBM design tokens' own names, so the application move
  inherits chapter theming rather than fighting it.

**The Artifact cannot embed video.** An Artifact page may not embed an iframe
of any other site, so there is no video player on it: a recorded walkthrough is
a link that opens in a new tab. The application page can embed the player
properly when the course moves in, which is one more thing the second surface
buys. The content file already carries each video's URL, so nothing changes in
the content when the player gains the ability to embed it.

When the course graduates into the application it becomes a feature arc with a
plan of its own in `prds/`. This document stays the course's plan.

## Proposed layout

```
training/events-marketing-manager/
  PLAN.md                        this document
  course/
    index.html                   the player — published as the Artifact
    course.js                    the content: modules, slides, videos
    styles.css
  recording-scripts/
    module-1-create.md           one file per module
    ...
```

**The recording scripts are the deliverable you act on.** I cannot record
video. Each script names the sign-in, the screen, every click and what to say,
written to the Step-by-Step Instructions standard — one action per step, exact
locations, every value written out in full.

Two conditions each script states in its "Before you start" block:

- **Record as a real non-admin in the audience's own teams**, never as an
  administrator. An administrator bypasses ACL and sees a different
  application, so an admin recording teaches screens the room will never meet.
  Module 2 needs **both** the events team and the campaigns team — the promote
  path checks for both.
- **Record a module in one sitting.** The sandbox reverts every night, so an
  event created for a walkthrough is gone by morning and a half-recorded module
  starts again from the beginning.

## The five modules

### Module 1 — Create the event
*Live, and `event-administration.md` documents it.*

Slides:
- Why an event is created here and not in the CRM — this screen is what gives
  it a web address.
- The fields that carry behaviour: **Title** fixes the web address for good,
  **Format** is what decides whether a Zoom webinar gets created, **Capacity**
  empty means unlimited and 0 does not mean full.
- Three separate questions, not one: **Show this event** decides whether,
  **Audience** decides where, **Display from** decides when.
- Reach and chapters — recorded now, other chapters do not show your events
  yet.
- **Limit to teams is not privacy.** Anyone who can read events in the CRM can
  still find the event; genuinely confidential meetings stay off the calendar.

Videos:
1. Create a virtual public webinar, end to end, and get its Zoom webinar.
2. Create an in-person internal event and limit it to teams.
3. The event graphic and the presenters.

### Module 2 — Market the event
*Written now, recorded when the flags are on. Needs both the events team and
the campaigns team.*

Slides:
- What **Promote this event** does: one Draft campaign per ticked channel,
  through the same path as + New campaign, each linked to the event, each
  carrying a link that opens the event's page, each sent to the list chosen
  for it.
- The four channels — Email, Text, Postcard, Calls — and that the first three
  are ticked to start.
- **What stays manual:** building and signing off, campaign by campaign.
  Promote makes Drafts, it does not send anything.
- What credits a registration to a campaign: the public form writes it **on
  the create, once**. Nothing afterwards re-decides it, which is why the
  roll-up can be trusted and why a late campaign cannot steal a registration.

Videos:
1. Promote an event, and see the Drafts it made.
2. Build and sign off the email campaign.
3. Read the send report — opens and clicks.

### Module 3 — Run the delivery
*Live, except the registrant emails, which sit behind a System Settings switch.*

Slides:
- Where registrations come from, and the Registrants tab.
- Capacity, the waitlist, and offering a freed seat.
- Cancelling, and what cancelling does to the Zoom webinar.
- The registrant's three emails and the five follow-ups — eight templates in
  the CRM, the wording yours to change at any time.
- **A missing template refuses the send and names itself.** The application
  will never improvise an email in the organisation's name.
- **Nobody gets the same email twice**, and cancelled registrants get nothing.

Videos:
1. The Registrants tab, and adding a registration by hand.
2. The waitlist, and a cancellation freeing a seat.
3. Check-in at an in-person event.

### Module 4 — Follow up
Slides:
- The five follow-ups and who gets which.
- The two marketing-flavoured sends — the mentor call to action and the survey
  — go only to people who opted in. The reminder, recording and no-show emails
  are about something the person signed up for, so they need no opt-in.
- Publishing the recording.

Videos:
1. Preview and send a follow-up.
2. Publish the recording.

### Module 5 — See what it did
Slides:
- Attendance, and where it shows up elsewhere.
- The programme and conversion reports. **Conversion counts an attendee only
  when their engagement postdates their first attended event** — otherwise a
  client who happened to attend would read as a win the event did not earn.
- The event's Campaigns tab: Reached, Registered, Attended, the "not linked"
  row and the *No campaign* row.

Videos:
1. Read the reports.
2. Read the event's Campaigns tab.

## Two defects the course must not inherit

1. **`event-administration.md` contradicts itself on the registrant's
   confirmation email.** The Zoom section says Zoom sends its own confirmation
   with each person's unique join link; the follow-up section says Zoom's own
   confirmation emails are switched off and the application's is the only email
   a registrant receives. The second is right — it is ruling D3-2. The Zoom
   section is stale and should be corrected before module 3 quotes either.
2. **There is no Marketing Management user guide.** Module 2's slides have no
   user-facing source; they have to be written out of `campaigns/CLAUDE.md` and
   `prds/prospect-marketing/rulings.md`. That content is most of a guide, so
   module 2 should produce `marketing-management.md` as a by-product rather
   than leave the only plain-language account of that application inside a
   course.

## Stopping points

DETAIL mode, so this plan names where work pauses for Doug.

1. **This plan.** Nothing is built until it is approved.
2. **After module 1** — the player, the content file, module 1's slides and its
   three recording scripts. Reviewed before anything else is written, because
   the player and the content shape are settled by it.
3. **After modules 3, 4 and 5.** Reviewed, then published as the Artifact.
4. **Module 2** only once `EVENT_PROMOTE` is on and M10 has had its live pass.

Between two stopping points I work without asking.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 11-04-26 10:22 | Claude (Claude Code) | Doug's two rulings of 11-04-26 recorded: no learning management system and no completion record, so authoring stays here; and screenshots rather than per-step clips. Module 1's seven slides each gained a screenshot, the player renders one and names the file when it is missing, and `recording-scripts/screenshot-capture-list.md` says how to capture them. |
| 1.1 | 11-04-26 01:10 | Claude (Claude Code) | Approved by Doug 11-04-26 and module 1 built: the player, the content file, module 1's seven slides and its three recording scripts, published as the development Artifact. Added the finding that an Artifact cannot embed an iframe, so a walkthrough is a link out until the course moves into the application. |
| 1.0 | 11-04-26 00:42 | Claude (Claude Code) | Created for approval. Audience and form from Doug 11-04-26; the Artifact-then-application surface ruling the same day. Five modules mapped against the application as built, the dark marketing middle held for recording, the content-as-data architecture that makes the application move cheap, and the two documentation defects found while mapping. |
