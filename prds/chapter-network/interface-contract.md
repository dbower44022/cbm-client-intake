# The interface contract — what any CRM-configuration applier must satisfy

**Status: settled as requirements; no implementation is bound to it yet.**
Lifted out of [Phase 1](phase-1-crm-config.md) because it has two audiences that
do not overlap. It is what *this* repo requires of whatever applies CRM
configuration, stated without naming a tool, so a candidate implementation can be
held against it and fail. It is also **the input the CRMBuilder requirements
session currently lacks** — that prompt
(`prompts/crmbuilder-chapter-network-prompt-v0.1.md`) tells its session what
CRMBuilder can do and nothing about what its consumer needs. Carrying this file
into that prompt as a "what the consumer requires" section is the one legitimate
way this repo influences that one.

The two version stamps are defined here rather than in a phase file for the same
reason: Phase 1 writes Stamp B, Phase 2 writes Stamp A, Phase 5 consumes both and
owns neither. Defining them once is what stops three phases each inventing one.

---

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

## The two version stamps, and where each comes from

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
