# Kickoff prompt — Events, after the production test and the confirmation email

Last Updated: 10-26-26 11:58 · Revision 1.0 — see change log at the end.

Paste this into a fresh Claude Code session rooted in `cbm-client-intake`.
It carries the state of the events arc at the close of the 10-09 to 10-26-26
sessions, so the next session starts working rather than reconstructing.

---

## Kickoff

Operating mode: ARCHITECTURE.

Read `CLAUDE.md` in this repository first and confirm it is the one in force,
then `events/CLAUDE.md`. Then read the memory notes `events-production-test-ruling`
and `events-track-f-state`, and `OPEN-ITEMS.md` #42. Open every reply with the
local time from `date`. Three sessions edit this repository in parallel: read
the version at patch time, stage only your own hunks of a shared file, and
never open a file for writing before you have read it (memory
`patch-scripts-read-before-open-for-write`).

### Where the work stands

Everything is pushed; production reports **v0.289.0** (10-26-26 11:53).

| Piece | State |
|---|---|
| Production end-to-end test (runbook `https://claude.ai/artifact/Dkbb1t7MKFb9vnjabpcyMc`) | **Complete 10-19-26.** The website's seven sessions, twelve recordings and six presenter cards are production's programme; Track F F1 and F4 are on production. |
| Website redirect (Track A, A8) | **Waits** by Doug's rulings: a few weeks (10-09-26), and not until Track C (Zoom) is tested and active (10-22-26, D3-2). |
| Confirmation email (Track D, D3) | **Built v0.277.0, dark** behind `EVENTS_CONFIRMATIONS`. Rulings D3-1 (the confirmation is the ticket; a Public online event without its Join URL is on no page) and D3-2 (one email, ours, with the personal Zoom link; Zoom's registrant emails off). Design `prds/events/CBM_Events_Confirmation_Email_Design.md`. Eight templates seeded on crm-test; `Seat Offered` option applied on crm-test. **Live pass owed** (design § 10). Production: plan, seed script and switch owed at a slot. |
| Follow-up tab (Track D, D2) | **Built v0.283.1, live.** Preview / two-click Send per kind; Emails column on Registrants. Never sent to a real registrant. |
| Consent over false | **Built v0.278.4, live.** A ticked consent or opt-in sets true over a stored false on every public door. |
| Submission Admin search by name | **Built v0.283.1, live.** |
| Duration choices 75 / 90 / 210 min | **Live on both CRMs** (`cevent-duration-options.json`). |
| Track C — Zoom | Never run against real Zoom. Doug: "we will test the zoom integration when done." `webinar_settings` now turns Zoom's registrant emails off. |
| Boston | Owed with its next release: F1, F4, durations, `Seat Offered`, the templates (`scripts/seed_event_templates.py`), `CHAPTER_KEY=boston` first. |

### Doug's open decisions

1. The five-week in-person series: one event (as entered) or one per session (check-in is per event).
2. Whether the Holiday Social should be an Internal event.
3. Data: three mentors' `mentorTitle` is a tagline; Cindie Pacheco's profile has no photo or biography; Get Your Board Fundraising lacks the Industry-Specific topic; the 10-22 AI webinar has none.

### The work, in order

1. **The confirmation's live pass on crm-test, in-person half.** Write the
   runbook page to the 10-17-26 step standard (done boxes, values pre-filled
   from reads): switch `EVENTS_CONFIRMATIONS` on at `/setup`, an in-person test
   event, a registration with a readable address (the confirmation with its
   calendar file arrives; a second registration of the same person sends
   nothing), capacity one plus a second registrant (the waiting-list note),
   the first person's cancel link (the second person's Seat Offered). Verify
   from the container, never from the page.
2. **Track C with real Zoom**, when Doug says: C1 (the Server-to-Server
   application), `scripts/probe_zoom.py`, a test webinar on crm-test, then the
   online half of the confirmation pass: Zoom's own email NOT received, ours
   received with the personal link.
3. **Production**: `cevent-confirmation.json`, the seed script, the switch —
   at a slot, from the web container, with a step page.
4. **Boston** with its release.
5. Then the redirect runbook (`EVENTS-SETUP.md` § 6b) once Doug lifts the hold.

### What the last sessions taught (do not re-learn)

- A known email never makes a second contact: a test registrant with Doug's
  address became Doug. A receipt deleted in the CRM is recreated by the
  hourly sweep. Submission Admin's search did not match names (fixed).
- The Track F production apply sat "owed" for nine days after its page was
  written; read production from the container before believing a page ran.
- A patch helper that opens a file for writing before reading it empties the
  file when its anchor has moved under a parallel session (10-25-26).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-26-26 11:58 | Claude (Claude Code) | Written at the close of the 10-09 to 10-26-26 events sessions. |
