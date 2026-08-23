# System Settings (`/setup`) — activation and use

The admin-only page that changes this deployment's runtime settings from the
browser instead of editing a deployment overlay and running `doctl`. Plan and
the rulings behind it: `prds/system-settings-plan.md`.

**Audience:** an EspoCRM administrator. No CLI needed once it is switched on.

---

## 1. What it is for

There is no branch-level gate between a merge and production — all three App
Platform apps track `main` with `deploy_on_push: true`. The gate is the feature
flag (`DEPLOYMENT.md` § *Reviewing a change before it reaches production*), and
this page is where you operate it:

1. merge the feature **dark** (its flag defaults off, so the production deploy
   changes nothing);
2. switch it on **here, on crm-test**, and review it live;
3. switch it on **here, on production**.

Rollback is the same toggle. No overlay edit, no redeploy, and no chance of
tripping the `EV[…]` trap that encrypts an overlay's plaintext secrets.

## 2. Turning it on

**Status: on in BOTH environments.** crm-test since v0.190; **production since
2026-08-12** — until then `SETUP_ENABLED` had only ever been added to the
crm-test overlay, so `/setup/` 404'd on prod and every prod flag change still
needed an overlay edit plus `doctl`. Step 3 above is now done, so the promotion
gate can be operated entirely from the browser.

Three env vars, all on the **web** component (the page is user-facing; the
worker only reads the overrides).

| Variable | Value | What it does |
|---|---|---|
| `SETUP_ENABLED` | `true` | The `/setup` page and the portal tile |
| `DATABASE_URL` | *(already set)* | Overrides live in `app_setting` — no database, no page |
| `SETTINGS_OVERRIDES` | *(leave unset)* | Defaults to `true`. This is the break-glass — see §6 |

Apply the overlay as usual:

```bash
doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml   # crm-test
doctl apps update aa1ddf69-f359-4b53-91ba-035cbed7bd53 --spec .do/app.prod-crm.yaml  # prod
```

⚠️ Edit the overlays **by hand**. Regenerating one with `doctl apps spec get`
encrypts every plaintext secret into an `EV[…]` blob.

The migration (`0025_app_setting`, `0026_app_job`) runs in the PRE_DEPLOY job
like every other. Confirm afterwards on `/healthz`:

```json
"settings": { "page": true, "overridesActive": true, "overrideCount": 0, "settingsVersion": 0 }
```

## 3. Who can use it

**EspoCRM administrators only.** Not a team gate — this page can reconfigure the
platform, so the audience is deliberately the smallest one available. The check
is the CRM user's own admin flag, re-read from the CRM on every session restore.
Non-admins get a 403 that says so, and the portal tile does not appear for them.

## 4. Using the page

### Settings tab

Curated groups — Features, Integrations, Email, Reliability, Team gates,
Presentation — with everything else visible read-only behind **Show all**.

Each row shows where its value came from:

- **Default** — nobody has set it anywhere.
- **Deployment** — it comes from the overlay.
- **Override** — it was changed here. The row then also shows the overlay's
  value, so the overlay never silently lies about what the app is doing.

The **worker / both** badge tells you which process reads the setting. A
worker-side change takes up to `SETUP_REFRESH_SECONDS` (default 45s) to reach the
worker, because it is a separate container on its own timer.

### Presentation — whose name the app carries

The **Presentation** group holds the deployment's identity, added in
v0.205.0–v0.206.0: `Organisation name`, the four policy-document URLs the
consent checkbox links to on the public forms, and `Chapter design-token
override` (a stylesheet loaded after the base tokens that may redefine the
`--cbm-*` custom properties).

These behave differently from most settings here in one useful way: **they take
effect on the next page load, with no redeploy and no restart**, because the
name and the URLs are substituted into the page as it is served. Change one,
reload the page, and it is there. Changing it back works the same way.

Treat the policy URLs with more care than the rest — they are the documents a
member of the public is told they are agreeing to, so a typo points consent at
nothing.

### What this page cannot switch on

**The master flags that mount an app are not here** — `EVENTS_ENABLED`,
`ANALYTICS_ENABLED`, `EVENTS_PUBLIC_API`, `ASSIGNMENTS_ENABLED` — nor are the
intake rate limits, body cap, or `LOG_LEVEL`.

`create_app` decides router mounting and builds the middleware from the
**environment**, and the override layer only loads afterwards in the startup
hook. An override for one of those keys can therefore never take effect — not
even after a redeploy, because the redeploy re-runs mounting first. Offering the
control would be a lie, so they are denylisted and appear under *Show all* as
**Never editable**.

**Change them in the deployment overlay** (§2 shows the shape), then apply with
`doctl` and let the app restart. Everything else on the page is live.

**Reset to deployment value** deletes the override rather than writing the
default back, so the setting returns to whatever the overlay says.

### Temporary changes

Tick **Temporary** and give a review date. Nothing ever reverts on its own — an
unattended auto-revert is its own outage — but overdue ones are banner-flagged
on the page and logged by the worker every hour. This is the right mode for
`GMAIL_RESYNC`, which must be turned off again after one pass.

### Scoped rollout

Roll a feature out to named teams or people before everyone: that is how you
review a change in production as a real non-admin without exposing it to all
users. **Only web-side settings can be scoped** — the worker has no signed-in
user to evaluate a scope against, and the page refuses rather than offering a
control that would do nothing.

A scoped override deliberately does **not** change the process-wide
configuration; it applies only to matching users.

### Feature readiness tab

Per feature: the flag, the settings that must be non-empty, the CRM fields that
must exist, which process runs it, and how long ago the worker last checked in.
It exists for two specific failure modes — a flag set on the wrong component,
and a feature staying dark because its CRM field hasn't been built yet. A
worker feature that is on while the worker is silent is called out explicitly.

### Environment diff tab

"What is on in test that is off in prod?" Needs both deployments configured with
each other's URL and a shared token:

| Variable | crm-test | prod |
|---|---|---|
| `SETUP_PEER_URL` | prod's root URL | crm-test's root URL |
| `SETUP_PEER_TOKEN` | the same random string on both | the same random string on both |

Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
The snapshot endpoint is closed unless a token is set, carries **no secret
values** — a secret contributes only "set / not set" — and is authorised by
constant-time token comparison, not by the staff session.

### Operations tab

Maintenance jobs that used to need a container console. A job that changes
anything runs in two steps: **produce a plan → review it → apply that plan.** If
the plan has changed by the time you apply, nothing runs and you review the new
one. Applying requires a reason, which is recorded with the run.

Some mutating routines are listed but **not runnable**: they write as they go
and have no plan-producing pass, so they cannot honour dry-run-then-apply yet.
They say so instead of offering a button that would skip the review.

**The plan is the point — read it before applying.** A dry run prints exactly
what it would do: for the attachment cleanup, every document it would archive,
by record, with its filename, type, date and id, and a count line at the end.
Applying re-derives that plan and compares it to the one you read, so the two
are bound together. Every run keeps its report: **Recent runs** has a **Report**
column, and expanding a row shows what that run printed — which is how an apply
stays auditable against the plan it came from. (Before v0.208.1 the report was
rendered and then immediately destroyed by the page's own refresh, so a run
showed "done" and nothing else.)

**Clean up excluded email attachments** archives the documents that inbound mail
auto-filed but whose file type is now on the never-file list — calendar invites
above all (see *Email → Never file these attachments* on the Settings tab).
"Archive" is the same move as the Archive button on a record's Documents tab:
the file goes to that record folder's `_Archived` subfolder and leaves the
default list. Nothing is deleted, anything can be restored, and a file a person
uploaded by hand is never touched — the sweep only considers documents whose
type is *Email attachment*.

### History tab

Every change: old value → new value, who, when, and why. Also written to
`CActionLog` through the standard action-log path.

## 5. What can never be changed here

Enforced on the server, not merely hidden in the UI:

- **every secret** — API keys, passwords, the service-account JSON. They are
  never editable and never rendered; the page shows only whether one is set;
- **`ESPO_BASE_URL` and `ESPO_DRY_RUN`** — which CRM this app writes to and
  whether it writes at all;
- **`DATABASE_URL`, `SESSION_SECRET`, `APP_ENCRYPTION_KEY`** — read once at boot;
- **`SETUP_ENABLED` and `SETTINGS_OVERRIDES`** — if the page could switch itself
  off, recovery would need a redeploy.

Change those in the overlay.

## 6. Break-glass

`SETTINGS_OVERRIDES=false` in the overlay disables the override layer entirely
and the app runs on pure environment configuration, whatever is in the table.
The page still renders and says so in a banner, so nobody wonders why a toggle
did nothing.

Related safety property: if the override lookup fails — database unreachable,
query error — the app falls back to **the overlay's values**, not to code
defaults, and logs a warning. A database incident must not silently reconfigure
the application.

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/setup/` 404s | `SETUP_ENABLED` unset, or no `DATABASE_URL` | Both are required (§2) |
| Tile missing on the portal | You are not an EspoCRM admin | §3 |
| Saved a flag, nothing changed | The row is badged **Takes effect on next deploy** | Redeploy |
| Saved a worker flag, nothing happened yet | The worker refreshes on its own timer | Wait `SETUP_REFRESH_SECONDS`; compare `settingsVersion` on each component's `/healthz` |
| Saves succeed but have no effect | Break-glass is off | §6 |
| Diff says "No peer configured" | `SETUP_PEER_URL` / `SETUP_PEER_TOKEN` missing | §4 |
| Diff says the peer rejected our token | The two tokens differ | Set the same value on both |
| A job says it cannot be run | It has no dry-run mode | §4, Operations |
