# CRM handoff — the multi-column sorted list endpoint

Last Updated: 10-30-26 00:48 · Revision 0.5 — see change log at the end.

A small piece of our own code in the CRM: `GET /api/v1/SortedList/{entityType}`
returns a page of records sorted on up to six columns, which EspoCRM's own
list cannot do. Plan: `prds/shared-grid-plan.md` § 8 (Doug's ruling
10-28-26 to change the CRM itself rather than keep a copy of the data).

**What it is.** Two files under the CRM's `custom/` folder:
`custom/Espo/Custom/Api/SortedList.php` and one route merged into
`custom/Espo/Custom/Resources/routes.json`. Source:
`crm/extensions/sorted-list/`. No database change. Removing the two and
rebuilding takes it away (`scripts/install_sorted_list.sh <chapter> --remove`).

**How it is called.** The standard list's parameters (`where[…]`, `select`,
`maxSize` up to 200, `offset`, `textFilter`) plus
`orderList=leadStatus:asc,name:desc` — not `sortBy`, which EspoCRM treats as
its own one-field `orderBy`. Access control is the standard list's: the
caller must read the type, the query runs under the caller's roles and
teams, and attributes the caller may not read are removed. The total is not
returned; callers take it from the standard list with the same `where`.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Installed 10-28-26** by Doug (`scripts/install_sorted_list.sh test`, EspoCRM 9.3.10). Checked by Claude with the org-wide key: two-column sort correct; 150–190 ms, the same as the standard one-column list; `where` and paging consistent; an unknown column 400, an unreadable type 403, a page over 200 refused; linked names (a contact's company) returned. | The checks above. |
| Production | **Installed 10-30-26** by Doug (step page part B, run early). `check_sorted_list.sh production` in the web console: all four checks passed (181 companies); the Companies directory sorted on two columns with no one-column note. | Doug's console output; B11. |
| Lakeside | **Installed 10-30-26** by Doug (step page part A), EspoCRM 10.0.10: `check_sorted_list.sh lakeside` passed all four checks (200 rows sorted on two columns). The EspoCRM 10 rehearsal for Boston passed. | Doug's terminal output. |
| Boston | **Installed 10-30-26** by Doug (step page part C, run early), EspoCRM 10.0.10: `check_sorted_list.sh boston` passed all four checks. Boston holds one company, so the ordering itself was proven on Lakeside (same version, 200 rows); Boston proves the route, the access control and the refusals. Unused until Boston's next release. | Doug's terminal output. |

## 1. Install

From the build computer, in `~/Dropbox/Projects/cbm-client-intake`:

```
scripts/install_sorted_list.sh production
```

Boston: `scripts/install_sorted_list.sh boston`. Each prints the EspoCRM
version, the number of routes in the routes file (any routes already there
are kept; the old file is saved as `routes.json.bak-<stamp>`), and
`rebuild: done`.

## 2. Verify

As the org-wide key:
`GET /api/v1/SortedList/CProspect?orderList=leadStatus:asc,name:desc&maxSize=5`
answers 200 with the rows in that order.

## 3. Upgrades

**Re-check after every EspoCRM upgrade.** The endpoint uses EspoCRM's own
search-parameter reader, query builder and access control; a major version
could change them. The check is § 2.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.5 | 10-30-26 00:48 | Claude (Claude Code) | Boston installed and checked. |
| 0.4 | 10-30-26 00:47 | Claude (Claude Code) | Lakeside (EspoCRM 10) installed and checked; Boston cleared. |
| 0.3 | 10-30-26 00:35 | Claude (Claude Code) | Installed and checked on production. |
| 0.2 | 10-29-26 22:28 | Claude (Claude Code) | `scripts/check_sorted_list.sh` (read-only check, passed on crm-test 10-29-26); production, Lakeside and Boston booked on the Sunday step page. |
| 0.1 | 10-28-26 13:20 | Claude (Claude Code) | Created; installed and checked on crm-test. |
