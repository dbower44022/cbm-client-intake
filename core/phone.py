"""Phone-number normalization for EspoCRM writes.

crm-test stores phone numbers in E.164 (e.g. +12166447439) and rejects other
formats with a phone "valid" validation failure. The intake forms collect
phone as free text, so normalize at the CRM boundary before writing a Contact.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("cbm_intake.phone")

# E.164 permits at most 15 digits; we require a practical minimum of 10 (NANP and
# most international subscriber numbers), which rejects obviously-bogus entries
# like "12345" that EspoCRM would 400 on (phone "valid" failure).
_MIN_E164_DIGITS = 10
_MAX_E164_DIGITS = 15


def to_e164(raw: str) -> str:
    """Best-effort E.164 normalization, defaulting to US (+1).

    A US 10-digit number, or an 11-digit number led by 1, becomes
    ``+1XXXXXXXXXX``. A value already starting with ``+`` keeps its country
    code. Anything else returns ``+`` plus its digits; an input with no digits
    is returned unchanged.
    """
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return raw
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    return "+" + digits


def e164_or_none(raw: Optional[str]) -> Optional[str]:
    """Normalize to E.164, or return ``None`` if the value can't be a real phone
    number (too few/many digits).

    Lets a caller OMIT an unparseable phone rather than fail the whole CRM write
    on it — EspoCRM rejects e.g. ``+12345`` with a phone "valid" 400, which would
    otherwise sink the Contact create and lose the lead. Email remains the primary
    contact channel; the raw value is still preserved in the submission audit log.
    """
    if not raw or not raw.strip():
        return None
    normalized = to_e164(raw)
    digits = re.sub(r"\D", "", normalized)
    if _MIN_E164_DIGITS <= len(digits) <= _MAX_E164_DIGITS:
        return normalized
    log.warning("dropping implausible phone %r (normalized %r)", raw, normalized)
    return None
