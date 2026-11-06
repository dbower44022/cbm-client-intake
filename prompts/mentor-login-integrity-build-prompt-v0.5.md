# Kickoff prompt — Mentor login integrity: the build, steps 5 and 6

Last Updated: 11-05-26 23:53 · Revision 0.5 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). Follow-on detail
is announced as "decided unless you object" and does not stop, except a
choice that changes what a user sees or receives, which goes to Doug for a
ruling.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Then read, in full:

- `prds/mentor-login-integrity-plan.md` — **the plan. Its rulings are
  settled; do not re-open them.** § 4.2 (items 8 and 9), § 4.5, § 5, § 7.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `events/CLAUDE.md`,
  `assignments/CLAUDE.md`.
- The `integrity/` package (step 4) and `core/action_log.py` — the History
  tab reads what `CActionLog` holds.
- `OPEN-ITEMS.md` #66 — what is live, what is owed.

Open every reply with the local time from `date`.

## Where the build stands (11-05-26)

- **Steps 0–3** — see `OPEN-ITEMS.md` #66. Steps 1–3 live on crm-test and
  production; their switches off.
- **Step 4, built 11-05-26, committed, not pushed**, each release reviewed
  by an independent subagent and its findings fixed:
  - **4a, v0.307.0** — `LOGIN_INTEGRITY_CHECK` (worker): the six daily
    conditions, the `login_integrity_fault` table (migration 0041, reset
    nightly on crm-test), a summary line in the worker log, and
    `scripts/integrity_report.py` (`--live` reads the CRM, records
    nothing). A short CRM read fails the run rather than closing faults.
  - **4b, v0.308.0** — `INTEGRITY_DIGEST` (the emailing switch, which is
    how "the first run reports only" is met), `INTEGRITY_DIGEST_TO`, the
    Login faults list with Acknowledge, the portal badge, deep links.
  - **4c, part one, v0.309.0** — `INTEGRITY_SIGNIN_ALERT`: condition 7.
  - **4c, part two, v0.310.0** — `INTEGRITY_CRM_USE_REPORT`: the
    direct-use and shared-account reports (conditions 8 and 9), on the web
    component by Doug's C2 ruling of 11-05-26.
- **Owed from step 4** (not this session's build): the production
  measurement and backlog read, `scripts/c2_reads.sh` run by Doug with
  `!`; then the switches, instance by instance, in the order
  `OPEN-ITEMS.md` #66 item 9 gives.

## Scope of this session

1. **Step 5 — the History tab** (plan § 4.5), in Mentor Administration
   first, then Client Administration, Partner and Funder Management (one
   code path, `DomainConfig`), Event Administration. Never in Client
   Management.
2. **Step 6 — the activity page** and its team.

End by updating the plan's change log and `OPEN-ITEMS.md` #66.

## Two notes carried forward

- **Step 5's History tab detects tracked fields** from the CRM's own
  definitions, and shows the action history without them. The tracked
  fields are live on crm-test only; production waits on the step 0
  handoff, and the tab must not be blocked on it.
- **Step 6: put the team to Doug before building** (`OPEN-ITEMS.md` #66
  item 4). Production already has a System Administration Team (2
  members, no role, an internal event audience) and an empty Data
  Integrity Team.

## Stopping points

1. After each release, for Doug's review, before it is enabled anywhere.
2. Before any CRM change on any instance (`*_crm-handoff.md`, the
   `espo-crm-changes` skill), and before any production read the
   auto-mode classifier blocks. In that case give Doug the one-line
   command.
3. The team decision before step 6.

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
| 0.5 | 11-05-26 23:53 | Claude (Claude Code) | Step 4 built (v0.307.0–v0.310.0, C2 ruled on web 11-05-26); steps 5 and 6 with the two notes revision 0.4 asked for. |
| 0.4 | 11-05-26 22:21 | Claude (Claude Code) | Scope narrowed to step 4; see that revision. |
| 0.3 | 11-05-26 18:05 | Claude (Claude Code) | Steps 4–6. |
| 0.2 | 11-05-26 12:08 | Claude (Claude Code) | Steps 0–3; orchestration with subagents. |
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue. |
