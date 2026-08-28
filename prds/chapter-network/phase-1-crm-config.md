# Phase 1 — CRM configuration as a build artifact

**Status: in progress. The first tranche is built.** The conformance check landed
in `ac6f1b4` (2026-08-21) — `scripts/preflight_crm.py` rewritten to the contract,
with `tests/test_preflight_conformance.py` — and was run against **both live
instances**, producing the first measured statement of how far crm-test and prod
have actually drifted. The findings are in *Acceptance criteria § Measured*
below, and two of them are live production defects now tracked in
[TASKS.md](TASKS.md).

**What is left**, in the order the *Size* section argues for:

| Tranche | Deliverable | State |
|---|---|---|
| A weekend | The conformance check: teams, templates, JSON output, defined exit codes, absent/forbidden/unreachable | **done** (`ac6f1b4`) |
| A week | `/healthz` `crmConfig` block, the `releaseTag` slot, Stamp B's home decided against a live CRM, the gate wired PRE_DEPLOY on crm-test with a break-glass | **Stamp B's home done** — ruled D1 (`CNetworkStandard`), built and verified on crm-test 2026-08-27, production owed at a Sunday slot. The other three not started |
| A month | The applier: desired-state definition, directive executor, plan identity, additive-only fence, the extension package, the roles capture and adjudication | not started, and **the only part at risk from the decision trigger** |

The interface contract that governs all of it — C1–C10 and both version stamps —
is [its own file](interface-contract.md), because the CRMBuilder session needs to
read it without reading this.

---

This is the heart of the plan. Two hand-maintained instances already produce
documented drift — [[crm-test-schema-drift]], role scopes especially, team→role
attachments vanishing twice, and the two CRMs diverging often enough that
`scripts/sync_form_options.py`'s dry-run doubles as the detector. Six instances
maintained the same way is not a system, it is a support queue.

## Why this phase is written in three layers

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

## The file half — ship it as an EspoCRM extension

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


## Layer 1 — the interface contract

Moved to **[interface-contract.md](interface-contract.md)**, along with the two
version stamps it defines. It is the half of this phase that survives every
answer, and it has an audience outside this phase — which is the reason it is its
own file. **The rest of this document refers to its requirements by number**
(C1 headless, C2 least-credential, C3 absent-vs-forbidden, C4 exit codes, C5 the
JSON result, C6 idempotence, C7 plan identity, C8 additive-only, C9 the stamp,
C10 what it must not require).

## Where it runs, and whether failing the deploy is right

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

## The categories that cannot be applied

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

## What this repo owns either way

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
the mechanism.** The two halves must version together as one standard — see the pinned pair in
[interface-contract.md](interface-contract.md#the-two-version-stamps-and-where-each-comes-from) — which is a coordination requirement on Layer 2, not a reason
to move ownership.

## Layer 2 — CRMBuilder as the preferred realization

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

## Layer 3 — the fallback, and the plan of record

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

## The decision trigger

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

## Acceptance criteria

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

### Measured, 2026-08-21 — criteria 1–5 and 7 run for real

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

## Size

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

## Dependency changes this rewrite forces on other phases

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
