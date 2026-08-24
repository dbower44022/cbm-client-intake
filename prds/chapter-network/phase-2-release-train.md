# Phase 2 — The release train

**Status: not started, and the repo has zero git tags** — so the train's tag is
not merely unreported, it has never been cut.

**Why it comes early.** It must precede the first real member, because taking
`deploy_on_push` off a chapter's app after that chapter has learned to expect
immediate delivery is far harder than never granting it. It is also the phase that
gives *this* project a lane of its own: today all three CBM apps track `main` with
`deploy_on_push: true`, so there is no branch-level gate on anything, chapter work
included.

**What this phase owns that Phase 1 does not:**

- **Stamp A, the release tag** — cutting it, baking it into the image as a build
  arg (a container has no `.git`), and surfacing it at `/healthz` as `releaseTag`,
  null on an untagged dev build. It does **not** replace `version`: `version`
  answers "what code is this", `releaseTag` answers "what promotion is this", and
  after a hotfix rebuild those differ. Defined in
  [interface-contract.md](interface-contract.md#the-two-version-stamps-and-where-each-comes-from).
- **The apply step.** An earlier draft had the CRM applier running inside each
  chapter's PRE_DEPLOY job; [Phase 1](phase-1-crm-config.md) moved it here, so that
  CRM admin credentials are held by the services org and never resident in a
  chapter's app spec. The promotion still moves app image and CRM configuration
  together, as ruling 7 requires — it moves them from the train rather than from
  the app.
- **The invariant that makes both stamps worth having**: a promotion pins a
  **pair**, `(releaseTag, standardVersion)`, and an instance is conformant when it
  holds the pair the train pinned, not when each half is independently plausible.

---

## The release train (ruling 7)

- **Merge → staging.** The services org runs a full staging deployment (app +
  CRM). Every merge lands there immediately; that is where "immediate" now lives.
- **Soak, then ship.** On a fixed cadence, a tag is cut and **every chapter moves
  to it together** — app image and CRM configuration in the same promotion.
- **`deploy_on_push` comes off chapter apps.** They deploy the pinned tag. This is
  the single largest operational change in the plan, and the one most likely to be
  missed at onboarding.
- **Rollback** is re-pinning the previous tag. Feature flags stay what they are —
  the mechanism for dark-shipping within a release, not the release gate.
- **An emergency path** for security fixes bypasses the cadence but not staging.


---

## Open

- **Cadence is unruled** — [DECISIONS.md](DECISIONS.md) proposal 1 (weekly, with
  the soak being the week itself) and proposal 2 (the staging instance is CBM's
  current crm-test app, repurposed rather than newly stood up).
- **`deploy_on_push` left on at a chapter** is named in the risk list as one of the
  ways this whole plan fails quietly. Whatever this phase builds, that specific
  setting needs a detector in the [fleet console](phase-5-fleet-console.md), not
  just a line in the onboarding runbook.
