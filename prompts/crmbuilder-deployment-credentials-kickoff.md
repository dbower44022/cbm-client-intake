# Kickoff prompt — a new deployment's own provider credentials before its first run

**Document:** Prompt to start a CRMBuilder session that lets a new deployment hold its own DigitalOcean and Cloudflare tokens before its first deploy run
**Version:** 0.1
**Status:** Draft — written by Claude for Doug 11-08-26 (Doug chose this route, option A); Doug pastes it into a session in `~/Dropbox/Projects/crmbuilder`
**Owner:** Doug Bower
**Last Updated:** 11-08-26 14:18

---

Paste everything below the line into a new Claude Code session started in `~/Dropbox/Projects/crmbuilder`.

---

> Opening answer: requirements for setting a new deployment's own provider credentials before its first deploy run

## What is wrong

The Business Mentors Association is being set up as a chapter (Association rulings 71 and 72). Its CRM is the next step: a new deployment of the application **ENG-002 (CBM — Cleveland Business Mentoring)** for a new client, Business Mentors Association, in the Association's own DigitalOcean account, with DNS in its own Cloudflare account.

The deploy wizard cannot give that deployment its own tokens before the run:

- `segments/operate/ui/dialogs/deploy_wizard_dialog.py`: `_deployment_identifier` is None until `_deploy()` creates the deployment at the moment the run is queued (lines ~985–1013). Step 1's **Set credentials…** (`_open_credentials`, ~967) therefore opens `ProviderCredentialsDialog` with no deployment.
- `segments/operate/ui/dialogs/provider_credentials_dialog.py` `_save`: with no deployment it calls `put_provider_credential`, which writes at **application** scope.
- ENG-002's application-scope DigitalOcean credential is `crmbuilder-eng002-readonly (cbm team, read-only)`, which Cleveland's deployments DPL-001 (crm-test) and DPL-002 (production) read through. Saving the Association's token there replaces Cleveland's — the hazard the chapter network recorded on 09-23-26 (`cbm-client-intake/prds/chapter-network/TASKS.md`, G1 item 14), which happened once and was repaired.
- Left alone, the run would use Cleveland's read-only token against Cleveland's team and fail.

Every chapter after the Association meets the same wall: each deploys ENG-002 into its own account (DEC-1155, a deployment holds its own credentials).

## What this session is for

Follow this repository's own process: requirement-first, a confirmed requirement and an implementing planning item before any code. Read `CLAUDE.md` first. The outcome to reach, in whatever shape the requirements session settles:

- A person can give a **not-yet-run deployment** its own DigitalOcean and Cloudflare tokens, at **deployment** scope, before the first deploy run — for example by creating the deployment record (client, purpose, hosting provider) first, or by having the wizard create it at step 1.
- The deploy wizard never writes a token at application scope while a deployment is being prepared for a client other than the application's defining client, or warns plainly before it does.
- The run uses the deployment's own tokens, and the application's credential stays untouched.

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
