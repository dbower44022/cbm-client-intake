# Deployment Runbook — cbm-client-intake

How to deploy the CBM intake app (client-intake + volunteer forms) to
**DigitalOcean App Platform**, and how to **reproduce the deployment for
production**. App Platform builds the repo's `Dockerfile` straight from GitHub
and serves it over managed HTTPS — no server to run, patch, or renew certs on.

> **Non-technical reader?** See [`STAFF-DEPLOYMENT-GUIDE.md`](STAFF-DEPLOYMENT-GUIDE.md)
> for a plain-language, web-console-only companion to this runbook.

> **New session quick-start:** read `CLAUDE.md` first (current state), then run
> `./scripts/deploy.sh`. The script is idempotent (creates the app the first
> time, updates it after). It deploys in **dry-run** (no EspoCRM writes); see
> [Going live](#going-live-write-to-espocrm) to wire EspoCRM and
> [Reproduce in production](#reproduce-the-deployment-in-production) for the
> clean from-scratch sequence.

## Decision record — why App Platform

**Chosen method: DigitalOcean App Platform** (2026-05-28, confirmed by Doug).

The app is stateless (no DB, no disk writes), low-traffic, already
containerized, and the team is standardized on DigitalOcean. App Platform is
the lowest-ops option that satisfies every hard requirement: automatic managed
HTTPS, encrypted secrets, auto-deploy from GitHub on push, one-click rollback,
and `doctl`/console log access — with 100% carryover of the existing
`Dockerfile`. The alternatives were rejected for this app: a dedicated droplet
adds OS/nginx/cert ops burden for no benefit on a tiny stateless service;
co-hosting on the production EspoCRM droplet couples a feedback app's blast
radius to the system of record; another PaaS (Render/Fly/Railway) splits infra
off DigitalOcean with no advantage over App Platform. Full comparison is in the
session that produced this runbook.

## What gets deployed

- One service from [`Dockerfile`](Dockerfile), spec in
  [`.do/app.yaml`](.do/app.yaml): `basic-xxs` instance, `http_port: 8080`,
  health check `/healthz`, `deploy_on_push: true`.
- Config is env-driven ([`core/config.py`](core/config.py)); all values default,
  and `ESPO_DRY_RUN` defaults to `true`, so the app boots with **no secrets** and
  performs **no EspoCRM writes** until you explicitly go live.

## Verified locally (reproduction baseline)

The container App Platform builds was verified locally on 2026-05-28 — this is
the baseline a fresh deploy should match:

```bash
docker build -t cbm-intake . && docker run --rm -d --name cbm-intake -p 8099:8080 cbm-intake
curl -s localhost:8099/healthz          # -> {"status":"ok","dryRun":true,"forms":["client-intake","volunteer"]}
curl -s -o /dev/null -w '%{http_code}\n' localhost:8099/client-intake/   # 200
curl -s -o /dev/null -w '%{http_code}\n' localhost:8099/volunteer/       # 200
docker rm -f cbm-intake
```

A dry-run submission to `POST /api/volunteer/intake` returns synthetic
`dryrun-*` ids and logs `volunteer ok …` with **no CRM call**; resubmitting the
same `submission_token` returns `"idempotent": true`. Test suite: `uv run
pytest -q` (17 passing).

## Prerequisites (one time)

1. A DigitalOcean account.
2. **doctl** (the DO CLI), installed and authenticated:
   - Linux: `sudo snap install doctl` (or download from the doctl releases page)
   - macOS: `brew install doctl`
   - Authenticate: `doctl auth init` — paste a Personal Access Token from
     DO → API → Tokens (needs read/write).
   - Verify: `doctl account get`.
3. **Connect GitHub to App Platform** (only needed for the very first create of
   each app): in the DO console, Apps → Create App → GitHub → authorize the
   `dbower44022/cbm-client-intake` repo. After this, `doctl` can create/update
   the app non-interactively. (If `deploy.sh` fails the first run with a GitHub
   error, this is why.)

## Deploy (dry-run, for feedback)

```bash
./scripts/deploy.sh
```

The script: validates the spec → creates the app (or updates it if one named
`cbm-client-intake` already exists) → waits for the deployment → prints the
public `…ondigitalocean.app` URL → checks `/healthz`. Expect `"dryRun": true`.

> **Safety guard:** if the existing app is already **live**
> (`ESPO_DRY_RUN=false`), `deploy.sh` refuses to update it, because applying the
> committed spec would revert it to dry-run and drop the CRM secrets (see
> [Going live](#going-live-write-to-espocrm)). Override only when you mean to:
> `ALLOW_LIVE_UPDATE=1 ./scripts/deploy.sh`.

Then sanity-check in a browser:

- `…/` — the public form index (dry-run app; with `SESSION_SECRET` set it is the staff sign-in portal instead)
- `…/client-intake/` and `…/volunteer/` — the two wizards
- Submissions are validated and **logged only** (no records created) while in
  dry-run.

`deploy_on_push: true` means every push to `main` thereafter auto-redeploys —
**and that path preserves console-set env vars** (it redeploys the app's stored
spec). It is only `doctl apps update --spec` (what `deploy.sh` runs) that
replaces the whole spec; see the safety guard above.

## Going live (write to EspoCRM)

The integration is verified against `crm-test` (see `CLAUDE.md`). To make a
**deployed** app write to EspoCRM, set these as **encrypted, app-level**
environment variables — never commit them:

| Variable | Value |
|---|---|
| `ESPO_DRY_RUN` | `false` |
| `ESPO_BASE_URL` | e.g. `https://crm-test.clevelandbusinessmentors.org` (or the prod CRM URL) |
| `ESPO_API_KEY` | the **dedicated, create-only** intake API user's key |

The API user must be scoped **create-only** on `Account`, `Contact`,
`CClientProfile`, `CEngagement`, and `CMentorProfile` (verified: it cannot
delete — DELETE returns 403).

### Staff tools + mentor-login provisioning (optional, web component)

The staff tools (`/assignments` = **Client Administration**, `/ops` =
**Submission Admin**, `/mentoradmin` = **Mentor Administration**) mount only
when `SESSION_SECRET` is set — and with it the root `/` becomes the
**authenticated portal**: staff sign in **once** with their own EspoCRM
username/password and see the links their **Teams** allow; each app enforces
its own team per request (admins always pass). The four gate teams must exist
in the CRM: `Client Administration Team`, `Mentor Administration Team`,
`Marketing Admin Team` (create it — new with v0.30.0), and `Mentor Team`
(mentors get a CRM link + the public form links on the portal). All are on the
**web** component:

| Variable | Value |
|---|---|
| `SESSION_SECRET` | random string, **`type: SECRET`** — enables the portal + staff tools + signed sessions |
| `ASSIGN_ALLOWED_TEAMS` | `Client Administration Team` (gate for `/assignments`) |
| `MENTOR_ADMIN_ALLOWED_TEAMS` | `Mentor Administration Team` (gate for `/mentoradmin`; default) |
| `OPS_ALLOWED_TEAMS` | `Marketing Admin Team` (gate for `/ops`; default) |
| `SESSION_COOKIE_SECURE` | `true` in prod (false only for plain-HTTP local dev) |

**Mentor-login provisioning** — approving a mentor in `/mentoradmin` can
auto-create their EspoCRM login. EspoCRM makes User creation **admin-only**
(API keys / `api`-type users 403, and a *regular* user with roles also 403), so
this runs as a dedicated **admin-type** EspoCRM service account via the
`App/user` token flow — never a staff token. Off unless enabled:

| Variable | Value |
|---|---|
| `MENTOR_PROVISION_USERS` | `true` to enable |
| `ESPO_PROVISION_USERNAME` | the dedicated admin account's username |
| `ESPO_PROVISION_PASSWORD` | its password, **`type: SECRET`** |
| `MENTOR_TEAM_NAME` | team the new login is added to (default `Mentor Team`) |

The service account's **Type must be Admin** in EspoCRM. Verified live against
`crm-test` 2026-06-22 **and against the production CRM 2026-06-24** (provisioned a
real mentor login end-to-end; the `sendAccessInfo` welcome email delivered to the
mentor's CBM address). (The async delivery worker — `worker.py` — does **not** need
these; provisioning runs synchronously in the web request.)

**Google Workspace mailbox check + creation (optional, web component)** — during
mentor approval the app handles the `firstname.lastname@cbmentors.org` mailbox:
**check** whether it exists, and (v0.11.0) **create** it when missing instead of
blocking — then provision the EspoCRM login once it verifies, with a live status
window. A *confirmed-missing* mailbox blocks (when creation is off) or is created
(when on); an inconclusive check (unconfigured, API/auth error) **fails open** so a
Google outage can't freeze approvals. Off unless enabled. **Preferred config path:
the in-app admin "Email Setup" screen** (`/mentoradmin`, admin-only) which stores
the creds **encrypted in Postgres** and takes precedence over the env vars below;
the env vars are the fallback.

| Variable | Value |
|---|---|
| `GOOGLE_DIRECTORY_CHECK` | `true` to enable the existence check |
| `GOOGLE_CREATE_MAILBOX` | `true` to CREATE a missing mailbox (needs the read-write scope) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the service-account JSON key, **`type: SECRET`** |
| `GOOGLE_DELEGATED_ADMIN` | a Workspace admin to impersonate, **`type: SECRET`** |
| `APP_ENCRYPTION_KEY` | Fernet key encrypting the Email-Setup creds in Postgres, **`type: SECRET`**, web **+ worker** |

**Google Calendar events for sessions (optional, web component, v0.40.0)** —
`GCAL_EVENTS=true` makes a saved **Scheduled** session create/patch/cancel a
Google Calendar event (with a Meet link written to `videoMeetingLink`) on the
manager's own calendar, inviting the attendees. Reuses
`GOOGLE_SERVICE_ACCOUNT_JSON` (or the Email-Setup config) — no new secret.
Activation order (the app is inert until ALL are done): enable the **Google
Calendar API** in the GCP project; add
`https://www.googleapis.com/auth/calendar.events` to the service account's
existing domain-wide-delegation row (see `GMAIL-INTEGRATION-GUIDE.md`); build
`CSession.googleCalendarEventId` in the CRM (`csession-calendar-field.md` —
feature-detected, crm-test first); **disable EspoCRM's own Google Calendar
sync on crm-test** (double events otherwise; prod never had it); then set the
flag. Worker not involved.

| Variable | Value |
|---|---|
| `GCAL_EVENTS` | `true` to enable session calendar events + Meet links (web) |

**Meeting transcripts — Google Meet (optional, web + worker, v0.83.0)** —
`MEET_TRANSCRIPTS=true` makes every app-scheduled Meet get **automatic
transcription** (enabled on the Meet space at schedule time, as the
organizer), and the **worker** periodically retrieves finished transcripts
into `CSession.sessionTranscription` (lights up the session view's Transcript
zone) plus the permanent Google Doc link into `CSession.transcriptDocUrl`.
Reuses `GOOGLE_SERVICE_ACCOUNT_JSON` (or the Email-Setup config) — no new
secret. Activation order (the app is inert until ALL are done; plan:
`prds/meet-transcript-integration.md`): **confirm Workspace licensing**
(Meet transcripts need Business Standard+ for the meeting organizer — the
free Nonprofits tier lacks them) and the Meet transcription admin toggle;
enable the **Google Meet REST API** in the GCP project; add
`https://www.googleapis.com/auth/meetings.space.created` to the service
account's existing domain-wide-delegation row (edit the line — the field
REPLACES, keep all current scopes); build the two CRM fields + the API-role
CSession read/edit grant (`csession-transcript-fields.md` — feature-detected,
crm-test first); then set the flag on **web AND worker**.

| Variable | Value |
|---|---|
| `MEET_TRANSCRIPTS` | `true` to enable Meet auto-transcription + retrieval (web + worker) |
| `MEET_TRANSCRIPTS_POLL_SECONDS` | worker retrieval cadence (default 1800) |
| `TRANSCRIPT_GIVE_UP_DAYS` | stop looking this many days after a session's start (default 14) |

**Google Drive documents (optional, web component, v0.65.0–v0.70.0 — DOC-MGMT
Phases 1+2, PRD v1.2)** — `GDRIVE_DOCS=true` turns the session tools' Documents
tab AND the Mentor Administration Documents tab live: staff upload files to
the **"CBM Documents" shared drive** and each record's documents are listed
from the `app_document` Postgres table. Since v0.70.0 (Phase 2) the tab also
**views documents in-app** (View streams the file through the app as the
signed-in user; Google Docs/Sheets/Slides arrive as exported PDF) with the
browser as the cache (immutable responses on modifiedTime-versioned URLs — no
server cache to size or clear), and re-syncs each row's modifiedTime from
Drive when the tab opens. Phase 2 adds **no new env vars and no new
migration**. Folder tree (created on first upload;
top levels are display labels): mentor documents (Contact anchor) →
`Mentors/{Name} (contactId)/`; client-work documents (CEngagement anchor) →
`Clients/{Client Name} (clientId)/{Engagement Name} (engagementId)/` (the
parent client is resolved from the engagement at upload time);
partner/sponsor → `Partners/…`, `Sponsors/…`. Drive
access impersonates the signed-in manager's own `cbmEmail` — reuses
`GOOGLE_SERVICE_ACCOUNT_JSON` (or the Email-Setup config), no new secret.
Activation order (full step-by-step: **`GDRIVE-DOCS-SETUP.md`**): enable the
Drive API on the GCP project; create the shared drive + grant memberships
(staff need Content Manager); add `https://www.googleapis.com/auth/drive` to
the service account's domain-wide-delegation row;
run the pre-deploy migrate (Alembic `0005_app_document`); then set the flags.
Requires `DATABASE_URL` (the tab 503s without the store).

**Phase 3 (v0.76.0 — CRM integration and lifecycle, PRD v1.3):**
Archive/Restore is live on every Documents tab (soft delete — the file moves
to the record folder's `/_Archived` subfolder, an "Include archived" toggle
reveals archived rows; needs no new config). Under the **service-identity
access model** (`GDRIVE_IDENTITY=service`, Doug's ruling — no person is ever
a drive member) the app also maintains **per-person folder-level Commenter
grants** mirroring CRM assignments (engagement folders → assigned mentor +
co-mentors; partner/sponsor → their manager; `Mentors/` folders → no one),
issued/revoked by the Assign and co-mentor actions + first upload, and
re-derived by a **nightly reconciliation job in the worker** — so the
**worker now needs the `GDRIVE_*` vars too** (it already carries the SA
JSON + `DATABASE_URL`). On first upload the app writes the record folder's
Drive link to the CRM's `documentsFolderUrl` field (CEngagement + Contact;
feature-detected — inert until the CRM team builds it, spec:
`documentsfolderurl-crm-field.md`). Activation order matters (SA drive
membership BEFORE flipping the identity): `GDRIVE-DOCS-SETUP.md` Task 6.

| Variable | Value |
|---|---|
| `GDRIVE_DOCS` | `true` to enable the Documents tab (web + worker) |
| `GDRIVE_SHARED_DRIVE_ID` | the "CBM Documents" shared drive id (from its Drive URL; web + worker) |
| `GDRIVE_IDENTITY` | `service` (the ruled access model — users have NO Drive access): the service account acts as itself; **add the SA's `client_email` as the shared drive's ONLY member (Content Manager) and remove all humans**. Default `user` = the original impersonation mode, kept for compatibility. Web + worker. |
| `GDRIVE_RECONCILE_SECONDS` | worker: how often the grant reconciliation re-derives all folder grants from the CRM (default `86400` = daily; `0` disables) |
| `GDRIVE_DOC_TYPES` | optional override of the doc-type choices (comma-separated; default `Resume,Agreement,Intake Document,Pitch Deck,Other`) |
| `GDRIVE_MAX_FILE_MB` | optional upload size cap (default 100) |
| `GDRIVE_ENTITY_LABELS` | optional override of the top-level folder labels (default `Contact=Mentors,CEngagement=Clients,CPartnerProfile=Partners,CSponsorProfile=Sponsors`) |

`APP_ENCRYPTION_KEY` is required for the in-app Email Setup screen (with
`DATABASE_URL`); generate one with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
The Alembic `0003_app_config` migration (run by the pre-deploy migrate job) adds
the `app_config` table the encrypted config lives in.

**Not yet stood up for prod.** Standing it up requires two halves that must *both*
be in place — a plain service account has zero directory access until a Workspace
super-admin grants it **domain-wide delegation** (permission to impersonate a real
user for one named scope).

*In Google Cloud Console* (any project):
1. **Enable the Admin SDK API** (APIs & Services → Library → "Admin SDK API").
2. **Create a service account** (IAM & Admin → Service Accounts). It needs **no GCP
   IAM roles** — its power comes from the Workspace delegation, not GCP.
3. **Create a JSON key** for it (Keys → Add Key → JSON). This is the secret the app
   signs tokens with — keep it encrypted, rotate by replacing the key.
4. Note the service account's **OAuth client ID** (the numeric "Unique ID").

*In the Google Workspace Admin console* (admin.google.com, as a super-admin):
5. **Security → Access and data control → API controls → Domain-wide delegation →
   Add new.**
6. Paste the service account's **Client ID** and, for scopes, list **both** (the
   read-only scope is enough to *check*; the read-write scope is required to
   *create* a mailbox):
   `https://www.googleapis.com/auth/admin.directory.user.readonly`,
   `https://www.googleapis.com/auth/admin.directory.user`
   (If you only ever want the check-and-block behavior, the read-only scope alone
   suffices and `GOOGLE_CREATE_MAILBOX` must stay off.)
7. Pick a Workspace admin for the service account to **impersonate** — to *create*
   users it must be an admin with the **User Management** privilege; this becomes
   `GOOGLE_DELEGATED_ADMIN`.

*Config:* either paste the JSON key + delegated admin into the **Email Setup**
screen (`/mentoradmin`, admin-only — stored encrypted; needs `APP_ENCRYPTION_KEY`
+ `DATABASE_URL`), **or** set the `GOOGLE_*` vars in the overlay and re-apply.
(Delegation changes can take ~5–10 min to propagate — a brief `UNKNOWN`/auth error
right after setup isn't necessarily wrong. The Email Setup **Test connection**
button confirms it.)

**How it works at runtime** (`core/google_directory.py` + `mentoradmin/service.py`
`provision_mentor_user_steps`): the browser saves the mentor's fields, then opens a
**status window** that streams `POST /mentoradmin/api/mentors/{id}/provision`
(Server-Sent Events). The app mints a short-lived OAuth token from the JSON key,
signed as the service account with `subject = GOOGLE_DELEGATED_ADMIN` (read-only to
check, read-write to create), and calls `admin/directory/v1/users`:
**check** → 200 = exists (proceed), 404 = missing, anything else = `UNKNOWN` (fail
open). On **missing** with `GOOGLE_CREATE_MAILBOX` on, it `POST`s a new user (temp
password + change-at-first-login + the mentor's personal email as **recovery
email**), polls ≤60s for it to go live, then creates the EspoCRM login + welcome
email; the window shows the temp password to relay. If the mailbox doesn't verify
in time the mentor stays Approved and the next Save self-heals. The creds are a
separate credential from the EspoCRM admin service account.

> **CRITICAL — do not clobber a live app.** The committed `.do/app.yaml` is the
> *dry-run* spec: it hardcodes `ESPO_DRY_RUN=true` and contains **no secrets**.
> Running `doctl apps update --spec .do/app.yaml` (i.e. `deploy.sh`) against a
> live app would overwrite its env back to dry-run and **delete the CRM
> secrets**. Two safe ways to manage a live app:

**Option A — console + git push (simplest).** Set the three variables in the
console: App → Settings → the `web` component → Environment Variables; mark
`ESPO_API_KEY` (and `ESPO_BASE_URL` if you prefer) as *Encrypted*; save (this
redeploys). Thereafter ship **code** changes with `git push` — `deploy_on_push`
redeploys using the stored spec, leaving your env vars intact. Do **not** run
`deploy.sh` against this app again.

**Option B — gitignored prod spec overlay (reproducible).** Copy `.do/app.yaml`
to `.do/app.prod.yaml`, set `ESPO_DRY_RUN=false`, add the secret env vars above
(each as `type: SECRET`), and keep it **out of git** (`.do/app.prod.yaml` is
gitignored). This is how the live app is managed today (web + worker + a
PRE_DEPLOY `migrate` job + the managed Postgres for V2). Apply intentional
updates with
`doctl apps update <app-id> --spec .do/app.prod.yaml --wait`. This makes the
live config reproducible without committing secrets.

After either, confirm `curl https://<app-url>/healthz` shows `"dryRun": false`.

## Custom domain (optional, recommended for production)

**LIVE for prod (2026-07-06):** `https://apps.clevelandbusinessmentors.org` is
attached to the prod app as its PRIMARY domain (phase ACTIVE, Let's Encrypt
cert auto-provisioned). DNS is a Cloudflare CNAME `apps` →
`cbm-client-intake-prod-a9li7.ondigitalocean.app` set to **DNS only (grey
cloud)** — the orange-cloud proxy must stay off or DO's cert
validation/renewal fails. The default `…ondigitalocean.app` URL still works.
(Gotcha: right after creating the record, resolvers that had already looked up
the name cache the failure for up to 30 min — the zone's negative TTL.)

The default `…ondigitalocean.app` URL works, but a public production form
usually wants a branded host (e.g. `intake.clevelandbusinessmentors.org`):

1. DO console → the app → Settings → Domains → Add Domain → enter the hostname.
2. App Platform shows the DNS record to create. Add the **CNAME** (or the
   apex/`ALIAS` record it specifies) at the domain's DNS provider pointing at
   the app.
3. App Platform auto-provisions and renews the Let's Encrypt cert once DNS
   resolves — no certbot, no manual renewal.
4. If the form is ever embedded from another origin, add that origin to
   `ALLOWED_ORIGINS` (env var) — the wizard posts to its own origin, so this is
   not needed for the standalone forms.

## Reproduce the deployment in production

Two viable shapes — pick one:

- **Promote the same app to live** (one environment): deploy dry-run as above,
  gather feedback, then [go live](#going-live-write-to-espocrm) on the same app.
- **A separate production app** (recommended if the feedback app keeps running):
  create a second app named e.g. `cbm-client-intake-prod` so feedback and
  production are isolated.

**Clean from-scratch production sequence:**

1. **Prereqs** — `doctl` installed + `doctl auth init`; GitHub repo connected
   once in the console (see [Prerequisites](#prerequisites-one-time)).
1a. **Schema pre-flight (read-only, do this first).** Verify the *production* CRM
   has every entity/field/link/enum the app writes — a missing one silently sinks
   a live submission (the crm-test drift saga, see CHANGELOG.md). Run:
   `uv run python scripts/preflight_crm.py --url <PROD_CRM_URL> --key <READ_KEY>`.
   It exits non-zero and lists what's missing if the CRM isn't ready; fix those in
   EspoCRM first. (It can't check the API user's *create grants* — those are proven
   by the labelled test submissions in step 6. Enum gaps are advisory: orchestrators
   drop unknown values rather than failing.)
1b. **Provision the intake API user's role (CRM admin, one time).** A fresh CRM
   has no role for the create-only API user, so it can't create anything (every
   create 403s; the pre-flight shows all scopes "not visible"). Recreate the
   crm-test role in the prod CRM admin UI (Administration → Roles) and assign it to
   the intake API user. For EACH of these 9 entities — **Account, Contact,
   CClientProfile, CEngagement, CMentorProfile, CPartnerProfile, CSponsorProfile,
   CInformationRequest, CIntakeSubmission** — set **Create=Yes, Read=All, Edit=All,
   Delete=No** (Stream=All, except CInformationRequest=No). No field-level
   restrictions; Export=No, Mass Update=No, Assignment Permission=all. (Role
   creation is admin-only — an API key can't do it. Derived from the crm-test
   user's computed ACL via `GET /api/v1/App/user`.) Re-run the pre-flight (1a) — it
   should go green once the role is assigned.
2. **Pick the app name.** For a separate prod app, copy `.do/app.yaml` to a
   gitignored `.do/app.prod.yaml` and change `name:` to `cbm-client-intake-prod`
   (the `deploy.sh` `APP_NAME` only matches `cbm-client-intake`, so a renamed
   spec is created as a new app and never collides with the feedback app).
3. **Create dry-run first** — `doctl apps create --spec .do/app.prod.yaml --wait`
   (still `ESPO_DRY_RUN=true`). Verify `/healthz` shows `"dryRun": true` and
   both forms load. This proves the build/deploy before any CRM writes.
4. **Custom domain** (optional) — add it now so the cert provisions while you
   finish CRM setup.
5. **Go live** — set `ESPO_DRY_RUN=false` + the two CRM secrets via
   [Option A or B](#going-live-write-to-espocrm). Point `ESPO_BASE_URL` at the
   **production** CRM (not `crm-test`).
6. **Verify live** — see below. Submit one obviously-labelled test through each
   form and confirm the records in EspoCRM.
7. **Ongoing** — ship code with `git push` (auto-redeploy preserves env). Use
   the prod spec overlay (Option B) for any intentional infra change.

## Verify a live deployment

1. `curl https://<app-url>/healthz` → `"dryRun": false`.
2. Submit one test through each form; use obvious test data (the API user can't
   delete, so you'll remove test records in the EspoCRM UI).
3. Confirm the records in EspoCRM:
   - client-intake → Account → Contact → CClientProfile → CEngagement
   - volunteer → Contact (`cContactType=["Mentor"]`) → CMentorProfile
4. Logs: DO console → the app → **Runtime Logs**, or
   `doctl apps logs <app-id> --type run -f`. The decisive line on a failed
   submission is `ERROR cbm_intake: … create <Entity> failed: HTTP <code> <body>`
   (the browser only shows a generic 502).

## Reliability operations (added with the 2026-07-18 hardening, v0.94.0)

### Database backups — DECISION NEEDED (P1-7, ruled: tier upgrade — Doug 2026-07-18)

`pending` / `retry` / `needs_attention` submissions exist **only** in the two
managed databases (`cbm-db` on crm-test, `cbm-db-prod` on prod). Both were
created on the **dev tier**, which has **no automated backups or point-in-time
recovery** — losing the database during a CRM outage backlog loses those
submissions unrecoverably. Doug's ruling (decision D4): **upgrade both to a
production tier** (DO then takes daily backups + PITR automatically; no
scheduled-dump machinery to build or monitor).

**To do (console, one time each):** DO console → Databases → `cbm-db` /
`cbm-db-prod` → Settings → **Upgrade** to the smallest production tier.
No app change; the connection string is unchanged.

**Restore runbook** (once on a production tier): DO console → the database →
Backups → restore creates a NEW cluster → update `DATABASE_URL` on the app's
web + worker components (the gitignored overlay, applied with
`doctl apps update <app-id> --spec …`) → redeploy. The design survives restore
well: re-delivery is idempotent (per-record `progress`), and replayed rows
dedupe on `uq_submission_form_token`. Comms sync cursors restore stale =
the next pass re-reads the gap; Message-ID dedup absorbs the overlap.

### Alert delivery by EMAIL (v0.117.0 — CBM uses no messaging service)

Every worker alert (needs-attention backlog, stranded rows, Gmail sync
failures/dead-letters, Drive-grant reconciliation findings, schema drift) can
be delivered as **email** through the existing Gmail service-account
delegation — no new infrastructure. On the **worker** component set:

- `ALERT_EMAIL_TO` — comma-separated recipients (any addresses, personal
  Gmail included).
- `ALERT_EMAIL_FROM` — the `@cbmentors.org` mailbox to send AS. Must be a
  real licensed Workspace mailbox (delegation can't send as a group/alias);
  falls back to `OPS_MAILBOX` when unset.

The webhook (`ALERT_WEBHOOK_URL`) still works, alone or alongside email; with
no channel configured (or all deliveries failing) alerts log at WARNING, as
always.

### Uptime + alert checks (point at /healthz)

`/healthz` now reports worker liveness — configure a DO uptime check /
alert (or any external monitor) on it:

- `database: "error"` / HTTP 503 → the managed Postgres is down.
- `worker.lastHeartbeatAgeSeconds` → the delivery worker stamps this every
  loop; **alert when it exceeds ~120s** (a dead, wedged, or undeployed
  worker produces no other signal — the in-app alerter runs INSIDE the
  worker and dies with it).
- `worker.backlog` / `worker.oldestPendingAgeSeconds` /
  `worker.stranded` → growing values mean deliveries aren't completing.

### Worker: exactly one instance

Keep the `delivery-worker` component at `instance_count: 1`. The Gmail sync
cursors, alert cooldowns, and reconciliation error-tracking assume a single
worker process; a second instance would double-read mailboxes and race the
timers (submission claiming itself is safe — `FOR UPDATE SKIP LOCKED` — but
nothing else is). Deploys are now graceful: the worker finishes its current
item on SIGTERM and stops claiming.

### Overlay recovery (laptop loss)

The gitignored `.do/app.prod.yaml` (crm-test) and `.do/app.prod-crm.yaml`
(prod) are the only local copies of the live specs; they live inside
Dropbox. If lost, regenerate structure with
`doctl apps spec get <app-id> > file.yaml` — **but** every `type: SECRET`
env var comes back as an encrypted `EV[…]` blob, which keeps working when
re-applied **unchanged** yet can never be read back. The secret **values**
that exist nowhere else and would need re-issuing if you ever must set them
fresh: `ESPO_API_KEY` (re-key the API user in EspoCRM), `SESSION_SECRET`
(generate anew — users just re-log-in), `GOOGLE_SERVICE_ACCOUNT_JSON`
(create a new key on the service account in GCP), `APP_ENCRYPTION_KEY`
(if lost, in-app Email-Setup config is unreadable — re-enter it), and
`ESPO_PROVISION_PASSWORD` (reset the provisioning admin's password).
Consider keeping a copy of the overlays (or just those values) in a real
secret store.

### Schema comes from Alembic only (v0.94.0 change)

The web app and worker **no longer create tables at boot**. The schema
authority is the PRE_DEPLOY `migrate` job (`alembic upgrade head`) — already
in both overlays — and locally `uv run alembic upgrade head` after
`docker compose up -d db`. (Boot-time `create_all` used to build current
tables on a fresh environment WITHOUT an `alembic_version` stamp, wedging
every later migration.) A brand-new environment booted without the migrate
job now surfaces visible capture 503s / worker cycle errors until the
migration runs — by design.

### Intake limits (decision D3)

Public form POSTs are capped at **2 MB** (`INTAKE_MAX_BODY_MB`; the
volunteer form allows 8 MB for its in-JSON resume) and rate-limited to
**30 submissions per IP per 10 minutes** (`INTAKE_RATE_LIMIT` /
`INTAKE_RATE_WINDOW_SECONDS`; 0 disables). Limits are in-memory per web
instance — fine at one instance; revisit if the web tier ever scales out.

## Rollback

- List deployments: `doctl apps list-deployments <app-id>`
- Roll back: in the console, the app → Deployments → pick a prior successful
  deployment → **Rollback** (re-runs that build). Or revert the offending commit
  on `main` and let `deploy_on_push` roll forward with the fix.
- App Platform keeps prior deployments, so rollback never touches your env vars.

## Troubleshooting (gotchas already hit — see CLAUDE.md for detail)

- **`deploy.sh` aborts: "App … appears to be LIVE"** — the safety guard fired;
  you tried to update a live app from the dry-run spec. Manage live apps per
  [Going live](#going-live-write-to-espocrm); override with
  `ALLOW_LIVE_UPDATE=1` only if you truly intend to reset it to dry-run.
- **First `deploy.sh` fails with a GitHub/repo error** — the repo isn't
  connected to App Platform yet; do the one-time console authorize
  ([Prerequisites](#prerequisites-one-time) step 3).
- **`/healthz` shows `"dryRun": true` after going live** — env vars didn't take,
  or `deploy.sh` clobbered them back. Re-apply via console (Option A) or the
  prod overlay (Option B); confirm you're not re-running `deploy.sh` on the live
  app.
- **400 `phoneNumber valid`** — phone must be E.164; handled by
  `core/phone.to_e164`.
- **400 `<field> valid`** on an enum/multiEnum — a form dropdown value isn't in
  the deployed CRM enum's options. Form option lists are aligned to the CRM in
  `forms/*/frontend/options.js`; re-align if the CRM enums change.
- **403 on create** — the intake API user's role lacks create permission on that
  entity (grant it in EspoCRM admin → Roles).
- **409 on Account** — duplicate-name detection; the orchestrator reuses a
  same-named Account (find-or-create).
- **"Submitted but no records"** — almost always a dry-run server or a stale
  browser cache. Check `/healthz` `"dryRun"`, and hard-refresh / use a private
  window so the latest `options.js` loads.
