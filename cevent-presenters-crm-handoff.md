# CRM handoff — presenters on events (Track F, F4)

Last Updated: 10-08-26 11:04 · Revision 1.1 — see change log at the end.

One new record type, `CEventPresenter`, joining one event to one presenter and
carrying that presenter's biography, title, company, photo and display order
for that event; one new switch on the event, `showPresenterBios`; and the role
grants that let Event Administration staff search for, copy from and create
the people involved. Design and rulings:
`prds/events/CBM_Events_Presenters_Design.md`. Application: v0.241.0, dark
behind `EVENT_PRESENTERS` until this change has landed.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-08-26** (role script re-run 11:03 for the assignment permission) — plan applied by the shipping applier as the configuration administrator (fingerprint `5a78484e6b9c`), every entity, field and link read back from metadata; the role script applied and each grant read back; `GET /CEventPresenter?maxSize=1` as the org-wide key answers 200. | This document's § 2 and § 3 output, 10-08-26 01:12–01:25 local. |
| Production | **Owed** — Sunday 17:00 UTC slot, from inside the deployed web container. | *Inferred:* production has neither the entity nor the field; it has `CEvent.presenters` (the bare link) like crm-test. The dry run in § 2 proves it. |
| Boston | **Owed** — with the release that carries v0.241.0. | *Inferred:* built from crm-test's files before this change. |

## 1. The naming rules

Every name below is given **unprefixed**; EspoCRM prefixes it. The entity is
typed `EventPresenter` and stored `CEventPresenter` (typing `CEventPresenter`
would store `CCEventPresenter`). Fields on a custom entity are stored as
typed. The link on Contact is typed `presenterAppearances` and stored
`cPresenterAppearances`, because Contact is not custom. The applier computes
all of this; verify with `GET /Metadata`, never by reading a label.

## 2. The automated path — the whole change

From the repository root, as the configuration administrator (credentials in
`.env` as `ESPO_ADMIN_BASE` / `ESPO_ADMIN_USER` / `ESPO_ADMIN_PASS`; in a
deployed container they are the web component's provisioning admin):

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

Dry run, which changes nothing and prints the plan and its fingerprint:

```bash
PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/apply_crm_plan.py \
  scripts/plans/cevent-presenters.json
```

Read the plan it prints. Then apply exactly that plan:

```bash
PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/apply_crm_plan.py \
  scripts/plans/cevent-presenters.json --apply --expect <fingerprint>
```

The applier rebuilds and reads every name back. On crm-test the whole run,
including the `image` field (the applier's first), took under a minute and
reported nine changes and nine verifications.

## 3. The role grants — scripted, merge-only

Decision D1 (Doug, 10-08-26): presenter reads and writes run as the signed-in
user. The Marketing Admin Role held nothing on `Contact` or `CMentorProfile`.

```bash
PYTHONPATH=. uv run python .claude/skills/espo-crm-changes/scripts/run_with_admin.py \
  scripts/migrate_presenter_roles.py
```

Dry run first (above), then `--apply`. It grants: Marketing Admin Role —
`Contact` create yes, read all (edit stays **no**); `CMentorProfile` read all;
`CEventPresenter` create yes, read/edit/delete all; **and Assignment Permission
`team`** (found in the live pass 10-08-26: without it, `POST Contact` as a
Marketing Admin answered `403 Assignment failure: assigned user or team not
allowed` despite Contact create — EspoCRM stamps the creator's team on a new
record and then checks the role may assign it; the Mentor Role carries `team`,
the API role learnt the same lesson as #16). `CustomAppAPIRole` —
`CEventPresenter` read all. Nothing is ever lowered. It refuses to run before
§ 2 has created the entity. A CRM whose org-wide API user holds a role with a
different name needs that name in the script's table first — check with
`GET /User?where[0][type]=equals&where[0][attribute]=type&where[0][value]=api`.

## 4. Verification — read the data back

1. `GET /Metadata?key=entityDefs.CEventPresenter.links` shows `event` →
   `CEvent` and `contact` → `Contact`; `entityDefs.CEvent.links.eventPresenters`
   → `CEventPresenter`; `entityDefs.CEvent.fields.showPresenterBios` is `bool`.
2. As the **org-wide API key**: `GET /CEventPresenter?maxSize=1` is HTTP 200
   (a 403 means § 3 was missed and the public pages will show no presenters).
3. As a **real Marketing Admin Team member, not an administrator**, in Event
   Administration with `EVENT_PRESENTERS` switched on at `/setup`: open a saved
   event, add a mentor presenter and see the copied biography, title and
   photo; add a guest by a new email and confirm a `Presenter`-typed Contact
   appeared in the CRM; add the same email to a second event and confirm no
   second Contact. Administrators bypass ACL, so an admin pass proves nothing.

## 5. Then production

At the Sunday 17:00 UTC slot, by a human, from inside the deployed **web**
container (`[[do-app-console-scripting]]`): § 2 dry run, § 2 apply, § 3 dry
run, § 3 apply, § 4 steps 1 and 2. Then `EVENT_PRESENTERS` on at `/setup`, and
§ 4 step 3 as a real non-admin. Record the result in § 0.

## 6. Then Boston

With the release that carries v0.241.0: the same four runs against
`crm.bbmentors.org` with Boston's configuration administrator, from the build
computer using Boston's settings file. Switch stays off until Boston's staff ask.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-08-26 11:04 | Claude (Claude Code) | Live pass step 3.10 refused Contact create with an assignment failure; the role script now also sets the Marketing Admin Role's Assignment Permission to `team`, applied on crm-test 11:03. |
| 1.0 | 10-08-26 01:26 | Claude (Claude Code) | Written after the crm-test run: plan applied and verified, role grants applied and read back, org-key read proven. Production and Boston owed. |
