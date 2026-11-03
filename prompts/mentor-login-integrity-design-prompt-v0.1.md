# Kickoff prompt — Mentor login integrity: prevention, logging and alerting

Last Updated: 11-02-26 20:24 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`. It carries the findings of the
11-02-26 investigation, so the design session starts from evidence rather
than reconstructing it.

---

## Kickoff

Operating mode: ARCHITECTURE. This is a design discussion. No code, no
change to either CRM, and no change to any record is made in this session.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read `mentoradmin/CLAUDE.md` and `sessions/CLAUDE.md`. Open every reply
with the local time from `date`.

**Elicit before drafting.** Doug's requirements come first. Present a draft
only as an explicit strawman, and never record a design decision as made
until Doug has ruled on it. Take one consequential decision at a time, using
the consequential decision template in `~/.claude/CLAUDE.md`.

**Do not repair the affected records.** Doug is waiting for confirmation from
Milt Sierra and others before any data is changed. This session designs the
protection only.

## What happened (verified 11-02-26 against the production CRM)

A mentor profile is a `CMentorProfile` record. Its login is the EspoCRM User
listed in the profile's Assigned Users field (`assignedUsersIds`; the single
`assignedUser` field is disabled in production). The model is one login, one
mentor profile.

- On 10-16-26 at 15:18:48 (CRM time), Milt Sierra changed Assigned Users on
  David Weissman's mentor profile (`6a62ca9f5188b9656`). The change removed
  David's own login (`david.weissman@cbmentors.org`, User
  `6a67ae6deca84d2a0`) and added Doug Bower's login
  (`doug.bower@cbmentors.org`, User `6a3b47b5ec0a32190`). The evidence is an
  "Assign" note in the profile's stream.
- The same mentor profile's CBM email field (`cbmEmail`) now reads
  `Doug.Bower@cbmentors.org`. The capital letters suggest it was typed by
  hand. The CRM keeps no history for that field, so who typed it, and where,
  is not known.
- Milt's only sign-in that day was at 15:04:07 from his own connection (the
  address is in the CRM's login records and is deliberately not copied here). Sign-ins through this application come from DigitalOcean
  addresses. The conclusion is that the edit was made directly in the CRM's
  own interface. This is strongly supported, not proven: the CRM's Action
  History had already been purged for 10-16 by the time it was read
  (earliest entry 10-17-26 01:04:55).
- On 10-17-26 at 04:05:22 this application's own repair added Doug's login
  to David Weissman's Contact as well (an "Assign" note by the API user
  `customappsproduction`). **The application spread the mistake.** It treated
  the wrong login on the mentor profile as true and copied it to the Contact.
- The fault was found 17 days later, and only because Doug saw the
  application report two mentor profiles on his login. David Weissman's own
  login is active but linked to no mentor profile, so David sees no profile
  and no clients. Nothing alerted anyone.

## What the code does today (verified by reading, 11-02-26)

- `sessions/service.py`, `resolve_manager_profiles` and
  `choose_manager_profile`: when one login is on several mentor profiles,
  the Active profile wins. A WARNING is written to the web log, and the
  Client Management grid tells the signed-in person (`profileChoice`). No
  one else is told.
- `mentoradmin/service.py`, `reconcile_user_links`: runs on every Mentor
  Administration save and in the "Update Mentor Status" sweep. It fills an
  empty login from the Contact's first assigned user, and copies the mentor
  profile's login onto the Contact. It never asks whether that login also
  sits on another mentor profile.
- The nightly reconciliation in the worker (the assignment-stamp layer
  described in the root `CLAUDE.md`) is the likely writer of the 10-17
  Contact note. Confirm which code path wrote it before designing around it.
- Mentor Administration lets staff edit the CBM email field (`cbmEmail`,
  in `EDITABLE_FIELDS`). `_reserve_cbm_email` checks uniqueness only for an
  address the application assigns, not for one a person types.
- Mentor Administration provisioning skips a mentor who already has a login,
  and it is the only path that writes an action log entry
  (`mentoradmin/router.py`, `_log_provision`). An ordinary Mentor
  Administration save appears to write none. Verify this. If it is true, it
  breaks the convention that every mutating staff action is recorded through
  `core/action_log.py`.
- `core/monitoring.py` already runs periodic checks from the worker
  (`run_alert_check`, `run_schema_drift_check`) and sends to `ALERT_EMAIL_TO`.
  A data-integrity check would have a natural home there.

## Questions for the session

Take these in order. Each is a candidate decision, not a settled one.

1. **Prevention in the CRM.** Should staff roles lose edit access to Assigned
   Users on `CMentorProfile`, so the link changes only through Mentor
   Administration? What does that cost the people who fix data by hand today?
   Read the roles as an administrator before proposing anything, and follow
   the `espo-crm-changes` skill for any change that is drafted.
2. **Prevention in this application.** Should Mentor Administration refuse a
   CBM email that differs from the login's user name, that another mentor
   profile holds, or that is not lower case? Should the CBM email field become
   read-only once a login exists?
3. **Stop the repair code from spreading a fault.** Should
   `reconcile_user_links` and the nightly reconciliation refuse to copy a
   login that sits on more than one mentor profile, or whose user name
   disagrees with the CBM email, and raise an alert instead?
4. **Detection.** What should a nightly integrity check report? Candidates:
   - one login on more than one mentor profile;
   - a CBM email that differs from the login's user name;
   - one CBM email on more than one mentor profile;
   - an Approved or Active mentor profile with no login;
   - an active mentor login linked to no mentor profile.
   Who receives the alert, how often, and does it repeat until the data is
   fixed?
5. **Logging.** Three gaps:
   - the CRM's Action History was purged within about two weeks;
   - the CRM keeps no history of the CBM email field;
   - ordinary Mentor Administration saves may leave no action log entry.
   What retention period should the CRM keep, at what cost in database size?
   Should the CBM email field be audited? Should every Mentor Administration
   save be recorded? Read the live CRM settings before proposing values; the
   setting names are not verified here.
6. **What the affected mentor sees.** A mentor whose login is linked to no
   mentor profile currently sees an empty screen. Should the application tell
   them who to contact, and should staff be alerted at the same moment?
7. **Scope.** Does the same fault apply to Contacts, to partner and funder
   managers, or to Boston and Lakeside, and should the design cover them now
   or later?

## What the session produces

A plan document at `prds/mentor-login-integrity-plan.md`. It carries revision
control and a change log, the rulings Doug made with their dates, and a build
order in which every change ships dark behind a feature flag (enabled on
crm-test first, then production; root `CLAUDE.md`, Deployment). Any CRM change
gets its own `*-crm-handoff.md` at the repository root. The open items are
added to `OPEN-ITEMS.md`. The session ends by naming the next step and writing
the kickoff prompt for the build session.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-02-26 20:24 | Claude (Claude Code) | First draft, from the 11-02-26 investigation of David Weissman's mentor profile. |
