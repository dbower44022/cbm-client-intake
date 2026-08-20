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
from .espo import EspoClient, EspoError, validation_message
from .schema_contract import EXPECTED_ENUMS

log = logging.getLogger("cbm_intake.monitoring")

# How many failed submissions an alert names individually before summarizing.
_ALERT_DETAIL_LIMIT = 5

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


def console_url(settings: Settings, submission_id: Optional[str] = None) -> str:
    """A clickable Submission Admin URL, or ``""`` when ``APP_BASE_URL`` is unset.

    An alert that only says "review them in /ops" makes the reader hunt for the
    site and then for the row; with a base URL configured, every alert carries a
    direct link (``?submission=<id>`` opens that submission's detail).
    """
    base = (settings.app_base_url or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/ops/?submission={submission_id}" if submission_id else f"{base}/ops/"


def _console_line(settings: Settings) -> str:
    """The closing "where to look" line every alert ends with."""
    console = console_url(settings)
    return (
        f"Submission Admin: {console}" if console
        else "Submission Admin: the /ops page of the intake app."
    )


def _age(now: datetime, when) -> str:
    """``2026-06-30 17:39 UTC (26 days ago)`` — when the submission came in."""
    if when is None:
        return "unknown"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    hours = max(0, int((now - when).total_seconds() // 3600))
    if hours < 48:
        ago = "less than an hour ago" if hours < 1 else (
            "1 hour ago" if hours == 1 else f"{hours} hours ago"
        )
    else:
        ago = f"{hours // 24} days ago"
    return f"{when:%Y-%m-%d %H:%M} UTC ({ago})"


def _why(last_error: Optional[str]) -> str:
    """The failure in plain language where the CRM's error can be parsed
    (a validation rejection names the field), else the raw error, trimmed."""
    if not last_error:
        return "no error was recorded"
    readable = validation_message(Exception(last_error))
    if readable:
        # Drop the router's "Correct that field and try again." tail — the
        # reader of an alert isn't the person who typed the value.
        return readable.replace(" Correct that field and try again.", "")
    return last_error.strip().splitlines()[0][:300]


def _form_label(slug: Optional[str]) -> str:
    """The form's human title ("Become a Sponsor") rather than its slug."""
    if not slug:
        return "submission"
    try:
        from forms import SPECS_BY_SLUG

        spec = SPECS_BY_SLUG.get(slug)
        if spec is not None:
            from core.branding import MODE_TEXT, render as render_branding
            from core.config import get_settings

            return render_branding(spec.title, get_settings(), MODE_TEXT)
    except Exception:  # noqa: BLE001 — a label is never worth failing an alert
        pass
    return slug


async def _failed_rows(store) -> list[dict]:
    """The OPEN needs-attention submissions, newest first — best-effort, since
    an alert must never fail over its own detail lookup."""
    try:
        rows = await store.list_submissions(status="needs_attention", limit=50)
    except Exception as exc:  # noqa: BLE001 — detail is a nicety, the alert is not
        log.warning("could not load needs-attention detail for the alert: %s", exc)
        return []
    return [r for r in rows if not r.get("closed_at")]


def _needs_attention_report(
    settings: Settings, rows: list[dict], count: int, now: datetime
) -> str:
    """The needs-attention alert body: what failed, for whom, why, and where to
    fix it. Degrades to the bare count when the row detail isn't available."""
    one = count == 1
    lines = [
        f"{count} intake {'submission was' if one else 'submissions were'} NOT "
        f"delivered to the CRM and {'needs' if one else 'need'} a decision.",
        f"Environment: {settings.environment}.",
        "",
    ]
    for i, row in enumerate(rows[:_ALERT_DETAIL_LIMIT], start=1):
        email = row.get("email") or "no email captured"
        lines.append(f"{i}. {_form_label(row.get('form_slug'))} — {email}")
        lines.append(
            f"   Received: {_age(now, row.get('received_at'))}"
            f" · delivery attempts: {row.get('attempt_count') or 0}"
        )
        lines.append(f"   Why it failed: {_why(row.get('last_error'))}")
        link = console_url(settings, row.get("id"))
        if link:
            lines.append(f"   Open it: {link}")
        else:
            lines.append(f"   Submission id: {row.get('id')}")
        lines.append("")
    if count > len(rows[:_ALERT_DETAIL_LIMIT]):
        lines.append(
            f"…and {count - len(rows[:_ALERT_DETAIL_LIMIT])} more — see the console."
        )
        lines.append("")
    lines.append(
        "What to do: open each one in Submission Admin and either fix the cause "
        "and Re-drive it, or Close it with a reason. A closed submission stops "
        "alerting; leaving one open repeats this message every hour."
    )
    lines.append(_console_line(settings))
    return "\n".join(lines)


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

    # Only OPEN failures are actionable: an admin who closed one in the console
    # has made the decision the alert is asking for, and the machine status
    # stays ``needs_attention`` forever (it is not human-editable), so counting
    # closed rows makes the alert impossible to clear. Older stores that don't
    # report the open count fall back to the raw status count.
    needs = metrics.get("needsAttentionOpen")
    if needs is None:
        needs = metrics.get("needsAttention", 0)
    if needs >= settings.alert_needs_attention_threshold and _due(
        state, "needs_attention", now, settings.alert_cooldown_seconds
    ):
        await send(_needs_attention_report(settings, await _failed_rows(store), needs, now))

    age = metrics.get("oldestPendingAgeSeconds")
    if (
        age is not None
        and age >= settings.alert_pending_age_minutes * 60
        and _due(state, "backlog", now, settings.alert_cooldown_seconds)
    ):
        backlog = metrics.get("backlog") or 0
        await send(
            f"Delivery backlog: the oldest undelivered submission is "
            f"{int(age // 60)} minutes old ({backlog} waiting). The CRM may be "
            f"slow or unavailable — submissions are safely stored and will "
            f"deliver automatically once it recovers.\n"
            f"Environment: {settings.environment}.\n"
            f"{_console_line(settings)}"
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
            f"component if this persists.\n"
            f"Environment: {settings.environment}.\n"
            f"{_console_line(settings)}"
        )


async def run_worker_liveness_check(
    store,
    settings: Settings,
    state: dict,
    *,
    now: Optional[datetime] = None,
    send: Optional[Send] = None,
) -> None:
    """WEB-side worker liveness (2026-07-23): a dead worker can't alert on
    itself, so the web process — which survives it — watches the heartbeat
    row and alerts when it goes stale; a one-time all-clear goes out on
    recovery. Pairs with an external uptime check on ``/healthz`` (which
    covers the web process itself being down — the case THIS check can't
    see). ``state`` carries the cooldown stamps, the alerted flag, and a
    first-seen stamp so a fresh environment (worker not yet started, no
    heartbeat row) gets a grace window instead of an instant alert.
    """
    now = now or datetime.now(timezone.utc)
    send = send or (lambda text: send_alert(settings, text))
    threshold = settings.worker_heartbeat_alert_seconds
    state.setdefault("liveness_first_seen", now)

    metrics = await store.metrics()
    age = metrics.get("workerHeartbeatAgeSeconds")
    if age is None:
        # Never stamped: stale only once we've been watching longer than the
        # threshold (web usually boots before the worker's first stamp).
        stale = (
            now - state["liveness_first_seen"]
        ).total_seconds() >= threshold
    else:
        stale = age >= threshold

    if stale:
        if _due(state, "worker_liveness", now, settings.alert_cooldown_seconds):
            state["liveness_alerted"] = True
            last = f"{int(age)}s ago" if age is not None else "never"
            await send(
                f"The delivery worker's heartbeat is stale (last beat: {last}; "
                f"threshold {threshold}s) — the worker may be down or "
                f"crash-looping. Submissions will queue safely until it "
                f"recovers; check the delivery-worker component's logs in the "
                f"DigitalOcean console.\n"
                f"Environment: {settings.environment}."
            )
    elif state.get("liveness_alerted"):
        state["liveness_alerted"] = False
        # Clear the cooldown stamp so the NEXT incident alerts immediately
        # instead of waiting out the cooldown from this one.
        state.pop("worker_liveness", None)
        await send("The delivery worker's heartbeat has recovered.")


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
                f"reconcile the form options with the CRM "
                f"(scripts/sync_form_options.py).\n"
                f"Environment: {settings.environment}."
            )
