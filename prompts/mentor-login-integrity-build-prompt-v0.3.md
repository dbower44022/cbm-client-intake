# Kickoff prompt — Mentor login integrity: the build, steps 4 to 6

Last Updated: 11-05-26 18:05 · Revision 0.3 — see change log at the end.

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
  settled; do not re-open them.** § 7 holds the results of checks C1–C8;
  build to § 4, in the order of § 5.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `assignments/CLAUDE.md`,
  `setup/CLAUDE.md`, `events/CLAUDE.md`.
- `core/login_guard.py` — the guards built in step 2. The daily check
  reports the same conditions; reuse its helpers.
- `OPEN-ITEMS.md` #66 — what is live, what is owed.

Open every reply with the local time from `date`.

## Where the build stands (11-05-26)

- **Step 0** — the three CRM scripts are built. History settings and the
  nine tracked fields are **applied on crm-test**. Production and Boston
  are owed, after the next-day sign-in log check and a non-administrator
  stream check on crm-test.
- **Step 1** (v0.304.0) — action history everywhere. **Live** on crm-test
  and production; no switch.
- **Step 2** (v0.305.0) — `LOGIN_REPAIR_GUARDS` and
  `MANAGER_PROFILE_STRICT`. **Live, both off.** Keep
  `MANAGER_PROFILE_STRICT` off on production until step 4b ships: its
  message says "staff have been told", which is true only once the digest
  exists.
- **Step 3** (v0.306.0) — `CBM_EMAIL_LOCK`. Committed. Confirm with
  `git log origin/main..main` whether it has been pushed.

## Scope of this session

**Steps 4, 5 and 6**, in that order. End by updating the plan's change
log and `OPEN-ITEMS.md` #66.

- **Step 4 — the integrity check**, three releases (plan § 4.2):
  - **4a — report only.** The seven conditions, run daily from the worker
    beside `run_alert_check` (`core/monitoring.py`), under the key-based
    account (C1: it reads every login). The first run on production and
    Boston writes a report and emails no one. Fault state lives in the
    application's database (an Alembic migration), so a deploy resends
    nothing and a fault the check no longer finds closes itself.
  - **4b — telling people.** The daily digest. The per-chapter address
    setting at `/setup`, falling back to `ALERT_EMAIL_TO`. The fault list
    and the badge in Mentor Administration. Acknowledging, which is
    recorded in the action history.
  - **4c — the extra reports.** The sign-in trigger (condition 7: a login
    with no mentor profile opens Client Management or My Mentor Profile;
    one email per mentor per day). The direct-use report and the
    shared-account report. **C2 decides where these run:** Action History
    and the sign-in log are readable through the CRM's programming
    interface by an administrator only, and the administrator account is on
    the web component only. Decide between running them on web and giving
    the worker that account. That choice passes the two-part test, so put
    it to Doug. Exclude the configuration account (`crm.config`) and the
    provisioning account. Measure the read on production's sign-in log
    first: it was 6.6 GB before the switch.
- **Step 5 — the History tab** (plan § 4.5): Mentor Administration first,
  then Client Administration, Partner and Funder Management (one code
  path), then Event Administration. The tracked fields must be live on the
  CRM concerned. The tab is not in Client Management. The Mentor
  Status-Admin entries (staff notes plan) reach only the Mentor
  Administration and Client Administration teams.
- **Step 6 — the activity page and its team gate** (plan § 4.5). **Before
  building, put the team to Doug** (`OPEN-ITEMS.md` #66 item 4). Production
  already has a **System Administration Team** (2 members, no role, used
  as an internal event audience) and an empty Data Integrity Team. The
  ruled name, "System Management Team", would sit beside the first.

## Stopping points

1. After each release — 4a, 4b, 4c, each application's History tab, and
   step 6 — for Doug's review, before it is enabled anywhere.
2. Before any CRM change on any instance (`*_crm-handoff.md`, the
   `espo-crm-changes` skill), and before any production read the auto-mode
   classifier blocks. In that case give Doug the one-line command.
3. The C2 decision in 4c, and the team decision in step 6.

## How the work is divided

The session is the orchestrator. Subagents do three kinds of work:

1. Read-only checks and measurements, in parallel.
2. Independent pieces in their own worktrees (`isolation: "worktree"`).
   An example is the digest's email body beside the fault store.
3. **An independent review of every release** before it goes to Doug. In
   this session's predecessor, every review found something real: a fourth
   repair path, a check that could never fire, a configuration file that
   could be left half-written.

The orchestrator builds the releases themselves, in order.

## Process

Root `CLAUDE.md`: each release ships dark behind its own feature flag,
defaulting off, and every flag appears at `/setup`. Enable on crm-test
first and review there as a **real non-administrator** of the relevant
team; then production; then Boston after a soak. Each release gets a
`CHANGELOG.md` entry and a version bump. Bump `uv.lock`'s own version line
with `pyproject.toml`. Commit locally with Conventional Commits; Doug
reviews and pushes. Never commit anything under `.do/` but `app.yaml`.
Stage and commit atomically and audit with `git show --stat`.

## Things to know before the first line of code

- **Do not repair David Weissman's record.** It waits on Doug, through the
  plan's § 6, never through Mentor Administration.
- **`CActionLog.outcome` takes only `Success`, `Partial` or `Failed`** on
  both CRMs. Any other value makes the CRM refuse the whole row.
- **A `login-integrity:` WARNING** is how step 2 reports a refused repair
  today. The daily check should find the same conditions on its own and
  not depend on those log lines.
- **Every new page** loads `frontend/shared/busy.js` first, uses the shared
  grid for any grid, never caps its width, and uses `{{org}}` / `{{abbr}}`
  for the organisation's name.

## What the session ends with

Steps 4 to 6 built, reviewed, committed and listed for Doug's review. The
plan's change log and `OPEN-ITEMS.md` #66 updated. The next step named.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.3 | 11-05-26 18:05 | Claude (Claude Code) | Steps 4–6, after steps 0–3 were built 11-05-26. Records where the build stands, the C2 and team decisions owed, and the `MANAGER_PROFILE_STRICT` timing. |
| 0.2 | 11-05-26 12:08 | Claude (Claude Code) | Steps 0–3; orchestration with subagents. |
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue. |
