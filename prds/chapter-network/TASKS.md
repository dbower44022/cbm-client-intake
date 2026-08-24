# Chapter network — open work

Every entry below has the same three parts, in the same order:

1. **What this is** — the issue in plain language, long enough to be understood
   by someone who has not just read the plan.
2. **The decision**, where there is one — the options, what each costs, and a
   recommendation.
3. **Steps** — what to actually do, in order.

Newest work goes to the top of its section. Finished work moves to *Closed* at
the bottom **with the evidence**, not deleted.

**What belongs in this file:** work owed by a chapter-network phase.
**What does not:** a Cleveland defect that chapter work merely *found*. Those go
to `OPEN-ITEMS.md`, where the people who fix Cleveland defects are looking. There
is a table at the end of this file linking to them.

---

# Part 1 — Decisions waiting on Doug

Each of these blocks work that is otherwise ready. They are here rather than in
[DECISIONS.md](DECISIONS.md) because a task is stalled behind each one;
`DECISIONS.md` holds the organizational rulings that stall nothing.

---

## D1. Where does the CRM record which configuration version it is running?

### What this is

Every chapter runs its own EspoCRM. The whole point of Phase 1 is that all of
them hold the *same* configuration, and that we can tell at a glance which ones
have drifted. That requires each CRM to carry a stamp saying "I am running
configuration version X, applied on date Y" — the same way a database carries an
Alembic migration number.

**No such stamp exists anywhere today.** `/healthz` reports the *app* version
(read from `pyproject.toml`) but nothing at all about the CRM's configuration.
So the question "is this chapter's CRM up to date?" currently has no answer short
of a full field-by-field sweep.

Three properties decide where the stamp can live:

- It describes the **CRM**, so it must survive the app being redeployed,
  reconfigured or replaced entirely. That rules out an app environment variable.
- Only the applier is entitled to write it. An env var could be edited by anyone
  with the DigitalOcean console, and would then **lie** — worse than no stamp,
  because the fleet console would believe it.
- The app must be able to **read** it with the ordinary org-wide API key. If
  reading it needs an admin login, we have dragged CRM admin credentials into
  application runtime, which the interface contract (C2) exists to prevent.

### The decision

| Option | How it works | Cost / risk |
|---|---|---|
| **A. A single-record custom entity, `CNetworkStandard`** | A new EspoCRM entity holding one row, with fields `standardVersion`, `appliedAt`, `appliedBy`, `planFingerprint`, `appliedByTool`. | Needs a small CRM build (Entity Manager) on every instance — but the applier already drives Entity Manager, so creating it is inside the mechanism it already needs. Readable by the API key. Nothing else writes to it, so it cannot be clobbered by hand. |
| **B. A key under EspoCRM's admin Settings** | Store the version string in the CRM's own settings. | Fewer moving parts, but **reading admin Settings requires an admin login**, which breaks C2. It also shares a surface that CBM staff and the CRM team edit by hand. |
| **C. A `CActionLog` row** | Reuse the entity the app already writes to when it acts on its own initiative. | It exists already — but it is an append-only *history*, not a current-state assertion. Answering "what version is this" by scanning a log is the wrong shape, and gets slower forever. |

**Recommendation: A, and the evidence for it firmed up today.** I probed
crm-test's org-wide API key read-only: it reads custom entities and `Team` and
`EmailTemplate` fine (HTTP 200), and it gets **HTTP 403 on `Role`**. That is not
a preference — it is proof that admin-only surfaces are genuinely closed to the
credential the app runs on, so option B would not merely be inelegant, it would
not work without a second credential in the web tier.

The cost of A is one CRM build handoff, which this repo does routinely and has a
documented convention for.

### Steps

1. Write `cnetworkstandard-entity-crm-handoff.md` at the repo root, in the same
   shape as the existing handoffs (`cgrant-entities-crm-handoff.md` is the most
   recent example). It must be written in **Entity Manager vocabulary**, not
   metadata vocabulary — see [[crm-specs-use-entity-manager-terms]], and note
   EspoCRM will prepend a `C` to the entity name on its own, so type
   `NetworkStandard`, not `CNetworkStandard`.
2. Specify the five fields: `standardVersion` (varchar), `appliedAt` (datetime),
   `appliedBy` (varchar), `planFingerprint` (varchar), `appliedByTool` (varchar).
   All plain scalars; no links, no formulas, no enums to drift.
3. Build it on **crm-test** first. Grant the org-wide API role **read** on the
   new scope — that grant is the thing being tested, and it is easy to forget.
4. Verify the read works with the API key and nothing else:
   `GET /api/v1/CNetworkStandard?maxSize=1` with `X-Api-Key`. A **403 here means
   the role grant was missed**; an empty 200 with `total: 0` is the correct
   "built but never applied" state and is what you want to see.
5. Only then build it on prod, and re-verify the same way.
6. Record the outcome in [phase-1](phase-1-crm-config.md) and unblock task R1.

---

## D2. What happens on 2026-09-19, and who convenes the session before it?

### What this is

Phase 1's biggest deliverable is the **applier** — the program that takes a
description of the correct CRM configuration and makes a chapter's CRM match it.
There are two ways to get one.

- **Adopt CRMBuilder** (the separate repo). A read-only review on 2026-08-18
  found it already has most of the machinery: a CHECK→ACT deploy pipeline,
  managers for roles, teams, email templates and entity settings, and — most
  valuable of all — an **Audit** that reverse-engineers a live CRM into the same
  format the engine consumes. That Audit is the answer to the single hardest
  unknown in Phase 1 (see task R4, the roles problem), and we have nothing like
  it here.
- **Build our own**, generalizing `scripts/migrate_event_schema.py` from a
  hand-written change list into a declarative desired state plus a runner.

We cannot simply choose. CRMBuilder is governed **requirement-first** — its shape
is not ours to assume, and we cannot write a plan obliging it to grow an
interface it has not agreed to. The session that would settle it has a prompt
written and waiting (`prompts/crmbuilder-chapter-network-prompt-v0.1.md`, which
already carries our full interface contract), and **it has not been convened.**
CRMBuilder's HEAD is still `db1dbef0`, dated 2026-08-10 — nothing has moved.

**Why there is a date at all.** Without one, "wait for CRMBuilder" becomes an
indefinite block on the one phase everything downstream assumes. The proposed
date, 2026-09-19, was chosen so the decision lands *before* our own applier's
write path starts — the build order deliberately puts the conformance check and
the version stamps first, and those are safe under either answer. If we build our
own applier and then adopt CRMBuilder anyway, roughly two to three weeks of work
is genuinely thrown away: the directive executor, the plan-fingerprint plumbing
and their tests.

### The decision

Two separate things need answering, and only you can do either.

**First: will you convene the CRMBuilder requirements session, and by when?** It
needs answers to two of its own questions — is the network standard a CRMBuilder
*product capability* or a *CBM-network artifact that merely uses CRMBuilder*, and
is headless execution something it will support.

**Second: is 2026-09-19 the right date?**

| Option | What it means | Cost |
|---|---|---|
| **A. Keep 2026-09-19.** | Convene the session in the next four weeks. If it has not run by that date, we build our own applier in full and accept the sunk cost deliberately. | Requires ~half a day of your time in the next four weeks. |
| **B. Move the date out.** | More time to convene, but the applier does not start, and everything from Phase 2 onward waits on it. | Phase 1 stalls. Nothing else can fill the gap — the check and the stamps are only about four weeks of work and they are already partly done. |
| **C. Decide now, without the session.** | Rule that the network standard is a CBM-network artifact, and build our own applier starting immediately. | Loses the CRMBuilder Audit, which is the only existing answer to the roles problem. Probably means solving R4 by hand. |

**Recommendation: A, with one change — treat "convene the session" as the task
and put a date on that instead.** The trigger as written fires on a session that
nobody has scheduled, which makes it a deadline on an event rather than on a
person. A date on *your* action ("I will run this session by 2026-09-12") makes
it real; 2026-09-19 then becomes the fallback it was designed to be rather than
the only thing carrying the weight.

### Steps

1. Decide whether to convene, and put a date on it.
2. If yes: run the session using `prompts/crmbuilder-chapter-network-prompt-v0.1.md`.
   It is ready — its § *What the consumer requires* already carries C1–C10, and
   as of today it points at [interface-contract.md](interface-contract.md) so the
   session can be handed that file on its own.
3. Record the answer in [DECISIONS.md](DECISIONS.md), and update
   [phase-1](phase-1-crm-config.md) § *The decision trigger* to say which layer
   is now the plan of record.
4. Whichever way it goes, task B1 unblocks.

---

## D3. Does this product have a logo — and should it have a favicon regardless?

### What this is

The chapter plan has said from the start that per-chapter branding is
"`tokens.css` overrides plus a logo". The first half is built and shipped
(`CHAPTER_TOKENS_URL`). The second half turns out to describe something that does
not exist: **the application contains no image asset of any kind.** No `.svg`,
`.png`, `.jpg`, `.ico`, `.webp` or `.gif` outside the vendored Jodit editor, and
**no `<link rel="icon">` on any page** — every hit for "logo" in the codebase is
the word *logout*.

So "parameterize the logo" is not a find-and-replace. It is a new feature: a
header slot on 18 pages, a path that serves the asset, and a sizing contract that
stops one chapter's wide wordmark from breaking a layout that fits another's
square mark.

Worth separating out: the **missing favicon is a Cleveland defect today**, not a
chapter question. Every tab of every one of these apps shows a blank default
icon, and staff routinely have several open at once.

### The decision

| Option | What lands | Cost |
|---|---|---|
| **A. Nothing now.** | Keep the plan honest by deleting "plus a logo" from it. Chapters get colours, not marks. | Free. A chapter's staff see their colours but Cleveland's absence of a mark — which is survivable, since there is no mark today either. |
| **B. Favicon only.** | One favicon, settable per chapter, added to the shared head. Treats the real defect and gives chapters the one branding surface people actually notice. | Small. One asset, one setting, one line in the shared page head, plus the same escaping treatment `ORGANIZATION_NAME` already gets. |
| **C. Full logo slot.** | Header mark on all 18 pages, asset-serving path, sizing contract. | Real design work, and it is the first time this product would have a header image at all. Justified by chapters that may not exist. |

**Recommendation: B now, C never until a second chapter is actually real.** B
fixes something that is wrong for Cleveland today, which is the same test Phase 0
held itself to and the reason Phase 0 was worth doing at all. C fails that test.

### Steps

1. Rule on it.
2. If B: add a `FAVICON_URL` setting (empty default = today's behaviour exactly),
   inject the `<link rel="icon">` through `core/branding.py`'s existing rewrite so
   the nineteenth page cannot forget it, and extend
   `tests/test_shared_branding.py` to assert it appears on every served page.
3. Update [phase-0](phase-0-decleveland.md) § 6 and
   [DECISIONS.md](DECISIONS.md) with the ruling either way.

---

## D4. Release cadence, and which machine is the staging tenant

### What this is

Ruling 7 says all chapters move together on a release train: every merge lands on
a services-org staging instance, it soaks, then on a fixed cadence a tag is cut
and every chapter moves to that tag at once. Two details were never settled, and
[Phase 2](phase-2-release-train.md) cannot start without them.

**Cadence.** How often the train leaves. This is the number that decides how long
a finished feature waits before a chapter sees it, and therefore how much
pressure builds behind the change-request route — which is already named as the
project's top risk.

**The staging tenant.** Which machine soaks the release. Today CBM's crm-test app
is already doing three jobs: pre-production review gate, training sandbox, and
release-test environment, with a nightly reset that keeps them from ruining each
other.

### The decision

| Question | Option | Assessment |
|---|---|---|
| Cadence | **Weekly**, the soak being the week itself | Recommended. Short enough that chapters do not route around it, long enough that a bad merge is caught by real use. |
| | Fortnightly or monthly | Every extra week is pressure on ruling 4. Monthly means a chapter waits up to a month for a fix it has already seen work. |
| Staging tenant | **Repurpose CBM's crm-test** | Cheapest, and it already has the reset machinery and the training data. **But it makes CBM's sandbox the network's gate**, which is exactly the "Cleveland as landlord" shape ruling 1 was written to avoid, and it is already carrying three jobs. |
| | Stand up a new services-org instance | Costs a droplet and a DO app. Keeps the guinea pig a machine the co-op owns, which is what ruling 7 actually says. |

**Recommendation: weekly cadence, and a new instance rather than repurposing
crm-test — but not yet.** Standing up the staging tenant is only worth doing when
there is a second chapter to soak *for*. Rule the cadence now (it is free and it
shapes Phase 2's design); defer the machine until Phase 6 is in sight, and record
that crm-test is the interim.

### Steps

1. Rule the cadence.
2. Record it in [DECISIONS.md](DECISIONS.md) against proposals 1 and 2.
3. Note in [phase-2](phase-2-release-train.md) that crm-test is the interim
   staging tenant and that a dedicated instance is a Phase 6 prerequisite.

---

# Part 2 — Ready to build

No decision needed. Listed in the order the plan's own build sequence argues for
— the things that survive whatever D2 rules come first.

---

## R1. Report both version numbers on `/healthz`

### What this is

`/healthz` is how you find out what a deployment is running, and it is the deploy
marker this project already relies on. Today it answers **one** version question
and there are three.

It currently returns `status`, `version`, `environment`, `organization`,
`dryRun`, `forms`, `assignments`, `durableStore`, `database`, a `worker` block,
and a `settings` block carrying `settingsVersion` (`core/app.py:710`).

`version` comes from `core/version.py`, which reads `pyproject.toml`. That
identifies **the code**. It does not identify:

- **Which promotion this is.** After a hotfix rebuild, two deployments can carry
  the same `version` and be different builds. The release train needs to pin a
  tag and then verify that a chapter is actually running it. This repo has
  **zero git tags** — the train's tag has never been cut, so this slot is empty
  in both senses.
- **What configuration the CRM behind it holds.** Covered by D1.

The invariant that makes both worth having: a promotion pins a **pair**,
`(releaseTag, standardVersion)`, and an instance is conformant when it holds the
pair the train pinned — not when each half independently looks plausible.

Build the slots now, before there is anything to put in them. Both report `null`
until a tag is cut and a stamp is written, which is the honest reading of every
instance today, and it means the fleet console can be built against a stable
shape rather than waiting.

### Steps

1. **`releaseTag`.** A container has no `.git`, so the tag has to be baked in at
   build time. Add to the `Dockerfile`, after the `COPY . .` line:
   `ARG RELEASE_TAG=""` and `ENV RELEASE_TAG=$RELEASE_TAG`.
2. Add `release_tag: str = ""` to `core/config.py`, and return it from `/healthz`
   as `"releaseTag": settings.release_tag or None`. Empty string becomes `null` —
   an untagged dev build says so rather than pretending.
3. **`crmConfig`.** Add a block returning
   `{"version": …, "appliedAt": …, "fingerprint": …}`, **all `null`** until D1 is
   built. Read it on the same refresh loop that already serves `settingsVersion`
   rather than hitting the CRM on every health check — `/healthz` deliberately
   never pings the CRM, because a CRM outage must not take the web tier down, and
   that rule must not be broken here.
4. Add tests asserting both keys are present and null on a stock deployment. The
   point of the test is the *shape*, so the fleet console has a contract.
5. Do **not** add `releaseTag` to the footer. `version` is what a human needs
   there; `releaseTag` is for machines and the fleet console.

Acceptance criterion 11 in [phase-1](phase-1-crm-config.md) is the finish line
for the `crmConfig` half, and it cannot be fully met until D1 lands.

---

## R2. Wire the conformance check as a deploy gate on crm-test

### What this is

`scripts/preflight_crm.py` was rewritten on 2026-08-21 into a real conformance
check: it asks a live EspoCRM whether it holds everything this application
requires, needs only the org-wide API key, distinguishes *absent* from
*forbidden* from *unreachable*, and exits 0 / 1 / 3 accordingly with `--json` for
machines. It has been run by hand against both live CRMs.

**Nothing runs it automatically.** So the failure it exists to prevent — a chapter
deploying app code that expects a CRM configuration its CRM does not hold — is
still entirely possible. Wiring it as a `PRE_DEPLOY` job makes the deploy itself
fail when the CRM has drifted.

Two design points already settled, both worth understanding before you wire it:

- **The gate is a CHECK, never an apply.** Read-only, org-wide API key, no admin
  credentials anywhere near the deploy path. Applying is a release-train step
  (Phase 2) so that CRM admin passwords never live in a chapter's app spec.
- **Unreachable fails closed, but distinctly** (exit 3). A gate that passes when
  it could not check is a gate that reports success for an unknown, and silent
  passes are this codebase's documented failure mode.

A **break-glass** is mandatory, not a nicety. Without one, the first CRM outage
during an urgent app fix produces an undocumented bypass invented under pressure.

### Steps

1. Add a bypass to `scripts/preflight_crm.py`: if `CRM_GATE_BYPASS` is truthy,
   run the check as normal, log the result at WARNING with an unmistakable
   "GATE BYPASSED" line, and exit 0. Same shape as the existing
   `SETTINGS_OVERRIDES=false` break-glass. Add a test that it exits 0 on an
   instance that would otherwise exit 1.
2. Edit `.do/app.prod.yaml` (this is the **crm-test** overlay — the filenames are
   confusing; `app.prod-crm.yaml` is production). Add a second entry to the
   existing `jobs:` list, alongside `migrate`:
   `kind: PRE_DEPLOY`, `name: crm-conformance`,
   `run_command: .venv/bin/python scripts/preflight_crm.py --json`,
   `dockerfile_path: Dockerfile`, same `github:` block, and two envs —
   `PREFLIGHT_CRM_URL` and `PREFLIGHT_CRM_KEY`, set to the same values the web
   service already carries as `ESPO_BASE_URL` / `ESPO_API_KEY`.
3. **Edit the overlay in place. Do not regenerate it** from `doctl apps spec get`
   — that encrypts every plaintext secret into unreadable `EV[…]` blobs and you
   lose the local credentials ([[overlay-regen-encrypts-secrets]]).
4. Apply with `doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml`.
5. Prove all three behaviours, which is acceptance criterion 12 and the point of
   the whole exercise:
   - Deploy with the CRM conformant → the job passes, the deploy proceeds.
   - Hand-introduce a drift on crm-test (remove one required field, or rename one
     of the seven teams) → the deploy **fails** at the gate.
   - Set `CRM_GATE_BYPASS=true` and redeploy → the same drifted deploy **passes**,
     with the bypass logged.
   - Remove the drift, remove the bypass → clean deploy.
6. Leave prod alone until all four have been observed on crm-test.

---

## R3. Fix a stale count in `CLAUDE.md`

### What this is

`CLAUDE.md` line 198 says `sync_form_options.py` manages "8 lists". It manages
**16** — I counted the sentinel blocks in the tree today: 6 in
`forms/volunteer/frontend/options.js`, 6 in `client_intake`, 3 in `partner`, 1 in
`sponsor`, drawn from **14** distinct `Entity.field` sources.

Small, but `CLAUDE.md` loads into every session, so a wrong number there is a
wrong number everywhere, and this one was noticed during the Phase 1 rewrite and
never fixed.

### Steps

1. Change "8 lists are managed today" to "16 lists across 4 `options.js` files,
   from 14 distinct `Entity.field` sources, are managed today".
2. Re-derive rather than trusting me:
   `grep -rc ">>> crm-enum" --include=options.js .`

---

## R4. Capture both CRMs' roles and tabulate where they differ

### What this is

This is the largest unknown in Phase 1, and it is the one thing the conformance
check cannot help with.

The application gates every screen on **teams** — seven of them, named in
`core/config.py`. It names **no role anywhere**, deliberately: a regular user's
token cannot read its own `rolesNames`, so gating on roles was never an option
([[crm-test-assignment-acl-fields]]).

But teams are empty vessels. What a team actually *permits* is defined by the
roles attached to it, and **those definitions exist only inside the two live
CRMs**. They are not in this repo, not derivable from code, and are documented as
**divergent between crm-test and prod** — role scopes especially. So the standard
cannot be written until someone reads both, lays them side by side, and rules
which one is correct where they differ.

**Reading them is mechanical. Deciding which is right is a ruling** — and it is
yours. Doing the capture now converts an unknown into a table you can rule on in
an afternoon, and it de-risks the most expensive part of the applier.

**One hard constraint, verified today:** the org-wide API key **cannot read
roles**. I probed crm-test read-only — `Team` returns HTTP 200 with 9 teams and
`EmailTemplate` returns 200, but **`Role` returns HTTP 403**. So this capture
needs an Admin-type account, which means it cannot run from a laptop against
prod: admin CRM credentials (`ESPO_PROVISION_USERNAME` / `_PASSWORD`) exist only
on the deployed **web** component.

### Steps

1. Write `scripts/capture_roles.py` — **read-only**, no writes of any kind. It
   should log in with the provisioning admin account via `core/admin_client.py`
   (the existing shared admin login), `GET /api/v1/Role?maxSize=200`, then fetch
   each role's full record including its `data` and `fieldData` scope maps, and
   print one JSON document.
2. Run it inside the **crm-test** app's console and save the output. Use the
   pty-pipe technique in [[do-app-console-scripting]] — running it inside the
   container is the only way to reach those credentials, and it is also how you
   avoid copying an admin password onto a laptop.
3. Run the same script inside the **production** app's console and save that
   output.
4. Diff the two into a table: one row per (role × entity scope), three columns —
   crm-test's value, prod's value, and a blank *standard* column.
5. Bring the table to Doug with the blank column. Where they agree, that is the
   standard by default; only the disagreements need a ruling.
6. File the ruled table in [phase-1](phase-1-crm-config.md) as the roles half of
   the desired state.

---

# Part 3 — Blocked

## B1. The applier itself

**Blocked on D2.** This is the month-sized deliverable: the desired-state
definition generalized from `scripts/migrate_event_schema.py`'s change list, the
directive executor that applies it, plan identity (dry-run, then apply *that
exact plan*, refusing if the plan moved), the additive-only fence, the EspoCRM
extension package, and the release-train wiring.

It is the **only** part of Phase 1 at risk from D2. The desired-state definition,
the conformance check, the exit-code contract, the JSON result and both version
stamps are the app-derived half this repo owns under either answer — they are
what a CRMBuilder adoption would *consume*. What is genuinely thrown away if we
build this and then adopt CRMBuilder is the write path: the executor, the
fingerprint plumbing, and their tests. Two to three weeks.

This is why the build order is what it is: check and stamps first, applier last.

## B2. The throwaway-instance round trip

**Blocked on B1.** Acceptance criterion 13: stand up a fresh EspoCRM, apply the
standard to it, have the conformance check pass, and have a **real non-admin**
user in each gated team successfully open each app. Admins bypass ACL entirely,
so an admin test proves nothing.

Worth flagging that this needs **no chapter** — it is the onboarding runbook's
dress rehearsal, and running it inside Phase 1 is what turns
[Phase 6](phase-6-first-chapter.md) into a rehearsal rather than a first attempt.

---

# Part 4 — Verification owed

## V1. Phase 0's live browser pass

### What this is

The de-Cleveland work shipped and was verified by **fetching served pages** —
which proves the right bytes leave the server and cannot prove the one thing the
design was chosen for. The organisation name is substituted **server-side** rather
than filled in by JavaScript precisely so the browser tab and the public forms'
prose do not visibly repaint after a round-trip. **Nobody has watched a page
load.**

Four things remain unverified, none reachable with an unauthenticated `curl`.

### Steps

1. Hard-refresh a public form (`/volunteer/`) and watch the **browser tab** and
   the lead paragraph. Any flicker means the mechanism is not doing its job.
2. Sign in and open the two remaining **direct-read** pages — a sessions record
   page (`/mentorsessions/record/{id}`) and a directory contact page
   (`/directory/contacts/record/{id}`). These bypass the static mount and render
   the token explicitly; a raw `{{org}}` on either is the bug this mechanism
   invites. A third such page, the portal root, was already checked.
3. Check the two scripts that read `<meta name="cbm-org">` rather than fetching:
   the **portal birthday card's eyebrow line** and the **directory mentor page's
   tab title**.
4. At `/setup`, change `ORGANIZATION_NAME` to something obviously different,
   confirm the pages follow **without a redeploy**, then change it back. The
   revert is the path with the subtle failure mode.
5. Tick these off in `OPEN-ITEMS.md` § *Live verification owed*. Phase 0 does not
   close until they are done.

---

# Part 5 — Found here, owed to Cleveland

Not chapter work. Recorded in `OPEN-ITEMS.md`, where Cleveland defects get fixed,
and linked from here so the finding is not lost between two lists.

| Finding | Why it matters | Tracked as |
|---|---|---|
| Production holds **`MentorAssignmentNotice` twice** | The app looks email templates up **by name**, so which of the two a staff member actually sends after an Assign is arbitrary — and the two may differ | `OPEN-ITEMS.md` item 26 |
| Prod's `CMentorProfile.howDidYouHearAboutCBM` differs from the static list in **order only** | Cosmetic today (dropdown sequence on the volunteer form). Notable because one static file serves both deploys, so "which order is correct" has no answer until the code is the truth | `OPEN-ITEMS.md` item 26 |
| Five `Event*` email templates missing on **both** instances | Blocks the events follow-up sends | `OPEN-ITEMS.md` item 19 (already an events blocker) |

---

# Closed

- **The CRMBuilder prompt already carries the interface contract** (checked
  2026-08-24). I had this listed as work to do; it is not. § *What the consumer
  requires — the interface contract* was added to
  `prompts/crmbuilder-chapter-network-prompt-v0.1.md` on 2026-08-20 and carries
  C1 through C10 by number. The only thing owed was its citation, which pointed
  at the pre-split path — repointed at
  [interface-contract.md](interface-contract.md) the same day.

- **The conformance check is built and has been run against both live instances**
  (2026-08-21, commit `ac6f1b4`). `scripts/preflight_crm.py` rewritten to C1–C5
  with `tests/test_preflight_conformance.py`; acceptance criteria 1–5 and 7 met
  for real, and exit codes 1 and 3 produced live. It also corrected **three dead
  requirements in its own contract** — `Account.cAccountType` and
  `CIntakeSubmission.reason` / `.status` had been required for months and are
  written by nothing — because a gate that reports drift nobody can fix is a gate
  that gets ignored. Full result: [phase-1](phase-1-crm-config.md) §
  *Measured, 2026-08-21*.

- **The drift narrative was wrong, and there is a measurement in its place**
  (2026-08-21, re-confirmed on crm-test 2026-08-24). The two CRMs are far closer
  than assumed: **identical teams** (7 required, 9 present, same lists),
  **identical enum values across all 16 managed option lists**, and one ordering
  difference. Where they actually differ is **email templates** — crm-test holds
  2, prod holds 5 — which is the one surface nothing was watching.

- **Phase 0's mechanism** (v0.205.0–v0.206.0, deployed and prod-verified).
  `ORGANIZATION_NAME` and the `{{org}}` token substituted server-side,
  `CHAPTER_TOKENS_URL` for per-chapter colours, `ops_mailbox_name` derived from
  the organisation name, `organization` reported at `/healthz`, and
  `tests/test_shared_branding.py` (24 cases) as the thing that keeps it done.
