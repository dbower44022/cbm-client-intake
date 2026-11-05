# Mentor login integrity — prevention, detection and history — Plan

Last Updated: 11-05-26 18:05 · Revision 1.5 — see change log at the end.

**Status:** Approved by Doug 11-05-26 ("approved"). Not built.
**Kickoff that produced it:** `prompts/mentor-login-integrity-design-prompt-v0.2.md`.
**Build kickoff:** `prompts/mentor-login-integrity-build-prompt-v0.2.md` (steps 0–3; steps 4–6 follow in revision 0.3).
**Sibling plan:** staff notes on mentors and the page-space work are a
separate arc, started from `prompts/mentor-staff-notes-prompt-v0.1.md`.

## 1. The problem in one paragraph

On 10-16-26 a staff member's account replaced David Weissman's login with
Doug Bower's on David's mentor profile, in the CRM's own screens. Someone
also typed `Doug.Bower@cbmentors.org` into the profile's CBM email field.
On 10-17-26 this application's clean-up job copied Doug's login onto
David's Contact as well. David could sign in but saw no mentor profile and
no clients. Nobody was told. Doug found it 17 days later by chance. By then
the CRM's Action History for 10-16 had been deleted. The full evidence is
in the design prompt, sections "What happened" and "What the code does
today".

## 2. What this plan does

- **Detects** every login fault within a day and keeps reporting it until
  it is fixed (§ 4.2).
- **Stops the application spreading or acting on a fault** (§ 4.3, § 4.4).
- **Keeps a history staff can read** inside the applications, and keeps
  the CRM's own evidence long enough to investigate (§ 4.5, § 4.6).
- **Does not block the CRM's own screens.** Doug ruled this a training
  matter: detection catches a mistaken edit the next morning (§ 4.7).

## 3. Rulings

All by Doug. Issue numbers are from the prompt review; Q numbers from the
design session.

| # | Date | Ruling |
|---|---|---|
| Issue 1 | 11-02-26 | Write down a safe repair procedure (§ 6); verify the case-insensitive login lookup (done, crm-test). |
| Issue 2 | 11-02-26 | "A mentor with no mentor profile signs in" is a detection trigger, not a screen design. |
| Issue 3 | 11-02-26 | The 10-17 writer is the clean-up job, Phase A of `run_stamp_reconciliation`, stated as found. |
| Issue 4 | 11-02-26 | Every Mentor Administration change is recorded in the action history — a defect fix, straight into the build. |
| Issue 5 | 11-02-26 | Question 3 covers every place that guesses when login data disagrees. |
| Issue 8a | 11-02-26 | A History tab and an activity page in five applications (§ 4.5). |
| Q1 | 11-04-26 | Scope: every mentor profile (partner and funder managers are mentor profiles), Contacts checked as where a fault spreads; Cleveland's crm-test, then production, then Boston after a soak; Boston's CRM changes against EspoCRM 10; Lakeside left out. |
| Q2.1 | 11-04-26 | The check looks for seven conditions (§ 4.2); its first run on production and Boston reports only. |
| Q2.2 | 11-04-26 | Alerts go to a per-chapter address list at `/setup` (falling back to `ALERT_EMAIL_TO`); open faults also show as a badge and a list in Mentor Administration. |
| Q2.3 | 11-04-26 | Daily check, daily digest repeating while a fault is open, staff can acknowledge a fault; the sign-in trigger emails at once. |
| Q3 | 11-04-26 | The three repair paths stop when data disagrees; the two-profile guess is narrowed (§ 4.3). |
| Q4 | 11-04-26 | The CBM email field locks once a login exists, and is checked before then (§ 4.4). |
| Q5.1 | 11-04-26 | The CRM keeps Action History for 30 days. |
| Q5.2 | 11-04-26 | Nine fields become tracked fields (§ 4.6). |
| Q5.3 | 11-04-26 | The History tab is for each application's own team, never mentors; the activity page is gated by a new **System Management Team**. |
| Issue 5b | 11-04-26 | The CRM stops writing a sign-in log row for every request by the application's key-based account. |
| Q6.1 | 11-05-26 | No block on the CRM's own screens for now; training, plus the direct-use report in the daily digest; revisit if direct edits continue. Doug: "This is primarily a training issue, and we may be making it more complex than necessary. Complexity leads to errors." |
| Q6.2 | 11-05-26 | Staff roles keep the right to change a mentor profile's login. |
| Q6.3 | 11-05-26 | Personal Administrator-type logins replace the shared ones for people (§ 4.8). |

## 4. The design

### 4.1 Mentor Administration records every change (issue 4)

Today only provisioning writes an action history entry
(`mentoradmin/router.py`, `_log_provision`). Every mutating Mentor
Administration endpoint gets a `record_action` call at the router layer,
with before and after values: the save (`PUT /mentors/{id}`), the teams
change, the three document actions, and the Update Mentor Status sweep
(one entry per mentor it changed). The background jobs that change records
also write action history (`log_action`, actor "System" plus the job's
name): the clean-up job's Phase A and the team reconciliation first.

### 4.2 The daily integrity check (Q2)

Runs from the worker beside `run_alert_check` in `core/monitoring.py`,
once a day. It reads every mentor profile, its login and its Contact.
Mentor Administration reads logins with the provisioning administrator
account (`ESPO_PROVISION_*`); the build confirms which account the check
uses (owed check C1, § 7).

The seven conditions. "Ignoring case" applies to every address comparison.

1. One login on more than one mentor profile.
2. A CBM email that differs from its login's user name.
3. One CBM email on more than one mentor profile.
4. An Approved or Active mentor profile with no login.
5. An active login on the Mentor, Partner Management or Sponsor Management
   team linked to no mentor profile.
6. A mentor's own Contact carrying a login that is not its mentor profile's
   login.
7. At the moment it happens: a login with no mentor profile opens Client
   Management or My Mentor Profile.

Plus two reports added to the digest by Q6.1 and Q6.3:

8. Direct edits in the CRM's own screens, from the direct-use report
   (`scripts/crm_direct_use_report.sh` is the prototype). Whether this can
   be read through the CRM's programming interface or needs a server-side
   read is owed check C2.
9. Any sign-in to the CRM's own screens by a shared account (`admin`,
   `admin@cbmentors.org`, `mentoradmin@cbmentors.org`).

**First run reports only.** On production and on Boston, the first run
writes a report and sends no alert, so the backlog of existing faults is
known before anyone is emailed.

**Who is told.** A new setting, editable at `/setup`, holds this
chapter's addresses for integrity alerts; empty falls back to
`ALERT_EMAIL_TO`. The Mentor Administration tile's badge counts open faults,
and Mentor Administration gets a fault list naming each fault and its
mentor, with a link to the record.

**How often.** One digest a day lists every open fault, new ones marked,
repeating while any is open. A staff member can acknowledge a fault ("known
— being handled", with a note): it leaves the email and stays in the list,
showing who acknowledged it, when, and the note, and the acknowledgement is
recorded in the action history. Condition 7 emails at once, at most once
per mentor per day. Fault state lives in the application's database, so a
deploy resends nothing; a fault the check no longer finds closes itself.

### 4.3 When login data disagrees (Q3)

**The three repair paths stop and raise a fault** when the data disagrees,
and act normally when it agrees:

- **The clean-up job, Phase A** (`assignments/stamps.py`) copies a mentor
  profile's login onto its Contact only when that login sits on exactly one
  mentor profile and matches that profile's CBM email.
- **`reconcile_user_links`** (`mentoradmin/service.py`) fills an empty
  mentor profile login from the Contact only when the Contact carries
  exactly one login, it sits on no other mentor profile, and it matches the
  CBM email.
- **Provisioning's login-reuse guard** links an existing login found by the
  CBM email only when no other mentor profile carries that login.

**The two-profile guess** (`sessions/service.py`, `choose_manager_profile`)
acts only when exactly one candidate is Active **and** its CBM email matches
the login's user name. Otherwise Client Management and My Mentor Profile
show "Your login is linked to more than one mentor profile — staff have
been told" and no records. A fault is raised either way. Note: until David
Weissman's record is repaired, Doug's own two screens may stop under this
rule (David's status is unchecked, C5).

### 4.4 The CBM email field (Q4)

- **With a login:** read-only in Mentor Administration, showing the login's
  user name, with a line saying why it is locked.
- **Before a login exists:** a typed address is accepted only on the
  chapter's mail domain and when no other mentor profile and no login holds
  it, reusing `_reserve_cbm_email`'s checks; saved in lower case.
- A surname change has no path in the application; an administrator changes
  the login, the Google mailbox and the field together (open item).

### 4.5 History in the applications (issue 8a, Q5.3)

**A History tab** on each record in Client Administration (engagement),
Mentor Administration (mentor profile), Partner Management and Funder
Management (partner and funder profiles, one code path) and Event
Administration (event). It merges the application's action history
(`CActionLog`, read under the application's account, filtered to the
record) with the CRM's own record notes (read as the signed-in person),
newest first. One line per change: when (local time), who (a person, or
"System" and the job), where (which application, or "in the CRM
directly"), and what in one sentence. Opening a line shows each field's old
and new value. Filters: date range, person, kind of change. Never shown:
record ids, raw data, who merely viewed, email contents, passwords and
keys. Visible to each application's own team; **not in Client
Management** (mentors).

**An activity page** across records: every change by one person, or in a
date range, same line format and filters, with an export. Gated by the new
**System Management Team** (setting with the usual `*_ALLOWED_TEAMS`
pattern); Administrator-type logins always pass. The team is named to carry
later functions, such as backup review.

**Mentor Status-Admin** (staff notes plan) writes action history with no
note on the mentor profile, and its entries are shown only to the Mentor
Administration and Client Administration teams.

### 4.6 What the CRM keeps (Q5.1, Q5.2, issue 5b)

- **Action History: 30 days** (`cleanupActionHistoryPeriod`, today
  `15 days`). The clean-up job runs Sundays at 01:01, so today's real
  retention is 15 to 22 days. Production adds about 50 MB a day
  (estimated), so 30 days is about 1.5 GB.
- **Tracked fields** (EspoCRM "Audited"): on the mentor profile `cbmEmail`,
  `mentorStatus`, `mentorType`, `acceptingNewClients`,
  `maximumClientCapacity`, `mentorStatusNotes` (to become Mentor Assignment
  Preferences), `departureDate`; on the partner profile
  `partnershipStatus`; on the funder profile `funderStatus`. Tracked changes
  on these entities are kept forever: the 3-month audit clean-up skips
  entities that have a stream (read in EspoCRM's source, crm-test, 11-04-26).
  A mentor sees tracked changes on their own mentor profile; none of these
  fields is internal.
- **Sign-in log: stop logging the key-based account**
  (`authApiUserLogDisabled = true`, a system setting edited in the server's
  configuration file, not through the API). The application's account wrote
  4,257,677 rows in 7 days against 124 by people; the log is 6.6 GB of the
  8.4 GB database. People's sign-ins stay, for the default 2 months.
- **The application's own action history** (`CActionLog`) is kept
  indefinitely; 638 rows in 0.7 MB today.

### 4.7 The CRM's own screens (Q6.1, Q6.2)

No block. The people in the 11-04-26 direct-use report are trained to use
the applications; the digest's direct-use report shows whether it worked.
Staff roles are unchanged. The block is revisited only if direct edits
continue. Two real gaps were found and go to `OPEN-ITEMS.md` as ordinary
requests: CRM reports (Sharon Rose builds them in the CRM's report builder)
and email templates (Andrew Ciszczon writes them in the CRM).

### 4.8 Shared administrator accounts (Q6.3)

- Each person who administers a chapter's CRM gets a personal
  Administrator-type login.
- `mentoradmin@cbmentors.org` is used only by the application (provisioning)
  and by runbook scripts, never to sign in to the screens.
- `admin` is kept as an emergency login; Doug holds its password.
- `admin@cbmentors.org` stops being used in the CRM; its own job is the
  DigitalOcean and Google sign-ins.
- The digest reports any screen sign-in by a shared account (§ 4.2, item 9).

## 5. Build order

Each step ships dark behind its own feature flag, defaulting off, and is
enabled on crm-test, reviewed as a real non-administrator, then production,
then Boston after a soak (root `CLAUDE.md`, Deployment). Flag names are set
in the build. Each step is one release.

1. **Action history everywhere** (§ 4.1). Not user-facing; no flag needed
   beyond the existing `CActionLog` feature detection.
2. **The repair paths stop on disagreement**, and the narrowed two-profile
   guess (§ 4.3). Do the repair procedure (§ 6) on production first, or the
   narrowed guess may stop Doug's own screens.
3. **The CBM email lock and checks** (§ 4.4).
4. **The integrity check**, in three releases: (a) report only;
   (b) the digest, the address setting, the fault list, the badge and
   acknowledging; (c) the sign-in trigger, the direct-use report and the
   shared-account report.
5. **The History tab**, in Mentor Administration first, then Client
   Administration, Partner and Funder Management, Event Administration.
6. **The activity page** and the System Management Team.

The CRM handoffs (§ 8) are independent of the code and can go first; the
tracked fields should be in place before step 5, so the History tab has
something to show.

## 6. Repair procedure — not part of the build

For David Weissman's record, once Milt Sierra and the others have confirmed.
**Do not use Mentor Administration on this mentor profile until step 2 of
the build ships.** Two traps, both verified: a Mentor Administration save
of a mentor profile with no login runs provisioning, which links the login
whose user name matches the CBM email field (letter case ignored, verified
on crm-test 11-02-26), and that field holds Doug's address; and the Update
Mentor Status button fills an empty login from the Contact's first login,
which is now Doug's.

1. In the CRM's own screens, on David Weissman's mentor profile
   (`6a62ca9f5188b9656`), in **one** save: set Assigned Users to David's
   login (`david.weissman@cbmentors.org`, User `6a67ae6deca84d2a0`) and the
   CBM email field to `david.weissman@cbmentors.org`. (C5, production,
   11-05-26: the field reads `Doug.Bower@cbmentors.org` with capitals —
   letter case is ignored, so the trap stands; David's own link to the
   profile is soft-deleted, not missing, and is re-added by this save.)
2. On David Weissman's Contact, remove Doug's login
   (`doug.bower@cbmentors.org`) from Assigned Users.
3. Check: Doug's Client Management no longer shows the two-profile notice;
   David signs in and sees his mentor profile and clients.

## 7. Checks owed

| # | Check | Where |
|---|---|---|
| C1 | Which account the integrity check reads logins (`User`) with: the application's key-based account, or the provisioning administrator. | crm-test |
| C2 | Whether the direct-use report can be read through the CRM's programming interface (Action History and the sign-in log as an administrator) or needs a server-side read. | crm-test |
| C3 | Production's current tracked fields, so the handoff adds only what is missing. | production, read-only |
| C4 | What Sharon Rose's two User changes were (10-17 to 11-02). | production, read-only |
| C5 | David Weissman's and Doug Bower's mentor profile statuses. | production, read-only |
| C6 | Boston's database and table sizes (`scripts/crm_table_sizes.sh`). | Boston, read-only |
| C7 | A "Data Integrity Team" already exists in the CRM, with its own role (open item #30). Confirm the System Management Team does not duplicate it. | production, read-only |
| C8 | Whether any mentor role can read `CActionLog` (staff notes plan, Mentor Status-Admin). | crm-test and production |

**Results, 11-05-26** (crm-test and production read-only; Boston for C6):

- **C1** — the application's key-based account reads every login with
  every field the seven conditions need (User read all, both CRMs). The
  check runs in the worker under the key; no administrator needed.
- **C2** — Action History and the sign-in log are readable through the
  programming interface as an administrator only (the key reads only its
  own history; the sign-in log is administrator-only). The administrator
  account is on the web component only, so the direct-use report runs from
  web or the worker gains that account — decided at step 4c. People in
  the CRM's screens and people in the applications both sign in as
  `Espo`; only the network address separates them, as in the prototype.
  The configuration account's own reads must be excluded too. Speed of the
  read on production's sign-in log not measured.
- **C3** — production tracks none of the nine fields; all nine exist under
  the handoff's names; `mentorStatusNotes` not yet renamed.
- **C4** — Sharon Rose's two User changes: 10-23-26 Event Manager Role
  given to Gwen Howze; 11-01-26 Sue Marrone moved off Client and Mentor
  Administration. Unrelated to this fault.
- **C5** — David Weissman's profile is Approved, Doug Bower's Active, both
  carrying Doug's login. The narrowed guess picks Doug's (the only Active
  one, its CBM email matching), so Doug's screens keep working.
- **C6** — Boston's database 709 MB; Action History 0.7 MB.
- **C7** — the Data Integrity Team is empty and its role attached to
  nothing. Production also has a **System Administration Team** (2
  members, no role, used as an internal event audience): the System
  Management Team name is put to Doug before step 6.
- **C8** — no mentor, partner or funder role reads `CActionLog` on either
  CRM; only the key's role (and an unattached intake role) does.

## 8. CRM handoffs

- `crm-history-settings-crm-handoff.md` — Action History 30 days; the
  sign-in log switch.
- `mentor-tracked-fields-crm-handoff.md` — the nine tracked fields.
- `system-management-team-crm-handoff.md` — the new team.
- `personal-admin-logins-crm-handoff.md` — personal Administrator-type
  logins and the shared accounts.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.5 | 11-05-26 18:05 | Claude (Claude Code) | Steps 1 and 2 pushed and live (v0.305.0, switches off); step 3 built (v0.306.0), committed, not pushed. No ruling changed. |
| 1.4 | 11-05-26 17:41 | Claude (Claude Code) | Step 2 built (v0.305.0), committed, not pushed; review found a fourth repair path (My Mentor Profile's heal-on-access), now guarded too. No ruling changed. |
| 1.3 | 11-05-26 17:24 | Claude (Claude Code) | Step 0 applied on crm-test; step 1 built (v0.304.0), committed, not pushed. No ruling changed. |
| 1.2 | 11-05-26 12:20 | Claude (Claude Code) | Checks C1–C8 done; results under § 7; two facts added to the § 6 repair procedure. No ruling changed. |
| 1.1 | 11-05-26 12:08 | Claude (Claude Code) | Build kickoff pointer moved to revision 0.2 of the prompt. No ruling changed. |
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the design session of 11-02-26 to 11-05-26. Approved by Doug 11-05-26. |
