# Session kickoff — choose and build a deployment method for cbm-client-intake

## Your task

Explore alternative ways to deploy this app, **decide on one together with the
user**, then build the infrastructure and documentation for it. Three phases:
(1) evaluate options → (2) a decision gate with the user → (3) build + document.

You have no prior conversation context. Orient yourself from the files below
before doing anything else.

## Orientation — read these first

- `CLAUDE.md` — current state, architecture, conventions. Read it fully.
- `DEPLOYMENT.md` — the deployment method that **already exists** (DigitalOcean
  App Platform) plus the gotchas hit while wiring EspoCRM. This is your baseline
  to compare against, not a constraint to keep.
- `.do/app.yaml`, `Dockerfile` — existing build/deploy artifacts (much of this
  carries over to other methods).
- `core/config.py`, `core/app.py` — how the app is configured and served.
- Prior art for a VM/droplet path: the parent repo
  `~/Dropbox/Projects/crmbuilder` (`automation/core/deployment/`) has
  battle-tested DigitalOcean droplet + Docker + nginx + Let's Encrypt + SSH
  tooling for EspoCRM. Reuse its patterns; don't reinvent them.

## What the app is (to judge fit)

Stateless FastAPI app (`uvicorn main:app`), no database, no disk writes. Serves
two static wizard forms and creates EspoCRM records. Config is env-driven;
`ESPO_DRY_RUN` defaults to `true` (no CRM writes). It already builds and runs as
a container (verified). Hosting provider is **DigitalOcean**.

## Phase 1 — Explore (high freedom)

Evaluate at least these candidates, plus any you judge better:

- **DigitalOcean Droplet (VM):** Docker + systemd + nginx + Let's Encrypt.
- **Co-host on the existing CBM EspoCRM droplet:** reuse that box — note it runs
  nginx in Docker on 80/443, so you'd route around that.
- **Another PaaS:** Render / Fly.io / Railway.
- **App Platform** (the existing method) as the comparison baseline.

**First, confirm the user's priorities** — cost vs. control vs. low ops burden
vs. using infrastructure they already own. That ordering decides the winner.
Then score the candidates against: cost; ongoing maintenance burden; HTTPS/TLS;
secrets handling (env-driven `ESPO_*`, never committed); auto-deploy from
GitHub; fit with the team's existing DigitalOcean + SSH tooling; rollback; log
access; how much of the current `Dockerfile` / `.do/app.yaml` carries over.
Produce a short comparison (a table is fine) — not an essay.

## Phase 2 — Decide (STOP here)

**YOU MUST present the comparison and get the user's explicit choice before
building anything.** Provisioning remote infrastructure (droplets, DNS, external
services) is high blast-radius and hard to reverse — do NOT create any external
resource until the user picks a method and approves the plan. No exceptions.
Record the decision (chosen method + one-paragraph why) in the runbook you write
in Phase 3.

## Phase 3 — Build + document (medium freedom)

For the chosen method:

- Build the infrastructure: deploy script(s) and any config (compose / systemd /
  nginx / provider spec), following the existing patterns and prior art.
- **Hard requirements:** HTTPS; first (feedback) deploy runs `ESPO_DRY_RUN=true`;
  `ESPO_BASE_URL` + `ESPO_API_KEY` injected as **secrets, never committed**;
  deploy dry-run first and verify `/healthz`, then document the flip to live. The
  intake API user is **create-only** (it cannot delete — verified).
- Write or replace the runbook (mirror `DEPLOYMENT.md`'s shape): prerequisites,
  deploy, going-live, verification, rollback, troubleshooting.
- Update `CLAUDE.md`'s resume point to the new method.
- Test as far as you can, and **state explicitly what you could not verify**
  (e.g., live provisioning that needs the user's credentials).

## Working conventions (from CLAUDE.md — follow them)

- **Push convention:** you commit; the user pushes. Do not push without being asked.
- Never commit `.env` or secrets.
- Confirm before risky / remote / irreversible actions. For terminal walkthroughs
  the user prefers one command at a time, waiting for output.
- Test against `crm-test` with obviously-labeled records, and remember they must
  be deleted in the EspoCRM UI afterward (the API user can't delete).

## Definition of done

Method chosen with the user and recorded; infra + runbook committed; `CLAUDE.md`
resume point updated; a dry-run deploy verified (or the exact blocker
documented); and a clear, documented path to go live against EspoCRM.
