"""Invented training addresses never leave the system.

A deployment that holds invented training data names the domain its invented
addresses sit on in ``SANDBOX_ADDRESS_DOMAIN`` (System Settings → Email). The
domain has no mailboxes, so a mentor's own send or calendar invitation already
fails at Google. This module stops the paths that do NOT go out as the
mentor's own address: a send as the shared mailbox, a Drive share, a Google
group membership and the mailing service's lists. Each of those four calls
:func:`is_sandbox_address` at the last step before it reaches outside.

Why a setting and not the CRM's address: the Business Mentors Association's
system is a real chapter AND the training system (Association rulings 72 and
77), so its shared mailbox, Drive and group stay switched on, and only the
invented addresses must be kept in. Empty (the default) changes nothing.

Read per call through :func:`core.config.get_settings`, so a change at
``/setup`` applies at once.
"""

from __future__ import annotations

from email.utils import getaddresses
from typing import Iterable, Optional


def sandbox_domain(settings: Optional[object] = None) -> str:
    """The configured sandbox address domain, lower-case, or ``""``."""
    if settings is None:
        from .config import get_settings

        settings = get_settings()
    return (getattr(settings, "sandbox_address_domain", "") or "").strip().lower().lstrip("@.")


def is_sandbox_address(address: str, domain: Optional[str] = None) -> bool:
    """True when ``address`` is on the sandbox domain or one of its subdomains.

    ``domain`` defaults to the live setting. An empty setting matches nothing.
    """
    domain = sandbox_domain() if domain is None else domain.strip().lower().lstrip("@.")
    if not domain:
        return False
    _, _, host = (address or "").strip().lower().rpartition("@")
    host = host.rstrip(">").strip()
    return bool(host) and (host == domain or host.endswith("." + domain))


def sandbox_recipients(headers: Iterable[str], domain: Optional[str] = None) -> list[str]:
    """Every address in the given To/Cc/Bcc header values that is a sandbox address."""
    domain = sandbox_domain() if domain is None else domain
    if not domain:
        return []
    found = []
    for _, address in getaddresses([h for h in headers if h]):
        if address and is_sandbox_address(address, domain):
            found.append(address)
    return found


def refusal(address: str, domain: Optional[str] = None) -> str:
    """The one sentence every refusal uses, so the four places read alike."""
    domain = sandbox_domain() if domain is None else domain
    return (f"{address} is an invented training address (on {domain}), and this system "
            f"never sends to, shares with or lists one. System Settings → Email → "
            f"Sandbox address domain.")
