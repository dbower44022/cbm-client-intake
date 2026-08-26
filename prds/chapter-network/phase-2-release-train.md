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

## Cadence — ruled weekly (Doug, 2026-08-26)

**The train leaves weekly, and the soak is the week itself.** Every merge lands on
staging immediately; once a week a tag is cut and every chapter moves to it
together. A security fix may bypass the cadence — never staging.

Two consequences worth designing around rather than discovering:

- **Weekly needs a day**, and the day is not a detail. Cutting late in the week
  means a bad promotion is discovered by a chapter's staff on a Monday with
  nobody having watched it land. **Recommend cutting Tuesday or Wednesday**, so
  the people who can roll it back are at their desks for the two days that
  matter. Doug's to override; it does not block the build.
- **A week is short enough that the tag has to be cheap to cut.** If cutting a
  release is a half-hour ritual, fifty of them a year will not happen and the
  cadence quietly becomes "when someone remembers". Tag cutting and the image
  stamp (Stamp A) should be one command.

## Open

- **Which machine is the staging tenant** — [TASKS.md](TASKS.md) § D4. Nothing in
  this phase except the soak itself waits on it; tag cutting, `deploy_on_push`
  and the pinned-tag deploys are all independent of where staging lives.
- **`deploy_on_push` left on at a chapter** is named in the risk list as one of the
  ways this whole plan fails quietly. Whatever this phase builds, that specific
  setting needs a detector in the [fleet console](phase-5-fleet-console.md), not
  just a line in the onboarding runbook.
