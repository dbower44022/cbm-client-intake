"""Periodic monitoring — V2 Phase 3 (Requirements 5 + 6).

Two checks the worker runs on a timer:

  * ``run_alert_check`` — alerts when delivery is failing or a backlog is
    building (from the store's metrics).
  * ``run_schema_drift_check`` — alerts when an enum value the forms rely on has
    gone missing from EspoCRM, before a submission fails on it.

Alerts go to a Slack-compatible webhook (``ALERT_WEBHOOK_URL``) or, if none is
set, to the log. Each alert has a cooldown so a standing condition doesn't spam.
The check functions accept injected ``send``/``fetch`` callables for testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx

from .config import Settings
from .espo import EspoClient, EspoError
from .schema_contract import EXPECTED_ENUMS

log = logging.getLogger("cbm_intake.monitoring")

Send = Callable[[str], Awaitable[None]]
FetchOptions = Callable[[str, str], Awaitable[Optional[list[str]]]]


async def send_alert(settings: Settings, text: str) -> None:
    """Deliver an alert to the webhook, or log it if none is configured."""
    if not settings.alert_webhook_url:
        log.warning("ALERT (no webhook configured): %s", text)
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.alert_webhook_url, json={"text": text})
        log.info("alert sent: %s", text)
    except Exception as exc:  # noqa: BLE001 — alerting must never crash the worker
        log.warning("alert webhook failed (%s); alert was: %s", exc, text)


def _due(state: dict, key: str, now: datetime, cooldown: int) -> bool:
    """True if this alert key hasn't fired within the cooldown; records the time."""
    last = state.get(key)
    if last is not None and (now - last).total_seconds() < cooldown:
        return False
    state[key] = now
    return True


async def run_alert_check(
    store,
    settings: Settings,
    state: dict,
    *,
    now: Optional[datetime] = None,
    send: Optional[Send] = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    send = send or (lambda text: send_alert(settings, text))
    metrics = await store.metrics()

    needs = metrics.get("needsAttention", 0)
    if needs >= settings.alert_needs_attention_threshold and _due(
        state, "needs_attention", now, settings.alert_cooldown_seconds
    ):
        await send(
            f"{needs} submission(s) need attention — delivery to the CRM failed. "
            f"Review them in the operations console (/ops)."
        )

    age = metrics.get("oldestPendingAgeSeconds")
    if (
        age is not None
        and age >= settings.alert_pending_age_minutes * 60
        and _due(state, "backlog", now, settings.alert_cooldown_seconds)
    ):
        await send(
            f"Delivery backlog: the oldest undelivered submission is "
            f"{int(age // 60)} minutes old. The CRM may be slow or unavailable."
        )


def _default_fetch(settings: Settings) -> FetchOptions:
    client = EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )

    async def fetch(entity: str, field: str) -> Optional[list[str]]:
        return await client.metadata_enum_options(entity, field)

    return fetch


async def run_schema_drift_check(
    settings: Settings,
    state: dict,
    *,
    now: Optional[datetime] = None,
    fetch: Optional[FetchOptions] = None,
    send: Optional[Send] = None,
) -> None:
    # Nothing to check without a real CRM to read metadata from.
    if settings.espo_dry_run or not settings.espo_api_key:
        return
    now = now or datetime.now(timezone.utc)
    send = send or (lambda text: send_alert(settings, text))
    fetch = fetch or _default_fetch(settings)

    for (entity, field), expected in EXPECTED_ENUMS.items():
        try:
            live = await fetch(entity, field)
        except EspoError as exc:
            log.warning("schema-drift fetch failed for %s.%s: %s", entity, field, exc)
            continue
        if live is None:
            continue
        missing = [value for value in expected if value not in live]
        if missing and _due(state, f"drift:{entity}.{field}", now, settings.alert_cooldown_seconds):
            await send(
                f"CRM schema drift: {entity}.{field} no longer offers expected "
                f"value(s) {missing}. Forms/tools that send them will fail — "
                f"reconcile the form options with the CRM."
            )
