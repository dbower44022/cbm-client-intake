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

## Cadence — ruled weekly, Sunday 17:00 UTC (Doug, 2026-08-26)

**The train leaves every Sunday at 17:00 UTC, and the soak is the week itself.**
Every merge lands on staging immediately; at the Sunday slot a tag is cut and
every chapter moves to it together. A security fix may bypass the cadence —
never staging.

**Worth stating once, because the slot was described as "Sunday night": 17:00 UTC
is Sunday *afternoon* in Cleveland** — 13:00 EDT in summer, 12:00 EST in winter.
It is evening in the UK (18:00 BST / 17:00 GMT) and Sunday night in central
Europe. If the intent was "late enough that nobody is working", the Cleveland
slot is the middle of Sunday; if the intent was a UTC-evening window that suits a
future non-US chapter, it is exactly right. Recorded as ruled either way — the
step-by-step procedure in [crm-update-runbook.md](crm-update-runbook.md) uses
17:00 UTC throughout.

The choice has one thing going for it that a weekday slot does not: **the CRM
half of a promotion is the risky half**, and Sunday is the day with the fewest
staff mid-transaction in a CRM being altered underneath them.

Two consequences worth designing around rather than discovering:

- **The day is settled and it is Sunday**, which trades away the thing a midweek
  cut buys — people at their desks when it lands — for the thing Sunday buys, an
  empty CRM at the moment it is altered. That trade is fine, but it means
  **nobody is watching by default**, so the promotion has to report its own
  outcome rather than relying on someone noticing. The conformance check's JSON
  result and the fleet console are what make an unattended Sunday cut safe; until
  those exist, a human confirms the Monday-morning state (runbook step 12).
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
