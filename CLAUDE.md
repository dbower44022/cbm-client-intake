# CLAUDE.md

Guidance for Claude Code working in the **cbm-client-intake** repository.
This file is read automatically at session start — it is the recovery anchor
if a session is lost. Keep the "Current status" section up to date.

## What this is

A custom web application for **Cleveland Business Mentors (CBM)**. It hosts
branded, multi-step wizard **intake forms**; a completed submission creates
linked records in EspoCRM (the system of record). Two forms ship today:

- **client-intake** — SCORE Mentor Request (FormAssembly form 111), reconciled
  to the CBM model. Creates Account → Contact → CClientProfile → CEngagement.
- **volunteer** — SCORE volunteer/become-a-mentor (form 6 / MR-APPLY). Creates
  a single Contact (Mentor) with an optional in-memory resume upload.

This repo owns the *application*, not the business definition of the process.
The Client Intake process is defined by **MN-INTAKE** in the
`dbower44022/ClevelandBusinessMentoring` repo; the Requirements Spec here is
kept aligned to it by carry-forward.

## Current status (2026-05-28)

**Goal right now:** publish the app **as-is** to DigitalOcean for user feedback.
EspoCRM wiring is deliberately deferred to *after* feedback.

**Chosen path:** **DigitalOcean App Platform**, building the `Dockerfile`
straight from this GitHub repo (`dbower44022/cbm-client-intake`, branch `main`).
A new droplet was ruled out for time. Deploys in **dry-run**
(`ESPO_DRY_RUN=true`): submissions are validated and logged but **no EspoCRM
records are created**.

**Done:**
- Both forms build and serve (locally: `uv run uvicorn main:app --reload --port 8000`).
- Tests green (17 passing).
- Deploy glue committed at `12791d9` and **verified by a local Docker build+run**
  (`/healthz` → `{"status":"ok","dryRun":true,...}`, both forms 200):
  `Dockerfile`, `.dockerignore`, `.do/app.yaml`.

**Deployment method confirmed (2026-05-28): DigitalOcean App Platform.** The
method was re-evaluated against a droplet, co-hosting on the CRM box, and other
PaaS, and App Platform was confirmed (decision record + full comparison in
`DEPLOYMENT.md`). The prod-like container (the exact image App Platform builds)
was **tested locally and verified**: `docker build`/`run` → `/healthz` is
`dryRun:true`, both forms + index + shared assets 200, a dry-run
`POST /api/volunteer/intake` returns synthetic ids (no CRM call) and is
idempotent on token re-submit, `pytest` 17 passing.

**Resume point — run the live dry-run deploy.** `DEPLOYMENT.md` is the full
runbook: prerequisites, deploy, going-live, **custom domain**, **reproduce in
production from scratch**, verification, rollback, troubleshooting.
1. **Blocker (needs Doug's DO account):** `doctl` is **not installed** on this
   machine, and the GitHub repo must be connected to App Platform once in the
   DO console. These are the only steps Claude can't do — they need Doug's
   credentials. See `DEPLOYMENT.md` Prerequisites.
2. **Deploy:** `./scripts/deploy.sh` — idempotent; deploys **dry-run**
   (`ESPO_DRY_RUN=true`, no EspoCRM writes). It now has a **safety guard** that
   refuses to update a *live* app (would revert it to dry-run + drop secrets);
   override with `ALLOW_LIVE_UPDATE=1` only when intended.
3. Verify `/healthz`, `/client-intake/`, `/volunteer/` at the
   `…ondigitalocean.app` URL; share it for feedback.
4. To write to EspoCRM: set `ESPO_DRY_RUN=false` + `ESPO_BASE_URL` +
   `ESPO_API_KEY` as **encrypted** env vars (console or a gitignored
   `.do/app.prod.yaml` overlay) — **not** by re-running `deploy.sh`. See
   `DEPLOYMENT.md` "Going live".

**EspoCRM wiring — BOTH forms VERIFIED end-to-end against crm-test (2026-05-28).**
- **client-intake**: created/linked Account → Contact → CClientProfile →
  CEngagement (all GET-verified 200).
- **volunteer**: created/linked Contact (`cContactType=["Mentor"]`) → CMentorProfile
  (`contactRecord` link), data verified on the records. The orchestrator was
  rewritten (commit 95765e4) from its wrong flat-Contact model to the deployed
  Contact+CMentorProfile model — mentor data lives on CMentorProfile, not flat
  Contact fields. Mapping decisions: mentorStatus=`Candidate`, mentorType=`Mentor`,
  multi-select industry → first `industrySector` only (single enum; multi-store
  deferred), terms_accepted → `termsAccepted`. The form's industry/expertise/
  language dropdowns are aligned to the deployed CRM enum options — a value
  outside the enum 400s the create (`forms/volunteer/frontend/options.js`).
  **Deferred:** resume upload (no
  attachment field deployed), `currently_employed`/`contact_preference`/`phone_type`
  (no target field). The volunteer mapping doc `score-volunteer-form-6-mapping.md`
  is now STALE (describes the old flat-Contact model) — orchestrator is the truth.

Local `.env` stays `ESPO_DRY_RUN=true`; live tests use an inline
`ESPO_DRY_RUN=false` override on a throwaway port. Findings while wiring:
- **Phone must be E.164** — crm-test rejects other formats with a phone "valid"
  failure; `core/phone.to_e164` normalizes at the CRM boundary (commit 95f841c).
- **API-user role** must grant *create* on CEngagement (was read-only until
  granted 2026-05-28); it already had create on Account/Contact/CClientProfile.
- **Account duplicate detection** — EspoCRM returns 409 on a same-named Account.
  RESOLVED (commit befa2cc): `_find_or_create_account` reuses a same-named match
  (exact, case-insensitive) instead of creating, so repeat submitters dedupe and
  the 409 path is avoided. Distinct businesses sharing a name collapse to one
  Account by design — split downstream if ever needed.
- Mapping source of truth: `forms/client_intake/orchestrator.py`; see also
  Technical Design §3.4 and the §11.1 pending-carry-forward set.

**Open follow-ups:**
- Make the *deployed* app write to EspoCRM: set `ESPO_DRY_RUN=false` plus
  `ESPO_BASE_URL` + `ESPO_API_KEY` as **encrypted** App Platform env vars.
- Clean up the `ZZTEST` test records left in crm-test by the wiring tests
  (must be done in the EspoCRM UI — the intake API user is create-only and
  cannot delete; verified by 403s).
- ~~Evaluate an alternative deployment method~~ **Done (2026-05-28).** App
  Platform was re-evaluated and confirmed; see the decision record in
  `DEPLOYMENT.md`. The kickoff that drove it is
  `prompts/CLAUDE-CODE-PROMPT-deployment-method.md`.

## Commands

```bash
uv sync                                  # install deps (uv-managed; package = false)
uv run uvicorn main:app --reload --port 8000   # run locally -> http://localhost:8000/
uv run pytest -q                         # tests
docker build -t cbm-intake . && docker run --rm -p 8099:8080 cbm-intake  # prod-like run
./scripts/deploy.sh                      # deploy to DO App Platform (see DEPLOYMENT.md)
```

## Architecture

A shared core hosts any number of per-form packages.

- `main.py` — composition root: `create_app([client_intake.SPEC, volunteer.SPEC])`.
- `core/` — the only place that holds EspoCRM credentials.
  - `app.py` — FastAPI factory. Per form it exposes `POST /api/{slug}/intake`
    and serves `/{slug}/`. Also `GET /` (form index), `GET /healthz`, and
    `/shared/` for the design tokens / wizard assets. Honeypot (`company_url`)
    and a `submission_token` idempotency cache live here.
  - `espo.py` — `EspoClient` (real) and `DryRunEspoClient` (logs + synthetic ids).
  - `config.py` — `pydantic-settings`. **All settings default**, and
    `espo_dry_run` defaults to `True`, so the app boots with zero env vars.
  - `forms.py` — the `FormSpec` + `BaseSubmission` registry contract.
- `forms/<name>/` — one form per package: `schemas.py` (submission model),
  `orchestrator.py` (EspoCRM mapping), `frontend/` (static wizard), and `SPEC`.
- `frontend/shared/` — `tokens.css` (CBM design tokens extracted from the
  staging site), `wizard.css`, `wizard.js` (shared step controller).

The frontend is plain HTML/CSS/vanilla JS — **no build step**. The wizard posts
to its own origin, so CORS is not in the form's request path; `ALLOWED_ORIGINS`
only matters if a separate frontend origin is ever introduced.

## Gotchas / things learned

- **`.dockerignore` must exclude `.venv`** — `COPY . .` otherwise copies the
  host virtualenv over the container's, whose interpreter paths are wrong
  (`sh: .venv/bin/uvicorn: not found`, exit 127). It also keeps `.env` out of
  the image.
- The app is **stateless**: no DB, no disk writes (resume upload is base64
  in-memory). On App Platform the filesystem is ephemeral and the idempotency
  cache resets on redeploy — fine for a dry-run feedback build, but **dry-run
  submissions are logged only, not stored**, so there is no record of what
  testers submitted beyond runtime logs.
- The EspoCRM integration was reconciled against the `crm-test` instance
  (Technical Design v0.3): the Engagement links to a **CClientProfile** hub,
  not directly to the Account.
- Canonical SCORE field inventory / mapping lives here
  (`score-*-form*.md`, `score-mentor-request-form.yaml`). Copies may appear as
  scratch under the separate `crmbuilder` repo root — those are not canonical.

## Documentation

- `prds/CBM_Client_Intake_Requirements_Specification.md` — what it must do.
- `prds/CBM_Client_Intake_Technical_Design.md` — how it's built (deployment in
  §6, open issues in §7, EspoCRM mapping in §3).

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- Never commit `.env` or any secret. Secrets are injected as environment
  variables at deploy time (App Platform encrypted env vars).
- Commit messages follow Conventional Commits (`feat:`, `build:`, `docs:`, …).
