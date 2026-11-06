# CRM handoff — the System Management Team

Last Updated: 11-06-26 15:36 · Revision 1.1 — see change log at the end.

A new team, **System Management Team**, that gates the activity page — every
change by one person or in one date range, across all records — and later
functions such as backup review. From the mentor login integrity plan
(`prds/mentor-login-integrity-plan.md`, § 4.5; Doug's ruling Q5.3,
11-04-26). Doug chose the name so the team can carry more than history, and
to avoid the words "System Administrator".

The team grants no CRM records by itself. It is a membership the
application reads, the same pattern as the Analytics Admin Team. Members
need no role from it; Administrator-type logins pass the application's gate
regardless.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Owed.** | Read 11-06-26: no team by that name (`scripts/create_system_management_team.py` dry run). |
| Production | **Owed.** | — |
| Boston | **Owed.** | — |

**Check first (plan check C7):** a **Data Integrity Team** already exists in
the CRM, with its own role, which production attaches to no team (open item
#30). Read its members and its role before creating the new team, and tell
Doug if it already serves this purpose.

**Ruled 11-06-26 by Doug (Q5.5, option 1): a new team.** Production's
System Administration Team (2 members, an internal event audience) is not
reused and the empty Data Integrity Team is not renamed.

## 1. Automated path (preferred)

`scripts/create_system_management_team.py` creates `Team` with
`name = "System Management Team"` if none exists by that name, then reads it
back. Dry run by default, `--apply` to write; crm-test first:

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/create_system_management_team.py --apply

Production and Boston: the same script, run where their administrator
credentials are (`run_with_admin.py --env <file>`, or the web container).

## 2. Hand path

In the CRM, as an Administrator-type login: Administration → Teams →
Create Team. Name: `System Management Team`. No roles. Save. Then add the
members Doug names (none decided yet).

**Trap.** The application matches the team by its exact name. A trailing
space, or "Systems Management Team", makes the gate refuse everyone except
administrators. Copy the name.

## 3. Check

1. `GET /Team?where[0][type]=equals&where[0][attribute]=name&where[0][value]=System Management Team`
   as the org-wide key returns one row.
2. Once the activity page ships: a non-administrator member sees it; a
   non-member gets the message naming the team.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 11-06-26 15:36 | Claude (Claude Code) | Doug's ruling (new team); the script; crm-test read. |
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the mentor login integrity design session. |
