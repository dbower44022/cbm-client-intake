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
    """Deliver an alert to every configured channel — the Slack-compatible
    webhook and/or EMAIL (CBM uses no messaging service, so email via the
    existing Gmail delegation is the primary channel — Doug 2026-07-20).
    With no channel configured, or every delivery failing, the alert lands in
    the log at WARNING so it is never silently dropped. Never raises."""
    delivered = False
    if settings.alert_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.alert_webhook_url, json={"text": text})
            log.info("alert sent (webhook): %s", text)
            delivered = True
        except Exception as exc:  # noqa: BLE001 — alerting must never crash the worker
            log.warning("alert webhook failed (%s); alert was: %s", exc, text)
    if settings.alert_email_to_list:
        try:
            await _email_alert(settings, text)
            log.info("alert sent (email to %s)", ", ".join(settings.alert_email_to_list))
            delivered = True
        except Exception as exc:  # noqa: BLE001
            log.warning("alert email failed (%s); alert was: %s", exc, text)
    if not delivered:
        log.warning("ALERT (no delivery channel configured/working): %s", text)


async def _email_alert(settings: Settings, text: str) -> None:
    """One alert as a plain-text email, sent via the Gmail service-account
    delegation AS ``alert_email_from`` (a real @cbmentors.org mailbox;
    OPS_MAILBOX is the fallback sender) TO the ``alert_email_to`` list."""
    # Lazy imports: comms.sync imports this module (its failure alerts), and
    # comms.service imports comms.sync — a top-level import here would cycle.
    from comms.service import get_service_account
    from core.gmail import GmailClient, build_mime

    sender = (settings.alert_email_from or settings.ops_mailbox or "").strip().lower()
    if not sender:
        raise RuntimeError(
            "ALERT_EMAIL_TO is set but no sender mailbox is configured — set "
            "ALERT_EMAIL_FROM (an @cbmentors.org Workspace mailbox) or OPS_MAILBOX"
        )
    sa_info = await get_service_account(settings)
    if sa_info is None:
        raise RuntimeError("no Google service-account credentials configured")
    # First line of the alert makes the subject scannable in an inbox.
    first_line = text.strip().splitlines()[0][:120] if text.strip() else "alert"
    mime = build_mime(
        sender=sender,
        sender_name="CBM Intake Alerts",
        to=settings.alert_email_to_list,
        subject=f"[CBM Intake — {settings.environment}] {first_line}",
        body_text=text,
    )
    gmail = GmailClient(sa_info, sender, settings.request_timeout_seconds)
    try:
        await gmail.send(mime)
    finally:
        await gmail.aclose()


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

    # A lease-expired ``processing`` row means a worker died mid-delivery
    # (P1-6). A healthy worker reclaims it within a claim pass or two; alerting
    # on it makes a crash-looping or dead worker visible even before the
    # backlog-age alert would fire.
    stranded = metrics.get("stranded") or 0
    if stranded and _due(state, "stranded", now, settings.alert_cooldown_seconds):
        await send(
            f"{stranded} submission(s) are stranded mid-delivery (their worker "
            f"lease expired) — a delivery worker likely crashed. They will be "
            f"reclaimed automatically if a worker is running; check the worker "
            f"component if this persists."
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
