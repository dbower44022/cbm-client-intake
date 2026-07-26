"""Self-service cancellation tokens (EV-16).

A registrant must be able to cancel from a link in their email, with no login.
The link therefore carries a token that proves "the holder of this link was sent
it for this registration" — and nothing else.

**Derived, not stored.** The token is an HMAC of the registration id keyed by the
app secret, so there is no table to keep, nothing to expire, and no extra CRM
field. Rotating ``SESSION_SECRET`` invalidates every outstanding cancel link,
which is the correct behaviour for a secret rotation.

Compared in constant time (EV-83), and the id is carried in the clear alongside
the signature so a tampered token fails signature verification rather than
resolving to someone else's registration.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

_PURPOSE = b"cbm-event-registration-cancel-v1"
#: Enough to make guessing hopeless without making the URL unwieldy.
_DIGEST_CHARS = 32


class TokenError(ValueError):
    """The token is malformed, unsigned, or signed with a different secret."""


def _signature(registration_id: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), _PURPOSE + registration_id.encode(), hashlib.sha256)
    return mac.hexdigest()[:_DIGEST_CHARS]


def make_cancel_token(registration_id: str, secret: str) -> str:
    """``<registration id>.<signature>`` — safe to put in a URL."""
    if not secret:
        raise TokenError("No app secret is configured; cancel links cannot be signed.")
    if not registration_id:
        raise TokenError("A registration id is required.")
    return f"{registration_id}.{_signature(registration_id, secret)}"


def read_cancel_token(token: str, secret: str) -> str:
    """The registration id a valid token refers to.

    Raises :class:`TokenError` for anything that doesn't verify — the caller
    turns that into the same generic "this link is not valid" response for every
    failure mode, so the endpoint can't be used to probe which ids exist.
    """
    if not secret:
        raise TokenError("No app secret is configured.")
    if not token or "." not in token:
        raise TokenError("Malformed cancellation link.")
    registration_id, _, signature = token.rpartition(".")
    if not registration_id or not signature:
        raise TokenError("Malformed cancellation link.")
    if not hmac.compare_digest(signature, _signature(registration_id, secret)):
        raise TokenError("This cancellation link is not valid.")
    return registration_id


def cancel_url(registration_id: str, secret: str, base_url: str) -> Optional[str]:
    """The full self-service cancel URL, or None when it can't be signed."""
    try:
        token = make_cancel_token(registration_id, secret)
    except TokenError:
        return None
    return f"{base_url.rstrip('/')}/api/events/registrations/{token}/cancel"
