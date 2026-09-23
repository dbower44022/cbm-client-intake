Opening answer: Define and build a requirement — the deployment wizard must deploy a CRM for a client whose DNS is not at Cloudflare.

# Kickoff — CRMBuilder deployment wizard with DNS at any provider

**Revision:** 1.0 · **Last Updated:** 09-23-26 10:09 · **Author:** Claude (Claude Code, in cbm-client-intake), for Doug

This prompt opens a session in the CRMBuilder repository. It carries no
authority to skip that repository's process: the requirement is confirmed and a
planning item exists before any code, every commit carries its `Governed-By`
trailer, and the work is recorded in the store as it happens.

## Why this is needed today

The Boston Business Mentors chapter is being deployed today (2026-09-23). Its
domain, `bbmentors.org`, is registered at Squarespace Domains and its DNS is
hosted there (name servers `nsc1`–`nsc4.squarespacedns.com`). The domain also
has DNSSEC switched on. Moving the DNS to Cloudflare would take two to three
hours and would put a change on Boston's live email and website, so Doug chose
to have the wizard support Boston's DNS where it is instead (2026-09-23).

This amends the chapter network's 2026-09-18 ruling that every chapter's DNS
lives in a Cloudflare account the chapter owns: Cloudflare stays the supported
automatic path, and a chapter may keep its existing DNS provider.

## What the code does today (read-only review, commit `736629f1`)

All paths are under `crmbuilder-v2/src/crmbuilder_v2/`.

- `deploy/runner.py` `_phase_validate` (line ~333) refuses to start without a
  `cloudflare` provider credential, and reads the Cloudflare zone named in the
  spec.
- `deploy/runner.py` `_phase_create_dns` (line ~429) writes the A record through
  the Cloudflare application programming interface (API).
- `deploy/runner.py` `_phase_wait_dns` (line ~437) polls public resolvers
  (`resolve_a_public`), not Cloudflare. It already works with any DNS provider.
  Its limit is `dns_wait_seconds = 600`.
- `deploy/runner.py` `_phase_create_instance` (line ~569) records
  `dns_provider="cloudflare"` unconditionally. The deploy configuration already
  has a `dns_provider` column.
- `deploy/spec.py` requires `zone_id`, `zone_name` and `subdomain`.
- The certificate is issued on the server (`letsencrypt_email`), so it does not
  depend on the DNS provider once the address resolves. Confirm this in the
  session.
- Runs are resumable: a finished phase is skipped on a re-run (`_phase_done`).

## The requirement to confirm (strawman — elicit, do not assume)

**Manual DNS mode.** The operator can choose, per deployment, that DNS is
managed by hand at another provider. In that mode:

1. The wizard asks for the full address of the CRM (for example
   `crm.bbmentors.org`) instead of a Cloudflare zone.
2. Validation does not require or read any Cloudflare credential.
3. Once the server has its IP address, the wizard shows the exact record to
   add: type A, the name, the IP address, and a note that a proxy must be off.
   The run log shows the same record.
4. The wizard waits for public resolvers to return that IP address, with a limit
   long enough for a person to add the record at a third-party panel (suggest
   30 minutes, configurable). The run can be resumed if the limit passes.
5. The instance record stores `dns_provider = "manual"` and no DNS record
   identifier. Any teardown or clean-up path never tries to delete a Cloudflare
   record for it.
6. Cloudflare mode behaves exactly as today.

**Out of scope for today, record as its own requirement:** CRMBuilder holds one
DigitalOcean credential and one Cloudflare credential for everything
(`segments/operate/repositories/provider_credentials.py`,
`get_provider_credential(session, provider)`, no engagement scope). The
2026-09-18 ruling says a chapter is built with its own tokens. Today's
workaround is to replace the global DigitalOcean credential with Boston's for
the build and restore Doug's afterwards.

## Definition of done for today

- The requirement confirmed and the planning item recorded in the store.
- The change built with tests, merged under the repository's own process.
- One dry run of the wizard in manual DNS mode, as far as the first phase that
  would spend money, before Boston's real run.

## What happens next, outside this session

The Boston install resumes in the cbm-client-intake repository at deployment
guide step 9.2, with the wizard in manual DNS mode, the `crm.` record added in
Squarespace's DNS panel, and the `apps.` record for step 11.10 added there too.

## Change log

| Revision | Date | Change |
|---|---|---|
| 1.0 | 09-23-26 10:09 | First version, after Doug chose option C (build the wizard change before the Boston install). |
