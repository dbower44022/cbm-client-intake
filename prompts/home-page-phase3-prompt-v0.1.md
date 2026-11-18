# Kickoff prompt — the home page, phase 3: Needs you

Last Updated: 11-18-26 18:00 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-18-26 at the close of phase 2
(v0.346.0, Today and My clients; stop 2 passed the same day) and of Doug's
three changes after it (v0.348.0: the Directories menu, the Upcoming events
panel, the text size; checked the same day). Start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read
this file, and tell it to follow everything below the line.

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
and committed in one step, then audit with `git show --stat`. If another
session commits between your read and your commit, check that your
`CHANGELOG.md` entry still sits above theirs (it did not at v0.346.0).

Read, in full, before any code:

- `prds/home-page-plan.md`: the plan. **Rulings 1 to 9 are settled; do not
  re-open them.** This phase builds § 8's phase 3, to § 4.2 (the Needs you
  list) and § 4.1's greeting count, in the look of § 5. § 9 names two
  questions decided in this phase.
- `prompts/home-page-mix-mockup.html`: the Needs you panel as sample data.
- The root `CLAUDE.md`: "Portal + authentication" (the new home page line
  and its endpoint), "My Email", "Client Management" under Session
  Management, "Conventions" (busy.js, **textsize.js and no bare `vh`/`vw`**,
  buttons never disabled or hidden, the shared grid, CRM datetimes are UTC),
  and the "A 403 and a 404" gotcha.
- `sessions/CLAUDE.md`: owned and co-mentored engagements, the session
  fields, the AI summary (`AI_SUMMARY_FIELD`, transcripts), `touch_last_contact`
  and `lastContactDate`.
- Phase 2's code, which this phase extends: `portal/router.py`
  (`_home_sections`, `_home_mentoring`, `GET /api/portal/home/mentoring`,
  `GET /api/portal/attention`), `portal/frontend/home.js` (`loadMentoring`,
  the frames), `home.css`, `frontend/shared/panel.css` (chips,
  `cbm-row--urgent`), `core/attention.py`.
- `myemail/` (router, service, `frontend/app.js`): how a conversation is
  found to be awaiting a reply, and how the page could open one
  conversation from a link.
- `assignments/service.py`: `engagementAssignedDate` and the waiting-client
  count (ruling 3: mentors never see waiting clients).
- `setup/CLAUDE.md` and `core/settings_registry.py`: how a new System
  Settings value is added (the fixture `tests/fixtures/setup_payload_before_integrations.json`
  must gain its row).
- `OPEN-ITEMS.md` #89.

## Scope of this phase

Fill the Needs you frame, still dark behind `HOME_V2`:

1. **The list** (§ 4.2): one row per attention item, each with a chip in its
   § 5.3 colour and words, the record's name, a short reason and a link that
   opens the owning application on that record in its stable named tab
   (ruling 1). Sorted by urgency, then by age. The single most urgent row
   may carry `cbm-row--urgent`; no other row does.
2. **The mentoring kinds**, read **as the member** (owned and co-mentored):
   no contact past the threshold (red, the day count), a held session with
   no notes (amber, Notes), a meeting summary waiting for review (navy,
   Summary), a client email waiting for a reply (navy, Email), an engagement
   near its close date (amber, Closing), a newly assigned client (navy,
   New).
3. **The staff kinds**: today's `/api/portal/attention` counts folded into
   the same list as purple Staff rows, for the members whose teams see them
   (ruling 2: one list, sorted by urgency, not by application). Ruling 3
   stands: no waiting-client row for a mentor who is not Client
   Administration staff.
4. **The threshold**: a System Settings value, default 21 days, read per
   request.
5. **My Email opens one conversation from a link**:
   `/myemail/?conversation=<id>`, so the Email rows can point at it.
6. **The greeting's count**: "N items need you" joins the date line after
   the session count (§ 4.1).
7. **Each kind fails on its own**: a kind whose read fails is left out with
   a logged warning; the panel says one line if the whole read fails, never
   the page. Wrapped in `CBMBusy.loading`.
8. **Tests**: each kind's rule, co-mentored engagements included, the sort,
   ruling 3, the threshold setting (and its fixture row), the switch off,
   the branding guard, and the My Email link.
9. **Records**: version bump and `CHANGELOG.md`; `OPEN-ITEMS.md` #89; the
   plan's status line, § 8 and § 9; the root `CLAUDE.md` home page line if
   the endpoint changes; `myemail`'s documentation for the new link.

Out of scope: At the chapter (phase 4), Chapter News (phases 5 to 7), any
write from the home page other than Join (ruling 1), and acting on an item
in place (no "dismiss" for attention items; an item leaves the list when
the owning application resolves it).

## Stopping point (a) — before building

Put to Doug, each as one question with options, their costs, and a
recommendation, then stop. **Verify each premise against the code or the
Association's CRM first** (read-only), and name what you verified.

- **No notes**: which sessions count — Completed sessions with an empty
  `sessionNotes`, from how far back — and whether a session whose meeting
  summary or next steps were filled counts as having notes.
- **Summary waiting for review**: what in the CRM says a summary was
  reviewed. If nothing does, the options are a new field (a CRM change, with
  its handoff) or a rule from what exists; name the cost of each.
- **Email waiting for a reply**: reuse My Email's own awaiting-reply rule
  as-is, and how old a message must be before it is listed.
- **Closing**: how many days before `closeDate`, and which statuses.
- **New**: assigned in the last how many days (`engagementAssignedDate`),
  or every engagement still Pending Acceptance, or both.
- **The threshold** (§ 9): one value for every status, or none for On-Hold.
- **Urgency order** across the kinds, and whether the staff rows sort among
  them or after them.
- **The read**: extend `GET /api/portal/home/mentoring` or add one endpoint
  for Needs you. Name what each costs in CRM calls per sign-in (the `timing`
  log line from phase 2's check is the measure) and whether the bar's
  attention badges stay once the counts are in the list.

Show the answers on one rendered screenshot of the filled panel with sample
data if that settles them faster than words.

## Stopping point (b) — after building

Commit. Then write Doug the check as a runbook page, following his
step-by-step instructions standard: push; switch `HOME_V2` on at the
Association's System Settings; set the threshold low enough that a training
client shows the no-contact row; sign in as Joe Mentor and find one example
of each mentoring kind, opening each link and seeing it land on the record
(make the missing examples in Client Management: a Completed session with
no notes; say which records each example uses); sign in as Kitty Cat for
the staff rows beside her mentoring rows, and as Mark Marketing for the
staff rows alone; open an Email row and see My Email open on that
conversation; set the threshold back; switch `HOME_V2` off. Raise the
Association's owed baseline re-capture (#87) first: every record made for
the check stays in its CRM. Close the phase only after Doug's check (plan
§ 8, stop 3).

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-18-26 18:00 | First draft, written at the close of phase 2. |
