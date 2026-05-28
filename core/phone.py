"""Phone-number normalization for EspoCRM writes.

crm-test stores phone numbers in E.164 (e.g. +12166447439) and rejects other
formats with a phone "valid" validation failure. The intake forms collect
phone as free text, so normalize at the CRM boundary before writing a Contact.
"""

from __future__ import annotations

import re


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
