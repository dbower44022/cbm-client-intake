# setup/ — System Settings

Last Updated: 10-20-26 17:30 · Revision 1.0

Detail for System Settings (`/setup`): the override model, the verified path, confirm-or-revert, restart-required settings, refresh, scoped rollout and the page's other panels.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## System Settings — `/setup`

**EspoCRM admins only** (not a team gate — this page can reconfigure the
platform). Changes this deployment's runtime settings from the browser instead
of an overlay edit plus `doctl`, which is what makes the flag-based promotion
gate practical. Gated by `SETUP_ENABLED` + a database. **Live on both
environments** — prod since 2026-08-12; before that the flag was only ever in
the crm-test overlay, so every prod flag change needed `doctl`. Runbook:
`SYSTEM-SETTINGS-SETUP.md`; rulings: `prds/system-settings-plan.md`.

- **Env is the default, the DB row is the override, and both are shown when they
  disagree** — `app_setting` holds only overridden keys and
  `core/settings_store.py` merges them over the env baseline behind the same
  `get_settings()` every package already calls. An empty table is exactly the
  old behaviour.
- **Degrade to the overlay, never to the code default.** If the override lookup
  fails (no DB, Postgres down, a bad value) the accessor returns the env value
  and logs. A database incident must not silently reconfigure the app — which is
  also why the overlays keep their flags permanently.
- **Every setting is editable unless a change is genuinely impossible** (Doug's
  ruling, 2026-08-28: *"All settings should be editable, unless a change would
  make the system unusable. Then there must be a verification that the system is
  still functional."*). The denylist is down to **three** keys — `DATABASE_URL`
  (the override table lives inside the database it names, so a move would be
  left behind in the database being abandoned), `APP_ENCRYPTION_KEY` (rotating
  it makes every stored secret permanently unreadable — data loss, not lockout)
  and `RELEASE_TAG` (the release stamp travels in the image's own
  `release-tag.txt`; a stored override would survive a restart and make the
  deployment misreport which promotion it is). All three are **visible and read-only**,
  each refusal naming its reason. Everything else that used to be hidden — the
  CRM address and key, dry-run, the provisioning account, every integration
  credential, the session secret, `SETUP_ENABLED`, `SETTINGS_OVERRIDES` — is
  editable through the **verified path** (`setup/verify.py`):
  - **Pre-flight**: the value is tried before it is stored. A CRM key the CRM
    rejects, or an address that answers but holds none of this app's entities,
    is refused with the CRM's own error. A probe that cannot *reach* its target
    returns `unknown`, never `ok`, and `unknown` does **not** block the save —
    an admin fixing configuration during an outage must not be blocked by it.
  - **Post-apply**: a `VERIFIED_KEYS` change that leaves the system non-functional
    is **reverted automatically**.
  - **Confirm-or-revert**: `LOCKOUT_KEYS` (the two switches guarding this page,
    the session secret, the cookie flag, allowed origins) apply with a
    **10-minute countdown** and undo themselves unless an admin confirms. No
    probe can detect a lockout — the app is working perfectly and simply will not
    let anyone back in — so this is the only mechanism that survives it. The
    sweep runs in **both** processes on the settings timer, and works directly
    against the database so it still fires when the change under test was
    `settings_overrides=false`.
  - **Secrets are editable but never readable** — set a new one, never read the
    old one back. Stored **encrypted** with `APP_ENCRYPTION_KEY`; without a
    cipher a secret is **refused**, never written in plain text. `DATABASE_URL`
    counts as a secret because the password is inside the URL. History stores
    `(secret set)`, never the value.
  `SETTINGS_OVERRIDES=false` is still the env-only break-glass.
- **Every setting is on the page — including the ones that need a restart**
  (Doug's ruling, 2026-08-28: a setting hidden where it cannot be viewed or
  edited is unacceptable). `BOOT_READ_KEYS` are curated into a **Restart
  required** group that explains itself, and each row shows the value **in
  force** beside the stored one, badged *Waiting for restart* when they differ.
  Two things make that honest rather than a repeat of v0.190.1, when these were
  offered with a "takes effect on next deploy" badge and toggling
  `events_enabled` produced a portal tile whose routes did not exist:
  - **`core/boot_overrides.load_at_boot` installs the override layer at the very
    top of `create_app`**, before routers are mounted, middleware built or
    logging configured. Previously the layer loaded afterwards, so such an
    override never applied *at all* — a redeploy re-ran the mounting first. It
    never raises, and on a database failure it degrades to the **deployment's**
    values, never the code defaults.
  - **The live `Settings` object is not the truth for these keys.** The periodic
    refresh installs a newer value into it while the already-built routers keep
    the old one, so reading it back would report a change as taken effect when it
    had not. `boot_overrides.state().snapshot` is the only honest source and is
    what the page reports as `inForce`.
  `DENYLIST` now holds only secrets, infrastructure and the break-glass pair —
  plus **`release_tag`**, which is curated **read-only**: it is stamped into the
  image, so a stored override would survive a restart and make the deployment
  misreport which image it is running. **The denylist is still filtered on READ
  as well as write**, so a row that outlives its rule goes inert with no cleanup.
- **Web and worker refresh independently** (`SETUP_REFRESH_SECONDS`, default 45).
  `/healthz` reports `settingsVersion` per component so you can see the worker
  catch up.
- **Overrides never auto-revert**; a change can be marked temporary with a review
  date, and overdue ones are flagged on the page and logged hourly by the worker.
- **Scoped rollout is web-only** — a per-team/per-user scope needs a signed-in
  user to evaluate, so worker-side settings refuse it. A scoped override is
  deliberately excluded from the process-wide config.
- Also on the page: a **feature-readiness** panel (flag · required secrets · CRM
  fields detected · which component · worker heartbeat), an **environment diff**
  against the peer deployment (token-authorised snapshot, no secret values ever
  crossing the wire), and an **operations** tab whose mutating jobs are
  **dry-run → apply that exact plan**, refusing if the plan moved.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
