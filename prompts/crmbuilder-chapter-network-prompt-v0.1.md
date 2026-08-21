# Kickoff prompt — CRMBuilder as the chapter-network deployment engine

**Written 2026-08-18 in `cbm-client-intake`, to be run in a Claude Code session
rooted at `~/Dropbox/Projects/crmbuilder`.** It is deliberately stored here, not
there: adding files to a governed repo is itself an act that repo governs. Carry
it over, or paste it in.

**Read this first, before pasting:** the prompt below asks for *requirements
work*, not a build. CRMBuilder's governing rule is that a confirmed requirement
and an implementing PI must exist before any code — "I'm only drafting" and
"I'll apply it later" are still building. A prompt that opened with "add a CLI"
would be asking a session to break its own repo's founding rule. So the prompt
ends at confirmed requirements and an approved plan, and the build is a separate
session under a PI.

**Extended 2026-08-20** with a section the first draft lacked — *What the consumer
requires* — plus three verified refinements to the repo review below and pointers
into it from candidates 1, 2 and 5. The original prompt told this session what
CRMBuilder can do and nothing about what its consumer needs; that gap is now
closed, and the added material is candidate input like everything else here, not
a specification handed down.

---

## The prompt

You are working in **CRMBuilder**. Before anything else, orient properly:

1. Read this repo's `CLAUDE.md` in full.
2. Run the **session bootstrap** it specifies — the database is the source of
   truth. Read topic **TOP-013** and its children, active `governance_rules`,
   active `preferences`, and the `reference_pointer` index. Pull `lessons` for
   any area this work touches.
3. Confirm which engagement you are recording under before writing any
   governance record. This work is a **new engagement or a new scope within an
   existing one** — CBM is `ENG-002`, but the subject here is a *network of
   chapters* rather than CBM alone. **Ask Doug which engagement this belongs to
   rather than assuming.**

**Do not write code in this session.** The outcome of this session is: a set of
**confirmed requirements**, the decisions they depend on, and planning items to
implement them. Nothing else.

### The business context

Cleveland Business Mentors (CBM) runs a suite of custom applications over
EspoCRM (a separate repo, `cbm-client-intake` — not this one, and not in scope
here). Other mentoring chapters now want to use the same system. A planning
arc in that repo produced eight rulings from Doug, recorded in
`prds/multi-chapter-deployment-plan.md` there. The ones that constrain this
work:

- **A central services organization** owns development and support, funded by
  the chapters.
- **One EspoCRM per chapter** — never a shared multi-tenant instance.
- **Strictly identical function across all chapters — core or nothing.** No
  per-chapter fields, enum values or form questions.
- **Each chapter owns its own infrastructure** (its DigitalOcean account, its
  Google Workspace) and grants the services org administrative access. Neither
  side can lock the other out.
- **The services org holds the only EspoCRM admin accounts**; chapter staff get
  non-admin roles. This is what makes "identical" enforceable rather than
  requested — EspoCRM has no partial admin.
- **A release train**: all chapters move to the same version together, after a
  soak on a services-org staging instance. **CRM configuration is promoted with
  the app in the same release** — a release that moves one without the other is
  the drift this exists to prevent.

CRMBuilder is proposed as the tool that provisions each chapter's instance and
keeps all of them conformant to one standard.

### What a review of this repo already established

Done on 2026-08-18 from `cbm-client-intake`, read-only. Verify anything you
intend to rely on, but do not re-derive it from scratch:

- **The configure engine is already headless.** `espo_impl/core/deploy_pipeline.py`
  is explicitly "Qt-free deploy orchestration — the 12-step CHECK→ACT pipeline",
  1,207 lines, managers injected as dependencies. Nothing under
  `espo_impl/core/` imports PySide6. The Qt `RunWorker` is a ~200-line wrapper.
- **The database half of EspoCRM config is already covered** — `role_manager.py`,
  `team_manager.py`, `email_template_manager.py`, `security_rule_manager.py`,
  `entity_settings_manager.py`, `filtered_tab_manager.py`, and a pipeline step
  named "Security (teams and roles)". The Audit feature captures roles and teams
  to `security/security.yaml` by default.
- **Round-trip already exists in both directions** — Audit reverse-engineers a
  live CRM into the same YAML schema the configure engine consumes, and
  `espo_impl/core/reconcile/` compares live config against source YAML and
  writes differences back surgically.
- **In-place EspoCRM upgrades already exist** — four phases with backup and
  retention, the `chown` fix, version detection across four config locations.
- **The only console script is the GUI** (`crmbuilder = espo_impl.main:main`).
- **Three directives cannot be applied**: `savedViews`, `duplicateChecks` and
  `workflows` return `NOT_SUPPORTED` and route to a manual-configuration block,
  because `/api/v1/Metadata` accepts GET only.
- **`Instance` and `DeploymentRun` live in the per-client schema**, with
  `master.db` holding the client list — so there is no cross-client view today.
- **Secrets live in the operator's OS keyring.**
- **The tool is built for divergent clients** — `CRMBuilder-ABCOptical/` and
  `CRMbuilder-AHOPTICAL/` each carry their own `programs/`. The network case is
  the inverse: one program set, N conforming instances.

Three refinements, all verified read-only on **2026-08-20**, after the review
above:

- **Nothing has moved.** HEAD is `db1dbef0`, dated **2026-08-10** — so the
  2026-08-18 review looked at the tree that is still there.
- **`pyproject.toml` declares six console scripts, and three of them point at a
  `crmbuilder_v2` package that does not exist at HEAD** (`crmbuilder-v2-api`,
  `crmbuilder-v2-mcp`, `crmbuilder-v2-bootstrap*`). "The only console script is
  the GUI" is right about what actually runs. Flagged because it suggests
  in-flight direction of your own that this prompt knows nothing about — and if
  there is such a direction, the contract below should be shaped against it
  rather than against `espo_impl`.
- **`NOT_SUPPORTED` is not confined to the three directives.**
  `espo_impl/core/layout_manager.py` emits it too, for **portal layout variants**
  and for layouts carrying `forRoles` per-role variants (DEC-6: EspoCRM 9.x has
  no per-role layout binding without Layout Sets + Teams). Ordinary list and
  detail layouts deploy normally. This matters to the consumer because its
  Workspace Directories feature reads the CRM's own `layout/list` and
  `layout/detail` live — that dependency sits **inside** the supported set today,
  and knowing where the boundary is stops it being crossed by accident.

### What the consumer requires — the interface contract

**Added 2026-08-20**, and it is the part of this prompt that did not exist when
the rest was written. Everything above tells you what CRMBuilder *can do*. This
section tells you what its consumer *needs*, which is the other half of a
requirements conversation and the half that was missing.

It comes from `prds/multi-chapter-deployment-plan.md` § *Phase 1*, in
`cbm-client-intake`, rewritten 2026-08-20. That phase is deliberately written in
three layers: **Layer 1** is this contract, stated without naming a tool, because
it survives whatever this session rules; **Layer 2** is adopting CRMBuilder as the
realization; **Layer 3**, the current *plan of record*, is that repo generalizing
its own applier if this session says no or defers. Nothing here obliges CRMBuilder
to do anything — **these are candidates like all the others**, and the honest
answer "not in CRMBuilder" is one this session is entitled to give.

Each clause is written so a candidate implementation can be held against it and
**fail**. The clause numbers (C1…) are the plan's, so the two documents can be
read side by side.

- **C1 — Headless invocation.** One non-interactive entry point, driven by
  arguments and environment only. The consumer's precedent is a DigitalOcean App
  Platform `PRE_DEPLOY` job (`run_command: .venv/bin/alembic upgrade head`). If it
  cannot decide something, it exits — it does not ask.
- **C2 — Least credential that works.** Read-only conformance checking must need
  only the org-wide **API key**; only *applying* may require an Admin-type
  account. This is not a preference: verified 2026-08-20 in the consumer's live
  production spec, the `PRE_DEPLOY` job carries only `DATABASE_URL` while the
  EspoCRM admin credentials sit on the web service alone, so an applier in the
  deploy path means putting CRM admin credentials into N chapter-owned
  environments.
- **C3 — A credential problem must never read as a configuration problem.** Not
  hypothetical: the consumer's own `scripts/preflight_crm.py` collapses *absent*,
  *forbidden* and *unreachable* into one outcome today, because EspoCRM returns an
  **empty 200** for a scope the caller cannot see. In an unattended fleet check
  that turns "your key lost its role" into "your CRM is missing nine entities".
  Report and exit-code these three separately.
- **C4 — Exit codes with defined meanings.** This is the clause that most changes
  candidate requirement 1 below, which currently asks this session to invent the
  semantics. The consumer proposes five, and the two contested calls are stated
  as such: **0** conformant (nothing to do, or everything asked for was applied);
  **1** drift; **2** apply failed (a directive was attempted and rejected —
  deterministic, a 4xx or a validation error); **3** could not be checked
  (transport, 5xx, timeout, DNS, a 401 from a rotated password — the instance's
  conformance is *unknown*, not bad); **4** the standard names something this
  applier cannot write (`NOT_SUPPORTED`). **Drift is a failure in an unattended
  run** — the alternative is a gate that passes while reporting a difference,
  which is not a gate — and interactive-versus-unattended is a *mode flag*, not a
  different exit code. **Unknown is not bad**, which is the whole reason 3 exists:
  a fleet view must be able to say "18 conformant, 1 drifted, 1 unreachable"
  rather than collapsing the last two.
- **C5 — A machine-readable result on every exit code, including the failures.**
  A result produced only on success is useless to the console that has to explain
  a failure. Minimum shape: instance identity, standard version attempted, run
  mode, counts by outcome, and a per-directive list carrying entity, directive,
  outcome (`conformant` / `applied` / `drifted` / `failed` / `unapplyable` /
  `unchecked`) and a human-readable reason. The existing human console output
  stays; it is not the interface.
- **C6 — Idempotence, and "already conformant" is a success.** Two runs in a row:
  the second writes nothing and exits **0**. The strong form is observable — the
  second run leaves no trace in the CRM's own modification history, rather than
  merely reporting "skipped".
- **C7 — Dry-run, then apply that exact plan, refusing if the plan moved.** The
  consumer enforces this mechanically in one place (a stored plan fingerprint;
  the apply re-derives the plan, compares, and *refuses* with the fresh plan when
  they differ). Note for accuracy: the consumer's own schema applier does **not**
  do this today — it is idempotent but has no plan identity. The contract asks for
  the discipline, not for a claim that either side already has it everywhere.
- **C8 — Additive-only in any automatic slot.** Anything running in a deploy gate
  changes the CRM **before the new application code is live**, so a directive that
  removes or narrows something the currently-running code still uses opens a live
  incident for the width of the deploy. Removals, narrowings and type changes
  belong in a separate, deliberately-triggered run with a review step in front of
  it.
- **C9 — A standard-version stamp the tool writes.** See below; it is the clause
  the release train cannot do without.
- **C10 — What it must not require.** An operator's laptop. An interactive OS
  keyring. A GUI or a display. A human decision mid-run. Network access to
  anything but the instance being configured. Write access to the consumer's repo.

#### The version stamp, in more detail than candidate 2 currently carries

Verified 2026-08-20: **neither stamp exists on either side today.** The consumer's
`/healthz` reports an application version, environment, organization and a
settings-override version — **no release tag and no CRM-configuration version** —
and the consumer's repository has **zero git tags**, so the release train's tag has
never been cut.

Two distinct stamps, and conflating them is the trap:

- **Stamp A, the release tag** — "what promotion is this". The consumer's problem,
  named here only so this session does not solve it twice.
- **Stamp B, the CRM-configuration version** — "which version of the standard does
  this instance hold". **This is the one that belongs to whatever applies the
  configuration.** It must live **in the CRM**, not in the application's
  environment or database: it describes the CRM, it must survive the application
  being redeployed or replaced, and the applier should be the only thing entitled
  to write it.

Three requirements on Stamp B that the consumer cares about more than it cares
about where it is stored:

1. It is written **only after a complete successful apply**. A partial apply must
   leave the previous stamp untouched — an instance claiming conformance it does
   not have is worse than one claiming nothing, because the fleet view believes it.
2. It carries the **plan fingerprint** from C7, so "which plan was actually
   applied" is answerable after the fact.
3. It is **readable with the org-wide API key**, not only as admin — otherwise the
   consumer's own health endpoint cannot report it without dragging admin
   credentials into application runtime, which C2 exists to prevent. The
   consumer's preferred home is therefore a single-record custom entity rather
   than a key behind the admin Settings endpoint, but **the home is genuinely
   open** and this session may know better. None of the candidate homes has been
   verified against a live instance yet.

The release-train invariant these serve: **a promotion pins a pair**,
`(releaseTag, standardVersion)`, and an instance is conformant when it holds the
pair the train pinned — not when each half is independently plausible.

#### One structural consequence the consumer has already drawn

The consumer's plan originally put the applier in the deploy gate. Testing that
against the failure modes moved it, and the split is worth knowing because it
changes what this session is being asked for:

- **The deploy gate is a read-only conformance CHECK**, API key only, failing the
  deploy on drift (exit 1) and failing *distinctly* on unreachable (exit 3), with
  a documented one-deploy break-glass.
- **The apply is a release-train step**, run against each chapter's CRM
  immediately before the application promotion, with admin credentials held by the
  services organization and never resident in a chapter's application spec. The
  ruling that CRM configuration is promoted with the application in the same
  release is unchanged — the promotion still moves both, from the train rather
  than from the app.

So the capability the consumer most needs first is **conformance checking that
runs unattended and reports precisely**, and the applier second. If this session
can confirm only one requirement, that is the one worth confirming.

### The candidate requirements to work through with Doug

Treat every one of these as a **candidate**, to be confirmed, reshaped or
rejected with him — not as a backlog to accept. Where a candidate implies a
decision, raise the decision first.

1. **Headless execution.** The pipeline can be driven without a GUI, so that
   configure / audit / verify can run from a deploy job or CI: an entry point,
   explicit exit codes, and a machine-readable result (the reporter already
   emits JSON). Establish what a non-zero exit must mean — in particular whether
   `NOT_SUPPORTED` and `DRIFT` are failures in an unattended run, given that
   interactively they deliberately are not. **The consumer has now answered that
   question for its own use** — C4 above proposes five codes, rules drift a
   failure in an unattended run, and separates "could not be checked" from
   "drifted". Take it as a stated need to confirm or contest, not as a
   requirement already agreed; C2, C3 and C5 shape this same entry point.
2. **A network standard.** One program set that many instances conform to,
   distinct from the existing per-client `programs/` model. This is the
   conceptual heart of the work: what "the standard" *is*, where it lives, how
   it is versioned, and how an instance records which version of it it holds.
   The release train needs that version stamp to exist — and *The version stamp*
   above says what the consumer needs of it: written only after a complete
   successful apply, carrying the plan fingerprint, and **readable with an
   org-wide API key rather than only as admin**. The storage location is open.
3. **Conformance as a first-class result.** "Is this instance equal to the
   standard, and if not, exactly how does it differ" — reported across many
   instances, not one at a time. Much of this is the CHECK half of CHECK→ACT
   plus the reconcile diff; the question is what has to be added to make it a
   fleet-level answer rather than a per-run log.
4. **A fleet view.** Which instances exist, which standard version and which
   EspoCRM version each holds, when each was last reconciled, and what drifted.
   Note the per-client schema constraint above before designing this.
5. **The three unapplyable directives.** `savedViews`, `duplicateChecks`,
   `workflows`. Under "core or nothing" a category that must be hand-applied on
   every instance is a permanent drift source. The options named in this repo's
   own `CLAUDE.md` are reimplementation against `EntityManager` (duplicate
   checks), the Workflow entity CRUD API gated on Advanced Pack (workflows), and
   SSH-based file writes plus cache rebuild (saved views) — the last being
   outside the current API-only model. **Doug's ruling is needed**: reimplement,
   or formally exclude them from the standard and accept that they are
   configured by hand once per chapter.

   Two things the consumer would add to that ruling. First, **`duplicateChecks`
   is a behavioural dependency of the consumer's intake path, not a staff
   convenience**: a tree-wide grep on 2026-08-20 found **no**
   `X-Skip-Duplicate-Check` header anywhere in it, so whatever duplicate-check
   configuration an instance holds applies to every record the public intake
   forms create — and whether Cleveland's two instances have it configured on
   `Account` or `Contact` **has not been checked** and needs a live read. Second,
   **"cannot be applied" and "cannot be detected" may be separable**: the
   Metadata endpoint is GET-only, but GET is exactly what a check needs. Whether
   each category has a representation there a check could compare against is
   unverified — worth establishing, because a category that is excluded from the
   standard but still *detected* is a known drift rather than a blind spot. If
   they are excluded and undetectable, the consumer's gate exits **4** rather
   than 0, so that "we knowingly cannot express this" never reads as "this
   instance is conformant".
6. **System Settings and Dashboards.** Neither has a manager today
   (`entity_settings_manager` is entity-level). Decide whether they belong in
   the standard at all.
7. **Unattended secrets.** The OS keyring is an interactive-desktop assumption.
   Headless runs need another path, without weakening the existing rule that no
   secret is ever stored in a plaintext column or logged unmasked.
8. **Chapter provisioning, end to end.** Today's Setup Wizard provisions a
   droplet. The network case is a longer sequence: provision into an account the
   *chapter* owns, install, apply the standard, create the services-org admin
   accounts and the chapter's non-admin roles, then verify and report. Establish
   how much of that belongs in this tool.

### Decisions to surface early

- **New terminology needs Doug's approval and a glossary entry** — this repo's
  rule. "Chapter", "network", "standard", "conformance" and "fleet" are all
  candidates. Agree the vocabulary *before* it is written into requirements, or
  it will have to be renamed afterwards.
- **Engagement and scope**: is the chapter network a new engagement, a scope
  within CBM's, or a product-level requirement against CRMBuilder itself? This
  determines where every record lands.
- **Product vs client boundary**: is "the network standard" a CRMBuilder product
  capability, or a CBM-network artifact that happens to use CRMBuilder? Both are
  defensible; they lead to different homes for the requirements.

### Constraints to respect

- **No code in this session.** Confirmed requirements and PIs first.
- Follow this repo's `CLAUDE.md` "What NOT to Do" list in full — in particular:
  do not call `EspoAdminClient.put_metadata()` (the endpoint does not exist), do
  not add new top-level directories, do not skip `validate_program()` from any
  new YAML-loading path, and do not store secrets in plaintext columns.
- **`cbm-client-intake` is out of scope.** That repo owns the applications and
  their Postgres; this one owns CRM instances and their configuration. Do not
  propose changes to it here — surface them for its own governed process.

### What "done" looks like for this session

A set of confirmed requirements with their decisions recorded in the database,
implementing planning items created, and a short written statement of what was
*deliberately excluded* and why. If the session ends with Doug having answered
the terminology and scope questions and nothing else, that is a good session —
those answers gate everything downstream.

### Ask before assuming

The single most useful thing this session can do is ask Doug precise questions
early rather than infer. `PRDs/process/conduct/charter.md` governs how — in
particular §11.6.b, "inferences require positive support". One question at a
time; prose, not menus.
