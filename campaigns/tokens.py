"""Tokens printed on things: a link's short address and a card's own scan token.

Both come from ``secrets`` with the ambiguous glyphs removed (0/O, 1/l/I), so a
printed card or a text message can be read back by a person (build plan § 3.7,
§ 1.4). Neither is ever a record id: the card carries no CRM id in the clear.
"""

from __future__ import annotations

import re
import secrets

#: Crockford-style: digits and letters without 0, O, 1, I, l.
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
LINK_TOKEN_LENGTH = 8
SCAN_TOKEN_LENGTH = 12
_VALID = re.compile(r"^[a-z0-9]{6,16}$")


def new_token(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def new_link_token() -> str:
    return new_token(LINK_TOKEN_LENGTH)


def new_scan_token() -> str:
    return new_token(SCAN_TOKEN_LENGTH)


def looks_like_token(value: str) -> bool:
    """Cheap shape check before any lookup — so a probing request with a
    malformed token costs no database or CRM read."""
    return bool(value) and bool(_VALID.match(value.lower()))
