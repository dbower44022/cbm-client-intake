# Kickoff prompt — a new deployment's own provider credentials before its first run

**Document:** Prompt to start a CRMBuilder session that lets a new deployment hold its own DigitalOcean and Cloudflare tokens before its first deploy run
**Version:** 0.2
**Status:** Draft — written by Claude for Doug 11-08-26 (Doug chose this route, option A); reviewed against CRMBuilder's code 11-09-26 (SES-457). Doug pastes it into a session in `~/Dropbox/Projects/crmbuilder`
**Owner:** Doug Bower
**Last Updated:** 11-09-26 00:06

---

Paste everything below the line into a new Claude Code session started in `~/Dropbox/Projects/crmbuilder`. Alternatively, give the session only this file's full path, on one line with nothing typed before it, so the session-open rule reads the opening answer from the file (a path split across lines or preceded by a word is not recognised — PI-597, PI-598).

---

> Opening answer: requirements for setting a new deployment's own provider credentials before its first deploy run, under PRJ-129

**Project.** Proposed home: **PRJ-129 "Deployment inputs: settings, secrets and readiness"** (planned), because a deployment holding its own credentials is a deployment input (DEC-1155, DEC-1157). The alternative is PRJ-127 "Deploy without DNS access, and a clearer deploy wizard" (planned). PRJ-133 is complete and takes no new work; DEC-1198 placed the first run under a grant in a client project, which this is not — this is the product gap that blocks that run. Confirm the project with Doug before recording the requirement.

## What is wrong

The Business Mentors Association is being set up as a chapter (Association rulings 71 and 72). Its CRM is the next step: a new deployment of the application **ENG-002 (CBM — Cleveland Business Mentoring)** for a new client, Business Mentors Association, in the Association's own DigitalOcean account, with DNS in its own Cloudflare account.

The deploy wizard cannot give that deployment its own tokens before the run:

- `segments/operate/ui/dialogs/deploy_wizard_dialog.py`: `_deployment_identifier` is None until `_deploy()` creates the deployment at the moment the run is queued (lines ~985–1013). Step 1's **Set credentials…** (`_open_credentials`, ~967) therefore opens `ProviderCredentialsDialog` with no deployment.
- `segments/operate/ui/dialogs/provider_credentials_dialog.py` `_save`: with no deployment it calls `put_provider_credential`, which writes at **application** scope.
- ENG-002's application-scope DigitalOcean credential is `crmbuilder-eng002-readonly (cbm team, read-only)`, which Cleveland's deployments DPL-001 (crm-test) and DPL-002 (production) read through. Saving the Association's token there replaces Cleveland's — the hazard the chapter network recorded on 09-23-26 (`cbm-client-intake/prds/chapter-network/TASKS.md`, G1 item 14), which happened once and was repaired.
- Left alone, the run would use Cleveland's read-only token against Cleveland's team and fail.

Every chapter after the Association meets the same wall: each deploys ENG-002 into its own account (DEC-1155, a deployment holds its own credentials).

There is no desktop workaround today: the wizard always creates its own new deployment, so a deployment created beforehand cannot be built through it, and saving the token at application scope is the hazard above.

## What already exists (verified 11-09-26 — do not re-specify)

Everything below the wizard already supports deployment-scope credentials (PI-576). The gap is the wizard's flow only.

- **A deployment can exist with no instance.** `POST /deployments` takes the instance as optional (`segments/operate/schemas.py` ~210).
- **Deployment-scope credentials have their own routes:** `GET`, `PUT` and `DELETE` under `/deployments/{id}/provider-credentials` (`segments/operate/routers/deployments.py` ~209–246), with client methods `list_`/`put_`/`delete_deployment_provider_credential` (`segments/operate/client.py` ~293–317).
- **The Deployments panel can already set them** for an existing deployment (`segments/operate/ui/panels/deployments.py`, `_on_credentials_clicked` ~860).
- **The run already prefers the deployment's own token:** `resolve_provider_credential` returns the deployment's credential, else the application's (`segments/operate/repositories/provider_credentials.py` ~78; called from `deploy/runner.py` ~414).
- **The wizard's credentials dialog already accepts a deployment identifier** (`deploy_wizard_dialog.py` ~969), and the wizard already reuses the deployment it created when a run is refused (`_deploy`, ~991).

## What this session is for

Follow this repository's own process: requirement-first, a confirmed requirement and an implementing planning item before any code. Read `CLAUDE.md` first. The outcome to reach:

- A person can give a **not-yet-run deployment** its own DigitalOcean and Cloudflare tokens, at **deployment** scope, before the first deploy run.
- **The deploy wizard never writes a provider credential at application scope.** Once the wizard always has a deployment, it has no reason to. Application-scope credentials are set only outside the wizard.
- The run uses the deployment's own tokens, and the application's credential stays untouched.
- The wizard's zone lookup and DNS step use the deployment's Cloudflare token, not the application's.

## The shape to settle (recommendation: A)

- **A — the wizard creates the deployment early,** when step 1 is left or when **Set credentials…** is pressed, and works on that deployment from then on, as it already does after a refused run. Smallest change. Cost: an abandoned wizard leaves a deployment that never ran, so not-yet-run deployments must be visible as such in the Deployments panel and removable.
- **B — create first, build second.** The Deployments panel gains a "Build…" action that opens the wizard on an existing not-yet-run deployment. No orphans. Cost: a second user-interface path and more build work.
- **C — the wizard keeps the tokens in memory and saves them after Deploy creates the deployment.** Not recommended: the zone list runs before Deploy and would still use Cleveland's Cloudflare token.

Whichever shape is chosen, the zone list needs a deployment: `list_cloudflare_zones` calls `GET /provider-credentials/cloudflare/zones`, which takes no deployment and so reads the application's Cloudflare credential (`segments/operate/client.py` ~216; verified 11-09-26). It needs a deployment-scoped form. Check `lookup_deploy_address` (`GET /deploy-runs/dns-lookup`, ~385) the same way.

Present the choice to Doug with the consequential decision template before recording the requirement.

## Facts for the Association's deployment (for testing, not to write without Doug)

- Client: **Business Mentors Association** (new; needs a deployment grant on ENG-002 — Clients, Deployment grants, Add application).
- Purpose: Client's own.
- Hosting: DigitalOcean team "Business Mentors Association", signed in as admin@mentorsassociation.org. Token "crmbuilder-bma", full access, in the Association's Proton Pass as "DigitalOcean token for CRMBuilder".
- DNS: Cloudflare, zones mentorsassociation.org and businessmentorsassociation.org. Token "crmbuilder-bma" (Zone DNS Edit and Zone Read on both zones) in Proton Pass as "Cloudflare DNS token for CRMBuilder".
- CRM address: https://crm.businessmentorsassociation.org/ (from `cbm-client-intake/prds/chapter-network/chapters/bma-values.yaml`).
- Build without the two paid add-ons for now (Doug, 11-08-26; Association ruling 74); install them at guide step 9.5 later.

## At the end

Report what changed, and the exact screens and labels for guide steps 5.8 and 9.3, so `cbm-client-intake`'s deployment guide can be corrected (its step 5.8 still describes engagements). Record the Association's stage 9 as unblocked in `cbm-client-intake/OPEN-ITEMS.md` item 73 only through a session in that repository.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 11-08-26 14:18 | First version, from Claude's reading of CRMBuilder's code and records on 11-08-26. |
| 0.2 | 11-09-26 00:06 | Reviewed against the code in CRMBuilder SES-457. Added "What already exists" (deployment-scope credentials, their routes and panel, and the run's deployment-first lookup are built; the gap is the wizard only), the no-workaround note, a proposed project (PRJ-129, alternative PRJ-127) named in the opening answer, and the three shapes with A recommended. "Never write at application scope, or warn" became "never write at application scope". Added the zone-lookup outcome, the finding that the Cloudflare zone list takes no deployment (verified), and the one-line path instruction. |
