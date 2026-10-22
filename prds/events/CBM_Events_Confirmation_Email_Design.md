# CBM Events — The Registration Confirmation: Design (Track D, D3)

Last Updated: 10-22-26 13:32 · Revision 0.1 — see change log at the end.

**Status: BUILT as v0.277.0 on Doug's instruction to move forward (10-22-26), dark behind
`EVENTS_CONFIRMATIONS` (off). The two rulings that shape it are recorded in
`CBM_Events_Finalization_Plan.md` revisions 4.37 and 4.38 and cited here as
D3-1 and D3-2. The 08-17-26 ruling that CBM sends its own confirmation is in
`CBM_Events_Registration_Recognition_Plan.md`, cited as R-1. Everything else is
Claude's design under the two-part test and is marked where it is a choice.
Nothing has run against a real mailbox or a real Zoom webinar.**

**Terms used here.** A **registration** is a `CEventRegistration` row, made by
the public sign-up (the calendar dialog or the event page), by a member on the
portal, or by staff. The **confirmation** is the email the registrant receives
after registering. The **personal join link** is the web address Zoom issues to
one registrant of one webinar, stored on the registration as `zoomJoinUrl`. The
**shared Join URL** is the event's own `virtualMeetingUrl`. A **ledger** is the
field on the registration that records a send, so it never happens twice. An
**app token** is a `{{name}}` placeholder this application fills after EspoCRM
has rendered its own `{Contact.firstName}`-style placeholders.

---

## 1. What this changes, in one paragraph

A registrant receives exactly one email from CBM at the moment the
registration lands: a confirmation that is the ticket, with the event's date,
time and place, their personal Zoom join link for an online event, a calendar
file, and a cancel link; or a waiting-list note when the event is full; and a
seat-offered email, with the join link, if a cancellation later gives them the
seat. Zoom's own registrant emails are switched off. A public online event
that has no Zoom webinar yet is on no page and takes no registrations, so the
confirmation can never promise a way in that does not exist.

## 2. The rulings and what each one decided

- **R-1 (08-17-26):** CBM sends its own confirmation, built like the five
  follow-ups: an EspoCRM template, the shared info@ identity, a ledger written
  after a successful send, a single-recipient sender rather than the fan-out.
- **D3-1 (10-22-26):** *"We should not be inviting people to an event that does
  not already have a zoom meeting/webinar setup."* The confirmation is the
  ticket; a Public event in an online format is not shown and takes no
  registrations until its Join URL exists. Zoom fills it at publish once Track C
  is on. The hand-pasted link on a Public event (offered as an option) was
  declined.
- **D3-2 (10-22-26):** *"We will not release this to production until the zoom
  integration is tested and active so that we send all emails and not use Zooms
  email confirmations."* One email, ours, carrying the personal join link; Zoom's
  registrant confirmation and its update notifications are off on every
  webinar the application creates; the website is not redirected until Track C
  is tested and active.

## 3. Who gets what, when

| Moment | Kind | Template | Carries | Ledger |
|---|---|---|---|---|
| Delivery of a registration that holds a seat | Confirmation | `EventConfirmation` | when, where, personal join link (online) or venue, calendar file, cancel link, event page | `confirmationSentAt` |
| Delivery of a registration the capacity waitlisted | Waitlisted | `EventWaitlisted` | when, where, cancel link; **no join link, no calendar file** | `confirmationSentAt` |
| A cancellation promotes the longest-waiting person | Seat Offered | `EventSeatOffered` | as Confirmation | `followUpsSent` gains `Seat Offered` |

The three doors feed the same sender: the public sign-up (worker, at
delivery), the portal member registration (web, at save) and the waitlist
promotion inside a cancellation (web). Staff and walk-in registrations do not
send; staff made them with the person present.

**The join link a registrant is sent** (choice): the personal Zoom link first.
An Internal event that takes registrations lends its shared Join URL, because a
registered member already sees it on the member page (Portal Calendar design
D2). A Public online event's shared link is never sent: the personal link is
the ticket.

**A public online registrant with no personal link is not confirmed** (follows
from D3-2): a ticket without a way in is worse than a late ticket. The send is
skipped with the reason "no personal join link yet"; the next delivery attempt
(a redrive from Submission Admin) pushes the registrant to Zoom again and then
confirms. Cost: a Zoom outage at registration time delays the confirmation
until someone redrives; the worker log and Submission Admin show why.

**The waitlist promotion now pushes the person to Zoom first** (follows from
D3-2): until now a promoted person was never registered with Zoom at all,
which did not matter while Zoom's email was the ticket for nobody. The push
is best-effort; on a public online event the Seat Offered email waits for it.

## 4. The template and the app tokens

EspoCRM renders the template (`POST EmailTemplate/{id}/prepare`) with the event
as parent and the registrant's email, so `{CEvent.*}` and `{Contact.*}` resolve
as they do for every other send. The values only this application knows ride as
app tokens, substituted after that render, HTML-escaped in the body:

`{{firstName}}` `{{lastName}}` `{{eventName}}` `{{when}}` (the chapter's own
zone, *Wednesday, October 21, 2026, 12:00 PM – 1:15 PM*) `{{where}}` (the venue,
or *Online*) `{{joinUrl}}` `{{joinBlock}}` (a ready "Join online" paragraph,
empty when there is no link, placed unescaped) `{{cancelUrl}}` `{{eventUrl}}`
`{{recordingUrl}}` `{{orgName}}` `{{orgAbbr}}`.

**The five follow-ups gain the same tokens** (choice): `send_follow_up`
substitutes them per recipient, so the reminder carries *this* person's join
link, which D3-2 requires of every email CBM sends. An unknown token stays
literal, as EspoCRM's own unresolved ones do.

**Staff own the wording.** `scripts/seed_event_templates.py` creates the eight
templates (the three above and the five follow-ups) with plain default wording
once, by exact name, and never touches one that exists. Doug's D1 becomes
"edit the eight", not "write the eight".

## 5. The calendar file

One `VEVENT`, built in `events/ics.py` without a library: UTC times with a
`Z` suffix (what Zoom's own invitations do, so every client converts), the
summary, the venue or the join link as location, the event page as URL, info@
as organizer, RFC 5545 escaping and 75-octet folding. Attached as
`event.ics`, `text/calendar`, through the same attachment path a staff compose
uses. Not attached to the waiting-list note.

## 6. The gate — `events/visibility.py`

`needs_join_link(event)` is true for a Public event in an online format
(Virtual, Hybrid) whose `virtualMeetingUrl` is empty. `is_shown` returns False
for such an event on **both** surfaces (the portal rail hands a Public event to
the public page, which would refuse it); the public `where` clauses add the
same test when the CRM carries the field; the registration form, which runs
`is_shown`, refuses too. Event Administration shows the state **Awaiting join
link** in the Shown column, and a save of such an event warns in plain words.
Internal events are exempt. **No switch**: it is a rule about the event, and
the two webinars on production's calendar today fall under it the day this
ships (accepted by Doug, 10-22-26).

## 7. Zoom

`core/zoom.webinar_settings` sets `registrants_confirmation_email` and
`registrants_email_notification` to false. Webinars created before this
change keep Zoom's emails on until updated; the application has created none
outside tests.

## 8. Settings, switches, components

`EVENTS_CONFIRMATIONS` (off), `/setup` → Features, *Registration confirmation
emails*, read on both components: the worker sends at delivery, the web process
at a member registration and a promotion. Sends also require the follow-ups'
stack: Events on, Gmail sync on, the shared mailbox set, and not dry-run. With
the switch off, every door reports `skipped: confirmation email is not switched
on` and nothing else changes.

## 9. The CRM change

`scripts/plans/cevent-confirmation.json`: the `Seat Offered` option on
`CEventRegistration.followUpsSent`. `confirmationSentAt`, `zoomJoinUrl` and
`zoomRegistrantId` already exist on both CRMs (built with the entity). crm-test
first, production with the next Sunday apply, Boston with its release.

## 10. Rollout and verification

Built dark. Verified by tests (`tests/test_events_confirm.py`) only. The live
pass needs: the eight templates seeded on crm-test, `EVENTS_CONFIRMATIONS` on
there, an in-person test event, a registration with a readable address (the
confirmation with the calendar file arrives; a second registration of the same
person sends nothing), a capacity of one and a second registrant (the
waiting-list note), the first person's cancel link (the second person's Seat
Offered). The online half waits for Track C: a real webinar, Zoom's own email
not received, ours received with the personal link.

## 11. What this leaves open

- The consent write (a ticked consent over an existing `false`), a ruling owed.
- The re-arm and correction links of the recognition plan: the confirmation is
  where they will live; nothing of them is built.
- A registrant who registers again for the same event after the 24-hour hold
  (the orchestrator updates the row) gets no second confirmation; that is the
  ledger, by design.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 10-22-26 13:32 | Claude (Claude Code) | First version, written with the build: rulings R-1, D3-1, D3-2; the three kinds, the app tokens, the calendar file, the gate, Zoom's emails off, the switch, the CRM change, the live pass. |
