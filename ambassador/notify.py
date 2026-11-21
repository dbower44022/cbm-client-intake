"""Who the Ambassador Program emails, and how (PRD § 4.2 item 6, § 5.1).

Everything goes from the shared mailbox (``OPS_MAILBOX``). A CBM member is
written to at their CBM address only (``cbmEmail``), never a personal one.
An invented training address is left out (``core/sandbox_addresses``).
Every send is best-effort: a failure is logged and returned, never raised,
and the delivery guards each send with a named step so a retry never sends
it twice.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from core.espo import EspoError

from . import config as cfg

log = logging.getLogger("cbm_intake.ambassador")

Sender = Callable[[Any, list[str], str, str], Awaitable[None]]


async def send_shared(settings: Any, to: list[str], subject: str, body_html: str) -> None:
    from feedback.sending import send_shared as _send

    await _send(settings, to, subject, body_html)


def base_url(settings: Any) -> str:
    return (getattr(settings, "app_base_url", "") or "").rstrip("/")


def _deliverable(settings: Any, addresses: list[str]) -> list[str]:
    from core.sandbox_addresses import is_sandbox_address, sandbox_domain

    domain = sandbox_domain(settings) if hasattr(settings, "sandbox_address_domain") else ""
    out: list[str] = []
    for a in addresses:
        a = (a or "").strip()
        if a and not is_sandbox_address(a, domain) and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out


async def profile_mailbox(client: Any, profile_id: str) -> tuple[str, str, str]:
    """A mentor profile's CBM address, full name and first name; blanks when
    it cannot be read."""
    if not profile_id:
        return "", "", ""
    try:
        p = await client.get(cfg.MENTOR, profile_id, select="id,name,cbmEmail,firstName,lastName")
    except EspoError as exc:
        log.warning("ambassador: mentor profile %s not read: %s", profile_id, exc)
        return "", "", ""
    name = p.get("name") or ""
    first = p.get("firstName") or (name.split(" ", 1)[0] if name else "")
    return (p.get("cbmEmail") or "").strip(), name, first


async def team_mailboxes(client: Any, team_names: list[str]) -> list[str]:
    from feedback.alerts import team_addresses

    out: list[str] = []
    for team in team_names:
        out.extend(await team_addresses(client, team))
    return out


async def send(settings: Any, to: list[str], filled: dict[str, str], *, what: str,
               sender: Optional[Sender] = None) -> str:
    """Send one email; one word back: ``sent``, ``no-mailbox``,
    ``no-recipients`` or ``failed``."""
    if not (getattr(settings, "ops_mailbox", "") or "").strip():
        log.info("ambassador %s not sent: no shared mailbox", what)
        return "no-mailbox"
    recipients = _deliverable(settings, to)
    if not recipients:
        log.info("ambassador %s not sent: no recipients", what)
        return "no-recipients"
    try:
        await (sender or send_shared)(settings, recipients, filled["subject"], filled["bodyHtml"])
    except Exception as exc:  # noqa: BLE001 — best-effort, logged
        log.warning("ambassador %s failed: %s", what, exc)
        return "failed"
    log.info("ambassador %s sent (%d)", what, len(recipients))
    return "sent"
