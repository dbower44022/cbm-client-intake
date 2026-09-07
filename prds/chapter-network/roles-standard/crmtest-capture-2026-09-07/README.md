# crm-test roles capture — 2026-09-07

Last Updated: 09-07-26 19:40 · Revision 1.0

A read of crm-test's `role`, `team` and `role_team` tables from its database over
SSH (through the reset script's own `sql()` helper), in the same shape as the
2026-08-31 rehearsal capture in `prds/chapter-network/rehearsal-2026-08-31/crmtest-capture/`.
That earlier directory is the record of what was applied to Lakeside and is left
untouched; this one is what crm-test holds today.

Taken right after `scripts/migrate_client_assignment_role.py` gave the Client
Assignment Role `User: read all, edit own`. The diff against 08-31 is far wider
than that one cell — see `OPEN-ITEMS.md` #28 — and the ruling on it is owed
before anything is re-captured into the standard or applied to a chapter.

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-07-26 19:40 | Claude (Claude Code) | First capture |
