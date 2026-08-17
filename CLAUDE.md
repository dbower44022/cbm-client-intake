# CLAUDE.md

Guidance for Claude Code working in the **cbm-client-intake** repository.
Read automatically at session start — the orientation anchor if a session is lost.

**Keeping this file useful.** It is loaded into *every* session, so it earns its
size or it costs every future session. The rule that keeps it small:

- **Release history belongs in `CHANGELOG.md`**, which already carries every
  version in equal or greater detail. Do not narrate releases here.
- **Unresolved work belongs in `OPEN-ITEMS.md`** — outstanding CRM
  prerequisites, live verification owed, cleanups, pending decisions.
- **This file holds only what stays true**: what each app is, the constraints
  and rulings that govern future work, the traps, the conventions.
- The "Current status" section at the bottom is a **rolling window of the last
  few releases**. When a release is deployed and verified, delete its block —
  the changelog owns it. Do not prepend a new block and keep the old ones.

## What this is

A custom web application for **Cleveland Business Mentors (CBM)**. It hosts
branded, multi-step wizard **intake forms** whose submissions create linked
records in EspoCRM (the system of record), plus a suite of **staff and mentor
tools** over that same CRM.

This repo owns the *application*, not the business definition of the process.
The Client Intake process is defined by **MN-INTAKE** in the
`dbower44022/ClevelandBusinessMentoring` repo; the Requirements Spec here is
kept aligned to it by carry-forward.

### The five public intake forms

The **orchestrator module is the source-of-truth mapping** for each form.

| Form | Creates |
|---|---|
| **client-intake** | Account → Contact → CClientProfile → CEngagement |
| **volunteer** | Contact (`cContactType=["Mentor"]`) → CMentorProfile, optional in-memory resume |
| **info-request** | Contact (`Prospect`) + Account when a company is given + a `CInformationRequest` |
| **partner** | Account (`cCompanyType=["Partner"]`) → Contact → CPartnerProfile (`Candidate`) |
| **sponsor** | Account (`cCompanyType=["Sponsor"]`) → Contact → CSponsorProfile |

Cross-form behaviour worth knowing before changing an orchestrator:

- **Company type is `cCompanyType`, never `cAccountType`.** The Account entity
  is presented as **Company**; `cAccountType` is gone from both CRMs. Valid
  options are `Client / Sponsor / Partner / Other` — the sponsor value is
  `"Sponsor"`, NOT `"Donor/Sponsor"`, and **EspoCRM rejects an invalid multiEnum
  outright** (the create 400s, nothing written). See
  [[prod-account-caccounttype-missing]].
- **Repeat submitters null-fill, never overwrite** —
  `core/crm_upsert.find_create_or_fill` reuses an existing Contact and backfills
  only empty fields. `CClientProfile` is find-or-create too (matched on
  `linkedCompanyId`): it used to be an unconditional create, and because
  `linkedCompany` is a **hasOne**, a second profile silently moved the company
  and contact off the first.
- **Near-duplicate submissions are held, not delivered** — same form + same
  email inside `DUPLICATE_HOLD_SECONDS` (default 24h) is captured with status
  `held_duplicate` for review in Submission Admin. Fails open; `=0` disables.
- **info-request** appends to an existing contact's description on a repeat
  email (needs the Contact *edit* grant, which the API user has).
- Consent is one checkbox writing three Contact bools (`cTermsOfUseAccepted`,
  `cPrivacyPolicyAccepted`, `cCodeOfConductAccepted`) plus
  `CMentorProfile.mentorCodeAccepted` / `ethicsAgreementAccepted` on volunteer.
- Volunteer's `contact_preference`, `currently_employed` and `how_did_you_hear`
  are **required in the form only** (frontend `required` + `checkValidity()`),
  deliberately NOT in the Pydantic schema — a direct API call may omit them.
- Every input collected across all five forms maps to a real CRM field; nothing
  is silently dropped. Record: `field-mapping-completion-plan.md`.

## Deployment

Three DigitalOcean App Platform apps, all building `main` from
`dbower44022/cbm-client-intake` — **a push deploys crm-test AND prod.** Full
runbook: `DEPLOYMENT.md`; plain-language console companion:
`STAFF-DEPLOYMENT-GUIDE.md`.

| Env | Root URL | CRM | App ID |
|---|---|---|---|
| **prod** | https://apps.clevelandbusinessmentors.org/ (custom domain, primary) | production | `aa1ddf69-f359-4b53-91ba-035cbed7bd53` |
| **crm-test** | https://cbm-client-intake-svxs3.ondigitalocean.app/ | crm-test | `509b4370-b9ca-42c7-b251-04d6820fe88e` |
| **dev** (`lobster-app`) | https://lobster-app-w6h5m.ondigitalocean.app/ | none — dry-run | `b3b28113-6113-4ba7-ae99-efd5ea633fcd` |

- Config lives in **gitignored overlays**: `.do/app.prod.yaml` (crm-test) and
  `.do/app.prod-crm.yaml` (prod), applied with
  `doctl apps update <app-id> --spec <file>`. **Regenerating an overlay from
  `doctl apps spec get` encrypts plaintext secrets into `EV[…]` blobs** — save
  any creds you still need locally first ([[overlay-regen-encrypts-secrets]]).
- Each app runs a **web** component and a **`delivery-worker`** (`python -m
  worker`), plus a **PRE_DEPLOY `migrate` job** (`alembic upgrade head`).
  Alembic is the sole schema authority — there is no boot-time `create_all()`,
  so a fresh environment must migrate before first boot.
- `/healthz` reports version, environment, `dryRun`, `durableStore` and a
  worker-liveness block. It is the deploy marker.
- **Which component gets which flag matters**: the worker runs the delivery
  loop, monitoring, Gmail sync, Drive reconciliation, transcripts and receipt
  sweeps; the web process runs everything user-facing plus worker-liveness
  watching. Getting this wrong is a common cause of "the feature is on but
  nothing happens."
- **There is no branch-level review gate** — all three apps track `main` with
  `deploy_on_push: true`, so one push builds dev, crm-test AND prod. The gate is
  the **feature flag**: build it dark (default off), enable it on crm-test's
  overlay, review live as a **real non-admin** in the relevant team (admins
  bypass ACL), then add the var to the prod overlay. Rollback is flipping the
  flag back, not reverting code. Runbook: `DEPLOYMENT.md` § *Reviewing a change
  before it reaches production*.
- To run a script inside a deployed container (the only way to reach prod
  secrets), see [[do-app-console-scripting]]. Admin CRM creds are on **web**
  only.

## Commands

```bash
uv sync                                  # install deps (uv-managed; package = false)
uv run uvicorn main:app --reload --port 8000   # run locally -> http://localhost:8000/
uv run pytest -q                         # tests
docker build -t cbm-intake . && docker run --rm -p 8099:8080 cbm-intake  # prod-like run
./scripts/deploy.sh                      # deploy to DO App Platform (see DEPLOYMENT.md)
uv run python scripts/sync_form_options.py          # dry-run: form dropdowns vs live CRM enums
uv run python scripts/sync_form_options.py --write  # apply the sync (review the git diff)
```

## Architecture

A shared core hosts any number of per-form packages, plus one package per
staff/mentor tool.

- `main.py` — composition root: `create_app([...SPECS])`.
- `core/` — the only place that holds EspoCRM credentials.
  - `app.py` — FastAPI factory. Per form: `POST /api/{slug}/intake` + `/{slug}/`.
    Also `GET /` (portal, or the form index on dev), `GET /healthz`, `/shared/`.
    Honeypot (`company_url`) and submission-token idempotency live here.
  - `espo.py` — `EspoClient` (real) and `DryRunEspoClient`. All calls funnel
    through `_request`, which wraps httpx transport failures as
    `EspoTransportError(EspoError)` so every `except EspoError` net covers CRM
    outages. `forbidden_hint` turns a 403 into a message naming the exact denied
    entity and operation.
  - `config.py` — `pydantic-settings`. **All settings default** and
    `espo_dry_run` defaults to `True`, so the app boots with zero env vars.
  - `store.py` — the durable submission store (V2). `receipts.py` — the
    CIntakeSubmission receipt engine. `resumable.py` — `ResumableClient`, which
    makes delivery replay-safe. `action_log.py` — staff-action history.
    `admin_client.py` — the shared provisioning-admin login + token cache.
  - `crm_upsert.py`, `enum_filter.py`, `phone.py`, `stream.py`, `monitoring.py`,
    `schema_contract.py` — the CRM-boundary helpers described under Gotchas.
  - Integration clients: `gmail.py`, `gcalendar.py`, `gdrive.py`, `gmeet.py`,
    `fathom.py`, `zoom.py`, `google_directory.py`.
- `forms/<name>/` — `schemas.py`, `orchestrator.py`, `frontend/`, and `SPEC`.
- `frontend/shared/` — `tokens.css` (CBM design tokens), `wizard.css/js`,
  `busy.js`, `richtext.js` + vendored Jodit, `quickmail.js`,
  `conversation.js/css`, `charts.js/css`, `phone-format.js`.

The frontend is plain HTML/CSS/vanilla JS — **no build step**. The wizard posts
to its own origin, so CORS is not in the request path; `ALLOWED_ORIGINS` only
matters if a separate frontend origin is ever introduced.

### Environment indicator

Every page names the deploy target in the footer after the version —
`v0.187.0 (Production)` / `(Test)` / `(Dev)`. **Derived server-side**, not
configured per deploy: `Settings.environment` returns `dev` when `espo_dry_run`
is on, `test` when `espo_base_url` contains `crm-test`, else `production`
(`ENV_LABEL` overrides the wording). Surfaced on `/healthz`. Forms read it via
`frontend/shared/footer.js`; the landing page renders it server-side.

Note the footer reads `/healthz` (the **server**), so a stale cached `app.js`
shows the new version with old behaviour — hard-refresh before diagnosing
([[footer-version-stale-js]]).

### Form dropdown lists — static, synced from the CRM on demand

Each form's `frontend/options.js` ships hand-curated static lists (forms stay
fast and stateless — no CRM call at page load). CRM-backed arrays are wrapped in
sentinel comments and refreshed by `scripts/sync_form_options.py`:

```js
// >>> crm-enum key=industryExperience field=CMentorProfile.industrySector — generated; do not hand-edit between the markers.
industryExperience: [ ... ],
// <<< crm-enum
```

The marker is self-describing (no mapping duplicated in the script) and supports
`exclude="A|B"`. Default run is a **non-destructive dry-run** that exits
non-zero on drift, so it doubles as a CI check; `--write` applies, then review
the diff and commit. 8 lists are managed today. The static file serves **both**
deploys, so synced values must be valid on crm-test *and* prod — the dry-run is
also how you catch the two CRMs diverging. To check prod, override
`ESPO_BASE_URL`/`ESPO_API_KEY` for one run (read-only metadata GETs).

A value outside the live enum would 400 the create, but the orchestrators'
`EnumSanitizer` drops it first — so the real symptom of drift is a field
silently storing nothing.

## The V2 reliability platform — `prds/v2/`

Never lose a submission, keep working when the CRM is down, deliver exactly once
with retries, alert on trouble. **Live in production.** Specs in `prds/v2/`.

- **Durable capture** — with `DATABASE_URL` set, every submission is written to
  Postgres BEFORE any CRM call and idempotency is enforced by the
  `uq_submission_form_token` unique key. Empty `DATABASE_URL` ⇒ exact V1
  behaviour.
- **Async delivery** (`ASYNC_DELIVERY`) — the endpoint returns
  `received`+`reference` on capture; the worker claims due rows
  (`FOR UPDATE SKIP LOCKED` with a **lease**, so a worker that dies mid-delivery
  is reclaimed rather than stranding the row), delivers via the orchestrators,
  and retries transient failures with backoff (1m/5m/30m/2h/6h → then
  `needs_attention`). **4xx is permanent.** Delivery is **resumable** —
  `ResumableClient` records each create/upload in the `progress` column and
  skips it on retry, so a half-finished chain converges to one complete set and
  a re-drive resumes rather than duplicating.
- **Monitoring** — the worker runs periodic alerting (backlog, oldest pending,
  stranded leases, open failures) and a **schema-drift check** against
  `core/schema_contract.py`. Alerts go to `ALERT_EMAIL_TO` via the Gmail
  delegation, or `ALERT_WEBHOOK_URL`, else a WARNING log. The web process
  watches the worker heartbeat.
- **Rollback is instant** via the overlay: `ASYNC_DELIVERY=false` → synchronous;
  drop `DATABASE_URL` → V1.
- **Gotcha:** DO's `DATABASE_URL` ends in `?sslmode=require`, which asyncpg
  rejects — `core/store.make_async_engine` strips `sslmode`/`channel_binding`
  and sets SSL via `connect_args`.

Alerts count only **open** failures (`needs_attention` AND not closed), so
closing a submission in Submission Admin actually clears the recurring email.

## Portal + authentication — `/`

The root of both staff-stack apps is an **authenticated portal** (`portal/`).
One CRM login (`POST /api/portal/login` → EspoCRM `App/user`) puts the user's
token in a shared signed session cookie (`assignments.auth.SESSION_KEY =
"staff_user"`), and **every app reads and writes as that user**, so EspoCRM
enforces their ACL and records them as modifier. The dev app (no
`SESSION_SECRET`) keeps the old public form index.

- **Each app enforces its own team gate per request** — the portal listing is
  convenience, not the security boundary. 401 → the frontend redirects to
  `/?next=<app>`; 403 names the required team; admins always pass.
- **Gate by Team, not Role.** A regular user's own token can read its
  `teamsNames` but NOT its `rolesNames` ([[crm-test-assignment-acl-fields]]).
- Membership is **re-read from the CRM on every session restore**, and staff API
  requests re-check when the session stamp is older than
  `MEMBERSHIP_REFRESH_SECONDS` (default 900) — so a team granted after sign-in
  works without a re-login, and a dead token clears the session.
- Portal tiles open apps in **stable named browser tabs**, so re-clicking reuses
  the tab. Also on the portal: a Documentation link (`DOCS_SITE_URL` →
  docs.clevelandbusinessmentors.org), attention badges, the analytics dashboard
  panel, and the birthday overlay.
- "Forgot your password?" proxies EspoCRM's own unauthenticated
  `User/passwordChangeRequest` — the CRM matches, throttles and emails its
  standard recovery link; the app never sees or sets a password.

**Team gates** (each an env var, listed with its default):
`ASSIGN_ALLOWED_TEAMS` = Client Administration Team · `MENTOR_ADMIN_ALLOWED_TEAMS`
= Mentor Administration Team · `MENTOR_PROFILE_ALLOWED_TEAMS` = Mentor Team ·
`SESSION_MENTOR_ALLOWED_TEAMS` = Mentor Team · `SESSION_PARTNER_ALLOWED_TEAMS` =
Partner Management Team · `SESSION_SPONSOR_ALLOWED_TEAMS` = Sponsor Management
Team · `OPS_ALLOWED_TEAMS` = Marketing Admin Team · `WORKSPACE_ALLOWED_TEAMS` =
Mentor Team · `ANALYTICS_VIEW_ALLOWED_TEAMS` / `ANALYTICS_ADMIN_ALLOWED_TEAMS` =
Analytics Admin Team.

## The applications

Every staff/mentor tool follows the same shape: a package with `service.py`
(the CRM logic and the **field whitelist**), `router.py` (endpoints, gate, the
`_crm_failure` mapping), and `frontend/` (vanilla JS, no build). A recurring
pattern worth knowing before adding a field anywhere: **one declared field spec
serves as BOTH the form layout and the server-side update whitelist**, and
enum options + required flags are read **live from CRM metadata** so the CRM
stays the source of truth.

### Client Administration — `/assignments`

Staff-only. Page title is "Client Administration"; the package and route stay
`assignments`. Lists `CEngagement` records in a sortable, searchable,
full-height grid with a status multi-select, and assigns each to a mentor.

- **Mentor dropdown** = `CMentorProfile` where `acceptingNewClients=true` AND
  `mentorStatus="Active"` AND `assignedUser` set. An empty dropdown means no
  mentor passes all three.
- **Assign** (`service.assign_engagement`) sets `mentorProfile` +
  `engagementStatus="Pending Acceptance"`, stamps `engagementAssignedDate`, and
  re-homes assigned users across every related Contact, the CClientProfile and
  the Account. **Merge, never overwrite** (`_merged_assignment_payload`) — an
  overwrite silently revokes co-mentor access.
- **Stale-write guard**: the engagement is re-read before any write and the call
  is rejected (400, nothing written) if it already has a mentor or is no longer
  `Submitted`. The frontend reloads the grid on any Assign 400.
- **Assigning the SAME mentor again is a repair run**, not an error — it
  re-executes the idempotent re-homing. Reachable from the row's right-click
  menu ("Repair assignment…"), which is the only door to it since assigned rows
  have no Assign control.
- **Reassign Mentor** swaps `mentorProfile`, re-stamps the date, re-homes
  everything including every CSession (swap-merge: the old mentor is removed
  unless a co-mentor shares the user or they personally own the session),
  and deliberately **leaves `engagementStatus` untouched**.
- A successful Assign/Reassign opens the quick-compose with the mentor's
  `cbmEmail` and the EspoCRM `MentorAssignmentNotice` template pre-applied.
- Every row function is also on the **right-click context menu**. The Notes
  column edits `CEngagement.description` inline — staff-internal by design, and
  excluded from the session tools' Details tab for that reason.

### Mentor Administration — `/mentoradmin`

Staff-only, page title "Mentor Administration". The full mentor roster plus a
detail screen that edits any whitelisted field on `CMentorProfile`.

- **`EDITABLE_FIELDS` in `mentoradmin/service.py`** is the single source for the
  tabbed layout and the update whitelist. Fields marked `entity: "Contact"`
  route to the mentor's **linked Contact** (no linked Contact ⇒ a readable 400
  *before any write*).
- **Save sends only changed fields** (diffed against a render-time snapshot).
  Re-sending an unchanged value that has since drifted out of its CRM enum would
  400 the whole update.
- **Completeness badge** — a mentor is Complete when a Contact is linked and
  ethics/training/terms are all true (**background check is optional**); plus,
  if Active, a CBM email and a User assigned to *both* the member and its
  Contact. `publicProfile` is deliberately not part of completeness. The
  computed value persists to `recordStatus` on save **and on view** when it
  changed, so the grid self-heals; a manual `Duplicate` is never overwritten.
- **`reconcile_user_links` runs on every save** (best-effort), assigning the
  mentor's User to both the member and its Contact — this is what self-heals
  one-sided assignments.
- **Approval → user provisioning.** A save leaving `mentorStatus` at Approved or
  Active with no linked login, and `MENTOR_PROVISION_USERS` on, creates an
  EspoCRM User (`firstname.lastname@cbmentors.org`, welcome email via
  `sendAccessInfo`), places it in `MENTOR_TEAM_NAME`, links it as
  `assignedUser`, back-fills `cbmEmail`, and stamps the User onto the linked
  Contact. **Privilege split — EspoCRM makes User creation admin-only; API keys
  and `api`-type users cannot do it and a *regular* user with roles 403s.** So
  this runs as a **dedicated admin service account** (`ESPO_PROVISION_*`,
  Type=Admin) via `core/admin_client.py` — Mentor Admin staff stay non-admin.
  Best-effort: a failure returns `provision:{ok:false,error}` and never rolls
  back the saved status.
- **Permission teams** on the Status tab write the linked **User's** `teamsIds`
  (teams live on the User, not the profile), also under the admin account.
  Always clickable; a login-less mentor gets an explanatory message.
- **"Update Mentor Status"** sweeps the roster: verifies each login User, checks
  the mailbox, runs `reconcile_user_links`, and bulk re-syncs `recordStatus`.
  This is the staff-facing repair button for stamp drift.
- Functional reference for staff: `mentor-administration.md`.

### My Mentor Profile — `/mentorprofile`

Mentor self-service (Mentor Team, not staff-only): a mentor edits their OWN
profile + linked Contact, with a live preview that is an **exact reproduction of
the public website mentor page** — the Elementor HTML and CSS were copied
verbatim from the live site into `mentorprofile/frontend/`. **Keep the marked
block in styles.css in sync if the website template changes.** Rendered at the
site's 1200px desktop width and scaled to fit; the mobile media block is
deliberately omitted.

- **Always "me"** — no record id from the client. Every endpoint resolves the
  caller's own profile server-side via `resolve_manager_profile`.
- **`PROFILE_FIELDS`** is the layout + whitelist and is deliberately
  **non-administrative**: status/type, compliance, dues, cbmEmail and departure
  are NOT in it, and smuggled changes are dropped. The page has no width cap.
- Photo upload is base64 JSON → Attachment → `profilePhotoId`; display proxies
  through the app (`GET /photo`) because the browser can't reach the CRM.
- Also hosts the **email-signature editor** (EspoCRM `Preferences.signature`).
- The `description` field is surfaced here as **"Personal interests"** — it is
  what the directory's mentor profile page shows to fellow members, and this is
  the single edit surface for it.
- The page-slot ↔ CRM-field mapping for the WordPress feed is in
  `cmentorprofile-summary-field.md`.

### Session Management — `/mentorsessions`, `/partnersessions`, `/sponsorsessions`

User-facing titles: **Client Management**, **Partner Management**, **Funder
Management**. Packages, routes, slugs and team gates are unchanged. "Funder" is
display wording only — the CRM entities stay `CSponsorProfile` etc.

**One configurable engine, three team-gated routes.** Managers review the
records they own and record meetings as **`CSession`** records — one entity with
the parent link swapped. The domains differ only by a per-domain
`sessions/config.py:DomainConfig`; the whole feature is one engine
(`sessions/service.py`), one router factory (`sessions/router.make_router`), and
one shared frontend that derives its domain from the first segment of its URL.

| slug | parent | owned-records link on the user's `CMentorProfile` | co-mentors |
|---|---|---|---|
| `mentorsessions` | `CEngagement` | `engagements1` (+ `engagements` for co-mentored) | yes |
| `partnersessions` | `CPartnerProfile` | `managedPartners` | no |
| `sponsorsessions` | `CSponsorProfile` | `managedSponsors` | no |

- **Managers are `CMentorProfile` records** — the one whose `assignedUser` is
  their login. `resolve_manager_profile` matches `assignedUser` **in Python,
  never a `where` on `assignedUserId`** (prod's field ACL forbids it). A record
  assigned to a *duplicate unlinked* profile is invisible here — a recurring
  data trap ([[crm-test-duplicate-mentor-profiles]],
  [[sessions-manager-profile-must-be-assigned]]).
- **Partner and Funder grids list ALL records** (`DomainConfig.list_all`), not
  just owned ones — the user's CRM ACL is the gate. This also means those
  domains never read `CMentorProfile` for the list, which is what fixed the
  sponsor-team 403.
- **Detail tabs**: Overview · Details · Sessions · Communications · Documents,
  plus Contributions (funder only), Referred Clients (partner only), and
  Analytics (when enabled). Each optional tab is gated by a `DomainConfig` field
  that controls **both the tab and the endpoint registration** — a router that
  doesn't own the feature never registers its routes.
- **Overview** is a facts rail + notes feed with drag splitters, an aggregated
  Company peek, a Next-session callout with a Start/Open button, and (partner +
  funder) a **Discussion pane** — an app-only, append-only, attributed comment
  stream in the `record_comment` Postgres table, **never written to the CRM or
  shown to the partner/funder**. Record notes edit in place from the Overview.
  Every scalar rail fact renders "—" when empty rather than vanishing (an empty
  slot that disappears reads as a missing feature).
- **Details** renders from live CRM metadata (editable scalars, humanized
  labels) in curated, packed, full-width group panels. Curated lists control
  what appears: `DETAILS_LAYOUTS`, `DETAILS_REMOVED_FIELDS`, and
  `_ENTITY_LINK_FIELDS` (belongsTo links render **only** if curated there — the
  metadata sweep covers scalars only). Permission-aware down to per-record
  ownership. The PUT is entity-allowlisted (`cfg.details_entities` + Contact,
  else 404).
- **Re-assigning a record's manager happens on the Details tab**, through those
  curated link pickers — `CPartnerProfile.partnerManager` on the Partnership
  panel and `CSponsorProfile.cBMSponsorManager` on the Funding panel (v0.197.x).
  Each is the belongsTo behind the `manager_owned_link` reverse
  (`managedPartners` / `managedSponsors`), so it decides **whose** record this
  is — which is why it went unnoticed for so long that the grid displayed it and
  nothing could change it. Options are the mentor profiles the signed-in user
  can read; a forbidden list degrades the picker to read-only rather than
  breaking the tab, and a stored manager outside the list stays selected so a
  save can never silently drop them. **Mentor has no equivalent** — an
  engagement's mentor is re-assigned in Client Administration, deliberately
  (`DETAILS_LAYOUTS` keeps `mentorProfileName` read-only there).
- **The record's COMPANY is set on the Details tab too** (v0.198.0), the same
  way: `partnerCompany` / `sponsorCompany` as curated link pickers leading the
  Partnership and Funding panels, gated per domain by
  `DomainConfig.company_link_editable` (mentor has none — an engagement's
  company resolves through the client profile via `company_fallback`). These
  pickers also **create** the company, because a partner/funder the CRM holds no
  Account for cannot be repaired by picking: "+ New company" find-or-creates it
  (`details.create_company` → `service._find_or_create_company`, so a same-named
  company is reused and `cCompanyType` merged in), and the panel's **Save**
  writes the link — creating and linking stay separate so there is exactly one
  write path to the link. `POST /records/{id}/company` is **not** gated by
  `RECORD_QUICK_ADD`: it repairs records that already exist.
- **A company can carry MANY partner profiles.**
  `Account.cCompanyPartnerProfile` was `hasOne` until 2026-08-14, so linking a
  company to a second partner profile silently *moved* it off the first — that
  is how a live partner record lost its company to a duplicate entered nine
  hours later. Doug's ruling: a partnership is with a programme inside an
  organisation as often as with the organisation itself, so one company, many
  partner records. Recreated as many-to-one on prod 2026-08-14 and crm-test
  2026-08-15, verified in both; no application code was involved.
  **Funders followed on 2026-08-16** — `sponsorCompany` ↔
  `Account.cSponsorProfiles`, both environments, all links intact, proven by a
  two-funders-one-company test on crm-test.
- **Clients are the exception, and it is deliberate.** Doug's ruling
  (2026-08-16): **a client never has two client business profiles**, so
  `CClientProfile.linkedCompany` staying `hasOne` is *correct* — do not "fix" it
  to match partners and funders. The guard that makes the model safe lives in
  the app: `forms/client_intake/orchestrator._find_or_create_client_profile`
  find-or-creates the profile **matched on `linkedCompanyId`**, because an
  unconditional create silently moved the Account and contact off the existing
  hub (twice in production, 2026-07-17 and 2026-07-27). Verified clean
  2026-08-16: all 73 prod client profiles have a company and none share one.
- **Partner and Funder can be CREATED here** (`RECORD_QUICK_ADD`, off by
  default): the grid's "+ Add partner" / "+ Add funder" runs the same
  Account → Contact → profile sequence the public intake forms do, as the
  signed-in user. `DomainConfig.create_spec` gates both the button and the
  routes (mentor has none — engagements arrive through intake), and the spec is
  BOTH the form layout and the write whitelist. Same dedupe policy as intake:
  a same-named company / same-email contact is reused and null-filled, never
  duplicated; a reused company gains the type value merge-only.
- **Contacts tables are per-domain**: mentor shows Role chips and an Agreements
  badge; partner/funder show neither (every contact has the same relationship to
  CBM, and the consent bools are a client-intake concept) but offer **Make
  primary**.
- **First completed session activates the engagement** — a session saved
  Completed on an `Assigned`/`Assignment Dormant` engagement moves it to
  `Active`. The status guard *is* the "first session" rule. Best-effort.
- **Closing a session with a future "Next session" date books the follow-up**
  automatically (Scheduled, 1h, contacts invited). The grid's Next Session
  column derives **only from real sessions** — the stored
  `CEngagement.nextSessionDateTime` is deliberately discarded because staff can
  hand-edit it in the CRM and a stale value showed as a ghost session.
- **`touch_last_contact`** advances `CEngagement.lastContactDate` /
  `lastContacted` (advance-only, never backward or future) on a recorded session
  and an outbound email from the record.
- **Editor**: `SESSION_FIELDS` is layout + whitelist. `duration` is EspoCRM's
  *virtual* type — the frontend translates the Duration select into a recomputed
  `dateEnd`. The time picker **shades slots that conflict** with the user's own
  Google calendar (advisory only — a shaded slot stays selectable).
- **Co-mentor visibility** requires two things, both in the app: reading the
  `engagements` reverse link *and* stamping the co-mentor's User into the
  engagement's `assignedUsers` (Mentor Role reads CEngagement at "own", which
  with `assignedUser` disabled means `assignedUsers` membership). `add_comentor`
  also stamps the client records and backfills existing sessions;
  `remove_comentor` un-stamps symmetrically unless the user is shared.
- **New sessions are owner-stamped** so a read-own role can see its own create —
  without this the create itself 403s, because EspoCRM ACL-checks the read-back.

Watch for these when touching this package:

- **`sessionAttendees` and `additionalMentors` are RELATIONSHIPS, not fields** —
  read via `list_related`, write via relate/unrelate. Reading `<field>Ids` always
  returns empty and setting it on an update is silently ignored
  ([[espo-custom-linkmultiple-is-a-relationship]]). `unrelate` sends the id in
  the DELETE **body**; the path-suffix form 404s.
- **Relate/unrelate checks BOTH sides** — adding a co-mentor needs edit on the
  *other* mentor's profile. `_link_or_escalate` runs as the user first and only
  escalates a `noAccessToForeignRecord` denial to the admin account
  ([[espo-link-checks-both-sides]]).
- **Enum drift is handled in two layers**: the frontend sends only changed
  fields, and `_sanitize_enum_payload` drops values outside the live options
  before the CRM call (fails open).
- Required fields come from CRM metadata, not hard-coding.
- The `CSession` **name formula must be keep-if-present**
  (`ifThen(name == null || name == '', …)`) or it clobbers the supplied title.
- **One record, one tab** — records open in a stable per-record window and a
  `BroadcastChannel` elects one owner tab ([[single-tab-record-guard]]).

### Submission Admin — `/ops`

Marketing Admin Team. A multi-admin review-and-respond workspace over the
durable store. Staff reference: `submission-admin.md`.

- **Two status axes, deliberately separate**: **Intake status** (what happened
  to this arrival — Received / Completed / Held-Spam / Held-Email / Error /
  Discarded, the CRM receipt vocabulary) and **Response status** (where the
  reply conversation stands — New → In progress → Reply owed / Waiting on them →
  Responded → Closed). Machine words like `pending`/`needs_attention` never
  render. Count chips are one-click filters; filtering is client-side.
- **No owner — coordination by visibility**: an attributed comment stream, an
  automatic activity feed, and presence ("viewed 4 min ago").
- **Close requires a reason**; discard requires one too (422 without) and stamps
  who/when/why on the CRM receipt. A submitter replying on an anchored thread
  after close **auto-reopens** it.
- **Record-creating submissions auto-close** on successful delivery ("Process
  completed") — they are owned by the downstream admin team from that point, so
  the open queue is only info-request and info-email items needing a reply.
- **Email is thread-anchored**, not an address search: every send records its
  Gmail thread on the submission, and the conversation view reads only anchored
  threads. Sends go as **`OPS_MAILBOX`** (info@, display name "CBM Info") so
  every admin sees the same conversation.
- **Inbound info@ capture**: the worker polls the shared inbox and captures each
  new thread as a **held `info-email` submission** for triage. Approve = redrive
  (creates CRM records via the info-request orchestrator); Discard = spam with
  zero CRM residue. Layered stateless dedup means replies to anchored threads
  never double-capture. **Only ONE poller may run** — setting `OPS_MAILBOX` on
  both environments double-captures.
- **Other correspondence** surfaces inbound info@ threads not tied to a
  submission (replies to notices staff sent), read and replied to in-app,
  nothing stored.
- `?submission=<id>` deep-links a row even when filtered out; alert emails use
  it via `APP_BASE_URL`.

### Workspace Directories — `/directory`

Browsable grids over Companies, Contacts, Mentors and Partners, gated by
`WORKSPACE_ALLOWED_TEAMS`. **Grid columns and the detail pop-up arrangement are
read LIVE from the CRM's own layouts** (`{entity}/layout/list` and
`/layout/detail`) so they match the CRM and auto-sync — nothing hardcoded
([[espo-layout-api-readable]]). Toolbar is Filter · Search · View/Edit.

- **Contacts get a full record page** (`/directory/contacts/record/{id}`) with
  Overview + Communications, the latter scoped to **only the signed-in user's own
  conversations** (filtered server-side).
- **Mentors get a rich read-only profile page**
  (`/directory/mentors/record/{id}`) — a warm internal "get to know your
  colleague" view, deliberately not the CRM pop-up and not the public website
  look: hero, professional lane, "Get to know them" (interests, birthday
  month+day, spouse, city), mentoring availability with a slot bar, and
  reach-out links. Editing lives in My Mentor Profile. Guide:
  `mentor-directory.md`.
- Availability is computed under the **org-wide API key** (a peer mentor can't
  read another's engagements as themselves; it's a non-sensitive aggregate).
- Composite `address` fields must be composed from sub-fields — reading them as
  one attribute returns empty.

### My Email — `/myemail`

One inbox across every record the manager handles — scope is the
`CMentorProfile` reverse links (owned + co-mentored, all three domains),
deliberately NOT ACL-wide. Rows carry record chips, unread state, and
awaiting-reply / delivery-failed chips. The thread modal's reply path is "Open
in record — reply there"; full compose lives on the record page.

### Analytics — `/analytics`

A **metric library → panels → pages** engine, gated by `ANALYTICS_ENABLED`.
Live on both environments. User guide: `analytics-guide.md`; activation runbook:
`ANALYTICS-SETUP.md`; design record: `prds/analytics-app-plan.md`.

- Four result shapes — `scalar` / `series` / `breakdown` / `rows` — each tied to
  one panel renderer. Charts are **hand-rolled SVG/HTML** in
  `frontend/shared/charts.js` (Doug's decision: no charting library).
- **Hybrid caching**: cheap counts run live off the EspoCRM list `total`
  envelope; sweeps are cached in `analytics_cache`. A metric error degrades to
  an "unavailable" panel, never a 500.
- System metrics compute under the **org-wide API key** (the team gate and
  per-panel visibility are the boundary). **Record-scoped metrics always run
  live as the user, never cached** — a shared per-record cache would leak scope.
- **Authoring is self-serve** — admins build metrics (entity + filters +
  aggregation, with live preview) and compose pages in-app, no deploy.
- **Built-ins are defaults**: a DB page or metric with the same key overrides
  the built-in, and deleting a built-in writes a `source='suppressed'` marker.
  The three operational metrics read the app's own data and so aren't
  builder-editable.
- **A dashboard's `scope` IS its location**, one dashboard per record type,
  enforced at save. Starter dashboards exist for Mentor / Engagement / Partner /
  Funder / Contact. Company and Client have no host screen yet (OPEN-ITEMS #0).

### System Settings — `/setup`

**EspoCRM admins only** (not a team gate — this page can reconfigure the
platform). Changes this deployment's runtime settings from the browser instead
of an overlay edit plus `doctl`, which is what makes the flag-based promotion
gate practical. Gated by `SETUP_ENABLED` + a database. **Live on both
environments** — prod since 2026-08-12; before that the flag was only ever in
the crm-test overlay, so every prod flag change needed `doctl`. Runbook:
`SYSTEM-SETTINGS-SETUP.md`; rulings: `prds/system-settings-plan.md`.

- **Env is the default, the DB row is the override, and both are shown when they
  disagree** — `app_setting` holds only overridden keys and
  `core/settings_store.py` merges them over the env baseline behind the same
  `get_settings()` every package already calls. An empty table is exactly the
  old behaviour.
- **Degrade to the overlay, never to the code default.** If the override lookup
  fails (no DB, Postgres down, a bad value) the accessor returns the env value
  and logs. A database incident must not silently reconfigure the app — which is
  also why the overlays keep their flags permanently.
- **A server-side denylist** (`core/settings_registry.py`) refuses every secret,
  `ESPO_BASE_URL`/`ESPO_DRY_RUN`, `DATABASE_URL`, `SESSION_SECRET` and the two
  switches guarding this feature. Secrets are never rendered — "set / not set"
  only. `SETTINGS_OVERRIDES=false` is the env-only break-glass.
- **Boot-read flags are denylisted, not badged** (`BOOT_READ_KEYS`).
  `create_app` mounts routers and builds middleware from the ENVIRONMENT and the
  override layer loads afterwards, so an override for `analytics_enabled`,
  `events_enabled`, `intake_rate_limit`, `log_level` … never applies — not even
  after a redeploy, which re-runs mounting first. v0.190.1 offered them with a
  "takes effect on next deploy" badge and toggling `events_enabled` produced a
  portal tile whose routes did not exist. **The denylist is filtered on READ as
  well as write**, so a row that outlives its rule goes inert with no cleanup.
- **Web and worker refresh independently** (`SETUP_REFRESH_SECONDS`, default 45).
  `/healthz` reports `settingsVersion` per component so you can see the worker
  catch up.
- **Overrides never auto-revert**; a change can be marked temporary with a review
  date, and overdue ones are flagged on the page and logged hourly by the worker.
- **Scoped rollout is web-only** — a per-team/per-user scope needs a signed-in
  user to evaluate, so worker-side settings refuse it. A scoped override is
  deliberately excluded from the process-wide config.
- Also on the page: a **feature-readiness** panel (flag · required secrets · CRM
  fields detected · which component · worker heartbeat), an **environment diff**
  against the peer deployment (token-authorised snapshot, no secret values ever
  crossing the wire), and an **operations** tab whose mutating jobs are
  **dry-run → apply that exact plan**, refusing if the plan moved.

### Events & Webinars — `/events`

Replaces the data layer behind `clevelandbusinessmentors.org/webinars/`, which
today runs on a Google Apps Script plus a browser-side YouTube API call with
**EspoCRM involved at no point** — so every registrant is an invisible lead.
Staff guide: `event-administration.md`; activation + test script:
`EVENTS-SETUP.md`; schema: `cevent-entities-crm-handoff.md`.

**Live on crm-test, off on prod, and the website still runs on the Apps Script.**
`EVENTS_ENABLED` + `EVENTS_PUBLIC_API` are on for crm-test only; `ZOOM_EVENTS`,
`EVENTS_REMINDERS` and the attendance pull are off everywhere. Phases 1, 2, 3, 5
and **6** are built; **Phase 4 (WordPress plugin + cutover) is the only one left**
— and it is the one that actually stops the lead leak.

- **Phase 6a attendance** (`events/attendance.py`, worker): pulls each finished
  online event's Zoom participant report and matches by email. An empty report
  means "not published yet", never "nobody came"; a `Manual`/`Check-in` source
  is never overwritten; an attendee matching no registration is recorded flagged
  rather than dropped. **Never run against real Zoom.**
- **Phase 6b follow-ups** (`events/notify.py`): five sends as the shared info@
  identity, from EspoCRM templates. Once per registrant/event/kind, ledgered on
  `followUpsSent` **after** a successful send and enum-checked first. Preview is
  the default. **Needs five templates** — `EventReminder`,
  `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA`, `EventSurvey` —
  and has no frontend yet.
- **Phase 6c reporting** (`events/reporting.py`): the engagement **Events tab**
  (attendance rolled up across all of a client's contacts, deduplicated by
  event), the contact **Events tab** in the directory, and programme + conversion
  reports in `/events`. Conversion counts an attendee only when their engagement
  postdates their first attended event.
- **Phase 6d** `scripts/import_youtube_events.py` — playlist backfill, dry-run by
  default, importing **unpublished** because an upload date is not an event date.
  Never run against the real playlist.

- **⚠️ `CEvent` doubles as CBM's org calendar** — most rows are internal team
  meetings and mentoring-session mirrors. That is true **on crm-test (94 rows)**;
  **prod's `CEvent` is empty** because it was never connected to Google
  (verified 2026-08-08), so the first published event there will be a real one.
  Workshops share the entity, gated by
  **`publishToWebsite`** (default false). **That flag is the entire boundary to
  the public site** — every public read goes through
  `events/service._public_where`, and an unpublished event's page 404s rather
  than merely hiding. Never hand-roll a public CEvent query
  ([[events-publish-gate]]).
- **Zoom here is the explicit exception** to the mentor-sessions "user-supplied
  links only" ruling: the public webinar programme uses the CBM Zoom account via
  Server-to-Server OAuth (host `zweb@cbmentors.org`). Ask which world you're in
  before applying either ruling ([[zoom-user-supplied-only]]).
- **Vocabulary trap**: in the public payload `topic` means the event **TITLE**
  (Zoom/Apps-Script vocabulary); the category rides as `category`. Aligning the
  names would blank every title on the live site.
- The renderer needs a **same-origin thumbnail proxy** — hotlinked
  `i.ytimg.com` thumbnails return 503 on the live page, which is why the current
  page already ships one.
- **`wp-plugin/cbm-events/` holds the two files the website will run**: the
  renderer (`cbm-events.js`) and the site's **own stylesheet**
  (`cbm-events.css`, copied verbatim from the live page's Elementor widgets —
  keep it in sync, do not restyle it). Cutover replaces those widgets, so the
  plugin must carry the CSS with the markup. `/events/preview.html` loads both
  from the shipping location, which is what makes it a real check; **nothing in
  `events/frontend/preview.css` may style a contract class** — an approximation
  there hid a live class-name drift for three weeks. A guard test asserts every
  class the renderer emits has a rule in the stylesheet.
- **A per-event link must come from `CBMEvents.config.eventUrlBase`**, never the
  payload's `url` — that is always the live site's `/webinars/<slug>`, so
  anywhere else it 404s. **Sign-up stays a modal on the calendar** (Doug,
  2026-08-16); the event page is for reading, not the registration door.

## Cross-cutting subsystems

### Email

Umbrella reference: **`email-management.md`**. Deep dives:
`communications-tab.md`, `submission-email-flow.md`.

- **Sync** (`comms/`, worker, `GMAIL_SYNC`): per-mailbox Gmail clients under the
  service-account + domain-wide-delegation stack, historyId cursors with
  expired-cursor and new-address backfills, RFC Message-ID dedup across
  co-mentor mailboxes, and upsert into `CConversation`/`CCommunication` with
  parent/contact links. A failed message ingest **holds the cursor** (the replay
  is cheap thanks to dedup) and dead-letters after 5 consecutive failing passes.
- **`core/email_clean.py`** produces two zones: quoted reply demoted into
  `blockquote.quoted-reply`, signatures and boilerplate deleted. **Outbound
  messages are cleaned with `outbound=True`** — the inbound signature-stripping
  heuristics used to delete everything after an early "Thanks," in a message our
  own user wrote.
- **Two sending identities, deliberately**: mentor↔client mail sends as the
  manager's own `@cbmentors.org`; staff-tool outbound (Submission Admin,
  quick-compose) sends as the shared **info@ / "Cleveland Business Mentors"**
  identity. Alerts keep their own address.
- **Internal CBM↔CBM mail links to the members' Contacts, never to records** —
  it was polluting engagement Communications tabs.
- **Compose** is one shared surface: templates, signature, attachments (local +
  from the record's Documents + forwarded originals), drafts, Cc/Bcc,
  reply/reply-all/forward, and an Email-record write-back with a retry screen.
  Every address shown anywhere in the staff UIs is a **compose link, never a
  bare `mailto:`** — record pages use the record-scoped compose, everywhere else
  uses the shared `quickmail.js` widget.
- **Templates**: EspoCRM renders (`POST EmailTemplate/{id}/prepare`), the app
  sends. Unresolved placeholders stay literal and the UI warns. The domain
  filter rides the **native template category** — `EmailTemplate` is
  `customizable:false`, so a custom field is impossible
  ([[espo-system-entities-not-customizable]]). `{CMentorProfile.*}` resolves
  because the parse passes the record's manager profile as `relatedType/Id`.
- **Signatures** come from the user's EspoCRM `Preferences.signature` and are
  re-appended below a rendered template — so templates must not carry sign-offs.
- **Inbound attachments auto-file** to the record's Documents tab (real
  attachments only, never inline images), with per-record SHA-256 dedup and a
  `comm_attachment` retry ledger. **View original** renders the sanitized
  original in a sandboxed iframe. Bounces are classified and rendered as a red
  "Delivery failed" card rather than masquerading as a reply.
- All four thread windows render through the shared
  **`frontend/shared/conversation.js`** ([[shared-conversation-renderer]]).
- **The impersonation subject must be a real licensed mailbox** — a group or
  alias 403s `unauthorized_client`
  ([[gmail-delegation-needs-licensed-mailbox]]).

### Documents — Google Drive

`docs/` package, gated by `GDRIVE_DOCS`. Setup runbook: `GDRIVE-DOCS-SETUP.md`;
PRD in `prompts/Google Drive Documents/`.

- Folder scheme under the shared drive: `{Entity Label}/{Record Name} (id)/`,
  with engagement folders **nested under their client**. Labels are configurable
  (`GDRIVE_ENTITY_LABELS`: Contact=Mentors, CEngagement=Clients, …).
- **Access model (Doug's ruling, PRD v1.5)**: no person is a member of the
  shared drive except the two designated system administrators; the **service
  account is the operational member** and all Drive ops run as it
  (`GDRIVE_IDENTITY=service`). Drive-side access is per-person folder-level
  **Commenter** grants mirroring CRM entitlements, revoked by the same app
  actions that end the entitlement, plus a **nightly reconciliation** that
  re-derives grants from the CRM. `Mentors/` personnel folders get **no**
  grants. Commenter means uploads can never bypass the app's index.
- **A grant needs a real Google account.** The person's address is their
  `CMentorProfile.cbmEmail`, and mentor provisioning back-fills that
  (`firstname.lastname@cbmentors.org`) **without creating a Workspace mailbox**
  — so the address often doesn't exist, which is the norm on crm-test. Drive
  400s a silent share to an unknown address, so `create_permission` raises
  `DriveNoAccountError` and the reconciliation counts it as `unfulfillable`,
  **not** an error: logged and counted, never alerted, retried every pass so it
  self-heals the day the mailbox appears. In-app document access is unaffected
  either way (the app reads Drive as the service account); only opening the
  folder directly in Drive needs the grant.
- **A drive member needs no grant.** The two designated administrators ARE
  shared-drive members, so Drive reports their access on every folder as
  *inherited* (`permissionDetails[].inherited`, `permissionType: member`) and
  merges any file-level grant into that one permission. The engine treats
  at-least-Commenter inherited access as satisfying the entitlement —
  `driveMembers` in the result, never a create and never a delete. Before
  v0.201.2 it skipped inherited permissions outright, so it re-created the same
  grant every night forever without converging.
- **Rollback rule**: a row-write failure deletes the Drive file; a Drive failure
  never writes a row. Uploads pre-assign ids via `files.generateIds` so a retry
  can't duplicate.
- **Archive** moves the file to `_Archived` **first**, then flips metadata, with
  a move-back rollback on a mid-failure.
- Viewing streams through an ACL-gated proxy; **the browser is the cache**
  (immutable responses on modifiedTime-versioned URLs). Office formats
  convert-on-view; `?original=true` streams exact bytes for download.
- `documentsFolderUrl` write-back is feature-detected and inert until the CRM
  field exists.

### Calendar, meetings and transcripts

- **Google Calendar** (`GCAL_EVENTS`, web component; live on both envs): saving
  a **Scheduled** session reconciles an event on the manager's own calendar.
  Scheduled + no event → create (with a Meet conference only when
  `videoMeetingLink` is blank); a change → patch; Cancelled → cancel;
  Completed/No Show → skipped. **Past-dated starts never create a NEW event**
  (>5 min in the past), though an existing event still patches. Best-effort
  throughout — the save response carries `calendar:{ok,…}`.
- **CBM members are invited at their `cbmEmail` ONLY** — never their Contact's
  personal address. This eliminated a duplicate-event bug where a mentor was
  invited to their own meeting ([[cbm-members-cbm-email-only]]).
- **Mentor-supplied Zoom**: a profile preference uses the mentor's Zoom Personal
  Meeting room instead of a generated Meet. Session meetings never use a CBM
  Zoom account ([[zoom-user-supplied-only]]).
- **Transcripts** ride an **ordered source list** in `sessions/transcripts.py` —
  Fathom first, Meet-native fallback. Fathom correlates on normalized
  `meeting_url` within a ±36h window, preferring invitee overlap for reused
  personal rooms. Action items route to `nextSteps` when empty, else into
  `sessionAiSummary`; human content is never overwritten. Fathom API contract
  quirks: [[fathom-api-contract]].

### Assignment stamps and CRM access

A recurring failure class: a mentor 403s on a contact or session write because
the record lacks their `assignedUsers` stamp. Four layers handle it, all
**merge-only** with CRM links as the source of truth
([[assignedusers-stamp-drift]]):

1. `scripts/audit_assignment_stamps.py` — read-only report, `--heal` to fix.
2. The **Repair assignment** action in Client Administration.
3. A **nightly reconciliation** in the worker.
4. **Heal-on-access** in `/mentorprofile` for the mentor's own Contact.

Provisioning now stamps the Contact at source, which closed the largest inflow.

### Action history

Every mutating staff action is recorded via **`core/action_log.py`** — see
Conventions. Plan: `prds/action-history-plan.md`;
[[action-log-history-build]].

## Gotchas / things learned

**EspoCRM behaviour**

- **Field-level ACL silently strips writes** — a 200 OK where one field didn't
  store. Newer fields saving while older ones don't is the tell. Diagnose by
  reading each role's `fieldData` as admin
  ([[espo-field-acl-silently-strips-writes]]).
- **A 403 names the exact denied entity and operation** — read it precisely.
  Effective ACL is the union of **team-attached** roles; verify via Users →
  Access ([[espo-403-diagnosis-merged-team-roles]]). Admin accounts bypass ACL
  entirely, which is how several mentor-only bugs stayed invisible.
- **Custom linkMultiple fields are relationships** — see the Session Management
  notes ([[espo-custom-linkmultiple-is-a-relationship]]).
- **The Create Link dialog INVERTS the two Name boxes.** Read this before
  writing a single line of relationship build steps — it has now been got wrong
  four times (CConversation, CEvent, CPartnerProfile ×2). The dialog has two
  panels: **LHS** = the entity you opened it from (fixed, shown in the header),
  **RHS** = the Foreign Entity you pick. Each panel has its own **Name** and
  **Label** — the phrases "Link Name" and "Foreign Link Name" are NOT on the
  form, so never use them. A panel's Name defines the link that *points at that
  panel's entity*, which means it is **stored on the other side**:
  **LHS Name → the link created on the RHS entity. RHS Name → the link created
  on the LHS entity.** Work the two link names out first, then write each one
  under the panel of the entity it POINTS AT. EspoCRM also blindly prepends `c`
  to a name landing on a non-custom entity (Account, Contact, …), so type those
  UNPREFIXED — `companyPartnerProfile` is stored as `cCompanyPartnerProfile`,
  while typing `cCompanyPartnerProfile` yields `cCCompanyPartnerProfile`.
  **Always verify before moving on**: read `entityDefs.<Entity>.links` from
  `GET /Metadata` and confirm each link is on the side you intended
  ([[crm-specs-use-entity-manager-terms]]).
- **A list `maxSize` above `recordListMaxSizeLimit` (200) is a 403, not a
  truncation** — and in this app a 403 on a best-effort read is *swallowed*, so
  the symptom is an empty list, not an error. v0.198.0 raised the Details
  link-picker options to 500 and emptied **every** picker in production
  (v0.202.2 pages at 200). Page at 200 or below unless the CRM setting is raised
  on BOTH environments; no other call site in the repo exceeds it. Note that
  neither the unit tests (fakes) nor the preview harness (canned JSON) issue a
  real list request, so **a page-size change has to be tried against a live CRM**
  ([[espo-list-maxsize-limit]]).
- **Removing a relationship is metadata-only — the column and its data stay.**
  Entity Manager cannot change a relationship's *type*, so a type change is
  delete-then-recreate; that is safe, because `LinkManager::delete()` only
  strips metadata. Verified on crm-test 2026-08-14: deleting
  `CPartnerProfile.partnerCompany` left all 14 values in `partner_company_id`
  through a rebuild, and a recreate under the SAME name re-adopts them with no
  restore step. A **mis-named** recreate is the trap — it strands the data in
  the old column and leaves an empty new one behind, which reads exactly like
  data loss ([[espo-removelink-is-metadata-only]]).
- **Foreign fields are read-only mirrors** of a linked record's field — "shows
  but can't be edited" is usually this, not a bug
  ([[espo-foreign-fields-are-readonly-mirrors]]).
- **Switching an entity to Multiple Assigned Users disables the single
  `assignedUser`**: reads return null (hiding previously-stored values) and
  writes are silently ignored. All five assigned entities are now collaborators;
  the service dual-writes ([[crm-test-assignment-acl-fields]]).
- **A list `maxSize` over 200 is a 403, not a truncation** — EspoCRM's
  `recordListMaxSizeLimit` (default 200) makes an oversized page fail outright:
  *"Max size should not exceed 200. Use offset and limit."* Page with `offset`
  instead of asking for one big page. This is nastiest inside a **best-effort
  `except EspoError`**, where the 403 reads as "no records" — a hard-coded 500
  left every curated link picker showing only "(none)", for every user including
  admins, and looked like a permissions problem ([[espo-list-maxsize-403]]).
- **Soft deletes**: an admin's GET still returns a deleted row with
  `deleted: true` (ordinary users get 404). A cleanup script must treat that as
  gone or it re-plans the delete forever.
- **Currency fields validate against their `*Currency` companion** — any save
  setting an amount must backfill the currency or the CRM 400s.
- **Inline images** in wysiwyg fields: the filename must carry the content
  type's extension or EspoCRM 403s "Not allowed file type"; store
  `src="?entryPoint=attachment&amp;id=X"` so the Wysiwyg Saver binds it
  ([[espo-inline-attachment-contract]]).
- **System entities may not be customizable** — check `scopes.{Entity}
  .customizable` before speccing a field build
  ([[espo-system-entities-not-customizable]]).
- **App writes are indistinguishable from hand edits** by the same user in Espo
  history, and `mentorProfile` changes aren't audited — hence the stream notes
  ([[espo-history-app-writes-indistinguishable]]).
- **The CRM team changes crm-test under the live app** — check field/enum drift
  first when something that worked stops ([[crm-test-schema-drift]]). The two
  CRMs also drift from each other; role scopes especially.
- **Settled negative finding — do not re-open**: engagements stuck at `Assigned`
  despite a Completed session are NOT a field-ACL strip. Prod's Mentor Role has
  no field lock on `CEngagement` and 15 of 16 live cases are correctly Active;
  the one exception was collateral from the duplicate-save bug and self-heals on
  the next Completed save ([[engagement-activation-not-systemic]]).

**This application**

- **Enum drift is tolerated on creates.** `core/enum_filter.EnumSanitizer`
  validates user-supplied enum values against live CRM options and **drops**
  unrecognized ones rather than letting one value 400 the whole create. It never
  touches system discriminators. Fails open. This is why re-driving a
  drift-failed submission succeeds.
- **Implausible phone numbers are dropped, not fatal** — `e164_or_none` returns
  None for <10 or >15 digits, and the Contact create omits the field rather than
  losing the lead. `create_dropping_invalid` handles a CRM-side `valid`/`pattern`
  rejection the same way. The raw value survives in the audit log.
- **Non-required fields must never block a save** over enum drift — schemas use
  free strings, the sanitizer is the gate, and validation errors return readable
  messages ([[non-required-enums-never-block]]).
- **`.dockerignore` must exclude `.venv`** — `COPY . .` otherwise overwrites the
  container's virtualenv with the host's (`sh: .venv/bin/uvicorn: not found`).
- **`app.js` in the session tools is one shared IIFE** — a later duplicate
  function declaration silently wins. Grep the name before adding a helper
  ([[sessions-appjs-single-scope-collisions]]).
- **Never cap page width.** Density comes from packing more into the full width;
  users are on 4K monitors. This outranks spec documents — flag a width cap in a
  spec before implementing it ([[no-page-width-caps-density-by-packing]]).
- **`display:flex` beats the `[hidden]` attribute** — a hidden overlay can still
  cover the page. Verify with a real mouse click and computed styles, not an
  attribute check ([[harness-js-clicks-bypass-overlays]]).
- Browser-harness quirks: `rAF` is throttled in the MCP tab and awaiting an rAF
  loop freezes the renderer ([[harness-raf-throttled-in-mcp-tab]]); a fetch stub
  must reject on `AbortSignal` or timeouts never fire; load stubs *before*
  `busy.js` or the instrumentation is bypassed. Harness recipe:
  [[sessions-frontend-stub-harness]].
- Parallel sessions share one git index — stage and commit atomically, then
  audit with `git show --stat` ([[parallel-sessions-share-one-git-index]]).
- Canonical SCORE field inventory lives here (`score-*-form*.md`,
  `score-mentor-request-form.yaml`); copies under the `crmbuilder` repo are not
  canonical.

## Documentation

**Start here for status:** `CHANGELOG.md` (per-version detail — the value
`/healthz` reports is the deploy marker) and `OPEN-ITEMS.md` (everything
unresolved: CRM prerequisites, live verification owed, cleanups, decisions).

| Doc | What it covers |
|---|---|
| `README.md` | Repo overview; how to run locally / add a form |
| `DEPLOYMENT.md` | Engineer deploy runbook, env vars, reliability ops, backups |
| `STAFF-DEPLOYMENT-GUIDE.md` | Console-only companion for CBM staff |
| `SYSTEM-ADMIN-TROUBLESHOOTING.md` | **Verify + troubleshoot the whole platform without an engineer** — health check, weekly sweep, symptom index, the safe-remediation toolkit and its off-limits list. Audience: EspoCRM Admin + DO console, no CLI |
| `SYSTEM-SETTINGS-SETUP.md` | `/setup` activation + use: the override model, the denylist, temporary and scoped changes, the environment diff, the ops jobs, break-glass |
| `intake-processing-overview.md` | Plain-language capture → worker → CRM pipeline, per-form records, where each intake kind gets worked |
| `mentor-administration.md` | `/mentoradmin` functionality + the completeness rules |
| `mentor-directory.md` | Mentors directory + the read-only mentor profile page |
| `address-paste.md` | Staff guide to pasting a whole address into one box |
| `birthday-greetings.md` | The portal birthday celebration, rules, and how to test it without touching data |
| `email-management.md` | **Umbrella** email reference; links to the deep-dives |
| `communications-tab.md` | The session tools' Communications tab |
| `submission-email-flow.md` | Inbound info@ → queue and outbound respond-to-a-form lifecycles |
| `submission-admin.md` | `/ops` work queue, resolution workflow, conversations |
| `analytics-guide.md` / `ANALYTICS-SETUP.md` | Analytics user guide / activation runbook |
| `event-administration.md` / `EVENTS-SETUP.md` | Events staff guide / activation + 20-min test script |
| `GDRIVE-DOCS-SETUP.md`, `GCAL-GOOGLE-SETUP.md`, `GMAIL-INTEGRATION-GUIDE.md` | Google integration activation runbooks |
| `prds/CBM_Client_Intake_Requirements_Specification.md` | What the client-intake process must do (the formal spec) |
| `prds/CBM_Client_Intake_Technical_Design.md` | How it is built — deployment §6, open issues §7, EspoCRM mapping §3 |
| `prds/v2/` | The V2 reliability platform specs (requirements, technical design, operations guide) |
| `email-executive-summary.md` | Published to the docs site as the Email Guide — **keep the two in sync** |

The formal PRDs cover the **client-intake** form and process only; every other
form, tool and platform arc is documented in this file plus its own guide.
`prds/` also holds **one plan document per feature arc** (analytics, events,
funder contributions, Gmail communications, email quality, the info@ mailbox
rollout, the intake-receipt redesign, Meet and Fathom transcripts, submission-admin
collaboration, workspace directories, transcription-vendor options) — each records
the decisions and Doug's rulings behind that arc, so read the relevant one before
reworking a feature. `prompts/` holds the kickoff prompts, design mockups and
review documents those arcs were built from (including
`reliability-review-2026-07-17.md` at the repo root, whose six hardening phases
are all implemented).

**CRM build handoffs** (one file per pending or completed CRM change, written in
Entity Manager vocabulary — [[crm-specs-use-entity-manager-terms]]):
`cintake-submission-*.md`, `cinformation-request-entity.md`,
`cconversation-entity.md`, `cevent-entities-crm-handoff.md`,
`csession-*.md`, `cmentorprofile-*.md`, `clastcontactdate-field.md`,
`documentsfolderurl-crm-field.md`, `emailtemplate-et-crm-prereqs.md`,
`crm-field-handoff.md`.

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- **Never commit `.env` or any secret.** Secrets are injected as App Platform
  encrypted env vars.
- **Commit messages follow Conventional Commits** (`feat:`, `fix:`, `docs:`, …).
- **Every app page loads `frontend/shared/busy.js`, FIRST.** The press-feedback
  spinner is self-wiring — one script tag — but it wraps `fetch` and
  `XMLHttpRequest`, so it must precede any script that can start a request. Any
  new page must include it. It is visual only and **never sets `disabled`**.
  Manual control: `var done = CBMBusy.start(btn); … done();`.
- **Action buttons are never disabled and never hidden** — validate on click and
  show a message naming the missing input or the missing permission. A missing
  button reads as a bug and generates support calls. Transient in-flight
  disables are fine ([[buttons-never-disabled-validate-on-click]]).
- **Every mutating staff action is recorded via `core/action_log.py`** — call
  `record_action(...)` (stream note as the user + a `CActionLog` row via the API
  key), or `log_action(...)` when the service already posts the note. Do it at
  the **router** layer, which has the actor, app identity and result.
  `actionType` is free text from the module's vocabulary constants. Both writes
  are best-effort and the `CActionLog` half is feature-gated.
- **Every date/time field uses the shared `CBMDateTime` control**
  (`frontend/shared/datetime.js` + `datetime.css`) — a Date input plus a
  half-hour slot grid with an "Other time" escape hatch. **Never a raw
  `datetime-local`.** The control owns the local↔UTC conversion, and that is the
  point: EspoCRM stores datetimes as UTC with no offset, a `datetime-local`
  hands you local wall time, and the Events editor sent one straight to the CRM
  — every event it created was four hours early. `create({value})` takes a CRM
  stamp, `read(el)` returns one; no caller does date arithmetic. Optional
  `busyFetch` shades slots that clash with the user's own calendar (advisory —
  the slot stays clickable). A guard test fails on any new quoted
  `"datetime-local"`.
- **All wysiwyg fields use the shared CBMRichText editor**
  (`frontend/shared/richtext.js`, wrapping vendored Jodit). Never hand-roll a
  contenteditable. Load `jodit.min.css` + `jodit.min.js` + `richtext.js` before
  the app's own JS. It sanitizes on load and on read, and `getValue()` is
  snapshot-stable for untouched editors so save-diffing keeps working.
- **Every postal-address form wires the shared paste-parser**
  (`frontend/shared/address-paste.js` + `.css`): paste a whole address into the
  first input and it splits across Street / line 2 / City / State / ZIP, with an
  inline Undo. Hosts pass the input **elements** (`attach`, or `attachByFields`
  for flat `data-field` forms) and nothing else. Local heuristic only — no
  network, no Places, no validation. Its writes dispatch **bubbling
  `input`/`change`** events because host dirty-tracking and the sessions
  "Same as billing" mirror listen for them. Add new address pages to
  `ADDRESS_PAGES` in `tests/test_shared_address.py`, which is what catches a
  form that forgot it. Plan: `prds/address-paste-parsing-plan.md`.
- **A new CRM-facing feature should feature-detect its field from metadata**
  rather than requiring a coordinated deploy — the established pattern is that
  the feature stays dark until the CRM field exists, then activates with no
  deploy.
- **Best-effort side effects never fail the user's save** — calendar, stream
  notes, grants, provisioning, receipts and stamping all report through the
  response payload instead of raising.

## Current status

*Rolling window — the last few releases only. Delete a block once it is
deployed and verified; `CHANGELOG.md` is the permanent record, `OPEN-ITEMS.md`
holds anything still owed.*

**Pushed through v0.202.2 on 2026-08-16**, so all three apps built it. Nothing
is unpushed. What is *verified* is narrower than what is deployed — see each
block.

- **v0.203.0 — the events website preview is the website now.** The site's own
  stylesheet (verbatim from its Elementor widgets) ships with the plugin and
  drives the preview, so the colours and type are the site's rather than an
  invented green approximation. Doing it exposed a defect the approximation had
  been hiding since 2026-07-25: the recorded-library markup was off the class
  contract and would have rendered unstyled on the live page. A webinar's title
  now opens its own page (it used to 404 off to the live site), sign-up is the
  site's modal, and both are guarded by tests. **Verified against stub data
  only** — `/events` is live on crm-test, so the real side-by-side is available
  today (`OPEN-ITEMS.md` 19e), along with the consent-wording decision (19d).
- **v0.202.1 / v0.202.2 — the curated link pickers actually work now.** Two
  separate defects, both found from one report ("no way to select or create a
  company"). (1) The Details **summary strip** dropped empty fields, including
  link pickers — so on the record with no company, nothing about Company
  appeared in view mode and there was no signpost to the picker behind **Edit**.
  An unset picker now renders "—", and Company leads the partner/funder strip.
  (2) The option list was fetched with `maxSize=500`, which EspoCRM **403s**
  rather than truncating (see the Gotchas entry) — swallowed by the best-effort
  handler, so **every** picker on every domain offered nothing but "(none)", for
  every user including admins. Options are now paged at 200. Owed: a live look
  now that they populate (`OPEN-ITEMS.md` #20).
- **v0.202.0 — the events Add/Edit screens.** A resizable workspace modal with
  pinned Save/Cancel, the two Content fields on the shared CBMRichText editor,
  grid-packed panels, and the page's local `.cbm-button` override dropped in
  favour of `/shared/tokens.css` (this page was the only one defining its own
  buttons). Verified in a stub harness only — but `/events` is **live on
  crm-test**, so the live pass can be done today; prod has the router unmounted
  (`/events/api/session` 404s there, 401s on crm-test).

*(The v0.198.0 company-link arc — the Company picker, the many-to-one CRM
change for partners and funders, the client one-to-one ruling — is deployed and
verified on both environments; its standing facts live in the Session
Management section above, its history in `CHANGELOG.md`, and the one thing still
owed is `OPEN-ITEMS.md` #19b: the picker's CREATE path has never run as a
non-admin.)*

- **v0.197.0 / v0.197.1** — the partner and funder **manager pickers** on the
  Details tab (see that app's section). The 2026-08-13 "verified live" pass was
  narrower than it read: v0.202.2 proved the option list had been empty for
  everyone since the pickers shipped, so what was verified was the picker
  rendering and holding its stored value, never *changing* one. Re-check both
  halves now that the options populate.
- **v0.196.1** — a Drive grant for a `cbmEmail` with no Google account is no
  longer counted as a reconciliation failure (it was alerting nightly, forever).
- **v0.196.0** — address paste-parsing across all six address surfaces (see the
  Conventions entry). **Deployed** on the 2026-08-13 push; **not yet verified
  live.** There is no flag — the module is inert unless a page loads it, so
  per-surface wiring was the rollout control and a **revert is the only
  rollback**. Owed: a live pass on the session tools' Details tab, the only
  surface with a State `<select>`, disabled shipping inputs and the billing
  mirror in play at once (`OPEN-ITEMS.md` #20).
- **v0.195.0** — quick add on Partner + Funder Management (see that app's
  section), **deployed to both environments** 2026-08-12. `RECORD_QUICK_ADD` is
  off by default, so the button is absent until toggled at `/setup` (now
  available on prod too). The UI is reviewed; what is still owed is the CRM
  half — proving a **non-admin** Partner/Sponsor Management Team role actually
  holds `CPartnerProfile`/`CSponsorProfile` create and `Contact` create
  (`OPEN-ITEMS.md` #20). An admin account passes those regardless, so an admin
  test proves nothing.
- **2026-08-12 config**: `SETUP_ENABLED` added to the prod overlay (System
  Settings is now live on prod). `APP_BASE_URL` rode along in the same apply —
  it had been sitting in the overlay unapplied — so prod alert emails and the
  daily digest now carry absolute record deep links.
*(v0.181.0–v0.187.0 blocks removed 2026-08-13 — all deployed and verified in
July; `CHANGELOG.md` holds them. The v0.187.0 analytics work still has two
surfaces outstanding, tracked as `OPEN-ITEMS.md` #0, not here.)*

**The open work is all in `OPEN-ITEMS.md`** — chiefly: CRM prerequisites still
to build (items 11–19, including the three Google-side changes that gate Meet
transcripts), the live-verification backlog (item 20 — the code is deployed, the
eyeball is owed), and a CRM test-record sweep (item 21).
