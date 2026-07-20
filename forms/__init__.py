"""Per-form modules. Each subpackage exposes a ``SPEC`` (core.forms.FormSpec).

``ALL_SPECS`` / ``SPECS_BY_SLUG`` are the single registry used by the web app
(`main.py`) and the delivery worker (`worker.py`).
"""

from . import client_intake, info_email, info_request, partner, sponsor, volunteer

ALL_SPECS = [
    client_intake.SPEC,
    volunteer.SPEC,
    info_request.SPEC,
    partner.SPEC,
    sponsor.SPEC,
]

# Delivered by the worker but NEVER mounted as a public form/endpoint: these
# submissions are captured by the inbound info@ mailbox poller (ops/inbound.py)
# and approved by staff in /ops — an HTTP POST must not be able to fake one.
DELIVERY_ONLY_SPECS = [info_email.SPEC]

SPECS_BY_SLUG = {spec.slug: spec for spec in ALL_SPECS + DELIVERY_ONLY_SPECS}
