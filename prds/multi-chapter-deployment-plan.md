# Multiple chapters — deployment, propagation and support

**Status: PLAN. Eight rulings settled 2026-08-17/18; the design below follows
from them. The seven items in *Proposals* are mine, not Doug's — rule on them in
this document.**

Other chapters like CBM want to use these apps and this website. The requirement:
**all instances hold the same configuration, and a change made once propagates to
all of them**, while each chapter keeps **its own website with its own graphics
and marketing content**.

This document was reconstructed after the planning session ended in a power cut.
Everything under *Rulings* is Doug's, given in that session and preserved
verbatim in substance.

---

## Rulings — the settled architecture

1. **A central services organization owns development and support.** CBM and the
   other chapters fund one organization that provides all services. Immediate
   propagation requires central operational control, and this supplies it without
   making Cleveland the landlord of its peers — the franchisor model minus the
   franchisor.
2. **One EspoCRM per chapter.** Not one shared multi-tenant database.
3. **Google Workspace is mixed** — some chapters have one, some do not. The two
   branches ("bring your own Workspace and grant delegation to our service
   account" vs "we provision a domain under the network Workspace") differ in an
   onboarding runbook, not in code.
4. **Strictly identical function — core or nothing.** No per-chapter fields, enum
   values or form questions. A want becomes core for everyone, or it does not
   exist.
5. **Each chapter owns its own infrastructure** — its DigitalOcean account and its
   Google Workspace — and grants the services org administrative access to run
   them. Lock-out is impossible in either direction: the services org can stop
   working, the chapter can stop paying and revoke access, neither can destroy the
   other. Dividend: each chapter claims **its own** nonprofit grants (Workspace
   for Nonprofits, TechSoup/DO credits), so the co-op fee is purely labour.
6. **The services org holds the only EspoCRM admin accounts.** Chapter staff get
   non-admin roles. This is what makes ruling 4 enforceable rather than requested:
   EspoCRM has no partial admin, so anyone who can add a user can open Entity
   Manager and add a field. Safe because ruling 5 leaves the chapter able to break
   glass through the droplet it owns.
7. **A release train — all chapters move together.** Every merge deploys to a
   services-org staging instance and soaks; on a fixed cadence all chapters move
   to that tag at once. Chosen over ring promotion because rings create deliberate
   **version skew**, which is what ruling 4 exists to prevent and which makes every
   support call begin with "which version are you on". The guinea pig is a machine
   the co-op owns, not a member.
8. **The app serves the public pages for every chapter**, and each chapter's
   WordPress site embeds them.

### What ruling 4 costs, and who pays it

Ruling 6 makes ruling 4 real, and together they move every configuration change
onto the services org's desk. That is the trade: sameness is bought with
responsiveness. **If the change-request route is slow, chapters will route around
it** — not by hacking, but by asking their own admin, and there will not be one,
so they will ask for one, and the first exception granted ends the architecture.
The governance design below is therefore not paperwork; it is the load-bearing
half of ruling 4.

---

## What already works, and what is genuinely new

**Already true, and free.** Code propagation is the existing model — every app
tracks `main` with `deploy_on_push`, so N chapters costs a DO app each. Branding
is `frontend/shared/tokens.css`, 162 lines of CSS custom properties. The marketing
sites are already separate WordPress installs. Per-deployment configuration is
already how everything works: `get_settings()` reads one environment, `gmail.py`
and `gdrive.py` impersonate exactly one subject per client, and there is one
service-account JSON, one `gdrive_shared_drive_id`, one members group. A chapter's
Google stack is just another env set.

**Why one app per chapter rather than one multi-tenant app.** `get_settings()` is
process-global, `core/settings_store.py` merges the DB override layer
process-wide, and the worker is a single process owning the delivery loop, Gmail
sync, Drive reconciliation and receipt sweeps. Resolving a tenant per request
through all of that is a rewrite of the foundation, and it would put every
chapter's CRM credentials in one process — discarding the isolation ruling 2
buys. N deployments of one image get isolation for free.

**Why not one shared CRM**, even though it would make propagation free by
construction: **29 non-test modules construct an EspoCRM client**, and the
org-wide API-key paths among them (the worker, receipts, action log, directory
availability, analytics system metrics, monitoring, birthday, docs grants, ops
inbound, assignment stamps) plus **8 modules reaching the admin service account**
all bypass user ACL by design. In a shared database each becomes a place where one
chapter can read another's records, and a miss is silent — this codebase's
documented failure mode ([[espo-field-acl-silently-strips-writes]],
[[espo-403-diagnosis-merged-team-roles]]). Separate instances delete that surface
physically rather than by audit.

**The one genuinely new build is CRM configuration.** Everything else in this plan
is configuration, runbook or governance. EspoCRM has no supported
push-config-from-A-to-B, and its customization is split in two halves with very
different distribution stories.

---

## Phase 1 — CRM configuration as a build artifact

This is the heart of the plan. Two hand-maintained instances already produce
documented drift — [[crm-test-schema-drift]], role scopes especially, team→role
attachments vanishing twice, and the two CRMs diverging often enough that
`scripts/sync_form_options.py`'s dry-run doubles as the detector. Six instances
maintained the same way is not a system, it is a support queue.

### Why this phase is written in three layers

An earlier draft of this phase said: generalize `scripts/migrate_event_schema.py`
from a change list into a declarative desired state, and build the applier here.
A read-only review of the **CRMBuilder** repo on 2026-08-18 then established that
most of that already exists there — a Qt-free 12-step CHECK→ACT deploy pipeline,
managers for roles, teams, email templates, security rules, entity settings and
filtered tabs, an Audit that reverse-engineers a live CRM into the same YAML the
engine consumes, a `reconcile` package that diffs live config against source, and
in-place EspoCRM upgrades. The obvious conclusion is "Phase 1 is adoption, not
construction."

**That conclusion is not safe to write into this plan yet, and the reason is
dated.** Verified 2026-08-20: CRMBuilder's HEAD is `db1dbef0`, dated 2026-08-10 —
so the 2026-08-18 review looked at the tree that is still there, and nothing has
moved since. The requirements session that
`prompts/crmbuilder-chapter-network-prompt-v0.1.md` asks for **has not run**. That
prompt deliberately ends at confirmed requirements, and among the questions it
puts to Doug is whether "the network standard" is a **CRMBuilder product
capability** or a **CBM-network artifact that merely uses CRMBuilder**. Those two
answers put this work in different repos under different governance. CRMBuilder is
also requirement-first: its shape is not ours to assume, and we cannot write a
plan that obliges it to grow an interface it has not agreed to.

There is a second, smaller reason not to assume its shape. Its `pyproject.toml`
declares six console scripts, five of them beyond the GUI — but three point at a
`crmbuilder_v2` package that **does not exist at HEAD** (verified 2026-08-20). The
2026-08-18 review's "the only console script is the GUI" is right about what
actually runs, and the declared-but-absent entry points are a reminder that the
repo has in-flight direction of its own.

So Phase 1 is written in three layers:

- **Layer 1 — the interface contract.** What *this* repo requires of whatever
  applies CRM configuration, stated without naming a tool. Survives any answer.
- **Layer 2 — CRMBuilder as the preferred realization.** The adoption path,
  written as adoption, with its dependency stated honestly.
- **Layer 3 — the fallback, and the plan of record.** Generalize the applier here,
  until Layer 2 is confirmed. Not a footnote: this is what is built if nothing
  else happens.

Layer 1 is the valuable half, and it is also **an input the CRMBuilder
requirements session currently lacks** — that prompt tells its session what
CRMBuilder can do and nothing about what its consumer needs. When Layer 1 is
settled it should be carried into
`prompts/crmbuilder-chapter-network-prompt-v0.1.md` as a "what the consumer
requires" section, which is the one legitimate way this repo influences that one.

### The file half — ship it as an EspoCRM extension

Entity and field definitions, links, layouts and formulas live in files under
`custom/Espo/Custom/`. Espo's own supported distribution mechanism for these is an
**extension package**, which brings versioning and rollback with it. The network's
CRM shape becomes a versioned extension built from this repo and installed on
every chapter instance by the release train.

**The file half is largely orthogonal to the CRMBuilder question.** CRMBuilder's
established capability is the admin-API surface — field manager, entity manager,
roles, teams, templates — not extension packaging; nothing in the 2026-08-18
review mentions building an extension, and that has not been verified either way.
Treat the extension build as ours until the requirements session says otherwise,
and put the question to that session rather than assuming an answer.

### Layer 1 — the interface contract

Stated as requirements on **the applier**, whoever builds it. Each one is written
so that a candidate implementation can be held against it and fail.

**C1 — Headless invocation.** One non-interactive entry point, invocable as a
process with arguments and environment only. The precedent is already in the
overlays: the live prod spec carries `kind: PRE_DEPLOY`, `name: migrate`,
`run_command: .venv/bin/alembic upgrade head` (`.do/app.prod-crm.yaml` lines
14–27, verified 2026-08-20), and the checked-in `.do/app.yaml` documents the same
shape in its commented reference block.
No GUI, no operator laptop, no interactive keyring, no prompt, no human decision
mid-run. If it cannot decide something, it exits — it does not ask.

**C2 — Credentials supplied by environment, and the least of them that works.**
Two credential classes, and the difference decides where the work can run.
Read-only conformance checking needs only the org-wide **API key** —
`scripts/preflight_crm.py` already proves this, auditing entities, fields and enum
options with an API key and nothing else. Applying needs an **Admin-type account**;
`scripts/migrate_event_schema.py` documents why (the intake API key 403s on
`Admin/fieldManager`) and refuses to proceed when `app_user()` reports a non-admin
type. Verified 2026-08-20 in the live prod overlay: the `migrate` PRE_DEPLOY job
carries **only** `DATABASE_URL`, and `ESPO_PROVISION_USERNAME` / `ESPO_PROVISION_PASSWORD`
sit on the **web service** alone. Putting an applier in the deploy gate therefore
means putting CRM admin credentials into a new component. That is a real cost and
it drives the ruling under *Where it runs* below.

**C3 — A credential problem must never read as a configuration problem.** This is
a defect the existing tooling has today, not a hypothetical:
`preflight_crm.py::_safe_metadata` treats an error, a transport failure and
EspoCRM's *empty 200 for a scope the user cannot see* as one outcome, and the
report says so out loud — `"not visible (entity absent, or the API user has no
grant on this scope)"`. In an unattended fleet check that ambiguity is fatal: it
turns "your key lost its role" into "your CRM is missing nine entities". The
contract requires the applier to separate *absent*, *forbidden* and *unreachable*
in both its report and its exit code.

**C4 — Exit codes with defined meanings.** The repo has three scripts that answer
this question three different ways today, which is the argument for fixing it once
(all verified 2026-08-20 by reading the code):

| Script | Drift found in a dry run | Write failed | Bad config / wrong credential |
|---|---|---|---|
| `migrate_event_schema.py` | **0** — pending changes are recorded as `WOULD …` in the *done* list | 1 | 2 (missing env, or account not Admin-type) |
| `preflight_crm.py` | **1** for a missing entity/field; **0** for a missing enum option (advisory) | n/a (read-only) | 0 — a key with no grants prints "NOT READY" but still exits 0 unless a scope reads as absent |
| `sync_form_options.py` | **1** — "dry-run exits non-zero when anything would change, so it doubles as a CI drift check" | 0 after a successful `--write` | argparse error |

Proposed contract — five codes, and the two hard cases are the point:

| Code | Meaning | In a deploy gate |
|---|---|---|
| **0** | Conformant. Nothing to do, or everything asked for was applied. | Proceed. |
| **1** | **Drift** — the instance differs from the standard and this was a check, or an apply was not authorised to close the gap. | **Fail.** In an unattended run drift is a failure; interactively it is information. That difference is the mode flag, not the exit code. |
| **2** | **Apply failed** — a directive was attempted and rejected. Deterministic: a 4xx, a validation error, a field the CRM will not accept. | Fail. This is the analogue of a bad Alembic migration. |
| **3** | **Could not be checked** — transport failure, 5xx, timeout, DNS, or a 401 because the admin password rotated. The instance's conformance is *unknown*, not bad. | Fail closed, but distinctly — see below. |
| **4** | **Unapplyable directive present** — the standard names something this applier cannot write (CRMBuilder's `NOT_SUPPORTED`). Nothing is wrong with the instance; the standard is not fully expressible. | Fail in the gate; see *The categories that cannot be applied*. |

Two calls inside that table are the ones worth arguing with. **Drift is a failure
in an unattended run** because the only alternative is a gate that passes while
reporting a difference, which is not a gate. **Unknown is not the same as bad**,
which is why code 3 exists at all — the fleet console must be able to show "18
conformant, 1 drifted, 1 unreachable" rather than collapsing the last two.

**C5 — A machine-readable result.** A JSON document on stdout or at a named path,
emitted on **every** exit code including the failures — a result only produced on
success is useless to the console that needs to explain a failure. Minimum shape:
the instance identity, the standard version attempted, the run mode, the counts by
outcome, and a per-directive list carrying entity, directive, outcome
(`conformant` / `applied` / `drifted` / `failed` / `unapplyable` / `unchecked`) and
a human-readable reason. The human-readable console output stays; it is not the
interface.

**C6 — Idempotence, and what "already conformant" exits as.** Running twice in a
row must produce no writes the second time and exit **0** both times.
`migrate_event_schema.py` already holds this line and says why — *"running it
against production later produces exactly the same schema as crm-test (which is
the point)"* — reading each field before touching it and recording
`"already exists"` / `"already has …"` / `"is already writable"` as *skipped*
rather than acting. Conformant is a first-class success, not a no-op that happens
to not crash. The stronger form of this requirement is observable: a second run
must leave no trace in the CRM's own modification history.

**C7 — Dry-run, then apply that exact plan, refusing if the plan moved.** The
repo's convention, and it is enforced mechanically in exactly one place today:
`setup/jobs.py` stores the dry-run's output under a **fingerprint**, and the apply
call names that dry-run, re-derives the plan, compares fingerprints, and returns
`STATUS_REFUSED` with the fresh plan when they differ — *"The plan changed since
you reviewed it — nothing was applied."*

**Correction to the earlier draft of this phase, which claimed
`migrate_event_schema.py` already works this way: it does not.** It is dry-run by
default and its `--apply` is idempotent, but there is no plan identity — `--apply`
re-derives every decision from scratch and acts on whatever it finds. Nothing
carries a fingerprint, so nothing can refuse. The pattern to generalize from is
`setup/jobs.py`; the pattern to generalize *is* `migrate_event_schema.py`'s change
list. They are two different files and the phase needs both.

**C8 — Additive-only in any automatic slot.** A PRE_DEPLOY job that mutates the
CRM changes it **before the new app code is live**, so any directive that removes
or narrows something the currently-running code still uses opens a live incident
for the width of the deploy. Alembic has the identical property and nobody notices
because migrations are almost always additive. The contract: the automatic path
may create and widen; **removals, narrowings and type changes are a separate,
deliberately-triggered job** with the `setup/jobs.py` review discipline in front of
it. This is not theoretical here — [[espo-removelink-is-metadata-only]] records
that a mis-named relationship recreate strands data in the old column and reads
exactly like data loss, and `migrate_event_schema.py` already fences itself the
same way: *"Deliberately NOT included: … anything destructive."*

**C9 — A standard-version stamp.** The applier must be able to say which version
of the configuration an instance holds, and must write that stamp itself. Detailed
below, because it is shared with Phases 2 and 5.

**C10 — What it must not require.** An operator's laptop. An interactive OS
keyring (CRMBuilder's current secret store, and an interactive-desktop
assumption). A GUI or a display. A human decision mid-run. Network access to
anything but the instance it is configuring. Write access to this repo.

### The two version stamps, and where each comes from

**Neither exists today.** Verified 2026-08-20 by reading `core/app.py`:
`/healthz` returns `status`, `version`, `environment`, `organization`, `dryRun`,
`forms`, `assignments`, `durableStore`, `database`, a `worker` block and a
`settings` block carrying `settingsVersion` — **no release tag and no
CRM-configuration version**. `__version__` comes from `core/version.py`, which
reads `pyproject.toml` (`version = "0.206.0"`), so it identifies *the code*, not
the promotion. And `git tag | wc -l` in this repo is **0** — the release train's
tag is not merely unreported, it has never been cut.

**Stamp A — the release tag.** *Belongs to Phase 2; defined here only so the slot
exists once.* Source: an annotated git tag cut by the services org when a staging
soak ends. Written into the image at build time (a build arg baked into the
container, since a container has no `.git`). Surfaces as a new `/healthz` key —
`releaseTag`, null on an untagged dev build — and in the fleet console. It does
**not** replace `version`: `version` answers "what code is this", `releaseTag`
answers "what promotion is this", and after a hotfix rebuild those differ.

**Stamp B — the CRM-configuration version.** *Belongs to Phase 1.* It must live
**in the CRM**, not in the app's environment or database, for three reasons: it
describes the CRM, it must survive the app being redeployed or replaced, and the
applier is the only thing entitled to write it — an env var could be edited by
anyone with the DO console and would then lie.

Candidate homes, in preference order, **none of them verified against a live
instance yet** — deciding between them is the first hour of Layer 3 or the first
question to Layer 2:

1. **A single-record custom entity** (working name `CNetworkStandard`) with
   `standardVersion`, `appliedAt`, `appliedBy`, `planFingerprint` and
   `appliedByTool`. Preferred: the applier already drives `Admin/fieldManager` and
   `EntityManager`, so creating it is inside the mechanism; it is readable by the
   app's ordinary org-wide API key with no admin escalation; and it does not
   collide with a surface the CRM team also edits by hand.
2. **A key under the admin Settings endpoint.** Fewer moving parts, but it shares
   a surface with settings CBM staff and the CRM team change, and reading it needs
   admin — which would drag admin credentials into the app's runtime, which C2
   exists to avoid.
3. **A `CActionLog` row.** Already exists and is already how this app records
   what it did on its own initiative, but it is an append-only history, not a
   current-state assertion, and answering "what version is this" by scanning a log
   is the wrong shape.

**Who writes it, and when.** The applier, and **only after a complete successful
apply**. A partial apply must leave the previous stamp untouched — an instance that
claims conformance it does not have is worse than one that claims nothing, because
the fleet console believes it. The stamp carries the plan fingerprint from C7, so
"which plan was actually applied" is answerable after the fact.

**Where it surfaces.** The app reads Stamp B on the same refresh loop that already
serves `settingsVersion` and reports it at `/healthz` as a `crmConfig` block —
`{version, appliedAt, fingerprint}`, all null when the CRM holds no stamp, which
is the honest reading of every instance today. `/setup`'s environment-diff panel
gains it too, where it is immediately useful with only two instances.

**The coupling, named rather than solved three times.** Phase 1 defines and writes
Stamp B and defines the `/healthz` slot for both. Phase 2 cuts and writes Stamp A.
Phase 5 (fleet console) is a **consumer of both and an owner of neither** — if
Phase 5 finds itself designing a stamp, one of the earlier phases did not finish.
The release-train invariant that makes all this worth doing: **a promotion pins a
pair**, `(releaseTag, standardVersion)`, and an instance is conformant when it
holds the pair the train pinned, not when each half is independently plausible.

### Where it runs, and whether failing the deploy is right

The earlier draft said the applier runs as a PRE_DEPLOY job, exactly as
`alembic upgrade head` does, and that a chapter whose CRM cannot be reconciled
fails its deploy. **The instinct is right and the placement is wrong, for three
reasons that only appear when you test the analogy.**

*The failure modes are not alike.* Alembic's failure is local, deterministic and
in our own code; retrying does not help and failing is unambiguous. The CRM
applier's failure is a third-party HTTP API that may merely be unreachable — an
outage on the chapter's own droplet, a certificate, a rotated admin password.
Failing a deploy for that blocks a rollout that might itself be the fix.

*The credentials do not belong in the deploy path.* Verified above: the `migrate`
job carries only `DATABASE_URL`, and admin creds live on the web service. Adding
CRM admin credentials to a job component multiplies the number of places an admin
password exists across N chapter-owned accounts, and it does so in the component
with the least oversight.

*Applying before cutover is expand/contract without the discipline.* C8's point:
the CRM is changed while the old code is still serving.

**The ruling this phase proposes.** Split the two halves and put each where its
failure mode belongs:

- **The deploy gate is a conformance CHECK, not an apply.** Read-only, org-wide
  API key, no admin, fast, and it runs in the existing PRE_DEPLOY slot. It fails
  the deploy on **drift** (exit 1), because a chapter running code that expects a
  configuration its CRM does not hold is the thing this phase exists to prevent.
  With Stamp B in place the check is also cheap in the common case: compare the
  stamp to the pinned pair first, and do the full sweep only when they differ or
  the stamp is absent.
- **The apply is a release-train step**, run against each chapter's CRM
  immediately before the app promotion, with admin credentials held by the
  services org and never resident in a chapter's app spec. This keeps ruling 7's
  "app image and CRM configuration in the same promotion" exactly as written — the
  promotion still moves both — while removing admin credentials from every
  chapter's deploy environment.
- **Unreachable fails closed but distinctly** (exit 3, with a bounded retry inside
  the job before it gives up, since a transient 502 is the common case). Fail-open
  is not an option: a gate that passes when it could not check is a gate that
  reports success for an unknown, and this codebase's documented failure mode is
  precisely the silent pass ([[espo-field-acl-silently-strips-writes]],
  [[espo-list-maxsize-403]]).
- **A documented break-glass** downgrades the gate to a warning for one deploy —
  a single environment variable, in the shape `SETTINGS_OVERRIDES=false` already
  has, logged loudly and visible in the fleet console as "gate bypassed". Without
  one, the first CRM outage during an urgent app fix produces an undocumented
  bypass invented under pressure.

### The categories that cannot be applied

CRMBuilder returns `NOT_SUPPORTED` for `savedViews`, `duplicateChecks` and
`workflows`, because `/api/v1/Metadata` accepts GET only, and routes them to a
manual-configuration block in its run report. Under ruling 4 a category that must
be hand-configured on every instance is a permanent drift source with no detector.

Two refinements, both verified read-only against CRMBuilder at HEAD on 2026-08-20:

- **The three are not the whole set.** `espo_impl/core/layout_manager.py` also
  emits `NOT_SUPPORTED`, for **portal layout variants** and for layouts using
  `forRoles` per-role variants (its DEC-6: EspoCRM 9.x has no per-role layout
  binding without Layout Sets + Teams). Ordinary list and detail layouts deploy
  normally — which matters here, because `/directory` reads the CRM's own
  `layout/list` and `layout/detail` live ([[espo-layout-api-readable]]) and would
  otherwise be exposed to exactly this. **This repo's layout dependency sits
  inside the supported set**; the per-role variant case does not arise for us
  today and must not be introduced without knowing this.
- **Managers exist for all three** — `saved_view_manager.py`,
  `duplicate_check_manager.py`, `workflow_manager.py` are all present. The
  limitation is on *writing through the Metadata API*, not on the concept — and
  `/api/v1/Metadata` **is** readable. Whether each of the three has a
  representation there that a check could compare against is **not verified
  here** and needs a live CRM read. But "cannot be applied" and "cannot be
  detected" are separable in principle, and a check-only path for an unapplyable
  category is worth asking about rather than assuming away. That question belongs to the CRMBuilder session; it is recorded here so
  it is asked.

**The ruling belongs to that session. Phase 1's consequence under either answer is
ours, and must be stated now:**

- **If they are reimplemented** (EntityManager for duplicate checks, the Workflow
  entity CRUD API gated on Advanced Pack, SSH file writes plus cache rebuild for
  saved views), Phase 1 gains nothing to build and one thing to verify: that the
  gate's exit code 4 never fires in practice, which is a fleet-console assertion.
- **If they are formally excluded from the standard**, Phase 1 must (a) name them
  in the onboarding runbook as hand-configured steps with a written definition of
  the correct state, (b) *detect* them where a readable representation exists, so
  the drift is visible even though it cannot be closed, and (c) exit **4** rather
  than 0 when the standard names one, so that "we knowingly cannot express this"
  never silently reads as "this instance is conformant".

**One dependency of ours is live and unverified either way.** This app sends no
`X-Skip-Duplicate-Check` header anywhere (case-insensitive `grep` for
`skip.duplicate` across every `.py` and `.js` in the tree, 2026-08-20: zero hits), so whatever duplicate-check
configuration a chapter's instance holds applies to every intake create the
orchestrators make. Whether Cleveland's two instances have duplicate checking
configured on `Account` or `Contact` **has not been checked** — it needs a live
CRM read. If they do not and a chapter's does, the intake path behaves differently
on that chapter with no code difference. That makes `duplicateChecks` a
behavioural dependency of this repo, not a staff convenience, and it should be
said in the CRMBuilder session rather than left as a UI-preferences question.

### What this repo owns either way

**The desired-state definition for everything derivable from this repo's code is
ours; the engine is not.** The justification is that the failing test already
lives here. Four artifacts in this tree already declare, in code, what this
application requires of a CRM, and each is maintained in the same commit as the
code that requires it:

| Artifact | Lines | What it already declares | Verified count, 2026-08-20 |
|---|---|---|---|
| `scripts/preflight_crm.py` | 181 | Entities and fields the orchestrators and the submission log write | 9 entities, `REQUIRED_FIELDS` for all 9 |
| `core/schema_contract.py` | 93 | Enum options the app writes or filters on | 10 `(entity, field)` contracts |
| `scripts/sync_form_options.py` | 228 | The form dropdown lists that must equal live CRM enums | **16** managed `crm-enum` blocks across 4 `options.js` files, **14** distinct `Entity.field` sources |
| `scripts/migrate_event_schema.py` | 297 | A worked, idempotent, dry-run-by-default applier for one change list | 16 new fields, 3 enum additions, 4 `readOnly` clears, 1 link |

Two more categories are declared in this repo's code but are not in any of those
artifacts, and belong in the desired state:

- **Team names** — 7 distinct names across 12 settings in `core/config.py`
  (Client Administration Team, Mentor Administration Team, Marketing Admin Team,
  Mentor Team, Partner Management Team, Sponsor Management Team, Analytics Admin
  Team). Every team gate in the product resolves one of these strings; a missing
  team is a locked-out app, and `OPEN-ITEMS.md` already carries "`Analytics Admin
  Team` — create in both CRMs" as an outstanding item.
- **Email template names** — 6 named in code: `MentorAssignmentNotice`
  (`assignments/frontend/app.js`) and `EventReminder`, `EventRecordingAvailable`,
  `EventNoShow`, `EventMentorCTA`, `EventSurvey` (`events/notify.py`).

**Note the count correction while touching this**: `CLAUDE.md` says "8 lists are
managed today" by `sync_form_options.py`. The tree says 16 blocks / 14 distinct
sources. The figure is stale, not wrong in kind — flagged here, not fixed here.

**What is NOT derivable from this repo, and this is the expensive part: roles and
security rules.** This repo names teams everywhere and **names no role anywhere**
— by design, since [[crm-test-assignment-acl-fields]] establishes that a regular
user's token cannot read its own `rolesNames`, so the product gates on teams. The
role definitions that make those teams mean anything exist only inside the two
live CRMs, they are documented as **divergent between them**
([[espo-403-diagnosis-merged-team-roles]], and CLAUDE.md's "the two CRMs also
drift from each other; role scopes especially"), and capturing them produces two
answers with no rule for which is the standard. That capture-and-adjudicate step
is the single largest unknown in this phase, it is exactly what CRMBuilder's Audit
is built to do, and it is the strongest argument for Layer 2.

So the split this phase proposes: **this repo owns the app-derived half of the
desired state and the interface contract; whoever owns the engine owns the
general-purpose half (roles, security rules, layouts, dashboards, settings) and
the mechanism.** The two halves must version together as one standard — see the
pinned pair above — which is a coordination requirement on Layer 2, not a reason
to move ownership.

### Layer 2 — CRMBuilder as the preferred realization

Written as adoption, because on the evidence it is the better answer: the
capability overlap is large, the Audit path solves the roles problem this repo
cannot solve alone, and building a second applier means maintaining two.

**What would have to be true.** Each of these is a requirement the CRMBuilder
session would have to confirm, not something we can assert on its behalf:

1. A **headless entry point** meeting C1, with the exit codes of C4 and the JSON
   result of C5. Its reporter already emits JSON, so this is shaping an existing
   output, not inventing one.
2. A **network-standard concept** — one program set that N instances conform to,
   as against the existing per-client `programs/` model built for divergent
   clients. This is the conceptual heart of the other session's work and it is the
   requirement most likely to be reshaped.
3. **A version stamp the tool writes** (Stamp B), and a definition of the standard
   that can be versioned as a unit alongside our app-derived half.
4. **Unattended secrets** — its secrets live in the operator's OS keyring today,
   which C10 rules out for the release train.
5. **Conformance as a fleet-level result**, not a per-run log — noting that
   `Instance` and `DeploymentRun` live in its per-client schema with `master.db`
   holding only the client list, so there is no cross-client view today.
6. A ruling on the unapplyable categories, per the section above.

**What changes here if the answer is yes.** Less than it looks. The four artifacts
above stop being three separate scripts with three exit-code conventions and
become one exported desired-state document plus the conformance check that reads
it. `migrate_event_schema.py` stays as history and as the worked example of a
directive set — it is not deleted, and it is still the reference for how
`Admin/fieldManager` actually behaves (its comment that a partial PUT returns HTTP
500 with no detail, verified against EspoCRM 9.3.6, is the kind of knowledge that
must not be lost in a migration). `preflight_crm.py` becomes the gate of the
*Where it runs* section, whoever applies. The `/healthz` `crmConfig` block, the
break-glass and the pinned pair are ours in either world.

**What changes here if the answer is no** — meaning the network standard is ruled a
CBM-network artifact rather than a CRMBuilder product capability, or the
requirements session defers the headless work: Layer 3 is already the plan of
record, so nothing stops. The cost of having waited is bounded by the trigger
below.

**State the dependency honestly.** Layer 2 depends on a session that has not been
scheduled, in a repo governed requirement-first, whose answer to one of its own
open questions can relocate this work. It is the preferred realization and it is
not a plan until it is confirmed.

### Layer 3 — the fallback, and the plan of record

**Until the trigger below fires, this is what Phase 1 builds.** It is not a
contingency section.

Generalize `scripts/migrate_event_schema.py` from a hand-written change list into
a declarative desired state: one definition in this repo describing the entities,
fields, enums, links, teams, templates and settings every chapter must have, and a
runner that reconciles a live instance to it. It inherits what that script already
proves — read-before-write, per-directive skip when already correct,
admin-type assertion, `Admin/rebuild` at the end — and adds what it lacks: plan
identity (C7, from `setup/jobs.py`), the exit codes (C4), the JSON result (C5),
the version stamp (C9) and the additive-only fence (C8).

The three read-only artifacts fold in rather than being replaced:
`preflight_crm.py` becomes the conformance check and the deploy gate;
`core/schema_contract.py` becomes part of the desired state rather than a parallel
list; and `sync_form_options.py` **reverses direction** under ruling 4 — today it
pulls CRM truth into code, and in a network the code is the truth and the CRM is
made to match. That reversal is a real behavioural change to a script staff
already use, and it should ship as a second mode rather than a redefinition of the
existing one.

**The order matters, and it is chosen so that the first two deliverables survive
either answer.** Build the conformance check and the version stamp first; build
the applier last.

**The sunk cost if the switch happens after the fallback is built.** Stated
honestly, in two parts. The **desired-state definition, the conformance check, the
exit-code contract, the JSON result and both stamps are not sunk** — they are the
app-derived half this repo owns either way, and they are what a CRMBuilder
adoption would consume. What *is* sunk is **the applier's write path**: the
directive executor, the plan-fingerprint plumbing around it, and its tests.
Estimated at the larger half of the applier work — call it two to three weeks of
the month-sized block below — and it is genuinely thrown away, not repurposed,
because the whole point of adopting CRMBuilder is that it already has one. That is
the number the trigger's date should be chosen against.

### The decision trigger

**Event.** The CRMBuilder requirements session produces confirmed answers to two
of its own questions: the **product-vs-client boundary** ("is the network standard
a CRMBuilder product capability or a CBM-network artifact?") and **candidate
requirement 1, headless execution**. Either answer moves Phase 1 — a product-level
answer with a confirmed headless requirement switches Phase 1 to Layer 2; an
artifact-level answer, or headless execution declined or deferred, confirms Layer
3 permanently.

**Date. Proposed: 2026-09-19** — four weeks from the rewrite of this phase. Chosen
so the decision lands **before** Layer 3's applier write path starts, given the
build order above puts the check and the stamps first and those are roughly four
weeks of work that is not at risk. If the session has not run by that date, Layer
3 proceeds in full and the sunk cost above is accepted deliberately rather than by
drift.

**Owner. Doug** — he is the only person who can convene that session, and the
boundary question is his to rule in either repo. *Proposal, not a ruling: the
date is mine and needs his confirmation.*

Recording the trigger without a date or an owner would make it a wish. Recording
it with them makes the "wait for CRMBuilder" position falsifiable, which is the
only thing that stops it becoming an indefinite block on the one phase everything
downstream assumes.

### Acceptance criteria

Deliberately weighted toward what can be **run against crm-test and prod today,
with zero chapters involved**, because this project's standing weakness is a
verification backlog, not a documentation one. Several of these are expected to
**fail on first run** — that is the point of listing them.

**Provable today, no new decision required:**

1. The conformance check runs against **crm-test and prod** with the org-wide API
   key only, and never needs an admin login. Anything not checkable with that
   credential is reported as *not checkable*, not as conformant.
2. It reports the 7 team names from `core/config.py` per instance. **Predicted to
   fail today**: `OPEN-ITEMS.md` carries `Analytics Admin Team` as still to be
   created in both CRMs. A check that passes here is a check that is not looking.
3. It reports the 6 email templates named in code. **Predicted to fail today**:
   `CLAUDE.md` records that the five `Event*` templates are still needed.
4. It reports the 9 entities and their required fields, and the 10 enum contracts
   — matching `preflight_crm.py`'s current result on crm-test, which is the
   regression baseline for folding it in.
5. `sync_form_options.py`'s dry-run exits **0 against crm-test and against prod**
   (overriding `ESPO_BASE_URL` / `ESPO_API_KEY` for one read-only run). Whatever it
   reports is the first measured statement of how far the two CRMs have actually
   drifted on the 16 managed lists — a number nobody currently has.
6. **C3 is demonstrated, not assumed**: run the check with a deliberately
   under-granted key and confirm the report says *forbidden*, not *absent*, and
   exits 3 rather than 1. Today `preflight_crm.py` cannot pass this.
7. **Every exit code is produced on demand**: 0 against a conformant instance, 1
   against one with a hand-introduced drift, 3 against a URL that does not resolve.
   A code that has never been observed is a code that does not exist.

#### Measured, 2026-08-21 — criteria 1–5 and 7 run for real

The check was built (`scripts/preflight_crm.py`, rewritten; contract tests in
`tests/test_preflight_conformance.py`) and run against **both live instances**
with the org-wide API key only. Criterion 6 is covered by unit test rather than
live, deliberately: producing a 403 needs an under-granted key, and hammering a
production CRM with a bad credential to prove a message is not worth the auth
noise. What it found:

- **Two of the three predicted failures were wrong, and the check is what proved
  it.** All **7 required teams exist on BOTH instances** (9 teams each,
  identical lists), so `OPEN-ITEMS.md`'s "`Analytics Admin Team` — create in both
  CRMs" is **done** and closable. And `sync_form_options.py`'s dry-run exits
  **0 on crm-test**.
- **The email-template prediction was right, and worse than recorded.** All five
  `Event*` templates are missing on **both** instances. Beyond that: crm-test
  holds 2 templates, prod holds 5, so the two CRMs **diverge on templates as well
  as roles** — and **prod holds `MentorAssignmentNotice` TWICE**. The app looks
  templates up by name, so a duplicate makes which one staff send arbitrary.
  That is a live defect nobody was looking for.
- **prod drifts on exactly one managed option list, and only in ORDER.**
  `sync_form_options.py` inside the prod container exits 1 on
  `CMentorProfile.howDidYouHearAboutCBM`: same nine values, different sequence.
  No value would fail to store; the only effect is the order of a dropdown on the
  volunteer form. It is also a neat illustration of why ruling 4 reverses this
  script's arrow — with one static file serving both deploys, "which order is
  correct" has no answer until the code is the truth.
- **The check found three dead requirements in its own contract.**
  `Account.cAccountType` and `CIntakeSubmission.reason` / `.status` had been
  required for months and are written by nothing (`core/submission_log.py`, cited
  as their source, no longer exists). A gate that reports drift nobody can fix is
  a gate that gets ignored — corrected in the same commit.
- **Exit codes 1 and 3 were produced live** (drift on both instances; 22
  `unreachable` checks and exit 3 against a hostname that does not resolve), and
  0 is reachable once the templates land.

The residual value of criterion 5 stands: **the two CRMs are far closer than the
drift narrative assumed** — identical teams, identical enum values across all 16
managed lists, one ordering difference — and where they actually differ is
**email templates**, which nothing was watching.

**Provable once the applier exists (Layer 2 or 3):**

8. **Idempotence, observed in the CRM**: apply against crm-test, then apply again.
   The second run writes nothing and exits 0, and the CRM's own modification
   history shows no second write. Not "the script said skipped" — the CRM said
   nothing changed.
9. **Plan identity**: dry-run, then hand-change one field in the CRM, then apply
   the stored plan. The apply is **refused** and returns the fresh plan. This is
   the test `migrate_event_schema.py` fails today.
10. **The stamp is written last and only on success**: force one directive to fail,
    confirm the run exits 2 and Stamp B is **unchanged** from before the run.
11. `/healthz` on the crm-test app reports a `crmConfig` block whose version equals
    the standard applied, and a null block before any apply has run.
12. **The gate behaves**: with the check wired as PRE_DEPLOY on the crm-test app,
    a hand-introduced drift blocks a deploy; the break-glass variable lets that
    same deploy through with a bypass logged; removing the drift restores a clean
    deploy. All three observed, on a real deployment, not asserted.
13. **A round trip on a throwaway instance**: stand up a fresh EspoCRM, apply the
    standard, and have the conformance check pass — with a **real non-admin** user
    in each gated team able to open each app. Admins bypass ACL, so an admin test
    proves nothing ([[espo-403-diagnosis-merged-team-roles]]). This is the honest
    dress rehearsal for onboarding, and it can be done before any chapter exists.

### Size

- **A weekend.** The conformance check as an extension of `preflight_crm.py`:
  teams, email templates, JSON output, the defined exit codes, and the
  absent/forbidden/unreachable split of C3. All read-only, all API-key, and
  criteria 1–7 above are reachable at the end of it. This is also the highest
  ratio of information to effort in the whole plan — it produces the first
  measured statement of crm-test/prod divergence.
- **A week.** The `/healthz` `crmConfig` block and the `releaseTag` slot, the
  standard-version stamp's home decided and verified against a live CRM, and the
  gate wired as PRE_DEPLOY on crm-test with the break-glass — criteria 11 and 12,
  minus the applier half of 12.
- **A month, and it is the applier.** The desired-state definition generalized from
  the change list, the directive executor, plan identity, the additive-only fence,
  the extension package build, and the release-train wiring. The **roles capture
  and adjudication is inside this and is its riskiest part** — it needs two live
  CRMs read, their divergence adjudicated, and a ruling on which is the standard.
- **Cannot be estimated until a decision lands.** Anything downstream of the
  CRMBuilder boundary question: the engine itself, fleet-level conformance across
  N instances, the unattended-secrets path, and the disposition of the unapplyable
  categories. Estimating these now would be estimating someone else's requirements
  session, which is how a plan acquires a number nobody owns.

### Dependency changes this rewrite forces on other phases

Flagged, not acted on — the other phases are untouched.

- **Phase 2 (release train)** gains two things it did not have: it **owns Stamp A**
  (cutting the tag and baking it into the image — and there are zero tags in this
  repo today, so this is a build, not a wiring job), and under *Where it runs* it
  **owns the apply step**, which the earlier draft had sitting inside each
  chapter's PRE_DEPLOY job. The promotion still moves app and CRM configuration
  together, as ruling 7 requires; it moves them from the train rather than from
  the app.
- **Phase 3 (spec generation + secrets)** is **no longer a prerequisite for Phase
  1's gate** — the check needs only the org-wide API key that every app already
  has. It remains a prerequisite for automating the apply step, and that
  dependency moves with the apply step to Phase 2.
- **Phase 5 (fleet console)** becomes a **consumer** of `releaseTag`, the
  `crmConfig` block and the conformance check's JSON result, and the owner of
  none of them. If Phase 5 finds itself designing a version stamp, Phase 1 or 2
  did not finish.
- **Phase 6 (first chapter)** inherits acceptance criterion 13 — the throwaway-
  instance round trip is the onboarding runbook's dry run, and doing it inside
  Phase 1 is what makes Phase 6 a rehearsal rather than a first attempt.

---

## Per-chapter configuration and secrets

Today `.do/app.prod.yaml` and `.do/app.prod-crm.yaml` are gitignored overlays
holding plaintext secrets, applied by hand with `doctl`, and regenerating one
encrypts the secrets into unreadable `EV[…]` blobs
([[overlay-regen-encrypts-secrets]]). That is already fragile for two apps. Across
N chapter-owned accounts it is not viable.

- **One spec template plus a per-chapter values file.** The template is in this
  repo and versions with the release; the values file carries only what differs —
  chapter name, domains, CRM URL, Workspace subject, Drive id, Zoom host, feature
  flags.
- **Secrets in a real store**, referenced by the generator, never in a file on one
  laptop. This is also what makes the services org survivable as an organization:
  today the ability to deploy lives with whoever holds the overlays.
- **`/setup` remains the runtime control** for anything not boot-read. The
  denylist and `BOOT_READ_KEYS` rules are unchanged and matter more now — an
  override that silently does not apply is worse across six chapters than one.

---

## Branding, and the public pages (ruling 8)

Two places in the app deliberately reproduce Cleveland's website byte-for-byte:
`mentorprofile/frontend/` carries the site's Elementor HTML and CSS verbatim so a
mentor's preview is an exact reproduction of their public page, and
`wp-plugin/cbm-events/cbm-events.css` is copied from the live page's widgets —
that one only in v0.203.0, precisely because an approximation had been hiding a
real class-contract defect for three weeks. Both are coupled to **one specific
website**, and neither is reachable by ruling 4, because neither is CRM
configuration. Six chapters would mean six verbatim copies chasing six
independently-redesigned WordPress sites.

Ruling 8 ends this rather than multiplying it. **`prds/public-mentor-pages-plan.md`
is therefore a network-level prerequisite, not a Cleveland nicety.** Its embed
mechanics become load-bearing for every chapter: the `frame-ancestors` header (per
chapter, naming that chapter's site), height sync to the parent, and deep-link
sync so a mentor inside the frame is shareable. The same shape covers the events
programme, which `wp-plugin/cbm-events/` already almost delivers — it ships the
renderer plus the stylesheet and is one step from a distributable chapter plugin
configured with that chapter's app URL and `eventUrlBase`.

Per-chapter visual identity is then `tokens.css` overrides plus a logo — a small,
contained, versioned asset set, not a copy of anybody's site.

**De-Clevelanding is an explicit workstream** — measured in full in the next
section. In outline: the settings are cheap and already settings, the markup is
the work (18 frontend HTML files, 48 occurrences), and there are four surfaces
outside HTML that the first pass missed, including one that hands a chapter's
applicants Cleveland's own privacy policy.

---

## Phase 0 — De-Cleveland: the measured inventory

**Measured against the tree on 2026-08-20**, not estimated. The plan's earlier
figure ("18 frontend HTML files") counts *files* correctly and undercounts
*occurrences* by roughly two-thirds, and it misses four surfaces outside HTML
entirely — one of which sends the public to Cleveland's own legal documents.

Every item below is classified as **setting** (already parameterized in
`core/config.py`), **override** (a per-chapter value supplied at deploy or via
`/setup`), or **markup edit** (the name is baked into a file). The safety
property governing all of it: **with no chapter configuration set, every page
must render byte-identical to today.** Cleveland is the default, not a special
case, which is why Phase 0 needs no feature flag.

### 0. Brand-as-identifier — fenced off, and it stays

This is the distinction that keeps the workstream from doing damage. The `CBM`
and `cbm-` tokens below are **identifiers, not content**. They are never shown to
a user, renaming them is enormous churn for zero benefit, and a partial rename
breaks every page. **They are out of scope permanently — this is not an
unfinished job for someone to "complete" later.**

| Identifier surface | Count | Examples |
|---|---|---|
| `window.CBM*` JS namespaces | 12 | `CBMBusy`, `CBMDateTime`, `CBMRichText`, `CBMConversation`, `CBMEvents`, `CBMWizard`, `CBMAddress`, `CBMCharts`, `CBMQuickMail`, `CBMBirthday`, `CBMDirRender`, `CBM` |
| `--cbm-*` CSS custom properties | 52 distinct, **1223 uses** | `--cbm-navy`, `--cbm-gold`, `--cbm-surface` |
| `cbm-` class-name occurrences | **2298** | `cbm-button`, `cbm-footer__version`, `cbm-required` |
| `data-cbm-*` attributes | 4 | `data-cbm-year`, `data-cbm-version`, `data-cbm-busy`, `data-cbm-upload` |

Two of these are worse than churn — they are **contracts**. `cbm-` classes in
`wp-plugin/cbm-events/` are the class contract between the renderer and the
website's own stylesheet, guarded by a test precisely because a drift there went
unnoticed for three weeks; and `CBMEvents.config` is the object a chapter's
WordPress page configures. Renaming either breaks a live site.

**A new per-chapter attribute therefore keeps the `data-cbm-` prefix.** The
prefix names the software, not the chapter.

### 1. Settings — already parameterized, needing only a non-Cleveland default story

All in `core/config.py`. Each already reads from the environment, so a chapter
supplies its own value with no code change; what Phase 0 owes them is (a) a
default that is *derived* rather than *hardcoded to Cleveland* where possible,
and (b) a place in the per-chapter values file (Phase 3).

| Setting | Today's default | Classification |
|---|---|---|
| `ops_mailbox_name` | `"Cleveland Business Mentors"` | **setting** → should default to `organization_name` |
| `comms_internal_domains` | `"cbmentors.org"` | **setting**, per-chapter override |
| `zoom_host_email` | `"zweb@cbmentors.org"` | **setting**, per-chapter override |
| `docs_site_url` | `"https://docs.clevelandbusinessmentors.org"` | **setting**, per-chapter override |
| `events_public_base_url` | `"https://clevelandbusinessmentors.org/webinars"` | **setting**, per-chapter override |

`alert_email_from`, `gdrive_shared_drive_id`, `google_members_group` and
`app_base_url` are already Cleveland-free in code and supplied per deployment.

### 2. Locale — a fifth axis the plan did not name

Cleveland's **timezone** is hardcoded in four places, and it is not the same
thing as Cleveland's name:

- `portal/birthday.py:47` — `_LOCAL = ZoneInfo("America/New_York")`
- `assignments/service.py:942` — `ZoneInfo("America/New_York")` for the assignment stamp
- `events/config.py:72` — `PUBLIC_TIMEZONE = "America/New_York"`
- `core/zoom.py:247` — default argument
- (`comms_digest_tz` is already a setting with the same default)

A chapter outside Eastern time would show wrong calendar days on birthdays,
assignment stamps and the public events programme. **Deliberately left out of
Phase 0**, by the standard Phase 0 holds itself to: fixing this is justified
*only* by chapters that may never exist — Cleveland gains nothing. It belongs
with the per-chapter values file in **Phase 3**, and is recorded here so it is
not rediscovered as a surprise during the first onboarding.

### 3. Markup — the actual work

**18 frontend HTML files, 48 occurrences**, in three shapes:

| Shape | Count | Form |
|---|---|---|
| `<title>` | 18 | `<title>Cleveland Business Mentors — Client Administration</title>` |
| Footer | 17 | `&copy; <span data-cbm-year>2026</span> Cleveland Business Mentors. All rights reserved.<span class="cbm-footer__version" data-cbm-version></span>` |
| Body prose | 13 | headings, form labels, confirmation messages |

`setup/frontend/index.html` is the one page with a title but no footer text — it
loads `footer.js` for the year and version only. The two `events/frontend/preview*.html`
harnesses use `CBM — …` titles instead; they are developer harnesses, not shipped
pages, and are listed for completeness.

The 13 body-prose occurrences are the hardest and the most likely to be missed,
because they are **read by a member of the public**:

- `portal/frontend/index.html:17` — the portal `<h1>`
- Four public forms × "How did you hear about …?" labels
- Three public forms × the `intake__sub` lead paragraph
- Five public forms × "A member of the … team will be in touch." confirmations

### 4. Four surfaces outside HTML that the earlier count missed

| Location | What it is | Classification |
|---|---|---|
| **`frontend/shared/legal-links.js:11–15`** | **Four hardcoded Cleveland policy URLs** — client code of conduct, mentor code of ethics, terms of use, privacy policy — injected into the consent checkbox on all four consent-bearing public forms | **setting** (new) — see below |
| `directory/frontend/mentor.js:120` | Sets `document.title` in JS on the mentor profile page | markup edit |
| `core/app.py:393` | Server-rendered footer on the dev-app public form index | markup edit |
| `portal/frontend/birthday.js:176` | The birthday card's eyebrow line | markup edit |
| `forms/info_email/__init__.py:17` | `FormSpec.title = "Email to Cleveland Business Mentors"`, shown to staff in `/ops` | markup edit |
| `comms/service.py:1287` | `"company": "Cleveland Business Mentors"` on a CBM member's contact lookup result | markup edit |
| `comms/summarize.py:34` | The LLM system prompt's opening line | markup edit |
| `events/frontend/app.js:891` | A warning naming the live website | markup edit |
| `frontend/shared/tokens.css:2–10` | Header comment attributing the palette to Cleveland's staging site | comment reword |

**`legal-links.js` is the serious one.** It is the single source of truth for the
policy document URLs, its own comment says so, and every one of the four URLs
points at Cleveland's WordPress (three of them still at the *staging* host,
`cbmentostagdev.wpenginepowered.com`). A second chapter running this code would
present Cleveland's privacy policy and Cleveland's code of conduct to its own
applicants as the documents they are consenting to. That is a legal exposure, not
a branding blemish — and unlike everything else in this list, **it is worth fixing
for Cleveland alone**, since three of the four already point at a staging domain
rather than the production site.

### 5. Two names, not one — **ruled a copy bug** (Doug, 2026-08-20)

The product says **"Cleveland Business Mentors"** in 59 places in code and
**"Cleveland Business Mentoring"** in 7. The seven are not scattered: they are
*exclusively* body prose on the four public intake forms —

- `how_did_you_hear` labels on info-request, partner, sponsor, volunteer
- the `intake__sub` lead paragraph on info-request, partner, sponsor

Provenance points to a slip rather than a second brand. Commit `7cc6a8f`
("fix(volunteer): rebrand SCORE wording to Cleveland Business Mentoring on the
review step") introduced the wording, and the later partner/sponsor/info-request
forms copied the phrasing. Everywhere else the *organization* is "Mentors": the
domain is `clevelandbusinessmentors.org`, `ops_mailbox_name` is
`"Cleveland Business Mentors"`, and every footer and title says Mentors.
"Cleveland Business Mentoring" does have a legitimate separate use — it names the
**process-definition repository** (`dbower44022/ClevelandBusinessMentoring`) and
is used that way in all five markdown occurrences — but that is a repo name, not
public-facing copy.

**Doug's ruling, 2026-08-20: a copy bug. Sweep them into `{{org}}`.** So the
token vocabulary stays at one token, `organization_name`, and the seven
occurrences were replaced in v0.205.0 — the four "How did you hear about …?"
labels and the three lead paragraphs. Two parameters would have
institutionalised an inconsistency no chapter would want to reproduce.

A test now fails if the wording reappears in a frontend file, because a copied
form is exactly how it spread the first time.

**There is precedent, and it points the same way.** The v0.131.0 changelog
(2026-07-21) records the same slip in a different place — *"the PROD CRM's
Outbound Emails From Name reads 'Cleveland Business Mentoring' (with -ing) — fix
to 'Cleveland Business Mentors' … so CRM-native sends match (crm-test is already
correct)"*. So the wording has been recognised as wrong once before, in the CRM
rather than the app. That Doug-side fix was never tracked anywhere and may still
be outstanding on production; it is now in `OPEN-ITEMS.md`, because a chapter's
CRM-native sends would carry whatever that field says regardless of what the app
renders.

### 6. The logo — Phase 0 would be *introducing* one, not parameterizing one

**Verified: the application contains no image asset of any kind.** No `.svg`,
`.png`, `.jpg`, `.ico`, `.webp` or `.gif` outside the vendored Jodit editor, no
`<link rel="icon">` on any page, and every hit for "logo" in the codebase is the
word *logout*. The plan's "per-chapter `tokens.css` + logo" therefore describes a
**new feature** — a header/logo slot on 18 pages, an asset-serving path, and a
sizing contract — not a find-and-replace. **Raised, not built.** It is a scope
question for Doug and it is not required by the safety property.

### 7. `tokens.css` — the override mechanism

162 lines, 52 custom properties, all on `:root`, all consumed through
`var(--cbm-*)`. The override mechanism is therefore already latent in the
cascade: a chapter supplies a second stylesheet defining the same properties on
`:root`, loaded **after** `tokens.css`, and it cannot break the base tokens
because it can only shadow values it explicitly names — anything it omits falls
back to Cleveland's. No `!important`, no build step, no new mechanism. What Phase
0 owes is the loading slot and the rule that a chapter override may define
**only** `--cbm-*` properties on `:root` (never selectors), plus rewording the
header comment, which currently attributes the palette to Cleveland's staging
site.

### 9. What v0.205.0 actually built

**Shipped, tested, unpushed as of 2026-08-20.** The mechanism, and the sweep of
everything it covers.

- **`ORGANIZATION_NAME`** — one setting, defaulting to Cleveland, substituted
  into the markup as the `{{org}}` token by `core/branding.py`
  **server-side, as the page is served** (`BrandedStaticFiles`). Chosen over
  extending `footer.js`'s `data-cbm-*` fill because that pattern is right for
  the version (nobody reads it at first paint) and wrong for the name: the
  browser tab would flicker and the public forms' prose would visibly repaint
  after the `/healthz` round-trip.
- **The safety property was verified, not assumed** — every page's rendered
  output was compared against `origin/main`. 14 differ by exactly one invisible
  `<meta name="cbm-org">` line; 2 (the developer preview harnesses) are
  untouched; 4 carry the one deliberate visible change in the whole phase, the
  seven "…Mentoring" words Doug ruled a copy bug (§ 5). No feature flag.
- **Three code paths read HTML directly instead of through the mount** — the
  portal root, the sessions record page and the directory record pages. Each
  would have served a raw `{{org}}` to a user. They render explicitly now; it
  is the shape of bug this mechanism invites and the reason the guard test
  checks *served* output rather than files on disk.
- **The value is escaped for its context** (HTML / JS string / plain text). It
  is settable from `/setup` and it lands on the public intake forms, so it is
  treated as untrusted input, not as our own markup.
- **`ops_mailbox_name` defaults to the organisation name** via
  `Settings.sender_display_name` — a chapter says who it is once.
- **`/healthz` reports `organization`**, which is what the fleet console
  (phase 5) will label an instance by.
- **`CHAPTER_TOKENS_URL`** — the `tokens.css` override slot: a stylesheet
  loaded immediately after the base tokens, injected by the same rewrite so no
  page needs a placeholder and the nineteenth page cannot forget one. The
  cascade is the safety mechanism. Empty injects nothing.
- **`tests/test_shared_branding.py`**, 24 cases, is the thing that keeps this
  done: it fails when a new page hardcodes the name, when a new page omits it,
  when a token survives to the browser, and when someone starts renaming
  `--cbm-*` or `cbm-` classes.

**Deliberately not built, and why.**

- **`legal-links.js`.** Making the four policy URLs settings is squarely in
  Phase 0's scope and the mechanism now exists for it, but *where the links
  should point* is a decision: three of the four currently point at the
  WPEngine staging host rather than the production site, which is a live
  Cleveland defect. Bundling a decision into a mechanical sweep is how the
  wrong URL ends up on a consent checkbox. Doug's call — see § 4.
- **The logo slot** — § 6. A feature, not a parameterization.
- **The hardcoded timezone** — § 2. Phase 3.

### 8. Explicitly left alone, and why

- **`mentorprofile/frontend/`** (index.html, styles.css) — a verbatim copy of
  Cleveland's Elementor page, including 5 `clevelandbusinessmentors.org` links.
  Ruling 8 and Phase 4 retire it; parameterizing a byte-copy would fight the
  thing that makes it correct.
- **`wp-plugin/cbm-events/assets/cbm-events.css`** and
  `events/frontend/preview.css` — same reason, and the stylesheet is the class
  contract with the live site.
- **`tests/`** — assertions follow the code; they change with the sweep, not
  before it.
- **Markdown** (`prds/`, `prompts/`, guides) — these describe Cleveland as
  historical fact and are not shipped to users.
- **Comments** recording that a value came from Cleveland — provenance, not
  identity.


---

## The release train (ruling 7)

- **Merge → staging.** The services org runs a full staging deployment (app +
  CRM). Every merge lands there immediately; that is where "immediate" now lives.
- **Soak, then ship.** On a fixed cadence, a tag is cut and **every chapter moves
  to it together** — app image and CRM configuration in the same promotion.
- **`deploy_on_push` comes off chapter apps.** They deploy the pinned tag. This is
  the single largest operational change in the plan, and the one most likely to be
  missed at onboarding.
- **Rollback** is re-pinning the previous tag. Feature flags stay what they are —
  the mechanism for dark-shipping within a release, not the release gate.
- **An emergency path** for security fixes bypasses the cadence but not staging.

---

## The fleet console

Today `/setup` and `/healthz` are per-deployment, and `/setup`'s environment-diff
panel compares against exactly one peer — built for a two-instance world. A
support organization needs one view answering: who is on which tag, whose CRM has
drifted from desired state, whose worker heartbeat is stale, who has open delivery
failures or `needs_attention` submissions, whose Drive reconciliation is reporting
`unfulfillable` grants, and who is stranded at `Accepted-Provisional`.

Every one of those signals already exists per deployment — `/healthz` reports
version, environment, `dryRun`, `durableStore`, worker liveness and
`settingsVersion`; monitoring already computes backlog, oldest pending, stranded
leases and open failures. The console is an aggregator over N instances plus the
conformance check, not new instrumentation. It is what makes the support contract
deliverable by a small team, and it is a first-class deliverable rather than a
nice-to-have.

---

## Onboarding a chapter

A runbook, executed by the services org inside accounts the chapter owns
(ruling 5):

1. **Accounts.** Chapter creates its DigitalOcean account and (branch A) its
   Google Workspace; grants the services org admin access to both. Nonprofit
   credits claimed in the chapter's own name.
2. **CRM.** Provision the EspoCRM instance (Dockerized on a droplet in the
   chapter's account), install the network extension, run the config applier,
   create the services-org admin accounts and the chapter's non-admin roles.
   Verify with `preflight_crm.py` before anything is pointed at it.
3. **Google.** Branch A (bring your own): the chapter's super-admin enters the
   domain-wide delegation grant **in their own console** with the exact scope
   list — a known recurring failure point, and the impersonation subject must be
   a real licensed mailbox, never a group or alias, which fails with an error
   naming nothing useful ([[gmail-delegation-needs-licensed-mailbox]]). Branch B
   (provisioned): a domain under the network Workspace, with the exit consequence
   below stated **before** the branch is chosen.
4. **App.** Generate the spec from template + values, create web + worker +
   PRE_DEPLOY jobs, run migrations, deploy the current pinned tag.
5. **Website.** Install the chapter events plugin and the embed snippets, pointed
   at that chapter's app; set `frame-ancestors` for that chapter's domain.
6. **Go-live verification** as a real non-admin in each gated team — admins bypass
   ACL, so an admin test proves nothing.

---

## Change governance

Ruling 6 routes every configuration change through the services org, so the route
must be visibly responsive.

- **One intake** for change requests, visible to all members — a member should be
  able to see what others have asked for and where it stands.
- **A decision forum** among the funding members, with a published cadence
  matching the release train, and a standing rule that the answer is *core for
  everyone* or *no*. Under ruling 4 there is no third answer, and pretending
  otherwise is how exceptions start.
- **A published turnaround** for the operational requests that are not
  configuration at all — a user added, a permission team changed, a password
  reset. Most requests will be these, and they must never queue behind a design
  decision. Much of this is already self-service in the apps (Mentor
  Administration provisions users through the `ESPO_PROVISION_*` account
  precisely because user creation is admin-only), which is what keeps ruling 6
  from becoming a bottleneck.

---

## Non-payment and exit

Withholding **service** is legitimate. Withholding **access** must be impossible
by construction — these are independent 501(c)(3)s with their own donors, clients
and retention obligations, and a co-op that can switch a member off would never be
granted the admin concession ruling 6 depends on.

- **A frozen chapter keeps running.** Decay is gradual over months: missed Espo
  security releases, Google and Zoom API deprecations, unrotated credentials, and
  eventually a CRM change the frozen app does not know about.
- **"You keep your CRM" is not "you keep your data."** Ruling 2 makes the CRM half
  clean, but material data lives only in the app's Postgres and was deliberately
  never written to the CRM: `record_comment` (the partner and funder Discussion
  streams), the durable submission store with its Gmail thread anchors and the
  whole response-status history, authored analytics metrics and pages, and
  `app_setting` overrides. **The exit kit must include a Postgres export.**
- **Branch B is the hard exit.** A bring-your-own chapter owns its domain and
  walks away intact. A chapter provisioned inside the network Workspace has mail,
  Drive documents (in a shared drive the services org owns, with the service
  account as operational member) and calendars in someone else's tenant.
  Recoverable by Workspace data transfer — but chapters must be told this before
  choosing the branch.
- **Written in:** notice period, defined wind-down, exit kit (CRM dump, Postgres
  export, Drive transfer, per-chapter asset bundle), and a perpetual licence to
  the last version received.
- **Rehearsed once**, on crm-test, like a restore drill, with an owner and a date.
  An unexecuted exit path is a promise, not a capability.

---

## Phases

| Phase | What lands | Why here |
|---|---|---|
| **0 — De-Cleveland** | The four settings, the 18 HTML files, per-chapter `tokens.css` + logo. | Nothing else can be onboarded while the product says Cleveland. Useful alone. |
| **1 — CRM config as an artifact** | Written in three layers. **Layer 1**, the interface contract every applier must meet — headless, least-credential, five defined exit codes, a machine-readable result, plan identity, additive-only in an automatic slot, a version stamp. **Layer 2**, CRMBuilder as the preferred realization, pending its own requirements session. **Layer 3** and the current **plan of record**, the applier generalized from `migrate_event_schema.py`. Landing first either way: the extension package, the conformance check from `preflight_crm.py` wired as a read-only PRE_DEPLOY **gate**, and both version stamps. | The only genuinely new engineering, and everything downstream assumes it. Layer 1 and the conformance check are provable against crm-test **and prod** today with zero chapters involved, and they survive either answer from CRMBuilder — which is why they are built first. The applier's write path is the only part at risk from the decision trigger (2026-09-19, Doug). |
| **2 — Release train** | Staging instance, tag cutting, `deploy_on_push` off, pinned-tag deploys, emergency path. | Must precede the first real member, because it is far harder to impose later. |
| **3 — Spec generation + secrets** | Template plus per-chapter values, secrets store, generator. | The onboarding tool. Also removes the single-laptop dependency that exists today. |
| **4 — Public pages** | `prds/public-mentor-pages-plan.md` delivered network-wide; the chapter events plugin. | Ruling 8. Retires the byte-copy coupling before it is multiplied. |
| **5 — Fleet console** | Aggregated health, versions, drift, queues across N instances. | Needed the moment there is a second production tenant. |
| **6 — First chapter** | The onboarding runbook executed end to end, with the exit rehearsal. | The runbook is proven by use, not by writing. |

Phases 0 and 1 are worth doing **whatever happens with the chapters** — the first
removes hardcoded identity, the second ends the drift that has bitten this project
repeatedly with only two instances.

---

## What would make this fail

- **The change-request route being slow.** Named above; it is the top risk, and it
  is organizational rather than technical.
- **The first exception.** One chapter granted one custom field ends ruling 4, and
  the applier's desired state stops being describable.
- **Espo upgrades.** The extension and the applier both bind to Espo's admin API
  surface; a major upgrade lands on six instances at once. The train helps —
  staging sees it first.
- **`deploy_on_push` left on** at a chapter, quietly delivering unreleased `main`
  to a member's production.
- **The services org bus factor.** Today deployment ability lives with whoever
  holds the gitignored overlays. Phase 3 fixes that; until then it is the single
  point of failure for the whole network.

---

## Proposals — mine, not rulings. Please rule.

1. **Release cadence: weekly**, with the staging soak being the week itself, and a
   documented emergency path for security fixes.
2. **The staging instance is CBM's current crm-test app**, repurposed and renamed
   as the network staging tenant rather than standing up a new one.
3. **The change forum meets monthly**, with operational requests explicitly out of
   scope and answered on a published turnaround instead.
4. **Prefer branch A (bring your own Workspace)** for every chapter that can, and
   treat branch B as a transitional state with a documented path to A — because
   branch B is the only hard exit in the architecture.
5. **The fee is labour only**, chapters paying hosting and Workspace directly in
   their own accounts under their own nonprofit grants (ruling 5).
6. **The exit rehearsal is a Phase 6 deliverable with a named owner**, not a
   clause.
7. **Phase 1's decision trigger fires 2026-09-19, and Doug owns it** — the date
   is mine, the event and the owner are not negotiable for the trigger to mean
   anything. See *Phase 1 § The decision trigger*: if the CRMBuilder requirements
   session has not answered the product-vs-artifact boundary and the headless
   requirement by then, Layer 3 proceeds in full and its sunk cost is accepted
   deliberately.
