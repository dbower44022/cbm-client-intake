"""Prove a setting's new value works BEFORE it is stored, and prove the system
still works after.

Doug's ruling, 2026-08-28: *"All settings should be editable, unless a change
would make the system unusable. Then there must be a verification that the
system is still functional."*

The second sentence is the design. The old answer to a dangerous setting was to
hide it, which pushed the risk onto whoever edits the deployment overlay by hand
at 2am with no check at all — a worse place for it. The new answer is that the
system proves the value before accepting it, and proves itself afterwards.

THREE THINGS HAPPEN, IN THIS ORDER
==================================
1. **Pre-flight.** The candidate value is tried for real — a CRM key is used to
   call that CRM and confirm it is one this application can use. A value that
   fails is **refused and never stored**, and the message is the actual error
   rather than "invalid". Each probe claims exactly what it checked and no
   more: the Google one says it cannot see whether delegation was granted.
2. **Post-apply.** Once stored and installed, a functional check runs. If the
   system is no longer working, the change is **reverted automatically** and the
   failure reported.
3. **Confirm-or-revert.** For the few settings that can lock the admin out of
   this page altogether, neither check above can help — the app would be working
   perfectly and simply refusing to let anyone back in. Those changes carry a
   deadline: unless a human confirms the system still works, they revert on
   their own. This is the network-engineer's ``commit confirmed``, and it is the
   only mechanism that survives the operator being locked out.

WHAT A PROBE MUST BE
====================
**Cheap, decisive and read-only.** A probe runs inside a request while an admin
waits. It gets a short timeout and it never writes anything anywhere.

**Honest about not knowing.** A probe that cannot reach the thing it is testing
returns ``UNKNOWN``, never ``OK``. Reporting success for an unverified value is
this codebase's documented failure mode, and it is exactly what a verification
feature must not do. UNKNOWN does not block the save — an unreachable CRM should
not stop an admin fixing a setting during an outage — but it is reported plainly
and the change still gets its confirm-or-revert deadline.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from core.config import Settings, env_values

log = logging.getLogger("cbm_intake.setup.verify")

# A probe gets this long, total. An admin is waiting on it.
PROBE_TIMEOUT_SECONDS = 12.0

OK = "ok"
FAILED = "failed"
UNKNOWN = "unknown"
NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class Result:
    outcome: str
    detail: str = ""

    @property
    def blocks_save(self) -> bool:
        """Only an outright failure stops a save.

        UNKNOWN deliberately does not: an admin fixing configuration during an
        outage must not be blocked by the outage. It is reported, and the change
        still gets its confirm-or-revert deadline.
        """
        return self.outcome == FAILED

    def as_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "detail": self.detail}


def _candidate(key: str, value: str) -> Settings:
    """A Settings built from this deployment's values with one key replaced.

    Never mutates the live configuration — the whole point is to try the value
    without adopting it.
    """
    return Settings(**{**env_values(), key: value})


async def _crm_reachable(settings: Settings) -> Result:
    """Can we talk to the CRM these settings describe, as the key they name?"""
    if settings.espo_dry_run:
        return Result(OK, "Dry-run mode: no CRM calls are made, so nothing to check.")
    if not settings.espo_base_url:
        return Result(FAILED, "No CRM address is set.")
    if not settings.espo_api_key:
        return Result(FAILED, "No CRM API key is set.")

    from core.espo import EspoClient

    client = EspoClient(settings.espo_base_url, settings.espo_api_key, 10)
    # Ask for ONE entity's field definitions rather than the whole metadata
    # document: it is a far smaller response and it proves more. A stranger's
    # EspoCRM would answer a bare connectivity check and then fail on every
    # write, because it has none of this application's entities.
    try:
        defs = await client.metadata("entityDefs.CEngagement.fields")
    except Exception as exc:  # noqa: BLE001 — the message is the product here
        text = str(exc)
        if "401" in text or "403" in text:
            return Result(
                FAILED, f"The CRM answered but rejected this key: {text}"
            )
        return Result(UNKNOWN, f"Could not reach the CRM to check: {text}")

    if not defs:
        return Result(
            FAILED,
            "That address answered, but it is not a CRM this application can "
            "use — it has no CEngagement entity. Check the address.",
        )
    return Result(OK, f"Connected; CEngagement has {len(defs)} fields.")


async def _probe_crm_setting(key: str, value: str) -> Result:
    return await _crm_reachable(_candidate(key, value))


async def _probe_google_service_account(_key: str, value: str) -> Result:
    """Is this a usable service-account key?

    Parses and checks the fields delegation actually needs. It does NOT mint a
    token: that is a network round trip to Google for a credential whose real
    failure mode is the domain-wide-delegation grant, which this cannot see
    either. Claiming more than it checks would be the false-confidence this
    module exists to avoid.
    """
    import json as _json

    if not value.strip():
        return Result(OK, "Cleared — every Google integration will be inert.")
    try:
        data = _json.loads(value)
    except Exception as exc:  # noqa: BLE001
        return Result(FAILED, f"That is not valid JSON: {exc}")
    if not isinstance(data, dict):
        return Result(FAILED, "A service-account key must be a JSON object.")
    missing = [
        f for f in ("type", "client_email", "private_key", "token_uri")
        if not data.get(f)
    ]
    if missing:
        return Result(
            FAILED, f"That JSON is missing {', '.join(missing)} — not a usable key."
        )
    if data.get("type") != "service_account":
        return Result(
            FAILED,
            f"That is a {data.get('type')!r} key, not a service-account key.",
        )
    return Result(
        OK,
        f"A service-account key for {data.get('client_email')}. Whether "
        "domain-wide delegation is granted cannot be checked from here.",
    )


def _probe_nonempty(label: str, min_len: int = 1):
    async def probe(_key: str, value: str) -> Result:
        if len(value.strip()) < min_len:
            return Result(
                FAILED,
                f"{label} must be at least {min_len} characters — a short or empty "
                "value would leave this unprotected.",
            )
        return Result(OK, f"{label} accepted. It is not checked against anything else.")

    return probe


async def _probe_session_secret(_key: str, value: str) -> Result:
    if len(value.strip()) < 32:
        return Result(
            FAILED,
            "A session secret shorter than 32 characters is not safe — sessions "
            "are signed with it.",
        )
    return Result(
        OK,
        "Accepted. Note this signs every session cookie, so changing it signs "
        "everyone out, including you.",
    )


# key -> probe. A setting with no entry here is not verified, which is the
# ordinary case; the tier is what decides whether a probe is REQUIRED.
PROBES: dict[str, Callable[[str, str], Awaitable[Result]]] = {
    "espo_api_key": _probe_crm_setting,
    "espo_base_url": _probe_crm_setting,
    "espo_dry_run": _probe_crm_setting,
    "google_service_account_json": _probe_google_service_account,
    "session_secret": _probe_session_secret,
    "espo_provision_password": _probe_nonempty("A password", 8),
    "espo_provision_username": _probe_nonempty("A username", 3),
}


async def probe(key: str, value: str) -> Result:
    """Try ``value`` for ``key``. Never raises, never writes, always bounded."""
    fn = PROBES.get(key)
    if fn is None:
        return Result(NOT_CHECKED, "")
    try:
        return await asyncio.wait_for(fn(key, value), PROBE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return Result(
            UNKNOWN,
            f"The check did not finish within {PROBE_TIMEOUT_SECONDS:.0f} seconds.",
        )
    except Exception as exc:  # noqa: BLE001 — a probe must never break a save
        log.warning("probe for %s raised: %s", key, exc)
        return Result(UNKNOWN, f"The check could not be run: {exc}")


async def still_functional(settings: Optional[Settings] = None) -> Result:
    """Is the system still working, right now, with whatever is installed?

    Run AFTER a change has been applied. Deliberately narrow: it asks whether
    the things the application cannot work without are answering, not whether
    every feature is healthy. A broad check would produce false alarms that
    revert good changes, which is worse than no check at all.
    """
    from core.config import get_settings

    settings = settings or get_settings()
    return await _crm_reachable(settings)
