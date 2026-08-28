"""Load the settings-override layer BEFORE the app is built, and remember what
the process actually booted with.

WHY THIS EXISTS
===============
Doug's ruling, 2026-08-28: **every setting belongs on the Settings page.**
Hiding one where it cannot be viewed or edited is not acceptable, and the answer
to "changing this does nothing until a restart" is to say so on the page and
show which value is live — not to remove the setting from sight.

That ruling could not be honoured as the app was built. ``create_app`` reads
``get_settings()`` and mounts routers, builds middleware and configures logging
from it, and the override layer only loaded afterwards, inside the lifespan. So
an override for one of those keys did not merely wait for a restart — it
**never applied at all**, because every restart re-ran the mounting first.
Offering such a setting would have been a lie, which is why they were previously
hidden (and why v0.190.1's "takes effect on next deploy" badge produced a portal
tile whose routes did not exist).

:func:`load_at_boot` closes that gap. It installs the override layer *before*
``create_app`` inspects anything, so "restart-required" now means what it says.

THREE RULES IT KEEPS
====================
**Degrade to the deployment's own values, never to the code defaults.** A
database that is down, slow or holding a bad row must leave the app running on
its environment configuration. A database incident must not silently
reconfigure the application — that is settled ruling 6 of the System Settings
design and it applies with more force here, since this runs before anything is
serving.

**Never raise.** A failure here would mean the app does not boot at all. Every
path is caught; the outcome is recorded for the page to display.

**Remember what booted.** Once the layer is installed, the effective values of
the restart-required keys are snapshotted. That snapshot is the ONLY honest
answer to "what is this process actually running", because the periodic refresh
will happily install a newer value into the live settings object while the
routers, middleware and logging built at startup carry on using the old one.
Without it the page would read the new value back and report that a change had
taken effect when it had not.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("cbm_intake.boot_overrides")

# Outcomes, in the order they are worth knowing about.
BOOT_APPLIED = "applied"        # the override layer was installed at startup
BOOT_NONE = "none"              # nothing stored; the deployment's values stand
BOOT_DISABLED = "disabled"      # no database, or the override layer is off
BOOT_FAILED = "failed"          # could not read — running on the deployment's values
BOOT_SKIPPED = "skipped"        # a loop was already running (tests, embedded use)


@dataclass
class BootLoad:
    """What happened when the process started, for the Settings page to show."""

    outcome: str = BOOT_DISABLED
    detail: str = ""
    applied_keys: tuple[str, ...] = ()
    # The effective value of each restart-required key AS THIS PROCESS BOOTED.
    snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.outcome != BOOT_FAILED


_state = BootLoad()


def state() -> BootLoad:
    return _state


def reset() -> None:
    """For tests."""
    global _state
    _state = BootLoad()


def _snapshot(settings) -> dict[str, Any]:
    from core.settings_registry import BOOT_READ_KEYS

    return {k: getattr(settings, k, None) for k in sorted(BOOT_READ_KEYS)}


def load_at_boot(settings) -> BootLoad:
    """Install stored overrides, then record what this process booted with.

    Call once, at the very top of ``create_app``, before anything reads a
    setting. Safe to call when there is no database: it does nothing and says so.
    """
    global _state

    if not getattr(settings, "database_url", "") or not getattr(
        settings, "settings_overrides", True
    ):
        _state = BootLoad(
            outcome=BOOT_DISABLED,
            detail=(
                "No database, or the override layer is switched off. This process "
                "is running entirely on its deployment configuration."
            ),
            snapshot=_snapshot(settings),
        )
        return _state

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # the normal case at process start — no loop yet
    else:
        # Already inside a loop (a test, or an embedded caller). Reading
        # synchronously here would deadlock, and the periodic refresh in the
        # lifespan will pick the overrides up anyway.
        _state = BootLoad(
            outcome=BOOT_SKIPPED,
            detail="An event loop was already running, so the boot-time load was skipped.",
            snapshot=_snapshot(settings),
        )
        return _state

    try:
        _state = asyncio.run(_load(settings))
    except Exception as exc:  # noqa: BLE001 — the app must boot regardless
        log.warning(
            "boot-time settings load failed, continuing on the deployment's own "
            "values: %s", exc
        )
        _state = BootLoad(
            outcome=BOOT_FAILED,
            detail=f"{type(exc).__name__}: {exc}",
            snapshot=_snapshot(settings),
        )
    return _state


async def _load(settings) -> BootLoad:
    from core import config as config_module
    from core.settings_store import SettingsStore, global_overrides

    store: Optional[SettingsStore] = None
    try:
        store = SettingsStore(settings.database_url)
        rows = await store.load()
    except Exception as exc:  # noqa: BLE001 — degrade to the overlay, never the default
        log.warning(
            "boot-time settings read failed, continuing on the deployment's own "
            "values: %s", exc
        )
        return BootLoad(
            outcome=BOOT_FAILED,
            detail=f"{type(exc).__name__}: {exc}",
            snapshot=_snapshot(settings),
        )
    finally:
        if store is not None:
            try:
                await store.dispose()
            except Exception:  # noqa: BLE001 — nothing depends on a clean close here
                pass

    values = global_overrides(rows)
    if not values:
        return BootLoad(
            outcome=BOOT_NONE,
            detail="No stored overrides; the deployment's own values are in force.",
            snapshot=_snapshot(settings),
        )

    config_module.apply_overrides(values)
    log.info(
        "boot-time settings load: %d override(s) installed before app construction (%s)",
        len(values), ", ".join(sorted(values)),
    )
    return BootLoad(
        outcome=BOOT_APPLIED,
        detail=f"{len(values)} stored override(s) installed at startup.",
        applied_keys=tuple(sorted(values)),
        # Snapshot AFTER applying: this is what the process is really running.
        snapshot=_snapshot(settings),
    )
