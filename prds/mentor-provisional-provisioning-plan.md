# Provision the mentor's email at Accepted-Provisional

**Status:** **built and shipped in v0.204.0** (2026-08-17), verified by tests
only — the live pass is `OPEN-ITEMS.md` #22, and it waits on the All Members group
address, the `admin.directory.group` delegation scope, and "Create missing
mailboxes" being on for the environment. This document is now the design record:
the rulings and the reasoning stand, and where the built code differs it is noted
inline.
**Date:** 2026-08-17
**App:** Mentor Administration (`/mentoradmin`)

## The change Doug asked for

Split today's single provisioning event into two, so CBM can talk to a mentor
during their provisional period. `Accepted-Provisional` is a **signal status**,
not a resting one: it means *this mentor has been accepted and still needs a
Google account*. The app acts on it and then advances the record.

| Save leaves the mentor at | What the system does |
|---|---|
| **`Accepted-Provisional`** | Create the `firstname.lastname@cbmentors.org` **Google Workspace account**, add it to the **All Members Google Group**, and then **set `mentorStatus` to `Provisional`**. Nothing else in EspoCRM — no login User. |
| **`Provisional`** | Nothing. This is the resting state: the mentor has their account and is serving their provisional period. (A `Provisional` mentor with a blank `cbmEmail` is treated as a recovery case — see below.) |
| **`Approved` / `Active`** | Exactly what happens today: ensure the mailbox, then create the **EspoCRM login User**, place it in the Mentor Team, link it to the profile and the Contact, back-fill `cbmEmail`. **Never flips the status back to `Provisional`.** |

Doug's rulings (2026-08-17):

- The two provisional statuses describe the same period; the difference is
  **whether the Google account exists yet**. `Accepted-Provisional` → create it
  and move them to `Provisional`.
- "Update Mentor Status" should **report** group membership.

## What exists today (so the change is small)

`mentoradmin/service.py:568 provision_mentor_user_steps` is already a two-part
generator, and the parts are in the right order:

1. **mailbox part** (`service.py:619–662`) — resolve the address, check Workspace
   (`GoogleDirectory.mailbox_status`), and if MISSING **create** it when
   `create_mailbox` is on (temp password + change-at-first-login + the mentor's
   personal address as recovery), then poll until it is live. A MISSING mailbox
   with creation off is a hard stop; an UNKNOWN check fails open.
2. **login part** (`service.py:664–774`) — the EspoCRM User, the team, the
   profile link, the Contact stamp, the `cbmEmail` back-fill.

So the work is *not* "write mailbox creation" — it is **making part 1 runnable on
its own, at a different status, and adding the group and the status advance**.
Three things are genuinely new: Google **group membership** (no group API exists
in `core/google_directory.py` today), the **provisional trigger**, and the
**`Accepted-Provisional` → `Provisional` write**.

Who drives it today: the frontend save (`mentoradmin/frontend/app.js:1341
needsProvisioning`) fires the streaming `POST /mentors/{id}/provision`
(`router.py:598`) whenever a saved mentor is Approved/Active with no linked User.
The long-running mailbox flow lives **only** in that SSE stream — the inline
`update_mentor` fallback deliberately passes `create_mailbox=False`
(`service.py:425–432`) because a browser-less PUT has nowhere to show the temp
password. That division stays.

## Design

### 1. One endpoint, mode chosen server-side from the mentor's status

Rather than a second endpoint or a client-supplied mode, `POST
/mentors/{id}/provision` derives what to do from the mentor's **effective
status** — so the state machine lives in one place and the frontend stays dumb:

- `Accepted-Provisional` → **mailbox + group + advance to `Provisional`**, then
  stop with a final `done` event. No EspoCRM User.
- `Provisional` → the same mailbox + group steps (they are idempotent), but **no
  status write** — they are already there. Reached only via the recovery trigger.
- `Approved` / `Active` → mailbox + group **+** the EspoCRM login (today's flow),
  and **no status write** — flipping an Approved mentor to Provisional would be a
  demotion, and a mentor may legitimately jump straight from
  `Accepted-Provisional` to `Approved`.
- anything else → today's error, reworded to cover both events.

Implementation: extract the mailbox part of `provision_mentor_user_steps` into
`provision_mentor_mailbox_steps(...)`, which yields the same `_step(...)` events
and carries out the resolved address, whether it created the mailbox, and whether
the account is **confirmed** to exist. `provision_mentor_user_steps` delegates to
it and then continues into the login part, so the Approved/Active path is
byte-for-byte the behaviour it has now (including the MISSING-and-creation-off
hard stop). The router picks which generator to iterate and whether the status
advance applies.

Idempotency is what makes this safe: mailbox EXISTS → "found"; group add
already-a-member → success; status already `Provisional` → no write. A re-run is
a no-op, and a mentor who skips the provisional stage still gets everything. That
preserves the recovery-friendliness `update_mentor` was deliberately built for
(`service.py:361–372`).

### 2. The status advance — when exactly

A new final step in the provisional flow, `_step("status", …)`, writing
`{"mentorStatus": "Provisional"}` through the **staff user's** client (they just
saved that same field, so no privilege escalation is involved).

It fires **only** when all of these hold:

- the effective status is `Accepted-Provisional`, **and**
- the Google account is **confirmed** — either we created it and the poll saw it
  become active, or the pre-flight check returned EXISTS (an admin had already
  made it).

It does **not** fire when:

- the mailbox check returned **UNKNOWN** (the fail-open path). The login flow
  proceeds on UNKNOWN and keeps doing so, but we must not record "has a Google
  account" on a guess during a Google outage — the mentor stays
  `Accepted-Provisional` and the next run advances them.
- the create succeeded but the mailbox **never became active** within the poll
  window. That already yields an error step telling staff to save again; the
  re-run finds it EXISTS and advances then.
- the **group add failed**. The group is a distribution concern, not the
  account's existence — the account is real, so the status advances and the group
  failure is warned (see §3).

Guard on the enum: read the live `mentorStatus` options before writing (the same
metadata read `_sanitize_enum_changes` uses) and, if `Provisional` is not among
them, yield a warning step and leave the status alone rather than 400 the write.
The two CRMs drift ([[crm-test-schema-drift]]) and a failed status write must not
read as a failed provisioning.

**Audit.** The app is now changing a mentor's status on its own, and EspoCRM does
not audit `mentorProfile`/status changes in a way that distinguishes an app write
from a hand edit ([[espo-history-app-writes-indistinguishable]]). Per the repo
convention, add a `core/action_log.record_action(...)` call at the router layer
for the provisioning run, carrying the mentor, whether a mailbox was created,
whether the group add succeeded, and the `Accepted-Provisional → Provisional`
transition. This endpoint records nothing today — it is the highest-privilege
flow in the app and the one the action-history plan already lists as owed
(`prds/action-history-plan.md:329`).

### 3. Group membership — new in `core/google_directory.py`

Add `add_group_member(group_email, member_email)`:

- `POST https://admin.googleapis.com/admin/directory/v1/groups/{groupKey}/members`
  with `{"email": member, "role": "MEMBER"}`.
- **409 = already a member → success** (same idempotency contract as
  `create_user`'s 409).
- 404 → raise `GoogleDirectoryError` naming the group address, because a typo'd
  group must not read as "added".
- New scope constant `DIRECTORY_GROUP_SCOPE =
  https://www.googleapis.com/auth/admin.directory.group`, requested only for this
  call, exactly as `create_user` requests the write scope only for itself.

**Failure policy.** The group add is a step of its own in the status window and is
**non-fatal**: a mailbox that exists but is not yet in All Members must not block
the status advance or a later approval, and the message tells staff to add it by
hand (or just re-run). This matches how the Contact stamp is handled in the login
part (`service.py:746–752`). It runs only *after* a confirmed mailbox, never
before.

### 4. Configuration — the group address

The Google integration has **two config sources** and the DB one wins
(`core/google_directory.resolve_google_directory`), so the group address must be
added to both or it will silently disappear the moment Email Setup is used:

- **env**: `GOOGLE_MEMBERS_GROUP` (default `""`) in `core/config.py`, alongside
  `google_create_mailbox`; registered in `core/settings_registry.py` under the
  Integrations group so it is settable at `/setup` (not a secret, not boot-read).
- **in-app Email Setup**: a `members_group` key in the stored config
  (`core/app_config.py` get/set are schemaless dicts, so no migration), surfaced
  in `GET/PUT /mentoradmin/setup/google` (`router.py:670`, `:710`, `:728`) and as
  one text input on the Email Setup panel (`frontend/app.js:1490–1538`).
- `ResolvedGoogle` gains `members_group: str` from the same precedence chain — so
  `resolve_google_directory` stays the single place deciding which Google config a
  request uses.

**Empty address = the group step is skipped entirely** (one "not configured" note
in the status window, never an error). The status advance still happens: the
account exists, which is what `Provisional` asserts. That keeps the feature dark
until Doug supplies the address, with no flag of its own.

### 5. Trigger in the UI

`needsProvisioning(m)` (`frontend/app.js:1341`) becomes two questions:

```
needsEmailAccount(m)  → status is "Accepted-Provisional"
                        OR (status is "Provisional" AND no cbmEmail)   // recovery
needsLogin(m)         → status is Approved/Active AND no assignedUserId  // today's rule
```

`doSave` (`:1353`) starts the stream when either is true. The recovery arm mirrors
the existing "already Approved but never got a user" behaviour, and because the
flow is idempotent an extra run costs one Directory lookup.

Cosmetics that must follow, or the screen lies to staff:

- the modal title is the hard-coded "Setting up the mentor's login" (`:1423`) —
  it becomes status-dependent ("Setting up the mentor's email account").
- the "Saved. Setting up the mentor's login…" notice (`:1367`) likewise.
- the temp-password box (`showCreds`, `:1457`) already renders from
  `result.tempPassword` and needs no change — which is the whole reason the
  provisional run stays inside this SSE window. **The mentor's temp password must
  be shown to a human**, so this can never move into the worker or a bulk sweep.
- the modal's close already re-opens the mentor (`:1433 openMentor`), so the new
  `Provisional` status and the badge refresh on close with no extra work — and
  the detail view is also what self-heals `recordStatus` after the flip, since
  completeness persists on view as well as on save.

### 6. `update_mentor`'s inline path and the "disabled" notice

- The inline (JS-off / API) path keeps provisioning **only** for Approved/Active
  and keeps `create_mailbox=False`. A provisional save straight over the API does
  nothing Google-side and does not advance the status — by design, since it
  cannot create the account it would be asserting.
- The `provision: {ok: false, disabled: true}` branch (`service.py:455–469`),
  which stops an approval from *looking* successful when provisioning is switched
  off, is extended to `Accepted-Provisional` — otherwise a save on a server with
  `MENTOR_PROVISION_USERS` off silently implies an email account was created, and
  the mentor sits at a signal status nobody is acting on.

### 7. "Update Mentor Status" — report, never create

Doug's ruling: the sweep reports group membership. `verify_mentor_status`
(`service.py:804`) already verifies the login User and the mailbox per mentor and
reports `unavailable` when the Directory is unconfigured. Add:

- a **group membership** check (`groups.members.hasMember`, or the get-member call
  treating 404 as "not a member"), reported per row and `unavailable` when no
  group address is configured — same non-failure contract as the mailbox check.
- a row flag for **`Accepted-Provisional` with no mailbox** — a mentor stuck at
  the signal status is precisely what this sweep should surface.

It still **creates nothing**: creation stays per-mentor and interactive because of
the temp password.

### 8. Deliberately NOT in scope

- **Completeness / `recordStatus` rules are untouched.** A provisional mentor with
  no mailbox is not "incomplete" — completeness stays the Active-mentor contract
  (`service.py:229–242`).
- **No new CRM field.** `cbmEmail` records the address and `mentorStatus` records
  the stage; nothing else is needed.
- **No change to what `Provisional` means elsewhere.** `portal/birthday.py:56`
  already treats both provisional statuses as greetable members, which stays
  correct.

## A wrinkle to be careful about: `cbmEmail` and the login-reuse guard

Today `cbmEmail` is written **inside the login part**, immediately before the User
create (`service.py:687–695`), and the presence of `cbmEmail` is what the
duplicate-login guard reads: a stored `cbmEmail` means "this mentor was assigned
this address before, so a User with that userName IS their login — reuse it";
blank means "fresh assignment, so a userName clash is a *different person* —
suffix it to `jane.doe2@`". That guard is what stopped the
`doug.bower2`/`doug.bower3` pile-up.

Creating the mailbox at provisional time moves the `cbmEmail` write earlier, which
**weakens that signal**: at approval every mentor now arrives with a `cbmEmail`,
so the reuse branch always fires. For a brand-new mentor the lookup finds no User
and it falls through to create — correct. The bad case is two same-named mentors:
mentor B would reuse mentor A's login instead of getting `jane.doe2@`.

Fix, in the same change: resolve the address **once, uniquely across both
directories**, in the mailbox step — a candidate must be free as a Workspace
mailbox *and* free as an EspoCRM `userName` before it is written to `cbmEmail`
(reusing `_unique_user_name`'s numbering). Then any User later found under that
userName can only be the login we minted for this mentor, and the guard is sound
again. This also cleans up an existing inconsistency: today a suffixed login gets
`userName = jane.doe2@…` while `cbmEmail` and the User's `emailAddress` are left
at the unsuffixed `jane.doe@…`.

## Tests

`tests/test_mentoradmin.py` already covers the provisioning matrix with fakes
(`test_missing_mailbox_blocks_when_create_disabled`,
`test_existing_mailbox_allows_provisioning`, `test_unknown_mailbox_fails_open`,
`test_steps_missing_creates_then_provisions`, the stream tests at `:1143`). New
cases:

1. `Accepted-Provisional` runs the mailbox steps, **stops before any User create**
   (assert the fake admin client saw no `User` create) and writes
   `mentorStatus="Provisional"`.
2. An **already-existing** mailbox at `Accepted-Provisional` still advances the
   status (no create, no duplicate).
3. **UNKNOWN** mailbox check at `Accepted-Provisional` → no status write, mentor
   stays put.
4. Mailbox created but **never becomes active** → error step, no status write.
5. `Approved`/`Active` **never** writes `Provisional` — including a mentor coming
   straight from `Accepted-Provisional`. This is the demotion guard.
6. `Provisional` with a blank `cbmEmail` runs the mailbox steps and writes no
   status.
7. Group add: attempted with the configured address; 409 counts as success; a
   failure yields a warning step but the flow still reaches `done`, still advances
   the status, and on the Approved path still creates the login.
8. An empty `members_group` skips the group step entirely.
9. Address resolution skips an address already taken as a mailbox *or* a userName.
10. `resolve_google_directory` precedence for `members_group` (DB over env).
11. `Provisional` missing from the live enum → warning step, no 400, provisioning
    still reported successful.
12. Approved/Active behaviour is otherwise unchanged — the existing tests must
    pass untouched. That is the regression guard.

## External prerequisites (not code — these gate the live test)

1. **The All Members group address.** Still outstanding.
2. **The group scope must be authorized for domain-wide delegation** —
   `.../auth/admin.directory.group` added to the service account's DWD grant in
   the Workspace Admin console, and the impersonated `GOOGLE_DELEGATED_ADMIN`
   must hold group-admin privilege. Without it the group add 403s
   `unauthorized_client`, the same failure shape as
   [[gmail-delegation-needs-licensed-mailbox]]. The read-only and read-write
   *user* scopes are already granted; this is a third scope.
3. **`GOOGLE_CREATE_MAILBOX` (or Email Setup's "Create missing mailboxes") must
   actually be on** in the target environment — the overlays are gitignored, so
   check at `/setup` per environment. With it off, an `Accepted-Provisional` save
   reports the mailbox missing and stops, which is correct behaviour but not the
   intended outcome.
4. **Both statuses must exist in prod's `mentorStatus` enum.** Verified on
   crm-test 2026-08-17 (live options: `Prospect · Candidate · Under Review ·
   Accepted-Provisional · Provisional · Approved · Active · Paused · Inactive ·
   Dormant · Resigned · Retired · Declined · Terminated`). Prod is unverified from
   here and the two CRMs drift. Note the value is **hyphenated** —
   `Accepted-Provisional`, not "Accepted Provisional".

## Documentation to update

- `mentor-administration.md` — the two-stage flow and what each status means to
  staff; this is the guide they will actually read when a mentor sits at
  `Accepted-Provisional`.
- `intake-processing-overview.md:54` — currently says approval "flips the status
  and provisions the @cbmentors.org login", which becomes two events.
- `CLAUDE.md` Mentor Administration section — the approval→provisioning bullet
  gains the provisional stage and the status advance.
- `CHANGELOG.md` + a rolling-window entry.

## Rollout

No new feature flag is needed and none is wanted: `MENTOR_PROVISION_USERS`
already gates the whole provisioning subsystem and an unset
`GOOGLE_MEMBERS_GROUP` makes the group step inert. The one behaviour change that
ships live is the provisional trigger plus its status write — bounded to a status
that today does nothing at all, and the status write is guarded on a *confirmed*
account.

Verify on **crm-test as a real non-admin Mentor Administration user**: saving a
mentor at `Accepted-Provisional` creates the mailbox, adds it to the group, shows
the temp password, creates **no** EspoCRM User, and leaves the record at
`Provisional`; a later `Approved` save then creates the login reusing that same
address, with no second mailbox, no suffixed duplicate, and no demotion back to
`Provisional`.

Do that pass against the **real Google Workspace** with a throwaway name — unlike
Zoom and the YouTube playlist there is no test tenant, so agree the disposable
address with Doug first, and delete both the mailbox and the group membership
afterwards.

## What the build changed from this plan (v0.204.0)

Three departures, all small:

- **The address reservation is stronger than "no User holds that userName".** It
  also refuses an address another `CMentorProfile` already carries as its
  `cbmEmail` — two same-named mentors both reserving `jane.doe@` before either is
  approved would otherwise collide. A merely *existing mailbox* is still not
  "taken": a pre-created mailbox is the long-standing normal case, and the caller
  reads EXISTS as "found — it's theirs".
- **`cbmEmail` is written by the mailbox stage**, as soon as the account is
  confirmed, rather than by the login stage. That preserves the P2 rule (the
  address is persisted before any User exists) and means the provisional run leaves
  the record carrying the address it just created.
- **A failed `cbmEmail` write is terminal**, not best-effort: an account that
  exists but is recorded nowhere would be re-derived — possibly re-created — on the
  next run, so the run stops and says exactly that.

The group step also emits its own `group` line in the status window (so a failure
is visible as a step rather than buried in the final message), and the sweep's
`needsEmailAccount` flag is surfaced as a named call-out above the results table,
not just a column.
