# Resume prompt — the training application, stop 3

Last Updated: 11-21-26 23:57 · Revision 0.1 — see change log at the end.

Start a fresh Claude Code session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell it to follow everything below the line.

---

**Operating mode: DETAIL** (this repository's default). Phase 3 of `prds/training-app-plan.md` is built and pushed (v0.364.0, commits `5f822b1b` and the stop 3 check page's source). The session that built it closed for a reboot before Doug ran the check.

1. Read `OPEN-ITEMS.md` #92, the phase 3 entry in `CHANGELOG.md`, and `prompts/training-app-stop-3-check.md`.
2. Confirm with `git log origin/main..main` that nothing is unpushed, and read `https://apps.businessmentorsassociation.org/healthz` for version 0.364.0 or later.
3. Ask Doug which sections of the step page https://claude.ai/artifact/Wk8UVWYCvwZr5WPLSD5zm7 he has run, and for each checkpoint's report. Section 1 (the push) is already done.
4. Fix anything the check finds, as a patch release with its tests and changelog entry.
5. When the check passes: mark phase 3 done in the plan (a new revision), in `OPEN-ITEMS.md` #92 and in the Current status section of `CLAUDE.md`; then draft phase 4's prompt (mentor onboarding, TR10) as `prompts/training-app-phase-4-prompt-v0.1.md` for Doug's approval.

Raise `OPEN-ITEMS.md` #87 (the Association's baseline re-capture) at the start, as every session touching the Association does.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 23:57 | Claude (Claude Code) | Written at the close of the phase 3 build session, before the stop 3 check ran. |
