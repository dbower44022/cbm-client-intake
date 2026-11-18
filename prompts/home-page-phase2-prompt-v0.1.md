# Kickoff prompt — the home page, phase 2: Today and My clients

Last Updated: 11-18-26 01:45 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-18-26 at the close of phase 1
(v0.343.0, the page frame; stop 1 passed the same day). Start a fresh
Claude Code session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell
it to read this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number, read `git log`, the working tree's
`pyproject.toml` and the top of `CHANGELOG.md`, and take the next free one;
never take numbers from this prompt. Commit only this phase's files, staged
and committed in one step, then audit with `git show --stat`. If a commit
of another session's appears to carry your lines, say so rather than
re-committing them.

Read, in full, before any code:

- `prds/home-page-plan.md`: the plan. **Rulings 1 to 9 are settled; do not
  re-open them.** This phase builds § 8's phase 2, to § 4.1 (Today, My
  clients) and § 4.4, in the look of § 5.
- `prompts/home-page-mix-mockup.html`: the Today and My clients panels as
  sample data.
- The root `CLAUDE.md`: "Portal + authentication" (the new home page line),
  "Client Management" under Session Management, "Conventions" (busy.js,
  buttons never disabled or hidden, the tokens, **the shared grid**, the
  `CBMDateTime` rule that CRM datetimes are UTC).
- `sessions/CLAUDE.md`: managers are `CMentorProfile` records matched in
  Python; owned and co-mentored engagements; the Next Session column comes
  only from real sessions, never `CEngagement.nextSessionDateTime`.
- `portal/router.py` (`_home_sections`, `_home_payload`),
  `portal/frontend/home.js`, `home.css` and `frontend/shared/panel.css`:
  phase 1's frame, which this phase fills.
- `sessions/service.py`: `resolve_manager_profile_detail`, `list_records`,
  `_attach_sessions_near_now`, `_next_session`, and
  `sessions/config.py`'s mentor `DomainConfig` (its `list_select`,
  `status_values`, `last_contact_attr`). Reuse these; do not write a second
  way to find a mentor's engagements.
- `core/attention.py` and the analytics `ACTIVE_CLIENT_STATUSES` (Active,
  Assigned, Pending Acceptance, On-Hold; Doug's ruling 2026-09-29).
- `OPEN-ITEMS.md` #89.

## Scope of this phase

Fill the Today and My clients frames, still dark behind `HOME_V2`:

1. **One read as the member.** Both sections read the member's own
   engagements and sessions **as the member** (their token, their ACL),
   owned and co-mentored, through the session engine's existing functions.
   A member with no linked mentor profile, or with several that the strict
   rule refuses, sees one plain line saying so, never an error. The read is
   wrapped in `CBMBusy.loading`, and a failure hides only its own section's
   content, with a line, never the page (§ 4.1).
2. **Today**: the member's sessions that start today, by time, each with the
   client's name, the session's name or type, a **Join** button when the
   session has a video meeting link (ruling 1: joining happens in place),
   and **Open**, which opens the engagement in Client Management on its
   Sessions tab in its stable named tab. Under them, one line for the rest
   of the week. With nothing today, one plain line.
3. **My clients**: one row per engagement in an active status: client,
   status as a status pill (§ 5.3 colours, words always shown), last
   contact, next session (from real sessions only). The client's name opens
   the engagement in Client Management. Built on the shared grid
   (`frontend/shared/grid.js`), sortable. A link at the head, **Open Client
   Management**.
4. **The greeting's count**: "N sessions today" joins the date line
   (§ 4.1); the Needs you count waits for phase 3.
5. **Time**: CRM datetimes are UTC. "Today" and "this week" are the
   member's own day in the browser, as Client Management's grid does; the
   server sends a window wide enough for every offset.
6. **Tests**: the endpoint as a mentor, a co-mentor, a member with no
   profile and a member whose read fails; the active-status filter; the
   next session taken from sessions, not the stored field; the switch off
   leaves the endpoint 404 or unused; the branding guard.
7. **Records**: version bump and `CHANGELOG.md`; `OPEN-ITEMS.md` #89; the
   plan's status line and § 8; the root `CLAUDE.md` home page line if the
   new endpoint changes what a later session must know.

Out of scope: Needs you and the no-contact threshold (phase 3), At the
chapter (phase 4), Chapter News (phases 5 to 7), any write from the home
page other than Join (ruling 1).

## Stopping point (a) — before building

Put to Doug, each as one question with options, their costs, and a
recommendation, then stop. Verify each premise against the code or the
test system first.

- **Which statuses My clients lists**: the four of
  `ACTIVE_CLIENT_STATUSES`, or those plus recently closed ones; and the
  pill colour for each (for example Active green, Assigned and Pending
  Acceptance navy, On-Hold amber).
- **Where Open and the client name land**: the engagement's record page in
  Client Management, on which tab, and how the page is told (`?tab=`).
- **When Join appears**: always when there is a link, or only from a set
  time before the start; and what it opens (the link itself, in a new tab).
- **Co-mentored engagements**: listed with the owned ones, marked, or
  listed apart.
- **The endpoint**: one new portal endpoint calling the session engine, or
  the existing Client Management endpoints called from the page. Name what
  each costs in CRM calls per sign-in (the timing log line is the measure).

Show the answers on one rendered screenshot of the two filled frames with
sample data if that settles them faster than words.

## Stopping point (b) — after building

Commit. Then write Doug the check, following his step-by-step instructions
standard (a runbook page if more than three steps): push; switch `HOME_V2`
on at the test system's System Settings (the Business Mentors
Association's); sign in as Joe Mentor, whose six clients have sessions in
the training data, and check Today and My clients against Client
Management's own grid; schedule a session for today in Client Management
and see it appear in Today with Join; sign in as Matt Mentor for the
co-mentor view and as Mark Marketing, who sees neither section; switch
`HOME_V2` off. Production is unaffected while its switch stays off. Raise
the Association's owed baseline re-capture (#87) first: a session made for
the check stays in its CRM. Close the phase only after Doug's check
(plan § 8, stop 2).

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-18-26 01:45 | First draft, written at the close of phase 1. |
