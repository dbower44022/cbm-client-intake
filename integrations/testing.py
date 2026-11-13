"""The integration test framework (prds/integrations-tab-plan.md § 3, part 2).

An **integration test** runs one integration's checks in order and collects its
**integration facts**. A **check** is a named coroutine that answers with one of
three outcomes and one line of detail:

* ``ok`` — the call succeeded;
* ``failed`` — the service answered and said no;
* ``unknown`` — the service could not be reached, or the check could not be
  made. A check that cannot reach its target says unknown, never ok.

A fourth state, ``skipped``, is for display only: a check whose feature is
switched off ("Not checked — switched off"). It never counts towards the
integration test's outcome.

Rules every check keeps (the phase 2 prompt):

* it never raises — the runner turns any exception into ``unknown``;
* it never writes to any outside service;
* a secret's value never reaches a detail line or a fact. The runner also
  scrubs every secret setting's value out of both before anything is returned
  or stored, so a vendor that echoes a credential back cannot leak it.
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

OK = "ok"
FAILED = "failed"
UNKNOWN = "unknown"
SKIPPED = "skipped"

#: One check gets this long unless it says otherwise (the same as setup/verify).
CHECK_TIMEOUT_SECONDS = 12.0
#: The whole integration test gets this long.
TEST_TIMEOUT_SECONDS = 30.0
#: A detail line is one line; anything longer is cut.
DETAIL_MAX = 400

SECRET_SHOWN_AS = "(secret)"

#: True while the nightly run (phase 5, integrations/nightly.py) is running a
#: test in the worker. A check whose value only the web process is given reads
#: it through :meth:`Context.web_only` (Doug's ruling 11-13-26, option A).
_NIGHTLY: contextvars.ContextVar[bool] = contextvars.ContextVar("integration_nightly", default=False)

NIGHT_SKIP = "Not checked at night: {what} is held by the web process only. The Test Integration button checks it."


class Skip(Exception):
    """Raised by a check whose feature is switched off: shown as skipped."""


class Blocked(Exception):
    """Raised by a check that cannot run because an earlier one failed:
    shown as unknown, with this detail."""


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    run: Callable[["Context"], Awaitable[tuple[str, str]]]
    timeout: float = CHECK_TIMEOUT_SECONDS


@dataclass
class Context:
    """What the checks of one integration test share."""

    settings: Any
    deps: Any = None
    # Values one check leaves for a later one (a client, a token result).
    state: dict[str, Any] = field(default_factory=dict)
    facts: list[dict[str, str]] = field(default_factory=list)
    # Extra strings to scrub, beyond the secret settings (for example a
    # service-account key read from the stored Email Setup).
    secrets: list[str] = field(default_factory=list)

    @property
    def nightly(self) -> bool:
        return _NIGHTLY.get()

    def web_only(self, value: Any, what: str) -> None:
        """At night, a value the worker is not given is skipped, never failed:
        a check that can never pass in the worker would alarm every night.
        A value present in the worker (saved at /setup) is checked as usual."""
        if self.nightly and not str(value or "").strip():
            raise Skip(NIGHT_SKIP.format(what=what))

    def fact(self, label: str, value: Any) -> None:
        text = "" if value is None else str(value)
        for f in self.facts:
            if f["label"] == label:
                f["value"] = text
                return
        self.facts.append({"label": label, "value": text})


def secret_values(settings: Any) -> list[str]:
    """Every secret setting's current value worth scrubbing."""
    from core.settings_registry import SETTINGS, is_secret

    out = []
    for spec in SETTINGS:
        if not is_secret(spec.key):
            continue
        value = getattr(settings, spec.key, None)
        if isinstance(value, str) and len(value.strip()) >= 6:
            out.append(value.strip())
    return out


def scrub(text: str, secrets: Iterable[str]) -> str:
    out = text or ""
    # Longest first, so a secret containing another is replaced whole.
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        if secret in out:
            out = out.replace(secret, SECRET_SHOWN_AS)
    return out


def _one_line(text: str) -> str:
    line = " ".join(str(text or "").split())
    return line if len(line) <= DETAIL_MAX else line[: DETAIL_MAX - 1] + "…"


def overall(results: list[dict[str, str]]) -> str:
    outcomes = {r["outcome"] for r in results}
    if FAILED in outcomes:
        return FAILED
    if UNKNOWN in outcomes:
        return UNKNOWN
    if OK in outcomes:
        return OK
    return UNKNOWN


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def run_checks(
    integration: str,
    checks: list[Check],
    ctx: Context,
    *,
    limit: float = TEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run ``checks`` in order and return the integration test's result.

    Never raises. The result carries no secret value: every detail line and
    fact is scrubbed of the secret settings and ``ctx.secrets``.
    """
    started = _now()
    clock = time.monotonic()
    results: list[dict[str, str]] = []
    for check in checks:
        remaining = limit - (time.monotonic() - clock)
        if remaining <= 0:
            outcome, detail = UNKNOWN, (
                f"Not run: the integration test reached its {limit:.0f}-second limit."
            )
        else:
            budget = min(check.timeout, remaining)
            try:
                outcome, detail = await asyncio.wait_for(check.run(ctx), budget)
            except Skip as exc:
                outcome, detail = SKIPPED, str(exc) or "Not checked — switched off."
            except Blocked as exc:
                outcome, detail = UNKNOWN, str(exc)
            except asyncio.TimeoutError:
                outcome, detail = UNKNOWN, f"The check did not finish within {budget:.0f} seconds."
            except Exception as exc:  # noqa: BLE001 — a check never raises out
                outcome, detail = UNKNOWN, (
                    f"The check could not be run: {type(exc).__name__}: {exc}"
                )
            if outcome not in (OK, FAILED, UNKNOWN, SKIPPED):
                outcome, detail = UNKNOWN, f"The check gave no usable answer ({outcome!r})."
        results.append({"key": check.key, "label": check.label,
                        "outcome": outcome, "detail": detail})

    secrets = secret_values(ctx.settings) + list(ctx.secrets)
    for r in results:
        r["detail"] = _one_line(scrub(r["detail"], secrets))
    facts = [{"label": f["label"], "value": _one_line(scrub(f["value"], secrets))}
             for f in ctx.facts]
    finished = _now()
    return {
        "integration": integration,
        "outcome": overall(results),
        "checks": results,
        "facts": facts,
        "startedAt": started.isoformat(),
        "finishedAt": finished.isoformat(),
        "durationMs": int((time.monotonic() - clock) * 1000),
    }


# --- running one integration's test -----------------------------------------

_locks: dict[str, asyncio.Lock] = {}


class AlreadyRunning(Exception):
    pass


def test_module(integ: Any) -> Optional[Any]:
    """The module holding ``integ``'s test, or None before its phase."""
    name = getattr(integ, "test_module", "")
    if not name:
        return None
    return importlib.import_module(name)


async def run_integration_test(integ: Any, settings: Any, deps: Any = None, *,
                               nightly: bool = False) -> dict[str, Any]:
    """Run ``integ``'s integration test. One at a time per integration in
    this process: a second request while one runs raises AlreadyRunning.
    ``nightly`` marks the worker's nightly run (checks skip web-only values)."""
    module = test_module(integ)
    if module is None:
        raise LookupError(f"{integ.name} has no integration test yet.")
    lock = _locks.setdefault(integ.key, asyncio.Lock())
    if lock.locked():
        raise AlreadyRunning(f"An integration test of {integ.name} is already running.")
    token = _NIGHTLY.set(bool(nightly))
    try:
        async with lock:
            return await module.run(settings, deps)
    finally:
        _NIGHTLY.reset(token)
