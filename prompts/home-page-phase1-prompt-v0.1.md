# Kickoff prompt — the home page, phase 1: the page frame

Last Updated: 11-17-26 02:30 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-17-26 at the close of phase 0
(v0.340.3, the contrast fix to the design tokens). Start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read this
file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number or an `OPEN-ITEMS.md` number, read `git log`, the
working tree's `pyproject.toml` and the top of `OPEN-ITEMS.md`, and take the
next free one; never take numbers from this prompt. Commit only this phase's
lines, staged and committed in one step, then audit with `git show --stat`.

Read, in full, before any code:

- `prds/home-page-plan.md`: the plan. **Its rulings 1 to 9 are settled; do
  not re-open them.** This phase builds § 8's phase 1, to the rules in § 4
  and § 5.
- `prompts/home-page-mix-mockup.html`: the chosen look, as a static page
  with sample data. Open it in a browser. Build from the tokens and
  `panel.css`, not from its inline colours.
- The root `CLAUDE.md`: "Portal + authentication", "Conventions" (busy.js
  first, buttons never disabled or hidden, the `{{org}}` and `{{abbr}}`
  tokens, the shared grid) and "Deployment" (a push deploys the test
  system, crm-test and production together).
- `portal/router.py` and `portal/frontend/` (`index.html`, `app.js`,
  `styles.css`, `birthday.js`, `event.*`): today's home page, the payload
  `_home_payload` and `_extra_tiles` build, the attention badges
  (`GET /api/portal/attention`), the preferences endpoints and
  `PREFERENCE_KEYS`.
- `frontend/shared/tokens.css` and `chapter-colours.md`: the base tokens and
  how a chapter overrides them.
- `core/config.py` and `core/settings_registry.py`: how a feature switch is
  declared and read per request (`portal_calendar` is the nearest pattern).
- `OPEN-ITEMS.md` #89: what is owed.

## Scope of this phase

Build the frame of the new home page, dark behind a new switch:

1. **The switch `HOME_V2`**, default off, read per request, declared in the
   Features group of System Settings. **Off, today's home page is
   unchanged, byte for byte where practical.**
2. **The new tokens** of plan § 5.1 in `frontend/shared/tokens.css`, and
   their lines in `chapter-colours.md` (which ones a chapter's colour file
   may override).
3. **`frontend/shared/panel.css`**: the panel, section label, chip, status
   pill, row and button rules of plan § 5.2, and the five colour meanings of
   § 5.3 as classes. Every text-on-tint pair reaches 4.5 to 1; a test checks
   the pairs.
4. **The header**: the organisation name and the member's applications as a
   compact navigation row, from the same entitlement lists as today's tiles
   (`_apps_for`, `_directories_for`, `_extra_tiles`), each still opening in
   its stable named tab. Today's attention badges stay on their applications
   until phase 3 folds them into Needs you. A narrow screen wraps or
   collapses the row; the choice is put to Doug at stopping point (a).
5. **The greeting**: the member's first name and today's date. No counts
   yet; they arrive with phases 2 and 3.
6. **The section frames**, in plan § 4.1's order: Today, Needs you, My
   clients, At the chapter. Chapter News has no frame until phase 5. Each
   frame is a panel that decides for itself whether to show and fails
   quietly on its own. Frames with no content yet say so in one plain line.
7. **Nothing today's page offers disappears.** The events rail, the analytics
   panel, the public pages list, the Documentation and CRM links and the
   birthday overlay all appear in the new frame. Where each goes is put to
   Doug at stopping point (a); Doug's standing rule is that removing any
   existing function needs his confirmation first.
8. **Collapse and hide**: each frame collapses from its header; a member can
   hide frames and bring them back. The choice is stored under the new
   preference key `home.sections` (add it to `PREFERENCE_KEYS`).
9. **Conventions**: `busy.js` first; every frame that waits on the server
   wrapped in `CBMBusy.loading`; buttons never disabled or hidden; no
   hardcoded organisation name or acronym; the page works at phone width.
10. **Tests**: the switch off serves today's page; on serves the frame; the
    preference key accepted and its size limit kept; the contrast pairs in
    `panel.css`; the branding guard passes for every new file.
11. **Records**: version bump and `CHANGELOG.md` entry; `OPEN-ITEMS.md` #89
    updated; the root `CLAUDE.md` "Portal + authentication" section gains
    one line on `HOME_V2`, the plan and `panel.css`; the plan's status line
    and § 8 marked with what was built.

Out of scope: any section's real content (phases 2 to 4), Chapter News
(phases 5 to 7), and moving other applications onto `panel.css`.

## Stopping point (a) — before building

Put to Doug, each as one question with options, their costs, and a
recommendation, then stop:

- **Where the new page lives**: a second view inside today's
  `portal/frontend/index.html`, chosen by the switch, or a separate file
  served in its place. Name what each costs in duplicated sign-in and
  session code.
- **Where today's pieces go** in the new frame (item 7): the events rail,
  the analytics panel, the public pages list, the two links, the birthday
  overlay.
- **The header on a narrow screen** (item 4): wrapping, or a "More apps"
  menu past a set number.

Show each answer on one rendered screenshot of the frame if that settles it
faster than words.

## Stopping point (b) — after building

Commit. Then write Doug the check, following his step-by-step instructions
standard (a runbook page if more than three steps): push; switch `HOME_V2`
on at the test system's System Settings (the Business Mentors
Association's); sign in as Joe Mentor, Kitty Cat and an administrator; for
each, what the header, greeting and frames should show; collapse and hide a
frame, sign out and in, and see it remembered; switch `HOME_V2` off and see
today's page return. Production is unaffected while its switch stays off.
Close the phase only after Doug's check (plan § 8, stop 1).

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-17-26 02:30 | First draft, written at the close of phase 0. |
