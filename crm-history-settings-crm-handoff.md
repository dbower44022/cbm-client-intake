# CRM handoff — history settings: Action History 30 days, and the sign-in log

Last Updated: 11-05-26 13:20 · Revision 1.1 — see change log at the end.

Two CRM settings from the mentor login integrity plan
(`prds/mentor-login-integrity-plan.md`, § 4.6; Doug's rulings Q5.1 and 5b,
11-04-26). No application release depends on either; they can go first.

1. **Keep Action History for 30 days** instead of 15
   (`cleanupActionHistoryPeriod`).
2. **Stop writing a sign-in log row for every request by the application's
   key-based account** (`authApiUserLogDisabled`). People's sign-ins stay
   logged.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Owed.** `cleanupActionHistoryPeriod` is `'15 days'`, set explicitly in `data/config.php` (line 266). `authApiUserLogDisabled` is not set (default: logging on). | Read 11-04-26 and 11-05-26: `GET /Settings` as the configuration administrator; `data/config.php` on the droplet. |
| Production | **Owed.** Action History's oldest row was 10-17-26 01:04:55 on 11-04-26; 0.89 GB. The sign-in log is 6.6 GB of 8.4 GB; the key-based account wrote 4,257,677 rows in the 7 days to 11-04-26, people 124. | `scripts/crm_table_sizes.sh` and `scripts/crm_signin_report.sh`, run by Doug 11-04-26. *Not read:* the settings themselves — assumed default, like crm-test. |
| Boston | **Owed**, after its sizes are read (plan check C6). EspoCRM 10.0.10: confirm both setting names still exist before applying. | — |

**What was verified, where (crm-test, EspoCRM 9.3.10, 11-04-26 and
11-05-26, by reading the source in the container):**

- The clean-up job (`Classes/Jobs/Cleanup.php`) runs on the schedule
  `1 1 * * 0` — Sundays at 01:01 — and deletes Action History older than
  `cleanupActionHistoryPeriod`, and sign-in log rows older than
  `cleanupAuthLogPeriod` (default `'2 months'`).
- `Core/Authentication/Authentication.php` writes a sign-in log row only for
  a request **not** made with an existing session, and skips it for a
  key-based account when `authApiUserLogDisabled` is true.
- `cleanupActionHistoryPeriod` is an *admin item*: an administrator can set
  it through the API (`PUT /Settings`) or in Administration → Settings.
  `authApiUserLogDisabled` is a *system item*: the API and the screens cannot
  set it. It is a line in the server's configuration file.

## 1. Action History — 30 days

**Automated path (preferred).** As the configuration administrator, from
the repository root:

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/set_crm_setting.py cleanupActionHistoryPeriod "30 days"
```

That is the dry run: it reads the value and prints the planned change.
Add `--apply` to write it with `PUT /Settings` and read it back. On any CRM
but crm-test, `--apply` also needs `--production` (the same guard as
`scripts/apply_crm_plan.py`). Boston: put
`--env ~/.config/cbm-boston/boston.env` after `run_with_admin.py`.

**Hand path.** In the CRM, signed in as an Administrator-type login:
Administration → Settings. Find the field for Action History clean-up
period (label not verified — EspoCRM may not show it on the Settings
screen at all; if it is not there, use the automated path). Enter
`30 days`. Save.

**Trap.** The value is a PHP date phrase. `30 days` works; `30` alone or
`1 month ` with a trailing space may not. Read it back.

**Check.** `GET /Settings` as an administrator shows
`"cleanupActionHistoryPeriod": "30 days"`. After the second Sunday,
`scripts/crm_table_sizes.sh` shows the oldest Action History row about 30
to 37 days back.

## 2. The sign-in log — stop logging the key-based account

This is a server change. Doug runs it; it restarts nothing.

**Before you start:** a terminal in `~/Dropbox/Projects/cbm-client-intake`;
the droplet scripts reach each CRM through `scripts/on_crm.sh`.

**The change.** In the CRM container's `data/config-internal.php` (not
`data/config.php`: the setting is a system item, and EspoCRM writes and
reads system items from the internal file — source read on 9.3.10 and
10.0.10, 11-05-26), inside the returned array, add the line:

```
'authApiUserLogDisabled' => true,
```

`scripts/set_authlog_switch.sh` does this safely: it builds a candidate,
checks it with `php -l`, backs the file up beside itself, writes it in
place as `www-data` (owner and mode kept), checks again and restores on
failure. Never hand-edit the file: a syntax error in it stops the whole
CRM. Read the state first (writes nothing):

```
scripts/on_crm.sh test scripts/set_authlog_switch.sh
```

Then apply:

```
scripts/on_crm.sh test scripts/set_authlog_switch.sh --apply
```

Use `production` or `boston` in place of `test` for the other CRMs. The
crm-test nightly reset restores the database only, so the switch survives
it.

**Trap.** `authLogDisabled` (without `ApiUser`) switches off **all**
sign-in logging, people included. That would destroy the evidence this plan
relies on. The setting is `authApiUserLogDisabled`.

**Check.** One day later, `scripts/crm_signin_report.sh` shows almost no
`api` / `ApiKey` rows in its first table, and `admin` / `regular` rows as
before. Sign in through the application once as a non-administrator and
confirm the application still works: the setting changes logging only.

**Rollback.** `scripts/on_crm.sh <chapter> scripts/set_authlog_switch.sh --off`
sets it to `false`. Nothing else changes. Prefer it to restoring the backup:
EspoCRM rewrites the internal file itself, so an old backup may undo more
than this line.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 11-05-26 13:20 | Claude (Claude Code) | Both scripts built (step 0). The sign-in log switch goes in `data/config-internal.php`, not `data/config.php`. The `--production` guard and the rollback command added. |
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the mentor login integrity design session. |
