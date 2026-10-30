# Partner and funder attendance report — plan

Last Updated: 10-30-26 01:08 · Revision 0.3 — change log at the end.

**Status: approved 10-30-26 ("run all stops"); built as v0.301.0; live-passed on crm-test 10-30-26 01:07 (https://claude.ai/artifact/AxWr4jsMPsPgfxvL8yUpgQ).** Decision 3 of
`prds/partner-association-plan.md` is the requirement; this plan is the
report itself (`OPEN-ITEMS.md` #61, item 4).

## 1. The decisions

- **Decision 3 (Doug, 10-28-26):** attendance is reported **by company**,
  the attendee as optional detail; never report someone who did not attend;
  never lose the partner–company tie when a contact is removed.
- **Where (Doug, 10-30-26, option A):** on the partner's and the funder's
  **Events tab**, in Partner Management and Funder Management alike (one
  code path — the two never differ). Staff copy or download it and send it
  themselves. An automatic email to the partner (option C) can be added
  later; it is not in this plan.

Decided here, routinely (Doug may push back on any):

- **Which events:** the events the partner or funder sponsored — the rows
  the Events tab already lists (`events.reporting.sponsor_rollup`).
- **Who:** only registrations marked **Attended**. Registered, No-show and
  Cancelled never appear.
- **Under which company:** the company the person was with when they
  registered (`CEventRegistration.registrationCompany`), else their
  company now (the Contact's account), else none — a person with no
  company is listed by name under *No company on file*.
- **Names:** hidden by default. The Copy text and the download carry names
  only while *Show names* is on.

## 2. What staff get

On the Events tab, each event row gains **Who attended**; above the grid,
**Who attended — all events**. Either opens a panel under the grid:

- the event (or "All events, <first date> to <last date>"), the number of
  companies and of people who attended;
- a grid (the shared grid): **Company**, **Attended** (how many people),
  and, for the all-events view, **Events** (which of the partner's events
  that company attended); with *Show names* on, a **People** column;
- **Copy** — plain text, one company a line, ready to paste into an email;
- **Download (CSV)** — the same rows as a spreadsheet file;
- an empty event says "Nobody was marked as attended at this event."

## 3. How it is built

- **Server:** `events.reporting.sponsor_attendance(client, parent_entity,
  parent_id, link, event_id=None)` → `{events, companies, people,
  rows: [{companyId, company, attended, events: [...], names: [...]}]}`,
  attended registrations only, the company rule above, companies A–Z.
  Route `GET /records/{id}/sponsoredevents/attendance?event=<id>` on the
  sessions router, registered where `sponsored_events_link` is (partner and
  funder). Gate: the user's own read of the parent record, then the
  registrations and companies under the org-wide key — the Events tab's
  rule (no team role reads `CEventRegistration`). An event not linked to
  this partner answers 404.
- **Page:** `sessions/frontend` — the row action, the all-events button,
  the panel, the names switch, Copy and Download (built in the browser from
  the rows; nothing stored).
- **No CRM change; no migration; no switch** — it rides the Events tab,
  which is already feature-detected.

## 4. Stops

Work pauses after each for Doug's go-ahead.

1. **Build** (a subagent, as the grid rollout was; built 10-30-26): the server function and
   route with tests (attended only, the three-step company rule, names,
   the 404), the page, and a check on a local copy.
2. **Review, version, documents** (Claude), then Doug's push.
3. **The live pass** on crm-test: Harrowgate Family Trust's Events tab
   (its *Pricing for Profit* had Brightline Bakehouse attend), with a
   results page.

## Revision control

| Field | Value |
|---|---|
| Document | Partner and funder attendance report — plan |
| Version | 0.3 |
| Last Updated | 10-30-26 01:08 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.3 | 10-30-26 01:08 | Claude (Claude Code) | Live-passed on crm-test. |
| 0.2 | 10-30-26 01:03 | Claude (Claude Code) | Approved; built (v0.301.0). Built-in choices: the company count leaves out *No company on file*; one person at two events counts once per company; a Close button; the CSV starts with a byte-order mark for Excel. |
| 0.1 | 10-30-26 00:52 | Claude (Claude Code) | Drafted from decision 3 and Doug's choice of option A. |
