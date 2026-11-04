# Kickoff prompt — Staff notes on mentors, and the page-space work

Last Updated: 11-03-26 13:33 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`. The design was ruled by Doug on
11-02-26 and 11-03-26, in the session that reviewed the mentor login
integrity prompt (`prompts/mentor-login-integrity-design-prompt-v0.2.md`,
issues 8b and 8c). This session turns those rulings into a plan, then builds
it.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default), with announced
follow-on detail: a smaller choice is stated under "Follow-on detail,
decided unless you object" and does not stop, except a choice that changes
what a user sees or receives, which is put up for Doug's ruling. Present each
consequential decision with the consequential decision template in
`~/.claude/CLAUDE.md`.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read `mentoradmin/CLAUDE.md`, `assignments/CLAUDE.md`,
`mentorprofile/` (its service and frontend), `prompts/record-discussion-pane-prompt.md`
(how the partner and funder discussion was built) and
`prds/mentor-detail-popup-plan.md` (the 09-01-26 view-only ruling). Open
every reply with the local time from `date`.

**Stopping points:**
1. After the plan document is written — Doug approves it before any code.
2. After each build step in the plan's build order, for Doug's review.
3. Before any CRM change, and before the migration script is run anywhere
   with its apply option.

**Process.** The plan document is `prds/mentor-staff-notes-plan.md`, with
revision control, a change log, the rulings below with their dates, and a
build order. Every user-facing change ships dark behind a feature flag
(enabled on crm-test first, then production; root `CLAUDE.md`, Deployment),
except where the plan says otherwise and Doug agrees. Any CRM change gets its
own `*-crm-handoff.md` at the repository root and follows the
`espo-crm-changes` skill. Open items go into `OPEN-ITEMS.md`. Claude commits
locally; Doug reviews and pushes.

## Doug's rulings (11-02-26 and 11-03-26) — build to these

### Three fields about each mentor, for administrators

1. **Mentor Assignment Preferences.** Today's Mentor Status Notes field
   (`CMentorProfile.mentorStatusNotes`), renamed. **Label only**: the stored
   field name stays, so no data moves. The label changes in the CRM and on
   every application screen.
   - It is the **mentor's** field. The mentor writes it, in My Mentor
     Profile, to tell the Client Administration Team their assignment
     preferences. Today My Mentor Profile does not include it (verified
     11-03-26); it is added to `PROFILE_FIELDS`.
   - Mentor Administration keeps editing it.
   - Client Administration shows it **read-only**.
2. **Mentor Status-Admin.** A new internal status about the mentor.
   - Stored in the **application's database**, next to the discussion.
     **Never written to the CRM.**
   - Both the Mentor Administration Team and the Client Administration Team
     can edit it quickly, from the preview panel. Administrators can too.
   - **Never visible to the mentor**, on any screen.
   - It shows who last changed it and when.
   - Each change is recorded in the action history **without a note on the
     mentor profile**. `core/action_log.record_action` posts a note on the
     record, and a mentor can read the notes on their own mentor profile, so
     use `log_action` (the `CActionLog` row only). Check whether any mentor
     role can read `CActionLog`; if one can, the summary text must not carry
     the status, or that grant must go.
3. **Mentor Discussion.** The dated, signed conversation between
   administrators of both teams, about the mentor's status or preferences.
   - Built the same way as the partner and funder discussion: the
     `record_comment` table (`core/store.py`, `add_record_comment` /
     `list_record_comments`), parent `CMentorProfile` and the mentor
     profile's id. Never written to the CRM.
   - Anyone on either team, or an administrator, can read and post on any
     mentor's discussion. Mentors never can.
   - Each comment shows its author's name and the date and time.
   - The discussion is not part of the record's History tab (login
     integrity plan): it is a conversation, not a change to the record.

### Where they appear

- **Mentor Administration's roster** gets a preview panel beside the grid,
  using the shared split-pane component (`frontend/shared/splitpane.js`), as
  Marketing Management does. Clicking a row shows, in this order:
  1. A short summary: name; status and type; CBM email; accepting new
     clients; active, maximum and available clients; the pause dates when a
     pause is set.
  2. Mentor Assignment Preferences.
  3. Mentor Status-Admin (quick edit).
  4. Mentor Discussion.
  5. An "Open full record" link.
  The three fields also appear on the mentor's detail screen.
- **Client Administration's "Available Mentors" chooser** gets the same
  panel beside its grid, inside the pop-up. Clicking a row opens it; clicking
  the mentor's name still opens the full detail pop-up. Mentor Assignment
  Preferences is read-only there; Mentor Status-Admin and Mentor Discussion
  can be edited. Client Administration writes nothing to the mentor profile,
  so the 09-01-26 view-only ruling stands.
- Doug: "We will refine the panel view over time." Build the panel so its
  contents are easy to change.

### Existing data

- **Existing Mentor Status Notes text moves before mentors can see the
  field** (ruling A, 11-03-26). Every existing note is written as an internal
  note. A one-time migration script copies each non-empty note into Mentor
  Status-Admin, then clears the CRM field. Mentors start with blank
  preferences; staff copy back any note that was truly a preference. The
  script is dry-run by default, reports what it would change, and runs on
  crm-test before production. **My Mentor Profile shows the field only after
  the script has run on that deployment.**
- **"Description / notes" is the field every member sees** (ruling C,
  11-03-26). Mentor Administration labels `CMentorProfile.description`
  "Description / notes"; My Mentor Profile calls it "Personal interests", and
  the mentor directory shows it to every member. Relabel it in Mentor
  Administration "Personal interests (shown to members)". Produce a
  read-only listing of its current contents on production for Doug's review.
  Anything he marks as a staff note moves to Mentor Status-Admin in the same
  migration.

### Page space (issue 8c, ruling C)

Doug's rule: every page uses the whole screen and wastes as little space as
possible ("Never cap page width", root `CLAUDE.md`).

1. **Remove Mentor Administration's page cap.**
   `mentoradmin/frontend/styles.css`, line 6:
   `.ma { … max-width: min(1480px, 96vw); }`. It is the only staff page with
   a page-level cap. The shared `.cbm-container` in
   `frontend/shared/tokens.css` caps at 1,200 pixels; every other staff page
   that uses it cancels the cap (`max-width: none` or `100%`).
2. **A guard test** that fails whenever a staff page caps its overall width,
   in the manner of `tests/test_shared_branding.py`. Dialog boxes, sign-in
   cards and the public intake forms (`cbm-container--narrow`) are allowed.
3. **A page-by-page review of wasted space** ("Page space review", a
   separate phase after the notes work): padding, margins and caps on single
   elements across all 12 staff pages (the portal, Client Administration,
   Mentor Administration, My Email, Client / Partner / Funder Management,
   Submission Admin, the directories, Analytics, System Settings, Marketing
   Management, Event Administration). Element caps seen so far include search
   boxes at 22 to 28 rem and Marketing Management's preview pane at 34 rem.
   Some are deliberate. **One page at a time, with Doug's ruling on each.**

Items 1 and 2 ship first, before the preview panel, which needs the width.

## Checks owed before or during the plan

- Can any mentor role read `CActionLog`? (Read the roles as an administrator:
  Doug's Chrome session signed in to the CRM, or a read-only script inside the
  production container; the local `.env` reaches crm-test only.)
- Can the Mentor Role edit `mentorStatusNotes` on the mentor's own mentor
  profile? A field rule can strip the write silently (HTTP 200, nothing
  stored).
- Can the Client Administration Team read `mentorStatusNotes`?
- How many production mentor profiles carry Mentor Status Notes text, and
  what does `description` hold on each?
- On crm-test the application database is wiped every night, so the
  discussion and Mentor Status-Admin start empty each morning there.

## Draft build order (the plan confirms or changes it)

1. Page cap removed, plus the guard test.
2. Storage for Mentor Status-Admin (an Alembic migration), plus the
   Mentor Administration and Client Administration endpoints for the status
   and the discussion, each behind its own team gate.
3. Mentor Administration: the preview panel on the roster, the three fields
   on the detail screen, and the two relabels.
4. Client Administration: the preview panel in the "Available Mentors"
   chooser.
5. The migration script (Mentor Status Notes and the reviewed
   `description` entries into Mentor Status-Admin).
6. CRM label change for Mentor Assignment Preferences (handoff), then the
   field added to My Mentor Profile, after step 5 has run on that deployment.
7. Page space review, page by page.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-03-26 13:33 | Claude (Claude Code) | First draft, from Doug's rulings on issues 8b and 8c in the review of the mentor login integrity prompt, 11-02-26 to 11-03-26. |
