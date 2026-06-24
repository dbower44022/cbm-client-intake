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

- `…/` — form index
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

The staff tools (`/assignments` = **Client Administration**, `/ops` = Submission
Operations, `/mentoradmin` = **Mentor Administration**) mount only when
`SESSION_SECRET` is set. Staff authenticate with their own EspoCRM
username/password; access is gated by EspoCRM **Team**. All are on the **web**
component:

| Variable | Value |
|---|---|
| `SESSION_SECRET` | random string, **`type: SECRET`** — enables the staff tools + signed sessions |
| `ASSIGN_ALLOWED_TEAMS` | `Client Administration Team` (gate for `/assignments`) |
| `MENTOR_ADMIN_ALLOWED_TEAMS` | `Mentor Administration Team` (gate for `/mentoradmin`; default) |
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
`crm-test` 2026-06-22. (The async delivery worker — `worker.py` — does **not**
need these; provisioning runs synchronously in the web request.)

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
