"""The nightly integration test (prds/integrations-tab-plan.md § 5, ruling I8;
the design Doug approved 11-13-26, phase 5 stopping point 1, option A).

Once a day, at ``integration_test_hour`` in ``integration_test_tz``, the worker
runs the integration test of every integration that is in use and has at
least one feature switched on — EspoCRM always — while ``INTEGRATIONS_TAB`` is
on. Each run is stored with ``trigger=nightly`` and no person. The diagnosis
agent never runs on its own.

**A check whose value only the web process is given is skipped at night**, not
failed (option A): the EspoCRM provisioning account, Lob's webhook secret and
Google's All Members group, unless the value reached the worker through
``/setup`` (``integrations.testing.Context.web_only``).

**The alert remembers through the stored runs, never the worker's memory**, so
a deploy or a restart never repeats one:

* a **failed** integration alerts when its set of failed checks differs from
  the last earlier nightly run that was not unknown — an unchanged failure is
  not repeated, and a night of "unknown" in between changes nothing;
* **unknown** alerts once, on the third night in a row;
* a **recovery** (ok after a failure, or after three or more unknown nights) is
  reported once.

Every alert goes through ``core.monitoring.send_alert``, with a link to the
integration's sub-tab. Never raises; every call the tests make is a read.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from integrations import registry
from integrations.guard import switches_on
from integrations.store import NIGHTLY
from integrations.testing import run_integration_test

log = logging.getLogger("cbm_intake.integrations.nightly")

#: Nights in a row an integration may read unknown before it alerts.
UNKNOWN_NIGHTS = 3

Send = Callable[[str], Awaitable[None]]
Runner = Callable[[Any, Any], Awaitable[dict[str, Any]]]


def due(settings: Any) -> list[Any]:
    """The integrations the nightly run covers, in registry order."""
    out = []
    for integ in registry.INTEGRATIONS:
        if not integ.testable:
            continue
        if integ.always_in_use:
            out.append(integ)
            continue
        if not registry.in_use(integ, settings):
            continue
        if switches_on(integ, settings, {}):
            out.append(integ)
    return out


def _local(settings: Any, iso: Optional[str]) -> str:
    try:
        from zoneinfo import ZoneInfo

        when = datetime.fromisoformat(str(iso))
        return when.astimezone(ZoneInfo(settings.integration_test_tz)).strftime("%m-%d-%y %H:%M")
    except Exception:  # noqa: BLE001 — a bad time zone still gets a time
        return str(iso or "")[:16].replace("T", " ") + " UTC"


def _link(settings: Any, key: str) -> str:
    base = (getattr(settings, "app_base_url", "") or "").strip().rstrip("/")
    return f"{base}/setup/#integrations/{key}" if base else f"/setup/#integrations/{key}"


def _failed(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in run.get("checks") or [] if c.get("outcome") == "failed"]


def _failed_keys(run: Optional[dict[str, Any]]) -> frozenset[str]:
    return frozenset(c.get("key") for c in _failed(run or {}))


def _head(settings: Any, integ: Any, what: str, run: dict[str, Any]) -> str:
    return (f"Integration test {what}: {integ.name} (environment: {settings.environment}), "
            f"{_local(settings, run.get('finishedAt') or run.get('startedAt'))}.")


def message(settings: Any, integ: Any, run: dict[str, Any],
            earlier: list[dict[str, Any]]) -> Optional[str]:
    """The alert this night's ``run`` calls for, given the ``earlier`` nightly
    runs (newest first, this one excluded), or None."""
    outcome = run.get("outcome")
    open_line = f"Open: {_link(settings, integ.key)}"
    if outcome == "failed":
        settled = next((r for r in earlier if r.get("outcome") != "unknown"), None)
        if settled and settled.get("outcome") == "failed" and _failed_keys(settled) == _failed_keys(run):
            return None
        lines = [_head(settings, integ, "failed", run)]
        for c in _failed(run):
            lines.append(f"Failed: {c.get('label')} ({c.get('detail')})")
        lines.append(open_line)
        return "\n".join(lines)
    if outcome == "unknown":
        streak = 1
        for r in earlier:
            if r.get("outcome") != "unknown":
                break
            streak += 1
        if streak != UNKNOWN_NIGHTS:
            return None
        lines = [_head(settings, integ, f"could not be completed for {UNKNOWN_NIGHTS} nights", run)]
        for c in run.get("checks") or []:
            if c.get("outcome") == "unknown":
                lines.append(f"Unknown: {c.get('label')} ({c.get('detail')})")
        lines.append(open_line)
        return "\n".join(lines)
    if outcome == "ok" and earlier:
        prev = earlier[0]
        streak = 0
        for r in earlier:
            if r.get("outcome") != "unknown":
                break
            streak += 1
        settled = earlier[streak] if streak < len(earlier) else None
        if prev.get("outcome") == "failed" or streak >= UNKNOWN_NIGHTS or (
                streak and settled and settled.get("outcome") == "failed"):
            return "\n".join([_head(settings, integ, "passes again", run), open_line])
    return None


async def _default_runner(integ: Any, settings: Any) -> dict[str, Any]:
    return await run_integration_test(integ, settings, nightly=True)


async def run_nightly(
    settings: Any,
    store: Any,
    *,
    send: Optional[Send] = None,
    runner: Optional[Runner] = None,
) -> dict[str, Any]:
    """One nightly pass. Returns a summary for the log: each integration's
    outcome, and the alerts sent. Never raises."""
    from core.monitoring import send_alert

    send = send or (lambda text: send_alert(settings, text))
    runner = runner or _default_runner
    summary: dict[str, Any] = {"outcomes": {}, "alerts": [], "stored": 0}
    for integ in due(settings):
        try:
            result = await runner(integ, settings)
        except Exception as exc:  # noqa: BLE001 — one integration never stops the rest
            log.warning("nightly integration test of %s could not run: %s", integ.key, exc)
            summary["outcomes"][integ.key] = "not run"
            continue
        summary["outcomes"][integ.key] = result.get("outcome")
        earlier: list[dict[str, Any]] = []
        if store is not None:
            try:
                earlier = await store.recent(integ.key, trigger=NIGHTLY, limit=UNKNOWN_NIGHTS + 2)
                await store.record(result, trigger=NIGHTLY)
                summary["stored"] += 1
            except Exception as exc:  # noqa: BLE001 — the alert still goes
                log.warning("nightly integration test of %s could not be stored: %s", integ.key, exc)
        text = message(settings, integ, result, earlier)
        if text:
            try:
                await send(text)
                summary["alerts"].append(integ.key)
            except Exception as exc:  # noqa: BLE001
                log.warning("nightly integration alert for %s could not be sent: %s", integ.key, exc)
    log.info("nightly integration test: %s; alerts: %s",
             ", ".join(f"{k}={v}" for k, v in summary["outcomes"].items()) or "nothing due",
             ", ".join(summary["alerts"]) or "none")
    return summary


def next_run_time(settings: Any, after: datetime, next_local_hour: Callable[..., datetime]) -> datetime:
    """The next nightly run, strictly after ``after`` (worker's ``_next_local_hour``)."""
    return next_local_hour(settings.integration_test_hour, settings.integration_test_tz,
                           after.astimezone(timezone.utc), label="integration test")
