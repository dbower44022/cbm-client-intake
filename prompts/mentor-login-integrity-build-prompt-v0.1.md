# Kickoff prompt — Mentor login integrity: the build

Last Updated: 11-05-26 11:04 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). Follow-on detail
is announced as "decided unless you object" and does not stop, except a
choice that changes what a user sees or receives, which goes to Doug for a
ruling.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read, in full:

- `prds/mentor-login-integrity-plan.md` — **the plan. Its rulings are
  settled; do not re-open them.** Build to § 4, in the order of § 5.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `assignments/CLAUDE.md`.
- The four handoffs listed in the plan's § 8.

Open every reply with the local time from `date`.

**Stopping points:**
1. After the read-only checks C1–C8 (plan § 7) — report what each found;
   Doug decides whether any finding changes the build.
2. After each build step in plan § 5, for Doug's review, before it is
   enabled anywhere.
3. Before any CRM change on any instance, and before any production read
   that the auto-mode classifier blocks (give Doug the one-line command to
   run; the three read-only report scripts are in `scripts/`).

**Process** (root `CLAUDE.md`): every step ships dark behind its own
feature flag, defaulting off; enabled on crm-test first and reviewed there
as a **real non-administrator** of the relevant team (administrators bypass
ACL); then production; then Boston after a soak. Each step is its own
release, with a `CHANGELOG.md` entry and a version bump. Commit locally with
Conventional Commits; Doug reviews and pushes. Never commit anything under
`.do/` but `app.yaml`. Parallel sessions share one git index: stage and
commit atomically and audit with `git show --stat`.

## Things to know before the first line of code

- **Do not repair David Weissman's record.** It waits on Doug. If it is
  repaired, it is by the plan's § 6, never through Mentor Administration.
- **Step 2 can stop Doug's own screens.** Under the narrowed two-profile
  guess, a login on two Active mentor profiles both carrying its address
  sees no records. Check C5 first; enable step 2 on production only after
  the repair, or tell Doug what he will see.
- **The CRM handoffs need two small scripts the handoffs name but which do
  not exist yet:** `scripts/set_crm_setting.py` (an admin setting through
  `PUT /Settings`, read back) and `scripts/set_authlog_switch.sh` (a
  guarded edit of the droplet's `data/config.php`, with a backup and
  `php -l`). Plus the tracked-field change: an `audited` change type in
  `scripts/apply_crm_plan.py`, or `scripts/set_audited_fields.py`. Use
  the `espo-crm-changes` skill for all three. A `PUT` to
  `Admin/fieldManager` must send the whole field definition.
- **The staff notes plan runs alongside.** Mentor Status-Admin writes
  action history with no note on the mentor profile, and its entries reach
  only the Mentor Administration and Client Administration teams. The
  History tab (step 5) must respect that.
- **Every new setting** (the integrity alert address list, the System
  Management Team gate, the feature flags) must appear at `/setup`
  (`setup/CLAUDE.md`).
- **Every new page** loads `frontend/shared/busy.js` first, uses the shared
  grid for any grid, never caps its width, and uses `{{org}}` / `{{abbr}}`
  for the organisation's name (root `CLAUDE.md`, Conventions).

## What the session ends with

Each step built, tested, committed and listed for Doug's review; the plan's
state updated in its change log; `OPEN-ITEMS.md` #66 updated; and the next
step named.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the design session that produced `prds/mentor-login-integrity-plan.md`. |
