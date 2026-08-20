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

### The candidate requirements to work through with Doug

Treat every one of these as a **candidate**, to be confirmed, reshaped or
rejected with him — not as a backlog to accept. Where a candidate implies a
decision, raise the decision first.

1. **Headless execution.** The pipeline can be driven without a GUI, so that
   configure / audit / verify can run from a deploy job or CI: an entry point,
   explicit exit codes, and a machine-readable result (the reporter already
   emits JSON). Establish what a non-zero exit must mean — in particular whether
   `NOT_SUPPORTED` and `DRIFT` are failures in an unattended run, given that
   interactively they deliberately are not.
2. **A network standard.** One program set that many instances conform to,
   distinct from the existing per-client `programs/` model. This is the
   conceptual heart of the work: what "the standard" *is*, where it lives, how
   it is versioned, and how an instance records which version of it it holds.
   The release train needs that version stamp to exist.
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
