# Kickoff prompt — the dress rehearsal: a throwaway CRM, the full application suite, a real non-admin

**Written 2026-08-31. For a fresh Claude Code session rooted in
`cbm-client-intake`.** This session executes **Phase 1's acceptance criterion
13**, which is also **Phase 6's dry run**: stand up a throwaway EspoCRM, bring
it to the CBM standard, prove conformance mechanically, put the whole
application suite in front of it, and verify as a **real non-admin** in each
gated team. Nothing about this rehearsal involves a chapter, and nothing it
touches is Cleveland production or crm-test.

**What changed to make this runnable now.** CRMBuilder can provision the CRM
itself: its admin-driven deployment feature shipped and reached production on
2026-08-31 (CRMBuilder REQ-522, ratified by a four-run live proof, DEC-956).
The rehearsal's step 1 — "provision the EspoCRM instance on a droplet" — is now
a wizard in the CRMBuilder desktop that creates the server, DNS record and
certificate, installs the CRM, verifies it, and registers the instance. Doug
drives that wizard (it is admin-only and human-paced); this session guides him
with the CRMBuilder from-zero guide and owns everything after it.

---

## The prompt

Execute the dress rehearsal end to end, with Doug at the wheel for every
console and wizard action (follow his instruction-discipline: one action per
step, exact labels, expected result, "stop and tell me" on mismatch). Your
deliverables are (a) the rehearsal executed, (b) an honest findings record of
every gap between the plan's paper and what actually happened, filed where
this repo's conventions say findings go, and (c) the phase files updated only
where execution proved them wrong.

### Read first

1. This repo's `CLAUDE.md`, in full.
2. `prds/chapter-network/phase-1-crm-config.md` — especially the acceptance
   criteria and the *Measured* sections; criterion 13 is your mission.
3. `prds/chapter-network/interface-contract.md` — C1–C6. You are not building
   the applier, but everything you apply gets scored against this contract's
   outcome categories, including CRMBuilder's `NOT_SUPPORTED` items.
4. `prds/chapter-network/phase-6-first-chapter.md` — the runbook this
   rehearsal rehearses; note which of its six steps are in scope (below).
5. `prds/chapter-network/chapter-values.md` — the per-chapter values; the
   rehearsal fills one in for a fictional chapter.
6. `prds/chapter-network/crm-update-runbook.md` § 7 (the traps) before
   touching any CRM configuration.
7. `DEPLOYMENT.md` and `.do/app.yaml` (the reference spec shape);
   `SANDBOX-RESET.md` only for what it teaches about what lives in files vs
   the database.
8. `scripts/preflight_crm.py` — read the module docstring and the exit-code
   table; this is your conformance judge.
9. In `~/Dropbox/Projects/crmbuilder` (read-only for this session):
   `crmbuilder-v2/docs/from-zero-to-deployed-crm.md` (the deploy path Doug
   will follow) and `crmbuilder-v2/docs/live-proof-desktop-crm-deployment.md`
   § 8 (what the deploy feature is proven to do and its known minor findings).

### Scope — Phase 6's six steps, rehearsed as four

1. **CRM.** Doug deploys a throwaway CRM with the CRMBuilder desktop
   (from-zero guide sections 5–6; a throwaway subdomain on a zone he
   designates — never a real chapter's name). Success bar: the deploy run
   succeeded, HTTPS answers, admin login works.
2. **The standard.** Bring the empty instance to the CBM standard
   configuration. The plan's applier does not exist yet, so this step is
   *also a measurement*: decide with Doug which combination applies it —
   the CRM team's Entity-Manager-file baseline, the repo's own scripts
   (`migrate_event_schema.py`, `sync_form_options.py`), CRMBuilder publish
   from a design, or documented hand-work — and record, per configuration
   category, which mechanism carried it and which category had none
   (contract category `unapplyable`). This record is the rehearsal's most
   valuable output. Gate: `scripts/preflight_crm.py` against the new
   instance exits 0, or every non-zero is explained line by line.
3. **The app.** Put the application suite in front of the new CRM. Default
   to the cheapest honest wiring and confirm it with Doug before building:
   repoint the dev app (`lobster-app`, currently dry-run) at the throwaway
   CRM with dry-run off, using a values file written per `chapter-values.md`
   for the fictional chapter. A fresh App Platform app from the spec
   template is the fuller rehearsal of Phase 6 step 4 — offer it as the
   alternative with its cost. Migrations must run before first boot
   (PRE_DEPLOY `migrate`); `/healthz` is the deploy marker and its
   `crmConfig` block should read the throwaway's stamp or `absent` —
   distinguish, don't collapse.
4. **Verification and teardown.** Create the chapter's non-admin roles,
   teams and at least one real non-admin user per gated team; open every
   gated app as that user; submit at least one public form end to end and
   see its records land in the throwaway CRM. Admins bypass ACL — an
   admin-only test proves nothing and does not count. Then tear everything
   down: the throwaway droplet, DNS record and SSH key (CRMBuilder's guide
   § 6 names what a run creates), the app repoint reverted, nothing left
   billing, and the dev app back to dry-run.

**Out of scope, deliberately:** Google Workspace integration (branch A/B is a
chapter decision; run with those flags dark and record that they were dark),
the website/plugin step (Phase 6 step 5 — no chapter website exists), the
release train and spec generator (Phases 2–3 — measure what they'll need,
build nothing), and any change to Cleveland prod or crm-test.

### Rules

- **Do not reopen rulings.** `prds/chapter-network/DECISIONS.md` is settled;
  execution findings go to the phase files and TASKS, not into re-argument.
- **Doug's consoles, Doug's hands.** DigitalOcean, Cloudflare, the CRMBuilder
  desktop, App Platform: you write the steps, he clicks. Follow his
  instruction-discipline skill for every instruction you give.
- **Secrets:** never into a committed file; mind the overlay-regeneration
  trap ([[overlay-regen-encrypts-secrets]]) before touching any `.do` spec.
- **Findings home:** chapter-network findings → `prds/chapter-network/TASKS.md`
  (its three-part entry format); Cleveland defects the rehearsal merely
  *finds* → `OPEN-ITEMS.md`. CRMBuilder defects → report to Doug for the
  CRMBuilder repo's requirement-first process; do not fix them from here.
- **Close with evidence.** When the rehearsal completes, criterion 13's entry
  moves to TASKS *Closed* with the evidence: the preflight JSON, the
  non-admin verification list, the applier-coverage record, and the teardown
  confirmation.

### Open questions to settle with Doug before step 2

1. Which zone hosts the throwaway CRM's name, and what fictional chapter
   name/values fill the chapter-values file?
2. Which applier combination attempts the standard (step 2) — and is
   CRMBuilder-publish-from-a-design in or out of this rehearsal?
3. Dev-app repoint or fresh App Platform app for step 3?
4. Budget/urgency: the rehearsal holds one droplet (~$24/mo prorated) and
   possibly one extra App Platform app while it runs.
