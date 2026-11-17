# setup/ — System Settings

Last Updated: 11-17-26 11:20 · Revision 1.3

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

## Zoom Meetings and Zoom Webinars — the settings the Events side reads

Integrations tab phase 9 (v0.333.0), rulings EH1, EH5 to EH8 of
`prds/events/event-hosting-plan.md`. Two integrations: **Zoom Meetings**
(`zoom_meetings`) and **Zoom Webinars** (`zoom`, the key kept). Zoom Webinars
keeps its old setting keys, relabelled, so no stored override is stranded.

- **Zoom Meetings**: `zoom_meetings_in_use`; the switch
  `zoom_meetings_events` (off by default — the Events side creates a meeting
  only while it is on, `Settings.zoom_meetings_active`);
  `zoom_meetings_account_id`, `zoom_meetings_client_id`,
  `zoom_meetings_client_secret` (secret); **`zoom_event_host_email`**, the
  event host user (EH8); `zoom_meetings_capacity` (EH6, default 100).
- **Zoom Webinars**: `zoom_in_use`, `zoom_events`, `zoom_account_id`,
  `zoom_client_id`, `zoom_client_secret`, `zoom_host_email` (its own, used
  only on a separate account), and **`zoom_webinars_same_account`** (EH7,
  default Yes).
- **The defaults per audience** (EH5), on the Settings tab:
  `events_default_method_public` and `events_default_method_members`, each
  one of the CRM's stored values `CBM Zoom` (shown as Zoom Webinars), `Zoom
  Meetings`, `Other platform`, `Outside host`; both default `CBM Zoom`. A
  choice setting may carry `choice_labels`, which the page shows.
- **`events_other_platform`** (Features, v0.341.0): the switch for the Other
  platform hosting method (event hosting plan step 4). Read per request
  through `events/hosting.other_platform_on`.
- **Never read the Zoom credentials directly.** `core/zoom.meetings_account`
  and `core/zoom.webinars_account` are the one rule (Doug, 11-15-26, option
  A): Zoom Webinars uses Zoom Meetings' app and event host user when "same
  account" is Yes AND all three Zoom Meetings credentials are set, otherwise
  its own four. `core/zoom.make_client` (webinars) and
  `make_meetings_client` build from them; the tests, readiness and the
  status line read them too.
- A test check that finds nothing to read yet (no past meeting or webinar)
  is **skipped**, not unknown, so a new account can pass its whole test.
- A wizard screen's `when:` reads a question not answered in this run from
  the settings its answer saved (`wizard.when_answers`), so Start again keeps
  the branch.

## The Integrations tab — rules not to break

Built v0.321.0 to v0.335.0, behind `INTEGRATIONS_TAB` (off by default).
Administrator guide: `SYSTEM-SETTINGS-SETUP.md` § 8. Design and rulings:
`prds/integrations-tab-plan.md` (I1 to I13, W1 to W6; § 4, § 6.3, § 6.5 and
§ 7 describe what phase 10 removed).

- **The registry is the one list.** `integrations/registry.py` names each
  integration, its "in use" setting, its switches, its "Used by" entries,
  its credentials and its test module. A setting reaches a sub-tab only by
  its `integration=` (and `section=`) tag, set from one table,
  `core/settings_registry.INTEGRATION_TAGS`. A new integration setting is
  tagged there, or it stays on the Settings tab.
- **The guard runs in the save AND the reset path**
  (`integrations/guard.py`): no "not in use" while a feature is on, no
  feature on while "not in use" (I5, I13). It counts the used-by features
  that cannot work without the integration (`blocking_switches`) and a
  scoped override as on. It is always active, switch or no switch. A new
  write path to `app_setting` must call it, which is one more reason there
  is only one (`_checked_save`).
- **A check that cannot read its answer says unknown, never ok**
  (`integrations/testing.py`). An exception or a timeout is unknown. Every
  detail line and fact is scrubbed of every secret's value (`scrub`,
  `secret_values`) before it is returned or stored.
- **"Skipped" counts as passing a wizard screen** (`wizard.evaluate`): a
  check skipped because its feature is off, or because there is nothing
  to read yet, has nothing to prove. Unknown never passes a screen.
- **The wizard's screens live in the guide's step files**, under a step's
  `wizard:` key, beside `integration:`. Screen keys: `ask:` (answers with
  `sets:` and `then:`), `enters:`, `runs:` (a coded action in
  `integrations/actions.py`), `connect: mailing`, `sets:` (only with
  `enters:`), `check:` (`decided:`, `setting_set:`, `test:<integration>`
  or `test:<integration>/<check>[,<check>]`), `when:`, `copy:` (may hold
  `{APP_BASE_URL}`), `see:`, `if_not:`. The renderer never prints them.
  **`wizard.problems` must return nothing for every integration**
  (`tests/test_integration_wizard_phase9.py`): it refuses an unknown
  setting, check, test line, coded action, Connect, branch target or
  `when:`. Run it after any step-file edit.
- **Claude is read-only.** Ask Claude (`integrations/diagnosis.explain`,
  `setup/router._run_ask`) gets read-only tools and the web tools held to
  the integration's `doc_sites`. It has no tool that writes, and it is
  never called at night. **A secret's value never reaches it**: only set
  or not set and when it changed, and every message is scrubbed again on
  the way out.
- **One budget table.** `integration_agent_call` holds every call's cost,
  including the old fix and setup plans' costs that migration 0049 copied
  in. `WizardStore.spent_this_month` is the one sum
  `INTEGRATION_AGENT_MONTHLY_BUDGET` is checked against. A new call to
  Claude from this tab records its cost there.
- **Alembic revision ids are at most 32 characters**: `version_num` is
  `varchar(32)`, so a longer id fails every deploy's migrate job, and only
  Postgres notices. `tests/test_integration_removal.py` checks every
  revision.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 11-17-26 11:20 | Claude (Claude Code) | `events_other_platform`, the Other platform switch (v0.341.0). |
| 1.2 | 11-15-26 13:30 | Claude (Claude Code) | The Integrations tab: the rules a future session must not break (phase 11). |
| 1.1 | 11-15-26 02:50 | Claude (Claude Code) | Zoom Meetings and Zoom Webinars: the settings the Events side reads (Integrations tab phase 9, v0.333.0). |
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
