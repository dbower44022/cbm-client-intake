# Multiple chapters — deployment, propagation and support

**Status: PLAN. Eight rulings settled 2026-08-17/18; the design below follows
from them. The six items in *Proposals* are mine, not Doug's — rule on them in
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

## CRM configuration as a build artifact

This is the heart of the plan. Two hand-maintained instances already produce
documented drift — [[crm-test-schema-drift]], role scopes especially, team→role
attachments vanishing twice, and the two CRMs diverging often enough that
`scripts/sync_form_options.py`'s dry-run doubles as the detector. Six instances
maintained the same way is not a system, it is a support queue.

### The file half — ship it as an EspoCRM extension

Entity and field definitions, links, layouts and formulas live in files under
`custom/Espo/Custom/`. Espo's own supported distribution mechanism for these is an
**extension package**, which brings versioning and rollback with it. The network's
CRM shape becomes a versioned extension built from this repo and installed on
every chapter instance by the release train.

### The database half — a small applier, generalized from one we already have

Roles, Teams, Email Templates, Dashboards and Settings are database rows with no
distribution path at all. They are, however, reachable: Roles, Teams and Email
Templates are ordinary records through the API as admin, and Settings has its own
admin endpoint.

**We are not starting from zero.** `scripts/migrate_event_schema.py` is already an
idempotent, **dry-run-by-default**, admin-authenticated applier: it reads current
state, creates fields through `Admin/fieldManager`, creates links through
`EntityManager/action/createLink`, patches only what differs, and finishes with
`Admin/rebuild`. It is 297 lines, hand-written for one change list, and it exists
precisely because "running it against production later produces exactly the same
schema as crm-test" was already the goal.

The build is to **generalize that from a change list into a declarative desired
state**: one definition in this repo describing the roles, teams, templates and
settings every chapter must have, and a runner that reconciles a live instance to
it. Dry-run prints the plan; `--apply` executes exactly that plan and refuses if
the plan has moved — the pattern `/setup`'s operations tab already uses.

Three existing pieces point the same direction and get folded in rather than
replaced: `scripts/preflight_crm.py` (asserts a required entity/field/enum shape
against a live CRM, read-only, non-zero exit on failure — this becomes the
conformance check), `core/schema_contract.py` (declares expected enums; becomes
part of the desired state rather than a parallel list), and
`scripts/sync_form_options.py` (pulls CRM truth into code; under ruling 4 the
arrow reverses — code becomes the truth and the CRM is made to match).

### Where it runs

As a **PRE_DEPLOY job**, exactly as `alembic upgrade head` already gates every
deploy. Alembic is the sole schema authority for Postgres; this becomes the sole
authority for CRM configuration. A chapter whose CRM cannot be reconciled fails
its deploy rather than drifting quietly.

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

**De-Clevelanding is an explicit workstream.** The settings are cheap and already
settings: `ops_mailbox_name` ("Cleveland Business Mentors"), `comms_internal_domains`
(`cbmentors.org`), `zoom_host_email` (`zweb@cbmentors.org`), `docs_site_url`. The
markup is the work: **18 frontend HTML files carry the name in the page itself.**

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
| **1 — CRM config as an artifact** | The extension package, the desired-state definition, the applier generalized from `migrate_event_schema.py`, conformance from `preflight_crm.py`, wired as PRE_DEPLOY. | The only genuinely new engineering. Everything downstream assumes it. Provable against crm-test today, with zero chapters involved. |
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
