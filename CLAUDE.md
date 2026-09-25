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

**The per-application detail lives in `APPLICATIONS.md`** — every screen, field
spec, ruling and trap, moved there verbatim on 2026-09-25. What follows is the
roster plus the one constraint per application you are most likely to break.

- **Client Administration — `/assignments`** (staff-only). Assign/Reassign
  **merges, never overwrites** (`_merged_assignment_payload`) — an overwrite
  silently revokes co-mentor access.
- **Mentor Administration — `/mentoradmin`** (staff-only). Provisioning is two
  stages keyed on `mentorStatus`, and the EspoCRM User half runs as the
  dedicated **admin service account** — EspoCRM makes User creation admin-only.
- **My Mentor Profile — `/mentorprofile`** (Mentor Team). Always "me" — no record
  id from the client — and `PROFILE_FIELDS` is deliberately non-administrative,
  so smuggled status/compliance/dues changes are dropped.
- **Session Management — `/mentorsessions`, `/partnersessions`,
  `/sponsorsessions`** (Client / Partner / Funder Management). **One engine,
  three team-gated routes**: the domains differ only by a
  `sessions/config.py:DomainConfig`, so fix it once, not three times.
- **Submission Admin — `/ops`** (Marketing Admin Team). Two deliberately
  separate status axes (intake vs response), and **only ONE info@ poller may
  run** — `OPS_MAILBOX` on both environments double-captures.
- **Workspace Directories — `/directory`**. Grid columns and the detail pop-up
  are read **live from the CRM's own layouts**, so they auto-sync — nothing is
  hardcoded.
- **My Email — `/myemail`**. Scope is the `CMentorProfile` reverse links (owned
  + co-mentored, all three domains), deliberately **not** ACL-wide.
- **Analytics — `/analytics`** (`ANALYTICS_ENABLED`). **Record-scoped metrics
  always run live as the user and are never cached** — a shared per-record cache
  would leak scope.
- **System Settings — `/setup`** (EspoCRM admins only). Env is the default and
  the DB row the override; on any override failure **degrade to the overlay,
  never to the code default**.
- **Events & Webinars — `/events`**. **`publishToWebsite` (default false) is the
  entire boundary to the public site** — every public read goes through
  `events/service._public_where`; never hand-roll a public `CEvent` query.
- **The PUBLIC pages — `/webinars/` and `/webinars/{slug}`**. They are **routes,
  not static files**: each event's `<head>` is filled server-side for crawlers,
  and an unpublished event must **404**, not render empty.

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
| `APPLICATIONS.md` | Per-application detail — every staff and mentor tool, split out of this file 2026-09-25 |
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
management** and **the rating engine**) — each records
the decisions and Doug's rulings behind that arc, so read the relevant one before
reworking a feature. The chapter network is
**not** one of those plans any more — it is its own project directory,
**`prds/chapter-network/`**, worked separately from the app's feature arcs; start
at its `README.md`. Eight settled rulings, three of them replaced or amended on 2026-09-19 by the Business Mentors Association's own rulings (`dbower44022/business-mentors-association`), a phase file each for phases 0–6, a
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
`cnetworkstandard-entity-crm-handoff.md` (the chapter network's config-version
stamp — pending on both CRMs), `cintake-submission-*.md`, `cinformation-request-entity.md`,
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

- **2026-09-24/25 — Boston Business Mentors, the first real chapter, has a
  live CRM and live applications.** CRM at `https://crm.bbmentors.org`
  (EspoCRM 10.0.8, DigitalOcean droplet 209.97.157.6, manual DNS at
  Squarespace); applications at `https://apps.bbmentors.org` (App Platform app
  `4fab6656-…`, release branch, latest-stable, managed Postgres, v0.231.1).
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

*The older release blocks were removed on 2026-09-25 under this section's
own rolling-window rule — `CHANGELOG.md` is the permanent per-version
record and `OPEN-ITEMS.md` holds anything still owed.*

**The open work is all in `OPEN-ITEMS.md`** — chiefly: CRM prerequisites still
to build (items 11–19, including the three Google-side changes that gate Meet
transcripts), the live-verification backlog (item 20 — the code is deployed, the
eyeball is owed), and a CRM test-record sweep (item 21).
