# What the consumer requires — app deployments managed from CRMBuilder

**Written 2026-08-31 in `cbm-client-intake`, for a requirements session in
`~/Dropbox/Projects/crmbuilder`.** Stored here, not there, for the same reason
as `crmbuilder-chapter-network-prompt-v0.1.md`: adding a file to a governed
repo is an act that repo governs. This is **candidate input for a requirements
session, not a specification** — CRMBuilder's founding rule is that a confirmed
requirement and an implementing PI exist before any code, and nothing here is
either. It ends at what the consumer needs and why; the shape of the
requirement is that session's to write.

**Origin.** The Lakeside dress rehearsal (2026-08-31,
`prds/chapter-network/rehearsal-2026-08-31/`) produced the first app deployment
that is *not* on automatic updates — `lakeside-intake`, `deploy_on_push: false`
— and the question of how such a deployment gets updated, by whom, and how the
fleet knows which release each one runs. Doug's direction, discussed the same
evening: manage this from CRMBuilder, which already provisions each chapter's
CRM and holds each engagement's DigitalOcean credential, with a per-deployment
setting and an Update button. Recorded as **proposal 8** in
`prds/chapter-network/DECISIONS.md`.

---

## The consumer's world, in five facts

1. **One codebase, N app deployments, one per chapter, each in the chapter's own
   DigitalOcean account** (rulings 2, 5). A deployment is a DigitalOcean App
   Platform app with three components — `web`, `delivery-worker`, and a
   `PRE_DEPLOY` job `migrate` — each carrying its own `github.deploy_on_push`
   flag. A toggle that sets one component and not the others half-updates the
   app.
2. **All chapters move together to a named release** (ruling 7). A release is
   an annotated git tag (`v0.217.0`), cut weekly at Sunday 17:00 UTC
   (`scripts/cut_release.sh`). The consumer's plan of record for *what a
   deployment follows* is a **release branch** that the weekly cut fast-forwards
   to the tag; chapter apps track that branch, and only the one soak copy tracks
   `main`. Building an image once per tag and shipping it by tag is the later
   refinement; the policy model below must survive that change unchanged.
3. **Every deployment reports itself at `/healthz`** — unauthenticated JSON with
   `version` (the code), **`releaseTag`** (the promotion; `null` on an untagged
   build), `organization`, `environment`, `dryRun`, worker liveness, and a
   **`crmConfig`** block (`state` ∈ `stamped | unstamped | absent | forbidden |
   unreachable | disabled`, plus `version`, `appliedAt`, `fingerprint`). Nothing
   in the console needs to be invented; it aggregates.
4. **`releaseTag` is baked into the image at build time** by a `RELEASE_TAG`
   build argument that lives in the app's spec as an env var with scope
   `RUN_AND_BUILD_TIME`. Under the release-branch mechanism an update is
   therefore **two operations, not one**: set that variable to the new tag on
   every component, then trigger a deployment. Triggering without setting it
   makes the deployment misreport its own promotion — worse than reporting null.
5. **A release must not reach a CRM that is not ready for it.** The consumer has
   a read-only conformance check (`scripts/preflight_crm.py --json`, org-wide
   API key, exit codes 0/1/3) and, under ruling 7, the CRM configuration moves
   *in the same promotion* as the app. CRMBuilder's publish is the CRM half of
   that promotion.

## What is asked for

### D1 — A Deployment record, beside each Instance

An engagement's CRM instance already has a record (`INST-NNN`). The consumer
needs its **app deployment** to have one too, holding at least: the DigitalOcean
app id and account (credential) it lives under; the CRM instance it is paired
with; the git ref it follows; its **Updates policy** (D2); the `releaseTag` and
`crmConfig.state` last read from its `/healthz`; and when they were read. Zero or
one deployment per instance; a deployment without an instance is a
misregistration.

### D2 — The Updates policy, with three values and one rule

Named by Doug, 2026-08-31, because they say what the copy *is*:

| Value | Meaning | Mechanism today |
|---|---|---|
| **Development** | Takes every push to `main`; the soak copy | `deploy_on_push: true` on all components, tracking `main` |
| **Latest Stable** | Moves automatically to each named release; **the default for a chapter** | `deploy_on_push: true`, tracking the release branch |
| **On Demand** | Updates only when someone presses Update, with a **reason and a review date** recorded | `deploy_on_push: false`; the Update button (D3) is the only way forward |

**The one rule: exactly one deployment in the fleet may be Development, and it
is never a chapter's.** A second Development is a mistake the console catches,
not a choice it offers. (Today the soak copy is Cleveland's crm-test app; the
dry-run `lobster-app` is *not* the soak copy and should not be registered at
all.)

Changing the policy changes the DigitalOcean spec (`deploy_on_push` on every
component, and the tracked branch) through the engagement's stored credential
— the same credential the deploy feature already uses. The record must show
**both** the policy and the spec's actual state, because they can disagree
(someone edits the spec in the DO console), and "Latest Stable, but
`deploy_on_push` is off" is exactly the quiet failure Phase 2 names.

### D3 — An Update button, and an Update-all

**Update** on one deployment means: move it to the fleet's current release.
Concretely, under the release-branch mechanism: set `RELEASE_TAG=<tag>` on
every component, ensure the tracked branch is the release branch, trigger a
deployment, wait for it, re-read `/healthz`, and record the outcome — including
a failure, which must show the deployment's *previous* `releaseTag` still in
force. **Update all** is the weekly release applied to every Latest Stable
deployment (On Demand ones are listed, not moved).

Two guards, both of which exist on the consumer's side already:

- **Refuse when the CRM is not conformant.** Before triggering, run or read the
  conformance check for the paired instance; exit 1 (drift) or 3 (unreachable)
  refuses with the check's JSON reason. A break-glass exists for the gate
  (`SETTINGS_OVERRIDES=false`-shaped, logged loudly) — the button may expose it
  as a deliberate, recorded override, never as a default.
- **Move the CRM configuration in the same promotion.** If the release pins a
  new standard version, the CRM publish happens *before* the app deployment
  (expand-then-contract, additive only), and the button's log shows both halves.
  The consumer does not require CRMBuilder to be the applier for that to hold —
  only that the two are one recorded operation.

### D4 — A fleet view

One screen answering: which release is each deployment on, which policy, which
`crmConfig.state`, whether the spec and the policy agree, when `/healthz` was
last read, and which deployments are On Demand and why (reason, date). It must
preserve the distinction the conformance check exists for — *drifted* and
*unreachable* are different columns — and it must show an On Demand deployment
whose review date has passed as overdue. This is the consumer's Phase 5 (fleet
console); the consumer's plan says that phase **owns no instrumentation**, and
that holds here: every signal is read from `/healthz` or the check's JSON.

### D5 — What must not be required

An operator's laptop; a person's own DO credential (the engagement's stored one
is the actor); an interactive keyring or prompt mid-run; write access to the
consumer's repository; secrets in the Deployment record beyond a reference to
the engagement's credential. A release that skips staging (the Development copy)
— an emergency path bypasses the *cadence*, never the soak.

## What the consumer supplies

- `/healthz` with both stamps — **built** (v0.214.0), inert until `RELEASE_TAG`
  is set per deployment.
- `scripts/cut_release.sh` — **built**; the release branch fast-forward is a
  one-line addition owed to Phase 2 (TASKS R10).
- The conformance check with defined exit codes and a JSON result — **built**.
- A spec generator from a values file (`scripts/rehearsal/render_spec.py`) that
  already emits `deploy_on_push: false` — the shape CRMBuilder would set, not
  invent.
- The DigitalOcean calls the button needs, all in the public API: read the app
  spec (`GET /v2/apps/{id}`), update it (`PUT /v2/apps/{id}` with the spec —
  `deploy_on_push`, `github.branch`, the `RELEASE_TAG` env on each component),
  create a deployment (`POST /v2/apps/{id}/deployments`), and read deployment
  status. `doctl apps update --spec` / `doctl apps create-deployment` are the
  same calls.

## Open questions for the session — the consumer has no ruling on these

- **Is the fleet console a CRMBuilder product capability or a CBM-network
  artifact that uses CRMBuilder?** The same boundary question the CRM-applier
  session carries; the two should be answered together.
- **Where does the release branch live and who fast-forwards it** — the
  consumer's CI on the tag, or CRMBuilder's Update-all? The consumer's
  recommendation: the cut is the consumer's (one command, already exists);
  Update-all reads the tag and acts.
- **Registry-based images later**: when the fleet outgrows N builds of one
  commit, the Update button's implementation changes to "set the image tag";
  the Deployment record and the policy do not. Worth designing D1–D3 so that
  swap is a mechanism change, not a schema change.
