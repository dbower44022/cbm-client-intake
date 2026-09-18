# What the consumer requires — a chapter onboarding app in CRMBuilder

**Version:** 0.1
**Status:** Draft — candidate input for a CRMBuilder requirements session
**Owner:** Doug Bower
**Last Updated:** 09-18-26 17:20

**Written 2026-09-18 in `cbm-client-intake`, for a requirements session in
`~/Dropbox/Projects/crmbuilder`.** It is stored here, not there, for the same reason
as `crmbuilder-deployment-updates-requirements-v0.1.md`: adding a file to a governed
repository is an act that repository governs. CRMBuilder's founding rule is that a
confirmed requirement and an implementing planning item exist before any code.
Nothing here is either. This document says what the consumer needs and why; the
shape of the requirement is that session's to write.

**Origin.** Doug, 09-18-26: *"write an app that interviews the user to provide
information and decisions, and then automates the entire process."* Discussed the
same day. The ruling was: the app belongs in CRMBuilder, beside the deployment
wizard it already has and the fleet console proposed on 08-31 (proposal 8 in
`prds/chapter-network/DECISIONS.md`). The New Chapter Deployment Guide becomes the
app's specification, held as data.

---

## The consumer's world, in six facts

1. **A chapter is built in 18 stages and about 155 steps**, from a legal organization
   to a running, supported system. They are held as structured data, one YAML file
   per stage, in `prds/chapter-network/deployment-guide/steps/`. Each step has a
   finishing test, the people who do it, the steps that must come first, the
   information it needs and produces, its actions, and a check. The field meanings
   are in that folder's `README.md`. The same data renders the readable guide
   (`scripts/render_deployment_guide.py`).
2. **Each step is marked with what an app can do with it.**
   - `automated`: the app does it.
   - `guided`: a person does it, the app instructs them, then checks the result.
   - `offline`: a person does it outside any system, and the app only records it.

   Roughly half the steps are automatable. Account sign-ups, payment, the Google
   administrator's permission grant, and the legal and training steps are not.
3. **Every chapter owns its own infrastructure** (ruling 5): its DigitalOcean
   account, its Cloudflare account, its Google Workspace and its Proton Pass vault.
   The central support organization works inside them by the chapter's grant, and
   either side can walk away without destroying the other.
4. **CRMBuilder already builds a chapter's CRM** with DigitalOcean plus Cloudflare,
   its only provider pair (DEC-946, REQ-522 / PI-419). Ruled 09-18-26: for a chapter
   it always uses the chapter's own tokens, never CRMBuilder's own default.
5. **Secrets live in the chapter's Proton Pass vault** (ruled 09-18-26). Proton Pass
   has a command-line tool that injects secrets into scripts and deployments. The
   consumer's settings generator is to read secrets from it and write them nowhere.
6. **Half the steps have never been done for real.** They include the Google
   connection, loading existing records and the website stages. Their data is
   marked `not-yet-tried`. The consumer's rule is to automate only what has been
   done once by hand.

## What is asked for

### O1 — An interview driven by the step data

The app asks the chapter for the information each step `needs`, at the point the
step needs it, and never twice. Its questions come from the step data, not from
code, so a change to the guide changes the interview. It records each answer with
who gave it and when. Secrets are never typed into the app; they are named, and
their value lives in the chapter's vault.

### O2 — Automated steps, run with the chapter's own credentials

For each `automated` step, the app does the work using the chapter's own
credentials: the DigitalOcean token, the Cloudflare DNS token, the CRM's
administrator account and keys read from the vault. It never falls back to
CRMBuilder's own accounts for a chapter. A failed step keeps what it built and
reports the phase, as the deployment wizard already does.

### O3 — Guided steps with automatic checks

For each `guided` step, the app shows the actions, then runs the step's
`check.probe` to confirm the person's work. Examples: a name-server lookup
confirms the domain is on Cloudflare, and Google confirms the domain is verified.
Checking a person's step automatically is as valuable as doing the step, because
it is the "how you know it worked" line run by a machine.

### O4 — A durable, resumable progress record per chapter

One record per chapter shows every step's state: not started, in progress, done,
checked, or blocked with its reason. The build can stop and resume across days and
people. The record shows the order the step data sets out (`first`), and refuses
to start a step whose prerequisites are not done.

### O5 — Only proven steps are automated

A step marked `not-yet-tried` runs as `guided` even if its target mode is
`automated`, until a person has done it once and the data says so. The first real
chapter is the rehearsal for those steps. The app records what actually happened,
so the step data can be corrected.

### O6 — The step data is read from the consumer's repository, by version

The app reads the step data from `cbm-client-intake`, pinned to a named release, so
a chapter's build follows one version of the guide from start to finish. CRMBuilder
does not keep its own copy of the steps.

## How this relates to what already exists

- **The deployment wizard** (REQ-522 / PI-419) is stage 9's steps 9.2 to 9.6
  already built. It becomes one automated run inside the larger process.
- **Proposal 8, the fleet console** (Deployment record, update policy, Update button)
  covers the chapter after it is running. This app covers getting it there. They
  share the chapter's record.
- **The CRM configuration applier** (Phase 1, ruled 08-31 to live in CRMBuilder) is
  steps 9.8 to 9.19. Until it exists, those steps run through the consumer's trial
  scripts, and the app treats them as `guided`.

## Not asked for

- Creating a chapter's accounts at Google, DigitalOcean, Cloudflare, Proton Pass or
  a registrar. Those need a person to sign up, verify their identity and pay.
- Anything about legal formation, the agreement, or policy documents beyond
  recording that they are done.
- Holding any secret value inside CRMBuilder.

## Open for the session

1. Whether the chapter's own people use the app, or only the central support
   organization on their behalf.
2. How the app authenticates to a chapter's Proton Pass vault without holding a
   standing credential.
3. Whether the progress record is the same record as proposal 8's Deployment
   record, or one beside it.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First draft, from Doug's direction on 09-18-26 that an app should interview the chapter and automate the process, and the ruling that it belongs in CRMBuilder with the deployment guide as its specification. |
