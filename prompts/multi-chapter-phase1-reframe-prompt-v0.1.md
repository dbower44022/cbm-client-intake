# Kickoff prompt — reframe Phase 1 of the multi-chapter plan

**Written 2026-08-20. For a fresh Claude Code session rooted in
`cbm-client-intake`.** Deliberately narrow: this session rewrites **one phase**
of one plan. It exists because Phase 1 is the plan's only genuinely new
engineering, and as written it rests on a dependency that has not started.

---

## The prompt

`prds/multi-chapter-deployment-plan.md` describes how CBM's application suite
extends to a network of mentoring chapters. Its architecture is settled — eight
rulings, do not reopen them. Your job is to **rewrite Phase 1** — "CRM config as
an artifact" — and nothing else. Leave the other phases alone except where
Phase 1's rewrite forces a dependency change, and say so when it does.

### Read first

1. This repo's `CLAUDE.md` in full.
2. `prds/multi-chapter-deployment-plan.md`, in full, but especially the section
   **"CRM configuration as a build artifact"** and the **Phases** table.
3. `prompts/crmbuilder-chapter-network-prompt-v0.1.md` — the parallel work
   handed to the CRMBuilder repo. Read its *open questions*, not just its
   findings.
4. The four existing artifacts Phase 1 builds on, all verified present
   2026-08-20: `scripts/migrate_event_schema.py` (297 lines, dry-run by
   default, `--apply` to execute), `scripts/preflight_crm.py` (181),
   `core/schema_contract.py` (93), `scripts/sync_form_options.py` (228).

### The problem you are solving

Phase 1 currently says: generalize `migrate_event_schema.py` from a change list
into a declarative desired state. A review on 2026-08-18 then established that
**CRMBuilder already covers most of that** — a Qt-free 12-step CHECK→ACT
pipeline, managers for roles, teams, email templates, security rules, entity
settings and filtered tabs, an Audit that reverse-engineers a live CRM into the
same YAML the engine consumes, a reconcile package for drift, and in-place
EspoCRM upgrades. The obvious conclusion is "Phase 1 becomes adoption, not
construction."

**Do not write that conclusion straight into the plan.** Verified 2026-08-20:
CRMBuilder's HEAD is `db1dbef0`, dated **2026-08-10**. The requirements session
that `prompts/crmbuilder-chapter-network-prompt-v0.1.md` asks for **has not
run**. That prompt ends at confirmed requirements by design, and among the
questions it puts to Doug is whether "the network standard" is a CRMBuilder
product capability or a CBM-network artifact that merely uses it. That answer
could relocate this work entirely. CRMBuilder is also governed by a
requirement-first process — its shape is not ours to assume.

So Phase 1 must be buildable whichever way that session rules, without being
vague. Write it in **three layers**.

### Layer 1 — the interface contract (the durable artifact)

What **this repo** requires of whatever applies CRM configuration, stated
without naming a tool. This is the part that survives any answer from the other
repo, and it is the most valuable thing this session can produce.

Treat these as candidates to work through, not a list to accept:

- **Headless invocation** from a `PRE_DEPLOY` job. The precedent is in the
  overlays today: `kind: PRE_DEPLOY`, `name: migrate`,
  `run_command: .venv/bin/alembic upgrade head`.
- **Exit codes with defined meanings.** The hard question is what *drift* means
  in an unattended run, and what an unapplyable directive means. Interactively
  neither is a failure; in a deploy gate they have to be one thing or the other.
- **A machine-readable result** the fleet console can consume.
- **A standard-version stamp** — an instance must be able to say which version
  of the configuration it holds, or the release train cannot pin it. See below;
  this does not exist on either side today.
- **Dry-run then apply-that-exact-plan**, refusing if the plan moved. This repo
  already uses that pattern in `/setup`'s operations tab and in
  `migrate_event_schema.py`; the contract should demand it rather than reinvent
  it.
- **Idempotence**, and what "already conformant" must exit as.
- **What it must not require**: an operator's laptop, an interactive keyring, a
  GUI, or a human deciding anything mid-run.

### Layer 2 — CRMBuilder as the preferred realization

The adoption path, written as adoption: what would have to be true, what this
repo would still own either way (the desired-state definition is arguably ours
even if the engine is theirs — decide and justify), and what changes here.
State the dependency honestly, including the possibility that the answer comes
back "not in CRMBuilder."

### Layer 3 — the fallback, named as plan-of-record

Generalizing `migrate_event_schema.py`, as Phase 1 says today — but explicitly
**the plan of record until CRMBuilder confirms**, not a footnote. It needs a
**decision trigger**: what event, by what date, and whose call, switches Phase 1
from Layer 3 to Layer 2. And an honest statement of the sunk cost if the switch
happens after the fallback is built.

### Go deeper than the plan does on these four

- **The version stamp is missing on both sides.** Verified 2026-08-20: prod
  `/healthz` reports `version`, `environment`, `dryRun`, `durableStore`, a
  `worker` block and `settings.settingsVersion` — and **no release tag and no
  CRM-configuration version**. `__version__` comes from `pyproject.toml`, which
  is the app's version, not the release train's tag. Say where each stamp comes
  from, who writes it, and where it surfaces. This is shared with Phase 2 and
  Phase 5, so name the coupling rather than solving it three times.
- **Whether failing the deploy is right.** Putting the applier in the
  `PRE_DEPLOY` slot means a chapter whose CRM cannot be reconciled does not
  deploy. Test that claim. Alembic's failure mode is a bad migration; this one's
  is a third-party HTTP API that might merely be *unreachable*. Distinguish
  "drifted" from "could not be checked", and say what each does.
- **The three unapplyable directives** — `savedViews`, `duplicateChecks`,
  `workflows` return `NOT_SUPPORTED` in CRMBuilder because `/api/v1/Metadata`
  is GET-only. Under ruling 4 a category configured by hand on every instance is
  a permanent drift source. The ruling belongs to the CRMBuilder session, but
  Phase 1 must state its own consequence under **both** answers.
- **Acceptance criteria you could fail.** Prefer things observable against
  crm-test today, with zero chapters involved, over things assertable in a
  document. This project's standing weakness is a verification backlog, not a
  documentation one.

Also size it: what is a weekend, what is a month, what cannot be estimated until
a decision lands.

### How to work

- **Update Phase 1 in place** in `prds/multi-chapter-deployment-plan.md`,
  including its row in the Phases table. **Do not create a second document, a
  summary, or a v2 file.**
- **Commit early and often.** The first session on this arc was lost to a power
  cut, and uncommitted work is the one category this project's salvage procedure
  cannot rescue (`OPEN-ITEMS.md` item 1 — cite items by title, the numbering has
  duplicates).
- **Verify before asserting.** Check names and counts against the code rather
  than repeating figures from this prompt. Where a claim needs a live CRM or a
  deployed environment, say it is unverified rather than implying it was
  checked.
- **Ask one question at a time, in prose** — a recommendation, the reasoning,
  and the single question that actually blocks you. No stacked option menus, no
  bulleted issue lists. Verify a question's premise against the live system
  before putting it to Doug.
- If you think the three-layer framing is wrong, say so **once**, in a sentence,
  with the evidence — then work within it unless Doug changes it.

### Do not

- **Do not touch the CRMBuilder repo.** Read it if you must, but write nothing:
  it is governed by a requirement-first process. Anything it needs goes into
  `prompts/crmbuilder-chapter-network-prompt-v0.1.md` in this repo.
- **Do not build.** No new scripts, no modules, no feature flags, no
  desired-state YAML "just to show the shape". The output is a plan.
- **Do not rewrite the other phases.** Flag a forced dependency change; don't
  act on it.

### What done looks like

Phase 1 of `prds/multi-chapter-deployment-plan.md` rewritten in three layers,
its Phases-table row updated, with acceptance criteria that could fail, an
honest size, and a decision trigger naming an event, a date and an owner.

**If the session produces only Layer 1, that is a good session.** The interface
contract is the durable half, and it is also the input the CRMBuilder
requirements session currently lacks — that prompt tells its session what
CRMBuilder can do, and nothing about what its consumer needs.
