"""Per-form modules. Each subpackage exposes a ``SPEC`` (core.forms.FormSpec).

``ALL_SPECS`` / ``SPECS_BY_SLUG`` are the single registry used by the web app
(`main.py`) and the delivery worker (`worker.py`).
"""

from . import (
    client_intake,
    event_registration,
    info_email,
    info_request,
    partner,
    sponsor,
    volunteer,
)

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

# Event registrations arrive at POST /api/events/{slug}/register (which needs
# the event slug from the URL), not at the generic /api/{slug}/intake route, so
# the spec is registered for DELIVERY only. The worker, /ops redrive and the
# resumable machinery all work exactly as they do for the public forms.
DELIVERY_ONLY_SPECS.append(event_registration.SPEC)

SPECS_BY_SLUG = {spec.slug: spec for spec in ALL_SPECS + DELIVERY_ONLY_SPECS}
