# Continue the chapter-network work — session prompt, 2026-08-29

Paste everything below the line into a fresh session rooted in
`cbm-client-intake`. It assumes nothing from the previous conversation.

---

You are continuing the **chapter network** project in this repository: the
architecture by which other mentoring organizations would run this software,
with every chapter holding identical configuration and a weekly release train
moving all of them together.

## Read first, in this order

1. `CLAUDE.md` — auto-loaded. Its *Current status* block names the four things
   still owed from the 2026-08-28/29 releases.
2. `prds/chapter-network/README.md` — the project's own anchor. Then
   `DECISIONS.md` (the eight rulings; do not re-litigate them) and `TASKS.md`
   (every open item, each with steps). Read the *Closed* section of TASKS too —
   it records what the last two sessions did and what they found.
3. Only then the phase file for whatever you work on.

Work Doug's way: prose and a recommendation, one question at a time, never a
menu of options. Verify a premise against the live system before asking about
it. Commit locally; **Doug pushes** — except that he has been saying "push" in
chat, and when he does, `git push origin main` and any new tag. Remember that
**a push deploys dev, crm-test AND production**: check `git log
origin/main..main` before every push and say what it will carry.

## Where things stand — verified 2026-08-29 06:30 UTC

**All three apps run v0.216.1, healthy, workers alive, backlogs empty.** Two git
tags exist: `v0.214.0` and `v0.216.1`. `deploy_on_push` is still on everywhere,
deliberately — turning it off is Phase 2's real work and has not started.

In the last two days the project produced its first application code since the
conformance check on 2026-08-21:

- **Both version stamps are live at `/healthz`** — `releaseTag` (which promotion)
  and `crmConfig` (what configuration the CRM holds, from `CNetworkStandard`,
  with `absent`/`forbidden`/`unreachable` kept as three distinct states). **Both
  ship inert**: `releaseTag` is `null` and `crmConfig.state` is `disabled` on
  every app until the overlay switches are applied.
- **`scripts/cut_release.sh`** cuts an annotated tag in one command and refuses
  to move a published one. **`scripts/capture_roles.py`** reads a CRM's roles
  and teams, read-only, admin-only, and refuses a partial capture.
- **The Settings page holds every setting and every one is editable** unless a
  change is genuinely impossible (Doug's two rulings of 2026-08-28, recorded in
  `CLAUDE.md` § System Settings). `core/boot_overrides.py` loads overrides
  before `create_app` mounts anything; `setup/verify.py` probes a value before
  storing it, checks the system after, and gives lockout-capable keys a
  10-minute confirm-or-revert countdown that sweeps in both processes. Secrets
  are editable, encrypted, never readable. The denylist is three keys.

The two overlay files (`.do/app.prod.yaml` = **crm-test**, `.do/app.prod-crm.yaml`
= production; gitignored, plaintext secrets, **never regenerate them from
`doctl apps spec get`**) already carry `RELEASE_TAG: v0.216.1` at
`RUN_AND_BUILD_TIME` scope and `CRM_CONFIG_REFRESH_SECONDS: "300"`. They have
not been applied.

## What is owed, in the order to do it

**1. Sunday 2026-08-30, 17:00 UTC — production's `CNetworkStandard`** (TASKS
§ R0, steps 6+). Doug's hands in the CRM; you read back the verification. Follow
`crm-update-runbook.md` — this is the first change ever to ride it, chosen
because five scalar fields with no links cannot cascade. Type the entity name
**without the leading C** (EspoCRM prepends it; typing it yields `CCNetworkStandard`).
Grant the org-wide API role **read** on the scope — the step missed on crm-test.
Verify as the API key, not as an admin: `GET /api/v1/CNetworkStandard` must be
HTTP 200 with `total: 0`. Confirm the shape from `GET /Metadata`, never a screen.
If the timing is missed, it waits a week — the slot is ruled, not suggested.

**2. The two `doctl` applies** (TASKS § R6). Doug runs them, crm-test first:
`doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml`,
then production with `aa1ddf69-f359-4b53-91ba-035cbed7bd53` and the other file.
Before each, confirm the `RELEASE_TAG` value in the file matches the tag you
mean to report — it goes stale every time the version bumps, and it already did
once. Afterwards `/healthz` on crm-test should read `releaseTag: v0.216.1` and
`crmConfig.state: unstamped`; production reads `absent` until step 1 is done,
and **that is correct, not a fault**. Watching it flip is the reader's first
live proof.

**3. The roles capture** (TASKS § R4). Doug runs
`.venv/bin/python scripts/capture_roles.py --indent 0` in the DigitalOcean
console of the crm-test app, then production, and pastes both outputs. You
build the comparison table — one row per (role × entity scope), three columns:
crm-test, prod, and a blank *standard* — and hand it back with only the
disagreements needing a ruling. This feeds **the project's only dated
commitment**: the CRMBuilder requirements session by **2026-09-19** (TASKS
§ A1, Doug's). Do not let it slip past the session.

**4. The live pass for the verified-settings path** (`OPEN-ITEMS.md` #20, the
new bullet). It has run only in tests and a stub harness. The one that matters:
toggle *This Settings page* off on crm-test and **let the countdown expire for
real**. Nobody has watched the revert happen, and it is the mechanism the
whole ruling rests on.

**5. Only then, the deploy gate** (TASKS § R2): `preflight_crm.py` as a
PRE_DEPLOY job on crm-test with a `CRM_GATE_BYPASS` break-glass, proving all
three behaviours on a real deployment. It edits the live overlays, which is the
step where a mistake costs an outage — after Sunday, not before.

## Do not

- Do not delete or move a published git tag. It was tried, correctly refused,
  and both tags stay.
- Do not put a page width cap anywhere. Do not disable or hide an action button.
- Do not read `.env` with a shell; `source` leaks password punctuation.
- Do not invent friendlier synonyms for things that have a name on screen. It
  is a "release tag", not a "release marker" — that mistake cost a confused
  status report.
- Do not add a setting to the denylist. The rule is now the opposite: editable
  with verification, and a refusal must name a reason that is impossible, not
  merely risky.
