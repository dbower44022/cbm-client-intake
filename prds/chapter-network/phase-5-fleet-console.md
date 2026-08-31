# Phase 5 — The fleet console

**Status: not started — and, since 2026-08-31, proposed to be CRMBuilder.**
Needed the moment there is a second production tenant. [DECISIONS.md](DECISIONS.md)
proposal 8 puts the console inside CRMBuilder: a Deployment record beside each
CRM Instance, an *Updates* policy (Development / Latest Stable / On Demand), an
Update button with the conformance guard, and the fleet view below. Everything
in this file stays true under that answer — the console still owns no
instrumentation; it reads `/healthz` and the check's JSON. The consumer
requirements handed to that session are
`prompts/crmbuilder-deployment-updates-requirements-v0.1.md` § D4.

**It owns no instrumentation.** Every signal it aggregates already exists per
deployment, and both version stamps are defined and written elsewhere —
`releaseTag` by [Phase 2](phase-2-release-train.md), the `crmConfig` block by
[Phase 1](phase-1-crm-config.md). **If this phase finds itself designing a version
stamp, one of the earlier phases did not finish.**

---

## The fleet console

Today `/setup` and `/healthz` are per-deployment, and `/setup`'s environment-diff
panel compares against exactly one peer — built for a two-instance world. A
support organization needs one view answering: who is on which tag, whose CRM has
drifted from desired state, whose worker heartbeat is stale, who has open delivery
failures or `needs_attention` submissions, whose Drive reconciliation is reporting
`unfulfillable` grants, and who is stranded at `Accepted-Provisional`.

Every one of those signals already exists per deployment — `/healthz` reports
version, environment, `dryRun`, `durableStore`, worker liveness and
`settingsVersion`; monitoring already computes backlog, oldest pending, stranded
leases and open failures. The console is an aggregator over N instances plus the
conformance check, not new instrumentation. It is what makes the support contract
deliverable by a small team, and it is a first-class deliverable rather than a
nice-to-have.


---

## What it consumes

| Source | Signal |
|---|---|
| `/healthz` per instance | `version`, `releaseTag`, `organization`, `environment`, `dryRun`, `durableStore`, worker liveness, `settingsVersion`, the `crmConfig` block |
| The conformance check's JSON result | per-instance conformance: `conformant` / `drifted` / `unchecked`, per directive |
| Existing monitoring | backlog, oldest pending, stranded leases, open failures |
| Existing sweeps | Drive `unfulfillable` grants, mentors stranded at `Accepted-Provisional` |

The distinction the console must preserve, and the reason exit code 3 exists at
all: **"18 conformant, 1 drifted, 1 unreachable"** — never collapsing the last two
into each other.

A signal with no source yet: **whether a chapter's app still has
`deploy_on_push` on**. See [Phase 2](phase-2-release-train.md) § Open.
