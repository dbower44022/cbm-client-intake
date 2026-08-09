# System Settings — plan

**Status: PLAN ONLY, nothing built.** Doug's four founding rulings are recorded
in §1; everything after them is proposal for review.

A `/setup` page on the portal that makes runtime settings — above all the 19
feature flags — changeable per instance from the browser, instead of by editing
a gitignored overlay and running `doctl apps update`.

## 1. Doug's rulings (2026-08-08)

1. **Access: EspoCRM admins only.** No new team. `isAdmin` is already carried on
   the session (`assignments/auth.py`) and re-read on every session restore, so
   the gate needs no new plumbing and cannot go stale.
2. **Precedence: the DB override wins, and the env value is shown alongside it.**
   The page is authoritative and always works. Every overridden setting renders
   both values ("overlay says X · override says Y") so the overlay never
   silently lies about what the app is doing.
3. **Scope: curated groups; everything else read-only.** The 19 feature flags
   plus the operational knobs that actually get tuned. The remaining ~80 settings
   are visible behind "show all" but not editable.
4. **All four extras are in scope**: feature-readiness panel, environment diff,
   scoped rollout, operations tab. Phasing in §6 is the proposal.

**Second round (2026-08-09) — the four open questions, settled:**

5. **Overrides never revert themselves.** A change can be marked **temporary**
   with a review date; overdue ones are listed by the worker's existing
   monitoring loop and flagged on the page. Nothing ever flips on its own — an
   unattended auto-revert is its own outage, and the real problem with a
   forgotten test flag is that it is invisible, not that it is permanent.
6. **The overlays keep their feature flags permanently.** The overlay is not
   redundancy, it is the **safe floor**: if Postgres is unreachable the app must
   fall back to the overlay value, not to the code default. Consistent with the
   V2 posture where dropping `DATABASE_URL` degrades to V1 rather than changing
   behaviour.
7. **Mutating ops jobs are dry-run first, then apply that exact plan** — the
   house script convention (`--write` / `--apply`) rendered as a UI, not a new
   idea to learn.
8. **The environment diff keeps no snapshots of its own.** It shows what differs
   now, and a key can be expanded to pull that key's change history from both
   instances on demand.

## 2. Why this exists

The gate between a merge and production is the feature flag — there is no
branch-level gate, since all three App Platform apps track `main` with
`deploy_on_push: true` (`DEPLOYMENT.md` § *Reviewing a change before it reaches
production*). Today flipping a flag means editing `.do/app.prod.yaml` or
`.do/app.prod-crm.yaml` and applying it with `doctl`, which:

- requires a laptop with `doctl` and the overlays,
- sits one step away from the `EV[…]` trap, where regenerating an overlay
  encrypts its plaintext secrets and breaks local admin-credentialed scripts,
- redeploys the app to change one boolean,
- and leaves no audit trail of who turned what on, or why.

With the page, promotion is: merge dark → toggle on crm-test → review → toggle
on prod. Rollback is the same toggle, in seconds, with no redeploy.

## 3. The override layer

A new `app_setting` table (migration 0025) holding **only overridden keys** —
key, value, updated_by, updated_at — plus `app_setting_history` for old→new.
Follow the `analytics_definitions` / `PostgresStore` pattern already in the repo.

Reads go through a cached accessor layered over `Settings`, so the precedent is
familiar: analytics already treats built-ins as defaults that a DB row of the
same key overrides.

**Three hard boundaries.**

- **Secrets are never editable and never rendered.** The 9 secret settings (API
  keys, passwords, the service-account JSON) show as "set / not set" only.
  Secrets stay in the encrypted overlay, full stop.
- **A never-overridable denylist**, enforced server-side, not just hidden in the
  UI: every secret, `SESSION_SECRET`, `DATABASE_URL`, the `/setup` gate itself,
  and `SETTINGS_OVERRIDES`. The page must not be able to lock you out of the
  page that fixes it.
- **`SETTINGS_OVERRIDES=false` is a break-glass env var** that disables the whole
  override layer and reverts the app to pure-env behaviour. Recovery path when a
  bad value gets in and the UI can't be reached.

**Live vs restart-required.** Each setting is classified. `SESSION_SECRET`,
`DATABASE_URL` and `ALLOWED_ORIGINS` only take effect at boot, and the app cannot
restart itself on App Platform — those render with a "takes effect on next
deploy" badge rather than pretending to apply.

**Worker pickup.** The web process and the worker are separate containers, so a
toggle on web is not instantly true for the worker. A short TTL (30–60s) on the
cached accessor, plus a settings version stamp on `/healthz`, so you can see when
the worker picked up the change rather than guessing. This matters because the
worker owns delivery, monitoring, Gmail sync, Drive reconciliation, transcripts
and receipt sweeps.

**Degrade to the overlay, never to the code default** (ruling 6). If the
override lookup fails — no `DATABASE_URL`, Postgres unreachable, a query error —
the accessor returns the **env value**, logs a warning, and the app keeps
behaving as its overlay says. It must never fall through to the dataclass
default, which would silently change behaviour during a database incident. The
dev app has no `DATABASE_URL` at all; there the page is read-only and says so.

**Temporary overrides** (ruling 5). A change can be marked temporary with a
review date. The worker's existing monitoring loop reports overdue ones through
the normal alert path, and the page badges them. Nothing auto-reverts.

**Audit.** Every change goes through `core/action_log.py` — the established
requirement for a mutating staff action — with a **required reason** on the
dangerous ones, following Submission Admin's close-reason pattern.

## 4. The page

`/setup`, admin-gated, on the portal as a tile. Curated groups rather than a
flat 107-row grid, which would be a footgun:

**Features** (the 19 flags) · **Integrations** (Google, Zoom, Fathom — plus
set/unset for their secrets) · **Email** (mailboxes, alert addresses, digest
timing) · **Reliability** (async delivery, retry and sweep intervals, alert
thresholds) · **Gates** (the per-app team gates) · **Show all** (read-only).

Per row: current effective value, where it came from (default / overlay /
override), the other value when they disagree, live-vs-restart badge, last
changed by and when, and a **Reset to default** that deletes the override row
rather than writing the default back.

Conventions that apply: `busy.js` loaded first, buttons never disabled — validate
on click and name the missing input or grant — and no page width cap.

## 5. The four extras

**Feature-readiness panel.** Per feature: flag state · required secrets present ·
required CRM fields detected (the feature-detection results the code already
computes) · **which component runs it** · worker heartbeat age. This targets two
failure classes with history here: the flag set on `web` when the worker does the
work, and a feature staying dark because its CRM field doesn't exist yet.

**Environment diff.** "What is on in test that is off in prod?" as a promotion
checklist. Needs a signed read-only snapshot endpoint (`GET /api/setup/snapshot`,
shared-token auth, peer URL + token as env vars) so one app can read the other.
The snapshot carries non-secret values and set/unset for secrets — never a secret
value. Drift between the two instances is a recurring theme (CRM schema, role
scopes, and now flags), so this is the highest-value extra.

Per ruling 8 the diff stores nothing of its own: it shows what differs now, and
expanding a key pulls that key's history from `app_setting_history` on **both**
instances. ⚠️ **Known blind spot, accepted:** a flag changed by editing an
overlay and running `doctl` never passes through the app, so it appears in the
diff but has no history entry on either side. If that turns out to matter, the
fix is a periodic snapshot per environment — deliberately not built now.

**Scoped rollout.** Enable a feature for one team or one user before everyone.
This is what unblocks "verify as a real non-admin in the relevant team", owed on
roughly a dozen features in `OPEN-ITEMS.md` #20 precisely because the only
granularity today is off/on for everybody.

⚠️ **Constraint:** a per-user scope can only be evaluated where there is a user
in context — i.e. the web process. Worker-side features (delivery, sync, sweeps)
stay instance-wide, and the UI must refuse to scope them rather than offering a
control that silently does nothing.

**Operations tab.** Run the maintenance jobs that today need a container console:
assignment-stamp audit and `--heal`, Drive grant reconciliation, the receipt
sweep, form-options drift check, the schema probes, re-drive a submission. A
server-side registry of allowed jobs with typed arguments — never a free-text
command. Long jobs dispatch to the worker through a job table and report status
back, so the web request doesn't block. This extends the safe-remediation toolkit
in `SYSTEM-ADMIN-TROUBLESHOOTING.md` to staff with no CLI.

**Mutating jobs are two-step** (ruling 7), mirroring the house convention that
every script here is dry-run by default with `--write` / `--apply`:

1. Run the **dry-run**. It returns a plan — the specific changes it intends —
   which is stored and shown.
2. **Apply that stored plan**, not a fresh run. The apply call carries the plan's
   id, so what executes is what was reviewed; if the world moved underneath it,
   the apply is refused and you re-run the dry-run. This is the same stale-write
   discipline the Client Administration assign path already uses.

Plus the standing requirements for a mutating staff action: confirm, a required
reason, and `core/action_log.py`. Read-only jobs (probes, audits, drift checks)
run in one step.

## 6. Proposed phasing

The feature ships dark behind `SETUP_ENABLED`, dogfooding the process in §2.

- **Phase 1 — the override layer and the page.** Migration, accessor, denylist,
  break-glass, curated groups, audit + reasons. Delivers two-toggle promotion on
  its own; everything else is additive.
- **Phase 2 — readiness panel.** Read-only, no new write paths.
- **Phase 3 — environment diff.** The peer snapshot endpoint and its token.
- **Phase 4 — scoped rollout.** Evaluation helper plus the web-only constraint.
- **Phase 5 — operations tab.** Job registry and worker dispatch — the largest
  piece and the one with the most blast radius, hence last.

## 7. Open questions

All four founding questions are settled — see rulings 5–8 in §1. What remains is
build-time detail, to be decided in the phase that needs it:

- **Which settings count as "operational knobs"** for the curated groups in §4.
  Needs one pass through the 107 with the 19 flags as the fixed core.
- **The registry of ops jobs** and which of them have a meaningful dry-run. Some
  existing scripts already produce a plan; others would need one added before
  they can appear in the tab under ruling 7.
- **Cache TTL** for the accessor — 30s vs 60s is a trade between worker pickup
  latency and query volume. Decide with the Phase 1 load in hand rather than now.
