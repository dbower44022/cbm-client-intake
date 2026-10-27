# CRM handoff — opens on the outreach touch

Last Updated: 10-27-26 18:45 · Revision 1.0 — see change log at the end.

Two new fields on the outreach touch (`COutreachTouch`): **`openCount`**
(integer, *Opens*) and **`firstOpenedAt`** (date and time, *First opened*).
The Constant Contact send report (build plan § 7e.9, ruling 96, step M9)
records one touch per recipient of an email campaign: delivered or bounced,
opens and clicks. The touch already carries clicks (`clickCount`,
`firstClickedAt`); these two put opens beside them (Doug's ruling at the M9
plan, 10-27-26: on the CRM's touch, not in the application's database).

**Additive.** Two optional fields on an entity every role that needs it
already reads. **Neither is Read-only**: the application writes both under
the org-wide API key, and a Read-only field drops every API write
(ruling 40). The application feature-detects both: on a CRM without them,
the report records everything except opens.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-27-26 22:28 UTC** — applied by Claude through the applier as the configuration administrator, `--expect 50cae75c1274`; both fields read back from `GET /Metadata`. The org-wide key read both on a touch, wrote `openCount` 2 and a time, read them back and cleared them (22:29 UTC). | This session's applier output and proof script. |
| Production | **Owed** — at the prospect marketing arc's Sunday slot. | — |
| Boston | **Owed** — with the release that carries M9. | — |

## 1. The naming rules

`COutreachTouch` is a custom entity, so field names are stored **exactly as
typed**: `openCount`, `firstOpenedAt`. Verify with `GET /Metadata`, never by
reading a label.

## 2. The automated path — the whole change

From the repository root on the build computer for crm-test, or inside the
deployed web container for production (the container holds the
configuration administrator's credentials).

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

Dry run, which changes nothing and prints the plan and its fingerprint:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/coutreach-touch-opens.json
```

It prints two lines, `create field COutreachTouch.openCount (int)` and
`create field COutreachTouch.firstOpenedAt (datetime)`, and the fingerprint
**`50cae75c1274`** (crm-test, 10-27-26). Then apply exactly that plan (a
target that is not crm-test also needs `--production`):

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/coutreach-touch-opens.json --apply --expect 50cae75c1274
```

The applier rebuilds and reads both fields back. Never between 04:00 and
05:00 UTC on crm-test (the reset window).

## 3. Role grants — none

The Marketing Admin Role already reads `COutreachTouch`, and the application
writes the two fields under the org-wide key, whose role already edits
touches. **No scope or field rule changes.** If a role carries a field-level
rule on `COutreachTouch`, it does not name these new fields, so it cannot
strip them.

## 4. Prove it landed

1. **Shape:** `GET /Metadata?key=entityDefs.COutreachTouch.fields` shows
   `openCount` with type `int` and `firstOpenedAt` with type `datetime`.
2. **The application's key:** `GET /COutreachTouch?maxSize=1&select=id,openCount,firstOpenedAt`
   as the org-wide key answers 200.
3. **The feature:** with *Campaign send report* on at /setup, a campaign's
   **Recipients** tab shows an **Opens** column, and *Read the report now*
   does not end with "Opens are not recorded".

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-27-26 18:45 | Claude (Claude Code) | Written for M9 (ruling 96; Doug's ruling at the M9 plan, 10-27-26). Applied and proven on crm-test the same evening. |
