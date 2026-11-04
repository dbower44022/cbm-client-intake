# Kickoff prompt — Mentor login integrity: prevention, detection, history

Last Updated: 11-03-26 13:33 · Revision 0.2 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, or carry it out in the session that
reviewed it. It carries the findings of the 11-02-26 investigation and Doug's
rulings from the review of revision 0.1, so the design session starts from
evidence rather than reconstructing it.

---

## Kickoff

**Operating mode: DETAIL for the questions, with announced follow-on detail**
(Doug's ruling, 11-02-26). Each design question below stops for Doug's
ruling. Within a ruled question, smaller choices (a setting's name, a log
line's wording) are stated under "Follow-on detail, decided unless you
object" and do not stop. Any follow-on choice that changes what a user sees
or receives — an alert's recipient, a message's wording, who may see a
screen — is put up for a ruling instead. Stopping points: after each
question's ruling, and once more before the plan document is written.

This is a design discussion. **No code, no change to either CRM, and no
change to any record is made in this session.** Read-only checks against
crm-test or production are allowed.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `events/CLAUDE.md`
and `prds/action-history-plan.md`. Open every reply with the local time from
`date`.

**Elicit before drafting.** Doug's requirements come first. Present a draft
only as an explicit strawman, and never record a design decision as made
until Doug has ruled on it. Present each consequential decision with the
consequential decision template in `~/.claude/CLAUDE.md`: the consequence
first, a concrete example from this incident, each option with its strengths
and weaknesses, a recommendation with its cost, then a request to choose.

**Reading production.** The production CRM's roles and settings are read as
an administrator through Doug's Chrome session signed in to the CRM, or by a
read-only script run inside the production application's container
(memory `do-app-console-scripting`). The local `.env` administrator
credential reaches crm-test only.

## Do not repair the affected records — and why a careless repair fails

Doug is waiting for confirmation from Milt Sierra and others before any data
is changed. This session designs the protection only. It does write down a
safe repair procedure for later use (Doug's ruling, 11-02-26, issue 1).

Two pieces of code can put Doug's login back on David Weissman's mentor
profile during a repair. Both are verified by reading the code; the first
was also verified live on crm-test on 11-02-26.

1. **Provisioning, on any Mentor Administration save.** Mentor
   Administration does not show Assigned Users as an editable field — only a
   read-only "Assigned user" line — so the login is never removed there. But
   if the login is cleared in the CRM's own screens, the next Mentor
   Administration save of that mentor profile, on any field and by anyone,
   runs provisioning, because the profile is Active and has no login
   (`mentoradmin/service.py`, `update_mentor`). Provisioning's login-reuse
   guard treats a stored CBM email as proof of ownership and links the User
   whose user name matches it. David's profile stores
   `Doug.Bower@cbmentors.org`. On crm-test, a user-name lookup in any letter
   case found the same User (`Partner.Manager@…` and the all-capitals form
   both matched `partner.manager@…`).
2. **The Update Mentor Status button.** It runs `reconcile_user_links` on
   every mentor, which fills an empty mentor profile login from the first
   login on the mentor's Contact. Since 10-17 David's Contact carries Doug's
   login.

The safe order, to be recorded in the plan document under "Repair procedure —
not part of the build" and in `OPEN-ITEMS.md`:

1. In the CRM's own screens, in **one** save on David Weissman's mentor
   profile, set Assigned Users to David's login and the CBM email field to
   `david.weissman@cbmentors.org`.
2. Remove Doug's login from David Weissman's Contact.
3. Do not use Mentor Administration on that mentor profile until the
   protection ships.

## What happened (verified 11-02-26 against the production CRM)

A mentor profile is a `CMentorProfile` record. Its login is the EspoCRM User
listed in the profile's Assigned Users field (`assignedUsersIds`; the single
`assignedUser` field is disabled in production). The model is one login, one
mentor profile.

- On 10-16-26 at 15:18:48 (CRM time), Milt Sierra's account changed Assigned
  Users on David Weissman's mentor profile (`6a62ca9f5188b9656`). The change
  removed David's own login (`david.weissman@cbmentors.org`, User
  `6a67ae6deca84d2a0`) and added Doug Bower's login
  (`doug.bower@cbmentors.org`, User `6a3b47b5ec0a32190`). The evidence is an
  "Assign" note in the profile's stream.
- The same mentor profile's CBM email field (`cbmEmail`) now reads
  `Doug.Bower@cbmentors.org`. The capital letters suggest it was typed by
  hand. The CRM keeps no history for that field, so who typed it, and where,
  is not known.
- The 10-16 change was made in the CRM's own screens. This is strongly
  supported, not proven. Three facts point to it: Milt's only sign-in that
  day (15:04:07) came from his own connection, while sign-ins through this
  application come from DigitalOcean addresses (the address is in the CRM's
  login records and is deliberately not copied here); Mentor Administration
  has no control that changes a login; and the only application code that
  writes a login onto a mentor profile fills an empty one and cannot remove
  one. The CRM's Action History had already been purged for 10-16 when it was
  read (earliest entry 10-17-26 01:04:55).
- On 10-17-26 at 04:05:22 this application added Doug's login to David
  Weissman's Contact as well (an "Assign" note by the API user
  `customappsproduction`). **The application spread the mistake.** The writer
  is Phase A of `run_stamp_reconciliation` in `assignments/stamps.py`, the
  worker's clean-up job. The evidence is the signing account: that job writes
  under the API key, while `reconcile_user_links` writes under the signed-in
  staff member's own login. The log line from that night was not seen. The
  job runs every 24 hours from the worker's last start
  (`assignment_reconcile_seconds`, default 86400), not at a fixed hour, so
  04:05 says nothing about a schedule.
- The fault was found 17 days later, only because Doug saw the application
  report two mentor profiles on his login. David Weissman's login is active
  but linked to no mentor profile. Nothing alerted anyone.

## What the code does today (verified by reading, 11-02-26)

- **Two mentor profiles on one login: the application guesses.**
  `sessions/service.py`, `resolve_manager_profiles` and
  `choose_manager_profile`: the Active profile wins; if several are Active,
  the first in CRM order wins. A WARNING goes to the web log. Client
  Management tells the signed-in person (`profileChoice`); My Mentor Profile
  uses the same guess and says nothing. Doug's own Client Management and My
  Mentor Profile may therefore be acting on David's mentor profile (not
  checked; the Client Management notice names the profile it acts as).
- **A login with no mentor profile already gets a message.** Client
  Management shows "Your login isn't linked to a profile — ask an
  administrator." My Mentor Profile shows "We couldn't find a mentor profile
  linked to your login. Please contact staff to have your profile
  connected." Nobody on staff is told.
- **The repair code trusts the login it finds.** `mentoradmin/service.py`,
  `reconcile_user_links`, runs on every Mentor Administration save and in the
  Update Mentor Status sweep. It fills an empty login from the Contact's
  first assigned user, and copies the mentor profile's login onto the
  Contact. Phase A of the clean-up job copies the mentor profile's login onto
  the Contact every 24 hours and logs at INFO with no alert. Neither asks
  whether that login sits on another mentor profile or matches the CBM email
  field, and both copy only the **first** login listed
  (`assignments/service.py`, `assigned_user_id`).
- **Provisioning trusts the CBM email field.** The login-reuse guard (see
  "Do not repair" above). `_reserve_cbm_email` checks uniqueness only for an
  address the application picks, not for one a person types. The CBM email
  field is editable in Mentor Administration (`EDITABLE_FIELDS`).
- **Mentor Administration records almost nothing.** Only provisioning writes
  an action history entry (`mentoradmin/router.py`, `_log_provision`). An
  ordinary save, a teams change, the document actions and the Update Mentor
  Status sweep write none. This breaks the standing rule that every mutating
  staff action is recorded through `core/action_log.py`.
- **No history is visible in any application.** The application's action
  history (`CActionLog`) was designed to be read in the CRM's own list view
  (`prds/action-history-plan.md` § 4.2). The CRM's own record history (stream
  notes) is likewise read only in the CRM. Background jobs write no action
  history.
- `core/monitoring.py` already runs periodic checks from the worker
  (`run_alert_check`, `run_schema_drift_check`) and sends to
  `ALERT_EMAIL_TO`. A data-integrity check would have a natural home there.

## Already decided (Doug's rulings, 11-02-26)

These go into the plan as rulings and into the build order. They are not
re-opened.

- **The repair procedure** above is written into the plan and
  `OPEN-ITEMS.md` (issue 1).
- **Every Mentor Administration change is recorded in the action history**,
  as the standing rule requires: saves, teams changes, document actions and
  the Update Mentor Status sweep. This is a defect fix and goes straight into
  the build (issue 4).
- **Background jobs write action history too**, so a change made by the
  clean-up job appears as a structured "System" entry (issue 8a).
- **A change history is shown inside the applications** (issue 8a, option
  C), on five of them: Client Administration, Mentor Administration, Partner
  Management, Funder Management and Event Administration. Partner Management
  and Funder Management share one code path and are built together. Two
  parts, built in this order:
  1. **A History tab on each record** (engagement, mentor profile, partner
     profile, funder profile, event). It merges the application's action
     history and the CRM's own record history, newest first. Each change is
     one line: when (local time), who (a person's name, or "System" and the
     job's name), where (which application, or "in the CRM directly"), and
     what, in one plain sentence. Opening a line shows each field's old and
     new value. Filters: date range, person, kind of change. Left out: record
     ids and raw technical data, who merely viewed a record, email contents,
     passwords and keys.
  2. **An activity page across records**: every change by one person, or in
     one date range, across all records, same line format and filters, with
     an export.
- **Staff notes on mentors, and the page-space work, are a separate plan**
  (issue 8b, option C), started from `prompts/mentor-staff-notes-prompt-v0.1.md`.
  This session does not design them. Two points from that plan touch this
  one: Mentor Administration's roster gets a preview panel, and a new
  internal field, Mentor Status-Admin, writes action history with **no**
  note on the mentor profile, so that a mentor can never read it.

## Questions for the session

Take these in order. Each is a candidate decision, not a settled one.

1. **Scope.** Do partner and funder managers, other Contacts, and the Boston
   and Lakeside chapters get the same login protection, now or later? Ruled
   first so each later ruling is made once for every place it applies.
2. **Detection.** What should a periodic integrity check report? Candidates:
   - one login on more than one mentor profile;
   - a CBM email that differs from the login's user name;
   - one CBM email on more than one mentor profile;
   - an Approved or Active mentor profile with no login;
   - an active mentor login linked to no mentor profile;
   - **at the moment it happens:** a mentor login with no mentor profile
     opened Client Management or My Mentor Profile (folded in from revision
     0.1's question 6; the mentor already sees a message, staff are not
     told).

   Who receives the alert, how often, and does it repeat until the data is
   fixed?
3. **When login data disagrees.** When a login, the User's user name and the
   CBM email field disagree, or one login sits on several mentor profiles,
   does the application guess (as today), stop and alert, or ask the person?
   One principle, ruled once, governing:
   - `reconcile_user_links` and Phase A of the clean-up job;
   - provisioning's login-reuse guard;
   - the two-profile guess in Client Management and My Mentor Profile.
4. **CBM email rules.** Should Mentor Administration refuse a CBM email that
   differs from the login's user name, that another mentor profile holds, or
   that is not lower case? Should the CBM email field lock once a login
   exists?
5. **History: what is kept, and what the applications show.** The display is
   ruled above; this question covers the rest:
   - who may see the History tab and the activity page (Client Management
     shares the Partner / Funder Management code, so mentors would get the
     tab on their engagements unless ruled out). Whatever is ruled, a
     mentor must never see a Mentor Status-Admin entry (staff notes plan);
     check whether any mentor role can read `CActionLog`;
   - the CRM's Action History was purged within about two weeks — what
     retention should the CRM keep, at what cost in database size;
   - should the CBM email field, and the other fields this incident touched,
     be tracked in the CRM's own record history;
   - how long the application's action history is kept.

   Read the live CRM settings before proposing values; the setting names are
   not verified here. Ruled before question 6, because blocking the CRM's own
   screens depends on history being visible elsewhere first.
6. **Prevention in the CRM, together with blocking access to the CRM's own
   screens.** Doug's direction: staff and mentors should never need to sign
   in to the CRM's own screens. How can that be enforced, given that this
   application signs every user in with those same CRM credentials through
   the CRM's interface for programs? Who, if anyone, keeps access to the
   CRM's screens (administrators, the people who fix data by hand), and
   should their roles lose edit access to Assigned Users on
   `CMentorProfile`? Read the roles as an administrator before proposing
   anything, and follow the `espo-crm-changes` skill for any change that is
   drafted.

## What the session produces

A plan document at `prds/mentor-login-integrity-plan.md`. It carries revision
control and a change log, the rulings Doug made with their dates (including
the "Already decided" rulings above), the repair procedure under its own
heading, and a build order in which every change ships dark behind a feature
flag (enabled on crm-test first, then production; root `CLAUDE.md`,
Deployment). Any CRM change gets its own `*-crm-handoff.md` at the repository
root. The open items, including the repair procedure, are added to
`OPEN-ITEMS.md`. The session ends by naming the next step and writing the
kickoff prompt for the build session.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-03-26 13:33 | Claude (Claude Code) | Doug's review of revision 0.1, 11-02-26 to 11-03-26. Staff notes and the page-space work split into their own prompt (issue 8b, option C), with the Mentor Status-Admin constraint carried into question 5. Mode set to DETAIL for the questions with announced follow-on detail (issue 7). Added the repair hazard, verified on crm-test, and the safe repair order (issue 1). Question 6 folded into detection; its premise corrected (issue 2). The 10-17 writer stated as found (issue 3). The Mentor Administration action history gap verified and moved into the build (issue 4). Question 3 widened to "when login data disagrees"; first-login copying and the production read route added (issue 5). Questions reordered: scope, detection, data disagreement, CBM email rules, history, CRM prevention with blocking the CRM's screens (issues 6 and 8a). Added Doug's two issues: blocking direct sign-in to the CRM's screens, and a change history in five applications (issue 8a, option C). Saved as a new file; revision 0.1 stays as it was. |
| 0.1 | 11-02-26 20:24 | Claude (Claude Code) | First draft, from the 11-02-26 investigation of David Weissman's mentor profile. |
