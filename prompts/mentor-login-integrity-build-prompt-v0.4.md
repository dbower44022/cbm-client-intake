# Kickoff prompt — Mentor login integrity: the build, step 4 (the integrity check)

Last Updated: 11-05-26 22:21 · Revision 0.4 — see change log at the end.

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
  build to § 4.2, in the order of § 5.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `setup/CLAUDE.md`.
- `core/login_guard.py` — the guards built in step 2. The daily check
  reports the same conditions; reuse its helpers.
- `core/monitoring.py` and `worker.py` — where the check runs and how the
  worker schedules a daily job (`_next_local_hour`).
- `core/sandbox_reset.py` and `tests/test_sandbox_reset.py` — every new
  table must be classified.
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
  `MANAGER_PROFILE_STRICT` off on production until step 4b's emailing is
  on there: its message says "staff have been told", which is true only
  once the digest goes out.
- **Step 3** (v0.306.0) — `CBM_EMAIL_LOCK`. **Pushed 11-05-26, live on
  crm-test and production, switch off.** `OPEN-ITEMS.md` #66 still says
  steps 1 to 3 are "committed, not pushed" in places; correct it first.

## Scope of this session

**Step 4 only — the integrity check, three releases (plan § 4.2).**
Steps 5 (the History tab) and 6 (the activity page) are the next session.
End by updating the plan's change log and `OPEN-ITEMS.md` #66, and by
writing revision 0.5 of this prompt, which starts at step 5. If the session
ends before 4c, revision 0.5 starts where the work stopped instead.

- **4a — report only.** The six daily conditions (1 to 6), run once a day
  from the worker beside `run_alert_check` (`core/monitoring.py`), under
  the key-based account (C1: it reads every login). **No email of any
  kind.** Fault state lives in the application's database (an Alembic
  migration), so a deploy resends nothing and a fault the check no longer
  finds closes itself.
  - **Schedule:** a local hour, through `_next_local_hour`, with its own
    setting. On crm-test it must land after 05:00 UTC: the CRM is
    restored at 04:00 UTC and the application's database at 05:00 UTC,
    and between the two the data disagrees by design.
  - **The sandbox reset:** the fault table goes in `RESET_TABLES`. Its
    faults point at CRM records the reset restores every night. On
    crm-test every fault therefore reads as new each morning; that is
    expected.
  - **How Doug reads the report:** a one-line summary in the worker log
    on every run (counts per condition, new and closed), plus a read-only
    script that prints the open faults and can be run inside the
    container (`do-app-console-scripting` memory). This is how the backlog
    on production and Boston is reviewed before anyone is emailed.
- **4b — telling people.** The daily digest, named the **integrity
  digest** in code, settings and log lines: the worker already sends a
  "daily email digest" (`comms/digest.py`). The per-chapter address
  setting at `/setup`, falling back to `ALERT_EMAIL_TO`. The fault list and
  the badge in Mentor Administration. Acknowledging, which is recorded in
  the action history.
  - **Emailing is its own switch**, separate from the check's switch.
    This is how the plan's "first run reports only" is met: Doug turns
    emailing on for an instance only after reading that instance's 4a
    report. No code decides what a "first run" is — an empty fault table
    would make every crm-test night a first run, and crm-test would never
    email.
  - **When "staff have been told" becomes true:** step 2's guards report
    a fault as a log line only (`login_guard.fault`). Condition 1 finds the
    same fault at the next daily run, so staff are told the next morning.
    That meets the message; say so in the changelog.
- **4c — the extra reports.** The sign-in trigger (condition 7: a login
  with no mentor profile opens Client Management or My Mentor Profile; one
  email per mentor per day). It runs on the web component, which already
  sends alerts (the worker-liveness check) and has the database. The
  direct-use report and the shared-account report. **C2 decides where
  these two run:** Action History and the sign-in log are readable
  through the CRM's programming interface by an administrator only, and
  the administrator account is on the web component only. Decide between
  running them on web and giving the worker that account. That choice
  passes the two-part test, so put it to Doug. Exclude the configuration
  account (`crm.config`) and the provisioning account. Measure the read on
  production's sign-in log first: it was 6.6 GB before the switch.

## Stopping points

1. After each release — 4a, 4b, 4c — for Doug's review, before it is
   enabled anywhere.
2. Before any CRM change on any instance (`*_crm-handoff.md`, the
   `espo-crm-changes` skill), and before any production read the auto-mode
   classifier blocks. In that case give Doug the one-line command.
3. The C2 decision in 4c.

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
  plan's § 6, never through Mentor Administration. The check will find it
  (condition 1 and condition 6); that is correct.
- **`CActionLog.outcome` takes only `Success`, `Partial` or `Failed`** on
  both CRMs. Any other value makes the CRM refuse the whole row.
- **A `login-integrity:` WARNING** is how step 2 reports a refused repair
  today. The daily check finds the same conditions on its own and does not
  depend on those log lines.
- **Every new page** loads `frontend/shared/busy.js` first, uses the shared
  grid for any grid, never caps its width, and uses `{{org}}` / `{{abbr}}`
  for the organisation's name.

## What the session ends with

Step 4 (4a, 4b, 4c) built, reviewed, committed and listed for Doug's
review. The plan's change log and `OPEN-ITEMS.md` #66 updated. Revision 0.5
of this prompt written for steps 5 and 6, carrying these two notes:

- **Step 5's History tab detects tracked fields** from the CRM's own
  definitions, and shows the action history without them. The tracked
  fields are live on crm-test only; production waits on the step 0
  handoff, and the tab must not be blocked on it.
- **Step 6: put the team to Doug before building** (`OPEN-ITEMS.md` #66
  item 4). Production already has a System Administration Team (2
  members, no role, an internal event audience) and an empty Data
  Integrity Team.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.4 | 11-05-26 22:21 | Claude (Claude Code) | Review before running, approved by Doug: scope narrowed to step 4 (steps 5–6 to revision 0.5); step 3 recorded as pushed and live; the fault table reset nightly on crm-test and the check scheduled after 05:00 UTC; "first run reports only" met by a separate emailing switch rather than first-run code; a log summary and a read-only script so the 4a report has a reader; the new digest named the integrity digest beside the existing one; the History tab to detect tracked fields. |
| 0.3 | 11-05-26 18:05 | Claude (Claude Code) | Steps 4–6, after steps 0–3 were built 11-05-26. Records where the build stands, the C2 and team decisions owed, and the `MANAGER_PROFILE_STRICT` timing. |
| 0.2 | 11-05-26 12:08 | Claude (Claude Code) | Steps 0–3; orchestration with subagents. |
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue. |
