# Kickoff prompt — Mentor login integrity: the build, steps 5 and 6

Last Updated: 11-06-26 01:35 · Revision 0.6 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). Follow-on detail
is announced as "decided unless you object" and does not stop, except a
choice that changes what a user sees or receives, which goes to Doug for a
ruling.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires, **and puts the team question to Doug**
(stopping point 1 below). Then read, in full:

- `prds/mentor-login-integrity-plan.md` — **the plan. Its rulings are
  settled; do not re-open them.** § 3 (ruling Q5.4), § 4.2 (items 8 and
  9), § 4.5, § 5, § 7.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `events/CLAUDE.md`,
  `assignments/CLAUDE.md`.
- The `integrity/` package (step 4) and `core/action_log.py` — the History
  tab reads what `CActionLog` holds. `mentoradmin/router.py`'s `_record`
  and its callers are the worked example of recording before-and-after
  values.
- `OPEN-ITEMS.md` #66 — what is live, what is owed.

Open every reply with the local time from `date`.

## Where the build stands (11-06-26)

- **Steps 0–4 are built and live on crm-test and production**
  (v0.304.0–v0.310.0). Details in `OPEN-ITEMS.md` #66.
- **`LOGIN_INTEGRITY_CHECK` is on** on both, since 11-06-26 ~01:20
  Eastern; first run 12:00 UTC 11-06-26. Every other switch is off.
- **Production measured 11-06-26** (`scripts/c2_reads.sh`): the sign-in
  log reads time out and one page of Action History takes 19 seconds.
  `INTEGRITY_CRM_USE_REPORT` stays off in production until step 0's
  production half lands. Production's backlog is David Weissman's known
  case only.
- **Owed from step 4, not this session's build:** reading the first run's
  log line, then `INTEGRITY_DIGEST` on crm-test for the non-administrator
  review, in the order `OPEN-ITEMS.md` #66 gives.

## Scope of this session

Three releases, in order:

1. **5a — the History engine and the History tab in Mentor
   Administration**, switch `RECORD_HISTORY_TAB` (off).
2. **5b — the History tab in Client Administration, Partner and Funder
   Management (one code path, `DomainConfig`) and Event Administration**,
   the same switch. **Includes ruling Q5.4** (below). Never in Client
   Management: the partner and funder endpoint **refuses the mentor domain
   on the server**, not only by hiding the tab, because the same router
   serves Client Management.
3. **6 — the activity page** and its team, switch `ACTIVITY_PAGE` (off),
   with a CSV export.

End by updating the plan's change log and `OPEN-ITEMS.md` #66.

## Ruling Q5.4 — every application records old and new values

Doug, 11-06-26, option A. Plan § 4.5 promises that opening a History line
shows each field's old and new value. Today only Mentor Administration
records them; Client Administration, Partner and Funder Management and
Event Administration record field names only (for example
`details={"fields": changed}` in `sessions/router.py` and
`events/router.py`). No tracked field exists on an engagement or an event.

So step 5b extends each mutating endpoint in those four applications to
record the before-and-after values in `CActionLog.details`, the way
Mentor Administration does: read the record before the write where the
endpoint does not already, compare with `_same_value`'s normalising rule,
record only what changed. The stream note stays value-free. Values appear
from the day 5b ships; older lines show field names only and say so.
Never record a password, a key, email contents or a raw attachment.

## The History tab — how the two sources merge

Plan § 4.5 merges `CActionLog` with the CRM's own record notes.
`record_action` writes both a stream note and a `CActionLog` row, and an
application save of a tracked field also produces a CRM "Update" note
under the same person's name. Without a rule every application action
shows twice, and the Update note is mislabelled "in the CRM directly".
The rule:

- **`CActionLog` is the authority for application actions.**
- From the stream take only the CRM's own system notes (Create, Update,
  Status, Assign), **never "Post" notes** — the applications write theirs
  as Post.
- **Fold an Update note into a `CActionLog` row** with the same record,
  the same person and the same fields within about a minute.
- A change by the application's key-based account is shown as "System"
  and the job's name.
- Page every read at 200 or below.

The independent review of 5a checks this rule against real notes on
crm-test.

## Two notes carried forward

- **Step 5's History tab detects tracked fields** from the CRM's own
  definitions, and shows the action history without them. The tracked
  fields are live on crm-test only; production waits on the step 0
  handoff, and the tab must not be blocked on it.
- **Mentor Status-Admin entries** (plan § 4.5) are shown only to the
  Mentor Administration and Client Administration teams. The feature is
  not built yet (`prompts/mentor-staff-notes-prompt-v0.1.md`); build the
  filter hook keyed on its action type, not a working filter.

## Before step 6 — one read-only check

The activity page finds a person's changes "in the CRM directly" across
every record, which means listing the CRM's `Note` entity across
entities. Check on crm-test whether the key-based account may list `Note`
filtered by type and author, then measure the read on production (a
production read the auto-mode classifier blocks goes to Doug as a
one-line command). If it is too slow, the activity page shows application
history only until step 0's production half lands, and says so on the
page.

## Stopping points

1. **The first reply: the team question** (`OPEN-ITEMS.md` #66 item 4).
   Production already has a System Administration Team (2 members, no
   role, an internal event audience) and an empty Data Integrity Team.
   Reuse, rename or a new System Management Team. Building 5a continues
   while Doug decides; the gate can be built dark before the team exists,
   because Administrator-type logins always pass.
2. After each release, for Doug's review, before it is enabled anywhere.
3. Before any CRM change on any instance (`*_crm-handoff.md`, the
   `espo-crm-changes` skill), and before any production read the
   auto-mode classifier blocks. In that case give Doug the one-line
   command.

## How the work is divided

The session is the orchestrator and builds the releases itself, in order.
Subagents do read-only checks in parallel, independent pieces in their own
worktrees, and **an independent review of every release** before it goes
to Doug. In step 4 every review found something worth fixing: a partial
CRM read that would have closed faults, a digest stamp that could mark
faults new twice, a deep link lost at sign-in.

## Process

Root `CLAUDE.md`: each release ships dark behind its own feature flag,
defaulting off, and every flag appears at `/setup`. Enable on crm-test
first and review there as a **real non-administrator** of the relevant
team; then production; then Boston after a soak. Each release gets a
`CHANGELOG.md` entry and a version bump; bump `uv.lock`'s own version line
with `pyproject.toml`. Commit locally with Conventional Commits; Doug
reviews and pushes. Never commit anything under `.do/` but `app.yaml`.
Stage and commit atomically and audit with `git show --stat`.

## Things to know before the first line of code

- **Do not repair David Weissman's record.** It waits on Doug, through the
  plan's § 6. The check finds it under conditions 1, 3, 5 and 6; correct.
- **`CActionLog.outcome` takes only `Success`, `Partial` or `Failed`.**
- **The History tab never shows** record ids, raw data, who merely viewed,
  email contents, passwords or keys (plan § 4.5). The acknowledgement of
  a login fault is a `CActionLog` row with no stream note; it belongs on
  the mentor's History tab.
- **No mentor, partner or funder role reads `CActionLog`** (check C8), so
  the tab reads it under the application's key-based account, after the
  user's own read of the record gates the tab.
- **Every new page** loads `frontend/shared/busy.js` first, uses the
  shared grid for any grid, never caps its width, and uses `{{org}}` /
  `{{abbr}}` for the organisation's name.
- A local Postgres for store tests: `docker run -d --rm -e
  POSTGRES_PASSWORD=pw -p 55439:5432 postgres:16-alpine`, then
  `DATABASE_URL=… uv run alembic upgrade head` and
  `TEST_DATABASE_URL=… uv run pytest`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.6 | 11-06-26 01:35 | Claude (Claude Code) | Review before the build. Status brought up to date (step 4 live, the check on). Ruling Q5.4 (Doug, option A): every application records old and new values. The merge rule for the two sources, the release split and switch names, the server-side refusal for Client Management, the team question moved to the first reply, the `Note` read check before step 6, the Status-Admin filter hook. |
| 0.5 | 11-05-26 23:53 | Claude (Claude Code) | Step 4 built (v0.307.0–v0.310.0, C2 ruled on web 11-05-26); steps 5 and 6 with the two notes revision 0.4 asked for. |
| 0.4 | 11-05-26 22:21 | Claude (Claude Code) | Scope narrowed to step 4; see that revision. |
| 0.3 | 11-05-26 18:05 | Claude (Claude Code) | Steps 4–6. |
| 0.2 | 11-05-26 12:08 | Claude (Claude Code) | Steps 0–3; orchestration with subagents. |
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue. |
