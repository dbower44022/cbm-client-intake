# CRM handoff — topics on events (Track F, F1)

Last Updated: 10-08-26 23:50 · Revision 1.1 — see change log at the end.

One new field on the event, `CEvent.topics` — a multiple-choice field with the
same ten values as the single `topic` it supersedes — and a one-time copy of
each event's single topic into it. Nobody types a topic (Doug's ruling
10-08-26): the list is this field's options, changed in the CRM. Design and
rulings: `prds/events/CBM_Events_Topics_Design.md`. Application: v0.242.0,
feature-detected with no switch — a CRM without the field behaves exactly as
before, and on a CRM with it the single `topic` is retired from the
application (the column and its values stay).

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-09-26 03:34 UTC** — the plan applied by the shipped applier as the configuration administrator (dry-run fingerprint `1a404fc9c337`, one line: `create field CEvent.topics (multiEnum)`), the field read back from metadata by the applier and again as the org-wide key (`multiEnum`, ten options in order, `isCustom`); the copy run (dry run, then apply): one event, *AI Tools for Small Business*, `topics` ← `[Business Fundamentals]`, read back; four events had no topic to copy. **The nightly reset empties `topics` on every row** (the column is rebuilt from files, the rows restored from the snapshot) — re-run § 3 there before a live pass. | This document's § 2 and § 3 output, 10-09-26 03:33–03:36 UTC. |
| Production | **Owed** — Sunday 17:00 UTC slot, from inside the deployed web container. v0.242.0 reported by production at 23:47 on 10-08-26, so the container carries the plan and the copy script. | *Inferred:* production has `topic` and not `topics`; ten published recordings carry a topic each (09-14-26). The dry run in § 2 proves the first; the copy's dry run in § 3 counts the second. |
| Boston | **Owed** — with the release that carries v0.242.0. | *Inferred:* built from crm-test's files before this change. |

## 1. The naming rules

`CEvent` is a custom entity, so a field name is stored exactly as typed:
`topics` is `topics`. The applier computes and verifies this; read
`entityDefs.CEvent.fields.topics` from `GET /Metadata`, never a label.

## 2. The automated path — the field

From the repository root, as the configuration administrator (credentials in
`.env` as `ESPO_ADMIN_BASE` / `ESPO_ADMIN_USER` / `ESPO_ADMIN_PASS`; in a
deployed container they are the web component's provisioning admin). The
applier is `scripts/apply_crm_plan.py` (v0.241.2 — it ships in the image):

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

Dry run, which changes nothing and prints the plan and its fingerprint:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/cevent-topics.json
```

Expected: one `WOULD CHANGE` line, `create field CEvent.topics (multiEnum)`,
and fingerprint **`1a404fc9c337`** (a hash of the work, so the same on every
CRM that lacks the field). Then apply exactly that plan:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/cevent-topics.json --apply --expect 1a404fc9c337
```

A target that is not crm-test also needs `--production`. The applier rebuilds
and reads the field back; on crm-test the whole run took a few seconds.

## 3. The one-time copy — the values

`scripts/migrate_event_topics.py` copies each event's single `topic` into
`topics` where `topics` is empty; idempotent, dry-run by default, refuses to
run before § 2, and names a stored value outside the option list rather than
writing it (the CRM would refuse the whole write). It runs as the org-wide API
key — its role holds `CEvent` edit on every CRM — reading the address and key
from the application's own settings (`.env` from the repository; the process
environment in a container):

```bash
PYTHONPATH=. uv run python scripts/migrate_event_topics.py
```

```bash
PYTHONPATH=. uv run python scripts/migrate_event_topics.py --apply
```

The dry run lists `WOULD set '<event>': topics <- [<topic>]` per event to
copy and `SKIPPED` lines for the rest; the apply prints `set … - read back
OK` per event. On crm-test: one event copied, four skipped.

## 4. Verification — read the data back

1. As the **org-wide API key**: `GET /Metadata?key=entityDefs.CEvent.fields.topics`
   is `{"type":"multiEnum", …, "options":[…ten values…]}`; `GET /CEvent?select=name,topic,topics&maxSize=10`
   shows `topics` as a list on every event the copy named.
2. As a **real Marketing Admin Team member, not an administrator**, in Event
   Administration (no switch to turn on — the editor lights up when the CRM
   has the field): open a saved event, see **Topics** as a tick list where
   Topic stood and no way to type one, tick two topics, save, see both on
   the Overview facts and as two chips in the grid; give a published past
   event with a recording two topics and confirm the public library offers
   both and finds it by either, and its page's eyebrow names both; save an
   event with no topic ticked. Administrators bypass ACL, so an admin pass
   proves nothing about the role's field-level access to the new field.
   **Step page for crm-test, written 10-08-26:** https://claude.ai/artifact/Me5JXig7rzCzy9c6RwvMNi
   (Doug's private page; its section 1 re-runs § 3, because the nightly
   reset empties the values).

## 5. Then production

At the Sunday 17:00 UTC slot, by a human, from inside the deployed **web**
container (`[[do-app-console-scripting]]`), once production reports
**v0.242.0** on `/healthz`: § 2 dry run, § 2 apply (with `--production`),
§ 3 dry run (ten events expected), § 3 apply, § 4 step 1. Then § 4 step 2 as
a real non-admin. Record the result in § 0. Inside the container:

```bash
export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"
cd /app
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/cevent-topics.json
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/cevent-topics.json --apply --production --expect 1a404fc9c337
PYTHONPATH=/app .venv/bin/python scripts/migrate_event_topics.py
PYTHONPATH=/app .venv/bin/python scripts/migrate_event_topics.py --apply
```

Between the plan and the copy the editor already shows Topics (the field
exists) and an event opened in it shows none until the copy has run —
minutes, in the same window. The public library's filter is empty for the
same minutes.

## 6. Then Boston

With the release that carries v0.242.0: § 2 and § 3 against
`crm.bbmentors.org` from the build computer with Boston's configuration
administrator and Boston's settings file. Zero events are expected to copy.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-08-26 23:50 | Claude (Claude Code) | v0.242.0 live on production, crm-test and dev (23:47); the crm-test live pass and production's § 5 can run. |
| 1.0 | 10-08-26 23:55 | Claude (Claude Code) | Written after the crm-test run: field applied and verified, the copy run and read back. Production and Boston owed. |
