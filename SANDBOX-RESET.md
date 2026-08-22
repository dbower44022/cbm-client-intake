# The training sandbox — nightly reset runbook

crm-test does three jobs now: it is the **pre-production review gate**, the
**training sandbox**, and the **release-test environment**. This document is
how the nightly restore keeps those three from ruining each other.

Audience: whoever operates the platform. Needs droplet SSH and `doctl`.

## Why there is a reset at all

Not cleanup — training is demo-led and creates almost nothing. The reset earns
its keep two other ways:

1. **Release testing leaves wreckage.** Exercising every function means half-
   finished engagements, test submissions in the queue, orphaned documents.
   Somebody has to undo that, and doing it by hand is how sandboxes rot.
2. **Repeatability.** A demo that starts from an identical screen every single
   time is teachable. The trainer's script always matches what's in front of
   them, and nobody has to explain why last week's mess is still there.

## What it does NOT throw away

This is the part that makes it safe to run against an instance other people
rely on.

**The CRM team's schema work survives.** EspoCRM keeps Entity Manager output
in *files* — `data/espocrm/custom/Espo/Custom/Resources/` — not the database.
The reset restores the record tables and then runs `rebuild`, so the schema
re-derives from whatever metadata is live at that moment. A field added at 3pm
still exists at 00:05 with its data cleared.

**The review gate survives.** `app_setting` is never cleared, so a feature flag
turned on at `/setup` to review a change before it reaches production is still
on in the morning.

**Credentials and definitions survive.** Roles, teams, portals, email
templates, scheduled jobs, reports, workflow definitions, and the Google and
mailbox wiring (`integration`, `external_account`, `o_auth_*`, `app_secret`,
`inbound_email`).

**Runtime noise is emptied, not restored.** `job`, `auth_log_record`,
`scheduled_job_log_record`, `action_history_record`, the native `email` tables
and their siblings are excluded from the baseline and truncated on every reset.
This matters for more than size: the first baseline was 62 MB compressed and
660 MB raw, almost all of it those three tables — and restoring `job` nightly
would re-insert old queued jobs for the EspoCRM daemon to run. A reset that
makes the CRM *do* things is not a reset. Excluding them took the baseline to
**286 KB**.

**Everything else resets** — including users. Trainee password and signature
changes revert, and logins created by a provisioning demo disappear, which is
the point. The cost: a user the CRM team adds mid-day reverts at midnight.
Re-baseline (below) to keep one.

The classification is **keep-by-exception**: a new custom entity the CRM team
adds later is not on the keep list, so it resets as records without anyone
having to remember anything.

## The two halves

| Half | Where | When | What |
|---|---|---|---|
| CRM | droplet cron | 00:00 local | `scripts/sandbox/reset_crm_sandbox.py reset --apply` |
| App database | `delivery-worker` | 01:00 local | `core/sandbox_reset.py`, gated by `SANDBOX_NIGHTLY_RESET` |

They run an hour apart, in that order, deliberately. The app's Postgres holds
the Submission Admin queue, the partner/funder discussion comments and the
Drive document index; a CRM restored to fifty engagements while `/ops` still
lists last night's submissions is not a pristine sandbox, it is a confusing
one. The hour of slack means a slow `rebuild` never overlaps the second half.

Both halves **refuse to run against a CRM that is not crm-test**, whatever
their flag says. The droplet script checks the deployment's own site URL; the
worker checks `ESPO_BASE_URL` directly rather than `Settings.environment`,
because that honours an `ENV_LABEL` override and the guard on a destructive job
must not be overridable by a label.

## First-time setup

**1. Install the script on the droplet.**

```bash
scp scripts/sandbox/reset_crm_sandbox.py root@104.131.45.208:/usr/local/sbin/
ssh root@104.131.45.208 'chmod 750 /usr/local/sbin/reset_crm_sandbox.py'
```

**2. Clear the soft-deleted rows.** EspoCRM soft-deletes, and its own Cleanup
job only removes rows past a three-month retention window — so a baseline
captured after a purge carries every purged record's data forward for ever:

```bash
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py purge-deleted'
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py purge-deleted --apply'
```

**3. Get the instance into the state you want to return to every night** —
the seeded training data, the right users, the right teams. Everything present
at this moment becomes "pristine" until you re-baseline.

**4. Capture the baseline.**

```bash
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py baseline --apply'
```

Writes `/var/lib/cbm-sandbox/golden/`: `records.sql.gz`, `upload.tar.gz` (the
attachment *files* — restoring the table without them leaves every golden
record pointing at a missing document), `config-reference.sql.gz` (disaster
recovery only; a reset never restores it) and `manifest.json`.

**5. Prove the restore before trusting it.** Change something obvious in the
CRM, run the reset by hand, confirm it came back:

```bash
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py reset'          # dry run first
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py reset --apply'
```

**6. Arm the CRM half.**

```bash
ssh root@104.131.45.208 \
  '(crontab -l; echo "0 0 * * * /usr/bin/python3 /usr/local/sbin/reset_crm_sandbox.py reset --apply >> /var/log/cbm-sandbox-reset.log 2>&1") | crontab -'
```

**7. Arm the app half** — add to the crm-test overlay (`.do/app.prod.yaml`),
**worker component only**, then `doctl apps update 509b4370-… --spec <file>`:

```yaml
- key: SANDBOX_NIGHTLY_RESET
  value: "true"
```

`SANDBOX_RESET_HOUR` (default 1) and `SANDBOX_RESET_TZ` (default
`America/New_York`) are available if you need to move it. The arming flag is
**denylisted from `/setup` on purpose** — it empties the queue and the Drive
index, so it should cost a deliberate `doctl` apply, not a toggle anyone
holding that page can flip.

Confirm it armed: the worker logs `training-sandbox reset enabled` at boot, or
`training-sandbox reset NOT armed: <reason>` if a guard refused it.

## Day-to-day

**Pause tonight's reset** — for a release test running late, or a review whose
state you want to keep:

```bash
ssh root@104.131.45.208 'touch /var/www/espocrm/.sandbox-hold'   # resume: rm
```

The CRM half logs `reset: HELD` and does nothing. **The app half does not read
this sentinel** — it is on the other side of an SSH boundary. Either clear the
worker flag too, or accept that the app tables clear while the CRM does not;
for a release test in progress the CRM state is usually the part that matters.

**Re-baseline** after deliberately improving the training data, adding a user
who should persist, or a CRM change you want in the pristine state:

```bash
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py baseline --apply'
```

Nothing re-baselines on a schedule. A day's training mess can never be
silently promoted into the pristine state — that only ever happens because
someone typed this.

**Check on it:**

```bash
ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py status'
ssh root@104.131.45.208 'tail -40 /var/log/cbm-sandbox-reset.log'
```

## Rollback

Disarm the CRM half by removing the crontab line; disarm the app half by
setting `SANDBOX_NIGHTLY_RESET=false` in the overlay and re-applying. Neither
half destroys the golden baseline, so re-arming later needs no re-capture.

## The eventual fix: a separate test Google Workspace

Doug's direction (2026-08-22): a Workspace of its own for the test environment,
so the sandbox can exercise Google end to end instead of being contained by
making its addresses unreachable. Containment today works by *preventing*
sends; a test tenant would let them happen harmlessly, which is the difference
between "we could not break anything" and "we saw it work."

It is not urgent — training is demo-led and contained. It matters for **release
testing**, where a calendar write that silently no-ops looks exactly like one
that passed.

What changes when it lands, so this is a job rather than a rediscovery:

| Today | With a test Workspace |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` is the production tenant's service account | A new service account in the test tenant, with its own domain-wide-delegation grants for the same scopes |
| `GDRIVE_SHARED_DRIVE_ID` = `0ALcjRDPAiHRLUk9PVA`, a drive inside the production tenant | A shared drive in the test tenant |
| Training `cbmEmail`s are on `@sandbox.cbmentors.org` **because it has no mailboxes** | They become **real** mailboxes in the test domain; the containment check flips from "must be unroutable" to "must be in the test tenant" |
| `OPS_MAILBOX` must stay unset — setting it would double-poll the real info@ | Can be set to the test tenant's info@, unlocking Submission Admin's inbound half |
| `GOOGLE_CREATE_MAILBOX` / `GOOGLE_DIRECTORY_CHECK` / `GOOGLE_MEMBERS_GROUP` all off — they would create real accounts | Can be turned on, which is the only way to release-test mentor provisioning |
| EspoCRM has no outbound email at all | Point its SMTP at the test tenant |

The one thing that does **not** change is the reset itself: none of the above
touches the golden baseline or either half of the nightly restore.

## Containment — assume somebody saves

Doug's ruling 2026-08-21: nobody is supposed to save anything during training,
but the sandbox has to be safe on the assumption that somebody will. Run the
pre-flight before a session — a checklist nobody runs is how this fails
quietly:

```bash
uv run python scripts/sandbox/check_containment.py
```

The rules it checks, and why each one holds:

| Reach | What stops it |
|---|---|
| Outbound email, calendar invites | Both impersonate the signed-in user's `CMentorProfile.cbmEmail` (the staff quick-compose falls back to the same per-user identity when `OPS_MAILBOX` is unset). An address with no mailbox 403s `unauthorized_client` and the best-effort call gives up. |
| Drive uploads | **cbmEmail does not help** — Drive runs as the service account (`GDRIVE_IDENTITY=service`), so uploads go wherever the app points. Only a separate sandbox shared drive contains this. |
| Real Google account creation | `GOOGLE_CREATE_MAILBOX` / `GOOGLE_DIRECTORY_CHECK` / `GOOGLE_MEMBERS_GROUP` all off. |
| Sending as info@, and double-polling the shared inbox | `OPS_MAILBOX` unset on this deployment. |
| CRM and app-database changes | The nightly reset. |

So the one rule that carries the most weight: **every identity anyone trains
on — mentor and staff alike — must have a `cbmEmail` that is not a real
mailbox.** Nobody trains on their own login. A staff trainee signed in as
themselves sends real mail from their real mailbox the moment they click Send
on the quick-compose that Client Administration opens after an assignment.

## ⚠️ What the reset cannot undo

**Google side effects outlive it.** Rolling the database back does not unsend
an email or delete a calendar invite, so containment has to stop them being
created in the first place. As of 2026-08-22 it does, and
`check_containment.py` reports **0 blocking issues**:

- **Drive** — crm-test has its own shared drive (`0ALcjRDPAiHRLUk9PVA`,
  "CBM Sandbox Documents"), separate from production's. Set in the overlay AND
  overridable at `/setup`; the overlay matters because if the override lookup
  ever fails the app falls back to the env var, and that must not be
  production's drive. Verified from inside the container that the service
  account can read it.
- **Email and calendar** — still live, and contained by the addresses: every
  training `cbmEmail` is on `@sandbox.cbmentors.org`, which has no mailboxes,
  so the delegation call fails and nothing reaches a real person. The
  pre-flight checks this rather than asking a human to eyeball the list.
- **The CRM cannot send at all** — EspoCRM's Google integration was removed on
  2026-08-22 and its global SMTP is unconfigured. Provisioning welcome emails
  and CRM password resets therefore fail on this instance, which is correct for
  training and a limitation to know about for release testing.

For **training** this barely matters — training is demo-led and creates almost
nothing. For **release testing** it matters a great deal, and it cannot be
solved by turning the integrations off: a release test whose calendar write
silently no-ops looks exactly like one that passed. A **separate test Google
Workspace** is the real fix, and until it exists, release testing either leaves
real residue or leaves those surfaces uncovered. Decide which per test rather
than by default.
