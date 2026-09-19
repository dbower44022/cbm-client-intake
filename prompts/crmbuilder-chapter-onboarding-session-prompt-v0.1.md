# Kickoff prompt — a chapter onboarding app in CRMBuilder

**Version:** 0.1
**Status:** Ready to run
**Owner:** Doug Bower
**Last Updated:** 09-18-26 23:50

**Written 2026-09-18 in `cbm-client-intake`, to be run in a Claude Code session
rooted at `~/Dropbox/Projects/crmbuilder`.** It is stored here, not there, because
adding a file to a governed repository is an act that repository governs. Paste the
prompt below as the session's first message.

**This prompt asks for requirements work, not a build.** CRMBuilder's founding rule
is that a confirmed requirement and an implementing planning item exist before any
code. The session ends at approved requirements and an approved planning item. The
build is a later session under that planning item.

---

## The prompt

Opening answer: Define the requirements for a chapter onboarding app — an interview
that collects a new chapter's information and decisions, and then builds the chapter's
system by automating the steps that can be automated.

**Orient first.**

1. Read this repository's `CLAUDE.md` in full.
2. Complete the session bootstrap it specifies. The database is the source of truth
   for rules, preferences and lessons.
3. Read the two existing records this work builds on:
   - REQ-522 / PI-419, the deployment wizard that already provisions a CRM on
     DigitalOcean with Cloudflare DNS;
   - DEC-946, which made DigitalOcean plus Cloudflare the only provider pair.

**Read the consumer's material.** It lives in the separate repository
`~/Dropbox/Projects/cbm-client-intake`. Treat that repository as read-only: read
its files, never edit them, and never commit there.

1. `prompts/crmbuilder-chapter-onboarding-requirements-v0.1.md` — what the consumer
   needs, and why. Start here. It lists six asks, O1 to O6, and three open questions.
2. `prds/chapter-network/deployment-guide/steps/README.md` — the format of the step
   data the app would run from.
3. Two stage files as examples:
   - `prds/chapter-network/deployment-guide/steps/stage-09.yaml` (building the CRM:
     mostly automated, and done for real);
   - `prds/chapter-network/deployment-guide/steps/stage-04.yaml` (Google Workspace:
     entirely person-led, and never done).
4. `prds/chapter-network/DECISIONS.md` — the network's rulings. Rulings 2, 4, 5, 6
   and 7, proposal 8, and the decision log entries dated 2026-09-18 matter most.
5. `prompts/crmbuilder-deployment-updates-requirements-v0.1.md` — the earlier
   request for a fleet console (proposal 8). The onboarding app covers getting a
   chapter running; the fleet console covers it once it runs.

**What the consumer has already ruled.** Treat these as fixed inputs, not open
questions.

- Every chapter owns its own DigitalOcean, Cloudflare, Google Workspace and Proton
  Pass accounts. The central support organization works inside them by the chapter's
  grant.
- CRMBuilder builds a chapter's CRM with the chapter's own DigitalOcean and
  Cloudflare tokens. Its own default tokens are never used for a chapter.
- Secrets live in the chapter's Proton Pass vault. Proton Pass has a command-line
  tool that can inject secrets into scripts and deployments. CRMBuilder never holds a
  secret value.
- The consumer's step data is the specification. CRMBuilder reads it from the
  consumer's repository, pinned to a named release, and keeps no copy of its own.
- Only steps that have been done once by hand are automated. Each step's `status`
  field says which those are.

**What to produce, under this repository's governance.**

1. One or more requirements, each within this repository's requirement rules. They
   should cover:
   - the interview driven by the step data;
   - running automated steps with the chapter's own credentials;
   - guided steps with automatic checks;
   - a resumable progress record per chapter;
   - automating only proven steps;
   - reading the step data by release.
2. A decision on each of the consumer's three open questions, or a recorded reason
   it stays open:
   - whether the chapter's own people use the app, or only the central support
     organization;
   - how the app reaches a chapter's vault without a standing credential;
   - whether the progress record is proposal 8's Deployment record or sits beside
     it.
3. The relationship to the existing deployment wizard and to the Phase 1
   configuration applier, recorded as decisions. The wizard already does steps 9.2
   to 9.6. The applier, which lives in CRMBuilder by the 08-31 ruling, would do steps
   9.8 to 9.19.
4. A planning item implementing the approved requirements, inside a project and a
   release, with its slices named. Do not start a slice.

**Constraints.**

- Write no code in this session.
- Ask Doug for each approval this repository's process requires. Do not assume one.
- Any gap between what the consumer asks for and what CRMBuilder can do goes to Doug
  as a question, not into a requirement as a guess.
- Report at the end:
  - the requirement, decision and planning item identifiers created;
  - anything in the consumer's material that looked wrong or incomplete.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 23:50 | First version, written after Doug asked on 09-18-26 for the CRMBuilder session prompt for the chapter onboarding app. |
