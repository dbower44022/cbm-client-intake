# Kickoff prompt — Mentor login integrity: the build, steps 0 to 3

Last Updated: 11-05-26 12:08 · Revision 0.2 — see change log at the end.

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
  settled; do not re-open them.** Build to § 4, in the order of § 5.
- `mentoradmin/CLAUDE.md`, `sessions/CLAUDE.md`, `assignments/CLAUDE.md`,
  `setup/CLAUDE.md`.
- The four handoffs listed in the plan's § 8.

Open every reply with the local time from `date`.

## Scope of this session

**This session does the checks C1–C8, step 0 and build steps 1 to 3.** It
ends by writing revision 0.3 of this prompt, which starts at step 4.
Steps 4 to 6 are later sessions.

- **Step 0 — the CRM helper scripts** (not in plan § 5; added here). Write
  `scripts/set_crm_setting.py` (an admin setting through `PUT /Settings`,
  read back), `scripts/set_authlog_switch.sh` (a guarded edit of the
  droplet's `data/config.php`, with a backup and `php -l`), and the
  tracked-field change: an `audited` change type in
  `scripts/apply_crm_plan.py`, or `scripts/set_audited_fields.py`. Use the
  `espo-crm-changes` skill for all three. A `PUT` to `Admin/fieldManager`
  must send the whole field definition. Apply the handoffs on crm-test
  only, after Doug's go-ahead (stopping point 3). The tracked fields must
  be in place before step 5.
- **Step 1 — action history everywhere** (plan § 4.1). No feature flag:
  the plan rules it not user-facing, covered by the existing `CActionLog`
  feature detection.
- **Step 2 — two flags, not one.** The three repair paths that stop on
  disagreement (plan § 4.3, first half) get one flag. They only add
  protection, so they can be enabled on production at once: the clean-up
  job runs every night and is what spread the fault on 10-17-26. The
  narrowed two-profile guess (§ 4.3, second half) gets its own flag,
  enabled on production only after David Weissman's record is repaired.
- **Step 3 — the CBM email lock and checks** (plan § 4.4).

## Stopping points

1. After the read-only checks C1–C8 (plan § 7) — report what each found;
   Doug decides whether any finding changes the build.
2. After step 0, and after each of steps 1, 2 and 3, for Doug's review,
   before it is enabled anywhere. A step that ships as more than one
   release stops after each release.
3. Before any CRM change on any instance, and before any production read
   that the auto-mode classifier blocks — give Doug the one-line command to
   run. The three read-only report scripts are
   `scripts/crm_direct_use_report.sh`, `scripts/crm_signin_report.sh` and
   `scripts/crm_table_sizes.sh`; chapter CRM droplets are reached through
   `scripts/on_crm.sh <test|production|boston>`.

## How the work is divided

The session is the orchestrator. Subagents do three kinds of work, and
nothing else:

1. **The checks C1–C8**, in parallel. Each gets the plan's § 7 row, the
   relevant handoff and the gotchas it needs from the root `CLAUDE.md`.
   Read-only, always. A check the classifier blocks comes back as a
   one-line command for Doug.
2. **Step 0's three scripts**, in parallel, each in its own worktree
   (`isolation: "worktree"`), so they never share one git index. The
   orchestrator merges and commits.
3. **An independent review of each step** before it goes to Doug: a fresh
   subagent reads the change against the plan and the root `CLAUDE.md`
   Conventions. The orchestrator fixes what it finds, then stops.

**The orchestrator builds steps 1 to 3 itself, in order.** They edit the
same files (`mentoradmin/router.py`, `mentoradmin/service.py`,
`assignments/stamps.py`, `sessions/service.py`), so parallel building
would only conflict, and each stops for review anyway.

A subagent's report reaches the orchestrator, not Doug: relay what matters.

## Process

Root `CLAUDE.md`: every step except step 1 ships dark behind its own
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
- **The narrowed two-profile guess can stop Doug's own screens.** A login
  on two Active mentor profiles, both carrying its address, sees no
  records. Check C5 first; tell Doug what he will see.
- **Never run alongside the staff notes work**
  (`prompts/mentor-staff-notes-prompt-v0.1.md`). Both edit `mentoradmin/`
  and both add a database migration; run together they make two migration
  heads and clashing edits. That work also turns `mentorStatusNotes` into
  Mentor Assignment Preferences, which is on the tracked-field list: before
  applying the tracked fields, read which field name exists.
- **Mentor Status-Admin** (staff notes plan) writes action history with no
  note on the mentor profile, and its entries reach only the Mentor
  Administration and Client Administration teams. Step 1 must not add a
  note there.
- **Every new setting** (each feature flag) must appear at `/setup`
  (`setup/CLAUDE.md`).
- **Every new page or screen element** loads `frontend/shared/busy.js`
  first, uses the shared grid for any grid, never caps its width, and uses
  `{{org}}` / `{{abbr}}` for the organisation's name (root `CLAUDE.md`,
  Conventions).

## What the session ends with

Steps 0 to 3 built, tested, committed and listed for Doug's review; the
plan's state updated in its change log; `OPEN-ITEMS.md` #66 updated;
revision 0.3 of this prompt written, starting at step 4.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-05-26 12:08 | Claude (Claude Code) | Doug's review, 11-05-26. Scope cut to the checks, step 0 and steps 1–3; revision 0.3 carries steps 4–6. Step 0 added for the CRM helper scripts. Step 2 split into two flags so the repair-path guards can go on production before the repair. Step 1's no-flag exception stated. A stop after each release. Orchestration section: subagents for the checks, step 0 and per-step review; the orchestrator builds steps 1–3. Never run alongside the staff notes work. Report scripts named. "Confirm `CLAUDE.md`" replaced by the global first-reply rule. |
| 0.1 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the design session that produced `prds/mentor-login-integrity-plan.md`. |
