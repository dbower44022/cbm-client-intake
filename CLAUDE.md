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

- **"Door" is retired (ruling 41).** Where a record came from is its
  **Lead Source** (the three imports, the five public forms, event
  registration, the info mailbox). The intake forms, the webinar page and
  the postcard landing page are **public forms**. A record from an outside
  source is a **lead**. The staff screens that create records are not an
  outside source and create no lead (ruling 48). Doug's 10-18-26 rule still
  binds them: a rule meant for every place a record enters is written as
  "every public form and every staff screen that creates records"
  (wording approved by Doug 10-19-26).

- **Company type is `cCompanyType`, never `cAccountType`.** The Account entity
  is presented as **Company**; `cAccountType` is gone from both CRMs. Valid
  options are `Client / Sponsor / Partner / Other` — the sponsor value is
  `"Sponsor"`, NOT `"Donor/Sponsor"`, and **EspoCRM rejects an invalid multiEnum
  outright** (the create 400s, nothing written). See
  [[prod-account-caccounttype-missing]].
- **A company the CRM already knows GAINS the new role** (v0.236.0,
  Doug's ruling 2026-10-07): every public form and staff screen that
  find-or-creates a Company — the four public forms and the Partner/Funder
  quick-add — calls `core/crm_upsert.merge_company_type` on a match,
  appending its own
  `cCompanyType` value and never removing one. Best-effort: a refused merge
  is logged, never fatal. A funder's company applying as a partner used to
  stay typed `Sponsor` only. **The Contact's `cContactType` is deliberately
  NOT merged** — null-fill only, a person's type is curated data.
- **A company that exists at a DIFFERENT web address HOLDS the submission**
  (v0.238.0, Doug's ruling 2026-10-07): client intake, partner and sponsor
  raise `core/crm_upsert.CompanyConflict` on a matched company whose stored
  website disagrees with the submitted one (`website_key` comparison — the
  quick-add refuses with a message; a public form cannot, so it holds). The
  row goes to **`held_company`** before any record is written, and Submission
  Admin resolves it — *Same company* (website set aside) or *Different
  company* (a qualified name) — through **`delivery_overrides`**, merged
  over the captured payload at delivery; the payload itself is never
  rewritten. Plan: `prds/company-website-hold-plan.md`.
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
- **A partner's intake link credits them as the referring partner**
  (v0.255.0, Doug's requirement 2026-10-12, link form ruled **the CRM id**):
  `client-intake/?partner=<CPartnerProfile id>` rides a hidden field and the
  captured payload (`referring_partner_id`); delivery writes
  `CEngagement.referringPartnerId` after a validate-or-drop read (an unknown
  id drops the attribution, never the submission) and appends a notes line
  saying the LINK did it. The banner and the *Partner Referral* preset come
  from the public name-only lookup `GET /api/client-intake/partner/{id}`,
  which 404s on anything it cannot resolve. The link itself is on the
  partner's Details tab (`DomainConfig.intake_link_form`), derived from
  `APP_BASE_URL`, never stored.
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
  **Backups of an overlay are secrets too** — `.do/*.bak*` is ignored since one
  published production's `APP_ENCRYPTION_KEY` (2026-09-14, found 09-23,
  `OPEN-ITEMS.md` #33). Never `git add` anything under `.do/` but `app.yaml`.
- Each app runs a **web** component and a **`delivery-worker`** (`python -m
  worker`), plus a **PRE_DEPLOY `migrate` job** (`alembic upgrade head`).
  Alembic is the sole schema authority — there is no boot-time `create_all()`,
  so a fresh environment must migrate before first boot.
- `/healthz` reports version, environment, `dryRun`, `durableStore` and a
  worker-liveness block. It is the deploy marker. Since v0.214.0 it also
  answers the other two version questions the chapter network needs:
  **`releaseTag`** (which *promotion* this is — read from **`release-tag.txt`**,
  which `scripts/cut_release.sh` writes into the commit the tag names, since a
  container has no `.git`. Honoured **only when it matches this build's
  version**, so an untagged build and every commit after the cut report null
  rather than the last release that went by; `RELEASE_TAG` in the environment
  still overrides it, and no deployment should need to) and **`crmConfig`** (what configuration the CRM behind it
  holds, read from `CNetworkStandard`). The `crmConfig` probe is a cached
  background read — **`/healthz` still never pings the CRM** — ships dark
  (`CRM_CONFIG_REFRESH_SECONDS=0`), and reports `absent` / `forbidden` /
  `unreachable` as three distinct states, because collapsing them turns a
  lost API grant into "the CRM is missing an entity".
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

**⚠️ crm-test reverts to a fixed snapshot every night.** It doubles as the
training sandbox, and since 2026-08-22 a nightly reset runs in two halves — the
CRM at **04:00 UTC** (droplet cron) and the app's own Postgres an hour later
(the `delivery-worker`, `SANDBOX_NIGHTLY_RESET`). **Anything you create or edit
on crm-test during the day is gone by morning**, so a live verification left
half-finished overnight has to start again. The two halves are an hour apart, so
**between 04:00 and 05:00 UTC app rows outlive the CRM records they point at** —
a submission whose `CInformationRequest` has already been restored away is the
normal case there, not a defect (see the 403-vs-404 gotcha). Pause a night with
`touch /var/www/espocrm/.sandbox-hold` on the droplet (CRM half only — clear the
worker flag too if the app-side data matters). **Attachment uploads failing on
crm-test only** (`POST /Attachment` 500, *Permission denied for data/upload*)
means the restored upload folder is owned by the wrong uid — the reset used to
hard-code `1000:1000`; it must be the container's `www-data` (33)
([[sandbox-reset-upload-ownership]]). What survives by design: the CRM
team's Entity Manager work (it lives in files, and the reset rebuilds from it),
the `/setup` overrides in `app_setting`, roles, teams, email templates and the
integration credentials. Runbook: `SANDBOX-RESET.md`; the training data and its
showcase records: `training-guide.md` and `demo-records.md`.

## Commands

```bash
uv sync                                  # install deps (uv-managed; package = false)
uv run uvicorn main:app --reload --port 8000   # run locally -> http://localhost:8000/
uv run pytest -q                         # tests
docker build -t cbm-intake . && docker run --rm -p 8099:8080 cbm-intake  # prod-like run
./scripts/deploy.sh                      # deploy to DO App Platform (see DEPLOYMENT.md)
uv run python scripts/sync_form_options.py          # dry-run: form dropdowns vs live CRM enums
uv run python scripts/sync_form_options.py --write  # apply the sync (review the git diff)
uv run python scripts/publish_docs.py               # check every docs-site twin for drift
uv run python scripts/publish_docs.py --publish training-guide.md   # publish one
uv run python scripts/render_deployment_guide.py    # chapter deployment guide: YAML steps -> guide/ (--check in CI)
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
    through `_request`, which sends through **one process-wide connection
    pool** (`shared_http`, closed by the lifespan / worker exit — v0.245.0;
    a per-call client cost a TLS handshake on every CRM call), serves
    metadata / layout / i18n / enum-option reads from a **process-wide cache
    for `CRM_METADATA_CACHE_SECONDS`** (60; keyed by CRM + caller identity;
    v0.246.0 — ARMED only by `create_app` and `worker.main`, so a script's
    read-back after a CRM build stays exact) and wraps httpx transport failures as
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
// >>> crm-enum key=industryExperience field=CMentorProfile.industryExperience — generated; do not hand-edit between the markers.
industryExperience: [ ... ],
// <<< crm-enum
```

The marker is self-describing (no mapping duplicated in the script) and supports
`exclude="A|B"`. Default run is a **non-destructive dry-run** that exits
non-zero on drift, so it doubles as a CI check; `--write` applies, then review
the diff and commit. 16 lists across 4 `options.js` files, from 14 distinct
`Entity.field` sources, are managed today. The static file serves **both**
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
- **The events rail and the member page (F5, v0.235.0)** — behind
  `PORTAL_CALENDAR` (off by default, `/setup` → Features; needs Events on). The
  home view is a 22rem rail of upcoming events beside the tiles; **the portal
  has no width cap any more.** What the rail SELECTS is F3's and lives in
  `events/service.portal_calendar` + `events/visibility.py` — never re-filter
  in the portal. The rail shows `PORTAL_EVENTS_WINDOW_DAYS` (30) in full and
  folds the rest; two saved switches (Internal / Public) in the F3 preference
  store; Register/Cancel in the row and on the page behind a one-line
  confirmation; a phone strip at ≤767px. Every event opens
  **`/portal/events/{id}`** (the id, not the slug — Internal events often have
  none), a route registered ahead of the `/portal` static mount, whose body is
  the shared `frontend/shared/event-body.js` the public event page also uses.
  **Its reads are the member endpoints in `events/member.py`**, all through
  `is_shown(..., "portal")`, and **an event the member may not see answers 404
  in the same words as an unknown id** — keep it that way. The graphic comes
  from `/api/portal/events/{id}/image` because the public image route is keyed
  on the slug and gated on the public surface. Join link rule (D2): everyone
  when the event takes no registrations, registered members only when it does,
  decided server-side. **Where the link comes from (D3, v0.240.0):** the Join
  URL is **editable in Event Administration for Internal events only** — the
  spec's `editable_when` rule offers an app-managed field under a condition
  and `_writable` admits it only when the record *as saved* meets it; for a
  Public event Zoom owns the field and a posted-back value is dropped.
  Design: `prds/events/CBM_Events_Portal_Calendar_Design.md`.

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
- **Client counts are app-computed from `CEngagement`, never the CRM's own
  `currentActiveClients`/`availableCapacity`** (crm-test's formula is
  known-buggy). `ACTIVE_CLIENT_STATUSES` = Active, Assigned, Pending Acceptance
  **and On-Hold** (Doug's ruling 2026-09-29 — the same set Analytics uses, so
  every screen agrees). Available = Max Clients − Active Clients.
  **CoMentors** (v0.234.0) counts the active engagements where the mentor is a
  *non-primary* mentor, read per mentor through the `engagements` reverse link
  of `CEngagement.additionalMentors` (a relationship — `additionalMentorsIds`
  on a list read is always empty). It does **not** reduce Available, and only
  the Client Administration roster asks for it
  (`list_all_mentors(include_comentors=True)`) — Mentor Administration shares
  the function and makes no extra reads. A failed per-mentor read renders "—",
  never 0.
- **A mentor's name in the Available Mentors list opens a read-only detail
  popup** (v0.220.0): the CRM's own `CMentorProfile` detail layout rendered by
  the shared `/shared/detail-render.js`, plus a Contact panel and an "Other
  fields" sweep (`directory.service.detail(..., include_unplaced=True)` via
  `service.mentor_detail`), read as the signed-in user. Its footer
  Assign/Reassign button completes the assignment when the roster was opened
  from an engagement's Assign/Reassign card ("Browse the full mentor list…");
  unscoped it explains itself on click. View-only by ruling — editing stays in
  Mentor Administration.
- **Assign** (`service.assign_engagement`) sets `mentorProfile` +
  `engagementStatus="Pending Acceptance"`, stamps `engagementAssignedDate`, and
  re-homes assigned users across every related Contact, the CClientProfile and
  the Account. **Merge, never overwrite** (`_merged_assignment_payload`) — an
  overwrite silently revokes co-mentor access.
- **The mentor gets a stamp too** — `CMentorProfile.lastClientAssignedDate`, the
  last date that mentor was given a NEW client. Written by Assign and by
  Reassign (the **new** mentor only; the field records gaining a client, not
  losing one), never by a repair. Advance-only, feature-detected, and
  best-effort — a role without `CMentorProfile` edit logs a warning rather than
  losing an assignment already written. It is a sortable **Last Assigned**
  column in the Available Mentors picker (ascending = who is most overdue), and
  the roster query asks for the field only when the CRM has it. Spec:
  `cmentorprofile-last-client-assigned-field.md`.
- **Assign needs `User: read` on the acting role.** The assignedUsers stamp is
  a link write, and EspoCRM refuses it (403 `cannotRelateForbidden`, identical
  in 9.3.4 and 10.0.6) unless the user can read every User being linked. The
  Client Assignment Role carried no User grant until 2026-09-07; Cleveland's
  client admins only ever passed through a second team seat (Mentor Team).
  Ruling: `User: read all, edit own` on the role itself —
  `scripts/migrate_client_assignment_role.py`, Lakeside done, crm-test and
  prod owed (`OPEN-ITEMS.md` #28).
- **Stale-write guard**: the engagement is re-read before any write and the call
  is rejected (400, nothing written) if it already has a mentor or is no longer
  `Submitted`. The frontend reloads the grid on any Assign 400.
- **Assigning the SAME mentor again is a repair run**, not an error — it
  re-executes the idempotent re-homing. Reachable from the row's right-click
  menu ("Repair assignment…"), which is the only way to reach it since assigned rows
  have no Assign control.
- **Reassign Mentor** swaps `mentorProfile`, re-stamps the date, re-homes
  everything including every CSession (swap-merge: the old mentor is removed
  unless a co-mentor shares the user or they personally own the session),
  and deliberately **leaves `engagementStatus` untouched**.
- A successful Assign/Reassign opens the quick-compose with the mentor's
  `cbmEmail` and the EspoCRM `MentorAssignmentNotice` template pre-applied.
- Every row function is also on the **right-click context menu**. The Notes
  column edits `CEngagement.description` inline — staff-internal by design, and
  excluded from the session tools' Details tab for that reason. **Whether it
  is a rich editor or a plain textarea is feature-detected per load** from the
  field's live CRM type (`service.live_wysiwyg_fields`): wysiwyg ⇒ the shared
  editor with images, text ⇒ the textarea, because only a wysiwyg field binds
  its inline attachments (an unbound one is collected by EspoCRM's cleanup).
  crm-test and production are converted (production 10-11-26,
  `scripts/convert_notes_wysiwyg.sh`); Boston is owed
  (`cengagement-description-wysiwyg-crm-handoff.md`). The popup's
  Engagement-notes and Mentoring-needs fields are wysiwyg on both CRMs and take
  images now.
- **The View-details popup is editable** (v0.210.0). It opens at 90% of the
  window, resizable, with the title bar and the Save/Cancel bar pinned around a
  scrolling body. `service.ENGAGEMENT_EDIT_FIELDS` is **one spec serving as both
  the form layout and the update whitelist**; enum options come from live CRM
  metadata, link-picker options are **paged at 200** (an oversized page is a 403,
  not a truncation), a forbidden list degrades the field to read-only, a stored
  value outside the option list keeps its place, and Save sends only what
  changed. **The referring partner is named in the popup's HEAD** (v0.256.0,
  Doug's request 2026-10-12): a "Referred by <partner>" band under the
  title, visible in view and edit mode alike because the head is outside
  the swapped body; no partner, no band. **The assigned mentor is deliberately not an editable field** —
  swapping `mentorProfile` re-homes contacts, client profile, company and
  sessions, so the row hands off to Assign/Reassign instead.

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
- **Provisioning happens in TWO stages, keyed on `mentorStatus`** (Doug's ruling
  2026-08-17). `Accepted-Provisional` is a **signal** status, not a resting one:
  it means *accepted, still needs a Google account*.
  - **`Accepted-Provisional` → the Google Workspace account** (+ the All Members
    group), then the app **advances the record to `Provisional`** — so CBM can
    reach them during the provisional period. No EspoCRM login.
    `provision_mentor_email_steps`.
  - **`Approved` / `Active` → the EspoCRM login**, unchanged, on top of the same
    mailbox stage — so a mentor who jumps straight here still gets everything.
    It **never writes the status**: that would demote them.
  - The status advance requires a **confirmed** account (created and live, or
    already there). An UNKNOWN Directory check fails open for the *login* but must
    never advance the status — we don't record "has an account" on a guess. A
    stuck `Accepted-Provisional` is therefore the "account still owed" signal, and
    the sweep flags it.
  - Which stage runs is decided **server-side in the router** from the mentor's
    status; the frontend only asks. Both run in the SSE status window and never in
    `update_mentor`, because a mailbox create yields a **temp password a human
    must relay** (also why the sweep reports but never creates).
  - The group add is **non-fatal** (a distribution list is not the account), and
    an empty `GOOGLE_MEMBERS_GROUP` / Email-Setup address skips it — the address is
    its own switch. It needs a **third** DWD scope, `admin.directory.group`.
  - `_reserve_cbm_email` is what keeps the login-reuse guard sound now that every
    mentor reaches approval carrying a `cbmEmail`: an address is only stored if no
    User holds it as a userName and no *other* mentor profile holds it. A merely
    *existing* mailbox is not "taken" — a pre-created mailbox is the normal case.
  - The login half creates an EspoCRM User (`firstname.lastname@` the
    `MENTOR_EMAIL_DOMAIN` setting, default `cbmentors.org` — v0.217.0,
    welcome email via `sendAccessInfo`), places it in `MENTOR_TEAM_NAME`, links it
    as `assignedUser`, back-fills `cbmEmail`, and stamps the User onto the linked
    Contact. **Privilege split — EspoCRM makes User creation admin-only; API keys
    and `api`-type users cannot do it and a *regular* user with roles 403s.** So
    this runs as a **dedicated admin service account** (`ESPO_PROVISION_*`,
    Type=Admin) via `core/admin_client.py` — Mentor Admin staff stay non-admin.
  - Best-effort: a failure returns `provision:{ok:false,error}` and never rolls
    back the saved status. Every run is action-logged (it changes a status on the
    app's own initiative), with the temp password stripped.
- **Permission teams** on the Status tab write the linked **User's** `teamsIds`
  (teams live on the User, not the profile), also under the admin account.
  Always clickable; a login-less mentor gets an explanatory message.
- **"Update Mentor Status"** sweeps the roster: verifies each login User, checks
  the mailbox and its members-group membership, flags anyone stranded at
  `Accepted-Provisional`, runs `reconcile_user_links`, and bulk re-syncs
  `recordStatus`. This is the staff-facing repair button for stamp drift. It
  **reports, never creates** — see the temp-password reason above.
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
- Also hosts the **email-signature editor** (EspoCRM `Preferences.signature`),
  whose toolbar carries the Insert-logo button (`ORGANIZATION_LOGO_URL` — see
  the CBMRichText convention); uploaded/pasted images stay refused because
  recipients can't reach them.
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
- **The Overview notes editor follows the field's LIVE CRM type** (v0.252.0,
  `service.live_notes_type`): wysiwyg ⇒ the rich editor, text ⇒ the plain
  box. Funder Notes (`CSponsorProfile.description`) is wysiwyg on crm-test
  and production since 10-11-26 (one command per instance,
  `scripts/convert_notes_wysiwyg.sh`; Boston owed) —
  `csponsorprofile-description-wysiwyg-crm-handoff.md` (Doug 2026-10-11:
  "the funder notes should be wysiwyg").
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
- **Events (partner and funder, `sponsored_events_link`)** — the Events tab
  just before Communications (v0.239.0): every event linked to the record,
  with registered / attended / became-a-client counts and totals, all from
  `events/reporting.sponsor_rollup` so every screen agrees. "Became a
  client" is the programme's conversion rule scoped to one event, and never
  a separate "requested a mentor" count (Doug's ruling 2026-10-07). The
  endpoint feature-detects the reverse link and answers `available: false`
  with a reason on a CRM without it; an unreadable count renders "—", never 0.
  **The counts compute under the org-wide API key** after the user's own read
  of the parent record gates the tab — the Partner Manager and Sponsor Manager
  roles hold no event, registration or engagement access, and the numbers are
  aggregates (the directory-availability precedent).
- **Grants (funder only, `grants_link`)** — the Grants tab: awards, their
  deliverables, and later their funder reports. The **grant is the hub**:
  `CContribution` rows become its payments and deliverables its obligations, and
  the two are **siblings under it, never a chain**. Client attribution lives on
  the grant (`fundedEngagements`), so a renewal starts clean. Deliverable
  progress math lives in ONE place (`service.deliverable_progress`) — a stored
  status always beats the arithmetic, and a Narrative deliverable has no
  percentage at all. Gated by `GRANTS_ENABLED` **and** CRM feature detection,
  which fails closed. Plan + rulings: `prds/grant-management-plan.md`.
- **Partner and Funder can be CREATED here** (`RECORD_QUICK_ADD`, off by
  default): the grid's "+ Add partner" / "+ Add funder" runs the same
  Account → Contact → profile sequence the public intake forms do, as the
  signed-in user. `DomainConfig.create_spec` gates both the button and the
  routes (mentor has none — engagements arrive through intake), and the spec is
  BOTH the form layout and the write whitelist. Same dedupe policy as intake:
  a same-named company / same-email contact is reused and null-filled, never
  duplicated; a reused company gains the type value merge-only. **A website,
  when entered, must agree with the match** (v0.237.0, Doug's ruling
  2026-10-07): a same-named company at a *different* web address is a
  different company, and the save is **refused with the existing company
  named** — never a second same-named Account, which would make every
  name-based match in the CRM ambiguous. Same rule on the Details tab's
  "+ New company" picker (shared function). **Since v0.254.0 the quick-add's
  Company is a picker** (every company under the org-wide key, website
  beside the name, "+ New company…" for the typed path): a chosen company's
  id rides as `companyId` and skips the match and the website rule — the
  way to make a company that is both a partner and a funder. **A picked
  company with an empty contact block inherits the primary contact of its
  record in the other application** (Partner Management ↔ Funder
  Management; v0.257.0, Doug 2026-10-14): the newest such record naming
  one wins, read under the org key, contact stamped merge-only. Compared through
  `core/crm_upsert.website_key` (scheme, `www.`, case, trailing slash
  ignored; the path counts). No stored website ⇒ match and null-fill it.
  **The new contact is owned by its creator and the domain team** (v0.249.0,
  Doug's ruling 2026-10-09): `_create_quick_contact` stamps a NEW contact with
  `assignedUserId` + `assignedUsersIds` and `teamsIds`, exactly as the
  profile is. Without it EspoCRM refuses the create for a role whose
  Assignment Permission is *not-set* ("Assignment failure: assigned user or
  team not allowed" — the Sponsor Manager Role on both CRMs), and a
  team-read role could never see the contact it just made. The Partner
  Manager Role only passed because it is *all*/*all*; Partner Management and
  Funder Management share the function and must stay identical. **The company too** (v0.249.1):
  the match, the null-fill, the type merge, the team lookup and the create
  all run under the intake API client (a team-read user matching as
  themself created a duplicate per attempt; the Sponsor Manager Role has no
  Team read), a NEW company carries the creator and the team, and a REUSED
  company or contact GAINS them when missing (`_merge_owner_stamps`,
  merge-only, best-effort) — the contact's company link needs the user to
  read the company. Null-fills and creates still run as the user.
- **A new contact on the Contacts tab reuses a known email** (v0.264.2, the
  staff screens are bound like the public forms): matched under the intake API client, linked,
  null-filled as the user; a CBM member is refused.
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
- **The partner's Details tab carries its client intake link** (v0.255.0):
  a card under the summary strip with the `?partner=<id>` address and a
  Copy button, gated by `DomainConfig.intake_link_form` (partner only) and
  derived in the router from `APP_BASE_URL`, else the request's origin.
  What the link produces shows on the Referred Clients tab. Rule in the
  five-forms section above.
- **Additional managers on partner and funder records** (v0.251.0, Doug's
  requirement 2026-10-11, Partner Management and Funder Management alike): the co-mentor model —
  `CPartnerProfile.additionalManagers` / `CSponsorProfile.additionalManagers`
  (many-to-many to `CMentorProfile`, reverses `comanagedPartners` /
  `comanagedSponsors`), **feature-detected** per request
  (`service.comanager_link_available`) so a CRM without the build shows
  nothing. Same routes, same CBM-contacts card, same picker; off the
  engagement the add is the link plus a history note — no stamps, no
  session backfill. The email scope reads every domain's second reverse
  link (a 404 is skipped at debug); Drive grants entitle them; My Email
  already did. Plan `scripts/plans/additional-managers.json`; handoff
  `cpartner-csponsor-additional-managers-crm-handoff.md`. The links exist
  on crm-test and production (10-11/12-26, both passed as non-admins);
  Boston owed with its next release. **"Make primary" on a CBM row**
  (v0.253.0, Doug's ruling 2026-10-12): `service.promote_comanager` writes
  the manager link first as the user, moves the new manager out of
  `additionalManagers`, and **keeps the former manager as an additional
  manager** (non-destructive, one click undoes it); partner and funder
  only — the engagement's mentor is Client Administration's.
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
  ([[espo-link-checks-both-sides]]). **Attendee linking goes through the same
  helper** (v0.258.6): `_sync_attendees` and the create-path relate loop
  escalate a foreign-contact 403 exactly as co-mentor linking does — a mentor
  recording an attendee assigned to someone else used to hit the warning
  "N attendee change(s) could not be applied" (Greg Malkin, prod 2026-10-15).
  The warning now fires only when no admin is configured or the admin fallback
  also fails.
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
- **A Held-Company row has its own control, not Approve** (v0.238.0): the
  company the submission names exists at a different web address, so
  *Company ▾* offers *Same company* / *Different company* (name required,
  must differ from the one on file); both write `delivery_overrides` and
  re-queue. A bare re-drive is not offered — it would hit the same conflict.
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
  enforced at save. **All seven record views host one** — Mentor / Engagement /
  Partner / Funder / Contact / Company / Client, each with a starter dashboard.
  Company got a real record page of its own
  (`/directory/companies/record/{id}`, sharing `record.html` with View Contact
  but without Communications); Client has no screen by ruling — its dashboard
  renders as a second section on the **engagement** Analytics tab, keyed off
  `clientProfileId` in the session-detail payload.

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
- **Every setting is editable unless a change is genuinely impossible** (Doug's
  ruling, 2026-08-28: *"All settings should be editable, unless a change would
  make the system unusable. Then there must be a verification that the system is
  still functional."*). The denylist is down to **three** keys — `DATABASE_URL`
  (the override table lives inside the database it names, so a move would be
  left behind in the database being abandoned), `APP_ENCRYPTION_KEY` (rotating
  it makes every stored secret permanently unreadable — data loss, not lockout)
  and `RELEASE_TAG` (the release stamp travels in the image's own
  `release-tag.txt`; a stored override would survive a restart and make the
  deployment misreport which promotion it is). All three are **visible and read-only**,
  each refusal naming its reason. Everything else that used to be hidden — the
  CRM address and key, dry-run, the provisioning account, every integration
  credential, the session secret, `SETUP_ENABLED`, `SETTINGS_OVERRIDES` — is
  editable through the **verified path** (`setup/verify.py`):
  - **Pre-flight**: the value is tried before it is stored. A CRM key the CRM
    rejects, or an address that answers but holds none of this app's entities,
    is refused with the CRM's own error. A probe that cannot *reach* its target
    returns `unknown`, never `ok`, and `unknown` does **not** block the save —
    an admin fixing configuration during an outage must not be blocked by it.
  - **Post-apply**: a `VERIFIED_KEYS` change that leaves the system non-functional
    is **reverted automatically**.
  - **Confirm-or-revert**: `LOCKOUT_KEYS` (the two switches guarding this page,
    the session secret, the cookie flag, allowed origins) apply with a
    **10-minute countdown** and undo themselves unless an admin confirms. No
    probe can detect a lockout — the app is working perfectly and simply will not
    let anyone back in — so this is the only mechanism that survives it. The
    sweep runs in **both** processes on the settings timer, and works directly
    against the database so it still fires when the change under test was
    `settings_overrides=false`.
  - **Secrets are editable but never readable** — set a new one, never read the
    old one back. Stored **encrypted** with `APP_ENCRYPTION_KEY`; without a
    cipher a secret is **refused**, never written in plain text. `DATABASE_URL`
    counts as a secret because the password is inside the URL. History stores
    `(secret set)`, never the value.
  `SETTINGS_OVERRIDES=false` is still the env-only break-glass.
- **Every setting is on the page — including the ones that need a restart**
  (Doug's ruling, 2026-08-28: a setting hidden where it cannot be viewed or
  edited is unacceptable). `BOOT_READ_KEYS` are curated into a **Restart
  required** group that explains itself, and each row shows the value **in
  force** beside the stored one, badged *Waiting for restart* when they differ.
  Two things make that honest rather than a repeat of v0.190.1, when these were
  offered with a "takes effect on next deploy" badge and toggling
  `events_enabled` produced a portal tile whose routes did not exist:
  - **`core/boot_overrides.load_at_boot` installs the override layer at the very
    top of `create_app`**, before routers are mounted, middleware built or
    logging configured. Previously the layer loaded afterwards, so such an
    override never applied *at all* — a redeploy re-ran the mounting first. It
    never raises, and on a database failure it degrades to the **deployment's**
    values, never the code defaults.
  - **The live `Settings` object is not the truth for these keys.** The periodic
    refresh installs a newer value into it while the already-built routers keep
    the old one, so reading it back would report a change as taken effect when it
    had not. `boot_overrides.state().snapshot` is the only honest source and is
    what the page reports as `inForce`.
  `DENYLIST` now holds only secrets, infrastructure and the break-glass pair —
  plus **`release_tag`**, which is curated **read-only**: it is stamped into the
  image, so a stored override would survive a restart and make the deployment
  misreport which image it is running. **The denylist is still filtered on READ
  as well as write**, so a row that outlives its rule goes inert with no cleanup.
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

### Campaign Management — `/campaigns`

Marketing Admin Team (`CAMPAIGNS_ALLOWED_TEAMS`), behind **`CAMPAIGNS_ENABLED`**
(off; read **per request**, so a `/setup` flip needs no restart — the routers
mount with the staff stack and answer 404 while off). Prospect marketing
Phase 1 (v0.258.0, 10-15-26); the arc is `prds/prospect-marketing/` (its
`README.md` first; `rulings.md` 1–33 binding; `build-plan.md` v0.4). Package
`campaigns/` in the house shape. **Needs the Phase 1 CRM change**
(`coutreach-entities-crm-handoff.md`, `contact-sms-opt-in-crm-handoff.md`):
every read feature-detects `CProspect` / `COutreachCampaign` / `COutreachTouch`
and the campaign's links, and a CRM without them answers *not available* with
the reason.

- **Who acts:** campaign reads and writes run as the signed-in user (the
  Marketing Admin Role creates/reads/edits the three entities). Aggregates and
  machine writes — the postcard selection and its Planned touches, the import's
  already-known reads and its Company/Contact creates (**ruling 33**), the
  counts on the partner's Campaigns tab — run under the **org-wide API key**.
  Relating a campaign to a partner needs edit on the partner, which that role
  lacks by ruling, so `service._link_or_escalate` retries only a
  `noAccessToForeignRecord` denial as the admin account.
- **Links live in the application database** (ruling 31; `campaigns/store.py`,
  migration 0031: `campaign_link`, `campaign_link_visit`, the import ledger).
  `GET /c/{token}` **never calls the CRM**: it counts the visit and 302s to the
  destination with `?campaign=&link=`. A token that resolves to nothing is a 404
  in the same words whatever the reason; a **retired link still opens** and its
  visit is flagged late; an event link's slug is cached and refreshed whenever
  staff open the Links tab. A postcard's per-card code is `/c/{link}/{scan}`,
  its QR PNG `…/qr.png` (`core/qr.py`, `segno`).
- **The postcard kind** (`campaigns/postcard.py`): *Build the list* selects
  under rulings 10, 14 (one card per business, ever — any Sent/Delivered/
  Returned postcard touch from any campaign excludes the target) and 15 (a dead
  address is skipped), reconciles this campaign's Planned touches (kept /
  created / Cancelled) and moves Draft → Awaiting sign-off. *Sign off and run*
  needs the **typed piece count** (ruling 13), stamps the campaign and sets
  **Signed off, which is the worker's queue** (`run_campaign_cycle`, every
  `CAMPAIGNS_RUN_SECONDS`): each Planned touch becomes a vendor piece with the
  **touch id as the idempotency key**, then Sent with `scanToken`,
  `mailedAddress` (the snapshot) and `stageAtTouch`; Complete when none is left.
  The vendor is `core/postal.py` — `DryRunPostalClient` by default (nothing
  printed, `dryrun-<touch id>`), `LobPostalClient` written from the published
  API and **never run**. Delivery events arrive signed at
  `POST /api/campaigns/postal/events` (404 until `POSTAL_WEBHOOK_SECRET` is
  set); a returned piece marks the **address** dead and leaves the rung
  (ruling 15). In dry run a staff *Simulate* button posts the same event.
- **The landing page `/p/{token}`** (`campaigns/landing.py`, behind
  `CAMPAIGNS_LANDING_PUBLIC`): the scan writes `firstScannedAt` once,
  `scanCount`, outcome Scanned and moves the record to **Lead, advance-only**
  (ruling 16); a Planned touch is a preview and writes nothing. The page shows
  **only what the card printed** — the business name and the address as mailed
  — never an email, phone or person's name the chapter holds. Its response is
  the sixth form kind, `forms/prospect_response/` (delivery-only, scoped
  duplicate hold by `scan_token`, `company_keys` for the `held_company` hold):
  email promotes the person, website the business (ruling 21), consent
  **true-only**, never a relationship record. A mentor or information request
  then opens the standard form with `?prospect=&campaign=&link=`; the typed
  details travel in `sessionStorage` only, and `GET /api/campaigns/prospect/{id}`
  serves the printed facts alone.
- **Every public form carries `campaign_id`, `campaign_link`, `prospect_id`**
  (declared on `core/forms.BaseSubmission` — an undeclared key is dropped by
  capture) and the **SMS tick** `sms_consent` → `Contact.cSmsOptIn`, true-only
  (ruling 9). **Honoured at delivery since Phase 2 (v0.259.0)** — the next
  bullet. The shared
  `frontend/shared/campaign-link.js` fills the hidden fields, shows the banner
  from the name-only lookup `GET /api/campaigns/public/{id}` and prefills the
  printed facts. The GET rate limit covers `/c/` and `/api/campaigns/public/`.
- **The import** (`campaigns/imports.py`): plan, then apply; the file is read
  in the browser and posted as text (no multipart); the already-known check is
  Company by name **and** postal code, Company by website key, Contact by email
  (ruling 12) — a match still creates the prospect record, with the *Already
  known* side exit; a re-upload of the same file is a no-op through the ledger.
- **The Leads and Review grids at volume** (v0.267.0, build plan § 7b,
  Doug's five answers 10-20-26): `campaigns/leads.py` — the CRM searches,
  sorts and counts a page at a time (never load every lead; the old list
  stopped silently at 2,000); bulk Disqualify / Do Not Contact over ticked
  rows or all matching (cap 2,000, batches of 50, each lead re-read and
  skipped if changed since seen); a CSV export; Review as a queue whose row
  takes the website or email and qualifies in one step. **Every decision
  carries what the reviewer saw (`seenStatus` / `seenExit`) and a change
  since answers 409 naming who** — keep that on any new review action.
- **The partner's Campaigns tab** (CM-5): `DomainConfig.sponsored_campaigns_link`
  on the partner domain only, the Events-tab shape exactly.
- **Phase 2 — the public forms honour the ids** (v0.259.0, 10-17-26; build plan
  § 5). One module, `campaigns/attribution.py`, serves the five
  orchestrators (client intake, information request, event registration,
  partner, sponsor): a **validate-or-drop** read of the campaign and of the
  prospect record (unknown, stale, cancelled, forged, or a CRM without the
  link ⇒ the attribution is dropped with a logged note, never the
  submission — every write feature-detects its link or field, so
  production until its Sunday slot behaves exactly as before); the campaign
  on the **relationship record every time** (`outreachCampaignId`) and on
  the Contact and Company (`cOutreachCampaignId`) **only when that
  orchestrator created them** (ruling 27 — on a registration, the create
  only, so a repeat sign-up keeps the first); a prospect record's
  **promoted company used by id before any name match**, its promotion
  links set if empty; the rung as evidence, advance-only (information
  request and registration ⇒ Warm Lead on the Contact, the entry stage
  written once on a new record; a client has no stored rung — Candidate is
  read from the engagement); the notes line *"Arrived through the campaign
  <name>."*. **Step 6a (ruling 30):** the engagement's `referringPartners`
  holds EVERY referring partner — the partner link's partner plus every
  partner the campaign names — related after the create; the single
  `referringPartner` is the partner link's own and is never written by a
  campaign; the three readers (the popup's *Referred by* band, the
  Referred Clients tab via `engagements` + `referredEngagements`, the
  Partner Analytics metrics) take the **union**, deduplicated by
  engagement. **The relabel at conversion is one rule** (§ 1.9):
  `core/crm_upsert.merged_types` — appending Client, Partner, Sponsor or
  Mentor removes `Prospect`, nothing else is ever removed; both
  `merge_company_type` and the new `merge_contact_type` apply it, and
  `merge_contact_type` is the ONE reason a public form touches a matched
  contact's type (the information request and registration forms never do).
  **Ruling 34:** the information request form creates its company typed `Prospect`,
  `cClientStatus` untouched, a matched company left alone (it used to gain
  Client), feature-detected with the old shape as the fallback;
  `scripts/relabel_info_request_companies.py` (dry-run default) relabels
  the old-shape companies once per CRM — Doug runs it. **The carry-through:**
  the programme page appends `?campaign=&link=` to every event address it
  renders (`CBMEvents.config.eventUrlQuery`); a freshly typed address has
  left the campaign. **The Responses tab** leads with *Responded* /
  *Converted* (`campaigns/router.summarize_responses`) and links through:
  `/assignments/?engagement=<id>` opens the popup, `/events/?event=<id>`
  the event (both new deep links), partner / funder record pages,
  Submission Admin for an information request.
- **Ruling 37 (v0.260.2):** the information request and registration
  forms never write a stage on a record that already holds a relationship
  type — `attribution.holds_relationship`, checked inside `advance_rung`, so
  every caller must SELECT the type field (`cContactType` / `cCompanyType`).
- **Phase 3 — lists, review, calls** (v0.261.0, 10-18-26; dark behind
  **`CAMPAIGNS_CALLS`**, read per request). The **Review** tab
  (`campaigns/review.py`): *Qualify* / *Unqualified* (note required) on an
  Unverified record, *Do Not Contact*, *Not the same company* (clears
  *Already known* and `alreadyKnownCompany`, the link under the API
  client); **no side exit is ever written over another**. **The call kind**
  (`campaigns/calls.py`): a promoted prospect record IS its Contact; *Sign
  off* starts the list at once (no worker) and the last recorded row
  completes it. **Who calls is ruling 36**: the members of the teams named
  on the campaign (its own `teams`, set by the form's *Who calls* picker;
  none ⇒ the Marketing Admin Team), gated per campaign in `calls`, NOT by
  `CAMPAIGNS_ALLOWED_TEAMS` — the Calls page `/campaigns/calls.html` and
  `/campaigns/api/calls*` admit any signed-in user and the campaign decides.
  **The touch is written as the caller; the rung, the `Declined` exit, the
  *Call again* row and the completion under the API client** (the Mentor
  Role reads `CProspect`, never edits it). **Every call record carries its
  campaign's teams** (v0.261.1): the Mentor Role's Assignment Permission is
  *team*, and EspoCRM refuses such a role ANY save of a record with neither
  a team nor an assigned user (`isPermittedTeamsEmpty`) — so the API client
  stamps the teams before the caller writes. The Mentor Role's grants
  (`COutreachTouch` read/edit, `CProspect` read) are in
  `migrate_outreach_roles.py`. **The Stale sweep** (`campaigns/stale.py`):
  Unverified/Qualified, no side exit, no Planned touch, no activity within
  `PROSPECT_STALE_DAYS`; worker every `PROSPECT_STALE_SWEEP_SECONDS`, and
  `/setup` → Operations *Prospect Stale sweep* (its plan text carries no
  clock, so the fingerprint holds). **Every number is
  `campaigns/reporting.py`** (`summarize_responses` moved there; the
  router re-exports it): the record page, the Responses tab and the new
  Analytics page *Campaigns* (`analytics/campaigns.py`, live, org key).
- **Phase 4** (v0.262.0–v0.264.0, 10-18-26). **Texts (rulings 38, 39,
  `CAMPAIGNS_SMS`):** the application sends — `core/sms.py`, Twilio behind
  `DryRunSmsClient` (the default, `SMS_PROVIDER`); the wording is the CRM
  field `COutreachCampaign.smsMessage`, feature-detected
  (`cfg.CAMPAIGN_OPTIONAL_FIELDS`, dropped from the form and the write
  when absent) and NOT in `CAMPAIGN_SELECT` (a CRM without it would refuse
  the select — read it by a whole get). Selection is ruling 9 (a Contact
  with `cSmsOptIn`). Sign-off refuses wording without STOP. **A touch is
  marked `vendorStatus=sending` before every send and a touch left so is
  never resent by itself** (Twilio has no idempotency key). Sends only
  inside `SMS_SEND_HOURS`. Signed callbacks `/api/campaigns/sms/inbound`
  (STOP → `cSmsOptIn` false) and `/status`, 404 until Twilio is
  configured; the body is parsed by hand (no python-multipart).
  **Email (`CAMPAIGNS_EMAIL`):** `campaigns/email.py` pushes each campaign
  as its OWN list `Campaign — <name>` and never reads or writes the
  standing list or its stored id; *Mark as sent* completes it. **The
  funnel** (`reporting.funnel`, Candidate/Client from the engagement
  status) and **the campaign dashboard scope** `COutreachCampaign`
  (`analytics/campaigns.py`, counts under the org key after the user's read
  — the Marketing Admin Role reads no engagement). **Opportunity on
  attendance** (`attribution.opportunity_on_attendance`) from the manual
  mark, the check-in and the Zoom pull, org key, best-effort.
- **The lead model (v0.265.0, rulings 41–53; build plan § 7a)** supersedes
  the rung words in the Phase 1–4 bullets above. A lead (`CProspect`, CRM
  label *Outreach Lead*) carries `leadStatus` Unqualified · Qualified ·
  Disqualified · Converted and `leadSource`; a Company or Contact is made
  only at first contact and carries `cFunnelStage` Prospect · Engaged ·
  Opportunity. One conversion rule, `campaigns/conversion.py`: an email or
  a website converts; a business lead becomes a Company (matched by website,
  then name and postal code) and the Contact for the email (ruling 52); a
  scan changes nothing (51). A filing row with a website or email enters
  Qualified (53). Every new public-form record gets a lead Converted at
  once (48, `attribution.record_lead`, retry-safe through
  `ResumableClient.created_ids`). **Stage writes need the NEW options**
  (`rung_available`): a CRM still on the old ladder gets none rather than a
  400. Every campaign read requires `CProspect.leadStatus`. Three counts:
  Responded, Converted, Became a client, partner or funder (46).
- Owed: nothing on production's CRM (both slots done 10-18-26; every
  campaign switch off there — turning one on is Doug's call at `/setup`);
  Boston with its release; a seeder and sandbox re-baseline; the Twilio
  account and A2P 10DLC before any real text; questions 2, 4, 5 before the
  first real card (`OPEN-ITEMS.md` #51).

### Events & Webinars — `/events`

Replaces the data layer behind `clevelandbusinessmentors.org/webinars/`, which
today runs on a Google Apps Script plus a browser-side YouTube API call with
**EspoCRM involved at no point** — so every registrant is an invisible lead.
Staff guide: `event-administration.md`; activation + test script:
`EVENTS-SETUP.md`; schema: `cevent-entities-crm-handoff.md`.

**Live on BOTH deployments since 2026-09-14; the website still runs on the Apps
Script.** `EVENTS_ENABLED` + `EVENTS_PUBLIC_API` are on for crm-test and
production; `ZOOM_EVENTS`, `EVENTS_REMINDERS` and the attendance pull are off
everywhere. Production's overlay also carries `YOUTUBE_API_KEY` and
`YOUTUBE_PLAYLIST_ID` (five playlists, comma separated) on the **web** component
only — the worker needs neither until attendance is switched on.

**Production holds a real programme now**: 10 recorded webinars imported from the
playlists on 2026-09-14 and published with topics, plus one internal
`CRM Training Webinar` that is **published** and dated in the future, so it is
currently the only thing on the public calendar — check whether that is intended
before the redirect. Zero registrations so far; the end-to-end test registration
is still owed.

**The only thing between here and the lead leak stopping is the redirect
itself** — one rule on the marketing site, and removing it is the rollback. Phases 1, 2, 3, 5
and **6** are built. **Phase 4 — the WordPress plugin — was STRUCK on
2026-09-11**: Doug ruled that the marketing site should **redirect** to a page
this app serves rather than embed or reimplement one. What stops the lead leak
now is one redirect, plus two things owed before it (`OPEN-ITEMS.md` 19d
consent, 19f the per-event duplicate hold).

### The PUBLIC pages — `/webinars/` and `/webinars/{slug}` (v0.222.0)

`events/pages.py` + `events/public_frontend/`. Gated on `events_public_active`,
so an unconfigured deploy serves nothing. Assets ride `/webinars-assets` — a
separate top-level path, because `/webinars/{slug}` is a route and "assets"
would be indistinguishable from a slug.

- **They are ROUTES, not static files, for two reasons.** A social crawler runs
  no JavaScript, so each event's `<head>` is filled **server-side** or a shared
  link renders as a blank card. And an unpublished event must **404** — `CEvent`
  doubles as the internal calendar, so a page that merely rendered empty would
  still confirm the record exists.
- **The body is the SAME renderer the staff preview drives**
  (`/events-plugin/cbm-events.js`) under the site's own stylesheet, so the
  preview and the live page are one code path rather than two kept in step.
- **The site's stylesheet has TWO wrapper scopes, and they are not
  interchangeable**: `.cbm-wb` for the calendar, `.cbm-yt` for the recorded
  library, each carrying its own CSS variables, every rule written as
  `.cbm-wb .panel …`. The wrapper must be an **ancestor** of `.panel`, never the
  same element. Getting this wrong unstyles a whole panel and raises no error —
  it shipped that way for an hour on 2026-09-11 and is now in the class contract
  (`HOST_CLASSES` in `tests/test_events_graphic.py`).
- **Branding renders first, page values second**, every value HTML-escaped, so
  CRM-authored content is never rescanned for a `{{token}}`.
- **Both public doors send `consent: false`** — the calendar modal and the event
  page's own form — so a registration records **no opt-in at all**. That is
  deliberate and blocking: see `OPEN-ITEMS.md` 19d.
- **`EVENTS_PUBLIC_BASE_URL` empty means "this app"** (derived from
  `APP_BASE_URL` + `/webinars`). It used to default to the marketing site's
  `/webinars`, which **404s**, so every shared event link pointed at nothing.
- **The marketing page's whole opening came across, not just its panels** — the
  navy hero, the gold strapline band and the organisation's own top-level menu.
  All of it is content on a page that redirects away, and the first side-by-side
  (2026-09-12) is what found it missing, exactly as it found the presenting
  invitation. Settings: `EVENTS_HERO_TAGLINE`, `EVENTS_HERO_PILLARS`,
  `EVENTS_HERO_BAND` (each emptiable) and `ORGANIZATION_SITE_NAV`
  (`Label|path` pairs; a leading `/` resolves against
  `ORGANIZATION_WEBSITE_URL`, so a chapter changes one setting, not seven).
  The menu is built **server-side** for the same reason the name is substituted
  there: a menu that appears a moment late is worse than none, and it is the
  visitor's only way on to the rest of the site.
- **The recorded library has a TOPIC filter** (v0.230.x). It offers only
  subjects that actually have a recording — a filter listing an empty one is a
  dead end — computed from the whole library rather than the current results so
  the options do not shift as a visitor searches, and hidden below two topics.
  The selector sits **above** the search box because the search runs *inside*
  the chosen topic, and the placeholder names it. Clearing the search box
  reloads on its own (`input`, not the `search` event, which Firefox does not
  raise). One CRM read serves the results, the topic list and the count:
  `published_recordings` plus the pure `filter_recordings` / `recording_topics`.
  Order follows the live field's option order (`service.live_topic_order`),
  `cfg.TOPIC_ORDER` as the fallback; a value that has drifted out of the enum
  still appears.
- **An event carries SEVERAL curated topics, and nobody types one** (v0.242.0,
  Track F F1, Doug's ruling 2026-10-08: *"They must pick from the list, or
  update the list if they do not like the choices."*). `CEvent.topics` is a
  multiEnum with the same ten values as the single `topic` it supersedes.
  **Feature-detected, no switch**: a CRM without `topics` behaves exactly as
  before; on a CRM with it the single `topic` is **retired** from the editor,
  the write whitelist and every read — `service.event_topics(row)` decides by
  whether the row carries the `topics` key (a CRM that lacks the attribute
  omits it), and never falls back to `topic` when `topics` is merely empty.
  A chosen filter topic matches a recording carrying it among others; the
  eyebrow, the grid chips and the Events tabs name all of them; public
  payloads keep `category` (the first topic) and gain `categories`.
  `scripts/migrate_event_topics.py` copies the old value once per CRM, after
  `scripts/plans/cevent-topics.json`. The retired column stays until a removal
  handoff. Design: `prds/events/CBM_Events_Topics_Design.md`.
- **Panel wording is the SITE's, not ours** — "Calendar of Upcoming Webinars"
  and "Find a Recorded Webinar". Inventing better names put our page out of step
  with the one it replaces; don't re-invent them.
- **⚠️ The recorded library is empty and that blocks the redirect**
  (`OPEN-ITEMS.md` 19i). The live page's library comes straight from the YouTube
  playlist; ours comes from `CEvent` rows with a `recordingUrl`, and there are
  none on either CRM. `scripts/import_youtube_events.py` fixes it and has never
  been run — it needs `YOUTUBE_API_KEY` and `YOUTUBE_PLAYLIST_ID`, neither of
  which is configured anywhere, and the playlist id is not in the live page's
  source.
- New settings: `ORGANIZATION_WEBSITE_URL` (the back-link and the menu's base,
  per-chapter like `DOCS_SITE_URL`) and `EVENTS_CONTACT_EMAIL` (the
  presenting invitation's address; empty falls back to `OPS_MAILBOX`).
- The portal's bottom section is **"Public pages"** and leads with Workshops and
  Webinars, beside the five intake forms.
- Redirect runbook: `EVENTS-SETUP.md` § 6b. **The rollback is removing the
  redirect** — under a minute, no deploy.

- **The staff Overview tab is the whole record, read-only** (v0.231.0, Doug's
  rule): facts left, driven by `EVENT_FIELDS` so a new spec field shows without
  a second edit; graphic + Summary + Full description + Syllabus right, rich
  text through the shared sanitizer. Every slot renders even when empty.
- **An event's partners and funders are RELATIONSHIPS, set in the editor's
  Sponsorship group** (v0.239.0, plan `prds/mailing-list-and-event-sponsorship-plan.md`).
  `events/config.SPONSOR_LINKS` names the two links (`partnerProfiles` →
  `CPartnerProfile`, `sponsorProfiles` → `CSponsorProfile`, both reversed as
  `sponsoredEvents`); they are feature-detected per load from
  `entityDefs.CEvent.links`, ride their own `PUT …/sponsors` with the exact
  set per link (never the record PUT — a `*Ids` write is ignored), and only a
  `noAccessToForeignRecord` denial escalates to the admin account. The
  Marketing Admin Role reads partner and funder profiles, it does not edit
  them (Doug's ruling 2026-10-07). Production and Boston lack the partner
  link until the Phase A handoff is applied there, so they show Funders only.
- **Presenters are RECORDS, one per presenter per event** (v0.241.0, Track F
  F4, `prds/events/CBM_Events_Presenters_Design.md`). `CEventPresenter` holds
  the biography, title, company, photo and order as **copies made when the
  presenter is added and never refreshed** from the Contact or the mentor
  profile (Doug's rulings 10-07/08-26) — a past event's page is the record of
  what was presented. Added from the editor's Presenters group: a Contact
  search, or a new person whose unknown email **creates a `Presenter`-typed
  Contact** (an existing Contact is reused untouched — no null-fill, no type
  merge). One switch per event, `showPresenterBios`. Every staff read and
  write runs **as the signed-in user** (D1: the Marketing Admin Role carries
  Contact create + read, mentor-profile read **and Assignment Permission
  `all`** — `scripts/migrate_presenter_roles.py`. **A role that creates a
  record the app leaves unassigned needs Assignment Permission `all`**: at
  *not set* or *team* EspoCRM's checker inspects the new record's teams and
  assigned users, and at *team* a record with neither is refused outright
  ("Assignment failure: assigned user or team not allowed") — read from
  `Acl/AssignmentChecker/Helper.php` on crm-test 10-08-26 after the live
  pass found Contact create 403ing on a role that had the create grant); the page reads run
  under the org key, whose role reads the entity. Photos ride routes **keyed on the event and the entry** (public by
  slug, portal by id, staff authenticated), never on an attachment id. Dark
  behind `EVENT_PRESENTERS` AND feature detection (fails closed). The bare
  `CEvent.presenters` link is unused and left in place. crm-test CRM done;
  production and Boston owed (`cevent-presenters-crm-handoff.md`).
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
  postdates their first attended event. **Both record tabs read the
  registrations under the org-wide key after the user's own read gates the
  tab** (v0.249.2, Doug's ruling 2026-10-11, option B): no team role reads
  `CEventRegistration`, so as the user they 403'd for every non-administrator
  since they shipped. Same rule as the partner / funder Events tab.
- **Registration recognition is designed, not built** —
  `prds/events/CBM_Events_Registration_Recognition_Plan.md` (Doug's rulings
  2026-08-17): recognise a returning registrant by a signed device token, else
  by an email-first lookup that **registers them and echoes nothing** (a public
  page that returns what we know is a harvester), else the normal form; a
  signed-in member is recognised through a **redirect handoff**, never by
  loosening the staff session cookie. CBM sends its own confirmation email.
  Prerequisite and live defect: the near-duplicate hold holds a person's *second
  webinar of the day* (`OPEN-ITEMS.md` 19f).
- **Phase 6d** `scripts/import_youtube_events.py` — playlist backfill, dry-run by
  default, importing **unpublished** because an upload date is not an event date.
  Never run against the real playlist.

- **⚠️ `CEvent` doubles as CBM's org calendar** — most rows are internal team
  meetings and mentoring-session mirrors. That is true **on crm-test (94 rows)**;
  **prod's `CEvent` is empty** because it was never connected to Google
  (verified 2026-08-08), so the first published event there will be a real one.
  Workshops share the entity. **Since v0.233.0 visibility is ONE rule in
  `events/visibility.py`** (F2 + F3, Doug's rulings 09-27/29-26): the tick
  (`publishToWebsite`, labelled **"Show this event"**, default false) decides
  *whether* — unticked is on no page; **`audience`** (Internal / Public)
  decides *where* — Internal is the portal calendar only; **`eventReleaseDate`**
  (reused as the display time) decides *when*, on every page. **An empty
  audience carries over from the tick** (ticked → Public), which is how old rows
  and a CRM without the field behave exactly as before. Every public read goes
  through `_public_where` AND re-checks each row with `visibility.is_shown`; the
  registration form uses the same rule; a guard test fails on any other read of
  the tick. A failed metadata read **fails closed** (502) — guessing "no audience
  field" would publish Internal events. The team limit (`internalTeams`) is a
  **display filter, not confidentiality** — every role reads all events in the
  CRM (ruling D4). Never hand-roll a public CEvent query
  ([[events-publish-gate]]). Design:
  `prds/events/CBM_Events_Audience_and_Display_Design.md`.
- **Zoom here is the explicit exception** to the mentor-sessions "user-supplied
  links only" ruling: the public webinar programme uses the CBM Zoom account via
  Server-to-Server OAuth (host `zweb@cbmentors.org`). Ask which world you're in
  before applying either ruling ([[zoom-user-supplied-only]]).
- **Vocabulary trap**: in the public payload `topic` means the event **TITLE**
  (Zoom/Apps-Script vocabulary); the category rides as `category`. Aligning the
  names would blank every title on the live site.
- **The live page restricts images** — it sends `content-security-policy:
  img-src 'self' data: https://drive.google.com https://*.googleusercontent.com`
  (measured 2026-09-11). Anything rendered INSIDE that page would have needed
  every event graphic and YouTube thumbnail proxied through the WordPress
  domain; hotlinked `i.ytimg.com` thumbnails also returned 503 there. Serving
  our own page sidesteps both, because our document carries no such policy —
  one of the reasons the plugin was struck.
- **`wp-plugin/cbm-events/` holds the two files the public pages run**: the
  renderer (`cbm-events.js`) and the site's **own stylesheet** (`cbm-events.css`,
  copied verbatim from the live page's Elementor widgets — keep it in sync, do
  not restyle it). The directory name is now historical; the plugin was struck,
  but these two files are how our pages look like the website, so they stay
  where they are. `/webinars/` and `/events/preview.html` both load them from
  this shipping location, which is what makes either a real check. **Neither
  `events/frontend/preview.css` nor `events/public_frontend/public.css` may
  style a contract class** — an approximation in one hid a live class-name drift
  for three weeks. Guard tests assert every class the renderer emits has a rule
  in the stylesheet, and that neither of our own sheets styles one. Both guards
  strip CSS comments first, since a comment naming a class is the opposite of
  styling it.
- **A per-event link comes from `CBMEvents.config.eventUrlBase`**, which the
  public programme page sets to `/webinars/`. The payload's `url` is now this
  app's own address for the event (derived from `APP_BASE_URL`), so it is
  usable rather than a 404 — but the renderer still takes the base from config,
  because a host serving these panels somewhere else needs its own. **Sign-up
  stays a modal on the calendar** (Doug, 2026-08-16); the event page is for
  reading, and carries its own form rather than the modal.

## Cross-cutting subsystems

### Email

Umbrella reference: **`email-management.md`**. Deep dives:
`communications-tab.md`, `submission-email-flow.md`.

- **Sync** (`comms/`, worker, `GMAIL_SYNC`): per-mailbox Gmail clients under the
  service-account + domain-wide-delegation stack, historyId cursors with
  expired-cursor and new-address backfills, RFC Message-ID dedup across
  co-mentor mailboxes, and upsert into `CConversation`/`CCommunication` with
  parent/contact links. **The scopes (who handles which records) are cached
  across passes** (`comms/scopes.py`, v0.247.0): each pass asks the CRM only
  whether any of the five watched entities changed since the last build, and
  rebuilds every `COMMS_SCOPE_REBUILD_SECONDS` (3600) regardless. Doug's
  ruling (option A, 10-09-26): linking an already-known contact to an existing
  record is not seen until the hourly rebuild, and a message skipped meanwhile
  is not captured for that record — set the interval to 0 if that ever bites. A failed message ingest **holds the cursor** (the replay
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
  `comm_attachment` retry ledger. A managed **never-file list**
  (`COMMS_ATTACHMENT_EXCLUDED_TYPES`, editable at `/setup`) drops mail plumbing
  before filing — calendar invites, S/MIME blobs, `winmail.dat`. The dedup
  cannot handle invites on its own: a reschedule, a cancellation and every
  acceptance are all different bytes. It is applied at the FILING step, never
  in `is_attachment` — an excluded part is still a real attachment and stays in
  View original. Emptying the setting is the rollback. Documents filed before
  the list existed are archived by `/setup` → Operations → *Clean up excluded
  email attachments* (`scripts/cleanup_excluded_attachments.py`). **View original** renders the sanitized
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
  (`firstname.lastname@` the `MENTOR_EMAIL_DOMAIN` setting, default
  `cbmentors.org`) **without creating a Workspace mailbox**
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
3. A **nightly reconciliation** in the worker — which since v0.250.0 also
   puts every partner / funder record, its company and its contacts into
   the **domain team** (`run_team_reconciliation`, Doug's ruling 2026-10-11:
   the Sponsor Manager Role reads at *team*, so an un-teamed record is
   invisible to its own managers; merge-only, re-heals the sandbox after
   each reset, `teamRecords` / `teamHealed` on the summary line).
4. **Heal-on-access** in `/mentorprofile` for the mentor's own Contact.

Provisioning now stamps the Contact at source, which closed the largest inflow.

### Action history

Every mutating staff action is recorded via **`core/action_log.py`** — see
Conventions. Plan: `prds/action-history-plan.md`;
[[action-log-history-build]].

## Gotchas / things learned

**EspoCRM behaviour**

- **A metadata key the CRM does not have answers HTTP 200 with an EMPTY body**
  (verified on crm-test 2026-10-01). `resp.json()` on it raises a
  `JSONDecodeError`, which no `except EspoError` catches — that is how Event
  Administration 500'd on production for every F2/F3 field its CRM lacked
  (v0.235.1). `EspoClient.metadata` / `metadata_enum_options` now read an empty
  or non-JSON body as None; any new metadata read must go through them, and a
  feature-detected field's OPTIONS read must tolerate the field being absent.
- **A SCALAR metadata key comes back as a bare unquoted string** (verified on
  crm-test 2026-10-11: `Metadata?key=entityDefs.CSponsorProfile.fields.description.type`
  → 200, body `wysiwyg`, no quotes). That is not JSON, so `EspoClient.metadata`
  reads it as None, exactly like a missing key — which is how the converted
  Funder Notes field still opened the plain box (v0.252.1). Read the
  enclosing dict (`…fields.description`) and index it; never a `.type` /
  `.entity` / `.foreign` key on its own.
- **A Read-only field drops EVERY API write** — the Entity Manager Read-only
  checkbox becomes a global ACL restriction (`Acl/GlobalRestriction`) for
  every user, administrators and the org-wide API key included; HTTP 200,
  nothing stored. Never build a field the application writes as Read-only;
  keep staff off it with a field rule on their roles instead (ruling 40,
  v0.264.1 — eight campaign fields had never stored since Phase 1).
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
- **EspoCRM renames what you type, by three DIFFERENT rules** (all read from
  source on crm-test 2026-08-23; `customPrefixDisabled` is `false`). An
  **entity** name is *always* given a leading `C` — type `Grant`, get `CGrant`;
  type `CGrant`, get **`CCGrant`**, which is exactly what a handoff saying
  "Name: `CGrant`" produced. A **field** name is prefixed only when its entity
  is NOT custom, so fields on `C*` entities are stored exactly as typed. A
  **link** name is prefixed per side — `link` when *this* entity isn't custom,
  `linkForeign` when the *foreign* entity isn't custom **or when there is no
  foreign entity at all** (which is the Children-to-Parent case). Verify names
  in `GET /Metadata` after building, never by reading the UI label — the label
  said "CGrant" while the entity was `CCGrant`
  ([[espo-custom-prefix-rules]]).
- **The API has no inversion — prefer it to the dialog.**
  `EntityManager/action/createLink` takes `entity`/`link` and
  `entityForeign`/`linkForeign` with `link` stored on `entity`, full stop.
  `scripts/migrate_grant_schema.py` and `scripts/migrate_event_schema.py` are
  the worked examples (idempotent, dry-run by default); the grant one also reads
  every link back to prove it landed on the intended side.
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
- **`Contact.title` is one of those mirrors, and it is not stored at all**
  (`notStorable`, selected from `accountContactPrimary.role` — read on
  crm-test 2026-10-08): a Contact with no Company has no title, and a title
  sent on create or update is silently discarded, HTTP 200. Keep a person's
  job title on the record that needs it (the presenter entry does), never on
  a Company-less Contact.
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
- **A 403 and a 404 from the CRM mean OPPOSITE things to the person reading the
  message** — and a best-effort mirror that lumps them together cries wolf. A
  403/5xx means the write was refused, so the app and the CRM may now disagree:
  worth alarming about, and worth retrying. A **404 means the record is gone**
  (deleted, or soft-deleted so an ordinary user cannot see it): there is nothing
  left to keep in step and no retry can ever help, so it is a fact to state on a
  successful action, not a warning. `core.espo.is_not_found` is the sibling of
  `is_forbidden`; `ops.router._writethrough_request_status` is the worked
  example, returning `(updated, warning, note)` so the two land in different
  colours. **Every other best-effort mirror onto a CRM record still has this
  case buried in its `except EspoError`** — check before adding another.
  A stale id is deliberately NOT rewritten when this happens: it is the audit
  trail of what the delivery created, so the note recurs by design.
- **A CRM text value does not read back byte-for-byte** — an empty string
  reads back as null; line endings and trailing whitespace are normalised. A
  "converge if different" comparison with a bare `!=` therefore never
  converges: the hourly receipt sweep rewrote 206 of 211 production receipts
  every hour until v0.248.0 (`core/receipts._same`). Compare text as a reader
  would, and make a reconciliation loop REPORT what it found differing
  (the sweep's summary line names the keys), so a loop that never converges
  names itself.
- **The browser's failures are in the web log too** (v0.260.0): search the
  DigitalOcean runtime log for **`client-error`**. `busy.js` reports a
  request that got no answer ("Failed to fetch"), a timeout, a 5xx and a
  script error to `POST /api/client-errors`; a report delayed by the broken
  connection carries `queued=Ns`. A 5xx timing line is WARNING and a crash
  ERROR. Start any "it didn't save" report there.
- **Every API request logs what it cost** (v0.248.0):
  `timing GET /…/api/… 200 812ms crm=9/640ms` in the web log, plus a
  `Server-Timing` header. Start a slowness report there — the CRM-call count
  and their time is usually the whole story. `REQUEST_TIMING_LOG_MS` raises
  the bar.
- **Implausible phone numbers are dropped, not fatal** — `e164_or_none` returns
  None for <10 or >15 digits, and the Contact create omits the field rather than
  losing the lead. `create_dropping_invalid` handles a CRM-side `valid`/`pattern`
  rejection the same way. The raw value survives in the audit log.
- **Non-required fields must never block a save** over enum drift — schemas use
  free strings, the sanitizer is the gate, and validation errors return readable
  messages ([[non-required-enums-never-block]]).
- **HTML never answers `304` through the DO edge** — it strips the `ETag` from
  HTML responses (assets served from disk keep theirs) and does not act on
  `If-Modified-Since` for anything. Measured on prod 2026-08-20: an asset 304s
  by ETag and 200s by date; HTML 200s both ways, because it has no ETag left to
  send. **At the origin all four combinations 304 correctly**, so a local test
  proves nothing about this. The `_revalidate_frontend` middleware's docstring
  ("StaticFiles answers with a cheap 304") is true locally and not true in
  production. Do not read a missing HTML `ETag` as a regression — it is the
  edge, it predates the branding rewrite, and it cost a wrong diagnosis and a
  corrected changelog entry once already ([[do-edge-strips-html-etag]]).
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

**"Keep the two in sync" is checked now, rather than remembered.**
`scripts/publish_docs.py` compares every published twin against its repo
original and exits non-zero on drift, so it doubles as a CI check; `--publish`
pushes one. The `PUBLISHED` tuple in that script is the registry and credentials
come from `.env`, never an app env var — the application does not publish docs.
**That site is readable without signing in**, so a publish is refused if the
text still carries a live `@cbmentors.org` address or a credential, and the
repo-only `> Published to the docs site` header is stripped from the twin. Two
entries are `check_only` because their live copy differs on purpose
(`data-model.md`'s PNGs, the Email Guide's rewording): drift is reported,
publishing refused.

| Doc | What it covers |
|---|---|
| `README.md` | Repo overview; how to run locally / add a form |
| `DEPLOYMENT.md` | Engineer deploy runbook, env vars, reliability ops, backups |
| `STAFF-DEPLOYMENT-GUIDE.md` | Console-only companion for CBM staff |
| `SYSTEM-ADMIN-TROUBLESHOOTING.md` | **Verify + troubleshoot the whole platform without an engineer** — health check, weekly sweep, symptom index, the safe-remediation toolkit and its off-limits list. Audience: EspoCRM Admin + DO console, no CLI |
| `SYSTEM-SETTINGS-SETUP.md` | `/setup` activation + use: the override model, the denylist, temporary and scoped changes, the environment diff, the ops jobs, break-glass |
| `intake-processing-overview.md` | Plain-language capture → worker → CRM pipeline, per-form records, where each intake kind gets worked |
| `data-model.md` | **ERD reference** — the CRM entity model, the 18 Postgres tables, the soft key that joins them, and the cardinality rulings. **Published to the docs site** as *Data Model → How the data is structured* — keep the two in sync |
| `mentor-administration.md` | `/mentoradmin` functionality + the completeness rules |
| `mentor-directory.md` | Mentors directory + the read-only mentor profile page |
| `training-guide.md` | **Delivering a training session**: who to sign in as, the per-audience walkthroughs, what to tell the room, and how the overnight reset behaves. **Published to the docs site** as *Training Sandbox → Running a training session* — keep the two in sync, and note the published copy omits the sign-in usernames because that site is public |
| `demo-records.md` | The data reference behind that guide — which record to open for each user type, and what is on each of its tabs |
| `SANDBOX-RESET.md` | The training sandbox: the nightly restore, containment, capturing and re-baselining |
| `address-paste.md` | Staff guide to pasting a whole address into one box |
| `chapter-colours.md` | **Changing a chapter's colours**: the colour file, entering its address at `/setup`, where each of the four colours appears and what stays fixed, the check, the undo. Companion to deployment guide step 6.5 |
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
collaboration, workspace directories, transcription-vendor options, **grant
management**, **the rating engine** and **the mailing list and event
sponsorship arc** — Constant Contact as a mirror of the CRM, partner
many-to-many, the deferred in-app designer) — each records
the decisions and Doug's rulings behind that arc, so read the relevant one before
reworking a feature. The chapter network is
**not** one of those plans any more — it is its own project directory,
**`prds/chapter-network/`**, worked separately from the app's feature arcs; start
at its `README.md`. **Prospect marketing and Campaign Management are a directory
too** (consolidated 10-14-26 after three sessions in one day left three
documents that disagreed): **`prds/prospect-marketing/`** — start at its
`README.md`; `rulings.md` holds rulings 1–37 and CM-1 to CM-11 and is the
binding record (append only); `build-plan.md` v0.5 is the one plan; its two
CRM handoffs (`contact-sms-opt-in-crm-handoff.md`,
`coutreach-entities-crm-handoff.md`) are complete on crm-test (10-15-26) and
owed on production and Boston; **Phases 1 and 2 are built** (v0.258.0,
v0.259.0, dark — the Campaign Management section above); Phase 1's live
pass ran 10-15/17-26, Phase 2's is `OPEN-ITEMS.md` #51.
**One session on that arc at a time.** Eight settled rulings, a phase file each for phases 0–6, a
decision log, and its own task list. Phase 0 (de-Cleveland) is **built**; **Phase
1, CRM configuration as a versioned build artifact, is the next one and the only
genuinely new engineering in the plan** — its conformance check is built, its
applier is not. `prompts/` holds the kickoff prompts, design mockups and
review documents those arcs were built from (including
`reliability-review-2026-07-17.md` at the repo root, whose six hardening phases
are all implemented).

**How to apply any of them**, step by step — author the handoff, crm-test first,
rebuild, verify the shape AND the grants (twice: as the org-wide API key and as a
real non-admin), soak, then production at the Sunday 17:00 UTC slot:
`prds/chapter-network/crm-update-runbook.md`. Its § 7 is the twelve traps this
project has actually been bitten by.

**CRM build handoffs** (one file per pending or completed CRM change, written in
Entity Manager vocabulary — [[crm-specs-use-entity-manager-terms]]):
**`GRANT-CRM-FIX-RUNBOOK.md`** (the ordered do-this-next list for the grant
build on crm-test), `cengagement-description-wysiwyg-crm-handoff.md` (converts
the Notes column's field to wysiwyg — the switch that turns rich notes on),
`cgrant-entities-crm-handoff.md`,
`crating-entity-crm-handoff.md`,
`cevent-audience-display-crm-handoff.md` (event audience + display time —
crm-test done, production and Boston owed),
`cevent-partner-sponsorship-crm-handoff.md` (many partners per event +
the notice-campaign id — written, nothing applied), `cnetworkstandard-entity-crm-handoff.md` (the chapter network's config-version
stamp — pending on both CRMs), `contact-sms-opt-in-crm-handoff.md` and
`coutreach-entities-crm-handoff.md` (prospect marketing Phase 1 — written
10-14-26, dry-run on crm-test, nothing applied), `cintake-submission-*.md` (incl. `cintake-submission-company-status.md`, the
`Held-Company` option — pending on both CRMs), `cinformation-request-entity.md`,
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
  **Images**: the Insert-image button appears only when the host passes an
  `uploadImage` hook (dataUri → attachment URL), and pasted/dropped/picked
  images all funnel through one pipeline (`core/inline_images.py` server-side:
  Inline Attachment + `?entryPoint=attachment&amp;id=X`, display via an app
  proxy, saves rewritten back to the stored form). **Only a live-wysiwyg CRM
  field may take one** — the Wysiwyg saver's binding is what keeps the
  attachment from cleanup. Two editors refuse images BY RULING: `aboutMentor`
  (public website) and the email signature (email recipients) — their
  audiences can't reach the proxy. The signature's sanctioned alternative is
  the **Insert-logo button** (`opts.logo`), which places the publicly-hosted
  `ORGANIZATION_LOGO_URL` image (per-chapter, `/setup` → Presentation); with
  the setting empty the button stays visible and explains itself.
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
- **No page may hardcode the organisation's name.** Every `<title>`, footer and
  piece of body prose uses the `{{org}}` token, substituted server-side as the
  page is served (`core/branding.py`; setting `ORGANIZATION_NAME`, default
  Cleveland). A new page also needs `<meta name="cbm-org" content="{{org}}" />`
  in its head — that is how page scripts read the name synchronously, with no
  fetch and no race. `tests/test_shared_branding.py` fails on a hardcoded name
  AND on a page that omits it. **`CBM`/`cbm-`/`--cbm-*`/`data-cbm-*` are
  IDENTIFIERS, not content** — never renamed; two are live contracts with the
  website. Chapter theming is `CHAPTER_TOKENS_URL`, a stylesheet loaded after
  `/shared/tokens.css` that may redefine `--cbm-*` on `:root` and nothing else.
  Inventory and rulings: `prds/chapter-network/phase-0-decleveland.md`.
  The rewrite covers `.js` too (`vendor/` excluded, token-free files untouched),
  which is how `legal-links.js` gets the four `POLICY_*_URL` settings — the
  policy documents the public consent checkbox links to. **The acronym is a
  token too** (v0.232.0, Doug's ruling 2026-09-25): `{{abbr}}` in pages and
  scripts, `branding.abbr()` in server-side messages, `branding.render_text()`
  for labels built at import time; setting `ORGANIZATION_ABBREVIATION`, default
  `CBM`. Never type the word CBM in served text — the guard fails on it. CRM
  list values (`options.js`) and the CRM's own field labels are data, not UI
  strings, and stay until the CRM standard rules on them (TASKS G1 item 26).
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

**Released v0.231.1 on 2026-09-23** — cut with `scripts/cut_release.sh`, pushed
with `main`; **Lakeside took it off the release lane by itself** (its
`/healthz` read `v0.231.1` about a minute after the push, verified), the first
unattended update of a chapter deployment. `deploy_on_push` is still on for
Cleveland by design. What is *verified* is narrower than what is deployed — see
each block.

- **v0.267.0 (2026-10-20) — the Leads and Review grids at volume.**
  Committed, not pushed. Rulings 55 and 56 recorded first (social media one
  kind; the lead screens stay in the tile). Verified by tests (17 new) and
  a stubbed browser preview; the live pass on crm-test with 3,000
  throwaway leads is owed (`OPEN-ITEMS.md` #51).

- **v0.266.0 (2026-10-20) — Campaign Management demo data on the
  sandbox.** `scripts/sandbox/seed_outreach_data.py` (the fourth seeder,
  run as the CRM administrator) and `campaigns/sandbox_demo.py`, which puts
  the six fixed demo links back after every nightly reset (Doug's ruling
  10-20-26) — `/setup` → Operations → *Sandbox demo campaign links* does it
  on demand. **Deployed and baselined on crm-test 10-20-26** (Doug ran the
  re-baseline); the worker's first nightly restore ran 05:00 UTC the same
  night, `sandbox demo links: 6 created`, and the codes answer 302. Done. Record list:
  `demo-records.md`.

- **v0.265.0–v0.265.3 (2026-10-19) — the lead model.** Live on crm-test
  and production, dark on production (its CRM lacks the lead fields until
  its Sunday slot). Rulings 51–54. **Live-passed on crm-test 10-19-26
  23:44**; the pass found the lead's missing notes, a marketing user unable to
  name *Who calls* (Team read — the teams write now escalates that one
  refusal to the admin), and the call screen hiding the lead's email (now
  prefilled, with Cancel). Owed: production's slot and Boston
  (`OPEN-ITEMS.md` #51).

- **v0.258.6 (2026-10-15) — attendee linking escalates a foreign-record 403
  to the admin.** A mentor recording an attendee assigned to someone else
  saw "1 attendee change(s) could not be applied" (Greg Malkin, prod
  2026-10-15, the Betsy Nero intake session). `_sync_attendees` and the
  create-path relate loop now route through `_link_or_escalate`, the same
  foreign-record escalation co-mentor linking uses; standing rule in the
  Session Management section. Pushed the same day on origin and carried into
  current `main` by the later releases. No CRM change, no flag; rollback is
  a revert. Verified by tests only — the live pass is `OPEN-ITEMS.md` #53
  (a real non-admin mentor attaching an attendee assigned to someone else).

- **v0.257.0 (2026-10-14) — a quick-add picking a company from the other
  application inherits its primary contact.** Pushed with another session's commits
  the same evening; both deployments report it and serve the notice by
  22:06. Doug's request the same day; standing rule in the Session
  Management section. No CRM change. Verified by tests only — the live
  pass is `OPEN-ITEMS.md` #52.

- **v0.256.2 (2026-10-12) — the popup's Cancel/Save pair no longer shows
  in view mode; the referring-partner band renders on every engagement.**
  Pushed 18:54, live on crm-test and production 18:56; **verified in the
  browser by computed style** on crm-test: view mode shows Edit only, edit
  mode shows Cancel/Save, Cancel returns to view, the band reads "none
  recorded". v0.256.3 (pushed 21:02, live on both 21:05) gates the edit
  form's own display the same way — the live check found it still flex
  when hidden. **Verified in the browser 21:08** on crm-test at v0.256.3
  by computed style and screenshot: view mode shows Edit alone with the
  form and the Cancel/Save pair at display none, edit mode swaps them,
  Cancel returns to view, Internal Notes render formatted. Closed; the
  only open item from the day is `OPEN-ITEMS.md` #50. Doug's screenshot settled the Cancel report: a bare
  `display: flex` beat the `hidden` attribute since v0.210.0, and the
  v0.256.1 reproduction read the attribute, not the rendered state.
  Guarded by `tests/test_assignments_frontend_guards.py`.

- **v0.256.1 (2026-10-12) — the popup's Internal Notes render rich on a
  rich field; the discard dialog says Keep editing / Discard changes.**
  Pushed 18:15 with v0.256.0, live on crm-test and production 18:18 (the
  served script carries both). Doug's two reports the same evening; the Cancel
  one was NOT reproduced — the check read the `hidden` attribute, and the
  real fault (v0.256.2) was the buttons rendering through it.

- **v0.256.0 (2026-10-12) — the referring partner named prominently in
  the Client Administration popup.** Pushed 18:15, live on both 18:18. Doug's request
  the same evening; standing rule in the Client Administration section.
  No CRM change, no flag. Verified by tests only; the live check is part of
  `OPEN-ITEMS.md` #50.

- **v0.255.0 (2026-10-12) — a partner's own client intake link.**
  Pushed 17:40, live on crm-test and production 17:42 (both served scripts
  carry the new code; the lookup 404s an unknown id on both). Doug's requirement the same afternoon, discussed
  first; link form ruled the CRM id. No CRM change, no flag; rollback is a
  revert. Standing rules in the five-forms and Session Management
  sections. Verified by tests only — the live pass is `OPEN-ITEMS.md` #50.

- **v0.254.0 (2026-10-12) — the quick-add's Company is a picker.**
  Pushed 14:46, live on crm-test and production 14:49 (the served script
  carries the picker). Doug's question the same afternoon; standing rule
  in the Session Management section. No CRM change. **Live pass matched
  the same afternoon** (`OPEN-ITEMS.md` #49, Doug as sally.sponsor).

- **v0.253.0 (2026-10-12) — "Make primary" on a partner's or funder's
  CBM contacts.** Pushed 10-12-26 14:25, live on crm-test and production
  14:28 (the served script carries the button). Doug's request the same day, after
  additional managers went live on production; his ruling: the former
  manager is kept as an additional manager (option 1). No CRM change;
  standing rule in the Session Management section. **Live pass matched
  the same afternoon** (`OPEN-ITEMS.md` #48, Doug as sally.sponsor).

- **v0.252.0–v0.252.2 (2026-10-11) — rich Funder Notes, live-typed; the
  sign-in Show button out of the tab order.** Live on crm-test and
  production; both CRMs' notes fields converted and the passes matched
  (`OPEN-ITEMS.md` #47). **Boston's conversion ran 10-11-26 21:06** (found
  10-14-26 by a read-only probe; the item had not recorded it) — owed there
  is only the release, which brings the Overview editor that follows the
  live type. Standing rules: the Overview notes editor follows the
  field's live type (Session Management section); never read a scalar
  metadata key (Gotchas).

- **v0.251.0 (2026-10-11) — additional managers on partner and funder
  records.** Live on crm-test and production, both CRMs' links applied by
  Doug and the non-admin passes matched (`OPEN-ITEMS.md` #46). Standing rule
  in the Session Management section. **Owed: Boston's two links** with its
  next release (`scripts/plans/additional-managers.json`, fingerprint
  `f2d6a41ea16c`) — **prepared 10-14-26**: both links read absent on
  Boston, the dry run matched, and the apply is one line from this
  computer, `scripts/apply_plan.sh boston <plan> <fingerprint>` (the
  chapter-aware wrapper around `scripts/apply_crm_plan.py`; Boston's image
  predates the applier shipping in it), awaiting Doug's go on the step
  page in `OPEN-ITEMS.md` #46 (still awaiting it 10-18-26 22:50; page
  rev 2.0, kickoff `prompts/boston-release-session-2026-10-18.md`) — and
  **a role ruling**: a Mentor-Role-only user named
  additional manager on a FUNDER sees it in neither Funder Management nor
  My Email, because that role reads no `CSponsorProfile` (the mail sync is
  unaffected — its scope runs under the org key).

- **v0.264.3 / v0.264.4 (2026-10-18/19) — the events production test is
  complete.** Doug's ruling 10-09-26: the website redirect waits a few weeks;
  events is tested end to end on production first with the website's own
  sessions as real records. Done 10-18/19-26 from one runbook
  (`OPEN-ITEMS.md` #42): Track F F1 and F4 applied on production (CRM,
  grants, switch, a real non-admin pass), three duration choices added
  (`scripts/plans/cevent-duration-options.json`; v0.264.3 makes the applier
  take integer options and the editor read Duration from the CRM), the
  library's two missing recordings imported, the website's seven sessions
  and six presenter cards entered, three registrations driven through the
  public door and cleaned up. v0.264.4: a registered sign-up form locks on
  both doors. **Owed before the redirect:** the confirmation email (Track D
  D3 — both doors say "Check your email" and nothing is sent), a ruling on
  writing a ticked consent over an existing `false`, the Zoom question for
  webinar registrations, Submission Admin search by name, and Doug's
  decision on the five-week series as one event or five. Standing facts
  learned: a known email never makes a second contact (a test registrant
  with Doug's address became Doug); a receipt removed in the CRM is put back
  by the hourly sweep; the Submission Admin search matches email and status,
  not a name.

- **v0.248.0 (2026-10-09) — the receipt sweep converges; a timing line per
  API request.** Pushed 10-09-26 22:29. The last two review items; standing
  rules in the Gotchas (*This application*). **The receipt fix is inferred**:
  the live check is the first production sweep's summary line after deploy —
  `updated` should be near 0, and `differing keys:` names whatever still
  is. The timing line is the new starting point for any slowness report.

- **v0.247.0 (2026-10-09) — the Gmail sync rebuilds its scopes only when the
  CRM changed.** Pushed 10-09-26 with v0.246.0. Third review item, Doug's option A;
  standing rule in the Email section above. Verified by tests plus a
  read-only probe that the modified-after filter counts on crm-test. The
  live check is the production worker log: "scopes reused" at debug, one
  "scopes rebuilt (…)" an hour, and the CRM call count per pass falling
  from ~400 to single figures.

- **v0.246.0 (2026-10-09) — CRM metadata is cached for a minute.** Pushed
  10-09-26. Second review item; standing rule in the `espo.py` line above.
  What it changes for a live pass: **a field built in the CRM shows in the
  app within a minute, not instantly** — wait, or set the cache to 0 at
  `/setup` → Reliability for the pass. Scripts are unaffected (not armed).
  Verified by tests only; the live check is the record page's CRM-call count
  dropping on a second open within a minute.

- **v0.245.0 (2026-10-09) — every CRM call shares one connection pool.**
  Pushed 10-09-26 (production and crm-test built from it). From the performance review Doug asked for on
  10-09-26 (pages "getting a little slower"): a record page made nine
  sequential CRM calls, each on a fresh TLS connection. Measured against
  crm-test: eight metadata reads 1,530 ms → 940 ms. No flag; rollback is a
  revert. Verified by tests and that timing only — the live check is the
  same pages on crm-test after deploy, and the worker log still reaching
  its Gmail passes. **Still owed from the review**, in order: a short-TTL
  metadata cache; the hourly receipt sweep rewriting 206 of 211 production
  receipts every hour (`sync_row` never converges — find the key, a
  defect); the Gmail sync rebuilding every manager's scope every five
  minutes (~87 CRM calls/min on production); a request-duration log line.

- **v0.242.0 (2026-10-08/09) — an event carries several curated topics
  (Track F, F1). Pushed and live on all three apps (23:47 on 10-08); ships
  dark (feature-detected, no switch).** Doug struck the user-entered topic on 10-08 and ruled D1 (a new
  `topics` field with a one-time copy); standing rule in the Events section
  above; design `prds/events/CBM_Events_Topics_Design.md`. **crm-test's CRM
  side is done** (the field applied by the applier and read back as the org
  key; the copy script run — one event). **Live pass done 10-09-26 by Doug
  as Mark Marketing**, every step matched, verified in the web log
  (`OPEN-ITEMS.md` #41). Owed: production at a Sunday slot (plan + copy from
  the container), Boston with its release.
  Note the nightly reset empties crm-test's `topics` values (the column is
  rebuilt from files, the rows from the snapshot), so the copy is re-run
  there before a pass.

- **v0.241.0 / v0.241.1 (2026-10-08) — presenters on an event (Track F, F4).
  both pushed and live on all three apps (22:36 on 10-08); ships DARK.** Doug's eight requirements were gathered one question per
  turn on 10-07/08-26 and the design approved the same night; standing rules
  in the Events section above. **crm-test's CRM side is complete** (the plan
  applied by the applier — its first `image` field, no hand step — and the
  role script applied, both read back; the org key reads `CEventPresenter`).
  **Live pass done 2026-10-08 by Doug as real non-admins** (`OPEN-ITEMS.md`
  #39): every step matched once two defects the pass found were fixed — the
  role needed **Assignment Permission `all`** (a role that creates a record
  the app leaves unassigned needs it), and a guest's typed title was lost
  because `Contact.title` is a read-only mirror (v0.241.1). Owed: production's
  CRM change and grants at a Sunday slot, Boston with its release, and one
  design follow-up (a guest's title and company do not carry to a second
  event). Switch off everywhere but crm-test.
  **Production's step page is written** (10-08-26, linked from #39 and the
  handoff § 5) and its prerequisite is met: **v0.241.2**, which moves the
  CRM-plan applier into `scripts/` so it ships in the image (the skill's copy
  under `.claude/` was never in a container), is live on all three apps
  (23:07 on 10-08).
  **Kickoff prompt for the next Track F session:**
  `prompts/track-f-session-2026-10-08.md` (production slot, Boston, then F1).

- **v0.240.0 (2026-10-07) — an Internal event's Join URL is editable in Event
  Administration** (F5 design D3, `OPEN-ITEMS.md` #38). Pushed 10-09-26 22:29.
  `editable_when` on the field spec; the server admits the value only when the
  record as saved is Internal. Verified by tests only; the live check rides
  the next crm-test pass.

- **v0.238.0 (2026-10-07) — the public forms HOLD a submission whose company
  exists at a different web address.** Pushed and live on all three apps
  the same day (migration 0029 ran); **verified live on crm-test by Doug**
  — both decisions, partner form (`OPEN-ITEMS.md` Resolved). Standing rules
  in the five-forms and Submission Admin sections; plan
  `prds/company-website-hold-plan.md`. No flag; rollback is a revert. Owed:
  the `Held-Company` CRM option on production (#11 — crm-test has both held
  words since 2026-10-07, `crm-plans/intake-status-held-options.json`; since
  v0.238.1 a running process picks a new option up within a minute of a
  miss), and production's intake API role needs
  Team read **plus Assignment Permission = all** before its partner/sponsor
  records carry a team (#16 — crm-test proved that Team read alone turns a
  skipped stamp into a refused create).

- **v0.239.0 (2026-10-07) — partners and funders on an event; Events tab on
  the Partner and Funder records (Phase B of the mailing-list and
  event-sponsorship plan).** Pushed; crm-test and production built the same
  day. **Verified live on crm-test as real non-admins** (Doug as admin, then
  the three sandbox logins in the browser): the pickers, both relate and
  unrelate through the admin fallback, the Events tab under the org-wide key,
  and the client count after its live-found fix. Standing rules in the Events
  and Session Management sections. crm-test's CRM side is complete (the
  many-to-many link, the old host link removed by hand, `CActionLog.record`
  able to point at an event). **Owed:** Phase A and the `CActionLog` fix on
  production and Boston (until then they show Funders only, by design);
  Phases C and D of the plan.

- **v0.237.0 (2026-10-07) — quick-add refuses a same-named company at a
  different web address.** Pushed 2026-10-07 with v0.236.0; standing rule in the
  Session Management section. No flag; rollback is a revert. **Verified by
  tests only** — the live case is "+ Add partner" on crm-test for a company
  whose name exists with another website, expecting the refusal message.

- **v0.236.0 (2026-10-07) — a company the CRM already knows gains the new
  door's role.** Pushed with v0.237.0 (production reported 0.237.0 on 10-07). The four public forms now apply the
  merge-only `cCompanyType` rule the staff quick-add already had (standing
  rule in the five-forms section above). No flag; rollback is a revert.
  **Verified by tests only** — the live case is a funder's company submitting
  the partner form on crm-test and reading `cCompanyType` as `Sponsor, Partner`
  afterwards.

- **v0.235.1 (2026-10-01) — Event Administration 500'd on production.** A
  metadata key the CRM lacks answers 200 with an EMPTY body; `resp.json()` on
  it raised a `JSONDecodeError` that no `except EspoError` caught, so the
  editor's option read died on `audience`, the first F2/F3 field production's
  CRM does not have. Latent since 09-29, found by Doug 10-01. The client now
  reads an empty body as None for every caller (`core/espo._json_or_none`).
  **Standing rule:** a feature-detected field's OPTIONS read must tolerate the
  field being absent — `live_event_fields` was never the only read.

- **v0.235.0 (2026-09-30) — upcoming events on the portal home page (Track F,
  F5). Pushed; live on all three apps the same day, switch OFF everywhere.**
  Production's push-triggered build stalled at 2/13 with no build output for
  32 minutes (the 09-14 stall again); a manual `create-deployment` of the same
  commit built in three minutes. Doug's six rulings and two design decisions
  were gathered one question at a time on 09-30 and the design approved the
  same day; standing rules are in the Portal section above. **Ships dark**
  behind `PORTAL_CALENDAR`, so a push changes nothing visible. **Live pass
  done 2026-10-07** by Doug on crm-test as two real non-admin accounts — every
  step matched; one defect found and fixed (v0.239.1: a slug-less Public event
  was blamed on the public-pages switch); the phone strip verified in a stub
  harness only (`OPEN-ITEMS.md` #37 has the detail). The F2/F3 CRM change
  reached production the same day (#35), so production has the fields.
  **`PORTAL_CALENDAR` is ON in production and crm-test** (Doug switched
  production on at `/setup` 2026-10-07 22:50, after 0.239.1 deployed, and
  saw the rail). Boston: off until asked.

- **v0.234.0 / v0.234.1 (2026-09-29) — CoMentors column, and On-Hold counts
  as an active client.** Pushed and live on production and crm-test the same
  day; standing rules in the Client Administration section above. No feature
  flag — the rollback is a revert. Verified by tests and one org-wide-key read
  on crm-test; the pass as a real non-admin Client Administration user is
  `OPEN-ITEMS.md` #36.

- **v0.233.0 (2026-09-29) — event audience and display time (Track F, F2 +
  F3). Committed, not pushed.** Standing rules in the Events section above.
  The CRM fields are on **crm-test only** (applied and verified 09-29); the code
  is dark until a CRM has them, so a push changes nothing visible anywhere. New
  **`CHAPTER_KEY`** (default `cleveland`) — Boston must set `boston` at `/setup`
  before its events are saved, or Cleveland lands in Boston's reach; the settings
  generator now writes it for new chapters. The portal endpoints are F5's to put
  on screen. **Reviewed live on crm-test by Doug on 2026-09-30 as two real
  non-admin accounts** (team limit, display time, public refusal all confirmed);
  production at a Sunday slot and Boston are `OPEN-ITEMS.md` #35.

- **v0.232.0 (2026-09-25) — the chapter's acronym replaces CBM in every UI
  string.** Cut and released the same day; **Boston took it by itself** from the
  push to `release` (two minutes) and its *Chapter acronym* is set to BBM as a
  `/setup` override, verified on the public form, a served script and the
  public programme band. Cleveland's three apps run it and still say CBM (the
  default). Standing rule in Conventions; what was deliberately left is
  `prds/chapter-network/TASKS.md` G1 item 26 (CRM list values and field
  labels). Verified live on Boston only — Cleveland's pages were checked for
  *no change*, not for a configured acronym.

- **2026-09-24/25 — Boston Business Mentors, the first real chapter, has a
  live CRM and live applications.** CRM at `https://crm.bbmentors.org`
  (EspoCRM 10.0.8, DigitalOcean droplet 209.97.157.6, manual DNS at
  Squarespace); applications at `https://apps.bbmentors.org` (App Platform app
  `4fab6656-…`, release branch, latest-stable, managed Postgres, v0.232.0 with
  two `/setup` overrides: the public events page on, acronym BBM).
  The standard is applied (9.6, 9.7, 9.9); the public events page is on by a
  `/setup` override. **Owed:** stage 10 (Google — every Google switch is off),
  step 9.5 (the two paid add-ons) followed by a 9.7 re-run to fill 73
  permissions, Boston's setup contact entering the fourteen switch answers on
  the chapter information page (they were answered in `boston-values.yaml` by
  ruling), and CRMBuilder's certificate job (G1 item 21). Three traps this
  build found, all now in the guide: **CRMBuilder's self-healing certificate
  job can never succeed from cron** (the installer runs certbot with a
  terminal flag; it left the CRM off the air on both ports until recovered by
  hand — [[crmbuilder-certificate-job-needs-tty]]); **the DigitalOcean token
  must be minted by the sign-in that linked GitHub** or `apps create` 400s
  "GitHub user not authenticated" ([[do-github-link-is-per-user]]); and
  `doctl auth switch` changes this computer's default for Cleveland too, so
  every chapter doctl call names `--context` (Boston: `boston-central`).
  Preparing the build on 09-23 also found production's `APP_ENCRYPTION_KEY`
  published in a committed overlay backup (`OPEN-ITEMS.md` #33, key
  replacement owed) and that the worker reads its mail switches only at
  start-up (#34). Guide state: `prds/chapter-network/TASKS.md` G1 and
  `DECISIONS.md`.

- **v0.228.0–v0.228.2 (2026-09-13) — a chapter upgrade is one operation.**
  Doug's ruling after the nine-step Lakeside upgrade was put in front of him:
  *"This is way too difficult."* The release tag no longer rides in each
  deployment's spec. `scripts/cut_release.sh` writes it into **`release-tag.txt`**
  in the commit the tag names, and it counts **only when it matches that build's
  version** — so a deployment on the `release` branch with `deploy_on_push` on
  updates itself correctly on the push, and a Sunday release is two commands:
  cut, push. `scripts/set_updates_policy.py` sets a deployment to
  Development / Latest Stable / On Demand across all three components at once
  and drops the redundant variable; `promote.py` remains for On Demand ones.
  **Lakeside is on `latest-stable` and reports `v0.228.1` with nothing set** —
  the mechanism proven on a real chapter deployment. Two defects were found by
  *deploying*, not by testing, and both are worth remembering: the Dockerfile
  sets `RELEASE_TAG` **empty** on every image and pydantic read empty as a
  value, so the whole thing was inert in containers while 2025 tests passed
  ([[env-var-empty-vs-absent]]); and a spec update rebuilds the **same commit**,
  not the branch tip, so switching a policy on leaves the app behind
  ([[do-spec-update-rebuilds-same-commit]]). Cleveland's three apps still track
  `main` and keep their overlay variable, so they report `v0.217.0` while
  running current code — `OPEN-ITEMS.md` #29 is the decision.

**Confirm that against the remote, do not trust this line.** On 2026-08-20 it
still read "pushed through v0.202.2" while v0.203.x/v0.204.0 sat unpushed
locally, and a session that believed it pushed a docs commit and shipped a
feature to production with it. `git log origin/main..main` is the answer; this
sentence is a convenience.

- **v0.223.0 (2026-09-12) — the public page opens the way the page it replaces
  does.** The first side-by-side against the live site found four differences.
  Three are fixed: the navy hero, the gold band and the organisation's menu all
  came across, and the panel headings are the site's again. **The fourth is
  blocking and is not fixed** — the recorded library would go from full to
  empty, because the live one is the YouTube playlist and ours is CRM rows with
  a recording link, of which there are none. The backfill script exists and has
  never been run; it needs a YouTube key and the playlist id, neither of which
  is configured anywhere (`OPEN-ITEMS.md` 19i). **Committed, not pushed.**

- **v0.222.0 (2026-09-11) — the public workshops-and-webinars programme is a
  page THIS APP serves, at `/webinars/`.** Doug struck the WordPress plugin:
  the marketing site will **redirect** here rather than embed or reimplement the
  programme. The standing rules are in the Events section above; what belongs
  here is what is owed. **Committed, not yet pushed or deployed** — so nothing
  public has changed and the website still runs the Apps Script. Three defects
  were found by opening the page in a browser that 1,983 green tests missed: the
  recorded library rendered unstyled (the site's stylesheet has two wrapper
  scopes, `.cbm-wb` and `.cbm-yt`, and they are not interchangeable), the
  organisation logo rendered as a broken image (`display:block` beating the
  `hidden` **attribute**, the same trap as the page-covering overlay), and an
  event's date read "September 2026 26". All three are fixed and guarded. Still
  owed before the redirect: **19d the consent wording** — both public doors send
  `consent: false`, so a registration records no opt-in at all — and **19f the
  per-event duplicate hold**. The browser pass against **real** crm-test data
  has never run (19e); note crm-test's seeded events carry no slug, so an event
  has to be created through `/events` first.

- **v0.222.0 → v0.230.1 (2026-09-11 to 09-14) — the events programme is a page
  this app serves, and production is switched on.** The WordPress plugin was
  struck; the marketing site will **redirect** to `/webinars/` instead. Standing
  rules are in the Events section above. What belongs here is what is owed and
  what was learned.

  **Done:** the public pages with the site's own hero, band, menu and panel
  wording; consent as an active tick on both sign-up doors; the near-duplicate
  hold scoped per event; production switched on and its recorded library
  imported from five YouTube playlists and published; a topic filter on that
  library.

  **Owed, and all Doug's:** create the upcoming sessions on production, one
  end-to-end test registration (none has ever run there), decide whether the
  internal `CRM Training Webinar` should be publicly listed, and add the
  redirect.

  **Four things this arc taught, the hard way:**
  - **A version not moving is as likely to be DigitalOcean as us.** A push was
    ignored entirely on 09-13 (no deployment created at all) and a build stalled
    at 2/13 on 09-14. `doctl apps list-deployments` tells the two apart; a
    manual `create-deployment` clears the first.
  - **Confirm an overlay apply by the Spec Name in its output.** The first
    production apply silently did nothing, and the tell was that the live app
    carried no events keys while every deployment was push-triggered.
  - **The editor posts every field, not just changed ones.** An unset enum went
    as `""`, which EspoCRM refuses, so publishing an imported recording failed
    and looked like the publish flag's fault. Enums now go as `null`, and a CRM
    400 names the field instead of reading as an outage.
  - **A test that reads the developer's own `.env` passes until the day the
    value is set.** Two did (`OPEN-ITEMS.md` #31 is the survivor).

- **v0.220.0 / v0.221.0 (2026-09-01) — the mentor detail popup, and
  employment status on both mentor screens.** Both deployed and **verified
  live by Doug the same day** (OPEN-ITEMS #31 closed); standing rules live in
  the Client Administration and Mentor Administration sections above. Two
  things worth keeping here: the popup's ACL half is only as verified as the
  account Doug's pass used — a staff "fields missing in the popup" report
  starts at field-level ACL, not the renderer — and
  `mentoradmin.field_options`/`_sanitize_enum_changes` now cover
  **Contact-entity enums**, so a new Contact-backed enum field needs no new
  plumbing.


- **v0.214.0 → v0.216.1 (2026-08-28/29) — the release train's two version
  stamps, and the Settings page holds and edits every setting.** Four releases
  in one day, all live on all three apps. Standing rules are in the Deployment
  (`/healthz`) and System Settings sections above; what belongs here is what is
  still owed. (a) ~~Both stamps ship inert~~ — **switched ON 2026-08-31**:
  Doug applied both overlays and crm-test AND production now report
  `releaseTag: "v0.217.0"` and `crmConfig.state: "unstamped"` (dev deliberately
  stays `null`/`disabled` — no overlay there). (b) ~~production reads `absent`
  until its `CNetworkStandard` is built~~ — **built 2026-08-31** by
  `scripts/build_networkstandard.py` run from inside the prod web container, so
  the `absent` interlude never happened. (c) **The verified-settings live pass
  ran 2026-08-29** and found and fixed three defects (override saves 500'd;
  the page-off switch was boot-read; a non-CRM address was accepted —
  v0.216.2–v0.216.4). Still owed: the encrypted-secret check, blocked on
  crm-test having no `APP_ENCRYPTION_KEY` (`OPEN-ITEMS.md` #20).
  (d) A pre-existing leak was fixed on the way: `DATABASE_URL` had been rendered
  in the clear on the read-only "show all" list.

- **v0.212.0 — Grants on the funder record** (phase 2 of the grant arc). The
  standing model is in `prds/grant-management-plan.md`; what belongs here is the
  shape of the gate. It ships **dark twice over**: `GRANTS_ENABLED` (off,
  per-request like `record_quick_add`, so `/setup` flips it) **and** live CRM
  feature detection — **the three entities do not exist in either CRM yet**, so
  `grants_available()` probes for them and **fails closed**, and every field is
  filtered against live metadata before it is served. That matters because the
  spec IS the whitelist: an absent field drops out of the form and the write
  together. Switching the flag on before the CRM build shows an explanatory
  panel, not a broken tab. Doug is building the entities from
  `cgrant-entities-crm-handoff.md`. **Verified by tests only (36 new, suite
  green) — nothing has ever run against a real CGrant.** The rating engine that
  turns rating deliverables automatic is its own arc:
  `prds/rating-engine-plan.md` + `crating-entity-crm-handoff.md`.

- **v0.210.0 — the Client Administration engagement popup fills the window and
  can be edited.** The standing rules are in that app's section above. Two things
  worth keeping here: the 1040px cap it replaced is exactly the width cap the
  density ruling exists to prevent, and **the mentor is not one of the editable
  fields on purpose** — a plain `mentorProfileId` write would skip the re-homing,
  the stamp, the history note and the Drive grants, so the edit form hands off to
  the existing Assign/Reassign picker. **Verified in a stub harness only**, and
  the half that harness cannot rehearse is the one that has failed before: no
  test and no harness issues a real list request, which is how `maxSize=500`
  emptied every link picker in production unnoticed. `OPEN-ITEMS.md` #20 has the
  live pass.

- **v0.209.0 — Client Administration got Status and Company columns.** Both
  sortable, both out of the Engagement cell's meta line. The Company column is
  the one with a trap behind it: intake-created engagements leave
  `CEngagement.clientOrganization` **null** and carry the Account on
  `CClientProfile.linkedCompany`, so the column resolves through the client
  profile when the direct link is empty (`assignments/service._fill_company_names`,
  mirroring `sessions.service.fill_company_fallback` — duplicated because
  sessions imports FROM assignments). Best-effort: an unreadable profile renders
  "—". **Verified in a stub harness only** — the fallback read is the path most
  prod rows take and has not been watched against a live CRM.

- **v0.205.0–v0.206.0 — the product stopped saying Cleveland** (Phase 0 of the
  chapter-network plan; worth doing whatever happens with the chapters).
  **Deployed and verified live on prod.** The standing rules now live in the
  Conventions section above; the inventory, the rulings and what was
  deliberately *not* built are in
  `prds/chapter-network/phase-0-decleveland.md`.

  What is worth keeping in mind here rather than there:

  - **No feature flag, deliberately.** The safety property is that an
    unconfigured deployment renders what it always did, so **the rollback is a
    revert, not a toggle.**
  - **The one thing still owed is a browser.** Everything was verified by
    fetching served pages, which cannot show the **absence of flicker** — the
    entire reason the name is substituted server-side rather than filled by JS.
    Also unchecked: the two *authenticated* direct-read pages
    (`/mentorsessions/record/{id}`, `/directory/contacts/record/{id}`), the two
    scripts reading `<meta name="cbm-org">` (portal birthday eyebrow, directory
    mentor tab title), and changing `ORGANIZATION_NAME` at `/setup` and back.
    `OPEN-ITEMS.md` § *Live verification owed* has the list.
  - **Two diagnoses in this arc were wrong before they were right**, both from
    reading a symptom without a control: a missing HTML `ETag` in prod was
    called a shipped regression when it is the edge and always was
    ([[do-edge-strips-html-etag]]), and a test "proved" the JS escaping missing
    after stripping the backslash that was doing the escaping. Run the control
    on something the change did not touch.

- **v0.204.0 — a mentor's Google account is created at Accepted-Provisional.**
  Provisioning is two events now (see the Mentor Administration section for the
  standing rules): the Workspace account + All Members group at
  `Accepted-Provisional`, which then advances the record to `Provisional`; the CRM
  login still waits for Approved/Active. **Verified by tests only, and live on
  production since 2026-08-20 with the mailbox half unarmed** — checked that day:
  neither overlay sets `GOOGLE_DIRECTORY_CHECK`, `GOOGLE_CREATE_MAILBOX` or
  `GOOGLE_MEMBERS_GROUP`, and prod's single `/setup` override is `record_quick_add`,
  so all three sit at their defaults. `google_directory_check` off means no Directory
  client is built at all, which makes the create flag inert whatever it says and
  leaves the status advance unable to fire (it demands a *confirmed* account). So a
  prod mentor set to `Accepted-Provisional` behaves exactly as before. The live pass
  still needs three things Doug owns: the group address (still unknown, so the group
  step ships inert), the `admin.directory.group` DWD scope, and "Create missing
  mailboxes" turned on deliberately for the environment. Details and the exact live
  script: `OPEN-ITEMS.md` #22; rulings:
  `prds/mentor-provisional-provisioning-plan.md`.
- **v0.203.0 / v0.203.1 — the events website preview is the website now.** The
  site's own stylesheet (verbatim from its Elementor widgets) ships with the
  plugin and drives the preview, so the colours, type and the two-column
  layout — calendar left, library right, filling the window and stacking at
  767px — are the site's rather than an invented green approximation. Doing it exposed a defect the approximation had
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

- **v0.259.0 (2026-10-17) — prospect marketing Phase 2, the doors honour
  the ids.** Pushed 10:52, live on crm-test and production 10:54 (both
  `/healthz` read 0.259.0). Dark by nature (no id, no change; every
  write feature-detected), no switch, no CRM change; standing rules in the
  Campaign Management section above. Question 7 was put to Doug first and
  answered "A" — **ruling 34**, the information request door's company
  typed Prospect, with `scripts/relabel_info_request_companies.py` for the
  companies created under the old shape (dry-run first; Doug runs it per
  CRM once the Prospect option is there). **Live pass 10-17-26:** sections
  A–E matched on crm-test (a card through to delivery, two partners, a
  partner link plus a campaign link, ruling 27); F's registrations and G–I
  are owed on 10-18-26 — crm-test's 04:00 UTC reset removed the pass's
  records mid-F. The pass found two defects, both fixed: **v0.259.1** (the
  worker's `ResumableClient` lacked `metadata` and `list_related`, so every
  worker delivery dropped the campaign — live 22:35) and **ruling 35** (two
  CRM fields both labelled *Campaign*; ours is *Outreach Campaign* in the
  CRM, crm-test relabelled, production and Boston owed, handoff § 3.4).
  Step page https://claude.ai/artifact/JLZyupBD4i6scAogws6sWD. Doug opened
  the Phase 3 gate to build in parallel (10-18-26 00:05).

- **v0.260.2 / v0.261.0 (2026-10-18) — ruling 37, and prospect marketing
  Phase 3.** Committed, not pushed. Rulings 36 (callers are the campaign's
  teams, acting as themselves) and 37 (no rung on a record holding a
  relationship type) put to Doug first. Standing rules in the Campaign
  Management section. Verified by tests (26 new, suite green) and a stub
  harness; never against a live CRM. Doug's six-step pass:
  https://claude.ai/artifact/D8atEqEdRaRBKh4mmxiPsj (`OPEN-ITEMS.md` #51).
  Next kickoff: Phase 4. **Live-passed 10-18-26** (v0.261.1 fixed the
  Mentor Role's call write).

- **v0.262.0–v0.264.0 (2026-10-18) — prospect marketing Phase 4.**
  Committed, not pushed. Rulings 38 (texts sent by the application) and 39
  (the wording in `COutreachCampaign.smsMessage`, a CRM field owed on every
  CRM). Standing rules in the Campaign Management section. **Live-passed
  on crm-test 10-18-26 15:05** (Doug as Mark Marketing); the pass found
  ruling 40 (Read-only campaign fields dropped every write — v0.264.1,
  proven on the text campaign's stored sign-off).

- **v0.260.0 / v0.260.1 (2026-10-17/18) — the browser reports its own
  failures.** v0.260.0 pushed and live on both deployments 23:14 (served
  `busy.js` and the endpoint checked); v0.260.1 committed, not pushed.
  Standing rule in the Gotchas (*This application*). Doug ruled against a
  `/setup` screen for now — Claude reads the `client-error` lines with
  `doctl` when a failure is reported. The browser half has not yet caught a
  real failure.

- **v0.258.0–v0.258.5 (2026-10-15) — Campaign Management, prospect marketing
  Phase 1.** Pushed and live on all three apps; dark behind
  `CAMPAIGNS_ENABLED` and `CAMPAIGNS_LANDING_PUBLIC` (both ON on crm-test
  since the pass), the mail vendor the dry run. **Live pass run by Doug on
  crm-test 10-15/17-26** from https://claude.ai/artifact/XSEA7eWTx3yhXkH6Kw9oLD;
  it found five defects, fixed in .1–.5: `[hidden]` losing to `display:grid`
  (every panel at once); a prospect create carrying a Company link 403s as a
  Marketing Admin (links now the API client's second write); a partial import
  that could not resume; the Imports route shadowed; **the API role needs
  edit on `COutreachCampaign`** for the worker's run (the role script's
  seventh grant — re-run it on every CRM); a promoted company selected
  beside its own prospect record. Owed: production's CRM change at a Sunday
  slot (`coutreach-entities-crm-handoff.md` § 7: both plans, the
  `Prospect Response` receipt option, the role script, the notes
  conversion, the tab list, the three entities' layouts), Boston, a seeder
  and re-baseline.

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
