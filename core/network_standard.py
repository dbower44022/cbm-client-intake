"""Stamp B — the CRM's configuration version, read for ``/healthz``.

Every chapter in the network runs its own EspoCRM, and the whole point of the
configuration-as-an-artifact work is that they all hold the *same* one. That
needs each CRM to carry a stamp saying "I am running configuration version X,
applied on date Y" — the CRM's equivalent of the Alembic version row in the
app's own Postgres. The stamp lives in the CRM rather than in the app's
environment for three reasons: it describes the CRM, it must survive the app
being redeployed or replaced entirely, and only the applier is entitled to write
it (an environment variable could be edited by anyone with the console, and
would then lie). Ruled 2026-08-26 (D1); built as ``CNetworkStandard``, one
single-record entity, five scalars and no links.

Three properties this module exists to hold, in the order they would hurt:

**``/healthz`` never waits on the CRM.** The health check deliberately does not
ping EspoCRM — a CRM outage must not take the web tier down, since durable
capture and the async worker exist precisely to ride one out. So nothing here is
called from the request path. :func:`refresh` runs on a timer and caches; the
handler serves :func:`current`, which touches no network and cannot block.

**Absent, forbidden and unreachable are three different facts.** Collapsing them
is this project's documented failure mode, and it is the specific defect the
conformance check was rewritten to stop making: it turns "your API key lost its
role" into "your CRM is missing an entity". They matter here for an immediate
and concrete reason — production's ``CNetworkStandard`` is owed at a Sunday
release slot and this code may well deploy before it, so ``absent`` is the
*expected* production state for a while and must not read as a fault. A fleet
console has to be able to say "18 conformant, 1 drifted, 1 unreachable" without
guessing which is which.

**Nothing here may fail a health check.** Every path is wrapped; the worst
outcome is a null block and a log line.

The probe ships **dark**: ``crm_config_refresh_seconds`` defaults to 0, which
disables it entirely, and it is switched on per deployment (crm-test first) the
way this repo gates anything that touches runtime. Zero reports ``disabled``,
which is honest rather than silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.espo import EspoApi, EspoError, is_forbidden, is_not_found

log = logging.getLogger(__name__)

ENTITY = "CNetworkStandard"

# The five states, and why each is not one of the others.
#
#   stamped      a version is recorded — the only state that answers the
#                question the stamp was built to answer
#   unstamped    the entity exists and holds no row. "Configured to report,
#                never applied to" — the honest state of every instance until
#                an applier first runs, and deliberately NOT an error
#   absent       the CRM has no such entity: this instance predates the build,
#                or the build has not reached it yet
#   forbidden    the entity is there and this credential may not read it — a
#                grant problem, fixable by an admin, and never a statement
#                about the configuration
#   unreachable  the CRM could not be asked at all. Conformance is UNKNOWN,
#                which is not the same as bad
#   disabled     the probe is switched off here (refresh interval 0)
STATE_STAMPED = "stamped"
STATE_UNSTAMPED = "unstamped"
STATE_ABSENT = "absent"
STATE_FORBIDDEN = "forbidden"
STATE_UNREACHABLE = "unreachable"
STATE_DISABLED = "disabled"


@dataclass(frozen=True)
class CrmConfig:
    """One cached reading of the CRM's configuration stamp."""

    state: str = STATE_DISABLED
    version: Optional[str] = None
    applied_at: Optional[str] = None
    fingerprint: Optional[str] = None

    def as_health(self) -> dict[str, Any]:
        """The ``/healthz`` shape.

        The three documented keys are always present and always null unless a
        version was actually read, so a consumer that only knows the documented
        contract still works. ``state`` is the extension that keeps a
        credential problem from reading as a configuration problem.
        """
        return {
            "state": self.state,
            "version": self.version,
            "appliedAt": self.applied_at,
            "fingerprint": self.fingerprint,
        }


# Process-wide cache. Written only by `refresh`, read only by `current`.
_cached = CrmConfig()


def current() -> CrmConfig:
    """The last successful reading. Never touches the network."""
    return _cached


def reset() -> None:
    """Drop the cache back to its startup value. For tests."""
    global _cached
    _cached = CrmConfig()


async def read(client: EspoApi) -> CrmConfig:
    """Ask the CRM for its stamp and classify the answer.

    Returns a :class:`CrmConfig` for every outcome including the failures —
    there is no exception path out of here, because the caller is a background
    task whose only job is to keep a health field current.
    """
    try:
        # maxSize=1: the entity is single-record by design, and a page size
        # over the CRM's list limit is a 403 rather than a truncation.
        envelope = await client.list(ENTITY, max_size=1, order_by="createdAt", order="desc")
    except EspoError as exc:
        # A transport failure arrives as EspoTransportError, which is an
        # EspoError, so this one net covers a CRM outage too.
        if is_forbidden(exc):
            log.warning(
                "crmConfig: %s is present but this credential may not read it — "
                "the API role is missing a read grant on the scope (%s)",
                ENTITY,
                exc,
            )
            return CrmConfig(state=STATE_FORBIDDEN)
        if is_not_found(exc):
            log.info(
                "crmConfig: this CRM has no %s entity yet — expected until the "
                "configuration stamp is built here",
                ENTITY,
            )
            return CrmConfig(state=STATE_ABSENT)
        log.warning("crmConfig: could not read %s: %s", ENTITY, exc)
        return CrmConfig(state=STATE_UNREACHABLE)
    except Exception as exc:  # noqa: BLE001 — a health field must never raise
        log.warning("crmConfig: unexpected failure reading %s: %s", ENTITY, exc)
        return CrmConfig(state=STATE_UNREACHABLE)

    rows = (envelope or {}).get("list") or []
    if not rows:
        # Built, never applied to. A real and expected state, not a fault.
        return CrmConfig(state=STATE_UNSTAMPED)

    row = rows[0] or {}
    version = row.get("standardVersion") or row.get("name") or None
    if not version:
        # A row with no version is closer to "never applied" than to "stamped":
        # claiming conformance we cannot name is worse than claiming none.
        log.warning("crmConfig: a %s row exists but carries no version", ENTITY)
        return CrmConfig(state=STATE_UNSTAMPED)
    return CrmConfig(
        state=STATE_STAMPED,
        version=str(version),
        applied_at=row.get("appliedAt") or None,
        fingerprint=row.get("planFingerprint") or None,
    )


async def refresh(client: EspoApi) -> CrmConfig:
    """Read the stamp and update the cache. Returns what was cached."""
    global _cached
    _cached = await read(client)
    return _cached
