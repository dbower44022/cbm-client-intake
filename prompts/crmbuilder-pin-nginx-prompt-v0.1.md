# Kickoff prompt — pin the CRM server's NGINX image (CRMBuilder)

Last Updated: 11-20-26 23:26 · Revision 0.1 (draft for Doug's approval)

> Opening answer: Define and build a fix so a newly installed CRM server pins its NGINX image to an exact version instead of the bare `nginx` image.

Operating mode: DETAIL.

## Why this session exists

On 11-18-26 two critical NGINX flaws were disclosed: CVE-2026-123007 and CVE-2026-123633, part of the group called "NGINX2Root". Both are rated 9.2 and both let an unauthenticated attacker run code over HTTP/2. The fixed releases are NGINX 1.31.9 (mainline) and 1.30.7 (stable).

On 11-20-26 every CRM server that CRMBuilder had installed was running an affected version, with HTTP/2 switched on:

- crm-test: 1.29.7
- Cleveland production: 1.31.1
- Boston: 1.31.6
- Lakeside: 1.31.4
- the Business Mentors Association: 1.31.8

The cause is a single line in each server's `/var/www/espocrm/docker-compose.yml`, which names the image as the bare `nginx`. That means "whatever was latest on the day the server was built". Nothing ever pulls it again, so each server stays on its build-day version for good.

On 11-20-26 the cbm-client-intake repository patched all five servers by hand with `scripts/patch_nginx2root.sh`, pinning each to `nginx:1.31.9`. Read that script before designing anything. Its tested order is: pull the image; run `nginx -t` in a throwaway container on the live container's network, with the live container's environment variables and a temporary log folder; only then edit the compose file and recreate `espocrm-nginx`. Three things were learned on crm-test:

- The configuration is a template. The image fills in `$NGINX_HOST` and similar values from the container's environment, so a test without that environment fails with `unknown "nginx_host" variable`.
- The live log folder is mounted, so a read-only test needs a temporary log folder.
- The `listen ... http2` lines are deprecated in favour of the `http2` directive. This is a warning only.

## What the installer does today (verified 11-20-26 by reading the code, not run)

CRMBuilder does not write the NGINX image itself. It runs EspoCRM's own installer, `install.sh`, from `automation/core/deployment/ssh_deploy.py` (line 242: `sudo bash install.sh -y --clean --ssl --letsencrypt …`). The certificate job in `crmbuilder-v2/src/crmbuilder_v2/deploy/certificate_job.py` also runs `install.sh`. The installer is what writes the bare `nginx` image. So a fix is a step that runs after the installer, or a change to how the installer is called, not an edit to a compose file that CRMBuilder generates.

## The task

1. Follow this repository's own process first. A confirmed requirement and an implementing planning item exist before any code is written, on a branch. Record the requirement from the facts above.
2. Decide with Doug how the pinned version is chosen and kept current. A pin stops drift, but it also means each later NGINX fix is a deliberate change. Present that as a decision, using the template in `~/.claude/CLAUDE.md`.
3. Make sure the certificate job's re-run of `install.sh` cannot undo the pin.
4. Have the server record show the NGINX version, as it already reads `docker exec espocrm-nginx nginx -v` (`automation/core/deployment/record_generator.py` line 342).
5. Do not touch the five live servers. They are already pinned to `nginx:1.31.9`.

## Out of scope

- The EspoCRM image pin. This was already done by hand on 10-22-26 for PHP2Shell.
- The docs server. It runs BookStack, not a CRMBuilder install.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-20-26 23:26 | Claude (Claude Code, cbm-client-intake session) | First draft, written after the five servers were patched by hand. |
