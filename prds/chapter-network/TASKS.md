# Chapter network — open work

Every entry below has the same three parts, in the same order:

1. **What this is** — the issue in plain language, long enough to be understood
   by someone who has not just read the plan.
2. **The decision**, where there is one — the options, what each costs, and a
   recommendation.
3. **Steps** — what to actually do, in order.

Newest work goes to the top of its section. Finished work moves to *Closed* at
the bottom **with the evidence**, not deleted.

**What belongs in this file:** work owed by a chapter-network phase.
**What does not:** a Cleveland defect that chapter work merely *found*. Those go
to `OPEN-ITEMS.md`, where the people who fix Cleveland defects are looking. There
is a table at the end of this file linking to them.

---

# Part 1 — Ruled, and what follows

**Doug ruled D1, D2 and D3 on 2026-08-26, and the cadence half of D4 the same
day.** They are recorded in [DECISIONS.md](DECISIONS.md); what each one now
*obliges* is below. **No decision is currently blocking work** — the one still
open (which machine hosts staging) does not need answering until Phase 6 is in
sight.

---

## A1. Convene the CRMBuilder requirements session — by 2026-09-19

**Owner: Doug. This is the only dated commitment in the project.**

> **The decision half is DONE (2026-08-31):** Doug ruled the applier a
> **CRMBuilder product capability** — see DECISIONS. The session is now a
> *drafting* session, not a decision session: turn the two briefs
> (`prompts/crmbuilder-chapter-network-prompt-v0.1.md` and
> `prompts/crmbuilder-deployment-updates-requirements-v0.1.md`, per A3) into
> confirmed CRMBuilder requirements, headless execution included. The date
> stands.

### What this is

**Ruled (D2, 2026-08-26): the trigger date stands at 2026-09-19.**

Phase 1's biggest deliverable is the **applier** — the program that takes a
description of the correct CRM configuration and makes a chapter's CRM match it.
There are two ways to get one: adopt **CRMBuilder** (a separate repo that already
has most of the machinery, including an **Audit** that reverse-engineers a live
CRM — the only existing answer to the roles problem in R4), or **build our own**
by generalizing `scripts/migrate_event_schema.py`.

We cannot simply pick. CRMBuilder is governed requirement-first: its shape is not
ours to assume, and we cannot oblige it to grow an interface it has not agreed
to. Only a requirements session with Doug can answer its two questions — is the
network standard a CRMBuilder *product capability* or a *CBM-network artifact
that merely uses CRMBuilder*, and will it support headless execution.

**What happens if the date passes with no session:** Layer 3 becomes permanent.
We build our own applier in full, and the sunk cost is accepted **deliberately
rather than by drift** — that is the entire purpose of having a date. If
CRMBuilder is then adopted anyway, roughly two to three weeks is genuinely thrown
away: the directive executor, the plan-fingerprint plumbing and their tests. The
conformance check, the desired-state definition, the exit-code contract, the JSON
result and both version stamps are *not* at risk — they are the app-derived half
this repo owns under either answer, which is why the build order does them first.

### Steps

1. Schedule the session. It needs roughly half a day.
2. Run it from `prompts/crmbuilder-chapter-network-prompt-v0.1.md`. It is ready
   and needs no preparation — its § *What the consumer requires* already carries
   C1 through C10 by number, and it now cites
   [interface-contract.md](interface-contract.md) so that file can be handed over
   on its own.
3. Record the answer in [DECISIONS.md](DECISIONS.md) and update
   [phase-1](phase-1-crm-config.md) § *The decision trigger* to name which layer
   is the plan of record.
4. Either way, B1 unblocks the same day.

**If 2026-09-19 arrives with no session held**, that is not a failure to escalate
— it is the ruling taking effect. Start B1 as Layer 3 and note the date it fired.

---

## D4. Which machine is the staging tenant

**Half ruled. The cadence is settled; the machine is not — and it is not urgent.**

### What this is

**Ruled (2026-08-26): the release train leaves WEEKLY**, the soak being the week
itself, with a security fix allowed to bypass the cadence but never staging. That
was the half of D4 that shaped Phase 2's design, and it is now recorded in
[phase-2](phase-2-release-train.md).

What is still open is **which machine soaks the release**. CBM's crm-test app
already does three jobs — pre-production review gate, training sandbox, and
release-test environment — with a nightly reset keeping them from ruining each
other.

| Option | Assessment |
|---|---|
| **Repurpose CBM's crm-test** | Cheapest, and it already has the reset machinery and the training data. **But it makes CBM's sandbox the network's gate** — the "Cleveland as landlord" shape ruling 1 exists to avoid — and it would be that machine's fourth job. |
| **Stand up a services-org instance** | Costs a droplet and a DO app. Keeps the guinea pig a machine the co-op owns, which is what ruling 7 actually says. |

**Recommendation: a services-org machine eventually, crm-test as the interim, and
do not decide yet.** Standing one up is only worth the money when there is a
second chapter to soak *for*. Until then crm-test is what exists and it works.

**This blocks almost nothing.** Tag cutting, the image stamp, `deploy_on_push`
and pinned-tag deploys are all independent of where staging lives — only the soak
step itself is not.

### Steps

1. When Phase 6 comes into view, decide.
2. Record it in [DECISIONS.md](DECISIONS.md) against proposal 2, which currently
   argues the opposite of my present recommendation and says so.

---

# Part 2 — Ready to build

## R10. The release branch, and a `promote` script for one deployment

**Done except the fleet half of step 4 — and used for real the same day.**
`release` exists on origin and the weekly cut fast-forwards it; `scripts/promote.py`
promoted `lakeside-intake` to **v0.217.0** on 2026-08-31 — the first deployment
ever to report a non-null `releaseTag` (`/healthz`: version 0.217.0, releaseTag
v0.217.0, all three components on the `release` branch). One defect found live
and fixed on the spot: the guard compared the branch against the annotated
**tag object** instead of its peeled commit and refused its own success case
(`73b97e9`). `--status` is the per-app policy-vs-spec signal; the fleet-wide
"policy says Latest Stable but the spec disagrees" detector needs the policy to
live somewhere first — CRMBuilder's Deployment record (A3).

### What this is

Decided 2026-08-31 ([DECISIONS.md](DECISIONS.md) log): chapter apps follow a
`release` branch that the weekly cut fast-forwards to the tag, and the Update
button in CRMBuilder (proposal 8) promotes one deployment by **two** operations
— set `RELEASE_TAG=<tag>` on every component of its spec, then trigger a
deployment. This repo owes the consumer's half.

### Steps

1. Create the `release` branch at `v0.216.4` (the last tag every live app is
   past) and add the fast-forward to `scripts/cut_release.sh` — printed, not
   pushed, like the tag itself.
2. Write `scripts/promote.py <app-id> <tag>`: read the spec (`doctl apps spec
   get`), set `RELEASE_TAG` on every component (create it where absent, scope
   `RUN_AND_BUILD_TIME`), confirm the tracked branch is `release`, apply, create
   a deployment, wait, re-read `/healthz`, and print the before/after
   `releaseTag`. Dry-run by default. This is the worked example the CRMBuilder
   button is specified against, and the way `lakeside-intake` gets v0.217.0.
3. Mind the overlay trap: never regenerate `.do/app.prod*.yaml` from the live
   spec to do this ([[overlay-regen-encrypts-secrets]]) — `promote.py` works on
   the live spec via the API and touches only `RELEASE_TAG`.
4. Add the detector: a read-only comparison of "policy says Latest Stable" against
   the live spec's `deploy_on_push` and branch, reported as the fleet-console
   signal Phase 2 § Open asks for.

---

## A3. Hand the deployment-updates requirements to CRMBuilder's process

**Owner: Doug.** `prompts/crmbuilder-deployment-updates-requirements-v0.1.md`
is candidate input for a requirements session in the CRMBuilder repo: the
Deployment record (D1), the *Updates* policy (D2), the Update / Update-all
button with its two guards (D3), the fleet view (D4) and what must not be
required (D5). It should be run together with A1 — both carry the same boundary
question (product capability or CBM-network artifact) and should get one answer.

## R7. Rule on the extensions — are Advanced Pack and Google Integration part of the standard?

**RULED 2026-08-31: IN the standard** (DECISIONS log). Follow-through done the
same day: [chapter-values.md](chapter-values.md) § G and
[phase-6](phase-6-first-chapter.md) step 2 now state it unconditionally. Step 1
(does anyone actually use a Report or a BPM flowchart?) was overtaken by the
ruling and not performed.

### What this is

The dress rehearsal (§ Closed, 2026-08-31) found that **crm-test's twelve roles
name scopes from two installed extensions** — `Report`, `ReportCategory`,
`BpmnFlowchart`, `BpmnProcess`, `BpmnUserTask` from the paid **Advanced Pack
3.12.1**, and `GoogleCalendar`, `GoogleContacts` from **Google Integration
1.8.4** — and EspoCRM 10 **refuses a role that names a scope the instance does
not have** (HTTP 400, whole role rejected). Nothing in this project's documents
had listed either extension as part of the standard; the roles simply assumed
them. 71 role×scope entries were stripped to get the roles on, and the applier
correctly exited 4 (*unapplyable*) rather than 0.

### The decision

Either answer works; what does not work is not choosing.

- **In the standard.** Every chapter installs both extensions before the roles
  are applied. Cost: an Advanced Pack licence per instance (paid, per site), and
  the extension install becomes a step in the runbook (it is a file upload to
  Admin → Extensions, or the droplet). Benefit: the roles apply verbatim and the
  reports/BPM features the CRM team may be using stay available.
- **Out of the standard.** The roles are filtered to core scopes per target —
  exactly what `scripts/rehearsal/apply_api_half.py` does today — and the
  extension scopes become a Cleveland-only local addition. Cost: Cleveland and
  the chapters differ, which ruling 4 says must not happen; the drift detector
  has to know about it.

**Recommendation: in the standard**, because ruling 4 leaves no room for a
"Cleveland-only" anything, and because the alternative makes the roles capture
a per-target computation forever. If the Advanced Pack is not actually used
(nobody has checked whether any Report or BPM flowchart exists on either CRM),
the cheaper answer is to **remove its scopes from the roles on crm-test and
prod** and drop the pack — but that is a removal, so it is a deliberate job
under the additive-only rule, not something the applier does.

### Steps

1. Read whether either CRM holds a Report, a ReportCategory or a BpmnFlowchart
   record (admin, both instances).
2. Rule.
3. If *in*: add both extensions (name, version) to
   [chapter-values.md](chapter-values.md) § G as standard, and to
   [phase-6](phase-6-first-chapter.md) step 2 as a runbook step before the
   roles. If *out*: file the scope removal as a Sunday-slot job.

---

## R8. The file half is three trees, and it needs a shell — fix the runbook

### What this is

The rehearsal carried the file half by copying crm-test's Entity Manager tree
and rebuilding, and it worked cleanly across a major version (9.3.4 → 10.0.6).
Three things it learned that the plan did not say:

1. **There are three trees, not one.** `custom/Espo/Custom/` (entities, fields,
   links, layouts, labels, formulas) **and `client/custom/src/`** — the
   CBM navbar view that `clientDefs/App.json` names. Without the second the
   CRM's own UI renders a blank page. (The extensions' `client/custom/modules/`
   is theirs, not ours.) The third is the database-side API half.
2. **It needs a shell on the droplet**, which the CRMBuilder deploy gives nobody
   unless *Extra SSH keys* is ticked. The DO web console is the fallback.
3. **The on-disk path differs by installer version** — `data/espocrm/custom`
   on crm-test, `data/espocrm/persistent/custom` (+ `custom-client`) on the
   10.x installer.

### Steps

1. Amend [phase-6](phase-6-first-chapter.md) step 2 and
   [crm-update-runbook.md](crm-update-runbook.md) § 7 — **done 2026-08-31** in
   the same commit as this entry.
2. When the applier (B1) is designed, its file half is "two trees + rebuild",
   and the extension package the phase proposes must carry both.
3. Ask CRMBuilder (A1 session) whether the deploy run's SSH key can be shared
   with the services org, or *Extra SSH keys* made the default.

---

## R9. Validate a roles capture against the target before writing it

### What this is

crm-test's `Standard User` role carries a **field-level entry for
`Account.cCompanyPartnerProfile`**, a field deleted on 2026-08-14 when that link
was rebuilt many-to-one. crm-test tolerates the stale entry; EspoCRM 10 rejects
the entire role for it. CRMBuilder's Audit skips such entries silently
("has no design field — skipped"). So a capture is not a definition until it has
been checked against the target's `entityDefs`.

### Steps

1. `scripts/capture_roles.py` (R4) should flag field-level entries whose field
   is not in the source's own `entityDefs` — a stale entry is a source defect.
2. The applier's role directive filters `fieldData` against the target's
   `entityDefs`, as `apply_api_half.py` now does, and reports each strip.
3. Clean the stale entry out of `Standard User` on crm-test and prod (a
   removal — Sunday slot).

---

## A2. Report the rehearsal's CRMBuilder findings to that repo's process

**Owner: Doug.** Four findings belong to CRMBuilder and are not fixed from here:

- The deploy installs the **current EspoCRM (10.0.6)**; Cleveland runs 9.3.4. A
  chapter starts a major version ahead unless the deploy pins a version.
- The deploy leaves the services org **without a shell** unless *Extra SSH
  keys* is ticked (R8).
- The Audit's **email-template listing returns HTTP 400 on 10.0.6** for every
  parent type, so it reports 0 templates where 2 exist.
- The Audit **silently skips** a field-level role entry that names a link or a
  deleted field (R9).

No decision needed. Listed in the order the plan's own build sequence argues for
— the things that survive whatever A1 concludes come first.

---

## R0. Build the `CNetworkStandard` entity in both CRMs

### What this is

**Ruled (D1, 2026-08-26): the CRM's configuration version lives in a new
single-record custom entity, `CNetworkStandard`.**

Every chapter runs its own EspoCRM, and the point of Phase 1 is that they all
hold the same configuration. That needs each CRM to carry a stamp saying "I am
running configuration version X, applied on date Y" — the CRM's equivalent of the
Alembic version row in the app's Postgres. **No such stamp exists anywhere
today**, so "is this chapter's CRM up to date?" currently has no answer short of
a full field-by-field sweep.

The two rejected alternatives are worth remembering, because both look cheaper:
storing it under EspoCRM's admin **Settings** would need an admin login just to
*read* the version, dragging admin credentials into application runtime — and a
read-only probe of crm-test on 2026-08-24 proved that wall is real, with the
org-wide API key returning HTTP 200 on `Team` and `EmailTemplate` and **403 on
`Role`**. A **`CActionLog`** row is append-only history, and answering "what
version is this" by scanning a log is the wrong shape and gets slower forever.

**Nothing writes to this until the applier exists (B1), and building it now is
deliberate.** An instance holding the entity with no row reads as *"configured to
report, never applied to"* — the honest state of every instance today — and it
lets R1 ship against a real scope rather than a hypothetical one.

The build is the smallest in the repo: **one entity, six fields, no links, no
enums, no formulas.** That is the design, not an omission.

### Steps

The full specification is written: **`cnetworkstandard-entity-crm-handoff.md`**
at the repo root, in Entity Manager vocabulary. Follow
[crm-update-runbook.md](crm-update-runbook.md) to apply it — this is the first
change to go through that procedure. In outline:

1. Create the entity on **crm-test**, typing the name **`NetworkStandard`
   without the `C`** — EspoCRM prepends it unconditionally, and typing
   `CNetworkStandard` yields `CCNetworkStandard`. That is exactly how the grant
   build produced `CCGrant`.
2. Add the six scalar fields; type `Base`, stream off, no navigation tab.
3. Grant the org-wide API role **read** on the new scope. This is the step that
   is easy to miss and it is the whole reason this option was chosen.
4. **Verify with the API key, not an admin session** — an admin bypasses ACL, so
   an admin check proves nothing about step 3. `GET /api/v1/CNetworkStandard`
   must return **HTTP 200 with `total: 0`**; a 403 means the grant was missed and
   a 404 means the name landed wrong.
5. Confirm `entityDefs.CNetworkStandard` in `GET /Metadata` — six fields, empty
   `links`. If it reads `CCNetworkStandard`, delete and rebuild rather than
   renaming around it.
6. ~~Repeat the whole build on production and verify the same way~~ —
   **done 2026-08-31**; R0 is complete on both CRMs. See § Closed.

---

## R2. Wire the conformance check as a deploy gate on crm-test

### What this is

`scripts/preflight_crm.py` was rewritten on 2026-08-21 into a real conformance
check: it asks a live EspoCRM whether it holds everything this application
requires, needs only the org-wide API key, distinguishes *absent* from
*forbidden* from *unreachable*, and exits 0 / 1 / 3 accordingly with `--json` for
machines. It has been run by hand against both live CRMs.

**Nothing runs it automatically.** So the failure it exists to prevent — a chapter
deploying app code that expects a CRM configuration its CRM does not hold — is
still entirely possible. Wiring it as a `PRE_DEPLOY` job makes the deploy itself
fail when the CRM has drifted.

Two design points already settled, both worth understanding before you wire it:

- **The gate is a CHECK, never an apply.** Read-only, org-wide API key, no admin
  credentials anywhere near the deploy path. Applying is a release-train step
  (Phase 2) so that CRM admin passwords never live in a chapter's app spec.
- **Unreachable fails closed, but distinctly** (exit 3). A gate that passes when
  it could not check is a gate that reports success for an unknown, and silent
  passes are this codebase's documented failure mode.

A **break-glass** is mandatory, not a nicety. Without one, the first CRM outage
during an urgent app fix produces an undocumented bypass invented under pressure.

### Steps

1. Add a bypass to `scripts/preflight_crm.py`: if `CRM_GATE_BYPASS` is truthy,
   run the check as normal, log the result at WARNING with an unmistakable
   "GATE BYPASSED" line, and exit 0. Same shape as the existing
   `SETTINGS_OVERRIDES=false` break-glass. Add a test that it exits 0 on an
   instance that would otherwise exit 1.
2. Edit `.do/app.prod.yaml` (this is the **crm-test** overlay — the filenames are
   confusing; `app.prod-crm.yaml` is production). Add a second entry to the
   existing `jobs:` list, alongside `migrate`:
   `kind: PRE_DEPLOY`, `name: crm-conformance`,
   `run_command: .venv/bin/python scripts/preflight_crm.py --json`,
   `dockerfile_path: Dockerfile`, same `github:` block, and two envs —
   `PREFLIGHT_CRM_URL` and `PREFLIGHT_CRM_KEY`, set to the same values the web
   service already carries as `ESPO_BASE_URL` / `ESPO_API_KEY`.
3. **Edit the overlay in place. Do not regenerate it** from `doctl apps spec get`
   — that encrypts every plaintext secret into unreadable `EV[…]` blobs and you
   lose the local credentials ([[overlay-regen-encrypts-secrets]]).
4. Apply with `doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml`.
5. Prove all three behaviours, which is acceptance criterion 12 and the point of
   the whole exercise:
   - Deploy with the CRM conformant → the job passes, the deploy proceeds.
   - Hand-introduce a drift on crm-test (remove one required field, or rename one
     of the seven teams) → the deploy **fails** at the gate.
   - Set `CRM_GATE_BYPASS=true` and redeploy → the same drifted deploy **passes**,
     with the bypass logged.
   - Remove the drift, remove the bypass → clean deploy.
6. Leave prod alone until all four have been observed on crm-test.

---

## R4. Capture both CRMs' roles and tabulate where they differ

**Both captures are DONE (2026-08-31) and the table is built — what is owed is
the ruling.** Production was captured by `capture_roles.py` in its web
container; crm-test's capture came from the rehearsal (database over SSH, the
API login being dead there — F8). The diff:
[roles-standard/differences-2026-08-31.md](roles-standard/differences-2026-08-31.md)
— same 12 roles and 9 teams on both; 43 cells and ONE team attachment differ
for real (Data Integrity Team Role has no team on production —
`OPEN-ITEMS.md` #30). Found and fixed on the way: `GET Role/{id}` returns
empty `teamsIds` even where attachments exist, so the script now reads
`Role/{id}/teams`. **RULED the same day** (DECISIONS log): production is the standard; group A's
delete grant is a sanctioned crm-test-only deviation (the nightly recycle
deletes via the API); crm-test was updated to match on B and C — verified by
re-capture at 18:37Z, with six leftover cells listed in the table's
postscript for the CRM team to finish. Owed still: file the ruled table in
phase-1, and the six leftovers.

### What this is

This is the largest unknown in Phase 1, and it is the one thing the conformance
check cannot help with.

The application gates every screen on **teams** — seven of them, named in
`core/config.py`. It names **no role anywhere**, deliberately: a regular user's
token cannot read its own `rolesNames`, so gating on roles was never an option
([[crm-test-assignment-acl-fields]]).

But teams are empty vessels. What a team actually *permits* is defined by the
roles attached to it, and **those definitions exist only inside the two live
CRMs**. They are not in this repo, not derivable from code, and are documented as
**divergent between crm-test and prod** — role scopes especially. So the standard
cannot be written until someone reads both, lays them side by side, and rules
which one is correct where they differ.

**Reading them is mechanical. Deciding which is right is a ruling** — and it is
yours. Doing the capture now converts an unknown into a table you can rule on in
an afternoon, and it de-risks the most expensive part of the applier.

**One hard constraint, verified today:** the org-wide API key **cannot read
roles**. I probed crm-test read-only — `Team` returns HTTP 200 with 9 teams and
`EmailTemplate` returns 200, but **`Role` returns HTTP 403**. So this capture
needs an Admin-type account, which means it cannot run from a laptop against
prod: admin CRM credentials (`ESPO_PROVISION_USERNAME` / `_PASSWORD`) exist only
on the deployed **web** component.

### Steps

1. ~~Write `scripts/capture_roles.py`~~ — **done 2026-08-28.** Read-only, no
   write path in the file at all. It logs in with the provisioning admin via
   `core/admin_client.py`, pages `Team` and `Role` at 200, fetches each role's
   full record for its `data` and `fieldData` scope maps, and prints one JSON
   document. Two guards worth knowing: it **refuses to run as a non-admin**,
   because a non-admin's answer is silently partial and a partial capture
   adjudicated as complete is worse than none; and a role it cannot read is
   recorded in `notes` rather than dropped, since a missing role would read as
   "this instance does not have it". Run it with `--indent 0` for a single line
   that is easier to copy out of a web console.
2. Run it inside the **crm-test** app's console and save the output. Use the
   pty-pipe technique in [[do-app-console-scripting]] — running it inside the
   container is the only way to reach those credentials, and it is also how you
   avoid copying an admin password onto a laptop.
3. Run the same script inside the **production** app's console and save that
   output.
4. Diff the two into a table: one row per (role × entity scope), three columns —
   crm-test's value, prod's value, and a blank *standard* column.
5. Bring the table to Doug with the blank column. Where they agree, that is the
   standard by default; only the disagreements need a ruling.
6. File the ruled table in [phase-1](phase-1-crm-config.md) as the roles half of
   the desired state.

---

## R6. Switch the two new stamps on, crm-test first

### What this is

v0.214.0 added both version stamps to `/healthz` and **both ship inert**, which
is this repo's standing gate rather than caution for its own sake. **The two
overlay edits are DONE (2026-08-28) and validated** — both files parse, both
variables sit on the web component, and the tag value is **`v0.216.1`**, the tag
cut against the currently-deployed commit (an earlier draft said `v0.214.0`,
which would have made each system report a promotion it was not running — the
exact lie the two stamps exist to prevent). What is left is the two `doctl`
applies, which need the overlays and are Doug's.

- **`RELEASE_TAG`** supplies the value `releaseTag` reports. Without it the key
  is `null`, which is honest but useless. Scope **`RUN_AND_BUILD_TIME`** — the
  Dockerfile reads it as a build arg, so a plain run-time variable will not
  reach it. That scope is already used in `.do/app.prod.yaml`, so the mechanism
  is proven here rather than assumed.
- **`CRM_CONFIG_REFRESH_SECONDS`** arms the CRM stamp probe. `0` disables it and
  `0` is the default; `300` is plenty, since the stamp changes at most weekly.
  It is a **boot-read** key — the refresh task is created once in the lifespan.
  Since v0.215.0 it IS on `/setup`, in the *Restart required* group, so it can
  be set there and takes effect on the next restart; the overlay is simply the
  route that does not need one.

### Steps

1. ~~Add both to the overlays~~ **done 2026-08-28**, in place, never
   regenerated ([[overlay-regen-encrypts-secrets]]). `.do/app.prod.yaml` is
   **crm-test** (the filenames are confusing; `app.prod-crm.yaml` is
   production). Re-check the `RELEASE_TAG` value matches the tag you mean to
   report before applying — it goes stale every time the version bumps.
2. Apply crm-test: `doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml`
3. Check `/healthz` on crm-test: `releaseTag` should read `v0.216.1` and
   `crmConfig.state` should read **`unstamped`** — the entity is there (built
   2026-08-27) and nothing has applied to it yet. A `forbidden` here would mean
   the read grant was lost; an `absent` would mean the entity is not what we
   think it is.
4. Repeat on production (`.do/app.prod-crm.yaml`, app
   `aa1ddf69-f359-4b53-91ba-035cbed7bd53`) — but expect
   `crmConfig.state: "absent"` until R0's production half is built at the Sunday
   slot, and **that is the correct reading**, not a fault. Watching it flip from
   `absent` to `unstamped` on Sunday is the reader proving itself against a real
   change at no cost.

---

# Part 3 — Blocked

## B1. The applier itself

**Now CRMBuilder's to build (ruled 2026-08-31) — blocked on A1's requirements
session.** This repo's remaining obligation is the consumer half, already
written: [interface-contract.md](interface-contract.md), the plan-file format,
the ruled roles table, and the conformance check that verifies whatever the
applier does. This is the month-sized deliverable: the desired-state
definition generalized from `scripts/migrate_event_schema.py`'s change list, the
directive executor that applies it, plan identity (dry-run, then apply *that
exact plan*, refusing if the plan moved), the additive-only fence, the EspoCRM
extension package, and the release-train wiring.

It is the **only** part of Phase 1 at risk from the CRMBuilder decision. The desired-state definition,
the conformance check, the exit-code contract, the JSON result and both version
stamps are the app-derived half this repo owns under either answer — they are
what a CRMBuilder adoption would *consume*. What is genuinely thrown away if we
build this and then adopt CRMBuilder is the write path: the executor, the
fingerprint plumbing, and their tests. Two to three weeks.

This is why the build order is what it is: check and stamps first, applier last.

## B2. The throwaway-instance round trip

**Done 2026-08-31 — moved to *Closed* with its evidence.** It turned out not to
be blocked on B1 after all: the standard went on without the applier, and the
measurement of *what carried each category* is the most useful thing the day
produced. Its follow-ups are R7–R9 and A2 above.

---

# Part 4 — Verification owed

## V1. Phase 0's live browser pass

### What this is

The de-Cleveland work shipped and was verified by **fetching served pages** —
which proves the right bytes leave the server and cannot prove the one thing the
design was chosen for. The organisation name is substituted **server-side** rather
than filled in by JavaScript precisely so the browser tab and the public forms'
prose do not visibly repaint after a round-trip. **Nobody has watched a page
load.**

Four things remain unverified, none reachable with an unauthenticated `curl`.

### Steps

1. Hard-refresh a public form (`/volunteer/`) and watch the **browser tab** and
   the lead paragraph. Any flicker means the mechanism is not doing its job.
2. Sign in and open the two remaining **direct-read** pages — a sessions record
   page (`/mentorsessions/record/{id}`) and a directory contact page
   (`/directory/contacts/record/{id}`). These bypass the static mount and render
   the token explicitly; a raw `{{org}}` on either is the bug this mechanism
   invites. A third such page, the portal root, was already checked.
3. Check the two scripts that read `<meta name="cbm-org">` rather than fetching:
   the **portal birthday card's eyebrow line** and the **directory mentor page's
   tab title**.
4. At `/setup`, change `ORGANIZATION_NAME` to something obviously different,
   confirm the pages follow **without a redeploy**, then change it back. The
   revert is the path with the subtle failure mode.
5. Tick these off in `OPEN-ITEMS.md` § *Live verification owed*. Phase 0 does not
   close until they are done.

---

# Part 5 — Found here, owed to Cleveland

Not chapter work. Recorded in `OPEN-ITEMS.md`, where Cleveland defects get fixed,
and linked from here so the finding is not lost between two lists.

| Finding | Why it matters | Tracked as |
|---|---|---|
| Production holds **`MentorAssignmentNotice` twice** | The app looks email templates up **by name**, so which of the two a staff member actually sends after an Assign is arbitrary — and the two may differ | `OPEN-ITEMS.md` item 26 |
| Prod's `CMentorProfile.howDidYouHearAboutCBM` differs from the static list in **order only** | Cosmetic today (dropdown sequence on the volunteer form). Notable because one static file serves both deploys, so "which order is correct" has no answer until the code is the truth | `OPEN-ITEMS.md` item 26 |
| Five `Event*` email templates missing on **both** instances | Blocks the events follow-up sends | `OPEN-ITEMS.md` item 19 (already an events blocker) |
| Two visible **"CBM"** strings on the public client-intake form | Content an applicant reads on a non-Cleveland deployment; Phase 0 treated `CBM` as an identifier | `OPEN-ITEMS.md` item 28 |
| **`Analytics Admin Team` has no role** on crm-test | A user in only that team holds no CRM grant at all | `OPEN-ITEMS.md` item 28 |
| The `crm.config` admin on crm-test **does not survive the nightly reset** | The `espo-crm-changes` skill's crm-test path is dead until it is re-made | `OPEN-ITEMS.md` item 28 |

---

# Closed

- **R6 is done — both stamps are LIVE on crm-test and production**
  (2026-08-31, ~17:40 UTC). Doug applied both overlays (`doctl apps update`,
  crm-test 17:38, production 17:40); each app flipped within two minutes.
  Both now report `releaseTag: "v0.217.0"` and `crmConfig.state: "unstamped"`
  — production included, because R0's production half was built the same
  afternoon, so the `absent` interlude never happened. The overlays' RELEASE_TAG
  had been bumped v0.216.4 → v0.217.0 before the applies (the stale-tag trap,
  caught a second time). Dev deliberately unchanged: no overlay carries the
  switches there, so it reads `null` / `disabled` — the honest values.

- **R0 is done on production too — `CNetworkStandard` exists on both CRMs**
  (2026-08-31). Built NOT by hand: Doug ran `scripts/build_networkstandard.py`
  from inside the deployed production web container (dry run, then
  `--apply --expect 54fb5b37192027f7 --production`), so production was built
  from the same plan file crm-test matches, through code rehearsed twice
  (crm-test's container 2026-08-30, the Lakeside instance the same weekend).
  Both crm-test misses were caught mechanically this time: the § 4 role grant
  applied in the same run, and the entity's automatic tab-list entry removed
  (39 → 38 tabs). Read back as the org-wide API key: five plan fields, zero
  custom links, no `CCNetworkStandard`, `GET /api/v1/CNetworkStandard` →
  HTTP 200 `total 0` — the correct "built, never applied to" state. The Sunday
  slot was spent on the Lakeside rehearsal, so this ran Monday by Doug's call.
  `/healthz` `crmConfig` still reads `disabled` everywhere until the § R6
  overlay applies; production will read `unstamped` once they run.

- **B2 — the throwaway-instance round trip, acceptance criterion 13, is done**
  (2026-08-31). Evidence in
  [rehearsal-2026-08-31/](rehearsal-2026-08-31/): the applier-coverage record,
  both preflight JSONs, the 7×12 non-admin gate matrix, the API-half result, the
  final `/healthz`, the values file, and crm-test's roles/teams/templates
  capture. What happened, in one paragraph: Doug deployed a throwaway EspoCRM
  with the CRMBuilder desktop (DEP-001 / INST-001, `crm-lakeside`, one wizard,
  under twenty minutes); crm-test's file tree was copied and rebuilt clean on
  **EspoCRM 10.0.6** (source 9.3.4); the API half — 9 teams, **12 roles written
  through the API for the first time**, attachments, templates, the API user, a
  provisioning admin, the § E settings — was applied by script; the conformance
  check on the new instance read **identically to crm-test** (20 conformant, one
  absent: the five `Event*` templates); a fresh App Platform app rendered from a
  values file by a 60-line generator went ACTIVE on first deploy with
  `/healthz` honest on both stamps (`releaseTag null`, `crmConfig unstamped`);
  seven **real non-admins**, one per gated team, each got 200 only on their own
  apps and 403 on the other eleven; and a human pass — public form → client
  admin assigns → mentor sees it → marketing sees it closed — matched every
  expectation. **The stamp was deliberately not written**: 73 role entries were
  unapplyable (extension scopes, one stale field), so the apply exited 4, and
  C9 says the stamp follows a complete apply. Thirteen findings, F1–F13, are in
  the coverage record; the ones that need a decision or a fix are R7–R9, A2 and
  `OPEN-ITEMS.md` 28. **Teardown was not executed** — Doug ruled the same day
  that the instance stays up for the Google-integration rehearsal (Phase 6
  step 3), so the "nothing left billing" half of the criterion is owed when
  that arc ends; the teardown steps are written and waiting.

- **The Settings page holds every setting, and every setting is editable
  unless a change is genuinely impossible** (v0.215.0 + v0.216.0 + v0.216.1,
  2026-08-28/29, all live on both environments). Two of Doug's rulings in one
  afternoon, both recorded in `CLAUDE.md` § System Settings and both
  chapter-relevant because they change what `/setup` — and so the future fleet
  console — can do. (1) *All settings on the page*: the ten boot-read keys now
  form a **Restart required** group, and `core/boot_overrides.load_at_boot`
  installs the override layer BEFORE `create_app` mounts anything, so "takes
  effect on restart" is true rather than the v0.190.1 lie; each row shows the
  value in force beside the stored one. (2) *All settings editable, with
  verification*: the denylist fell from 23 keys to 3, and `setup/verify.py`
  tries a value before storing it, checks the system after, and gives the
  lockout-capable keys a 10-minute confirm-or-revert countdown that sweeps in
  BOTH processes. Secrets are editable, encrypted, never readable. Found on the
  way: `DATABASE_URL` was rendered in the clear on the read-only list — now
  masked. The three that stay read-only (`DATABASE_URL`, `APP_ENCRYPTION_KEY`,
  `RELEASE_TAG`) sit under **Foundations** with their reasons.

- **Two tags exist now, and `v0.216.1` is the one the overlays name**
  (2026-08-29). `v0.214.0` was cut first; the code moved on the same day, and
  the prepared overlay value was stale before it was ever applied — a live
  illustration of why `version` and `releaseTag` are separate fields. An attempt
  to delete `v0.214.0` was (correctly) refused: it marks a real published
  commit, and `cut_release.sh` refuses to move a published tag for the same
  reason. Both stay.


- **R1 and R5 are done — both version stamps exist, and so does the first tag**
  (v0.214.0, 2026-08-28, commit `786c138`). `/healthz` now answers all three
  version questions: `version` (the code), `releaseTag` (the promotion, baked in
  by a `RELEASE_TAG` Dockerfile arg because a container has no `.git`) and
  `crmConfig` (the CRM's configuration standard, from `CNetworkStandard`, in new
  `core/network_standard.py`). 17 tests in `tests/test_version_stamps.py`; full
  suite green at 1894 passed.

  Three things worth keeping. **`/healthz` still never pings the CRM** — a
  background task caches and the handler serves the cache, and a test asserts
  that priming it once is the only call however many health checks follow.
  **`absent`, `forbidden` and `unreachable` are three separate states** rather
  than one null, which is not academic: production has no `CNetworkStandard`
  until its Sunday build, so `absent` is production's *expected* reading and
  must not read as a fault — and `forbidden` is exactly the grant that was
  missed on crm-test on 2026-08-27. That is one key (`state`) beyond the three
  the interface contract documents; the documented three are still always
  present and null, so a consumer that only knows the contract still works.
  **Both keys are denylisted at `/setup`** as boot-read — an override for either
  would be inert, and offering an inert override is the v0.190.1 mistake.

  `scripts/cut_release.sh` cuts the tag: clean tree on `main`, version from
  `pyproject.toml`, refuses to move an existing tag, annotated (it carries the
  tagger and date the fleet console wants), and prints the push rather than
  pushing. **`v0.214.0` is this repository's first tag ever** — `git tag | wc -l`
  had been 0 since the repo was created. It promotes nothing; `deploy_on_push`
  stays on and pinned-tag deploys remain Phase 2. What is still owed is turning
  the two switches on per deployment, which needs `doctl` — now § R6.


- **R3 — the stale count in `CLAUDE.md` is fixed** (2026-08-28). It now reads
  "16 lists across 4 `options.js` files, from 14 distinct `Entity.field` sources"
  — both numbers re-derived rather than trusted (`grep -rc ">>> crm-enum"` gives
  1/6/6/3, and the distinct `field=` values sort to 14). The same paragraph's
  worked example cited `field=CMentorProfile.industrySector`; the real marker in
  `forms/volunteer/frontend/options.js:47` is `industryExperience`, so that was
  corrected in the same edit. Both were wrong in a file that loads into every
  session.

- **Three stale spots in this project's own documents** (2026-08-28). Found by a
  review pass that checked each document's falsifiable claims against the tree.
  (1) [DECISIONS.md](DECISIONS.md)'s proposals preamble still said each open
  proposal "blocks work that is otherwise ready to start", which contradicted
  Part 1 of this file — two of the seven are ruled and none of the remaining five
  blocks anything today. (2) [README.md](README.md)'s Phase 1 row and (3)
  [phase-1](phase-1-crm-config.md)'s tranche table both still listed "Stamp B's
  home" as pending, which D1 ruled on 2026-08-26 and R0 built on crm-test on
  2026-08-27. Everything else in all fourteen documents checked out: zero git
  tags, no `releaseTag`/`crmConfig` in `core/`, no conformance job in either
  overlay, the four timezone hardcodes at the exact cited lines, and
  `OPEN-ITEMS.md` item 26 present.

- **R0 is done on crm-test, and it took two corrections** (2026-08-27).
  `CNetworkStandard` was built correctly in every structural respect — one `C`,
  type `Base`, stream off, all six fields, no custom links, all read back from
  `GET /Metadata` rather than from a screen. But **the org-wide API key got HTTP
  403**: `CustomAppAPIRole` had no grant on the new scope, which is exactly the
  step the handoff flags as "the grant that is easy to forget" and exactly the
  property the entity was chosen for. Doug granted it, then narrowed it to
  read-only after review — confirmed via the effective ACL the app itself sees:
  `{create: no, delete: no, edit: no, read: all}`, against a `CEngagement`
  control still showing full write. The entity was also in the navigation tab
  list; removed via the API (45 → 44 tabs). `GET /api/v1/CNetworkStandard` as the
  org key now returns **HTTP 200, `total: 0`** — the correct "built, never applied
  to" state. Production is owed at a Sunday slot.

- **The per-chapter values are inventoried** (2026-08-27).
  [chapter-values.md](chapter-values.md). Two findings worth keeping: **eleven
  EspoCRM instance settings are per-city and had never been listed anywhere**
  (including a logo file, so there *is* one per-city image asset despite the app
  having none by ruling); and **email template bodies carry no hardcoded brand at
  all**, so templates are genuinely build-once-deploy-everywhere rather than
  per-city content. Neither was knowable without reading the live instance.

- **The release slot is Sunday 17:00 UTC, and the CRM-update procedure is
  written** (2026-08-26). [crm-update-runbook.md](crm-update-runbook.md) is the
  twelve-step procedure for getting a configuration change onto every instance —
  written for today's by-hand reality with a section on what changes when the
  applier lands, because the *shape* does not change, only who performs two of
  the steps. Two things it settles that were previously folklore: the order is
  always crm-test then production, and verification is **two** checks, one as the
  org-wide API key and one as a real non-admin, because an admin bypasses ACL and
  proves nothing. Flagged in passing: 17:00 UTC is Sunday **afternoon** in
  Cleveland (13:00 EDT), not night.

- **Release cadence ruled: weekly** (Doug, 2026-08-26). The soak is the week
  itself; a security fix may bypass the cadence but never staging. It unblocked
  the tagging half of Phase 2 (§ R5) and left one sub-question — which machine
  hosts staging — which does not need answering until Phase 6 (§ D4). Two
  consequences are designed around rather than discovered, both recorded in
  [phase-2](phase-2-release-train.md): weekly needs a **day** (recommend Tuesday
  or Wednesday, so a bad promotion meets people at their desks), and fifty tags a
  year means cutting one must be a single command.

- **D1, D2 and D3 ruled** (Doug, 2026-08-26). The configuration stamp is a new
  `CNetworkStandard` entity, not an EspoCRM setting and not a log row — build
  handoff written, now task R0. The CRMBuilder trigger stands at **2026-09-19**,
  which makes convening that session the project's only dated commitment (A1).
  And there is **no logo and no favicon** — chapters get colours, not marks, so
  "per-chapter `tokens.css` + logo" comes out of the plan wording rather than
  becoming a backlog item. That last one **closes the last open question in
  Phase 0**, which now finishes on a browser pass alone (V1).

- **The CRMBuilder prompt already carries the interface contract** (checked
  2026-08-24). I had this listed as work to do; it is not. § *What the consumer
  requires — the interface contract* was added to
  `prompts/crmbuilder-chapter-network-prompt-v0.1.md` on 2026-08-20 and carries
  C1 through C10 by number. The only thing owed was its citation, which pointed
  at the pre-split path — repointed at
  [interface-contract.md](interface-contract.md) the same day.

- **The conformance check is built and has been run against both live instances**
  (2026-08-21, commit `ac6f1b4`). `scripts/preflight_crm.py` rewritten to C1–C5
  with `tests/test_preflight_conformance.py`; acceptance criteria 1–5 and 7 met
  for real, and exit codes 1 and 3 produced live. It also corrected **three dead
  requirements in its own contract** — `Account.cAccountType` and
  `CIntakeSubmission.reason` / `.status` had been required for months and are
  written by nothing — because a gate that reports drift nobody can fix is a gate
  that gets ignored. Full result: [phase-1](phase-1-crm-config.md) §
  *Measured, 2026-08-21*.

- **The drift narrative was wrong, and there is a measurement in its place**
  (2026-08-21, re-confirmed on crm-test 2026-08-24). The two CRMs are far closer
  than assumed: **identical teams** (7 required, 9 present, same lists),
  **identical enum values across all 16 managed option lists**, and one ordering
  difference. Where they actually differ is **email templates** — crm-test holds
  2, prod holds 5 — which is the one surface nothing was watching.

- **Phase 0's mechanism** (v0.205.0–v0.206.0, deployed and prod-verified).
  `ORGANIZATION_NAME` and the `{{org}}` token substituted server-side,
  `CHAPTER_TOKENS_URL` for per-chapter colours, `ops_mailbox_name` derived from
  the organisation name, `organization` reported at `/healthz`, and
  `tests/test_shared_branding.py` (24 cases) as the thing that keeps it done.
