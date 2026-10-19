# Kickoff prompt — Boston's two CRM changes and its next release

Last Updated: 10-18-26 23:05 · Revision 1.0 — see change log at the end.

Paste this into a fresh Claude Code session rooted in `cbm-client-intake`.
It carries the state of Boston's half of the additional-managers arc at the
close of the 10-14-26 and 10-18-26 sessions, so the next session starts
working rather than reconstructing.

---

## Kickoff

Operating mode: ARCHITECTURE.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read the memory note `quick-add-ownership-and-comanagers-state` and
`OPEN-ITEMS.md` #46 and #47. Open every reply with the local time from `date`.

### Where the work stands

- **Boston's CRM is prepared, not changed.** Both `additionalManagers`
  links and both `CMentorProfile` reverses are absent (read-only probe
  10-14-26 22:00, re-read 10-18-26 22:50). The applier's dry run against
  Boston signs in as its administrator and prints fingerprint
  `f2d6a41ea16c`, the same plan crm-test and production took.
- **The funder-notes conversion on Boston is already done** (10-11-26 21:06,
  backup `CSponsorProfile.json.bak-desc-wysiwyg-20261012-010651` on the
  droplet). Nothing to run for #47 on the CRM; only the release is owed.
- **Boston's applications run v0.232.0**, the release lane still points at
  v0.232.0, and `main` is at v0.264.2. Boston's image predates the applier
  shipping in it (v0.241.2), so the apply runs from this computer through
  `scripts/apply_plan.sh boston <plan> [fingerprint]` (parses
  `~/.config/cbm-boston/boston.env`, never sources it).
- **The step page is written and current:**
  https://claude.ai/artifact/Covmt3vPbZnvWpr8WdQBY6 (private, *Boston
  Release Changes*, rev 2.0, 10-18-26). Sections 1–2 apply the plan and
  check Entity Manager; sections 3–6 are the release day: cut and push,
  the chapter label `boston` at Boston's System Settings page, the pass on
  a test funder, its removal. Boston holds one mentor profile and no
  partner or funder records, so the add itself cannot be exercised there
  yet; the page says so at section 5 step 7.
- Doug has not given the go for section 1 step 3 (the apply). Nothing on
  the page has run.

### What to do first

1. Re-run the read-only dry run and confirm nothing moved:
   `scripts/apply_plan.sh boston scripts/plans/additional-managers.json`
   should print `f2d6a41ea16c` and the two `create link` lines. If it
   prints `ALREADY CORRECT`, Doug applied it between sessions: record that
   in #46 and the handoff before anything else.
2. Confirm `git status --short --untracked-files=no` is empty before the
   release day's cut; on 10-18-26 22:55 `uv.lock` was dirty from another
   session and `scripts/cut_release.sh` refuses a dirty tree.
3. Ask Doug for the go on section 1 step 3, in one sentence, and stop.
   Once the apply and the Entity Manager check are reported, record them in
   `OPEN-ITEMS.md` #46 and `cpartner-csponsor-additional-managers-crm-handoff.md`
   § 2, then the release-day sections as Doug reports each checkpoint.

### Rules this work is under

- The step standard mirrored in the global `CLAUDE.md` (10-17-26): one
  action per step, every entry click-to-copy, every place named from the
  outside in (application, page, tab, control), warnings with an undo on
  every changing step, a checkpoint per section. The page conforms; keep it
  so when revising it.
- The applier's `--apply` and anything mutating on a droplet are Doug's to
  run. Read-only probes and dry runs are fine from the session.
- A chapter's step page is one standing page per task, updated in place at
  the same address.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-18-26 23:05 | Claude (Claude Code) | Written at the close of the 10-18-26 session: state, the page, what to do first, the rules. |
