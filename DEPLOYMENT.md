# Deployment Runbook — cbm-client-intake

How to deploy the CBM intake app (client-intake + volunteer forms) to
**DigitalOcean App Platform**. App Platform builds the repo's `Dockerfile`
straight from GitHub and serves it over managed HTTPS — no server to run.

> **New session quick-start:** read `CLAUDE.md` first (current state), then run
> `./scripts/deploy.sh`. The script is idempotent (creates the app the first
> time, updates it after). It deploys in **dry-run** (no EspoCRM writes); see
> "Going live" to wire EspoCRM.

## What gets deployed

- One service from `Dockerfile`, spec in [`.do/app.yaml`](.do/app.yaml):
  `basic-xxs` instance, health check `/healthz`, `deploy_on_push: true`.
- Config is env-driven (`core/config.py`); all values default, and
  `ESPO_DRY_RUN` defaults to `true`, so the app boots with **no secrets** and
  performs no EspoCRM writes until you explicitly go live.

## Prerequisites (one time)

1. A DigitalOcean account.
2. **doctl** (the DO CLI), installed and authenticated:
   - macOS: `brew install doctl`
   - Linux: `sudo snap install doctl` (or download from the doctl releases page)
   - Authenticate: `doctl auth init` — paste a Personal Access Token from
     DO → API → Tokens (needs read/write).
3. **Connect GitHub to App Platform** (only needed for the very first create):
   in the DO console, Apps → Create App → GitHub → authorize the
   `dbower44022/cbm-client-intake` repo. After this, `doctl` can create/update
   the app non-interactively. (If `deploy.sh` fails the first run with a GitHub
   error, this is why.)

## Deploy (dry-run, for feedback)

```bash
./scripts/deploy.sh
```

The script: validates the spec → creates the app (or updates it if it already
exists) → waits for the deployment → prints the public `…ondigitalocean.app`
URL → checks `/healthz`. Expect `"dryRun": true`.

Then sanity-check in a browser:

- `…/` — form index
- `…/client-intake/` and `…/volunteer/` — the two wizards
- Submissions are validated and **logged only** (no records created) while in
  dry-run.

`deploy_on_push: true` means every push to `main` thereafter auto-redeploys.

## Going live (write to EspoCRM)

The integration is verified against `crm-test` (see `CLAUDE.md`). To make the
**deployed** app write to EspoCRM, set these as **encrypted** App-level
environment variables — never commit them:

| Variable | Value |
|---|---|
| `ESPO_DRY_RUN` | `false` |
| `ESPO_BASE_URL` | e.g. `https://crm-test.clevelandbusinessmentors.org` |
| `ESPO_API_KEY` | the **dedicated, create-only** intake API user's key |

Set them either in the console (App → Settings → the `web` component → Environment
Variables, mark `ESPO_API_KEY` as *Encrypted*) or via `doctl apps update` with a
local spec overlay that you keep out of git. Redeploy, then confirm `/healthz`
shows `"dryRun": false`.

The API user must be scoped **create-only** on `Account`, `Contact`,
`CClientProfile`, `CEngagement`, and `CMentorProfile` (verified: it cannot
delete — DELETE returns 403).

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
- Re-deploy a previous one: `doctl apps create-deployment <app-id>` after
  reverting the offending commit on `main` (auto-deploy), or roll forward with a
  fix. App Platform keeps prior deployments for quick redeploy in the console.

## Troubleshooting (gotchas already hit — see CLAUDE.md for detail)

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
