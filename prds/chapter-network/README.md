# The chapter network

**Read this first if you are working on chapters.** This directory is the whole
project: the architecture other chapters would run on, split so that a phase can
be worked and closed without loading the rest. It is deliberately separate from
the app's ongoing feature work — the repo's `CLAUDE.md` is the anchor for *this
application*, and this file is the anchor for *the network*.

## What the project is

Other mentoring chapters like CBM want to use these apps and this website. The
requirement: **all instances hold the same configuration, and a change made once
propagates to all of them**, each chapter taking it when it chooses (ruled 09-24-26),
while each chapter keeps **its own website with its own graphics and marketing
content**.

The shape that answers it: a **central services organization** — the **Business
Mentors Association**, a limited liability company owned by its member chapters
(ruled 2026-09-19/25) — owns development and support, **one EspoCRM per
chapter**, **one application everywhere**, **each chapter owning its own
infrastructure** including its own administrator accounts, and **a release train**
that offers every chapter the same release each week.

Two of those changed in September, and the wording here follows the new rulings
rather than the old:

- **One application, not strictly identical function.** Chapters may differ
  through **optional settings and their own processes**; the application itself is
  the same everywhere. A chapter that wants something new submits a feature
  request to the Association's technical committee, and if accepted it is built
  for every chapter (ruled 2026-09-19, amending ruling 4).
- **Chapters hold their own administrator accounts.** The Association supports the
  chapter's own technical personnel and works on a chapter's system directly only
  when that contact is unavailable. Ruling 4 is therefore kept by agreement, and
  the conformance check is how anyone finds out it has been broken (ruled
  2026-09-19, replacing ruling 6).
- **Each chapter decides when its deployment takes a release** — automatically, on
  request, or at a time it schedules, after trying it on the demo/test
  deployment — and may decline one. Releases are certified by every chapter's
  technical personnel and go forward on a double-majority vote of the chapter
  representatives (ruled 2026-09-19, replacing ruling 7; confirmed in CRMBuilder
  decision DEC-1156, 2026-09-24; chapters may therefore run different releases at
  the same time, with no limit on how far behind one may fall).

Eight rulings were settled 2026-08-17/18; three of them have since been replaced
or amended. They are in **[DECISIONS.md](DECISIONS.md)**, each marked in place.
**The organization's own rulings live in
`dbower44022/business-mentors-association`** — membership, dues, governance,
liability and the Association's own systems. This directory remains the source
for the applications and the CRM.

## Where it stands

| Phase | State | Next thing |
|---|---|---|
| **[0 — De-Cleveland](phase-0-decleveland.md)** | **Substantially delivered.** v0.205.0–v0.206.0, deployed and verified on prod: `{{org}}`, `CHAPTER_TOKENS_URL`, the guard test, the four policy URLs. | A browser verification pass — the last thing owed |
| **[1 — CRM config as an artifact](phase-1-crm-config.md)** | **In progress.** The interface contract is written; the conformance check is built (`ac6f1b4`) and run against both live CRMs. Stamp B's home is ruled (D1, `CNetworkStandard`), built on BOTH CRMs (crm-test 2026-08-27, production 2026-08-31 via `build_networkstandard.py`), and **both stamps are live and SWITCHED ON** (2026-08-31): crm-test and production report `releaseTag v0.217.0` and `crmConfig unstamped`. **The roles are captured on BOTH instances and RULED** (2026-08-31): production is the standard, the API delete grant a sanctioned staging-only deviation, the extensions ruled IN (R7) — [roles-standard/](roles-standard/differences-2026-08-31.md). **The applier's home is ruled: inside CRMBuilder** (Layer 2 is the plan of record). Criterion 13 — the throwaway round trip — is done (2026-08-31). | ~~Six leftover role cells on crm-test~~ (applied 2026-09-13, `align_crmtest_roles.py`) + the § R4 table filed into phase-1; the PRE_DEPLOY gate (§ R2); then A1, the requirements session (by 2026-09-19). R0, R4, R6, R7 closed 2026-08-31 |
| **[2 — Release train](phase-2-release-train.md)** | **Started.** Cadence ruled weekly, Sunday 17:00 UTC (2026-08-26); the CRM procedure is written; `scripts/cut_release.sh` exists, **six tags are cut** (through `v0.217.0`), **both stamps are switched on** and the `release` branch exists. `deploy_on_push` is still on for Cleveland's three apps, deliberately; the Lakeside app is the first with it off. **Decided 2026-08-31:** chapter apps follow a `release` branch the weekly cut fast-forwards; images-by-tag deferred. | R10 is done, and the lane has carried two promotions (`lakeside-intake` → v0.217.0 on 2026-08-31, → v0.226.0 on 2026-09-13). The 09-06 slot was missed and the 09-13 cut ran late; v0.218–v0.225 were never tagged. **v0.228.0 made the update one operation** — the tag is stamped into `release-tag.txt` at cut time instead of each deployment's spec, so a Latest Stable deployment updates itself on the push; `lakeside-intake` is on that policy and reports `v0.228.1` with nothing set. **v0.231.1 was cut 2026-09-23 and Lakeside took it by itself within a minute of the push** (verified) — the first unattended chapter update. Next: cut on cadence each Sunday; Cleveland's `deploy_on_push` stays on until the train is trusted |
| **[3 — Spec generation + secrets](phase-3-spec-secrets.md)** | Not started. | Nothing blocks it; it also fixes today's single-laptop deploy dependency |
| **[4 — Public pages](phase-4-public-pages.md)** | Not started. Substance is in `prds/public-mentor-pages-plan.md`. | — |
| **[5 — Fleet console](phase-5-fleet-console.md)** | Not started; **ruled to be CRMBuilder** (2026-09-24, CRMBuilder decisions DEC-1152 to DEC-1159): a Deployment record per client, an update policy each client chooses (automatic, or on request with a scheduled time), an Update button, a readiness list of person-only steps with checks, secrets held in CRMBuilder with a handover file to the chapter's vault, the CRM published from the design, the apps deployed by CRMBuilder, and a web sign-in for chapter people. The model is client → application → deployment. | The CRMBuilder requirements session — kickoff `PRDs/product/crmbuilder-v2/kickoff-deployment-automation-requirements.md` in that repository |
| **[6 — First chapter](phase-6-first-chapter.md)** | **Rehearsed** (2026-08-31): steps 2, 4 and 6 run for real on a throwaway instance for a fictional chapter — record in [rehearsal-2026-08-31/](rehearsal-2026-08-31/). The instance is kept, by ruling, for step 3 | **Boston Business Mentors is the first real chapter, in progress since 2026-09-23**: the form is filled in (`chapters/boston-values.yaml`), the CRM server waits on CRMBuilder's manual-DNS mode (Boston keeps its DNS at Squarespace). **Ruled 2026-09-24 (CRMBuilder DEC-1160): Boston's hand build under this guide is its test system; its production deployment is made by the updated CRMBuilder when Boston chooses to go live.** Lakeside's step 3 (Google) and teardown remain |

**Phases 0 and 1 are worth doing whatever happens with the chapters** — the first
removes hardcoded identity, the second ends the drift that has bitten this project
repeatedly with only two instances. Everything from Phase 2 on is contingent on
there actually being a network.

The live work list is **[TASKS.md](TASKS.md)**, where every entry carries a plain
summary of the issue, the options and a recommendation where a decision is owed,
and step-by-step instructions. Its Part 1 is the four decisions currently blocking
otherwise-ready work — start there. The organizational rulings that block nothing
are in **[DECISIONS.md](DECISIONS.md)**.

## The files

| File | What it holds | Changes when |
|---|---|---|
| `README.md` | This. Orientation and current state. | A phase changes state |
| [`DECISIONS.md`](DECISIONS.md) | The eight rulings — three of them replaced or amended on 2026-09-19, marked in place — the proposals awaiting a ruling, the decision log, and the open questions nobody owns yet | Doug rules something |
| [`TASKS.md`](TASKS.md) | The project's own open items. Each one: what the issue is, the options and a recommendation where a decision is owed, then steps | Every working session |
| [`chapter-values.md`](chapter-values.md) | **Everything that differs between cities** — ~35 values, six secrets, one image. The per-city surface in one place, plus the ruling-4 fence listing what is deliberately the same everywhere | A new per-chapter value appears, or one gets parameterized |
| [`crm-update-runbook.md`](crm-update-runbook.md) | **How to get a configuration change onto every CRM, step by step.** The procedure, the verification, and the twelve traps this project has been bitten by | The procedure changes — chiefly when the applier lands |
| [`interface-contract.md`](interface-contract.md) | C1–C10 and both version stamps: what any CRM-config applier must satisfy | Rarely. It is meant to be stable, and it has a reader outside this repo |
| `phase-0…6-*.md` | One file per phase, each closable on its own | Work on that phase |
| [`governance-and-exit.md`](governance-and-exit.md) | Change governance, non-payment, the exit kit. **Written before the 2026-09-19 rulings** — its case for withholding administrator accounts no longer holds, and the exit licence is now the open-source licence | The organizational design changes |
| [`deployment-guide/guide/`](deployment-guide/guide/README.md) | **The New Chapter Deployment Guide** — one page per stage, generated from `deployment-guide/steps/` (the source, and the onboarding app's specification). Render with `scripts/render_deployment_guide.py` | A step changes: edit the YAML, re-render |
| [`deployment-guide/`](deployment-guide/) | **Drafts of the New Chapter Deployment Guide** — the plan for writing it, the step list, the written-out methods for all eighteen stages, and the work owed before any chapter can follow it | The guide is drafted further |

## Working this project separately

**There is no branch-level lane yet, and that is the same defect the project
exists to fix.** All three CBM apps track `main` with `deploy_on_push: true`, so a
push deploys dev, crm-test *and* prod. [Phase 2](phase-2-release-train.md) is what
creates a real lane. Until then, separation is by discipline:

- **Documents and read-only scripts are inert.** Everything in this directory,
  plus `scripts/preflight_crm.py`, ships to production on every push and does
  nothing there. Work them on `main` freely.
- **Anything that touches runtime ships dark**, behind a flag defaulting off, and
  is reviewed on crm-test as a real non-admin before the flag reaches the prod
  overlay. That is the repo's existing gate and this project does not get an
  exception from it.
- **A chapter change that alters Cleveland's behaviour is not a chapter change.**
  The safety property Phase 0 held itself to — an unconfigured deployment renders
  and behaves exactly as it did before — is the standard for every later phase
  too. Where a phase cannot hold it, say so in that phase's file.

**A session working this project** should read this file, `DECISIONS.md`, and the
one phase file it is working. It should not need the 1,235-line original, which
is now a pointer file — kept only so that the changelog, the session prompts and
the commit history that cite it by path still land somewhere. It *will* still need the repo's `CLAUDE.md`
for how the application works.

## Other repositories this touches

The network spans more than this repo, and only this one's `CLAUDE.md` loads
automatically. Read the other repo's own rules before creating or changing
anything in it.

| Repo / system | Relationship | Rule |
|---|---|---|
| **`dbower44022/business-mentors-association`** | **The services organization's own records** — its rulings, open questions, proposal summary, cost list and account setup runbook. The organization is a limited liability company owned by its member chapters | Where the two disagree about the *organization*, that repository is the source. This directory stays the source for the applications and the CRM |
| **CRMBuilder** | **The ruled home of Phase 1's applier** (Doug, 2026-08-31 — a product capability). HEAD `db1dbef0`, 2026-08-10; nothing has moved since the 2026-08-18 read-only review. | **Requirement-first governance.** Its shape is not ours to assume, and we cannot write a plan that obliges it to grow an interface it has not agreed to. Read-only from here until the requirements session runs |
| **`dbower44022/ClevelandBusinessMentoring`** | Owns **MN-INTAKE**, the business definition of the client-intake process. The Requirements Spec here is kept aligned to it by carry-forward | Process definition, not application. Changes there are Doug's |
| The chapters' **WordPress sites** | Ruling 8: the app serves the public pages, each chapter's site embeds them. `wp-plugin/cbm-events/` already ships the renderer plus the site's own stylesheet | The stylesheet is a **class contract**, guarded by a test. Do not restyle it |
| **DigitalOcean, per chapter** | Ruling 5: each chapter owns its account and grants the services org access | Lock-out must be impossible in either direction |

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

## What would make this fail

- **The change-request route being slow.** Named above; it is the top risk, and it
  is organizational rather than technical. It is sharper since 2026-09-19: a
  chapter that cannot get a change now holds the administrator account it would
  need to make one itself.
- **The first exception.** One chapter's own custom field ends the one-application
  rule, and the applier's desired state stops being describable. Nothing prevents
  it technically any more — the chapter agreement and the conformance check are
  the whole defence.
- **Espo upgrades.** The extension and the applier both bind to Espo's admin API
  surface; a major upgrade lands on six instances at once. The train helps —
  staging sees it first.
- **`deploy_on_push` left on** at a chapter, quietly delivering unreleased `main`
  to a member's production.
- **The services org bus factor.** Today deployment ability lives with whoever
  holds the gitignored overlays. Phase 3 fixes that; until then it is the single
  point of failure for the whole network. The Association's own rulings start it
  with volunteers, which does not fix this.


---

*Split out of `prds/multi-chapter-deployment-plan.md` on 2026-08-24. Nothing was
summarized away: every section of that document is in one of these files, and the
substance of the rulings is unchanged.*
