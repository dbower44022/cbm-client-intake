"""The app-database half of the nightly training-sandbox reset.

crm-test doubles as CBM's training sandbox and release-test environment, so it
is restored to a golden baseline every night.  The CRM half of that runs on the
droplet (``scripts/sandbox/reset_crm_sandbox.py``); this is the other half —
the app's own Postgres, which holds the Submission Admin queue, the
partner/funder discussion comments, the Drive document index and the
conversation read-state.

The two halves have to move together.  A CRM restored to fifty engagements
while ``/ops`` still lists last night's submissions, and ``app_document`` still
indexes Drive files for records that no longer exist, is not a pristine
sandbox — it is a confusing one.

Why this lives in the repo rather than beside the droplet script: the table
list has to track migrations.  :mod:`tests.test_sandbox_reset` fails the moment
a migration adds a table nobody classified, which is the only mechanism that
keeps this honest a year from now.

What survives, and why:

* ``app_setting`` / ``app_setting_history`` — the ``/setup`` overrides.  These
  are how a feature flag gets turned on for a pre-production review, and
  crm-test is the only review gate this project has.  Wiping them nightly
  would silently roll back the thing being reviewed.
* ``analytics_metric`` / ``analytics_page`` — admin-authored, like email
  templates.  Someone's afternoon building a metric is work, not litter.
* ``email_sync_state`` — deliberately left alone.  Restoring Gmail cursors to a
  golden position would make the next pass re-read months of mail into a
  freshly emptied CRM; leaving them means sync simply carries on.
* ``app_config`` / ``worker_heartbeat`` — instance bookkeeping the app writes
  about itself.
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import text

from core.config import Settings

log = logging.getLogger("cbm_intake.sandbox_reset")

#: Marker that must appear in the CRM base URL for a reset to be allowed.
#: Deliberately NOT ``Settings.environment`` — that honours an ``ENV_LABEL``
#: override, and the guard on a destructive job should not be overridable.
SANDBOX_URL_MARKER = "crm-test"

#: Training/record data: emptied on every reset.
RESET_TABLES: tuple[str, ...] = (
    # Submission Admin: the arrival queue and everything staff hang off it.
    "submission_presence",
    "submission_activity",
    "submission_comment",
    "submission",
    # Partner/funder Discussion pane (app-only, never written to the CRM).
    "record_comment",
    # Drive document index + the inbound-attachment filing ledger.
    "app_document",
    "comm_attachment",
    # Communications read-state and thread anchoring.
    "conversation_seen",
    "conversation_override",
    "conversation_thread",
    # Derived, and rebuilds on the next sweep.
    "analytics_cache",
    # Runtime job ledger.
    "app_job",
)

#: Configuration, authored artefacts and instance bookkeeping: never touched.
KEEP_TABLES: frozenset[str] = frozenset(
    {
        "app_setting",
        "app_setting_history",
        "analytics_metric",
        "analytics_page",
        "app_config",
        "email_sync_state",
        "worker_heartbeat",
    }
)


class SandboxResetRefused(RuntimeError):
    """Raised when a reset is attempted somewhere it must never run."""


def guard(settings: Settings) -> None:
    """Refuse anywhere that is not the crm-test sandbox.

    Two independent conditions, both required: the feature is switched on for
    this deployment, and the CRM it talks to is crm-test.  The second is read
    straight from ``espo_base_url`` so no label override can widen it.
    """
    if not settings.sandbox_nightly_reset:
        raise SandboxResetRefused("sandbox_nightly_reset is off for this deployment")
    if SANDBOX_URL_MARKER not in (settings.espo_base_url or "").lower():
        raise SandboxResetRefused(
            f"CRM base URL is not the sandbox ({settings.espo_base_url!r}) — refusing"
        )


async def reset_app_tables(engine, settings: Settings, *, apply: bool = False) -> dict:
    """Empty the training-data tables, leaving configuration in place.

    Returns a summary dict either way; with ``apply=False`` it reports the row
    counts it *would* clear and changes nothing, which is what the operations
    runbook uses to check the classification before arming the job.
    """
    guard(settings)

    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        for table in RESET_TABLES:
            result = await conn.execute(text(f'select count(*) from "{table}"'))
            counts[table] = int(result.scalar_one())

        if apply:
            # One statement for all of them: mutual foreign keys between these
            # tables are satisfied together. No CASCADE — if a table outside the
            # list references one of these, this must fail loudly rather than
            # quietly truncating configuration.
            targets = ", ".join(f'"{name}"' for name in RESET_TABLES)
            await conn.execute(text(f"truncate table {targets} restart identity"))

    total = sum(counts.values())
    log.info(
        "sandbox reset: %s %s rows across %s tables",
        "cleared" if apply else "would clear",
        total,
        len(RESET_TABLES),
    )
    return {"applied": apply, "total_rows": total, "tables": counts}


def classified_tables() -> set[str]:
    """Every table this module has an opinion about — the test's other half."""
    return set(RESET_TABLES) | set(KEEP_TABLES)


def unclassified(all_tables: Iterable[str]) -> set[str]:
    """Tables a migration created that nobody has classified yet."""
    return set(all_tables) - classified_tables()
