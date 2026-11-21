# The Ambassador Program — staff guide

Last Updated: 11-21-26 03:01 · Revision 0.1

How members log what they do to spread the word, what the application does
with each report, and how the program team answers them.

## For members: logging an activity

1. Open **Ambassador Activity** from the portal, or **Log an activity** on
   the home page. On a phone, bookmark the page. If you are not signed in,
   the page asks for your CRM username and password, then shows the form.
2. Say when you did it, and which of the six activities it was.
3. If you talked to someone, type their email address. Anything we already
   know about them fills in, marked as from our records; everything stays
   editable. A change you make is noted for the program team; our records
   are not changed by it.
4. Say who the person is: a potential client, partner or funder, someone
   from an organization we already work with, or someone else. For a
   potential client, partner or funder, say whether they agreed to hear from
   us.
5. Say whether we need to follow up. If yes, say what help you need.
6. Save. The page thanks you and shows a reference.

**My activity**, under the form, lists your reports. You can correct the
date, activity and note for 14 days. A report still being recorded shows
"Saving…".

## What the application does with a report

- **Someone we know at a partner, funder or client** — an *Ambassador
  Contact* session is recorded on that record, and its manager or mentor is
  emailed. It is not a mentoring session: no count of sessions includes it.
- **A new potential client** — a contact (typed Prospect), the company and a
  lead are created, credited to you. When they apply by any route, their
  engagement carries your credit and you are emailed.
- **A new potential partner or funder** — the same, plus a starting record
  in Partner Management (Candidate) or Funder Management (Prospective). When
  the organization applies, that record is used, not a second one.
- **Anyone the application cannot place** — waits on the program team's
  review list.

## For the program team: the review list

**Ambassador Review** (portal tile; the home page's *Ambassador follow-up*
row opens the oldest request) lists:

1. **Follow-up** — act on it, write what was done, and Mark follow-up done.
   The member is emailed your note.
2. **Contact to place** — link it to an existing partner, funder or client's
   engagement (a session is recorded and its manager or mentor told), create
   it as a new referral, or dismiss it with a reason.
3. **Correction** — the member changed something we hold. Change the record
   in its own screen if they are right, then Mark as read.

Every action is recorded in the action history, on the member's mentor
profile.

## Reporting

Analytics → **Ambassador Program**: active ambassadors, activities by type,
open follow-ups, contacts awaiting review, referrals made and applied, and
contacts recorded on known records. Mentor Administration's mentor record
has a read-only **Ambassador** tab.

## Switching it on

The CRM needs `crm-plans/ambassador.json` and
`scripts/migrate_ambassador_roles.py` (`ambassador-activity-crm-handoff.md`).
Then System Settings → Features → **Ambassador Program**. Team gates:
*Ambassador Activity — members* (Mentor Team) and *Ambassador Activity —
program team* (Marketing Admin Team). Switching it off is the rollback.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 03:01 | Claude (Claude Code) | Created with the build (v0.360.0). |
